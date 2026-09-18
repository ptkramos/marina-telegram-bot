"""Read-only camera projection over Living World state (v3.6.6).

Camera World Continuity never calls WorldStateManager.resolve(). It projects the
latest snapshot and/or a confirmed calendar commitment into photographic
constraints without mutating world_state or inventing travel.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import re
from typing import Mapping, Optional

from config import settings
from db import DatabaseManager
from world_repository import WorldBibleRepository, WorldStateRepository


logger = logging.getLogger(__name__)

# Generic photographic descriptions — never forward private region/commitment text.
PLACE_VISUAL: dict[str, str] = {
    'marina_apartment': 'modern Rio de Janeiro apartment interior, candid indoor smartphone photo',
    'puc_rio': 'university campus indoor setting, classroom or corridor, candid smartphone photo',
    'bodytech_sao_clemente': 'modern gym interior, fitness equipment background, candid smartphone photo',
    'enseada_botafogo': 'Botafogo waterfront promenade outdoors, coastal path, candid smartphone photo',
    'botafogo_praia_shopping': 'shopping mall interior corridor, casual storefront lighting',
    'zona_sul_sao_clemente': 'supermarket aisle interior, fluorescent store lighting',
    'pet_services_botafogo': 'pet shop or pet service interior, casual indoor lighting',
    'vet_botafogo': 'veterinary clinic waiting area interior',
    'shopping_gavea': 'shopping mall interior, bright commercial lighting',
    'starbucks_shopping_gavea': 'cafe interior seating, warm indoor lighting',
    'quartinho_bar': 'casual bar interior, evening indoor ambient light',
    'copacabana_beach': 'Copacabana beach outdoors, sand and sea background',
    'ipanema_beach': 'Ipanema beach outdoors, sand and sea background',
    'leblon_beach': 'Leblon beach outdoors, sand and sea background',
    'boutique_agency': 'fashion agency office interior, studio-adjacent indoor space',
}

NEUTRAL_VISUAL = 'neutral candid smartphone selfie, soft indoor lighting, no identifiable landmark'

# Destination categories implied by user text or LLM scene tags.
PLACE_CATEGORIES: dict[str, str] = {
    'marina_apartment': 'apartment',
    'puc_rio': 'campus',
    'bodytech_sao_clemente': 'gym',
    'enseada_botafogo': 'beach',
    'botafogo_praia_shopping': 'shopping',
    'zona_sul_sao_clemente': 'market',
    'pet_services_botafogo': 'pet',
    'vet_botafogo': 'clinic',
    'shopping_gavea': 'shopping',
    'starbucks_shopping_gavea': 'cafe',
    'quartinho_bar': 'bar',
    'copacabana_beach': 'beach',
    'ipanema_beach': 'beach',
    'leblon_beach': 'beach',
    'boutique_agency': 'agency',
}

CATEGORY_SCENE_MARKERS: dict[str, tuple[str, ...]] = {
    'apartment': (
        'apartment', 'living room', 'bedroom', 'kitchen', 'balcony', 'sofa at home',
        'home interior',
    ),
    'campus': (
        'campus', 'classroom', 'university', 'lecture hall', 'faculty corridor', 'puc',
    ),
    'gym': (
        'gym', 'fitness equipment', 'workout', 'academia', 'treadmill', 'weight room',
        'dumbbell',
    ),
    'beach': (
        'beach', 'praia', 'ocean', 'sand', 'seaside', 'shoreline', 'bikini on sand',
    ),
    'shopping': (
        'shopping mall', 'mall corridor', 'storefront', 'shopping center',
    ),
    'bar': (
        'bar interior', 'cocktail bar', 'nightclub', 'quartinho', 'pub booth',
    ),
    'agency': (
        'photo studio', 'studio backdrop', 'green screen', 'agency office',
    ),
    'cafe': ('cafe interior', 'coffee shop', 'starbucks'),
    'market': ('supermarket', 'grocery aisle'),
    'pet': ('pet shop', 'pet service'),
    'clinic': ('veterinary', 'clinic waiting'),
}

# User requests that imply a destination incompatible with another place_key.
REQUEST_PLACE_HINTS: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (re.compile(r'\b(?:praia|beach|copacabana|ipanema|leblon)\b', re.I),
     frozenset({'copacabana_beach', 'ipanema_beach', 'leblon_beach', 'enseada_botafogo'})),
    (re.compile(r'\b(?:academia|gym|treino|bodytech)\b', re.I),
     frozenset({'bodytech_sao_clemente'})),
    (re.compile(r'\b(?:faculdade|facul|puc|campus|aula)\b', re.I),
     frozenset({'puc_rio'})),
    (re.compile(r'\b(?:shopping|mall)\b', re.I),
     frozenset({'botafogo_praia_shopping', 'shopping_gavea'})),
    (re.compile(r'\b(?:bar|quartinho)\b', re.I),
     frozenset({'quartinho_bar'})),
    (re.compile(r'\b(?:est[uú]dio|studio)\b', re.I),
     frozenset({'boutique_agency'})),
    (re.compile(r'\b(?:apartamento|ap[eê]|em casa|no ap)\b', re.I),
     frozenset({'marina_apartment'})),
)

ROOM_HINTS = (
    (re.compile(r'\b(?:bedroom|quarto|cama|bed)\b', re.I), 'bedroom'),
    (re.compile(r'\b(?:bathroom|banheiro)\b', re.I), 'bathroom'),
    (re.compile(r'\b(?:living room|sala|sofa|sof[aá])\b', re.I), 'living room'),
    (re.compile(r'\b(?:kitchen|cozinha)\b', re.I), 'kitchen'),
    (re.compile(r'\b(?:balcony|varanda)\b', re.I), 'balcony'),
)

# Only home places expose room/sub-location; campus/gym/bar never inherit "quarto".
PLACES_WITH_ROOMS = frozenset({'marina_apartment'})
HOME_SUBLOCATIONS = frozenset({'bedroom', 'bathroom', 'living room', 'kitchen', 'balcony'})


@dataclass(frozen=True)
class CameraWorldContext:
    """Immutable read-only projection for one photo request."""

    snapshot_id: Optional[int]
    place_key: Optional[str]
    visual_location: str
    sublocation: Optional[str]
    activity: Optional[str]
    activity_source: str
    local_time: datetime
    weather: Optional[dict]
    present_people: tuple[str, ...] = ()
    negative_constraints: tuple[str, ...] = ()
    presence_assertable: bool = False
    request_conflict: bool = False
    conflict_hint: str = ''
    safe_scene_tags: str = NEUTRAL_VISUAL
    director_restrictions: str = ''

    def compatible_with_previous(self, place_key: Optional[str], location: str = '') -> bool:
        """Camera continuity may reuse outfit/sublocation only at the same place."""
        if not self.presence_assertable or not self.place_key:
            return False
        if place_key:
            return place_key == self.place_key
        if not location:
            return False
        expected = PLACE_VISUAL.get(self.place_key, '').lower()
        return location.lower() in expected or location.lower() in (self.visual_location or '').lower()


class CameraWorldBuilder:
    """Builds camera constraints without advancing or writing world_state."""

    def __init__(self, db: DatabaseManager, *, stale_minutes: Optional[int] = None):
        self.db = db
        self.states = WorldStateRepository(db)
        self.bible = WorldBibleRepository(db)
        self.stale_minutes = stale_minutes or int(
            getattr(settings, 'WORLD_STATE_DEFAULT_STALE_MINUTES', 60))

    def build(self, now: datetime, user_request: str = '') -> CameraWorldContext:
        from calendar_world import CalendarWorld, local_time

        now = local_time(now)
        snapshot = self.states.latest()
        commitment = None
        if getattr(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            commitment = CalendarWorld(self.db).current(
                now, include_academic=getattr(settings, 'ACADEMIC_LIFE_ENABLED', False))

        place_key: Optional[str] = None
        activity: Optional[str] = None
        activity_source = 'unknown'
        snapshot_id: Optional[int] = None
        presence_assertable = False
        plan_blob: Optional[Mapping] = None
        people: tuple[str, ...] = ()
        weather: Optional[dict] = None
        snap_fresh = False
        snap_place: Optional[str] = None

        if snapshot:
            observed = datetime.fromisoformat(snapshot['observed_at'])
            same_day = observed.date() == now.date()
            age = now - observed
            snap_fresh = same_day and timedelta(0) <= age < timedelta(minutes=self.stale_minutes)
            snap_place = self._place_key_from_id(snapshot.get('location_place_id'))

        if commitment and commitment.get('place_key'):
            place_key = commitment['place_key']
            activity = commitment.get('activity')
            activity_source = 'confirmed_commitment'
            presence_assertable = True
            # Provenance: only keep snapshot_id when it actually supports this place.
            if snapshot and snap_fresh and snap_place == place_key:
                snapshot_id = snapshot['id']
                plan_blob = json.loads(snapshot.get('current_plan_json') or 'null')
                people = self._people(snapshot.get('active_people_json'))
                weather = self._weather_from_snapshot(snapshot)
            else:
                snapshot_id = None
        elif snapshot:
            source = json.loads(snapshot.get('source_json') or '{}')
            reason = source.get('reason') or 'inferred_routine'
            if snap_fresh:
                place_key = snap_place
                activity = snapshot.get('activity')
                activity_source = (
                    'confirmed_commitment' if reason == 'confirmed_commitment'
                    else 'explicit_plan' if reason == 'explicit_plan'
                    else 'inferred_routine')
                presence_assertable = place_key is not None
                plan_blob = json.loads(snapshot.get('current_plan_json') or 'null')
                people = self._people(snapshot.get('active_people_json'))
                weather = self._weather_from_snapshot(snapshot)
                snapshot_id = snapshot['id']
            else:
                # Stale: never assert presence; never treat snapshot weather as current.
                activity_source = 'stale_snapshot'
                snapshot_id = snapshot['id']
                weather = None
        else:
            activity_source = 'absent'

        if weather is None and getattr(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            weather = self._weather_from_cache(now)

        sublocation = self._explicit_sublocation(
            plan_blob, activity, user_request, place_key=place_key if presence_assertable else None)
        visual = PLACE_VISUAL.get(place_key, NEUTRAL_VISUAL) if place_key and presence_assertable else NEUTRAL_VISUAL
        if sublocation and presence_assertable and place_key in PLACES_WITH_ROOMS:
            visual = f'{visual}, {sublocation}'

        negatives = self._negatives(now, place_key, weather, presence_assertable)
        conflict, conflict_hint = self._request_conflict(user_request, place_key, presence_assertable)
        safe_tags = self._safe_scene_tags(visual, activity, now, weather, presence_assertable)
        director = self._director_restrictions(
            place_key, visual, activity, activity_source, now, weather,
            negatives, presence_assertable, conflict, conflict_hint)

        logger.info(
            'CAMERA_WORLD_CONTEXT place=%s assertable=%s source=%s conflict=%s snapshot=%s',
            place_key, presence_assertable, activity_source, conflict, snapshot_id,
        )
        return CameraWorldContext(
            snapshot_id=snapshot_id,
            place_key=place_key if presence_assertable else None,
            visual_location=visual if presence_assertable else NEUTRAL_VISUAL,
            sublocation=sublocation if presence_assertable else None,
            activity=activity if presence_assertable or activity_source == 'confirmed_commitment' else None,
            activity_source=activity_source,
            local_time=now,
            weather=weather,
            present_people=people,
            negative_constraints=tuple(negatives),
            presence_assertable=presence_assertable,
            request_conflict=conflict,
            conflict_hint=conflict_hint,
            safe_scene_tags=safe_tags,
            director_restrictions=director,
        )

    def sanitize_scene_tags(self, tags: str, ctx: CameraWorldContext) -> str:
        """Allowlist current place; reject any foreign destination geography."""
        text = (tags or '').strip()
        if not text:
            return ctx.safe_scene_tags

        # Conflict or unknown presence: never merge foreign destination into the prompt.
        if ctx.request_conflict or not ctx.presence_assertable:
            return ctx.safe_scene_tags

        if self._contains_foreign_destination(text, ctx.place_key):
            return ctx.safe_scene_tags

        hour = ctx.local_time.hour
        if hour >= 19 or hour < 6:
            text = re.sub(
                r'\b(midday sun|bright daylight|sunny noon|harsh noon sunlight)\b',
                'evening indoor light', text, flags=re.I)

        if ctx.weather and ctx.weather.get('heavy_rain'):
            if self._outdoors(ctx.place_key) and 'clear blue sky' in text.lower():
                text = re.sub(r'clear blue sky', 'overcast rainy sky', text, flags=re.I)

        # Anchor to the observed place without appending a second geography.
        anchor = (ctx.visual_location or '').split(',')[0].strip().lower()
        if anchor and anchor not in text.lower():
            text = f'{text}, {ctx.visual_location}'
        return text.strip(', ')

    def caption_facts(self, ctx: CameraWorldContext, scene_tags: str) -> str:
        """Only confirmed metadata for caption LLMs — no invented place/outfit/weather."""
        parts = []
        if ctx.presence_assertable and ctx.place_key:
            parts.append(f'local observado: {ctx.visual_location}')
        if ctx.activity:
            parts.append(f'atividade: {ctx.activity}')
        parts.append(f'hora local: {ctx.local_time.strftime("%H:%M")}')
        if ctx.weather and ctx.weather.get('heavy_rain') and self._outdoors(ctx.place_key):
            parts.append('chuva observada (relevante na cena)')
        if scene_tags:
            parts.append(f'tags confirmadas: {scene_tags[:160]}')
        return '; '.join(parts)

    def _contains_foreign_destination(self, tags: str, place_key: Optional[str]) -> bool:
        if not place_key:
            return True
        allowed = PLACE_CATEGORIES.get(place_key)
        lowered = tags.lower()
        for category, markers in CATEGORY_SCENE_MARKERS.items():
            if category == allowed:
                continue
            if any(marker in lowered for marker in markers):
                return True
        return False

    def _place_key_from_id(self, place_id: Optional[int]) -> Optional[str]:
        if place_id is None:
            return None
        with self.db.get_connection() as conn:
            row = conn.execute(
                'SELECT canonical_key FROM world_places WHERE id=?', (place_id,)
            ).fetchone()
        return row['canonical_key'] if row else None

    def _people(self, raw: Optional[str]) -> tuple[str, ...]:
        if not raw:
            return ()
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return ()
        if not isinstance(data, list):
            return ()
        names = []
        for item in data:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict) and item.get('canonical_key'):
                names.append(str(item['canonical_key']))
        return tuple(names[:4])

    def _weather_from_snapshot(self, snapshot: Mapping) -> Optional[dict]:
        raw = snapshot.get('weather_context_json')
        if not raw:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (TypeError, json.JSONDecodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _weather_from_cache(self, now: datetime) -> Optional[dict]:
        from calendar_world import CalendarWorld

        observed = CalendarWorld(self.db).context.get('weather:rio', now=now)
        if not observed:
            return None
        payload = observed.get('payload')
        return dict(payload) if isinstance(payload, dict) else None

    def _explicit_sublocation(
        self, plan: Optional[Mapping], activity: Optional[str], user_request: str,
        *, place_key: Optional[str],
    ) -> Optional[str]:
        if place_key not in PLACES_WITH_ROOMS:
            return None
        # Prefer plan/activity evidence; user_request alone is only valid at home places.
        trusted = ' '.join(filter(None, [
            json.dumps(plan, ensure_ascii=False) if plan else '',
            activity or '',
            user_request or '',
        ]))
        for pattern, label in ROOM_HINTS:
            if pattern.search(trusted) and label in HOME_SUBLOCATIONS:
                return label
        return None

    def _negatives(
        self, now: datetime, place_key: Optional[str], weather: Optional[dict],
        presence_assertable: bool,
    ) -> list[str]:
        negatives = ['photo studio backdrop', 'green screen', 'travel montage']
        hour = now.hour
        if hour >= 19 or hour < 6:
            negatives.extend(['midday sun', 'bright noon daylight sky', 'harsh midday sunlight'])
        if weather and weather.get('heavy_rain') and self._outdoors(place_key):
            negatives.extend(['clear blue sky', 'bright sunny beach weather'])
        if presence_assertable and place_key:
            allowed = PLACE_CATEGORIES.get(place_key)
            for category, markers in CATEGORY_SCENE_MARKERS.items():
                if category == allowed:
                    continue
                # Compact foreign-destination bans for the director.
                negatives.append(markers[0])
        if not presence_assertable:
            negatives.extend(['famous landmark', 'recognizable beach', 'named city skyline'])
        return negatives

    def _request_conflict(
        self, user_request: str, place_key: Optional[str], presence_assertable: bool,
    ) -> tuple[bool, str]:
        if not user_request or not presence_assertable or not place_key:
            return False, ''
        for pattern, allowed in REQUEST_PLACE_HINTS:
            if pattern.search(user_request) and place_key not in allowed:
                return True, (
                    'Patrick pediu um lugar diferente do estado atual. '
                    'Ofereça a foto no local atual ou peça se ele quer uma foto '
                    'antiga/imaginada — sem deslocar o world_state.'
                )
        return False, ''

    def _safe_scene_tags(
        self, visual: str, activity: Optional[str], now: datetime,
        weather: Optional[dict], presence_assertable: bool,
    ) -> str:
        parts = [visual if presence_assertable else NEUTRAL_VISUAL]
        if activity and presence_assertable:
            if 'faculdade' in activity or 'aula' in activity:
                parts.append('pausing briefly for a candid selfie')
            elif 'academia' in activity or 'treinando' in activity:
                parts.append('post-workout candid selfie, athletic wear')
            else:
                parts.append('candid natural expression')
        hour = now.hour
        if hour >= 19 or hour < 6:
            parts.append('evening or night lighting')
        elif 6 <= hour < 11:
            parts.append('soft morning light')
        if weather and weather.get('heavy_rain') and presence_assertable:
            parts.append('overcast rainy atmosphere visible only if outdoors or through a window')
        parts.append('fully clothed unless boyfriend explicitly requested otherwise')
        return ', '.join(parts)

    def _director_restrictions(
        self, place_key, visual, activity, source, now, weather, negatives,
        presence_assertable, conflict, conflict_hint,
    ) -> str:
        lines = [
            'CAMERA WORLD CONTINUITY — authoritative visual constraints:',
            f'- Local time (America/Sao_Paulo): {now.isoformat(timespec="minutes")}',
            f'- Activity source: {source}',
        ]
        if presence_assertable and place_key:
            lines.append(f'- Observed place_key: {place_key}')
            lines.append(f'- Allowed visual setting: {visual}')
            if activity:
                lines.append(f'- Activity (generic): {activity}')
        else:
            lines.append('- Current place is NOT assertable; use neutral indoor framing only.')
            lines.append('- Do NOT invent beach, campus, gym, bar or travel geography.')
        if weather and weather.get('heavy_rain'):
            lines.append('- Observed weather: heavy rain (only affect outdoor/window scenes).')
        elif weather is None:
            lines.append('- No valid weather observation; do NOT invent rain or clear skies.')
        lines.append('- Forbidden: ' + ', '.join(negatives))
        lines.append('- Do NOT invent a room (bedroom/bathroom/balcony) unless explicitly evidenced.')
        lines.append('- Patrick requesting another place does NOT authorize instant travel.')
        if conflict:
            lines.append(f'- CONFLICT: {conflict_hint}')
            lines.append('- Output tags for the CURRENT observed place only, or a neutral indoor selfie.')
        return '\n'.join(lines)

    @staticmethod
    def _outdoors(place_key: Optional[str]) -> bool:
        return place_key in {
            'enseada_botafogo', 'copacabana_beach', 'ipanema_beach', 'leblon_beach',
        }
