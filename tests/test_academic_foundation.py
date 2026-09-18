import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academic_repository import AcademicRepository
from db import DatabaseManager
from seed_academic_v36 import COURSES, seed_academic
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
        self.assertIsNone(self.repo.get_term('2026.2')['start_date'])
        self.assertEqual(len(self.repo.get_courses('2026.2')), 5)
        grade = self.repo.get_schedule('2026.2')
        self.assertEqual(len(grade), 5)
        self.assertEqual(len({b['weekday'] for b in grade}), 4)
        self.assertEqual(sum(int(b['end_time'][:2])-int(b['start_time'][:2]) for b in grade), 14)
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
        bad = (*COURSES[:-1], (*COURSES[-1][:3], 7, '10:00', '12:00'))
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
        self.assertEqual(len(self.repo.get_courses('2026.2')), 5)

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
