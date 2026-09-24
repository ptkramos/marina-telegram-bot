"""Fase D9 — casa e vida adulta: roupa, faxina, mercado, contas e perrengues do apê.

Antes (24/09): a casa dela não existia como rotina. Ela nunca lavava roupa,
nunca ia ao mercado, nunca arrumava nada, e lâmpada nenhuma queimava.

Mesmo molde do `milo.py`: o plano de cada dia sai da data (determinístico) e
o que já aconteceu vira acontecimento do dia (`life_events`, chave
`casa:<dia>:<o quê>`), que o motor emocional lê (emotion.appraise_event).
O mercado vira estado ("no mercado") por uns 45–70 min.

Decisões do Patrick (24/09, revisão da tarde):
1. O Henrique paga uma faxineira, a **Dona Neide** (canônica, `canon_extras.py`):
   ela vai TODA QUINTA, mesmo com a Marina fora de casa. O porteiro, **Seu
   Jorge** (canônico), libera a entrada dela, recebe as encomendas e rende
   história. A Marina cuida da bagunça DELA (quarto, closet, louça, roupa); a
   faxineira cuida do geral.
2. O Henrique paga o que é do apartamento (aluguel, condomínio, luz, internet,
   gás) e a mesada da comida; o resto é a Marina quem paga (celular,
   streamings, unha, roupa, rolês…), com o dinheiro dos jobs.
3. Prédio de padrão médio/alto: nada de perrengue de gás (é encanado) nem de
   água; problema do prédio é raro.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta

LAUNDRY_DAYS_PER_WEEK = 2
LAUNDRY_FORGOT_CHANCE = 0.15
CLEANUP_SKIP_CHANCE = 0.2            # às vezes o fim de semana passa e a geral fica pra depois
GROCERY_FORGOT_CHANCE = 0.25
MISHAP_CHANCE = 0.05                 # por dia → 1–2 coisinhas do apê/prédio por mês
# Sem gás nem água (gás encanado, prédio médio/alto — Patrick, 24/09).
MISHAPS = (
    ("a lâmpada do banheiro queimou", "raiva"),
    ("a internet do apê caiu por umas duas horas", "raiva"),
    ("achou a blusa que achava que tinha perdido, no fundo do armário", "alegria"),
    ("o Seu Jorge, o porteiro, segurou uma encomenda dela que chegou enquanto ela tava fora", "alegria"),
    ("o Seu Jorge contou uma fofoca do prédio quando ela passou pela portaria", "alegria"),
    ("o elevador social ficou parado a tarde toda e ela teve que ir pelo de serviço", "raiva"),
)
FAXINEIRA = "neide_souza"
PORTEIRO = "jorge_almeida"
CLEANING_WEEKDAY = 3                 # quinta
HER_OWN_CHORES = ("arrumou o quarto e o closet, que tava um caos",
                  "lavou a louça que tava acumulada na pia",
                  "trocou a roupa de cama",
                  "deu um jeito na bagunça dela ouvindo música")
GROCERY_FORGOT = ("o leite", "o papel higiênico", "o sabão de roupa", "a ração do Milo", "o café")
BILLS = ("aluguel", "condomínio", "luz", "internet", "gás")   # tudo do apê é o Henrique


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
        if day.weekday() == CLEANING_WEEKDAY:
            rng = _rng(day, "faxineira")
            chega = datetime.combine(day, time(8, 0)) + timedelta(minutes=rng.randint(0, 50))
            plan.append({"key": f"casa:{iso}:faxina_chegou", "at": chega, "people": [FAXINEIRA, PORTEIRO],
                         "summary": "A Dona Neide chegou pra faxina de quinta (o Seu Jorge liberou a entrada)."})
            plan.append({"key": f"casa:{iso}:geral", "at": chega + timedelta(minutes=rng.randint(300, 360)),
                         "people": [FAXINEIRA],
                         "summary": "A Dona Neide terminou a faxina: o apê ficou um brinco."})
        if day.weekday() == 5 + _rng(_week(day), "bagunca_dia").randint(0, 1):
            rng = _rng(day, "bagunca")
            if rng.random() >= CLEANUP_SKIP_CHANCE:
                at = datetime.combine(day, time(10, 30)) + timedelta(minutes=rng.randint(0, 120))
                plan.append({"key": f"casa:{iso}:bagunca", "at": at,
                             "summary": f"Cuidou da bagunça dela: {rng.choice(HER_OWN_CHORES)}."})
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
        if day.day == 5 + _rng(day.replace(day=1), "contas_dela").randint(0, 3):
            at = datetime.combine(day, time(12, 0)) + timedelta(minutes=_rng(day, "contas_dela_h").randint(0, 480))
            plan.append({"key": f"casa:{iso}:contas_dela", "at": at,
                         "summary": "Pagou as contas dela (celular e os streamings) com o dinheiro dos jobs."})
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
                        (item["key"], item["at"].isoformat(), item["summary"],
                         json.dumps(["marina", *item.get("people", [])]),
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
