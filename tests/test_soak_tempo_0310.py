"""Soak, dia 5 (sábado 03/10): o tempo do Rio no dia de chuva.

O Patrick: "o tempo hoje no Rio ficou chuvoso o tempo todo e a Marina andou na chuva e agora tá pegando sol".
Open-Meteo: chuva (códigos 61–80) das 6h às 10h, garoa densa depois, 100% de nuvens o dia inteiro.
- 08:52–09:30 passeio do Milo na Enseada com o mundo SEM tempo (o tempo só era lido no turno do Patrick, e ele ainda
  não tinha escrito); ela disse "O dia tá bonito demais" e "tá um solzinho agora".
- 14:37 "em casa, tomando sol (piscina do prédio)" com `condition: drizzle` na mesma linha do world_state.
"""
import inspect
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from tempo_livre import TIPOS, TempoLivre
from vontade import Vontade


def _com_tempo(db, cond):
    w = json.dumps({"heavy_rain": False, "temperature_c": 20.6, "condition": cond})
    p = patch.object(db, "get_connection")
    gc = p.start()
    gc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {"weather_context_json": w}
    return p


class SolSoComCeuLimpoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "t.db")

    def test_sol_e_ceu_limpo(self):
        for cond, esperado in (("clear", True), ("cloudy", False), ("drizzle", False), ("rain", False),
                               ("storm", False), ("unknown", False)):
            p = _com_tempo(self.db, cond)
            try:
                for mod in (TempoLivre(self.db), Vontade(self.db)):
                    self.assertEqual(mod._sol(), esperado, (type(mod).__name__, cond))
            finally:
                p.stop()

    def test_sem_tempo_conhecido_nao_tem_sol(self):
        self.assertFalse(TempoLivre(self.db)._sol())
        self.assertFalse(Vontade(self.db)._sol())


class TomarSolNaGaroaTest(unittest.TestCase):
    """O caso das 14:37: com garoa, nenhum bloco do dia vira "Tomando sol"."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "t.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) "
                         "VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        for alvo, kw in (("tempo_livre.TempoLivre._quer_se_masturbar", {"return_value": None}),
                         ("unhas.Unhas.quer_em_casa", {"return_value": False}),
                         ("cabelo.Cabelo.quer_umectar", {"return_value": False})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)

    def _textos(self, sol: bool) -> set:
        textos = set()
        with patch.object(TempoLivre, "_sol", return_value=sol):
            for dia in range(1, 29):
                for h in range(9, 16):
                    b = TempoLivre(self.db)._escolhe(datetime(2026, 9, dia, h, 0), h, datetime(2026, 9, dia, h, 0),
                                                     datetime(2026, 9, dia, h, 59), registrar=False)
                    textos.add(b.texto)
        return textos

    def test_garoa_nao_toma_sol(self):
        self.assertNotIn("Tomando sol", self._textos(sol=False))

    def test_ceu_limpo_ainda_toma_sol(self):
        self.assertIn("Tomando sol", self._textos(sol=True))


class GaroaDensaEChuvaTest(unittest.TestCase):
    """Decisão do Patrick (03/10): a garoa densa das 11h em diante (código 55, 0,3 mm a cada 15 min) é chuva —
    tira a caminhada e pesa contra sair; garoa fraca/moderada continua chuvisco."""

    def test_codigos(self):
        from real_context_provider import _condicao
        self.assertEqual(_condicao(55, 0.3), "rain")
        self.assertEqual(_condicao(57, 0.3), "rain")
        self.assertEqual(_condicao(53, 0.2), "drizzle")
        self.assertEqual(_condicao(51, 0.1), "drizzle")
        self.assertEqual(_condicao(3, 0), "cloudy")


class PraiaSoComSolTest(unittest.TestCase):
    def test_praia_pede_sol(self):
        fonte = inspect.getsource(Vontade._pesos)
        self.assertIn('(tipo == "praia" and not sol)', fonte)


class TempoForaDoTurnoTest(unittest.TestCase):
    def test_job_do_tempo_agendado(self):
        import bot
        fonte = inspect.getsource(bot)
        self.assertIn("scheduler.add_job(tempo_real_routine", fonte)
        self.assertIn("RealContextProvider(memory_manager.db).refresh", inspect.getsource(bot.tempo_real_routine))


if __name__ == "__main__":
    unittest.main()
