-- Patch 018 — coluna `model` em `conversas` para auditoria de qual LLM gerou cada resposta.
-- Populada em role='assistant' com settings.LLM_MODEL no momento da persistência.
-- Deixada NULL em role='user' e em respostas anteriores à migration.
ALTER TABLE conversas ADD COLUMN model TEXT;
CREATE INDEX IF NOT EXISTS idx_conversas_model ON conversas(model);
