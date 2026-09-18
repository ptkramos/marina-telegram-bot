"""Academic storage. Does not resolve dates, project events or advance semesters."""

from db import DatabaseManager


class AcademicRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_profile(self, character_key='marina'):
        with self.db.get_connection() as conn:
            row = conn.execute('SELECT * FROM academic_profile WHERE character_key=?',
                               (character_key,)).fetchone()
            return dict(row) if row else None

    def get_term(self, term_key, character_key='marina'):
        with self.db.get_connection() as conn:
            row = conn.execute('SELECT * FROM academic_terms WHERE character_key=? AND term_key=?',
                               (character_key, term_key)).fetchone()
            return dict(row) if row else None

    def get_courses(self, term_key, character_key='marina'):
        with self.db.get_connection() as conn:
            return [dict(row) for row in conn.execute('''
                SELECT c.* FROM academic_courses c JOIN academic_terms t ON t.id=c.academic_term_id
                WHERE t.character_key=? AND t.term_key=? ORDER BY c.course_key
                ''', (character_key, term_key))]

    def get_schedule(self, term_key, character_key='marina'):
        """Weekly patterns, not today's commitments; includes inactive historical rows."""
        with self.db.get_connection() as conn:
            return [dict(row) for row in conn.execute('''
                SELECT b.*, c.course_key, c.display_name FROM academic_schedule_blocks b
                JOIN academic_courses c ON c.id=b.academic_course_id
                JOIN academic_terms t ON t.id=c.academic_term_id
                WHERE t.character_key=? AND t.term_key=? ORDER BY b.weekday,b.start_time
                ''', (character_key, term_key))]
