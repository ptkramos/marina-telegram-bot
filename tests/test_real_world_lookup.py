"""Demand-driven place lookup: no discovery, no unchecked hours, no permanent memory."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from db import DatabaseManager
from real_world_lookup import RealWorldLookupService
from seed_world_bible_v36 import seed_world_bible


class TestRealWorldLookup(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'lookup.db')
        seed_world_bible(self.db)
        self.now = datetime(2026, 9, 18, 12)
        self.search = Mock(return_value=[])
        self.lookup = RealWorldLookupService(self.db, search=self.search)
        self.lookup.cache.put('holiday_year:rio:2026', 'holiday_year',
                              {'year': 2026, 'coverage': 'RIO_ALL', 'holidays': []},
                              source_name='Feriados API', observed_at=self.now,
                              expires_at=self.now + timedelta(days=10))

    def test_no_search_without_specific_place_and_hours_question(self):
        self.assertIsNone(self.lookup.lookup_for_message('Estou em casa descansando', now=self.now))
        self.assertIsNone(self.lookup.lookup_for_message('Quero conhecer restaurantes novos', now=self.now))
        self.assertIsNone(self.lookup.lookup_for_message('A Petz está aberta?', now=self.now))
        self.assertIsNone(self.lookup.lookup_for_message('Vamos ao Shopping da Gávea', now=self.now))
        self.search.assert_not_called()

    def test_explicit_petz_unit_can_be_checked_without_canonical_promotion(self):
        self.search.return_value = [{
            'title': 'Petz Botafogo', 'href': 'https://www.petz.com.br/loja/petz-botafogo',
            'body': 'Petz Botafogo: todos os dias das 08:00 às 22:00',
        }]
        fact = self.lookup.lookup_for_message('A Petz Botafogo ainda está aberta?', now=self.now)
        self.assertEqual(fact['status'], 'CONFIRMED')
        with self.db.get_connection() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM world_places WHERE canonical_key='petz_botafogo_candidate'").fetchone())

    def test_official_hours_cached_and_generic_snippet_ignored(self):
        self.search.return_value = [
            {'title': 'Shopping da Gávea', 'href': 'https://directory.example/shopping',
             'body': 'Shopping da Gávea das 09h às 23h'},
            {'title': 'Shopping da Gávea - horários', 'href': 'https://shoppingdagavea.com.br/horarios',
             'body': 'Shopping da Gávea funciona sexta das 10h às 22h'},
        ]
        result = self.lookup.lookup_for_message('O Shopping da Gávea abre que horas?', now=self.now)
        self.assertEqual(result['status'], 'CONFIRMED')
        self.assertEqual(result['value']['opens_at'], '10:00')
        self.assertEqual(result['source_type'], 'official')
        self.assertTrue(self.lookup.lookup_for_message(
            'Shopping da Gávea está aberto?', now=self.now + timedelta(minutes=1))['cache_hit'])
        self.assertEqual(self.search.call_count, 1)

    def test_conflicting_official_results_and_failure_are_unknown(self):
        self.search.return_value = [
            {'title': 'Shopping da Gávea', 'href': 'https://shoppingdagavea.com.br/?source=a',
             'body': 'Shopping da Gávea sexta das 10h às 22h'},
            {'title': 'Shopping da Gávea', 'href': 'https://shoppingdagavea.com.br/?source=b',
             'body': 'Shopping da Gávea sexta das 11h às 20h'},
        ]
        result = self.lookup.lookup_opening_hours('shopping_gavea', now=self.now)
        self.assertEqual(result['status'], 'UNKNOWN')
        self.search.side_effect = TimeoutError('search unavailable')
        self.assertEqual(self.lookup.lookup_opening_hours(
            'shopping_gavea', now=self.now + timedelta(minutes=21))['status'], 'UNKNOWN')

    def test_holiday_requires_specific_hours_and_never_promotes_place(self):
        self.lookup.cache.put('place:shopping_gavea:opening_hours:2026-09-18',
                              'place_fact', {'status': 'CONFIRMED',
                                             'entity_key': 'shopping_gavea',
                                             'entity_name': 'Shopping da Gávea',
                                             'fact_type': 'opening_hours',
                                             'for_date': '2026-09-18',
                                             'value': {'opens_at': '10:00', 'closes_at': '22:00'},
                                             'source_url': 'https://shoppingdagavea.com.br/',
                                             'source_type': 'official', 'confidence': .85},
                              source_name='shoppingdagavea.com.br',
                              observed_at=self.now,
                              expires_at=self.now + timedelta(hours=12))
        self.lookup.cache.put('holiday:2026-09-18', 'holiday',
                              {'date': '2026-09-18', 'name': 'Feriado', 'scope': 'municipal'},
                              source_name='Feriados API', observed_at=self.now,
                              expires_at=self.now + timedelta(hours=12))
        self.search.return_value = [
            {'title': 'Shopping da Gávea', 'href': 'https://shoppingdagavea.com.br/horarios',
             'body': 'Shopping da Gávea funciona das 10h às 22h'},
        ]
        result = self.lookup.lookup_for_message('Shopping da Gávea abre hoje?', now=self.now)
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(self.search.call_count, 1)
        self.assertIn('feriado', self.search.call_args.args[0])
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM world_places WHERE canonical_key='new_place'").fetchone()[0], 0)
