"""Living World hygiene for v3.6.7 — decay, promotion review, dedup, compaction, debug.

Does not invent events, rewrite canon, or create a second Story/Memory/Calendar
authority. SessionReflector and MemoryHygiene remain the conversational reflection
path; this module only maintains Living World durability.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import Optional

from config import settings
from db import DatabaseManager


logger = logging.getLogger(__name__)

INTEREST_ACTIVE = 'ACTIVE'
INTEREST_FADING = 'FADING'
INTEREST_DORMANT = 'DORMANT'


class WorldHygiene:
    def __init__(self, db: DatabaseManager):
        self.db = db

    # --- Current interest decay -------------------------------------------------

    def interest_status(self, row: dict, now: datetime) -> Optional[str]:
        if row.get('preference_type') != 'current_interest' or row.get('canon_locked'):
            return None
        last = datetime.fromisoformat(row['last_seen_at'])
        age = now - last
        fading_after = timedelta(days=int(getattr(settings, 'INTEREST_FADING_DAYS', 14)))
        dormant_after = timedelta(days=int(getattr(settings, 'INTEREST_DORMANT_DAYS', 45)))
        if age < fading_after:
            return INTEREST_ACTIVE
        if age < dormant_after:
            return INTEREST_FADING
        return INTEREST_DORMANT

    def decay_current_interests(self, now: datetime) -> dict:
        """Weaken temporary interests; never touch core_like / canon_locked rows."""
        fading_step = float(getattr(settings, 'INTEREST_FADING_STRENGTH_STEP', 0.08))
        dormant_floor = float(getattr(settings, 'INTEREST_DORMANT_STRENGTH', 0.15))
        faded = dormant = 0
        with self.db.transaction():
            with self.db.get_connection() as conn:
                rows = conn.execute(
                    """SELECT * FROM character_preferences
                       WHERE character_key='marina' AND preference_type='current_interest'
                         AND canon_locked=0 AND active=1"""
                ).fetchall()
                for row in rows:
                    status = self.interest_status(dict(row), now)
                    if status == INTEREST_FADING:
                        new_strength = max(dormant_floor, float(row['strength']) - fading_step)
                        if new_strength < float(row['strength']):
                            conn.execute(
                                'UPDATE character_preferences SET strength=? WHERE id=?',
                                (round(new_strength, 4), row['id']),
                            )
                            faded += 1
                            self._log(conn, now, 'INTEREST_DECAY', 'preference',
                                      str(row['id']), 'fading',
                                      {'value': row['value'], 'strength': new_strength})
                    elif status == INTEREST_DORMANT:
                        # Keep the autobiographical row; stop competing as current interest.
                        conn.execute(
                            """UPDATE character_preferences
                               SET strength=?, active=0 WHERE id=?""",
                            (dormant_floor, row['id']),
                        )
                        dormant += 1
                        self._log(conn, now, 'INTEREST_DECAY', 'preference',
                                  str(row['id']), 'dormant',
                                  {'value': row['value']})
        return {'faded': faded, 'dormant': dormant}

    def reactivate_interest_on_reinforce(self, preference_id: int, now: datetime) -> None:
        """Explicit reinforcement may revive a dormant current interest."""
        with self.db.get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM character_preferences WHERE id=?', (preference_id,)
            ).fetchone()
            if not row or row['preference_type'] != 'current_interest' or row['canon_locked']:
                return
            conn.execute(
                """UPDATE character_preferences
                   SET active=1, last_seen_at=?, strength=?
                   WHERE id=?""",
                (now.isoformat(), max(float(row['strength']), 0.45), preference_id),
            )

    # --- Thread dormancy review (wrap existing policy) --------------------------

    def review_thread_dormancy(self, now: datetime) -> dict:
        from story_engine import StoryEngine

        before = self._thread_counts()
        StoryEngine(self.db).quiet_old_threads(now)
        after = self._thread_counts()
        return {
            'open': after['open'],
            'dormant': after['dormant'],
            'abandoned': after['abandoned'],
            'newly_dormant': max(0, after['dormant'] - before['dormant']),
            'newly_abandoned': max(0, after['abandoned'] - before['abandoned']),
        }

    def _thread_counts(self) -> dict:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                'SELECT status, COUNT(*) AS n FROM story_threads GROUP BY status'
            ).fetchall()
        counts = {'open': 0, 'dormant': 0, 'abandoned': 0, 'resolved': 0}
        for row in rows:
            counts[row['status']] = row['n']
        return counts

    # --- Promotion review (list / mark, no ambiguous auto-promote) --------------

    def review_promotions(self, now: datetime) -> dict:
        """Mark PROMOTABLE candidates from reinforcement counts; do not invent NPCs."""
        person_threshold = int(getattr(settings, 'WORLD_DISCOVERY_PROMOTION_THRESHOLD', 3))
        place_threshold = int(getattr(settings, 'WORLD_PREFERENCE_PROMOTION_THRESHOLD', 4))
        people, places = [], []
        with self.db.transaction():
            with self.db.get_connection() as conn:
                for row in conn.execute(
                    """SELECT w.canonical_key, w.display_name, w.character_type, w.canon_locked,
                              COUNT(DISTINCT substr(e.occurred_at,1,10)) AS days
                       FROM world_characters w
                       LEFT JOIN social_evidence e ON e.character_key=w.canonical_key
                            AND e.meaningful=1 AND e.valence>0
                       WHERE w.canon_locked=0 AND w.active=1
                         AND w.character_type IN ('ephemeral','secondary')
                       GROUP BY w.canonical_key
                       HAVING days >= ?""",
                    (person_threshold,),
                ).fetchall():
                    people.append({
                        'canonical_key': row['canonical_key'],
                        'display_name': row['display_name'],
                        'character_type': row['character_type'],
                        'reinforcement_days': row['days'],
                        'status': 'PROMOTABLE',
                    })
                    self._log(conn, now, 'NPC_PROMOTION', 'character', row['canonical_key'],
                              'promotable_review',
                              {'days': row['days'], 'auto_promoted': False})

                for row in conn.execute(
                    """SELECT p.canonical_key, p.name, p.familiarity, p.canon_locked,
                              p.usage_rules_json,
                              COUNT(DISTINCT substr(e.occurred_at,1,10)) AS days
                       FROM world_places p
                       LEFT JOIN social_evidence e ON e.place_key=p.canonical_key
                       WHERE p.canon_locked=0 AND p.active=1 AND p.familiarity='discovered'
                       GROUP BY p.canonical_key
                       HAVING days >= ?""",
                    (place_threshold,),
                ).fetchall():
                    rules = json.loads(row['usage_rules_json'] or '{}')
                    if rules.get('promotion_status') != 'PROMOTABLE':
                        rules['promotion_status'] = 'PROMOTABLE'
                        rules['promotable_at'] = now.isoformat()
                        conn.execute(
                            'UPDATE world_places SET usage_rules_json=? WHERE canonical_key=?',
                            (json.dumps(rules, ensure_ascii=False, sort_keys=True),
                             row['canonical_key']),
                        )
                    places.append({
                        'canonical_key': row['canonical_key'],
                        'name': row['name'],
                        'reinforcement_days': row['days'],
                        'status': 'PROMOTABLE',
                    })
                    self._log(conn, now, 'PLACE_PROMOTION', 'place', row['canonical_key'],
                              'promotable_review',
                              {'days': row['days'], 'auto_promoted': False})
        return {'people': people, 'places': places}

    # --- Event dedup ------------------------------------------------------------

    def dedup_life_events(self, now: datetime) -> dict:
        """Conservative exact duplicates only — never merge similar-but-distinct events."""
        removed = 0
        with self.db.transaction():
            with self.db.get_connection() as conn:
                dupes = conn.execute(
                    """SELECT source_type, event_type, title, event_at, MIN(id) AS keep_id,
                              GROUP_CONCAT(id) AS ids, COUNT(*) AS n
                       FROM life_events
                       GROUP BY source_type, event_type, title, event_at
                       HAVING n > 1"""
                ).fetchall()
                for group in dupes:
                    ids = [int(x) for x in group['ids'].split(',')]
                    keep = group['keep_id']
                    for event_id in ids:
                        if event_id == keep:
                            continue
                        if self._event_protected(conn, event_id):
                            continue
                        # Soft-mark rather than hard-delete so provenance survives.
                        meta = conn.execute(
                            'SELECT metadata_json FROM life_events WHERE id=?', (event_id,)
                        ).fetchone()
                        blob = json.loads(meta['metadata_json'] or '{}')
                        if blob.get('duplicate_of') == keep:
                            continue
                        blob['duplicate_of'] = keep
                        blob['deduped_at'] = now.isoformat()
                        conn.execute(
                            """UPDATE life_events
                               SET resolved=1, metadata_json=?, share_worthy=0
                               WHERE id=?""",
                            (json.dumps(blob, ensure_ascii=False, sort_keys=True), event_id),
                        )
                        removed += 1
                        self._log(conn, now, 'EVENT_DEDUP', 'event', str(event_id),
                                  'exact_duplicate', {'keep_id': keep})
        return {'marked_duplicates': removed}

    # --- Event history compaction -----------------------------------------------

    def compact_event_history(self, now: datetime) -> dict:
        """Archive old low-value resolved events; never destroy protected provenance."""
        older_than = int(getattr(settings, 'EVENT_COMPACTION_DAYS', 90))
        cutoff = (now - timedelta(days=older_than)).isoformat()
        max_importance = float(getattr(settings, 'EVENT_COMPACTION_MAX_IMPORTANCE', 0.35))
        compacted = 0
        with self.db.transaction():
            with self.db.get_connection() as conn:
                candidates = conn.execute(
                    """SELECT e.* FROM life_events e
                       WHERE e.resolved=1 AND e.importance<=?
                         AND e.event_at<?
                         AND COALESCE(json_extract(e.metadata_json,'$.duplicate_of'),'')=''
                         AND NOT EXISTS (
                             SELECT 1 FROM story_threads t
                             WHERE t.id=e.thread_id AND t.status IN ('open','dormant')
                         )
                         AND NOT EXISTS (
                             SELECT 1 FROM life_events c
                             WHERE c.consequence_of_event_id=e.id
                         )
                         AND NOT EXISTS (
                             SELECT 1 FROM knowledge_items k
                             WHERE k.subject_type='event' AND k.subject_id=e.id
                               AND k.revoked_at IS NULL
                         )
                         AND NOT EXISTS (
                             SELECT 1 FROM knowledge_shares s
                             WHERE s.subject_type='event' AND s.subject_id=e.id
                         )
                         AND NOT EXISTS (
                             SELECT 1 FROM eventos_pendentes p
                             WHERE p.story_thread_id=e.thread_id AND p.status='pending'
                               AND p.confirmed=1 AND p.event_at>?
                         )""",
                    (max_importance, cutoff, now.isoformat()),
                ).fetchall()
                for row in candidates:
                    if self._event_protected(conn, row['id']):
                        continue
                    existing = conn.execute(
                        'SELECT 1 FROM life_events_archive WHERE original_event_id=?',
                        (row['id'],),
                    ).fetchone()
                    if existing:
                        conn.execute('DELETE FROM life_events WHERE id=?', (row['id'],))
                        compacted += 1
                        continue
                    conn.execute(
                        """INSERT INTO life_events_archive(
                             original_event_id,event_key,event_at,end_at,event_type,title,summary,
                             source_type,autonomy_level,importance,emotional_valence,location_place_id,
                             participants_json,thread_id,consequence_of_event_id,share_worthy,resolved,
                             metadata_json,created_at,compacted_at,compact_reason)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row['id'], row['event_key'], row['event_at'], row['end_at'],
                         row['event_type'], row['title'], row['summary'], row['source_type'],
                         row['autonomy_level'], row['importance'], row['emotional_valence'],
                         row['location_place_id'], row['participants_json'], row['thread_id'],
                         row['consequence_of_event_id'], row['share_worthy'], row['resolved'],
                         row['metadata_json'], row['created_at'], now.isoformat(),
                         'old_resolved_low_value'),
                    )
                    conn.execute('DELETE FROM life_events WHERE id=?', (row['id'],))
                    compacted += 1
                    self._log(conn, now, 'EVENT_COMPACTION', 'event', str(row['id']),
                              'archived_low_value', {'event_key': row['event_key']})
        return {'compacted': compacted}

    def _event_protected(self, conn, event_id: int) -> bool:
        row = conn.execute('SELECT * FROM life_events WHERE id=?', (event_id,)).fetchone()
        if not row:
            return True
        if row['source_type'] == 'canonical' or float(row['importance']) >= 0.7:
            return True
        if conn.execute(
            """SELECT 1 FROM knowledge_items
               WHERE subject_type='event' AND subject_id=? AND revoked_at IS NULL""",
            (event_id,),
        ).fetchone():
            return True
        if conn.execute(
            'SELECT 1 FROM life_events WHERE consequence_of_event_id=?', (event_id,)
        ).fetchone():
            return True
        if row['thread_id'] and conn.execute(
            """SELECT 1 FROM story_threads
               WHERE id=? AND (status IN ('open','dormant')
                 OR COALESCE(json_extract(metadata_json,'$.protected'),0)=1
                 OR thread_type IN ('academic','professional'))""",
            (row['thread_id'],),
        ).fetchone():
            return True
        return False

    # --- Debug / dashboard ------------------------------------------------------

    def debug_snapshot(self, now: datetime) -> dict:
        """Safe Living World overview — no chain-of-thought, no confidential bodies."""
        from calendar_world import CalendarWorld, local_time
        from world_repository import WorldStateRepository

        now = local_time(now) if getattr(settings, 'CALENDAR_CONTINUITY_ENABLED', False) else now
        state = WorldStateRepository(self.db).latest()
        with self.db.get_connection() as conn:
            threads = [dict(r) for r in conn.execute(
                """SELECT id,thread_key,thread_type,status,importance,last_event_at,
                          COALESCE(json_extract(metadata_json,'$.protected'),0) AS protected,
                          COALESCE(json_extract(metadata_json,'$.has_future_commitment'),0)
                            AS has_future_commitment
                   FROM story_threads
                   ORDER BY last_event_at DESC LIMIT 12"""
            ).fetchall()]
            interests = []
            for row in conn.execute(
                """SELECT id,category,value,preference_type,strength,last_seen_at,active,canon_locked
                   FROM character_preferences
                   WHERE character_key='marina' AND preference_type='current_interest'
                   ORDER BY last_seen_at DESC LIMIT 10"""
            ).fetchall():
                item = dict(row)
                item['lifecycle'] = self.interest_status(item, now) or 'N/A'
                interests.append(item)
            privacy = conn.execute(
                """SELECT privacy_level, COUNT(*) AS n FROM knowledge_items
                   WHERE revoked_at IS NULL GROUP BY privacy_level"""
            ).fetchall()
            cache = conn.execute(
                """SELECT kind, COUNT(*) AS n FROM real_context_cache
                   WHERE expires_at>? GROUP BY kind""",
                (now.isoformat(),),
            ).fetchall() if self._table_exists(conn, 'real_context_cache') else []
            hygiene = conn.execute(
                """SELECT action, COUNT(*) AS n FROM world_hygiene_log
                   GROUP BY action"""
            ).fetchall() if self._table_exists(conn, 'world_hygiene_log') else []
            archived = conn.execute(
                'SELECT COUNT(*) AS n FROM life_events_archive'
            ).fetchone()['n'] if self._table_exists(conn, 'life_events_archive') else 0

        upcoming = None
        if getattr(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            upcoming = CalendarWorld(self.db).next(
                now, include_academic=getattr(settings, 'ACADEMIC_LIFE_ENABLED', False))
            if upcoming:
                upcoming = {
                    'activity': upcoming.get('activity'),
                    'start_at': upcoming.get('start_at'),
                    'place_key': upcoming.get('place_key'),
                }

        source = json.loads(state['source_json'] or '{}') if state else {}
        return {
            'observed_at': now.isoformat(timespec='minutes'),
            'world_state': {
                'id': state['id'] if state else None,
                'activity': state['activity'] if state else None,
                'region': state['location_region'] if state else None,
                'reason': source.get('reason'),
            } if state else None,
            'threads': [
                {k: t[k] for k in (
                    'id', 'thread_key', 'thread_type', 'status', 'importance',
                    'last_event_at', 'protected', 'has_future_commitment')}
                for t in threads
            ],
            'upcoming_event': upcoming,
            'current_interests': [
                {k: i[k] for k in (
                    'id', 'category', 'value', 'strength', 'lifecycle', 'active')}
                for i in interests
            ],
            'privacy_counts': {r['privacy_level']: r['n'] for r in privacy},
            'provider_cache': {r['kind']: r['n'] for r in cache},
            'hygiene_counters': {r['action']: r['n'] for r in hygiene},
            'archived_events': archived,
            'narrative_budget': {
                'cadence_threshold': getattr(settings, 'STORY_EVENT_CADENCE_THRESHOLD', 0.60),
                'dormant_days': getattr(settings, 'STORY_THREAD_DORMANT_DAYS', 7),
            },
        }

    def format_debug_text(self, snap: dict) -> str:
        lines = [
            f"Living World debug · {snap['observed_at']}",
            f"State: {snap.get('world_state')}",
            f"Upcoming: {snap.get('upcoming_event')}",
            f"Threads ({len(snap.get('threads') or [])}):",
        ]
        for t in snap.get('threads') or []:
            lines.append(
                f"  - {t['thread_key']} [{t['status']}] type={t['thread_type']} "
                f"prot={t['protected']} future={t['has_future_commitment']}"
            )
        lines.append('Interests:')
        for i in snap.get('current_interests') or []:
            lines.append(
                f"  - {i['value']} ({i['lifecycle']}) strength={i['strength']} active={i['active']}"
            )
        lines.append(f"Privacy counts: {snap.get('privacy_counts')}")
        lines.append(f"Hygiene: {snap.get('hygiene_counters')} archived={snap.get('archived_events')}")
        lines.append(f"Budget: {snap.get('narrative_budget')}")
        return '\n'.join(lines)

    # --- Cycle ------------------------------------------------------------------

    def run_cycle(self, now: Optional[datetime] = None) -> dict:
        if not getattr(settings, 'WORLD_HYGIENE_ENABLED', False):
            return {'status': 'disabled', 'success': False}
        now = now or datetime.now()
        if getattr(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            from calendar_world import local_time
            now = local_time(now)
        promos = self.review_promotions(now)
        result = {
            'timestamp': now.isoformat(),
            'interest_decay': self.decay_current_interests(now),
            'thread_dormancy': self.review_thread_dormancy(now),
            'promotions': {'people': len(promos['people']), 'places': len(promos['places'])},
            'dedup': self.dedup_life_events(now),
            'compaction': self.compact_event_history(now),
            'status': 'completed',
            'success': True,
        }
        logger.info('WORLD_HYGIENE_CYCLE %s', json.dumps(result, ensure_ascii=False, default=str))
        return result

    def _log(self, conn, now, action, subject_type, subject_key, reason_code, detail):
        if not self._table_exists(conn, 'world_hygiene_log'):
            return
        conn.execute(
            """INSERT INTO world_hygiene_log(ran_at,action,subject_type,subject_key,reason_code,detail_json)
               VALUES (?,?,?,?,?,?)""",
            (now.isoformat(), action, subject_type, subject_key, reason_code,
             json.dumps(detail, ensure_ascii=False, sort_keys=True)),
        )

    @staticmethod
    def _table_exists(conn, name: str) -> bool:
        return bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone())
