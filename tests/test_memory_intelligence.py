"""
Suite de Testes Automatizados para a Release 3.5.0 (Memory Intelligence).
Valida:
1. FTS5 multi-tipo para momentos e resumos (db.py)
2. Core memories, volatilidade e confirmação/decay (db.py)
3. Chaves canônicas e desativação semântica (db.py)
4. MemoryRetriever 2.0: score híbrido, diversidade e deduplicação (memory_retriever.py)
5. MemoryConsolidator 2.0: recuperação seletiva de candidatos e decisões (memory_consolidator.py)
"""
import sys
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from memory_retriever import MemoryRetriever
from memory_consolidator import MemoryConsolidator


class TestMemoryIntelligenceDB(unittest.TestCase):
    """Testa os novos métodos de banco SQLite introduzidos na migration 005."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_mem_intel.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_version_is_five(self):
        """Valida que a migration 005_memory_intelligence foi aplicada com sucesso."""
        self.assertEqual(self.db.get_schema_version(), 5)

    def test_adicionar_fato_com_tier_volatilidade_e_canonical_key(self):
        """Testa inserção e recuperação de fatos com os novos metadados da 3.5.0."""
        fid = self.db.adicionar_fato_patrick(
            fato="Patrick ama suco de maracujá bem gelado",
            category="preferencia",
            importance=0.85,
            confidence=1.0,
            memory_tier="core",
            volatility="stable",
            canonical_key="favorite_juice"
        )
        self.assertGreater(fid, 0)

        fatos = self.db.get_fatos_patrick_detalhados()
        fato = next((f for f in fatos if f["id"] == fid), None)
        self.assertIsNotNone(fato)
        self.assertEqual(fato["memory_tier"], "core")
        self.assertEqual(fato["volatility"], "stable")
        self.assertEqual(fato["canonical_key"], "favorite_juice")
        self.assertEqual(fato["confirmation_count"], 0)

    def test_get_core_memories(self):
        """Valida recuperação exclusiva de memórias com memory_tier='core'."""
        self.db.adicionar_fato_patrick("Fato Standard", memory_tier="standard")
        self.db.adicionar_fato_patrick("Fato Contextual", memory_tier="contextual")
        self.db.adicionar_fato_patrick("Fato Core 1", memory_tier="core", importance=0.9)
        self.db.adicionar_fato_patrick("Fato Core 2", memory_tier="core", importance=0.95)

        core = self.db.get_core_memories(limit=5)
        self.assertEqual(len(core), 2)
        self.assertTrue(all(c["memory_tier"] == "core" for c in core))
        # Deve ordenar por importância decrescente
        self.assertEqual(core[0]["fato"], "Fato Core 2")

    def test_confirmar_fato(self):
        """Valida o ciclo de confirmação: incrementa confirmation_count, ajusta confiança e atualiza timestamp."""
        fid = self.db.adicionar_fato_patrick(
            fato="Patrick joga tênis aos sábados",
            confidence=0.6,
            volatility="medium"
        )
        # Confirma o fato
        sucesso = self.db.confirmar_fato(fid)
        self.assertTrue(sucesso)

        fatos = self.db.get_fatos_patrick_detalhados()
        fato = next(f for f in fatos if f["id"] == fid)
        self.assertEqual(fato["confirmation_count"], 1)
        self.assertAlmostEqual(fato["confidence"], 0.7)  # 0.6 + 0.1
        self.assertIsNotNone(fato["last_confirmed_at"])

    def test_desativar_fato_por_chave_canonica(self):
        """Valida que desativar_fato_por_chave inativa registros com a mesma canonical_key."""
        fid1 = self.db.adicionar_fato_patrick(
            fato="Patrick joga Final Fantasy XIV",
            canonical_key="current_main_game"
        )
        self.db.desativar_fato_por_chave("current_main_game")

        # Fato 1 não deve estar ativo
        ativos = self.db.get_fatos_patrick_detalhados(active_only=True)
        self.assertFalse(any(f["id"] == fid1 for f in ativos))

        # Mas ainda existe no banco inativo
        todos = self.db.get_fatos_patrick_detalhados(active_only=False)
        self.assertTrue(any(f["id"] == fid1 for f in todos))

    def test_buscar_momentos_e_resumos_fts(self):
        """Valida FTS5 em momentos marcantes e resumos de conversas anteriores."""
        self.db.adicionar_momento_marcante(
            momento="Fomos juntos ao mirante ver o pôr do sol no verão",
            importance=0.9
        )
        self.db.salvar_resumo_conversa(
            topic="viagem, praia, planos",
            summary="Conversamos sobre planos de viajar para a praia em Florianópolis"
        )

        # Busca FTS em momentos
        momentos_fts = self.db.buscar_momentos_fts("mirante")
        self.assertEqual(len(momentos_fts), 1)
        self.assertIn("mirante", momentos_fts[0]["momento"])

        # Busca FTS em resumos
        resumos_fts = self.db.buscar_resumos_fts("Florianópolis")
        self.assertEqual(len(resumos_fts), 1)
        self.assertIn("Florianópolis", resumos_fts[0]["summary"])


class TestMemoryRetrieverIntelligence(unittest.TestCase):
    """Testa a inteligência de busca híbrida e balanceamento do MemoryRetriever 2.0."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_retriever.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.retriever = MemoryRetriever(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compute_hybrid_score_calculation(self):
        """Valida o cálculo do score híbrido ponderado."""
        fact = {
            "importance": 0.9,
            "confidence": 1.0,
            "memory_tier": "core",
            "access_count": 5,
            "created_at": datetime.now().isoformat(),
            "last_confirmed_at": None,
            "updated_at": None
        }
        # Com match FTS
        score_fts = self.retriever.compute_hybrid_score(fact, is_fts_match=True)
        # lexical: 1.0 * 0.4 = 0.40
        # importance: 0.9 * 0.2 = 0.18
        # confidence: 1.0 * 0.15 = 0.15
        # freshness: 1.0 * 0.10 = 0.10
        # core: 1.0 * 0.10 = 0.10
        # access: (5/10) * 0.05 = 0.025
        # Total esperado: 0.40 + 0.18 + 0.15 + 0.10 + 0.10 + 0.025 = 0.955
        self.assertAlmostEqual(score_fts, 0.955, places=2)

        # Sem match FTS
        score_no_fts = self.retriever.compute_hybrid_score(fact, is_fts_match=False)
        self.assertLess(score_no_fts, score_fts)

    def test_diversity_deduplication_by_canonical_key(self):
        """Valida que memórias com a mesma chave canônica não duplicam na recuperação."""
        self.db.adicionar_fato_patrick(
            "Patrick adora Monster Energy Ultra",
            category="bebidas",
            canonical_key="energy_drink",
            importance=0.8
        )
        self.db.adicionar_fato_patrick(
            "Patrick toma Monster Energy todo dia",
            category="bebidas",
            canonical_key="energy_drink",
            importance=0.7
        )

        contexto = self.retriever.retrieve_context("energy monster", max_facts=5)
        # Deve conter no máximo 1 fato sobre energy_drink
        detalhes = contexto["fatos_detalhados"]
        chaves = [f.get("canonical_key") for f in detalhes if f.get("canonical_key")]
        self.assertEqual(chaves.count("energy_drink"), 1)

    def test_low_confidence_fact_annotation(self):
        """Valida que fatos com confiança < 0.5 recebem a anotação para o prompt reconfirmar com sutileza."""
        self.db.adicionar_fato_patrick(
            fato="Patrick treina na academia pela manhã",
            category="rotina",
            confidence=0.4,
            importance=0.7
        )

        contexto = self.retriever.retrieve_context("academia manhã", max_facts=3)
        self.assertTrue(any("lembrança vaga/a confirmar" in f for f in contexto["fatos"]))


