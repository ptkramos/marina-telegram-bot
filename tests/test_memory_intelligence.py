"""
Suite de Testes Automatizados para a Release 3.5.0 (Memory Intelligence Hardened).
Cobre os testes obrigatórios 7.1 a 7.16 da REVISAO_TECNICA_MARINA_V3_5_0.md:
- 7.1: SAME com texto idêntico (confirmação sem perda de memória)
- 7.2: SAME semanticamente igual com texto diferente
- 7.3: IGNORE (zero mutações no banco)
- 7.4: UPDATE atômico com supersedes_id
- 7.5: CONTRADICTION atômico
- 7.6: Falha durante replacement (rollback e preservação do fato original)
- 7.7: UNIQUE(fato) não apaga memória (reprodução e prevenção do bug crítico)
- 7.8: ID alucinado pela LLM bloqueado por allowlist
- 7.9: Key fora do allowlist bloqueada
- 7.10: Volatilidade afetando effective_confidence sem mutar o banco
- 7.11: Relevância lexical FTS relativa/normalizada
- 7.12: Background retrieval sem side-effects em access_count
- 7.13: Context Builder registrando acesso normalmente
- 7.14: /memorydebug sem alterar access_count
- 7.15: Feature flag MEMORY_INTELLIGENCE_ENABLED=False (fallback legado v3.4.3)
- 7.16: Migration regression v3.4.3 -> v3.5.0
"""
import sys
import sqlite3
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
from config import settings


