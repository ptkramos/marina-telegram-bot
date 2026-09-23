"""Behavioral regressions found during the independent pre-soak gate."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from config import settings
from db import DatabaseManager
from pending_response import ResponseAvailabilityService, resolve_cancelled_requests
from response_availability import ResponseAvailabilityDecision


class TelegramHistoryCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_bulk_failure_falls_back_to_individual_recent_messages(self):
        from bot import delete_recent_telegram_history

        fake = SimpleNamespace(
            delete_messages=AsyncMock(side_effect=RuntimeError('mixed old batch')),
            delete_message=AsyncMock(return_value=True),
        )
        with patch('bot.asyncio.sleep', new=AsyncMock()):
            result = await delete_recent_telegram_history(
                fake, 1, 10, window=5, batch_size=5,
            )
        self.assertEqual(result['deleted'], 5)
        self.assertFalse(result['stopped_at_limit'])
        self.assertEqual(fake.delete_message.await_count, 5)

    async def test_cleanup_stops_after_reaching_undeletable_history(self):
        from bot import delete_recent_telegram_history

        async def delete_one(*, chat_id, message_id):
            if message_id <= 7:
                raise RuntimeError('too old')
            return True

        fake = SimpleNamespace(
            delete_messages=AsyncMock(side_effect=RuntimeError('mixed old batch')),
            delete_message=AsyncMock(side_effect=delete_one),
        )
        with patch('bot.asyncio.sleep', new=AsyncMock()):
            result = await delete_recent_telegram_history(
                fake, 1, 10, window=10, batch_size=5,
                consecutive_failure_limit=3,
            )
        self.assertEqual(result['deleted'], 3)
        self.assertTrue(result['stopped_at_limit'])


class CancellationResolutionTests(unittest.TestCase):
    def test_second_launcher_is_blocked_and_lock_is_released(self):
        from runtime_lock import single_instance
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'bot.lock'
            with single_instance(path):
                with self.assertRaises(RuntimeError):
                    with single_instance(path):
                        self.fail('second launcher acquired the lock')
            with single_instance(path):
                pass

    def test_modifiers_are_not_cancellations(self):
        for modifier in ('não esquece de sorrir', 'não precisa de pressa',
                         'pode deixar que eu espero', 'esqueci minha chave'):
            text = 'manda uma foto\n' + modifier
            self.assertEqual(resolve_cancelled_requests(text).text, text)
            self.assertFalse(resolve_cancelled_requests(text).cancelled)

    def test_photo_voice_avatar_and_reminder_are_cancelled(self):
        for request in ('manda uma foto', 'manda um áudio', 'troca seu avatar',
                        'me lembra de beber água às 18h', 'grava sua voz', 'uma selfie'):
            for separator in ('\n', '; ', '. ', ', '):
                with self.subTest(request=request, separator=separator):
                    result = resolve_cancelled_requests(request + separator + 'deixa pra lá')
                    self.assertTrue(result.cancelled)
                    self.assertEqual(result.text, '')

    def test_preserves_conversation_before_and_after(self):
        result = resolve_cancelled_requests(
            'hoje meu dia foi corrido\nmanda uma foto\ndeixa pra lá\nme conta como foi seu dia?')
        self.assertNotIn('foto', result.text)
        self.assertIn('hoje meu dia foi corrido', result.text)
        self.assertIn('me conta como foi seu dia', result.text)

    def test_same_message_cancel_then_question(self):
        result = resolve_cancelled_requests('manda uma foto, deixa pra lá, me conta do seu dia')
        self.assertEqual(result.text, 'me conta do seu dia')

    def test_later_request_can_replace_cancelled_request(self):
        result = resolve_cancelled_requests('manda uma foto\ncancela\nmanda um áudio')
        self.assertEqual(result.text, 'manda um áudio')

    def test_targeted_cancel_preserves_other_request(self):
        result = resolve_cancelled_requests('manda uma foto\nmanda um áudio\ncancela a foto')
        self.assertEqual(result.text, 'manda um áudio')


class PendingCancellationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = DatabaseManager(Path(tmp.name) / 'test.db')
        self.svc = ResponseAvailabilityService(self.db)
        self.now = datetime.now()
        self.decision = ResponseAvailabilityDecision(
            decision='DEFER', phone_access='LOW', attention_level='LOW',
            interruptibility='LOW', message_urgency='LOW', response_complexity='SHORT',
            activity_type='CLASS', activity_source='WORLD_STATE', reason_code='class_busy',
            earliest_reply_at=self.now, target_window_start=self.now,
            target_window_end=self.now + timedelta(hours=1), selected_target_at=self.now,
            context_snapshot_id=None, world_state_freshness='fresh', decision_seed='cancel-test',
            can_claim_activity=True, shadow_only=False,
        )

    def enqueue(self, messages):
        batch = None
        for i, text in enumerate(messages):
            batch, _, _ = self.svc.repo.enqueue_item(
                self.decision, message=text, telegram_message_id=1000+i, received_at=self.now)
        return batch

    async def test_cancelled_batch_never_enters_media_pipeline(self):
        import bot
        for request in ('manda uma foto', 'manda um áudio', 'troca seu avatar'):
            with self.subTest(request=request):
                # Use distinct IDs between iterations, as Telegram IDs are idempotent.
                with self.db.get_connection() as conn:
                    conn.execute('DELETE FROM response_pending_batch_items')
                batch = self.enqueue([request, 'deixa pra lá'])
                pipeline = AsyncMock()
                fake_bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock(), send_voice=AsyncMock())
                with patch.object(bot, 'availability_service', self.svc), \
                     patch.object(bot, 'process_incoming_batch', pipeline):
                    await bot.pending_response_routine(SimpleNamespace(bot=fake_bot))
                pipeline.assert_not_called()
                fake_bot.send_photo.assert_not_called()
                fake_bot.send_voice.assert_not_called()
                self.assertEqual(self.svc.repo.get_batch(batch['id'])['status'], 'SUPERSEDED')

    async def test_immediate_burst_cancels_before_any_provider(self):
        import bot
        fake_update = SimpleNamespace(effective_chat=SimpleNamespace(id=1),
                                      message=SimpleNamespace(message_id=2, reply_to_message=None))
        fake_sent = SimpleNamespace(message_id=99)
        with patch.object(bot, 'send_human_messages', AsyncMock(return_value=fake_sent)) as send, \
             patch.object(bot.memory_manager, 'registrar_mensagem_usuario') as remember_user, \
             patch.object(bot.memory_manager, 'registrar_mensagem_assistente') as remember_bot, \
             patch.object(bot.style_engine, 'processar_mensagem_patrick'), \
             patch.object(bot, 'iniciar_escolha_avatar', AsyncMock()) as avatar, \
             patch.object(bot.llm_client.chat.completions, 'create') as llm:
            await bot.process_incoming_batch(fake_update, SimpleNamespace(bot=object()),
                                             'manda uma foto\ndeixa pra lá', availability_bypass=True)
            send.assert_awaited_once()
            remember_user.assert_called_once()
            remember_bot.assert_called_once()
            avatar.assert_not_called()
            llm.assert_not_called()

    def test_remaining_question_not_superseded_and_history_preserved(self):
        batch = self.enqueue(['manda uma foto', 'deixa pra lá', 'como foi seu dia?'])
        self.assertFalse(self.svc.repo.check_cancellation(batch['id']))
        self.assertEqual(self.svc.repo.get_batch(batch['id'])['status'], 'READY')
        self.assertEqual(len(self.svc.repo.list_items(batch['id'])), 3)
        self.assertNotIn('foto', resolve_cancelled_requests(self.svc.compose_batch_text(batch['id'])).text)

    def test_single_persisted_burst_is_superseded(self):
        batch = self.enqueue(['manda uma foto\ndeixa pra lá'])
        self.assertTrue(self.svc.repo.check_cancellation(batch['id']))
        self.assertEqual(self.svc.repo.get_batch(batch['id'])['status'], 'SUPERSEDED')

    def test_urgent_merge_cannot_wake_sleeping_marina(self):
        with patch.multiple(settings, RESPONSE_AVAILABILITY_ENABLED=True,
                            HUMAN_REPLY_LATENCY_ENABLED=True, PENDING_CONVERSATION_BATCHING_ENABLED=True,
                            CRITICAL_WAKE_POLICY_ENABLED=False), \
             patch.object(self.svc.policy, '_resolve_activity',
                          return_value=('SLEEPING', 'WORLD_STATE', None, 'fresh', True)):
            _, _, batch = self.svc.evaluate_and_maybe_defer('oi amor', telegram_message_id=80, now=self.now)
            _, decision, merged = self.svc.evaluate_and_maybe_defer(
                'socorro', telegram_message_id=81, now=self.now + timedelta(seconds=1))
        self.assertEqual(merged['id'], batch['id'])
        self.assertEqual(decision.message_urgency, 'CRITICAL')
        self.assertEqual(decision.decision, 'DEFER')
        self.assertEqual(merged['status'], 'PENDING')

    async def test_deferred_replay_does_not_learn_again(self):
        import bot
        from style_engine import StyleEngine
        engine = StyleEngine(self.db)
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=1),
                                 message=SimpleNamespace(message_id=4, reply_to_message=None))
        batch = self.enqueue(['manda uma foto\ndeixa pra lá'])
        text = self.svc.compose_batch_text(batch['id'])
        engine.processar_mensagem_patrick(text)
        before = engine.patrick_sample_count()
        with patch.object(bot, 'style_engine', engine), patch.object(bot, 'availability_service', self.svc):
            await bot.process_incoming_batch(update, SimpleNamespace(bot=object()), text,
                                             availability_bypass=True, pending_batch_id=batch['id'])
        self.assertEqual(engine.patrick_sample_count(), before)
        self.assertEqual(self.svc.repo.get_batch(batch['id'])['status'], 'SUPERSEDED')

    def test_explicit_awake_at_five_am_can_trigger_proactivity(self):
        from proactivity_service import ProactivityService
        from world_repository import WorldStateRepository
        now = datetime(2026, 9, 18, 5, 0)
        WorldStateRepository(self.db).add_snapshot({
            'state_date': now.date().isoformat(), 'observed_at': now.isoformat(),
            'activity': 'acordada trabalhando num freela', 'energy_level': 0.7,
            'source_json': {'reason': 'explicit_plan'},
        })
        svc = ProactivityService(self.db)
        with patch.multiple(settings, LIVING_WORLD_ENABLED=True, RELATIONSHIP_WORLD_ENABLED=True,
                            PROACTIVITY_ENABLED=True), \
             patch.object(svc, 'get_autonomous_count_today', return_value=0), \
             patch.object(svc, 'get_last_messages_timestamps', return_value=(None, None)), \
             patch.object(svc, 'determine_living_world_candidate', return_value={'rank': 80, 'reason': 'grounded'}):
            self.assertEqual(svc.should_trigger(now), (True, 'grounded'))

    async def test_photo_outage_uses_llm_reply_without_attempting_gpu(self):
        import bot
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=1),
                                 message=SimpleNamespace(message_id=4, reply_to_message=None))
        reply = 'Poxa amor, não consegui mandar a foto agora 🥺 Mas me conta como foi seu dia.'
        with patch.multiple(settings, PHOTO_PROVIDER_MAINTENANCE=True, KNOWLEDGE_PRIVACY_ENABLED=False,
                            REAL_CONTEXT_FETCH_ENABLED=False, PLANNER_ENABLED=False,
                            RESPONSE_RHYTHM_ENABLED=False, VOICE_PROSODY_ENABLED=False), \
             patch.object(bot.memory_manager, 'db', self.db), \
             patch.object(bot, 'planner') as planner, \
             patch.object(bot, 'build_messages_payload', return_value=[{'role': 'system', 'content': 'Test context'}]), \
             patch.object(bot, 'buscar_web_se_necessario', return_value=''), \
             patch.object(bot, 'set_safe_message_reaction', AsyncMock()), \
             patch.object(bot.random, 'random', return_value=1.0), \
             patch.object(bot.style_engine, 'processar_mensagem_patrick'), \
             patch.object(bot.llm_client.chat.completions, 'create',
                          return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])) as llm, \
             patch.object(bot, 'send_human_messages', AsyncMock(return_value=SimpleNamespace(message_id=9))) as send, \
             patch.object(bot.sd_client, 'generate_photo_with_context', AsyncMock()) as photo, \
             patch.object(bot, 'check_and_trigger_memory_consolidation', AsyncMock()):
            planner.plan_message.return_value = {}
            await bot.process_incoming_batch(update, SimpleNamespace(bot=AsyncMock()),
                                             'manda uma foto', availability_bypass=True)
            llm.assert_called_once()
            self.assertTrue(any(m['content'] == bot.PHOTO_UNAVAILABLE_INSTRUCTION
                                for m in llm.call_args.kwargs['messages']))
            # sem o ponto que fecha o balão (chat_naturalness, 23/09)
            self.assertEqual(send.call_args.args[2], reply.rstrip('.'))
            photo.assert_not_called()

    async def test_photo_and_avatar_maintenance_never_start_gpu(self):
        from sd_client import ImageGeneratorClient
        client = ImageGeneratorClient()
        with patch.object(settings, 'PHOTO_PROVIDER_MAINTENANCE', True), \
             patch.object(client, '_ensure_instance_running', AsyncMock()) as start:
            result = await client.generate_photo_with_context('synthetic fully clothed portrait')
            avatars = await client.generate_avatar()
        self.assertIsNone(result.image)
        self.assertEqual(avatars, (None, None))
        start.assert_not_called()

    async def test_dynamic_apology_falls_back_if_llm_unavailable(self):
        import bot
        with patch.object(bot, 'generate_dynamic_speech', return_value=''), \
             patch.object(bot, 'send_human_messages', AsyncMock(return_value=SimpleNamespace(message_id=10))) as send, \
             patch.object(bot.memory_manager, 'db', self.db):
            await bot.send_photo_unavailable(1, object())
        self.assertIn('não consegui', send.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
