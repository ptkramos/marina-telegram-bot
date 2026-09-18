-- Living World v3.6: storage only. Canonical data is seeded in a separate step.
CREATE TABLE IF NOT EXISTS world_characters (
    id INTEGER PRIMARY KEY,
    canonical_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    character_type TEXT NOT NULL CHECK(character_type IN ('marina', 'close_npc', 'recurring', 'secondary', 'ephemeral')),
    birth_date TEXT,
    home_region TEXT,
    occupation TEXT,
    relationship_to_marina TEXT,
    personality_json TEXT,
    story_tendencies_json TEXT,
    initial_state_json TEXT,
    canon_locked INTEGER NOT NULL DEFAULT 0 CHECK(canon_locked IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_places (
    id INTEGER PRIMARY KEY,
    canonical_key TEXT UNIQUE,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    place_type TEXT NOT NULL,
    truth_type TEXT NOT NULL CHECK(truth_type IN ('canonical', 'real_world', 'simulated')),
    familiarity TEXT NOT NULL CHECK(familiarity IN ('discovered', 'known', 'habitual', 'favorite')),
    distance_class TEXT,
    associated_characters_json TEXT,
    usage_rules_json TEXT,
    canon_locked INTEGER NOT NULL DEFAULT 0 CHECK(canon_locked IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_state (
    id INTEGER PRIMARY KEY,
    state_date TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    location_place_id INTEGER REFERENCES world_places(id) ON DELETE SET NULL,
    location_region TEXT,
    activity TEXT,
    energy_level REAL CHECK(energy_level BETWEEN 0 AND 1),
    social_drive REAL CHECK(social_drive BETWEEN 0 AND 1),
    stress_level REAL CHECK(stress_level BETWEEN 0 AND 1),
    physical_comfort REAL CHECK(physical_comfort BETWEEN 0 AND 1),
    weather_context_json TEXT,
    active_people_json TEXT,
    active_threads_json TEXT,
    current_plan_json TEXT,
    source_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_world_state_observed ON world_state(observed_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS story_threads (
    id INTEGER PRIMARY KEY,
    thread_key TEXT NOT NULL UNIQUE,
    thread_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('open', 'dormant', 'resolved', 'abandoned')),
    importance REAL NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1),
    started_at TEXT NOT NULL,
    last_event_at TEXT NOT NULL,
    resolution_json TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_story_threads_status ON story_threads(status, last_event_at);

CREATE TABLE IF NOT EXISTS life_events (
    id INTEGER PRIMARY KEY,
    event_key TEXT UNIQUE,
    event_at TEXT NOT NULL,
    end_at TEXT,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('canonical', 'real_world', 'simulated', 'user_shared', 'system')),
    autonomy_level INTEGER NOT NULL CHECK(autonomy_level BETWEEN 1 AND 4),
    importance REAL NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1),
    emotional_valence REAL NOT NULL DEFAULT 0 CHECK(emotional_valence BETWEEN -1 AND 1),
    location_place_id INTEGER REFERENCES world_places(id) ON DELETE SET NULL,
    participants_json TEXT,
    thread_id INTEGER REFERENCES story_threads(id) ON DELETE SET NULL,
    consequence_of_event_id INTEGER REFERENCES life_events(id) ON DELETE SET NULL,
    share_worthy REAL NOT NULL DEFAULT 0 CHECK(share_worthy BETWEEN 0 AND 1),
    resolved INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0, 1)),
    metadata_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_life_events_time ON life_events(event_at DESC);
CREATE INDEX IF NOT EXISTS idx_life_events_thread ON life_events(thread_id, event_at);

CREATE TABLE IF NOT EXISTS knowledge_items (
    id INTEGER PRIMARY KEY,
    subject_type TEXT NOT NULL CHECK(subject_type IN ('event', 'fact', 'thread', 'relationship')),
    subject_id INTEGER NOT NULL,
    holder_character_key TEXT NOT NULL,
    source_character_key TEXT,
    source_chain_json TEXT,
    privacy_level TEXT NOT NULL CHECK(privacy_level IN ('PRIVATE_SELF', 'PRIVATE_COUPLE', 'CONFIDENTIAL', 'CLOSE_CIRCLE', 'PUBLIC_SOCIAL')),
    permission_json TEXT,
    safe_metadata_json TEXT,
    learned_at TEXT NOT NULL,
    revoked_at TEXT,
    UNIQUE(subject_type, subject_id, holder_character_key)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_holder ON knowledge_items(holder_character_key, revoked_at);

CREATE TABLE IF NOT EXISTS knowledge_shares (
    id INTEGER PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    from_character_key TEXT NOT NULL,
    to_character_key TEXT NOT NULL,
    shared_at TEXT NOT NULL,
    detail_level TEXT,
    explicit_permission INTEGER NOT NULL DEFAULT 0 CHECK(explicit_permission IN (0, 1)),
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_knowledge_shares_recipient ON knowledge_shares(to_character_key, shared_at);

CREATE TABLE IF NOT EXISTS character_preferences (
    id INTEGER PRIMARY KEY,
    character_key TEXT NOT NULL,
    category TEXT NOT NULL,
    value TEXT NOT NULL,
    preference_type TEXT NOT NULL CHECK(preference_type IN ('core_like', 'current_interest', 'discovered_preference')),
    strength REAL NOT NULL CHECK(strength BETWEEN 0 AND 1),
    confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    times_reinforced INTEGER NOT NULL DEFAULT 1 CHECK(times_reinforced >= 0),
    canon_locked INTEGER NOT NULL DEFAULT 0 CHECK(canon_locked IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    UNIQUE(character_key, category, value, preference_type)
);
CREATE INDEX IF NOT EXISTS idx_preferences_character ON character_preferences(character_key, active);

CREATE TABLE IF NOT EXISTS routine_patterns (
    id INTEGER PRIMARY KEY,
    canonical_key TEXT UNIQUE,
    character_key TEXT NOT NULL,
    routine_type TEXT NOT NULL,
    day_scope TEXT,
    window_start TEXT,
    window_end TEXT,
    probability REAL NOT NULL CHECK(probability BETWEEN 0 AND 1),
    context_rules_json TEXT,
    fallback_json TEXT,
    canon_locked INTEGER NOT NULL DEFAULT 0 CHECK(canon_locked IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_routines_character ON routine_patterns(character_key, active);

CREATE TABLE IF NOT EXISTS world_decisions (
    id INTEGER PRIMARY KEY,
    decision_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'chosen', 'expired')),
    context_json TEXT NOT NULL,
    options_json TEXT NOT NULL,
    chosen_option TEXT,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_world_decisions_status ON world_decisions(status, created_at);

CREATE TABLE IF NOT EXISTS world_bootstrap (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
