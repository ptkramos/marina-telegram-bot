"""Auditoria #2 — garantias do tier de memória.

Contexto: o `MemoryRetriever` carrega core memories em todo turno,
independentemente de casamento lexical (contrato 3.5.0: "deve ser recuperável
sem depender de palavra exata"). O mecanismo sempre esteve correto, mas nenhum
fato era classificado como core, então o passo ficava inerte.

Os testes existentes injetavam `memory_tier='core'` à mão, validando o
mecanismo e não a alimentação dele — por isso nenhum falhava. Estes fecham
essa lacuna.
"""
import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from memory_retriever import MemoryRetriever
import memory_consolidator


class SeedCoreMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(Path(self.tmp.name) / "core_tier.db")

    def test_banco_novo_nasce_com_core_memory(self):
        """Sem isso, o passo de core do retriever nunca é exercido."""
        cores = self.db.get_core_memories()
        self.assertGreaterEqual(len(cores), 1,
                                "banco novo precisa nascer com ao menos uma core memory")

    def test_identidade_do_patrick_e_core_e_estavel(self):
        cores = self.db.get_core_memories()
        identidade = next((c for c in cores if "Patrick Ramos" in c["fato"]), None)
        self.assertIsNotNone(identidade, "a identidade do Patrick deve ser core")
        self.assertEqual(identidade["memory_tier"], "core")
        self.assertEqual(identidade["volatility"], "stable")
        self.assertEqual(identidade["confidence"], 1.0)

    def test_reset_do_soak_recria_identidade_como_core(self):
        """O `/limpar` zera o aprendizado e recria o seed mínimo.

        Se ele recriasse a identidade como 'standard', cada reset devolveria o
        banco ao estado sem nenhuma core memory — o defeito que esta auditoria
        corrigiu voltaria a cada limpeza.
        """
        self.db.reset_soak_learning()
        cores = self.db.get_core_memories()
        self.assertTrue(any("Patrick Ramos" in c["fato"] for c in cores),
                        "após reset a identidade deve voltar como core")


class CoreRetrievalGuaranteeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(Path(self.tmp.name) / "core_retrieval.db")
        self.retriever = MemoryRetriever(self.db)

    def test_core_entra_sem_casamento_lexical(self):
        """Contrato 3.5.0: core é recuperável sem depender de palavra exata."""
        self.db.adicionar_fato_patrick(
            "Patrick está construindo um bot da Marina",
            memory_tier="core", volatility="stable", importance=0.95,
        )
        # Pergunta sem nenhuma palavra em comum com o fato acima.
        recuperado = self.retriever.retrieve_context(
            user_message="qual música você tá ouvindo?", max_facts=5)
        fatos = recuperado.get("fatos", [])
        self.assertTrue(any("bot da Marina" in f for f in fatos),
                        f"core memory deveria entrar sem palavra-chave; veio {fatos}")

    def test_contextual_nao_tem_a_mesma_garantia(self):
        """Só core tem entrada garantida — senão o prompt encheria de ruído."""
        self.db.adicionar_fato_patrick(
            "Patrick precisa levar o carro no lava-jato sexta",
            memory_tier="contextual", volatility="volatile", importance=0.3,
        )
        recuperado = self.retriever.retrieve_context(
            user_message="me conta uma fofoca da facul", max_facts=2)
        cores = [c["fato"] for c in self.db.get_core_memories()]
        self.assertNotIn("lava-jato", " ".join(cores),
                         "fato contextual não deve ser tratado como core")


class ConsolidatorPromptTests(unittest.TestCase):
    """Guard contra regressão do Patch 021 nesta camada.

    O prompt do consolidator processa e escreve texto pt-BR; instrução em
    inglês sobre conteúdo português foi identificada como causa de degradação.
    """

    def test_prompt_esta_em_portugues(self):
        prompt = memory_consolidator.CONSOLIDATOR_SYSTEM_PROMPT
        self.assertIn("REGRAS DE CLASSIFICAÇÃO", prompt)
        self.assertNotIn("CLASSIFICATION AND INTELLIGENCE RULES", prompt)

    def test_prompt_ensina_os_tres_tiers(self):
        """Antes, só o pedido explícito produzia core — 1 dos 4 casos do contrato."""
        prompt = memory_consolidator.CONSOLIDATOR_SYSTEM_PROMPT
        self.assertIn("COMO ESCOLHER memory_tier", prompt)
        for tier in ("'core'", "'standard'", "'contextual'"):
            self.assertIn(tier, prompt, f"o prompt precisa explicar {tier}")

    def test_prompt_pede_criterio_com_core(self):
        """Sem freio explícito, o modelo marca tudo como core."""
        prompt = memory_consolidator.CONSOLIDATOR_SYSTEM_PROMPT.lower()
        self.assertIn("se tudo for core, nada é", prompt)


if __name__ == "__main__":
    unittest.main()
