"""
Módulo de Planejamento Interno Híbrido (Internal Planner).
Analisa a mensagem do usuário para determinar intenções, detectar novos compromissos futuros
(eventos pendentes para follow-up posterior), calibrar ajustes emocionais sutis e orientar a resposta.

Princípio Arquitetural: Híbrido
- Heurísticas imediatas para pedidos claros (foto, áudio, comandos) -> 0 latência.
- Análise semântica via LLM para conversas naturais, detecção de eventos e calibração de tom.
"""
import re
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from openai import OpenAI

from config import settings
from db import db_manager, DatabaseManager

logger = logging.getLogger("InternalPlanner")


def parse_iso_or_relative_datetime(
    raw_val: Any,
    reference_dt: Optional[datetime] = None,
    default_offset_hours: Optional[int] = None
) -> Optional[str]:
    """
    Normaliza uma representação temporal (ISO 8601 ou expressão relativa em português)
    para uma string ISO 8601 canônica (YYYY-MM-DDTHH:MM:SS), garantindo compatibilidade
    com consultas SQLite (ex: follow_up_after <= CURRENT_TIMESTAMP).
    Retorna None se a string for apenas descritiva ou não contiver marcadores temporais claros.
    """
    if not raw_val or not str(raw_val).strip():
        return None

    s = str(raw_val).strip()
    now = reference_dt or datetime.now()

    # 1. Tenta parse direto de ISO
    try:
        cleaned_iso = s.replace(" ", "T")
        parsed = datetime.fromisoformat(cleaned_iso)
        return parsed.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        pass

    # 2. Heurísticas em português
    s_lower = s.lower()
    target_date = None
    target_hour = 14
    target_minute = 0
    has_explicit_time = False

    # Extrair horário com marcadores explícitos ("às 14h", "as 10:30", "14h", "14:30", "15hrs")
    # Não dá match em números soltos sem indicador de horário
    time_match = re.search(r'\b(?:às|as)\s*(\d{1,2})(?:[:h](\d{1,2}))?\b|\b(\d{1,2})(?:[:](\d{2})|h(?:oras?|rs?)?(?:(\d{2}))?)\b', s_lower)
    if time_match:
        # Grupo 1 ou 3 é hora, grupo 2 ou 4 é minuto
        h_str = time_match.group(1) or time_match.group(3)
        m_str = time_match.group(2) or time_match.group(4) or time_match.group(5)
        try:
            h = int(h_str)
            m = int(m_str) if m_str else 0
            if 0 <= h <= 23 and 0 <= m <= 59:
                target_hour = h
                target_minute = m
                has_explicit_time = True
        except (ValueError, TypeError):
            pass

    # Períodos do dia se horário não foi explícito
    if not has_explicit_time:
        if "de manhã" in s_lower or "pela manhã" in s_lower or "de manha" in s_lower:
            target_hour = 10
            target_minute = 0
            has_explicit_time = True
        elif "à tarde" in s_lower or "a tarde" in s_lower or "pela tarde" in s_lower:
            target_hour = 15
            target_minute = 0
            has_explicit_time = True
        elif "à noite" in s_lower or "a noite" in s_lower or "de noite" in s_lower:
            target_hour = 20
            target_minute = 0
            has_explicit_time = True

    # Relativo por dias/palavras-chave
    if "depois de amanhã" in s_lower or "depois de amanha" in s_lower:
        target_date = (now + timedelta(days=2)).date()
    elif "amanhã" in s_lower or "amanha" in s_lower:
        target_date = (now + timedelta(days=1)).date()
    elif "hoje" in s_lower:
        target_date = now.date()
    elif "semana que vem" in s_lower or "próxima semana" in s_lower or "proxima semana" in s_lower:
        target_date = (now + timedelta(days=7)).date()
    elif "mês que vem" in s_lower or "mes que vem" in s_lower or "próximo mês" in s_lower:
        target_date = (now + timedelta(days=30)).date()
    elif "fim de semana" in s_lower or "final de semana" in s_lower:
        dias_ate_sab = (5 - now.weekday()) % 7
        if dias_ate_sab == 0:
            dias_ate_sab = 7
        target_date = (now + timedelta(days=dias_ate_sab)).date()
    else:
        # Dias da semana
        dias_semana = {
            "segunda": 0, "terça": 1, "terca": 1, "quarta": 2,
            "quinta": 3, "sexta": 4, "sábado": 5, "sabado": 5, "domingo": 6
        }
        matched_day = False
        for nome_dia, dia_idx in dias_semana.items():
            if nome_dia in s_lower:
                dias_a_frente = (dia_idx - now.weekday()) % 7
                if dias_a_frente == 0:
                    dias_a_frente = 7
                target_date = (now + timedelta(days=dias_a_frente)).date()
                matched_day = True
                break

        if not matched_day:
            delta_match = re.search(r'(?:daqui\s*a|em)\s*(\d+)\s*(hora|horas|dia|dias|minuto|minutos)', s_lower)
            if delta_match:
                qtd = int(delta_match.group(1))
                unidade = delta_match.group(2)
                if "minuto" in unidade:
                    return (now + timedelta(minutes=qtd)).strftime("%Y-%m-%dT%H:%M:%S")
                elif "hora" in unidade:
                    return (now + timedelta(hours=qtd)).strftime("%Y-%m-%dT%H:%M:%S")
                elif "dia" in unidade:
                    return (now + timedelta(days=qtd)).strftime("%Y-%m-%dT%H:%M:%S")

    # Se identificou dia ou horário explícito, monta o datetime final
    if target_date is not None or has_explicit_time:
        d = target_date if target_date is not None else now.date()
        result_dt = datetime(d.year, d.month, d.day, target_hour, target_minute, 0)
        return result_dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Se não identificou nenhum marcador temporal e foi fornecido um default explícito
    if default_offset_hours is not None:
        return (now + timedelta(hours=default_offset_hours)).strftime("%Y-%m-%dT%H:%M:%S")

    # Caso contrário, retorna None (evita converter frases descritivas em timestamps falsos)
    return None

