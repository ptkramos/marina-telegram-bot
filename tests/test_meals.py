"""Refeições: "vou jantar agora" vira estado (soak de 22/09)."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from db import DatabaseManager
from unittest.mock import patch

from meals import MENU, Meals, announces_meal, meal_kind
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
        self.assertEqual(self.meals.eaten_today(self.now), [])
        later = self.meals.eaten_today(start + timedelta(minutes=40))
        self.assertEqual(len(later), 1)
        self.assertIn(payload["dish"], later[0]["summary"])
        self.assertTrue(later[0]["summary"].startswith("Jantar em casa"))
        # A comida tem bloco próprio: não disputa as vagas do "seu dia" social.
        self.assertEqual(SocialDay(self.db).today_so_far(start + timedelta(minutes=40)), [])

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


class FoodDayTest(unittest.TestCase):
    """Fase D1 — o dia de comida dela existe no mundo, com fome, disfarce, dieta e peso."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "d1.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        self.meals = Meals(self.db)
        self.days = [datetime(2026, 9, 21).date() + timedelta(days=i) for i in range(14)]

    def tearDown(self):
        self.temp.cleanup()

    def _slot(self, day, kind):
        return next(s for s in self.meals.day_plan(day) if s.kind == kind)

    def _state(self, when, activity):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_state (state_date, observed_at, activity, source_json) VALUES (?,?,?,?)",
                         (when.date().isoformat(), when.isoformat(), activity, "{}"))
            conn.commit()

    def test_every_day_has_breakfast_lunch_and_dinner_at_plausible_varied_times(self):
        dinners = set()
        for day in self.days:
            plan = {s.kind: s for s in self.meals.day_plan(day)}
            self.assertTrue({"cafe", "almoco", "jantar"} <= set(plan), day)
            self.assertLess(plan["cafe"].at, plan["almoco"].at)
            self.assertLess(plan["almoco"].at, plan["jantar"].at)
            self.assertTrue(19 <= plan["jantar"].at.hour <= 22, day)
            dinners.add(plan["jantar"].at.strftime("%H:%M"))
        self.assertGreater(len(dinners), 5, "horário do jantar não pode ser fixo")

    def test_class_day_lunch_is_at_puc_or_gavea(self):
        day = next(d for d in self.days if self.meals._blocks(d)
                   and self.meals._blocks(d)[-1][1].hour <= 15)
        lunch = self._slot(day, "almoco")
        self.assertIn(lunch.where, ("puc", "gavea"))

    def test_dinner_happens_even_without_promise(self):
        """Arena companhia_caminho: sem jantar no mundo, o modelo inventava um."""
        day = self.days[1]
        dinner = self._slot(day, "jantar")
        before = dinner.at - timedelta(minutes=1)
        self.meals.materialize(before)
        self.assertNotIn("jantar", {e["event_key"].split(":")[2] for e in self.meals.eaten_today(before)})
        if before.hour >= 19:
            self.assertIn("ainda não jantou", "\n".join(self.meals.prompt_lines(before)))
        during = dinner.at + timedelta(minutes=5)
        self.meals.materialize(during)
        self.assertIn("jantar", {e["event_key"].split(":")[2] for e in self.meals.eaten_today(during)})
        state = json.loads(self.db.get_estado_relacional()["pending_transition_json"])
        self.assertEqual(state["activity"], "jantando em casa")
        self.assertIn(dinner.dish, "\n".join(self.meals.prompt_lines(during)))

    def test_promise_moves_dinner_earlier_and_never_duplicates_it(self):
        day = next(d for d in self.days if self._slot(d, "jantar").at.hour >= 20)
        dinner = self._slot(day, "jantar")
        early = datetime.combine(day, datetime.min.time()).replace(hour=19, minute=5)
        self.assertIsNotNone(self.meals.observe_marina_line("vou jantar agora", early))
        self.meals.materialize(dinner.at + timedelta(minutes=5))
        jantares = [e for e in self.meals.eaten_today(dinner.at + timedelta(minutes=5))
                    if e["event_key"].split(":")[2] == "jantar"]
        self.assertEqual(len(jantares), 1)

    def test_hunger_grows_with_time_and_drops_after_eating(self):
        day = self.days[2]
        lunch = self._slot(day, "almoco")
        self.meals.materialize(lunch.at + timedelta(minutes=1))
        right_after = self.meals.hunger(lunch.at + timedelta(minutes=30))
        later = self.meals.hunger(lunch.at + timedelta(hours=5))
        self.assertLess(right_after, 0.3)
        self.assertGreater(later, right_after + 0.4)

    def test_disguise_mode_only_when_hungry(self):
        day = next(d for d in self.days if self.meals.disguises_today(d))
        dinner = self._slot(day, "jantar")
        hungry_at = dinner.at - timedelta(minutes=2)
        self.meals.materialize(hungry_at)
        with patch.object(Meals, "hunger", return_value=0.9):
            self.assertIn("modo disfarce", "\n".join(self.meals.prompt_lines(hungry_at)))
        with patch.object(Meals, "hunger", return_value=0.1):
            self.assertNotIn("modo disfarce", "\n".join(self.meals.prompt_lines(hungry_at)))

    def test_weigh_in_above_range_brings_agency_and_diet(self):
        now = datetime(2026, 9, 23, 20, 0)
        week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
        self.db.set_estado_relacional(Meals.WEIGHT_KEY, json.dumps({"kg": 56.8, "week": week}))
        self._state(now - timedelta(hours=3), "treinando na academia")
        self._state(now - timedelta(hours=1), "tempo livre em casa")
        self.meals._weigh_in(now)
        with self.db.get_connection() as conn:
            summaries = [r[0] for r in conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'peso:%'")]
        self.assertTrue(any("56,8 kg" in s for s in summaries))
        self.assertTrue(any("Lívia" in s for s in summaries))
        self.assertTrue(self.meals.on_diet(now.date() + timedelta(days=2)))
        self.assertIn(self._slot(now.date() + timedelta(days=1), "jantar").dish, MENU["dieta"])
        self.assertIn("dieta", "\n".join(self.meals.prompt_lines(now)))
        self.meals._weigh_in(now + timedelta(hours=1))   # uma pesagem por semana
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM life_events WHERE event_key LIKE 'peso:%:peso'")
                             .fetchone()[0], 1)

    def test_underweight_is_health_not_agency(self):
        now = datetime(2026, 9, 23, 20, 0)
        week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
        self.db.set_estado_relacional(Meals.WEIGHT_KEY, json.dumps({"kg": 51.6, "week": week}))
        self._state(now - timedelta(hours=3), "treinando na academia")
        self._state(now - timedelta(hours=1), "tempo livre em casa")
        self.meals._weigh_in(now)
        self.assertFalse(self.meals.on_diet(now.date()))
        with self.db.get_connection() as conn:
            summaries = " ".join(r[0] for r in conn.execute("SELECT summary FROM life_events"))
        self.assertIn("tontura", summaries)
        self.assertNotIn("Lívia", summaries)

    def test_weight_moves_slowly(self):
        now = datetime(2026, 9, 28, 12, 0)
        self.db.set_estado_relacional(Meals.WEIGHT_KEY, json.dumps({"kg": 54.0, "week": "2026-W39"}))
        with self.db.get_connection() as conn:
            for i in range(12):
                conn.execute("INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,"
                             "autonomy_level,importance,participants_json,share_worthy,created_at) "
                             "VALUES (?,?,'snack','lanche','Beliscou.','simulated',1,0.1,'[]',0.1,?)",
                             (f"t:{i}", (now - timedelta(days=1, minutes=i)).isoformat(), now.isoformat()))
            conn.commit()
        self.meals._weekly_weight(now)
        kg = self.meals.weight()["kg"]
        self.assertGreater(kg, 54.0)
        self.assertLessEqual(kg, 54.6)


if __name__ == "__main__":
    unittest.main()
