"""Stage 15b / Round 2 — Prompt Authority & legacy cleanup contracts."""
from __future__ import annotations

import ast
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from config import settings
from context_builder import ContextBuilder
from db import DatabaseManager
from memory import MemoryManager
from planner import PLANNER_SYSTEM_PROMPT
from memory_consolidator import CONSOLIDATOR_SYSTEM_PROMPT
from session_reflector import SESSION_REFLECTOR_SYSTEM_PROMPT
from vision_service import VISION_PROMPT, vision_service
from prompt_policy import (
    FORBIDDEN_LEGACY_TOKENS,
    build_safe_core_prompt,
    continuity_repair_constraint,
    format_web_evidence,
    format_vision_evidence,
    get_daypart,
    is_continuity_challenge,
    is_canonical_runtime_ready,
    reminder_offer_constraint,
    reminder_clarification_constraint,
)
from prompts import EVENTOS_COTIDIANO, MARIN_SYSTEM_PROMPT
from seed_world_bible_v36 import seed_world_bible
from seed_academic_v36 import seed_academic
from style_engine import StyleEngine
from visual_profile import MARINA_VISUAL_DNA_BASE


ROOT = Path(__file__).resolve().parents[1]


class DaypartAndSafeCoreTests(unittest.TestCase):
    def test_daypart_neutral(self):
        self.assertEqual(get_daypart(datetime(2026, 9, 18, 9)), 'morning')
        self.assertEqual(get_daypart(datetime(2026, 9, 18, 15)), 'afternoon')
        self.assertEqual(get_daypart(datetime(2026, 9, 18, 20)), 'evening')
        self.assertEqual(get_daypart(datetime(2026, 9, 18, 2)), 'late_night')

    def test_safe_core_forbids_legacy(self):
        prompt = build_safe_core_prompt(db=None)
        for token in FORBIDDEN_LEGACY_TOKENS:
            self.assertNotIn(token, prompt)
        self.assertIn('Marina Salles', prompt)

    def test_monolith_retired(self):
        self.assertIsNone(MARIN_SYSTEM_PROMPT)
        self.assertEqual(EVENTOS_COTIDIANO, ())


class DynamicAgeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'age.db')
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.builder = ContextBuilder(memory_mgr=MemoryManager(db=self.db))

    def test_birthday_boundary(self):
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO world_bootstrap (key, value, updated_at)
                   VALUES ('clean_canonical_start_done', '1', '2026-09-17T00:00:00')"""
            )
        with patch.object(settings, 'LIVING_WORLD_ENABLED', True), \
             patch.object(settings, 'ACADEMIC_LIFE_ENABLED', False), \
             patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False), \
             patch.object(settings, 'RESPONSE_RHYTHM_ENABLED', False):
            a = self.builder.build_system_prompt(now=datetime(2026, 4, 28, 12))
            b = self.builder.build_system_prompt(now=datetime(2026, 4, 29, 12))
            c = self.builder.build_system_prompt(now=datetime(2027, 4, 29, 12))
        self.assertIn('Idade hoje: 19 anos', a)
        self.assertIn('Idade hoje: 20 anos', b)
        self.assertIn('Idade hoje: 21 anos', c)


class BackendPromptLanguageTests(unittest.TestCase):
    def test_control_prompts_english_markers(self):
        self.assertIn('You are Marina Salles', PLANNER_SYSTEM_PROMPT)
        self.assertIn('Extract durable facts', CONSOLIDATOR_SYSTEM_PROMPT)
        self.assertIn('internal session reflection', SESSION_REFLECTOR_SYSTEM_PROMPT)
        self.assertIn('visual perception extraction', VISION_PROMPT)
        for text in (PLANNER_SYSTEM_PROMPT, CONSOLIDATOR_SYSTEM_PROMPT,
                     SESSION_REFLECTOR_SYSTEM_PROMPT, VISION_PROMPT):
            self.assertNotIn('Você é', text)


class VisualDnaTests(unittest.TestCase):
    def test_no_fixed_numeric_age(self):
        self.assertNotIn('19yo', MARINA_VISUAL_DNA_BASE)
        self.assertNotIn('20yo', MARINA_VISUAL_DNA_BASE)
        self.assertIn('young adult', MARINA_VISUAL_DNA_BASE)


class ProactivityNoEventosTests(unittest.TestCase):
    def test_legacy_eventos_never_consulted(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / 'pro.db')
        from proactivity_service import ProactivityService
        svc = ProactivityService(db)
        with patch('proactivity_service.random.choice', side_effect=AssertionError('EVENTOS consulted')):
            info = svc.determine_proactive_prompt(now=datetime(2026, 9, 18, 15))
        self.assertEqual(info['reason'], 'neutral_affection')
        self.assertNotIn('banho', info['instruction'].lower())


class SafeCoreStaleAttackTests(unittest.TestCase):
    """Adversarial: pre-clean SafeCore must not resurrect pre-v3.6 memory/history/style."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'stale.db')
        self.mm = MemoryManager(db=self.db)
        self.builder = ContextBuilder(memory_mgr=self.mm)
        # Poison DB with legacy autobiography + history + fake style
        self.db.adicionar_fato_patrick(
            'CONTINUIDADE ANTIGA INVALIDA: Patrick e Marina moram juntos no apartamento antigo'
        )
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO conversas (timestamp, role, content)
                   VALUES (?, 'assistant', ?)""",
                (datetime.now().isoformat(),
                 'LEGACY INVALID: meu nome é Marina Seltin e tenho 19 anos'),
            )
        # Attempt fake style seed via old pattern — StyleEngine must not claim learned
        se = StyleEngine(db=self.db)
        self.assertEqual(se.patrick_sample_count(), 0)

    def test_incomplete_canonical_database_fails_closed(self):
        self.assertFalse(is_canonical_runtime_ready(self.db))
        with patch.object(settings, 'LIVING_WORLD_ENABLED', False), \
             patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', False), \
             patch.object(settings, 'MEMORY_INTELLIGENCE_ENABLED', True), \
             patch.object(settings, 'RESPONSE_RHYTHM_ENABLED', False):
            with self.assertRaisesRegex(RuntimeError, 'World Bible v3.6'):
                self.builder.build_system_prompt(
                    user_message='onde a gente mora amor?',
                    now=datetime(2026, 9, 18, 15),
                )

    def test_complete_canonical_seed_uses_only_post_reset_memory(self):
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute('DELETE FROM conversas')
            conn.execute('DELETE FROM fatos_patrick')
            conn.execute(
                """INSERT INTO world_bootstrap (key, value, updated_at)
                   VALUES ('clean_canonical_start_done', '1', ?)""",
                (datetime.now().isoformat(),),
            )
        self.assertTrue(is_canonical_runtime_ready(self.db))
        # Post-reset fact
        self.db.adicionar_fato_patrick('FATO POS-RESET: Patrick trabalha com software')
        with patch.object(settings, 'LIVING_WORLD_ENABLED', False), \
             patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', False), \
             patch.object(settings, 'MEMORY_INTELLIGENCE_ENABLED', True), \
             patch.object(settings, 'RESPONSE_RHYTHM_ENABLED', False):
            prompt = self.builder.build_system_prompt(
                user_message='o que eu faço no trabalho?',
                now=datetime(2026, 9, 18, 15),
            )
        self.assertIn('FATO POS-RESET', prompt)
        self.assertNotIn('Marina Seltin', prompt)


class WebVisionDataOnlyTests(unittest.TestCase):
    def test_web_context_data_only(self):
        block = format_web_evidence(['fato A', 'fato B'])
        self.assertIn('fato A', block)
        self.assertIn('WEB EVIDENCE', block)
        for bad in ('Use essas informações', 'sem citar que', 'INSTRUÇÃO'):
            self.assertNotIn(bad, block)

    def test_vision_context_data_only(self):
        ctx = vision_service.format_vision_context(
            {'scene': 'cozinha', 'people': ['Patrick'], 'food': [], 'objects': ['xícara'],
             'visible_text': [], 'notable_details': []},
            caption='café',
        )
        self.assertIn('cozinha', ctx)
        self.assertIn('VISION EVIDENCE', ctx)
        for bad in ('INSTRUÇÃO DE RESPOSTA', 'NUNCA diga', 'Reaja de forma', 'vejo na imagem'):
            self.assertNotIn(bad, ctx)
        # format_vision_evidence wrapper also clean
        wrapped = format_vision_evidence(['- scene: x'])
        self.assertEqual(wrapped, '- scene: x')


class InlineBotSystemPromptLanguageTests(unittest.TestCase):
    def test_reminder_constraints_english(self):
        offer = reminder_offer_constraint('dentista')
        clar = reminder_clarification_constraint('reunião')
        self.assertIn('TURN CONSTRAINT', offer)
        self.assertIn('TURN CONSTRAINT', clar)
        self.assertNotIn('INSTRUÇÃO OBRIGATÓRIA', offer)
        self.assertNotIn('INSTRUÇÃO CRÍTICA', clar)
        bot_src = (ROOT / 'bot.py').read_text(encoding='utf-8')
        self.assertNotIn('[INSTRUÇÃO OBRIGATÓRIA DESTE TURNO]', bot_src)
        self.assertNotIn('[INSTRUÇÃO CRÍTICA DESTE TURNO]', bot_src)

    def test_continuity_challenge_gets_grounded_repair_constraint(self):
        self.assertTrue(is_continuity_challenge('Como assim, quase acordando?'))
        self.assertTrue(is_continuity_challenge('Mas você falou outra coisa'))
        self.assertFalse(is_continuity_challenge('Como foi seu dia?'))
        block = continuity_repair_constraint('Acordei cedo para ir ao mercado')
        self.assertIn('exact contradiction', block)
        self.assertIn('Do not invent any reason', block)
        self.assertIn('mercado', block)


class StyleEngineFreshDbTests(unittest.TestCase):
    def test_fresh_db_no_fake_learned(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / 'style.db')
        eng = StyleEngine(db=db)
        self.assertEqual(eng.patrick_sample_count(), 0)
        self.assertEqual(eng.get_style_prompt_injection(), '')
        for _ in range(3):
            eng.processar_mensagem_patrick('kkkk trampo fechou amor')
        self.assertTrue(eng.has_learned_style())
        self.assertIn('SINCRONIA', eng.get_style_prompt_injection())


class CanonicalProactivityTests(unittest.TestCase):
    def test_only_grounded_engine_is_registered(self):
        src = (ROOT / 'bot.py').read_text(encoding='utf-8')
        self.assertNotIn('Chance espontânea: ~18%', src)
        tree = ast.parse(src)
        found = False
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef) and node.name == 'autonomous_routine':
                found = True
                dump = ast.dump(node)
                self.assertIn('autonomous_routine_v36', dump)
                self.assertNotIn('LIVING_WORLD_ENABLED', dump)
        self.assertTrue(found)


class LocationErrorNoApartmentTests(unittest.TestCase):
    def test_bot_errors_do_not_invent_apartment(self):
        src = (ROOT / 'bot.py').read_text(encoding='utf-8')
        # Round-1 already cleaned; keep regression
        lowered = src.lower()
        # Allow comments about not inventing; fail on user-facing invent phrases
        self.assertNotIn('tô no apê', lowered)
        self.assertNotIn('to no ape', lowered)
        self.assertNotIn('aqui no apartamento', lowered)


class ValidationArchiveTests(unittest.TestCase):
    def test_build_archive_excludes_secrets(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'build_validation_archive',
            ROOT / 'scripts' / 'build_validation_archive.py',
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        out = Path(temp.name) / 'clean.zip'
        members = mod.build_archive(out)
        self.assertTrue(out.exists())
        self.assertTrue(any(m.endswith('.py') for m in members))
        violations = mod.verify_archive(out)
        self.assertEqual(violations, [])
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            self.assertFalse(any(n.endswith('.env') and not n.endswith('.env.example') for n in names))
            self.assertFalse(any(n.endswith('.db') for n in names))


class PhotoDeferGatePresenceTests(unittest.TestCase):
    def test_photo_constraint_english_and_availability_wiring(self):
        from prompt_policy import PHOTO_TURN_CONSTRAINT_EN, TURN_CONSTRAINTS
        self.assertIn('Response Availability', PHOTO_TURN_CONSTRAINT_EN)
        self.assertEqual(TURN_CONSTRAINTS['photo_request'], PHOTO_TURN_CONSTRAINT_EN)
        bot_src = (ROOT / 'bot.py').read_text(encoding='utf-8')
        self.assertIn('availability_service', bot_src)
        self.assertTrue(
            'PHOTO_TURN_CONSTRAINT' in bot_src or 'photo_request' in bot_src
        )


if __name__ == '__main__':
    unittest.main()
