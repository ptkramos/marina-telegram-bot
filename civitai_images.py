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
FLUX_KREA_DEV = "urn:air:flux1:checkpoint:civitai:1827475@2068069"   # Flux 1 Krea Dev FP8 (aceita os LoRAs Flux1)
USER_AGENT = "marin-telegram-bot"
TERMINAL = {"succeeded", "failed", "expired", "canceled", "cancelled"}
POLL_S = 3.0
TIMEOUT_S = 420   # checkpoint da comunidade frio leva ~3,5 min pra carregar (Yogi, 24/09)
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


# ---------------------------------------------------------------- Krea 2 --
# 24/09: o Patrick vai retreinar a Marina em Krea 2 ("outro nível"). A receita
# pública do Krea 2 (FAL) não aceita LoRA, mas o motor Comfy aceita:
# engine=comfy, ecosystem=krea2, model=turbo|raw, loras, diffusionModel.
# Pilhas revisadas em 24/09 depois de ler a descrição de cada LoRA (autores):
# SNOFS pede pra não empilhar outros LoRAs/modelos de NSFW; TextFusion saiu
# (treinado no Krea 2 não-destilado, dá textura estranha no Turbo); o slider
# de seios vai de -5 a 5/8; o NSFW Helper negativo deixa a foto mais comportada;
# o Emotions tem gatilho próprio (vai no prompt, visual_profile.krea2_prompt).
# Candidatas pro A/B com o LoRA novo — escolhidas no .env:
#   foto normal  CIVITAI_KREA2_SFW_STACK  = n1 (Turbo + 3 LoRAs de realismo) | n2 (Stable Yogi + Snapshot)
#   foto adulta  CIVITAI_KREA2_NSFW_STACK = a (Turbo + SNOFS) | b (AIO sozinho) | c (Stable Yogi + Realism Engine)
#                                           | d (Turbo + Krea 2 NSFW V4, experimental)
KREA2_AIO = "urn:air:krea2:checkpoint:civitai:2732185@3071970"         # Krea2 turbo NSFW AIO v1.0 (12-14 passos)
KREA2_YOGI = "urn:air:krea2:checkpoint:civitai:2786499@3329215"        # Realism by Stable Yogi v3.0 (8 passos cfg 1)
# 24/09: a v3.0 nunca ficou disponível nos servidores (nem com prepareResource);
# a v2.5 INT8 Turbo funciona (~3,5 min de aquecimento a frio). Escolha do Patrick.
KREA2_YOGI_25 = "urn:air:krea2:checkpoint:civitai:2786499@3231611"
# FinePorn v4 (Patrick, 24/09): Turbo com Realism Engine, NSFW V4.3, Breasts&Nipples etc. já
# embutidos → sem SNOFS/NSFW Helper por cima. Só a v4 nvfp4 fica no ar (a bf16 não carrega).
KREA2_FINEPORN = "urn:air:krea2:checkpoint:civitai:2762538@3215452"
# LoRAs de ocasião (Patrick, 24/09) — entram só quando a cena pede (CONDITIONAL abaixo).
KREA2_SQUEEZE = "urn:air:krea2:lora:civitai:2761661@3161094"   # Breast squeezing V1 (gatilho "squeezing breasts")
KREA2_WETNESS = "urn:air:krea2:lora:civitai:2738333@3079282"   # Wetness Slider (−1..1; o FinePorn embute negativo)
KREA2_SPREAD = "urn:air:krea2:lora:civitai:2923413@3332400"    # Pussy Spread v2 (gatilho "vag_spread")
KREA2_CREAMY = "urn:air:krea2:lora:civitai:2931761@3318154"    # Creamy Pussy v0.1 (gatilhos "creamythings", "creamy vagina")
KREA2_BETTER = "urn:air:krea2:lora:civitai:2729157@3288922"    # Better Pussy v4.2.1 — testado e REPROVADO (24/09)
KREA2_OILED = "urn:air:krea2:lora:civitai:87685@3096878"      # Oiled Skin (Krea 2 v1.0, gatilho "OiledSkin")
KREA2_WEIGHT = "urn:air:krea2:lora:civitai:2858768@3229815"    # Body Weight Slider v2 (−3..5, maior = mais magra)
KREA2_TANLINES = "urn:air:krea2:lora:civitai:2840638@3206585"  # Bikini Tan Lines (AiMami) — gatilho "bikini tan-lines"
KREA2_PHONE = "urn:air:krea2:lora:civitai:2796343@3151907"     # Elusarca Smartphone Photography Slider (1–2)
# {perdedor: vencedor} quando dois LoRAs de ocasião brigam: óleo no pós-banho já brilha — a
# molhada por cima dobrava o brilho.
EXCLUSIVE: dict = {}
PHONE_SELFIE_WEIGHT = 0.8   # 1.5 enchia de purpurina; 0.8 = "realismo perfeito" (Patrick, 24/09) — em TODA foto
PHONE_DESATURATE = 0.83   # o autor corrige −15 a −20 de saturação depois de gerar; fazemos no download
KREA2_NICEGIRLS = "urn:air:krea2:lora:civitai:1862761@3075498"         # NiceGirls UltraReal (0.6-0.8)
KREA2_LENOVO = "urn:air:krea2:lora:civitai:1662740@3075606"            # Lenovo UltraReal (1.2-2 no Turbo)
KREA2_REALISM_V2 = "urn:air:krea2:lora:civitai:2728365@3090634"        # Krea2-realism V2 (1.0)
KREA2_SNAPSHOT = "urn:air:krea2:lora:civitai:2268008@3084537"          # Realistic Snapshot v0.5 (foto de iPhone)
KREA2_REALISM_ENGINE = "urn:air:krea2:lora:civitai:2688234@3109006"    # Realism Engine v3 (0.7, nunca >0.9)
KREA2_SNOFS = "urn:air:krea2:lora:civitai:1972981@3290120"             # SNOFS Krea 2 v1.4
KREA2_NSFW_V4 = "urn:air:krea2:lora:civitai:2725430@3147117"           # Krea 2 NSFW v4.3_EXP (0.8-1.2)
KREA2_NSFW_HELPER = "urn:air:krea2:lora:civitai:2779347@3130045"       # NSFW Helper Slider (-1 a 5)
KREA2_EMOTIONS = "urn:air:krea2:lora:civitai:2829908@3193133"          # Detailed Emotions and Expressions
KREA2_BREAST_SLIDER = "urn:air:krea2:lora:civitai:2540187@3131773"     # valor da Marina: CIVITAI_BREAST_SLIDER
KREA2_EMOTIONS_WEIGHT = 0.6
KREA2_SFW_GUARD = -1.0   # NSFW Helper negativo na foto normal: trava extra contra nudez acidental

