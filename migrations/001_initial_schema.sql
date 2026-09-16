-- Migration 001: Initial Database Schema
-- Marina Seltin SQLite Baseline

CREATE TABLE IF NOT EXISTS conversas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    is_initiative INTEGER DEFAULT 0,
    media_type TEXT DEFAULT 'text'
);
CREATE INDEX IF NOT EXISTS idx_conversas_timestamp ON conversas(timestamp);

CREATE TABLE IF NOT EXISTS fatos_patrick (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fato TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    relevance INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS gostos_marina (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria TEXT NOT NULL,
    item TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(categoria, item)
);

CREATE TABLE IF NOT EXISTS perfil (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    autor TEXT NOT NULL,
    feedback TEXT NOT NULL,
    contexto_recente TEXT,
    status TEXT DEFAULT 'pendente'
);

CREATE TABLE IF NOT EXISTS ciclo_biologico (
    id INTEGER PRIMARY KEY,
    data_inicio_ciclo TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS momentos_marcantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    momento TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS estilo_linguagem (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    exemplos TEXT,
    updated_at TEXT NOT NULL
);
