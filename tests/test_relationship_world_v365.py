"""Stage 12 evidence, disclosure and ranking contracts. Run externally."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from config import settings
from db import DatabaseManager
from knowledge_privacy import KnowledgePrivacy
from proactivity_service import ProactivityService
from relationship_world import RelationshipWorld
from seed_world_bible_v36 import seed_world_bible


class RelationshipWorldTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'relationship.db')
        seed_world_bible(self.db)
        self.world = RelationshipWorld(self.db)
        self.privacy = KnowledgePrivacy(self.db)
        self.now = datetime(2026, 9, 18, 15)

    def _event(self, *, summary='Recebi uma resposta positiva do projeto de moda.'):
        with self.db.get_connection() as conn:
            return conn.execute('''INSERT INTO life_events
                (event_key,event_at,event_type,title,summary,source_type,
                 autonomy_level,importance,share_worthy,created_at)
                VALUES (?,?,?,?,?,'canonical',1,.6,.85,?)''',
                ('project-reply', (self.now - timedelta(days=8)).isoformat(),
                 'project_feedback', 'Resposta do projeto', summary, self.now.isoformat())
            ).lastrowid

    def test_culture_requires_recorded_phrase_and_distinct_reinforcement(self):
        first = self.db.adicionar_mensagem('user', 'Pode me chamar de "Sol".')
        second = self.db.adicionar_mensagem('user', 'Me chama de "Sol", amor.')
        self.assertEqual(self.world.culture_context(), [])
        self.world.observe_explicit_user_culture('Pode me chamar de "Sol".', conversation_id=first)
        self.world.observe_explicit_user_culture('Pode me chamar de "Sol".', conversation_id=first)
        self.assertEqual(self.world.culture_context(), [])
        self.world.observe_explicit_user_culture('Me chama de "Sol", amor.', conversation_id=second)
        self.assertIn('Patrick pediu para ser chamado de: Sol', self.world.culture_context())
        with self.assertRaises(ValueError):
            self.world.observe_culture('nickname_for_patrick', 'Lua', conversation_id=first)

    def test_share_candidate_needs_permission_and_disappears_after_confirmed_share(self):
        event_id = self._event()
        self.privacy.observe('event', event_id, 'marina', privacy_level='PRIVATE_COUPLE')
        self.assertEqual(self.world.shareable_events(self.now), [])
        self.privacy.grant('event', event_id, 'marina', 'patrick_ramos',
                           authorized_by='marina', spontaneous=True)
        candidate = self.world.ranked_candidate(self.now)
        self.assertEqual(candidate['reason'], 'share_worthy_event')
        self.assertEqual(candidate['subject_id'], event_id)
        self.assertFalse(self.privacy.known_by('event', event_id, 'patrick_ramos'))
        self.privacy.record_confirmed_share('event', event_id, 'marina', 'patrick_ramos',
                                            detail_level='details', evidence_key='telegram:1:101:event:1')
        self.assertEqual(self.world.shareable_events(self.now), [])
        self.assertEqual(self.world.shared_history()[0]['title'], 'Resposta do projeto')

    def test_private_and_abstract_events_never_become_spontaneous_news(self):
        event_id = self._event(summary='')
        self.privacy.observe('event', event_id, 'marina', privacy_level='PRIVATE_SELF')
        self.assertEqual(self.world.shareable_events(self.now), [])

    def test_safe_metadata_share_does_not_expose_event_title_as_shared_history(self):
        event_id = self._event()
        self.privacy.observe('event', event_id, 'marina', privacy_level='CONFIDENTIAL',
                             safe_metadata={'severity': 'low'})
        self.privacy.grant('event', event_id, 'marina', 'patrick_ramos',
                           authorized_by='marina', detail_level='safe_metadata')
        self.privacy.record_confirmed_share('event', event_id, 'marina', 'patrick_ramos',
                                            detail_level='safe_metadata',
                                            evidence_key='telegram:safe:101')
        self.assertEqual(self.world.shared_history(), [])
        self.assertEqual(self.world.shareable_events(self.now), [])
        self.privacy.grant('event', event_id, 'marina', 'patrick_ramos',
                           authorized_by='marina', spontaneous=True)
        self.assertEqual(self.world.shareable_events(self.now)[0]['id'], event_id)

    def test_grounded_reason_outranks_affection_but_low_priority_can_stay_quiet(self):
        service = ProactivityService(self.db)
        with patch.object(settings, 'LIVING_WORLD_ENABLED', True), \
             patch.object(settings, 'RELATIONSHIP_WORLD_ENABLED', True), \
             patch('proactivity_service.random.random', return_value=.99):
            self.assertEqual(service.should_trigger(self.now), (False, 'living_world_quiet'))
            due = (self.now - timedelta(hours=2)).isoformat()
            self.db.adicionar_evento_pendente('consulta', 'Consulta do Patrick', due,
                                              follow_up_after=due)
            self.assertEqual(service.determine_living_world_candidate(self.now)['reason'],
                             'pending_event_followup')
            self.assertEqual(service.should_trigger(self.now), (True, 'pending_event_followup'))

    def test_marinas_calendar_event_is_not_treated_as_patricks_followup(self):
        due = (self.now - timedelta(hours=2)).isoformat()
        event_id = self.db.adicionar_evento_pendente('aula', 'Apresentação de Marina', due,
                                                      follow_up_after=due)
        with self.db.get_connection() as conn:
            conn.execute("UPDATE eventos_pendentes SET owner_character_key='marina' WHERE id=?",
                         (event_id,))
        self.assertEqual(self.world.ranked_candidate(self.now)['reason'], 'light_affection')


class LivingWorldDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_send_does_not_consume_open_loop_or_record_message(self):
        from bot import autonomous_routine_v36
        candidate = {'reason': 'open_loop_checkin', 'rank': 80,
                     'loop_id': 17, 'detail': 'o projeto'}
        fake_service = MagicMock()
        fake_service.should_trigger.return_value = (True, 'open_loop_checkin')
        fake_service.determine_living_world_candidate.return_value = candidate
        fake_bot = MagicMock()
        fake_bot.send_message = AsyncMock(side_effect=RuntimeError('Telegram offline'))
        fake_db = MagicMock()
        with patch.object(settings, 'TARGET_CHAT_ID', 123), \
             patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', True), \
             patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False), \
             patch('bot.proactivity_service', fake_service), \
             patch('bot._proactive_text', return_value='amor, e o projeto?'), \
             patch('bot.memory_manager.db', fake_db):
            await autonomous_routine_v36(SimpleNamespace(bot=fake_bot))
        fake_service.db.atualizar_open_loop_touch.assert_not_called()
        fake_db.registrar_iniciativa_marina.assert_not_called()
        fake_service.record_autonomous_sent.assert_not_called()

    async def test_confirmed_send_advances_open_loop_after_delivery(self):
        from bot import autonomous_routine_v36
        candidate = {'reason': 'open_loop_checkin', 'rank': 80,
                     'loop_id': 17, 'detail': 'o projeto'}
        fake_service = MagicMock()
        fake_service.should_trigger.return_value = (True, 'open_loop_checkin')
        fake_service.determine_living_world_candidate.return_value = candidate
        fake_bot = MagicMock()
        fake_bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=42))
        fake_bot.send_chat_action = AsyncMock()   # 23/09: iniciativa sai em balões (send_human_messages)
        fake_db = MagicMock()
        with patch.object(settings, 'TARGET_CHAT_ID', 123),              patch('bot.asyncio.sleep', AsyncMock()), \
             patch.object(settings, 'KNOWLEDGE_PRIVACY_ENABLED', True), \
             patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False), \
             patch('bot.proactivity_service', fake_service), \
             patch('bot._proactive_text', return_value='amor, e o projeto?'), \
             patch('bot.memory_manager.db', fake_db):
            await autonomous_routine_v36(SimpleNamespace(bot=fake_bot))
        fake_service.db.atualizar_open_loop_touch.assert_called_once()
        fake_db.registrar_iniciativa_marina.assert_called_once()
        fake_service.record_autonomous_sent.assert_called_once()


if __name__ == '__main__':
    unittest.main()