KREA2_STACKS = {
    # n1 = escolha do Patrick (24/09, tarde): Krea 2 Turbo oficial (o da corpo_n1), CFG 1, Lenovo 1.0
    # (só selfie) + Realism Engine 0.8 (+ Emotions, slider 2.5 e a trava −1 em toda foto normal).
    # NiceGirls saiu depois do teste com 0.8 / 0.6 / sem.
    "n1": {"model": None, "steps": 8,
           "loras": {KREA2_LENOVO: 1.0, KREA2_REALISM_ENGINE: 0.8}},
    "n2": {"model": KREA2_YOGI, "steps": 8, "loras": {KREA2_SNAPSHOT: 0.6}},
    # n3 (teste 24/09): FinePorn como base da foto normal — o rosto dela ficou lindo nele. A trava
    # −1 (NSFW Helper) é obrigatória aqui: o checkpoint tem NSFW embutido.
    # Smartphone slider em 0.8 em toda foto (1.5 enchia de purpurina), com a correção de cor no download.
    "n3": {"model": KREA2_FINEPORN, "steps": 10, "scheduler": "beta", "loras": {KREA2_PHONE: PHONE_SELFIE_WEIGHT}},
    "a": {"model": None, "steps": 8, "loras": {KREA2_SNOFS: 1.0, KREA2_NSFW_HELPER: 0.5}},
    "b": {"model": KREA2_AIO, "steps": 12, "loras": {}},
    "c": {"model": KREA2_YOGI, "steps": 8, "loras": {KREA2_REALISM_ENGINE: 0.7, KREA2_NSFW_HELPER: 0.5}},
    "d": {"model": None, "steps": 8, "loras": {KREA2_NSFW_V4: 1.0, KREA2_NSFW_HELPER: 0.5}},
    # Marquinha de biquíni realista (tirinhas, borda suave) só na foto adulta, em 0.6 (Patrick, 24/09).
    "e": {"model": KREA2_FINEPORN, "steps": 10, "scheduler": "beta",
          "loras": {KREA2_PHONE: PHONE_SELFIE_WEIGHT, KREA2_TANLINES: 0.6}},
}
SFW_STACKS, NSFW_STACKS = ("n1", "n2", "n3"), ("a", "b", "c", "d", "e")


