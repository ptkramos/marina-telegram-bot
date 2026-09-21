"""Deterministic subject routing and post-delivery ledger contracts."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config import settings
from db import DatabaseManager
from knowledge_dialogue import KnowledgeDialogue
from seed_knowledge_v363 import seed_knowledge
from seed_world_bible_v36 import seed_world_bible


class TestKnowledgeDialogue(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'knowledge_dialogue.db')
        seed_world_bible(self.db)
        self.dialogue = KnowledgeDialogue(self.db)
        # Patch 026: força availability_service a "proceed" — senão
        # AVAILABILITY_DEFER (janela de sono) bloqueia process_incoming_batch.
        import bot as _bot
        self._availability_patcher = patch.object(
            _bot.availability_service, "evaluate_and_maybe_defer",
            return_value=("proceed", None, None),
        )
        self._availability_patcher.start()
        self.addCleanup(self._availability_patcher.stop)

    def _topics(self):
        bia = self.dialogue.register_subject(
            'fact', 'o assunto da Bia', ['assunto da Bia'],
            approved_detail='Bia contou um detalhe pessoal.')
        self.dialogue.privacy.observe('fact', bia, 'bia_andrade',
                                      privacy_level='CONFIDENTIAL',
                                      safe_metadata={'physical_safety': 'okay'})
        self.dialogue.privacy.grant('fact', bia, 'bia_andrade', 'marina',
                                    authorized_by='bia_andrade')
        self.dialogue.privacy.record_confirmed_share(
            'fact', bia, 'bia_andrade', 'marina', detail_level='details',
            evidence_key='bia-marina-reviewed')
        self.dialogue.privacy.grant('fact', bia, 'marina', 'patrick_ramos',
                                    authorized_by='bia_andrade',
                                    detail_level='safe_metadata')
        trip = self.dialogue.register_subject(
            'fact', 'a viagem da faculdade', ['viagem da faculdade'],
            approved_detail='A viagem será no sábado.')
        self.dialogue.privacy.observe('fact', trip, 'marina',
                                      privacy_level='PUBLIC_SOCIAL')
        return bia, trip

    def test_resolves_real_registered_ids_without_guessing(self):
        bia, trip = self._topics()
        found = self.dialogue.resolve('E o assunto da Bia e a viagem da faculdade?')
        self.assertEqual({topic.subject_id for topic in found}, {bia, trip})
        self.assertEqual(self.dialogue.resolve('E aquele segredo que eu imagino?'), [])
        self.dialogue.register_subject('fact', 'outro assunto', ['assunto da Bia'])
        self.assertEqual([topic.subject_id for topic in self.dialogue.resolve('assunto da Bia')], [])

    def test_event_subject_uses_the_actual_life_event_id(self):
        with self.db.get_connection() as conn:
            event_id = conn.execute('''INSERT INTO life_events
                (event_key,event_at,event_type,title,summary,source_type,autonomy_level,created_at)
                VALUES (?,?,?,?,?,'canonical',1,?)''',
                ('event:campus', '2026-09-18T12:00:00', 'campus', 'Mostra da faculdade',
                 'Mostra no campus', '2026-09-18T12:00:00')).lastrowid
        registered = self.dialogue.register_subject(
            'event', 'a mostra da faculdade', ['mostra da faculdade'],
            approved_detail='A mostra é hoje.', source_event_id=event_id)
        self.assertEqual(registered, event_id)
        found = self.dialogue.resolve('Como foi a mostra da faculdade?')
        self.assertEqual([(topic.subject_type, topic.subject_id) for topic in found],
                         [('event', event_id)])

    def test_canonical_subject_seed_is_idempotent(self):
        first = seed_knowledge(self.db)
        self.assertEqual(seed_knowledge(self.db), first)
        self.assertEqual({topic.subject_id for topic in self.dialogue.resolve(
            'Como está o Milo e o nosso namoro?')}, set(first.values()))
        self.assertEqual(self.dialogue.privacy.decision(
            'relationship', first['relationship'], 'marina', 'patrick_ramos').level,
            'DETAILS')

    def test_mixed_privacy_is_calculated_and_rendered_per_subject(self):
        bia, trip = self._topics()
        topics = self.dialogue.resolve('assunto da Bia e viagem da faculdade')
        replies = self.dialogue.prepare_replies(topics)
        by_id = {reply.subject_id: reply for reply in replies}
        self.assertEqual(by_id[bia].disclosed_level, 'safe_metadata')
        self.assertIn('fisicamente bem', by_id[bia].text)
        self.assertNotIn('detalhe pessoal', by_id[bia].text)
        self.assertEqual(by_id[trip].disclosed_level, 'details')
        self.assertIn('sábado', by_id[trip].text)

    def test_ledger_only_records_confirmed_per_subject_delivery(self):
        import bot

        bia, trip = self._topics()
        replies = self.dialogue.prepare_replies(
            self.dialogue.resolve('assunto da Bia e viagem da faculdade'))

        class FailingSecondBot:
            def __init__(self):
                self.calls = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs['text'])
                if len(self.calls) == 2:
                    raise RuntimeError('Telegram send failed')
                return SimpleNamespace(message_id=781)

        sender = FailingSecondBot()
        with self.assertRaisesRegex(RuntimeError, 'Telegram send failed'):
            asyncio.run(bot.send_registered_privacy_replies(123, sender, replies, db=self.db))
        first = replies[0]
        second = replies[1]
        with self.db.get_connection() as conn:
            shares = conn.execute('''SELECT subject_id,detail_level,metadata_json FROM knowledge_shares
                WHERE from_character_key='marina' AND to_character_key='patrick_ramos'
                ORDER BY id''').fetchall()
        self.assertEqual([(row['subject_id'], row['detail_level']) for row in shares],
                         [(first.subject_id, first.disclosed_level)])
        self.assertNotEqual(first.subject_id, second.subject_id)
        self.assertIn('telegram:123:781:', shares[0]['metadata_json'])

    def test_failed_or_unconfirmed_send_never_creates_share(self):
        import bot

        bia, _ = self._topics()
        reply = self.dialogue.prepare_replies(
            self.dialogue.resolve('assunto da Bia'))[0]

        class NoReceiptBot:
            async def send_message(self, **_kwargs):
                return SimpleNamespace(message_id=None)

        with self.assertRaisesRegex(RuntimeError, 'did not confirm'):
            asyncio.run(bot.send_registered_privacy_replies(
                123, NoReceiptBot(), [reply], db=self.db))
        self.assertFalse(self.dialogue.privacy.known_by('fact', bia, 'patrick_ramos'))

    def test_incoming_flow_routes_registered_subjects_before_llm(self):
        import bot

        bia, trip = self._topics()
        sent = []

        class RecordingBot:
            async def send_message(self, **kwargs):
                sent.append(kwargs['text'])
                return SimpleNamespace(message_id=900 + len(sent))

        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=123),
            message=SimpleNamespace(message_id=777, reply_to_message=None),
        )
        context = SimpleNamespace(bot=RecordingBot())
        with (patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', True),
              patch.object(settings, 'LIVING_WORLD_ENABLED', True),
              patch.object(bot.memory_manager, 'db', self.db),
              patch.object(bot.style_engine, 'processar_mensagem_patrick'),
              patch.object(bot.llm_client.chat.completions, 'create') as llm):
            asyncio.run(bot.process_incoming_batch(
                update, context, 'assunto da Bia e viagem da faculdade'))
        llm.assert_not_called()
        self.assertEqual(len(sent), 2)
        self.assertTrue(self.dialogue.privacy.known_by('fact', bia, 'patrick_ramos'))
        self.assertTrue(self.dialogue.privacy.known_by('fact', trip, 'patrick_ramos'))


if __name__ == '__main__':
    unittest.main()
