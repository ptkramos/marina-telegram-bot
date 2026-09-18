-- One dated commitment store: extend the existing Calendar/Events table.
ALTER TABLE eventos_pendentes ADD COLUMN owner_character_key TEXT NOT NULL DEFAULT 'patrick_ramos';
ALTER TABLE eventos_pendentes ADD COLUMN end_at TEXT;
ALTER TABLE eventos_pendentes ADD COLUMN location_key TEXT;
ALTER TABLE eventos_pendentes ADD COLUMN source_key TEXT;
ALTER TABLE eventos_pendentes ADD COLUMN story_thread_id INTEGER REFERENCES story_threads(id);
ALTER TABLE eventos_pendentes ADD COLUMN confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed IN (0,1));
ALTER TABLE eventos_pendentes ADD COLUMN metadata_json TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_source_key ON eventos_pendentes(source_key)
    WHERE source_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calendar_owner_time
    ON eventos_pendentes(owner_character_key,status,event_at);
CREATE INDEX IF NOT EXISTS idx_calendar_thread
    ON eventos_pendentes(story_thread_id,status,event_at);

CREATE TABLE IF NOT EXISTS real_context_cache (
    context_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('weather','holiday')),
    payload_json TEXT NOT NULL,
    source_name TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    CHECK(observed_at < expires_at)
);
