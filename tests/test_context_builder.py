"""
Testes Automatizados para o Memory Retriever e Context Builder da Marina Salles (v3.7.0).
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from memory_retriever import memory_retriever
from context_builder import context_builder


class TestMemoryRetrieverAndContextBuilder(unittest.TestCase):
    def test_keyword_extraction(self):
        """Testa se stop words são removidas e termos reais são preservados."""
        texto = "Oi amor, tudo bem? Lembra daquele videogame de RPG que eu falei ontem?"
        keywords = memory_retriever.extract_keywords(texto)
        self.assertIn("videogame", keywords)
        self.assertIn("rpg", keywords)
        self.assertNotIn("amor", keywords)
        self.assertNotIn("tudo", keywords)

    def test_selective_retrieval_returns_relevant_fact(self):
        """Testa recuperação seletiva com termo presente em fatos conhecidos."""
        from memory import memory_manager
        memory_manager.db.adicionar_fato_patrick('Nome: Patrick Ramos')
        res = memory_retriever.retrieve_context(user_message="Patrick", max_facts=3)
        self.assertGreaterEqual(len(res["fatos"]), 1)
        self.assertTrue(any("Patrick" in f for f in res["fatos"]))

    def test_context_builder_payload_structure(self):
        """Testa se context_builder gera estrutura válida para LLM (pós clean-start)."""
        from unittest.mock import patch
        from config import settings
        from memory import memory_manager
        with memory_manager.db.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO world_bootstrap (key, value, updated_at)
                   VALUES ('clean_canonical_start_done', '1', '2026-09-18T00:00:00')"""
            )
        with patch.object(settings, 'LIVING_WORLD_ENABLED', False), \
             patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', False), \
             patch.object(settings, 'RESPONSE_RHYTHM_ENABLED', False):
            messages = context_builder.build(
                user_message="Amor, me tira uma dúvida rápida?",
                quoted_context="[Patrick disse anteriormente: Vamos jantar fora?]",
                web_context="",
                recent_history=[
                    {"role": "user", "content": "Oi linda"},
                    {"role": "assistant", "content": "Oie meu bem!"}
                ]
            )

        self.assertIsInstance(messages, list)
        self.assertGreaterEqual(len(messages), 3) # system + 2 history
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[2]["role"], "assistant")

        system_content = messages[0]["content"]
        self.assertNotIn("Marina Seltin", system_content)
        self.assertIn("Marina Salles", system_content)
        self.assertIn("Vamos jantar fora?", system_content)

    def test_context_builder_with_vision_context(self):
        """Verifica se dados visuais de foto são devidamente incorporados ao system prompt."""
        vision_info = "[FOTO RECEBIDA DO PATRICK AGORA]\n- O que você está vendo na foto: pizza de quatro queijos bem recheada"
        messages = context_builder.build(
            user_message="Olha a janta amor!",
            vision_context=vision_info
        )
        system_content = messages[0]["content"]
        self.assertIn("[FOTO RECEBIDA DO PATRICK AGORA]", system_content)
        self.assertIn("pizza de quatro queijos", system_content)

    def test_context_builder_preserves_recent_history_under_knowledge_privacy(self):
        """Verifica se o histórico recente é preservado mesmo com KNOWLEDGE_PRIVACY_ENABLED ativo quando pronto."""
        from unittest.mock import patch
        from config import settings
        from memory import memory_manager

        from seed_world_bible_v36 import seed_world_bible
        seed_world_bible(memory_manager.db)
        with memory_manager.db.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO world_bootstrap (key, value, updated_at)
                   VALUES ('clean_canonical_start_done', '1', '2026-09-18T00:00:00')"""
            )
        memory_manager.db.adicionar_mensagem(role="user", content="Boa noite vida")
        memory_manager.db.adicionar_mensagem(role="assistant", content="Boa noite meu amor!")

        with patch.object(settings, "LIVING_WORLD_ENABLED", True), \
             patch.object(settings, "KNOWLEDGE_PRIVACY_ENABLED", True), \
             patch.object(settings, "ACADEMIC_LIFE_ENABLED", False), \
             patch.object(settings, "CALENDAR_CONTINUITY_ENABLED", False), \
             patch.object(settings, "RESPONSE_RHYTHM_ENABLED", False):
            messages = context_builder.build(user_message="Dormiu bem?")

        self.assertGreaterEqual(len(messages), 3) # system + 2 history
        self.assertTrue(any("Boa noite vida" in m.get("content", "") for m in messages))
        self.assertTrue(any("Boa noite meu amor!" in m.get("content", "") for m in messages))

    def test_context_builder_uses_character_budget_instead_of_fixed_turn_cap(self):
        """Short exchanges remain available past the old 26-message boundary."""
        from unittest.mock import patch
        from config import settings

        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"fala curta {i}"}
            for i in range(34)
        ]
        history[0]["content"] = "Vou ver uma série e comer sushi"

        with patch.object(settings, "LIVING_WORLD_ENABLED", True), \
             patch.object(settings, "KNOWLEDGE_PRIVACY_ENABLED", True), \
             patch.object(settings, "ACADEMIC_LIFE_ENABLED", False), \
             patch.object(settings, "CALENDAR_CONTINUITY_ENABLED", False), \
             patch.object(settings, "RESPONSE_RHYTHM_ENABLED", False):
            messages = context_builder.build(
                user_message="Tá vendo qual?", recent_history=history)

        self.assertTrue(any("série e comer sushi" in m.get("content", "") for m in messages))


if __name__ == "__main__":
    unittest.main(verbosity=2)
