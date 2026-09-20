"""Stage 14 / release 3.6.7 — World Hygiene contracts."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from config import settings
from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from world_hygiene import WorldHygiene, INTEREST_ACTIVE, INTEREST_FADING, INTEREST_DORMANT
from world_repository import WorldBibleRepository
from social_world import SocialWorld, seed_social


class WorldHygieneInterestTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'hygiene.db')
        seed_world_bible(self.db)
        self.hygiene = WorldHygiene(self.db)
        self.now = datetime(2026, 9, 18, 12, 0)
        self.bible = WorldBibleRepository(self.db)

    def _interest(self, value, *, strength=0.7):
        return self.bible.upsert_preference(
            'marina', 'media', value, 'current_interest',
            strength=strength, confidence=0.6, canon_locked=False,
        )

    def test_interest_lifecycle_and_core_never_decays(self):
        recent = self._interest('serie-x')
        fading = self._interest('tema-y')
        dormant = self._interest('moda-z')
        core = self.bible.upsert_preference(
            'marina', 'music', 'pop', 'core_like',
            strength=1.0, confidence=1.0, canon_locked=True)
        with self.db.get_connection() as conn:
            conn.execute(
                'UPDATE character_preferences SET last_seen_at=? WHERE id=?',
                (self.now.isoformat(), recent['id']),
            )
            conn.execute(
                'UPDATE character_preferences SET last_seen_at=? WHERE id=?',
                ((self.now - timedelta(days=20)).isoformat(), fading['id']),
            )
            conn.execute(
                'UPDATE character_preferences SET last_seen_at=? WHERE id=?',
                ((self.now - timedelta(days=50)).isoformat(), dormant['id']),
            )
            conn.execute(
                'UPDATE character_preferences SET last_seen_at=? WHERE id=?',
                ((self.now - timedelta(days=200)).isoformat(), core['id']),
            )

        with self.db.get_connection() as conn:
            rows = {r['value']: dict(r) for r in conn.execute(
                'SELECT * FROM character_preferences').fetchall()}
        self.assertEqual(self.hygiene.interest_status(rows['serie-x'], self.now), INTEREST_ACTIVE)
        self.assertEqual(self.hygiene.interest_status(rows['tema-y'], self.now), INTEREST_FADING)
        self.assertEqual(self.hygiene.interest_status(rows['moda-z'], self.now), INTEREST_DORMANT)
        self.assertIsNone(self.hygiene.interest_status(rows['pop'], self.now))

        stats = self.hygiene.decay_current_interests(self.now)
        self.assertGreaterEqual(stats['faded'], 1)
        self.assertGreaterEqual(stats['dormant'], 1)
        with self.db.get_connection() as conn:
            dormant_row = conn.execute(
                'SELECT active,strength FROM character_preferences WHERE value=?',
                ('moda-z',)).fetchone()
            core_row = conn.execute(
                'SELECT strength,active FROM character_preferences WHERE value=?',
                ('pop',)).fetchone()
        self.assertEqual(dormant_row['active'], 0)
        self.assertEqual(core_row['active'], 1)
        self.assertEqual(core_row['strength'], 1.0)

        social = SocialWorld(self.db)
        social.reinforce_preference(
            'ev-reactivate', 'media', 'moda-z',
            occurred_at=self.now.isoformat(), preference_type='current_interest')
        with self.db.get_connection() as conn:
            revived = dict(conn.execute(
                'SELECT * FROM character_preferences WHERE value=?', ('moda-z',)).fetchone())
        self.assertEqual(revived['active'], 1)
        self.assertEqual(self.hygiene.interest_status(revived, self.now), INTEREST_ACTIVE)


class WorldHygienePromotionDedupCompactTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'hygiene2.db')
        seed_world_bible(self.db)
        seed_social(self.db)
        self.hygiene = WorldHygiene(self.db)
        self.social = SocialWorld(self.db)
        self.now = datetime(2026, 9, 18, 12, 0)

    def test_one_mention_not_promotable_repeated_is(self):
        self.social.discover_person('guest', 'Convidado', 'Botafogo')
        self.social.record('once', character_key='guest', occurred_at='2026-09-01T10:00:00',
                           meaningful=True, valence=1)
        with patch.object(settings, 'WORLD_DISCOVERY_PROMOTION_THRESHOLD', 3):
            first = self.hygiene.review_promotions(self.now)
        self.assertFalse(any(p['canonical_key'] == 'guest' for p in first['people']))
        for day in range(2, 5):
            self.social.record(f'd{day}', character_key='guest',
                               occurred_at=f'2026-09-{day:02d}T10:00:00',
                               meaningful=True, valence=1)
        with patch.object(settings, 'WORLD_DISCOVERY_PROMOTION_THRESHOLD', 3):
            second = self.hygiene.review_promotions(self.now)
        self.assertTrue(any(p['canonical_key'] == 'guest' and p['status'] == 'PROMOTABLE'
                            for p in second['people']))
        # Canonical professor never appears as discovered candidate.
        self.assertFalse(any(p['canonical_key'] == 'helena_prado' for p in second['people']))

    def test_ddgs_discovered_place_needs_repeated_days(self):
        self.social.discover_place('cafe_x', 'Café X', 'Botafogo',
                                   source_url='https://example.com', observed_at='2026-09-01')
        self.social.record('p1', place_key='cafe_x', occurred_at='2026-09-01T10:00:00', valence=1)
        with patch.object(settings, 'WORLD_PREFERENCE_PROMOTION_THRESHOLD', 4):
            first = self.hygiene.review_promotions(self.now)
        self.assertFalse(any(p['canonical_key'] == 'cafe_x' for p in first['places']))
        for day in range(2, 6):
            self.social.record(f'p{day}', place_key='cafe_x',
                               occurred_at=f'2026-09-{day:02d}T10:00:00', valence=1)
        with patch.object(settings, 'WORLD_PREFERENCE_PROMOTION_THRESHOLD', 4):
            second = self.hygiene.review_promotions(self.now)
        self.assertTrue(any(p['canonical_key'] == 'cafe_x' for p in second['places']))
        with self.db.get_connection() as conn:
            rules = json.loads(conn.execute(
                "SELECT usage_rules_json FROM world_places WHERE canonical_key='cafe_x'"
            ).fetchone()[0])
        self.assertEqual(rules['promotion_status'], 'PROMOTABLE')

    def test_exact_duplicate_events_marked_similar_stay_separate(self):
        stamp = self.now.isoformat()
        with self.db.get_connection() as conn:
            for key in ('cast-a', 'cast-a-dup'):
                conn.execute(
                    """INSERT INTO life_events(
                         event_key,event_at,event_type,title,summary,source_type,
                         autonomy_level,importance,created_at)
                       VALUES (?,?,?,?,?,'simulated',1,0.2,?)""",
                    (key, stamp, 'casting', 'Casting boutique', 'mesmo fato', stamp),
                )
            conn.execute(
                """INSERT INTO life_events(
                     event_key,event_at,event_type,title,summary,source_type,
                     autonomy_level,importance,created_at)
                   VALUES (?,?,?,?,?,'simulated',1,0.2,?)""",
                ('cast-b', stamp, 'casting', 'Casting outra agencia', 'fato distinto', stamp),
            )
        result = self.hygiene.dedup_life_events(self.now)
        self.assertEqual(result['marked_duplicates'], 1)
        with self.db.get_connection() as conn:
            rows = list(conn.execute(
                "SELECT event_key,resolved,metadata_json FROM life_events WHERE title LIKE 'Casting%'"
            ).fetchall())
        dup = next(r for r in rows if r['event_key'] == 'cast-a-dup')
        other = next(r for r in rows if r['event_key'] == 'cast-b')
        self.assertEqual(dup['resolved'], 1)
        self.assertIn('duplicate_of', dup['metadata_json'])
        self.assertEqual(other['resolved'], 0)

    def test_compaction_archives_old_resolved_and_is_idempotent(self):
        old = (self.now - timedelta(days=120)).isoformat()
        with self.db.get_connection() as conn:
            event_id = conn.execute(
                """INSERT INTO life_events(
                     event_key,event_at,event_type,title,summary,source_type,
                     autonomy_level,importance,resolved,created_at)
                   VALUES ('old-banal',?, 'ordinary','Bagunça','Milo bagunçou','simulated',1,0.1,1,?)""",
                (old, old),
            ).lastrowid
            protected = conn.execute(
                """INSERT INTO life_events(
                     event_key,event_at,event_type,title,summary,source_type,
                     autonomy_level,importance,resolved,created_at)
                   VALUES ('old-important',?, 'ordinary','Projeto','Entrega','simulated',1,0.9,1,?)""",
                (old, old),
            ).lastrowid
        first = self.hygiene.compact_event_history(self.now)
        second = self.hygiene.compact_event_history(self.now)
        self.assertEqual(first['compacted'], 1)
        self.assertEqual(second['compacted'], 0)
        with self.db.get_connection() as conn:
            self.assertIsNone(conn.execute(
                'SELECT 1 FROM life_events WHERE id=?', (event_id,)).fetchone())
            self.assertIsNotNone(conn.execute(
                'SELECT 1 FROM life_events_archive WHERE original_event_id=?',
                (event_id,)).fetchone())
            self.assertIsNotNone(conn.execute(
                'SELECT 1 FROM life_events WHERE id=?', (protected,)).fetchone())

    def test_debug_snapshot_has_no_chain_of_thought_keys(self):
        snap = self.hygiene.debug_snapshot(self.now)
        text = self.hygiene.format_debug_text(snap)
        for banned in ('chain-of-thought', 'thinking', 'scratchpad', 'PRIVATE_SELF detail'):
            self.assertNotIn(banned, text)
        self.assertIn('Living World debug', text)
        self.assertIn('threads', snap)
        self.assertIn('current_interests', snap)


class WorldHygieneThreadReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'threads.db')
        seed_world_bible(self.db)
        self.hygiene = WorldHygiene(self.db)
        self.now = datetime(2026, 9, 18, 12, 0)

    def test_review_uses_existing_quiet_policy(self):
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO story_threads(
                     thread_key,thread_type,title,summary,status,importance,started_at,last_event_at)
                   VALUES ('old:1','ordinary','Bagunça','Milo','open',0.2,?,?)""",
                ((self.now - timedelta(days=20)).isoformat(),
                 (self.now - timedelta(days=20)).isoformat()),
            )
        stats = self.hygiene.review_thread_dormancy(self.now)
        self.assertGreaterEqual(stats['newly_dormant'], 1)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute(
                "SELECT status FROM story_threads WHERE thread_key='old:1'"
            ).fetchone()[0], 'dormant')


class ConversationalNaturalnessConfirmTests(unittest.TestCase):
    """3.6.7 only confirms Response Rhythm; it must not grow a second planner."""

    def test_optimize_for_next_turn_and_default_bubble_budget(self):
        from response_rhythm import apply_policy, select_policy
        policy = select_policy('oi tudo bem')
        self.assertEqual(policy.mode, 'casual_short')
        self.assertLessEqual(policy.max_bubbles, settings.RESPONSE_DEFAULT_MAX_BUBBLES)
        prompt = apply_policy('Identidade.', policy)
        self.assertIn('Optimize for the next conversational turn', prompt)
        self.assertIn('usually finish without a question', prompt)
        # v3.7.0 rhythm refactor slimmed the guidance block; the two removed
        # sentences ('Do not restate obvious…' and 'World context informs…')
        # are subsumed by the current 'Skip stock reassurance…' guidance.
        self.assertEqual(select_policy('oi', plan={'followup_question': 'none'}).followup_question,
                         'not_required')


if __name__ == '__main__':
    unittest.main()
