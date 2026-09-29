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
ARTE_ANTES_DE_DORMIR = timedelta(minutes=30)   # arte adiada (ela estava na rua) não entra na hora de deitar
ARTE_DEPOIS_DE_CHEGAR = (20, 40)   # 28/09 (auditoria): adiada, vem 20–40 min depois que ela chega, não no minuto
XIXI_ANTES_DO_PASSEIO = timedelta(minutes=90)   # passeio mais perto que isso do xixi: só o passeio
ANTICS = ("roubou uma meia e saiu correndo pela casa", "latiu pro entregador do iFood",
          "pediu colo e não quis mais sair", "deitou em cima da roupa que ela ia usar",
          "ficou encarando ela até ganhar um petisco", "fez xixi no tapete do banheiro",
          "dormiu encostado nela no sofá")
# 28/09 (Patrick): dormir encostado nela não é arte, é chamego — no Hoje, "Chamego com o Milo"
CHAMEGO = ("dormiu encostado nela no sofá", "pediu colo e não quis mais sair")


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
                from world_state import current_energy
                energy = current_energy(self.db)
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

    def _passeio(self, day: date) -> Optional[dict]:
        try:
            from academia import PasseioMilo
            return PasseioMilo(self.db).plano(day)
        except Exception:
            return None

    def _cafe(self, day: date):
        try:
            from meals import Meals
            return next((s for s in Meals(self.db).day_plan(day)
                         if s.kind == "cafe" and s.where == "casa" and not s.skipped), None)
        except Exception:
            return None

    def day_plan(self, day: date) -> list[dict]:
        iso = day.isoformat()
        plan = []
        rng = _rng(day, "manha")
        at = self._wake(day) + timedelta(minutes=rng.randint(5, 25))
        minutes = rng.randint(10, 15)
        cafe = self._cafe(day)
        if cafe and at < cafe.end and at + timedelta(minutes=minutes) > cafe.at:
            # 28/09: o café (quando ela toma) e a descida não se atropelam — desce antes se dá, senão depois.
            antes = cafe.at - timedelta(minutes=minutes + 1)
            at = antes if antes >= self._wake(day) + timedelta(minutes=3) else cafe.end + timedelta(minutes=1)
        passeio = self._passeio(day)
        # 27/09 (auditoria): o xixi rapidinho saía 09:28 e o passeio planejado 09:41 — duas descidas em
        # 13 min. Com o passeio logo depois de acordar, o passeio é a saída da manhã.
        if not (passeio and passeio["inicio"] - at < XIXI_ANTES_DO_PASSEIO):
            plan.append({"key": f"milo:{iso}:manha", "at": at, "minutes": minutes, "state": False,
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
            texto = rng.choice(ANTICS)
            plan.append({"key": f"milo:{iso}:arte", "at": at, "minutes": 0, "state": False, "em_casa": True,
                         "chamego": texto in CHAMEGO, "summary": f"O Milo {texto}."})
        return sorted(plan, key=lambda p: p["at"])

    # ------------------------------------------------------------ mundo --
    def _depois_de_chegar(self, item: dict, now: datetime) -> Optional[datetime]:
        """28/09 (auditoria): a arte adiada caía no minuto da chegada, junto com "Brincando com o Milo" (17:43).
        Vem 20–40 min depois que ela chega, fora de etapa da aba Agora. None: ainda não é hora."""
        from meals import Meals
        chegou = now
        with self.db.get_connection() as conn:          # o 1º retrato em casa depois do último fora (ou cochilo)
            rows = conn.execute("SELECT * FROM world_state WHERE observed_at<=? ORDER BY observed_at DESC, id DESC "
                                "LIMIT 400", (now.isoformat(),)).fetchall()
        for r in rows:
            if Meals._fora(dict(r)):
                break
            chegou = datetime.fromisoformat(r["observed_at"])
        at = max(chegou, item["at"]) + timedelta(minutes=_rng(item["at"].date(), "arte:chegada").randint(*ARTE_DEPOIS_DE_CHEGAR))
        if at > now:
            return None
        try:
            from agenda import Agenda
            ag = Agenda(self.db)
            if ag.agora(now) is not None:
                return None               # se arrumando pra sair de novo: fica pra quando voltar
            if ag.agora(at) is not None:
                at = now
        except Exception:
            pass
        return at

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
            at = item["at"]
            if item["state"]:
                # 28/09 (auditoria, rodada 3): o xixi da noite desceu 21:30–21:38 no meio do jantar (21:07–21:41)
                # e o mundo ficou em "jantando". Comendo, no banho ou estudando, o Milo espera ela terminar.
                if meals._transition_busy(now):
                    continue
                if now >= at + timedelta(minutes=item["minutes"]):
                    at = now          # passou da hora esperando: desce agora
            end = at + timedelta(minutes=item["minutes"])
            if item.get("em_casa"):
                # 28/09 (bug 14): a arte é coisa de casa (sofá, meia, tapete). Se ela estava na rua na hora,
                # o Milo apronta 20–40 min depois que ela chega — nunca durante o passeio nem perto de deitar.
                if not meals._at_home():
                    continue
                if meals._away_at(at):
                    at = self._depois_de_chegar(item, now)
                    if at is None or now >= self._bed(now.date()) - ARTE_ANTES_DE_DORMIR:
                        continue
            with self.db.get_connection() as conn:
                fim_item = at + timedelta(minutes=item["minutes"]) if item["minutes"] else None
                cur = conn.execute(
                    """INSERT OR IGNORE INTO life_events(event_key,event_at,end_at,event_type,title,summary,
                       source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                       VALUES (?,?,?,?,?,?,'simulated',1,0.1,?,0.3,?)""",
                    (item["key"], at.isoformat(), fim_item.isoformat() if fim_item else None, "routine",
                     "Milo", item["summary"], json.dumps(["marina"]), now.isoformat()))
                conn.commit()
                fresh = bool(cur.rowcount)
            created += int(fresh)
            if fresh and item["state"] and now < end:
                payload = {"routine_type": "pet_walk", "activity": "passeio rapidinho com o Milo (xixi da noite)",
                           "place_key": "marina_apartment", "announced_at": now.isoformat(),
                           "transition_at": at.isoformat(), "end_at": end.isoformat()}
                self.db.set_estado_relacional("pending_transition_json", json.dumps(payload, ensure_ascii=False))
        return created
