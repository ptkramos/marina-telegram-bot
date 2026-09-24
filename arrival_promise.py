"""Promessa de avisar quando chegar (feedback do Patrick, 23/09).

Ela disse "te aviso assim que chegar no shopping, prometo" e não avisou; ele
cobrou 45 min depois ("esqueceu de avisar né"). O bot não tinha como cumprir:
a fala virava texto e mais nada. Agora a promessa vira um lembrete dela,
amarrado ao trajeto real do mundo (commute.py): quando a perna termina, ela
avisa com a própria voz. Às vezes esquece — gente esquece —, mas o normal é
cumprir.

Nada aqui chama LLM ou rede.
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta
from typing import Optional

KEY = "arrival_promise_json"
# 24/09 (Patrick): 12% era muito — ela é carinhosa, ama o namorado e é nova demais pra esquecer
# assim. 5%, e nunca duas vezes na mesma semana (levou bronca, fica esperta).
FORGET_CHANCE = 0.05
FORGOT_KEY = "arrival_promise_forgot_at"
NO_FORGET_AFTER = timedelta(days=7)
LATE_MIN = (2, 6)                 # tira o sapato, larga a bolsa, aí avisa
LOOKAHEAD = timedelta(minutes=90)  # perna que ainda vai começar

_PROMISE_RE = re.compile(r"\b(?:te\s+)?aviso\b|\bte\s+(?:mando|dou)\s+(?:um\s+)?(?:sinal|not[ií]cia)", re.I)
_ARRIVE_RE = re.compile(r"\bcheg(?:ar|o|ue|uei|ando)\b", re.I)
_HOME_RE = re.compile(r"\b(?:casa|ap[eê]|apartamento)\b", re.I)
_ARRIVED_RE = re.compile(r"\bcheguei\b", re.I)


def observe(db, her_line: str, his_last: str, now: Optional[datetime] = None) -> Optional[dict]:
    """Se a fala dela promete avisar a chegada, amarra a promessa ao trajeto real."""
    now = now or datetime.now()
    text = her_line or ""
    if not _PROMISE_RE.search(text) or not (_ARRIVE_RE.search(text) or _ARRIVE_RE.search(his_last or "")):
        return None
    leg = _target_leg(db, now, home=bool(_HOME_RE.search(text) or _HOME_RE.search(his_last or "")))
    if leg is None:
        return None
    rng = random.Random(f"aviso:{leg.key}")
    where = "em casa" if leg.direction == "volta" else leg.destination.replace("pra ", "na ").replace("pro ", "no ")
    promise = {"made_at": now.isoformat(), "leg": leg.key,
               "due_at": (leg.end + timedelta(minutes=rng.randint(*LATE_MIN))).isoformat(),
               "where": where, "forget": rng.random() < FORGET_CHANCE}
    db.set_estado_relacional(KEY, json.dumps(promise, ensure_ascii=False))
    return promise


def _target_leg(db, now: datetime, *, home: bool):
    try:
        from commute import Commute
        legs = []
        c = Commute(db)
        for day in (now.date() - timedelta(days=1), now.date()):
            legs += c.legs_on(day)
    except Exception:
        return None
    live = [leg for leg in legs if leg.end > now and leg.start <= now + LOOKAHEAD]
    if home:
        live = [leg for leg in live if leg.direction == "volta"] or live
    return min(live, key=lambda leg: leg.end) if live else None


def _forgot_recently(db, now: datetime) -> bool:
    raw = db.get_estado_relacional(FORGOT_KEY)
    try:
        return bool(raw) and now - datetime.fromisoformat(raw) < NO_FORGET_AFTER
    except (TypeError, ValueError):
        return False


def due(db, now: Optional[datetime] = None) -> Optional[dict]:
    """A promessa venceu e ela ainda não avisou? Devolve e limpa (uma vez só)."""
    now = now or datetime.now()
    raw = db.get_estado_relacional(KEY)
    if not raw:
        return None
    try:
        promise = json.loads(raw)
        due_at = datetime.fromisoformat(promise["due_at"])
    except (TypeError, ValueError, KeyError):
        db.set_estado_relacional(KEY, "")
        return None
    if now < due_at:
        return None
    db.set_estado_relacional(KEY, "")
    if now - due_at > timedelta(hours=2):
        return None   # já passou muito
    if promise.get("forget") and not _forgot_recently(db, now):
        db.set_estado_relacional(FORGOT_KEY, now.isoformat())
        return None   # esqueceu (às vezes acontece)
    with db.get_connection() as conn:
        rows = conn.execute("SELECT content FROM conversas WHERE role='assistant' AND timestamp>?",
                            (promise["made_at"],)).fetchall()
    if any(_ARRIVED_RE.search(r["content"] or "") for r in rows):
        return None   # já contou na conversa que chegou
    return promise
