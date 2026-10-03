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
* **Peso**: 1,68 m, base 54 kg; muda devagar pelo saldo da semana (lanches,
  excessos × academia). Ela só sabe quando se pesa (na academia, 1×/semana). Acima
  de 56 kg a Lívia cobra e vem a dieta curta; abaixo de 52 kg é a saúde que reage.
* **Saciedade** (Patrick, 26/09): a fome cai em tempo real enquanto ela come. Satisfeita,
  ela larga o prato (a refeição acaba antes); se é dia de gula, come tudo mesmo assim e
  o que passou da conta vira **excesso** (fica estufada, demora mais pra ter fome, e
  pesa na balança da semana).
* **Beliscando** (Patrick, 26/09): com fome em casa e a próxima refeição longe, ela
  belisca alguma coisa na hora — vira lanche de verdade.
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
# Saciedade: quanto cada refeição "enche" (mesma escala da fome, 0–1).
PORCAO = {"cafe": 0.6, "almoco": 0.9, "jantar": 0.85, "lanche": 0.3}
SATISFEITA = 0.1          # come até a fome passar disso pra baixo… (margem de conforto)
EXCESSO_MIN = 0.15        # …e o que passar disto além da conta é excesso
GULA_CHANCE = 0.35        # glutoninha: dia de comer tudo mesmo satisfeita
BELISCO_FOME = 0.62       # fome em casa que faz ela beliscar
BELISCO_GAP = timedelta(minutes=90)
DURATION_MIN = {"cafe": (10, 25), "almoco": (25, 45), "jantar": (20, 35), "lanche": (5, 15)}
# Uma refeição por janela: repetir "vou jantar agora" não abre outro jantar.
SAME_MEAL_WINDOW = timedelta(hours=3)

KIND_NAME = {"cafe": ("café da manhã", "tomando café da manhã"),
             "almoco": ("almoço", "almoçando"),
             "jantar": ("jantar", "jantando"),
             "lanche": ("lanche", "beliscando")}

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
               "biscoito com café", "pipoca"],     # soak, dia 2: "pipoca vendo série" com ela no TikTok/closet
    "dieta": ["salada com frango grelhado", "omelete de claras com salada", "sopa de legumes"],
}


SAIDA_PREFIXOS = ("outing", "freela", "vontade", "mercado", "medico", "unhas", "cabelo")
SAIDA_ANTES = timedelta(minutes=75)         # caminho (~40) + se arrumar (~35): a refeição acaba antes disso
SAIDA_ANTES_NOITE = timedelta(minutes=110)  # rolê à noite: arrumação longa (60–90)
SAIDA_VOLTA = timedelta(minutes=40)
LANCHE_NOITE_ANTES_DE_DEITAR = timedelta(minutes=15)
SAIDA_CURTA = timedelta(minutes=90)
SAIDA_DEPOIS_DA_AULA = timedelta(hours=2)   # saída até 2 h depois da última aula: não almoça por lá antes
REFEICAO_INTERVALO = timedelta(minutes=60)
REFEICAO_PISO = {"almoco": time(11, 0), "jantar": time(18, 0)}   # mais cedo que isso não é almoço/jantar


@dataclass(frozen=True)
class MealSlot:
    kind: str             # cafe | almoco | jantar | lanche
    key: str              # meal:<data>:<tipo>[:n]
    at: datetime
    minutes: int
    where: str            # casa | puc | gavea
    dish: str
    skipped: bool = False
    por_la: bool = False  # come no rolê: a primeira comida de lá é a refeição (consumo.py), não "pulou"

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


# 24/09: "vou ficar aqui jantando", "tô engolindo correndo" — nada disso abria refeição, e o
# /status seguia mostrando outra coisa. Presente/imediato: começa já, sem atraso.
MEAL_NOW_RE = re.compile(
    r"\b(?:t[oô]|estou|t[oô] aqui|fico aqui|vou ficar aqui)\s+(?:jantando|almo[çc]ando|comendo|lanchando|"
    r"engolindo|atacando|devorando|tomando (?:meu|o) (?:caf[eé]|a[çc]a[ií]))\b",
    re.IGNORECASE,
)


# 28/09: "vou comprar um sanduíche antes de entrar" (a caminho da PUC) não virava nada — só a promessa em casa e
# "agora" abria refeição. Na rua, comprar/comer algo vira lanche fora, com o preço no saldo dela.
RUA_COMIDA = {"sanduíche": 15, "sanduiche": 15, "misto": 12, "salgado": 8, "coxinha": 8, "empada": 8, "esfiha": 8,
              "pão de queijo": 9, "pao de queijo": 9, "barrinha": 6, "fruta": 5, "banana": 3, "açaí": 18, "acai": 18,
              "biscoito": 5, "croissant": 14, "tapioca": 14, "lanche": 14}
