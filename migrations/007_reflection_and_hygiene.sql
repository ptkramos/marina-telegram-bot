-- Migration 007: Session Reflection & Memory Hygiene
-- Marina Salles v3.5.3

ALTER TABLE fatos_patrick ADD COLUMN needs_reconfirmation INTEGER DEFAULT 0;
ALTER TABLE fatos_patrick ADD COLUMN last_decay_at TEXT;
ALTER TABLE open_loops ADD COLUMN is_archived INTEGER DEFAULT 0;
ALTER TABLE open_loops ADD COLUMN resolution_notes TEXT;

CREATE INDEX IF NOT EXISTS idx_fatos_needs_reconf ON fatos_patrick(needs_reconfirmation);
CREATE INDEX IF NOT EXISTS idx_open_loops_archived ON open_loops(is_archived);

DELETE FROM resumos_conversa
WHERE id NOT IN (
    SELECT MIN(id)
    FROM resumos_conversa
    GROUP BY start_conversation_id, end_conversation_id
) AND start_conversation_id IS NOT NULL AND end_conversation_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_resumos_intervalo ON resumos_conversa(start_conversation_id, end_conversation_id) WHERE start_conversation_id IS NOT NULL AND end_conversation_id IS NOT NULL;
