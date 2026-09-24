"""Fase D10 — freela de modelo: oferta → casting → resposta → prova → job → cachê."""
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

import freela
from calendar_world import CalendarWorld
from db import DatabaseManager
from emotion import appraise_event
from freela import Freela

START = datetime(2026, 9, 1, 0, 0)


def _events(db, prefix):
    with db.get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT event_key, event_at, summary FROM life_events WHERE event_key LIKE ? ORDER BY event_at",
            (f"{prefix}%",))]


class FreelaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "f.db")
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start', ?, '2026-09-01')", (START.isoformat(),))
            conn.commit()
        self.f = Freela(self.db)
        for p in (patch("health.Health.illness", return_value=None), patch("health.Health.cramps", return_value=0)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _offer(self, after=date(2026, 9, 2)):
        for i in range(200):
            plan = self.f.offer_on(after + timedelta(days=i))
            if plan:
                return plan
        raise AssertionError("sem oferta")

    def _walk(self, plan, until_days=60, step_hours=3):
        now = plan["offer_at"]
        end = now + timedelta(days=until_days)
        while now <= end:
            self.f.materialize(now)
            now += timedelta(hours=step_hours)

    # ------------------------------------------------------------- plano --
    def test_two_or_three_castings_a_month_and_only_on_weekdays(self):
        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(365)]
        offers = [d for d in days if self.f.offer_on(d)]
        self.assertTrue(all(d.weekday() < 5 for d in offers))
        self.assertTrue(18 <= len(offers) <= 45, len(offers))
        self.assertEqual(self.f.offer_on(offers[0]), Freela(self.db).offer_on(offers[0]), "determinístico")

    # --------------------------------------------------------- caminhos --
    def test_approved_path_ends_with_the_paycheck(self):
        plan = self._offer()
        with patch.object(Freela, "_approve_chance", return_value=1.0):
            self.f.materialize(plan["offer_at"])
            booked = self.f.upcoming(plan["offer_at"], horizon_days=10)
            self.assertEqual(booked[0]["kind"], "casting")
            casting = booked[0]["start"]
            self.assertGreater(casting, plan["offer_at"] + timedelta(hours=3), "nada em cima da hora")
            current = CalendarWorld(self.db).current(casting + timedelta(minutes=10))
            self.assertIn("Casting", current["activity"])
            self._walk(plan)
        steps = [e["event_key"].rsplit(":", 1)[-1] for e in _events(self.db, plan["key"])]
        self.assertEqual(steps, ["oferta", "casting", "resultado", "prova", "job", "cache"])
        result = _events(self.db, f"{plan['key']}:resultado")[0]["summary"]
        self.assertIn("PASSOU", result)
        cache = _events(self.db, f"{plan['key']}:cache")[0]
        job = _events(self.db, f"{plan['key']}:job")[0]
        gap = datetime.fromisoformat(cache["event_at"]) - datetime.fromisoformat(job["event_at"])
        self.assertGreaterEqual(gap.days, 29)
        self.assertIn(f"R$ {plan['pay']}", cache["summary"])

    def test_rejected_path_stops_at_the_answer(self):
        plan = self._offer()
        with patch.object(Freela, "_approve_chance", return_value=0.0):
            self._walk(plan, until_days=15)
        steps = [e["event_key"].rsplit(":", 1)[-1] for e in _events(self.db, plan["key"])]
        self.assertEqual(steps, ["oferta", "casting", "resultado"])
        self.assertIn("não passou", _events(self.db, f"{plan['key']}:resultado")[0]["summary"])

    def test_virus_on_casting_day_loses_it(self):
        plan = self._offer()
        self.f.materialize(plan["offer_at"])
        start = self.f.upcoming(plan["offer_at"])[0]["start"]
        with patch.object(Freela, "_health_blocks", return_value="pegou uma virose"):
            self.f.materialize(start + timedelta(minutes=5))
        lost = _events(self.db, f"{plan['key']}:casting_perdido")
        self.assertEqual(len(lost), 1)
        self.assertIn("virose", lost[0]["summary"])
        self.assertIsNone(CalendarWorld(self.db).current(start + timedelta(minutes=10), include_academic=False))

    def test_nothing_before_her_recorded_life(self):
        plan = self._offer(after=date(2026, 8, 1))
        self.assertLess(plan["offer_at"], START)
        self.f.materialize(plan["offer_at"] + timedelta(days=1))
        self.assertEqual(_events(self.db, plan["key"]), [])

    def test_overweight_passes_less(self):
        with patch("meals.Meals.weight", return_value={"kg": 57.5}):
            heavy = self.f._approve_chance()
        with patch("meals.Meals.weight", return_value={"kg": 53.5}):
            fit = self.f._approve_chance()
        self.assertLess(heavy, freela.APPROVE_CHANCE)
        self.assertGreater(fit, heavy)

    # ------------------------------------------------------ prompt/emoção --
    def test_prompt_shows_the_real_agenda(self):
        plan = self._offer()
        self.f.materialize(plan["offer_at"])
        lines = "\n".join(self.f.prompt_lines(plan["offer_at"] + timedelta(minutes=1)))
        self.assertIn("não invente casting", lines)
        self.assertIn(f"casting: {plan['what']}", lines)

    def test_she_feels_each_step(self):
        ev = lambda key, text: appraise_event({"event_key": key, "event_type": "work", "summary": text,
                                               "participants_json": '["marina","livia_vasconcelos"]'})
        yes = ev("freela:2026-09-02:resultado", "A Lívia avisou: PASSOU no casting (x)! Job marcado")
        self.assertIn("empolgacao", [k for _, k, *_ in yes])
        no = ev("freela:2026-09-02:resultado", "A Lívia avisou: não passou no casting (x).")
        self.assertEqual(no[0][1], "decepcao")
        paid = ev("freela:2026-09-02:cache", "Caiu o cachê do job (x): R$ 900.")
        self.assertEqual(paid[0][1], "contentamento")


if __name__ == "__main__":
    unittest.main()
