"""Fase D1 — Fome viva: refeições, lanches, apetite, disfarce, dieta e peso.

Desenhado com o Patrick em 22–23/09 (PLANO_VOZ, Fase D1). Duas falhas reais
motivaram:
* soak de 22/09: ela prometeu jantar seis vezes e o mundo nunca teve jantar;
* arena `companhia_caminho`: sem refeição no mundo, o modelo **inventou**
  "arroz, feijão e franguinho".

Regra de ouro: o modelo só conta o que o mundo registrou. Este módulo registra.

* **Dia de comida** determinístico por data: café da manhã (corrido ou pulado
  em dia de aula, com calma em dia livre, brunch às vezes no fim de semana),
  almoço (na PUC ou no Shopping da Gávea entre aulas, em casa nos outros dias),
  jantar (casa: iFood ou cozinhando) e lanchinhos por vontade (tarde, série,
  TPM). Horários nunca fixos, sempre plausíveis.
* **Materialização**: refeição cujo horário chegou vira `life_event`
  (`meal`/`snack`); em casa, também vira estado ("jantando em casa") pelo mesmo
  `pending_transition_json` do banho — a disponibilidade trata como `MEAL`.
* **Promessa**: "vou jantar agora" antecipa a refeição do dia (não cria outra).
* **Apetite**: fome sobe com as horas desde a última comida; glutoninha de
  base; academia e TPM aceleram; energia baixa segura.
* **Disfarce**: em alguns dias, com fome, ela diz que já beliscou.
* **Peso**: 1,68 m, base 54 kg; muda devagar pelo saldo da semana (lanches ×
  academia). Ela só sabe quando se pesa (na academia, 1×/semana). Acima de
  56 kg a Lívia cobra e vem a dieta curta; abaixo de 52 kg é a saúde que reage.
"""
from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from db import DatabaseManager
from world_repository import WorldStateRepository

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ promessa --
# Só anúncio imediato: "vou jantar agora", "vou comer rapidinho". Promessa
# condicional ("vou comer assim que você chegar") ou futura não conta.
MEAL_PROMISE_RE = re.compile(
    r"\bvou\s+(?:l[aá]\s+)?(?:(?:comer|jantar|almo[çc]ar|lanchar)"
    r"|fazer\s+(?:meu|o)\s+(?:jantar|almo[çc]o|lanche)"
    r"|esquentar\s+(?:minha|a|meu|o)\s+(?:comida|janta|jantar|almo[çc]o))\b"
    r"[^.!?\n]{0,40}?\b(?:agora|agorinha|j[aá]\s+j[aá]|rapidinho)\b",
    re.IGNORECASE,
)

START_DELAY_MIN = (2, 5)
DURATION_MIN = {"cafe": (10, 25), "almoco": (25, 45), "jantar": (20, 35), "lanche": (5, 15)}
# Uma refeição por janela: repetir "vou jantar agora" não abre outro jantar.
SAME_MEAL_WINDOW = timedelta(hours=3)

KIND_NAME = {"cafe": ("café da manhã", "tomando café da manhã"),
             "almoco": ("almoço", "almoçando"),
             "jantar": ("jantar", "jantando"),
             "lanche": ("lanche", "lanchando")}

# Cardápio: o cânone (japonesa, massas, pizza, hambúrguer, brunch, doces, açaí)
# com o pé no chão de quem mora sozinha e cozinha o básico. Time iFood — o pai
# banca a comida, então o fim do mês não corta o delivery.
MENU = {
    "cafe_corrido": ["pão na chapa com café, correndo", "um café preto e uma banana no caminho",
                     "iogurte tomado em pé na cozinha"],
    "cafe_calma": ["tapioca de queijo com café", "ovos mexidos com torrada e café",
                   "pão de queijo com café com leite", "cuscuz com ovo"],
    "brunch": ["brunch com panqueca e café gelado", "tosta de avocado com ovo e suco"],
    "almoco_puc": ["prato feito no restaurante do campus", "salada com frango no restaurante do campus"],
    "almoco_gavea": ["um poke no Shopping da Gávea", "um sanduíche no Shopping da Gávea",
                     "comida japonesa no Shopping da Gávea"],
    "almoco_casa": ["arroz, feijão, frango grelhado e salada que ela mesma fez",
                    "macarrão ao sugo que ela mesma fez", "um poke pedido no iFood",
                    "sobra do jantar de ontem esquentada", "hambúrguer pedido no iFood"],
    "jantar_ifood": ["yakisoba pedido no iFood", "pizza de marguerita pedida no iFood",
                     "hambúrguer pedido no iFood", "temaki pedido no iFood", "açaí com granola no iFood"],
    "jantar_cozinha": ["omelete com queijo e tomate", "macarrão ao pesto que ela mesma fez",
                       "arroz, ovo frito e salada", "tapioca de queijo com presunto"],
    "lanche": ["pão de queijo", "um chocolate", "iogurte com granola", "um açaí pequeno",
               "biscoito com café", "pipoca vendo série"],
    "dieta": ["salada com frango grelhado", "omelete de claras com salada", "sopa de legumes"],
}