def parse_direct_reminder_datetime(raw_val: Any, reference_dt: Optional[datetime] = None) -> Optional[str]:
    """Aceita apenas hora informada ou intervalo relativo preciso para lembretes diretos."""
    if isinstance(raw_val, datetime):
        return raw_val.strftime("%Y-%m-%dT%H:%M:%S")
    if not raw_val:
        return None

    text = str(raw_val).strip().lower()
    has_clock = bool(re.search(
        r"\b(?:[aà]s\s*\d{1,2}(?:[:h]\d{1,2})?|\d{1,2}(?::\d{2}|h(?:oras?|rs?)?(?:\d{2})?))\b",
        text,
    ))
    has_iso_clock = bool(re.search(r"^\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}(?::\d{2})?$", text))
    has_precise_delta = bool(re.search(r"\b(?:daqui\s+a|em)\s*\d+\s*(?:horas?|minutos?)\b", text))
    if not (has_clock or has_iso_clock or has_precise_delta):
        return None
    return parse_iso_or_relative_datetime(raw_val, reference_dt=reference_dt, default_offset_hours=None)


def detect_explicit_scheduled_event(text: str, reference_dt: Optional[datetime] = None) -> Optional[dict]:
    """Recognize an affirmative, concrete future appointment with an explicit clock time."""
    if not text:
        return None
    normalized = text.strip().lower()
    if re.search(r"\b(?:n[aã]o|nem|nunca|cancelei|cancelado|era|tinha|talvez|se)\b", normalized):
        return None
    if not re.search(r"\b(?:tenho|vou ter|marquei|agendei)\b", normalized):
        return None
    if re.search(r"\bdia\s+\d{1,2}\b|\b\d{1,2}/\d{1,2}\b", normalized):
        return None  # This parser does not resolve calendar dates written by number.
    event_types = {
        "reunião": "trabalho", "reuniao": "trabalho", "consulta": "medico",
        "dentista": "medico", "médico": "medico", "medico": "medico",
        "prova": "estudo", "exame": "estudo", "entrevista": "trabalho",
        "voo": "viagem", "audiência": "compromisso", "audiencia": "compromisso",
    }
    event_type = next((kind for word, kind in event_types.items() if re.search(rf"\b{word}\b", normalized)), None)
    if not event_type:
        return None
    now = reference_dt or datetime.now()
    event_at = parse_direct_reminder_datetime(text, reference_dt=now)
    if not event_at or datetime.fromisoformat(event_at) <= now:
        return None
    description = re.sub(r"^.*?\b(?:tenho|vou ter|marquei|agendei)\b\s*", "", text.strip(), flags=re.IGNORECASE)
    description = re.sub(
        r"\s*\b(?:hoje|amanh[aã]|depois de amanh[aã])?\s*(?:[aà]s)\s*\d{1,2}(?:[:h]\d{1,2})?\b.*$",
        "", description, flags=re.IGNORECASE,
    ).strip(" .!?,")
    return {"event_type": event_type, "description": description or text.strip(), "event_at": event_at}

