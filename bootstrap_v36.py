"""Offline CLEAN_CANONICAL_START. Back up before importing database singletons.

The bot must remain stopped throughout this maintenance operation.
"""
import argparse
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4


CLEAR = ('reminders', 'open_loops', 'eventos_pendentes', 'conversas',
         'fatos_patrick', 'gostos_marina', 'resumos_conversa', 'momentos_marcantes',
         'feedbacks', 'estilo_linguagem', 'estado_relacional', 'estado_emocional',
         'knowledge_subject_aliases', 'knowledge_subjects',
         'real_context_cache', 'tmdb_cache',
         'relationship_culture_evidence', 'relationship_culture',
         'perfil', 'knowledge_shares', 'knowledge_items', 'life_events',
         'life_events_archive', 'world_hygiene_log',
         'response_pending_batch_items', 'response_pending_batches',
         'response_availability_events', 'intimacy_state',
         'story_threads', 'world_decisions', 'world_state',
         'academic_schedule_blocks', 'academic_courses', 'academic_terms',
         'academic_profile', 'preference_evidence', 'social_evidence',
         'social_place_state', 'social_place_links', 'social_relationships',
         'character_preferences', 'routine_patterns',
         'world_characters', 'world_places', 'world_bootstrap')
PRESERVE = {'schema_version', 'ciclo_biologico', 'patch_history'}
FTS = ('fatos_fts', 'momentos_fts', 'resumos_fts')
FTS_TABLES = {name + suffix for name in FTS
              for suffix in ('', '_config', '_content', '_data', '_docsize', '_idx')}
BASELINES = dict(affection=.85, playfulness=.75, energy=.75,
                 romantic_intensity=.80, social_battery=.90)


def _done(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='world_bootstrap'").fetchone():
        return False
    return conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done' AND value='1'").fetchone() is not None


def bootstrap(path, *, backup_dir=None, trusted_cycle_anchor=None, now=None):
    path = Path(path).resolve(strict=True)
    now = now or datetime.now()
    directory = Path(backup_dir or path.parent / 'backups' / 'v36').resolve()
    if directory == path.parent:
        raise ValueError('Backup deve ficar fora da pasta de abertura do banco ativo')
    with closing(sqlite3.connect(path)) as source:
        if _done(source):
            return {'status': 'already_complete'}
        version = source.execute('PRAGMA data_version').fetchone()[0]
        directory.mkdir(parents=True, exist_ok=True)
        backup = directory / f'pre_v36_{now:%Y%m%d_%H%M%S}_{uuid4().hex}.sqlite'
        with closing(sqlite3.connect(backup)) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup inválido')
            schema = dest.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
        audit = {'status': 'preparing', 'backup': str(backup),
                 'source_schema': schema, 'timestamp': now.isoformat()}
        manifest = backup.with_suffix('.json')
        manifest.write_text(json.dumps(audit, indent=2), encoding='utf-8')
        try:
            with tempfile.TemporaryDirectory(prefix='bootstrap_v36_', dir=directory) as temp:
                stage = Path(temp) / 'staged.sqlite'
                with closing(sqlite3.connect(backup)) as saved, closing(sqlite3.connect(stage)) as dest:
                    saved.backup(dest)
                # db.py has a legacy singleton: route its first import to staging too.
                previous_env = os.environ.get('MARINA_DB_PATH')
                os.environ['MARINA_DB_PATH'] = str(stage)
                try:
                    from db import DatabaseManager
                    from seed_world_bible_v36 import seed_world_bible
                    from seed_academic_v36 import seed_academic
                    from seed_knowledge_v363 import seed_knowledge
                    from social_world import seed_social
                    from world_state import WorldStateManager
                finally:
                    if previous_env is None:
                        os.environ.pop('MARINA_DB_PATH', None)
                    else:
                        os.environ['MARINA_DB_PATH'] = previous_env
                db = DatabaseManager(stage)
                with db.get_connection() as conn:
                    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                    unknown = tables - set(CLEAR) - PRESERVE - FTS_TABLES
                    if unknown:
                        raise RuntimeError(f'Tabelas sem política de migração: {sorted(unknown)}')
                    anchor = conn.execute('SELECT data_inicio_ciclo FROM ciclo_biologico WHERE id=1').fetchone()
                    if not anchor or anchor[0] != trusted_cycle_anchor:
                        raise ValueError('Âncora do Cycle Manager precisa ser explicitamente considerada confiável')
                    if date.fromisoformat(anchor[0]) > now.date():
                        raise ValueError('Âncora do ciclo não pode estar no futuro')
                    audit['cycle_anchor'] = anchor[0]
                    audit['cleared_rows'] = {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in CLEAR}
                    for table in CLEAR:
                        conn.execute(f'DELETE FROM {table}')
                    for table in FTS:
                        conn.execute(f'DELETE FROM {table}')
                    for key, value in BASELINES.items():
                        conn.execute('INSERT INTO estado_emocional VALUES (?,?,?,?)', (key,value,value,now.isoformat()))
                    conn.executemany('INSERT INTO perfil (chave,valor) VALUES (?,?)',
                        [('nome','Marina Salles'), ('namorado','Patrick Ramos'),
                         ('status_relacionamento','Relacionamento comprometido; Patrick é o primeiro namorado oficial')])
                    conn.execute('INSERT INTO estado_relacional VALUES (?,?,?)',
                                 ('relationship_status','committed',now.isoformat()))
                seed_world_bible(db)
                seed_academic(db)
                seed_social(db)
                WorldStateManager(db).resolve(now)
                with db.get_connection() as conn:
                    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
                        raise RuntimeError('Invariantes SQLite falharam')
                    for table in ('reminders', 'open_loops', 'eventos_pendentes',
                                  'conversas', 'fatos_patrick', 'gostos_marina',
                                  'resumos_conversa', 'momentos_marcantes',
                                  'feedbacks', 'estilo_linguagem', *FTS,
                                  'knowledge_items', 'knowledge_shares', 'life_events', 'story_threads'):
                        if conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:
                            raise RuntimeError(f'Memória antiga remanescente: {table}')
                    audit.update(status='validated', target_schema=db.get_schema_version())
                    conn.executemany('INSERT INTO world_bootstrap (key,value,updated_at) VALUES (?,?,?)',
                        [('clean_canonical_start_audit', json.dumps(audit), now.isoformat()),
                         ('clean_canonical_start_done','1',now.isoformat())])
                audit['knowledge_subjects'] = seed_knowledge(db)
                with db.get_connection() as conn:
                    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
                        raise RuntimeError('Seed de conhecimento violou invariantes SQLite')
                    conn.execute("UPDATE world_bootstrap SET value=? WHERE key='clean_canonical_start_audit'",
                                 (json.dumps(audit),))
                if source.execute('PRAGMA data_version').fetchone()[0] != version:
                    raise RuntimeError('Banco ativo mudou durante preparação; abortando')
                # SQLite backup publishes the validated image transactionally, including WAL.
                with closing(sqlite3.connect(stage)) as ready:
                    ready.backup(source)
                audit['status'] = 'complete'
        except Exception as exc:
            audit.update(status='failed', error=str(exc))
            raise
        finally:
            manifest.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
        return audit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--trusted-cycle-anchor', required=True)
    args = parser.parse_args()
    print(json.dumps(bootstrap(args.db, trusted_cycle_anchor=args.trusted_cycle_anchor), ensure_ascii=False, indent=2))
