"""Fase D9 — casa e vida adulta: roupa, faxina, mercado, contas e perrengues do apê.

Antes (24/09): a casa dela não existia como rotina. Ela nunca lavava roupa,
nunca ia ao mercado, nunca arrumava nada, e lâmpada nenhuma queimava.

Mesmo molde do `milo.py`: o plano de cada dia sai da data (determinístico) e
o que já aconteceu vira acontecimento do dia (`life_events`, chave
`casa:<dia>:<o quê>`), que o motor emocional lê (emotion.appraise_event).
O mercado vira estado ("no mercado") por uns 45–70 min.

Decisões PROVISÓRIAS (Patrick dormindo em 24/09 pediu pra eu decidir e
catalogar — PLANO_VOZ, seção D9):
1. Ela mesma cuida da casa (sem diarista): máquina 2×/semana, geral no fim de
   semana. O cânone manda não inventar gente nova ("undefined details must
   remain undefined").
2. Mercado 1×/semana, depois que o pai manda o dinheiro da semana (segunda);
   o pai banca comida e contas (D1/D12), então o fim do mês NÃO aperta.
3. As contas do apê chegam por volta do dia 10 e ela manda pro pai.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta

LAUNDRY_DAYS_PER_WEEK = 2
LAUNDRY_FORGOT_CHANCE = 0.15
CLEANUP_SKIP_CHANCE = 0.2            # às vezes o fim de semana passa e a geral fica pra depois
GROCERY_FORGOT_CHANCE = 0.25
MISHAP_CHANCE = 0.05                 # por dia → 1–2 perrengues por mês
MISHAPS = (
    ("a lâmpada do banheiro queimou", "raiva"),
    ("o chuveiro ficou frio do nada e ela teve que chamar o porteiro", "raiva"),
    ("a internet do apê caiu por umas duas horas", "raiva"),
    ("o gás do fogão acabou bem na hora de cozinhar", "raiva"),
    ("achou a blusa que achava que tinha perdido, no fundo do armário", "alegria"),
    ("o síndico colou aviso de que a água vai ser cortada amanhã de manhã", "raiva"),
)
GROCERY_FORGOT = ("o leite", "o papel higiênico", "o sabão de roupa", "a ração do Milo", "o café")
BILLS = ("luz", "internet", "condomínio")


def _rng(day: date, name: str) -> random.Random:
    return random.Random(f"marina-casa:{day.isoformat()}:{name}")


def _week(day: date) -> date:
    return day - timedelta(days=day.weekday())


class Casa:
    def __init__(self, db):
        self.db = db

    # -------------------------------------------------------------- plano --
    def _laundry_days(self, day: date) -> set[int]:
        rng = _rng(_week(day), "roupa_dias")
        return set(rng.sample(range(7), LAUNDRY_DAYS_PER_WEEK))

    def _grocery_day(self, day: date) -> int:
        """Terça a quinta à noite, ou sábado (o pai manda o dinheiro na segunda)."""
        return _rng(_week(day), "mercado_dia").choice((1, 2, 3, 5))

    def _sick(self, day: date) -> bool:
        try:
            from health import Health
            sick = Health(self.db).illness(day)
            return bool(sick and sick[0] == "virose")
        except Exception:
            return False

    def day_plan(self, day: date) -> list[dict]:
        iso, plan = day.isoformat(), []
        weekend = day.weekday() >= 5
        if day.weekday() in self._laundry_days(day):
            rng = _rng(day, "roupa")
            start = datetime.combine(day, time(9, 30) if weekend else time(19, 0)) + timedelta(
                minutes=rng.randint(0, 150))
            plan.append({"key": f"casa:{iso}:roupa", "at": start,
                         "summary": "Botou uma máquina de roupa pra lavar."})
            if rng.random() < LAUNDRY_FORGOT_CHANCE:
                plan.append({"key": f"casa:{iso}:roupa_esquecida", "at": start + timedelta(hours=3),
                             "summary": "Esqueceu a roupa dentro da máquina e ficou com cheiro — "
                                        "vai ter que lavar tudo de novo."})
            else:
                plan.append({"key": f"casa:{iso}:varal", "at": start + timedelta(minutes=rng.randint(70, 100)),
                             "summary": "Tirou a roupa da máquina e estendeu no varal."})
        if day.weekday() == 5 + _rng(_week(day), "geral_dia").randint(0, 1):
            rng = _rng(day, "geral")
            if rng.random() >= CLEANUP_SKIP_CHANCE:
                at = datetime.combine(day, time(10, 30)) + timedelta(minutes=rng.randint(0, 120))
                what = rng.choice(("trocou a roupa de cama e passou aspirador",
                                   "arrumou o quarto e o closet, que tava um caos",
                                   "limpou o banheiro e a cozinha",
                                   "deu uma geral no apê ouvindo música"))
                plan.append({"key": f"casa:{iso}:geral", "at": at, "summary": f"Faxina de fim de semana: {what}."})
        if day.weekday() == self._grocery_day(day) and not self._sick(day):
            rng = _rng(day, "mercado")
            base = time(10, 0) if weekend else time(18, 30)
            at = datetime.combine(day, base) + timedelta(minutes=rng.randint(0, 120))
            minutes = rng.randint(45, 70)
            forgot = rng.choice(GROCERY_FORGOT) if rng.random() < GROCERY_FORGOT_CHANCE else ""
            plan.append({"key": f"casa:{iso}:mercado", "at": at, "minutes": minutes, "state": True,
                         "summary": "Foi no mercado fazer as compras da semana (com o dinheiro que o pai mandou)."})
            if forgot:
                plan.append({"key": f"casa:{iso}:mercado_esqueceu", "at": at + timedelta(minutes=minutes),
                             "summary": f"Voltou do mercado e percebeu que esqueceu justo {forgot}."})
        if day.day == 10 + _rng(day.replace(day=1), "contas").randint(-2, 2):
            at = datetime.combine(day, time(11, 0)) + timedelta(minutes=_rng(day, "contas_hora").randint(0, 300))
            plan.append({"key": f"casa:{iso}:contas", "at": at,
                         "summary": f"Chegaram as contas do apê ({', '.join(BILLS)}); mandou pro pai pagar."})
        rng = _rng(day, "perrengue")
        if rng.random() < MISHAP_CHANCE:
            text, _mood = rng.choice(MISHAPS)
            at = datetime.combine(day, time(8, 0)) + timedelta(minutes=rng.randint(0, 14 * 60))
            plan.append({"key": f"casa:{iso}:perrengue", "at": at, "summary": text[:1].upper() + text[1:] + "."})
        return sorted(plan, key=lambda p: p["at"])

    # ------------------------------------------------------------ mundo --
    def _market(self, now: datetime) -> str:
        try:
            from social_world import SocialWorld
            SocialWorld(self.db).discover_place("mercado_botafogo", "Supermercado perto de casa", "Botafogo",
                                                observed_at=now.isoformat())
            return "mercado_botafogo"
        except Exception:
            return "marina_apartment"

    def materialize(self, now: datetime) -> int:
        from meals import Meals
        meals = Meals(self.db)
        floor = meals._floor(now)
        if floor is None:
            return 0
        created = 0
        for day in (now.date() - timedelta(days=1), now.date()):
            for item in self.day_plan(day):
                if item["at"] > now or item["at"] < floor:
                    continue
                with self.db.get_connection() as conn:
                    cur = conn.execute(
                        """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,
                           source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                           VALUES (?,?,'routine','casa',?,'simulated',1,0.1,?,0.3,?)""",
                        (item["key"], item["at"].isoformat(), item["summary"], json.dumps(["marina"]),
                         now.isoformat()))
                    conn.commit()
                    fresh = bool(cur.rowcount)
                created += int(fresh)
                end = item["at"] + timedelta(minutes=item.get("minutes", 0))
                if fresh and item.get("state") and now < end and not meals._transition_busy(now):
                    payload = {"routine_type": "errand", "activity": "no mercado fazendo as compras da semana",
                               "place_key": self._market(now), "announced_at": now.isoformat(),
                               "transition_at": item["at"].isoformat(), "end_at": end.isoformat()}
                    self.db.set_estado_relacional("pending_transition_json", json.dumps(payload, ensure_ascii=False))
        return created
