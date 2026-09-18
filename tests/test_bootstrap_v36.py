import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bootstrap_v36 import bootstrap
from db import DatabaseManager


class TestBootstrap(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'active.db'
        self.db = DatabaseManager(self.path)
        with self.db.get_connection() as c:
            c.execute("INSERT INTO conversas(timestamp,role,content) VALUES ('2026-09-01','user','OLD_SENTINEL')")
        self.kw = dict(trusted_cycle_anchor='2026-09-02', now=datetime(2026,9,17,10))

    def test_clean_backup_and_idempotency(self):
        result = bootstrap(self.path, **self.kw)
        self.assertEqual(result['status'], 'complete')
        with sqlite3.connect(result['backup']) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM conversas WHERE content='OLD_SENTINEL'").fetchone()[0], 1)
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM conversas').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM academic_courses').fetchone()[0], 9)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM world_state').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM knowledge_subjects').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT data_inicio_ciclo FROM ciclo_biologico').fetchone()[0], '2026-09-02')
            c.execute("INSERT INTO conversas(timestamp,role,content) VALUES ('2026-09-17','user','NEW')")
        self.assertEqual(bootstrap(self.path, **self.kw)['status'], 'already_complete')
        with self.db.get_connection() as c:
            self.assertEqual(c.execute('SELECT content FROM conversas').fetchone()[0], 'NEW')

    def test_seed_failure_never_publishes(self):
        with patch('seed_academic_v36.seed_academic', side_effect=RuntimeError('seed failed')):
            with self.assertRaisesRegex(RuntimeError, 'seed failed'):
                bootstrap(self.path, **self.kw)
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM conversas WHERE content='OLD_SENTINEL'").fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM world_characters').fetchone()[0], 0)

    def test_untrusted_cycle_aborts(self):
        with self.assertRaises(ValueError):
            bootstrap(self.path, now=self.kw['now'])
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM conversas WHERE content='OLD_SENTINEL'").fetchone()[0], 1)

    def test_unknown_table_aborts(self):
        with self.db.get_connection() as c:
            c.execute('CREATE TABLE unknown_memory (value TEXT)')
        with self.assertRaisesRegex(RuntimeError, 'sem política'):
            bootstrap(self.path, **self.kw)

    def test_upgrade_from_schema_eight_backed_up_before_migration(self):
        with self.db.get_connection() as c:
            for table in ('preference_evidence','social_evidence','social_place_state','social_place_links','social_relationships',
                          'academic_schedule_blocks','academic_courses','academic_terms','academic_profile'):
                c.execute(f'DROP TABLE {table}')
            c.execute('DELETE FROM schema_version WHERE version>=9')
        result = bootstrap(self.path, **self.kw)
        self.assertEqual(result['source_schema'], 8)
        self.assertEqual(self.db.get_schema_version(), 16)
        with sqlite3.connect(result['backup']) as c:
            self.assertEqual(c.execute('SELECT MAX(version) FROM schema_version').fetchone()[0], 8)
