"""
Cliente assíncrono oficial para geração de fotos da Marina Salles (v3.7.0).
Executa exclusivamente em infraestrutura com GPU dedicada (RTX 4090 / FLUX.1 Dev FP8)
com gestão automática do ciclo de vida da GPU (liga sob demanda, renderiza e pausa imediatamente para economizar créditos).
Inclui pipeline calibrado de LoRAs (marina_flux, NSFW_master, roundassv16, FluxSideboob, Hand_v2).
"""
import io
import os
import re
import json
import random
import base64
import logging
import asyncio
import aiohttp
from PIL import Image
from config import settings
from prompts import build_flux_prompt
from visual_profile import visual_profile, MARINA_VISUAL_DNA_BASE
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PhotoGenerationResult:
    """Per-call generation metadata — never share across concurrent requests."""

    image: Optional[io.BytesIO]
    full_prompt: str = ""
    scene_tags: str = ""
    is_nsfw: bool = False
    focus_angle: str = "frontal"
    place_key: str = ""
    world_snapshot_id: Optional[int] = None


CLOTHED_KEYWORDS = [
    "vestida", "roupa", "com roupa", "de roupa", "vestido", "calça", "short", "shorts",
    "blusa", "camisa", "camiseta", "casaco", "moletom", "pijama", "look", "lookinho",
    "clothed", "fully clothed", "dressed", "outfit", "suit", "jacket", "jeans"
]

NSFW_KEYWORDS = [
    "pelada", "nua", "sem roupa", "nude", "nudes", "naked", "topless",
    "seios", "peito", "peitos", "teta", "tetas", "mamilo", "mamilos",
    "calcinha", "sutiã", "sutia", "lingerie", "biquini", "biquíni", "bikini",
    "vagina", "pussy", "safada", "buceta", "bunda", "ass", "boobs", "breasts", "undies", "panties"
]

ROUNDASS_KEYWORDS = ["ass", "bunda", "costas", "behind", "from behind", "back view", "calcinha de costas"]
SIDEBOOB_KEYWORDS = ["sideboob", "side view", "lateral", "decote lateral", "de lado"]
MIRROR_SELFIE_KEYWORDS = ["espelho", "mirror", "selfie no espelho", "mirror selfie", "segurando celular", "na frente do espelho", "candid mirror"]


# Resolução padrão calibrada para FLUX.1 Dev vertical
PHOTO_WIDTH = 832
PHOTO_HEIGHT = 1216
PHOTO_STEPS = 24


