-- v3.6.7 World Hygiene: archive + audit log. No second authority layer.
CREATE TABLE IF NOT EXISTS life_events_archive (
    id INTEGER PRIMARY KEY,
    original_event_id INTEGER NOT NULL,
    event_key TEXT,
    event_at TEXT NOT NULL,
    end_at TEXT,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_type TEXT NOT NULL,
    autonomy_level INTEGER NOT NULL,
    importance REAL NOT NULL,
    emotional_valence REAL NOT NULL DEFAULT 0,
    location_place_id INTEGER,
    participants_json TEXT,
    thread_id INTEGER,
    consequence_of_event_id INTEGER,
    share_worthy REAL NOT NULL DEFAULT 0,
    resolved INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    compacted_at TEXT NOT NULL,
    compact_reason TEXT NOT NULL,
    UNIQUE(original_event_id)
);
CREATE INDEX IF NOT EXISTS idx_life_events_archive_time ON life_events_archive(event_at DESC);

CREATE TABLE IF NOT EXISTS world_hygiene_log (
    id INTEGER PRIMARY KEY,
    ran_at TEXT NOT NULL,
    action TEXT NOT NULL,
    subject_type TEXT,
    subject_key TEXT,
    reason_code TEXT NOT NULL,
    detail_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_world_hygiene_log_ran ON world_hygiene_log(ran_at DESC, id DESC);
