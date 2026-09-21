-- Auditoria #7 — reminders.offer_message_id vivia fora do sistema de migrations:
-- um ALTER TABLE avulso no startup (db._run_migrations) que rodava a cada
-- inicialização e engolia qualquer erro. Bancos antigos já têm a coluna, e o
-- replay de ADD COLUMN duplicada em db.py trata esse caso (versão 20).
ALTER TABLE reminders ADD COLUMN offer_message_id INTEGER;
