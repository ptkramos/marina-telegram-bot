"""Persistência isolada do Living World. Não ativa o simulador nem altera a v3.5."""

import json
from datetime import date, datetime
from typing import Any, Mapping, Optional

from db import DatabaseManager


class CanonConflictError(ValueError):
    """Uma tentativa de seed mudaria um valor canônico já bloqueado."""


def _iso_now() -> str:
    return datetime.now().isoformat()


def _encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class WorldBibleRepository:
    """UPSERT idempotente do seed; dados locked não são reescritos em silêncio."""

    _SPECS = {
        "world_characters": (
            "canonical_key",
            ("display_name", "character_type", "birth_date", "home_region", "occupation",
             "relationship_to_marina", "personality_json", "story_tendencies_json",
             "initial_state_json", "canon_locked", "active"),
        ),
        "world_places": (
            "canonical_key",
            ("name", "region", "place_type", "truth_type", "familiarity", "distance_class",
             "associated_characters_json", "usage_rules_json", "canon_locked", "active"),
        ),
        "routine_patterns": (
            "canonical_key",
            ("character_key", "routine_type", "day_scope", "window_start", "window_end",
             "probability", "context_rules_json", "fallback_json", "canon_locked", "active"),
        ),
    }

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_character(self, canonical_key: str) -> Optional[dict]:
        return self._get("world_characters", canonical_key)

    def age_on(self, canonical_key: str, on_date: date) -> Optional[int]:
        character = self.get_character(canonical_key)
        if not character or not character["birth_date"]:
            return None
        born = date.fromisoformat(character["birth_date"])
        return on_date.year - born.year - ((on_date.month, on_date.day) < (born.month, born.day))

    def get_place(self, canonical_key: str) -> Optional[dict]:
        return self._get("world_places", canonical_key)

    def get_routine(self, canonical_key: str) -> Optional[dict]:
        return self._get("routine_patterns", canonical_key)

    def _get(self, table: str, key: str) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                f"SELECT * FROM {table} WHERE canonical_key = ?", (key,)
            ).fetchone()
            return dict(row) if row else None

    def upsert_character(self, key: str, values: Mapping[str, Any]) -> dict:
        return self._upsert("world_characters", key, values)

    def upsert_place(self, key: str, values: Mapping[str, Any]) -> dict:
        return self._upsert("world_places", key, values)

    def upsert_routine(self, key: str, values: Mapping[str, Any]) -> dict:
        return self._upsert("routine_patterns", key, values)

    def upsert_preference(
        self, character_key: str, category: str, value: str,
        preference_type: str = "core_like", *, strength: float = 1.0,
        confidence: float = 1.0, canon_locked: bool = True,
    ) -> dict:
        if not all((character_key, category, value, preference_type)):
            raise ValueError("Identidade, categoria, valor e tipo são obrigatórios")
        key = (character_key, category, value, preference_type)
        now = _iso_now()
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM character_preferences
                   WHERE character_key = ? AND category = ? AND value = ? AND preference_type = ?""",
                key,
            ).fetchone()
            if row:
                if row["canon_locked"] and (
                    row["strength"] != strength or row["confidence"] != confidence
                    or row["canon_locked"] != int(canon_locked)
                ):
                    raise CanonConflictError(f"Preferência canônica bloqueada: {key}")
                return dict(row)
            cursor = conn.execute(
                """INSERT INTO character_preferences
                   (character_key, category, value, preference_type, strength,
                    confidence, first_seen_at, last_seen_at, canon_locked)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*key, strength, confidence, now, now, int(canon_locked)),
            )
            return dict(conn.execute(
                "SELECT * FROM character_preferences WHERE id = ?", (cursor.lastrowid,)
            ).fetchone())

    def _upsert(self, table: str, key: str, values: Mapping[str, Any]) -> dict:
        if not key or not key.strip():
            raise ValueError("canonical_key obrigatório")
        key_field, allowed = self._SPECS[table]
        unknown = set(values) - set(allowed)
        if unknown:
            raise ValueError(f"Campos não permitidos: {sorted(unknown)}")
        payload = {
            column: _encoded(value) if column.endswith("_json") and value is not None else value
            for column, value in values.items()
        }
        now = _iso_now()
        with self.db.get_connection() as conn:
            row = conn.execute(
                f"SELECT * FROM {table} WHERE {key_field} = ?", (key,)
            ).fetchone()
            if row:
                changed = {column: value for column, value in payload.items() if row[column] != value}
                if changed and row["canon_locked"]:
                    raise CanonConflictError(f"Canon bloqueado: {key}")
                if changed:
                    assignments = ", ".join(f"{column} = ?" for column in changed)
                    params = list(changed.values())
                    if table in ("world_characters", "world_places"):
                        assignments += ", updated_at = ?"
                        params.append(now)
                    conn.execute(
                        f"UPDATE {table} SET {assignments} WHERE {key_field} = ?",
                        (*params, key),
                    )
            else:
                insert = {key_field: key, **payload}
                if table in ("world_characters", "world_places"):
                    insert.update(created_at=now, updated_at=now)
                columns = ", ".join(insert)
                marks = ", ".join("?" for _ in insert)
                conn.execute(
                    f"INSERT INTO {table} ({columns}) VALUES ({marks})",
                    tuple(insert.values()),
                )
            return dict(conn.execute(
                f"SELECT * FROM {table} WHERE {key_field} = ?", (key,)
            ).fetchone())


class WorldStateRepository:
    """Estado observado por timestamp; leitura sempre escolhe o mais recente."""

    _FIELDS = (
        "state_date", "observed_at", "location_place_id", "location_region", "activity",
        "energy_level", "social_drive", "stress_level", "physical_comfort",
        "weather_context_json", "active_people_json", "active_threads_json",
        "current_plan_json", "source_json",
    )

    def __init__(self, db: DatabaseManager):
        self.db = db

    def add_snapshot(self, values: Mapping[str, Any]) -> dict:
        if not values.get("state_date") or not values.get("observed_at"):
            raise ValueError("state_date e observed_at são obrigatórios")
        unknown = set(values) - set(self._FIELDS)
        if unknown:
            raise ValueError(f"Campos não permitidos: {sorted(unknown)}")
        payload = {
            column: _encoded(value) if column.endswith("_json") and value is not None else value
            for column, value in values.items()
        }
        columns = ", ".join(payload)
        marks = ", ".join("?" for _ in payload)
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                f"INSERT INTO world_state ({columns}) VALUES ({marks})",
                tuple(payload.values()),
            )
            return dict(conn.execute(
                "SELECT * FROM world_state WHERE id = ?", (cursor.lastrowid,)
            ).fetchone())

    def latest(self) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM world_state ORDER BY observed_at DESC, id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None
