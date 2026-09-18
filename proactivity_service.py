"""
Serviço de Proatividade e Iniciativa Autônoma Contextual (Proactivity Service).
Gerencia a vontade própria de Marina com inteligência de continuidade,
follow-up de compromissos passados do Patrick e anti-spam rigoroso.
"""
import random
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, Tuple

from config import settings
from db import db_manager, DatabaseManager
from prompts import EVENTOS_COTIDIANO, get_temporal_greeting

logger = logging.getLogger("ProactivityService")


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

        living = (getattr(settings, 'LIVING_WORLD_ENABLED', False)
                  and getattr(settings, 'RELATIONSHIP_WORLD_ENABLED', False))

        # 1. Janela de sono
        if self.check_sleep_window(dt):
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
        if getattr(settings, "OPEN_LOOPS_ENABLED", True):
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

    def determine_proactive_prompt(self, now: Optional[datetime] = None, auto_complete: bool = False) -> Dict[str, Any]:
        """
        Determina a razão e o prompt estruturado de proatividade segundo hierarquia:
        1. Evento pendente vencido (ex: como foi a reunião?)
        2. Open Loop pronto para check-in (ex: teve novidades sobre aquela vaga?)
        3. Assunto recente compartilhado
        4. Rotina e momento do dia
        """
        dt = now or datetime.now()
        contexto_tempo = get_temporal_greeting()

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
                    f"Agora é {contexto_tempo}. Você acabou de se lembrar com carinho de namorada que o Patrick "
                    f"tinha o seguinte compromisso: '{desc}'. "
                    f"Pergunte a ele como foi e como ele está, mostrando interesse genuíno e afeto natural de namorada!"
                )
            }

        # Prioridade 2: Open Loop pronto para check-in (Release 3.5.1)
        if getattr(settings, "OPEN_LOOPS_ENABLED", True):
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
                        f"Agora é {contexto_tempo}. Você lembrou de um assunto que o Patrick comentou recentemente: "
                        f"'{loop['content']}'. "
                        "Puxe conversa de forma carinhosa, perguntando se teve alguma novidade ou como estão as coisas sobre isso, "
                        "com total leveza e afeto de namorada, sem cobrança."
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
                    f"Agora é {contexto_tempo}. Você estava aqui no apê pensando no assunto que vocês conversaram sobre '{shared_topic}'. "
                    f"Mande uma mensagem espontânea puxando esse assunto com doçura e intimidade!"
                )
            }

        # Prioridade 4: Momento cotidiano espontâneo
        evento_aleatorio = random.choice(EVENTOS_COTIDIANO)
        return {
            "reason": "daily_routine",
            "event_id": None,
            "instruction": (
                f"Agora é {contexto_tempo}. No seu dia a dia, {evento_aleatorio}. "
                "Você pensou no Patrick com carinho, saudades, empolgação ou vontade de provocar. "
                "Decida o que você quer mandar para o seu namorado agora com base na sua personalidade espontânea e no seu ciclo biológico."
            )
        }

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
