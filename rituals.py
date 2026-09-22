"""Fase C.3 — rituais de namorada na rotina.

Pedido do Patrick: "dar bom dia ao acordar caso acorde primeiro, boa noite
antes de ir realmente dormir se eu já não tiver dado… e coisas do cotidiano
que namorados usam para chamar atenção ou puxar conversa".

Três tipos, todos disparados pela agenda real dela (não pelo sorteio da
proatividade, e sem gastar a cota dele):

* **bom dia** — 5 a 40 min depois de ela acordar, se o Patrick não escreveu
  desde que ela deitou (se escreveu, ela responde a mensagem dele);
* **boa noite** — 5 a 30 min antes de deitar, se ele ainda não deu boa noite
  desde as 20h e ela não está na rua;
* **cotidiano** — mudanças reais de estado viram assunto: saiu da aula,
  levou o Milo, saiu da academia, vai tomar banho. No máximo 2 por dia,
  sorteados por dia. O banho registra uma transição: ela some de verdade por
  15–30 min. Com o humor provocador (ciclo, excitação, carinho e brincadeira
  altos), o tom pode ter malícia leve.

O texto sai pela voz normal (`_proactive_text`: prompt, biblioteca, guards).
"""
from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Optional

logger = logging.getLogger("Rituals")

PREFIX = "ritual:"
BOM_DIA_LAG_MIN = (5, 40)
BOA_NOITE_BEFORE_MIN = (5, 30)
DAILY_CHANCE = {"bom_dia": 0.85, "boa_noite": 0.85}
COTIDIANO_CHANCE = 0.45
COTIDIANO_MAX_PER_DAY = 2
MIN_GAP_MIN = 45             # entre qualquer iniciativa dela e um ritual de cotidiano
SHOWER_EVENING = ("19:30", "22:30")
SHOWER_AFTER_GYM_MIN = (20, 40)
SHOWER_DURATION_MIN = (15, 30)

_BOA_NOITE_RE = re.compile(r"\b(boa noite|boa noitee+|bna|dorme bem|durma bem|bons sonhos|vou dormir)\b", re.I)

COTIDIANO_TEXT = {
    "saiu_da_aula": "você acabou de sair da faculdade (agora: {activity})",
    "passeio_milo": "você está saindo agora pra passear com o Milo",
    "saiu_academia": "você acabou de sair da academia (agora: {activity})",
    "banho": "você vai tomar banho agora e vai sumir uns minutos",
}


@dataclass
class Ritual:
    kind: str                 # bom_dia | boa_noite | cotidiano
    key: str
    reason: str               # chave de instrução em bot._PROACTIVE_INSTRUCTIONS
    detail: str
    fallback: str
    moment: str = ""
    extra: dict = field(default_factory=dict)


