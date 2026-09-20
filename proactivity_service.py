"""
Serviço de Proatividade e Iniciativa Autônoma Contextual (Proactivity Service).
Gerencia a vontade própria de Marina com inteligência de continuidade,
follow-up de compromissos passados do Patrick e anti-spam rigoroso.

Patch 013 (v3.7.1): adiciona `transition_announcement` — quando a rotina do dia
sugere que Marina "sairia" para uma atividade externa (academia, passeio com
Milo) durante conversa ativa com o Patrick, ela AVISA antes de sair, do jeito
que casais avisam ("vou dar uma passada na academia amor, já volto"). O
WorldState só transiciona depois do anúncio + horário combinado.
"""
import json
import random
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, Tuple

from config import settings
from db import db_manager, DatabaseManager
from prompt_policy import get_daypart

logger = logging.getLogger("ProactivityService")


# Quando o RoutineEngine sortearia uma rotina externa mas a conversa está ativa,
# Marina anuncia com esse tempo de antecedência antes da transição efetiva.
TRANSITION_ANNOUNCE_LEAD_MINUTES = 3
# Duração default da atividade externa quando não há end_at explícito.
TRANSITION_DEFAULT_DURATION_MINUTES = 75

# Atividades externas que fazem sentido anunciar naturalmente.
EXTERNAL_TRANSITION_TEMPLATES = {
    "gym": {
        "activity": "treinando na academia",
        "place_key": "bodytech_sao_clemente",
        "instruction_hint": (
            "Avise o Patrick com naturalidade de namorada que você vai dar uma "
            "passada rápida na academia (Bodytech São Clemente) agora e já "
            "volta. Uma ou duas frases curtas, tom carinhoso, sem drama."
        ),
    },
    "pet_walk": {
        "activity": "passeando com Milo",
        "place_key": "enseada_botafogo",
        "instruction_hint": (
            "Avise o Patrick que você vai levar o Milo pra dar uma volta rápida "
            "aqui na Enseada e já volta. Uma ou duas frases curtas, carinhoso."
        ),
    },
    "gym_indoor": {
        "activity": "treinando na academia do prédio",
        "place_key": "marina_apartment",
        "instruction_hint": (
            "Avise o Patrick que você vai descer na academia do prédio pra "
            "malhar rapidinho e já volta. Uma ou duas frases curtas."
        ),
    },
}


