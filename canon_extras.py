"""Cânone acrescentado depois do seed travado (decisões do Patrick).

O seed da World Bible é travado por assinatura (mudar exige migração explícita),
e as migrations são só de esquema. Gente nova que o Patrick canoniza entra aqui:
idempotente, e só quando o mundo já foi semeado (a Marina existe).

24/09 (D9): a faxineira que o Henrique paga, toda quinta, e o porteiro do prédio
(libera a faxineira, recebe encomendas, rende história). Nomes escolhidos pelo
Claude; o Patrick pode trocar.
"""
from __future__ import annotations

import json

EXTRAS = {
    "neide_souza": {
        "display_name": "Dona Neide Souza", "character_type": "recurring", "birth_date": "1971-03-02",
        "home_region": "Rio de Janeiro, RJ", "occupation": "Diarista (paga pelo Henrique)",
        "relationship_to_marina": "faxineira do apê, vai toda quinta",
        "personality": {"caring": True, "talkative": True, "motherly": True},
        "tendencies": ["faxina de quinta", "acha coisa perdida", "deixa bilhete", "mima o Milo"],
        "initial": {"has_building_access_via_doorman": True, "comes_every_thursday": True},
        "relationship": ("household_help", 0.5, 0.8, "weekly"),
    },
    "jorge_almeida": {
        "display_name": "Seu Jorge Almeida", "character_type": "recurring", "birth_date": "1966-11-19",
        "home_region": "Rio de Janeiro, RJ", "occupation": "Porteiro do prédio da Marina",
        "relationship_to_marina": "porteiro do prédio",
        "personality": {"friendly": True, "gossipy": True, "protective": True},
        "tendencies": ["encomendas", "libera a faxineira", "fofoca do prédio", "Milo", "visitas"],
        "initial": {"receives_packages": True},
        "relationship": ("building_staff", 0.4, 0.7, "frequent"),
    },
}


def ensure(db) -> int:
    """Cria os personagens que faltam. Devolve quantos criou."""
    created = 0
    with db.get_connection() as conn:
        if not conn.execute("SELECT 1 FROM world_characters WHERE canonical_key='marina'").fetchone():
            return 0
        for key, c in EXTRAS.items():
            cur = conn.execute(
                """INSERT OR IGNORE INTO world_characters
                   (canonical_key, display_name, character_type, birth_date, home_region, occupation,
                    relationship_to_marina, personality_json, story_tendencies_json, initial_state_json,
                    canon_locked, active, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,1,1,'2026-09-24T00:00:00','2026-09-24T00:00:00')""",
                (key, c["display_name"], c["character_type"], c["birth_date"], c["home_region"], c["occupation"],
                 c["relationship_to_marina"], json.dumps(c["personality"], ensure_ascii=False),
                 json.dumps(c["tendencies"], ensure_ascii=False), json.dumps(c["initial"], ensure_ascii=False)))
            created += cur.rowcount or 0
            rel, closeness, trust, freq = c["relationship"]
            conn.execute(
                """INSERT OR IGNORE INTO social_relationships
                   (character_key, relationship_type, canon_locked, closeness, trust, contact_frequency,
                    recent_tension, recent_positive_interactions, last_interaction_at)
                   VALUES (?,?,1,?,?,?,0.0,0,NULL)""", (key, rel, closeness, trust, freq))
        conn.commit()
    return created
