"""Live-source parsing without network, and no invented cache fallback."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from config import settings
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
        with (patch.object(settings, 'FERIADOS_API_ENABLED', False),
              patch('real_context_provider._read_json', return_value=[
            {'countryCode': 'BR', 'global': True, 'types': ['Public'],
             'date': '2026-09-20', 'localName': 'Feriado de exemplo'},
            {'countryCode': 'BR', 'global': False, 'types': ['Public'],
             'date': '2026-09-21', 'localName': 'Regional'},
        ])):
            self.assertTrue(self.provider.refresh_holidays(now))
        self.assertIsNotNone(self.provider.cache.get(
            'holiday:2026-09-20', now=datetime(2026, 9, 20)))
        self.assertIsNone(self.provider.cache.get(
            'holiday:2026-09-21', now=datetime(2026, 9, 21)))
        self.assertEqual(self.provider.holiday_on(datetime(2026, 9, 21))['status'], 'UNKNOWN')

    def test_rio_primary_preserves_three_scopes_and_cache_avoids_repeat(self):
        now = datetime(2026, 9, 18, 12)
        data = {'cidade': {'ibge': 3304557, 'uf': 'RJ'}, 'ano': '2026',
                'feriados': [
                    {'data': '20/09/2026', 'nome': 'Nacional', 'tipo': 'NACIONAL'},
                    {'data': '21/09/2026', 'nome': 'Estadual', 'tipo': 'ESTADUAL'},
                    {'data': '22/09/2026', 'nome': 'Municipal', 'tipo': 'MUNICIPAL'},
                    {'data': '23/09/2026', 'nome': 'Facultativo', 'tipo': 'FACULTATIVO'},
                ], 'meta': {'total_pages': 1}}
        with (patch.object(settings, 'FERIADOS_API_ENABLED', True),
              patch.object(settings, 'FERIADOS_API_KEY', 'test-token'),
              patch('real_context_provider._read_json', return_value=data) as request,
              patch.object(self.provider, 'refresh_weather', return_value=True)):
            self.assertTrue(self.provider.refresh_holidays(now))
            self.assertEqual(self.provider.holiday_on(datetime(2026, 9, 20))['holidays'][0]['scope'], 'national')
            self.assertEqual(self.provider.holiday_on(datetime(2026, 9, 21))['holidays'][0]['scope'], 'state')
            self.assertEqual(self.provider.holiday_on(datetime(2026, 9, 22))['holidays'][0]['scope'], 'municipal')
            self.assertEqual(self.provider.holiday_on(datetime(2026, 9, 23))['holidays'][0]['scope'], 'optional')
            self.assertEqual(self.provider.holiday_on(datetime(2026, 9, 23))['status'], 'OPTIONAL')
            self.provider.refresh(now + timedelta(minutes=1))
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.kwargs['headers']['Authorization'], 'Bearer test-token')

    def test_primary_failure_uses_national_fallback_without_false_regional_absence(self):
        now = datetime(2026, 9, 18, 12)
        def source(url, **kwargs):
            if 'feriadosapi.com' in url:
                raise TimeoutError('provider timeout')
            return [{'countryCode': 'BR', 'global': True, 'types': ['Public'],
                     'date': '2026-09-18', 'localName': 'Nacional'}]
        with (patch.object(settings, 'FERIADOS_API_ENABLED', True),
              patch.object(settings, 'FERIADOS_API_KEY', 'test-token'),
              patch('real_context_provider._read_json', side_effect=source),
              patch('real_context_provider.logger.warning') as warning):
            self.assertTrue(self.provider.refresh_holidays(now))
        self.assertNotIn('test-token', str(warning.call_args_list))
        self.assertEqual(self.provider.holiday_on(now)['status'], 'HOLIDAY')
        self.assertEqual(self.provider.holiday_on(datetime(2026, 9, 19))['status'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
