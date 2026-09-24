"""Fase D9 — casa e vida adulta: roupa, faxina, mercado, contas, perrengues."""
import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

from casa import Casa
from db import DatabaseManager
from emotion import appraise_event


class CasaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "casa.db")
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        self.casa = Casa(self.db)
        p = patch("health.Health.illness", return_value=None)
        p.start()
        self.addCleanup(p.stop)
        self.weeks = [date(2026, 9, 7) + timedelta(weeks=w) for w in range(12)]

    def tearDown(self):
        self.temp.cleanup()

    def _week_keys(self, monday):
        return [p["key"].split(":")[2] for i in range(7) for p in self.casa.day_plan(monday + timedelta(days=i))]

    def test_every_week_has_laundry_twice_and_one_grocery_run(self):
        for monday in self.weeks:
            keys = self._week_keys(monday)
            self.assertEqual(keys.count("roupa"), 2)
            self.assertEqual(keys.count("mercado"), 1)
            self.assertEqual(keys.count("roupa_esquecida") + keys.count("varal"), 2)

    def test_grocery_comes_after_dad_sends_money_monday(self):
        for monday in self.weeks:
            days = [i for i in range(7) for p in self.casa.day_plan(monday + timedelta(days=i))
                    if p["key"].endswith(":mercado")]
            self.assertNotIn(0, days)
            self.assertNotIn(6, days)

    def test_weekend_cleanup_most_weekends(self):
        done = sum(1 for m in self.weeks if "geral" in self._week_keys(m))
        self.assertGreaterEqual(done, 7)

    def test_bills_once_a_month_around_the_10th(self):
        days = [date(2026, 9, 1) + timedelta(days=i) for i in range(90)]
        bills = [d for d in days for p in self.casa.day_plan(d) if p["key"].endswith(":contas")]
        self.assertEqual(len(bills), 3)
        self.assertTrue(all(8 <= d.day <= 12 for d in bills))

    def test_no_grocery_with_a_virus(self):
        monday = self.weeks[0]
        with patch("health.Health.illness", return_value=("virose", 1, 2, 1)):
            self.assertNotIn("mercado", self._week_keys(monday))

    def test_grocery_becomes_state_and_logs_the_day(self):
        monday = self.weeks[1]
        item = next(p for i in range(7) for p in self.casa.day_plan(monday + timedelta(days=i))
                    if p["key"].endswith(":mercado"))
        now = item["at"] + timedelta(minutes=5)
        self.assertGreaterEqual(self.casa.materialize(now), 1)
        payload = json.loads(self.db.get_estado_relacional()["pending_transition_json"])
        self.assertEqual(payload["activity"], "no mercado fazendo as compras da semana")
        self.assertEqual(self.casa.materialize(now), 0, "idempotente")

    def test_nothing_before_recorded_life(self):
        self.assertEqual(self.casa.materialize(datetime(2026, 8, 20, 22, 0)), 0)

    def test_she_feels_it(self):
        ev = lambda key, text: appraise_event({"event_key": key, "event_type": "routine", "summary": text})
        self.assertEqual(ev("casa:2026-09-08:roupa_esquecida", "Esqueceu a roupa")[0][1], "frustracao")
        self.assertEqual(ev("casa:2026-09-12:geral", "Faxina")[0][1], "alivio")
        self.assertEqual(ev("casa:2026-09-12:perrengue", "A lâmpada do banheiro queimou.")[0][1], "irritacao")
        self.assertEqual(ev("casa:2026-09-08:roupa", "Botou uma máquina"), [])


if __name__ == "__main__":
    unittest.main()
