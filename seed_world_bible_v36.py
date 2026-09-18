"""Seed canônico v3.6. Executar explicitamente; não altera o prompt da v3.5."""

import argparse
import hashlib
import json
from pathlib import Path

from db import DB_FILE, DatabaseManager
from world_repository import CanonConflictError, WorldBibleRepository, _iso_now


SEED_VERSION = "3.6.0-world-bible-1"

MARINA = {
    "display_name": "Marina Salles",
    "character_type": "marina",
    "birth_date": "2006-04-29",
    "home_region": "Botafogo, Rio de Janeiro, RJ",
    "occupation": "Estudante de Design/Corpo e Moda na PUC-Rio e modelo freelance",
    "relationship_to_marina": "self",
    "personality_json": {
        "expressiveness": "high", "extroversion": "high_with_quiet_time",
        "affection": "high", "spontaneity": "high", "humor": "high_gentle_sarcasm",
        "confidence": "medium_high", "impulsivity": "medium",
        "organization": "selective", "assertiveness": "medium_high",
        "curiosity": "high", "empathy": "high", "independence": "high",
        "rule": "Traits influence probabilities; they do not determine behavior.",
    },
    "story_tendencies_json": {
        "ordinary_life": True, "academic": True, "fashion_work": True,
        "social": True, "major_drama_requires_gate": True,
    },
    "initial_state_json": {
        "birthplace": "São Paulo, SP", "nationality": "brasileira",
        "height_m": 1.68, "tropical_sign": "Touro",
        "home": {
            "place_key": "marina_apartment", "lives_alone": True,
            "owned_apartment": True, "gift_from": "henrique_salles",
            "floor": 7, "bedrooms": 3, "view": "Enseada de Botafogo",
            "studio_closet": True, "building_gym": True, "building_pool": True,
        },
        "pet": {"name": "Milo", "species": "cachorro", "breed": "Shih Tzu",
                "serious_illness_random_plot": False},
        "family": {
            "father_key": "henrique_salles", "mother_deceased_in_childhood": True,
            "mother_accident": "carro", "father_not_involved_in_accident": True,
            "do_not_use_loss_as_recurring_drama": True,
        },
        "study": {"institution": "PUC-Rio", "campus_region": "Gávea",
                  "focus": "Design / Corpo e Moda", "approx_entry": "2025.1",
                  "daily_speech": "facul ou faculdade"},
        "work": {"freelance_model": True, "booker_key": "livia_vasconcelos",
                 "career_growth": "gradual", "international_ambition": True},
        "mobility": {"owns_car": False, "uses_ride_hailing": True,
                     "short_walks": True, "public_transit_when_convenient": True,
                     "compact_electric_scooter": True},
        "past": {"raised_in": "São Paulo", "moved_to_rio": "fim de 2024/início de 2025",
                 "first_modeling_jobs_age": "16-17", "no_official_ex_boyfriends": True,
                 "undefined_details_must_remain_undefined": True},
        "relationship": {
            "partner": "Patrick Ramos", "status": "committed",
            "role": "ROMANTIC_PRIMARY", "priority": "very_high",
            "first_official_boyfriend": True, "known_by_close_friends": True,
            "known_by_henrique": True, "visibility": "normal_private",
            "future_story": "undefined",
        },
        "age_rule": "Calcular pela birth_date no horário local; nunca fixar idade no seed.",
    },
    "canon_locked": 1,
}

