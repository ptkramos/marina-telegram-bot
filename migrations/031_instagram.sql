-- Instagram da Marina (Etapa 5 do PLANO_WEBAPP, decidido com o Patrick em 27/09).
-- Posts do feed e stories dela e das amigas, comentários (inclusive os agendados: aparecem quando
-- chega a hora) e as fotos vestidas que ela mandou no chat, guardadas pra ela poder postar.
CREATE TABLE IF NOT EXISTS ig_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    autor TEXT NOT NULL,                 -- 'marina' ou a chave da amiga ('bia_andrade')
    tipo TEXT NOT NULL DEFAULT 'feed',   -- feed | story
    criado_em TEXT NOT NULL,
    expira_em TEXT,                      -- story: 24 h depois
    imagem TEXT,                         -- arquivo em data/instagram/ (sem imagem: story de música/texto)
    legenda TEXT NOT NULL DEFAULT '',
    local TEXT NOT NULL DEFAULT '',
    marcados_json TEXT NOT NULL DEFAULT '[]',
    motivo TEXT NOT NULL DEFAULT '',     -- role | praia | salao | look | treino | milo | vista | chat | acervo
    motivo_chave TEXT,                   -- o acontecimento que virou post (não posta duas vezes)
    fonte TEXT NOT NULL DEFAULT '',      -- nova | grupo | chat | acervo | musica | texto
    descricao TEXT NOT NULL DEFAULT '',  -- o que a foto mostra (prompt dela e dos comentários)
    story_json TEXT,                     -- story sem foto: {"tipo": "musica"|"texto", ...}
    alcance REAL NOT NULL DEFAULT 0.08,  -- fração dos seguidores que curte
    visto_patrick_em TEXT,
    curtido_patrick_em TEXT,
    visto_marina_em TEXT,                -- ela viu a curtida do Patrick (post dela) / viu o post (da amiga)
    curtido_marina_em TEXT               -- ela curtiu (post de amiga)
);
CREATE INDEX IF NOT EXISTS idx_ig_posts_autor ON ig_posts(autor, tipo, criado_em);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ig_posts_motivo ON ig_posts(autor, motivo_chave);

CREATE TABLE IF NOT EXISTS ig_comentarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    pai_id INTEGER,                      -- resposta a outro comentário
    autor TEXT NOT NULL,                 -- 'marina' | 'patrick' | chave da amiga | handle de fora
    texto TEXT NOT NULL,
    criado_em TEXT NOT NULL,             -- no futuro = agendado
    visto_marina_em TEXT,
    curtido_patrick_em TEXT,
    curtido_marina_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_ig_comentarios_post ON ig_comentarios(post_id, criado_em);

CREATE TABLE IF NOT EXISTS ig_fotos_chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em TEXT NOT NULL,
    imagem TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    pose TEXT NOT NULL DEFAULT '',
    lugar TEXT NOT NULL DEFAULT '',
    usada_em TEXT
);