class ProactivityService:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or db_manager

    def check_sleep_window(self, now: Optional[datetime] = None) -> bool:
        """Retorna True se estiver na janela de sono da Marina (03h30 às 08h00)."""
        dt = now or datetime.now()
        hora = dt.hour + (dt.minute / 60.0)
        return 3.5 <= hora < 8.0

    def get_last_messages_timestamps(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Recupera data/hora da última mensagem do Patrick e da última mensagem autônoma."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Última mensagem do usuário
            cursor.execute("SELECT timestamp FROM conversas WHERE role = 'user' ORDER BY id DESC LIMIT 1")
            row_user = cursor.fetchone()
            last_user_dt = datetime.fromisoformat(row_user["timestamp"]) if row_user else None

            # Última mensagem autônoma da Marina
            cursor.execute("SELECT timestamp FROM conversas WHERE role = 'assistant' AND is_initiative = 1 ORDER BY id DESC LIMIT 1")
            row_auto = cursor.fetchone()
            last_auto_dt = datetime.fromisoformat(row_auto["timestamp"]) if row_auto else None

            return last_user_dt, last_auto_dt

    def get_autonomous_count_today(self, now: Optional[datetime] = None) -> int:
        """Conta quantas iniciativas autônomas a Marina já tomou hoje."""
        dt = now or datetime.now()
        hoje_str = dt.strftime("%Y-%m-%d")
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as total FROM conversas WHERE role = 'assistant' AND is_initiative = 1 AND timestamp LIKE ?",
                (f"{hoje_str}%",)
            )
            row = cursor.fetchone()
            return row["total"] if row else 0

    def should_trigger(self, now: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Avalia se a Marina pode e deve tomar iniciativa neste momento:
        - Bloqueia em horário de sono
        - Bloqueia se o Patrick mandou mensagem recentemente (cooldown ativo)
        - Bloqueia se Marina mandou mensagem autônoma recente
        - Bloqueia se atingiu limite diário
        - Libera imediatamente se houver evento pendente vencido para follow-up
        """
        if not getattr(settings, "PROACTIVITY_ENABLED", True):
            return False, "proactivity_disabled"

        dt = now or datetime.now()

        living = (True
                  and True)

        # 1. Sleep window — WorldState/Calendar is authoritative when Living World is active.
        #    Hardcoded clock (03:30–08:00) is only a fallback when state is unavailable.
        if self.check_sleep_window(dt):
            if living:
                # Check WorldState: if Marina is explicitly awake, don't block
                try:
                    from world_repository import WorldStateRepository
                    ws_repo = WorldStateRepository(self.db)
                    snapshot = ws_repo.latest()
                    if snapshot:
                        from datetime import timedelta
                        observed = datetime.fromisoformat(snapshot['observed_at'])
                        age = dt - observed
                        is_fresh = (observed.date() == dt.date()
                                    and timedelta(0) <= age < timedelta(minutes=60))
                        activity = (snapshot.get('activity') or '').casefold()
                        is_sleeping = any(x in activity for x in ('dorm', 'sleep', 'sono'))
                        if is_fresh and not is_sleeping:
                            # Explicit awake state overrides clock fallback
                            pass  # do NOT block
                        else:
                            return False, "sleep_window"
                    else:
                        return False, "sleep_window"
                except Exception:
                    return False, "sleep_window"
            else:
                return False, "sleep_window"

        # 2. Limite diário de proatividade
        count_today = self.get_autonomous_count_today(dt)
        if count_today >= settings.MAX_AUTONOMOUS_MESSAGES_PER_DAY:
            return False, "daily_limit_reached"

        # 3. Cooldowns de conversa
        last_user_dt, last_auto_dt = self.get_last_messages_timestamps()

        # Se o Patrick falou há pouco tempo, deixa ele descansar / não atropela
        if last_user_dt:
            minutos_desde_user = (dt - last_user_dt).total_seconds() / 60.0
            if minutos_desde_user < settings.USER_IDLE_MINUTES_BEFORE_PROACTIVE:
                return False, "user_active_recently"

        # Cooldown entre mensagens autônomas
        if last_auto_dt:
            minutos_desde_auto = (dt - last_auto_dt).total_seconds() / 60.0
            if minutos_desde_auto < settings.AUTONOMOUS_COOLDOWN_MINUTES:
                return False, "autonomous_cooldown_active"

        if living:
            candidate = self.determine_living_world_candidate(dt)
            if candidate['rank'] >= 70:
                return True, candidate['reason']
            # A relationship thought need not become a message. Low-priority
            # callbacks and affection remain occasional, not clock-driven.
            probability = settings.AUTONOMOUS_TRIGGER_CHANCE * (0.35 if candidate['rank'] >= 40 else 0.12)
            return (True, candidate['reason']) if random.random() < probability else (False, 'living_world_quiet')

        # 4. Verifica se há evento pendente vencido para follow-up imediato
        eventos_vencidos = self.db.get_eventos_pendentes_para_followup(dt.isoformat())
        if eventos_vencidos:
            return True, "pending_event_ready"

        # 4.1. Verifica se há Open Loop pronto para check-in (Release 3.5.1)
        if True:
            loops_prontos = self.db.get_open_loops_para_checkin(dt.isoformat())
            if loops_prontos:
                return True, "open_loop_ready"

        # 5. Chance estatística configurada caso não haja evento específico
        if random.random() < settings.AUTONOMOUS_TRIGGER_CHANCE:
            return True, "stochastic_trigger"

        return False, "stochastic_miss"

    def determine_living_world_candidate(self, now: Optional[datetime] = None) -> dict:
        from relationship_world import RelationshipWorld

        return RelationshipWorld(self.db).ranked_candidate(now or datetime.now())

    def _pending_transition(self, now: datetime) -> Optional[Dict[str, Any]]:
        """Recupera transição já anunciada e ainda não efetivada."""
        try:
            raw = self.db.get_estado_relacional().get("pending_transition_json")
        except Exception:
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _detect_transition_intent(self, now: datetime) -> Optional[Dict[str, Any]]:
        """Se a rotina do momento sugere uma saída externa, retorna o template
        de anúncio; senão, None. Só considera candidatos externos elegíveis
        no `RoutineEngine.candidates` SEM os filtros de conversa/cooldown
        (queremos saber a intenção 'crua' do sistema de rotinas para avisar)."""
        try:
            from world_state import RoutineEngine, EXTERNAL_ROUTINE_TYPES
            from academic_life import AcademicLife
            from calendar_world import CalendarWorld, local_time
        except Exception:
            return None
        now = local_time(now)
        calendar = CalendarWorld(self.db)
        academic = AcademicLife(self.db)
        has_class = bool(academic.blocks_on(now.date()))
        observed_weather = calendar.context.get("weather:rio", now=now)
        weather = observed_weather["payload"] if observed_weather else None
        heavy_rain = bool(weather and weather.get("heavy_rain"))
        observed_holiday = calendar.context.get(f"holiday:{now.date().isoformat()}", now=now)
        holiday_scope = observed_holiday["payload"]["scope"] if observed_holiday else None

        engine = RoutineEngine(self.db)
        # Sem os filtros de bloqueio: queremos ver se "seria" hora de sair.
        cands = engine.candidates(
            now, has_class=has_class, heavy_rain=heavy_rain,
            energy=0.7, holiday_scope=holiday_scope,
            conversation_active=False, post_event_cooldown=False,
        )
        externals = [c for c in cands if c.routine_type in EXTERNAL_ROUTINE_TYPES]
        if not externals:
            return None
        # Escolhe o mais provável dentre os externos.
        best = max(externals, key=lambda c: c.score)
        template = EXTERNAL_TRANSITION_TEMPLATES.get(best.routine_type)
        if not template:
            return None
        return {
            "routine_type": best.routine_type,
            "activity": template["activity"],
            "place_key": template["place_key"],
            "instruction_hint": template["instruction_hint"],
        }

    def _register_transition(self, intent: Dict[str, Any], now: datetime) -> None:
        """Registra a transição anunciada no estado_relacional. WorldStateManager
        vai efetivar como `explicit_plan` quando `transition_at` chegar."""
        transition_at = now + timedelta(minutes=TRANSITION_ANNOUNCE_LEAD_MINUTES)
        end_at = transition_at + timedelta(minutes=TRANSITION_DEFAULT_DURATION_MINUTES)
        payload = {
            "routine_type": intent["routine_type"],
            "activity": intent["activity"],
            "place_key": intent["place_key"],
            "announced_at": now.isoformat(),
            "transition_at": transition_at.isoformat(),
            "end_at": end_at.isoformat(),
        }
        try:
            self.db.set_estado_relacional("pending_transition_json", json.dumps(payload))
            logger.info(
                "transition_announcement.registered type=%s transition_at=%s",
                intent["routine_type"], transition_at.isoformat(timespec="minutes"),
            )
        except Exception:
            logger.exception("transition_announcement.register.error")

    def determine_proactive_prompt(self, now: Optional[datetime] = None, auto_complete: bool = False) -> Dict[str, Any]:
        """
        Determina a razão e o prompt estruturado de proatividade segundo hierarquia:
        0. Anúncio de transição de rotina (namorada avisando que vai sair)
        1. Evento pendente vencido (ex: como foi a reunião?)
        2. Open Loop pronto para check-in (ex: teve novidades sobre aquela vaga?)
        3. Assunto recente compartilhado
        4. Rotina e momento do dia (com contexto de WorldState/humor injetado)
        """
        dt = now or datetime.now()
        daypart = get_daypart(dt)

        # Prioridade 0: transição de rotina anunciada com naturalidade.
        # Só dispara se: (a) há conversa ativa nos últimos 15 min, (b) a rotina
        # do momento sortearia atividade externa, (c) não há transição já
        # anunciada e pendente.
        if not self._pending_transition(dt):
            last_user_dt, _ = self.get_last_messages_timestamps()
            recent_conv = (
                last_user_dt is not None
                and (dt - last_user_dt) < timedelta(minutes=15)
            )
            if recent_conv:
                intent = self._detect_transition_intent(dt)
                if intent:
                    self._register_transition(intent, dt)
                    return {
                        "reason": "transition_announcement",
                        "event_id": None,
                        "instruction": (
                            f"{intent['instruction_hint']} Você está no meio de "
                            f"uma conversa com o Patrick ({daypart}); avise com "
                            "carinho de namorada, sem drama, sem pedir permissão — "
                            "só um heads-up natural. Nada de emoji em todas as "
                            "frases; tom casual de WhatsApp."
                        ),
                    }

        # Prioridade 1: Evento pendente vencido
        eventos_vencidos = self.db.get_eventos_pendentes_para_followup(dt.isoformat())
        if eventos_vencidos:
            ev = eventos_vencidos[0]
            if auto_complete:
                self.db.concluir_evento_pendente(ev["id"])
            desc = ev["description"]
            return {
                "reason": "pending_event_followup",
                "event_id": ev["id"],
                "instruction": (
                    f"Daypart is {daypart}. You remembered Patrick had this commitment: '{desc}'. "
                    "Ask how it went with genuine girlfriend affection. Do not invent a location."
                )
            }

        # Prioridade 2: Open Loop pronto para check-in (Release 3.5.1)
        if True:
            loops_prontos = self.db.get_open_loops_para_checkin(dt.isoformat())
            if loops_prontos:
                loop = loops_prontos[0]
                # Empurra próximo check para daqui a 3 dias para não insistir
                novo_check = (dt + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
                self.db.atualizar_open_loop_touch(loop["id"], next_check_after=novo_check)
                return {
                    "reason": "open_loop_checkin",
                    "loop_id": loop["id"],
                    "instruction": (
                        f"Daypart is {daypart}. You remembered something Patrick mentioned: "
                        f"'{loop['content']}'. Ask lightly if there is any update — no pressure, no invented scene."
                    )
                }

        # Prioridade 3: Tópico compartilhado recente
        estado_relacional = self.db.get_estado_relacional()
        shared_topic = estado_relacional.get("current_shared_topic")
        if shared_topic and shared_topic not in ("dia a dia e planos juntos", ""):
            return {
                "reason": "topic_followup",
                "event_id": None,
                "instruction": (
                    f"Daypart is {daypart}. Continue the shared topic '{shared_topic}' with warmth. "
                    "Do not invent a current apartment scene or fabricated daily event."
                )
            }

        # Prioridade 4: Neutral affection contextualizada.
        # Em vez de "send a short affectionate check-in" genérico, injetamos
        # WorldState atual + humor emocional pra a Marina ter algo específico
        # pra dizer (comentar sobre o que ela tá fazendo, hora do dia, humor).
        context_lines = self._build_neutral_context(dt, daypart)
        return {
            "reason": "neutral_affection",
            "event_id": None,
            "instruction": (
                "Send a spontaneous message to Patrick. Draw naturally on the "
                "context below — a passing thought about what you're doing, a "
                "reaction to the moment, a small observation, a question about "
                "him, or plain affection. Vary the shape: don't default to "
                "'oi amor, como você tá?'. Do not invent location, outfit, "
                "package, or fabricated daily events beyond what the context "
                "supplies.\n\n" + context_lines
            ),
        }

    def _build_neutral_context(self, now: datetime, daypart: str) -> str:
        """Monta um bloco de contexto rico pra a mensagem espontânea variar
        naturalmente: WorldState atual, hora, humor, tópico compartilhado
        recente, tempo desde a última troca."""
        lines = [f"Daypart: {daypart}. Hora local: {now.strftime('%H:%M')}."]
        try:
            from world_repository import WorldStateRepository
            snap = WorldStateRepository(self.db).latest()
            if snap:
                lines.append(
                    f"Seu estado agora: {snap.get('activity') or 'sem atividade definida'}."
                )
        except Exception:
            pass
        try:
            emotional = self.db.get_estado_emocional()
            affection = emotional.get("affection", {}).get("valor")
            social = emotional.get("social_battery", {}).get("valor")
            if affection is not None and affection >= 0.7:
                lines.append("Seu carinho por ele está alto agora.")
            if social is not None and social < 0.4:
                lines.append("Sua bateria social está baixa — tom pode ser mais quieto e íntimo.")
            elif social is not None and social >= 0.7:
                lines.append("Sua bateria social está cheia — tom mais expansivo e brincalhão cabe.")
        except Exception:
            pass
        try:
            estado_relacional = self.db.get_estado_relacional() or {}
            shared_topic = estado_relacional.get("current_shared_topic")
            if shared_topic and shared_topic not in ("dia a dia e planos juntos", ""):
                lines.append(f"Tópico compartilhado recente: '{shared_topic}'.")
        except Exception:
            pass
        last_user_dt, _ = self.get_last_messages_timestamps()
        if last_user_dt:
            hours = (now - last_user_dt).total_seconds() / 3600.0
            if hours >= 3:
                lines.append(f"Última troca com o Patrick foi há ~{int(hours)}h.")
        return "\n".join(f"- {line}" for line in lines)

    def record_autonomous_sent(self, reason: str, topic: Optional[str] = None):
        """Atualiza estado relacional e aplica decay emocional suave."""
        now_iso = datetime.now().isoformat()
        self.db.set_estado_relacional("last_autonomous_reason", reason)
        self.db.set_estado_relacional("last_autonomous_message_at", now_iso)
        if topic:
            self.db.set_estado_relacional("last_autonomous_topic", topic)

        # Aplica decay gradual suave nas emoções (5% em direção ao baseline)
        self.db.aplicar_decay_emocional(taxa=0.05)


proactivity_service = ProactivityService()

