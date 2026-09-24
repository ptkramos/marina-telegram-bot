"""Fase D11 — corpo e saúde: cólica com intensidade, dor de cabeça, resfriado, virose.

Antes (24/09): o ciclo dava "cólica" fixa nos dias 1–2 e mais nada. Ela nunca
ficava gripada, nunca tinha dor de cabeça, nunca tomava um remédio.

Tudo aqui é FATO DO MUNDO calculado a partir da data (mesmo estilo do
`sleep_plan`): o mesmo dia sempre dá o mesmo resfriado, a mesma cólica, o
mesmo remédio na mesma hora. Nada chama LLM ou rede, nada grava tabela.

Quem usa:
- `emotion` — desconforto (valência, tesão) e energia do corpo;
- `meals` — apetite (virose tira a fome, resfriado diminui);
- `sleep_plan._onset` — doente dorme mais cedo;
- `college.skip_reason` — cólica forte / virose / resfriado forte = falta;
- `emotion.prompt_lines` — como ela está e como ela lida (ver abaixo).

Decisões PROVISÓRIAS (Patrick dormindo em 24/09 pediu pra eu decidir e
catalogar pra ele revisar — PLANO_VOZ, seção D11):
1. Frequência: resfriado ~3–5 por ano (3–5 dias; mais com sono ruim, chuva, estresse); virose 2–3×/ano
   (1–2 dias); dor de cabeça ~2×/mês, bem mais depois de noite mal dormida;
   cólica todo ciclo, com intensidade sorteada por ciclo (leve/moderada/forte).
2. Jeito: independente — coisa pequena ela minimiza ("é só uma dorzinha");
   quando é forte de verdade fica manhosa com o Patrick e aceita dengo.
3. Remédio: se automedica no leve (dipirona, Buscopan, Benegrip, chá);
   não vai ao médico por nada disso. O pai se preocupa e manda ir.
4. Condição fixa: nenhuma além da cólica (que já é "dela").
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

# ------------------------------------------------------------ calibragem --
COLD_START_CHANCE = 0.008         # por dia → ~3 por ano de base; 4–5 com a imunidade baixa
COLD_DAYS = (3, 5)
# Imunidade (dica do Patrick, 24/09: "imunidade, chuva, e etc"): o risco de
# pegar resfriado num dia sobe com o corpo e o mundo daquele dia.
COLD_RISK_BAD_SLEEP = 1.8         # dormiu menos de 6h → imunidade baixa
COLD_RISK_RAIN = 2.0              # pegou chuva / tempo frio e úmido
COLD_RISK_STRESS = 1.3            # semana de entrega na faculdade
COLD_RISK_MAX = COLD_RISK_BAD_SLEEP * COLD_RISK_RAIN * COLD_RISK_STRESS
VIRUS_START_CHANCE = 0.007        # por dia → ~2,5 viroses por ano
VIRUS_DAYS = (1, 2)
HEADACHE_CHANCE = 0.06            # por dia → ~2 por mês
HEADACHE_CHANCE_BAD_SLEEP = 0.30  # dormiu menos de 5h30
HEADACHE_RESIST_CHANCE = 0.2      # às vezes não toma nada e aguenta
CRAMP_LEVELS = ((0.55, 1), (0.85, 2), (1.01, 3))   # leve 55% · moderada 30% · forte 15%
CRAMP_WORD = {1: "leve", 2: "moderada", 3: "forte"}
CRAMP_DISCOMFORT = {1: 0.3, 2: 0.5, 3: 0.8}
SKIP_CHANCE = {"colica3": 0.85, "colica2": 0.2, "virose": 0.95, "resfriado_forte": 0.5}
LOOKBACK_DAYS = 6


def _rng(key: str) -> random.Random:
    return random.Random(f"marina-saude:{key}")


# O motor pergunta da saúde várias vezes por turno (energia, desconforto, fome,
# prompt). Os fatos de um dia não mudam de um segundo pro outro: cache curto.
CACHE_SECONDS = 30.0
_cache: dict = {}
try:
    from db import _running_under_tests
    _UNDER_TESTS = _running_under_tests()
except Exception:
    _UNDER_TESTS = False
_cache_in_tests = False


def clear_cache() -> None:
    _cache.clear()


def _memo(db, name: str, day: date, fn):
    import time as _time
    if _UNDER_TESTS and not _cache_in_tests:
        return fn()   # na suíte os bancos mudam a cada teste: sem cache
    key = (str(getattr(db, "db_path", id(db))), name, day)
    hit = _cache.get(key)
    now = _time.monotonic()
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = fn()
    if len(_cache) > 512:
        _cache.clear()
    _cache[key] = (now, value)
    return value


@dataclass
class Condition:
    kind: str               # colica | dor_de_cabeca | resfriado | virose
    label: str              # como ela chamaria
    discomfort: float       # 0–1
    energy_penalty: float   # quanto tira da energia
    appetite: float         # multiplica a fome
    remedy: str             # o que ela fez / tomou (fato)
    strong: bool            # forte de verdade → manhosa, pode faltar
    started: datetime


class Health:
    def __init__(self, db):
        self.db = db

    # ----------------------------------------------------------- ciclo --
    def _cycle_start(self) -> Optional[date]:
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT data_inicio_ciclo FROM ciclo_biologico ORDER BY id DESC LIMIT 1").fetchone()
            return date.fromisoformat(row["data_inicio_ciclo"][:10]) if row else None
        except Exception:
            return None

    def cramps(self, day: date) -> int:
        return _memo(self.db, "cramps", day, lambda: self._cramps(day))

    def _cramps(self, day: date) -> int:
        """Intensidade da cólica nesse dia: 0 nada · 1 leve · 2 moderada · 3 forte.

        A intensidade é sorteada uma vez por ciclo (tem mês que dói mais).
        Dia 1 é o pior; dia 2 um degrau abaixo; forte ainda incomoda no dia 3."""
        start = self._cycle_start()
        if not start:
            return 0
        from cycle import CYCLE_LENGTH
        offset = (day - start).days % CYCLE_LENGTH
        cycle_start = day - timedelta(days=offset)
        roll = _rng(f"colica:{cycle_start.isoformat()}").random()
        level = next(lv for limit, lv in CRAMP_LEVELS if roll < limit)
        return max(0, level - offset) if offset <= 2 else 0

    # -------------------------------------------------------- doenças --
    def illness(self, day: date) -> Optional[tuple[str, int, int, int]]:
        return _memo(self.db, "illness", day, lambda: self._illness(day))

    def _illness(self, day: date) -> Optional[tuple[str, int, int, int]]:
        """(tipo, dia da doença começando em 1, duração, gravidade 1–2) ou None.
        Uma doença por vez; a mais antiga ainda em curso vale."""
        for back in range(LOOKBACK_DAYS, -1, -1):
            start = day - timedelta(days=back)
            rng = _rng(f"doenca:{start.isoformat()}")
            roll = rng.random()
            if roll < VIRUS_START_CHANCE:
                kind, length = "virose", rng.randint(*VIRUS_DAYS)
            elif (roll < VIRUS_START_CHANCE + COLD_START_CHANCE * COLD_RISK_MAX   # só consulta o mundo se der
                  and roll < VIRUS_START_CHANCE + COLD_START_CHANCE * self.cold_risk(start)[0]):
                kind, length = "resfriado", rng.randint(*COLD_DAYS)
            else:
                continue
            if back < length:
                return kind, back + 1, length, 2 if rng.random() < 0.35 else 1
        return None

    def cold_risk(self, day: date) -> tuple[float, list[str]]:
        """Quanto a imunidade daquele dia multiplica a chance de resfriado, e por quê.
        Usa o sono aproximado (sem os fatores do corpo) pra não criar ciclo com o
        `sleep_plan`, que por sua vez pergunta aqui se ela está doente."""
        risk, why = 1.0, []
        if self._approx_slept(day) < 6.0:
            risk *= COLD_RISK_BAD_SLEEP
            why.append("dormindo pouco")
        try:
            from calendar_world import CalendarWorld
            observed = CalendarWorld(self.db).context.get("weather:rio", now=datetime.combine(day, time(12, 0)))
            payload = (observed or {}).get("payload") or {}
            wet = str(payload.get("condition") or "").lower()
            if payload.get("heavy_rain") or "rain" in wet or "chuv" in wet:
                risk *= COLD_RISK_RAIN
                why.append("pegou chuva")
        except Exception:
            pass
        try:
            from college import College
            if College(self.db).assignments(day, horizon_days=2):
                risk *= COLD_RISK_STRESS
                why.append("semana puxada de entrega")
        except Exception:
            pass
        return risk, why

    def _approx_slept(self, day: date) -> float:
        try:
            from sleep_plan import SleepPlan
            return SleepPlan(self.db)._approx_hours_slept(day)
        except Exception:
            return 7.5

    def headache(self, day: date) -> Optional[tuple[datetime, datetime, str]]:
        return _memo(self.db, "headache", day, lambda: self._headache(day))

    def _headache(self, day: date) -> Optional[tuple[datetime, datetime, str]]:
        """(começo, fim, remédio) da dor de cabeça do dia, se tiver."""
        rng = _rng(f"cabeca:{day.isoformat()}")
        roll = rng.random()
        if roll >= HEADACHE_CHANCE_BAD_SLEEP:
            return None   # nem com noite ruim daria: não precisa perguntar do sono
        if roll >= HEADACHE_CHANCE and self._approx_slept(day) >= 5.5:
            return None
        start = datetime.combine(day, time(13, 0)) + timedelta(minutes=rng.randint(0, 7 * 60))
        if rng.random() < HEADACHE_RESIST_CHANCE:
            return start, start + timedelta(hours=rng.randint(3, 5)), "não tomou nada, tá aguentando"
        took = start + timedelta(minutes=rng.randint(30, 90))
        return start, took + timedelta(minutes=40), f"tomou uma dipirona às {took:%H:%M}"

    # ------------------------------------------------------------ agora --
    def conditions(self, now: datetime) -> list[Condition]:
        day = now.date()
        out: list[Condition] = []
        level = self.cramps(day)
        if level:
            remedy = {1: "bolsa de água quente, sem remédio",
                      2: "tomou um Buscopan de manhã",
                      3: "tomou Buscopan, tá de bolsa de água quente e não sai da cama"}[level]
            out.append(Condition("colica", f"cólica {CRAMP_WORD[level]}", CRAMP_DISCOMFORT[level],
                                 0.04 * level, 1.0, remedy, level == 3, datetime.combine(day, time(6, 0))))
        sick = self.illness(day)
        if sick:
            kind, n, length, grav = sick
            started = datetime.combine(day - timedelta(days=n - 1), time(8, 0))
            if kind == "virose":
                out.append(Condition("virose", "virose (enjoo e dor de barriga)", 0.7, 0.25, 0.35,
                                     "soro caseiro, torrada e caldo; só dieta leve", True, started))
            else:
                peak = n in (1, 2) if length > 3 else n == 1
                strong = grav == 2 and peak
                label = ("resfriado forte (nariz entupido, corpo moído)" if strong
                         else "resfriada (nariz escorrendo, espirrando)" if n < length
                         else "finzinho de resfriado")
                remedy = ("Benegrip e chá de gengibre com mel" if n <= 2
                          else "chá de gengibre com mel, já melhorando")
                out.append(Condition("resfriado", label, 0.45 if strong else 0.25 if n < length else 0.1,
                                     0.2 if strong else 0.1, 0.8, remedy, strong, started))
        ache = self.headache(day)
        if ache and ache[0] <= now < ache[1]:
            out.append(Condition("dor_de_cabeca", "dor de cabeça", 0.4, 0.1, 0.9, ache[2], False, ache[0]))
        return out

    def discomfort(self, now: datetime) -> tuple[float, str]:
        conds = self.conditions(now)
        if not conds:
            return 0.0, ""
        worst = max(c.discomfort for c in conds)
        extra = sum(c.discomfort for c in conds) - worst
        return min(1.0, worst + 0.3 * extra), ", ".join(c.label for c in conds)

    def energy_penalty(self, now: datetime) -> float:
        return min(0.35, sum(c.energy_penalty for c in self.conditions(now)))

    def appetite(self, now: datetime) -> float:
        mult = 1.0
        for c in self.conditions(now):
            mult *= c.appetite
        return mult

    def is_sick(self, day: date) -> bool:
        return self.illness(day) is not None

    # --------------------------------------------------- sono e faculdade --
    def onset(self, day: date) -> tuple[int, list[str]]:
        """Doente dorme mais cedo (gancho do `sleep_plan._onset`)."""
        sick = self.illness(day)
        if sick:
            kind, _, _, grav = sick
            minutes = -60 if kind == "virose" or grav == 2 else -35
            return minutes, [f"{'com virose' if kind == 'virose' else 'resfriada'}, o corpo pediu cama cedo"]
        if self.cramps(day) == 3:
            return -30, ["cólica forte, foi deitar cedo com a bolsa de água quente"]
        return 0, []

    def skip_option(self, day: date) -> Optional[tuple[float, str]]:
        """(chance, motivo) de faltar aula por saúde, ou None."""
        sick = self.illness(day)
        if sick and sick[0] == "virose":
            return SKIP_CHANCE["virose"], "virose, passou mal e ficou em casa"
        options = []
        if sick and sick[0] == "resfriado":
            now = datetime.combine(day, time(8, 0))
            if any(c.kind == "resfriado" and c.strong for c in self.conditions(now)):
                options.append((SKIP_CHANCE["resfriado_forte"], "resfriado forte, ficou de molho"))
        level = self.cramps(day)
        if level >= 2:
            options.append((SKIP_CHANCE[f"colica{level}"],
                            "cólica forte, ficou em casa" if level == 3 else "cólica, preferiu ficar em casa"))
        return max(options) if options else None

    # ------------------------------------------------------------ prompt --
    def prompt_lines(self, now: datetime) -> list[str]:
        conds = self.conditions(now)
        if not conds:
            return []
        facts = "; ".join(f"{c.label} — {c.remedy}" for c in conds)
        lines = [f"- Saúde: {facts}."]
        if any(c.strong for c in conds):
            lines.append("  Tá mal de verdade: com o Patrick fica manhosa, curtinha, aceita dengo e cuidado. "
                         "Nada de médico por isso; se o pai souber, ele se preocupa e manda ir.")
        else:
            lines.append("  Coisa pequena: você minimiza e segue a vida (\"é só uma dorzinha\"). "
                         "Só fala disso se vier ao caso ou se ele perguntar.")
        return lines