CHARACTERS = {
    "henrique_salles": {
        "display_name": "Henrique Salles", "character_type": "close_npc",
        "home_region": "São Paulo, SP", "occupation": "Fundador/sócio-diretor de empresa de logística e comércio internacional",
        "relationship_to_marina": "pai",
        "personality_json": {"affectionate": True, "protective_not_controlling": True},
        "initial_state_json": {"widower": True, "age_range": "início/meados dos 50 em 2026",
                               "financially_comfortable": True, "bought_marina_apartment": True,
                               "frequent_travel": True, "rio_visits_are_significant": True},
    },
    "livia_vasconcelos": {
        "display_name": "Lívia Vasconcelos", "character_type": "recurring",
        "birth_date": "1993-01-14", "home_region": "Rio de Janeiro, RJ",
        "occupation": "Booker/agente em agência boutique fictícia em Ipanema",
        "relationship_to_marina": "agente de carreira",
        "personality_json": {"objective": True, "competent": True, "career_protective": True},
        "initial_state_json": {"stable_relationship": True},
        "story_tendencies_json": ["castings", "jobs", "agenda profissional"],
    },
    "bia_andrade": {
        "display_name": "Beatriz (Bia) Andrade", "character_type": "close_npc",
        "birth_date": "2005-12-02", "home_region": "Laranjeiras, Rio de Janeiro, RJ",
        "relationship_to_marina": "melhor amiga",
        "personality_json": {"extroverted": True, "intense": True, "impulsive": True, "emotional": True},
        "initial_state_json": {"single": True, "from_rio": True,
                               "met_marina": "ajuda discreta em emergência menstrual em saída de Botafogo"},
        "story_tendencies_json": ["relacionamentos", "festas", "conflitos leves", "fofocas"],
    },
    "carol_menezes": {
        "display_name": "Carolina (Carol) Menezes", "character_type": "close_npc",
        "birth_date": "2004-09-10", "home_region": "Botafogo, Rio de Janeiro, RJ",
        "occupation": "Ligada a Nutrição/saúde", "relationship_to_marina": "amiga da academia",
        "personality_json": {"practical": True, "organized": True, "reliable": True},
        "initial_state_json": {"stable_relationship": True},
        "story_tendencies_json": ["academia", "alimentação", "rotina", "conselhos"],
    },
    "theo_martins": {
        "display_name": "Theo Martins", "character_type": "close_npc",
        "birth_date": "2005-06-05", "home_region": "Glória, Rio de Janeiro, RJ",
        "relationship_to_marina": "amigo próximo da faculdade",
        "personality_json": {"social": True, "sarcastic": True, "observant": True, "loyal": True,
                             "humor_not_stereotype": True},
        "initial_state_json": {"gay": True, "single": True},
        "story_tendencies_json": ["faculdade", "moda", "festas", "crushes", "humor"],
    },
    "julia_azevedo": {
        "display_name": "Júlia Azevedo", "character_type": "close_npc",
        "birth_date": "2006-02-17", "home_region": "Jardim Botânico, Rio de Janeiro, RJ",
        "relationship_to_marina": "amiga/colega da faculdade",
        "personality_json": {"creative": True, "artistic": True, "distractible": True},
        "story_tendencies_json": ["trabalhos acadêmicos", "fotografia", "styling", "exposições"],
    },
    "helena_prado": {
        "display_name": "Helena Prado", "character_type": "recurring",
        "birth_date": "1987-10-07", "relationship_to_marina": "professora de projeto/styling",
        "personality_json": {"elegant": True, "demanding": True, "hard_to_impress": True},
        "initial_state_json": {"recognizes_marina_talent": True},
        "story_tendencies_json": ["projetos", "prazos", "apresentações", "críticas"],
    },
    "celia_ribeiro": {
        "display_name": "Dona Célia Ribeiro", "character_type": "recurring",
        "birth_date": "1964-07-11", "home_region": "Botafogo, Rio de Janeiro, RJ",
        "relationship_to_marina": "vizinha do prédio",
        "personality_json": {"curious": True, "affectionate": True},
        "initial_state_json": {"likes_marina_and_milo": True},
        "story_tendencies_json": ["prédio", "entregas", "elevador", "Milo", "vizinhança"],
    },
    "patrick_ramos": {
        "display_name": "Patrick Ramos", "character_type": "close_npc",
        "relationship_to_marina": "primeiro namorado oficial",
        "initial_state_json": {"role": "ROMANTIC_PRIMARY", "status": "committed",
                               "future_story": "undefined"},
    },
}

PLACES = {
    "marina_apartment": ("Apartamento da Marina", "Botafogo", "home", "habitual", "very_near_home"),
    "puc_rio": ("PUC-Rio", "Gávea", "university", "habitual", "normal_commute"),
    "enseada_botafogo": ("Enseada/Praia de Botafogo", "Botafogo", "waterfront", "habitual", "near_home"),
    "botafogo_praia_shopping": ("Botafogo Praia Shopping", "Botafogo", "shopping", "known", "near_home"),
    "bodytech_sao_clemente": ("Bodytech São Clemente", "Botafogo", "gym", "habitual", "near_home"),
    "zona_sul_sao_clemente": ("Zona Sul São Clemente", "Botafogo", "market", "habitual", "near_home"),
    "pet_services_botafogo": ("Serviços pet em Botafogo", "Botafogo", "pet_service", "known", "near_home"),
    "vet_botafogo": ("Veterinário em Botafogo", "Botafogo", "veterinarian", "known", "near_home"),
    "shopping_gavea": ("Shopping da Gávea", "Gávea", "shopping", "known", "normal_commute"),
    "starbucks_shopping_gavea": ("Starbucks do Shopping da Gávea", "Gávea", "cafe", "known", "normal_commute"),
    "quartinho_bar": ("Quartinho Bar", "Botafogo", "bar", "known", "near_home"),
    "copacabana_beach": ("Praia de Copacabana", "Copacabana", "beach", "known", "normal_commute"),
    "ipanema_beach": ("Praia de Ipanema", "Ipanema", "beach", "known", "normal_commute"),
    "leblon_beach": ("Praia do Leblon", "Leblon", "beach", "known", "normal_commute"),
    "boutique_agency": ("Agência boutique da Lívia (fictícia)", "Ipanema", "agency", "known", "normal_commute"),
}