class ImageGeneratorClient:
    def __init__(self, novita_key: str = settings.NOVITA_API_KEY, base_url: str = settings.SD_API_URL):
        self.novita_key = novita_key
        self.base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        # Instância dedicada RTX 4090 rodando ComfyUI oficial na porta 8188
        self.instance_id = os.getenv("NOVITA_INSTANCE_ID", "e70d0a62c99c2402").strip().strip('"')
        self.comfyui_url = (
            os.getenv("COMFYUI_URL", "").strip().strip('"')
            or f"https://{self.instance_id}-8188.us-ca-6.gpu-instance.novita.ai"
        )
        self._lock = asyncio.Semaphore(1)

    async def is_online(self) -> bool:
        if settings.IMAGE_ENGINE == "novita" and self.novita_key:
            return True
        check_url = f"{self.base_url}sdapi/v1/options"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(check_url) as response:
                    return response.status == 200
        except Exception:
            return False

    def is_nsfw_request(self, text: str) -> bool:
        return visual_profile.is_nsfw_text(text)


    async def _ensure_instance_running(self, session: aiohttp.ClientSession) -> bool:
        """Verifica se a GPU está online. Se pausada, liga via API PUT e aguarda o ComfyUI."""
        headers = {
            "Authorization": f"Bearer {self.novita_key}",
            "Content-Type": "application/json"
        }
        inst_url = f"https://api.novita.ai/gpus/v2/instances/{self.instance_id}"
        
        try:
            async with session.get(inst_url, headers=headers) as r:
                if r.status == 200:
                    d = await r.json()
                    status = d.get("status", {}).get("status")
                    if status == "running":
                        try:
                            async with session.get(f"{self.comfyui_url}/system_stats", headers=headers, timeout=3) as cs:
                                if cs.status == 200:
                                    logger.info("Instância GPU já estava rodando e ComfyUI pronto.")
                                    return True
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Erro ao verificar status da instância GPU: {e}")

        logger.info(f"⚡ Ligando instância GPU RTX 4090 ({self.instance_id}) para gerar foto...")
        start_url = f"https://api.novita.ai/gpus/v2/instances/{self.instance_id}/start"
        try:
            async with session.put(start_url, headers=headers, json={}) as start_resp:
                if start_resp.status not in (200, 201):
                    logger.error(f"Falha ao chamar start na instância Novita ({start_resp.status})")
                    return False
        except Exception as e:
            logger.error(f"Exceção ao ligar instância GPU: {e}")
            return False

        # Aguarda status 'running' e ComfyUI ativo (geralmente 10-25s)
        for attempt in range(30):
            await asyncio.sleep(2.5)
            try:
                async with session.get(inst_url, headers=headers) as check_r:
                    if check_r.status == 200:
                        c_data = await check_r.json()
                        st = c_data.get("status", {}).get("status")
                        if st == "running":
                            try:
                                async with session.get(f"{self.comfyui_url}/system_stats", headers=headers, timeout=3) as cs:
                                    if cs.status == 200:
                                        logger.info(f"✅ Instância GPU online e ComfyUI pronto em ~{int(attempt*2.5)}s!")
                                        return True
                            except Exception:
                                pass
            except Exception:
                pass

        logger.error("Timeout aguardando inicialização da instância GPU Novita.")
        return False

    async def _stop_instance(self, session: aiohttp.ClientSession) -> None:
        """Pausa imediatamente a instância GPU para não gastar créditos."""
        headers = {
            "Authorization": f"Bearer {self.novita_key}",
            "Content-Type": "application/json"
        }
        stop_url = f"https://api.novita.ai/gpus/v2/instances/{self.instance_id}/stop"
        try:
            logger.info(f"⏸️ Pausando instância GPU ({self.instance_id}) para proteger os créditos...")
            async with session.put(stop_url, headers=headers, json={}) as resp:
                if resp.status == 200:
                    logger.info("✅ Instância pausada com sucesso! Créditos protegidos.")
                else:
                    logger.warning(f"Resposta ao pausar ({resp.status}): {await resp.text()}")
        except Exception as e:
            logger.error(f"Erro ao pausar instância GPU: {e}")

    def _build_comfyui_workflow(
        self,
        prompt_text: str,
        is_nsfw: bool = False,
        focus_angle: str = "frontal",
        is_mirror_selfie: bool = False
    ) -> tuple[dict, str]:
        """
        Monta workflow ComfyUI FLUX.1 Dev FP8 oficial (UNET + DualCLIP + Cadeia de LoRAs calibrada).
        NUNCA utiliza Schnell. Respeita identidade, anatomia explícita, realismo de iPhone e micro-texturas naturais.
        """

        seed = random.randint(1, 999999999)
        workflow = {}
        n = 1

        # 1. UNET FLUX.1 Dev FP8 (EXCLUSIVO)
        unet_id = str(n)
        workflow[unet_id] = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "flux1-dev-fp8.safetensors",
                "weight_dtype": "default"
            }
        }
        n += 1

        # 2. DualCLIP (T5-XXL + CLIP-L)
        clip_loader_id = str(n)
        workflow[clip_loader_id] = {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "t5xxl_fp8_e4m3fn.safetensors",
                "clip_name2": "clip_l.safetensors",
                "type": "flux"
            }
        }
        n += 1

        # 3. LoRA 1: Identidade da Marina (Marina Sweet) - Peso 1.0 para fidelidade facial/corporal absoluta
        marina_id = str(n)
        workflow[marina_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": [unet_id, 0],
                "clip": [clip_loader_id, 0],
                "lora_name": "marina_flux.safetensors",
                "strength_model": 1.0,
                "strength_clip": 1.0
            }
        }
        current_model = [marina_id, 0]
        current_clip = [marina_id, 1]
        n += 1

        # 4. LoRA 2: iPhone Photo Booster (Realismo de Smartphone para todas as fotos)
        if settings.IPHONE_LORAS_ENABLED and settings.IPHONE_PHOTO_LORA_NAME:
            lora_iphone_boost_id = str(n)
            workflow[lora_iphone_boost_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": current_model,
                    "clip": current_clip,
                    "lora_name": settings.IPHONE_PHOTO_LORA_NAME,
                    "strength_model": 0.60,
                    "strength_clip": 0.60
                }
            }
            current_model = [lora_iphone_boost_id, 0]
            current_clip = [lora_iphone_boost_id, 1]
            n += 1

        # 5. LoRA 3: NSFW Master (Anatomia sem censura - mamilos eretos, aréolas, genitália)
        if is_nsfw:
            lora_nsfw_id = str(n)
            workflow[lora_nsfw_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": current_model,
                    "clip": current_clip,
                    "lora_name": "NSFW_master.safetensors",
                    "strength_model": 0.80,
                    "strength_clip": 0.80
                }
            }
            current_model = [lora_nsfw_id, 0]
            current_clip = [lora_nsfw_id, 1]
            n += 1

        # 6. LoRA 4: Ângulo / Curvas (Roundass de costas ou Sideboob de lado)
        if focus_angle == "behind":
            lora_angle_id = str(n)
            workflow[lora_angle_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": current_model,
                    "clip": current_clip,
                    "lora_name": "roundassv16_FLUX.safetensors",
                    "strength_model": 0.65,
                    "strength_clip": 0.65
                }
            }
            current_model = [lora_angle_id, 0]
            current_clip = [lora_angle_id, 1]
            n += 1
        elif focus_angle == "side":
            lora_side_id = str(n)
            workflow[lora_side_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": current_model,
                    "clip": current_clip,
                    "lora_name": "FluxSideboob-E3.safetensors",
                    "strength_model": 0.60,
                    "strength_clip": 0.60
                }
            }
            current_model = [lora_side_id, 0]
            current_clip = [lora_side_id, 1]
            n += 1

        # 7. LoRA 5: Mãos / Mirror Selfie / Aparelho iPhone 16 Pro
        if settings.IPHONE_LORAS_ENABLED and is_mirror_selfie:
            # 7.1 LoRA Mirror Selfie (Coerência anatômica da mão segurando o celular no espelho)
            lora_mirror_id = str(n)
            workflow[lora_mirror_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": current_model,
                    "clip": current_clip,
                    "lora_name": settings.MIRROR_SELFIE_LORA_NAME,
                    "strength_model": 0.65,
                    "strength_clip": 0.65
                }
            }
            current_model = [lora_mirror_id, 0]
            current_clip = [lora_mirror_id, 1]
            n += 1

            # 7.2 LoRA iPhone 16 Pro (Aparelho preto realista com 3 lentes de safira)
            lora_device_id = str(n)
            workflow[lora_device_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": current_model,
                    "clip": current_clip,
                    "lora_name": settings.IPHONE_DEVICE_LORA_NAME,
                    "strength_model": 0.65,
                    "strength_clip": 0.65
                }
            }
            current_model = [lora_device_id, 0]
            current_clip = [lora_device_id, 1]
            n += 1
        else:
            # Mãos anatômicas padrão Hand_v2
            lora_hand_id = str(n)
            workflow[lora_hand_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": current_model,
                    "clip": current_clip,
                    "lora_name": "Hand_v2.safetensors",
                    "strength_model": 0.50,
                    "strength_clip": 0.50
                }
            }
            current_model = [lora_hand_id, 0]
            current_clip = [lora_hand_id, 1]
            n += 1

        # 8. Prompt Positivo
        clip_id = str(n)
        workflow[clip_id] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": current_clip, "text": prompt_text}
        }

        n += 1

        # 8. Flux Guidance (calibrado para 3.5 em FLUX Dev)
        guide_id = str(n)
        workflow[guide_id] = {
            "class_type": "FluxGuidance",
            "inputs": {"conditioning": [clip_id, 0], "guidance": 3.5}
        }
        n += 1

        # 9. Latent Image (832 x 1216)
        latent_id = str(n)
        workflow[latent_id] = {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": PHOTO_WIDTH, "height": PHOTO_HEIGHT, "batch_size": 1}
        }
        n += 1

        # 10. KSampler FLUX Dev (Euler / Simple, 24 passos)
        sampler_id = str(n)
        workflow[sampler_id] = {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": PHOTO_STEPS,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": current_model,
                "positive": [guide_id, 0],
                "negative": [clip_id, 0],
                "latent_image": [latent_id, 0]
            }
        }
        n += 1

        # 11. VAE Loader
        vae_id = str(n)
        workflow[vae_id] = {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "flux_ae.safetensors"}
        }
        n += 1

        # 12. VAE Decode
        decode_id = str(n)
        workflow[decode_id] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": [sampler_id, 0], "vae": [vae_id, 0]}
        }
        n += 1

        # 13. Save Image
        save_id = str(n)
        workflow[save_id] = {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "Marina_Seltin_Dev", "images": [decode_id, 0]}
        }

        return workflow, save_id

    async def generate_photo(self, scene_description: str, user_intent: str = "") -> io.BytesIO | None:
        """Legacy contract: returns image bytes only. Does not persist camera continuity.

        Avatars, failed attempts and callers that never send to Telegram must not
        mutate camera_last_state. Prefer generate_photo_with_context() when the
        bot needs metadata and will record after a confirmed send_photo.
        """
        result = await self.generate_photo_with_context(scene_description, user_intent=user_intent)
        return result.image

    async def generate_photo_with_context(
        self,
        scene_description: str,
        user_intent: str = "",
        *,
        place_key: str = "",
        world_snapshot_id: Optional[int] = None,
        require_world_match: bool = False,
        current_place_key: Optional[str] = None,
    ) -> PhotoGenerationResult:
        """Generate a photo and return per-call metadata without recording continuity."""
        async with self._lock:
            full_prompt, is_nsfw, focus_angle = visual_profile.build_scene_prompt(
                scene_description=scene_description,
                user_intent=user_intent,
                current_place_key=current_place_key if require_world_match else None,
                require_world_match=require_world_match,
            )
            logger.info(
                f"📸 Gerando foto da Marina (FLUX.1 Dev): is_nsfw={is_nsfw} "
                f"angle={focus_angle} | prompt='{full_prompt[:80]}...'"
            )

            img = None
            if settings.IMAGE_ENGINE == "novita" and self.novita_key:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                    try:
                        ready = await self._ensure_instance_running(session)
                        if not ready:
                            logger.error("Instância GPU não iniciou a tempo.")
                            return PhotoGenerationResult(
                                image=None, full_prompt=full_prompt, scene_tags=scene_description,
                                is_nsfw=is_nsfw, focus_angle=focus_angle,
                                place_key=place_key, world_snapshot_id=world_snapshot_id,
                            )

                        is_mirror = any(
                            kw in scene_description.lower() or kw in user_intent.lower()
                            for kw in MIRROR_SELFIE_KEYWORDS
                        )
                        img = await self._generate_novita_comfyui(
                            session,
                            full_prompt,
                            is_nsfw=is_nsfw,
                            focus_angle=focus_angle,
                            is_mirror_selfie=is_mirror,
                        )
                    except Exception as e:
                        logger.error(f"Falha na geração ComfyUI Novita: {e}", exc_info=True)
                    finally:
                        await self._stop_instance(session)

            if not img:
                logger.warning("Tentando fallback para SD local...")
                img = await self._generate_local_sd(full_prompt)

            return PhotoGenerationResult(
                image=img,
                full_prompt=full_prompt,
                scene_tags=scene_description,
                is_nsfw=is_nsfw,
                focus_angle=focus_angle,
                place_key=place_key,
                world_snapshot_id=world_snapshot_id,
            )

    async def _generate_novita_comfyui(
        self,
        session: aiohttp.ClientSession,
        prompt_text: str,
        is_nsfw: bool = False,
        focus_angle: str = "frontal",
        is_mirror_selfie: bool = False
    ) -> io.BytesIO | None:
        workflow, save_id = self._build_comfyui_workflow(
            prompt_text,
            is_nsfw=is_nsfw,
            focus_angle=focus_angle,
            is_mirror_selfie=is_mirror_selfie
        )

        headers = {
            "Authorization": f"Bearer {self.novita_key}",
            "Content-Type": "application/json"
        }
        prompt_url = f"{self.comfyui_url}/prompt"
        logger.info(f"Disparando geração ComfyUI na RTX 4090: {prompt_url}")

        try:
            async with session.post(prompt_url, headers=headers, json={"prompt": workflow}) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    logger.error(f"Erro ao submeter workflow ComfyUI ({resp.status}): {err_text[:300]}")
                    return None
                data = await resp.json()
                prompt_id = data.get("prompt_id")
        except Exception as e:
            logger.error(f"Falha ao conectar no ComfyUI {prompt_url}: {e}")
            return None

        if not prompt_id:
            logger.error("Nenhum prompt_id retornado pelo ComfyUI")
            return None

        logger.info(f"ComfyUI prompt_id={prompt_id} aguardando renderização FLUX Dev...")
        history_url = f"{self.comfyui_url}/history/{prompt_id}"

        for attempt in range(90):
            await asyncio.sleep(2.0)
            try:
                async with session.get(history_url, headers=headers) as h_resp:
                    if h_resp.status != 200:
                        continue
                    h_data = await h_resp.json()
            except Exception as e:
                logger.warning(f"Poll ComfyUI erro: {e}")
                continue

            if prompt_id in h_data:
                prompt_info = h_data[prompt_id]
                outputs = prompt_info.get("outputs", {})
                if save_id in outputs and "images" in outputs[save_id]:
                    imgs = outputs[save_id]["images"]
                    if imgs:
                        fname = imgs[0].get("filename")
                        view_url = f"{self.comfyui_url}/view?filename={fname}&type=output"
                        logger.info(f"Renderização concluída! Baixando {fname}...")
                        async with session.get(view_url, headers=headers) as v_resp:
                            if v_resp.status == 200:
                                img_bytes = await v_resp.read()
                                logger.info(f"Foto oficial da Marina recebida com sucesso ({len(img_bytes)} bytes)!")
                                return io.BytesIO(img_bytes)

                status_info = prompt_info.get("status", {})
                if status_info.get("status_str") == "error":
                    logger.error(f"ComfyUI execution error: {status_info}")
                    return None

        logger.error(f"Timeout aguardando renderização do prompt {prompt_id}")
        return None

    async def generate_avatar(self, look_style: str = "fofa") -> tuple[io.BytesIO | None, io.BytesIO | None]:
        """
        Gera uma foto de perfil 100% VESTIDA (SFW), com enquadramento perfeito de modelo.
        Garante zero nudez e foco absoluto no rosto radiante da Marina Salles.
        """
        if look_style == "estilosa":
            clothing_tag = "wearing a stylish emerald green silk blouse, elegant gold necklace, confident charming smile"
        elif look_style == "fofa":
            clothing_tag = "wearing a cute pastel pink ribbed fitted crewneck top, delicate silver necklace, sweet warm smiling expression"
        else:
            clothing_tag = "wearing a chic classic white fitted crewneck top, fashionable necklace, fresh radiant smile"

        avatar_prompt = (
            f"candid close-up portrait of {MARINA_VISUAL_DNA_BASE}, fully clothed, {clothing_tag}, "
            "looking directly into camera, soft flattering natural apartment lighting, shallow depth of field, "
            "professional model portrait, modest covered neckline, zero nudity, perfectly clothed"
        )


        raw_img = await self.generate_photo(avatar_prompt)
        if not raw_img:
            return None, None

        try:
            raw_bytes = raw_img.getvalue()
            with Image.open(io.BytesIO(raw_bytes)) as im:
                w, h = im.size
                crop_size = min(w, h)
                left = (w - crop_size) // 2
                top = int(h * 0.02)
                right = left + crop_size
                bottom = top + crop_size
                if bottom > h:
                    bottom = h
                    top = max(0, bottom - crop_size)

                cropped = im.crop((left, top, right, bottom))
                cropped = cropped.resize((640, 640), Image.Resampling.LANCZOS)

                jpg_buf = io.BytesIO()
                cropped.convert("RGB").save(jpg_buf, format="JPEG", quality=95)
                jpg_buf.seek(0)

                return jpg_buf, io.BytesIO(raw_bytes)
        except Exception as e:
            logger.error(f"Erro ao processar avatar: {e}")
            return None, raw_img

    async def _generate_local_sd(self, full_prompt: str) -> io.BytesIO | None:
        payload = {
            "prompt": full_prompt,
            "negative_prompt": "blurry, low quality, deformed, bad hands",
            "steps": 20,
            "cfg_scale": 7.0,
            "width": 512,
            "height": 768,
            "sampler_name": "Euler a",
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
                async with session.post(f"{self.base_url}sdapi/v1/txt2img", json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return io.BytesIO(base64.b64decode(data["images"][0].split(",")[-1]))
        except Exception as e:
            logger.error(f"Erro no fallback local do SD: {e}")
        return None


sd_client = ImageGeneratorClient()
