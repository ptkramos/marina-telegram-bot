"""
Testes unitários e de integração para Open Loops (Assuntos em Aberto).
Marina Salles — Release 3.7.0
"""
import sys
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from context_builder import ContextBuilder
from memory import MemoryManager
from planner import InternalPlanner
from config import settings
from seed_world_bible_v36 import seed_world_bible
from seed_academic_v36 import seed_academic


class TestOpenLoops(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_open_loops.db"
        self.db = DatabaseManager(db_path=self.db_path)
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.memory_mgr = MemoryManager(db=self.db)
        self.context_builder = ContextBuilder(memory_mgr=self.memory_mgr)
        self.planner = InternalPlanner(db=self.db)

    def tearDown(self):
        del self.context_builder
        del self.memory_mgr
        del self.planner
        del self.db
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_open_loop_lifecycle(self):
        """Valida criação, consulta ativa, touch e resolução de um open loop."""
        loop_id = self.db.adicionar_open_loop(
            loop_type="waiting",
            content="Patrick aguarda retorno da proposta de trabalho na empresa X",
            importance=0.8,
            next_check_after=(datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        )
        self.assertGreater(loop_id, 0)

        # Consulta ativos
        ativos = self.db.get_open_loops_ativos(limit=3)
        self.assertEqual(len(ativos), 1)
        self.assertEqual(ativos[0]["id"], loop_id)
        self.assertEqual(ativos[0]["status"], "open")
        self.assertIn("empresa X", ativos[0]["content"])

        # Touch atualiza timestamp
        touch_res = self.db.atualizar_open_loop_touch(loop_id)
        self.assertTrue(touch_res)

        # Resolução
        res_ok = self.db.resolver_open_loop(loop_id)
        self.assertTrue(res_ok)

        # Não deve mais constar nos ativos
        ativos_depois = self.db.get_open_loops_ativos()
        self.assertEqual(len(ativos_depois), 0)

        # Detalhe tem resolved_at
        det = self.db.get_open_loop(loop_id)
        self.assertEqual(det["status"], "resolved")
        self.assertIsNotNone(det["resolved_at"])

    def test_open_loop_checkin_filtering(self):
        """Apenas loops que já atingiram next_check_after devem ser elegíveis para check-in."""
        now = datetime.now()
        
        # Loop futuro (daqui a 3 dias) -> não pronto
        id_futuro = self.db.adicionar_open_loop(
            loop_type="decision",
            content="Decidir sobre a viagem de férias",
            importance=0.6,
            next_check_after=(now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
        )

        # Loop passado (ontem) -> pronto para check-in
        id_pronto = self.db.adicionar_open_loop(
            loop_type="task",
            content="Levar o carro para revisão",
            importance=0.7,
            next_check_after=(now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        )

        prontos = self.db.get_open_loops_para_checkin(now.isoformat())
        ids_prontos = [p["id"] for p in prontos]
        self.assertIn(id_pronto, ids_prontos)
        self.assertNotIn(id_futuro, ids_prontos)

    def test_context_builder_injects_open_loops(self):
        """Verifica se open loops ativos são injetados de forma estruturada no System Prompt."""
        from unittest.mock import patch
        from config import settings
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO world_bootstrap (key, value, updated_at)
                   VALUES ('clean_canonical_start_done', '1', '2026-09-18T00:00:00')"""
            )
        self.db.adicionar_open_loop(
            loop_type="story",
            content="Patrick contou que o amigo dele vai se casar mês que vem",
            importance=0.9
        )

        with patch.object(settings, 'LIVING_WORLD_ENABLED', False), \
             patch.object(settings, 'RESPONSE_RHYTHM_ENABLED', False):
            sys_prompt = self.context_builder.build_system_prompt()
        self.assertIn("[ASSUNTOS AINDA EM ABERTO COM O PATRICK]", sys_prompt)
        self.assertIn("amigo dele vai se casar", sys_prompt)

    def test_planner_applies_open_loop_creation_and_resolution(self):
        """Valida que o apply_plan_effects do Planner cria e resolve Open Loops corretamente."""
        # 1. Criação via Planner
        plan_create = {
            "creates_event": False,
            "creates_open_loop": True,
            "open_loop_details": {
                "loop_type": "project",
                "content": "Patrick está desenvolvendo uma nova arquitetura de software",
                "importance": 0.85,
                "next_check_hint": "em 2 dias"
            },
            "emotional_deltas": {}
        }
        self.planner.apply_plan_effects(plan_create)

        ativos = self.db.get_open_loops_ativos()
        self.assertEqual(len(ativos), 1)
        self.assertIn("nova arquitetura", ativos[0]["content"])

        # 2. Resolução via Planner
        plan_resolve = {
            "creates_event": False,
            "resolves_open_loop": True,
            "resolved_loop_hint": "arquitetura",
            "emotional_deltas": {}
        }
        self.planner.apply_plan_effects(plan_resolve)

        ativos_pos = self.db.get_open_loops_ativos()
        self.assertEqual(len(ativos_pos), 0)


if __name__ == "__main__":
    unittest.main()
