-- Migration 004: Transactional Auto-Patcher & Audit History
-- Marina Salles v3.4 Foundation

CREATE TABLE IF NOT EXISTS patch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patch_id TEXT UNIQUE NOT NULL,
    autor TEXT NOT NULL,
    instruction TEXT NOT NULL,
    target_files TEXT NOT NULL,
    diff_content TEXT NOT NULL,
    status TEXT NOT NULL, -- 'applied', 'rolled_back', 'rejected', 'failed'
    created_at TEXT NOT NULL,
    reverted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_patch_history_id ON patch_history(patch_id);
CREATE INDEX IF NOT EXISTS idx_patch_history_status ON patch_history(status);
