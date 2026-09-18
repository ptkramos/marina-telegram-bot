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
        # 'Patrick' está no fato base 'Nome: Patrick Ramos'
        res = memory_retriever.retrieve_context(user_message="Patrick", max_facts=3)
        self.assertGreaterEqual(len(res["fatos"]), 1)
        self.assertTrue(any("Patrick" in f for f in res["fatos"]))

    def test_context_builder_payload_structure(self):
        """Testa se context_builder gera estrutura válida para LLM."""
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

        # Verifica injeções no system prompt
        system_content = messages[0]["content"]
        self.assertIn("Marina Seltin", system_content)
        self.assertIn("MEMÓRIA AFETIVA SELETIVA", system_content)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