class TestMemoryConsolidatorIntelligence(unittest.TestCase):
    """Testa a integração do MemoryConsolidator 2.0 com MemoryRetriever seletivo."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_consolidator_intel.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.consolidator = MemoryConsolidator(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_selective_candidate_retrieval(self):
        """Valida que consolidate_dialogue busca candidatos relevantes via retriever em vez de todos os fatos."""
        # Cria 20 fatos não relacionados
        for i in range(20):
            self.db.adicionar_fato_patrick(f"Fato irrelevante número {i}", category="geral")

        # Cria 1 fato relevante
        self.db.adicionar_fato_patrick("Patrick adora pizza de calabresa", category="comida")

        dialogo = [
            {"role": "user", "content": "Amor, tô com vontade de pedir uma pizza de calabresa hoje à noite."}
        ]

        # Intercepta chamada LLM para verificar prompt enviado
        captured_messages = []
        def mock_llm_create(*args, **kwargs):
            nonlocal captured_messages
            captured_messages = kwargs.get("messages", [])
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = '{"facts_to_create":[], "facts_to_deactivate":[], "important_moments":[], "topic_summary":"Pizza"}'
            mock_resp.choices = [mock_choice]
            return mock_resp

        with patch.object(self.consolidator.llm.chat.completions, "create", side_effect=mock_llm_create):
            self.consolidator.consolidate_dialogue(dialogo)

        self.assertTrue(len(captured_messages) > 0)
        user_prompt = captured_messages[1]["content"]

        # O fato relevante da pizza deve estar presente nos candidatos
        self.assertIn("calabresa", user_prompt)
        # Mas NÃO deve ter todos os 20 fatos irrelevantes entupindo o prompt
        self.assertNotIn("Fato irrelevante número 18", user_prompt)

    def test_apply_consolidation_with_canonical_key_and_tier(self):
        """Valida que apply_consolidation persiste memory_tier, volatility e canonical_key."""
        payload = {
            "facts_to_create": [
                {
                    "fato": "Patrick programa em Python e Rust",
                    "category": "trabalho",
                    "importance": 0.9,
                    "confidence": 1.0,
                    "memory_tier": "core",
                    "volatility": "stable",
                    "canonical_key": "programming_languages"
                }
            ],
            "facts_to_deactivate": [],
            "important_moments": [],
            "topic_summary": "Linguagens de programação do Patrick"
        }

        result = self.consolidator.apply_consolidation(payload)
        self.assertEqual(result["created"], 1)

        fatos = self.db.get_fatos_patrick_detalhados()
        f = next(f for f in fatos if f["canonical_key"] == "programming_languages")
        self.assertEqual(f["memory_tier"], "core")
        self.assertEqual(f["volatility"], "stable")


if __name__ == "__main__":
    unittest.main()
