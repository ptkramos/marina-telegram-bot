"""Patch 013 — Data migration: opening_hours canônicas para lugares externos.

Executar UMA vez após deploy do código. Atualiza `usage_rules_json` do Bodytech
São Clemente com horário de funcionamento oficial, permitindo que o
RoutineEngine filtre sorteios de gym fora do horário.

Uso:
    python apply_patch_013.py

Idempotente: se o horário já estiver aplicado, apenas confirma e sai.
"""
from __future__ import annotations

import json
import sys

from db import db_manager


BODYTECH_OPENING_HOURS = {
    "mon": "06:00-22:00",
    "tue": "06:00-22:00",
    "wed": "06:00-22:00",
    "thu": "06:00-22:00",
    "fri": "06:00-22:00",
    "sat": "08:00-18:00",
    "sun": "09:00-14:00",
}


def apply() -> int:
    with db_manager.get_connection() as conn:
        row = conn.execute(
            "SELECT id, usage_rules_json FROM world_places WHERE canonical_key = ?",
            ("bodytech_sao_clemente",),
        ).fetchone()
        if not row:
            print("ERRO: place 'bodytech_sao_clemente' não encontrado. Rode o seed antes.")
            return 1
        try:
            rules = json.loads(row["usage_rules_json"] or "{}")
        except (TypeError, ValueError):
            rules = {}
        existing = rules.get("opening_hours")
        if existing == BODYTECH_OPENING_HOURS:
            print("OK: opening_hours já canonizado, nada a fazer.")
            return 0
        rules["opening_hours"] = BODYTECH_OPENING_HOURS
        conn.execute(
            "UPDATE world_places SET usage_rules_json = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (json.dumps(rules, ensure_ascii=False), row["id"]),
        )
        conn.commit()
    print("OK: opening_hours da Bodytech São Clemente aplicadas.")
    print(json.dumps(BODYTECH_OPENING_HOURS, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(apply())
