"""Offline acceptance: real bootstrap -> memory retrieval -> context payload."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bootstrap_v36 import bootstrap
from config import settings
from context_builder import ContextBuilder
from db import DatabaseManager
from memory import MemoryManager


class TestV360Acceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / 'acceptance.db')
        self.now = datetime(2026, 9, 17, 16)
        self.old = 'Patrick coleciona orquídeas violetas na continuidade antiga'
        self.new = 'Patrick começou uma coleção de orquídeas amarelas hoje'
        self.db.adicionar_fato_patrick(self.old)
        bootstrap(self.db.db_path, trusted_cycle_anchor='2026-09-02', now=self.now)
        self.memory = MemoryManager(db=self.db)
        self.builder = ContextBuilder(memory_mgr=self.memory)

    def test_old_memory_disappears_and_new_memory_survives_repeat_bootstrap(self):
        with patch.object(settings, 'LIVING_WORLD_ENABLED', True), \
             patch.object(settings, 'ACADEMIC_LIFE_ENABLED', False), \
             patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False), \
             patch.object(settings, 'RESPONSE_RHYTHM_ENABLED', False), \
             patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', False):
            clean = self.builder.build_system_prompt(user_message='orquídeas', now=self.now)
            self.assertNotIn(self.old, clean)
            self.assertEqual(self.db.buscar_fatos_fts('orquídeas'), [])
            self.db.adicionar_fato_patrick(self.new)
            bootstrap(self.db.db_path, trusted_cycle_anchor='2026-09-02', now=self.now)
            current = self.builder.build_system_prompt(user_message='orquídeas', now=self.now)
        self.assertIn(self.new, current)
        self.assertNotIn(self.old, current)
        self.assertIn('Marina Salles', current)
        self.assertIn('Idade hoje: 20 anos', current)
        self.assertNotIn('Marina Seltin', current)

    def test_control_languages_use_existing_cycle_and_safe_fallback(self):
        with patch.object(self.memory.cycle_mgr, 'get_cycle_info',
                          wraps=self.memory.cycle_mgr.get_cycle_info) as cycle:
            for language, heading in [('en', '[CONTROL RULES]'), ('pt-BR', '[REGRAS DE CONTROLE]')]:
                with patch.object(settings, 'LIVING_WORLD_ENABLED', True), \
                     patch.object(settings, 'ACADEMIC_LIFE_ENABLED', False), \
                     patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False), \
                     patch.object(settings, 'PROMPT_CONTROL_LANGUAGE', language):
                    prompt = self.builder.build_system_prompt(now=self.now)
                self.assertIn(heading, prompt)
                self.assertIn('fonte única: MenstrualCycleManager', prompt)
                self.assertIn('Marina Salles', prompt)
            # Cada construção consulta o ciclo para energia emocional e para
            # o bloco canônico de contexto.
            self.assertEqual(cycle.call_count, 4)
        with self.db.get_connection() as conn:
            count = conn.execute('SELECT COUNT(*) FROM world_state').fetchone()[0]
        with patch.object(settings, 'LIVING_WORLD_ENABLED', False), \
             patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', False):
            safe = self.builder.build_system_prompt(now=self.now)
        self.assertNotIn('Marina Seltin', safe)
        self.assertIn('Marina Salles', safe)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM world_state').fetchone()[0], count)
