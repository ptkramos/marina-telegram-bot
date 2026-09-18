"""Demand-driven, conservative place facts over the existing DDGS adapter."""

from datetime import datetime, time, timedelta
import re
from urllib.parse import urlparse

from calendar_world import RealContextCache, local_time
from config import settings
from real_context_provider import RealContextProvider
from web_search_adapter import search_text
from world_repository import WorldBibleRepository


# Only known, unambiguous units. This map does not create World Bible places.
PLACE_ALIASES = {
    'petz_botafogo_candidate': ('petz botafogo',),
    'shopping_gavea': ('shopping da gávea', 'shopping da gavea'),
    'botafogo_praia_shopping': ('botafogo praia shopping',),
    'bodytech_sao_clemente': ('bodytech são clemente', 'bodytech sao clemente'),
    'zona_sul_sao_clemente': ('zona sul são clemente', 'zona sul sao clemente'),
    'starbucks_shopping_gavea': ('starbucks shopping da gávea', 'starbucks shopping da gavea'),
}
OFFICIAL_DOMAINS = {
    'petz_botafogo_candidate': ('petz.com.br',),
    'shopping_gavea': ('shoppingdagavea.com.br',),
    'botafogo_praia_shopping': ('botafogopraiashopping.com.br',),
    'bodytech_sao_clemente': ('bodytech.com.br',),
    'zona_sul_sao_clemente': ('zonasul.com.br',),
    'starbucks_shopping_gavea': ('starbucks.com.br',),
}
EXPLICIT_CANDIDATES = {
    # Patrick may name a specific real unit. Lookup does not promote it to canon.
    'petz_botafogo_candidate': {'name': 'Petz Botafogo', 'region': 'Botafogo'},
}
HOURS_INTENT = re.compile(r'\b(hor[aá]rio|abre|aberto|aberta|fecha|fechado|fechada|funciona)\b', re.I)
HOURS_PATTERN = re.compile(
    r'\b(?:das|de)\s*(\d{1,2})(?::(\d{2}))?\s*(?:h|horas)?\s*'
    r'(?:às|as|a|até|-)\s*(\d{1,2})(?::(\d{2}))?\s*(?:h|horas)?\b', re.I)
WEEKDAYS = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')


