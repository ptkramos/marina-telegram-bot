"""/pix e o dinheiro dela (Patrick, 24/09): presente vira compra; aperto → pede pra ele; devolve no cachê."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import financas
from db import DatabaseManager
from emotion import appraise_event

T = datetime(2026, 9, 25, 10, 0)


def _life(db, key, at, summary):
    with db.get_connection() as conn:
        conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                        autonomy_level,importance,participants_json,share_worthy,created_at)
                        VALUES (?,?,'routine','x',?,'simulated',1,0.1,'["marina"]',0.3,?)""",
                     (key, at.isoformat(), summary, at.isoformat()))
        conn.commit()


class FinancasTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "f.db")
        p = patch.object(financas, "EMERGENCY_WEEKLY_CHANCE", 0.0)
        p.start()
        self.addCleanup(p.stop)
        financas.materialize(self.db, T)

    def tearDown(self):
        self.temp.cleanup()

    def st(self):
        return json.loads(self.db.get_estado_relacional(financas.KEY))

    def test_world_moves_the_balance(self):
        _life(self.db, "freela:2026-09-20:sinal", T + timedelta(hours=1), "A Lívia fez o pix de metade do cachê (x): R$ 450.")
        _life(self.db, "casa:2026-09-25:contas_dela", T + timedelta(hours=2), "Pagou as contas dela.")
        _life(self.db, "meal:2026-09-25:jantar:delivery", T + timedelta(hours=3), "O açaí do delivery chegou.")
        financas.materialize(self.db, T + timedelta(hours=4))
        self.assertEqual(self.st()["saldo"], financas.START_BALANCE + 450 - financas.CONTAS_DELA - 38)
        financas.materialize(self.db, T + timedelta(hours=5))
        self.assertEqual(self.st()["saldo"], financas.START_BALANCE + 450 - financas.CONTAS_DELA - 38, "idempotente")

    def test_gift_becomes_a_purchase_she_tells_about(self):
        res = financas.receive_pix(self.db, 120, "pra você se mimar", T)
        self.assertEqual(res["kind"], "presente")
        self.assertIn("skincare", self.st()["presente"]["uso"])
        financas.materialize(self.db, T + timedelta(hours=21))
        self.assertIsNone(self.st()["presente"])
        with self.db.get_connection() as conn:
            used = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'financas:%:presente_usado'").fetchone()
        self.assertIn("pix do Patrick", used[0])

    def test_emergency_goes_to_patrick_first_and_is_repaid(self):
        with patch.object(financas, "EMERGENCY_WEEKLY_CHANCE", 1.0):
            financas.materialize(self.db, datetime(2026, 10, 4, 23, 30))
        pedido = self.st()["pedido"]
        self.assertTrue(pedido)
        lines = " ".join(financas.prompt_lines(self.db, datetime(2026, 10, 4, 23, 30)))
        self.assertIn("Patrick", lines)
        self.assertIn("devolver", lines)
        res = financas.receive_pix(self.db, pedido["valor"], "", datetime(2026, 10, 4, 23, 40))
        self.assertEqual(res["kind"], "emprestimo")
        self.assertIsNone(self.st()["pedido"])
        _life(self.db, "freela:2026-10-10:cache", datetime(2026, 10, 5, 12, 0), "Caiu o resto do cachê: R$ 900.")
        financas.materialize(self.db, datetime(2026, 10, 5, 13, 0))
        self.assertTrue(all(e.get("devolvido_at") for e in self.st()["emprestimos"]))

    def test_running_out_of_money_asks_patrick(self):
        for i in range(6):
            _life(self.db, f"casa:2026-09-2{i}:contas_dela", T + timedelta(minutes=i + 1), "Pagou as contas dela.")
        financas.materialize(self.db, T + timedelta(hours=1))
        self.assertIn("acabou", self.st()["pedido"]["motivo"])

    def test_parse_value(self):
        self.assertEqual(financas.parse_value("50"), 50)
        self.assertEqual(financas.parse_value("R$ 49,90 pro açaí"), 50)
        self.assertIsNone(financas.parse_value("pro açaí"))

    def test_she_feels_it(self):
        ev = lambda key, text: [k for _, k, *_ in appraise_event({"event_key": key, "event_type": "money", "summary": text})]
        self.assertIn("gratidao", ev("financas:2026-09-25T1000:pix", "O Patrick fez um pix de R$ 50 pra ela de presente."))
        self.assertIn("preocupacao", ev("financas:2026-09-25:emergencia", "Aperto: a tela trincou."))
        self.assertIn("alivio", ev("financas:2026-09-26T1000:devolveu", "Devolveu."))


if __name__ == "__main__":
    unittest.main()
