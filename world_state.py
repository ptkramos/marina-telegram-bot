"""Resolução mínima de estado/rotina v3.7.1 (Patch 013).

Novidades da 3.7.1:
- Cooldown pós-compromisso: 20 min de "acabou de terminar" antes de qualquer rotina externa.
- Bloqueio de rotinas externas quando há conversa ativa nos últimos 15 min
  (Marina avisa antes de sair via anúncio proativo em `proactivity_service`).
- Horário de funcionamento canônico do local: RoutineEngine consulta
  `world_places.usage_rules_json['opening_hours']` antes de sortear.
- Estado `pending_transition`: quando um anúncio de transição já foi enviado,
  a rotina anunciada vira `explicit_plan` até `transition_at`.

Nenhuma dessas regras adiciona chamadas externas ou dependência de LLM.
"""

import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Mapping, Optional

from db import DatabaseManager
from config import settings
from world_repository import WorldBibleRepository, WorldStateRepository


logger = logging.getLogger("WorldState")

# Rotinas com deslocamento externo (não são no apartamento nem no prédio).
# Usadas para: (a) filtro de conversa ativa; (b) cooldown pós-compromisso;
# (c) triggers de anúncio proativo de transição.
EXTERNAL_ROUTINE_TYPES = frozenset({"gym", "pet_walk", "university"})

# Janela de "acabou de terminar um compromisso" durante a qual nenhuma
# rotina externa é elegível.
POST_EVENT_COOLDOWN_MINUTES = 20

# Se a última mensagem trocada foi há menos disso, rotinas externas ficam
# bloqueadas do sorteio (Marina anuncia antes de sair — ver proactivity_service).
CONVERSATION_ACTIVE_WINDOW_MINUTES = 15

# Auditoria #4 — agenda diária determinística.
# Antes, a rotina era uma amostra aleatória do INSTANTE, refeita a cada vez que
# o snapshot ficava stale (60 min). Numa janela de 15:00–21:00 isso deixava a
# Marina "treinando na academia" em quase toda amostra — cinco horas seguidas —
# e em todo dia da semana, porque `3_to_5_days_per_week` nunca era aplicado.
# Agora cada rotina com deslocamento ganha UM slot concreto por dia, derivado
# só da data: o mesmo em /status, disponibilidade, prompt, câmera e anúncio de
# saída, e o mesmo depois de um restart.
SLOT_DURATION_MINUTES = {
    "pet_walk": (30, 50),
    "gym": (60, 90),
    "gym_indoor": (60, 90),  # mesmo slot da academia de rua, só muda o lugar
}
WEEKLY_QUOTA = {"3_to_5_days_per_week": (3, 5)}
# Dia de aula: o Milo passeia onde couber entre 07:00 e 19:00, fora da faculdade.
CLASS_DAY_PET_WALK_WINDOW = ("07:00", "19:00")
CLASS_PREP_MINUTES = 60          # arrumar + ir pra PUC
CLASS_COMMUTE_BACK_MINUTES = 45  # voltar da Gávea pra Botafogo



def current_energy(db: DatabaseManager, now: Optional[datetime] = None) -> float:
    """Energia atual da Marina. Fonte única para todo leitor de rotina.

    Fase D14: vem do corpo (motor emocional) — sono da última noite, dívida de
    sono, horas acordada, moleza pós-almoço, cochilo e ciclo. Antes era um
    número que o planner empurrava pra cima a cada mensagem (0,91 depois de
    dormir 6 h)."""
    try:
        from emotion import EmotionEngine
        return EmotionEngine(db).energy(now)
    except Exception:
        return 0.7

@dataclass(frozen=True)
class RoutineCandidate:
    activity: str
    place_key: str
    score: float
    source_key: str
    routine_type: str = ""

    @property
    def is_external(self) -> bool:
        return self.routine_type in EXTERNAL_ROUTINE_TYPES


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _within_opening_hours(now: datetime, opening_hours: Optional[Mapping]) -> bool:
    """Valida se `now` cai dentro do horário de funcionamento canônico do local.

    `opening_hours` é um dict {"mon": "06:00-22:00", ..., "sun": "closed"|"09:00-14:00"}.
    Retorna True se não houver definição (compatibilidade com places antigos).
    """
    if not opening_hours:
        return True
    weekday_keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    key = weekday_keys[now.weekday()]
    window = opening_hours.get(key)
    if not window or window == "closed":
        return False
    if window == "24h":
        return True
    try:
        start_str, end_str = window.split("-")
        start = _parse_hhmm(start_str)
        end = _parse_hhmm(end_str)
    except (ValueError, AttributeError):
        logger.warning("world_state.opening_hours.invalid key=%s value=%r", key, window)
        return True
    current = now.time()
    if start <= end:
        return start <= current <= end
    # Janela cruza a meia-noite (raro pra academia, comum pra bar).
    return current >= start or current <= end


