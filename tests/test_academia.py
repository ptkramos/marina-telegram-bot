"""Academia como compromisso (Patrick, 26/09: "ela foi treinar e não teve preparação? nem barra de progresso?")."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from academia import Academia
from agenda import Agenda
from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible

PLANO_REAL = Academia.plano
DIA = datetime(2026, 9, 26)
TREINO = {"inicio": DIA.replace(hour=15, minute=10), "fim": DIA.replace(hour=16, minute=25), "onde": "rua"}


class AcademiaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "g.db")
        seed_world_bible(self.db)
        for alvo, kw in (("academia.Academia.plano", {"side_effect": lambda day, now=None: TREINO if day == DIA.date() else None}),
                         ("academic_life.AcademicLife.blocks_on", {"return_value": []}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("meals.Meals.day_plan", {"return_value": []})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)

    def test_etapas_do_treino(self):
        etapas = Agenda(self.db).etapas(DIA.date(), DIA.replace(hour=17))
        self.assertEqual([e.titulo for e in etapas], ["Se arrumando", "A caminho", "Na academia", "Voltando para casa"])
        prep, ida, la, volta = etapas
        self.assertEqual([p.texto for p in prep.passos], ["Colocando roupa de treino", "Enchendo a garrafinha", "Saindo"])
        self.assertEqual(prep.fim, TREINO["inicio"] - timedelta(minutes=12))
        self.assertEqual(ida.como, "A pé")
        self.assertEqual((la.inicio, la.fim), (TREINO["inicio"], TREINO["fim"]))
        self.assertEqual(la.passos[0].texto, "Fazendo cardio na esteira")
        self.assertEqual(volta.fim, TREINO["fim"] + timedelta(minutes=12))

    def test_card_na_academia_tem_barra(self):
        c = Agenda(self.db).card(DIA.replace(hour=15, minute=40))
        self.assertEqual((c["titulo"], c["linha2"]), ("Na academia", "Volta para casa por volta das 16:25"))
        self.assertEqual(c["barra"]["meio"].split(", ")[0], "há 30 minutos")
        self.assertIsNotNone(c["barra"]["pct"])
        self.assertIn(["device-mobile", "Celular", "Pega nos intervalos"], c["grade"])
        atual = next(e for e in c["linha"] if e["estado"] == "agora")
        self.assertTrue(atual["passos"])

    def test_se_arrumando_antes(self):
        act = Agenda(self.db).prep_activity(TREINO["inicio"] - timedelta(minutes=20))
        self.assertTrue(act["activity"].startswith("se arrumando pra sair"), act)

    def test_plano_fica_guardado(self):
        with patch("academia.Academia.plano", PLANO_REAL), \
                patch("academia.Academia._decide", return_value=TREINO) as decide:
            a = Academia(self.db).plano(DIA.date(), DIA)
            b = Academia(self.db).plano(DIA.date(), DIA + timedelta(hours=3))
        self.assertEqual(a, b)
        self.assertEqual(decide.call_count, 1, "decidido uma vez só no dia")


if __name__ == "__main__":
    unittest.main()
