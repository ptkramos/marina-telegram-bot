"""Auditoria #3 — montar prompt não pode sair pela rede.

O Patch 023 colocou `MediaLookupService.refresh_if_stale()` dentro de
`WorldContextBuilder.build()`. Como o refresh é síncrono e busca em
DDGS/Wikipedia/Brave, a montagem do prompt passou a fazer rede:

  · na conversa real, o turno da Marina esperava a busca sempre que o cache
    diário vencia (os logs mostram 5–10s de timeout por provedor);
  · na suíte, todo teste que montasse um prompt disparava as três buscas,
    porque banco temporário nasce com cache vazio — a suíte foi para ~15min e
    passou a depender de rate limit alheio (HTTP 429 do Brave em corrida normal).

O refresh agora vive em `bot.media_lookup_routine`, no scheduler. `build()` só
lê o cache.
"""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import media_lookup_service
from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from world_context import WorldContextBuilder


class PromptBuildDoesNotRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(Path(self.tmp.name) / "no_network.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO world_bootstrap (key, value, updated_at)
                   VALUES ('clean_canonical_start_done', '1', '2026-09-18T00:00:00')"""
            )
        self.builder = WorldContextBuilder(self.db)

    def test_build_nao_chama_refresh_if_stale(self):
        with patch.object(media_lookup_service.MediaLookupService,
                          "refresh_if_stale") as refresh:
            self.builder.build(now=datetime(2026, 9, 21, 14, 0), user_message="oi amor")
        refresh.assert_not_called()

    def test_build_ainda_le_o_cache(self):
        """Tirar o refresh não pode ter desligado a leitura do bloco."""
        with patch.object(media_lookup_service.MediaLookupService, "get_prompt_block",
                          return_value="[MÍDIA REAL EM ALTA]\n- Duna: Parte Dois") as bloco:
            prompt = self.builder.build(
                now=datetime(2026, 9, 21, 14, 0), user_message="vamos ver um filme?")
        bloco.assert_called_once()
        self.assertIn("Duna: Parte Dois", prompt)

    def test_falha_no_cache_nao_derruba_o_turno(self):
        """Contrato de fail-open: mídia é enriquecimento, não requisito."""
        with patch.object(media_lookup_service.MediaLookupService, "get_prompt_block",
                          side_effect=RuntimeError("cache corrompido")):
            prompt = self.builder.build(
                now=datetime(2026, 9, 21, 14, 0), user_message="oi")
        self.assertIn("Marina Salles", prompt)


class RefreshLivesInSchedulerTests(unittest.TestCase):
    """O refresh precisa existir em algum lugar — só não no caminho do turno."""

    def test_bot_expoe_job_de_media_lookup(self):
        import bot
        self.assertTrue(hasattr(bot, "media_lookup_routine"),
                        "o refresh do cache de mídia deve ter um job próprio")

    def test_job_esta_registrado_no_scheduler(self):
        """Os jobs vivem em `post_init`, não em `main` — `main` só monta handlers."""
        import inspect
        import bot
        fonte = inspect.getsource(bot.post_init)
        self.assertIn("media_lookup_routine", fonte,
                      "o job precisa ser registrado no scheduler de post_init, senão "
                      "o cache nunca é atualizado e o bloco de mídia fica vazio pra sempre")

    def test_job_registrado_junto_dos_outros_do_scheduler(self):
        """Guard contra registrar em função que não roda no startup."""
        import inspect
        import bot
        fonte = inspect.getsource(bot.post_init)
        for vizinho in ("memory_hygiene_routine", "pending_response_routine"):
            self.assertIn(vizinho, fonte)

    def test_job_respeita_o_kill_switch(self):
        import inspect
        import bot
        fonte = inspect.getsource(bot.media_lookup_routine)
        self.assertIn("MEDIA_LOOKUP_ENABLED", fonte)


if __name__ == "__main__":
    unittest.main()
