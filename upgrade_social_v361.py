"""Offline additive upgrade. Preserves all existing continuity; never calls reset."""
import argparse
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def upgrade(path):
    path = Path(path).resolve(strict=True)
    directory = path.parent/'backups'/'v361'
    directory.mkdir(parents=True,exist_ok=True)
    backup = directory/f'pre_social_{uuid4().hex}.sqlite'
    with closing(sqlite3.connect(path)) as source:
        version = source.execute('PRAGMA data_version').fetchone()[0]
        with closing(sqlite3.connect(backup)) as dest:
            source.backup(dest)
        with tempfile.TemporaryDirectory(dir=directory) as temp:
            stage=Path(temp)/'stage.sqlite'
            with closing(sqlite3.connect(backup)) as saved, closing(sqlite3.connect(stage)) as dest:
                saved.backup(dest)
            previous=os.environ.get('MARINA_DB_PATH')
            os.environ['MARINA_DB_PATH']=str(stage)
            try:
                from db import DatabaseManager
                from social_world import seed_social
            finally:
                if previous is None:
                    os.environ.pop('MARINA_DB_PATH',None)
                else:
                    os.environ['MARINA_DB_PATH']=previous
            db=DatabaseManager(stage)
            seed_social(db)
            with db.get_connection() as conn:
                if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
                    raise RuntimeError('Falha de integridade no upgrade social')
                conn.execute("INSERT OR IGNORE INTO world_bootstrap VALUES ('social_seed_version','3.6.1',?)", (datetime.now().isoformat(),))
            if source.execute('PRAGMA data_version').fetchone()[0]!=version:
                raise RuntimeError('Banco ativo mudou; upgrade abortado')
            with closing(sqlite3.connect(stage)) as ready:
                ready.backup(source)
    result={'status':'complete','release':'3.6.1','backup':str(backup)}
    backup.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(upgrade(args.db),ensure_ascii=False))
