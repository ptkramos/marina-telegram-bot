"""Refeições da Marina: o "vou jantar agora" que ela fala vira estado do mundo.

Soak de 22/09: ela prometeu comer seis vezes entre 21h14 e 22h31, seguiu
respondendo em 6 segundos e, quando o Patrick perguntou "já jantou?", só
conseguiu prometer de novo. A rotina não tinha refeição, e o que ela dizia que
ia fazer não mudava nada no mundo.

Agora, quando a fala dela anuncia uma refeição imediata, o mesmo mecanismo do
banho (C.3) entra em ação: `pending_transition_json` a leva para "jantando"
por 20 a 35 minutos, a disponibilidade deixa de ser instantânea, e o prato
vira acontecimento do dia ("seu dia até agora"), que ela pode contar depois.
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional

from db import DatabaseManager
from world_repository import WorldStateRepository

logger = logging.getLogger(__name__)

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
DURATION_MIN = (20, 35)
# Uma refeição por janela: repetir "vou jantar agora" não abre outro jantar.
SAME_MEAL_WINDOW = timedelta(hours=3)

# (nome da refeição, verbo no gerúndio, cardápio caseiro). O cardápio segue o
# cânone dela (massas, japonesa, pizza, hambúrguer), com o pé no chão de quem
# mora sozinha em Botafogo e cozinha pouco.
MEALS = {
    "almoco": ("almoço", "almoçando", [
        "arroz, feijão, frango grelhado e salada",
        "macarrão ao sugo que ela mesma fez",
        "um poke pedido no iFood",
        "sobra do jantar de ontem esquentada",
        "salada com frango desfiado",
    ]),
    "jantar": ("jantar", "jantando", [
        "omelete com queijo e tomate, preguiça de cozinhar",
        "macarrão ao sugo que sobrou do almoço",
        "yakisoba pedido no iFood",
        "pizza de marguerita pedida no iFood",
        "tapioca de queijo com presunto",
        "sanduíche natural com suco",
        "arroz, ovo frito e salada",
    ]),
    "lanche": ("lanche", "lanchando", [
        "pão de queijo com café",
        "iogurte com granola e banana",
        "torrada com requeijão",
    ]),
}


def meal_kind(now: datetime) -> str:
    if 11 <= now.hour < 15:
        return "almoco"
    if now.hour >= 18 or now.hour < 2:
        return "jantar"
    return "lanche"


def announces_meal(text: str) -> bool:
    return bool(MEAL_PROMISE_RE.search(text or ""))


class Meals:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def _recent_meal(self, now: datetime) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT event_at, summary FROM life_events WHERE event_type='meal'
                   AND event_at>=? ORDER BY event_at DESC LIMIT 1""",
                ((now - SAME_MEAL_WINDOW).isoformat(),)).fetchone()
        return dict(row) if row else None

    def _busy(self, now: datetime) -> bool:
        """Outra transição anunciada ainda valendo (banho, saída) tem prioridade."""
        raw = self.db.get_estado_relacional().get("pending_transition_json")
        if not raw:
            return False
        try:
            data = json.loads(raw)
            return datetime.fromisoformat(data["end_at"]) > now
        except (TypeError, ValueError, KeyError):
            return False

    def _at_home(self) -> bool:
        state = WorldStateRepository(self.db).latest()
        if not state:
            return True
        activity = (state.get("activity") or "").casefold()
        region = (state.get("location_region") or "").casefold()
        return not any(t in activity for t in ("dorm", "a caminho", "uber", "ônibus", "metrô", "carona")) \
            and "a caminho" not in region

    def observe_marina_line(self, text: str, now: datetime) -> Optional[dict]:
        """Chamado depois que a fala dela é entregue. Retorna o payload se abriu refeição."""
        if not announces_meal(text):
            return None
        if self._recent_meal(now) or self._busy(now) or not self._at_home():
            return None
        kind = meal_kind(now)
        name, gerund, menu = MEALS[kind]
        rng = random.Random(f"meal:{now.date().isoformat()}:{kind}")
        start = now + timedelta(minutes=rng.randint(*START_DELAY_MIN))
        end = start + timedelta(minutes=rng.randint(*DURATION_MIN))
        dish = rng.choice(menu)
        payload = {"routine_type": "meal", "activity": f"{gerund} em casa", "place_key": "marina_apartment",
                   "announced_at": now.isoformat(), "transition_at": start.isoformat(),
                   "end_at": end.isoformat(), "dish": dish}
        self.db.set_estado_relacional("pending_transition_json", json.dumps(payload, ensure_ascii=False))
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,
                   source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,?,?,?,'simulated',1,0.1,?,0.3,?)""",
                (f"meal:{now.date().isoformat()}:{kind}:{start.strftime('%H%M')}", start.isoformat(), "meal",
                 name, f"{name.capitalize()} em casa: {dish}.", json.dumps(["marina"]), now.isoformat()))
            conn.commit()
        logger.info("meal.announced kind=%s start=%s end=%s", kind,
                    start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"))
        return payload
