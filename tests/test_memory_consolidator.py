"""
Suite de Testes Automatizados Offline para o Memory Consolidator da Marina Salles (v3.7.0).
Testa lógica de banco de dados isolada (sem afetar dados de produção)
e testes de inteligência de extração/filtragem com LLM real.
"""
import sys
import os
import unittest
import tempfile
from pathlib import Path

# Adiciona o diretório raiz ao path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from memory_consolidator import MemoryConsolidator


class TestMemoryConsolidatorDatabase(unittest.TestCase):
    """Testa a integridade do banco SQLite com o consolidator em banco temporário isolado."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_memory.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.consolidator = MemoryConsolidator(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_migrations_applied(self):
        """Verifica se todas as migrações (incluindo FTS5 e Smart Memory) foram aplicadas."""
        self.assertGreaterEqual(self.db.get_schema_version(), 2)

    def test_apply_consolidation_and_fts_sync(self):
        """Testa inserção de fatos, momentos, resumos e sincronização FTS."""
        payload = {
            "facts_to_create": [
                {
                    "fato": "Patrick prefere energético Monster Ultra White",
                    "category": "preferencia",
                    "importance": 0.7,
                    "confidence": 1.0,
                    "supersedes_id": None
                }
            ],
            "facts_to_deactivate": [],
            "important_moments": [
                {
                    "momento": "Primeiro jantar que cozinhamos juntos no apê",
                    "importance": 0.9
                }
            ],
            "topic_summary": "Conversa sobre bebidas favoritas e culinária"
        }

        result = self.consolidator.apply_consolidation(payload)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["moments"], 1)
        self.assertTrue(result["summary_saved"])

        # Verifica dados no SQLite
        fatos = self.db.get_fatos_patrick_detalhados()
        self.assertTrue(any("Monster Ultra White" in f["fato"] for f in fatos))

        # Verifica busca FTS5 em tempo real
        busca = self.db.buscar_fatos_fts("Monster")
        self.assertEqual(len(busca), 1)
        self.assertIn("Monster", busca[0]["fato"])

    def test_ambiguous_referent_is_never_persisted(self):
        payload = {
            "facts_to_create": [{
                "fato": "Patrick considera Marina Salles parecida com outra pessoa",
                "category": "relacionamento",
                "importance": 0.6,
                "confidence": 0.8,
            }],
            "facts_to_deactivate": [],
            "important_moments": [{
                "momento": "Patrick disse que Marina é parecida com outra pessoa",
                "importance": 0.8,
            }],
            "topic_summary": "Conversa sobre Marina ser parecida com outra pessoa",
        }

        result = self.consolidator.apply_consolidation(payload)

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["moments"], 0)
        self.assertFalse(result["summary_saved"])
        facts = self.db.get_fatos_patrick_detalhados()
        self.assertFalse(any("parecida com outra pessoa" in row["fato"] for row in facts))

    def test_soak_reset_clears_learning_but_preserves_canonical_profile(self):
        self.db.adicionar_mensagem('user', 'mensagem do soak antigo')
        self.db.adicionar_fato_patrick('Patrick gosta de um teste antigo')
        self.db.salvar_estilo('risada', 'kkkk', ['kkkk'])
        self.db.set_estado_relacional('current_shared_topic', 'assunto antigo')
        self.db.ajustar_emocao('energy', -0.2)

        self.db.reset_soak_learning()

        self.assertEqual(self.db.get_total_conversas(), 0)
        self.assertEqual(self.db.get_estilo(), {})
        self.assertEqual(self.db.get_fatos_patrick(), ['Nome: Patrick Ramos'])
        self.assertEqual(self.db.get_estado_relacional('current_shared_topic'),
                         'dia a dia e planos juntos')
        emotions = self.db.get_estado_emocional()
        self.assertEqual(emotions['energy']['valor'], emotions['energy']['baseline'])
        self.assertEqual(self.db.get_perfil()['nome'], 'Marina Salles')

    def test_contradiction_handling(self):
        """Testa desativação de fato antigo contradito."""
        # 1. Cria fato inicial
        fato_antigo_id = self.db.adicionar_fato_patrick(
            fato="Patrick adora tomar café expresso forte",
            category="preferencia"
        )

        # 2. Consolidação que contradiz o fato
        payload = {
            "facts_to_create": [
                {
                    "fato": "Patrick parou de tomar café e agora bebe chá verde",
                    "decision": "update",
                    "category": "preferencia",
                    "importance": 0.8,
                    "confidence": 1.0,
                    "supersedes_id": fato_antigo_id
                }
            ],
            "facts_to_deactivate": [
                {
                    "existing_fact_id": fato_antigo_id,
                    "reason": "Parou de tomar café"
                }
            ],
            "important_moments": [],
            "topic_summary": "Mudança de hábitos matinais"
        }
        payload["_candidate_fact_ids"] = {fato_antigo_id}

        self.consolidator.apply_consolidation(payload)

        # Fato ativo deve conter o novo, e o antigo deve estar desativado
        fatos_ativos = self.db.get_fatos_patrick(active_only=True)
        self.assertTrue(any("chá verde" in f for f in fatos_ativos))
        self.assertFalse(any("café expresso forte" in f for f in fatos_ativos))

        # Fato antigo ainda existe no histórico completo (active=0)
        fatos_todos = self.db.get_fatos_patrick(active_only=False)
        self.assertTrue(any("café expresso forte" in f for f in fatos_todos))


@unittest.skipUnless(os.getenv("MARINA_LIVE_TESTS") == "1",
                     "chama o modelo de verdade (custa e oscila): rode com MARINA_LIVE_TESTS=1")
class TestMemoryConsolidatorLLM(unittest.TestCase):
    """Extração e descarte com chamadas REAIS ao modelo configurado.

    Fora da suíte por padrão: com temperatura > 0 o mesmo diálogo banal às vezes
    gera fato e às vezes não (falhou na troca para o GPT-5.6 Luna e passou na
    rodada seguinte), e cada execução gasta credencial paga."""

    @classmethod
    def setUpClass(cls):
        cls.consolidator = MemoryConsolidator()

    def setUp(self):
        import time
        time.sleep(2.0)

    def test_casual_chitchat_is_ignored(self):
        """Conversas casuais banais não devem gerar fatos permanentes."""
        dialogue = [
            {"role": "user", "content": "Oi amor! Tudo bem por aí?"},
            {"role": "assistant", "content": "Oii vida! Tudo ótimo aqui no apê e com você? 🥰"},
            {"role": "user", "content": "Tudo certinho também, só passei pra te dar um cheiro"},
            {"role": "assistant", "content": "Ai que delícia amor, adorei! kkkk te amo"},
            {"role": "user", "content": "Te amo também vida, beijo!"}
        ]

        result = self.consolidator.consolidate_dialogue(dialogue, existing_facts=[])
        err = str(result.get("error") or "")
        if err and ("402" in err or "Connection error" in err or "ConnectError" in err):
            self.skipTest(f"LLM indisponível no ambiente de teste: {err}")
        self.assertEqual(len(result.get("facts_to_create", [])), 0, "Chitchat casual não deve criar fatos!")

    def test_real_fact_extraction(self):
        """Informação relevante deve ser extraída com categoria e resumo adequados."""
        dialogue = [
            {"role": "user", "content": "Amor, novidade: voltei a jogar Final Fantasy XIV ontem no PC, escolhi a classe Black Mage!"},
            {"role": "assistant", "content": "Mentira amor! Que legal! Quero ver você jogando depois hein"},
            {"role": "user", "content": "Sim! Vou tentar jogar um pouquinho todo fim de semana"}
        ]

        result = self.consolidator.consolidate_dialogue(dialogue, existing_facts=[])
        err = str(result.get("error") or "")
        if err and ("402" in err or "Connection error" in err or "ConnectError" in err):
            self.skipTest(f"LLM indisponível no ambiente de teste: {err}")
        fatos = result.get("facts_to_create", [])
        self.assertGreaterEqual(len(fatos), 1, "Deveria ter extraído ao menos um fato sobre FFXIV")
        fato_texto = (fatos[0].get("fato") or fatos[0].get("fact") or "").lower()
        self.assertTrue("final fantasy" in fato_texto or "ffxiv" in fato_texto)

    def test_contradiction_detection(self):
        """Deve detectar contradição com fato previamente conhecido."""
        existing_facts = [
            {
                "id": 42,
                "fato": "Patrick adora tomar café todos os dias",
                "category": "preferencia"
            }
        ]
        dialogue = [
            {"role": "user", "content": "Amor, lembra daquele meu costume de tomar café? Cortei 100%, me fazia mal pro estômago. Agora só tomo suco de laranja natural de manhã."},
            {"role": "assistant", "content": "Sério amor? Que bom que você cuidou disso! Vai fazer bem pra você"}
        ]

        result = self.consolidator.consolidate_dialogue(dialogue, existing_facts=existing_facts)
        err = str(result.get("error") or "")
        if err and ("402" in err or "Connection error" in err or "ConnectError" in err):
            self.skipTest(f"LLM indisponível no ambiente de teste: {err}")
        deactivations = result.get("facts_to_deactivate", [])
        fatos_novos = result.get("facts_to_create", [])
        self.assertTrue(
            any(f.get("decision") in ("update", "contradiction") and f.get("existing_fact_id") == 42 for f in fatos_novos),
            "O fato ID 42 deve ser substituído por decisão atômica"
        )
        self.assertTrue(
            any(
                any(w in (f.get("fato") or f.get("fact") or "").lower() for w in ("suco", "juice", "café", "cafe", "coffee", "laranja", "orange"))
                for f in fatos_novos
            ),
            "Deveria ter criado fato sobre suco de laranja ou a alteração do hábito de café"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
