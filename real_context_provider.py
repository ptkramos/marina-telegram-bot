"""Optional, bounded live refresh for real context; cache misses stay unknown.

Provider contracts: https://open-meteo.com/en/docs and
https://github.com/nager/Nager.Date/blob/main/README.md
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from urllib.parse import urlencode
from urllib.request import urlopen

from calendar_world import LOCAL_ZONE, RealContextCache, local_time
from db import DatabaseManager


logger = logging.getLogger(__name__)


def _read_json(url: str):
    with urlopen(url, timeout=4) as response:
        if response.status != 200:
            raise RuntimeError(f'Provider returned HTTP {response.status}')
        raw = response.read(512_001)
    if len(raw) > 512_000:
        raise ValueError('Provider response too large')
    return json.loads(raw)


class RealContextProvider:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.cache = RealContextCache(db)

    def refresh(self, now: datetime) -> dict[str, bool]:
        now = local_time(now)
        result = {'weather': False, 'holidays': False}
        if not self.cache.get('weather:rio', now=now):
            try:
                result['weather'] = self.refresh_weather(now)
            except Exception as exc:
                logger.warning('Real weather unavailable: %s', type(exc).__name__)
        with self.db.get_connection() as conn:
            marker = conn.execute('SELECT 1 FROM world_bootstrap WHERE key=?',
                                  (f'holidays_fetched:{now.year}',)).fetchone()
        if not marker:
            try:
                result['holidays'] = self.refresh_holidays(now)
            except Exception as exc:
                logger.warning('Real holidays unavailable: %s', type(exc).__name__)
        return result

    def refresh_weather(self, now: datetime) -> bool:
        now = local_time(now)
        query = urlencode({
            'latitude': -22.9519, 'longitude': -43.2105,
            'current': 'temperature_2m,rain,showers',
            'timezone': 'America/Sao_Paulo',
        })
        data = _read_json(f'https://api.open-meteo.com/v1/forecast?{query}')
        current = data.get('current') or {}
        observed = datetime.fromisoformat(current['time'])
        if abs((now - observed).total_seconds()) > 7200:
            return False
        rain = float(current.get('rain') or 0) + float(current.get('showers') or 0)
        temperature = float(current['temperature_2m'])
        if not -20 <= temperature <= 55 or rain < 0:
            return False
        self.cache.put('weather:rio', 'weather',
                       {'heavy_rain': rain >= 3.0, 'temperature_c': temperature},
                       source_name='Open-Meteo current model', observed_at=now,
                       expires_at=now + timedelta(minutes=30))
        return True

    def refresh_holidays(self, now: datetime) -> bool:
        now = local_time(now)
        data = _read_json(f'https://date.nager.at/api/v3/PublicHolidays/{now.year}/BR')
        if not isinstance(data, list):
            raise ValueError('Holiday provider returned non-list')
        expiry = datetime(now.year + 1, 1, 1)
        for item in data:
            if item.get('countryCode') != 'BR' or not item.get('global'):
                continue
            if 'Public' not in item.get('types', []):
                continue
            day = str(item['date'])
            name = str(item.get('localName') or item.get('name') or '')
            if len(name) > 100 or any(ord(ch) < 32 for ch in name):
                continue
            self.cache.put(f'holiday:{day}', 'holiday',
                           {'date': day, 'name': name, 'scope': 'national'},
                           source_name='Nager.Date', observed_at=now,
                           expires_at=expiry)
        with self.db.get_connection() as conn:
            conn.execute('''INSERT OR IGNORE INTO world_bootstrap(key,value,updated_at)
                VALUES (?,?,?)''',
                (f'holidays_fetched:{now.year}', '1', now.isoformat()))
        return True
