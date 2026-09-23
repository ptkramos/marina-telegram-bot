"""Fase D7 — faculdade além da grade: trabalhos, véspera, faltas e atrasos (23/09)."""
import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

import college
from academic_life import AcademicLife
from college import College
from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from sleep_plan import SleepPlan


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "facul.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        self.c = College(self.db)
        self.start = date(2026, 9, 28)
        self.days = [self.start + timedelta(days=i) for i in range(35)]

    def tearDown(self):
        self.temp.cleanup()

    def _events(self, like):
        with self.db.get_connection() as conn:
            return [r[0] for r in conn.execute("SELECT summary FROM life_events WHERE event_key LIKE ?", (like,))]


class AssignmentsTest(_Base):
    def test_real_courses_have_spaced_deadlines(self):
        items = self.c.assignments(self.start, horizon_days=34)
        self.assertGreater(len(items), 4)
        with self.db.get_connection() as conn:
            names = {r[0] for r in conn.execute("SELECT display_name FROM academic_courses")}
        for a in items:
            self.assertIn(a["course"], names)
            self.assertIn(a["pace"], ("adiantada", "normal", "ultima_hora"))
            if a["kind"] == "exercício":
                self.assertEqual(a["lead_days"], 1)
        per_course = {}
        for a in items:
            per_course.setdefault(a["course_id"], []).append(date.fromisoformat(a["due"]))
        for dues in per_course.values():
            for d1, d2 in zip(dues, dues[1:]):
                self.assertGreaterEqual((d2 - d1).days, 21)

    def test_not_every_night_is_work(self):
        nights = [d for d in self.days if self.c.session_on(d)]
        self.assertLess(len(nights), len(self.days) * 0.75)
        self.assertTrue(all(not (d.weekday() == 5 and not self.c.session_on(d)["vespera"]) for d in nights))


class WorkNightTest(_Base):
    def test_work_session_becomes_state_event_and_work_availability(self):
        day = next(d for d in self.days if self.c.session_on(d))
        s = self.c.session_on(day)
        self.c.materialize(s["start"] + timedelta(minutes=5))
        state = json.loads(self.db.get_estado_relacional()["pending_transition_json"])
        self.assertIn("fazendo o trabalho de", state["activity"])
        self.assertTrue(any("Trabalhou no" in e for e in self._events("facul:sessao:%")))
        from response_availability import ResponseAvailabilityPolicy
        self.assertEqual(ResponseAvailabilityPolicy(self.db)._map_place_activity("marina_apartment",
                                                                                 state["activity"]), "WORK")

    def test_last_minute_eve_pulls_an_all_nighter(self):
        term = [date(2026, 8, 20) + timedelta(days=i) for i in range(115)]
        day = next((d for d in term if (s := self.c.session_on(d)) and s["vespera"]
                    and s["assignment"]["pace"] == "ultima_hora"), None)
        if day is None:
            self.skipTest("sem véspera de última hora na janela")
        extra, why = self.c.onset(day)
        self.assertGreaterEqual(extra, 60)
        self.assertIn("virou a noite", why[0])
        with patch("sleep_plan.ONSET_TROUBLE_CHANCE", 0.0):
            _delta, reasons = SleepPlan(self.db)._onset(day, live=False)
        self.assertTrue(any("virou a noite" in r for r in reasons))

    def test_tv_comes_after_work_not_instead(self):
        import watch
        with patch.object(watch, "WATCH_NIGHT_CHANCE", 1.0):
            for d in self.days:
                s = self.c.session_on(d)
                plan = watch.Watching(self.db).night_plan(d)
                if s and not (s["vespera"] and s["assignment"]["pace"] == "ultima_hora"):
                    self.assertGreaterEqual(plan["start"], s["end"])
                elif s:
                    self.assertIsNone(plan)


class MorningTest(_Base):
    def _class_day(self, skip_due=True):
        dues = {a["due"] for a in self.c.assignments(self.start, horizon_days=34)}
        return next(d for d in self.days if AcademicLife(self.db).blocks_on(d)
                    and (not skip_due or d.isoformat() not in dues))

    def test_she_skips_class_when_she_slept_terribly(self):
        day = self._class_day()
        wake = SleepPlan(self.db).wake(day)
        with patch.object(SleepPlan, "hours_slept", return_value=4.5), \
             patch.object(college, "SKIP_CHANCE_BAD_SLEEP", 1.0):
            self.assertEqual(self.c.morning(wake + timedelta(minutes=5)), "falta")
        self.assertEqual(AcademicLife(self.db).blocks_on(day), [])
        self.assertTrue(any("Faltou a aula hoje" in e and "dormiu muito mal" in e for e in self._events("falta:%")))
        self.assertEqual(SleepPlan(self.db).wake(day), wake, "a manhã que já aconteceu não muda")
        self.assertIsNone(self.c.morning(wake + timedelta(minutes=30)), "decide uma vez só")

    def test_never_skips_on_a_delivery_day(self):
        dues = [a for a in self.c.assignments(self.start, horizon_days=34)
                if AcademicLife(self.db).blocks_on(date.fromisoformat(a["due"]))]
        day = date.fromisoformat(dues[0]["due"])
        with patch.object(SleepPlan, "hours_slept", return_value=4.0), \
             patch.object(college, "SKIP_CHANCE_BAD_SLEEP", 1.0):
            self.assertIsNone(self.c.skip_reason(day, AcademicLife(self.db).blocks_on(day)))

    def test_late_for_real_when_she_oversleeps(self):
        day = self._class_day()
        first = min(datetime.fromisoformat(b["start_at"]) for b in AcademicLife(self.db).blocks_on(day))
        late_wake = first - timedelta(minutes=35)
        with patch.object(SleepPlan, "wake", return_value=late_wake), \
             patch.object(College, "skip_reason", return_value=None):
            self.assertEqual(self.c.morning(late_wake + timedelta(minutes=2)), "atraso")
        self.assertTrue(any("atrasada" in e for e in self._events("atraso:%")))

    def test_prompt_lists_real_deadlines(self):
        text = "\n".join(self.c.prompt_lines(datetime.combine(self.start, time(12, 0))))
        self.assertIn("[FACULDADE", text)
        self.assertIn("não invente trabalho", text)


if __name__ == "__main__":
    unittest.main()