class Rituals:
    def __init__(self, db, cycle_mgr=None):
        self.db = db
        self.cycle_mgr = cycle_mgr

    # ------------------------------------------------------------- marcas --
    def _get(self, key: str) -> Optional[str]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT value FROM world_bootstrap WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def _set(self, key: str, value: str, now: datetime) -> None:
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES (?, ?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                         (key, value, now.isoformat()))
            conn.commit()

    def _count_today(self, day, kind: str) -> int:
        with self.db.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM world_bootstrap WHERE key LIKE ? AND value='sent'",
                                (f"{PREFIX}{day.isoformat()}:{kind}%",)).fetchone()[0]

    # ------------------------------------------------------------- agenda --
    def _has_class(self, day) -> bool:
        from academic_life import AcademicLife
        return bool(AcademicLife(self.db).blocks_on(day))

    def _sleep_window(self, day) -> Optional[tuple[datetime, datetime]]:
        from world_state import RoutineEngine
        windows = RoutineEngine(self.db)._sleep_windows(day, self._has_class(day))
        return min(windows) if windows else None

    def wake_at(self, day) -> Optional[datetime]:
        window = self._sleep_window(day)
        return window[1] if window else None

    def bed_at(self, day) -> Optional[datetime]:
        """Hora de deitar da noite de `day` (o sono de amanhã começa à meia-noite)."""
        window = self._sleep_window(day + timedelta(days=1))
        return window[0] if window else None

    @staticmethod
    def _rng(day, name: str) -> random.Random:
        return random.Random(f"marina-ritual:{day.isoformat()}:{name}")

    # ------------------------------------------------------------- conversa --
    def _patrick_since(self, since: datetime) -> list[str]:
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT content FROM conversas WHERE role='user' AND timestamp > ? "
                                "ORDER BY id", (since.isoformat(),)).fetchall()
        return [r["content"] or "" for r in rows]

    def _last_patrick_at(self) -> Optional[datetime]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT timestamp FROM conversas WHERE role='user' "
                               "ORDER BY id DESC LIMIT 1").fetchone()
        try:
            return datetime.fromisoformat(row["timestamp"]) if row and row["timestamp"] else None
        except ValueError:
            return None

    def _last_initiative_at(self) -> Optional[datetime]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT timestamp FROM conversas WHERE role='assistant' AND is_initiative=1 "
                               "ORDER BY id DESC LIMIT 1").fetchone()
        try:
            return datetime.fromisoformat(row["timestamp"]) if row and row["timestamp"] else None
        except ValueError:
            return None

    def _owes_reply(self) -> bool:
        with self.db.get_connection() as conn:
            return bool(conn.execute("SELECT 1 FROM response_pending_batches "
                                     "WHERE status IN ('PENDING','READY','SENDING') LIMIT 1").fetchone())

    def _chat_hint(self, now: datetime) -> str:
        last = self._last_patrick_at()
        if last and (now - last) <= timedelta(minutes=15):
            return (" Vocês estavam conversando agora há pouco: encaixe isso na conversa, sem cumprimentar "
                    "de novo.")
        return ""

    # ------------------------------------------------------------- humor --
    def _flirty(self, now: datetime) -> bool:
        try:
            from intimacy import IntimacyEngine
            if IntimacyEngine(self.db).current(now).arousal >= 0.2:
                return True
        except Exception:
            pass
        try:
            phase = (self.cycle_mgr.get_cycle_info().get("phase_key", "") if self.cycle_mgr else "")
        except Exception:
            phase = ""
        if phase == "menstrual":
            return False
        emo = {k: v["valor"] for k, v in self.db.get_estado_emocional(now).items()}
        warm = emo.get("romantic_intensity", 0) >= 0.85 and emo.get("playfulness", 0) >= 0.78
        fertile = phase in ("ovulatoria", "folicular")
        return warm or (fertile and self._rng(now.date(), "flerte").random() < 0.35)

    # ------------------------------------------------------------- estado --
    def _state(self, now: datetime) -> tuple[str, str]:
        from world_state import WorldStateManager
        from response_availability import ResponseAvailabilityPolicy
        snap = WorldStateManager(self.db).resolve(now)
        place_key = None
        if snap.get("location_place_id"):
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT canonical_key FROM world_places WHERE id=?",
                                   (snap["location_place_id"],)).fetchone()
            place_key = row["canonical_key"] if row else None
        activity = snap.get("activity") or ""
        kind = ResponseAvailabilityPolicy(self.db)._map_place_activity(place_key, activity)
        return kind, activity

    # ------------------------------------------------------------- decisão --
    def tick(self, now: Optional[datetime] = None) -> Optional[Ritual]:
        """Chamado a cada poucos minutos. Devolve o ritual a enviar agora, se houver."""
        now = now or datetime.now()
        day = now.date()
        kind, activity = self._state(now)
        previous = self._get("ritual_last_kind")
        self._set("ritual_last_kind", kind, now)

        ritual = self._bom_dia(now, kind, activity) or self._boa_noite(now, kind)
        if ritual:
            return ritual
        return self._cotidiano(now, day, previous, kind, activity)

    def _bom_dia(self, now: datetime, kind: str, activity: str = "") -> Optional[Ritual]:
        day = now.date()
        key = f"{PREFIX}{day.isoformat()}:bom_dia"
        wake = self.wake_at(day)
        if not wake or self._get(key) or kind == "SLEEPING":
            return None
        rng = self._rng(day, "bom_dia")
        at = wake + timedelta(minutes=rng.randint(*BOM_DIA_LAG_MIN))
        if not (at <= now < wake + timedelta(hours=3)):
            return None
        if rng.random() >= DAILY_CHANCE["bom_dia"]:
            self._set(key, "skipped:dia_sem_ritual", now)
            return None
        bed = self.bed_at(day - timedelta(days=1)) or wake - timedelta(hours=8)
        if self._patrick_since(bed) or self._owes_reply():
            self._set(key, "skipped:patrick_primeiro", now)
            return None
        agenda = "hoje tem aula" if self._has_class(day) else "hoje é dia livre, sem aula"
        agora = f" Agora você está: {activity}." if activity else ""
        return Ritual("bom_dia", key, "ritual_bom_dia", f"Você acordou às {wake:%H:%M}; {agenda}.{agora}",
                      "Bom dia, amor 🖤")

    def _boa_noite(self, now: datetime, kind: str) -> Optional[Ritual]:
        day = now.date()
        key = f"{PREFIX}{day.isoformat()}:boa_noite"
        bed = self.bed_at(day)
        if not bed or self._get(key):
            return None
        rng = self._rng(day, "boa_noite")
        at = bed - timedelta(minutes=rng.randint(*BOA_NOITE_BEFORE_MIN))
        if not (at <= now < bed):
            return None
        if rng.random() >= DAILY_CHANCE["boa_noite"]:
            self._set(key, "skipped:dia_sem_ritual", now)
            return None
        evening = datetime.combine(day, time(20, 0))
        if any(_BOA_NOITE_RE.search(t) for t in self._patrick_since(evening)):
            self._set(key, "skipped:patrick_ja_deu", now)
            return None
        if kind == "SOCIAL":
            self._set(key, "skipped:na_rua", now)
            return None
        return Ritual("boa_noite", key, "ritual_boa_noite",
                      "Você está indo deitar agora." + self._chat_hint(now), "Boa noite, amor 🖤 dorme bem")

    def _cotidiano(self, now, day, previous: Optional[str], kind: str, activity: str) -> Optional[Ritual]:
        moment = None
        if previous == "CLASS" and kind not in ("CLASS", "SLEEPING"):
            moment = "saiu_da_aula"
        elif previous and previous != "PET_WALK" and kind == "PET_WALK":
            moment = "passeio_milo"
        elif previous == "GYM" and kind not in ("GYM", "SLEEPING"):
            moment = "saiu_academia"
            gap = self._rng(day, "banho_pos_treino").randint(*SHOWER_AFTER_GYM_MIN)
            self._set(f"{PREFIX}{day.isoformat()}:banho_at", (now + timedelta(minutes=gap)).isoformat(), now)
        if moment is None and kind == "HOME_RELAXING":
            moment = self._shower_due(now, day)
        if moment is None:
            return None

        key = f"{PREFIX}{day.isoformat()}:cotidiano:{moment}"
        if self._get(key):
            return None
        rng = self._rng(day, f"cotidiano:{moment}")
        flirty = self._flirty(now)
        chance = COTIDIANO_CHANCE + (0.2 if moment == "banho" and flirty else 0.0)
        if rng.random() >= chance:
            self._set(key, "skipped:dia_sem_ritual", now)
            return None
        if self._count_today(day, "cotidiano") >= COTIDIANO_MAX_PER_DAY:
            self._set(key, "skipped:teto_do_dia", now)
            return None
        last = self._last_initiative_at()
        if (last and now - last < timedelta(minutes=MIN_GAP_MIN)) or self._owes_reply():
            self._set(key, "skipped:cedo_demais", now)
            return None
        tom = (" Hoje você está com humor provocador: pode ter um toque de malícia leve, sem ser explícita."
               if flirty else "")
        detail = COTIDIANO_TEXT[moment].format(activity=activity) + "." + tom + self._chat_hint(now)
        fallback = {"saiu_da_aula": "Saí da aula agora, amor 🖤", "passeio_milo": "Vou levar o Milo pra passear 🐶",
                    "saiu_academia": "Saí da academia morta kkk", "banho": "Vou tomar banho, já volto 🖤"}[moment]
        extra = {}
        if moment == "banho":
            extra["shower_minutes"] = rng.randint(*SHOWER_DURATION_MIN)
        return Ritual("cotidiano", key, "ritual_cotidiano", detail, fallback, moment, extra)

    def _shower_due(self, now: datetime, day) -> Optional[str]:
        planned = self._get(f"{PREFIX}{day.isoformat()}:banho_at")
        if planned:
            at = datetime.fromisoformat(planned)
        else:
            lo, hi = (datetime.combine(day, time.fromisoformat(t)) for t in SHOWER_EVENING)
            at = lo + timedelta(minutes=self._rng(day, "banho").randint(0, int((hi - lo).total_seconds() // 60)))
        return "banho" if at <= now < at + timedelta(minutes=20) else None

    # ------------------------------------------------------------- efeitos --
    def mark(self, ritual: Ritual, now: datetime, status: str = "sent") -> None:
        self._set(ritual.key, status, now)
        if status == "sent" and ritual.moment == "banho":
            minutes = ritual.extra.get("shower_minutes", 20)
            payload = {"routine_type": "shower", "activity": "tomando banho", "place_key": "marina_apartment",
                       "announced_at": now.isoformat(),
                       "transition_at": (now + timedelta(minutes=2)).isoformat(),
                       "end_at": (now + timedelta(minutes=2 + minutes)).isoformat()}
            self.db.set_estado_relacional("pending_transition_json", json.dumps(payload))
        logger.info("ritual.%s key=%s", status, ritual.key)