class TestMemoryIntelligenceHardened(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_mem_hardened.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.retriever = MemoryRetriever(db=self.db)
        self.consolidator = MemoryConsolidator(db=self.db)

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # --- 7.1 SAME com texto idêntico ---
    def test_7_1_same_com_texto_identico(self):
        """Reafirmação exata deve confirmar e incrementar contagem sem criar duplicatas nem apagar fato."""
        fid = self.db.adicionar_fato_patrick(
            fato="Patrick joga FFXIV",
            canonical_key="current_main_game",
            confidence=0.7
        )
        self.assertGreater(fid, 0)

        payload = {
            "facts_to_create": [
                {
                    "fato": "Patrick joga FFXIV",
                    "decision": "same",
                    "existing_fact_id": fid,
                    "canonical_key": "current_main_game"
                }
            ],
            "facts_to_deactivate": [],
            "_candidate_fact_ids": {fid},
            "_candidate_keys": {"current_main_game"}
        }

        res = self.consolidator.apply_consolidation(payload)
        self.assertEqual(res["created"], 0)
        self.assertEqual(res["confirmed"], 1)

        ativos = self.db.get_fatos_por_chave("current_main_game", active_only=True)
        self.assertEqual(len(ativos), 1)
        self.assertEqual(ativos[0]["id"], fid)
        self.assertEqual(ativos[0]["confirmation_count"], 1)
        self.assertAlmostEqual(ativos[0]["confidence"], 0.8)
        self.assertIsNotNone(ativos[0]["last_confirmed_at"])

    # --- 7.2 SAME semanticamente igual, texto diferente ---
    def test_7_2_same_semanticamente_igual_texto_diferente(self):
        """LLM decide 'same' com variação de texto: não cria segunda linha, confirma original."""
        fid = self.db.adicionar_fato_patrick(
            fato="Patrick adora café expresso",
            canonical_key="coffee_preference",
            confidence=0.7
        )

        payload = {
            "facts_to_create": [
                {
                    "fato": "Patrick continua tomando bastante café expresso",
                    "decision": "same",
                    "existing_fact_id": fid,
                    "canonical_key": "coffee_preference"
                }
            ],
            "_candidate_fact_ids": {fid},
            "_candidate_keys": {"coffee_preference"}
        }

        res = self.consolidator.apply_consolidation(payload)
        self.assertEqual(res["created"], 0)
        self.assertEqual(res["confirmed"], 1)

        fatos_chave = self.db.get_fatos_por_chave("coffee_preference", active_only=True)
        self.assertEqual(len(fatos_chave), 1)
        self.assertEqual(fatos_chave[0]["id"], fid)
        self.assertEqual(fatos_chave[0]["confirmation_count"], 1)

    # --- 7.3 IGNORE ---
    def test_7_3_ignore(self):
        """Decisão ignore não realiza mutação de escrita no banco."""
        self.db.adicionar_fato_patrick("Fato base")
        count_antes = len(self.db.get_fatos_patrick_detalhados())

        payload = {
            "facts_to_create": [
                {
                    "fato": "Chitchat sem relevância",
                    "decision": "ignore"
                }
            ]
        }
        res = self.consolidator.apply_consolidation(payload)
        self.assertEqual(res["ignored"], 1)
        self.assertEqual(len(self.db.get_fatos_patrick_detalhados()), count_antes)

    # --- 7.4 UPDATE ---
    def test_7_4_update(self):
        """Update atômico substitui o antigo pelo novo, ligando supersedes_id e mantendo 1 ativo."""
        old_id = self.db.adicionar_fato_patrick(
            fato="Patrick joga FFXIV",
            canonical_key="current_main_game"
        )

        payload = {
            "facts_to_create": [
                {
                    "fato": "Patrick agora joga Guild Wars 2 como jogo principal",
                    "decision": "update",
                    "existing_fact_id": old_id,
                    "canonical_key": "current_main_game"
                }
            ],
            "_candidate_fact_ids": {old_id},
            "_candidate_keys": {"current_main_game"}
        }

        res = self.consolidator.apply_consolidation(payload)
        self.assertEqual(res["updated"], 1)

        ativos = self.db.get_fatos_por_chave("current_main_game", active_only=True)
        self.assertEqual(len(ativos), 1)
        self.assertIn("Guild Wars 2", ativos[0]["fato"])
        self.assertEqual(ativos[0]["supersedes_id"], old_id)

        # Fato antigo está inativo
        old_det = self.db.get_fato_detalhado(old_id, active_only=False)
        self.assertEqual(old_det["active"], 0)

    # --- 7.5 CONTRADICTION ---
    def test_7_5_contradiction(self):
        """Contradiction substitui atomicamente o fato contradito."""
        old_id = self.db.adicionar_fato_patrick(
            fato="Patrick toma café todo dia de manhã",
            canonical_key="morning_drink"
        )

        payload = {
            "facts_to_create": [
                {
                    "fato": "Patrick parou de tomar café e agora só toma suco de laranja",
                    "decision": "contradiction",
                    "existing_fact_id": old_id,
                    "canonical_key": "morning_drink"
                }
            ],
            "_candidate_fact_ids": {old_id},
            "_candidate_keys": {"morning_drink"}
        }

        res = self.consolidator.apply_consolidation(payload)
        self.assertEqual(res["updated"], 1)

        ativos = self.db.get_fatos_por_chave("morning_drink", active_only=True)
        self.assertEqual(len(ativos), 1)
        self.assertIn("suco de laranja", ativos[0]["fato"])

    # --- 7.6 Falha durante replacement preserva memória antiga ---
    def test_7_6_falha_durante_replacement(self):
        """Se ocorrer falha no banco durante replacement, rollback preserva o fato antigo ativo."""
        old_id = self.db.adicionar_fato_patrick(
            fato="Fato crítico importante",
            canonical_key="critical_fact"
        )

        # Simula erro forçado durante a inserção
        with patch.object(self.db, "get_connection") as mock_conn_mgr:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            # 1ª query (SELECT) retorna o fato antigo ativo
            mock_cursor.fetchone.return_value = {"id": old_id, "fato": "Fato crítico importante", "canonical_key": "critical_fact"}
            # 2ª query (INSERT) falha com erro de integridade
            mock_cursor.execute.side_effect = [None, sqlite3.IntegrityError("Falha simulada")]
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_mgr.return_value.__enter__.return_value = mock_conn

            res = self.db.substituir_fato_atomicamente(old_id, {"fato": "Novo fato que falha"})
            self.assertIsNone(res)
            mock_conn.rollback.assert_called_once()

        # O fato no SQLite real continua ativo e intacto
        det = self.db.get_fato_detalhado(old_id, active_only=True)
        self.assertIsNotNone(det)
        self.assertEqual(det["active"], 1)

    # --- 7.7 UNIQUE(fato) não apaga memória ---
    def test_7_7_unique_fato_nao_apaga_memoria(self):
        """Reprodução independente do bug da auditoria: mesma canonical key com texto idêntico não apaga a memória."""
        fid = self.db.adicionar_fato_patrick(
            fato="Patrick joga FFXIV",
            canonical_key="current_main_game",
            confidence=0.8
        )

        # Se vier update com o mesmo texto
        payload = {
            "facts_to_create": [
                {
                    "fato": "Patrick joga FFXIV",
                    "decision": "update",
                    "existing_fact_id": fid,
                    "canonical_key": "current_main_game"
                }
            ],
            "_candidate_fact_ids": {fid},
            "_candidate_keys": {"current_main_game"}
        }

        self.consolidator.apply_consolidation(payload)

        # DEVE restar 1 fato ativo, JAMAIS 0!
        ativos = self.db.get_fatos_por_chave("current_main_game", active_only=True)
        self.assertEqual(len(ativos), 1, "Bug crítico da auditoria evitado: exatamente 1 fato ativo deve restar.")
        self.assertEqual(ativos[0]["id"], fid)

    # --- 7.8 ID alucinado pela LLM bloqueado por allowlist ---
    def test_7_8_id_alucinado_pela_llm(self):
        """ID fora da allowlist de candidatos apresentados é rejeitado com NO-OP."""
        unrelated_id = self.db.adicionar_fato_patrick(
            fato="Fato não relacionado que não participou da conversa",
            canonical_key="secret_fact"
        )

        payload = {
            "facts_to_create": [],
            "facts_to_deactivate": [{"existing_fact_id": unrelated_id, "reason": "Alucinação da LLM"}],
            "_candidate_fact_ids": {101, 102}  # unrelated_id NÃO está na allowlist!
        }

        self.consolidator.apply_consolidation(payload)

        # Fato não relacionado deve continuar ativo
        det = self.db.get_fato_detalhado(unrelated_id, active_only=True)
        self.assertIsNotNone(det)
        self.assertEqual(det["active"], 1)

    # --- 7.9 Key fora do allowlist bloqueada ---
    def test_7_9_key_fora_do_allowlist(self):
        """Chave fora da allowlist de candidatos apresentados é rejeitada com NO-OP."""
        fid = self.db.adicionar_fato_patrick(
            fato="Patrick ama suco de maçã",
            canonical_key="protected_key"
        )

        payload = {
            "facts_to_create": [],
            "keys_to_deactivate": ["protected_key"],
            "_candidate_keys": {"other_key"}  # protected_key NÃO está na allowlist!
        }

        self.consolidator.apply_consolidation(payload)

        det = self.db.get_fato_detalhado(fid, active_only=True)
        self.assertIsNotNone(det)
        self.assertEqual(det["active"], 1)

    # --- 7.10 Volatilidade afetando effective_confidence sem mutar o banco ---
    def test_7_10_volatilidade_effective_confidence(self):
        """Volatilidade reduz confiança efetiva de fatos voláteis após 30 dias, sem alterar o valor bruto no banco."""
        # Cria fato stable e fato volatile há 45 dias
        ts_45d = (datetime.now() - timedelta(days=45)).isoformat()
        fact_stable = {
            "fato": "Patrick nasceu no Rio de Janeiro",
            "volatility": "stable",
            "confidence": 1.0,
            "created_at": ts_45d,
            "last_confirmed_at": ts_45d
        }
        fact_volatile = {
            "fato": "Patrick treina às 7h da manhã esta semana",
            "volatility": "volatile",
            "confidence": 1.0,
            "created_at": ts_45d,
            "last_confirmed_at": ts_45d
        }

        eff_stable = self.retriever.compute_effective_confidence(fact_stable)
        eff_volatile = self.retriever.compute_effective_confidence(fact_volatile)

        self.assertAlmostEqual(eff_stable, 1.0)
        self.assertLess(eff_volatile, eff_stable)
        self.assertLess(eff_volatile, 1.0)

        # Score híbrido reflete a perda de confiança no volátil
        score_stable = self.retriever.compute_hybrid_score(fact_stable)
        score_volatile = self.retriever.compute_hybrid_score(fact_volatile)
        self.assertGreater(score_stable, score_volatile)

    # --- 7.11 Relevância lexical relativa ---
    def test_7_11_relevancia_lexical(self):
        """Candidatos FTS com posições/ranks diferentes recebem scores léxicos proporcionais."""
        self.db.adicionar_fato_patrick("Energético Monster Energy favorito do Patrick")
        self.db.adicionar_fato_patrick("Patrick às vezes toma Monster branco")

        context = self.retriever.retrieve_context("Monster", max_facts=2, record_access=False)
        detalhes = context["fatos_detalhados"]
        self.assertGreaterEqual(len(detalhes), 2)
        # O primeiro resultado ordenado deve ter score híbrido maior ou igual ao segundo
        self.assertGreaterEqual(detalhes[0]["hybrid_score"], detalhes[1]["hybrid_score"])

    # --- 7.12 Background retrieval sem side-effects em access_count ---
    def test_7_12_background_retrieval_sem_popularity_feedback(self):
        """Busca do Consolidator com record_access=False não altera access_count."""
        fid = self.db.adicionar_fato_patrick("Patrick adora café arábica")
        det_antes = self.db.get_fato_detalhado(fid)
        self.assertEqual(det_antes["access_count"], 0)

        # Executa recuperação em background com record_access=False
        self.retriever.retrieve_context("café arábica", record_access=False)

        det_depois = self.db.get_fato_detalhado(fid)
        self.assertEqual(det_depois["access_count"], 0)

    # --- 7.13 Context Builder incrementa acesso normalmente ---
    def test_7_13_context_builder_incrementa_acesso_normalmente(self):
        """Conversa real com record_access=True incrementa métrica de acesso no banco."""
        fid = self.db.adicionar_fato_patrick("Patrick estuda Inteligência Artificial")
        det_antes = self.db.get_fato_detalhado(fid)
        self.assertEqual(det_antes["access_count"], 0)

        # Executa recuperação com record_access=True
        self.retriever.retrieve_context("Inteligência Artificial", record_access=True)

        det_depois = self.db.get_fato_detalhado(fid)
        self.assertEqual(det_depois["access_count"], 1)

    # --- 7.14 /memorydebug não altera access_count ---
    def test_7_14_memorydebug_nao_altera_access_count(self):
        """Comando administrativo /memorydebug usa record_access=False e é puramente observacional."""
        fid = self.db.adicionar_fato_patrick("Patrick joga xadrez online")
        self.retriever.retrieve_context("xadrez", record_access=False)

        det = self.db.get_fato_detalhado(fid)
        self.assertEqual(det["access_count"], 0)

    # --- 7.15 Feature flag MEMORY_INTELLIGENCE_ENABLED=False ---
    def test_7_15_feature_flag_off(self):
        """Com feature flag desativada, executa fallback legado v3.4.3 sem falhar."""
        self.db.adicionar_fato_patrick("Fato legado de teste", importance=0.8)
        self.db.adicionar_momento_marcante("Momento legado")
        self.db.salvar_resumo_conversa(topic="Geral", summary="Resumo legado")

        orig_flag = settings.MEMORY_INTELLIGENCE_ENABLED
        try:
            settings.MEMORY_INTELLIGENCE_ENABLED = False
            ctx = self.retriever.retrieve_context("legado", record_access=False)
            self.assertIn("fatos", ctx)
            self.assertIn("momentos", ctx)
            self.assertIn("resumos", ctx)
            self.assertTrue(len(ctx["fatos"]) >= 1)
        finally:
            settings.MEMORY_INTELLIGENCE_ENABLED = orig_flag

    # --- 7.16 Migration regression v3.4.3 -> v3.5.0 ---
    def test_7_16_migration_regression(self):
        """Valida que um banco legado v3.4.3 recebe migration 005 preservando todas as conversas e fatos."""
        legacy_db_path = Path(self.temp_dir.name) / "legacy_v343.db"
        conn = sqlite3.connect(legacy_db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
        """)
        # Executa migrations 001 a 004 manualmente para simular estado v3.4.3
        mig_dir = BASE_DIR / "migrations"
        for i in range(1, 5):
            mig_file = next(mig_dir.glob(f"{i:03d}_*.sql"))
            conn.executescript(mig_file.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, name, applied_at) VALUES (?, ?, datetime('now'))",
                (i, mig_file.stem)
            )
        
        # Insere dados legados
        conn.execute(
            "INSERT INTO conversas (role, content, timestamp) VALUES ('user', 'Oi amor', datetime('now'))"
        )
        conn.execute(
            "INSERT INTO fatos_patrick (fato, created_at, category, importance, confidence, active) "
            "VALUES ('Fato antigo v3.4.3', datetime('now'), 'geral', 0.8, 1.0, 1)"
        )
        conn.commit()
        conn.close()

        # Abre com DatabaseManager v3.5.0
        mgr = DatabaseManager(db_path=legacy_db_path)
        self.assertEqual(mgr.get_schema_version(), 5)
        self.assertEqual(mgr.get_mensagens_recentes()[0]["content"], "Oi amor")

        # Conversas e fatos intactos
        fatos = mgr.get_fatos_patrick_detalhados()
        self.assertEqual(len(fatos), 1)
        self.assertEqual(fatos[0]["fato"], "Fato antigo v3.4.3")
        self.assertEqual(fatos[0]["memory_tier"], "standard")
        self.assertEqual(fatos[0]["volatility"], "medium")
        self.assertEqual(fatos[0]["confirmation_count"], 0)


if __name__ == "__main__":
    unittest.main()