def detect_direct_reminder_intent(text: str) -> tuple[bool, Optional[str]]:
    """
    Analisa se o texto é uma ordem/pedido afirmativo e imperativo de lembrete direto futuro.
    Retorna (True, subject) se for um pedido legítimo afirmativo.
    Retorna (False, None) se contiver negação, se for pergunta de memória passada/recordação
    ou se não for um pedido de lembrete. (P0 - Rodada 4)
    """
    if not text:
        return False, None

    t = text.strip().lower()

    # 1. Rejeita imediatamente qualquer negação
    # ex: "não me lembra", "não precisa me lembrar", "nem me lembra", "sem me lembrar", "não me avisa"
    negative_patterns = [
        r"\b(?:n[aã]o|nem|nunca|jamais|sem|dispensa|esquece|nada de)\s+.*?\b(?:lembr|avis)",
        r"\b(?:n[aã]o\s+precisa|n[aã]o\s+quero|n[aã]o\s+vai)\s+.*?\b(?:lembr|avis)",
        r"\b(?:lembr|avis)\w*\s+n[aã]o\s+precisa\b",
        r"\bdeixa\s+que\s+eu\s+(?:me\s+)?lembro\b",
        r"\bdeixa\s+quieto\b",
        r"^\s*(?:n[aã]o|nem|nunca|jamais)\b"
    ]
    for neg in negative_patterns:
        if re.search(neg, t):
            return False, None

    # 2. Rejeita perguntas de memória passada / recordação / nostalgia
    # ex: "você lembra", "lembra quando", "lembra de quando", "lembra daquele", "lembra do"
    past_memory_patterns = [
        r"\b(?:voc[êe]|vc|c[êe]|tu)\s+lembra\b",
        r"\blembra\s+(?:de\s+quando|quando|como|daquela|daquele|daqueles|daquelas|do\s+dia|de\s+ontem)\b",
        r"\blembra\s+(?:do|da|dos|das|disso|dessa|desse|dele|dela|da\s+gente|do\s+nosso|da\s+nossa)\b.*?\?",
        r"^\s*lembra\s+de\s+.*?\?"
    ]
    for mem in past_memory_patterns:
        if re.search(mem, t):
            return False, None

    # 3. Padrões estritos de solicitação imperativa / afirmativa de lembrete futuro
    imperative_patterns = [
        # "me lembra de ...", "me lembra que ...", "me lembra pra ...", "me lembra amanhã ..."
        r"^\s*(?:por\s+favor,?\s*)?(?:me\s+)?(?:lembra|avisa)\s+(?:de\s+|que\s+|pra\s+|a\s+|quando\s+)?(.+)",
        # "pode me lembrar de ...", "favor me avisar de ..."
        r"\b(?:pode\s+(?:me\s+)?(?:lembrar|avisar)|favor\s+(?:me\s+)?(?:lembrar|avisar))\s+(?:de\s+|que\s+|pra\s+|a\s+|quando\s+)?(.+)",
        # "quero que você me lembre de ..."
        r"\b(?:quero\s+que\s+(?:voc[êe]|vc)\s+me\s+(?:lembre|avise))\s+(?:de\s+|que\s+|pra\s+|a\s+)?(.+)",
        # "coloca/agenda/cria um lembrete pra ..."
        r"\b(?:coloca|agenda|cria|marca)\s+(?:um\s+)?lembrete\s+(?:de\s+|que\s+|pra\s+|para\s+)?(.+)"
    ]

    for pat in imperative_patterns:
        m = re.search(pat, t)
        if m:
            subject = m.group(1).strip().rstrip(".!? ")
            if not subject:
                return False, None
            # Se a frase inteira for uma pergunta e o verbo for apenas "lembra" sem "me lembra" / "pode me lembrar"
            # ex: "Lembra disso?"
            if "?" in text and not re.search(r"\b(?:me\s+lembra|pode\s+me\s+lembrar|coloca\s+um\s+lembrete)\b", t):
                return False, None
            return True, subject

    return False, None


