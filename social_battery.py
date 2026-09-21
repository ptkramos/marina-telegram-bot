"""Bateria social da Marina (Auditoria #5, desenho aprovado pelo Patrick em 21/09).

Bateria social = energia pra GENTE e pra agito, não energia pro Patrick.

- Gasta com o dia real dela: aula na PUC, compromisso fora (amigas, evento,
  casting). O dia vem da mesma agenda da Auditoria #4, nunca de sorteio.
- Recarrega sozinha em casa, passeando com o Milo e, principalmente, dormindo.
- Com o Patrick depende do TIPO da conversa, nunca do tamanho: o planner manda
  `emotional_deltas.social_battery` (leve/carinhosa recarrega um pouco; briga,
  DR ou cobrança gasta um pouco). Horas de conversa boa nunca a esvaziam.

A integração é preguiçosa: cada `WorldStateManager.resolve()` credita o tempo
decorrido desde a última conta, amostrando a agenda em passos de 15 min. Um
silêncio de 10h durante a noite conta como sono, não como "o último estado".
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from db import DatabaseManager

logger = logging.getLogger("SocialBattery")

ACCRUED_AT_KEY = "social_battery_accrued_at"
STEP = timedelta(minutes=15)
MAX_GAP = timedelta(hours=24)

# Variação por hora em cada tipo de momento.
RATE_PER_HOUR = {
    "SLEEPING": +0.09,   # uma noite de sono recarrega quase tudo
    "HOME": +0.04,
    "WAKING": +0.04,
    "PET_WALK": +0.04,   # sozinha com o Milo também é recarga
    "GYM": 0.0,
    "CLASS": -0.08,      # 7h–15h na PUC: cheia → ~0,36 ao chegar em casa
    "SOCIAL": -0.10,     # rolê, evento, casting
}


def _kind_at(db: DatabaseManager, moment: datetime) -> str:
    """Tipo do momento pela agenda — sem gravar snapshot."""
    from calendar_world import CalendarWorld
    from academic_life import AcademicLife
    from world_state import RoutineEngine

    commitment = CalendarWorld(db).current(moment, include_academic=True)
    if commitment:
        if commitment.get("academic_block_id") or "faculdade" in (commitment.get("activity") or ""):
            return "CLASS"
        return "HOME" if commitment.get("place_key") == "marina_apartment" else "SOCIAL"
    engine = RoutineEngine(db)
    has_class = bool(AcademicLife(db).blocks_on(moment.date()))
    chosen, _ = engine.pick(moment, engine.candidates(moment, has_class=has_class), has_class=has_class)
    return {
        "sleep": "SLEEPING", "wake": "WAKING", "pet_walk": "PET_WALK",
        "gym": "GYM", "gym_indoor": "GYM",
    }.get(chosen.routine_type, "HOME")


def accrue(db: DatabaseManager, now: datetime) -> Optional[float]:
    """Credita/debita a bateria pelo tempo desde a última conta. Idempotente."""
    raw = db.get_estado_relacional(ACCRUED_AT_KEY)
    if not raw:
        db.set_estado_relacional(ACCRUED_AT_KEY, now.isoformat())
        return None
    try:
        since = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        db.set_estado_relacional(ACCRUED_AT_KEY, now.isoformat())
        return None
    if now - since < STEP:
        return None
    since = max(since, now - MAX_GAP)
    start = float(db.get_estado_emocional(now=now).get("social_battery", {}).get("valor", 0.9))
    value = start
    t = since
    while t + STEP <= now:
        # Clamp a cada passo: uma noite não "recarrega além de 100%" para
        # compensar a aula do dia seguinte numa conta de intervalo longo.
        rate = RATE_PER_HOUR[_kind_at(db, t + STEP / 2)]
        value = max(0.0, min(1.0, value + rate * (STEP.total_seconds() / 3600)))
        t += STEP
    delta = value - start
    if abs(delta) > 1e-9:
        # Sem retorno decrescente: é consumo/recarga física, não empurrão emocional.
        db.ajustar_emocao("social_battery", delta, now=now, soft_edges=False)
    db.set_estado_relacional(ACCRUED_AT_KEY, t.isoformat())
    return delta
