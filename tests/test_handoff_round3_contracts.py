"""Adversarial contract tests for Handoff Round 3 — v3.7.0 P1 blockers.

Each test reproduces a specific bug from REVISAO_TECNICA_MARINA_3_7_0V3_FINAL_SANITY.md
and validates that the fix holds.
"""
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from style_engine import StyleEngine


class TestBlandMessagesDoNotCreateLearnedStyle(unittest.TestCase):
    """P1.1: Fresh DB + bland messages must NOT fabricate learned Patrick style."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(db_path=Path(self.temp_dir.name) / 'test.db')
        self.engine = StyleEngine(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bland_messages_no_fake_laugh(self):
        self.engine.processar_mensagem_patrick("oi tudo bem")
        self.engine.processar_mensagem_patrick("sim tudo certo")
        estilo = self.db.get_estilo()
        # No laughter was observed; risada must not contain kkkk/haha/rsrs
        risada_val = estilo.get("risada", {}).get("valor", "")
        risada_exemplos = estilo.get("risada", {}).get("exemplos", {})
        total_laughs = sum(risada_exemplos.values()) if isinstance(risada_exemplos, dict) else 0
        self.assertEqual(total_laughs, 0, "Bland messages should produce 0 laugh observations")
        # risada value should be empty since no dominance observed
        self.assertEqual(risada_val, "", "No laughter observed → empty valor, not a default")

    def test_bland_messages_no_fake_emojis(self):
        self.engine.processar_mensagem_patrick("oi tudo bem")
        self.engine.processar_mensagem_patrick("sim tudo certo")
        estilo = self.db.get_estilo()
        emojis_val = estilo.get("emojis_favoritos", {}).get("valor", "")
        self.assertEqual(emojis_val, "", "No emojis observed → empty valor")

    def test_bland_messages_no_fake_slang(self):
        self.engine.processar_mensagem_patrick("oi tudo bem")
        self.engine.processar_mensagem_patrick("sim tudo certo")
        estilo = self.db.get_estilo()
        girias_val = estilo.get("girias", {}).get("valor", "")
        self.assertEqual(girias_val, "", "No slang observed → empty valor")

    def test_injection_excludes_unobserved_dimensions(self):
        """After threshold but only cadence observed, injection should not mention defaults."""
        self.engine.processar_mensagem_patrick("oi tudo bem")
        self.engine.processar_mensagem_patrick("sim tudo certo")
        injection = self.engine.get_style_prompt_injection()
        for fake in ['kkkk', '🥰', '💕', '❤️', '🥺', '🙈', 'trampo', 'codar', 'bora']:
            self.assertNotIn(fake, injection,
                             f"Injection must not contain default {fake!r} without evidence")


class TestWorldContextRespectsLearnedStyleThreshold(unittest.TestCase):
    """P1.2: WorldContext must use evidence-aware StyleEngine API."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(db_path=Path(self.temp_dir.name) / 'test.db')
        self.engine = StyleEngine(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fresh_db_one_message_no_learned_style(self):
        self.engine.processar_mensagem_patrick("oi tudo bem")
        self.assertFalse(self.engine.has_learned_style())
        summary = self.engine.get_learned_style_summary()
        self.assertEqual(summary, "", "1 message → no learned style summary")

    def test_summary_excludes_unobserved(self):
        """Even after threshold, summary only shows observed dimensions."""
        self.engine.processar_mensagem_patrick("oi tudo bem")
        self.engine.processar_mensagem_patrick("sim tudo certo")
        summary = self.engine.get_learned_style_summary()
        for fake in ['kkkk', '🥰', '💕', '❤️', '🥺', '🙈', 'trampo', 'codar', 'bora']:
            self.assertNotIn(fake, summary)

    def test_summary_includes_real_observations(self):
        """When Patrick actually uses kkkk and emojis, they appear."""
        for _ in range(3):
            self.engine.processar_mensagem_patrick("kkkk muito bom ❤️ trampo fechou")
        summary = self.engine.get_learned_style_summary()
        self.assertIn("kkkk", summary)
        self.assertIn("❤️", summary)
        self.assertIn("trampo", summary)


class TestShortDistressMessagesNotLow(unittest.TestCase):
    """P1.4: Urgency classifier must not underestimate short distress messages."""

    def test_me_ajuda_is_high(self):
        from response_availability import classify_urgency
        self.assertEqual(classify_urgency("me ajuda"), "HIGH")

    def test_acidente_is_high(self):
        from response_availability import classify_urgency
        self.assertEqual(classify_urgency("acidente"), "HIGH")

    def test_hospital_is_high(self):
        from response_availability import classify_urgency
        self.assertEqual(classify_urgency("hospital"), "HIGH")

    def test_to_mal_is_high(self):
        from response_availability import classify_urgency
        self.assertEqual(classify_urgency("tô mal"), "HIGH")

    def test_passei_mal_is_high(self):
        from response_availability import classify_urgency
        self.assertEqual(classify_urgency("passei mal"), "HIGH")

    def test_socorro_is_critical(self):
        from response_availability import classify_urgency
        self.assertEqual(classify_urgency("socorro"), "CRITICAL")

    def test_emergencia_is_critical(self):
        from response_availability import classify_urgency
        self.assertEqual(classify_urgency("emergência"), "CRITICAL")

    def test_short_bland_still_low(self):
        from response_availability import classify_urgency
        self.assertEqual(classify_urgency("ok"), "LOW")
        self.assertEqual(classify_urgency("valeu"), "LOW")


class TestSleepingCriticalRequiresExplicitWakePolicy(unittest.TestCase):
    """P1.5: SLEEPING + CRITICAL must not silently wake Marina."""

    def test_sleeping_critical_defers_when_policy_disabled(self):
        from response_availability import ResponseAvailabilityPolicy
        with tempfile.TemporaryDirectory() as td:
            db = DatabaseManager(db_path=Path(td) / 'test.db')
            policy = ResponseAvailabilityPolicy(db)
            profile = dict(policy.profiles['SLEEPING'])
            with patch.object(policy, '_resolve_activity',
                              return_value=('SLEEPING', 'WORLD_STATE', None, 'fresh', False)):
                with patch('response_availability.settings') as mock_settings:
                    mock_settings.CRITICAL_WAKE_POLICY_ENABLED = False
                    mock_settings.RESPONSE_AVAILABILITY_ENABLED = False
                    mock_settings.HUMAN_REPLY_LATENCY_ENABLED = False
                    mock_settings.WORLD_STATE_DEFAULT_STALE_MINUTES = 60
                    mock_settings.RESPONSE_AVAILABILITY_PROFILES = None
                    decision = policy.evaluate("socorro", now=datetime(2026, 1, 1, 4, 0))
                    self.assertEqual(decision.decision, 'DEFER',
                                     "SLEEPING + CRITICAL + policy=false → must DEFER")

    def test_sleeping_critical_wakes_when_policy_enabled(self):
        from response_availability import ResponseAvailabilityPolicy
        with tempfile.TemporaryDirectory() as td:
            db = DatabaseManager(db_path=Path(td) / 'test.db')
            policy = ResponseAvailabilityPolicy(db)
            with patch.object(policy, '_resolve_activity',
                              return_value=('SLEEPING', 'WORLD_STATE', None, 'fresh', False)):
                with patch('response_availability.settings') as mock_settings:
                    mock_settings.CRITICAL_WAKE_POLICY_ENABLED = True
                    mock_settings.RESPONSE_AVAILABILITY_ENABLED = False
                    mock_settings.HUMAN_REPLY_LATENCY_ENABLED = False
                    mock_settings.WORLD_STATE_DEFAULT_STALE_MINUTES = 60
                    mock_settings.RESPONSE_AVAILABILITY_PROFILES = None
                    decision = policy.evaluate("socorro", now=datetime(2026, 1, 1, 4, 0))
                    self.assertIn(decision.decision, ('REPLY_NOW', 'REPLY_BRIEFLY'),
                                  "SLEEPING + CRITICAL + policy=true → must wake")


class TestDeferredReplayDoesNotDoubleLearn(unittest.TestCase):
    """P1.6: Deferred replay must not re-learn Patrick style."""

    def test_pending_batch_id_skips_learning(self):
        """When pending_batch_id is set, style learning should be skipped in process_incoming_batch."""
        # This is a structural test — we verify the guard exists in bot.py source
        bot_src = (BASE_DIR / 'bot.py').read_text(encoding='utf-8')
        # Find the learning call and verify it's guarded by pending_batch_id
        pattern = r'if\s+pending_batch_id\s+is\s+None:\s*\n\s+style_engine\.processar_mensagem_patrick'
        self.assertTrue(
            re.search(pattern, bot_src),
            "Style learning in process_incoming_batch must be guarded by 'if pending_batch_id is None'"
        )


class TestDeferredPhotoCancellationSupersedes(unittest.TestCase):
    """P1.7: Deferred photo/voice cancellation must supersede the batch."""

    def test_cancellation_patterns_detected(self):
        from pending_response import PendingResponseRepository
        repo = PendingResponseRepository.__new__(PendingResponseRepository)
        cancel_phrases = [
            "deixa pra lá",
            "esquece",
            "não precisa",
            "pode deixar",
            "cancela",
            "não manda mais",
            "deixa quieto",
            "não quero mais",
        ]
        for phrase in cancel_phrases:
            self.assertTrue(
                repo._CANCEL_PATTERNS.search(phrase),
                f"Pattern should match cancellation phrase: {phrase!r}"
            )

    def test_non_cancellation_not_detected(self):
        from pending_response import PendingResponseRepository
        repo = PendingResponseRepository.__new__(PendingResponseRepository)
        normal_phrases = [
            "oi tudo bem",
            "manda uma foto",
            "que legal",
            "obrigado amor",
        ]
        for phrase in normal_phrases:
            self.assertIsNone(
                repo._CANCEL_PATTERNS.search(phrase),
                f"Pattern should NOT match normal phrase: {phrase!r}"
            )


class TestExplicitAwakeStateOverridesClockSleepFallback(unittest.TestCase):
    """P1.9: Explicit awake WorldState at 05:00 must not be blocked by clock window."""

    def test_clock_window_active_at_5am(self):
        from proactivity_service import ProactivityService
        svc = ProactivityService.__new__(ProactivityService)
        self.assertTrue(svc.check_sleep_window(datetime(2026, 1, 1, 5, 0)),
                        "05:00 should be inside clock sleep window")

    def test_proactivity_code_has_worldstate_override(self):
        """should_trigger must check WorldState before blindly blocking by clock."""
        src = (BASE_DIR / 'proactivity_service.py').read_text(encoding='utf-8')
        self.assertIn('WorldStateRepository', src,
                      "should_trigger must consult WorldState when Living World is active")
        self.assertIn('is_fresh and not is_sleeping', src,
                      "Fresh non-sleeping state must override clock window")


class TestActivityMapperPrefersExplicitActivity(unittest.TestCase):
    """P2.4: Activity mapper should prefer explicit activity over place heuristic."""

    def test_puc_with_cafe_not_class(self):
        from response_availability import ResponseAvailabilityPolicy
        with tempfile.TemporaryDirectory() as td:
            db = DatabaseManager(db_path=Path(td) / 'test.db')
            policy = ResponseAvailabilityPolicy(db)
            # PUC campus but activity says "tomando café no intervalo"
            # Without explicit class-related activity, the activity should reflect
            # what's actually being done
            result = policy._map_place_activity('puc_rio', 'tomando café no intervalo')
            self.assertEqual(result, 'SOCIAL')
            # "tomando café" is not sleeping, working, commuting, etc.
            # Place heuristic may still apply as fallback (CLASS) but explicit
            # non-class activity should ideally not auto-classify as CLASS
            # For now, CLASS is acceptable since "café" is not an overriding keyword

    def test_apartment_with_freela_is_work(self):
        from response_availability import ResponseAvailabilityPolicy
        with tempfile.TemporaryDirectory() as td:
            db = DatabaseManager(db_path=Path(td) / 'test.db')
            policy = ResponseAvailabilityPolicy(db)
            result = policy._map_place_activity('marina_apartment', 'trabalhando num freela')
            self.assertEqual(result, 'WORK',
                             "Explicit 'trabalhando num freela' should override apartment → WORK")


if __name__ == '__main__':
    unittest.main(verbosity=2)
