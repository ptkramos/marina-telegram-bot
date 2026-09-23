"""Fases D2 + D3 + D13 — sono variável, micro-despertares e manhã de trás pra frente."""
import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

from academic_life import AcademicLife
from db import DatabaseManager
from response_availability import ResponseAvailabilityPolicy
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from sleep_plan import DEEP_SLEEP, SleepPlan
from world_state import RoutineEngine, WorldStateManager


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "sono.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.plan = SleepPlan(self.db)
        self.days = [date(2026, 9, 21) + timedelta(days=i) for i in range(28)]
        self.class_days = [d for d in self.days if AcademicLife(self.db).blocks_on(d)]
        self.free_days = [d for d in self.days if d not in self.class_days]

    def tearDown(self):
        self.temp.cleanup()

    def _first_class(self, day):
        return min(datetime.fromisoformat(b["start_at"]) for b in AcademicLife(self.db).blocks_on(day))


class MorningBackwardsTest(_Base):
    def test_class_day_wake_leaves_time_to_get_ready(self):
        for day in self.class_days:
            alarm = self.plan.target_wake(day)
            leave = self.plan._first_commitment(day)
            self.assertLessEqual(leave, self._first_class(day), day)
            self.assertGreaterEqual((leave - alarm).total_seconds() / 60, 50, day)

    def test_sometimes_she_oversleeps_but_not_often(self):
        late = [d for d in self.class_days if self.plan.overslept(d)]
        self.assertTrue(0 < len(late) < len(self.class_days) / 2)
        for d in late:
            self.assertEqual(self.plan.wake(d), self.plan.target_wake(d) + timedelta(minutes=self.plan.overslept(d)))


class VariableSleepTest(_Base):
    def test_bedtime_is_never_the_same_fixed_minute(self):
        beds = {self.plan.bed(d).strftime("%H:%M") for d in self.days}
        self.assertGreater(len(beds), 10)

    def test_before_a_commitment_she_tries_8h_and_usually_sleeps_less(self):
        nights = [self.plan.hours_slept(d) for d in self.class_days]
        self.assertTrue(all(h <= 8.5 for h in nights))
        self.assertGreater(sum(h < 8 for h in nights), len(nights) / 2)

    def test_free_days_sleep_more_and_weekend_nights_run_late(self):
        free = [self.plan.hours_slept(d) for d in self.free_days]
        classes = [self.plan.hours_slept(d) for d in self.class_days]
        self.assertGreater(sum(free) / len(free), sum(classes) / len(classes))
        saturday = next(d for d in self.days if d.weekday() == 5)
        self.assertGreaterEqual(self.plan.bed(saturday),
                                datetime.combine(saturday, time(23, 30)))

    def test_outing_pushes_bedtime(self):
        day = next(d for d in self.days if d.weekday() == 4)
        before = self.plan.bed(day)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO eventos_pendentes (source_key, event_type, description, event_at, end_at, "
                         "confirmed, status, created_at) VALUES (?, 'outing', 'bar', ?, ?, 1, 'pending', ?)",
                         (f"outing:{day.isoformat()}:bar", datetime.combine(day, time(21, 0)).isoformat(),
                          datetime.combine(day + timedelta(days=1), time(1, 30)).isoformat(),
                          datetime.combine(day, time(12, 0)).isoformat()))
            conn.commit()
        self.assertGreater(self.plan.bed(day), max(before, datetime.combine(day + timedelta(days=1), time(1, 30))))

    def test_windows_cover_the_night_across_midnight(self):
        day = self.days[5]
        windows = self.plan.windows_on(day)
        self.assertEqual(windows[0], (max(datetime.combine(day, time(0, 0)),
                                          self.plan.bed(day - timedelta(days=1))), self.plan.wake(day)))


class MicroWakeTest(_Base):
    def test_zero_to_two_per_night_never_in_deep_sleep(self):
        counts = []
        for d in self.days:
            wakes = self.plan.micro_wakes(d)
            counts.append(len(wakes))
            for start, end, reason in wakes:
                self.assertTrue(self.plan.bed(d) < start < end < self.plan.wake(d + timedelta(days=1)))
                deep_lo = datetime.combine(d + timedelta(days=1), DEEP_SLEEP[0])
                deep_hi = datetime.combine(d + timedelta(days=1), DEEP_SLEEP[1])
                self.assertFalse(deep_lo <= start < deep_hi, (d, start))
                self.assertTrue(3 <= (end - start).total_seconds() / 60 <= 8)
        self.assertLessEqual(max(counts), 2)
        self.assertGreater(sum(counts), 0)
        self.assertGreater(counts.count(0), 0)

    def test_message_at_night_is_answered_at_the_micro_wake(self):
        night = next(d for d in self.days if self.plan.micro_wakes(d))
        start, _end, _reason = self.plan.micro_wakes(night)[0]
        before = start - timedelta(minutes=10)
        if self.plan.is_asleep(before):
            self.assertEqual(self.plan.next_wake_boundary(before), start)

    def test_micro_wake_becomes_a_brief_awake_state(self):
        night = next(d for d in self.days if self.plan.micro_wakes(d))
        start, _end, reason = self.plan.micro_wakes(night)[0]
        cands = RoutineEngine(self.db).candidates(start + timedelta(minutes=1))
        acts = [c.activity for c in cands]
        self.assertFalse(any(a == "dormindo" for a in acts))
        micro = [a for a in acts if a.startswith("acordou de madrugada")]
        self.assertEqual(len(micro), 1)
        self.assertNotIn("dorm", micro[0])
        policy = ResponseAvailabilityPolicy(self.db)
        self.assertEqual(policy._map_place_activity("marina_apartment", micro[0]), "MICRO_WAKE")


class WorldIntegrationTest(_Base):
    def test_asleep_and_awake_follow_the_plan(self):
        day = self.class_days[0]
        wake = self.plan.wake(day)
        engine = RoutineEngine(self.db)
        acts_before = [c.activity for c in engine.candidates(wake - timedelta(minutes=20), has_class=True)]
        self.assertIn("dormindo", acts_before)
        acts_after = [c.activity for c in engine.candidates(wake + timedelta(minutes=5), has_class=True)]
        self.assertNotIn("dormindo", acts_after)
        self.assertTrue(any("se arrumando" in a for a in acts_after))

    def test_she_wakes_up_in_the_world_right_away(self):
        """Antes ela podia seguir 'dormindo' até 60 min depois de acordar."""
        manager = WorldStateManager(self.db)
        day = self.free_days[0]
        wake = self.plan.wake(day)
        asleep = manager.resolve(wake - timedelta(minutes=30))
        self.assertIn("dorm", asleep["activity"])
        awake = manager.resolve(wake + timedelta(minutes=5))
        self.assertNotIn("dorm", awake["activity"])

    def test_kill_switch_restores_the_fixed_canon(self):
        from config import settings
        with patch.object(settings, "SLEEP_PLAN_ENABLED", False):
            day = self.class_days[0]
            windows = RoutineEngine(self.db)._sleep_windows(day, True)
            self.assertEqual(windows[0][0].strftime("%H:%M"), "00:00")

    def test_prompt_tells_how_she_slept(self):
        day = self.class_days[1]
        lines = "\n".join(self.plan.prompt_lines(self.plan.wake(day) + timedelta(hours=2)))
        self.assertIn("Esta noite você dormiu", lines)
        self.assertEqual(self.plan.prompt_lines(self.plan.wake(day) - timedelta(minutes=5)), [])


if __name__ == "__main__":
    unittest.main()
