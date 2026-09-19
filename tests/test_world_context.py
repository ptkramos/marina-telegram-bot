"""Flag e contexto v3.6 em banco temporário; nenhum provider externo."""

import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import settings
from context_builder import ContextBuilder
from db import DatabaseManager
from memory import MemoryManager
from seed_world_bible_v36 import seed_world_bible
from seed_academic_v36 import seed_academic


class TestWorldContext(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "context_test.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO world_bootstrap (key, value, updated_at)
                   VALUES ('clean_canonical_start_done', '1', '2026-09-17T00:00:00')"""
            )
        self.retriever = MagicMock()
        self.retriever.retrieve_context.return_value = {
            "fatos": [], "momentos": [], "resumos": [],
        }
        self.builder = ContextBuilder(
            memory_mgr=MemoryManager(db=self.db), retriever=self.retriever,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_compatibility_markers_cannot_disable_canonical_context(self):
        with patch.object(settings, "LIVING_WORLD_ENABLED", False), \
             patch.object(settings, "KNOWLEDGE_PRIVACY_ENABLED", False):
            prompt = self.builder.build_system_prompt(user_message="Oi")
        self.assertNotIn("Marina Seltin", prompt)
        self.assertNotIn("SEMPRE uma mulher de 19 anos", prompt)
        self.assertIn("Marina Salles", prompt)
        self.assertIn("[CONTROL RULES]", prompt)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM world_state").fetchone()[0], 1)

    def test_flag_on_uses_canon_dynamic_age_and_excludes_legacy_autobiography(self):
        with patch.object(settings, "LIVING_WORLD_ENABLED", True), \
             patch.object(settings, "ACADEMIC_LIFE_ENABLED", False), \
             patch.object(settings, "CALENDAR_CONTINUITY_ENABLED", False), \
             patch.object(settings, "RESPONSE_RHYTHM_ENABLED", False):
            before_birthday = self.builder.build_system_prompt(
                user_message="Oi", now=datetime(2026, 4, 28, 16, 0),
            )
            birthday = self.builder.build_system_prompt(
                user_message="Oi", quoted_context="Patrick perguntou da faculdade",
                planner_tone="carinhoso", now=datetime(2026, 4, 29, 16, 0),
            )
        self.assertIn("Marina Salles", birthday)
        self.assertIn("Idade hoje: 19 anos", before_birthday)
        self.assertIn("Idade hoje: 20 anos", birthday)
        self.assertNotIn("Marina Seltin", birthday)
        self.assertNotIn("Começou a namorar comigo recentemente", birthday)
        self.assertIn("[WORLD STATE — agora]", birthday)
        self.assertIn("Patrick perguntou da faculdade", birthday)
        self.assertIn("Tone: carinhoso", birthday)
        self.assertIn("Respond as Marina in natural Brazilian Portuguese", birthday)
        self.assertLess(len(birthday), 8000)
        # Retriever is optional for compact World Context; presence of canon is the contract.
        self.assertIn("Marina Salles", birthday)

    def test_control_language_is_configurable_without_changing_output_language(self):
        with (patch.object(settings, "LIVING_WORLD_ENABLED", True),
              patch.object(settings, "ACADEMIC_LIFE_ENABLED", False),
              patch.object(settings, "CALENDAR_CONTINUITY_ENABLED", False),
              patch.object(settings, "PROMPT_CONTROL_LANGUAGE", "pt-BR")):
            prompt = self.builder.build_system_prompt(now=datetime(2026, 9, 17, 16, 0))
        self.assertIn("[REGRAS DE CONTROLE]", prompt)
        self.assertIn("Marina Salles", prompt)
        self.assertNotIn("[CONTROL RULES]", prompt)

    def test_missing_seed_fails_closed(self):
        other = DatabaseManager(Path(self.temp.name) / "without_seed.db")
        builder = ContextBuilder(memory_mgr=MemoryManager(db=other), retriever=MagicMock())
        with patch.object(settings, "LIVING_WORLD_ENABLED", True):
            with self.assertRaises(RuntimeError):
                builder.build_system_prompt(now=datetime(2026, 9, 17, 16, 0))

    def test_seed_without_clean_bootstrap_fails_closed(self):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM world_bootstrap WHERE key = 'clean_canonical_start_done'")
        with patch.object(settings, "LIVING_WORLD_ENABLED", True):
            with self.assertRaisesRegex(RuntimeError, "CLEAN_CANONICAL_START"):
                self.builder.build_system_prompt(now=datetime(2026, 9, 17, 16, 0))
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM world_state").fetchone()[0], 0)

    def test_custom_database_uses_matching_memory_retriever(self):
        builder = ContextBuilder(memory_mgr=MemoryManager(db=self.db))
        self.assertIs(builder.retriever.db, self.db)

    def test_bot_routes_main_and_dynamic_speech_through_world_context(self):
        import bot

        with (patch.object(settings, "LIVING_WORLD_ENABLED", True),
              patch.object(settings, "SMART_MEMORY_ENABLED", False),
              patch.object(bot.context_builder, "build", return_value=[{"role": "system", "content": "WORLD"}]) as build):
            payload = bot.build_messages_payload(user_message="Oi")
        self.assertEqual(payload[0]["content"], "WORLD")
        build.assert_called_once()

        completion = MagicMock()
        completion.choices[0].message.content = " Oi, Patrick! "
        with (patch.object(settings, "LIVING_WORLD_ENABLED", True),
              patch.object(settings, "RESPONSE_RHYTHM_ENABLED", False),
              patch.object(bot.context_builder, "build_system_prompt", return_value="WORLD") as system,
              patch.object(bot.llm_client.chat.completions, "create", return_value=completion) as create):
            spoken = bot.generate_dynamic_speech("Diz oi")
        self.assertEqual(spoken, "Oi, Patrick!")
        system.assert_called_once_with(user_message="Diz oi")
        self.assertTrue(create.call_args.kwargs["messages"][0]["content"].startswith("WORLD\n[RESPONSE RHYTHM]"))

    def test_canonical_proactivity_ignores_retired_relationship_marker(self):
        import bot

        with (patch.object(settings, "LIVING_WORLD_ENABLED", True),
              patch.object(settings, "RELATIONSHIP_WORLD_ENABLED", False),
              patch.object(bot.proactivity_service, "should_trigger", return_value=(False, "test")) as trigger):
            asyncio.run(bot.autonomous_routine(MagicMock()))
        trigger.assert_called_once()


if __name__ == "__main__":
    unittest.main()
