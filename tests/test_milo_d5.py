"""Fase D5 (Milo, Shih Tzu) e cochilo da tarde (D2) — decisões do Patrick em 23/09."""
import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from milo import HEAT_BLOCK, Milo
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from sleep_plan import SleepPlan
from world_state import RoutineEngine


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "milo.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        self.milo = Milo(self.db)
        self.days = [date(2026, 9, 21) + timedelta(days=i) for i in range(28)]

    def tearDown(self):
        self.temp.cleanup()


class MiloTest(_Base):
    def test_two_or_three_outings_every_day(self):
        for d in self.days:
            keys = {p["key"].split(":")[2] for p in self.milo.day_plan(d)}
            self.assertIn("manha", keys)
            self.assertIn("noite", keys)
            walker = "passeador" in keys
            engine = RoutineEngine(self.db)
            slot = engine._placement(d, engine._routine_row("milo_morning_walk"), "pet_walk", None)
            if walker:
                self.assertIsNone(slot, "com passeador ela não passeia")

    def test_walker_is_her_call_on_heavy_days_not_every_heavy_day(self):
        heavy = [d for d in self.days if (self.milo._last_class_end(d) or datetime.min).time() >= time(16, 0)]
        if heavy:
            decided = [self.milo.walker_today(d) for d in heavy]
            self.assertTrue(any(decided) or len(heavy) < 3)
            self.assertFalse(all(decided) and len(heavy) >= 3, "é decisão dela, não regra")

    def test_main_walk_never_in_the_midday_sun(self):
        engine = RoutineEngine(self.db)
        row = engine._routine_row("milo_morning_walk")
        for d in self.days:
            slot = engine._placement(d, row, "pet_walk", None)
            if slot:
                lo, hi = datetime.combine(d, HEAT_BLOCK[0]), datetime.combine(d, HEAT_BLOCK[1])
                self.assertFalse(slot[0] < hi and slot[1] > lo, (d, slot))

    def test_night_walk_becomes_state_and_event(self):
        d = self.days[3]
        night = next(p for p in self.milo.day_plan(d) if p["key"].endswith(":noite"))
        self.milo.materialize(night["at"] + timedelta(minutes=2))
        state = json.loads(self.db.get_estado_relacional()["pending_transition_json"])
        self.assertIn("Milo", state["activity"])
        with self.db.get_connection() as conn:
            self.assertTrue(conn.execute("SELECT 1 FROM life_events WHERE event_key=?", (night["key"],)).fetchone())
        from response_availability import ResponseAvailabilityPolicy
        self.assertEqual(ResponseAvailabilityPolicy(self.db)._map_place_activity(None, state["activity"]),
                         "PET_WALK")

    def test_milo_gets_up_to_mischief_sometimes(self):
        antics = [d for d in self.days if any(p["key"].endswith(":arte") for p in self.milo.day_plan(d))]
        self.assertTrue(0 < len(antics) < len(self.days))


class NapTest(_Base):
    def test_short_night_brings_an_afternoon_nap_sometimes(self):
        plan = SleepPlan(self.db)
        naps = [(d, plan.nap(d)) for d in self.days]
        for d, nap in naps:
            if nap:
                self.assertLess(plan.hours_slept(d), 6.5)
                self.assertTrue(time(13, 30) <= nap[0].time() and nap[1].time() <= time(17, 30))
                self.assertTrue(20 <= (nap[1] - nap[0]).total_seconds() / 60 <= 60)
        with patch.object(SleepPlan, "hours_slept", return_value=5.0):
            self.assertTrue(any(plan.nap(d) for d in self.days))
        with patch.object(SleepPlan, "hours_slept", return_value=8.0):
            self.assertFalse(any(plan.nap(d) for d in self.days))

    def test_nap_is_real_sleep_in_the_world(self):
        with patch.object(SleepPlan, "hours_slept", return_value=5.0):
            plan = SleepPlan(self.db)
            d, nap = next((d, plan.nap(d)) for d in self.days if plan.nap(d))
            mid = nap[0] + (nap[1] - nap[0]) / 2
            self.assertTrue(plan.is_asleep(mid))
            self.assertEqual(plan.next_wake_boundary(mid), nap[1])
            acts = [c.activity for c in RoutineEngine(self.db).candidates(mid)]
            self.assertIn("dormindo", acts)
            self.assertIn("Cochilou", "\n".join(plan.prompt_lines(nap[1] + timedelta(minutes=5))))


if __name__ == "__main__":
    unittest.main()
