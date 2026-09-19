"""WorldState/Routine v3.6 em banco isolado, sem LLM ou Telegram."""

import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from seed_academic_v36 import seed_academic
from world_state import RoutineEngine, WorldStateManager


class TestWorldState(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "world_state_test.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.routine = RoutineEngine(self.db, random.Random(17))
        self.manager = WorldStateManager(self.db, routine=self.routine, stale_minutes=60)
        self.now = datetime(2026, 9, 17, 16, 0)

    def tearDown(self):
        self.temp.cleanup()

    def test_confirmed_commitment_beats_plan_and_routine_even_when_state_is_fresh(self):
        first = self.manager.resolve(self.now, has_class=False)
        commitment = {
            "activity": "em compromisso confirmado", "place_key": "puc_rio",
            "start_at": (self.now - timedelta(minutes=10)).isoformat(),
            "end_at": (self.now + timedelta(minutes=50)).isoformat(),
        }
        plan = {"activity": "em casa", "place_key": "marina_apartment"}
        second = self.manager.resolve(
            self.now + timedelta(minutes=5), confirmed_commitment=commitment,
            explicit_plan=plan, has_class=False,
        )
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(second["activity"], "em compromisso confirmado")
        self.assertEqual(second["location_region"], "Gávea")
        self.assertEqual(json.loads(second["source_json"])["reason"], "confirmed_commitment")

    def test_explicit_plan_and_freshness_then_stale_transition(self):
        plan = {"activity": "estudando no studio", "place_key": "marina_apartment"}
        first = self.manager.resolve(self.now, explicit_plan=plan)
        self.assertEqual(first["activity"], "estudando no studio")
        self.assertEqual(self.manager.resolve(self.now + timedelta(minutes=30))["id"], first["id"])
        later = self.manager.resolve(self.now + timedelta(minutes=61), has_class=False)
        self.assertNotEqual(later["id"], first["id"])

    def test_rain_shifts_gym_to_building_and_no_class_is_invented(self):
        dry = self.routine.candidates(self.now, has_class=False, heavy_rain=False)
        rain = self.routine.candidates(self.now, has_class=False, heavy_rain=True)
        dry_external = next(c.score for c in dry if c.source_key == "gym_weekly")
        rainy_external = next(c.score for c in rain if c.source_key == "gym_weekly")
        rainy_building = next(c for c in rain if c.source_key == "gym_weekly:rain_fallback")
        self.assertLess(rainy_external, dry_external)
        self.assertGreater(rainy_building.score, rainy_external)
        self.assertEqual(rainy_building.place_key, "marina_apartment")
        self.assertFalse(any(c.source_key == "class_day_study" for c in rain))
        self.assertFalse(any(c.source_key == "class_day_study" for c in
                             self.routine.candidates(self.now, has_class=None)))

    def test_outside_routine_window_is_quiet_and_creates_no_story(self):
        sunday = datetime(2026, 9, 20, 14, 0)
        self.assertEqual(self.routine.candidates(sunday, has_class=False), [])
        state = self.manager.resolve(sunday, has_class=False)
        self.assertEqual(state["activity"], "tempo livre em casa")
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM life_events").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM story_threads").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM conversas").fetchone()[0], 0)

    def test_sleep_is_default_after_midnight_on_class_and_light_days(self):
        for moment, has_class in (
            (datetime(2026, 9, 18, 2, 45), True),
            (datetime(2026, 9, 19, 2, 45), False),
        ):
            with self.subTest(moment=moment, has_class=has_class):
                candidates = self.routine.candidates(moment, has_class=has_class)
                self.assertEqual(self.routine.choose(candidates).activity, "dormindo")

    def test_sleep_window_invalidates_cached_soft_awake_state(self):
        earlier = datetime(2026, 9, 19, 2, 30)
        with self.db.get_connection() as conn:
            place = conn.execute(
                "SELECT id FROM world_places WHERE canonical_key='marina_apartment'"
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO world_state
                   (state_date,observed_at,location_place_id,location_region,activity,
                    energy_level,source_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (earlier.date().isoformat(), earlier.isoformat(), place, "Botafogo",
                 "tempo livre em casa", .7,
                 json.dumps({"reason": "free_time", "truth_type": "system"})),
            )
        resolved = self.manager.resolve(
            earlier + timedelta(minutes=15), has_class=False
        )
        self.assertEqual(resolved["activity"], "dormindo")

    def test_expired_commitment_does_not_override_routine(self):
        expired = {
            "activity": "compromisso antigo", "place_key": "puc_rio",
            "start_at": (self.now - timedelta(hours=3)).isoformat(),
            "end_at": (self.now - timedelta(hours=2)).isoformat(),
        }
        state = self.manager.resolve(self.now, confirmed_commitment=expired, has_class=False)
        self.assertNotEqual(state["activity"], "compromisso antigo")

    def test_cached_commitment_expires_before_normal_staleness(self):
        meeting = {
            "activity": "reunião", "place_key": "boutique_agency",
            "start_at": self.now.isoformat(),
            "end_at": (self.now + timedelta(minutes=20)).isoformat(),
        }
        first = self.manager.resolve(self.now, confirmed_commitment=meeting)
        later = self.manager.resolve(self.now + timedelta(minutes=30),
                                     confirmed_commitment=meeting, has_class=False)
        self.assertNotEqual(first["id"], later["id"])
        self.assertNotEqual(later["activity"], "reunião")

    def test_point_commitment_expires_and_weather_change_refreshes_state(self):
        point = {
            "activity": "casting", "place_key": "boutique_agency",
            "start_at": self.now.isoformat(),
        }
        first = self.manager.resolve(self.now, confirmed_commitment=point)
        self.assertEqual(first["activity"], "casting")
        later = self.manager.resolve(self.now + timedelta(hours=2), confirmed_commitment=point,
                                     has_class=False, weather={"heavy_rain": False})
        self.assertNotEqual(later["activity"], "casting")
        changed = self.manager.resolve(self.now + timedelta(hours=2, minutes=5),
                                       has_class=False, weather={"heavy_rain": True})
        self.assertNotEqual(changed["id"], later["id"])
        self.assertEqual(json.loads(changed["weather_context_json"]), {"heavy_rain": True})


if __name__ == "__main__":
    unittest.main()