class RoutineEngine:
    """Pontua rotinas canônicas com validação de horário de funcionamento."""

    _ACTIVITIES = {
        "wake": ("acordando e tomando café", "marina_apartment"),
        "university": ("na faculdade", "puc_rio"),
        "pet_walk": ("passeando com Milo", "enseada_botafogo"),
        "gym": ("treinando na academia", "bodytech_sao_clemente"),
        "home_evening": ("curtindo a noite em casa", "marina_apartment"),
        "sleep": ("dormindo", "marina_apartment"),
    }

    def __init__(self, db: DatabaseManager, rng: Optional[random.Random] = None):
        self.db = db
        self.rng = rng or random.Random()
        # Cache por instância (um resolve/uma consulta): a agenda consulta as
        # mesmas linhas várias vezes e cada consulta abre uma conexão SQLite.
        self._row_cache: dict = {}
        self._busy_cache: dict = {}
        self._hours_cache: dict = {}

    @staticmethod
    def _within_window(now: datetime, start: Optional[str], end: Optional[str]) -> bool:
        if not start or not end:
            return True
        current = now.hour * 60 + now.minute
        first_h, first_m = map(int, start.split(":"))
        last_h, last_m = map(int, end.split(":"))
        first = first_h * 60 + first_m
        last = last_h * 60 + last_m
        return first <= current <= last if first <= last else current >= first or current <= last

    @staticmethod
    def _day_applies(scope: Optional[str], now: datetime, has_class: Optional[bool]) -> bool:
        if scope == "class_day":
            return has_class is True
        if scope == "light_day":
            return has_class is not True
        if scope == "weekday":
            return now.weekday() < 5
        return scope in (None, "daily", "3_to_5_days_per_week")

    def _place_opening_hours(self, place_key: str) -> Optional[Mapping]:
        """Consulta `world_places.usage_rules_json['opening_hours']` do local."""
        if not place_key:
            return None
        if place_key not in self._hours_cache:
            with self.db.get_connection() as conn:
                self._hours_cache[place_key] = conn.execute(
                    "SELECT usage_rules_json FROM world_places WHERE canonical_key = ?",
                    (place_key,),
                ).fetchone()
        row = self._hours_cache[place_key]
        if not row or not row["usage_rules_json"]:
            return None
        try:
            rules = json.loads(row["usage_rules_json"])
        except (TypeError, ValueError):
            return None
        return rules.get("opening_hours") if isinstance(rules, Mapping) else None

    def candidates(
        self, now: datetime, *, has_class: Optional[bool] = None,
        heavy_rain: bool = False, energy: float = 0.7,
        holiday_scope: Optional[str] = None,
        conversation_active: bool = False,
        post_event_cooldown: bool = False,
    ) -> list[RoutineCandidate]:
        if not 0 <= energy <= 1:
            raise ValueError("energy deve estar entre 0 e 1")
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM routine_patterns WHERE character_key = 'marina' AND active = 1"
            ).fetchall()
        result: list[RoutineCandidate] = []
        from sleep_plan import SleepPlan, enabled as sleep_plan_enabled
        plan = SleepPlan(self.db) if sleep_plan_enabled() else None
        if plan is not None:
            reason = plan.micro_wake_at(now)
            if reason:
                # Fase D3: acordou rapidinho de madrugada; vê o celular e volta a dormir.
                result.append(RoutineCandidate(
                    # Sem "dorm" no texto: vários pontos tratam "dorm" como dormindo.
                    f"acordou de madrugada ({reason}) e já vai deitar de novo", "marina_apartment",
                    1.0, "micro_wake", routine_type="micro_wake"))
        for row in rows:
            routine_type = row["routine_type"]
            if not self._day_applies(row["day_scope"], now, has_class):
                continue
            window_start, window_end = row["window_start"], row["window_end"]
            if routine_type == "pet_walk" and has_class:
                # Dia de aula: o passeio vai pra onde couber (manhã antes da
                # faculdade ou tarde depois dela) — o slot decide o horário.
                window_start, window_end = CLASS_DAY_PET_WALK_WINDOW
            if plan is not None and routine_type == "sleep":
                if not plan.is_asleep(now):
                    continue
                result.append(RoutineCandidate("dormindo", "marina_apartment", float(row["probability"]),
                                               row["canonical_key"], routine_type="sleep"))
                continue
            if plan is not None and routine_type == "wake":
                # Fase D13: a manhã começa quando ela acorda de fato. Com compromisso
                # ela está se arrumando até sair; sem, acordando com calma.
                wake = plan.wake(now.date())
                leave = plan._first_commitment(now.date())
                end = leave if leave and leave > wake else wake + timedelta(minutes=45)
                if not (wake <= now < end):
                    continue
                activity = ("se arrumando pra faculdade (banho, skincare, cabelo, café)" if leave
                            else "acordando e tomando café")
                result.append(RoutineCandidate(activity, "marina_apartment", float(row["probability"]),
                                               row["canonical_key"], routine_type="wake"))
                continue
            if not self._within_window(now, window_start, window_end):
                continue
            if routine_type == "university":
                # Academic blocks are handled by CalendarWorld, not by routine sorting.
                continue
            activity, place_key = self._ACTIVITIES.get(routine_type, (None, None))
            if not activity:
                continue
            is_external = routine_type in EXTERNAL_ROUTINE_TYPES

            # Filtro A: horário real de funcionamento do lugar.
            if is_external and not _within_opening_hours(now, self._place_opening_hours(place_key)):
                logger.info(
                    "routine.filtered reason=place_closed type=%s place=%s at=%s",
                    routine_type, place_key, now.isoformat(timespec="minutes"),
                )
                continue

            # Filtro B: cooldown pós-compromisso — rotina externa fica de fora
            # durante os primeiros minutos após um compromisso terminar.
            if is_external and post_event_cooldown:
                logger.info(
                    "routine.filtered reason=post_event_cooldown type=%s", routine_type,
                )
                continue

            # Filtro C: conversa ativa — Marina anuncia antes de sair via
            # proactivity_service. Enquanto isso ela fica em casa.
            if is_external and conversation_active:
                logger.info(
                    "routine.filtered reason=conversation_active type=%s", routine_type,
                )
                continue

            score = float(row["probability"])
            if holiday_scope and holiday_scope != "optional":
                if routine_type == "gym":
                    score *= 0.8
                elif routine_type == "home_evening":
                    score *= 1.1

            if routine_type == "gym":
                score *= max(0.2, energy)
                if heavy_rain:
                    # Fallback: academia do prédio (interno, sem deslocamento).
                    result.append(RoutineCandidate(
                        "treinando na academia do prédio", "marina_apartment",
                        min(1.0, score * 1.1), row["canonical_key"] + ":rain_fallback",
                        routine_type="gym_indoor",
                    ))
                    score *= 0.1
            elif routine_type == "pet_walk" and heavy_rain:
                score *= 0.25

            result.append(RoutineCandidate(
                activity, place_key, score, row["canonical_key"],
                routine_type=routine_type,
            ))
        return [candidate for candidate in result if candidate.score > 0]

    # ------------------------------------------------------------------
    # Agenda diária (Auditoria #4)
    # ------------------------------------------------------------------
    def _routine_row(self, source_key: str) -> Optional[Mapping]:
        key = source_key.split(":", 1)[0]
        if key not in self._row_cache:
            with self.db.get_connection() as conn:
                self._row_cache[key] = conn.execute(
                    "SELECT * FROM routine_patterns WHERE canonical_key = ?", (key,)
                ).fetchone()
        return self._row_cache[key]

    @staticmethod
    def happens_on(day, row: Mapping) -> bool:
        """Rotinas com cota semanal escolhem os dias da semana ISO pela data."""
        quota = WEEKLY_QUOTA.get(row["day_scope"])
        if not quota:
            return True
        year, week, _ = day.isocalendar()
        rng = random.Random(f"marina-agenda:{year}-W{week:02d}:{row['canonical_key']}")
        days = rng.sample(range(7), rng.randint(*quota))
        return day.weekday() in days

    def _class_busy(self, day) -> Optional[tuple[datetime, datetime]]:
        """Intervalo ocupado pela faculdade, com arrumação/ida e volta pra casa."""
        if day in self._busy_cache:
            return self._busy_cache[day]
        from academic_life import AcademicLife
        blocks = AcademicLife(self.db).blocks_on(day)
        if not blocks:
            self._busy_cache[day] = None
            return None
        first = min(datetime.fromisoformat(b["start_at"]) for b in blocks)
        last = max(datetime.fromisoformat(b["end_at"]) for b in blocks)
        self._busy_cache[day] = (first - timedelta(minutes=CLASS_PREP_MINUTES),
                                 last + timedelta(minutes=CLASS_COMMUTE_BACK_MINUTES))
        return self._busy_cache[day]

    def _placement(self, day, row, routine_type: str, has_class: Optional[bool]):
        """Onde o slot cai no dia (sem considerar vontade). None = não cabe."""
        duration = SLOT_DURATION_MINUTES.get(routine_type)
        if not duration or not row["window_start"] or not row["window_end"]:
            return None
        if not self.happens_on(day, row):
            return None
        if routine_type == "pet_walk":
            from milo import Milo
            if Milo(self.db).walker_today(day):
                return None       # Fase D5: dia puxado, o passeador levou o Milo
        busy = self._class_busy(day) if has_class is not False else None
        window = (row["window_start"], row["window_end"])
        if routine_type == "pet_walk" and busy:
            window = CLASS_DAY_PET_WALK_WINDOW
        start_t, end_t = _parse_hhmm(window[0]), _parse_hhmm(window[1])
        if start_t >= end_t:
            return None  # janela cruzando a meia-noite não tem slot fixo
        free = [(datetime.combine(day, start_t), datetime.combine(day, end_t))]
        blocked = [busy] if busy else []
        # Auditoria #6 (bug da #4): em dia sem aula ela dorme até 08:29 e o
        # passeio podia cair às 07:05 — o sono vencia no pick() e o Milo não
        # saía. O slot agora nunca invade a janela de sono do próprio dia.
        blocked += self._sleep_windows(day, has_class if has_class is not None else busy is not None)
        if routine_type == "pet_walk":
            # Fase D5: Shih Tzu tem focinho curto — nada de passeio no sol do meio-dia.
            from milo import HEAT_BLOCK
            blocked.append((datetime.combine(day, HEAT_BLOCK[0]), datetime.combine(day, HEAT_BLOCK[1])))
        for b_start, b_end in blocked:
            free = [piece for lo, hi in free
                    for piece in ((lo, min(hi, b_start)), (max(lo, b_end), hi)) if piece[0] < piece[1]]
        rng = random.Random(f"marina-agenda:{day.isoformat()}:{row['canonical_key']}")
        minutes = rng.randint(*duration)
        fits = [(a, b) for a, b in free if (b - a).total_seconds() // 60 >= minutes]
        if not fits:
            return None
        window_start, window_end = fits[0]  # o primeiro horário livre que cabe
        span = int((window_end - window_start).total_seconds() // 60) - minutes
        start = window_start + timedelta(minutes=rng.randint(0, span) // 5 * 5)
        slot = (start, start + timedelta(minutes=minutes))
        if routine_type == "pet_walk":
            slot = self._avoid_gym(day, slot, has_class, window_end)
            slot = self._avoid_heat(day, slot)
        return slot

    @staticmethod
    def _avoid_heat(day, slot):
        """Fase D5: o remanejamento pela academia também não pode cair no sol do meio-dia."""
        if not slot:
            return slot
        from milo import HEAT_BLOCK
        lo, hi = datetime.combine(day, HEAT_BLOCK[0]), datetime.combine(day, HEAT_BLOCK[1])
        if slot[1] <= lo or slot[0] >= hi:
            return slot
        length = slot[1] - slot[0]
        after = hi + timedelta(minutes=15)
        if after + length <= datetime.combine(day, time(21, 0)):
            return after, after + length
        return None

    def _sleep_windows(self, day, has_class: bool) -> list[tuple[datetime, datetime]]:
        from sleep_plan import SleepPlan, enabled as sleep_plan_enabled
        if sleep_plan_enabled():
            # Fase D2: o sono da noite anterior e o desta noite, variáveis por data.
            return SleepPlan(self.db).windows_on(day)
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT window_start, window_end, day_scope FROM routine_patterns "
                "WHERE character_key='marina' AND routine_type='sleep' AND active=1").fetchall()
        moment = datetime.combine(day, time(12, 0))
        result = []
        for row in rows:
            if not row["window_start"] or not row["window_end"]:
                continue
            if not self._day_applies(row["day_scope"], moment, has_class):
                continue
            start_t, end_t = _parse_hhmm(row["window_start"]), _parse_hhmm(row["window_end"])
            if start_t < end_t:
                result.append((datetime.combine(day, start_t),
                               datetime.combine(day, end_t) + timedelta(minutes=1)))
        return result

    def _avoid_gym(self, day, slot, has_class, limit):
        """Passeio e academia no mesmo dia não se sobrepõem."""
        gym_row = self._routine_row("gym_weekly")
        gym = self._placement(day, gym_row, "gym", has_class) if gym_row else None
        if not gym or slot[1] <= gym[0] or slot[0] >= gym[1]:
            return slot
        length = slot[1] - slot[0]
        gap = timedelta(minutes=15)
        before = gym[0] - gap - length
        if before.date() == day and before >= datetime.combine(day, time(7, 0)):
            return before, before + length
        after = gym[1] + gap
        return (after, after + length) if after + length <= datetime.combine(day, time(21, 0)) else None

    @staticmethod
    def _willing(day, row, candidate: RoutineCandidate) -> bool:
        """Vontade do dia: energia, chuva e feriado continuam decidindo se ela vai.

        Rolagem fixa por dia; o score do candidato (que já embute energia,
        chuva e feriado) vira a chance de ir. Para academia a referência é a
        energia normal (0,7): com disposição normal ela vai nos dias da cota;
        cansada, pode pular. Chuva forte: academia de rua quase nunca (vira a
        do prédio), passeio com o Milo 1 em 4.
        """
        base = float(row["probability"] or 0) or 1.0
        chance = candidate.score / base
        if candidate.routine_type in ("gym", "gym_indoor"):
            chance /= 0.7
        roll = random.Random(f"marina-agenda:{day.isoformat()}:{row['canonical_key']}:vontade").random()
        return roll < min(1.0, chance)

    def slot_for(
        self, now: datetime, candidate: RoutineCandidate, *, has_class: Optional[bool] = None,
    ) -> Optional[tuple[datetime, datetime]]:
        """Slot concreto do dia para rotinas com deslocamento; None = não vai hoje."""
        if candidate.routine_type not in SLOT_DURATION_MINUTES:
            return None
        row = self._routine_row(candidate.source_key)
        if not row:
            return None
        day = now.date()
        slot = self._placement(day, row, candidate.routine_type, has_class)
        if not slot or not self._willing(day, row, candidate):
            return None
        return slot

    def pick(
        self, now: datetime, candidates: list[RoutineCandidate], *,
        has_class: Optional[bool] = None,
    ) -> tuple[RoutineCandidate, Optional[datetime]]:
        """Escolha determinística: sono > slot ativo > rotina de janela > tempo livre.

        Retorna também o fim do slot, para o snapshot expirar exatamente nele.
        """
        sleeping = [item for item in candidates if item.activity == "dormindo"]
        if sleeping:
            return max(sleeping, key=lambda item: item.score), None
        in_slot = []
        for item in candidates:
            if item.routine_type not in SLOT_DURATION_MINUTES:
                continue
            slot = self.slot_for(now, item, has_class=has_class)
            if slot and slot[0] <= now < slot[1]:
                in_slot.append((item, slot[1]))
        if in_slot:
            return max(in_slot, key=lambda pair: pair[0].score)
        windowed = [item for item in candidates if item.routine_type not in SLOT_DURATION_MINUTES]
        if windowed:
            return max(windowed, key=lambda item: item.score), None
        return RoutineCandidate("tempo livre em casa", "marina_apartment", 0.2, "free_time",
                                routine_type="free_time"), None

    def choose(self, candidates: list[RoutineCandidate]) -> RoutineCandidate:
        # Sleep window locked: never let free-time keep Marina awake at dawn.
        sleeping = [item for item in candidates if item.activity == "dormindo"]
        if sleeping:
            return max(sleeping, key=lambda item: item.score)
        # Fallback permite dias banais sem forçar rotina ou plot.
        options = [
            *candidates,
            RoutineCandidate("tempo livre em casa", "marina_apartment", 0.2, "free_time",
                             routine_type="free_time"),
        ]
        return self.rng.choices(options, weights=[item.score for item in options], k=1)[0]


class WorldStateManager:
    """Compromisso > plano explícito > pending_transition > consequência > rotina."""

    def __init__(
        self, db: DatabaseManager, *, routine: Optional[RoutineEngine] = None,
        stale_minutes: int = 60,
    ):
        if stale_minutes <= 0:
            raise ValueError("stale_minutes deve ser positivo")
        self.db = db
        self.routine = routine or RoutineEngine(db)
        self.states = WorldStateRepository(db)
        self.bible = WorldBibleRepository(db)
        self.stale_minutes = stale_minutes

    @staticmethod
    def _active_plan(plan: Optional[Mapping], now: datetime) -> bool:
        if not plan or not plan.get("activity"):
            return False
        start = plan.get("start_at")
        end = plan.get("end_at")
        if start and now < datetime.fromisoformat(start):
            return False
        if end and now >= datetime.fromisoformat(end):
            return False
        if start and not end and now >= datetime.fromisoformat(start) + timedelta(hours=1):
            return False
        return True

    def _last_conversation_at(self) -> Optional[datetime]:
        """Retorna o timestamp da última mensagem trocada (user OU assistant)."""
        try:
            with self.db.get_connection() as conn:
                row = conn.execute(
                    "SELECT timestamp FROM conversas ORDER BY id DESC LIMIT 1"
                ).fetchone()
            if row and row["timestamp"]:
                return datetime.fromisoformat(row["timestamp"])
        except Exception:
            logger.exception("world_state.last_conversation.error")
        return None

    def _recent_commitment_end(self, now: datetime) -> Optional[datetime]:
        """Fim do compromisso confirmado mais recente que já terminou.

        Usado para calcular o cooldown pós-evento.
        """
        try:
            snapshot = self.states.latest()
        except Exception:
            snapshot = None
        if not snapshot:
            return None
        prior_source = json.loads(snapshot.get("source_json") or "{}")
        if prior_source.get("reason") != "confirmed_commitment":
            return None
        current_plan = json.loads(snapshot.get("current_plan_json") or "null")
        if not current_plan or not current_plan.get("end_at"):
            return None
        try:
            end_at = datetime.fromisoformat(current_plan["end_at"])
        except (TypeError, ValueError):
            return None
        return end_at if end_at <= now else None

    def _pending_transition(self, now: datetime) -> Optional[Mapping]:
        """Recupera transição anunciada e ainda não efetivada (do estado_relacional)."""
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
        if not isinstance(data, Mapping):
            return None
        transition_at = data.get("transition_at")
        if not transition_at:
            return None
        try:
            when = datetime.fromisoformat(transition_at)
        except ValueError:
            return None
        if now < when:
            # Ainda no intervalo entre anúncio e efetivação — Marina anunciou
            # mas continua em casa até o horário combinado chegar.
            return {"phase": "announced_awaiting", "data": data, "transition_at": when}
        end_at = data.get("end_at")
        if end_at:
            try:
                end_dt = datetime.fromisoformat(end_at)
            except ValueError:
                end_dt = None
            if end_dt and now >= end_dt:
                # Transição já expirou naturalmente — limpar.
                try:
                    self.db.set_estado_relacional("pending_transition_json", "")
                except Exception:
                    logger.exception("world_state.pending_transition.clear.error")
                return None
        return {"phase": "active", "data": data, "transition_at": when}

    def resolve(
        self, now: datetime, *, confirmed_commitment: Optional[Mapping] = None,
        explicit_plan: Optional[Mapping] = None,
        active_consequence: Optional[Mapping] = None,
        has_class: Optional[bool] = None, weather: Optional[Mapping] = None,
        energy: Optional[float] = None, force: bool = False,
    ) -> dict:
        if energy is None:
            energy = current_energy(self.db)
        if not 0 <= energy <= 1:
            raise ValueError("energy deve estar entre 0 e 1")
        from calendar_world import CalendarWorld, local_time
        from academic_life import AcademicLife

        now = local_time(now)
        calendar = CalendarWorld(self.db)
        academic = AcademicLife(self.db)
        academic.catch_up(now, auto_generate=True)
        try:
            from social_battery import accrue
            accrue(self.db, now)
        except Exception:
            logger.exception("social_battery.accrue.error")
        try:
            from social_day import SocialDay
            SocialDay(self.db).materialize(now)
        except Exception:
            logger.exception("social_day.materialize.error")
        try:
            # Fase D7: antes do trajeto — faltar a aula cancela a ida pra PUC.
            from college import College
            College(self.db).materialize(now)
        except Exception:
            logger.exception("college.materialize.error")
        try:
            # Fase D10: a Lívia oferece, casting, resposta, prova, job, cachê (antes do trajeto).
            from freela import Freela
            Freela(self.db).materialize(now)
        except Exception:
            logger.exception("freela.materialize.error")
        try:
            from commute import Commute
            Commute(self.db).materialize(now)
        except Exception:
            logger.exception("commute.materialize.error")
        try:
            # Fase D1: refeições cuja hora chegou viram acontecimento (e estado, em casa).
            from meals import Meals
            Meals(self.db).materialize(now)
        except Exception:
            logger.exception("meals.materialize.error")
        try:
            # Fase D5: xixi da manhã e da noite, passeador, Milo aprontando.
            from milo import Milo
            Milo(self.db).materialize(now)
        except Exception:
            logger.exception("milo.materialize.error")
        try:
            # D11: a consulta médica que já aconteceu vira acontecimento do dia.
            from health import Health
            Health(self.db).materialize(now)
        except Exception:
            logger.exception("health.materialize.error")
        try:
            # Fase D9: roupa, faxina, mercado, contas e perrengues do apê.
            from canon_extras import ensure as ensure_canon_extras
            ensure_canon_extras(self.db)   # Dona Neide e Seu Jorge (24/09)
            from casa import Casa
            Casa(self.db).materialize(now)
        except Exception:
            logger.exception("casa.materialize.error")
        try:
            # Fase D6: a sessão de série/anime da noite (e o que ela descobre sozinha).
            from watch import Watching
            Watching(self.db).materialize(now)
        except Exception:
            logger.exception("watch.materialize.error")
        if has_class is None:
            has_class = bool(academic.blocks_on(now.date()))
        if confirmed_commitment is None:
            confirmed_commitment = calendar.current(now, include_academic=True)
        if weather is None:
            observed_weather = calendar.context.get("weather:rio", now=now)
            if observed_weather:
                weather = observed_weather["payload"]
        observed_holiday = calendar.context.get(f"holiday:{now.date().isoformat()}", now=now)
        holiday_scope = (observed_holiday["payload"]["scope"] if observed_holiday else None)

        reason = None
        chosen: Optional[Mapping] = None
        pending_transition = self._pending_transition(now)
        commute_leg = None
        try:
            from commute import Commute
            commute_leg = Commute(self.db).leg_at(now)
        except Exception:
            logger.exception("commute.leg_at.error")

        if confirmed_commitment and confirmed_commitment.get("start_at") and self._active_plan(confirmed_commitment, now):
            chosen = confirmed_commitment
            reason = "confirmed_commitment"
        elif self._active_plan(explicit_plan, now):
            chosen = explicit_plan
            reason = "explicit_plan"
        elif commute_leg is not None:
            # Fase C.4: entre compromissos ela está a caminho, não teleporta.
            chosen = {
                "activity": commute_leg.activity(now),
                "place_key": None,
                "location_region": f"a caminho ({commute_leg.region})",
                "start_at": commute_leg.start.isoformat(),
                "end_at": commute_leg.end.isoformat(),
            }
            reason = "commute"
        elif pending_transition and pending_transition["phase"] == "active":
            # Transição anunciada e horário atingido: Marina agora ESTÁ na atividade
            # anunciada. Vira `explicit_plan` de fato.
            data = pending_transition["data"]
            chosen = {
                "activity": data.get("activity") or "fora de casa",
                "place_key": data.get("place_key"),
                "start_at": data.get("transition_at"),
                "end_at": data.get("end_at"),
            }
            reason = "announced_transition"
        elif self._active_plan(active_consequence, now):
            chosen = active_consequence
            reason = "active_consequence"

        previous = self.states.latest()
        if chosen is None and previous and not force:
            observed = datetime.fromisoformat(previous["observed_at"])
            age = now - observed
            prev_weather = json.loads(previous["weather_context_json"] or "null")
            prev_heavy = bool(prev_weather and prev_weather.get("heavy_rain"))
            curr_heavy = bool(weather and weather.get("heavy_rain"))
            weather_changed = prev_heavy != curr_heavy
            previous_plan = json.loads(previous["current_plan_json"] or "null")
            plan_expired = previous_plan is not None and not self._active_plan(previous_plan, now)
            prior_source = json.loads(previous["source_json"] or "{}")
            if prior_source.get("holiday_scope") != holiday_scope:
                plan_expired = True
            if prior_source.get("calendar_event_id") or prior_source.get("academic_block_id"):
                plan_expired = True
            sleep_now = any(
                candidate.activity == "dormindo"
                for candidate in self.routine.candidates(
                    now, has_class=has_class,
                    heavy_rain=bool(weather and weather.get("heavy_rain")),
                    energy=energy, holiday_scope=holiday_scope,
                )
            )
            previous_sleeping = any(
                token in (previous.get("activity") or "").casefold()
                for token in ("dorm", "sleep", "sono")
            )
            slot_end_raw = prior_source.get("slot_end")
            if slot_end_raw:
                # Auditoria #4: saiu pra um slot, fica nele até o fim — mesmo que
                # o Patrick comece a conversar no meio. Antes, o re-sorteio com
                # `conversation_active` a teletransportava de volta pra casa.
                if (timedelta(0) <= age and now < datetime.fromisoformat(slot_end_raw)
                        and not plan_expired and not (sleep_now and not previous_sleeping)):
                    return previous
            elif (timedelta(0) <= age < timedelta(minutes=self.stale_minutes)
                    and not weather_changed and not plan_expired
                    and not (sleep_now and not previous_sleeping)
                    # Fase D2/D3: acordar (de manhã ou num micro-despertar) também
                    # vira estado na hora — antes ela ficava "dormindo" até 60 min.
                    and not (previous_sleeping and not sleep_now)
                    and not self._slot_began(now, has_class=has_class, weather=weather,
                                             energy=energy, holiday_scope=holiday_scope)):
                return previous

        slot_end: Optional[datetime] = commute_leg.end if reason == "commute" else None
        if chosen is None:
            # Sinais para o RoutineEngine sobre cooldown e conversa ativa.
            recent_end = self._recent_commitment_end(now)
            post_event_cooldown = bool(
                recent_end and (now - recent_end) < timedelta(minutes=POST_EVENT_COOLDOWN_MINUTES)
            )
            last_conv = self._last_conversation_at()
            conversation_active = bool(
                last_conv and (now - last_conv) < timedelta(minutes=CONVERSATION_ACTIVE_WINDOW_MINUTES)
            )
            heavy_rain = bool(weather and weather.get("heavy_rain"))
            candidates = self.routine.candidates(
                now, has_class=has_class, heavy_rain=heavy_rain, energy=energy,
                holiday_scope=holiday_scope,
                conversation_active=conversation_active,
                post_event_cooldown=post_event_cooldown,
            )
            selected, slot_end = self.routine.pick(now, candidates, has_class=has_class)

            # Se o cooldown pós-evento está ativo, marcamos explicitamente
            # para o world_context descrever o estado como "acabei de X".
            if post_event_cooldown and selected.source_key == "free_time":
                reason = "post_event_recovery"
                chosen = {
                    "activity": "em casa, ainda relaxando depois do compromisso anterior",
                    "place_key": "marina_apartment",
                }
            else:
                chosen = {"activity": selected.activity, "place_key": selected.place_key}
                reason = selected.source_key

        place_key = chosen.get("place_key") if isinstance(chosen, Mapping) else None
        place = self.bible.get_place(place_key) if place_key else None
        return self.states.add_snapshot({
            "state_date": now.date().isoformat(),
            "observed_at": now.isoformat(),
            "location_place_id": place["id"] if place else None,
            "location_region": place["region"] if place else chosen.get("location_region"),
            "activity": chosen["activity"],
            "energy_level": energy,
            "weather_context_json": dict(weather) if weather else None,
            "current_plan_json": dict(chosen) if reason in (
                "confirmed_commitment", "explicit_plan", "announced_transition",
            ) else None,
            "source_json": {
                "truth_type": "system", "reason": reason,
                "holiday_scope": holiday_scope,
                "calendar_event_id": chosen.get("calendar_event_id"),
                "academic_block_id": chosen.get("academic_block_id"),
                "slot_end": slot_end.isoformat() if slot_end else None,
            },
        })

    def _slot_began(self, now: datetime, *, has_class: Optional[bool], weather: Optional[Mapping],
                    energy: float, holiday_scope: Optional[str]) -> bool:
        """Um slot da agenda começou depois do snapshot em casa (e nada o bloqueia)?"""
        last_conv = self._last_conversation_at()
        candidates = self.routine.candidates(
            now, has_class=has_class, heavy_rain=bool(weather and weather.get("heavy_rain")),
            energy=energy, holiday_scope=holiday_scope,
            conversation_active=bool(
                last_conv and (now - last_conv) < timedelta(minutes=CONVERSATION_ACTIVE_WINDOW_MINUTES)
            ),
        )
        _, slot_end = self.routine.pick(now, candidates, has_class=has_class)
        return slot_end is not None
