-- Migration 002: Smart Memory & Facts Baseline
-- Marina Salles v3.1 Foundation

ALTER TABLE fatos_patrick ADD COLUMN category TEXT DEFAULT 'geral';
ALTER TABLE fatos_patrick ADD COLUMN importance REAL DEFAULT 0.5;
ALTER TABLE fatos_patrick ADD COLUMN confidence REAL DEFAULT 1.0;
ALTER TABLE fatos_patrick ADD COLUMN updated_at TEXT;
ALTER TABLE fatos_patrick ADD COLUMN last_accessed_at TEXT;
ALTER TABLE fatos_patrick ADD COLUMN access_count INTEGER DEFAULT 0;
ALTER TABLE fatos_patrick ADD COLUMN active INTEGER DEFAULT 1;
ALTER TABLE fatos_patrick ADD COLUMN source_conversation_id INTEGER;
ALTER TABLE fatos_patrick ADD COLUMN supersedes_id INTEGER;

ALTER TABLE momentos_marcantes ADD COLUMN importance REAL DEFAULT 0.8;
ALTER TABLE momentos_marcantes ADD COLUMN updated_at TEXT;
ALTER TABLE momentos_marcantes ADD COLUMN last_accessed_at TEXT;
ALTER TABLE momentos_marcantes ADD COLUMN access_count INTEGER DEFAULT 0;
ALTER TABLE momentos_marcantes ADD COLUMN source_conversation_id INTEGER;
ALTER TABLE momentos_marcantes ADD COLUMN active INTEGER DEFAULT 1;

CREATE TABLE IF NOT EXISTS resumos_conversa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT,
    summary TEXT NOT NULL,
    start_conversation_id INTEGER,
    end_conversation_id INTEGER,
    importance REAL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_resumos_created_at ON resumos_conversa(created_at);

-- Tabelas Virtuais FTS5 para busca textual ultra-rápida (Smart Retrieval)
CREATE VIRTUAL TABLE IF NOT EXISTS fatos_fts USING fts5(
    fato,
    category
);

CREATE VIRTUAL TABLE IF NOT EXISTS momentos_fts USING fts5(
    momento
);

CREATE VIRTUAL TABLE IF NOT EXISTS resumos_fts USING fts5(
    topic,
    summary
);

-- Triggers para sincronização automática de fatos_patrick com fatos_fts
CREATE TRIGGER IF NOT EXISTS fatos_ai AFTER INSERT ON fatos_patrick BEGIN
    INSERT INTO fatos_fts(rowid, fato, category) VALUES (new.id, new.fato, new.category);
END;

CREATE TRIGGER IF NOT EXISTS fatos_ad AFTER DELETE ON fatos_patrick BEGIN
    DELETE FROM fatos_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS fatos_au AFTER UPDATE ON fatos_patrick BEGIN
    DELETE FROM fatos_fts WHERE rowid = old.id;
    INSERT INTO fatos_fts(rowid, fato, category) VALUES (new.id, new.fato, new.category);
END;

-- Triggers para sincronização automática de momentos_marcantes com momentos_fts
CREATE TRIGGER IF NOT EXISTS momentos_ai AFTER INSERT ON momentos_marcantes BEGIN
    INSERT INTO momentos_fts(rowid, momento) VALUES (new.id, new.momento);
END;

CREATE TRIGGER IF NOT EXISTS momentos_ad AFTER DELETE ON momentos_marcantes BEGIN
    DELETE FROM momentos_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS momentos_au AFTER UPDATE ON momentos_marcantes BEGIN
    DELETE FROM momentos_fts WHERE rowid = old.id;
    INSERT INTO momentos_fts(rowid, momento) VALUES (new.id, new.momento);
END;

-- Triggers para sincronização automática de resumos_conversa com resumos_fts
CREATE TRIGGER IF NOT EXISTS resumos_ai AFTER INSERT ON resumos_conversa BEGIN
    INSERT INTO resumos_fts(rowid, topic, summary) VALUES (new.id, new.topic, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS resumos_ad AFTER DELETE ON resumos_conversa BEGIN
    DELETE FROM resumos_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS resumos_au AFTER UPDATE ON resumos_conversa BEGIN
    DELETE FROM resumos_fts WHERE rowid = old.id;
    INSERT INTO resumos_fts(rowid, topic, summary) VALUES (new.id, new.topic, new.summary);
END;

-- Migração dos fatos e momentos existentes para o índice FTS
INSERT INTO fatos_fts(rowid, fato, category) SELECT id, fato, category FROM fatos_patrick;
INSERT INTO momentos_fts(rowid, momento) SELECT id, momento FROM momentos_marcantes;
