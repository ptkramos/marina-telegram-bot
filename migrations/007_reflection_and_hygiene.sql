-- Migration 007: Session Reflection & Memory Hygiene
-- Marina Seltin v3.5.3

ALTER TABLE fatos_patrick ADD COLUMN needs_reconfirmation INTEGER DEFAULT 0;
ALTER TABLE open_loops ADD COLUMN is_archived INTEGER DEFAULT 0;
ALTER TABLE open_loops ADD COLUMN resolution_notes TEXT;

CREATE INDEX IF NOT EXISTS idx_fatos_needs_reconf ON fatos_patrick(needs_reconfirmation);
CREATE INDEX IF NOT EXISTS idx_open_loops_archived ON open_loops(is_archived);
