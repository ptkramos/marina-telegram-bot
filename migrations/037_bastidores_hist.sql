-- Redesenho dos Bastidores, passo 1 (06/10): o histórico que só a tela lê (ela nunca lê isto).
-- chave: 'orgasmo' (com o Patrick ou sozinha), 'excitacao' (a hora em que acendeu), 'vinculo' (retrato da hora:
-- Carinho, Desejo, Segurança, Mágoa, Saudade), 'peso' (retrato do dia) e 'pesagem' (a balança da academia).
-- ref: identidade do registro pra não duplicar (a hora do retrato, a chave do evento).
CREATE TABLE IF NOT EXISTS bastidores_hist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT NOT NULL,
    em TEXT NOT NULL,
    ref TEXT,
    valor_json TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    UNIQUE (chave, ref)
);
CREATE INDEX IF NOT EXISTS idx_bastidores_hist_chave_em ON bastidores_hist (chave, em);
