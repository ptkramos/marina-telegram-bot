-- Lovense pelo Mini App (PLANO_WEBAPP, "Lovense pelo Mini App — plano", passo 1; Patrick, 04–05/10).
-- O brinquedo é o dela na história e ele controla pelo app. Aqui mora só o estado: os brinquedos (bateria e
-- onde estão), as sessões (com qual, desde quando, onde colocou, a palavra de segurança e a escada quando ele
-- não para) e a linha do tempo dos comandos. A confiança é a barra geral `trust` do vínculo (recalibrar a
-- Marina, 05/10), que não relaxa pra cima enquanto houver pendência aberta (`emocao_travas`).
CREATE TABLE IF NOT EXISTS lovense_brinquedos (
    brinquedo TEXT PRIMARY KEY,           -- lush | hush
    bateria REAL NOT NULL DEFAULT 1.0,    -- 0–1, valendo no momento bateria_em
    bateria_em TEXT NOT NULL,
    onde TEXT NOT NULL DEFAULT 'gaveta'   -- gaveta | carregador | bolsa | nela
);
INSERT OR IGNORE INTO lovense_brinquedos (brinquedo, bateria, bateria_em, onde)
VALUES ('lush', 1.0, datetime('now', 'localtime'), 'gaveta'),
       ('hush', 1.0, datetime('now', 'localtime'), 'gaveta');

CREATE TABLE IF NOT EXISTS lovense_sessoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brinquedos_json TEXT NOT NULL DEFAULT '[]',  -- os que ela colocou nesta sessão
    origem TEXT NOT NULL DEFAULT 'dela',          -- dela | pedido (ele pediu e ela topou)
    desde TEXT NOT NULL,
    lugar TEXT NOT NULL DEFAULT '',               -- onde colocou (chave do lugar ou descrição)
    fora_de_casa INTEGER NOT NULL DEFAULT 0,
    palavra TEXT,                                 -- palavra de segurança combinada no chat desta vez
    estado TEXT NOT NULL DEFAULT 'conectada',     -- conectada | pausada (disse a palavra) | cortada | encerrada
    pediu_parar_em TEXT,                          -- início do prazo de 30 s da palavra
    escada INTEGER NOT NULL DEFAULT 0,            -- 0 nada | 1 repetiu firme | 2 bronca | 3 cortou
    respeitou INTEGER,                            -- NULL até decidir; 1 parou a tempo; 0 não
    incidentes INTEGER NOT NULL DEFAULT 0,        -- vezes que chegou na bronca ou no corte
    fim_em TEXT,                                  -- fim do controle (o brinquedo pode continuar nela)
    motivo_fim TEXT                               -- tirou | bateria | cortou
);
CREATE INDEX IF NOT EXISTS idx_lovense_sessoes_desde ON lovense_sessoes(desde);

CREATE TABLE IF NOT EXISTS lovense_comandos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id INTEGER NOT NULL,
    brinquedo TEXT NOT NULL,
    nivel INTEGER NOT NULL,                       -- 0–20 (0 = parado)
    modo TEXT NOT NULL DEFAULT 'classico',        -- classico | toque | padrao | sistema
    padrao TEXT,                                  -- pulso | onda | fogos | terremoto
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lovense_comandos ON lovense_comandos(brinquedo, criado_em);

-- Pendência que segura uma barra: enquanto existir, a barra não volta sozinha pra cima.
CREATE TABLE IF NOT EXISTS emocao_travas (
    chave TEXT NOT NULL,
    motivo TEXT NOT NULL,                         -- lovense (depois: degrau da escada, mágoa)
    desde TEXT NOT NULL,
    detalhe TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (chave, motivo)
);

INSERT OR IGNORE INTO estado_emocional (chave, valor, baseline, updated_at)
VALUES ('trust', 0.8, 0.8, datetime('now', 'localtime'));
