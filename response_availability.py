"""Deterministic Response Availability & Human Latency (v3.7.0).

Interprets WorldState/Calendar certainty into WHEN/HOW-MUCH to reply.
Does not invent activity, mutate WorldState, or replace Planner/Rhythm.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import logging
import re
from typing import Optional
from zoneinfo import ZoneInfo

from config import settings
from db import DatabaseManager
from world_repository import WorldStateRepository


logger = logging.getLogger(__name__)
LOCAL_ZONE = ZoneInfo('America/Sao_Paulo')
DECISION_VERSION = '3.7.0'

LEVELS = ('LOW', 'MEDIUM', 'HIGH')
URGENCIES = ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')
COMPLEXITIES = ('SHORT', 'NORMAL', 'LONG')
DECISIONS = ('REPLY_NOW', 'REPLY_BRIEFLY', 'DEFER')

# Soft profiles — calibration knobs, not canon.
DEFAULT_PROFILES = {
    'HOME_RELAXING': {
        'phone_access': 'HIGH', 'attention': 'HIGH', 'interruptibility': 'HIGH',
        'soft_delay_min_s': 0, 'soft_delay_max_s': 90, 'guardrail_s': 300,
        'brief_likelihood': 0.05, 'prefer': 'REPLY_NOW',
    },
    'COMMUTE': {
        'phone_access': 'HIGH', 'attention': 'HIGH', 'interruptibility': 'HIGH',
        'soft_delay_min_s': 5, 'soft_delay_max_s': 120, 'guardrail_s': 600,
        'brief_likelihood': 0.25, 'prefer': 'REPLY_NOW',
    },
    'GYM': {
        'phone_access': 'HIGH', 'attention': 'MEDIUM', 'interruptibility': 'MEDIUM',
        'soft_delay_min_s': 60, 'soft_delay_max_s': 900, 'guardrail_s': 1500,
        'brief_likelihood': 0.45, 'prefer': 'MIXED',
    },
    'CLASS': {
        'phone_access': 'HIGH', 'attention': 'LOW', 'interruptibility': 'LOW',
        'soft_delay_min_s': 120, 'soft_delay_max_s': 1800, 'guardrail_s': 2700,
        'brief_likelihood': 0.35, 'prefer': 'DEFER',
    },
    'CASTING': {
        'phone_access': 'MEDIUM', 'attention': 'LOW', 'interruptibility': 'LOW',
        'soft_delay_min_s': 180, 'soft_delay_max_s': 2400, 'guardrail_s': 3600,
        'brief_likelihood': 0.4, 'prefer': 'DEFER',
    },
    'WORK': {
        'phone_access': 'MEDIUM', 'attention': 'MEDIUM', 'interruptibility': 'MEDIUM',
        'soft_delay_min_s': 60, 'soft_delay_max_s': 1200, 'guardrail_s': 2700,
        'brief_likelihood': 0.35, 'prefer': 'MIXED',
    },
    'SOCIAL': {
        'phone_access': 'HIGH', 'attention': 'MEDIUM', 'interruptibility': 'MEDIUM',
        'soft_delay_min_s': 60, 'soft_delay_max_s': 1200, 'guardrail_s': 1800,
        'brief_likelihood': 0.3, 'prefer': 'MIXED',
    },
    'SLEEPING': {
        'phone_access': 'LOW', 'attention': 'LOW', 'interruptibility': 'LOW',
        'soft_delay_min_s': 1800, 'soft_delay_max_s': 28800, 'guardrail_s': 36000,
        'brief_likelihood': 0.0, 'prefer': 'DEFER',
    },
    'UNKNOWN': {
        'phone_access': 'HIGH', 'attention': 'HIGH', 'interruptibility': 'HIGH',
        'soft_delay_min_s': 0, 'soft_delay_max_s': 120, 'guardrail_s': 300,
        'brief_likelihood': 0.05, 'prefer': 'REPLY_NOW',
    },
}


def local_now(value: Optional[datetime] = None) -> datetime:
    value = value or datetime.now(LOCAL_ZONE)
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_ZONE)
    return value.astimezone(LOCAL_ZONE)


def local_naive(value: datetime) -> datetime:
    aware = local_now(value)
    return aware.replace(tzinfo=None)


@dataclass(frozen=True)
class ResponseAvailabilityDecision:
    decision: str
    phone_access: str
    attention_level: str
    interruptibility: str
    message_urgency: str
    response_complexity: str
    activity_type: str
    activity_source: str
    reason_code: str
    earliest_reply_at: datetime
    target_window_start: datetime
    target_window_end: datetime
    selected_target_at: datetime
    context_snapshot_id: Optional[int]
    world_state_freshness: str
    decision_seed: str
    decision_version: str = DECISION_VERSION
    can_claim_activity: bool = False
    shadow_only: bool = False
    telemetry_event_id: Optional[int] = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        for key in ('earliest_reply_at', 'target_window_start', 'target_window_end', 'selected_target_at'):
            payload[key] = getattr(self, key).isoformat()
        return payload


class ResponseAvailabilityPolicy:
    """Deterministic availability; fail-open callers must catch exceptions."""

    def __init__(self, db: DatabaseManager, *, stale_minutes: Optional[int] = None):
        self.db = db
        self.states = WorldStateRepository(db)
        self.stale_minutes = stale_minutes or int(
            getattr(settings, 'WORLD_STATE_DEFAULT_STALE_MINUTES', 60))
        self.profiles = getattr(settings, 'RESPONSE_AVAILABILITY_PROFILES', None) or DEFAULT_PROFILES

    def evaluate(
        self,
        message: str,
        *,
        now: Optional[datetime] = None,
        conversation_key: str = 'patrick',
        telegram_message_id: Optional[int] = None,
        batch_size: int = 1,
        plan: Optional[dict] = None,
        seed: Optional[str] = None,
    ) -> ResponseAvailabilityDecision:
        now = local_now(now)
        urgency = classify_urgency(message, plan=plan)
        complexity = classify_complexity(message, plan=plan, batch_size=batch_size)
        activity_type, activity_source, snapshot_id, freshness, can_claim = self._resolve_activity(now)
        profile = dict(self.profiles.get(activity_type) or self.profiles['UNKNOWN'])

        # Soft routine must not drive long DEFER or factual activity claims.
        if activity_source == 'ROUTINE_PROBABILITY':
            profile['soft_delay_max_s'] = min(int(profile['soft_delay_max_s']), 180)
            profile['guardrail_s'] = min(int(profile['guardrail_s']), 300)
            can_claim = False
        if freshness != 'fresh' or activity_type == 'UNKNOWN':
            profile = dict(self.profiles['UNKNOWN'])
            activity_type = 'UNKNOWN'
            activity_source = 'UNKNOWN'
            can_claim = False

        decision, reason = self._choose_decision(profile, urgency, complexity, activity_type)
        seed_value = seed or self._seed(conversation_key, telegram_message_id, now, message)
        delay_s = self._pick_delay_seconds(profile, urgency, decision, seed_value)
        if activity_type == 'UNKNOWN':
            delay_s = min(delay_s, 120)
        if urgency in ('HIGH', 'CRITICAL') and decision != 'REPLY_NOW':
            delay_s = min(delay_s, 180 if urgency == 'HIGH' else 30)
            if urgency == 'CRITICAL':
                decision = 'REPLY_NOW' if activity_type != 'SLEEPING' else 'REPLY_BRIEFLY'
                reason = 'critical_override'
                delay_s = 0 if decision == 'REPLY_NOW' else min(delay_s, 60)

        target = local_naive(now) + timedelta(seconds=delay_s)
        window_start = local_naive(now) + timedelta(seconds=max(0, int(profile['soft_delay_min_s'])))
        window_end = local_naive(now) + timedelta(seconds=int(profile['guardrail_s']))
        if target > window_end:
            target = window_end
        if target < window_start and decision == 'DEFER':
            target = window_start

        shadow = bool(getattr(settings, 'RESPONSE_AVAILABILITY_ENABLED', False)
                      and not getattr(settings, 'HUMAN_REPLY_LATENCY_ENABLED', False))

        result = ResponseAvailabilityDecision(
            decision=decision,
            phone_access=profile['phone_access'],
            attention_level=profile['attention'],
            interruptibility=profile['interruptibility'],
            message_urgency=urgency,
            response_complexity=complexity,
            activity_type=activity_type,
            activity_source=activity_source,
            reason_code=reason,
            earliest_reply_at=local_naive(now),
            target_window_start=window_start,
            target_window_end=window_end,
            selected_target_at=target,
            context_snapshot_id=snapshot_id,
            world_state_freshness=freshness,
            decision_seed=seed_value,
            can_claim_activity=can_claim,
            shadow_only=shadow,
        )
        logger.info(
            'AVAILABILITY_DECISION decision=%s activity=%s source=%s urgency=%s delay_s=%s shadow=%s',
            decision, activity_type, activity_source, urgency, delay_s, shadow,
        )
        return result

    def _resolve_activity(self, now: datetime) -> tuple[str, str, Optional[int], str, bool]:
        now_naive = local_naive(now)
        commitment = None
        if getattr(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            from calendar_world import CalendarWorld, local_time
            commitment = CalendarWorld(self.db).current(
                local_time(now_naive),
                include_academic=getattr(settings, 'ACADEMIC_LIFE_ENABLED', False),
            )
        if commitment:
            mapped = self._map_place_activity(
                commitment.get('place_key'), commitment.get('activity') or '')
            return mapped, 'CONFIRMED_COMMITMENT', None, 'fresh', True

        snapshot = self.states.latest()
        if not snapshot:
            return 'UNKNOWN', 'UNKNOWN', None, 'absent', False
        observed = datetime.fromisoformat(snapshot['observed_at'])
        same_day = observed.date() == now_naive.date()
        age = now_naive - observed
        fresh = same_day and timedelta(0) <= age < timedelta(minutes=self.stale_minutes)
        if not fresh:
            return 'UNKNOWN', 'UNKNOWN', snapshot['id'], 'stale', False

        place_key = self._place_key(snapshot.get('location_place_id'))
        activity = snapshot.get('activity') or ''
        source = json.loads(snapshot.get('source_json') or '{}')
        reason = source.get('reason') or ''
        mapped = self._map_place_activity(place_key, activity)
        if reason == 'confirmed_commitment':
            return mapped, 'CONFIRMED_COMMITMENT', snapshot['id'], 'fresh', True
        if reason == 'explicit_plan':
            return mapped, 'WORLD_STATE', snapshot['id'], 'fresh', True
        # Routine / free_time: soft signal only.
        return mapped, 'ROUTINE_PROBABILITY', snapshot['id'], 'fresh', False

    def _place_key(self, place_id: Optional[int]) -> Optional[str]:
        if place_id is None:
            return None
        with self.db.get_connection() as conn:
            row = conn.execute(
                'SELECT canonical_key FROM world_places WHERE id=?', (place_id,)
            ).fetchone()
        return row['canonical_key'] if row else None

    def _map_place_activity(self, place_key: Optional[str], activity: str) -> str:
        text = f'{place_key or ""} {activity}'.casefold()
        if any(x in text for x in ('dorm', 'sleep', 'sono')):
            return 'SLEEPING'
        if place_key == 'puc_rio' or 'faculdade' in text or 'aula' in text:
            return 'CLASS'
        if place_key == 'bodytech_sao_clemente' or 'academia' in text or 'treinando' in text:
            return 'GYM'
        if place_key == 'boutique_agency' or 'casting' in text or 'ensaio' in text:
            return 'CASTING'
        if any(x in text for x in ('uber', 'metrô', 'metro', 'ônibus', 'onibus', 'desloc')):
            return 'COMMUTE'
        if place_key in ('quartinho_bar',) or 'bar' in text or 'com amig' in text:
            return 'SOCIAL'
        if place_key == 'marina_apartment' or 'casa' in text or 'apartamento' in text:
            return 'HOME_RELAXING'
        if 'trabalho' in text or 'freela' in text:
            return 'WORK'
        return 'UNKNOWN'

    def _choose_decision(self, profile, urgency, complexity, activity_type) -> tuple[str, str]:
        prefer = profile.get('prefer', 'REPLY_NOW')
        brief_p = float(profile.get('brief_likelihood', 0.1))
        if urgency == 'CRITICAL' and activity_type != 'SLEEPING':
            return 'REPLY_NOW', 'critical_now'
        if urgency == 'HIGH' and activity_type != 'SLEEPING':
            return ('REPLY_BRIEFLY' if prefer == 'DEFER' else 'REPLY_NOW'), 'high_urgency'
        if activity_type == 'SLEEPING':
            return 'DEFER', 'sleeping'
        if prefer == 'REPLY_NOW':
            if complexity == 'LONG' and brief_p > 0.4:
                return 'REPLY_BRIEFLY', 'home_brief_long'
            return 'REPLY_NOW', f'{activity_type.lower()}_available'
        if prefer == 'DEFER':
            if complexity == 'SHORT' and urgency == 'NORMAL':
                return 'REPLY_BRIEFLY', f'{activity_type.lower()}_brief_ok'
            return 'DEFER', f'{activity_type.lower()}_busy'
        # MIXED
        if complexity == 'SHORT':
            return 'REPLY_BRIEFLY', f'{activity_type.lower()}_brief'
        if urgency == 'LOW':
            return 'DEFER', f'{activity_type.lower()}_low_stakes'
        return 'REPLY_BRIEFLY' if brief_p >= 0.4 else 'DEFER', f'{activity_type.lower()}_mixed'

    def _pick_delay_seconds(self, profile, urgency, decision, seed: str) -> int:
        if decision == 'REPLY_NOW':
            lo, hi = 0, min(45, int(profile['soft_delay_max_s']))
        elif decision == 'REPLY_BRIEFLY':
            lo = int(profile['soft_delay_min_s'])
            hi = min(int(profile['soft_delay_max_s']), max(lo + 30, 300))
        else:
            lo = int(profile['soft_delay_min_s'])
            hi = int(profile['soft_delay_max_s'])
        if urgency == 'HIGH':
            hi = min(hi, 180)
            lo = min(lo, 30)
        if urgency == 'CRITICAL':
            return 0
        if hi <= lo:
            return lo
        digest = hashlib.sha256(seed.encode()).digest()
        ratio = int.from_bytes(digest[:8], 'big') / 2**64
        return int(lo + (hi - lo) * ratio)

    @staticmethod
    def _seed(conversation_key, telegram_message_id, now, message) -> str:
        stamp = local_naive(now).isoformat(timespec='minutes')
        # Keep decision seeds reproducible without copying conversation text into
        # operational queue metadata or telemetry.
        digest = hashlib.sha256((message or '').encode('utf-8')).hexdigest()[:16]
        return f'{conversation_key}:{telegram_message_id or 0}:{stamp}:{digest}'


def classify_urgency(message: str, *, plan: Optional[dict] = None) -> str:
    text = (message or '').casefold()
    plan = plan or {}
    if plan.get('intent') in ('urgent', 'relationship_conflict') or plan.get('urgency') == 'critical':
        return 'CRITICAL' if 'emerg' in text or 'perigo' in text else 'HIGH'
    if re.search(
        r'\b(emerg[eê]ncia|socorro|perigo|me ajuda agora|urgente agora|ligue? (?:pra|para) mim agora)\b',
        text,
    ):
        return 'CRITICAL'
    if re.search(
        r'\b(preciso falar(?: contigo| com voc[eê])?|aconteceu uma coisa s[eé]ria|'
        r'temos que conversar|preciso de voc[eê] agora|é s[eé]rio|urgente)\b',
        text,
    ):
        return 'HIGH'
    if re.search(r'^(kk+|haha+|😂+|🤣+|ok+|valeu+|tmj+)\s*$', text.strip()):
        return 'LOW'
    if len(text) < 12 and not text.endswith('?'):
        return 'LOW'
    return 'NORMAL'


def classify_complexity(message: str, *, plan: Optional[dict] = None, batch_size: int = 1) -> str:
    text = message or ''
    plan = plan or {}
    questions = text.count('?')
    if (re.search(r'\b(detalhadamente|me explica|passo a passo|em detalhes)\b', text.casefold())
            or plan.get('intent') == 'explanatory' or len(text) > 500 or questions >= 3):
        return 'LONG'
    if len(text) < 40 and questions <= 1 and batch_size <= 1:
        return 'SHORT'
    return 'NORMAL'
