"""Geração de fotos da Marina pelo Civitai (Orchestration API), motor Krea 2.

24/09: a Novita ficou sem GPU pra alugar e o Patrick propôs o Civitai, onde o
LoRA da Marina foi treinado (Krea 2, gatilho "marinaX"). Não se aluga máquina:
cada foto é um "workflow" pago em Buzz. O Flux.1 (primeiro LoRA dela) saiu no
mesmo dia — a pilha oficial está em KREA2_STACKS (n3 normal, e adulta).

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
USER_AGENT = "marin-telegram-bot"
TERMINAL = {"succeeded", "failed", "expired", "canceled", "cancelled"}
POLL_S = 3.0
TIMEOUT_S = 420   # checkpoint da comunidade frio leva ~3,5 min pra carregar (Yogi, 24/09)
ALLOW_LIVE_IN_TESTS = False


def _settings():
    from config import settings
    return settings


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
# FinePorn v5 INT8 (saiu 25/09): o autor pede Euler Simple, 12 passos, CFG 1. GUARDADA pra A/B —
# a oficial continua a v4 até o Patrick aprovar a comparação (rosto, cor, sliders, LoRAs).
KREA2_FINEPORN_V5 = "urn:air:krea2:checkpoint:civitai:2762538@3356355"
# LoRAs de ocasião (Patrick, 24/09) — entram só quando a cena pede (CONDITIONAL abaixo).
KREA2_SQUEEZE = "urn:air:krea2:lora:civitai:2761661@3161094"   # Breast squeezing V1 (gatilho "squeezing breasts")
KREA2_WETNESS = "urn:air:krea2:lora:civitai:2738333@3079282"   # Wetness Slider (−1..1; o FinePorn embute negativo)
KREA2_SPREAD = "urn:air:krea2:lora:civitai:2923413@3332400"    # Pussy Spread v2 (gatilho "vag_spread")
KREA2_CREAMY = "urn:air:krea2:lora:civitai:2931761@3318154"    # Creamy Pussy v0.1 (gatilhos "creamythings", "creamy vagina")
# Penetração (Patrick, 24/09, 3 rodadas): sem LoRA ela só passava o dedo por fora.
# Dedo: Fingering v4 em 1.0 (0.5 não entrava; 0.8 ficava na entrada). Dildo: o objeto sai do
# TEXTO (Dildo Posing mudava a luz e o olho dela; Object Insertions fazia "garrafa") e o
# Grippy Pussy em 1.0 é quem faz ele entrar.
KREA2_FINGERING = "urn:air:krea2:lora:civitai:2923170@3343699"  # Fingering v4 (gatilho "finger_fucking")
KREA2_GRIPPY = "urn:air:krea2:lora:civitai:2796863@3152534"     # Grippy Pussy v1.0 (gatilho "GrippyPussy")
# Reprovados na mesma bateria: Dildo Posing (luz e cor do olho), Object Insertions (dildo virava
# "garrafa"), FINGERING-KREA2 (indisponível nos servidores) e Juicy Pussy 0.8 (mudou a Marina e
# o escorrido saía branco). Molhada antes do gozo = só texto; no gozo, o Creamy 0.5.
KREA2_JUICY = "urn:air:krea2:lora:civitai:2915944@3298822"      # REPROVADO (24/09)
# 25/09 (Patrick): gozo especial = Krea2 Squirt 1.5 sem Creamy e sem Fingering (teste WW);
# boquete no dildo = Suck Something 0.5 (0.8 igual, 0.5 mexe menos). Reprovados: GoddesSquirt
# (jato branco/grosso), Filter Bypass (o FinePorn não tem censura pra destravar), Pussy Helper.
KREA2_SQUIRT = "urn:air:krea2:lora:civitai:2817445@3177828"     # Krea2 Squirt (gatilho "squirt, female ejaculation")
KREA2_SUCK = "urn:air:krea2:lora:civitai:2805527@3163300"       # Suck Something (gatilho "sucking")
KREA2_AHEGAO = "urn:air:krea2:lora:civitai:2743970@3086237"     # Ahegao Face (0.5, só no gozo especial)
# Boquete no dildo (Patrick, 25/09, testes ZB/ZE): POV Blowjob 0.8 + Suck 0.5. O POV carimba uma marca
# d'água ("MARINAAX", o gatilho deformado) no canto de baixo à direita → a foto com ele sai sem os
# 6% de baixo (só lençol ali). Deepthroat (143472) reprovado: desenhava um homem na cena.
KREA2_POVBJ = "urn:air:krea2:lora:civitai:380283@3296875"      # (Mainly) POV Blowjob v2 K2
WATERMARK_CROP = 0.06
KREA2_BETTER = "urn:air:krea2:lora:civitai:2729157@3288922"    # Better Pussy v4.2.1 — testado e REPROVADO (24/09)
KREA2_OILED = "urn:air:krea2:lora:civitai:87685@3096878"      # Oiled Skin — REPROVADO (24/09): o FinePorn vira "esperma"
KREA2_WEIGHT_OLD = "urn:air:krea2:lora:civitai:2858768@3229815"  # Body Weight v2 — mexia na cabeça (reprovado)
# Sliders do Loraholic (Patrick, 24/09) — corpo canônico por slider, não por texto:
KREA2_WEIGHT = "urn:air:krea2:lora:civitai:2554553@3073386"    # Fat/Skinny (−10..10, POSITIVO = mais cheinha)
KREA2_GENITAL_COLOR = "urn:air:krea2:lora:civitai:2825933@3188207"   # −3 = o rosa aprovado
KREA2_AREOLA = "urn:air:krea2:lora:civitai:2554618@3120387"
KREA2_NIPPLE = "urn:air:krea2:lora:civitai:2554559@3191856"
KREA2_PUBES = "urn:air:krea2:lora:civitai:2617090@3136749"
KREA2_ASS = "urn:air:krea2:lora:civitai:2554616@3207249"
# Corpo dela em toda foto (vestida ou nua: o corpo não muda entre as fotos).
BODY_SLIDERS = {KREA2_ASS: 2.5}
# Só na foto adulta (partes à mostra). Lábios menores −2 deixou a vulva pequena demais: fora.
NUDE_SLIDERS = {KREA2_GENITAL_COLOR: -3.0, KREA2_AREOLA: -2.0, KREA2_NIPPLE: -1.0, KREA2_PUBES: -2.0}
KREA2_TANLINES = "urn:air:krea2:lora:civitai:2840638@3206585"  # Bikini Tan Lines (AiMami) — gatilho "bikini tan-lines"
KREA2_PHONE = "urn:air:krea2:lora:civitai:2796343@3151907"     # Elusarca Smartphone Photography Slider (1–2)
# {perdedor: vencedor} quando dois LoRAs de ocasião brigam: óleo no pós-banho já brilha — a
# molhada por cima dobrava o brilho.
EXCLUSIVE: dict = {}   # preenchido depois do CONDITIONAL
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
    # Candidatas com a v5 (A/B): mesmos LoRAs da n3/e, receita do autor.
    "n3v5": {"model": KREA2_FINEPORN_V5, "steps": 12, "scheduler": "simple", "loras": {KREA2_PHONE: PHONE_SELFIE_WEIGHT}},
    "ev5": {"model": KREA2_FINEPORN_V5, "steps": 12, "scheduler": "simple",
            "loras": {KREA2_PHONE: PHONE_SELFIE_WEIGHT, KREA2_TANLINES: 0.6}},
}
SFW_STACKS, NSFW_STACKS = ("n1", "n2", "n3", "n3v5"), ("a", "b", "c", "d", "e", "ev5")


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
    (KREA2_FINGERING, 1.0, ("up to the knuckles", "fingers inside her", "fingers sliding inside",
                            "finger_fucking", "dedos dentro", "dedo dentro"),
     True, "She slides two fingers into her vagina and moves them in and out, finger_fucking"),
    (KREA2_GRIPPY, 1.0, ("dildo", "consolo"), True, "GrippyPussy's vulva tightly gripping the dildo shaft"),
    (KREA2_SUCK, 0.5, ("sucking it", "lips tightly wrapped", "boquete", "chupando o dildo"), True, "sucking"),
    (KREA2_POVBJ, 0.8, ("sucking it", "lips tightly wrapped", "boquete", "chupando o dildo"), True, ""),
    # Molhada só de ÁGUA (banho, chuva, piscina, mar). Molhada de excitação ficou melhor SEM o slider
    # (teste do Patrick, 24/09) — aí quem descreve é o texto do prompt.
    (KREA2_WETNESS, 1.2, ("shower", "bath", "bathtub", "rain", "pool", "swimming", "in the sea", "ocean", "beach water",
                          "soaked", "wet hair", "banho", "chuva", "piscina", "no mar", "de biquíni molhado"),
     False, ""),
)
# Chupando o dildo não é o dildo entrando: o Grippy (e o gatilho dele) sai.
EXCLUSIVE[KREA2_GRIPPY] = KREA2_SUCK
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
    loras.update(BODY_SLIDERS)
    if is_nsfw:
        loras.update(NUDE_SLIDERS)
    slider = float(getattr(s, "CIVITAI_BREAST_SLIDER", 0) or 0) if breast_slider is None else breast_slider
    if slider:
        loras[KREA2_BREAST_SLIDER] = slider   # mesmo valor vestida e pelada: o corpo não muda entre as fotos
    if not is_nsfw:
        loras[KREA2_NSFW_HELPER] = KREA2_SFW_GUARD
    return loras


# Peso (D1) → slider de peso. Base 54 kg = WEIGHT_AT_BASE (magra, fit); cada kg a mais deixa
# mais cheinha e cada kg a menos mais magra. A faixa do D1 (52–57 kg) cabe folgada no −3..5.
# 24/09: o Body Weight mexia na cabeça; o Fat/Skinny do Loraholic ficou "perfeito, bem sutil"
# (Patrick, testado em ±2). Positivo = mais cheinha. Base 54 kg = 0 (o corpo aprovado das fotos).
WEIGHT_SLIDER_ENABLED = True
WEIGHT_AT_BASE = 0.0
WEIGHT_PER_KG = 0.8


def weight_slider(kg: Optional[float] = None) -> float:
    if kg is None:
        try:
            from db import db_manager
            from meals import Meals
            kg = float(Meals(db_manager).weight()["kg"])
        except Exception:
            kg = 54.0
    value = WEIGHT_AT_BASE + (float(kg) - 54.0) * WEIGHT_PER_KG
    return round(max(-4.0, min(4.0, value)), 2)


def conditional_loras(prompt: str, *, is_nsfw: bool, exclude=()) -> tuple[dict, list[str]]:
    """LoRAs de ocasião que a cena liga, e as frases-gatilho que faltam no prompt."""
    low = (prompt or "").lower()
    try:   # o cenário fixo do apê ("glass shower enclosure", "rooftop pool") não é ação da cena
        import apartamento
        for room in apartamento.ROOMS.values():
            low = low.replace(room["scene"].lower(), "").replace(room["short"].lower(), "")
    except Exception:
        pass
    loras, triggers = {}, []
    for air, weight, words, adult_only, trigger in CONDITIONAL:
        if (adult_only and not is_nsfw) or air in exclude:
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
                         breast_slider: Optional[float] = None, lora_weights: Optional[dict] = None) -> dict:
    name = krea2_stack_name(is_nsfw=is_nsfw, stack=stack)
    spec = KREA2_STACKS[name]
    off = {k for k, v in (lora_weights or {}).items() if not v}   # peso 0 do diretor = desligado
    extra, triggers = conditional_loras(prompt, is_nsfw=is_nsfw, exclude=off)
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
    step["loras"].update({k: v for k, v in (lora_weights or {}).items() if v})   # peso decidido pelo diretor
    if spec["model"]:
        step["diffusionModel"] = spec["model"]
    body = {"steps": [{"$type": "imageGen", "input": step}], "allowMatureContent": bool(is_nsfw)}
    if is_nsfw:
        body["currencies"] = ["yellow"]
    return body


def _token() -> str:
    return (getattr(_settings(), "CIVITAI_API_KEY", "") or "").strip().strip('"')


def available() -> bool:
    if not _token():
        return False
    if not (getattr(_settings(), "CIVITAI_LORA_MARINA_KREA2", "") or "").strip():
        logger.warning("civitai.sem_lora_da_marina — foto sem o rosto dela não serve")
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
                   seed: Optional[int] = None, lora_weights: Optional[dict] = None) -> Optional[io.BytesIO]:
    """Gera uma foto e devolve os bytes, ou None (sem token, erro, bloqueio, timeout)."""
    if not available():
        return None
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json",
               "User-Agent": USER_AGENT}
    body = build_workflow_krea2(prompt, is_nsfw=is_nsfw, seed=seed, lora_weights=lora_weights)
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
            if data and KREA2_POVBJ in (body["steps"][0]["input"].get("loras") or {}):
                data = _crop_bottom(data, WATERMARK_CROP)
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


def _crop_bottom(data: bytes, frac: float) -> bytes:
    """Tira a faixa de baixo (a marca d'água que o POV Blowjob desenha no canto)."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = img.size
        out = io.BytesIO()
        img.crop((0, 0, w, int(h * (1 - frac)))).save(out, format="JPEG", quality=93)
        return out.getvalue()
    except Exception:
        return data


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
