"""Geração de fotos da Marina pelo Civitai (Orchestration API).

24/09: a Novita ficou sem GPU disponível para alugar (nem trocando de região),
e o Patrick propôs o Civitai — onde o LoRA da Marina foi treinado. Aqui não
se aluga máquina: cada foto é um "workflow" pago em Buzz (~10 Buzz ≈ 1 centavo
de dólar no motor comfy, medido com whatif em 24/09).

Mesmo pipeline do ComfyUI da Novita (sd_client._build_comfyui_workflow):
Flux.1 Dev + LoRA da Marina 1.0 + iPhone Photo 0.6 + NSFW Master 0.8 (adulto) +
curvas de costas/lado + mirror selfie/iPhone 16 Pro ou mãos, 24 passos,
guidance 3.5, euler/simple, 832×1216. Os LoRAs são referenciados por AIR
(todos achados no Civitai em 24/09; o da Marina é da conta do Patrick).

Conteúdo adulto: `allowMatureContent` + Buzz amarelo (comprado). As saídas
adultas às vezes não abrem pela URL assinada (redirecionam pra
/blobs/blocked → 403); o download é feito pelo endpoint autenticado
/v2/consumer/blobs/{id}, com o token.
"""
from __future__ import annotations

import asyncio
import io
import logging
import random
from typing import Optional

import aiohttp

logger = logging.getLogger("CivitaiImages")

BASE_URL = "https://orchestration.civitai.com"
FLUX_DEV = "urn:air:flux1:checkpoint:civitai:618692@691639"
USER_AGENT = "marin-telegram-bot"
TERMINAL = {"succeeded", "failed", "expired", "canceled", "cancelled"}
POLL_S = 3.0
TIMEOUT_S = 240
ALLOW_LIVE_IN_TESTS = False

# AIR de cada LoRA do pipeline (sobrescrevível pelo .env: CIVITAI_LORA_<NOME>).
LORAS = {
    "marina": "urn:air:flux1:lora:civitai:2936925@3324653",       # marina_flux (conta psrxxx)
    "iphone_photo": "urn:air:flux1:lora:civitai:738556@967140",   # iPhone Photo (Realism booster)
    "nsfw_master": "urn:air:flux1:lora:civitai:667086@746602",    # NSFW_master.safetensors
    "roundass": "urn:air:flux1:lora:civitai:131822@1041921",      # roundassv16_FLUX.safetensors
    "sideboob": "urn:air:flux1:lora:civitai:454099@766170",       # FluxSideboob-E3.safetensors
    "mirror_selfie": "urn:air:flux1:lora:civitai:1604908@1816152",
    "iphone_device": "urn:air:flux1:lora:civitai:1809535@2047801",
    "hands": "urn:air:flux1:lora:civitai:200255@804967",          # "Hand v2.safetensors"
}


def _settings():
    from config import settings
    return settings


def _air(name: str) -> str:
    return (getattr(_settings(), f"CIVITAI_LORA_{name.upper()}", "") or "").strip() or LORAS[name]


def select_loras(*, is_nsfw: bool, focus_angle: str = "frontal", is_mirror_selfie: bool = False) -> dict:
    """Os mesmos LoRAs e pesos do workflow da Novita, por AIR."""
    s = _settings()
    iphone = bool(getattr(s, "IPHONE_LORAS_ENABLED", False))
    loras = {_air("marina"): 1.0}
    if iphone:
        loras[_air("iphone_photo")] = 0.6
    if is_nsfw:
        loras[_air("nsfw_master")] = 0.8
    if focus_angle == "behind":
        loras[_air("roundass")] = 0.65
    elif focus_angle == "side":
        loras[_air("sideboob")] = 0.6
    if iphone and is_mirror_selfie:
        loras[_air("mirror_selfie")] = 0.65
        loras[_air("iphone_device")] = 0.65
    else:
        loras[_air("hands")] = 0.5
    return loras


def build_workflow(prompt: str, loras: dict, *, is_nsfw: bool, width: int = 832, height: int = 1216,
                   steps: int = 24, seed: Optional[int] = None) -> dict:
    body = {
        "steps": [{
            "$type": "imageGen",
            "input": {
                "engine": "comfy", "ecosystem": "flux1", "operation": "createImage",
                "model": FLUX_DEV, "prompt": prompt, "width": width, "height": height,
                "steps": steps, "cfgScale": 3.5, "sampler": "euler", "scheduler": "simple",
                "seed": seed if seed is not None else random.randint(1, 2**31 - 1),
                "quantity": 1, "loras": loras,
            },
        }],
        "allowMatureContent": bool(is_nsfw),
    }
    if is_nsfw:
        body["currencies"] = ["yellow"]   # conteúdo adulto só com Buzz amarelo (comprado)
    return body