def ecosystem() -> str:
    """flux1 (padrão) ou krea2 — krea2 só vale com o LoRA Krea 2 da Marina configurado."""
    s = _settings()
    wanted = (getattr(s, "CIVITAI_ECOSYSTEM", "") or "flux1").strip().lower()
    if wanted == "krea2" and not (getattr(s, "CIVITAI_LORA_MARINA_KREA2", "") or "").strip():
        logger.warning("civitai.krea2_sem_lora_da_marina — usando Flux (foto sem o rosto dela não serve)")
        return "flux1"
    return wanted if wanted in ("flux1", "krea2") else "flux1"


def krea2_stack_name(*, is_nsfw: bool, stack: Optional[str] = None) -> str:
    s = _settings()
    if is_nsfw:
        name = (stack or getattr(s, "CIVITAI_KREA2_NSFW_STACK", "") or "e").strip().lower()
        return name if name in NSFW_STACKS else "e"
    name = (stack or getattr(s, "CIVITAI_KREA2_SFW_STACK", "") or "n3").strip().lower()
    return name if name in SFW_STACKS else "n3"


# 24/09 (Patrick): o Lenovo ("cara de foto de celular") só na selfie — em foto de
# corpo inteiro, junto com o LoRA dela (dataset quase todo de perto), ele virava
# tudo selfie, mesmo com o prompt dizendo "não é selfie".
SELFIE_ONLY = {KREA2_LENOVO}
# (lora, peso, palavras da cena que ligam, só adulta?, frase-gatilho que o LoRA precisa no prompt)
CONDITIONAL = (
    (KREA2_SQUEEZE, 0.6, ("squeezing her breast", "grabbing her breast", "holding her breasts", "squeezing breasts",
                          "grabbing breasts", "cupping her breasts", "apertando os seios", "segurando os seios"),
     True, "squeezing breasts, her nipples stay small and delicate"),   # 0.8 aumentava o mamilo
    (KREA2_SPREAD, 0.8, ("spreading her pussy", "spread her pussy", "spreads her pussy", "pussy lips open",
                         "pussy spread", "spread open", "abrindo a buceta", "abrindo a vagina", "abre a buceta"),
     True, "vag_spread"),
    # Creamy só na intensidade mínima: o líquido saindo, sem virar "gozo" (Patrick, 24/09).
    (KREA2_CREAMY, 0.5, ("she came", "just came", "right after she came", "orgasm", "cumming", "climax",
                         "gozou", "gozando", "gozar", "creamy"), True, "creamythings, creamy vagina"),
    # Óleo/creme no corpo no pós-banho, provocando (Patrick, 24/09). Força baixa (o autor usa 1.0 pro
    # máximo); só na adulta — o autor avisa que o LoRA "quer muito" deixar a mulher nua.
    (KREA2_OILED, 0.5, ("body oil", "oiled", "oiling", "rubbing lotion", "body lotion", "moisturizer",
                        "cream on her body", "applying cream", "passando creme", "passando óleo", "óleo no corpo",
                        "hidratante"), True, "OiledSkin"),
    # Molhada só de ÁGUA (banho, chuva, piscina, mar). Molhada de excitação ficou melhor SEM o slider
    # (teste do Patrick, 24/09) — aí quem descreve é o texto do prompt.
    (KREA2_WETNESS, 1.2, ("shower", "bath", "bathtub", "rain", "pool", "swimming", "in the sea", "ocean", "beach water",
                          "soaked", "wet hair", "banho", "chuva", "piscina", "no mar", "de biquíni molhado"),
     False, ""),
)
EXCLUSIVE[KREA2_WETNESS] = KREA2_OILED
# De longe o rosto aparece pequeno: o LoRA dela um pouco mais fraco deixa a pose livre
# (o Patrick viu isso na época 6 do treino).
MARINA_WEIGHT_DISTANT = 0.9   # 0.8 soltou a pose; 0.9 = escolha do Patrick pra segurar mais o rosto
NOT_SELFIE_MARK = "not a selfie"   # visual_profile.KREA2_PHOTO_DISTANT


