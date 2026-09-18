"""Optional, bounded live refresh for real context; cache misses stay unknown.

Provider contracts: https://open-meteo.com/en/docs and
https://github.com/nager/Nager.Date/blob/main/README.md
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from calendar_world import LOCAL_ZONE, RealContextCache, local_time
from config import settings
from db import DatabaseManager


logger = logging.getLogger(__name__)


def _read_json(url: str, *, headers: dict | None = None):
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=4) as response:
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
        annual = self.cache.get(f'holiday_year:rio:{now.year}', now=now)
        primary_ready = (getattr(settings, 'FERIADOS_API_ENABLED', False)
                         and bool(getattr(settings, 'FERIADOS_API_KEY', '')))
        fallback_due = (annual and primary_ready
                        and annual['payload']['coverage'] != 'RIO_ALL'
                        and now - datetime.fromisoformat(annual['observed_at']) >= timedelta(hours=1))
        if not annual or fallback_due:
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
        holidays = None
        source, coverage = 'Nager.Date', 'NATIONAL_ONLY'
        if (getattr(settings, 'FERIADOS_API_ENABLED', False)
                and getattr(settings, 'FERIADOS_API_KEY', '')):
            try:
                holidays = self._feriados_api_year(now.year)
                source, coverage = 'Feriados API', 'RIO_ALL'
            except Exception as exc:
                logger.warning('Brazilian holiday source unavailable: %s', type(exc).__name__)
        if holidays is None:
            holidays = self._nager_year(now.year)
        ttl = timedelta(hours=1) if coverage == 'NATIONAL_ONLY' and getattr(
            settings, 'FERIADOS_API_ENABLED', False) else timedelta(days=14)
        expiry = min(now + ttl, datetime(now.year + 1, 1, 1))
        with self.db.transaction():
            self.cache.put(f'holiday_year:rio:{now.year}', 'holiday_year',
                           {'year': now.year, 'coverage': coverage, 'holidays': holidays},
                           source_name=source, observed_at=now, expires_at=expiry)
            by_day = {}
            for item in holidays:
                by_day.setdefault(item['date'], []).append(item)
            priority = {'national': 0, 'state': 1, 'municipal': 2, 'optional': 3}
            for day, items in by_day.items():
                items.sort(key=lambda item: priority[item['scope']])
                scope = next((item['scope'] for item in reversed(items)
                              if item['scope'] != 'optional'), 'optional')
                self.cache.put(f'holiday:{day}', 'holiday',
                               {'date': day, 'name': ', '.join(i['name'] for i in items)[:100],
                                'scope': scope,
                                'holidays': [{'name': i['name'], 'scope': i['scope']}
                                             for i in items]},
                               source_name=source, observed_at=now, expires_at=expiry)
        return True

    def _feriados_api_year(self, year: int) -> list[dict]:
        key = settings.FERIADOS_API_KEY
        headers = {'Authorization': f'Bearer {key}', 'Accept': 'application/json'}
        items = []
        for page in range(1, 4):
            query = urlencode({'ano': year, 'facultativos': 'true', 'limit': 100, 'page': page})
            data = _read_json(f'https://feriadosapi.com/api/v1/feriados/cidade/3304557?{query}',
                              headers=headers)
            if not isinstance(data, dict) or not isinstance(data.get('feriados'), list):
                raise ValueError('Unexpected Feriados API response')
            city = data.get('cidade') or {}
            if city and (str(city.get('ibge')) != '3304557' or city.get('uf') != 'RJ'):
                raise ValueError('Feriados API returned another municipality')
            items.extend(data['feriados'])
            pages = int((data.get('meta') or {}).get('total_pages') or 1)
            if pages <= page:
                break
        else:
            raise ValueError('Feriados API pagination exceeds bounded request limit')
        scopes = {'NACIONAL': 'national', 'NATIONAL': 'national',
                  'ESTADUAL': 'state', 'STATE': 'state',
                  'MUNICIPAL': 'municipal',
                  'FACULTATIVO': 'optional', 'OPTIONAL': 'optional'}
        result = []
        seen = set()
        for item in items:
            scope = scopes.get(str(item.get('tipo', '')).upper())
            if scope is None:
                continue
            day = self._holiday_date(str(item.get('data', '')))
            name = self._holiday_name(item.get('nome'))
            if not day or not day.startswith(f'{year}-') or not name:
                continue
            identity = day, name, scope
            if identity not in seen:
                result.append({'date': day, 'name': name, 'scope': scope})
                seen.add(identity)
        if not result:
            raise ValueError('Feriados API returned no valid holidays')
        return result

    def _nager_year(self, year: int) -> list[dict]:
        data = _read_json(f'https://date.nager.at/api/v3/PublicHolidays/{year}/BR')
        if not isinstance(data, list):
            raise ValueError('Holiday fallback returned non-list')
        result = []
        for item in data:
            if item.get('countryCode') != 'BR' or not item.get('global') or 'Public' not in item.get('types', []):
                continue
            day = self._holiday_date(str(item.get('date', '')))
            name = self._holiday_name(item.get('localName') or item.get('name'))
            if day and day.startswith(f'{year}-') and name:
                result.append({'date': day, 'name': name, 'scope': 'national'})
        if not result:
            raise ValueError('Holiday fallback returned no valid national holidays')
        return result

    @staticmethod
    def _holiday_date(value: str) -> str | None:
        for format_ in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(value, format_).date().isoformat()
            except ValueError:
                pass
        return None

    @staticmethod
    def _holiday_name(value) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value if 0 < len(value) <= 100 and not any(ord(ch) < 32 for ch in value) else None

    def holiday_on(self, day: datetime) -> dict:
        """Nager-only absence cannot prove absence of RJ/local holidays."""
        day = local_time(day)
        entry = self.cache.get(f'holiday:{day.date().isoformat()}', now=day)
        if entry:
            holidays = entry['payload'].get('holidays') or [
                {'name': entry['payload']['name'], 'scope': entry['payload']['scope']}]
            return {'status': 'OPTIONAL' if all(item['scope'] == 'optional' for item in holidays)
                    else 'HOLIDAY', 'holidays': holidays,
                    'coverage': 'RIO_ALL' if entry['source_name'] == 'Feriados API' else 'NATIONAL_ONLY'}
        annual = self.cache.get(f'holiday_year:rio:{day.year}', now=day)
        if not annual or annual['payload']['coverage'] != 'RIO_ALL':
            return {'status': 'UNKNOWN', 'holidays': [], 'coverage': 'NATIONAL_ONLY' if annual else 'NONE'}
        return {'status': 'NONE', 'holidays': [], 'coverage': 'RIO_ALL'}