def is_pure_time_specification(text: str, pending_description: str = "") -> bool:
    """
    Verifica se uma mensagem do usuário é estritamente uma resposta de horário/tempo
    para um esclarecimento de lembrete pendente, ou se introduz uma nova atividade/outro assunto.
    (P1 - Rodadas 4 e 5)
    """
    if not text:
        return False

    t = text.strip().lower()

    # 1. Se contiver recusa ou cancelamento explícito, não é especificação de horário
    if re.search(r"\b(esquece|deixa pra l[aá]|deixa quieto|n[aã]o precisa|cancela|n[aã]o quero|deixa que eu me lembro)\b", t):
        return False

    # 2. Deve conter ao menos um marcador temporal reconhecível
    # Horas explícitas (ex: 14h, 14:00, às 10, às 8 da noite)
    has_time = bool(re.search(r"\b(?:[aà]s\s+)?\d{1,2}(?::\d{2}|h(?:\d{2})?|\s*(?:da\s+manh[aã]|da\s+tarde|da\s+noite))\b", t))
    # Palavras de dias/períodos/deltas
    has_day = bool(re.search(r"\b(?:hoje|amanh[aã]|depois\s+de\s+amanh[aã]|segunda(?:-feira)?|ter[çc]a(?:-feira)?|quarta(?:-feira)?|quinta(?:-feira)?|sexta(?:-feira)?|s[aá]bado|domingo|fim\s+de\s+semana|final\s+de\s+semana|fds|de\s+manh[aã]|pela\s+manh[aã]|[aà]\s+tarde|de\s+tarde|pela\s+tarde|de\s+noite|[aà]\s+noite|pela\s+noite|de\s+madrugada|cedo|cedinho|daqui\s+a\s+\d+|em\s+\d+\s+(?:minutos?|horas?|dias?))\b", t))

    if not (has_time or has_day):
        return False

    # 3. Normalização e remoção sistemática de componentes temporais e partículas
    cleaned = t

    # 3.1 Se pending_description for fornecida, remove as palavras do assunto pendente
    # (ex: se o lembrete pendente é "pagar a conta" e Patrick diz "pagar a conta amanhã às 14h")
    if pending_description:
        desc_words = [re.escape(w) for w in re.findall(r"\b\w+\b", pending_description.lower()) if len(w) > 1]
        if desc_words:
            cleaned = re.sub(rf"\b(?:{'|'.join(desc_words)})\b", " ", cleaned)

    # 3.2 Remove expressões temporais compostas
    cleaned = re.sub(r"\b(?:depois\s+de\s+amanh[aã]|fim\s+de\s+semana|final\s+de\s+semana|semana\s+que\s+vem|pr[oó]xima\s+semana|m[eê]s\s+que\s+vem|pr[oó]ximo\s+m[eê]s)\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:pela\s+manh[aã]|de\s+manh[aã]|na\s+parte\s+da\s+manh[aã]|pela\s+tarde|[aà]\s+tarde|de\s+tarde|na\s+parte\s+da\s+tarde|pela\s+noite|[aà]\s+noite|de\s+noite|de\s+madrugada)\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:daqui\s+a\s+\d+\s*(?:horas?|minutos?|dias?)|em\s+\d+\s*(?:horas?|minutos?|dias?))\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:mais\s+ou\s+menos|por\s+volta\s+de|l[aá]\s+pelas?)\b", " ", cleaned)

    # 3.3 Remove dias individuais e períodos
    cleaned = re.sub(r"\b(?:hoje|amanh[aã]|segunda(?:-feira)?|ter[çc]a(?:-feira)?|quarta(?:-feira)?|quinta(?:-feira)?|sexta(?:-feira)?|s[aá]bado|domingo|fds|cedo|cedinho)\b", " ", cleaned)

    # 3.4 Remove horários e números
    cleaned = re.sub(r"\b\d{1,2}(?::\d{2}|h(?:\d{2})?|\s*(?:da\s+manh[aã]|da\s+tarde|da\s+noite)?)\b", " ", cleaned)
    cleaned = re.sub(r"\b\d+\s*(?:horas?|hrs?|minutos?|mins?|dias?)\b", " ", cleaned)

    # 3.5 Remove partículas de concordância, verbos de agendamento e vocativos comuns de resposta
    filler_patterns = [
        r"\b(?:pode\s+ser|pode|ser)\b",
        r"\b(?:marca|marcar|coloca|colocar|bota|botar|agenda|agendar|cria|criar|anota|anotar)\b",
        r"\b(?:me\s+lembra|lembra|lembrar|me\s+avisa|avisa|avisar)\b",
        r"\b(?:por\s+favor|faz\s+favor|pfv|porfavor)\b",
        r"\b(?:beleza|blz|fechado|ok|okay|t[aá]|bom|sim|isso|combinado|perfeito|[oó]timo)\b",
        r"\b(?:obrigado|valeu|brigado|agrade[çc]o)\b",
        r"\b(?:amor|vida|marina|linda|querida|beb[eê])\b",
        r"\b(?:a[ií]|ent[aã]o|l[aá]|umas?|pelas?|pelo|pelos)\b",
        r"\b(?:[aà]s?|ao|aos|de|do|da|dos|das|em|no|na|nos|nas|pra|para|pro|pras|pros|com|que|e|ou|o|a|os|as|um|uma|uns|umas)\b"
    ]
    for pat in filler_patterns:
        cleaned = re.sub(pat, " ", cleaned)

    cleaned = re.sub(r"[^\w\s]", " ", cleaned).strip()

    # 4. Verificação estrita:
    # Se restou QUALQUER palavra (comprimento >= 2) que não era preposição/filler/tempo/assunto pendente,
    # significa que o Patrick introduziu uma nova atividade/proposição (ex: 'viajo', 'festa', 'médico', 'estudo', 'reunião').
    remaining_words = [w for w in cleaned.split() if len(w) >= 2]
    if remaining_words:
        return False

    return True


