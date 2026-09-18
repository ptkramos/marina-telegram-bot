"""Calendar authority, academic progression and future-thread protection."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from academic_life import AcademicLife
from calendar_world import CalendarWorld, RealContextCache
from config import settings
from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from story_engine import StoryEngine
from world_state import WorldStateManager


class TestCalendarAcademicV364(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'v364.db')
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.academic = AcademicLife(self.db)
        self.calendar = CalendarWorld(self.db)

    def test_grade_projects_into_calendar_and_confirmed_casting_needs_resolution(self):
        now = datetime(2026, 9, 22, 9)  # Tuesday, Linguagem e Estruturas.
        self.academic.catch_up(now)
        current = self.calendar.current(now)
        self.assertIn('faculdade', current['activity'])
        self.assertIn('academic_block_id', current)
        with self.assertRaisesRegex(ValueError, 'conflicts with class'):
            self.calendar.create_commitment(
                source_key='casting:1', event_type='casting', description='casting confirmado',
                start_at=now, end_at=now + timedelta(hours=1))
        event_id = self.calendar.create_commitment(
            source_key='casting:1', event_type='casting', description='casting confirmado',
            start_at=now, end_at=now + timedelta(hours=1),
            conflict_resolution='approved_absence')
        self.assertEqual(self.calendar.current(now)['calendar_event_id'], event_id)
        self.assertEqual(self.calendar.create_commitment(
            source_key='casting:1', event_type='casting', description='casting confirmado',
            start_at=now, end_at=now + timedelta(hours=1),
            conflict_resolution='approved_absence'), event_id)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM eventos_pendentes').fetchone()[0], 1)

    def test_exception_changes_one_class_occurrence_without_mutating_grade(self):
        now = datetime(2026, 9, 22, 9)
        self.academic.catch_up(now)
        block = self.academic.current_block(now)
        self.academic.cancel_class_occurrence(
            block['id'], now.date(), source_key='cancel:class:2026-09-22')
        self.assertIsNone(self.academic.current_block(now))
        self.assertIsNotNone(self.academic.current_block(now + timedelta(days=7)))
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT active FROM academic_schedule_blocks WHERE id=?',
                                          (block['id'],)).fetchone()[0], 1)

    def test_presentation_is_a_dated_calendar_event(self):
        now = datetime(2026, 9, 18, 11)
        self.academic.catch_up(now)
        event_id = self.academic.schedule_event(
            course_key='DSG1400', event_type='academic_presentation',
            description='apresentação do projeto', start_at=now + timedelta(days=3),
            end_at=now + timedelta(days=3, hours=1), source_key='academic:project:showcase')
        with self.db.get_connection() as conn:
            event = conn.execute('SELECT * FROM eventos_pendentes WHERE id=?',
                                 (event_id,)).fetchone()
        self.assertEqual(event['owner_character_key'], 'marina')
        self.assertEqual(event['confirmed'], 1)
        self.assertEqual(event['event_type'], 'academic_presentation')

    def test_vacation_and_two_year_lazy_catch_up_are_idempotent(self):
        self.academic.catch_up(datetime(2026, 9, 18), auto_generate=True)
        self.assertEqual(self.academic.phase(datetime(2026, 9, 18),
                                              self.academic._active_term_on(datetime(2026, 9, 18).date())),
                         'NORMAL')
        self.assertIsNotNone(self.academic.repo.get_term('2027.1'))
        january = self.academic.catch_up(datetime(2027, 1, 15), auto_generate=True)
        self.assertEqual(january['phase'], 'VACATION')
        self.assertEqual(self.academic.blocks_on(datetime(2027, 1, 15).date()), [])
        later = self.academic.catch_up(datetime(2028, 10, 10), auto_generate=True)
        self.assertEqual(later['term'], '2028.2')
        with self.db.get_connection() as conn:
            before = conn.execute('SELECT COUNT(*) FROM academic_terms').fetchone()[0]
            events = conn.execute('SELECT COUNT(*) FROM life_events').fetchone()[0]
        self.assertEqual(self.academic.catch_up(datetime(2028, 10, 10), auto_generate=True)['term'],
                         later['term'])
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM academic_terms').fetchone()[0], before)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM life_events').fetchone()[0], events)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM academic_terms WHERE status='ACTIVE'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM academic_courses WHERE status='FAILED'").fetchone()[0], 0)

    def test_real_context_ttl_and_rain_affect_world_state_without_invention(self):
        now = datetime(2026, 9, 18, 18)
        cache = RealContextCache(self.db)
        self.assertIsNone(cache.get('weather:rio', now=now))
        cache.put('weather:rio', 'weather', {'heavy_rain': True},
                  source_name='reviewed observation', observed_at=now - timedelta(minutes=1),
                  expires_at=now + timedelta(minutes=10))
        self.assertIsNotNone(cache.get('weather:rio', now=now))
        self.assertIsNone(cache.get('weather:rio', now=now + timedelta(minutes=11)))
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True):
            state = WorldStateManager(self.db).resolve(now, force=True)
        self.assertTrue(json.loads(state['weather_context_json'])['heavy_rain'])

    def test_observed_holiday_suppresses_only_that_day_schedule(self):
        day = datetime(2026, 9, 22).date()
        self.academic.catch_up(datetime(2026, 9, 18))
        self.assertTrue(self.academic.blocks_on(day))
        RealContextCache(self.db).put(
            f'holiday:{day.isoformat()}', 'holiday',
            {'date': day.isoformat(), 'name': 'Feriado confirmado', 'scope': 'campus'},
            source_name='calendário do campus', observed_at=datetime(2026, 9, 18),
            expires_at=datetime(2026, 9, 23))
        self.assertEqual(self.academic.blocks_on(day), [])
        self.assertTrue(self.academic.blocks_on(day + timedelta(days=7)))

    def test_official_puc_holiday_and_friday_have_no_class(self):
        self.assertEqual(self.academic.blocks_on(datetime(2026, 10, 15).date()), [])
        self.assertEqual(self.academic.blocks_on(datetime(2026, 9, 18).date()), [])
        self.assertEqual(len(self.academic.blocks_on(datetime(2026, 9, 23).date())), 3)

    def test_civil_holiday_does_not_override_explicit_puc_class_day(self):
        day = datetime(2026, 9, 23).date()
        RealContextCache(self.db).put(
            f'holiday:{day.isoformat()}', 'holiday',
            {'date': day.isoformat(), 'name': 'Feriado municipal observado',
             'scope': 'municipal'}, source_name='Feriados API',
            observed_at=datetime(2026, 9, 18), expires_at=datetime(2026, 9, 24))
        self.assertEqual(len(self.academic.blocks_on(day)), 3)

    def test_observed_civil_holiday_reaches_world_state_without_creating_event(self):
        now = datetime(2026, 9, 18, 18)
        RealContextCache(self.db).put(
            f'holiday:{now.date().isoformat()}', 'holiday',
            {'date': now.date().isoformat(), 'name': 'Feriado local', 'scope': 'municipal'},
            source_name='Feriados API', observed_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=3))
        with (patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True),
              patch.object(settings, 'ACADEMIC_LIFE_ENABLED', True)):
            state = WorldStateManager(self.db).resolve(now, force=True)
        self.assertEqual(json.loads(state['source_json'])['holiday_scope'], 'municipal')
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM life_events').fetchone()[0], 0)

    def test_world_state_uses_class_before_routine_when_enabled(self):
        now = datetime(2026, 9, 22, 9)
        with (patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True),
              patch.object(settings, 'ACADEMIC_LIFE_ENABLED', True)):
            state = WorldStateManager(self.db).resolve(now, force=True)
        self.assertIn('faculdade', state['activity'])
        self.assertEqual(json.loads(state['source_json'])['reason'], 'confirmed_commitment')

    def test_academic_flag_requires_shared_calendar(self):
        with (patch.object(settings, 'ACADEMIC_LIFE_ENABLED', True),
              patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False)):
            with self.assertRaisesRegex(RuntimeError, 'requires Calendar Continuity'):
                WorldStateManager(self.db).resolve(datetime(2026, 9, 22, 9))

    def test_cancelling_current_class_invalidates_cached_world_state(self):
        now = datetime(2026, 9, 22, 9)
        with (patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True),
              patch.object(settings, 'ACADEMIC_LIFE_ENABLED', True)):
            manager = WorldStateManager(self.db)
            first = manager.resolve(now)
            self.assertIn('faculdade', first['activity'])
            block = self.academic.current_block(now)
            self.academic.cancel_class_occurrence(
                block['id'], now.date(), source_key='cancel:current-class')
            second = manager.resolve(now + timedelta(minutes=1))
        self.assertNotEqual(second['id'], first['id'])
        self.assertNotIn('faculdade', second['activity'])

    def test_future_confirmed_calendar_event_protects_story_thread_until_cancelled(self):
        now = datetime(2026, 9, 18, 12)
        old = now - timedelta(days=45)
        with self.db.get_connection() as conn:
            thread_id = conn.execute('''INSERT INTO story_threads
                (thread_key,thread_type,title,summary,status,started_at,last_event_at,metadata_json)
                VALUES ('casting-thread','ordinary','Casting','Casting futuro','open',?,?,?)''',
                (old.isoformat(), old.isoformat(), '{}')).lastrowid
        event_id = self.calendar.create_commitment(
            source_key='casting:future', event_type='casting', description='casting confirmado',
            start_at=now + timedelta(days=12, hours=3), end_at=now + timedelta(days=12, hours=4),
            story_thread_id=thread_id)
        self.assertTrue(self.calendar.linked_future_commitment(thread_id, now=now))
        engine = StoryEngine(self.db)
        engine.quiet_old_threads(now)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT status FROM story_threads WHERE id=?',
                                          (thread_id,)).fetchone()[0], 'dormant')
        self.db.cancelar_evento_pendente(event_id)
        self.assertFalse(self.calendar.linked_future_commitment(thread_id, now=now))
        engine.quiet_old_threads(now)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT status FROM story_threads WHERE id=?',
                                          (thread_id,)).fetchone()[0], 'abandoned')

    def test_reschedule_and_relevance_change_use_calendar_as_authority(self):
        now = datetime(2026, 9, 18, 12)
        old = now - timedelta(days=45)
        with self.db.get_connection() as conn:
            thread_id = conn.execute('''INSERT INTO story_threads
                (thread_key,thread_type,title,summary,status,started_at,last_event_at)
                VALUES ('future-project','ordinary','Projeto','Entrega futura','dormant',?,?)''',
                (old.isoformat(), old.isoformat())).lastrowid
        event_id = self.calendar.create_commitment(
            source_key='project:future', event_type='academic_deadline',
            description='entrega do projeto', start_at=now + timedelta(days=21),
            end_at=now + timedelta(days=21, minutes=15), story_thread_id=thread_id)
        self.calendar.reschedule(event_id, start_at=now + timedelta(days=25),
                                 end_at=now + timedelta(days=25, minutes=15))
        self.assertTrue(self.calendar.linked_future_commitment(thread_id, now=now))
        self.calendar.unlink_thread(event_id)
        self.assertFalse(self.calendar.linked_future_commitment(thread_id, now=now))


if __name__ == '__main__':
    unittest.main()