class RealWorldLookupService:
    def __init__(self, db, *, search=search_text):
        self.db = db
        self.cache = RealContextCache(db)
        self.bible = WorldBibleRepository(db)
        self.search = search

    def lookup_for_message(self, message: str, *, now: datetime | None = None) -> dict | None:
        """None means no lookup trigger; UNKNOWN means a triggered, unresolved fact."""
        if not HOURS_INTENT.search(message):
            return None
        lowered = message.casefold()
        matches = [(len(alias), key) for key, aliases in PLACE_ALIASES.items()
                   for alias in aliases if alias in lowered]
        if not matches:
            return None  # Unknown/ambiguous units do not trigger broad discovery.
        best = max(length for length, _ in matches)
        keys = {key for length, key in matches if length == best}
        if len(keys) != 1:
            return None
        day = local_time(now or datetime.now())
        holiday_provider = RealContextProvider(self.db)
        if (getattr(settings, 'FERIADOS_API_ENABLED', False)
                and not self.cache.get(f'holiday_year:rio:{day.year}', now=day)):
            try:
                holiday_provider.refresh_holidays(day)
            except Exception:
                pass  # UNKNOWN is safer than blocking the conversation.
        holiday = holiday_provider.holiday_on(day)
        fact_type = ('holiday_opening_hours' if 'feriado' in lowered
                     or holiday['status'] != 'NONE' else 'opening_hours')
        return self.lookup_place_fact(keys.pop(), fact_type,
                                      decision_context='user_opening_hours_question', now=day)

    def lookup_opening_hours(self, place_key: str, *, now: datetime,
                             holiday_specific: bool = False) -> dict:
        return self.lookup_place_fact(
            place_key, 'holiday_opening_hours' if holiday_specific else 'opening_hours',
            decision_context='opening_hours_needed', now=now)

    def lookup_place_fact(self, place_key: str, fact_type: str, *,
                          decision_context: str, now: datetime) -> dict:
        if fact_type not in ('opening_hours', 'holiday_opening_hours'):
            raise ValueError('Unsupported place fact')
        if not decision_context:
            raise ValueError('Concrete decision or question required')
        place = self.bible.get_place(place_key) or EXPLICIT_CANDIDATES.get(place_key)
        if not place or place_key not in PLACE_ALIASES:
            return {'status': 'UNKNOWN', 'entity_key': place_key, 'fact_type': fact_type}
        now = local_time(now)
        day = now.date().isoformat()
        cache_key = f'place:{place_key}:{fact_type}:{day}'
        cached = self.cache.get(cache_key, now=now)
        if cached:
            return {**cached['payload'], 'cache_hit': True,
                    'checked_at': cached['observed_at'], 'expires_at': cached['expires_at']}
        name = place['name']
        query = f'"{name}" {place["region"]} horário de funcionamento'
        if fact_type == 'holiday_opening_hours':
            query += f' feriado {now:%d/%m/%Y}'
        try:
            results = self.search(query, max_results=5, timeout=4)
        except Exception:
            results = []
        candidates = []
        for item in results[:5]:
            url = str(item.get('href') or '')
            parsed = urlparse(url)
            domain = (parsed.hostname or '').lower()
            if parsed.scheme != 'https' or not any(
                domain == official or domain.endswith('.' + official)
                for official in OFFICIAL_DOMAINS[place_key]):
                continue
            text = f"{item.get('title') or ''} {item.get('body') or ''}"
            if not any(alias in text.casefold() for alias in PLACE_ALIASES[place_key]):
                continue
            if (place_key in ('shopping_gavea', 'botafogo_praia_shopping')
                    and parsed.path.strip('/') not in ('', 'horario', 'horarios', 'horarios-de-funcionamento')):
                continue
            if (place_key == 'petz_botafogo_candidate'
                    and parsed.path.rstrip('/') != '/loja/petz-botafogo'):
                continue
            if (fact_type == 'holiday_opening_hours'
                    and day not in text and now.strftime('%d/%m/%Y') not in text):
                continue
            if (fact_type == 'opening_hours' and WEEKDAYS[now.weekday()] not in text.casefold()
                    and 'todos os dias' not in text.casefold()
                    and not (now.weekday() < 6 and 'segunda' in text.casefold()
                             and 'sábado' in text.casefold())):
                continue
            match = HOURS_PATTERN.search(text)
            if not match:
                continue
            begin_h, begin_m, end_h, end_m = match.groups()
            opening = f'{int(begin_h):02d}:{int(begin_m or 0):02d}'
            closing = f'{int(end_h):02d}:{int(end_m or 0):02d}'
            if opening >= closing or int(end_h) > 23:
                continue
            candidates.append((opening, closing, url, domain))
        distinct = {(row[0], row[1]) for row in candidates}
        if len(distinct) == 1:
            opening, closing, url, domain = candidates[0]
            expiry = min(now + timedelta(hours=4 if fact_type == 'holiday_opening_hours' else 24),
                         datetime.combine(now.date() + timedelta(days=1), time.min))
            result = {'status': 'CONFIRMED', 'entity_key': place_key, 'entity_name': name,
                      'fact_type': fact_type, 'for_date': day,
                      'value': {'opens_at': opening, 'closes_at': closing},
                      'source_url': url, 'source_type': 'official', 'confidence': 0.85}
            kind, source = 'place_fact', domain
        else:
            result = {'status': 'UNKNOWN', 'entity_key': place_key, 'entity_name': name,
                      'fact_type': fact_type, 'for_date': day}
            expiry = now + timedelta(minutes=20)
            kind, source = 'place_negative', 'place lookup'
        self.cache.put(cache_key, kind, result, source_name=source,
                       observed_at=now, expires_at=expiry)
        return {**result, 'cache_hit': False,
                'checked_at': now.isoformat(), 'expires_at': expiry.isoformat()}
