"""
voice_profile.py — Perfis Vocais da Marina Seltin (Release 3.5.2 - Adaptive Dual Voice).

Define os dois perfis vocais oficiais da Marina:
1. Conversational (Versão 2 - dataset 1m43s): voz natural, dinâmica, para conversas cotidianas, rotina, apoio, perguntas e lembretes.
2. Intimate (Versão 1 - dataset 3m): voz dengosa, romântica, melosa/sensual, para momentos íntimos, flertes, declarações e pedidos explícitos.
"""
from dataclasses import dataclass
from config import settings


PROFILE_CONVERSATIONAL = "conversational"
PROFILE_INTIMATE = "intimate"


@dataclass
class VoiceProfile:
    name: str
    voice_id: str
    speed: float = 1.0
    volume: float = 1.0
    pitch: int = 0


def get_conversational_profile() -> VoiceProfile:
    """Retorna o perfil vocal conversacional/cotidiano da Marina."""
    voice_id = (
        getattr(settings, "NOVITA_VOICE_ID_CONVERSATIONAL", None)
        or getattr(settings, "NOVITA_VOICE_ID", None)
        or "voice_d91c415d-f6a2-4d6f-b32c-aacfd5ad2e39"
    )
    speed = float(getattr(settings, "NOVITA_CONVERSATIONAL_SPEED", 1.00))
    pitch = int(getattr(settings, "NOVITA_CONVERSATIONAL_PITCH", 0))
    return VoiceProfile(
        name=PROFILE_CONVERSATIONAL,
        voice_id=voice_id.strip(),
        speed=speed,
        volume=1.0,
        pitch=pitch,
    )


def get_intimate_profile() -> VoiceProfile:
    """Retorna o perfil vocal íntimo/dengoso da Marina."""
    voice_id = (
        getattr(settings, "NOVITA_VOICE_ID_INTIMATE", None)
        or getattr(settings, "NOVITA_VOICE_ID_CONVERSATIONAL", None)
        or getattr(settings, "NOVITA_VOICE_ID", None)
        or "voice_73e73b73-65be-4cf9-9ab6-35d84f1946a3"
    )
    speed = float(getattr(settings, "NOVITA_INTIMATE_SPEED", 0.96))
    pitch = int(getattr(settings, "NOVITA_INTIMATE_PITCH", 0))
    return VoiceProfile(
        name=PROFILE_INTIMATE,
        voice_id=voice_id.strip(),
        speed=speed,
        volume=1.0,
        pitch=pitch,
    )


def get_voice_profile(name: str) -> VoiceProfile:
    """Fábrica de perfil vocal a partir do identificador formal ('conversational' ou 'intimate')."""
    if name == PROFILE_INTIMATE:
        return get_intimate_profile()
    return get_conversational_profile()
