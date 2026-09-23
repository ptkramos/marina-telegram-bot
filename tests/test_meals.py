"""Refeições: "vou jantar agora" vira estado (soak de 22/09)."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from db import DatabaseManager
from meals import Meals, announces_meal, meal_kind
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from social_day import SocialDay


class AnnouncementTest(unittest.TestCase):
    def test_soak_lines_that_announce(self):
        for fala in [
            "Você tem razão, amor, não quero te deixar preocupado comigo. Vou comer agora, prometo.",
            "Falo sim, amor. Vou comer agora e depois te conto direitinho",
            "Ainda não, amor, mas vou jantar agora. Depois te conto o que eu comi direitinho, prometo.",
            "Eu me distraí falando com você, mas vou jantar agora de verdade",
            "vou lá esquentar minha comida rapidinho",
        ]:
            with self.subTest(fala=fala):
                self.assertTrue(announces_meal(fala))

    def test_not_immediate(self):
        for fala in [
            "Ainda não, amor kkkk. Vou comer assim que você chegar bem em casa.",
            "Tá bom, amor, vou comer direitinho sim.",
            "sexta vou jantar com a Bia",
        ]:
            with self.subTest(fala=fala):
                self.assertFalse(announces_meal(fala))

    def test_meal_kind_by_hour(self):
        self.assertEqual(meal_kind(datetime(2026, 9, 22, 12, 30)), "almoco")
        self.assertEqual(meal_kind(datetime(2026, 9, 22, 21, 14)), "jantar")
        self.assertEqual(meal_kind(datetime(2026, 9, 22, 16, 0)), "lanche")


class MealStateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "meals.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.meals = Meals(self.db)
        self.now = datetime(2026, 9, 22, 21, 14)

    def tearDown(self):
        self.temp.cleanup()

    def _payload(self):
        return json.loads(self.db.get_estado_relacional()["pending_transition_json"])

    def test_promise_opens_a_real_dinner(self):
        payload = self.meals.observe_marina_line("Vou comer agora, prometo", self.now)
        self.assertEqual(payload["activity"], "jantando em casa")
        start = datetime.fromisoformat(payload["transition_at"])
        end = datetime.fromisoformat(payload["end_at"])
        self.assertTrue(timedelta(minutes=2) <= start - self.now <= timedelta(minutes=5))
        self.assertTrue(timedelta(minutes=20) <= end - start <= timedelta(minutes=35))
        self.assertEqual(self._payload()["dish"], payload["dish"])

    def test_repeating_the_promise_does_not_open_another_dinner(self):
        first = self.meals.observe_marina_line("Vou comer agora, prometo", self.now)
        again = self.meals.observe_marina_line("vou jantar agora de verdade", self.now + timedelta(minutes=70))
        self.assertIsNone(again)
        self.assertEqual(self._payload()["transition_at"], first["transition_at"])

    def test_dinner_enters_her_day_only_once_it_starts(self):
        payload = self.meals.observe_marina_line("vou jantar agora", self.now)
        start = datetime.fromisoformat(payload["transition_at"])
        day = SocialDay(self.db)
        self.assertEqual(day.today_so_far(self.now), [])
        later = day.today_so_far(start + timedelta(minutes=40))
        self.assertEqual(len(later), 1)
        self.assertIn(payload["dish"], later[0]["summary"])
        self.assertTrue(later[0]["summary"].startswith("Jantar em casa"))

    def test_shower_in_progress_wins(self):
        self.db.set_estado_relacional("pending_transition_json", json.dumps({
            "routine_type": "shower", "activity": "tomando banho",
            "transition_at": self.now.isoformat(), "end_at": (self.now + timedelta(minutes=20)).isoformat()}))
        self.assertIsNone(self.meals.observe_marina_line("vou comer agora", self.now))
        self.assertEqual(self._payload()["activity"], "tomando banho")

    def test_eating_is_neither_instant_nor_gone(self):
        from response_availability import DEFAULT_PROFILES, ResponseAvailabilityPolicy
        policy = ResponseAvailabilityPolicy(self.db)
        self.assertEqual(policy._map_place_activity("marina_apartment", "jantando em casa"), "MEAL")
        self.assertGreaterEqual(DEFAULT_PROFILES["MEAL"]["soft_delay_min_s"], 30)
        payload = self.meals.observe_marina_line("vou jantar agora", self.now)
        during = datetime.fromisoformat(payload["transition_at"]) + timedelta(minutes=5)
        decision = policy.evaluate("já jantou?", now=during, telegram_message_id=11)
        self.assertEqual(decision.activity_type, "MEAL")
        self.assertGreaterEqual((decision.selected_target_at - during).total_seconds(), 30)


if __name__ == "__main__":
    unittest.main()
