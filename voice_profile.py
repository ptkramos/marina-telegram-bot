"""
voice_profile.py — Perfis vocais da Marina Salles.

03/10 (Patrick, /feedback de 02/10 19:52, "a voz está variando muito"): eram dois clones diferentes, um por perfil, e o
roteador trocava de clone a cada áudio — o íntimo ficava uns 3,5 semitons mais agudo e sussurrado, outra pessoa. Agora
é uma voz só, o clone original (dataset de 3 min, o do demo de 15/09 que ele reconhece como "a voz da Marina"):
1. Conversational: o dia a dia, velocidade 1.0.
2. Intimate: o modo provocar/sexting — a MESMA voz, arrastando um pouco (0.95, e pausas onde a frase fecha, em
   voice_prosody). Mistura de timbres e voice_modify foram testados e soaram artificiais.
"""
from dataclasses import dataclass
from config import settings


PROFILE_CONVERSATIONAL = "conversational"
PROFILE_INTIMATE = "intimate"

VOZ_DA_MARINA = "voice_73e73b73-65be-4cf9-9ab6-35d84f1946a3"


@dataclass
class VoiceProfile:
    name: str
    voice_id: str
    speed: float = 1.0
    volume: float = 1.0
    pitch: int = 0


def _voice_id() -> str:
    return (
        getattr(settings, "NOVITA_VOICE_ID_CONVERSATIONAL", None)
        or getattr(settings, "NOVITA_VOICE_ID", None)
        or VOZ_DA_MARINA
    ).strip()


def get_conversational_profile() -> VoiceProfile:
    """Retorna o perfil vocal do dia a dia da Marina."""
    return VoiceProfile(
        name=PROFILE_CONVERSATIONAL,
        voice_id=_voice_id(),
        speed=float(getattr(settings, "NOVITA_CONVERSATIONAL_SPEED", 1.00)),
        volume=1.0,
        pitch=int(getattr(settings, "NOVITA_CONVERSATIONAL_PITCH", 0)),
    )


def get_intimate_profile() -> VoiceProfile:
    """Retorna o modo provocar/sexting: a mesma voz, um pouco mais devagar."""
    return VoiceProfile(
        name=PROFILE_INTIMATE,
        voice_id=_voice_id(),
        speed=float(getattr(settings, "NOVITA_INTIMATE_SPEED", 0.95)),
        volume=1.0,
        pitch=int(getattr(settings, "NOVITA_INTIMATE_PITCH", 0)),
    )


def get_voice_profile(name: str) -> VoiceProfile:
    """Fábrica de perfil vocal a partir do identificador formal ('conversational' ou 'intimate')."""
    if name == PROFILE_INTIMATE:
        return get_intimate_profile()
    return get_conversational_profile()