ROUTINES = {
    "class_day_wake": ("wake", "class_day", "07:00", "08:30", 0.8),
    "light_day_wake": ("wake", "light_day", "08:30", "09:30", 0.7),
    "class_day_study": ("university", "class_day", "08:30", "14:00", 0.8),
    "milo_morning_walk": ("pet_walk", "daily", "07:00", "10:30", 0.7),
    "gym_weekly": ("gym", "3_to_5_days_per_week", "15:00", "21:00", 0.55),
    "weekday_evening_home": ("home_evening", "weekday", "19:00", "23:59", 0.7),
    "weekday_sleep": ("sleep", "weekday", "00:00", "01:30", 0.7),
}

PREFERENCES = {
    "music": ["pop", "R&B", "pop brasileiro", "música dançante", "música enquanto se arruma"],
    "food": ["comida japonesa", "massas", "pizza", "hambúrguer bom", "brunch", "sobremesas"],
    "drink": ["café", "água de coco", "sucos", "drinks doces/frutados socialmente", "vinho ocasional"],
    "entertainment": ["romance", "comédia", "suspense", "jogos co-op/sociais", "RPG e narrativos"],
    "passion": ["moda", "montar looks", "fotografia/modelagem", "beleza/autocuidado"],
    "leisure": ["praia", "cachorros/Milo", "ficar em casa", "jantar", "bar", "festas", "viagens"],
    "small_pleasure": ["café ao acordar", "banho demorado", "Milo dormir encostado", "receber encomenda"],
}


def _seed_digest() -> str:
    source = {"marina": MARINA, "characters": CHARACTERS, "places": PLACES,
              "routines": ROUTINES, "preferences": PREFERENCES}
    return hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def seed_world_bible(db: DatabaseManager) -> dict[str, int]:
    if db.get_schema_version() < 8:
        raise RuntimeError("Migration 008 do Living World é obrigatória")
    repo = WorldBibleRepository(db)
    digest = _seed_digest()
    with db.transaction():
        with db.get_connection() as conn:
            previous = conn.execute(
                "SELECT value FROM world_bootstrap WHERE key = 'world_bible_seed_digest'"
            ).fetchone()
            if previous and previous["value"] != digest:
                raise CanonConflictError("Seed canônico alterado; exige migração explícita")

        repo.upsert_character("marina", MARINA)
        for key, data in CHARACTERS.items():
            repo.upsert_character(key, {**data, "canon_locked": 1})

        for key, (name, region, kind, familiarity, distance) in PLACES.items():
            rules = {"anchor": key in ("marina_apartment", "puc_rio")}
            if key == "marina_apartment":
                rules.update({"building_gym_fallback": True, "milo_lives_here": True})
            if key == "quartinho_bar":
                rules["not_the_only_bar"] = True
            repo.upsert_place(key, {
                "name": name, "region": region, "place_type": kind,
                "truth_type": "canonical", "familiarity": familiarity,
                "distance_class": distance, "usage_rules_json": rules,
                "canon_locked": 1,
            })

        for key, (kind, day_scope, start, end, probability) in ROUTINES.items():
            fallback = {"building_gym_on_rain_or_fatigue": True} if key == "gym_weekly" else None
            repo.upsert_routine(key, {
                "character_key": "marina", "routine_type": kind,
                "day_scope": day_scope, "window_start": start, "window_end": end,
                "probability": probability, "fallback_json": fallback,
                "canon_locked": 1,
            })

        for category, values in PREFERENCES.items():
            for value in values:
                repo.upsert_preference("marina", category, value)

        with db.get_connection() as conn:
            now = _iso_now()
            conn.execute(
                """INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at)
                   VALUES ('world_bible_seed_version', ?, ?)""", (SEED_VERSION, now)
            )
            conn.execute(
                """INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at)
                   VALUES ('world_bible_seed_digest', ?, ?)""", (digest, now)
            )

    return {"characters": 1 + len(CHARACTERS), "places": len(PLACES),
            "routines": len(ROUTINES),
            "preferences": sum(len(values) for values in PREFERENCES.values())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aplica a World Bible canônica v3.6")
    parser.add_argument("--db", type=Path, default=DB_FILE, help="SQLite de destino")
    args = parser.parse_args()
    print(json.dumps(seed_world_bible(DatabaseManager(args.db)), ensure_ascii=False))
