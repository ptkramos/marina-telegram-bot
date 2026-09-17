"""
tests/test_reflection_hygiene.py — Suíte de Testes para Session Reflection & Memory Hygiene (Release 3.5.3).

Valida todas as novas funcionalidades da Release 3.5.3:
- Migration 007 e schema version >= 7
- Confidence Decay diferenciado por volatilidade ('volatile', 'medium', 'stable', 'core')
- Identificação e reconfirmação de memórias enfraquecidas
- Deduplicação leve por canonical_key
- Arquivamento de open loops antigos
- Session Reflector (parsing de JSON, persistência de resumo, resolução de loops)
- Injeção de oportunidade de reconfirmação no Context Builder
"""
import sys
import json
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from memory import MemoryManager
from context_builder import ContextBuilder
from memory_hygiene import MemoryHygieneService
from session_reflector import SessionReflector


class TestReflectionAndMemoryHygiene(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_hygiene.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.hygiene = MemoryHygieneService(db=self.db)
        self.reflector = SessionReflector(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_migration_007_applied(self):
        """Valida que a migration 007 foi aplicada com sucesso (versão >= 7)."""
        version = self.db.get_schema_version()
        self.assertGreaterEqual(version, 7)

        # Testa colunas novas
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(fatos_patrick);")
            cols_fatos = {row["name"] for row in cursor.fetchall()}
            self.assertIn("needs_reconfirmation", cols_fatos)

            cursor.execute("PRAGMA table_info(open_loops);")
            cols_loops = {row["name"] for row in cursor.fetchall()}
            self.assertIn("is_archived", cols_loops)

    def test_confidence_decay_volatile_and_reconfirmation_flag(self):
        """Fatos voláteis antigos perdem confiança e são sinalizados para reconfirmação."""
        # Cria fato volátil há 25 dias
        passado_25d = (datetime.now() - timedelta(days=25)).isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fatos_patrick
                (fato, category, importance, confidence, memory_tier, volatility, canonical_key, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                ("Patrick está treinando às 6h da manhã esta semana", "rotina", 0.8, 1.0, "standard", "volatile", "training_schedule", passado_25d, passado_25d)
            )
            conn.commit()
            fato_id = cursor.lastrowid

        stats = self.db.aplicar_confidence_decay(dias_volatil=14, dias_medio=60)
        self.assertGreaterEqual(stats["decayed_count"], 1)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT confidence, needs_reconfirmation FROM fatos_patrick WHERE id = ?", (fato_id,))
            row = cursor.fetchone()
            self.assertLess(row["confidence"], 1.0)
            self.assertEqual(row["confidence"], 0.9)  # 1.0 - 0.10
            # Simula passagem de mais 60 dias no tempo
            tempo_futuro = datetime.now() + timedelta(days=60)
            self.db.aplicar_confidence_decay(dias_volatil=14, dias_medio=60, now=tempo_futuro)

        # Após decair para <= 0.60, deve estar sinalizado
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT confidence, needs_reconfirmation FROM fatos_patrick WHERE id = ?", (fato_id,))
            row_final = cursor.fetchone()
            self.assertLessEqual(row_final["confidence"], 0.60)
            self.assertEqual(row_final["needs_reconfirmation"], 1)

        # Testa busca de candidatos a reconfirmação
        candidatos = self.db.get_memorias_para_reconfirmacao(limit=5)
        self.assertTrue(any(c["id"] == fato_id for c in candidatos))

        # Reconfirma o fato
        self.db.marcar_fato_reconfirmado(fato_id, nova_confianca=1.0)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT confidence, needs_reconfirmation, confirmation_count FROM fatos_patrick WHERE id = ?", (fato_id,))
            row_reconf = cursor.fetchone()
            self.assertEqual(row_reconf["confidence"], 1.0)
            self.assertEqual(row_reconf["needs_reconfirmation"], 0)
            self.assertEqual(row_reconf["confirmation_count"], 1)

    def test_stable_and_core_protected_from_excessive_decay(self):
        """Memórias 'stable' ou de tier 'core' não sofrem decaimento agressivo."""
        passado_100d = (datetime.now() - timedelta(days=100)).isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fatos_patrick
                (fato, category, importance, confidence, memory_tier, volatility, canonical_key, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                ("Patrick é desenvolvedor do jogo The Tower", "projeto", 0.95, 1.0, "core", "stable", "core_project_tower", passado_100d, passado_100d)
            )
            conn.commit()
            fato_core_id = cursor.lastrowid

        self.db.aplicar_confidence_decay(dias_volatil=14, dias_medio=60)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT confidence, needs_reconfirmation FROM fatos_patrick WHERE id = ?", (fato_core_id,))
            row = cursor.fetchone()
            self.assertGreaterEqual(row["confidence"], 0.85)
            self.assertEqual(row["needs_reconfirmation"], 0)

    def test_deduplicar_fatos_redundantes(self):
        """Deduplicação inativa réplicas mais antigas com a mesma canonical_key."""
        now_iso = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Insere fato mais antigo
            cursor.execute(
                """
                INSERT INTO fatos_patrick (fato, canonical_key, active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                ("Patrick joga FFXIV", "fav_game", now_iso, now_iso)
            )
            id_antigo = cursor.lastrowid

            # Insere fato mais recente
            cursor.execute(
                """
                INSERT INTO fatos_patrick (fato, canonical_key, active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                ("Patrick joga Final Fantasy XIV atualmente", "fav_game", now_iso, now_iso)
            )
            id_recente = cursor.lastrowid
            conn.commit()

        dedup_count = self.db.deduplicar_fatos_redundantes()
        self.assertEqual(dedup_count, 1)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT active FROM fatos_patrick WHERE id = ?", (id_antigo,))
            self.assertEqual(cursor.fetchone()["active"], 0)

            cursor.execute("SELECT active FROM fatos_patrick WHERE id = ?", (id_recente,))
            self.assertEqual(cursor.fetchone()["active"], 1)

    def test_archiving_old_resolved_open_loops(self):
        """Open loops resolvidos há mais de 30 dias são arquivados."""
        passado_40d = (datetime.now() - timedelta(days=40)).isoformat()
        passado_5d = (datetime.now() - timedelta(days=5)).isoformat()

        # Loop 1: resolvido há 40 dias
        loop1_id = self.db.adicionar_open_loop("ongoing", "Loop antigo resolvido")
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE open_loops SET status = 'resolved', resolved_at = ? WHERE id = ?",
                (passado_40d, loop1_id)
            )
            conn.commit()

        # Loop 2: resolvido há 5 dias
        loop2_id = self.db.adicionar_open_loop("ongoing", "Loop recente resolvido")
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE open_loops SET status = 'resolved', resolved_at = ? WHERE id = ?",
                (passado_5d, loop2_id)
            )
            conn.commit()

        # Loop 3: ainda aberto
        loop3_id = self.db.adicionar_open_loop("ongoing", "Loop ativo")

        arquivados = self.db.arquivar_open_loops_antigos(dias=30)
        self.assertEqual(arquivados, 1)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_archived FROM open_loops WHERE id = ?", (loop1_id,))
            self.assertEqual(cursor.fetchone()["is_archived"], 1)

            cursor.execute("SELECT is_archived FROM open_loops WHERE id = ?", (loop2_id,))
            self.assertEqual(cursor.fetchone()["is_archived"], 0)

            cursor.execute("SELECT is_archived FROM open_loops WHERE id = ?", (loop3_id,))
            self.assertEqual(cursor.fetchone()["is_archived"], 0)

        # Garante que get_open_loops_ativos só retorna o loop 3
        ativos = self.db.get_open_loops_ativos()
        self.assertEqual(len(ativos), 1)
        self.assertEqual(ativos[0]["id"], loop3_id)

    def test_session_reflector_apply_reflection(self):
        """SessionReflector aplica resumo, cria novos open loops e resolve loops existentes."""
        # Cria um loop que será resolvido na reflexão
        existing_loop_id = self.db.adicionar_open_loop("waiting_reply", "Aguardando resposta da entrevista")

        reflection_data = {
            "topics": ["Entrevista de Emprego", "Fim de Semana"],
            "summary": "Patrick contou que foi aprovado na entrevista e combinamos de comemorar no fim de semana.",
            "open_loops": [
                {
                    "loop_type": "decision",
                    "content": "Decidir restaurante para comemorar no sábado",
                    "importance": 0.7
                }
            ],
            "resolved_loops": [
                {
                    "loop_id": existing_loop_id,
                    "resolution_notes": "Patrick foi aprovado na vaga com sucesso!"
                }
            ],
            "relationship_moments": [
                {
                    "momento": "Comemoramos juntos a aprovação dele no novo emprego",
                    "importance": 0.9
                }
            ],
            "events": []
        }

        result = self.reflector.apply_reflection(reflection_data, allowed_loop_ids={existing_loop_id})
        self.assertIsNotNone(result["summary_id"])
        self.assertEqual(len(result["created_loops"]), 1)
        self.assertEqual(result["resolved_loops_count"], 1)
        self.assertEqual(len(result["moments_created"]), 1)

        # Valida que o loop anterior foi marcado como resolvido
        loop_resolvido = self.db.get_open_loop(existing_loop_id)
        self.assertEqual(loop_resolvido["status"], "resolved")
        self.assertIn("aprovado", loop_resolvido["resolution_notes"])

        # Valida que o novo loop está aberto
        novo_loop = self.db.get_open_loop(result["created_loops"][0])
        self.assertEqual(novo_loop["status"], "open")
        self.assertEqual(novo_loop["loop_type"], "decision")

    @patch("session_reflector.OpenAI")
    def test_session_reflector_llm_flow(self, mock_openai_cls):
        """Testa a chamada completa do SessionReflector à LLM com mock de JSON estruturado."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "topics": ["Projetos", "Faculdade"],
            "summary": "Patrick falou bastante sobre o projeto The Tower hoje.",
            "open_loops": [],
            "resolved_loops": [],
            "relationship_moments": [],
            "events": []
        })
        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        reflector = SessionReflector(db=self.db, llm_client=mock_client)
        messages = [
            {"role": "user", "content": "Hoje trabalhei bastante no The Tower amor"},
            {"role": "assistant", "content": "Que orgulho de você vida! Rendeu bem?"}
        ]
        res = reflector.reflect_session(messages)
        self.assertEqual(res["topics"], ["Projetos", "Faculdade"])
        self.assertIn("The Tower", res["summary"])

    def test_context_builder_includes_reconfirmation_opportunity(self):
        """Se houver memória precisando de reconfirmação, ContextBuilder injeta o bloco correspondente."""
        # Cria memória precisando de reconfirmação
        now_iso = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fatos_patrick
                (fato, category, importance, confidence, memory_tier, volatility, canonical_key, active, needs_reconfirmation, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                """,
                ("Patrick ainda está cursando Engenharia de Software", "estudos", 0.85, 0.55, "standard", "medium", "course_studies", now_iso, now_iso)
            )
            conn.commit()

        mgr = MemoryManager(db=self.db)
        cb = ContextBuilder(memory_mgr=mgr)
        prompt = cb.build_system_prompt()
        self.assertIn("[OPORTUNIDADE DE RECONFIRMAÇÃO SUTIL]", prompt)
        self.assertIn("Patrick ainda está cursando Engenharia de Software", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