@dataclass(frozen=True)
class MealSlot:
    kind: str             # cafe | almoco | jantar | lanche
    key: str              # meal:<data>:<tipo>[:n]
    at: datetime
    minutes: int
    where: str            # casa | puc | gavea
    dish: str
    skipped: bool = False

    @property
    def end(self) -> datetime:
        return self.at + timedelta(minutes=self.minutes)


def meal_kind(now: datetime) -> str:
    if 5 <= now.hour < 11:
        return "cafe"
    if 11 <= now.hour < 15:
        return "almoco"
    if now.hour >= 18 or now.hour < 2:
        return "jantar"
    return "lanche"


def announces_meal(text: str) -> bool:
    return bool(MEAL_PROMISE_RE.search(text or ""))


def _rng(day: date, name: str) -> random.Random:
    return random.Random(f"marina-meal:{day.isoformat()}:{name}")


def _at(day: date, lo: time, hi: time, rng: random.Random) -> datetime:
    start = datetime.combine(day, lo)
    span = int((datetime.combine(day, hi) - start).total_seconds() // 60)
    return start + timedelta(minutes=rng.randint(0, max(0, span)))


class Meals:
    WEIGHT_KEY = "marina_peso_json"
    BASE_KG = 54.0
    AGENCY_MAX_KG = 56.0
    HEALTH_MIN_KG = 52.0
    DIET_DAYS = 5

    def __init__(self, db: DatabaseManager):
        self.db = db

    # ------------------------------------------------------------- agenda --
    def _blocks(self, day: date) -> list[tuple[datetime, datetime]]:
        try:
            from academic_life import AcademicLife
            blocks = AcademicLife(self.db).blocks_on(day)
        except Exception:
            return []
        out = []
        for b in blocks:
            try:
                out.append((datetime.fromisoformat(b["start_at"]), datetime.fromisoformat(b["end_at"])))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(out)

    def _wake(self, day: date) -> datetime:
        try:
            from rituals import Rituals
            wake = Rituals(self.db).wake_at(day)
        except Exception:
            wake = None
        return wake or datetime.combine(day, time(8, 0))

    def _phase(self) -> str:
        try:
            from cycle import MenstrualCycleManager
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT data_inicio_ciclo FROM ciclo_biologico ORDER BY id DESC LIMIT 1").fetchone()
            return MenstrualCycleManager(row["data_inicio_ciclo"] if row else None).get_cycle_info()["phase_key"]
        except Exception:
            return ""

    def weight(self) -> dict:
        raw = self.db.get_estado_relacional().get(self.WEIGHT_KEY)
        try:
            data = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            data = {}
        data.setdefault("kg", self.BASE_KG)
        return data

    def _save_weight(self, data: dict) -> None:
        self.db.set_estado_relacional(self.WEIGHT_KEY, json.dumps(data, ensure_ascii=False))

    def on_diet(self, day: date) -> bool:
        until = self.weight().get("diet_until")
        return bool(until) and day <= date.fromisoformat(until)

    def day_plan(self, day: date) -> list[MealSlot]:
        """O dia de comida dela, determinístico por data."""
        blocks = self._blocks(day)
        wake = self._wake(day)
        weekend = day.weekday() >= 5
        diet = self.on_diet(day)
        tpm = self._phase() == "tpm"
        iso = day.isoformat()
        slots: list[MealSlot] = []

        def dur(kind, rng):
            return rng.randint(*DURATION_MIN[kind])

        # Café da manhã — em dia de aula é corrido e às vezes some.
        rng = _rng(day, "cafe")
        if blocks:
            first = blocks[0][0]
            at = wake + timedelta(minutes=rng.randint(15, 40))
            skipped = rng.random() < 0.25 or at + timedelta(minutes=45) > first
            slots.append(MealSlot("cafe", f"meal:{iso}:cafe", at, dur("cafe", rng), "casa",
                                  rng.choice(MENU["cafe_corrido"]), skipped=skipped))
        elif weekend and rng.random() < 0.35:
            at = max(wake + timedelta(minutes=60), datetime.combine(day, time(10, 30)))
            slots.append(MealSlot("cafe", f"meal:{iso}:cafe", at, 50, "casa", rng.choice(MENU["brunch"])))
        else:
            at = wake + timedelta(minutes=rng.randint(30, 90))
            slots.append(MealSlot("cafe", f"meal:{iso}:cafe", at, dur("cafe", rng), "casa",
                                  rng.choice(MENU["cafe_calma"])))

        # Almoço — entre aulas (campus ou Gávea) ou em casa.
        rng = _rng(day, "almoco")
        noon_lo, noon_hi = datetime.combine(day, time(11, 30)), datetime.combine(day, time(14, 30))
        lunch = None
        if blocks:
            gaps = [(a[1], b[0]) for a, b in zip(blocks, blocks[1:])
                    if (b[0] - a[1]) >= timedelta(minutes=40) and noon_lo <= a[1] <= noon_hi]
            if gaps:
                start, end = gaps[0]
                rushed = end - start < timedelta(minutes=75)
                where = "puc" if rushed or rng.random() < 0.5 else "gavea"
                lunch = MealSlot("almoco", f"meal:{iso}:almoco", start + timedelta(minutes=rng.randint(5, 15)),
                                 min(dur("almoco", rng), int((end - start).total_seconds() // 60) - 10),
                                 where, rng.choice(MENU["almoco_puc" if where == "puc" else "almoco_gavea"]))
            elif blocks[-1][1] <= datetime.combine(day, time(15, 0)) and blocks[-1][1] >= noon_lo:
                where = "puc" if rng.random() < 0.5 else "gavea"
                lunch = MealSlot("almoco", f"meal:{iso}:almoco", blocks[-1][1] + timedelta(minutes=rng.randint(10, 30)),
                                 dur("almoco", rng), where,
                                 rng.choice(MENU["almoco_puc" if where == "puc" else "almoco_gavea"]))
        if lunch is None:
            lunch = MealSlot("almoco", f"meal:{iso}:almoco", _at(day, time(12, 0), time(14, 0), rng),
                             dur("almoco", rng), "casa", rng.choice(MENU["almoco_casa"]))
        if diet and lunch.where == "casa":
            lunch = MealSlot(lunch.kind, lunch.key, lunch.at, lunch.minutes, lunch.where, rng.choice(MENU["dieta"]))
        slots.append(lunch)

        # Lanche da tarde — vontade, TPM e dieta mexem.
        rng = _rng(day, "lanche_tarde")
        chance = 0.10 if diet else (0.40 + (0.25 if tpm else 0.0))
        if rng.random() < chance:
            slots.append(MealSlot("lanche", f"meal:{iso}:lanche:1", _at(day, time(15, 30), time(17, 30), rng),
                                  dur("lanche", rng), "casa",
                                  "um chocolate" if tpm else rng.choice(MENU["lanche"])))

        # Jantar — casa; iFood ou cozinha.
        rng = _rng(day, "jantar")
        at = _at(day, time(19, 0), time(22, 0), rng)
        if diet:
            dish = rng.choice(MENU["dieta"])
        else:
            dish = rng.choice(MENU["jantar_ifood"] if rng.random() < 0.55 else MENU["jantar_cozinha"])
        slots.append(MealSlot("jantar", f"meal:{iso}:jantar", at, dur("jantar", rng), "casa", dish))

        # Lanchinho da noite (série) — depois do jantar.
        rng = _rng(day, "lanche_noite")
        chance = 0.05 if diet else (0.25 + (0.25 if tpm else 0.0))
        if rng.random() < chance:
            night = at + timedelta(minutes=rng.randint(80, 150))
            slots.append(MealSlot("lanche", f"meal:{iso}:lanche:2", night, dur("lanche", rng), "casa",
                                  rng.choice(["pipoca vendo série", "um chocolate", "um açaí pequeno"])))
        return sorted(slots, key=lambda s: s.at)

    # ----------------------------------------------------------- registros --
    def eaten_today(self, now: datetime) -> list[dict]:
        start = datetime.combine(now.date(), time(0, 0)).isoformat()
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT event_key, event_at, event_type, title, summary FROM life_events
                   WHERE event_type IN ('meal','snack') AND event_at>=? AND event_at<=? ORDER BY event_at""",
                (start, now.isoformat())).fetchall()
        return [dict(r) for r in rows]

    def _logged(self, day: date, kind: str) -> bool:
        with self.db.get_connection() as conn:
            return bool(conn.execute(
                "SELECT 1 FROM life_events WHERE event_type IN ('meal','snack') AND event_key LIKE ? LIMIT 1",
                (f"meal:{day.isoformat()}:{kind}%",)).fetchone())

    def _record(self, slot: MealSlot, now: datetime) -> bool:
        name, _ = KIND_NAME[slot.kind]
        where = {"casa": "em casa", "puc": "no restaurante da PUC", "gavea": "no Shopping da Gávea"}[slot.where]
        if slot.skipped:
            summary = f"Pulou o {name}: acordou em cima da hora pra aula."
        elif slot.kind == "lanche":
            summary = f"Beliscou {slot.dish}."
        else:
            summary = f"{name.capitalize()} {where}: {slot.dish}."
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,
                   source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,?,?,?,'simulated',1,0.1,?,0.3,?)""",
                (slot.key, slot.at.isoformat(), "snack" if slot.kind == "lanche" else "meal",
                 name, summary, json.dumps(["marina"]), now.isoformat()))
            conn.commit()
            return bool(cur.rowcount)

    def _transition_busy(self, now: datetime) -> bool:
        raw = self.db.get_estado_relacional().get("pending_transition_json")
        if not raw:
            return False
        try:
            return datetime.fromisoformat(json.loads(raw)["end_at"]) > now
        except (TypeError, ValueError, KeyError):
            return False

    def _at_home(self) -> bool:
        state = WorldStateRepository(self.db).latest()
        if not state:
            return True
        activity = (state.get("activity") or "").casefold()
        region = (state.get("location_region") or "").casefold()
        away = ("dorm", "a caminho", "uber", "ônibus", "metrô", "carona", "academia", "trein",
                "faculdade", "aula", "com amig", "bar", "praia", "saindo com")
        return not any(t in activity for t in away) and "a caminho" not in region

    def _start_eating(self, slot: MealSlot, start: datetime, end: datetime, now: datetime) -> None:
        _, gerund = KIND_NAME[slot.kind]
        payload = {"routine_type": "meal", "activity": f"{gerund} em casa", "place_key": "marina_apartment",
                   "announced_at": now.isoformat(), "transition_at": start.isoformat(),
                   "end_at": end.isoformat(), "dish": slot.dish}
        self.db.set_estado_relacional("pending_transition_json", json.dumps(payload, ensure_ascii=False))

    def _floor(self, now: datetime) -> Optional[datetime]:
        with self.db.get_connection() as conn:
            clean = conn.execute(
                "SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone()
        if not clean:
            return None
        try:
            from social_day import SocialDay
            return SocialDay(self.db)._floor(now)
        except Exception:
            return None

    def materialize(self, now: datetime) -> int:
        """Refeições cujo horário chegou viram acontecimento (idempotente).

        Mesmas travas do dia social e do trajeto: nada antes do bootstrap limpo
        e nada antes do início da vida registrada."""
        floor = self._floor(now)
        if floor is None:
            return 0
        created = 0
        self._weekly_weight(now)
        for slot in self.day_plan(now.date()):
            if slot.at > now or slot.at < floor:
                continue
            base_kind = slot.key.split(":")[2]
            if base_kind != "lanche" and self._logged(now.date(), base_kind):
                continue      # já comeu (promessa antecipou)
            if slot.where == "casa" and not slot.skipped and not self._at_home() and now < slot.end:
                continue      # fora de casa na hora: espera ela voltar (a janela ainda está aberta)
            if self._record(slot, now):
                created += 1
                if (slot.where == "casa" and not slot.skipped and now < slot.end
                        and not self._transition_busy(now)):
                    self._start_eating(slot, slot.at, slot.end, now)
        self._weigh_in(now)
        return created

    # ----------------------------------------------------------- promessa --
    def observe_marina_line(self, text: str, now: datetime) -> Optional[dict]:
        """Chamado depois que a fala dela é entregue. Retorna o payload se abriu refeição."""
        if not announces_meal(text):
            return None
        kind = meal_kind(now)
        if self._recent_meal(now) or self._transition_busy(now) or not self._at_home():
            return None
        if kind != "lanche" and self._logged(now.date(), kind):
            return None
        rng = random.Random(f"meal-promise:{now.isoformat(timespec='minutes')}")
        start = now + timedelta(minutes=rng.randint(*START_DELAY_MIN))
        planned = {s.kind: s for s in self.day_plan(now.date())}
        dish = planned[kind].dish if kind in planned else rng.choice(MENU["lanche"])
        slot = MealSlot(kind, f"meal:{now.date().isoformat()}:{kind}" + (":p" if kind == "lanche" else ""),
                        start, rng.randint(*DURATION_MIN[kind]), "casa", dish)
        self._record(slot, now)
        self._start_eating(slot, start, slot.end, now)
        logger.info("meal.promised kind=%s start=%s", kind, start.isoformat(timespec="minutes"))
        return json.loads(self.db.get_estado_relacional()["pending_transition_json"])

    def _recent_meal(self, now: datetime) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT event_at FROM life_events WHERE event_type='meal'
                   AND event_at>=? AND event_at<=? ORDER BY event_at DESC LIMIT 1""",
                ((now - SAME_MEAL_WINDOW).isoformat(), (now + timedelta(minutes=10)).isoformat())).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------ apetite --
    def _gym_today(self, now: datetime) -> bool:
        start = datetime.combine(now.date(), time(0, 0)).isoformat()
        with self.db.get_connection() as conn:
            return bool(conn.execute(
                "SELECT 1 FROM world_state WHERE observed_at>=? AND observed_at<=? AND "
                "(activity LIKE '%academia%' OR activity LIKE '%trein%') LIMIT 1",
                (start, now.isoformat())).fetchone())

    def hunger(self, now: datetime) -> float:
        eaten = [e for e in self.eaten_today(now) if "Pulou" not in (e["summary"] or "")]
        if eaten:
            last = datetime.fromisoformat(eaten[-1]["event_at"])
            base = 0.30 if eaten[-1]["event_type"] == "snack" else 0.05
        else:
            last = self._wake(now.date())
            base = 0.30                     # acorda com fome
        hours = max(0.0, (now - last).total_seconds() / 3600)
        rate = 0.15                         # glutoninha de base
        if self._gym_today(now):
            rate *= 1.3
        phase = self._phase()
        if phase == "tpm":
            rate *= 1.25
        elif phase == "menstrual":
            rate *= 0.85
        if self.on_diet(now.date()):
            rate *= 1.2
        try:
            from health import Health
            rate *= Health(self.db).appetite(now)   # D11: virose tira a fome, resfriado diminui
        except Exception:
            pass
        try:
            # Fase D14d: glutoninha ansiosa belisca mais.
            from emotion import EmotionEngine
            if any(e.family == "medo" and e.intensity >= 0.3 for e in EmotionEngine(self.db).episodes(now)):
                rate *= 1.15
        except Exception:
            pass
        try:
            from world_state import current_energy
            if current_energy(self.db, now) < 0.35:
                rate *= 0.85
        except Exception:
            pass
        return max(0.0, min(1.0, base + rate * hours))

    def disguises_today(self, day: date) -> bool:
        """Dias em que, com fome, ela diz que já beliscou (drama e mentirinha)."""
        return _rng(day, "disfarce").random() < (0.35 if self.on_diet(day) else 0.2)

    # --------------------------------------------------------------- peso --
    def _weekly_weight(self, now: datetime) -> None:
        data = self.weight()
        week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
        if data.get("week") == week:
            return
        if data.get("week"):
            since = (now - timedelta(days=7)).isoformat()
            with self.db.get_connection() as conn:
                snacks = conn.execute("SELECT COUNT(*) FROM life_events WHERE event_type='snack' AND event_at>=?",
                                      (since,)).fetchone()[0]
                gym = conn.execute(
                    "SELECT COUNT(DISTINCT substr(observed_at,1,10)) FROM world_state WHERE observed_at>=? AND "
                    "(activity LIKE '%academia%' OR activity LIKE '%trein%')", (since,)).fetchone()[0]
            rng = random.Random(f"marina-peso:{week}")
            delta = 0.12 * (snacks - 3) - 0.12 * (gym - 3) + rng.uniform(-0.2, 0.2)
            if self.on_diet(now.date()):
                delta -= 0.3
            data["kg"] = round(max(49.0, min(60.0, data["kg"] + max(-0.6, min(0.6, delta)))), 1)
        data["week"] = week
        self._save_weight(data)

    def _weigh_in(self, now: datetime) -> None:
        """Se pesa na academia, uma vez por semana: só aí ela sabe o peso."""
        data = self.weight()
        week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
        if data.get("weighed_week") == week or not self._gym_today(now) or self._at_gym_now():
            return
        kg = data["kg"]
        data.update(weighed_week=week, known_kg=kg, known_at=now.isoformat())
        texto = f"Se pesou na academia: {kg:.1f} kg.".replace(".", ",", 1)
        extra = []
        if kg > self.AGENCY_MAX_KG:
            until = now.date() + timedelta(days=self.DIET_DAYS)
            data["diet_until"] = until.isoformat()
            extra.append(("agencia", "A Lívia viu o peso e cobrou: acima do que a agência aceita pros castings. "
                                     f"Dieta até {until:%d/%m}."))
        elif kg < self.HEALTH_MIN_KG:
            extra.append(("saude", "Anda meio fraca e sentiu tontura no treino — está comendo menos do que devia."))
        self._save_weight(data)
        rows = [("peso", texto)] + extra
        with self.db.get_connection() as conn:
            for tag, summary in rows:
                conn.execute(
                    """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,
                       source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                       VALUES (?,?,?,?,?,'simulated',1,?,?,0.5,?)""",
                    (f"peso:{week}:{tag}", now.isoformat(), "routine", tag, summary,
                     0.4 if tag != "peso" else 0.2,
                     json.dumps(["marina", "livia_vasconcelos"] if tag == "agencia" else ["marina"]),
                     now.isoformat()))
            conn.commit()

    def _at_gym_now(self) -> bool:
        state = WorldStateRepository(self.db).latest()
        activity = ((state or {}).get("activity") or "").casefold()
        return "academia" in activity or "trein" in activity

    # ------------------------------------------------------------- prompt --
    def prompt_lines(self, now: datetime) -> list[str]:
        """Bloco de comida do dia: o que ela comeu de verdade, a fome e o peso que conhece."""
        eaten = self.eaten_today(now)
        lines = ["[SUA COMIDA HOJE — aconteceu de verdade; não invente refeição fora desta lista]"]
        for e in eaten:
            lines.append(f"- {datetime.fromisoformat(e['event_at']):%H:%M} — {e['summary']}")
        done = {e["event_key"].split(":")[2] for e in eaten}
        faltam = []
        if now.hour >= 11 and "cafe" not in done:
            faltam.append("não tomou café da manhã")
        if now.hour >= 15 and "almoco" not in done:
            faltam.append("ainda não almoçou")
        if now.hour >= 19 and "jantar" not in done:
            faltam.append("ainda não jantou")
        if faltam:
            lines.append(f"- Hoje você {', '.join(faltam)}.")
        # 24/09: a resposta pronta pro "já comeu?/já papou?" — pelos fatos, não pelo chute do modelo.
        refeicoes = [e for e in eaten if "Pulou" not in (e["summary"] or "")]
        if refeicoes:
            ultima = refeicoes[-1]
            lines.append(f"- Se o Patrick perguntar se você comeu/almoçou/jantou/papou: SIM — a última foi às "
                         f"{datetime.fromisoformat(ultima['event_at']):%H:%M} ({ultima['summary'].rstrip('.')}).")
        else:
            lines.append("- Se o Patrick perguntar se você comeu/papou: hoje ainda não comeu nada.")
        h = self.hunger(now)
        if h >= 0.8:
            fome = ("morrendo de fome — com fome assim você fica mais curtinha e impaciente, "
                    "e quando come volta ao normal (\"desculpa, eu tava com fome kkk\")")
        elif h >= 0.6:
            fome = "com fome"
        elif h >= 0.35:
            fome = "com um pouco de fome"
        else:
            fome = "sem fome"
        lines.append(f"- Fome agora: {fome}. Você é glutoninha: ama comer.")
        if h >= 0.6 and self.disguises_today(now.date()):
            lines.append("- Hoje você está no modo disfarce: se o Patrick perguntar se comeu, "
                         "diz que já beliscou alguma coisa (mesmo com fome).")
        w = self.weight()
        if self.on_diet(now.date()):
            lines.append(f"- Você está de dieta até {date.fromisoformat(w['diet_until']):%d/%m} "
                         "(a Lívia cobrou o peso): mais fome, sonhando com besteira, reclamando da salada.")
        if w.get("known_kg"):
            quando = datetime.fromisoformat(w["known_at"])
            lines.append(f"- Seu último peso: {w['known_kg']:.1f} kg (pesou em {quando:%d/%m}).".replace(".", ",", 1))
        return lines
