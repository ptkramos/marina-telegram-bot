-- Migration 006: Open Loops & Smart Reminders
-- Marina Seltin Release 3.5.1

-- 1. Tabela de Assuntos em Aberto (Open Loops)
CREATE TABLE IF NOT EXISTS open_loops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_type TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    importance REAL DEFAULT 0.5,
    due_at TEXT,
    next_check_after TEXT,
    source_conversation_id INTEGER,
    created_at TEXT NOT NULL,
    last_touched_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_open_loops_status_check ON open_loops(status, next_check_after);
CREATE INDEX IF NOT EXISTS idx_open_loops_status_importance ON open_loops(status, importance);

-- 2. Tabela de Lembretes Inteligentes com Consentimento (Smart Reminders)
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    description TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    offset_minutes INTEGER DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'offered',
    source_conversation_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sent_at TEXT,
    FOREIGN KEY(event_id) REFERENCES eventos_pendentes(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_status_remind ON reminders(status, remind_at);
CREATE INDEX IF NOT EXISTS idx_reminders_event_id ON reminders(event_id);

-- 3. Extensões em eventos_pendentes para suporte a cancelamento e prompt dedicado de follow-up
ALTER TABLE eventos_pendentes ADD COLUMN follow_up_prompt TEXT;
ALTER TABLE eventos_pendentes ADD COLUMN cancelled_at TEXT;
