"""External v3.6.4 suite handoff; Codex reviews the resulting JSON only."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'data' / 'calendar_academic_validation.v364.json'


def main() -> int:
    started = time.monotonic()
    try:
        completed = subprocess.run([sys.executable, str(ROOT / 'tests/run_isolated.py')],
                                   cwd=ROOT, capture_output=True, text=True, timeout=900)
        output = completed.stdout + completed.stderr
        exit_code = completed.returncode
        status = 'passed' if exit_code == 0 else 'failed'
    except subprocess.TimeoutExpired as exc:
        output = ''.join(part.decode(errors='replace') if isinstance(part, bytes)
                         else (part or '') for part in (exc.stdout, exc.stderr))
        exit_code, status = 124, 'timeout'
    count = re.search(r'Ran (\d+) tests?', output)
    skipped = re.search(r'skipped=(\d+)', output)
    report = {
        'release': '3.6.4', 'stage': 11,
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(time.monotonic() - started, 2),
        'python': sys.executable, 'status': status, 'exit_code': exit_code,
        'tests_run': int(count.group(1)) if count else None,
        'tests_skipped': int(skipped.group(1)) if skipped else 0,
        'output_tail': output[-5000:],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                      encoding='utf-8')
    print(RESULT)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
