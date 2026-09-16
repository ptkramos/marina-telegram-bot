"""
Testes Automatizados de Wiring e Validações de Auditoria (Release 3.4.1).
Impede regressões para os bugs identificados na auditoria técnica (REVISAO_TECNICA_MARINA_V3_4.md).
"""
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from planner import InternalPlanner
from context_builder import ContextBuilder
from auto_patcher import AutoPatcher


class TestWiringAuditoria(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_wiring.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_no_plan_response_in_codebase(self):
        """Garante que 'plan_response' (método inexistente que quebrava fotos) não exista em bot.py."""
        bot_file = BASE_DIR / "bot.py"
        content = bot_file.read_text(encoding="utf-8")
        self.assertNotIn("planner.plan_response", content)
        self.assertIn("planner.plan_message", content)

    def test_context_builder_injects_emotional_state(self):
        """Valida que o estado emocional do SQLite é injetado no prompt da Marina."""
        cb = ContextBuilder(memory_mgr=MagicMock(db=self.db, cycle_mgr=MagicMock(get_prompt_context=lambda: "", get_emotional_multipliers=lambda: {})))
        prompt = cb.build_system_prompt()
        self.assertIn("[SEU ESTADO EMOCIONAL INTERNO ATUAL]", prompt)
        self.assertIn("carinho e afeto", prompt)
        self.assertIn("energia e disposição", prompt)

    def test_context_builder_accepts_planner_tone_and_goal(self):
        """Valida que diretrizes estratégicas do planner são incorporadas ao system prompt."""
        cb = ContextBuilder(memory_mgr=MagicMock(db=self.db, cycle_mgr=MagicMock(get_prompt_context=lambda: "", get_emotional_multipliers=lambda: {})))
        prompt = cb.build_system_prompt(planner_tone="dengosa", planner_goal="Acolher com muito dengo")
        self.assertIn("[INTENÇÃO ESTRATÉGICA DESTE TURNO]", prompt)
        self.assertIn("dengosa", prompt)
        self.assertIn("Acolher com muito dengo", prompt)

    def test_auto_patcher_lifo_rollback_protection(self):
        """Valida que o auto-patcher rejeita rollback de patch antigo fora da ordem LIFO."""
        patcher = AutoPatcher()
        # Registra patch 1 e patch 2
        self.db.registrar_patch("patch_001", "Patrick", "patch 1", ["file1.py"], "diff1", status="applied")
        self.db.registrar_patch("patch_002", "Patrick", "patch 2", ["file2.py"], "diff2", status="applied")

        # Tentar rollback do patch_001 direto deve ser rejeitado por proteção LIFO
        with patch("auto_patcher.db_manager", self.db):
            sucesso, msg = patcher.rollback_patch("patch_001")
            self.assertFalse(sucesso)
            self.assertIn("LIFO", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
