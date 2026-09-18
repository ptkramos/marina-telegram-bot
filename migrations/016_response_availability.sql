-- v3.7.0 Response Availability: pending conversational batches + telemetry.
-- Operational only; not autobiographical memory.

CREATE TABLE IF NOT EXISTS response_pending_batches (
    id INTEGER PRIMARY KEY,
    conversation_key TEXT NOT NULL,
    active_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN (
        'PENDING','READY','SENDING','SENT','SUPERSEDED','CANCELLED','UNKNOWN_DELIVERY','FAILED'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('REPLY_NOW','REPLY_BRIEFLY','DEFER')),
    reason_code TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    activity_source TEXT NOT NULL,
    urgency_max TEXT NOT NULL CHECK(urgency_max IN ('LOW','NORMAL','HIGH','CRITICAL')),
    response_complexity TEXT NOT NULL CHECK(response_complexity IN ('SHORT','NORMAL','LONG')),
    eligible_after TEXT,
    target_window_start TEXT,
    target_window_end TEXT,
    selected_target_at TEXT,
    expires_at TEXT,
    context_snapshot_id INTEGER,
    arrival_activity TEXT,
    arrival_source TEXT,
    decision_seed TEXT NOT NULL,
    decision_version INTEGER NOT NULL DEFAULT 1,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    lease_owner TEXT,
    lease_until TEXT,
    followup_candidate INTEGER NOT NULL DEFAULT 0 CHECK(followup_candidate IN (0,1)),
    created_by_version TEXT NOT NULL DEFAULT '3.7.0',
    sent_message_id INTEGER,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_response_pending_status
    ON response_pending_batches(status, selected_target_at);
CREATE INDEX IF NOT EXISTS idx_response_pending_conversation
    ON response_pending_batches(conversation_key, status);

CREATE TABLE IF NOT EXISTS response_pending_batch_items (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES response_pending_batches(id) ON DELETE CASCADE,
    conversation_message_id INTEGER NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    telegram_message_id INTEGER,
    received_at TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    UNIQUE(batch_id, conversation_message_id),
    UNIQUE(batch_id, telegram_message_id)
);
CREATE INDEX IF NOT EXISTS idx_response_pending_items_batch
    ON response_pending_batch_items(batch_id, ordinal);

CREATE TABLE IF NOT EXISTS response_availability_events (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER,
    timestamp TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    activity_source TEXT NOT NULL,
    context_freshness TEXT,
    urgency TEXT NOT NULL,
    response_complexity TEXT NOT NULL,
    target_latency_seconds REAL,
    actual_latency_seconds REAL,
    pending_message_count INTEGER,
    batch_merged INTEGER NOT NULL DEFAULT 0 CHECK(batch_merged IN (0,1)),
    urgent_override INTEGER NOT NULL DEFAULT 0 CHECK(urgent_override IN (0,1)),
    decision_version INTEGER,
    release_version TEXT NOT NULL DEFAULT '3.7.0',
    error_flag TEXT,
    detail_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_response_availability_events_ts
    ON response_availability_events(timestamp DESC, id DESC);