def select_loras_krea2(*, is_nsfw: bool, stack: Optional[str] = None,
                       breast_slider: Optional[float] = None, selfie: bool = True) -> dict:
    s = _settings()
    loras = {getattr(s, "CIVITAI_LORA_MARINA_KREA2").strip(): 1.0 if selfie else MARINA_WEIGHT_DISTANT}
    loras.update({k: v for k, v in KREA2_STACKS[krea2_stack_name(is_nsfw=is_nsfw, stack=stack)]["loras"].items()
                  if selfie or k not in SELFIE_ONLY})
    loras[KREA2_EMOTIONS] = KREA2_EMOTIONS_WEIGHT
    if WEIGHT_SLIDER_ENABLED:
        loras[KREA2_WEIGHT] = weight_slider()   # D1: o corpo acompanha o peso dela
    slider = float(getattr(s, "CIVITAI_BREAST_SLIDER", 0) or 0) if breast_slider is None else breast_slider
    if slider:
        loras[KREA2_BREAST_SLIDER] = slider   # mesmo valor vestida e pelada: o corpo não muda entre as fotos
    if not is_nsfw:
        loras[KREA2_NSFW_HELPER] = KREA2_SFW_GUARD
    return loras


# Peso (D1) → slider de peso. Base 54 kg = WEIGHT_AT_BASE (magra, fit); cada kg a mais deixa
# mais cheinha e cada kg a menos mais magra. A faixa do D1 (52–57 kg) cabe folgada no −3..5.
# 24/09: DESLIGADO — o slider mudava o tamanho da cabeça dela (Patrick). A ligação com o D1
# fica pronta pra um slider melhor.
WEIGHT_SLIDER_ENABLED = False
WEIGHT_AT_BASE = 0.5
WEIGHT_PER_KG = 0.75


def weight_slider(kg: Optional[float] = None) -> float:
    if kg is None:
        try:
            from db import db_manager
            from meals import Meals
            kg = float(Meals(db_manager).weight()["kg"])
        except Exception:
            kg = 54.0
    value = WEIGHT_AT_BASE + (54.0 - float(kg)) * WEIGHT_PER_KG
    return round(max(-3.0, min(5.0, value)), 2)


def conditional_loras(prompt: str, *, is_nsfw: bool) -> tuple[dict, list[str]]:
    """LoRAs de ocasião que a cena liga, e as frases-gatilho que faltam no prompt."""
    low = (prompt or "").lower()
    loras, triggers = {}, []
    for air, weight, words, adult_only, trigger in CONDITIONAL:
        if adult_only and not is_nsfw:
            continue
        if any(w in low for w in words):
            loras[air] = weight
            if trigger and trigger not in low:
                triggers.append((air, trigger))
    for loser, winner in EXCLUSIVE.items():
        if loser in loras and winner in loras:
            loras.pop(loser)
    return loras, [t for air, t in triggers if air in loras]


