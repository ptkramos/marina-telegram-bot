-- Fase D14 — motor emocional: episódios de emoção com causa.
-- Cada linha é um sentimento que nasceu de algo concreto (um acontecimento do
-- mundo dela ou uma mensagem do Patrick) e esfria pela própria meia-vida.
-- `sticky`: só começa a esfriar quando a causa se resolve (resolved_at),
-- como a ansiedade de uma entrega que só passa quando ela entrega.
CREATE TABLE IF NOT EXISTS emotion_episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family TEXT NOT NULL,
    kind TEXT NOT NULL,
    intensity REAL NOT NULL CHECK (intensity BETWEEN 0 AND 1),
    cause TEXT NOT NULL,
    target TEXT,
    source_key TEXT UNIQUE,
    started_at TEXT NOT NULL,
    half_life_min INTEGER NOT NULL,
    sticky INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emotion_episodes_started ON emotion_episodes(started_at);

-- Vínculo com o Patrick: segurança (confia que ele está ali) e mágoa pendente.
INSERT OR IGNORE INTO estado_emocional (chave, valor, baseline, updated_at)
VALUES ('security', 0.8, 0.8, datetime('now', 'localtime')),
       ('hurt', 0.0, 0.0, datetime('now', 'localtime'));
