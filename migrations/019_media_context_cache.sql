-- Patch 023 — habilita kind='media' no cache de contexto real.
-- Segue o mesmo padrão da migration 013: swap-tabela pra atualizar o CHECK.
CREATE TABLE real_context_cache_v3 (
    context_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('weather','holiday','holiday_year','place_fact','place_negative','media')),
    payload_json TEXT NOT NULL,
    source_name TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    CHECK(observed_at < expires_at)
);
INSERT INTO real_context_cache_v3
    (context_key,kind,payload_json,source_name,observed_at,expires_at)
    SELECT context_key,kind,payload_json,source_name,observed_at,expires_at
    FROM real_context_cache;
DROP TABLE real_context_cache;
ALTER TABLE real_context_cache_v3 RENAME TO real_context_cache;
