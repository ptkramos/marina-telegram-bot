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

    def test_only_real_orders(self):
        self.assertFalse(delivery.observe(self.db, "pedi desculpa pra Bia", T))
        self.assertFalse(delivery.observe(self.db, "Açaí é uma ótima ideia", T))

    def test_eating_now_is_recognized(self):
        for line in ("Vou ficar aqui jantando e pensando em você", "Tô engolindo correndo kkkk",
                     "tô comendo meu açaí"):
            self.assertTrue(MEAL_NOW_RE.search(line), line)


if __name__ == "__main__":
    unittest.main()
