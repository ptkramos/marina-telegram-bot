"""MediaLookupService — Patch 023."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from calendar_world import RealContextCache
from config import settings
from db import DatabaseManager
from media_lookup_service import (
    MediaLookupService,
    _looks_like_title,
)


class TitleFilterTests(unittest.TestCase):
    def test_accepts_real_titles(self):
        for t in ("Wicked", "Konosuba", "Vale dos Dinossauros", "The Boys", "Chainsaw Man"):
            self.assertTrue(_looks_like_title(t), f"deveria aceitar {t!r}")

    def test_rejects_blocklist(self):
        for t in ("Netflix", "Amazon", "STREAMING", "brasil", "cinema", "top"):
            self.assertFalse(_looks_like_title(t), f"deveria rejeitar {t!r}")

    def test_rejects_too_short_or_too_long(self):
        self.assertFalse(_looks_like_title("Ab"))
        self.assertFalse(_looks_like_title("A" * 61))

    def test_rejects_all_caps_acronyms(self):
        self.assertFalse(_looks_like_title("HBOMAX"))


class MediaLookupServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "media.db")
        self.service = MediaLookupService(self.db)
        self.now = datetime(2026, 9, 20, 22, 0)

    def test_disabled_returns_empty(self):
        with patch.object(settings, "MEDIA_LOOKUP_ENABLED", False):
            self.assertFalse(self.service.refresh_if_stale(self.now))
            self.assertEqual(self.service.get_prompt_block(self.now), "")

    def test_prompt_block_empty_when_cache_absent(self):
        self.assertEqual(self.service.get_prompt_block(self.now), "")

    def test_cache_populated_block_renders(self):
        # Popula cache manualmente sem depender da rede.
        RealContextCache(self.db).put(
            "media_hot:br", kind="media",
            payload={"titles": ["Wicked", "Chainsaw Man", "The Boys"]},
            source_name="test",
            observed_at=self.now, expires_at=self.now + timedelta(hours=24),
        )
        block = self.service.get_prompt_block(self.now)
        self.assertIn("[MÍDIA REAL EM ALTA", block)
        self.assertIn("Wicked", block)
        self.assertIn("The Boys", block)

    def test_expired_cache_not_used(self):
        RealContextCache(self.db).put(
            "media_hot:br", kind="media",
            payload={"titles": ["Old Movie"]},
            source_name="test",
            observed_at=self.now - timedelta(hours=25),
            expires_at=self.now - timedelta(hours=1),
        )
        self.assertEqual(self.service.get_prompt_block(self.now), "")

    def test_refresh_fail_open(self):
        # Sem REAL_CONTEXT_FETCH_ENABLED e sem rede, refresh nunca deve lançar.
        with patch.object(settings, "REAL_CONTEXT_FETCH_ENABLED", False):
            self.assertFalse(self.service.refresh_if_stale(self.now))


if __name__ == "__main__":
    unittest.main()


class TitleExtractionRegressionTests(unittest.TestCase):
    """Auditoria #3 — o prompt recebeu '- Veja as 10 s' e '- Top 10 Netflix: s'.

    O lookahead aceitava zero espaços antes do gatilho "é", então o "é" dentro
    de "séries" cortava a manchete no meio da palavra.
    """

    def _extrair(self, body):
        from media_lookup_service import _TITLE_RE, _looks_like_title
        out = []
        for m in _TITLE_RE.finditer(body):
            c = (m.group(1) or m.group(2) or "").strip(" .,-:;'\"")
            if _looks_like_title(c):
                out.append(c)
        return out

    def test_manchetes_nao_viram_titulo(self):
        for body in ("Top 10 Netflix: séries mais vistas da semana",
                     "Veja as 10 séries mais assistidas",
                     "Netflix atualiza lista das séries do momento"):
            with self.subTest(body=body):
                self.assertEqual(self._extrair(body), [])

    def test_titulos_reais_sobrevivem(self):
        casos = {
            'O filme "Duna: Parte Dois" estreou no streaming': "Duna: Parte Dois",
            "Wandinha estreou na Netflix com recorde": "Wandinha",
            "Round 6 é a série mais vista": "Round 6",
        }
        for body, esperado in casos.items():
            with self.subTest(body=body):
                self.assertIn(esperado, self._extrair(body))
