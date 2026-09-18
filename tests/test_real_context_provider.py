"""Live-source parsing without network, and no invented cache fallback."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from real_context_provider import RealContextProvider


class TestRealContextProvider(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'context.db')
        self.provider = RealContextProvider(self.db)

    def test_weather_requires_timely_provider_value(self):
        now = datetime(2026, 9, 18, 12)
        with patch('real_context_provider._read_json', return_value={
            'current': {'time': '2026-09-18T12:00', 'rain': 3.2,
                        'showers': 0, 'temperature_2m': 25.0}}):
            self.assertTrue(self.provider.refresh_weather(now))
        value = self.provider.cache.get('weather:rio', now=now)
        self.assertTrue(value['payload']['heavy_rain'])
        self.assertEqual(value['source_name'], 'Open-Meteo current model')
        self.assertIsNone(self.provider.cache.get('weather:rio',
                                                  now=now + timedelta(hours=1)))

    def test_holidays_only_accept_public_national_entries(self):
        now = datetime(2026, 9, 18, 12)
        with patch('real_context_provider._read_json', return_value=[
            {'countryCode': 'BR', 'global': True, 'types': ['Public'],
             'date': '2026-11-15', 'localName': 'Feriado de exemplo'},
            {'countryCode': 'BR', 'global': False, 'types': ['Public'],
             'date': '2026-11-16', 'localName': 'Regional'},
        ]):
            self.assertTrue(self.provider.refresh_holidays(now))
        self.assertIsNotNone(self.provider.cache.get(
            'holiday:2026-11-15', now=datetime(2026, 11, 15)))
        self.assertIsNone(self.provider.cache.get(
            'holiday:2026-11-16', now=datetime(2026, 11, 16)))


if __name__ == '__main__':
    unittest.main()
