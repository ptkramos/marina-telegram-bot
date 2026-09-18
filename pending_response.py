"""Persistent pending conversational batches for v3.7.0 Response Availability."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import json
import logging
import sqlite3
from typing import Optional

from config import settings
from db import DatabaseManager
from response_availability import (
    ResponseAvailabilityDecision,
    ResponseAvailabilityPolicy,
    local_naive,
    local_now,
)


logger = logging.getLogger(__name__)
ACTIVE_STATUSES = ('PENDING', 'READY')
CONVERSATION_KEY = 'patrick_marina'


class PendingResponseRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_active_batch(self, conversation_key: str = CONVERSATION_KEY) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM response_pending_batches
                   WHERE conversation_key=? AND status IN ('PENDING','READY')
                   ORDER BY id DESC LIMIT 1""",
                (conversation_key,),
            ).fetchone()
        return dict(row) if row else None

    def find_telegram_item(self, telegram_message_id: Optional[int]) -> Optional[dict]:
        if telegram_message_id is None:
            return None
        with self.db.get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM response_pending_batch_items WHERE telegram_message_id=? LIMIT 1',
                (telegram_message_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_batch(self, batch_id: int) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute('SELECT * FROM response_pending_batches WHERE id=?',
                               (batch_id,)).fetchone()
        return dict(row) if row else None

    def has_sending_batch(self, conversation_key: str = CONVERSATION_KEY) -> bool:
        with self.db.get_connection() as conn:
            return conn.execute(
                "SELECT 1 FROM response_pending_batches WHERE conversation_key=? AND status='SENDING' LIMIT 1",
                (conversation_key,),
            ).fetchone() is not None

    def enqueue_item(self, decision: ResponseAvailabilityDecision, *, message: str,
                     telegram_message_id: Optional[int], received_at: datetime) -> tuple[dict, bool, bool]:
        """Persist conversation, batch and membership as one serialized unit."""
        with self.db.transaction():
            replay = self.find_telegram_item(telegram_message_id)
            if replay:
                with self.db.get_connection() as conn:
                    batch = conn.execute('SELECT * FROM response_pending_batches WHERE id=?',
                                         (replay['batch_id'],)).fetchone()
                return dict(batch), False, False
            active = self.get_active_batch()
            if active is None:
                batch = self._create_batch_in_transaction(decision, now=received_at)
            else:
                batch = active
            conversation_id = self.db.adicionar_mensagem(
                role='user', content=message, media_type='text',
                timestamp=received_at.isoformat(),
            )
            if not self.add_item(
                batch['id'], conversation_message_id=conversation_id,
                telegram_message_id=telegram_message_id, received_at=received_at,
            ):
                raise RuntimeError('Pending item insert unexpectedly rejected')
            if active is not None:
                batch = self.update_decision(batch['id'], decision, merged=True, now=received_at)
            return batch, True, active is not None

    def create_batch(self, decision: ResponseAvailabilityDecision,
                     *, conversation_key: str = CONVERSATION_KEY) -> dict:
        with self.db.transaction():
            return self._create_batch_in_transaction(decision, conversation_key=conversation_key)

    def _create_batch_in_transaction(self, decision: ResponseAvailabilityDecision,
                                     *, conversation_key: str = CONVERSATION_KEY,
                                     now: Optional[datetime] = None) -> dict:
        now = local_naive(local_now(now))
        active_key = f'{conversation_key}:active'
        with self.db.get_connection() as conn:
                existing = conn.execute(
                    """SELECT id FROM response_pending_batches
                       WHERE active_key=? AND status IN ('PENDING','READY')""",
                    (active_key,),
                ).fetchone()
                if existing:
                    raise ValueError('Active pending batch already exists')
                cursor = conn.execute(
                    """INSERT INTO response_pending_batches(
                        conversation_key,active_key,status,created_at,updated_at,decision,
                        reason_code,activity_type,activity_source,urgency_max,response_complexity,
                        eligible_after,target_window_start,target_window_end,selected_target_at,
                        expires_at,context_snapshot_id,arrival_activity,arrival_source,
                        decision_seed,decision_version,created_by_version)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        conversation_key, active_key, 'PENDING', now.isoformat(), now.isoformat(),
                        decision.decision, decision.reason_code, decision.activity_type,
                        decision.activity_source, decision.message_urgency,
                        decision.response_complexity,
                        decision.earliest_reply_at.isoformat(),
                        decision.target_window_start.isoformat(),
                        decision.target_window_end.isoformat(),
                        decision.selected_target_at.isoformat(),
                        (decision.selected_target_at + timedelta(hours=12)).isoformat(),
                        decision.context_snapshot_id, decision.activity_type,
                        decision.activity_source, decision.decision_seed, 1, '3.7.0',
                    ),
                )
                return dict(conn.execute(
                    'SELECT * FROM response_pending_batches WHERE id=?',
                    (cursor.lastrowid,),
                ).fetchone())

    def add_item(self, batch_id: int, *, conversation_message_id: int,
                 telegram_message_id: Optional[int], received_at: datetime) -> bool:
        with self.db.get_connection() as conn:
            ordinal = conn.execute(
                'SELECT COALESCE(MAX(ordinal),0)+1 FROM response_pending_batch_items WHERE batch_id=?',
                (batch_id,),
            ).fetchone()[0]
            try:
                conn.execute(
                    """INSERT INTO response_pending_batch_items(
                        batch_id,conversation_message_id,telegram_message_id,received_at,ordinal)
                       VALUES (?,?,?,?,?)""",
                    (batch_id, conversation_message_id, telegram_message_id,
                     received_at.isoformat(), ordinal),
                )
                return True
            except sqlite3.IntegrityError as exc:
                # Only an actual replay is a no-op; never swallow broken foreign keys.
                if 'UNIQUE constraint failed' in str(exc):
                    return False
                raise

    def update_decision(self, batch_id: int, decision: ResponseAvailabilityDecision,
                        *, merged: bool = False, now: Optional[datetime] = None) -> dict:
        now = local_naive(local_now(now))
        with self.db.get_connection() as conn:
            row = conn.execute(
                'SELECT decision_version FROM response_pending_batches WHERE id=?',
                (batch_id,),
            ).fetchone()
            version = int(row['decision_version']) + 1
            due_now = decision.selected_target_at <= now
            conn.execute(
                """UPDATE response_pending_batches SET
                    updated_at=?, decision=?, reason_code=?, activity_type=?, activity_source=?,
                    urgency_max=?, response_complexity=?, eligible_after=?,
                    target_window_start=?, target_window_end=?, selected_target_at=?,
                    expires_at=?, context_snapshot_id=?, decision_seed=?, decision_version=?,
                    status=CASE
                        WHEN status='SENDING' THEN status
                        WHEN ? THEN 'READY'
                        ELSE 'PENDING'
                    END
                   WHERE id=?""",
                (
                    now.isoformat(), decision.decision, decision.reason_code,
                    decision.activity_type, decision.activity_source, decision.message_urgency,
                    decision.response_complexity, decision.earliest_reply_at.isoformat(),
                    decision.target_window_start.isoformat(), decision.target_window_end.isoformat(),
                    decision.selected_target_at.isoformat(),
                    (decision.selected_target_at + timedelta(hours=12)).isoformat(),
                    decision.context_snapshot_id, decision.decision_seed, version,
                    1 if due_now else 0, batch_id,
                ),
            )
            if merged:
                pass
            return dict(conn.execute(
                'SELECT * FROM response_pending_batches WHERE id=?', (batch_id,)
            ).fetchone())

    def list_items(self, batch_id: int) -> list[dict]:
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                """SELECT i.*, c.content, c.role
                   FROM response_pending_batch_items i
                   JOIN conversas c ON c.id=i.conversation_message_id
                   WHERE i.batch_id=?
                   ORDER BY i.ordinal, i.id""",
                (batch_id,),
            ).fetchall()]

    def mark_ready_due(self, now: datetime) -> int:
        now_s = local_naive(now).isoformat()
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """UPDATE response_pending_batches
                   SET status='READY', updated_at=?
                   WHERE status='PENDING' AND selected_target_at<=?""",
                (now_s, now_s),
            )
            return cur.rowcount

    def claim_due(self, now: datetime, *, owner: str, lease_seconds: int = 120) -> Optional[dict]:
        now_dt = local_naive(now)
        now_s = now_dt.isoformat()
        lease_until = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            # Expired SENDING leases → UNKNOWN_DELIVERY (never blind-resend).
            conn.execute(
                """UPDATE response_pending_batches
                   SET status='UNKNOWN_DELIVERY', last_error='expired_lease_no_resend',
                       lease_owner=NULL, lease_until=NULL, updated_at=?,
                       active_key=printf('patrick_marina:closed:%s', id)
                   WHERE status='SENDING' AND (lease_until IS NULL OR lease_until<=?)""",
                (now_s, now_s),
            )
            if conn.execute(
                """SELECT 1 FROM response_pending_batches
                   WHERE conversation_key=? AND status='SENDING' LIMIT 1""",
                (CONVERSATION_KEY,),
            ).fetchone():
                conn.commit()
                return None
            row = conn.execute(
                """SELECT * FROM response_pending_batches
                   WHERE (status='READY' AND selected_target_at<=?)
                      OR (status='PENDING' AND selected_target_at<=?)
                   ORDER BY selected_target_at ASC, id ASC LIMIT 1""",
                (now_s, now_s),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            cur = conn.execute(
                """UPDATE response_pending_batches
                   SET status='SENDING', lease_owner=?, lease_until=?, updated_at=?,
                       active_key=printf('patrick_marina:sending:%s', id)
                   WHERE id=? AND status IN ('READY','PENDING')""",
                (owner, lease_until, now_s, row['id']),
            )
            conn.commit()
            if cur.rowcount != 1:
                return None
            return dict(conn.execute(
                'SELECT * FROM response_pending_batches WHERE id=?', (row['id'],)
            ).fetchone())

    def mark_sent(self, batch_id: int, *, sent_message_id: int) -> bool:
        now_dt = local_naive(local_now())
        now_s = now_dt.isoformat()
        with self.db.get_connection() as conn:
            batch_row = conn.execute(
                "SELECT created_at FROM response_pending_batches WHERE id=?", (batch_id,)
            ).fetchone()
            cur = conn.execute(
                """UPDATE response_pending_batches
                   SET status='SENT', sent_message_id=?, lease_owner=NULL, lease_until=NULL,
                       updated_at=?, last_error=NULL,
                       active_key=printf('patrick_marina:closed:%s', id)
                   WHERE id=? AND status='SENDING'""",
                (sent_message_id, now_s, batch_id),
            )
            if cur.rowcount == 1 and batch_row and batch_row['created_at']:
                try:
                    c_dt = datetime.fromisoformat(batch_row['created_at'])
                    actual_lat = max(0.0, (now_dt - c_dt).total_seconds())
                    conn.execute(
                        """UPDATE response_availability_events
                           SET actual_latency_seconds=?
                           WHERE batch_id=? AND actual_latency_seconds IS NULL""",
                        (round(float(actual_lat), 2), batch_id),
                    )
                except Exception:
                    logger.exception("Failed to update actual_latency on mark_sent for batch %s", batch_id)
            return cur.rowcount == 1

    def extend_lease(self, batch_id: int, *, owner: str, now: datetime,
                     lease_seconds: int = 120) -> bool:
        now_dt = local_naive(now)
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """UPDATE response_pending_batches
                   SET lease_until=?, updated_at=?
                   WHERE id=? AND status='SENDING' AND lease_owner=?""",
                ((now_dt + timedelta(seconds=lease_seconds)).isoformat(),
                 now_dt.isoformat(), batch_id, owner),
            )
            return cur.rowcount == 1

    def mark_failed_retry(self, batch_id: int, error: str, *, max_retries: int = 3) -> str:
        now_s = local_naive(local_now()).isoformat()
        with self.db.get_connection() as conn:
            row = conn.execute(
                'SELECT retry_count, status FROM response_pending_batches WHERE id=?', (batch_id,)
            ).fetchone()
            if not row or row['status'] != 'SENDING':
                return row['status'] if row else 'MISSING'
            retries = int(row['retry_count']) + 1 if row else 1
            if retries >= max_retries:
                status = 'FAILED'
                conn.execute(
                    """UPDATE response_pending_batches
                       SET status=?, retry_count=?, last_error=?, lease_owner=NULL, lease_until=NULL,
                           updated_at=?, active_key=printf('patrick_marina:closed:%s', id)
                       WHERE id=?""",
                    (status, retries, error[:500], now_s, batch_id),
                )
            else:
                status = 'READY'
                conn.execute(
                    """UPDATE response_pending_batches
                       SET status=?, retry_count=?, last_error=?, lease_owner=NULL, lease_until=NULL,
                           updated_at=?
                       WHERE id=?""",
                    (status, retries, error[:500], now_s, batch_id),
                )
            return status

    def mark_unknown_delivery(self, batch_id: int, reason: str) -> None:
        now_s = local_naive(local_now()).isoformat()
        with self.db.get_connection() as conn:
            conn.execute(
                """UPDATE response_pending_batches
                   SET status='UNKNOWN_DELIVERY', last_error=?, lease_owner=NULL, lease_until=NULL,
                       updated_at=?, active_key=printf('patrick_marina:closed:%s', id)
                   WHERE id=? AND status='SENDING'""",
                (reason[:500], now_s, batch_id),
            )

    def supersede(self, batch_id: int, reason: str = 'superseded') -> None:
        now_s = local_naive(local_now()).isoformat()
        with self.db.get_connection() as conn:
            conn.execute(
                """UPDATE response_pending_batches
                   SET status='SUPERSEDED', last_error=?, updated_at=?, lease_owner=NULL, lease_until=NULL,
                       active_key=printf('patrick_marina:closed:%s', id)
                   WHERE id=? AND status IN ('PENDING','READY','SENDING')""",
                (reason[:500], now_s, batch_id),
            )

    def recover_on_startup(self, now: datetime) -> dict:
        now_dt = local_naive(now)
        now_s = now_dt.isoformat()
        stats = {'ready': 0, 'unknown': 0, 'kept_pending': 0}
        with self.db.get_connection() as conn:
            # Earlier workers may have claimed before SENDING released active_key.
            conn.execute(
                """UPDATE response_pending_batches
                   SET active_key=printf('patrick_marina:sending:%s', id)
                   WHERE status='SENDING'"""
            )
            # Expired leases in SENDING → UNKNOWN_DELIVERY (do not blind-resend).
            cur = conn.execute(
                """UPDATE response_pending_batches
                   SET status='UNKNOWN_DELIVERY', last_error='startup_expired_lease',
                       lease_owner=NULL, lease_until=NULL, updated_at=?,
                       active_key=printf('patrick_marina:closed:%s', id)
                   WHERE status='SENDING' AND (lease_until IS NULL OR lease_until<=?)""",
                (now_s, now_s),
            )
            stats['unknown'] = cur.rowcount
            cur = conn.execute(
                """UPDATE response_pending_batches
                   SET status='READY', updated_at=?
                   WHERE status='PENDING' AND selected_target_at<=?""",
                (now_s, now_s),
            )
            stats['ready'] = cur.rowcount
            stats['kept_pending'] = conn.execute(
                "SELECT COUNT(*) FROM response_pending_batches WHERE status='PENDING'"
            ).fetchone()[0]
        return stats

    def force_ready_on_rollback(self, now: Optional[datetime] = None) -> int:
        """Flags OFF: make pending batches immediately processable."""
        now_s = local_naive(local_now(now)).isoformat()
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """UPDATE response_pending_batches
                   SET status='READY', selected_target_at=?, updated_at=?
                   WHERE status IN ('PENDING','READY')""",
                (now_s, now_s),
            )
            return cur.rowcount

    def record_event(self, decision: ResponseAvailabilityDecision, *, batch_id=None,
                     pending_count=0, merged=False, urgent_override=False,
                     actual_latency_seconds=None, error_flag=None) -> Optional[int]:
        if not getattr(settings, 'REAL_USAGE_TELEMETRY_ENABLED', False) and not getattr(
                settings, 'RESPONSE_AVAILABILITY_ENABLED', False):
            return None
        target = max(0.0, (decision.selected_target_at - decision.earliest_reply_at).total_seconds())
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO response_availability_events(
                    batch_id,timestamp,decision,reason_code,activity_type,activity_source,
                    context_freshness,urgency,response_complexity,target_latency_seconds,
                    actual_latency_seconds,pending_message_count,batch_merged,urgent_override,
                    decision_version,release_version,error_flag)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    batch_id, local_naive(local_now()).isoformat(), decision.decision,
                    decision.reason_code, decision.activity_type, decision.activity_source,
                    decision.world_state_freshness, decision.message_urgency,
                    decision.response_complexity, target, actual_latency_seconds,
                    pending_count, int(merged), int(urgent_override), 1, '3.7.0', error_flag,
                ),
            )
            return cur.lastrowid

    def record_actual_latency(
        self,
        *,
        event_id: Optional[int] = None,
        batch_id: Optional[int] = None,
        actual_latency_seconds: float,
    ) -> None:
        """Update actual_latency_seconds on telemetry events once response is delivered."""
        with self.db.get_connection() as conn:
            if event_id is not None:
                conn.execute(
                    """UPDATE response_availability_events
                       SET actual_latency_seconds=?
                       WHERE id=?""",
                    (round(float(actual_latency_seconds), 2), event_id),
                )
            elif batch_id is not None:
                conn.execute(
                    """UPDATE response_availability_events
                       SET actual_latency_seconds=?
                       WHERE batch_id=? AND actual_latency_seconds IS NULL""",
                    (round(float(actual_latency_seconds), 2), batch_id),
                )


class ResponseAvailabilityService:
    """Gate between debounce and full reply pipeline."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.policy = ResponseAvailabilityPolicy(db)
        self.repo = PendingResponseRepository(db)

    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, 'RESPONSE_AVAILABILITY_ENABLED', False))

    @property
    def enforce_latency(self) -> bool:
        return (self.enabled
                and bool(getattr(settings, 'HUMAN_REPLY_LATENCY_ENABLED', False))
                and bool(getattr(settings, 'PENDING_CONVERSATION_BATCHING_ENABLED', False)))

    def evaluate_and_maybe_defer(
        self,
        message: str,
        *,
        telegram_message_id: Optional[int],
        now: Optional[datetime] = None,
        plan: Optional[dict] = None,
        batch_size: int = 1,
    ) -> tuple[str, Optional[ResponseAvailabilityDecision], Optional[dict]]:
        """
        Returns (action, decision, batch):
          action in {'proceed', 'proceed_brief', 'deferred', 'legacy'}
        Fail-open → legacy.
        """
        if not self.enabled:
            if self.repo.get_active_batch():
                self.repo.force_ready_on_rollback()
            return 'legacy', None, None
        replay = self.repo.find_telegram_item(telegram_message_id)
        if replay:
            return 'deferred', None, self.repo.get_batch(replay['batch_id'])
        try:
            decision = self.policy.evaluate(
                message, now=now, telegram_message_id=telegram_message_id,
                plan=plan, batch_size=batch_size,
            )
        except Exception as exc:
            logger.error('AVAILABILITY_POLICY_ERROR %s', exc, exc_info=True)
            return 'legacy', None, None

        # Shadow mode: telemetry only, never defer.
        if decision.shadow_only or not self.enforce_latency:
            ev_id = self._record_event_safely(decision, pending_count=0)
            if ev_id is not None:
                decision = replace(decision, telemetry_event_id=ev_id)
            if decision.decision == 'REPLY_BRIEFLY':
                return 'proceed_brief', decision, None
            return 'proceed', decision, None

        # Active deferred batch: always append + recalculate (never parallel reply).
        active = self.repo.get_active_batch()
        if active:
            now_dt = local_naive(local_now(now))
            merged = True
            urgent_override = False
            prev_urgency = active['urgency_max']
            decision = self.policy.evaluate(
                message, now=now_dt, telegram_message_id=telegram_message_id,
                plan=plan, batch_size=batch_size + 1,
                seed=f"{active['decision_seed']}:v{active['decision_version']+1}",
            )
            rank = {'LOW': 0, 'NORMAL': 1, 'HIGH': 2, 'CRITICAL': 3}
            max_urgency = decision.message_urgency
            if rank.get(prev_urgency, 1) > rank.get(max_urgency, 1):
                max_urgency = prev_urgency
            if max_urgency in ('HIGH', 'CRITICAL') and prev_urgency in ('LOW', 'NORMAL'):
                urgent_override = True
            if urgent_override or decision.decision != 'DEFER':
                decision = ResponseAvailabilityDecision(
                    decision=decision.decision if decision.decision != 'DEFER' else 'REPLY_BRIEFLY',
                    phone_access=decision.phone_access,
                    attention_level=decision.attention_level,
                    interruptibility=decision.interruptibility,
                    message_urgency=max_urgency,
                    response_complexity=decision.response_complexity,
                    activity_type=decision.activity_type,
                    activity_source=decision.activity_source,
                    reason_code='urgent_recalc' if urgent_override else decision.reason_code,
                    earliest_reply_at=now_dt,
                    target_window_start=now_dt,
                    target_window_end=now_dt + timedelta(minutes=5),
                    selected_target_at=now_dt,
                    context_snapshot_id=decision.context_snapshot_id,
                    world_state_freshness=decision.world_state_freshness,
                    decision_seed=decision.decision_seed,
                    can_claim_activity=decision.can_claim_activity,
                    shadow_only=False,
                )
            elif max_urgency != decision.message_urgency:
                decision = ResponseAvailabilityDecision(
                    decision=decision.decision,
                    phone_access=decision.phone_access,
                    attention_level=decision.attention_level,
                    interruptibility=decision.interruptibility,
                    message_urgency=max_urgency,
                    response_complexity=decision.response_complexity,
                    activity_type=decision.activity_type,
                    activity_source=decision.activity_source,
                    reason_code=decision.reason_code,
                    earliest_reply_at=decision.earliest_reply_at,
                    target_window_start=decision.target_window_start,
                    target_window_end=decision.target_window_end,
                    selected_target_at=decision.selected_target_at,
                    context_snapshot_id=decision.context_snapshot_id,
                    world_state_freshness=decision.world_state_freshness,
                    decision_seed=decision.decision_seed,
                    can_claim_activity=decision.can_claim_activity,
                    shadow_only=False,
                )
            original_deadline = datetime.fromisoformat(active['target_window_end'])
            if decision.selected_target_at > original_deadline:
                decision = replace(
                    decision, selected_target_at=original_deadline,
                    target_window_end=original_deadline,
                    reason_code=f'{decision.reason_code}_original_guardrail',
                )
            elif decision.target_window_end > original_deadline:
                decision = replace(decision, target_window_end=original_deadline)
            batch, added, merged = self.repo.enqueue_item(
                decision, message=message, telegram_message_id=telegram_message_id,
                received_at=now_dt,
            )
            if added:
                ev_id = self._record_event_safely(
                    decision, batch_id=batch['id'], pending_count=self._pending_count_safely(batch['id']),
                    merged=merged, urgent_override=urgent_override,
                )
                if ev_id is not None:
                    decision = replace(decision, telemetry_event_id=ev_id)
            return 'deferred', decision, batch

        if decision.decision in ('REPLY_NOW', 'REPLY_BRIEFLY') and not self.repo.has_sending_batch():
            ev_id = self._record_event_safely(decision, pending_count=0)
            if ev_id is not None:
                decision = replace(decision, telemetry_event_id=ev_id)
            return ('proceed_brief' if decision.decision == 'REPLY_BRIEFLY' else 'proceed'), decision, None

        # DEFER, or hold a new message behind a batch already being sent.
        now_dt = local_naive(local_now(now))
        batch, added, merged = self.repo.enqueue_item(
            decision, message=message, telegram_message_id=telegram_message_id,
            received_at=now_dt,
        )
        if added:
            ev_id = self._record_event_safely(
                decision, batch_id=batch['id'], pending_count=self._pending_count_safely(batch['id']),
                merged=merged, urgent_override=False,
            )
            if ev_id is not None:
                decision = replace(decision, telemetry_event_id=ev_id)
        return 'deferred', decision, batch

    def _pending_count_safely(self, batch_id: int) -> int:
        try:
            return len(self.repo.list_items(batch_id))
        except Exception:
            logger.exception('AVAILABILITY_PENDING_COUNT_ERROR batch=%s', batch_id)
            return 1

    def _record_event_safely(self, decision: ResponseAvailabilityDecision, **kwargs) -> Optional[int]:
        try:
            return self.repo.record_event(decision, **kwargs)
        except Exception:
            logger.exception('AVAILABILITY_TELEMETRY_ERROR')
            return None

    def compose_batch_text(self, batch_id: int) -> str:
        items = self.repo.list_items(batch_id)
        return '\n'.join(i['content'] for i in items if i.get('role') == 'user').strip()

    def startup_recover(self, now: Optional[datetime] = None) -> dict:
        return self.repo.recover_on_startup(local_now(now))
