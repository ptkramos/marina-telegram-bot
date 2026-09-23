"""Fase D5 — Milo, o Shih Tzu dela (cânone).

Antes: um passeio por dia (o slot da agenda) e só. Cachorro de verdade sai de
2 a 3 vezes, e um Shih Tzu — pequeno, focinho curto — cansa rápido e sofre no
calor.

* **Xixi da manhã**: desce rapidinho logo depois de acordar (10–15 min).
* **Passeio principal**: o slot da agenda (`pet_walk`), agora longe do sol das
  11h30–15h30. Em dia puxado ou cansada, ela pode pagar um **passeador** — "na
  zona sul isso é normal" (Patrick, 23/09). A decisão é dela: cansaço e agenda
  pesam na chance, não obrigam.
* **Xixi da noite**: saidinha curta antes de deitar; vira estado ("passeio
  rapidinho com o Milo").
* **Milo aprontando**: de vez em quando ele apronta — assunto real pro dia.

Determinístico por data; mesmas travas do dia social.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta
from typing import Optional

WALKER_CHANCE_BUSY = 0.55       # dia de aula que termina tarde
WALKER_CHANCE_TIRED = 0.35      # noite curta
WALKER_EXTRA_LOW_ENERGY = 0.2
HEAT_BLOCK = (time(11, 30), time(15, 30))
ANTICS_CHANCE = 0.25
ANTICS = ("roubou uma meia e saiu correndo pela casa", "latiu pro entregador do iFood",
          "fez manha pedindo colo a noite toda", "deitou em cima da roupa que ela ia usar",
          "ficou encarando ela até ganhar um petisco", "fez xixi no tapete do banheiro",
          "dormiu encostado nela no sofá")


def _rng(day: date, name: str) -> random.Random:
    return random.Random(f"marina-milo:{day.isoformat()}:{name}")


class Milo:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------- decisões --
    def _last_class_end(self, day: date) -> Optional[datetime]:
        try:
            from academic_life import AcademicLife
            blocks = AcademicLife(self.db).blocks_on(day)
        except Exception:
            return None
        return max((datetime.fromisoformat(b["end_at"]) for b in blocks), default=None)

    def walker_today(self, day: date) -> bool:
        """Ela chama o passeador? Dia puxado e cansaço pesam; quem decide é ela."""
        chance = 0.0
        last = self._last_class_end(day)
        if last and last.time() >= time(16, 0):
            chance = max(chance, WALKER_CHANCE_BUSY)
        try:
            from sleep_plan import SleepPlan, enabled
            if enabled() and SleepPlan(self.db).hours_slept(day) < 6.0:
                chance = max(chance, WALKER_CHANCE_TIRED)
        except Exception:
            pass
        if chance:
            try:
                energy = float(self.db.get_estado_emocional()["energy"]["valor"])
                if energy < 0.35:
                    chance += WALKER_EXTRA_LOW_ENERGY
            except Exception:
                pass
        return _rng(day, "passeador").random() < chance

    def _wake(self, day: date) -> datetime:
        try:
            from rituals import Rituals
            return Rituals(self.db).wake_at(day) or datetime.combine(day, time(8, 0))
        except Exception:
            return datetime.combine(day, time(8, 0))

    def _bed(self, day: date) -> datetime:
        try:
            from rituals import Rituals
            return Rituals(self.db).bed_at(day) or datetime.combine(day, time(23, 30))
        except Exception:
            return datetime.combine(day, time(23, 30))

    def day_plan(self, day: date) -> list[dict]:
        iso = day.isoformat()
        plan = []
        rng = _rng(day, "manha")
        at = self._wake(day) + timedelta(minutes=rng.randint(5, 25))
        plan.append({"key": f"milo:{iso}:manha", "at": at, "minutes": rng.randint(10, 15), "state": False,
                     "summary": "Desceu rapidinho com o Milo pro xixi da manhã."})
        if self.walker_today(day):
            rng = _rng(day, "passeador_hora")
            at = datetime.combine(day, time(17, 0)) + timedelta(minutes=rng.randint(0, 90))
            plan.append({"key": f"milo:{iso}:passeador", "at": at, "minutes": 0, "state": False,
                         "summary": "Pagou o passeador pra levar o Milo hoje — dia puxado."})
        rng = _rng(day, "noite")
        bed = self._bed(day)
        lo = datetime.combine(day, time(21, 30))
        hi = max(lo + timedelta(minutes=15), bed - timedelta(minutes=15))
        at = lo + timedelta(minutes=rng.randint(0, int((hi - lo).total_seconds() // 60)))
        plan.append({"key": f"milo:{iso}:noite", "at": at, "minutes": rng.randint(8, 12), "state": True,
                     "summary": "Levou o Milo pro xixi da noite, rapidinho."})
        rng = _rng(day, "arte")
        if rng.random() < ANTICS_CHANCE:
            at = datetime.combine(day, time(9, 0)) + timedelta(minutes=rng.randint(0, 12 * 60))
            plan.append({"key": f"milo:{iso}:arte", "at": at, "minutes": 0, "state": False,
                         "summary": f"O Milo {rng.choice(ANTICS)}."})
        return sorted(plan, key=lambda p: p["at"])

    # ------------------------------------------------------------ mundo --
    def materialize(self, now: datetime) -> int:
        from meals import Meals
        meals = Meals(self.db)
        floor = meals._floor(now)
        if floor is None:
            return 0
        created = 0
        for item in self.day_plan(now.date()):
            if item["at"] > now or item["at"] < floor:
                continue
            if item["state"] and not meals._at_home():
                continue              # na rua: leva o Milo quando voltar
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,
                       source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                       VALUES (?,?,?,?,?,'simulated',1,0.1,?,0.3,?)""",
                    (item["key"], item["at"].isoformat(), "routine", "Milo", item["summary"],
                     json.dumps(["marina"]), now.isoformat()))
                conn.commit()
                fresh = bool(cur.rowcount)
            created += int(fresh)
            end = item["at"] + timedelta(minutes=item["minutes"])
            if fresh and item["state"] and now < end and not meals._transition_busy(now):
                payload = {"routine_type": "pet_walk", "activity": "passeio rapidinho com o Milo (xixi da noite)",
                           "place_key": "marina_apartment", "announced_at": now.isoformat(),
                           "transition_at": item["at"].isoformat(), "end_at": end.isoformat()}
                self.db.set_estado_relacional("pending_transition_json", json.dumps(payload, ensure_ascii=False))
        return created
