"""Aba Por fora dos Bastidores (Patrick, 28/09): a aparência dela sai do Por dentro — Peso, Cabelo e Unhas.
O Peso mostra o de verdade (ela só sabe o da balança), a folga até o limite da agência, Pesou, Dieta e Altura."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from db import DatabaseManager
from meals import Meals

AGORA = datetime(2026, 9, 28, 13, 0)   # segunda


class PesoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(Path(self.tmp.name) / "p.db")

    def _peso(self, **data):
        self.db.set_estado_relacional(Meals.WEIGHT_KEY, json.dumps(data))
        return Meals(self.db).painel_peso(AGORA)

    def test_peso_real_folga_e_pesagem_de_sabado(self):
        p = self._peso(kg=54.4, known_kg=54.0, known_at="2026-09-26T16:30:07")
        self.assertEqual(p["kg"], "54,4 kg")
        self.assertEqual(p["palavra"], "Folga 1,6 kg")
        self.assertEqual(p["barra"], 0.6)
        self.assertFalse(p["alerta"])
        self.assertEqual(p["linhas"], [["scale", "Pesou", "Sáb, 54,0 kg"], ["salad", "Dieta", "Não"],
                                       ["ruler-2", "Altura", "1,68 m"]])

    def test_passou_do_limite_fica_amarela_e_mostra_a_dieta(self):
        p = self._peso(kg=56.3, known_kg=56.3, known_at="2026-09-28T10:00:00", diet_until="2026-10-03")
        self.assertEqual(p["palavra"], "Passou 0,3 kg")
        self.assertTrue(p["alerta"])
        self.assertEqual(p["barra"], 1.0)
        self.assertEqual(p["linhas"][0][2], "Hoje, 56,3 kg")
        self.assertEqual(p["linhas"][1][2], "Até 03/10")

    def test_sem_pesagem_e_dieta_vencida(self):
        p = self._peso(kg=51.5, diet_until="2026-09-20")
        self.assertEqual(p["barra"], 0.0)
        self.assertEqual(p["linhas"][0][2], "Ainda não")
        self.assertEqual(p["linhas"][1][2], "Não")

    def test_pesagem_antiga_vira_ha_n_dias(self):
        p = self._peso(kg=54.0, known_kg=54.2, known_at="2026-09-15T18:00:00")
        self.assertEqual(p["linhas"][0][2], "Há 13 dias, 54,2 kg")


class TelaTest(unittest.TestCase):
    def test_unhas_e_cabelo_mudaram_de_aba(self):
        html = (Path(__file__).resolve().parents[1] / "webapp" / "index.html").read_text(encoding="utf-8")
        dentro = html.split('id="ba-dentro"')[1].split('id="ba-fora"')[0]
        fora = html.split('id="ba-fora"')[1].split('id="ba-dinheiro"')[0]
        self.assertNotIn("bd-unhas", dentro)
        self.assertNotIn("bd-cabelo", dentro)
        self.assertLess(fora.index("bf-peso"), fora.index("bd-cabelo"))
        self.assertLess(fora.index("bd-cabelo"), fora.index("bd-unhas"))
        self.assertIn('data-bast="fora">Por fora<', html)


if __name__ == "__main__":
    unittest.main()
