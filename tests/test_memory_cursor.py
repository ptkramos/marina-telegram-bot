"""
Testes Automatizados para o Cursor Persistente de Consolidação de Memória no SQLite.
Valida que as mensagens não são ignoradas e que a consolidação resiste a restarts do bot.
"""
import sys
import unittest
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager


class TestMemoryPersistentCursor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_cursor.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cursor_lifecycle(self):
        """Valida que o cursor inicia em 0, é persistido e lido corretamente."""
        self.assertEqual(self.db.get_last_consolidated_conversation_id(), 0)
        self.db.set_last_consolidated_conversation_id(42)
        self.assertEqual(self.db.get_last_consolidated_conversation_id(), 42)

    def test_get_conversas_desde_preserva_todas_as_mensagens(self):
        """Garante que conversas criadas são paginadas sem saltar mensagens intermediárias."""
        # Cria 10 mensagens
        ids = []
        for i in range(10):
            row_id = self.db.adicionar_mensagem(
                role="user" if i % 2 == 0 else "assistant",
                content=f"Mensagem {i + 1}"
            )
            ids.append(row_id)

        # Sem cursor (desde 0), deve retornar todas as 10
        todas = self.db.get_conversas_desde(since_id=0, limit=20)
        self.assertEqual(len(todas), 10)
        self.assertEqual(self.db.contar_conversas_desde(since_id=0), 10)

        # Se o cursor consolidou até a mensagem 4 (id = ids[3])
        cursor_id = ids[3]
        self.db.set_last_consolidated_conversation_id(cursor_id)

        # Deve retornar exatamente as 6 restantes (5 a 10)
        pendentes = self.db.get_conversas_desde(since_id=cursor_id, limit=20)
        self.assertEqual(len(pendentes), 6)
        self.assertEqual(pendentes[0]["content"], "Mensagem 5")
        self.assertEqual(pendentes[-1]["content"], "Mensagem 10")
        self.assertEqual(self.db.contar_conversas_desde(since_id=cursor_id), 6)

    def test_registrar_iniciativa_marina_nao_cria_user_falso(self):
        """Valida que iniciativa autônoma da Marina gera apenas mensagem assistant."""
        self.db.registrar_iniciativa_marina("Oi amor, passando pra dar um beijo!")
        mensagens = self.db.get_mensagens_recentes(limit=5)
        self.assertEqual(len(mensagens), 1)
        self.assertEqual(mensagens[0]["role"], "assistant")
        self.assertIn("passando pra dar um beijo", mensagens[0]["content"])

    def test_cursor_does_not_advance_on_consolidation_failure(self):
        """Valida que quando a consolidação de memória falha, o cursor permanece intacto."""
        from memory_consolidator import MemoryConsolidationError, MemoryConsolidator
        import asyncio

        # Cursor inicial = 10
        self.db.set_last_consolidated_conversation_id(10)

        # Mock de consolidator que simula falha
        mock_consolidator = MemoryConsolidator(db=self.db)
        mock_consolidator.consolidate_dialogue = lambda messages, existing_facts=None: {
            "facts_to_create": [],
            "facts_to_deactivate": [],
            "important_moments": [],
            "topic_summary": None,
            "error": "503 Service Unavailable: upstream provider down",
            "success": False
        }

        async def _run():
            with self.assertRaises(MemoryConsolidationError):
                await mock_consolidator.consolidate_and_apply_async(
                    [{"role": "user", "content": "teste"}],
                    start_conv_id=11,
                    end_conv_id=20
                )

        asyncio.run(_run())
        # Cursor continua estritamente em 10
        self.assertEqual(self.db.get_last_consolidated_conversation_id(), 10)

    def test_concurrent_consolidation_triggers_process_only_once(self):
        """Valida que chamadas simultâneas de consolidação processam o lote exatamente UMA vez."""
        import asyncio
        import bot
        from memory_consolidator import memory_consolidator

        orig_db = bot.memory_manager.db
        orig_enabled = getattr(bot.settings, "MEMORY_CONSOLIDATION_ENABLED", False)
        orig_batch = getattr(bot.settings, "MEMORY_CONSOLIDATION_BATCH_SIZE", 8)
        orig_method = memory_consolidator.consolidate_and_apply_async

        # Aponta para o banco limpo e temporário do teste
        bot.memory_manager.db = self.db

        # Cria exatamente 8 mensagens no banco isolado
        for i in range(8):
            self.db.adicionar_mensagem("user" if i % 2 == 0 else "assistant", f"Mensagem concorrente {i+1}")

        initial_cursor = self.db.get_last_consolidated_conversation_id()
        calls = []

        async def mock_apply(messages, start_conv_id=None, end_conv_id=None):
            calls.append((start_conv_id, end_conv_id))
            await asyncio.sleep(0.05)
            return {"created": 1, "deactivated": 0, "moments": 0, "summary_saved": True, "success": True}

        memory_consolidator.consolidate_and_apply_async = mock_apply

        async def _run_concurrent():
            # Ativa feature flag
            bot.settings.MEMORY_CONSOLIDATION_ENABLED = True
            bot.settings.MEMORY_CONSOLIDATION_BATCH_SIZE = 8

            # Dispara simultaneamente duas chamadas no mesmo tick
            await asyncio.gather(
                bot.check_and_trigger_memory_consolidation(),
                bot.check_and_trigger_memory_consolidation()
            )
            # Aguarda tarefas assíncronas do lock terminarem
            await asyncio.sleep(0.25)

        try:
            asyncio.run(_run_concurrent())
            # Deve ter sido processado exatamente 1 lote (sem duplicação!)
            self.assertEqual(len(calls), 1)
            # Cursor deve ter avançado para o final do lote
            self.assertGreater(self.db.get_last_consolidated_conversation_id(), initial_cursor)
        finally:
            memory_consolidator.consolidate_and_apply_async = orig_method
            bot.memory_manager.db = orig_db
            bot.settings.MEMORY_CONSOLIDATION_ENABLED = orig_enabled
            bot.settings.MEMORY_CONSOLIDATION_BATCH_SIZE = orig_batch


if __name__ == "__main__":
    unittest.main(verbosity=2)

