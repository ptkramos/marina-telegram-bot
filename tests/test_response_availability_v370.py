"""Stage 15 / release 3.7.0 — Response Availability contracts."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from config import settings
from db import DatabaseManager
from pending_response import PendingResponseRepository, ResponseAvailabilityService
from response_availability import (
    ResponseAvailabilityPolicy,
    classify_complexity,
    classify_urgency,
)
from response_rhythm import select_policy
from seed_world_bible_v36 import seed_world_bible
from world_repository import WorldStateRepository


class AvailabilityPolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'avail.db')
        seed_world_bible(self.db)
        self.policy = ResponseAvailabilityPolicy(self.db)
        self.now = datetime(2026, 9, 18, 14, 0)
        self.states = WorldStateRepository(self.db)

    def _snap(self, *, place_key='marina_apartment', activity='em casa', reason='explicit_plan',
              observed=None):
        observed = observed or self.now
        with self.db.get_connection() as conn:
            place = conn.execute(
                'SELECT id, region FROM world_places WHERE canonical_key=?', (place_key,)
            ).fetchone()
        return self.states.add_snapshot({
            'state_date': observed.date().isoformat(),
            'observed_at': observed.isoformat(),
            'location_place_id': place['id'] if place else None,
            'location_region': place['region'] if place else None,
            'activity': activity,
            'energy_level': 0.7,
            'source_json': {'reason': reason},
        })

    def test_urgency_and_complexity_classifiers(self):
        self.assertEqual(classify_urgency('socorro emergência'), 'CRITICAL')
        self.assertEqual(classify_urgency('amor preciso falar contigo'), 'HIGH')
        self.assertEqual(classify_urgency('kkkk'), 'LOW')
        self.assertEqual(classify_urgency('tudo bem amor?'), 'NORMAL')
        self.assertEqual(classify_complexity('oi'), 'SHORT')
        self.assertEqual(classify_complexity('me explica detalhadamente o plano'), 'LONG')

    def test_home_prefers_reply_now(self):
        self._snap()
        d = self.policy.evaluate('oi amor', now=self.now, telegram_message_id=1)
        self.assertEqual(d.decision, 'REPLY_NOW')
        self.assertEqual(d.activity_type, 'HOME_RELAXING')
        self.assertTrue(d.can_claim_activity)

    def test_class_busy_defers_normal(self):
        self._snap(place_key='puc_rio', activity='em aula', reason='confirmed_commitment')
        d = self.policy.evaluate(
            'amor me conta com detalhes o que aconteceu no ensaio ontem e o que você pensa sobre isso?',
            now=self.now, telegram_message_id=2,
        )
        self.assertEqual(d.activity_type, 'CLASS')
        self.assertIn(d.decision, ('DEFER', 'REPLY_BRIEFLY'))

    def test_stale_world_state_fail_open_unknown(self):
        self._snap(observed=self.now - timedelta(hours=5))
        d = self.policy.evaluate('oi', now=self.now, telegram_message_id=3)
        self.assertEqual(d.activity_type, 'UNKNOWN')
        self.assertEqual(d.decision, 'REPLY_NOW')
        self.assertFalse(d.can_claim_activity)

    def test_critical_overrides_class(self):
        self._snap(place_key='puc_rio', activity='em aula', reason='confirmed_commitment')
        d = self.policy.evaluate('socorro emergência me ajuda agora', now=self.now, telegram_message_id=4)
        self.assertEqual(d.decision, 'REPLY_NOW')
        self.assertIn(d.reason_code, ('critical_override', 'critical_now'))

    def test_routine_probability_cannot_claim_long_defer(self):
        self._snap(reason='routine_tick')
        d = self.policy.evaluate('tudo bem?', now=self.now, telegram_message_id=5)
        self.assertEqual(d.activity_source, 'ROUTINE_PROBABILITY')
        self.assertFalse(d.can_claim_activity)
        delay = (d.selected_target_at - d.earliest_reply_at).total_seconds()
        self.assertLessEqual(delay, 180)

    def test_sleep_routine_never_replies_before_window_ends(self):
        now = datetime(2026, 9, 19, 2, 45)
        self._snap(activity='dormindo', reason='light_day_sleep', observed=now)
        with patch.multiple(settings, CALENDAR_CONTINUITY_ENABLED=False,
                            CRITICAL_WAKE_POLICY_ENABLED=False):
            normal = self.policy.evaluate('tá acordada?', now=now, telegram_message_id=51)
            urgent = self.policy.evaluate('preciso falar contigo', now=now, telegram_message_id=52)
        expected = datetime(2026, 9, 19, 8, 30)
        self.assertEqual(normal.decision, 'DEFER')
        self.assertGreaterEqual(normal.selected_target_at, expected)
        self.assertEqual(urgent.decision, 'DEFER')
        self.assertGreaterEqual(urgent.selected_target_at, expected)

    def test_patch_015_stale_sleeping_snapshot_still_protects_sleep(self):
        """Reproduce the 20/09 01:27 bug: last snapshot said 'dormindo' 78 min
        earlier (stale > 60 min), we are still inside light_day_sleep window.
        Before Patch 015 the fallback dropped to UNKNOWN → REPLY_NOW; now it
        must preserve SLEEPING and DEFER until the window ends."""
        observed = datetime(2026, 9, 20, 0, 8)
        now = datetime(2026, 9, 20, 1, 27)  # 79 min after observed, still in sleep window
        self._snap(activity='dormindo', reason='light_day_sleep', observed=observed)
        with patch.multiple(settings, CALENDAR_CONTINUITY_ENABLED=False,
                            CRITICAL_WAKE_POLICY_ENABLED=False):
            decision = self.policy.evaluate('marinocaa tá acordada?',
                                            now=now, telegram_message_id=101)
        expected_end = datetime(2026, 9, 20, 8, 30)
        self.assertEqual(decision.activity_type, 'SLEEPING')
        self.assertEqual(decision.decision, 'DEFER')
        self.assertGreaterEqual(decision.selected_target_at, expected_end)

    def test_patch_015_stale_non_sleeping_still_falls_back_to_unknown(self):
        """Regression guard: outside the sleep window (or non-sleeping activity),
        stale snapshots must still fall back to UNKNOWN as before."""
        observed = datetime(2026, 9, 19, 14, 0)
        now = datetime(2026, 9, 19, 16, 30)  # 150 min stale, mid-afternoon
        self._snap(activity='tempo livre em casa', reason='free_time', observed=observed)
        with patch.multiple(settings, CALENDAR_CONTINUITY_ENABLED=False,
                            CRITICAL_WAKE_POLICY_ENABLED=False):
            decision = self.policy.evaluate('e aí amor?', now=now, telegram_message_id=102)
        self.assertEqual(decision.activity_type, 'UNKNOWN')


class PendingBatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'pending.db')
        seed_world_bible(self.db)
        self.repo = PendingResponseRepository(self.db)
        self.svc = ResponseAvailabilityService(self.db)
        self.now = datetime(2026, 9, 18, 14, 0)
        self.flags = {
            'RESPONSE_AVAILABILITY_ENABLED': True,
            'HUMAN_REPLY_LATENCY_ENABLED': True,
            'PENDING_CONVERSATION_BATCHING_ENABLED': True,
            'REAL_USAGE_TELEMETRY_ENABLED': True,
        }

    def _decision(self, **kwargs):
        from response_availability import ResponseAvailabilityDecision
        base = dict(
            decision='DEFER', phone_access='LOW', attention_level='LOW',
            interruptibility='LOW', message_urgency='LOW', response_complexity='SHORT',
            activity_type='CLASS', activity_source='WORLD_STATE', reason_code='class_busy',
            earliest_reply_at=self.now, target_window_start=self.now + timedelta(minutes=2),
            target_window_end=self.now + timedelta(minutes=30),
            selected_target_at=self.now + timedelta(minutes=15),
            context_snapshot_id=None, world_state_freshness='fresh',
            decision_seed='seed-1', can_claim_activity=True, shadow_only=False,
        )
        base.update(kwargs)
        return ResponseAvailabilityDecision(**base)

    def test_create_append_claim_sent_frees_active_slot(self):
        batch = self.repo.create_batch(self._decision())
        cid = self.db.adicionar_mensagem('user', 'meme kkk')
        self.assertTrue(self.repo.add_item(
            batch['id'], conversation_message_id=cid, telegram_message_id=10, received_at=self.now))
        self.assertFalse(self.repo.add_item(
            batch['id'], conversation_message_id=cid, telegram_message_id=10, received_at=self.now))
        due = self.now + timedelta(minutes=20)
        self.repo.mark_ready_due(due)
        claimed = self.repo.claim_due(due, owner='t1')
        self.assertEqual(claimed['id'], batch['id'])
        self.assertEqual(claimed['status'], 'SENDING')
        self.assertIsNone(self.repo.claim_due(due, owner='t2'))
        self.assertTrue(self.repo.mark_sent(batch['id'], sent_message_id=99))
        # New active batch allowed after SENT.
        again = self.repo.create_batch(self._decision(decision_seed='seed-2'))
        self.assertNotEqual(again['id'], batch['id'])

    def test_expired_sending_lease_becomes_unknown_not_resent(self):
        batch = self.repo.create_batch(self._decision(selected_target_at=self.now))
        cid = self.db.adicionar_mensagem('user', 'oi')
        self.repo.add_item(batch['id'], conversation_message_id=cid,
                           telegram_message_id=1, received_at=self.now)
        claimed = self.repo.claim_due(self.now, owner='w1', lease_seconds=60)
        self.assertEqual(claimed['status'], 'SENDING')
        later = self.now + timedelta(minutes=5)
        self.assertIsNone(self.repo.claim_due(later, owner='w2'))
        with self.db.get_connection() as conn:
            status = conn.execute(
                'SELECT status FROM response_pending_batches WHERE id=?', (batch['id'],)
            ).fetchone()['status']
        self.assertEqual(status, 'UNKNOWN_DELIVERY')

    def test_startup_recover_ready_and_unknown(self):
        pending = self.repo.create_batch(self._decision(selected_target_at=self.now - timedelta(minutes=1)))
        with self.db.get_connection() as conn:
            conn.execute(
                """UPDATE response_pending_batches
                   SET active_key='patrick_marina:closed:pending_seed' WHERE id=?""",
                (pending['id'],),
            )
        sending = self.repo.create_batch(self._decision(
            decision_seed='s2', selected_target_at=self.now - timedelta(minutes=2)))
        with self.db.get_connection() as conn:
            conn.execute(
                """UPDATE response_pending_batches
                   SET status='SENDING', lease_owner='dead', lease_until=?,
                       active_key='patrick_marina:closed:sending_seed'
                   WHERE id=?""",
                ((self.now - timedelta(minutes=10)).isoformat(), sending['id']),
            )
            conn.execute(
                """UPDATE response_pending_batches SET active_key='patrick_marina:active',
                       status='PENDING' WHERE id=?""",
                (pending['id'],),
            )
        stats = self.repo.recover_on_startup(self.now)
        self.assertGreaterEqual(stats['ready'], 1)
        self.assertGreaterEqual(stats['unknown'], 1)

    def test_inflight_batch_is_frozen_and_new_message_gets_successor(self):
        first, added, _ = self.repo.enqueue_item(
            self._decision(selected_target_at=self.now), message='primeira',
            telegram_message_id=501, received_at=self.now,
        )
        self.assertTrue(added)
        claimed = self.repo.claim_due(self.now, owner='worker')
        self.assertEqual(claimed['id'], first['id'])
        second, added, merged = self.repo.enqueue_item(
            self._decision(decision_seed='successor', selected_target_at=self.now),
            message='segunda', telegram_message_id=502, received_at=self.now,
        )
        self.assertTrue(added)
        self.assertFalse(merged)
        self.assertNotEqual(second['id'], first['id'])
        self.assertEqual([i['content'] for i in self.repo.list_items(first['id'])], ['primeira'])
        self.assertEqual([i['content'] for i in self.repo.list_items(second['id'])], ['segunda'])
        # A second worker cannot send the successor before the first delivery ends.
        self.assertIsNone(self.repo.claim_due(self.now, owner='other'))
        self.assertTrue(self.repo.extend_lease(
            first['id'], owner='worker', now=self.now + timedelta(seconds=30)))
        self.assertTrue(self.repo.mark_sent(first['id'], sent_message_id=800))
        self.assertEqual(self.repo.claim_due(self.now, owner='other')['id'], second['id'])

    def test_enqueue_replay_does_not_duplicate_conversation(self):
        decision = self._decision()
        first, added, _ = self.repo.enqueue_item(
            decision, message='olá', telegram_message_id=503, received_at=self.now)
        replay, added_again, _ = self.repo.enqueue_item(
            decision, message='olá', telegram_message_id=503, received_at=self.now)
        self.assertEqual(replay['id'], first['id'])
        self.assertFalse(added_again)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM conversas WHERE role='user' AND content='olá'"
            ).fetchone()[0], 1)

    def test_enqueue_rolls_back_conversation_when_item_insert_fails(self):
        with patch.object(self.repo, 'add_item', side_effect=RuntimeError('injected')):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                self.repo.enqueue_item(
                    self._decision(), message='atomic',
                    telegram_message_id=504, received_at=self.now,
                )
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM conversas WHERE content='atomic'"
            ).fetchone()[0], 0)
            self.assertEqual(conn.execute(
                'SELECT COUNT(*) FROM response_pending_batches'
            ).fetchone()[0], 0)

    def test_defer_merge_and_urgent_override(self):
        with self.db.get_connection() as conn:
            place_row = conn.execute(
                "SELECT id, region FROM world_places WHERE canonical_key='puc_rio'"
            ).fetchone()
        WorldStateRepository(self.db).add_snapshot({
            'state_date': self.now.date().isoformat(),
            'observed_at': self.now.isoformat(),
            'location_place_id': place_row['id'],
            'location_region': place_row['region'],
            'activity': 'em aula',
            'energy_level': 0.5,
            'source_json': {'reason': 'confirmed_commitment'},
        })
        with patch.multiple(settings, **self.flags):
            action, decision, batch = self.svc.evaluate_and_maybe_defer(
                'kkkk meme aleatório bem longo pra forçar defer na aula com contexto',
                telegram_message_id=100, now=self.now,
            )
            self.assertEqual(action, 'deferred')
            self.assertIsNotNone(batch)
            action2, decision2, batch2 = self.svc.evaluate_and_maybe_defer(
                'amor preciso falar contigo',
                telegram_message_id=101, now=self.now + timedelta(minutes=1),
            )
            self.assertEqual(action2, 'deferred')
            self.assertEqual(batch2['id'], batch['id'])
            self.assertIn(decision2.message_urgency, ('HIGH', 'CRITICAL'))
            self.assertEqual(batch2['status'], 'READY')
            items = self.repo.list_items(batch['id'])
            self.assertEqual(len(items), 2)


class BriefRhythmHintTests(unittest.TestCase):
    def test_brief_hint_caps_bubbles(self):
        policy = select_policy(
            'me explica detalhadamente',
            availability_budget_hint='brief_due_to_availability',
        )
        self.assertEqual(policy.reason_code, 'brief_due_to_availability')
        # v3.7.0 made max_bubbles advisory-only; segment() enforces limits.
        # target_bubbles=1 remains the intent hint for a brief availability turn.
        self.assertEqual(policy.target_bubbles, 1)
        self.assertEqual(policy.followup_question, 'not_required')


class PendingDeliveryRoutineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'delivery.db')
        self.svc = ResponseAvailabilityService(self.db)
        self.now = datetime.now()
        from response_availability import ResponseAvailabilityDecision
        self.decision = ResponseAvailabilityDecision(
            decision='DEFER', phone_access='LOW', attention_level='LOW',
            interruptibility='LOW', message_urgency='LOW', response_complexity='SHORT',
            activity_type='CLASS', activity_source='WORLD_STATE', reason_code='class_busy',
            earliest_reply_at=self.now, target_window_start=self.now,
            target_window_end=self.now + timedelta(hours=1),
            selected_target_at=self.now - timedelta(seconds=1),
            context_snapshot_id=None, world_state_freshness='fresh',
            decision_seed='delivery-test', can_claim_activity=True, shadow_only=False,
        )
        self.batch, _, _ = self.svc.repo.enqueue_item(
            self.decision, message='pending user message', telegram_message_id=901,
            received_at=self.now,
        )

    async def _run_with_send(self, send_message):
        import bot
        fake_bot = SimpleNamespace(send_message=send_message)

        async def pipeline(_update, context, _text, **_kwargs):
            await context.bot.send_message(chat_id=1, text='confirmed reply')

        with patch.object(bot, 'availability_service', self.svc), \
             patch.object(bot.memory_manager, 'db', self.db), \
             patch.object(bot, 'process_incoming_batch', side_effect=pipeline):
            await bot.pending_response_routine(SimpleNamespace(bot=fake_bot))

    async def test_due_job_drains_and_records_confirmed_send(self):
        await self._run_with_send(AsyncMock(return_value=SimpleNamespace(message_id=902)))
        batch = self.svc.repo.get_batch(self.batch['id'])
        self.assertEqual(batch['status'], 'SENT')
        self.assertEqual(batch['sent_message_id'], 902)

    async def test_ambiguous_telegram_failure_is_not_retried(self):
        await self._run_with_send(AsyncMock(side_effect=RuntimeError('network timeout')))
        batch = self.svc.repo.get_batch(self.batch['id'])
        self.assertEqual(batch['status'], 'UNKNOWN_DELIVERY')
        self.assertIsNone(self.svc.repo.claim_due(datetime.now(), owner='second-worker'))


class ConfigGateTests(unittest.TestCase):
    def test_availability_pipeline_is_canonical(self):
        from config import Settings
        self.assertTrue(Settings.RESPONSE_AVAILABILITY_ENABLED)
        self.assertTrue(Settings.HUMAN_REPLY_LATENCY_ENABLED)
        self.assertTrue(Settings.PENDING_CONVERSATION_BATCHING_ENABLED)


if __name__ == '__main__':
    unittest.main()
