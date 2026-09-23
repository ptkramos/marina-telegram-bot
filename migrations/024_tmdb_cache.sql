-- Fase D6 parte 2 — cache do TMDB (títulos, episódios, recomendações, onde
-- assistir no Brasil). Só dados de catálogo; cada resposta vale por um tempo
-- e a API é consultada poucas vezes por dia.
CREATE TABLE IF NOT EXISTS tmdb_cache (
    cache_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
