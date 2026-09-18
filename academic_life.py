"""Academic term progression and class projection into the shared calendar."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import logging

from academic_repository import AcademicRepository
from calendar_world import ACADEMIC_EVENTS, CalendarWorld, RealContextCache, local_time
from db import DatabaseManager


logger = logging.getLogger(__name__)
GENERATOR_VERSION = 'project_hybrid_v1'


def term_window(term_key: str) -> tuple[date, date]:
    """Project planning windows, not a claim about the official PUC calendar."""
    year_text, half_text = term_key.split('.')
    year, half = int(year_text), int(half_text)
    if half == 1:
        return date(year, 3, 1), date(year, 6, 30)
    if half == 2:
        return date(year, 8, 1), date(year, 12, 18)
    raise ValueError('Term must be YYYY.1 or YYYY.2')


def next_term_key(term_key: str) -> str:
    year_text, half_text = term_key.split('.')
    year, half = int(year_text), int(half_text)
    return f'{year + 1}.1' if half == 2 else f'{year}.2'


class AcademicLife:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.repo = AcademicRepository(db)
        self.context = RealContextCache(db)

    def _term_rows(self) -> list[dict]:
        with self.db.get_connection() as conn:
            return [dict(row) for row in conn.execute('''SELECT * FROM academic_terms
                WHERE character_key='marina' ORDER BY term_key''')]

    def _generate(self, term_key: str) -> None:
        if self.repo.get_term(term_key):
            return
        start, end = term_window(term_key)
        half = int(term_key[-1])
        year = int(term_key[:4])
        layouts = (
            ((0, '08:00', '12:00'), (2, '08:00', '10:00'),
             (2, '10:00', '12:00'), (4, '10:00', '12:00')),
            ((1, '08:00', '12:00'), (2, '10:00', '12:00'),
             (4, '08:00', '10:00'), (4, '10:00', '12:00')),
        )
        layout = layouts[(year + half) % 2]
        serial = term_key.replace('.', '_')
        courses = (
            (f'projeto_design_{serial}', 'Projeto de Design e Corpo', 'PROJECT'),
            (f'contextos_visuais_{serial}', 'Contextos Visuais', 'THEORY'),
            (f'experimentacao_{serial}', 'Experimentação de Materiais', 'LAB'),
            (f'portfolio_{serial}', 'Portfólio e Processos', 'ELECTIVE'),
        )
        if half == 1:
            previous_key = f'projeto_design_{year - 1}_2'
        else:
            previous_key = f'projeto_design_{year}_1'
        with self.db.transaction():
            with self.db.get_connection() as conn:
                if conn.execute("SELECT 1 FROM academic_terms WHERE character_key='marina' AND term_key=?",
                                (term_key,)).fetchone():
                    return
                if term_key != '2027.1':
                    prerequisite = conn.execute('''SELECT 1 FROM academic_courses
                        WHERE course_key=? AND status IN ('ENROLLED','COMPLETED') LIMIT 1''',
                        (previous_key,)).fetchone()
                    if not prerequisite:
                        raise ValueError('Academic prerequisite is absent')
                term_id = conn.execute('''INSERT INTO academic_terms
                    (character_key,term_key,start_date,end_date,status,generated_by,created_at,metadata_json)
                    VALUES ('marina',?,?,?,'PLANNED','ACADEMIC_ENGINE',?,?)''',
                    (term_key, start.isoformat(), end.isoformat(),
                     datetime.now().isoformat(),
                     json.dumps({'generator_version': GENERATOR_VERSION,
                                 'calendar_dates': 'project_planning_not_official'}))).lastrowid
                for (course_key, display_name, kind), (weekday, begins, ends) in zip(courses, layout):
                    prereq = [previous_key] if kind == 'PROJECT' and term_key != '2027.1' else []
                    course_id = conn.execute('''INSERT INTO academic_courses
                        (academic_term_id,course_key,display_name,course_type,area,
                         prerequisite_keys_json,metadata_json)
                        VALUES (?,?,?,?,?,?,?)''',
                        (term_id, course_key, display_name, kind, 'Corpo e Moda',
                         json.dumps(prereq),
                         json.dumps({'curriculum_source': 'project_authored_not_official'}))).lastrowid
                    conn.execute('''INSERT INTO academic_schedule_blocks
                        (academic_course_id,weekday,start_time,end_time,location_key)
                        VALUES (?,?,?,?,?)''',
                        (course_id, weekday, begins, ends, 'puc_rio'))
        logger.info('academic.term.generated %s', term_key)

    def catch_up(self, now: datetime, *, auto_generate: bool = True) -> dict:
        """Advance by term boundaries only; never replay missed classes or stories."""
        now = local_time(now)
        profile = self.repo.get_profile()
        if not profile:
            raise RuntimeError('Academic profile not seeded')
        seed = self.repo.get_term('2026.2')
        if not seed:
            raise RuntimeError('Canonical 2026.2 term not seeded')
        with self.db.get_connection() as conn:
            if seed['start_date'] is None or seed['end_date'] is None:
                start, end = term_window('2026.2')
                conn.execute('''UPDATE academic_terms SET start_date=?,end_date=? WHERE id=?
                    AND start_date IS NULL AND end_date IS NULL''',
                    (start.isoformat(), end.isoformat(), seed['id']))
        target = now.date()
        key = '2026.2'
        traversed = 0
        while traversed < 30:
            traversed += 1
            term = self.repo.get_term(key)
            if not term:
                if not auto_generate:
                    break
                if key >= '2029.1':
                    with self.db.get_connection() as conn:
                        completed_count = conn.execute('''SELECT COUNT(*) FROM academic_terms
                            WHERE character_key='marina' AND status='COMPLETED' ''').fetchone()[0]
                    if completed_count >= 5:
                        break
                self._generate(key)
                term = self.repo.get_term(key)
            start, end = date.fromisoformat(term['start_date']), date.fromisoformat(term['end_date'])
            if target > end and term['status'] in ('ACTIVE', 'PLANNED'):
                with self.db.transaction():
                    with self.db.get_connection() as conn:
                        conn.execute("UPDATE academic_courses SET status='COMPLETED' WHERE academic_term_id=? AND status='ENROLLED'",
                                     (term['id'],))
                        conn.execute("""UPDATE academic_terms SET status='COMPLETED',completed_at=?
                            WHERE id=? AND status IN ('ACTIVE','PLANNED')""",
                            (end.isoformat(), term['id']))
                logger.info('academic.term.completed %s', key)
            elif start <= target <= end and term['status'] == 'PLANNED':
                with self.db.get_connection() as conn:
                    unmet = conn.execute('''SELECT 1 FROM academic_courses c
                        WHERE c.academic_term_id=?
                          AND EXISTS (SELECT 1 FROM json_each(c.prerequisite_keys_json) p
                              WHERE NOT EXISTS (SELECT 1 FROM academic_courses prior
                                  WHERE prior.course_key=p.value AND prior.status='COMPLETED'))
                        LIMIT 1''', (term['id'],)).fetchone()
                    if unmet:
                        raise ValueError('Academic prerequisite was not completed')
                    conn.execute("UPDATE academic_terms SET status='ACTIVE' WHERE id=? AND status='PLANNED'",
                                 (term['id'],))
                logger.info('academic.term.started %s', key)
            if target <= end:
                # One upcoming term may be planned in advance; no future classes are
                # materialized as dated events.
                if auto_generate:
                    following = next_term_key(key)
                    if following < '2029.1' and not self.repo.get_term(following):
                        self._generate(following)
                break
            key = next_term_key(key)
        if traversed >= 30:
            raise RuntimeError('Academic catch-up exceeded 30 terms')
        rows = self._term_rows()
        active = [row for row in rows if row['status'] == 'ACTIVE'
                  and row['start_date'] <= target.isoformat() <= row['end_date']]
        if len(active) > 1:
            raise RuntimeError('Multiple active academic terms')
        current = active[0] if active else None
        latest = max((row for row in rows if row['status'] in ('ACTIVE', 'COMPLETED')),
                     key=lambda row: row['term_key'], default=None)
        if latest and profile['current_term'] != latest['term_key']:
            with self.db.get_connection() as conn:
                conn.execute("UPDATE academic_profile SET current_term=? WHERE character_key='marina'",
                             (latest['term_key'],))
        completed = [row for row in rows if row['status'] == 'COMPLETED']
        if len(completed) >= 5 and max(row['term_key'] for row in completed) >= '2028.2':
            with self.db.get_connection() as conn:
                conn.execute("""UPDATE academic_profile SET graduation_status='ELIGIBLE'
                    WHERE character_key='marina' AND graduation_status='in_progress'""")
            logger.info('academic.graduation.eligible')
        return {'term': current['term_key'] if current else None,
                'phase': self.phase(now, current), 'completed_terms': len(completed),
                'graduation_status': self.repo.get_profile()['graduation_status']}

    @staticmethod
    def phase(now: datetime, term: dict | None) -> str:
        day = local_time(now).date()
        if not term:
            next_start = date(day.year, 3, 1) if day.month < 3 else date(day.year, 8, 1)
            return 'REGISTRATION' if 0 <= (next_start - day).days <= 14 else 'VACATION'
        start, end = date.fromisoformat(term['start_date']), date.fromisoformat(term['end_date'])
        if (day - start).days < 14:
            return 'TERM_START'
        if (end - day).days <= 7:
            return 'TERM_END'
        if (end - day).days <= 14:
            return 'EXAM_PERIOD'
        if (end - day).days <= 28:
            return 'DELIVERY_PERIOD'
        return 'NORMAL'

    def _active_term_on(self, day: date) -> dict | None:
        with self.db.get_connection() as conn:
            row = conn.execute('''SELECT * FROM academic_terms WHERE character_key='marina'
                AND status IN ('ACTIVE','PLANNED') AND start_date<=? AND end_date>=?
                ORDER BY term_key DESC LIMIT 1''', (day.isoformat(), day.isoformat())).fetchone()
        return dict(row) if row else None

    def blocks_on(self, day: date) -> list[dict]:
        term = self._active_term_on(day)
        if not term:
            return []
        holiday = self.context.get(f'holiday:{day.isoformat()}',
                                   now=datetime.combine(day, datetime.min.time()))
        if holiday and holiday['payload']['date'] == day.isoformat():
            return []
        with self.db.get_connection() as conn:
            rows = conn.execute('''SELECT b.*,c.display_name FROM academic_schedule_blocks b
                JOIN academic_courses c ON c.id=b.academic_course_id
                WHERE c.academic_term_id=? AND b.weekday=? AND b.active=1
                  AND c.status='ENROLLED' ORDER BY b.start_time''',
                (term['id'], day.weekday())).fetchall()
            exceptions = conn.execute('''SELECT metadata_json FROM eventos_pendentes
                WHERE owner_character_key='marina' AND confirmed=1 AND status='pending'
                  AND event_type='academic_class_cancelled' AND substr(event_at,1,10)=?''',
                (day.isoformat(),)).fetchall()
        cancelled = {json.loads(row['metadata_json'] or '{}').get('academic_block_id')
                     for row in exceptions}
        result = []
        for row in rows:
            if row['id'] in cancelled:
                continue
            block = dict(row)
            block['start_at'] = f"{day.isoformat()}T{row['start_time']}:00"
            block['end_at'] = f"{day.isoformat()}T{row['end_time']}:00"
            result.append(block)
        return result

    def current_block(self, now: datetime) -> dict | None:
        now = local_time(now)
        return next((block for block in self.blocks_on(now.date())
                     if block['start_at'] <= now.isoformat() < block['end_at']), None)

    def upcoming_blocks(self, now: datetime, *, horizon_days: int = 14) -> list[dict]:
        now = local_time(now)
        blocks = []
        for offset in range(horizon_days + 1):
            blocks.extend(block for block in self.blocks_on(now.date() + timedelta(days=offset))
                          if block['start_at'] > now.isoformat())
        return blocks

    def conflicting_blocks(self, start: datetime, end: datetime) -> list[dict]:
        start, end = local_time(start), local_time(end)
        if end <= start:
            return []
        result = []
        day = start.date()
        while day <= end.date():
            result.extend(block for block in self.blocks_on(day)
                          if block['start_at'] < end.isoformat()
                          and block['end_at'] > start.isoformat())
            day += timedelta(days=1)
        return result

    def schedule_event(self, *, course_key: str, event_type: str, description: str,
                       start_at: datetime, end_at: datetime, source_key: str,
                       story_thread_id: int | None = None) -> int:
        """Project, presentation or deadline lives in Calendar/Events only."""
        if event_type not in ACADEMIC_EVENTS - {'academic_class_cancelled'}:
            raise ValueError('Unsupported academic event type')
        with self.db.get_connection() as conn:
            course = conn.execute('''SELECT c.id,t.term_key FROM academic_courses c
                JOIN academic_terms t ON t.id=c.academic_term_id
                WHERE t.character_key='marina' AND c.course_key=?
                  AND c.status='ENROLLED' AND t.status IN ('ACTIVE','PLANNED')''',
                (course_key,)).fetchone()
        if not course:
            raise ValueError('Academic course is not active or planned')
        return CalendarWorld(self.db).create_commitment(
            source_key=source_key, event_type=event_type, description=description,
            start_at=start_at, end_at=end_at, owner='marina', location_key='puc_rio',
            story_thread_id=story_thread_id,
            metadata={'academic_course_id': course['id'], 'academic_term': course['term_key']})

    def cancel_class_occurrence(self, block_id: int, day: date, *, source_key: str) -> int:
        block = next((item for item in self.blocks_on(day) if item['id'] == block_id), None)
        if not block:
            raise ValueError('No scheduled class occurrence to cancel')
        return CalendarWorld(self.db).create_commitment(
            source_key=source_key, event_type='academic_class_cancelled',
            description='aula cancelada',
            start_at=datetime.fromisoformat(block['start_at']),
            end_at=datetime.fromisoformat(block['end_at']),
            owner='marina', location_key=block['location_key'],
            metadata={'academic_block_id': block_id})
