"""
Cliente de fotos da Marina (v3.7.1): gera pelo Civitai (Krea 2 + LoRA dela, civitai_images).

24/09: a GPU da Novita (ComfyUI + FLUX.1 Dev) e o SD local saíram — a Novita só
cuida da voz agora. A continuidade de câmera e o prompt ficam no visual_profile.
"""
import io
import logging
import asyncio
from PIL import Image
from config import settings
from visual_profile import visual_profile
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


MIRROR_SELFIE_KEYWORDS = ["espelho", "mirror", "selfie no espelho", "mirror selfie", "segurando celular", "na frente do espelho", "candid mirror"]


class ImageGeneratorClient:
    def __init__(self):
        self._lock = asyncio.Semaphore(1)

    async def is_online(self) -> bool:
        import civitai_images
        return civitai_images.available()

    def is_nsfw_request(self, text: str) -> bool:
        return visual_profile.is_nsfw_text(text)

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
        if getattr(settings, 'PHOTO_PROVIDER_MAINTENANCE', False):
            logger.info('PHOTO_PROVIDER_MAINTENANCE: generation unavailable; nothing sent to Civitai')
            return PhotoGenerationResult(image=None)
        async with self._lock:
            full_prompt, is_nsfw, focus_angle = visual_profile.build_scene_prompt(
                scene_description=scene_description,
                user_intent=user_intent,
                current_place_key=current_place_key if require_world_match else None,
                require_world_match=require_world_match,
            )
            logger.info(
                f"📸 Gerando foto da Marina (Civitai Krea 2): is_nsfw={is_nsfw} "
                f"angle={focus_angle} | prompt='{full_prompt[:80]}...'"
            )

            is_mirror = any(
                kw in scene_description.lower() or kw in user_intent.lower()
                for kw in MIRROR_SELFIE_KEYWORDS
            )
            import civitai_images
            img = await civitai_images.generate(full_prompt, is_nsfw=is_nsfw, focus_angle=focus_angle,
                                                is_mirror_selfie=is_mirror)

            return PhotoGenerationResult(
                image=img,
                full_prompt=full_prompt,
                scene_tags=scene_description,
                is_nsfw=is_nsfw,
                focus_angle=focus_angle,
                place_key=place_key,
                world_snapshot_id=world_snapshot_id,
            )

    async def generate_directed(self, shot, *, world_snapshot_id: Optional[int] = None) -> PhotoGenerationResult:
        """Foto decidida pelo diretor de cena (photo_director): o prompt já vem pronto."""
        if getattr(settings, 'PHOTO_PROVIDER_MAINTENANCE', False):
            return PhotoGenerationResult(image=None)
        async with self._lock:
            import civitai_images
            prompt = shot.prompt
            img = await civitai_images.generate(prompt, is_nsfw=shot.is_nsfw, focus_angle=shot.focus_angle,
                                                seed=shot.seed, lora_weights=shot.lora_weights,
                                                pov=getattr(shot, "pov", False))
            if img is None and not shot.is_nsfw and civitai_images.ultima_recusa_sfw:
                # Soak, dia 4 (02/10): o moderador recusou a selfie normal pela expressão sensual; vai com um sorriso.
                import photo_director
                suave = photo_director.suavizar(prompt)
                if suave:
                    logger.info("civitai.refaz_sem_expressao pose=%s", shot.pose_id)
                    prompt = suave
                    img = await civitai_images.generate(prompt, is_nsfw=False, focus_angle=shot.focus_angle,
                                                        seed=shot.seed, lora_weights=shot.lora_weights,
                                                        pov=getattr(shot, "pov", False))
            friend = getattr(shot, "friend", "")
            if img is not None and friend:
                # 28/09: foto de grupo — o rosto da amiga vira o da foto-RG dela (Krea 2 Edit, só o lado dela).
                # Se a troca falhar, vai a foto como saiu (a amiga descrita no texto, com ar de parente).
                swapped = await civitai_images.swap_friend_face(img.getvalue(), friend,
                                                                side=getattr(shot, "friend_side", "right"),
                                                                is_nsfw=shot.is_nsfw)
                if swapped:
                    img = io.BytesIO(swapped)
                else:
                    logger.warning("foto de grupo sem a troca de rosto (%s)", friend)
        return PhotoGenerationResult(image=img, full_prompt=prompt, scene_tags=shot.pose_id,
                                     is_nsfw=shot.is_nsfw, focus_angle=shot.focus_angle,
                                     place_key=shot.place_key, world_snapshot_id=world_snapshot_id)

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
            f"close-up portrait, head and shoulders, {clothing_tag}, looking directly into the camera, "
            "soft flattering natural apartment lighting, shallow depth of field"
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


sd_client = ImageGeneratorClient()
