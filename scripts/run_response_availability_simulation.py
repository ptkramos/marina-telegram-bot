"""Synthetic Response Availability simulation (24h / 72h / 7d) for stage 15."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import settings
from db import DatabaseManager
from pending_response import ResponseAvailabilityService
from seed_world_bible_v36 import seed_world_bible
from world_repository import WorldStateRepository


SCENARIOS = {
    '24h': 24,
    '72h': 72,
    '7d': 24 * 7,
}

ACTIVITY_CYCLE = [
    ('marina_apartment', 'em casa', 'explicit_plan'),
    ('puc_rio', 'em aula', 'confirmed_commitment'),
    ('bodytech_sao_clemente', 'treinando', 'confirmed_commitment'),
    ('marina_apartment', 'deslocamento uber', 'explicit_plan'),
    ('quartinho_bar', 'com amigas', 'explicit_plan'),
    ('marina_apartment', 'dormindo', 'explicit_plan'),
]

MESSAGES = [
    ('oi amor', False),
    ('kkkk', False),
    ('me conta do seu dia com calma e detalhes porque quero saber tudo', False),
    ('amor preciso falar contigo', True),
    ('socorro emergência me ajuda agora', True),
    ('tudo bem?', False),
]


def _place(db, key):
    with db.get_connection() as conn:
        return conn.execute(
            'SELECT id, region FROM world_places WHERE canonical_key=?', (key,)
        ).fetchone()


def _set_activity(db, now, place_key, activity, reason):
    place = _place(db, place_key)
    WorldStateRepository(db).add_snapshot({
        'state_date': now.date().isoformat(),
        'observed_at': now.isoformat(),
        'location_place_id': place['id'] if place else None,
        'location_region': place['region'] if place else None,
        'activity': activity,
        'energy_level': 0.6,
        'source_json': {'reason': reason},
    })


def run_hours(hours: int) -> dict:
    temp = tempfile.TemporaryDirectory()
    db = DatabaseManager(Path(temp.name) / 'sim.db')
    seed_world_bible(db)
    svc = ResponseAvailabilityService(db)
    start = datetime(2026, 9, 18, 8, 0)
    flags = dict(
        RESPONSE_AVAILABILITY_ENABLED=True,
        HUMAN_REPLY_LATENCY_ENABLED=True,
        PENDING_CONVERSATION_BATCHING_ENABLED=True,
        REAL_USAGE_TELEMETRY_ENABLED=True,
    )
    decisions = {'REPLY_NOW': 0, 'REPLY_BRIEFLY': 0, 'DEFER': 0}
    empty_batches = 0
    duplicate_claims = 0
    sent = 0
    user_msgs = 0
    max_pending_age = 0.0
    inflight_successor_checked = False

    def drain(now):
        nonlocal sent, empty_batches, duplicate_claims, max_pending_age
        nonlocal user_msgs, inflight_successor_checked
        svc.repo.mark_ready_due(now)
        while True:
            claimed = svc.repo.claim_due(now, owner=f'sim-{now.isoformat()}')
            if not claimed:
                break
            if not inflight_successor_checked:
                # Intake during SENDING must create a successor, never mutate the claimed batch.
                user_msgs += 1
                action, _, successor = svc.evaluate_and_maybe_defer(
                    'cheguei agora, pode responder depois',
                    telegram_message_id=900000 + hours, now=now,
                )
                if action != 'deferred' or not successor or successor['id'] == claimed['id']:
                    duplicate_claims += 1
                inflight_successor_checked = True
            text = svc.compose_batch_text(claimed['id'])
            if not text:
                empty_batches += 1
                svc.repo.supersede(claimed['id'], 'empty')
                continue
            age = (now - datetime.fromisoformat(claimed['created_at'])).total_seconds()
            max_pending_age = max(max_pending_age, age)
            if svc.repo.mark_sent(claimed['id'], sent_message_id=5000 + claimed['id']):
                sent += 1
            else:
                duplicate_claims += 1

    with patch.multiple(settings, **flags):
        for hour in range(hours):
            now = start + timedelta(hours=hour)
            place_key, activity, reason = ACTIVITY_CYCLE[hour % len(ACTIVITY_CYCLE)]
            _set_activity(db, now, place_key, activity, reason)

            if hour == hours // 2:
                svc.startup_recover(now)

            msg, _ = MESSAGES[hour % len(MESSAGES)]
            user_msgs += 1
            action, decision, batch = svc.evaluate_and_maybe_defer(
                msg, telegram_message_id=1000 + hour, now=now,
            )
            if decision:
                decisions[decision.decision] = decisions.get(decision.decision, 0) + 1

            if hour % 24 == 1 and action == 'deferred' and batch:
                # A genuine urgent follow-up must upgrade the existing wait.
                user_msgs += 1
                _, urgent_decision, _ = svc.evaluate_and_maybe_defer(
                    'amor preciso falar contigo agora',
                    telegram_message_id=200000 + hour,
                    now=now + timedelta(minutes=1),
                )
                if urgent_decision:
                    decisions[urgent_decision.decision] = (
                        decisions.get(urgent_decision.decision, 0) + 1)

            for minute in (0, 15, 30, 45):
                drain(now + timedelta(minutes=minute))

        # Continue ordinary scheduler ticks; no forced rollback or end-of-run drain.
        end = start + timedelta(hours=hours)
        for tick in range(12 * 4):
            drain(end + timedelta(minutes=15 * tick))

        with db.get_connection() as conn:
            stuck = conn.execute(
                "SELECT COUNT(*) FROM response_pending_batches WHERE status IN ('PENDING','READY','SENDING')"
            ).fetchone()[0]
            users_stored = conn.execute(
                "SELECT COUNT(*) FROM conversas WHERE role='user'"
            ).fetchone()[0]
            deferred_messages = conn.execute(
                'SELECT COUNT(*) FROM response_pending_batch_items'
            ).fetchone()[0]
            sent_messages = conn.execute(
                """SELECT COUNT(*) FROM response_pending_batch_items i
                   JOIN response_pending_batches b ON b.id=i.batch_id
                   WHERE b.status='SENT'"""
            ).fetchone()[0]
            merges = conn.execute(
                'SELECT COUNT(*) FROM response_availability_events WHERE batch_merged=1'
            ).fetchone()[0]
            urgent_overrides = conn.execute(
                'SELECT COUNT(*) FROM response_availability_events WHERE urgent_override=1'
            ).fetchone()[0]

    lost = deferred_messages - sent_messages + empty_batches
    duplicates = duplicate_claims
    guardrail_exceeded = max_pending_age > 11 * 3600

    temp.cleanup()
    return {
        'hours': hours,
        'user_messages': user_msgs,
        'users_persisted_on_defer_path': users_stored,
        'deferred_messages': deferred_messages,
        'deferred_messages_delivered': sent_messages,
        'decisions': decisions,
        'sent_batches': sent,
        'lost_messages': lost,
        'duplicate_replies': duplicates,
        'stuck_pending': stuck,
        'batch_merges_events': merges,
        'urgent_override_events': urgent_overrides,
        'max_pending_age_seconds': max_pending_age,
        'guardrail_exceeded': guardrail_exceeded,
        'inflight_successor_checked': inflight_successor_checked,
        'pass': (lost == 0 and duplicates == 0 and stuck == 0
                 and not guardrail_exceeded and inflight_successor_checked
                 and urgent_overrides > 0),
    }


def main(argv: list[str]) -> int:
    labels = argv[1:] or ['24h', '72h', '7d']
    simulations = {}
    overall = True
    for label in labels:
        hours = SCENARIOS.get(label)
        if hours is None:
            print(f'Unknown scenario {label}', file=sys.stderr)
            return 2
        payload = run_hours(hours)
        simulations[label] = payload
        overall = overall and payload['pass']
    out = {
        'release': '3.7.0',
        'finished_at': datetime.utcnow().isoformat() + 'Z',
        'simulations': simulations,
        'status': 'passed' if overall else 'failed',
    }
    path = ROOT / 'data' / 'response_availability_simulation.v370.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                    encoding='utf-8')
    print(path)
    return 0 if overall else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
