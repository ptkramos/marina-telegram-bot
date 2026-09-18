"""Knowledge and disclosure contracts; execute with the external isolated suite."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import settings
from context_builder import ContextBuilder
from db import DatabaseManager
from knowledge_privacy import KnowledgePrivacy
from memory import MemoryManager
from seed_world_bible_v36 import seed_world_bible
from world_context import WorldContextBuilder


class TestKnowledgePrivacy(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'knowledge.db')
        seed_world_bible(self.db)
        self.knowledge = KnowledgePrivacy(self.db)

    def _bia_secret(self):
        self.knowledge.observe('fact', 1, 'bia_andrade', privacy_level='CONFIDENTIAL',
                               safe_metadata={'severity': 'moderate', 'physical_safety': 'okay'})
        self.knowledge.grant('fact', 1, 'bia_andrade', 'marina',
                             authorized_by='bia_andrade')
        self.knowledge.record_confirmed_share('fact', 1, 'bia_andrade', 'marina',
                                              detail_level='details', evidence_key='bia-to-marina')

    def test_confidential_fact_cannot_be_confirmed_from_a_guess(self):
        self._bia_secret()
        self.assertFalse(self.knowledge.known_by('fact', 1, 'patrick_ramos'))
        decision = self.knowledge.decision('fact', 1, 'marina', 'patrick_ramos')
        self.assertEqual(decision.level, 'WITHHOLD')
        self.assertFalse(decision.recipient_already_knows)
        prompt = self.knowledge.prompt_constraint('fact', 1)
        self.assertIn('Do not reveal, confirm, or deny', prompt)
        self.assertNotIn('bia_andrade', prompt)
        with self.assertRaises(PermissionError):
            self.knowledge.record_confirmed_share('fact', 1, 'marina', 'patrick_ramos',
                                                  detail_level='details', evidence_key='guess')

    def test_safe_metadata_can_be_shared_without_detail_and_permission_can_change(self):
        self._bia_secret()
        self.knowledge.grant('fact', 1, 'marina', 'patrick_ramos',
                             authorized_by='bia_andrade', detail_level='safe_metadata')
        decision = self.knowledge.decision('fact', 1, 'marina', 'patrick_ramos')
        self.assertEqual(decision.level, 'SAFE_METADATA')
        self.assertEqual(decision.safe_metadata['physical_safety'], 'okay')
        share = self.knowledge.record_confirmed_share('fact', 1, 'marina', 'patrick_ramos',
                                                     detail_level='safe_metadata', evidence_key='safe-share')
        self.assertTrue(self.knowledge.known_by('fact', 1, 'patrick_ramos'))
        self.assertEqual(self.knowledge.record_confirmed_share(
            'fact', 1, 'marina', 'patrick_ramos', detail_level='safe_metadata',
            evidence_key='safe-share')['id'], share['id'])
        with self.assertRaises(ValueError):
            self.knowledge.record_confirmed_share('fact', 1, 'marina', 'patrick_ramos',
                                                  detail_level='details', evidence_key='safe-share')
        self.assertEqual(self.knowledge.decision('fact', 1, 'patrick_ramos', 'henrique_salles').level,
                         'WITHHOLD')
        self.knowledge.grant('fact', 1, 'marina', 'patrick_ramos', authorized_by='bia_andrade')
        self.assertEqual(self.knowledge.decision('fact', 1, 'marina', 'patrick_ramos').level,
                         'DETAILS')
        self.assertIn('has not been told', self.knowledge.prompt_constraint('fact', 1))
        self.knowledge.record_confirmed_share('fact', 1, 'marina', 'patrick_ramos',
                                              detail_level='details', evidence_key='detail-share')
        self.assertIn('already knows', self.knowledge.prompt_constraint('fact', 1))
        self.knowledge.revoke_grant('fact', 1, 'marina', 'patrick_ramos',
                                    authorized_by='bia_andrade')
        self.assertEqual(self.knowledge.decision('fact', 1, 'marina', 'patrick_ramos').level,
                         'WITHHOLD')
        self.assertTrue(self.knowledge.known_by('fact', 1, 'patrick_ramos'))
        self.knowledge.set_privacy_level('fact', 1, 'bia_andrade',
                                         privacy_level='PRIVATE_SELF', authorized_by='bia_andrade')
        self.assertEqual(self.knowledge.decision('fact', 1, 'patrick_ramos', 'henrique_salles').level,
                         'WITHHOLD')

    def test_source_chain_requires_each_explicit_share(self):
        self.knowledge.observe('fact', 2, 'theo_martins', privacy_level='CLOSE_CIRCLE')
        self.assertFalse(self.knowledge.known_by('fact', 2, 'bia_andrade'))
        self.assertFalse(self.knowledge.known_by('fact', 2, 'marina'))
        self.knowledge.grant('fact', 2, 'theo_martins', 'bia_andrade',
                             authorized_by='theo_martins')
        self.knowledge.record_confirmed_share('fact', 2, 'theo_martins', 'bia_andrade',
                                              detail_level='details', evidence_key='theo-bia')
        with self.assertRaises(PermissionError):
            self.knowledge.grant('fact', 2, 'bia_andrade', 'marina', authorized_by='bia_andrade')
        self.knowledge.grant('fact', 2, 'bia_andrade', 'marina', authorized_by='theo_martins')
        self.knowledge.record_confirmed_share('fact', 2, 'bia_andrade', 'marina',
                                              detail_level='details', evidence_key='bia-marina')
        self.assertEqual(self.knowledge.source_chain('fact', 2, 'marina'),
                         ('theo_martins', 'bia_andrade', 'marina'))
        self.assertFalse(self.knowledge.known_by('fact', 2, 'patrick_ramos'))

    def test_private_self_and_revocation_fail_closed(self):
        self.knowledge.observe('fact', 3, 'marina', privacy_level='PRIVATE_SELF')
        with self.assertRaises(PermissionError):
            self.knowledge.grant('fact', 3, 'marina', 'patrick_ramos', authorized_by='marina')
        self.knowledge.set_privacy_level('fact', 3, 'marina', privacy_level='PRIVATE_COUPLE',
                                         authorized_by='marina')
        self.knowledge.grant('fact', 3, 'marina', 'patrick_ramos', authorized_by='marina')
        self.assertEqual(self.knowledge.decision('fact', 3, 'marina', 'patrick_ramos').level,
                         'DETAILS')
        self.knowledge.revoke('fact', 3, 'marina')
        self.assertFalse(self.knowledge.known_by('fact', 3, 'marina'))
        self.assertEqual(self.knowledge.decision('fact', 3, 'marina', 'patrick_ramos').level,
                         'UNKNOWN')

    def test_safe_metadata_rejects_unreviewed_free_text(self):
        with self.assertRaises(ValueError):
            self.knowledge.observe('fact', 4, 'marina', privacy_level='CONFIDENTIAL',
                                   safe_metadata={'category': 'Bia está grávida'})

    def test_safe_metadata_share_requires_reviewed_fields(self):
        self.knowledge.observe('fact', 4, 'marina', privacy_level='PUBLIC_SOCIAL')
        with self.assertRaisesRegex(ValueError, 'No reviewed safe metadata'):
            self.knowledge.record_confirmed_share('fact', 4, 'marina', 'patrick_ramos',
                                                  detail_level='safe_metadata', evidence_key='empty-safe')
        self.assertFalse(self.knowledge.known_by('fact', 4, 'patrick_ramos'))

    def test_prompt_integration_excludes_unclassified_memory_when_flag_enabled(self):
        self._bia_secret()
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO world_bootstrap (key,value,updated_at)
                VALUES ('clean_canonical_start_done','1','2026-09-18T00:00:00')""")
        retriever = MagicMock()
        retriever.retrieve_context.return_value = {
            'fatos': ['A frase privada de Bia'], 'momentos': [], 'resumos': []}
        builder = WorldContextBuilder(self.db, retriever=retriever)
        with patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', True):
            prompt = builder.build(now=datetime(2026, 9, 18, 12),
                                   user_message='E a Bia?', privacy_subjects=[('fact', 1)])
        self.assertIn('[KNOWLEDGE POLICY]', prompt)
        self.assertIn('Do not reveal, confirm, or deny', prompt)
        self.assertNotIn('A frase privada de Bia', prompt)
        retriever.retrieve_context.assert_not_called()
        with patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', True):
            with self.assertRaisesRegex(ValueError, 'One trusted privacy subject'):
                builder.build(now=datetime(2026, 9, 18, 12),
                              privacy_subjects=[('fact', 1), ('fact', 2)])
        memory = MemoryManager(db=self.db)
        memory.get_historico_recente = MagicMock(return_value=[
            {'role': 'assistant', 'content': 'A frase privada de Bia'}])
        context = ContextBuilder(memory_mgr=memory, retriever=retriever)
        with (patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', True),
              patch.object(settings, 'LIVING_WORLD_ENABLED', True)):
            messages = context.build(user_message='E a Bia?')
        self.assertEqual(len(messages), 1)
        self.assertNotIn('A frase privada de Bia', messages[0]['content'])
        memory.get_historico_recente.assert_not_called()

    def test_privacy_flag_refuses_legacy_bot_context(self):
        import bot

        with (patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', True),
              patch.object(settings, 'LIVING_WORLD_ENABLED', False)):
            with self.assertRaisesRegex(RuntimeError, 'requires Living World'):
                bot.build_messages_payload(user_message='Oi')


if __name__ == '__main__':
    unittest.main()