PLANNER_SYSTEM_PROMPT = """You are Marina Salles' internal response planner.
Analyze Patrick Ramos's message and return ONLY the required JSON object.
Do not invent future events, biography, or current location.
Do not speak as Marina to the user — plan only.

Respond STRICTLY with this JSON shape (preserve enum/key values exactly):
{
  "intent": "casual_chat|sharing_day|flirting|support_needed|planning_future|photo_request|voice_request|question|other",
  "tone": "carinhosa|brincalhona|dengosa|acolhedora|sensual|tranquila",
  "response_goal": "One short planning sentence for Marina's reply",
  "reaction_emoji": "❤️|🥰|😂|👍|🔥|null",
  "creates_event": false,
  "event_details": {
    "event_type": "trabalho|medico|viagem|encontro|estudo|compromisso|outro",
    "description": "Clear description of Patrick's commitment",
    "event_at": "ISO or textual time (e.g. 2026-09-17T14:00:00)",
    "follow_up_hint": "Follow-up time",
    "follow_up_prompt": "Specific follow-up hook for Marina"
  },
  "reminder_candidate": false,
  "should_offer_reminder": false,
  "recommended_reminder_offset_minutes": 30,
  "direct_reminder": {
    "is_direct_reminder": false,
    "description": null,
    "remind_at": null
  },
  "creates_open_loop": false,
  "open_loop_details": {
    "loop_type": "waiting|decision|task|story|promise|project|relationship|other",
    "content": "Concise pending topic",
    "importance": 0.5,
    "next_check_hint": "When to revisit"
  },
  "resolves_open_loop": false,
  "resolved_loop_hint": null,
  "shared_topic": "Shared topic or null",
  "emotional_deltas": {
    "affection": 0.0,
    "playfulness": 0.0,
    "energy": 0.0,
    "romantic_intensity": 0.0
  }
}

HARD RULES:
1. creates_event=true only for real FUTURE commitments.
2. Offer reminders only for concrete timed events; direct_reminder only on explicit ask without negation.
3. Open loops for unfinished topics without a fixed alarm.
4. emotional_deltas subtle in [-0.05, +0.05].
5. reaction_emoji common Telegram emoji or null.
"""


