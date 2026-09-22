-- Fase C.1 — modo íntimo. Excitação da Marina em minutos, não em horas: por
-- isso não mora em estado_emocional (meia-vida de 6 h). Uma linha só (id = 1).
CREATE TABLE IF NOT EXISTS intimacy_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    arousal REAL NOT NULL DEFAULT 0,
    updated_at TEXT,
    mode_since TEXT,
    hot_turns INTEGER NOT NULL DEFAULT 0,
    climax_at TEXT
);