RUA_RE = re.compile(
    r"\b(?:vou|j[aá] vou|vou l[aá])\s+(?:comprar|pegar|comer|beliscar)\s+(?P<item>(?:um|uma|uns|umas)\s+"
    r"(?P<comida>p[aã]o de queijo|[a-zçãéíõúâê]+)|alguma coisa|algo)(?P<resto>[^.!?\n]{0,60})",
    re.IGNORECASE,
)


def comida_na_rua(text: str) -> Optional[tuple[str, int]]:
    """("um sanduíche", 15) se ela disse que vai comprar/comer algo agora; None se não é comida."""
    for m in RUA_RE.finditer(text or ""):
        comida = (m.group("comida") or "").lower()
        if comida:
            base = comida[:-1] if comida.endswith("s") and comida[:-1] in RUA_COMIDA else comida
            if base in RUA_COMIDA:
                return m.group("item").lower(), RUA_COMIDA[base]
            continue
        if re.search(r"\b(comer|comprar|pegar)\b", m.group(0), re.IGNORECASE) and re.search(
                r"caminho|antes d[aeo]|rapidinh|pra comer|fome", m.group(0) + (m.group("resto") or ""), re.IGNORECASE):
            return "um lanche", RUA_COMIDA["lanche"]
    return None


def announces_meal(text: str) -> bool:
    return bool(MEAL_PROMISE_RE.search(text or "") or MEAL_NOW_RE.search(text or ""))


def _rng(day: date, name: str) -> random.Random:
    return random.Random(f"marina-meal:{day.isoformat()}:{name}")


