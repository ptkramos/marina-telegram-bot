"""Single calendar view over dated events and academic weekly patterns (v3.6.4)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from typing import Mapping
from zoneinfo import ZoneInfo

from db import DatabaseManager


LOCAL_ZONE = ZoneInfo('America/Sao_Paulo')
ACADEMIC_EVENTS = frozenset({
    'academic_exam', 'academic_presentation', 'academic_deadline',
    'academic_group_work', 'academic_field_visit', 'academic_workshop',
    'academic_class_cancelled', 'academic_class_rescheduled',
})
CONFLICT_RESOLUTIONS = frozenset({'rescheduled', 'approved_absence', 'miss_class'})


def local_time(value: datetime) -> datetime:
    """Existing SQLite dates are local-naive; convert aware input explicitly."""
    if not isinstance(value, datetime):
        raise TypeError('Expected datetime')
    return value.astimezone(LOCAL_ZONE).replace(tzinfo=None) if value.tzinfo else value


class RealContextCache:
    """Provenance and TTL gate. No weather or holiday is invented on cache miss."""
    def __init__(self, db: DatabaseManager):
        self.db = db

    def put(self, context_key: str, kind: str, payload: Mapping, *, source_name: str,
            observed_at: datetime, expires_at: datetime) -> None:
        observed_at, expires_at = local_time(observed_at), local_time(expires_at)
        if kind not in ('weather', 'holiday', 'holiday_year', 'place_fact', 'place_negative', 'media') or not context_key or not source_name:
            raise ValueError('Context needs a key, source and reviewed kind')
        if len(source_name) > 80 or any(ord(ch) < 32 for ch in source_name):
            raise ValueError('Invalid context source label')
        if observed_at >= expires_at:
            raise ValueError('Context expiry must follow observation')
        value = dict(payload)
        if kind == 'weather':
            if set(value) - {'heavy_rain', 'temperature_c', 'condition'}:
                raise ValueError('Unexpected weather field')
            if 'heavy_rain' in value and not isinstance(value['heavy_rain'], bool):
                raise ValueError('heavy_rain must be observed boolean')
            if 'temperature_c' in value and (not isinstance(value['temperature_c'], (int, float))
                                             or not -30 <= value['temperature_c'] <= 60):
                raise ValueError('Invalid temperature')
            if 'condition' in value and value['condition'] not in ('clear', 'cloudy', 'rain', 'storm', 'unknown'):
                raise ValueError('Unknown weather condition')
        elif kind == 'holiday':
            if set(value) - {'date', 'name', 'scope', 'holidays'} or not value.get('date'):
                raise ValueError('Unexpected holiday field')
            try:
                date.fromisoformat(value['date'])
            except (TypeError, ValueError) as exc:
                raise ValueError('Holiday date must be ISO') from exc
            if (not isinstance(value.get('name'), str) or len(value['name']) > 100
                    or any(ord(ch) < 32 for ch in value['name'])):
                raise ValueError('Invalid holiday name')
            if value.get('scope') not in ('national', 'state', 'municipal', 'campus', 'optional'):
                raise ValueError('Holiday scope must be explicit')
            if 'holidays' in value and (not isinstance(value['holidays'], list)
                    or any(not isinstance(item, dict) or set(item) != {'name', 'scope'}
                           for item in value['holidays'])):
                raise ValueError('Invalid holiday list')
        elif kind == 'holiday_year':
            if (set(value) != {'year', 'coverage', 'holidays'} or not isinstance(value['year'], int)
                    or value['coverage'] not in ('RIO_ALL', 'NATIONAL_ONLY')
                    or not isinstance(value['holidays'], list)):
                raise ValueError('Invalid annual holiday cache')
        elif kind in ('place_fact', 'place_negative'):
            if (set(value) - {'entity_key', 'entity_name', 'fact_type', 'value', 'source_url', 'source_type',
                              'confidence', 'status', 'for_date'} or not value.get('entity_key')
                    or value.get('status') not in ('CONFIRMED', 'UNKNOWN')):
                raise ValueError('Invalid place context')
        elif kind == 'media':
            if (set(value) - {'titles'} or not isinstance(value.get('titles'), list)
                    or not all(isinstance(t, str) and 1 <= len(t) <= 80 for t in value['titles'])):
                raise ValueError('Invalid media cache payload')
        with self.db.get_connection() as conn:
            conn.execute('''INSERT INTO real_context_cache
                (context_key,kind,payload_json,source_name,observed_at,expires_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(context_key) DO UPDATE SET
                kind=excluded.kind,payload_json=excluded.payload_json,
                source_name=excluded.source_name,observed_at=excluded.observed_at,
                expires_at=excluded.expires_at''',
                (context_key, kind, json.dumps(value, ensure_ascii=False, sort_keys=True),
                 source_name, observed_at.isoformat(), expires_at.isoformat()))

    def get(self, context_key: str, *, now: datetime) -> dict | None:
        now = local_time(now)
        with self.db.get_connection() as conn:
            row = conn.execute('''SELECT * FROM real_context_cache
                WHERE context_key=? AND observed_at<=? AND expires_at>?''',
                (context_key, now.isoformat(), now.isoformat())).fetchone()
        if not row:
            return None
        result = dict(row)
        result['payload'] = json.loads(result.pop('payload_json'))
        return result


class CalendarWorld:
    """Dated commitments remain in eventos_pendentes; classes are a projection."""
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.context = RealContextCache(db)

    def create_commitment(self, *, source_key: str, event_type: str, description: str,
                          start_at: datetime, end_at: datetime, owner: str = 'marina',
                          location_key: str | None = None, story_thread_id: int | None = None,
                          metadata: Mapping | None = None,
                          conflict_resolution: str | None = None) -> int:
        start_at, end_at = local_time(start_at), local_time(end_at)
        if not source_key or not description or start_at >= end_at:
            raise ValueError('A confirmed commitment needs key, text and valid interval')
        if owner != 'marina':
            raise ValueError('This projection only creates Marina commitments')
        if conflict_resolution and conflict_resolution not in CONFLICT_RESOLUTIONS:
            raise ValueError('Unknown conflict resolution')
        if event_type not in ACADEMIC_EVENTS and not conflict_resolution:
            from academic_life import AcademicLife

            if AcademicLife(self.db).conflicting_blocks(start_at, end_at):
                raise ValueError('Confirmed commitment conflicts with class; resolve explicitly')
        data = dict(metadata or {})
        if conflict_resolution:
            data['academic_conflict_resolution'] = conflict_resolution
        with self.db.transaction():
            with self.db.get_connection() as conn:
                existing = conn.execute('SELECT * FROM eventos_pendentes WHERE source_key=?',
                                        (source_key,)).fetchone()
                if existing:
                    if (existing['event_type'], existing['description'], existing['event_at'],
                        existing['end_at'], existing['owner_character_key'], existing['location_key'],
                        existing['story_thread_id'], json.loads(existing['metadata_json'] or '{}')) != (
                            event_type, description, start_at.isoformat(), end_at.isoformat(),
                            owner, location_key, story_thread_id, data):
                        raise ValueError('Conflicting calendar replay')
                    return existing['id']
                if story_thread_id and not conn.execute('SELECT 1 FROM story_threads WHERE id=?',
                                                        (story_thread_id,)).fetchone():
                    raise ValueError('Linked story thread does not exist')
                if event_type != 'academic_class_cancelled' and conn.execute('''
                    SELECT 1 FROM eventos_pendentes WHERE owner_character_key='marina'
                      AND status='pending' AND confirmed=1
                      AND event_type!='academic_class_cancelled'
                      AND event_at<? AND COALESCE(end_at,event_at)>? LIMIT 1''',
                    (end_at.isoformat(), start_at.isoformat())).fetchone():
                    raise ValueError('Calendar already has an overlapping confirmed event')
                return conn.execute('''INSERT INTO eventos_pendentes
                    (event_type,description,event_at,end_at,status,importance,created_at,
                     owner_character_key,location_key,source_key,story_thread_id,confirmed,metadata_json)
                    VALUES (?,?,?,?,'pending',0.5,?,?,?,?,?,1,?)''',
                    (event_type, description, start_at.isoformat(), end_at.isoformat(),
                     datetime.now(LOCAL_ZONE).replace(tzinfo=None).isoformat(), owner,
                     location_key, source_key, story_thread_id,
                     json.dumps(data, ensure_ascii=False, sort_keys=True))).lastrowid

    def _dated(self, start: datetime, end: datetime) -> list[dict]:
        with self.db.get_connection() as conn:
            return [dict(row) for row in conn.execute('''SELECT * FROM eventos_pendentes
                WHERE owner_character_key IN ('marina', 'shared') AND status='pending' AND confirmed=1
                  AND event_at<? AND COALESCE(end_at,event_at)>?
                ORDER BY event_at,id''', (end.isoformat(), start.isoformat()))]

    def current(self, now: datetime, *, include_academic: bool = True) -> dict | None:
        now = local_time(now)
        dated = [row for row in self._dated(now, now + timedelta(seconds=1))
                 if row['event_type'] != 'academic_class_cancelled']
        if dated:
            # Confirmed exceptional events override a recurring academic pattern.
            row = dated[0]
            # Calendar descriptions can be private. WorldState receives only a
            # generic activity; disclosure uses KnowledgePrivacy separately.
            if row['event_type'] in ACADEMIC_EVENTS:
                activity = 'em um compromisso da faculdade'
            elif row['event_type'] in ('social', 'lazer', 'encontro', 'trabalho') and row.get('description'):
                activity = row['description']
            else:
                activity = 'em um compromisso'
            place_key = row['location_key'] or 'marina_apartment'
            return {'activity': activity, 'place_key': place_key,
                    'start_at': row['event_at'], 'end_at': row['end_at'],
                    'calendar_event_id': row['id'], 'source_key': row['source_key']}
        if not include_academic:
            return None
        from academic_life import AcademicLife

        block = AcademicLife(self.db).current_block(now)
        if not block:
            return None
        return {'activity': f"na faculdade ({block['display_name']})",
                'place_key': block['location_key'], 'start_at': block['start_at'],
                'end_at': block['end_at'], 'academic_block_id': block['id'],
                'source_key': f"academic:{block['id']}:{now.date().isoformat()}"}

    def next(self, now: datetime, *, horizon_days: int = 14,
             include_academic: bool = True) -> dict | None:
        now = local_time(now)
        end = now + timedelta(days=horizon_days)
        dated = [row for row in self._dated(now, end)
                 if row['event_at'] > now.isoformat()
                 and row['event_type'] != 'academic_class_cancelled']
        blocks = []
        if include_academic:
            from academic_life import AcademicLife

            blocks = AcademicLife(self.db).upcoming_blocks(now, horizon_days=horizon_days)
        options = [(row['event_at'], {'activity':
                                     ('compromisso da faculdade' if row['event_type'] in ACADEMIC_EVENTS
                                      else 'compromisso'),
                                     'start_at': row['event_at'], 'end_at': row['end_at'],
                                     'place_key': row['location_key'], 'calendar_event_id': row['id']})
                   for row in dated]
        options.extend((block['start_at'], {'activity': block['display_name'],
                                            'start_at': block['start_at'],
                                            'end_at': block['end_at'],
                                            'place_key': block['location_key'],
                                            'academic_block_id': block['id']})
                       for block in blocks)
        return min(options, key=lambda item: item[0])[1] if options else None

    def linked_future_commitment(self, thread_id: int, *, now: datetime) -> bool:
        now = local_time(now)
        with self.db.get_connection() as conn:
            return conn.execute('''SELECT 1 FROM eventos_pendentes
                WHERE story_thread_id=? AND owner_character_key='marina'
                  AND status='pending' AND confirmed=1 AND event_at>?
                LIMIT 1''', (thread_id, now.isoformat())).fetchone() is not None

    def finish(self, event_id: int) -> None:
        self.db.concluir_evento_pendente(event_id)

    def cancel(self, event_id: int) -> bool:
        return self.db.cancelar_evento_pendente(event_id)

    def unlink_thread(self, event_id: int) -> None:
        """A once-relevant calendar event no longer protects a story thread."""
        with self.db.get_connection() as conn:
            conn.execute('''UPDATE eventos_pendentes SET story_thread_id=NULL
                WHERE id=? AND owner_character_key='marina' ''', (event_id,))

    def reschedule(self, event_id: int, *, start_at: datetime, end_at: datetime,
                   conflict_resolution: str | None = None) -> None:
        start_at, end_at = local_time(start_at), local_time(end_at)
        if start_at >= end_at:
            raise ValueError('Invalid commitment interval')
        with self.db.get_connection() as conn:
            row = conn.execute('''SELECT * FROM eventos_pendentes
                WHERE id=? AND owner_character_key='marina' AND status='pending' AND confirmed=1''',
                (event_id,)).fetchone()
        if not row:
            raise ValueError('Active confirmed calendar event not found')
        if row['event_type'] not in ACADEMIC_EVENTS:
            from academic_life import AcademicLife

            if AcademicLife(self.db).conflicting_blocks(start_at, end_at):
                if conflict_resolution not in CONFLICT_RESOLUTIONS:
                    raise ValueError('Rescheduled event conflicts with class')
        with self.db.transaction():
            with self.db.get_connection() as conn:
                if row['event_type'] != 'academic_class_cancelled' and conn.execute('''
                    SELECT 1 FROM eventos_pendentes WHERE id!=? AND owner_character_key='marina'
                      AND status='pending' AND confirmed=1
                      AND event_type!='academic_class_cancelled'
                      AND event_at<? AND COALESCE(end_at,event_at)>? LIMIT 1''',
                    (event_id, end_at.isoformat(), start_at.isoformat())).fetchone():
                    raise ValueError('Calendar already has an overlapping confirmed event')
                data = json.loads(row['metadata_json'] or '{}')
                if conflict_resolution:
                    data['academic_conflict_resolution'] = conflict_resolution
                conn.execute('''UPDATE eventos_pendentes
                    SET event_at=?,end_at=?,metadata_json=? WHERE id=?''',
                    (start_at.isoformat(), end_at.isoformat(),
                     json.dumps(data, ensure_ascii=False, sort_keys=True), event_id))
                for reminder in conn.execute('''SELECT id,offset_minutes FROM reminders
                    WHERE event_id=? AND status IN ('offered','confirmed')''',
                    (event_id,)).fetchall():
                    remind_at = start_at - timedelta(minutes=reminder['offset_minutes'] or 0)
                    conn.execute('''UPDATE reminders SET remind_at=?,updated_at=? WHERE id=?''',
                                 (remind_at.isoformat(), datetime.now().isoformat(),
                                  reminder['id']))
