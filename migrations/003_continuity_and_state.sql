-- Migration 003: Continuity & Emotional/Relational State
-- Marina Salles v3.2 Foundation

-- 1. Eventos Pendentes (Follow-ups contextuais automáticos)
CREATE TABLE IF NOT EXISTS eventos_pendentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    event_at TEXT,
    follow_up_after TEXT,
    status TEXT DEFAULT 'pending',
    importance REAL DEFAULT 0.5,
    source_conversation_id INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_eventos_status ON eventos_pendentes(status);
CREATE INDEX IF NOT EXISTS idx_eventos_follow_up ON eventos_pendentes(follow_up_after);

-- 2. Estado Relacional (Dinâmica contínua do casal)
CREATE TABLE IF NOT EXISTS estado_relacional (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 3. Estado Emocional (Dimensões emocionais orgânicas com baseline e clamp)
CREATE TABLE IF NOT EXISTS estado_emocional (
    chave TEXT PRIMARY KEY,
    valor REAL NOT NULL,
    baseline REAL NOT NULL,
    updated_at TEXT NOT NULL
);

-- Inserção dos baselines emocionais iniciais da Marina
INSERT OR IGNORE INTO estado_emocional (chave, valor, baseline, updated_at)
VALUES 
    ('affection', 0.85, 0.85, CURRENT_TIMESTAMP),
    ('playfulness', 0.75, 0.75, CURRENT_TIMESTAMP),
    ('energy', 0.75, 0.75, CURRENT_TIMESTAMP),
    ('romantic_intensity', 0.80, 0.80, CURRENT_TIMESTAMP),
    ('social_battery', 0.90, 0.90, CURRENT_TIMESTAMP);

-- Inserção do estado relacional padrão inicial
INSERT OR IGNORE INTO estado_relacional (chave, valor, updated_at)
VALUES
    ('current_nickname', 'amor', CURRENT_TIMESTAMP),
    ('closeness_level', 'intimo', CURRENT_TIMESTAMP),
    ('current_shared_topic', 'dia a dia e planos juntos', CURRENT_TIMESTAMP);