def _token() -> str:
    return (getattr(_settings(), "CIVITAI_API_KEY", "") or "").strip().strip('"')


def available() -> bool:
    if not _token():
        return False
    from db import _running_under_tests
    return not (_running_under_tests() and not ALLOW_LIVE_IN_TESTS)


def _images(workflow: dict) -> list[dict]:
    out = []
    for step in workflow.get("steps") or []:
        output = step.get("output") or {}
        out += output.get("images") or output.get("blobs") or []
    return out


async def generate(prompt: str, *, is_nsfw: bool, focus_angle: str = "frontal",
                   is_mirror_selfie: bool = False, session: Optional[aiohttp.ClientSession] = None
                   ) -> Optional[io.BytesIO]:
    """Gera uma foto e devolve os bytes, ou None (sem token, erro, bloqueio, timeout)."""
    if not available():
        return None
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json",
               "User-Agent": USER_AGENT}
    body = build_workflow(prompt, select_loras(is_nsfw=is_nsfw, focus_angle=focus_angle,
                                               is_mirror_selfie=is_mirror_selfie), is_nsfw=is_nsfw)
    own = session is None
    session = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_S + 30))
    try:
        async with session.post(f"{BASE_URL}/v2/consumer/workflows?wait=30", headers=headers, json=body) as resp:
            if resp.status >= 400:
                logger.error("civitai.submit_failed status=%s body=%s", resp.status, (await resp.text())[:300])
                return None
            wf = await resp.json()
        wf_id = wf.get("id")
        logger.info("civitai.submitted id=%s status=%s cost=%s nsfw=%s", wf_id, wf.get("status"),
                    (wf.get("cost") or {}).get("total"), is_nsfw)
        waited = 0.0
        while (wf.get("status") or "").lower() not in TERMINAL:
            if waited >= TIMEOUT_S:
                logger.error("civitai.timeout id=%s", wf_id)
                return None
            await asyncio.sleep(POLL_S)
            waited += POLL_S
            try:
                async with session.get(f"{BASE_URL}/v2/consumer/workflows/{wf_id}", headers=headers) as resp:
                    if resp.status >= 500:
                        continue   # instabilidade passageira: tenta de novo
                    if resp.status >= 400:
                        logger.error("civitai.poll_failed status=%s", resp.status)
                        return None
                    wf = await resp.json()
            except aiohttp.ClientError as exc:
                logger.warning("civitai.poll_error %s", type(exc).__name__)
        if (wf.get("status") or "").lower() != "succeeded":
            logger.error("civitai.workflow_%s id=%s", wf.get("status"), wf_id)
            return None
        for image in _images(wf):
            if image.get("available") is False:
                logger.warning("civitai.blob_unavailable id=%s reason=%s", image.get("id"), image.get("blockedReason"))
                continue
            data = await _download(session, headers, image)
            if data:
                logger.info("civitai.image_ok id=%s bytes=%d", wf_id, len(data))
                return io.BytesIO(data)
        logger.error("civitai.no_image id=%s", wf_id)
        return None
    except Exception as exc:
        logger.error("civitai.error %s: %s", type(exc).__name__, exc)
        return None
    finally:
        if own:
            await session.close()


async def _download(session: aiohttp.ClientSession, headers: dict, image: dict) -> Optional[bytes]:
    """Primeiro pelo endpoint autenticado do blob (conteúdo adulto não abre pela URL
    assinada); a URL assinada fica de reserva."""
    blob_id = image.get("id")
    urls = []
    if blob_id:
        urls.append((f"{BASE_URL}/v2/consumer/blobs/{blob_id}", {"Authorization": headers["Authorization"],
                                                                  "User-Agent": USER_AGENT}))
    if image.get("url"):
        urls.append((image["url"], {"User-Agent": USER_AGENT}))
    for url, h in urls:
        try:
            async with session.get(url, headers=h, allow_redirects=True) as resp:
                ctype = resp.headers.get("Content-Type", "")
                if resp.status == 200 and ctype.startswith("image/"):
                    return await resp.read()
                logger.warning("civitai.download status=%s type=%s", resp.status, ctype)
        except aiohttp.ClientError as exc:
            logger.warning("civitai.download_error %s", type(exc).__name__)
    return None
