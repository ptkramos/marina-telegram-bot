import tempfile
import json
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from story_engine import StoryEngine,SEEDS,StorySeed,LIBRARY_PATH,load_local_seed_pool
from config import settings
from scripts.story_datasets.simulate_story_seeds import realistic_context


class TestStoryEngine(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db=DatabaseManager(Path(temp.name)/'story.db')
        seed_world_bible(self.db)
        self.engine=StoryEngine(self.db)
        self.now=datetime(2026,9,18,12)

    def test_ordinary_days_dominate_selection_without_calendar_assumptions(self):
        dates=[datetime(2026,1,1)+timedelta(days=i) for i in range(100)]
        selections=[self.engine.select_seed(now) for now in dates]
        self.assertGreaterEqual(sum(seed is None for seed in selections),55)
        self.assertLessEqual(sum(seed is None for seed in selections),75)
        self.assertFalse(any(s and s.thread_type in ('academic','professional') for s in selections))
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM life_events').fetchone()[0],0)

    def test_daily_tick_is_idempotent_and_stores_only_abstract_facts(self):
        with patch.object(self.engine,'select_seed',return_value=SEEDS[1]):
            first=self.engine.daily_tick(self.now)
            second=self.engine.daily_tick(self.now)
        self.assertEqual(first,second)
        self.assertEqual(first['seed_key'],'pet_minor_mischief')
        with self.db.get_connection() as c:
            thread=c.execute('SELECT * FROM story_threads').fetchone()
            event=c.execute('SELECT * FROM life_events').fetchone()
            self.assertEqual(thread['status'],'open')
            self.assertEqual(event['share_worthy'],0)
            self.assertEqual(event['source_type'],'simulated')
            self.assertIn('ainda não está definido',event['summary'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM conversas').fetchone()[0],0)

    def test_consequence_requires_explicit_observation_and_can_resolve(self):
        with patch.object(self.engine,'select_seed',return_value=SEEDS[0]):
            start=self.engine.daily_tick(self.now)
        thread_key=start['event_key'].removesuffix(':start')
        with self.assertRaises(ValueError):
            self.engine.continue_thread(thread_key,evidence_key='e1',occurred_at=self.now.isoformat(),summary='achou',participants=('marina',))
        follow=self.engine.continue_thread(thread_key,evidence_key='e1',occurred_at=(self.now+timedelta(days=1)).isoformat(),summary='Marina encontrou o objeto.',participants=('marina',),resolved=True)
        self.assertEqual(self.engine.continue_thread(thread_key,evidence_key='e1',occurred_at=(self.now+timedelta(days=1)).isoformat(),summary='Marina encontrou o objeto.',participants=('marina',),resolved=True),follow)
        with self.db.get_connection() as c:
            row=c.execute('SELECT * FROM life_events WHERE id=?',(follow,)).fetchone()
            self.assertIsNotNone(row['consequence_of_event_id'])
            self.assertEqual(c.execute('SELECT status FROM story_threads').fetchone()[0],'resolved')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM life_events').fetchone()[0],2)

    def test_old_thread_can_go_dormant_then_abandoned_without_forced_plot(self):
        with patch.object(self.engine,'select_seed',return_value=SEEDS[0]):
            self.engine.daily_tick(self.now)
        self.engine.quiet_old_threads(self.now+timedelta(days=11))
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT status FROM story_threads').fetchone()[0],'dormant')
        self.engine.quiet_old_threads(self.now+timedelta(days=31))
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT status FROM story_threads').fetchone()[0],'abandoned')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM life_events').fetchone()[0],1)

    def test_budget_prevents_second_plot_and_major_events(self):
        with patch.object(self.engine,'select_seed',return_value=SEEDS[0]):
            self.engine.daily_tick(self.now)
        self.assertIsNone(self.engine.select_seed(self.now+timedelta(days=1)))
        dangerous=StorySeed('bad','Marina morreu','Morte da Marina','ordinary',4,.9,('marina',))
        with self.assertRaises(ValueError):
            with self.db.transaction():
                self.engine._start(dangerous,self.now+timedelta(days=2))
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM life_events').fetchone()[0],1)

    def test_conflicting_replay_cannot_rewrite_a_consequence(self):
        with patch.object(self.engine,'select_seed',return_value=SEEDS[0]):
            start=self.engine.daily_tick(self.now)
        thread_key=start['event_key'].removesuffix(':start')
        tomorrow=(self.now+timedelta(days=1)).isoformat()
        self.engine.continue_thread(thread_key,evidence_key='observed:1',occurred_at=tomorrow,
                                    summary='Marina encontrou o objeto.',participants=('marina',))
        for changes in ({'participants':('marina','bia')},
                        {'occurred_at':(self.now+timedelta(days=2)).isoformat()},
                        {'resolved':True}):
            args=dict(evidence_key='observed:1',occurred_at=tomorrow,
                      summary='Marina encontrou o objeto.',participants=('marina',))
            args.update(changes)
            with self.assertRaises(ValueError):
                self.engine.continue_thread(thread_key,**args)
        with self.assertRaises(ValueError):
            self.engine.continue_thread(thread_key,evidence_key=start['event_key'],
                occurred_at=self.now.isoformat(),summary=SEEDS[0].summary,participants=('marina',))
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM life_events').fetchone()[0],2)

    def test_coherence_rejects_unknown_canon_and_hard_gated_consequence(self):
        unknown=StorySeed('new_place','Passeio','Marina saiu.','ordinary',1,.1,('marina',),'invented_place')
        with self.assertRaises(ValueError):
            with self.db.transaction():
                self.engine._start(unknown,self.now)
        with patch.object(self.engine,'select_seed',return_value=SEEDS[0]):
            start=self.engine.daily_tick(self.now)
        thread_key=start['event_key'].removesuffix(':start')
        with self.assertRaises(ValueError):
            self.engine.continue_thread(thread_key,evidence_key='observed:2',
                occurred_at=(self.now+timedelta(days=1)).isoformat(),
                summary='Marina morreu.',participants=('marina',))
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM life_events').fetchone()[0],1)

    def test_selection_respects_observed_context_and_can_leave_day_empty(self):
        days=[self.now+timedelta(days=i) for i in range(30)]
        invitation_context={'allowed_seed_keys':['unexpected_invitation']}
        candidate=next(day for day in days if self.engine.select_seed(day,context=invitation_context))
        self.assertEqual(self.engine.select_seed(candidate,context=invitation_context).key,'unexpected_invitation')
        self.assertIsNone(self.engine.select_seed(candidate,context={**invitation_context,'calendar_busy':True}))
        home_context={'allowed_seed_keys':['pet_minor_mischief'],'location_place_key':'unknown_place'}
        self.assertIsNone(self.engine.select_seed(candidate,context=home_context))
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM life_events').fetchone()[0],0)

    def test_expanded_library_has_runtime_templates_and_observation_gates(self):
        with patch.object(settings,'STORY_SEED_LIBRARY_ENABLED',True):
            pool=load_local_seed_pool()
        keys={seed.key for seed in pool}
        library_keys={json.loads(line)['seed_key'] for line in LIBRARY_PATH.read_text(encoding='utf-8').splitlines()}
        self.assertEqual(keys,library_keys)
        self.assertIn('friend_plan_cancelled',keys)
        self.assertIn('academic_feedback',keys)
        with patch.object(self.engine,'seed_pool',pool):
            for seed in pool:
                if seed.key in ('friend_plan_cancelled','academic_feedback','weather_changes_plan'):
                    self.assertFalse(self.engine._eligible(seed,self.now,{}))
            observed={'plan_cancelled_observed':True,'academic_feedback_observed':True,
                      'weather_disruption_observed':True,'academic_available':True}
            for seed in pool:
                if seed.key in ('friend_plan_cancelled','academic_feedback','weather_changes_plan'):
                    self.assertTrue(self.engine._eligible(seed,self.now,observed))

    def test_curated_category_seeds_require_observed_context_and_canon(self):
        with patch.object(settings,'STORY_SEED_LIBRARY_ENABLED',True):
            pool={seed.key:seed for seed in load_local_seed_pool()}
        expected=('partner_small_gesture','father_check_in','self_care_pause')
        for key in expected:
            self.assertFalse(self.engine._eligible(pool[key],self.now,{}))
            self.engine.validator.validate_seed(pool[key])
        observed={'partner_gesture_observed':True,'father_contact_observed':True,
                  'rest_need_observed':True,'relationship_committed':True}
        for key in expected:
            self.assertTrue(self.engine._eligible(pool[key],self.now,observed))
        self.assertFalse(self.engine._eligible(pool['partner_small_gesture'],self.now,
                                              {'partner_gesture_observed':True}))

    def test_realistic_context_is_deterministic_and_does_not_force_cycle_effects(self):
        days=[self.now+timedelta(days=i) for i in range(60)]
        contexts=[realistic_context(day) for day in days]
        self.assertEqual(contexts,[realistic_context(day) for day in days])
        self.assertTrue(all(context['relationship_committed'] for context in contexts))
        self.assertTrue(any(not context['father_contact_observed'] for context in contexts))
        self.assertTrue(any(not context['partner_gesture_observed'] for context in contexts))
        self.assertTrue(any(context['rest_need_observed'] for context in contexts))
        self.assertTrue(all('cycle_phase' not in context for context in contexts))

    def test_dormant_thread_can_receive_evidence_and_return_to_open(self):
        with patch.object(self.engine, 'select_seed', return_value=SEEDS[0]):
            start = self.engine.daily_tick(self.now)
        thread_key = start['event_key'].removesuffix(':start')

        # Passam 11 dias: a thread torna-se dormant
        self.engine.quiet_old_threads(self.now + timedelta(days=11))
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT status FROM story_threads WHERE thread_key=?', (thread_key,)).fetchone()[0], 'dormant')

        # Nova evidência sem resolução reabre a thread (DORMANT -> OPEN)
        new_date = (self.now + timedelta(days=12)).isoformat()
        ev_id = self.engine.continue_thread(
            thread_key,
            evidence_key='observed:reopen_1',
            occurred_at=new_date,
            summary='Marina relembrou onde colocou o objeto e foi procurar.',
            participants=('marina',),
            resolved=False
        )
        self.assertIsNotNone(ev_id)
        with self.db.get_connection() as c:
            thread_row = c.execute('SELECT status, last_event_at FROM story_threads WHERE thread_key=?', (thread_key,)).fetchone()
            self.assertEqual(thread_row['status'], 'open')
            self.assertEqual(thread_row['last_event_at'], new_date)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM life_events WHERE thread_id=(SELECT id FROM story_threads WHERE thread_key=?)', (thread_key,)).fetchone()[0], 2)

    def test_dormant_selective_abandonment_policy(self):
        # 1. Thread acadêmica protegida por tipo (não abandona aos 30 dias)
        with self.db.get_connection() as c:
            c.execute('''INSERT INTO story_threads(thread_key, thread_type, title, summary, status, importance, started_at, last_event_at, metadata_json)
                         VALUES ('academic:1', 'academic', 'TCC', 'Revisão', 'dormant', 0.3, ?, ?, '{}')''',
                      (self.now.isoformat(), self.now.isoformat()))
            # 2. Thread social com compromisso futuro confirmado / auto_abandonable=False (protegida)
            c.execute('''INSERT INTO story_threads(thread_key, thread_type, title, summary, status, importance, started_at, last_event_at, metadata_json)
                         VALUES ('social:protected', 'social', 'Viagem', 'Plano futuro', 'dormant', 0.2, ?, ?, ?)''',
                      (self.now.isoformat(), self.now.isoformat(), json.dumps({'has_future_commitment': True})))
            # 3. Thread ordinária normal (deve abandonar aos 30 dias)
            c.execute('''INSERT INTO story_threads(thread_key, thread_type, title, summary, status, importance, started_at, last_event_at, metadata_json)
                         VALUES ('ordinary:fade', 'ordinary', 'Bagunça', 'Milo', 'dormant', 0.15, ?, ?, '{}')''',
                      (self.now.isoformat(), self.now.isoformat()))

        # Passam 31 dias
        self.engine.quiet_old_threads(self.now + timedelta(days=31))

        with self.db.get_connection() as c:
            acad_status = c.execute("SELECT status FROM story_threads WHERE thread_key='academic:1'").fetchone()[0]
            social_status = c.execute("SELECT status FROM story_threads WHERE thread_key='social:protected'").fetchone()[0]
            ord_status = c.execute("SELECT status FROM story_threads WHERE thread_key='ordinary:fade'").fetchone()[0]

            self.assertEqual(acad_status, 'dormant')
            self.assertEqual(social_status, 'dormant')
            self.assertEqual(ord_status, 'abandoned')


if __name__=='__main__':
    unittest.main()
