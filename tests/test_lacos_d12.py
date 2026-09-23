"""Fase D12 — laços: pai todo dia, Bia ao longo do dia, saudade do Patrick.

Soak de 22/09: nenhum contato com o pai nem com a Bia, e zero iniciativa dela
por vontade própria (só 2 rituais). Decisões do Patrick em 23/09: o pai checa
a filha pelo menos 1×/dia, liga quando está livre e banca a comida; a procura
pelo Patrick não tem teto — é o emocional que decide.
"""
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from db import DatabaseManager
from proactivity_service import SAUDADE_BACKOFF_MINUTES, ProactivityService
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from social_day import SocialDay


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "d12.db")
        seed_world_bible(self.db)
        seed_academic(self.db)

    def tearDown(self):
        self.temp.cleanup()


class BondsInTheSocialDayTest(_Base):
    def setUp(self):
        super().setUp()
        self.day = SocialDay(self.db)
        self.days = [date(2026, 9, 21) + timedelta(days=i) for i in range(14)]

    def test_father_checks_on_her_every_single_day(self):
        for d in self.days:
            dad = [c for c in self.day.plan(d) if c.character_key == "henrique_salles"]
            morning = [c for c in dad if c.key.endswith(":bomdia")]
            self.assertEqual(len(morning), 1, d)
            self.assertTrue(7 <= morning[0].at.hour <= 11, d)

    def test_father_sends_food_money_on_mondays(self):
        for d in self.days:
            money = [c for c in self.day.plan(d) if c.key.endswith(":henrique_salles:mercado")]
            self.assertEqual(len(money), 1 if d.weekday() == 0 else 0, d)
            if money:
                self.assertIn("comida", money[0].topic)

    def test_father_calls_some_evenings(self):
        calls = [c for d in self.days for c in self.day.plan(d)
                 if c.character_key == "henrique_salles" and c.channel == "ligação"]
        self.assertTrue(3 <= len(calls) <= 11)

    def test_best_friend_talks_several_times_a_day(self):
        for d in self.days:
            bia = [c for c in self.day.plan(d) if c.character_key == "bia_andrade"]
            self.assertTrue(2 <= len(bia) <= 4, d)
            self.assertEqual(len({c.at for c in bia}), len(bia))


class SaudadeTest(_Base):
    def setUp(self):
        super().setUp()
        self.svc = ProactivityService(self.db)
        self.now = datetime(2026, 9, 23, 15, 0)

    def _msg(self, role, when, initiative=0):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO conversas (timestamp, role, content, is_initiative) VALUES (?,?,?,?)",
                         (when.isoformat(), role, "oi", initiative))
            conn.commit()

    def _state(self, activity, reason="free_time"):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_state (state_date, observed_at, activity, source_json) VALUES (?,?,?,?)",
                         (self.now.date().isoformat(), (self.now - timedelta(minutes=5)).isoformat(), activity,
                          '{"reason": "%s"}' % reason))
            conn.commit()

    def test_free_and_alone_she_looks_for_him_past_the_daily_cap(self):
        self._state("tempo livre em casa")
        for i in range(6):   # já estourou o teto antigo de 4, antes da última fala dele
            self._msg("assistant", self.now - timedelta(hours=8, minutes=i), initiative=1)
        self._msg("user", self.now - timedelta(hours=4))
        self.assertEqual(self.svc.should_trigger(self.now), (True, "saudade"))

    def test_short_absence_is_not_saudade(self):
        self._state("tempo livre em casa")
        self._msg("user", self.now - timedelta(hours=1))
        self.assertFalse(self.svc.saudade(self.now)["trigger"])

    def test_busy_or_asleep_she_does_not(self):
        self._msg("user", self.now - timedelta(hours=6))
        self._state("na faculdade, aula de Tipografia")
        self.assertFalse(self.svc.saudade(self.now)["trigger"])

    def test_unanswered_messages_make_her_wait_longer_then_stop(self):
        self._state("tempo livre em casa")
        self._msg("user", self.now - timedelta(hours=6))
        self._msg("assistant", self.now - timedelta(minutes=SAUDADE_BACKOFF_MINUTES - 10), initiative=1)
        self.assertFalse(self.svc.saudade(self.now)["trigger"])
        later = self.now + timedelta(minutes=20)
        self.assertTrue(self.svc.saudade(later)["trigger"])
        self._msg("assistant", later, initiative=1)
        self.assertFalse(self.svc.saudade(later + timedelta(minutes=SAUDADE_BACKOFF_MINUTES + 10))["trigger"])
        self.assertTrue(self.svc.saudade(later + timedelta(minutes=2 * SAUDADE_BACKOFF_MINUTES + 10))["trigger"])
        self._msg("assistant", later + timedelta(hours=4), initiative=1)
        self.assertFalse(self.svc.saudade(later + timedelta(hours=20))["trigger"], "três sem resposta: para")

    def test_his_reply_resets_everything(self):
        self._state("tempo livre em casa")
        self._msg("user", self.now - timedelta(hours=6))
        for i in range(3):
            self._msg("assistant", self.now - timedelta(hours=5 - i), initiative=1)
        self.assertEqual(self.svc.saudade(self.now)["unanswered"], 3)
        self._msg("user", self.now - timedelta(minutes=1))
        self.assertEqual(self.svc.saudade(self.now)["unanswered"], 0)


if __name__ == "__main__":
    unittest.main()
