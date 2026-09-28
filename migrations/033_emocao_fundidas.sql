-- Bug de 28/09 (Patrick, Por dentro): o mesmo sentimento em 3 h reforça o episódio que já existe, mas a chave do
-- acontecimento fundido não ficava guardada — a cada turno ele fundia de novo e a força subia até 1.0.
CREATE TABLE IF NOT EXISTS emotion_sources (
    source_key TEXT PRIMARY KEY,
    episode_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
