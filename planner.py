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

    # Relativo por dias/palavras-chave
    if "depois de amanhã" in s_lower or "depois de amanha" in s_lower:
        target_date = (now + timedelta(days=2)).date()
    elif "amanhã" in s_lower or "amanha" in s_lower:
        target_date = (now + timedelta(days=1)).date()
    elif "hoje" in s_lower:
        target_date = now.date()
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


PLANNER_SYSTEM_PROMPT = """Você é o Planejador Cognitivo Interno de Marina Seltin.
Sua função é analisar a mensagem de Patrick Ramos (namorado da Marina) e planejar a melhor estratégia de resposta antes da geração final.

Você deve responder ESTRITAMENTE em formato JSON com a seguinte estrutura:
{
  "intent": "casual_chat|sharing_day|flirting|support_needed|planning_future|photo_request|voice_request|question|other",
  "tone": "carinhosa|brincalhona|dengosa|acolhedora|sensual|tranquila",
  "response_goal": "Objetivo em 1 frase curta para a fala da Marina",
  "reaction_emoji": "❤️|🥰|😂|👍|🔥|null",
  "creates_event": false,
  "event_details": {
    "event_type": "trabalho|medico|viagem|encontro|estudo|compromisso|outro",
    "description": "Descrição clara do compromisso do Patrick",
    "event_at": "Indicação temporal ISO ou textual do evento (ex: 2026-09-17T14:00:00 ou amanhã às 14h)",
    "follow_up_hint": "Momento para follow-up (ex: 2026-09-17T16:00:00 ou amanhã às 16h)",
    "follow_up_prompt": "Pergunta ou gancho específico que a Marina deve fazer no follow-up"
  },
  "shared_topic": "Tema ou assunto marcante compartilhado na mensagem ou null",
  "emotional_deltas": {
    "affection": 0.0,
    "playfulness": 0.0,
    "energy": 0.0,
    "romantic_intensity": 0.0
  }
}

REGRAS RÍGIDAS:
1. DETECÇÃO DE EVENTOS PENDENTES (creates_event):
   - Apenas marque creates_event = true se o Patrick mencionar um evento/compromisso FUTURO real (ex: "amanhã tenho consulta às 10h", "sexta tenho prova", "semana que vem vou viajar a trabalho").
   - Se for apenas um comentário do passado ou presente imediato ("estou comendo pizza"), creates_event = false.
2. DELTAS EMOCIONAIS (valores sutis entre -0.05 e +0.05):
   - Elogio, carinho ou declaração de amor -> affection +0.02 a +0.04, romantic_intensity +0.02
   - Brincadeira boba ou risadas -> playfulness +0.03
   - Conversa tensa ou cansaço do dia -> energy -0.02
3. REAÇÃO EMOJI:
   - Sugira um emoji comum do Telegram se o momento for propício (❤️, 🥰, 😂, 🔥, 👍), ou null se neutro.
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

        return None

    def plan_message(self, user_message: str, recent_context: str = "") -> Dict[str, Any]:
        """Gera o plano cognitivo da mensagem usando o modelo LLM com fallback para heurística."""
        # 1. Tenta heurística imediata primeiro
        heuristic_plan = self.plan_heuristics(user_message)
        if heuristic_plan:
            return heuristic_plan

        # 2. Se planner não estiver habilitado em config, usa plano padrão
        if not getattr(settings, "PLANNER_ENABLED", False):
            return {
                "intent": "casual_chat",
                "tone": "carinhosa",
                "response_goal": "Responder de forma espontânea e conectada",
                "reaction_emoji": None,
                "creates_event": False,
                "event_details": None,
                "emotional_deltas": {}
            }

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
                return data
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "rate" in err_str.lower()) and attempt < 1:
                    import time
                    time.sleep(2.0)
                    continue
                logger.warning(f"Aviso no InternalPlanner LLM: {e}. Usando plano de contingência.")
                break

        return {
            "intent": "casual_chat",
            "tone": "carinhosa",
            "response_goal": "Responder com carinho e naturalidade",
            "reaction_emoji": None,
            "creates_event": False,
            "event_details": None,
            "shared_topic": None,
            "emotional_deltas": {}
        }

    def apply_plan_effects(self, plan: Dict[str, Any], conversation_id: Optional[int] = None):
        """Aplica os efeitos colaterais do plano (criação de eventos pendentes normalizados, tópico e humor)."""
        # 1. Salva evento pendente com timestamps ISO rigorosos se detectado
        if plan.get("creates_event") and plan.get("event_details"):
            ed = plan["event_details"]
            try:
                raw_event_at = ed.get("event_at")
                raw_follow_up = ed.get("follow_up_hint") or ed.get("follow_up_at_iso")
                follow_prompt = ed.get("follow_up_prompt")

                event_at_iso = parse_iso_or_relative_datetime(raw_event_at, default_offset_hours=4)
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

                self.db.adicionar_evento_pendente(
                    event_type=ed.get("event_type", "compromisso"),
                    description=desc,
                    event_at=event_at_iso,
                    follow_up_after=follow_up_iso,
                    source_conversation_id=conversation_id
                )
                logger.info(f"Novo evento pendente registrado pelo Planner: {desc} (Event: {event_at_iso}, Follow-up: {follow_up_iso})")
            except Exception as e:
                logger.error(f"Erro ao salvar evento pendente do planner: {e}")

        # 2. Atualiza tópico compartilhado se relevante
        shared_topic = plan.get("shared_topic")
        if shared_topic and isinstance(shared_topic, str) and shared_topic.lower() not in ("null", "none", ""):
            try:
                self.db.set_estado_relacional("current_shared_topic", shared_topic.strip())
                logger.info(f"Tópico compartilhado atualizado pelo Planner: {shared_topic.strip()}")
            except Exception as e:
                logger.warning(f"Erro ao atualizar current_shared_topic: {e}")

        # 3. Aplica deltas emocionais com clamp automático
        deltas = plan.get("emotional_deltas", {})
        if deltas and isinstance(deltas, dict):
            for emotion, delta in deltas.items():
                if delta != 0.0:
                    try:
                        self.db.ajustar_emocao(emotion, float(delta))
                    except Exception:
                        pass


internal_planner = InternalPlanner()
planner = internal_planner
