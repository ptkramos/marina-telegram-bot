"""One-time guarded upgrade of the 2026.2 academic seed. Keep the bot stopped."""

import argparse
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import DatabaseManager  # noqa: E402
from seed_academic_v36 import upgrade_academic_grade_v2  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'marin_memory.db')
    parser.add_argument('--backup-dir', type=Path)
    args = parser.parse_args()
    path = args.db.resolve(strict=True)
    backup_dir = (args.backup_dir or path.parent / 'backups' / 'academic_grade_v2').resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'pre_grade_v2_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite'
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as dest:
        source.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Academic grade backup failed integrity check')
    changed = upgrade_academic_grade_v2(DatabaseManager(path))
    print(f"{'upgraded' if changed else 'already_v2'}; backup={backup}")


if __name__ == '__main__':
    main()