def build_workflow_krea2(prompt: str, *, is_nsfw: bool, width: int = 1024, height: int = 1536,
                         seed: Optional[int] = None, stack: Optional[str] = None,
                         breast_slider: Optional[float] = None) -> dict:
    name = krea2_stack_name(is_nsfw=is_nsfw, stack=stack)
    spec = KREA2_STACKS[name]
    extra, triggers = conditional_loras(prompt, is_nsfw=is_nsfw)
    if triggers:
        joined = ", ".join(triggers)
        prompt = f"{prompt} {joined[:1].upper()}{joined[1:]}."   # sem .capitalize(): "OiledSkin" tem caixa
    step = {"engine": "comfy", "ecosystem": "krea2", "model": "turbo", "operation": "createImage",
            "prompt": prompt, "width": width, "height": height, "steps": spec["steps"], "cfgScale": 1,
            "sampler": "euler", "scheduler": spec.get("scheduler", "simple"),
            "seed": seed if seed is not None else random.randint(1, 2**31 - 1),
            "quantity": 1, "loras": select_loras_krea2(is_nsfw=is_nsfw, stack=name, breast_slider=breast_slider,
                                                       selfie=NOT_SELFIE_MARK not in prompt)}
    step["loras"].update(extra)
    if spec["model"]:
        step["diffusionModel"] = spec["model"]
    body = {"steps": [{"$type": "imageGen", "input": step}], "allowMatureContent": bool(is_nsfw)}
    if is_nsfw:
        body["currencies"] = ["yellow"]
    return body


def base_model() -> str:
    """Modelo base (Flux.1 família, onde o LoRA da Marina funciona). CIVITAI_BASE_MODEL no .env troca."""
    return (getattr(_settings(), "CIVITAI_BASE_MODEL", "") or "").strip() or FLUX_DEV


def build_workflow(prompt: str, loras: dict, *, is_nsfw: bool, width: int = 832, height: int = 1216,
                   steps: int = 24, seed: Optional[int] = None, model: Optional[str] = None) -> dict:
    body = {
        "steps": [{
            "$type": "imageGen",
            "input": {
                "engine": "comfy", "ecosystem": "flux1", "operation": "createImage",
                "model": model or base_model(), "prompt": prompt, "width": width, "height": height,
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
                   is_mirror_selfie: bool = False, session: Optional[aiohttp.ClientSession] = None,
                   model: Optional[str] = None, seed: Optional[int] = None) -> Optional[io.BytesIO]:
    """Gera uma foto e devolve os bytes, ou None (sem token, erro, bloqueio, timeout)."""
    if not available():
        return None
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json",
               "User-Agent": USER_AGENT}
    if ecosystem() == "krea2" and model is None:
        body = build_workflow_krea2(prompt, is_nsfw=is_nsfw, seed=seed)
    else:
        body = build_workflow(prompt, select_loras(is_nsfw=is_nsfw, focus_angle=focus_angle,
                                                   is_mirror_selfie=is_mirror_selfie), is_nsfw=is_nsfw,
                              model=model, seed=seed)
    own = session is None
    session = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_S + 30))
    try:
        wf = None
        for _attempt in range(1):
            async with session.post(f"{BASE_URL}/v2/consumer/workflows?wait=30", headers=headers, json=body) as resp:
                if resp.status < 400:
                    wf = await resp.json()
                    break
                err = (await resp.text())[:300]
            # 24/09: foto normal NUNCA vira adulta. Reenviar como adulta quando o
            # moderador reclamava liberou nudez numa selfie de pijama. Se o
            # moderador marca uma foto normal, ela falha (e o log diz por quê).
            if not is_nsfw and "mature content" in err.lower():
                logger.error("civitai.sfw_flagged_by_moderator — prompt normal com termo adulto")
                return None
            logger.error("civitai.submit_failed status=%s body=%s", resp.status, err)
            return None
        if wf is None:
            return None
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
            if data and KREA2_PHONE in (body["steps"][0]["input"].get("loras") or {}):
                data = _desaturate(data, PHONE_DESATURATE)
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


def _desaturate(data: bytes, factor: float) -> bytes:
    """Correção de cor do slider de smartphone (o autor pede −15 a −20 de saturação)."""
    try:
        from PIL import Image, ImageEnhance
        img = Image.open(io.BytesIO(data)).convert("RGB")
        out = io.BytesIO()
        ImageEnhance.Color(img).enhance(factor).save(out, format="JPEG", quality=93)
        return out.getvalue()
    except Exception as exc:
        logger.warning("civitai.desaturate_failed %s", type(exc).__name__)
        return data


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
