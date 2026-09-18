"""Offline comparison of the versioned academic seed with the local raw snapshot."""

import csv
import hashlib
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from seed_academic_v36 import COURSES, METADATA  # noqa: E402


SNAPSHOT = ROOT / 'data' / 'external' / 'puc_rio' / '2026_2' / 'raw' / 'HORARIO_DAS_DISCIPLINAS_18092026.csv'
DAYS = ('SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM')


def validate_snapshot(path=SNAPSHOT):
    """Read only during offline validation; runtime never opens this file."""
    path = Path(path)
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != METADATA['schedule_snapshot_sha256']:
        raise ValueError('MicroHorário snapshot hash differs from canonical provenance')
    rows = list(csv.reader(content.decode('utf-16').splitlines(), delimiter=';'))
    if not rows or '20262' not in rows[0][0] or '18/09/2026' not in rows[0][1]:
        raise ValueError('Unexpected MicroHorário period or snapshot timestamp')
    offerings = {}
    for row in rows:
        if len(row) < 13 or row[0].strip() not in {course[0] for course in COURSES}:
            continue
        key = (row[0].strip(), row[4].strip(), row[5].strip())
        if key in offerings:
            raise ValueError(f'Duplicate official offering: {key}')
        offerings[key] = row
    for code, _, _, credits, section, _, _, blocks in COURSES:
        row = offerings.get((code, section, 'QQC'))
        if not row:
            raise ValueError(f'Official offering missing: {code}/{section}')
        if int(row[3].strip()) != credits:
            raise ValueError(f'Credit mismatch: {code}/{section}')
        if code == 'DSG1985' and row[12].strip().upper() != 'NÃO':
            raise ValueError('DSG1985 prerequisite changed in the official snapshot')
        raw_blocks = {
            (DAYS.index(day), f'{start}:00', f'{end}:00', room)
            for day, start, end, room in re.findall(
                r'\b(SEG|TER|QUA|QUI|SEX|SAB|DOM)\s+(\d{2})-(\d{2})\s+(\S+)', row[8])
        }
        expected = {(day, start, end, room) for day, start, end, room in blocks}
        if raw_blocks != expected:
            raise ValueError(f'Schedule/room mismatch: {code}/{section}: {raw_blocks} != {expected}')
    return {'source_sha256': digest,
            'offerings_validated': len(COURSES), 'snapshot': str(path)}


if __name__ == '__main__':
    print(validate_snapshot())