def _kg(v: float) -> str:
    """54.4 → '54,4' (painel)."""
    return f"{v:.1f}".replace(".", ",")


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

    def painel_peso(self, now: datetime) -> dict:
        """Seção "Peso" da aba Por fora (Patrick, 28/09): o peso de verdade (ela só sabe o da balança),
        a barra de folga até o limite da agência (enche de 52 a 56 kg; amarela quando passa), Pesou, Dieta
        e Altura."""
        data = self.weight()
        kg = float(data["kg"])
        folga = self.AGENCY_MAX_KG - kg
        palavra = (f"Folga {_kg(folga)} kg" if folga > 0.05 else "No limite" if folga > -0.05
                   else f"Passou {_kg(-folga)} kg")
        pesou = "Ainda não"
        if data.get("known_at") and data.get("known_kg") is not None:
            dias = (now.date() - datetime.fromisoformat(data["known_at"]).date()).days
            quando = ("Hoje" if dias == 0 else "Ontem" if dias == 1
                      else ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")[
                          datetime.fromisoformat(data["known_at"]).weekday()] if dias < 7 else f"Há {dias} dias")
            pesou = f"{quando}, {_kg(float(data['known_kg']))} kg"
        until = data.get("diet_until")
        dieta = f"Até {date.fromisoformat(until):%d/%m}" if until and now.date() <= date.fromisoformat(until) else "Não"
        span = self.AGENCY_MAX_KG - self.HEALTH_MIN_KG
        return {"kg": f"{_kg(kg)} kg", "barra": round(max(0.0, min(1.0, (kg - self.HEALTH_MIN_KG) / span)), 2),
                "palavra": palavra, "alerta": folga < -0.05,
                "linhas": [["scale", "Pesou", pesou], ["salad", "Dieta", dieta], ["ruler-2", "Altura", "1,68 m"]]}

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
        volta = self._volta_puc(day) if blocks else None
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
                # 28/09 (Patrick, "depende da carona"): a carona com o Theo saiu às 13:00 e o almoço ficou
                # "no restaurante da PUC" 13:15–13:58. Com carona volta direto e almoça em casa; sozinha, às vezes
                # almoça por lá e a volta sai depois (commute pergunta `almoco_pos_aula`).
                lunch = self.almoco_pos_aula(day, volta.mode if volta else "")
                if lunch is None and volta:
                    lunch = MealSlot("almoco", f"meal:{iso}:almoco", volta.end + timedelta(minutes=rng.randint(10, 25)),
                                     dur("almoco", rng), "casa", rng.choice(MENU["almoco_casa"]))
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
            minutos, prato = dur("lanche", rng), rng.choice(["pipoca", "um chocolate", "um açaí pequeno"])
            # 28/09 (auditoria): o Hoje previa "~22:55 Lanche" depois de "~22:30 Dormir" — só se couber antes de deitar
            if night + timedelta(minutes=minutos) <= self._deitar(day) - LANCHE_NOITE_ANTES_DE_DEITAR:
                slots.append(MealSlot("lanche", f"meal:{iso}:lanche:2", night, minutos, "casa", prato))
        return self._antes_das_saidas(day, sorted(slots, key=lambda s: s.at), wake, volta)

    def _deitar(self, day: date) -> datetime:
        """A hora de deitar sem os fatores do corpo (ou a congelada): o sono não depende das refeições."""
        try:
            from sleep_plan import SleepPlan
            return SleepPlan(self.db)._bed_simple(day)
        except Exception:
            logger.exception("meals.deitar")
            return datetime.combine(day + timedelta(days=1), time(3, 30))

    ALMOCO_POR_LA = 0.5         # sozinha, depois da última aula: chance de almoçar na PUC/Gávea antes de voltar
    ALMOCO_TARDE = time(14, 0)   # ...e aula acabando daí em diante, sozinha, almoça por lá (em casa seria 16h)

    def almoco_pos_aula(self, day: date, modo_volta: str) -> Optional[MealSlot]:
        """O almoço por lá depois da última aula (a volta sai depois dele), ou None (volta direto e come em casa).
        Não consulta o trajeto: o commute chama com o modo da volta."""
        blocks = self._blocks(day)
        if not blocks or modo_volta == "carona":
            return None
        noon_lo = datetime.combine(day, time(11, 30))
        if any((b[0] - a[1]) >= timedelta(minutes=40) and noon_lo <= a[1] <= datetime.combine(day, time(14, 30))
               for a, b in zip(blocks, blocks[1:])):
            return None                                  # almoça no intervalo entre aulas
        fim = blocks[-1][1]
        if not (noon_lo <= fim <= datetime.combine(day, time(15, 0))):
            return None
        if any(fim <= ini < fim + SAIDA_DEPOIS_DA_AULA for ini, _ in self._saidas(day)):
            # Soak, dia 2 (01/10 planejado): aula até 15:00, "comida japonesa no Shopping da Gávea" 15:18 e casting
            # às 15:30 — a volta saía 15:50 e emendava no 2º casting. Com saída logo depois, vai direto (come por lá).
            return None
        rng = _rng(day, "almoco_pos_aula")
        chance = 1.0 if fim.time() >= self.ALMOCO_TARDE else self.ALMOCO_POR_LA   # aula até 15:00: não espera chegar
        if rng.random() >= chance:
            return None
        where = "puc" if rng.random() < 0.5 else "gavea"
        return MealSlot("almoco", f"meal:{day.isoformat()}:almoco", fim + timedelta(minutes=rng.randint(10, 20)),
                        rng.randint(*DURATION_MIN["almoco"]), where,
                        rng.choice(MENU["almoco_puc" if where == "puc" else "almoco_gavea"]))

    def _volta_puc(self, day: date):
        try:
            from commute import Commute
            return Commute(self.db).volta_puc(day)
        except Exception:
            logger.exception("meals.volta_puc")
            return None

    def _saidas(self, day: date) -> list[tuple[datetime, datetime]]:
        """Saídas confirmadas do dia (rolê, freela, vontade, mercado, médico, salão): (início lá, fim lá)."""
        iso = day.isoformat()
        try:
            with self.db.get_connection() as conn:
                rows = conn.execute(
                    """SELECT event_at, end_at FROM eventos_pendentes WHERE confirmed=1 AND status != 'cancelled'
                       AND end_at IS NOT NULL AND (""" + " OR ".join("source_key LIKE ?" for _ in SAIDA_PREFIXOS)
                    + ")", [f"{p}:{iso}%" for p in SAIDA_PREFIXOS]).fetchall()
            saidas = sorted((datetime.fromisoformat(r["event_at"]), datetime.fromisoformat(r["end_at"])) for r in rows)
        except Exception:
            return []
        # Soak, dia 2 (01/10 planejado): castings 15:30–17:00 e 17:00–18:30 — o almoço "quando voltar" caía 17:40, no
        # meio do segundo. Saídas emendadas contam como uma só.
        juntas: list[tuple[datetime, datetime]] = []
        for ini, fim in saidas:
            if juntas and ini <= juntas[-1][1] + timedelta(minutes=15):
                juntas[-1] = (juntas[-1][0], max(juntas[-1][1], fim))
            else:
                juntas.append((ini, fim))
        return juntas

    def _comida_no_role(self, day: date, ini: datetime, fim: datetime) -> bool:
        """O rolê desse horário tem comida (consumo.plan, sem trajeto: aqui não pode chamar o Commute)?"""
        try:
            from consumo import plan
            with self.db.get_connection() as conn:
                rows = [dict(r) for r in conn.execute(
                    """SELECT source_key, event_at, end_at, location_key, metadata_json FROM eventos_pendentes
                       WHERE (source_key LIKE ? OR source_key LIKE ?) AND confirmed=1 AND status != 'cancelled'
                       AND end_at IS NOT NULL""", (f"outing:{day.isoformat()}:%", f"vontade:{day.isoformat()}:%"))]
            return any(i.comida for r in rows if datetime.fromisoformat(r["event_at"]) < fim
                       and datetime.fromisoformat(r["end_at"]) > ini for i in plan(r))
        except Exception:
            return False

    def _antes_das_saidas(self, day: date, slots: list[MealSlot], wake: datetime, volta_puc=None) -> list[MealSlot]:
        """27/09 (auditoria): o almoço em casa das 13:50–14:29 atravessava a saída das 14:20 pro cinema das 15:00
        e o Se arrumando sumia do card. Refeição em casa sai antes do preparo; se não cabe, ela come quando
        voltar (saída curta) ou come por lá (o consumo do rolê)."""
        saidas = self._saidas(day)
        if not saidas:
            return slots
        from dataclasses import replace
        out: list[MealSlot] = []
        for s in slots:
            if s.where != "casa" or s.skipped:
                out.append(s)
                continue
            for ini, fim in saidas:
                sai = ini - (SAIDA_ANTES_NOITE if ini.hour >= 18 else SAIDA_ANTES)
                volta = fim + SAIDA_VOLTA
                if not (s.at < volta and s.end > sai):
                    continue
                piso = (out[-1].end + REFEICAO_INTERVALO) if out else wake + timedelta(minutes=15)
                if volta_puc and s.at >= volta_puc.start:    # 28/09: não come em casa antes de chegar da PUC
                    piso = max(piso, volta_puc.end + timedelta(minutes=5))
                antes = sai - timedelta(minutes=s.minutes)
                if antes >= piso and antes.time() >= REFEICAO_PISO.get(s.kind, time(0)):
                    s = replace(s, at=antes)                                     # come antes de se arrumar
                elif fim - ini <= SAIDA_CURTA:
                    s = replace(s, at=volta)                                     # saída curta: come quando voltar
                else:
                    s = replace(s, skipped=True, por_la=self._comida_no_role(day, ini, fim))  # come por lá
                break
            out.append(s)
        return sorted(out, key=lambda s: s.at)

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

    def saciedade(self, slot: MealSlot) -> dict:
        """Quanto ela come dessa refeição: pela fome que chegou, pela porção e pelo dia de gula."""
        antes = self.hunger(slot.at)
        porcao = PORCAO.get(slot.kind, 0.5) * (1.1 if "brunch" in slot.dish else 1.0)
        precisa = max(0.0, antes - SATISFEITA)            # o que a fome dela pede
        rng = _rng(slot.at.date(), f"gula:{slot.key}")
        chance = GULA_CHANCE + (0.2 if self._phase() == "tpm" else 0.0) - (0.25 if self.on_diet(slot.at.date()) else 0.0)
        gula = rng.random() < chance
        if porcao <= precisa + EXCESSO_MIN or gula or slot.kind == "lanche":
            comeu, larga = porcao, False            # lanche é vontade (pipoca na série): come mesmo sem fome
        else:
            comeu, larga = max(precisa, porcao * 0.25), True
        minutos = max(5, round(slot.minutes * comeu / porcao)) if larga else slot.minutes
        excesso = round(max(0.0, comeu - precisa), 3) if gula and slot.kind != "lanche" else 0.0
        return {"fome_antes": round(antes, 3), "comeu": round(comeu, 3), "porcao": round(porcao, 3),
                "larga": larga, "excesso": excesso if excesso >= EXCESSO_MIN else 0.0, "minutos": minutos}

    def _record(self, slot: MealSlot, now: datetime, motivo: str = "") -> Optional[dict]:
        """Registra a refeição; devolve a saciedade (None se já estava registrada)."""
        name, _ = KIND_NAME[slot.kind]
        where = {"casa": "em casa", "puc": "no restaurante da PUC", "gavea": "no Shopping da Gávea"}[slot.where]
        sac = {} if slot.skipped else self.saciedade(slot)
        if sac:
            sac["prato"] = slot.dish
        if motivo:
            sac["motivo"] = motivo
        if slot.skipped and slot.kind == "cafe":
            summary = f"Pulou o {name}: acordou em cima da hora pra aula."
        elif slot.skipped:                                # soak, dia 2: o almoço de 01/10 cai entre aula e castings
            summary = f"Pulou o {name}: não deu tempo entre os compromissos."
        elif slot.kind == "lanche":
            summary = f"Beliscou {slot.dish}."
        else:
            summary = f"{name.capitalize()} {where}: {slot.dish}."
        if sac.get("larga"):
            summary = summary.rstrip(".") + "; ficou satisfeita e largou o resto no prato."
        elif sac.get("excesso"):
            summary = summary.rstrip(".") + "; comeu além da conta e ficou estufada."
        end = slot.at + timedelta(minutes=sac.get("minutos", slot.minutes))
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,end_at,event_type,title,summary,
                   source_type,autonomy_level,importance,participants_json,share_worthy,metadata_json,created_at)
                   VALUES (?,?,?,?,?,?,'simulated',1,0.1,?,0.3,?,?)""",
                (slot.key, slot.at.isoformat(), end.isoformat(), "snack" if slot.kind == "lanche" else "meal",
                 name, summary, json.dumps(["marina"]), json.dumps(sac, ensure_ascii=False) if sac else None,
                 now.isoformat()))
            conn.commit()
            return {**sac, "fim": end} if cur.rowcount else None

    def _transition_busy(self, now: datetime) -> bool:
        raw = self.db.get_estado_relacional().get("pending_transition_json")
        if not raw:
            return False
        try:
            return datetime.fromisoformat(json.loads(raw)["end_at"]) > now
        except (TypeError, ValueError, KeyError):
            return False

    def _at_home(self) -> bool:
        return not self._fora(WorldStateRepository(self.db).latest())

    def _away_at(self, t: datetime) -> bool:
        """Ela estava fora de casa às `t`? (o retrato do mundo que valia naquela hora)"""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM world_state WHERE observed_at<=? ORDER BY observed_at DESC, id DESC LIMIT 1",
                               (t.isoformat(),)).fetchone()
        return self._fora(dict(row)) if row else False

    @staticmethod
    def _fora(state: Optional[dict]) -> bool:
        if not state:
            return False
        activity = (state.get("activity") or "").casefold()
        region = (state.get("location_region") or "").casefold()
        source = state.get("source_json")
        source = json.loads(source or "{}") if isinstance(source, str) else (source or {})
        if source.get("reason") in ("confirmed_commitment", "commute", "pos_aula"):
            return True                                   # num compromisso ou no caminho: não está em casa
        away = ("dorm", "a caminho", "uber", "ônibus", "metrô", "carona", "academia", "trein",
                "faculdade", "aula", "com amig", "bar", "praia", "saindo com", "voltando", "a pé", "passeando")
        return any(t in activity for t in away) or "a caminho" in region

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
            if slot.por_la:
                # Soak, dia 4 (02/10, 20:35): "Pulou o jantar: não deu tempo entre os compromissos" no Quartinho, e
                # as fritas das 20:46 viraram lanche. Quem registra a refeição do rolê é o consumo.
                continue
            if slot.where == "casa" and not slot.skipped and not self._at_home():
                # fora de casa: espera ela voltar. 27/09: passada a janela, a pipoca "vendo série" das 21:07
                # era registrada com ela no Quartinho Bar.
                continue
            if slot.where == "casa" and not slot.skipped and self._comida_chegando(now):
                continue      # 27/09: comida a caminho (dela, ou do Patrick com aviso) — é essa que ela come
            if slot.where == "casa" and not slot.skipped and self._away_at(slot.at):
                # 26/09: o chocolate das 16:39 foi registrado com ela voltando da academia a pé.
                # Chegou em casa: come agora (lanche que passou de 1 h da hora não acontece mais).
                if slot.kind == "lanche" and now - slot.at > timedelta(hours=1):
                    continue
                from dataclasses import replace
                slot = replace(slot, at=now)
            sac = self._record(slot, now)
            if sac is not None:
                created += 1
                if (slot.where == "casa" and not slot.skipped and now < sac["fim"]
                        and not self._transition_busy(now)):
                    self._start_eating(slot, slot.at, sac["fim"], now)
        created += self._belisca(now, floor)
        created += self._belisca_na_puc(now, floor)
        self._weigh_in(now)
        return created

    def _belisca(self, now: datetime, floor: datetime) -> int:
        """Com fome em casa e a próxima refeição longe: belisca alguma coisa agora."""
        if now < floor or not self._at_home() or self._transition_busy(now) or now.hour < 7 and now.hour >= 2:
            return 0
        if self.hunger(now) < BELISCO_FOME or self._na_cama(now):
            return 0
        proxima = next((s for s in self.day_plan(now.date()) if s.at > now and not s.skipped), None)
        if proxima and proxima.at - now < timedelta(minutes=60):
            return 0                                      # segura pra próxima refeição
        if self._comida_chegando(now) or self._numa_etapa(now):
            return 0
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT MAX(event_at) FROM life_events WHERE event_type IN ('meal','snack') "
                               "AND event_at<=?", (now.isoformat(),)).fetchone()
            n = conn.execute("SELECT COUNT(*) FROM life_events WHERE event_key LIKE ?",
                             (f"meal:{now.date().isoformat()}:lanche:b%",)).fetchone()[0]
        if row and row[0] and now - datetime.fromisoformat(row[0]) < BELISCO_GAP:
            return 0
        rng = _rng(now.date(), f"belisco:{n}")
        opcoes = MENU["dieta"][:1] + ["uma fruta"] if self.on_diet(now.date()) else MENU["lanche"]
        slot = MealSlot("lanche", f"meal:{now.date().isoformat()}:lanche:b{n + 1}", now,
                        rng.randint(*DURATION_MIN["lanche"]), "casa", rng.choice(opcoes))
        sac = self._record(slot, now, motivo="fome")
        if sac is None:
            return 0
        if not self._transition_busy(now):
            self._start_eating(slot, slot.at, sac["fim"], now)
        logger.info("meal.belisco dish=%s", slot.dish)
        return 1

    BELISCO_PUC = ("um pão de queijo na cantina da PUC", "um salgado na cantina da PUC",
                   "uma barrinha de cereal entre as aulas", "um café com biscoito na cantina da PUC")

    def _belisca_na_puc(self, now: datetime, floor: datetime) -> int:
        """Soak, dia 1 (29/09): quatro aulas seguidas (07–15h), "morrendo de fome" às 11:47 e nada até o almoço das
        15:18 — o belisco só existia em casa. Com fome na PUC, belisca na troca de aula (até 10 min depois de uma
        aula começar), longe da próxima refeição."""
        if now < floor or self._transition_busy(now):
            return 0
        try:
            from academic_life import AcademicLife
            blocks = AcademicLife(self.db).blocks_on(now.date())
        except Exception:
            return 0
        inicios = [datetime.fromisoformat(b["start_at"]) for b in blocks]
        if not any(i <= now < i + timedelta(minutes=10) for i in inicios[1:]):
            return 0                                      # só na troca de aula, não na primeira
        latest = WorldStateRepository(self.db).latest() or {}
        src = latest.get("source_json")
        src = json.loads(src or "{}") if isinstance(src, str) else (src or {})
        if not src.get("academic_block_id"):
            return 0                                      # não está na aula (faltou ou já saiu): não é aqui
        if self.hunger(now) < BELISCO_FOME:
            return 0
        proxima = next((s for s in self.day_plan(now.date()) if s.at > now and not s.skipped), None)
        if proxima and proxima.at - now < timedelta(minutes=60):
            return 0
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT MAX(event_at) FROM life_events WHERE event_type IN ('meal','snack') "
                               "AND event_at<=?", (now.isoformat(),)).fetchone()
            n = conn.execute("SELECT COUNT(*) FROM life_events WHERE event_key LIKE ?",
                             (f"meal:{now.date().isoformat()}:lanche:b%",)).fetchone()[0]
        if row and row[0] and now - datetime.fromisoformat(row[0]) < BELISCO_GAP:
            return 0
        rng = _rng(now.date(), f"belisco:{n}")
        slot = MealSlot("lanche", f"meal:{now.date().isoformat()}:lanche:b{n + 1}", now,
                        rng.randint(*DURATION_MIN["lanche"]), "puc", rng.choice(self.BELISCO_PUC))
        if self._record(slot, now, motivo="fome") is None:
            return 0
        logger.info("meal.belisco_puc dish=%s", slot.dish)
        return 1

    def _na_cama(self, now: datetime) -> bool:
        """28/09: saiu do banho às 23:55 (o deitar acompanhou o banho) e às 23:56 "beliscou" — dormindo pelo plano
        de sono não belisca (o limite era só 02:00–07:00)."""
        try:
            from sleep_plan import SleepPlan, enabled
            return enabled() and SleepPlan(self.db).in_bed(now)
        except Exception:
            return False

    def _numa_etapa(self, now: datetime) -> bool:
        """27/09, 19:28: "beliscou iogurte com granola" com ela já saindo pra farmácia — o retrato do mundo ainda
        dizia "em casa". Se arrumando, a caminho, lá ou voltando (aba Agora): não é hora de beliscar em casa.
        28/09, 16:46 (auditoria): o belisco começou 1 min antes do Se arrumando do passeio do Milo e foi até 16:52
        — o mundo e o chat ficaram em "beliscando" e o preparo nunca apareceu. Etapa que começa antes do belisco
        acabar também conta."""
        try:
            from agenda import Agenda
            ag = Agenda(self.db)
            if ag.agora(now) is not None:
                return True
            ate = now + timedelta(minutes=DURATION_MIN["lanche"][1])
            return any(now < e.inicio < ate for e in ag.etapas(now.date(), now))
        except Exception:
            return False

    def _comida_chegando(self, now: datetime) -> bool:
        """26/09, 16:40: chegou da academia com fome e beliscou um chocolate, com o sanduíche que o Patrick
        mandou esperando na portaria desde 16:26 (pegou às 16:41). Presente na portaria ela pega ao subir;
        o pedido dela a caminho (até 45 min) ela espera."""
        try:
            import delivery
            cur = delivery.open_order(self.db)
        except Exception:
            return False
        if not cur:
            return False
        if cur.get("by") == "patrick":
            if cur.get("status") == "portaria":
                return cur.get("eats", True)
            # 27/09: ele avisou no chat que pediu — ela espera a comida dele (não janta tapioca às 21:32)
            try:
                return (cur.get("eats", True) and delivery.avisado(self.db, cur, now)
                        and datetime.fromisoformat(cur["eta_at"]) - now <= delivery.AVISADO_ESPERA)
            except (KeyError, TypeError, ValueError):
                return False
        try:
            return datetime.fromisoformat(cur["eta_at"]) - now <= timedelta(minutes=45)
        except (KeyError, TypeError, ValueError):
            return False

    # ----------------------------------------------------------- promessa --
    def observe_marina_line(self, text: str, now: datetime) -> Optional[dict]:
        """Chamado depois que a fala dela é entregue. Retorna o payload se abriu refeição."""
        if not self._at_home():
            self.lanche_na_rua(text, now)
            return None
        if not announces_meal(text):
            return None
        kind = meal_kind(now)
        if self._recent_meal(now) or self._transition_busy(now) or not self._at_home():
            return None
        if kind != "lanche" and self._logged(now.date(), kind):
            return None
        rng = random.Random(f"meal-promise:{now.isoformat(timespec='minutes')}")
        start = now if MEAL_NOW_RE.search(text or "") else now + timedelta(minutes=rng.randint(*START_DELAY_MIN))
        planned = {s.kind: s for s in self.day_plan(now.date())}
        dish = planned[kind].dish if kind in planned else rng.choice(MENU["lanche"])
        slot = MealSlot(kind, f"meal:{now.date().isoformat()}:{kind}" + (":p" if kind == "lanche" else ""),
                        start, rng.randint(*DURATION_MIN[kind]), "casa", dish)
        self._record(slot, now)
        self._start_eating(slot, start, slot.end, now)
        logger.info("meal.promised kind=%s start=%s", kind, start.isoformat(timespec="minutes"))
        return json.loads(self.db.get_estado_relacional()["pending_transition_json"])

    RUA_ATE_COMPRAR = timedelta(minutes=10)

    def lanche_na_rua(self, text: str, now: datetime) -> bool:
        """Na rua (a caminho, lá), ela disse que vai comprar/comer algo: compra e come (sai do saldo dela).
        Uma vez por hora (repetir a promessa na conversa não compra outro)."""
        achado = comida_na_rua(text)
        if not achado:
            return False
        try:                        # no rolê (bar, café, cinema) o consumo.py já decide o que ela pede
            from agenda import Agenda
            etapa = Agenda(self.db).agora(now)
            if etapa and etapa.tipo == "la" and not etapa.compromisso.startswith(("puc:", "gym:", "milo:", "medico:")):
                return False
        except Exception:
            logger.exception("meals.rua.agenda")
        item, valor = achado
        at = now + self.RUA_ATE_COMPRAR
        with self.db.get_connection() as conn:
            if conn.execute("SELECT 1 FROM life_events WHERE event_key LIKE ? AND event_at>=? LIMIT 1",
                            (f"meal:{now.date().isoformat()}:lanche:rua:%",
                             (now - timedelta(hours=1)).isoformat())).fetchone():
                return False
            chave = f"{now.date().isoformat()}:lanche:rua:{at:%H%M}"
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,end_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,?,'snack','comeu na rua',?,'simulated',1,0.1,?,0.2,?)""",
                (f"meal:{chave}", at.isoformat(), (at + timedelta(minutes=8)).isoformat(),
                 f"Comeu {item} no caminho.", json.dumps(["marina"]), now.isoformat()))
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'consumo',?,?,'simulated',1,0.1,?,0.1,?)""",
                (f"consumo:{chave}", at.isoformat(), f"na rua · {item}", f"Pediu {item} no caminho (R$ {valor}).",
                 json.dumps(["marina"]), now.isoformat()))
            conn.commit()
        logger.info("meal.rua item=%s at=%s", item, at.isoformat(timespec="minutes"))
        return True

    def _recent_meal(self, now: datetime) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT event_at FROM life_events WHERE event_type='meal'
                   AND event_at>=? AND event_at<=? ORDER BY event_at DESC LIMIT 1""",
                ((now - SAME_MEAL_WINDOW).isoformat(), (now + timedelta(minutes=10)).isoformat())).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------ apetite --
    def _gym_today(self, now: datetime) -> bool:
        """Treinou hoje (o treino em si). Bug 16, 28/09: o preparo ("colocando roupa de treino") contava, e ela
        "se pesou na academia" às 18:43, ainda a caminho."""
        start = datetime.combine(now.date(), time(0, 0)).isoformat()
        with self.db.get_connection() as conn:
            return bool(conn.execute(
                "SELECT 1 FROM world_state WHERE observed_at>=? AND observed_at<=? AND "
                "activity LIKE 'treinando%' LIMIT 1",
                (start, now.isoformat())).fetchone())

    def _ultima(self, now: datetime) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT event_at, end_at, event_type, summary, metadata_json FROM life_events
                   WHERE event_type IN ('meal','snack') AND event_at>=? AND event_at<=? AND summary NOT LIKE 'Pulou%'
                   ORDER BY event_at DESC LIMIT 1""",
                (datetime.combine(now.date(), time(0, 0)).isoformat(), now.isoformat())).fetchone()
        return dict(row) if row else None

    def hunger(self, now: datetime) -> float:
        """Fome agora (tempo real): cai enquanto ela come e sobe com as horas desde que terminou.
        Depois de um excesso começa abaixo de zero (estufada) e demora mais pra voltar."""
        e = self._ultima(now)
        meta = json.loads(e["metadata_json"] or "{}") if e else {}
        if e and "fome_antes" in meta:
            ini = datetime.fromisoformat(e["event_at"])
            fim = datetime.fromisoformat(e["end_at"]) if e["end_at"] else ini + timedelta(minutes=15)
            if now < fim:                   # comendo: a fome vai passando
                frac = (now - ini).total_seconds() / max(60.0, (fim - ini).total_seconds())
                return round(max(0.0, min(1.0, meta["fome_antes"] - meta["comeu"] * frac)), 3)
            last, base = fim, max(-0.4, meta["fome_antes"] - meta["comeu"])
        elif e:
            last = datetime.fromisoformat(e["event_at"])
            base = 0.30 if e["event_type"] == "snack" else 0.05
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

    def satiety_word(self, now: datetime) -> str:
        """Pro painel: "comendo", "satisfeita", "estufada" (vazio quando nada disso)."""
        e = self._ultima(now)
        meta = json.loads(e["metadata_json"] or "{}") if e else {}
        if not meta.get("fome_antes") and meta.get("fome_antes") != 0:
            return ""
        fim = datetime.fromisoformat(e["end_at"]) if e["end_at"] else None
        if fim and now < fim:
            return "comendo"
        if meta.get("excesso") and fim and now - fim < timedelta(hours=2):
            return "estufada"
        return ""

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
                snacks = conn.execute("SELECT COUNT(*) FROM life_events WHERE event_type='snack' AND event_at>=? "
                                      "AND COALESCE(metadata_json,'') NOT LIKE '%\"motivo\": \"fome\"%'",
                                      (since,)).fetchone()[0]
                excessos = sum(1 for (m,) in conn.execute(
                    "SELECT metadata_json FROM life_events WHERE event_type IN ('meal','snack') AND event_at>=? "
                    "AND metadata_json IS NOT NULL", (since,)) if json.loads(m).get("excesso"))
                gym = conn.execute(
                    "SELECT COUNT(DISTINCT substr(observed_at,1,10)) FROM world_state WHERE observed_at>=? AND "
                    "(activity LIKE '%academia%' OR activity LIKE '%trein%')", (since,)).fetchone()[0]
            rng = random.Random(f"marina-peso:{week}")
            delta = 0.12 * (snacks - 3) + 0.1 * excessos - 0.12 * (gym - 3) + rng.uniform(-0.2, 0.2)
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
        sac = self.satiety_word(now)
        if sac == "comendo":
            lines.append("- Você está comendo agora: a fome vai passando; satisfeita, você larga o prato (ou não, se "
                         "for dia de gula).")
        elif sac == "estufada":
            lines.append("- Você comeu além da conta e está estufada (\"comi demais kkk\").")
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
