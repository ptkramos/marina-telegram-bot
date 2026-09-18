-- Extend the existing short-lived context cache; no second Calendar/Events store.
CREATE TABLE real_context_cache_v2 (
    context_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('weather','holiday','holiday_year','place_fact','place_negative')),
    payload_json TEXT NOT NULL,
    source_name TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    CHECK(observed_at < expires_at)
);
INSERT INTO real_context_cache_v2
    (context_key,kind,payload_json,source_name,observed_at,expires_at)
    SELECT context_key,kind,payload_json,source_name,observed_at,expires_at
    FROM real_context_cache;
DROP TABLE real_context_cache;
ALTER TABLE real_context_cache_v2 RENAME TO real_context_cache;
