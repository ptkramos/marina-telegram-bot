"""O que mudou desde a última mensagem dela pro Patrick (24/09).

O caso: às 16:10 ela falou do Starbucks com a Júlia; o café acabou às 16:45,
ela voltou de metrô e chegou em casa às 17:25. Às 18:11 ele perguntou se ela
se divertiu e ela respondeu "ainda tô aqui com a Júlia" — o mundo tinha andado
em silêncio e o prompt não dizia isso, então o modelo continuou a história de
onde a conversa parou.

Este bloco conta, no prompt, o que aconteceu de verdade entre a última fala
dela e agora (trajetos concluídos, acontecimentos do dia) e onde ela está
AGORA. Nada aqui chama LLM ou rede.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

MIN_GAP = timedelta(minutes=20)   # conversa corrida: nada mudou de verdade
MAX_ITEMS = 8


def _last_her_message(db) -> Optional[datetime]:
    with db.get_connection() as conn:
        row = conn.execute("SELECT timestamp FROM conversas WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()
    try:
        return datetime.fromisoformat(row["timestamp"]) if row else None
    except (TypeError, ValueError):
        return None


def _legs(db, since: datetime, now: datetime) -> list[tuple[datetime, str]]:
    items = []
    try:
        from commute import Commute
        c = Commute(db)
        days = {since.date(), now.date()}
        for day in sorted(days):
            for leg in c.legs_on(day):
                if since < leg.end <= now:
                    verbo = "chegou em casa" if leg.direction == "volta" else f"chegou {leg.destination.replace('pra ', 'na ').replace('pro ', 'no ')}"
                    items.append((leg.end, f"{verbo} ({leg.how}, saiu às {leg.start:%H:%M})"))
                elif leg.start <= now < leg.end and leg.start > since:
                    items.append((leg.start, f"saiu, agora {leg.activity(now)}"))
    except Exception:
        pass
    return items


def _events(db, since: datetime, now: datetime) -> list[tuple[datetime, str]]:
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT event_at, summary FROM life_events WHERE event_at>? AND event_at<=? ORDER BY event_at",
            (since.isoformat(), now.isoformat())).fetchall()
    out = []
    for r in rows:
        try:
            out.append((datetime.fromisoformat(r["event_at"]), (r["summary"] or "").strip().rstrip(".")))
        except (TypeError, ValueError):
            continue
    return [x for x in out if x[1]]


def _now_activity(db, now: datetime) -> str:
    try:
        from world_state import WorldStateManager
        return (WorldStateManager(db).resolve(now) or {}).get("activity") or ""
    except Exception:
        return ""


def prompt_lines(db, now: Optional[datetime] = None) -> list[str]:
    now = now or datetime.now()
    last = _last_her_message(db)
    if not last or now - last < MIN_GAP:
        return []
    items = sorted(_legs(db, last, now) + _events(db, last, now), key=lambda x: x[0])
    agora = _now_activity(db, now)
    if not items and not agora:
        return []
    lines = [f"[DESDE A SUA ÚLTIMA MENSAGEM PRO PATRICK (às {last:%H:%M}) — aconteceu de verdade]"]
    for at, text in items[-MAX_ITEMS:]:
        lines.append(f"- {at:%H:%M} — {text}")
    if agora:
        lines.append(f"- AGORA você está: {agora}.")
    lines.append("O que você disse antes pode ter ficado velho (se estava num lugar, já saiu). Fale a partir "
                 "de agora; se ele perguntar do que passou, conte pelos fatos acima.")
    return lines
