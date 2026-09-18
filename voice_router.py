"""
voice_router.py — Roteador Adaptativo de Voz da Marina Salles (Release 3.7.0).

Mapeia deterministicamente o contexto conversacional, intenção do Planner,
estado emocional e pedidos explícitos para o perfil vocal adequado:
- Conversational (padrão natural)
- Intimate (dengosa / sensual / romântica)

Regras Centrais:
1. Lembretes sempre em voz Conversational.
2. Pedidos de apoio/consolo ("meu dia foi pesado") sempre em voz Conversational, independente de afeto alto.
3. Fase ovulatória/ciclo menstrual sozinha NÃO força voz íntima sem justificativa no diálogo.
4. Overrides explícitos do Patrick vencem o roteador.
"""
import re
import logging
from dataclasses import dataclass, field
from config import settings
from voice_profile import (
    VoiceProfile,
    PROFILE_CONVERSATIONAL,
    PROFILE_INTIMATE,
    get_conversational_profile,
    get_intimate_profile,
    get_voice_profile,
)

logger = logging.getLogger("VoiceRouter")

# Padrões regex para overrides explícitos do usuário
RE_EXPLICIT_NORMAL = re.compile(
    r'\b(voz\s+normal|voz\s+natural|fala\s+normal|fala\s+natural|[áa]udio\s+normal|[áa]udio\s+natural|fala\s+sem\s+ser\s+manhosa|na\s+voz\s+normal)\b',
    re.IGNORECASE
)

RE_EXPLICIT_INTIMATE = re.compile(
    r'\b(voz\s+manhosa|voz\s+sensual|fala\s+manhosa|fala\s+sensual|voz\s+[íi]ntima|fala\s+[íi]ntima|[áa]udio\s+manhoso|[áa]udio\s+sensual|[áa]udio\s+dengoso|voz\s+gostosa|fala\s+dengosa|voz\s+mais\s+sensual|daquele\s+seu\s+jeitinho|aquela\s+voz\s+manhosa)\b',
    re.IGNORECASE
)

# Indicadores de apoio emocional ou desabafo do Patrick
RE_SUPPORT_KEYWORDS = re.compile(
    r'\b(dia\s+(foi\s+)?(pesado|ruim|dif[íi]cil|uma\s+merda)|triste|cansad[oa]|estressad[oa]|chatead[oa]|desanimad[oa]|esgotad[oa]|barra\s+pesada|n[ãa]o\s+t[ôo]\s+bem)\b',
    re.IGNORECASE
)

# Palavras românticas/afetivas no texto do usuário
RE_ROMANTIC_KEYWORDS = re.compile(
    r'\b(amor|saudade|saudades|te\s+amo|beijo|beijinho|dormir\s+com\s+voc[êe]|cama|abra[çc]o|gostos[oa]|linda|maravilhosa|meu\s+bem)\b',
    re.IGNORECASE
)


@dataclass
class VoiceSelectionContext:
    intent: str = ""
    tone: str = ""
    emotional_state: dict = field(default_factory=dict)
    user_text: str = ""
    is_proactive: bool = False
    source: str = ""
    time_of_day: str = ""
    is_reminder: bool = False


