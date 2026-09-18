"""Read-only-source smoke of the real canonical DB under production flags.

Copies the live SQLite database to a disposable file; no Telegram or provider
request is sent, and no conversation is added to the live database.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import Settings, settings
from context_builder import ContextBuilder
from db import DatabaseManager
from memory import MemoryManager
from pending_response import ResponseAvailabilityService
from world_repository import WorldStateRepository


def main() -> int:
    source = Path(os.environ.get('MARINA_DB_PATH') or ROOT / 'marin_memory.db').resolve()
    if not source.is_file():
        raise RuntimeError('Live database not found')
    errors = Settings.validate()
    if errors:
        raise RuntimeError('Invalid settings: ' + '; '.join(errors))
    if not settings.LIVING_WORLD_ENABLED or not settings.RESPONSE_AVAILABILITY_ENABLED:
        raise RuntimeError('Production shadow flags are not enabled')
    if settings.HUMAN_REPLY_LATENCY_ENABLED != settings.PENDING_CONVERSATION_BATCHING_ENABLED:
        raise RuntimeError('Latency and batching flags must move together')
    mode = 'enforce' if settings.HUMAN_REPLY_LATENCY_ENABLED else 'shadow'

    with tempfile.TemporaryDirectory(prefix='marina_shadow_smoke_') as temp:
        copy_path = Path(temp) / 'world.db'
        with closing(sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(copy_path)) as dest:
                src.backup(dest)
        db = DatabaseManager(copy_path)
        with db.get_connection() as conn:
            before = conn.execute('SELECT COUNT(*) FROM response_pending_batches').fetchone()[0]
            canon = conn.execute(
                "SELECT COUNT(*) FROM world_characters WHERE canon_locked=1"
            ).fetchone()[0]
            academic = conn.execute(
                "SELECT COUNT(*) FROM academic_profile WHERE character_key='marina'"
            ).fetchone()[0]
            telemetry_before = conn.execute(
                'SELECT COUNT(*) FROM response_availability_events'
            ).fetchone()[0]
        if canon == 0 or academic != 1:
            raise RuntimeError('Canonical world or academic profile missing')

        now = datetime.now()
        prompt = ContextBuilder(memory_mgr=MemoryManager(db)).build_system_prompt(
            user_message='oi amor', now=now)
        if '[WORLD STATE' not in prompt or '[VIDA ACADÊMICA]' not in prompt:
            raise RuntimeError('Integrated world/academic context missing')

        svc = ResponseAvailabilityService(db)
        actions = []
        if mode == 'shadow':
            for message_id, message in ((98765001, 'oi amor'),
                                        (98765002, 'me conta do seu dia com calma')):
                action, decision, batch = svc.evaluate_and_maybe_defer(
                    message, telegram_message_id=message_id, now=now)
                if action not in ('proceed', 'proceed_brief') or batch is not None:
                    raise RuntimeError('Shadow mode deferred a message')
                actions.append({'action': action, 'activity': decision.activity_type,
                                'source': decision.activity_source})
        else:
            with db.get_connection() as conn:
                place = conn.execute(
                    "SELECT id, region FROM world_places WHERE canonical_key='puc_rio'"
                ).fetchone()
            WorldStateRepository(db).add_snapshot({
                'state_date': now.date().isoformat(), 'observed_at': now.isoformat(),
                'location_place_id': place['id'], 'location_region': place['region'],
                'activity': 'em aula', 'energy_level': 0.5,
                'source_json': {'reason': 'confirmed_commitment'},
            })
            action, decision, batch = svc.evaluate_and_maybe_defer(
                'me conta detalhadamente o que aconteceu no projeto e o que você pensa sobre tudo?',
                telegram_message_id=98765003, now=now)
            if action != 'deferred' or not batch:
                raise RuntimeError('Enforcement did not defer the class-time reply')
            actions.append({'action': action, 'activity': decision.activity_type,
                            'source': decision.activity_source})
            from datetime import timedelta
            urgent_at = now + timedelta(minutes=1)
            action, decision, merged = svc.evaluate_and_maybe_defer(
                'amor preciso falar contigo agora',
                telegram_message_id=98765004, now=urgent_at)
            if action != 'deferred' or merged['id'] != batch['id']:
                raise RuntimeError('Urgent follow-up did not merge into pending batch')
            claimed = svc.repo.claim_due(urgent_at, owner='smoke')
            if not claimed or claimed['id'] != batch['id']:
                raise RuntimeError('Urgent batch was not ready to send')
            if len(svc.repo.list_items(batch['id'])) != 2:
                raise RuntimeError('Pending batch lost a user message')
            if not svc.repo.mark_sent(batch['id'], sent_message_id=98765999):
                raise RuntimeError('Confirmed simulated send did not close batch')
            actions.append({'action': 'urgent_merge_and_simulated_send',
                            'activity': decision.activity_type,
                            'source': decision.activity_source})
        with db.get_connection() as conn:
            after = conn.execute('SELECT COUNT(*) FROM response_pending_batches').fetchone()[0]
            telemetry = conn.execute(
                'SELECT COUNT(*) FROM response_availability_events'
            ).fetchone()[0]
        expected_batches = before + (1 if mode == 'enforce' else 0)
        if after != expected_batches or telemetry - telemetry_before < 2:
            raise RuntimeError('Queue or telemetry contract failed')

    print(json.dumps({'release': '3.7.0', 'mode': mode, 'status': 'passed',
                      'world_canon_count': canon, 'academic_profile_count': academic,
                      'actions': actions, 'queue_delta': after - before,
                      'telemetry_events_in_copy': telemetry - telemetry_before},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
