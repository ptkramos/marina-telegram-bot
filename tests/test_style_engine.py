"""
Testes Unitários Automatizados para o StyleEngine 2.0 e MenstrualCycleManager da Marina Salles (v3.7.0).
"""
import sys
import unittest
import tempfile
from pathlib import Path
from datetime import date, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from style_engine import StyleEngine
from cycle import MenstrualCycleManager, PHASES


class TestStyleEngineV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_style.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.engine = StyleEngine(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_style_initialization(self):
        """Fresh DB must NOT receive fake learned Patrick observations."""
        estilo = self.db.get_estilo()
        self.assertFalse(estilo.get("risada"))
        self.assertEqual(self.engine.patrick_sample_count(), 0)
        self.assertFalse(self.engine.has_learned_style())
        self.assertEqual(self.engine.get_style_prompt_injection(), "")

    def test_laughter_accumulation_no_premature_overwrite(self):
        """Uma única risada isolada ('haha') não deve declarar dominância ainda."""
        self.engine.processar_mensagem_patrick("oi amor haha tudo bem")
        estilo = self.db.get_estilo()
        # P1.1: Below threshold — no dominance claimed without real evidence
        self.assertEqual(estilo["risada"]["valor"], "")
        self.assertEqual(estilo["risada"]["exemplos"].get("haha"), 1)
        self.assertFalse(self.engine.has_learned_style())

    def test_laughter_switches_when_predominantly_used(self):
        """Quando o Patrick usa repetidamente um padrão novo, a dominância estatística deve virar."""
        # Envia múltiplas mensagens com 'haha'
        for _ in range(8):
            self.engine.processar_mensagem_patrick("hahaha muito bom isso")

        estilo = self.db.get_estilo()
        self.assertEqual(estilo["risada"]["valor"], "haha")
        self.assertTrue(self.engine.has_learned_style())

    def test_emoji_frequency_ranking(self):
        """Os emojis mais frequentes devem aparecer no topo do ranking."""
        self.engine.processar_mensagem_patrick("te amo muito ❤️❤️❤️")
        self.engine.processar_mensagem_patrick("que linda ❤️")
        self.engine.processar_mensagem_patrick("olha isso 🔥")

        estilo = self.db.get_estilo()
        emojis_top = estilo["emojis_favoritos"]["valor"]
        self.assertTrue(emojis_top.startswith("❤️"))

    def test_slang_tracking_and_fechou(self):
        """Gírias catalogadas (incluindo 'fechou') devem ser rastreadas e refletidas no vocabulário."""
        self.engine.processar_mensagem_patrick("fechou então, depois do trampo eu te aviso!")
        estilo = self.db.get_estilo()
        girias = estilo["girias"]["valor"]
        self.assertIn("fechou", girias)
        self.assertIn("trampo", girias)

    def test_custom_slang_catalog_extension(self):
        """É possível estender o catálogo com gírias novas dinamicamente."""
        self.engine.adicionar_giria_ao_catalogo("partiu")
        catalogo = self.engine.get_custom_slang_catalog()
        self.assertIn("partiu", catalogo)

        self.engine.processar_mensagem_patrick("partiu praia fim de semana?")
        estilo = self.db.get_estilo()
        self.assertIn("partiu", estilo["girias"]["valor"])

    def test_cadence_statistics_and_ellipses(self):
        """Métricas de cadência, média de palavras e pontuação devem ser calculadas com precisão."""
        self.engine.processar_mensagem_patrick("tô saindo agora...")
        self.engine.processar_mensagem_patrick("cheguei em casa...")
        self.engine.processar_mensagem_patrick("já jantou amor?")

        estilo = self.db.get_estilo()
        cadencia_desc = estilo["cadencia"]["valor"]
        cadencia_dados = estilo["cadencia"]["exemplos"]

        self.assertGreater(cadencia_dados["total_messages"], 0)
        self.assertGreater(cadencia_dados["avg_words"], 0)
        self.assertIn("reticências", cadencia_desc)

    def test_prompt_injection_output(self):
        """Injection only after enough real samples."""
        self.assertEqual(self.engine.get_style_prompt_injection(), "")
        for _ in range(3):
            self.engine.processar_mensagem_patrick("fechou trampo kkkk bora")
        injection = self.engine.get_style_prompt_injection()
        self.assertIn("SINCRONIA LINGUÍSTICA", injection)
        self.assertIn("Risada compartilhada", injection)
        self.assertIn("Ritmo de escrita", injection)


class TestCycleManager(unittest.TestCase):
    def test_cycle_calculation_and_multipliers(self):
        """Verifica cálculo do dia do ciclo e extração de multiplicadores emocionais."""
        # Configura data de início para 13 dias atrás (dia 14 = ovulatória)
        data_inicio = (date.today() - timedelta(days=13)).strftime("%Y-%m-%d")
        manager = MenstrualCycleManager(cycle_start_str=data_inicio, cycle_length=28)

        self.assertEqual(manager.get_current_day(), 14)
        info = manager.get_cycle_info()
        self.assertEqual(info["phase_key"], "ovulatoria")

        multipliers = manager.get_emotional_multipliers()
        self.assertIn("affection", multipliers)
        self.assertIn("romantic_intensity", multipliers)
        self.assertGreaterEqual(multipliers["romantic_intensity"], 0.9)

    def test_set_cycle_start_date_and_prompt(self):
        """Verifica atualização de data de início e geração de prompt biológico."""
        manager = MenstrualCycleManager()
        nova_data = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
        manager.set_cycle_start_date(nova_data)

        self.assertEqual(manager.get_current_day(), 3)
        info = manager.get_cycle_info()
        self.assertEqual(info["phase_key"], "menstrual")

        prompt = manager.get_prompt_context()
        self.assertIn("Fase Menstrual", prompt)
        self.assertIn("Estado Físico", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
