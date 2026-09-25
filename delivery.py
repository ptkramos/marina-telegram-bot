"""Delivery de verdade (24/09, conversa das 19h): "vou pedir pelo iFood" virava só fala.

Ela prometeu mandar foto do açaí quando chegasse, disse "ainda não chegou" e depois
"chegou" — tudo inventado na hora pelo modelo, e o /status nunca mostrou ela comendo.
Agora o pedido vira estado: hora do pedido, previsão de chegada (30–55 min); quando
chega, o Seu Jorge interfona, vira acontecimento do dia e ela passa a estar comendo.
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "delivery_json"
ETA_MIN = (30, 55)
EAT_MIN = (15, 30)
SHOW_AFTER_ARRIVAL = timedelta(hours=2)

_FOOD = r"(a[cç]a[ií]|pizza|hamb[uú]rguer|burger|sushi|japa|temaki|lanche|comida|poke|salada|pastel|esfiha)"
ORDER_RE = re.compile(
    r"\b(vou pedir|j[aá] pedi|acabei de pedir|pedi|t[oô] pedindo|vou pegar)\b[^.!?\n]{0,40}?"
    r"\b(ifood|delivery|rappi|" + _FOOD[1:-1] + r")\b",
    re.IGNORECASE)
FOOD_RE = re.compile(r"\b" + _FOOD + r"\b", re.IGNORECASE)


def _load(db) -> Optional[dict]:
    try:
        raw = db.get_estado_relacional(KEY)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _save(db, data: dict) -> None:
    db.set_estado_relacional(KEY, json.dumps(data, ensure_ascii=False))


def _what(text: str, fallback: str = "o pedido") -> str:
    m = FOOD_RE.search(text or "")
    return m.group(1).lower() if m else fallback


def observe(db, text: str, now: datetime, context: str = "") -> bool:
    """Fala dela ('vou pedir pelo iFood'): abre um pedido. context = conversa recente, pra achar o quê."""
    if not ORDER_RE.search(text or ""):
        return False
    cur = _load(db)
    if cur and not cur.get("arrived_at"):
        return False                                   # já tem pedido a caminho
    rng = random.Random(f"delivery:{now.isoformat(timespec='minutes')}")
    what = _what(text, _what(context, "o pedido"))
    eta = now + timedelta(minutes=rng.randint(*ETA_MIN))
    _save(db, {"what": what, "ordered_at": now.isoformat(), "eta_at": eta.isoformat(), "arrived_at": None})
    logger.info("delivery.ordered what=%s eta=%s", what, eta.isoformat(timespec="minutes"))
    return True


def materialize(db, now: datetime) -> bool:
    """Chegou a hora: o pedido chega (acontecimento do dia) e ela passa a comer."""
    cur = _load(db)
    if not cur or cur.get("arrived_at"):
        return False
    eta = datetime.fromisoformat(cur["eta_at"])
    if eta > now:
        return False
    cur["arrived_at"] = eta.isoformat()
    _save(db, cur)
    what = cur["what"]
    from meals import meal_kind
    # Vira A refeição do horário (o açaí das 19:55 é o jantar): a fome zera e o jantar
    # planejado do dia não sai em dobro (Meals pula tipo já registrado).
    with db.get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
               autonomy_level,importance,participants_json,share_worthy,created_at)
               VALUES (?,?,'meal','delivery',?,'simulated',1,0.2,?,0.5,?)""",
            (f"meal:{eta.date().isoformat()}:{meal_kind(eta)}:delivery", eta.isoformat(),
             f"O {what} do delivery chegou (o Seu Jorge interfonou) e ela foi comer.",
             json.dumps(["marina", "jorge_almeida"]), now.isoformat()))
        conn.commit()
    end = eta + timedelta(minutes=random.Random(cur["ordered_at"]).randint(*EAT_MIN))
    if end > now:
        raw = db.get_estado_relacional().get("pending_transition_json")
        busy = False
        try:
            busy = bool(raw) and datetime.fromisoformat(json.loads(raw)["end_at"]) > now
        except Exception:
            busy = False
        if not busy:
            db.set_estado_relacional("pending_transition_json", json.dumps({
                "routine_type": "meal", "activity": f"comendo o {what} em casa", "place_key": "marina_apartment",
                "announced_at": now.isoformat(), "transition_at": eta.isoformat(), "end_at": end.isoformat(),
                "dish": what}, ensure_ascii=False))
    logger.info("delivery.arrived what=%s at=%s", what, eta.isoformat(timespec="minutes"))
    return True


def prompt_lines(db, now: datetime) -> list[str]:
    cur = _load(db)
    if not cur:
        return []
    ordered = datetime.fromisoformat(cur["ordered_at"])
    if cur.get("arrived_at"):
        arrived = datetime.fromisoformat(cur["arrived_at"])
        if now - arrived > SHOW_AFTER_ARRIVAL:
            return []
        return [f"[DELIVERY] O {cur['what']} que você pediu chegou às {arrived:%H:%M}."]
    eta = datetime.fromisoformat(cur["eta_at"])
    return [f"[DELIVERY] Você pediu {cur['what']} às {ordered:%H:%M}; ainda não chegou "
            f"(o app diz que chega lá pelas {eta:%H:%M})."]
