"""24/09 — delivery de verdade: 'vou pedir pelo iFood' vira pedido, chega e ela come."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import delivery
from db import DatabaseManager
from meals import MEAL_NOW_RE, Meals

T = datetime(2026, 9, 24, 19, 13)


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "d.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_order_arrives_and_she_eats(self):
        self.assertTrue(delivery.observe(self.db, "Tá bom, vou pedir pelo iFood então", T,
                                         context="Açaí é uma ótima ideia"))
        waiting = delivery.prompt_lines(self.db, T + timedelta(minutes=10))[0]
        self.assertIn("pediu açaí às 19:13", waiting)
        self.assertIn("ainda não chegou", waiting)
        self.assertFalse(delivery.observe(self.db, "vou pedir uma pizza", T + timedelta(minutes=5)), "um por vez")
        later = T + timedelta(minutes=60)
        self.assertTrue(delivery.materialize(self.db, later - timedelta(minutes=10)))
        self.assertIn("chegou", delivery.prompt_lines(self.db, later)[0])
        state = json.loads(self.db.get_estado_relacional()["pending_transition_json"])
        self.assertEqual(state["activity"], "comendo o açaí em casa")
        self.assertTrue(Meals(self.db)._logged(T.date(), "jantar"), "o açaí é o jantar dela")
        self.assertEqual(delivery.prompt_lines(self.db, later + timedelta(hours=3)), [])

    def test_pegar_na_portaria_e_contato_com_o_seu_jorge(self):
        """26/09 (Patrick): pegou a comida com o Seu Jorge, mas o Mundo dizia 'sem contato'."""
        import canon_extras
        from seed_world_bible_v36 import seed_world_bible
        from social_world import seed_social
        seed_world_bible(self.db)
        seed_social(self.db)
        canon_extras.ensure(self.db)
        delivery.gift(self.db, what="Cappuccino", restaurant="Rei do Mate", price=40, eta_min=(20, 20), note="", now=T)
        delivery.gift_tick(self.db, T + timedelta(minutes=21), can_receive=False, why_not="dormindo")
        delivery.gift_tick(self.db, T + timedelta(hours=2), can_receive=True)
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT last_interaction_at, contact_frequency FROM social_relationships "
                               "WHERE character_key='jorge_almeida'").fetchone()
        self.assertEqual(row["last_interaction_at"], (T + timedelta(hours=2)).isoformat())
        self.assertEqual(row["contact_frequency"], 1)

    def test_only_real_orders(self):
        self.assertFalse(delivery.observe(self.db, "pedi desculpa pra Bia", T))
        self.assertFalse(delivery.observe(self.db, "Açaí é uma ótima ideia", T))

    def test_eating_now_is_recognized(self):
        for line in ("Vou ficar aqui jantando e pensando em você", "Tô engolindo correndo kkkk",
                     "tô comendo meu açaí"):
            self.assertTrue(MEAL_NOW_RE.search(line), line)


if __name__ == "__main__":
    unittest.main()
