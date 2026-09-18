"""Offline 30/90/365/1095-day seed simulations on disposable SQLite databases."""
from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from db import DatabaseManager  # noqa: E402
from seed_world_bible_v36 import seed_world_bible  # noqa: E402
from story_engine import StoryEngine  # noqa: E402


OBSERVED_CONTEXT = {
    'plan_cancelled_observed': True, 'favor_request_observed': True,
    'friend_needs_support': True, 'embarrassment_observed': True,
    'feedback_observed': True, 'home_issue_observed': True,
    'leisure_change_observed': True, 'weather_disruption_observed': True,
    'academic_feedback_observed': True, 'professional_feedback_observed': True,
    'disagreement_observed': True, 'help_received_observed': True,
    'forgotten_commitment_observed': True,
    'partner_gesture_observed': True, 'father_contact_observed': True,
    'rest_need_observed': True, 'relationship_committed': True,
    'academic_available': True, 'work_available': True,
}
OBSERVED_SIGNAL_KEYS = tuple(key for key in OBSERVED_CONTEXT if key.endswith('_observed') or key == 'friend_needs_support')
REALISTIC_DAILY_RATES = {
    # Assumptions for a scenario, not measurements of Marina's real life.
    'plan_cancelled_observed': 1 / 45,
    'favor_request_observed': 1 / 24,
    'friend_needs_support': 1 / 35,
    'embarrassment_observed': 1 / 45,
    'feedback_observed': 1 / 18,
    'home_issue_observed': 1 / 70,
    'leisure_change_observed': 1 / 45,
    'weather_disruption_observed': 1 / 28,
    'academic_feedback_observed': 1 / 21,
    'professional_feedback_observed': 1 / 45,
    'disagreement_observed': 1 / 65,
    'help_received_observed': 1 / 28,
    'forgotten_commitment_observed': 1 / 100,
    'partner_gesture_observed': 1 / 21,
}


def _stable_hit(now, key, probability):
    digest = hashlib.sha256(f'{now.date().isoformat()}:{key}:realistic-v1'.encode()).digest()
    return int.from_bytes(digest[:8], 'big') / 2**64 < probability


def realistic_context(now):
    """Sparse, reproducible observed context; never inferred from a real conversation."""
    academic_term = now.month in (2, 3, 4, 5, 6, 8, 9, 10, 11, 12)
    weekday = now.weekday()
    academic_day = academic_term and weekday < 5
    work_day = weekday in (1, 3) and _stable_hit(now, 'work_day', .65)
    context = {key: _stable_hit(now, key, rate) for key, rate in REALISTIC_DAILY_RATES.items()}
    context.update({
        'academic_available': academic_day,
        'work_available': work_day,
        'relationship_committed': True,
        'father_contact_observed': weekday in (1, 6) and _stable_hit(now, 'father_contact', .65),
        'rest_need_observed': weekday in (2, 6) and _stable_hit(now, 'rest_need', .5),
        'existing_plan': weekday in (4, 5) and _stable_hit(now, 'existing_plan', .5),
        'travel_planned': weekday < 5 and _stable_hit(now, 'travel_planned', .35),
        'purchase_planned': weekday == 5 and _stable_hit(now, 'purchase_planned', .5),
        'ordinary_task': weekday < 5 and _stable_hit(now, 'ordinary_task', .6),
        'calendar_busy': weekday < 5 and _stable_hit(now, 'calendar_busy', .15),
        'heavy_rain': _stable_hit(now, 'heavy_rain', .08),
    })
    if not academic_day:
        context['academic_feedback_observed'] = False
    if not work_day:
        context['professional_feedback_observed'] = False
    context['energy'] = .35 if context['rest_need_observed'] else .7
    return context


def simulate_scenario(days, context_provider):
    start = datetime(2026, 1, 1, 12)
    with tempfile.TemporaryDirectory(prefix='marina_story_sim_') as temp:
        db = DatabaseManager(Path(temp) / 'simulation.db')
        seed_world_bible(db)
        with patch.object(settings, 'STORY_SEED_LIBRARY_ENABLED', True):
            engine = StoryEngine(db)
        snapshots = {}
        signal_counts = Counter()
        observed_context_days = 0
        for offset in range(days):
            now = start + timedelta(days=offset)
            context = context_provider(now) if callable(context_provider) else context_provider
            observed = [key for key in OBSERVED_SIGNAL_KEYS if context.get(key)]
            signal_counts.update(observed)
            observed_context_days += bool(observed)
            engine.daily_tick(now, context=context)
            if offset + 1 in (30, 90, 365, 1095):
                with db.get_connection() as conn:
                    events = conn.execute("SELECT event_type,importance FROM life_events WHERE source_type='simulated'").fetchall()
                    active = conn.execute("SELECT COUNT(*) FROM story_threads WHERE status='open'").fetchone()[0]
                    snapshots[str(offset + 1)] = {
                        'banal_day_ratio': round(1 - len(events) / (offset + 1), 3),
                        'events': len(events), 'active_threads': active,
                        'major_events': sum(row['importance'] >= .7 for row in events),
                        'seed_repetition': dict(Counter(row['event_type'] for row in events)),
                        'observed_context_days': observed_context_days,
                        'observed_signal_days': dict(sorted(signal_counts.items())),
                    }
        return snapshots


def simulate():
    report = {'baseline': simulate_scenario(1095, {}),
              'realistic_context': simulate_scenario(1095, realistic_context),
              'contextual_stress': simulate_scenario(1095, OBSERVED_CONTEXT)}
    baseline = report['baseline']['1095']
    realistic = report['realistic_context']['1095']
    stress = report['contextual_stress']['1095']
    report['checks'] = {
        'no_major_events': all(scenario['major_events'] == 0 for scenario in (baseline, realistic, stress)),
        'ordinary_days_predominate': min(scenario['banal_day_ratio'] for scenario in (baseline, realistic, stress)) >= .88,
        'context_increases_variety_without_event_pressure': (
            len(stress['seed_repetition']) > len(baseline['seed_repetition'])
            and stress['events'] <= baseline['events']),
        'realistic_observation_exposure_between_extremes': (
            baseline['observed_context_days'] < realistic['observed_context_days']
            < stress['observed_context_days']),
    }
    report['realistic_context_assumptions'] = {
        'status': 'illustrative deterministic scenario, not observed personal history',
        'daily_observation_probabilities': REALISTIC_DAILY_RATES,
        'academic_period': 'weekday in February-June or August-December',
        'professional_availability': 'Tuesday/Thursday, 65 percent of those days',
        'father_contact': 'Tuesday/Sunday, 65 percent of those days',
        'rest_need': 'Wednesday/Sunday, 50 percent of those days; never inferred from cycle phase',
        'relationship_status': 'committed; a gesture still requires its own observed signal',
    }
    return report


if __name__ == '__main__':
    result = simulate()
    path = ROOT / 'data' / 'story_seeds' / 'simulation_report.v1.json'
    path.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    print(path)
    if not all(result['checks'].values()):
        raise SystemExit('Story seed simulation check failed')
