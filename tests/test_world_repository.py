"""Primeira etapa da v3.6: schema e repositórios em SQLite temporário."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from db import DatabaseManager
from world_repository import CanonConflictError, WorldBibleRepository, WorldStateRepository


class TestLivingWorldStorage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "world_test.db")
        self.bible = WorldBibleRepository(self.db)
        self.state = WorldStateRepository(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_schema_is_complete_and_repeatable_without_touching_legacy_rows(self):
        expected = {
            "world_characters", "world_places", "world_state", "life_events",
            "story_threads", "knowledge_items", "knowledge_shares",
            "knowledge_subjects", "knowledge_subject_aliases", "real_context_cache",
            "character_preferences", "routine_patterns", "world_decisions",
            "world_bootstrap", "academic_profile", "academic_terms",
            "academic_courses", "academic_schedule_blocks",
        }
        with self.db.get_connection() as conn:
            actual = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )}
            self.assertTrue(expected <= actual)
            legacy_count = conn.execute("SELECT COUNT(*) FROM perfil").fetchone()[0]
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.db.get_schema_version(), 23)
        DatabaseManager(self.db.db_path)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM perfil").fetchone()[0], legacy_count)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM world_characters").fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM schema_version WHERE version = 8"
            ).fetchone()[0], 1)

    def test_canonical_upserts_are_idempotent_and_locked(self):
        character = {
            "display_name": "Marina Salles", "character_type": "marina",
            "birth_date": "2006-04-29", "personality_json": {"warm": True},
            "canon_locked": 1,
        }
        first = self.bible.upsert_character("marina", character)
        second = self.bible.upsert_character("marina", character)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(json.loads(first["personality_json"]), {"warm": True})
        with self.assertRaises(CanonConflictError):
            self.bible.upsert_character("marina", {"display_name": "Outro nome"})
        self.assertEqual(self.bible.get_character("marina")["display_name"], "Marina Salles")

        place = {"name": "Casa", "region": "Botafogo", "place_type": "home",
                 "truth_type": "canonical", "familiarity": "habitual", "canon_locked": 1}
        self.assertEqual(
            self.bible.upsert_place("home", place)["id"],
            self.bible.upsert_place("home", place)["id"],
        )
        with self.assertRaises(CanonConflictError):
            self.bible.upsert_place("home", {"region": "Outra cidade"})

        routine = {"character_key": "marina", "routine_type": "sleep",
                   "probability": 0.9, "canon_locked": 1}
        self.assertEqual(
            self.bible.upsert_routine("marina.sleep", routine)["id"],
            self.bible.upsert_routine("marina.sleep", routine)["id"],
        )
        with self.assertRaises(CanonConflictError):
            self.bible.upsert_routine("marina.sleep", {"probability": 0.1})

    def test_world_state_latest_and_constraints(self):
        place = self.bible.upsert_place("home", {
            "name": "Casa", "region": "Botafogo", "place_type": "home",
            "truth_type": "canonical", "familiarity": "habitual",
        })
        self.assertIsNone(self.state.latest())
        older = self.state.add_snapshot({
            "state_date": "2026-09-17", "observed_at": "2026-09-17T08:00:00",
            "location_place_id": place["id"], "activity": "café",
            "source_json": {"truth_type": "system"},
        })
        newer = self.state.add_snapshot({
            "state_date": "2026-09-17", "observed_at": "2026-09-17T09:00:00",
            "location_place_id": place["id"], "activity": "estudo",
        })
        self.assertGreater(newer["id"], older["id"])
        self.assertEqual(self.state.latest()["activity"], "estudo")
        self.assertEqual(json.loads(older["source_json"]), {"truth_type": "system"})
        with self.assertRaises(sqlite3.IntegrityError):
            self.state.add_snapshot({
                "state_date": "2026-09-17", "observed_at": "2026-09-17T10:00:00",
                "location_place_id": 999999,
            })


if __name__ == "__main__":
    unittest.main()
