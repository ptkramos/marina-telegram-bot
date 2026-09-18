CREATE TABLE social_relationships (
    character_key TEXT PRIMARY KEY REFERENCES world_characters(canonical_key),
    relationship_type TEXT NOT NULL,
    canon_locked INTEGER NOT NULL DEFAULT 0 CHECK(canon_locked IN (0,1)),
    closeness REAL NOT NULL DEFAULT 0 CHECK(closeness BETWEEN 0 AND 1),
    trust REAL NOT NULL DEFAULT 0 CHECK(trust BETWEEN 0 AND 1),
    contact_frequency INTEGER NOT NULL DEFAULT 0,
    recent_tension REAL NOT NULL DEFAULT 0 CHECK(recent_tension BETWEEN 0 AND 1),
    recent_positive_interactions INTEGER NOT NULL DEFAULT 0,
    last_interaction_at TEXT
);
CREATE TABLE social_place_links (
    character_key TEXT NOT NULL REFERENCES world_characters(canonical_key),
    place_key TEXT NOT NULL REFERENCES world_places(canonical_key),
    context TEXT NOT NULL,
    PRIMARY KEY(character_key, place_key)
);
CREATE TABLE social_evidence (
    evidence_key TEXT PRIMARY KEY,
    character_key TEXT REFERENCES world_characters(canonical_key),
    place_key TEXT REFERENCES world_places(canonical_key),
    occurred_at TEXT NOT NULL,
    valence REAL NOT NULL CHECK(valence BETWEEN -1 AND 1),
    meaningful INTEGER NOT NULL CHECK(meaningful IN (0,1)),
    CHECK(character_key IS NOT NULL OR place_key IS NOT NULL)
);
CREATE TABLE social_place_state (
    place_key TEXT PRIMARY KEY REFERENCES world_places(canonical_key),
    familiarity TEXT NOT NULL CHECK(familiarity IN ('discovered','known','habitual','favorite','occasional'))
);
CREATE TABLE preference_evidence (
    evidence_key TEXT PRIMARY KEY,
    preference_id INTEGER NOT NULL REFERENCES character_preferences(id),
    occurred_at TEXT NOT NULL
);
