import sqlite3
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academic_repository import AcademicRepository
from db import DatabaseManager
from seed_academic_v36 import COURSES, seed_academic, upgrade_academic_grade_v2, OLD_COURSES, OLD_METADATA, PROFILE, _digest
from seed_world_bible_v36 import seed_world_bible
from world_repository import CanonConflictError


class TestAcademicFoundation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / 'academic.db')
        seed_world_bible(self.db)
        self.repo = AcademicRepository(self.db)

    def test_seed_grade_and_repeat_preserve_progression(self):
        self.assertTrue(seed_academic(self.db))
        self.assertEqual(self.repo.get_profile()['current_term'], '2026.2')
        self.assertEqual(self.repo.get_term('2026.2')['start_date'], '2026-08-11')
        self.assertEqual(self.repo.get_term('2026.2')['end_date'], '2026-12-14')
        self.assertEqual(len(self.repo.get_courses('2026.2')), 9)
        grade = self.repo.get_schedule('2026.2')
        self.assertEqual(len(grade), 12)
        self.assertEqual(len({b['weekday'] for b in grade}), 4)
        self.assertEqual(sum(int(b['end_time'][:2])-int(b['start_time'][:2]) for b in grade), 26)
        courses = {c['course_key']: json.loads(c['metadata_json']) for c in self.repo.get_courses('2026.2')}
        self.assertEqual(sum(c['credits'] for c in courses.values()), 26)
        self.assertEqual(courses['DSG1985']['requirement_kind'], 'extra_emphasis_elective')
        self.assertEqual(courses['DSG1985']['curriculum_group'], 'DSG0011')
        self.assertEqual(courses['DSG1866']['curriculum_group'], 'DSG0860')
        self.assertEqual(courses['DSG1400']['curriculum_group'], 'DSG1814')
        self.assertEqual(json.loads(self.repo.get_profile()['metadata_json'])['curriculum_key'], 'design_2023_0')
        for a, b in zip(grade, grade[1:]):
            if a['weekday'] == b['weekday']:
                self.assertLessEqual(a['end_time'], b['start_time'])
        with self.db.get_connection() as conn:
            conn.execute("UPDATE academic_profile SET current_term='2027.1'")
            conn.execute("UPDATE academic_courses SET status='COMPLETED'")
        self.assertFalse(seed_academic(self.db))
        self.assertEqual(self.repo.get_profile()['current_term'], '2027.1')
        self.assertTrue(all(c['status'] == 'COMPLETED' for c in self.repo.get_courses('2026.2')))
        self.assertEqual(self.repo.get_schedule('2026.2'), grade)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM world_state').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM life_events').fetchone()[0], 0)

    def test_failure_rolls_back_entire_seed(self):
        bad = (*COURSES[:-1], (*COURSES[-1][:-1], ((7, '10:00', '12:00', 'LAB'),)))
        with patch('seed_academic_v36.COURSES', bad):
            with self.assertRaises(sqlite3.IntegrityError):
                seed_academic(self.db)
        self.assertIsNone(self.repo.get_profile())
        self.assertEqual(self.repo.get_courses('2026.2'), [])
        self.assertTrue(seed_academic(self.db))

    def test_changed_seed_rejected(self):
        seed_academic(self.db)
        with patch('seed_academic_v36.COURSES', COURSES[:-1]):
            with self.assertRaises(CanonConflictError):
                seed_academic(self.db)
        self.assertEqual(len(self.repo.get_courses('2026.2')), 9)

    def test_missing_world_bible_rolls_back(self):
        empty = DatabaseManager(Path(self.temp.name) / 'empty.db')
        with self.assertRaises(sqlite3.IntegrityError):
            seed_academic(empty)
        self.assertIsNone(AcademicRepository(empty).get_profile())

    def test_invalid_times_rejected(self):
        seed_academic(self.db)
        for start, end in [('29:00','30:00'), ('12:00','10:00'), ('8:00','10:00')]:
            with self.assertRaises(sqlite3.IntegrityError):
                with self.db.get_connection() as conn:
                    conn.execute('UPDATE academic_schedule_blocks SET start_time=?,end_time=?', (start,end))

    def _draft_seed(self):
        with self.db.get_connection() as conn:
            old_meta = json.dumps(OLD_METADATA, ensure_ascii=False, sort_keys=True)
            conn.execute('''INSERT INTO academic_profile
                (character_key,institution,campus_area,program_name,focus_name,entry_term,current_term,metadata_json)
                VALUES ('marina',?,?,?,?,?,?,?)''', (*PROFILE.values(), old_meta))
            term_id = conn.execute('''INSERT INTO academic_terms
                (character_key,term_key,status,generated_by,created_at,metadata_json)
                VALUES ('marina','2026.2','ACTIVE','CANONICAL_SEED','2026-09-18',?)''',
                (old_meta,)).lastrowid
            for key, name, kind, day, start, end in OLD_COURSES:
                course_id = conn.execute('''INSERT INTO academic_courses
                    (academic_term_id,course_key,display_name,course_type,area,metadata_json)
                    VALUES (?,?,?,?,?,?)''', (term_id,key,name,kind,'Corpo e Moda',old_meta)).lastrowid
                conn.execute('''INSERT INTO academic_schedule_blocks
                    (academic_course_id,weekday,start_time,end_time,location_key)
                    VALUES (?,?,?,?,'puc_rio')''', (course_id,day,start,end))
            conn.execute('''INSERT INTO world_bootstrap (key,value,updated_at)
                VALUES ('academic_seed_digest',?,'2026-09-18')''',
                (_digest(OLD_COURSES, OLD_METADATA),))

    def test_guarded_v2_upgrade_is_idempotent(self):
        self._draft_seed()
        self.assertTrue(upgrade_academic_grade_v2(self.db))
        self.assertFalse(upgrade_academic_grade_v2(self.db))
        self.assertEqual(len(self.repo.get_courses('2026.2')), 9)
        self.assertEqual(len(self.repo.get_schedule('2026.2')), 12)
        self.assertEqual(self.repo.get_term('2026.2')['start_date'], '2026-08-11')

    def test_guarded_v2_upgrade_preserves_changed_progress(self):
        self._draft_seed()
        with self.db.get_connection() as conn:
            conn.execute("UPDATE academic_courses SET status='COMPLETED' WHERE course_key='cultura_visual'")
        with self.assertRaises(CanonConflictError):
            upgrade_academic_grade_v2(self.db)
        self.assertEqual(len(self.repo.get_courses('2026.2')), 5)
