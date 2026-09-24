"""Fase D11 — saúde: cólica com intensidade, resfriado, virose, dor de cabeça."""
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

import health
from db import DatabaseManager
from emotion import EmotionEngine
from health import Health

CYCLE_START = date(2026, 1, 3)


def _first(pred, start=date(2026, 1, 1), days=900):
    for i in range(days):
        d = start + timedelta(days=i)
        if pred(d):
            return d
    raise AssertionError("nenhum dia encontrado")


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "h.db")
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO ciclo_biologico (data_inicio_ciclo, updated_at) VALUES (?, ?)",
                         (CYCLE_START.isoformat(), CYCLE_START.isoformat()))
            conn.commit()
        self.h = Health(self.db)
        health.clear_cache()
        self.addCleanup(health.clear_cache)
        p = patch.object(Health, "_approx_slept", return_value=7.5)   # sono neutro, sem o sleep_plan
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    # ------------------------------------------------------------ cólica --
    def test_cramps_have_a_level_per_cycle_and_ease_day_by_day(self):
        levels = set()
        for k in range(30):
            first = CYCLE_START + timedelta(days=28 * k)
            lv = self.h.cramps(first)
            levels.add(lv)
            self.assertEqual(self.h.cramps(first + timedelta(days=1)), max(0, lv - 1))
            self.assertEqual(self.h.cramps(first + timedelta(days=3)), 0)
            self.assertEqual(self.h.cramps(first + timedelta(days=10)), 0)
        self.assertEqual(levels, {1, 2, 3}, "tem mês que dói mais")

    def test_strong_cramps_keep_her_home_and_in_bed_early(self):
        day = _first(lambda d: self.h.cramps(d) == 3 and (d - CYCLE_START).days % 28 == 0, CYCLE_START)
        chance, reason = self.h.skip_option(day)
        self.assertGreaterEqual(chance, 0.8)
        self.assertIn("cólica forte", reason)
        minutes, why = self.h.onset(day)
        self.assertLess(minutes, 0)
        lines = "\n".join(self.h.prompt_lines(datetime.combine(day, time(10, 0))))
        self.assertIn("Buscopan", lines)
        self.assertIn("manhosa", lines)

    # ----------------------------------------------------------- doenças --
    def test_cold_lasts_days_and_is_the_same_every_time_you_ask(self):
        day = _first(lambda d: (self.h.illness(d) or ("",))[0] == "resfriado" and self.h.illness(d)[1] == 1)
        kind, n, length, _ = self.h.illness(day)
        self.assertEqual((kind, n), ("resfriado", 1))
        self.assertIn(length, range(3, 6))
        self.assertEqual(self.h.illness(day + timedelta(days=length - 1))[1], length)
        self.assertEqual(Health(self.db).illness(day), self.h.illness(day), "fato do mundo, determinístico")
        after = self.h.illness(day + timedelta(days=length))
        self.assertTrue(after is None or after[1] == 1, "acabou; se veio outra, é outra")

    def test_virus_kills_appetite_and_skips_class(self):
        day = _first(lambda d: (self.h.illness(d) or ("",))[0] == "virose")
        now = datetime.combine(day, time(12, 0))
        self.assertLess(self.h.appetite(now), 0.5)
        self.assertEqual(self.h.skip_option(day)[1], "virose, passou mal e ficou em casa")
        self.assertGreater(self.h.energy_penalty(now), 0.2)

    def test_bad_sleep_rain_and_stress_lower_immunity(self):
        day = date(2026, 5, 5)
        self.assertEqual(self.h.cold_risk(day)[0], 1.0)
        with patch.object(Health, "_approx_slept", return_value=5.0):
            risk, why = self.h.cold_risk(day)
        self.assertEqual(risk, health.COLD_RISK_BAD_SLEEP)
        self.assertIn("dormindo pouco", why)

    def test_low_immunity_means_more_colds(self):
        def colds(risk):
            health.clear_cache()
            with patch.object(Health, "cold_risk", return_value=(risk, [])):
                return sum(1 for i in range(730)
                           if (x := self.h.illness(date(2026, 1, 1) + timedelta(days=i))) and x[0] == "resfriado" and x[1] == 1)
        self.assertGreater(colds(4.0), colds(1.0))

    # ----------------------------------------------------- dor de cabeça --
    def test_headache_is_a_window_and_she_usually_takes_something(self):
        day = _first(lambda d: self.h.headache(d) is not None)
        start, end, remedy = self.h.headache(day)
        self.assertGreaterEqual(start.hour, 13)
        self.assertIn(":", remedy) if "dipirona" in remedy else self.assertIn("aguentando", remedy)
        self.assertTrue(any(c.kind == "dor_de_cabeca" for c in self.h.conditions(start + timedelta(minutes=5))))
        self.assertFalse(any(c.kind == "dor_de_cabeca" for c in self.h.conditions(end + timedelta(minutes=5))))

    def test_bad_night_makes_headache_much_likelier(self):
        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(365)]
        normal = sum(1 for d in days if self.h.headache(d))
        health.clear_cache()
        with patch.object(Health, "_approx_slept", return_value=5.0):
            bad = sum(1 for d in days if self.h.headache(d))
        self.assertGreater(bad, 3 * normal)

    # --------------------------------------------------------- no motor --
    def test_small_things_she_brushes_off(self):
        day = _first(lambda d: self.h.cramps(d) == 1 and not self.h.illness(d), CYCLE_START)
        lines = "\n".join(self.h.prompt_lines(datetime.combine(day, time(9, 0))))
        self.assertIn("minimiza", lines)
        self.assertNotIn("manhosa", lines)

    def test_engine_feels_it_in_the_body(self):
        day = _first(lambda d: (self.h.illness(d) or ("",))[0] == "virose")
        now = datetime.combine(day, time(15, 0))
        engine = EmotionEngine(self.db)
        value, why = engine._discomfort(now)
        self.assertGreaterEqual(value, 0.7)
        self.assertIn("virose", why)
        lines = "\n".join(engine.prompt_lines(now))
        self.assertIn("- Saúde: virose", lines)
        self.assertEqual(lines.count("virose (enjoo"), 1, "não repete no Corpo e na Saúde")

    def test_facts_of_the_day_are_cached_for_the_turn(self):
        with patch.object(health, "_cache_in_tests", True), patch.object(Health, "_illness", return_value=None) as calc:
            for _ in range(5):
                Health(self.db).illness(date(2026, 3, 3))
        self.assertEqual(calc.call_count, 1)

    # ------------------------------------------------------------ médico --
    def _strong_cold_start(self):
        return _first(lambda d: (x := self.h.illness(d)) is not None and x[0] == "resfriado" and x[1] == 1
                      and x[3] == 2 and x[2] >= 3, days=4000)

    def test_patrick_sends_her_to_the_doctor_and_she_gets_better_faster(self):
        with patch.object(health, "DAD_SENDS_CHANCE", 0.0):
            start = self._strong_cold_start()
            before = self.h.illness(start)[2]
            now = datetime.combine(start, time(10, 0))
            self.assertFalse(self.h.observe_patrick("te amo, se cuida", now))
            self.assertTrue(self.h.observe_patrick("amor vai no médico, não fica assim não", now))
            after = self.h.illness(start)[2]
            self.assertLess(after, before, "remédio de médico: melhora mais rápido")
            lines = " | ".join(self.h.prompt_lines(now))
            self.assertIn("O Patrick mandou você ir ao médico", lines)
            later = now + timedelta(hours=3)
            self.assertIn("foi ao médico", " | ".join(self.h.prompt_lines(later)))
            self.assertEqual(self.h.materialize(later), 1)

    def test_no_doctor_for_cramps_or_small_things(self):
        day = _first(lambda d: self.h.cramps(d) == 3 and not self.h.illness(d), CYCLE_START)
        self.assertFalse(self.h.observe_patrick("vai no médico amor", datetime.combine(day, time(10, 0))))

    def test_dad_sometimes_sends_her(self):
        with patch.object(health, "DAD_SENDS_CHANCE", 1.0):
            start = self._strong_cold_start()
            visit = self.h.doctor(datetime.combine(start, time(9, 0)))
        self.assertEqual(visit[1], "o pai")

    def test_healthy_day_is_silent(self):
        day = _first(lambda d: not self.h.conditions(datetime.combine(d, time(10, 0))), date(2026, 1, 20))
        self.assertEqual(self.h.prompt_lines(datetime.combine(day, time(10, 0))), [])
        self.assertEqual(self.h.discomfort(datetime.combine(day, time(10, 0))), (0.0, ""))


if __name__ == "__main__":
    unittest.main()
