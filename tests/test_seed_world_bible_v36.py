"""Seed v3.6: canon, repetição e rollback em banco descartável."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from seed_world_bible_v36 import SEED_VERSION, seed_world_bible
from world_repository import CanonConflictError, WorldBibleRepository


class TestWorldBibleSeed(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "seed_test.db")

    def tearDown(self):
        self.temp.cleanup()

    def _counts(self):
        with self.db.get_connection() as conn:
            return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("world_characters", "world_places", "routine_patterns",
                                  "character_preferences", "world_bootstrap",
                                  "story_threads", "knowledge_items")}

    def test_seed_canon_and_second_run_are_identical(self):
        expected = seed_world_bible(self.db)
        counts = self._counts()
        self.assertEqual(counts["world_characters"], expected["characters"])
        self.assertEqual(counts["world_places"], expected["places"])
        self.assertEqual(counts["routine_patterns"], expected["routines"])
        # Fase D6: a migration 023 grava o cânone de gostos (títulos) antes do seed.
        with self.db.get_connection() as conn:
            taste_canon = conn.execute("SELECT COUNT(*) FROM character_preferences "
                                       "WHERE category LIKE 'watched_%' OR category='games'").fetchone()[0]
        self.assertEqual(taste_canon, 20)
        self.assertEqual(counts["character_preferences"], expected["preferences"] + taste_canon)
        self.assertEqual(counts["world_bootstrap"], 2)
        self.assertEqual(counts["story_threads"], 0)
        self.assertEqual(counts["knowledge_items"], 0)

        repo = WorldBibleRepository(self.db)
        marina = repo.get_character("marina")
        self.assertEqual(marina["display_name"], "Marina Salles")
        self.assertEqual(marina["birth_date"], "2006-04-29")
        self.assertEqual(marina["canon_locked"], 1)
        self.assertEqual(repo.age_on("marina", date(2026, 4, 28)), 19)
        self.assertEqual(repo.age_on("marina", date(2026, 4, 29)), 20)
        self.assertEqual(repo.age_on("marina", date(2027, 4, 29)), 21)
        biography = json.loads(marina["initial_state_json"])
        self.assertTrue(biography["past"]["no_official_ex_boyfriends"])
        self.assertTrue(biography["relationship"]["first_official_boyfriend"])
        self.assertEqual(biography["pet"]["name"], "Milo")
        self.assertEqual(repo.get_place("marina_apartment")["canon_locked"], 1)
        self.assertEqual(repo.get_routine("gym_weekly")["canon_locked"], 1)
        self.assertIsNotNone(repo.get_character("bia_andrade"))
        self.assertIsNotNone(repo.get_character("livia_vasconcelos"))

        with self.db.get_connection() as conn:
            marker = conn.execute(
                "SELECT value FROM world_bootstrap WHERE key = 'world_bible_seed_version'"
            ).fetchone()[0]
            self.assertEqual(marker, SEED_VERSION)
            created_at = conn.execute(
                "SELECT created_at FROM world_characters WHERE canonical_key = 'marina'"
            ).fetchone()[0]
        self.assertEqual(seed_world_bible(self.db), expected)
        self.assertEqual(self._counts(), counts)
        self.assertEqual(repo.get_character("marina")["created_at"], created_at)

    def test_conflicting_canon_rolls_back_whole_seed(self):
        repo = WorldBibleRepository(self.db)
        repo.upsert_character("marina", {
            "display_name": "Nome conflitante", "character_type": "marina", "canon_locked": 1,
        })
        before = self._counts()
        with self.assertRaises(CanonConflictError):
            seed_world_bible(self.db)
        self.assertEqual(self._counts(), before)
        self.assertEqual(repo.get_character("marina")["display_name"], "Nome conflitante")

    def test_changed_seed_digest_is_rejected(self):
        seed_world_bible(self.db)
        before = self._counts()
        with patch("seed_world_bible_v36._seed_digest", return_value="changed"):
            with self.assertRaises(CanonConflictError):
                seed_world_bible(self.db)
        self.assertEqual(self._counts(), before)


if __name__ == "__main__":
    unittest.main()
