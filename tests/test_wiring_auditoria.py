"""
Testes Automatizados de Wiring e Validações de Auditoria da Marina Salles (v3.7.0).
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
from seed_world_bible_v36 import seed_world_bible
from seed_academic_v36 import seed_academic


class TestWiringAuditoria(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_wiring.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO world_bootstrap (key, value, updated_at)
                   VALUES ('clean_canonical_start_done', '1', '2026-09-18T00:00:00')"""
            )

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
        from config import settings
        cb = ContextBuilder(memory_mgr=MagicMock(db=self.db, cycle_mgr=MagicMock(get_prompt_context=lambda: "", get_emotional_multipliers=lambda: {})))
        with patch.object(settings, 'LIVING_WORLD_ENABLED', False), \
             patch.object(settings, 'RESPONSE_RHYTHM_ENABLED', False):
            prompt = cb.build_system_prompt()
        self.assertIn("[COMO VOCÊ ESTÁ POR DENTRO", prompt)   # D14: motor emocional
        self.assertIn("Com o Patrick:", prompt)   # D14: vínculo em palavras, não números
        self.assertIn("- Humor:", prompt)   # D14: humor sempre presente

    def test_context_builder_accepts_planner_tone_and_goal(self):
        """Valida que diretrizes estratégicas do planner são incorporadas ao system prompt."""
        from config import settings
        cb = ContextBuilder(memory_mgr=MagicMock(db=self.db, cycle_mgr=MagicMock(get_prompt_context=lambda: "", get_emotional_multipliers=lambda: {})))
        with patch.object(settings, 'LIVING_WORLD_ENABLED', False), \
             patch.object(settings, 'RESPONSE_RHYTHM_ENABLED', False):
            prompt = cb.build_system_prompt(planner_tone="dengosa", planner_goal="Acolher com muito dengo")
        # Auditoria #2: rótulo traduzido junto com o resto do prompt em pt-BR.
        self.assertIn("[INTENÇÃO DESTE TURNO — planner interno]", prompt)
        self.assertIn("dengosa", prompt)
        self.assertIn("Acolher com muito dengo", prompt)

if __name__ == "__main__":
    unittest.main(verbosity=2)
