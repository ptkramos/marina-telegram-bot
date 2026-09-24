"""Promessa de avisar quando chegar — caso real de 23/09 ("te aviso assim que chegar no shopping")."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import arrival_promise
from commute import Leg
from db import DatabaseManager

NOW = datetime(2026, 9, 23, 15, 8)
IDA = Leg("commute:outing:2026-09-23:1:ida", datetime(2026, 9, 23, 15, 5), datetime(2026, 9, 23, 15, 30),
          "uber", "ida", "pro Shopping da Gávea", "Gávea")
VOLTA = Leg("commute:outing:2026-09-23:1:volta", datetime(2026, 9, 23, 18, 15), datetime(2026, 9, 23, 18, 45),
            "metro", "volta", "do Shopping da Gávea", "Gávea")


class ArrivalPromiseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "a.db")
        p = patch("commute.Commute.legs_on", side_effect=lambda day: [IDA, VOLTA] if day == NOW.date() else [])
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _kept(self, forget=False):
        with patch.object(arrival_promise, "FORGET_CHANCE", 1.0 if forget else 0.0):
            return arrival_promise.observe(self.db, "Verdade, amor, confundi! Te aviso assim que chegar no shopping, prometo",
                                           "Chegar em casa não princesa, quando chegar no shopping!", NOW)

    def test_the_shopping_promise_is_kept_when_she_arrives(self):
        promise = self._kept()
        self.assertEqual(promise["where"], "no Shopping da Gávea")
        self.assertIsNone(arrival_promise.due(self.db, IDA.end - timedelta(minutes=1)), "ainda no caminho")
        kept = arrival_promise.due(self.db, IDA.end + timedelta(minutes=7))
        self.assertEqual(kept["where"], "no Shopping da Gávea")
        self.assertIsNone(arrival_promise.due(self.db, IDA.end + timedelta(minutes=12)), "avisa uma vez só")

    def test_home_promise_targets_the_way_back(self):
        promise = arrival_promise.observe(self.db, "Aviso sim, amor. E vou direto comer quando chegar",
                                          "Hmm, tá bom, avisa mesmo em! quando chegar em casa", NOW.replace(hour=18, minute=20))
        self.assertEqual(promise["where"], "em casa")
        self.assertEqual(promise["leg"], VOLTA.key)

    def test_sometimes_she_forgets(self):
        self._kept(forget=True)
        self.assertIsNone(arrival_promise.due(self.db, IDA.end + timedelta(minutes=7)))

    def test_no_double_notice_if_she_already_said_she_arrived(self):
        self._kept()
        self.db.adicionar_mensagem(role="assistant", content="Cheguei sim, amor, tô aqui no Starbucks",
                                   timestamp=(IDA.end + timedelta(minutes=1)).isoformat())
        self.assertIsNone(arrival_promise.due(self.db, IDA.end + timedelta(minutes=7)))

    def test_not_a_promise(self):
        self.assertIsNone(arrival_promise.observe(self.db, "Kkkkk manda mesmo, amor", "vou te mandar foto", NOW))


if __name__ == "__main__":
    unittest.main()
