-- Reviewed, deterministic references for conversational privacy routing.
-- For fact/relationship, the registry ID is the subject ID. For event/thread,
-- the subject ID is the actual life_events/story_threads ID linked below.
CREATE TABLE IF NOT EXISTS knowledge_subjects (
    id INTEGER PRIMARY KEY,
    subject_type TEXT NOT NULL CHECK(subject_type IN ('event', 'fact', 'thread', 'relationship')),
    topic_label TEXT NOT NULL,
    approved_detail TEXT NOT NULL DEFAULT '',
    source_event_id INTEGER REFERENCES life_events(id) ON DELETE RESTRICT,
    source_thread_id INTEGER REFERENCES story_threads(id) ON DELETE RESTRICT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE(subject_type, topic_label)
);
CREATE TABLE IF NOT EXISTS knowledge_subject_aliases (
    subject_id INTEGER NOT NULL REFERENCES knowledge_subjects(id) ON DELETE CASCADE,
    normalized_alias TEXT NOT NULL,
    PRIMARY KEY(subject_id, normalized_alias)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_subject_event
    ON knowledge_subjects(source_event_id) WHERE source_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_subject_thread
    ON knowledge_subjects(source_thread_id) WHERE source_thread_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_knowledge_alias_lookup
    ON knowledge_subject_aliases(normalized_alias);