class VoiceRouter:
    """Roteador determinístico de perfis vocais."""

    @classmethod
    def route(cls, context: VoiceSelectionContext | dict | None = None) -> tuple[VoiceProfile, str]:
        """
        Determina o perfil vocal apropriado com base no contexto.
        Retorna uma tupla (VoiceProfile, motivo_str).
        """
        if not getattr(settings, "DUAL_VOICE_ENABLED", True):
            return get_conversational_profile(), "dual_voice_disabled"

        # Converte dict para VoiceSelectionContext se necessário
        if context is None:
            ctx = VoiceSelectionContext()
        elif isinstance(context, dict):
            ctx = VoiceSelectionContext(
                intent=context.get("intent", ""),
                tone=context.get("tone", ""),
                emotional_state=context.get("emotional_state") or {},
                user_text=context.get("user_text", ""),
                is_proactive=context.get("is_proactive", False),
                source=context.get("source", ""),
                time_of_day=context.get("time_of_day", ""),
                is_reminder=context.get("is_reminder", False),
            )
        else:
            ctx = context

        user_text = ctx.user_text or ""
        intent = (ctx.intent or "").lower()
        tone = (ctx.tone or "").lower()

        # 1. Regra de Lembretes: Lembretes SEMPRE usam voz Conversational
        if ctx.is_reminder or intent in ("reminder", "smart_reminder"):
            logger.info("🎙️ Voice Router: perfil 'conversational' selecionado (motivo: reminder).")
            return get_conversational_profile(), "reminder"

        # 2. Overrides Explícitos do Usuário (vencem qualquer outra inferência)
        if RE_EXPLICIT_NORMAL.search(user_text):
            logger.info("🎙️ Voice Router: perfil 'conversational' selecionado (motivo: explicit_normal_override).")
            return get_conversational_profile(), "explicit_normal_override"

        if RE_EXPLICIT_INTIMATE.search(user_text):
            logger.info("🎙️ Voice Router: perfil 'intimate' selecionado (motivo: explicit_manhosa_override).")
            return get_intimate_profile(), "explicit_manhosa_override"

        # 3. Situação de Apoio Emocional / Dia Difícil (sempre Conversational com tom suave)
        if intent in ("support_needed", "support", "empathy", "comfort") or RE_SUPPORT_KEYWORDS.search(user_text):
            logger.info("🎙️ Voice Router: perfil 'conversational' selecionado (motivo: support_needed).")
            return get_conversational_profile(), "support_needed"

        # 4. Assuntos Cotidianos, Perguntas, Rotina, Planejamento
        if intent in ("casual_chat", "question", "planning_future", "sharing_day", "informational", "curiosity", "practical"):
            # Apenas se houver um tom explicitamente dengosa/sensual com contexto romântico no texto avalia intimate
            if tone in ("dengosa", "sensual") and RE_ROMANTIC_KEYWORDS.search(user_text):
                logger.info("🎙️ Voice Router: perfil 'intimate' selecionado (motivo: casual_with_explicit_intimate_tone).")
                return get_intimate_profile(), "casual_with_explicit_intimate_tone"
            logger.info("🎙️ Voice Router: perfil 'conversational' selecionado (motivo: casual_or_informational).")
            return get_conversational_profile(), "casual_or_informational"

        # 5. Sinais Íntimos / Sensuais / Flertes
        intimate_tones = {"dengosa", "sensual", "apaixonada", "romântica", "romantica", "intimate", "provocadora", "carinhosa_intima"}
        intimate_intents = {"flirting", "intimate", "seduction", "romantic"}

        if intent in intimate_intents and tone in intimate_tones:
            logger.info("🎙️ Voice Router: perfil 'intimate' selecionado (motivo: flirting_and_intimate_tone).")
            return get_intimate_profile(), "flirting_and_intimate_tone"

        if tone in ("dengosa", "sensual") and (RE_ROMANTIC_KEYWORDS.search(user_text) or ctx.is_proactive):
            logger.info("🎙️ Voice Router: perfil 'intimate' selecionado (motivo: intimate_tone_with_romantic_context).")
            return get_intimate_profile(), "intimate_tone_with_romantic_context"

        if intent in intimate_intents and RE_ROMANTIC_KEYWORDS.search(user_text):
            logger.info("🎙️ Voice Router: perfil 'intimate' selecionado (motivo: romantic_intent_and_keywords).")
            return get_intimate_profile(), "romantic_intent_and_keywords"

        # 6. Salvaguarda do Ciclo Menstrual: ciclo ovulatório/fértil sozinho NÃO deve forçar intimate
        # (Se chegou até aqui sem cair nas regras íntimas acima, mantém conversational)

        logger.info("🎙️ Voice Router: perfil 'conversational' selecionado (motivo: default_conversational).")
        return get_conversational_profile(), "default_conversational"


voice_router = VoiceRouter()