class InternalPlanner:
    def __init__(self, db: Optional[DatabaseManager] = None, llm_client: Optional[OpenAI] = None):
        self.db = db or db_manager
        self.llm = llm_client or OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL
        )

    def plan_heuristics(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Aplica regras rápidas (heurísticas) para evitar chamadas à LLM em mensagens óbvias."""
        t = (user_message or "").lower().strip()
        
        # Saudações simples
        t_clean = re.sub(r'[!?,.]+', '', t).strip()
        saudacoes = (
            "oi", "ola", "olá", "oie", "bom dia", "boa tarde", "boa noite",
            "oi amor", "oie amor", "olá amor", "bom dia amor", "boa tarde amor", "boa noite amor",
            "oi linda", "oie linda", "oi vida", "oie vida"
        )
        if t_clean in saudacoes:
            return {
                "intent": "casual_chat",
                "tone": "carinhosa",
                "response_goal": "Cumprimentar com carinho e entusiasmo de namorada",
                "reaction_emoji": "🥰",
                "creates_event": False,
                "event_details": None,
                "emotional_deltas": {"affection": 0.01}
            }

        # Declarações explícitas de amor
        if any(p in t for p in ["te amo", "amo você", "amo vc", "minha vida"]):
            return {
                "intent": "flirting",
                "tone": "dengosa",
                "response_goal": "Retribuir o amor com paixão e carinho intenso",
                "reaction_emoji": "❤️",
                "creates_event": False,
                "event_details": None,
                "emotional_deltas": {"affection": 0.04, "romantic_intensity": 0.03}
            }

        # Pedidos diretos óbvios de lembrete (P1 - Rodada 3 / P0 - Rodada 4)
        is_direct, subject = detect_direct_reminder_intent(user_message)
        if is_direct and subject:
            parsed_time = parse_direct_reminder_datetime(subject)
            is_valid_future = bool(parsed_time and datetime.fromisoformat(parsed_time) > datetime.now())
            plan_res = {
                "intent": "direct_reminder",
                "tone": "carinhosa",
                "response_goal": "Anotar o pedido de lembrete com carinho e confirmar o horário",
                "reaction_emoji": "⏰",
                "creates_event": False,
                "event_details": None,
                "direct_reminder": {
                    "is_direct_reminder": True,
                    "description": subject,
                    "remind_at": parsed_time if is_valid_future else None
                },
                "emotional_deltas": {"affection": 0.02}
            }
            if not is_valid_future:
                plan_res["needs_clarification"] = "direct_reminder_time"
                plan_res["clarification_subject"] = subject
            return plan_res

        explicit_event = detect_explicit_scheduled_event(user_message)
        if explicit_event:
            return {
                "intent": "planning_future",
                "tone": "carinhosa",
                "response_goal": "Apoiar Patrick no compromisso e oferecer um lembrete antes",
                "reaction_emoji": None,
                "creates_event": True,
                "event_details": explicit_event,
                "reminder_candidate": True,
                "should_offer_reminder": True,
                "recommended_reminder_offset_minutes": 30,
                "emotional_deltas": {},
            }

        return None

    def plan_message(self, user_message: str, recent_context: str = "") -> Dict[str, Any]:
        """Gera o plano cognitivo da mensagem usando o modelo LLM com fallback para heurística."""
        # 1. Tenta heurística imediata primeiro
        heuristic_plan = self.plan_heuristics(user_message)
        if heuristic_plan:
            return heuristic_plan
        user_content = f"HORÁRIO ATUAL: {datetime.now().strftime('%Y-%m-%d %H:%M')}\nMENSAGEM DO PATRICK: \"{user_message}\""
        if recent_context:
            user_content = f"CONTEXTO RECENTE:\n{recent_context}\n\n{user_content}"

        for attempt in range(2):
            try:
                response = self.llm.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.2,
                    max_tokens=350,
                    response_format={"type": "json_object"}
                )
                raw_text = response.choices[0].message.content.strip()
                data = json.loads(raw_text)

                # Validação antecipada de lembrete direto no plano (P1 - Rodada 3 / P0 - Rodada 4)
                dir_rem = data.get("direct_reminder")
                if dir_rem and isinstance(dir_rem, dict) and dir_rem.get("is_direct_reminder"):
                    is_valid_intent, detected_subj = detect_direct_reminder_intent(user_message)
                    if not is_valid_intent:
                        logger.info(f"LLM gerou direct_reminder indevido para mensagem negada/passada: '{user_message}'. Removendo direct_reminder.")
                        data["direct_reminder"] = None
                        if data.get("intent") == "direct_reminder":
                            data["intent"] = "casual_chat"
                    else:
                        rem_desc = dir_rem.get("description") or detected_subj or "seu compromisso"
                        rem_time_iso = parse_direct_reminder_datetime(user_message)
                        if not rem_time_iso or datetime.fromisoformat(rem_time_iso) <= datetime.now():
                            dir_rem["remind_at"] = None
                            data["needs_clarification"] = "direct_reminder_time"
                            data["clarification_subject"] = rem_desc
                        else:
                            # O horário vem da fala do usuário; a LLM não pode completá-lo por conta própria.
                            dir_rem["remind_at"] = rem_time_iso

                return data
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "rate" in err_str.lower()) and attempt < 1:
                    import time
                    time.sleep(2.0)
                    continue
                logger.warning(f"Aviso no InternalPlanner LLM: {e}. Usando plano de contingência.")
                break

        fallback_plan = {
            "intent": "casual_chat",
            "tone": "carinhosa",
            "response_goal": "Responder com carinho e naturalidade",
            "reaction_emoji": None,
            "creates_event": False,
            "event_details": None,
            "shared_topic": None,
            "emotional_deltas": {}
        }
        is_fallback_dir, fallback_subj = detect_direct_reminder_intent(user_message)
        if is_fallback_dir and fallback_subj:
            fallback_plan["intent"] = "direct_reminder"
            fallback_plan["direct_reminder"] = {"is_direct_reminder": True, "description": fallback_subj, "remind_at": None}
            fallback_plan["needs_clarification"] = "direct_reminder_time"
            fallback_plan["clarification_subject"] = fallback_subj
        return fallback_plan

    def apply_plan_effects(self, plan: Dict[str, Any], conversation_id: Optional[int] = None):
        """Aplica os efeitos colaterais do plano (eventos, lembretes, open loops, tópico e humor)."""
        # 1. Salva evento pendente com timestamps ISO rigorosos se detectado
        event_row_id = None
        event_at_iso = None
        if plan.get("creates_event") and plan.get("event_details"):
            ed = plan["event_details"]
            try:
                raw_event_at = ed.get("event_at")
                raw_follow_up = ed.get("follow_up_hint") or ed.get("follow_up_at_iso")
                follow_prompt = ed.get("follow_up_prompt")

                event_at_iso = parse_iso_or_relative_datetime(raw_event_at, default_offset_hours=None)
                follow_up_iso = parse_iso_or_relative_datetime(raw_follow_up, default_offset_hours=None)

                # Se não tiver follow-up explícito ou se o follow-up ficou agendado antes do evento:
                if event_at_iso:
                    try:
                        ev_dt = datetime.fromisoformat(event_at_iso)
                        expected_min_follow_up = ev_dt + timedelta(hours=2)
                        if not follow_up_iso:
                            follow_up_iso = expected_min_follow_up.strftime("%Y-%m-%dT%H:%M:%S")
                        else:
                            f_dt = datetime.fromisoformat(follow_up_iso)
                            if f_dt <= ev_dt:
                                follow_up_iso = expected_min_follow_up.strftime("%Y-%m-%dT%H:%M:%S")
                    except Exception:
                        pass

                desc = ed.get("description", "Compromisso do Patrick")
                if follow_prompt and follow_prompt not in desc:
                    desc = f"{desc} | Follow-up: {follow_prompt}"

                # Deduplicação de eventos pendentes idênticos ainda abertos (P1.3)
                existing_event = None
                if hasattr(self.db, "buscar_evento_pendente_identico"):
                    existing_event = self.db.buscar_evento_pendente_identico(desc, event_at_iso)

                if existing_event:
                    event_row_id = existing_event["id"]
                    logger.info(f"Evento pendente existente reutilizado para ID {event_row_id}: {desc}")
                else:
                    event_row_id = self.db.adicionar_evento_pendente(
                        event_type=ed.get("event_type", "compromisso"),
                        description=desc,
                        event_at=event_at_iso,
                        follow_up_after=follow_up_iso,
                        importance=float(ed.get("importance", 0.5)),
                        source_conversation_id=conversation_id,
                        follow_up_prompt=follow_prompt
                    )
                    logger.info(f"Novo evento pendente registrado pelo Planner: {desc} (Event: {event_at_iso}, Follow-up: {follow_up_iso})")
            except Exception as e:
                logger.error(f"Erro ao salvar evento pendente do planner: {e}")

        # 2. Oferta de Smart Reminder com consentimento
        if True:
            if plan.get("should_offer_reminder") and event_at_iso:
                try:
                    # Deduplicação: se já existe oferta/lembrete para este evento em status ativo/decidido, não duplicar (P1.3)
                    existing_rem = None
                    if event_row_id and hasattr(self.db, "get_reminder_by_event_id"):
                        existing_rem = self.db.get_reminder_by_event_id(event_row_id)

                    if existing_rem and existing_rem.get("status") in ("offered", "confirmed", "declined"):
                        logger.info(f"Ignorando nova oferta para evento {event_row_id}; lembrete já em status '{existing_rem.get('status')}'.")
                        if existing_rem.get("status") == "offered":
                            plan["offered_reminder_id"] = existing_rem["id"]
                    else:
                        offset = max(1, int(plan.get("recommended_reminder_offset_minutes") or 30))
                        ev_dt = datetime.fromisoformat(event_at_iso)
                        now_dt = datetime.now()
                        if ev_dt - timedelta(minutes=offset) <= now_dt and ev_dt - now_dt > timedelta(minutes=2):
                            # Keep a near-term reminder useful rather than silently dropping the offer.
                            offset = max(1, int((ev_dt - now_dt).total_seconds() // 120))
                        remind_at_iso = (ev_dt - timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%M:%S")
                        if datetime.fromisoformat(remind_at_iso) > now_dt:
                            from reminder_service import reminder_service
                            offered_id = reminder_service.offer_reminder(
                                event_id=event_row_id,
                                description=plan.get("event_details", {}).get("description", "seu compromisso"),
                                remind_at=remind_at_iso,
                                offset_minutes=offset,
                                source_conversation_id=conversation_id
                            )
                            if offered_id:
                                plan["offered_reminder_id"] = offered_id
                except Exception as e_rem:
                    logger.warning(f"Erro ao ofertar reminder para evento: {e_rem}")

            # Pedido direto de reminder (consentimento implícito)
            dir_rem = plan.get("direct_reminder")
            if dir_rem and isinstance(dir_rem, dict) and dir_rem.get("is_direct_reminder"):
                try:
                    rem_desc = dir_rem.get("description") or "seu compromisso"
                    neg_check = re.search(r"\b(?:n[aã]o|nem|nunca|jamais|sem|dispensa)\b.*?\b(?:lembr|avis)", rem_desc.lower())
                    mem_check = re.search(r"\b(?:voc[êe]|vc|tu)\s+lembra\b|\blembra\s+(?:quando|como|de\s+quando)\b", rem_desc.lower())
                    if neg_check or mem_check:
                        logger.warning(f"Rejeitando direct_reminder em apply_plan_effects com texto negado ou recordação: {rem_desc}")
                        plan["direct_reminder"] = None
                    else:
                        raw_rem_time = dir_rem.get("remind_at")
                        # P1.5 / P2: Exigir horário explícito e futuro, sem default_offset_hours implícito
                        rem_time_iso = parse_direct_reminder_datetime(raw_rem_time)
                        if rem_time_iso:
                            rem_dt = datetime.fromisoformat(rem_time_iso)
                            if rem_dt > datetime.now():
                                from reminder_service import reminder_service
                                reminder_service.create_direct_reminder(
                                    description=rem_desc,
                                    remind_at=rem_time_iso,
                                    offset_minutes=0,
                                    event_id=event_row_id,
                                    source_conversation_id=conversation_id
                                )
                            else:
                                logger.info(f"Horário de reminder direto no passado ({rem_time_iso}); solicitando esclarecimento.")
                                plan["needs_clarification"] = "direct_reminder_time"
                                plan["clarification_subject"] = rem_desc
                                if hasattr(self.db, "set_estado_relacional"):
                                    self.db.set_estado_relacional(
                                        "pending_direct_reminder",
                                        json.dumps({"description": rem_desc, "source_conversation_id": conversation_id, "created_at": datetime.now().isoformat()})
                                    )
                        else:
                            logger.info(f"Horário de reminder direto não reconhecido ({raw_rem_time}); pendente de esclarecimento.")
                            plan["needs_clarification"] = "direct_reminder_time"
                            plan["clarification_subject"] = rem_desc
                            if hasattr(self.db, "set_estado_relacional"):
                                self.db.set_estado_relacional(
                                    "pending_direct_reminder",
                                    json.dumps({"description": rem_desc, "source_conversation_id": conversation_id, "created_at": datetime.now().isoformat()})
                                )
                except Exception as e_dir:
                    logger.warning(f"Erro ao registrar reminder direto: {e_dir}")

        # 3. Gestão de Open Loops (Release 3.5.1)
        if True:
            # Criação de novo Open Loop
            if plan.get("creates_open_loop") and plan.get("open_loop_details"):
                old = plan["open_loop_details"]
                content = old.get("content")
                if content and isinstance(content, str):
                    try:
                        loop_type = old.get("loop_type", "task")
                        imp = float(old.get("importance", 0.5))
                        hint = old.get("next_check_hint")
                        next_check = parse_iso_or_relative_datetime(hint, default_offset_hours=48) if hint else None
                        self.db.adicionar_open_loop(
                            loop_type=loop_type,
                            content=content.strip(),
                            importance=imp,
                            due_at=None,
                            next_check_after=next_check,
                            source_conversation_id=conversation_id
                        )
                        logger.info(f"Novo Open Loop registrado pelo Planner: {content} (tipo: {loop_type})")
                    except Exception as e_loop:
                        logger.warning(f"Erro ao salvar open loop: {e_loop}")

            # Resolução de Open Loop existente
            if plan.get("resolves_open_loop"):
                hint = (plan.get("resolved_loop_hint") or "").strip().lower()
                try:
                    active_loops = self.db.get_open_loops_ativos(limit=5)
                    for loop in active_loops:
                        # Se só há 1 loop ativo ou se o hint dá match no conteúdo
                        if len(active_loops) == 1 or (hint and any(w in loop["content"].lower() for w in hint.split() if len(w) > 3)):
                            self.db.resolver_open_loop(loop["id"])
                            logger.info(f"Open Loop {loop['id']} ('{loop['content']}') marcado como resolvido.")
                            break
                except Exception as e_res:
                    logger.warning(f"Erro ao resolver open loop: {e_res}")

        # 4. Atualiza tópico compartilhado se relevante
        shared_topic = plan.get("shared_topic")
        if shared_topic and isinstance(shared_topic, str) and shared_topic.lower() not in ("null", "none", ""):
            try:
                self.db.set_estado_relacional("current_shared_topic", shared_topic.strip())
                logger.info(f"Tópico compartilhado atualizado pelo Planner: {shared_topic.strip()}")
            except Exception as e:
                logger.warning(f"Erro ao atualizar current_shared_topic: {e}")

        # 5. Aplica deltas emocionais com clamp automático
        deltas = plan.get("emotional_deltas", {})
        if deltas and isinstance(deltas, dict):
            for emotion, delta in deltas.items():
                if delta != 0.0:
                    try:
                        self.db.ajustar_emocao(emotion, float(delta))
                    except Exception:
                        pass

        return plan


internal_planner = InternalPlanner()
planner = internal_planner

