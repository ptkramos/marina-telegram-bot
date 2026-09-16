-- Migration 005: Memory Intelligence (Core Memories, Volatility, Canonical Key & Confirmations)
-- Marina Seltin Release 3.5.0

ALTER TABLE fatos_patrick ADD COLUMN memory_tier TEXT DEFAULT 'standard';
ALTER TABLE fatos_patrick ADD COLUMN volatility TEXT DEFAULT 'medium';
ALTER TABLE fatos_patrick ADD COLUMN canonical_key TEXT;
ALTER TABLE fatos_patrick ADD COLUMN last_confirmed_at TEXT;
ALTER TABLE fatos_patrick ADD COLUMN confirmation_count INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_fatos_tier ON fatos_patrick(memory_tier);
CREATE INDEX IF NOT EXISTS idx_fatos_canonical ON fatos_patrick(canonical_key);
