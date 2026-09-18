-- Only evidence-backed couple conventions live here. Shared facts remain in
-- knowledge_shares and conversations, rather than being copied into this table.
CREATE TABLE IF NOT EXISTS relationship_culture (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('nickname_for_patrick','ritual','inside_joke','shared_preference')),
    phrase TEXT NOT NULL,
    normalized_phrase TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    times_reinforced INTEGER NOT NULL DEFAULT 1 CHECK(times_reinforced >= 1),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    UNIQUE(kind, normalized_phrase)
);
CREATE TABLE IF NOT EXISTS relationship_culture_evidence (
    culture_id INTEGER NOT NULL REFERENCES relationship_culture(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    PRIMARY KEY(culture_id, conversation_id)
);
CREATE INDEX IF NOT EXISTS idx_relationship_culture_recent
    ON relationship_culture(active, last_seen_at DESC);
