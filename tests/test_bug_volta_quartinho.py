"""Bug do uso real: volta do Quartinho Bar (26→27/09), com as falas e os horários do caso.

- 20:19–20:20 ele pediu "vai e volta de uber", ela prometeu, e a ida saiu a pé (20:48–21:00).
- 21:39 ela prometeu "te aviso assim que chegar em casa"; a volta (uber dividido com a Bia) foi 23:59–00:05
  e ela não avisou: a promessa nem foi gravada (volta fora dos 90 min).
- 00:19, já em casa, disse "vou pedir o Uber pra voltar": o prompt não dizia de onde nem como ela voltou.
"""
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import arrival_promise
from agenda_reativa import AgendaReativa
from commute import Commute, Leg
from db import DatabaseManager
from world_context import WorldContextBuilder

DIA = date(2026, 9, 26)
IDA = Leg("commute:outing:2026-09-26:c1:ida", datetime(2026, 9, 26, 20, 48), datetime(2026, 9, 26, 21, 0),
          "a_pe", "ida", "pro Quartinho Bar", "Botafogo")
VOLTA = Leg("commute:outing:2026-09-26:c1:volta", datetime(2026, 9, 26, 23, 59), datetime(2026, 9, 27, 0, 5),
            "uber_dividido", "volta", "do Quartinho Bar", "Botafogo", companion="a Bia")


class VoltaDoQuartinhoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "q.db")
        p = patch("commute.Commute.legs_on", side_effect=lambda day: [IDA, VOLTA] if day == DIA else [])
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_promessa_de_avisar_em_casa_as_2139_amarra_na_volta_das_2359(self):
        promise = arrival_promise.observe(
            self.db, "Tá bom, eu te aviso assim que chegar em casa / Prometo não sumir de novo, pode deixar kkk",
            "tá difícil de lidar com vc em mulher... avisa quando chegar em casa pelo menos",
            datetime(2026, 9, 26, 21, 39, 50))
        self.assertEqual(promise["leg"], VOLTA.key)
        self.assertEqual(promise["where"], "em casa")
        self.assertIsNone(arrival_promise.due(self.db, datetime(2026, 9, 27, 0, 4)), "ainda no uber")
        self.assertIsNotNone(arrival_promise.due(self.db, datetime(2026, 9, 27, 0, 12)), "chegou: avisa")

    def test_vai_e_volta_de_uber_troca_a_ida_a_pe(self):
        r = AgendaReativa(self.db)
        self.assertEqual(r.combinar_uber("Pode deixar, amor, volto de Uber 🖤",
                                         "Ok, usa o dinheiro p uber também em, tá de noite já\n"
                                         "N quero você andando a pé a noite", datetime(2026, 9, 26, 20, 19, 42)),
                         [], "a volta já era uber dividido")
        trocados = r.combinar_uber("Pode deixar, amor, obrigada pelo cuidado",
                                   "Vai também! Vai e volta de uber, se precisar de mais dinheiro avisa",
                                   datetime(2026, 9, 26, 20, 20, 25))
        self.assertEqual(trocados, [IDA.key])
        ida, volta = Commute(self.db)._voltas_trocadas([IDA, VOLTA])
        self.assertEqual(ida.mode, "uber")
        self.assertEqual(ida.end, IDA.end, "chega no bar na mesma hora")
        self.assertLess(ida.end - ida.start, IDA.end - IDA.start)
        self.assertEqual((volta.mode, volta.companion), ("uber_dividido", "a Bia"), "volta intacta")

    def test_nao_troca_sem_ela_topar(self):
        r = AgendaReativa(self.db)
        self.assertEqual(r.combinar_uber("Não precisa, amor, é pertinho", "vai de uber",
                                         datetime(2026, 9, 26, 20, 20)), [])
        self.assertEqual(r.combinar_uber("Pode deixar", "te amo", datetime(2026, 9, 26, 20, 20)), [])

    def test_so_a_volta_quando_ele_fala_so_da_volta(self):
        ida_uber = Leg(IDA.key, IDA.start, IDA.end, "a_pe", "ida", IDA.destination, IDA.region)
        volta_pe = Leg(VOLTA.key, VOLTA.start, VOLTA.end, "a_pe", "volta", VOLTA.destination, VOLTA.region)
        with patch("commute.Commute.legs_on", side_effect=lambda day: [ida_uber, volta_pe] if day == DIA else []):
            trocados = AgendaReativa(self.db).combinar_uber("Tá bom, volto de uber", "na volta pega um uber",
                                                            datetime(2026, 9, 26, 20, 20))
        self.assertEqual(trocados, [VOLTA.key])

    def test_prompt_diz_que_ela_ja_chegou_e_como(self):
        chegada = WorldContextBuilder(self.db)._chegada(datetime(2026, 9, 27, 0, 19))
        self.assertIn("do Quartinho Bar", chegada)
        self.assertIn("dividindo um uber com a Bia", chegada)
        self.assertIn("00:05", chegada)
        self.assertIn("JÁ ESTÁ EM CASA", chegada)
        self.assertIsNone(WorldContextBuilder(self.db)._chegada(datetime(2026, 9, 27, 0, 3)), "ainda no caminho")
        self.assertIsNone(WorldContextBuilder(self.db)._chegada(datetime(2026, 9, 27, 1, 30)), "já faz tempo")


if __name__ == "__main__":
    unittest.main()
