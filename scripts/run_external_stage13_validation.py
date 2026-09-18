"""Gemini/Antigravity handoff for stage 13; Codex does not run this suite."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'data' / 'camera_world_validation.v366.json'


def main() -> int:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, str(ROOT / 'tests/run_isolated.py')],
            cwd=ROOT, capture_output=True, text=True, timeout=900,
        )
        output = completed.stdout + completed.stderr
        code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        output = ''.join(
            part.decode(errors='replace') if isinstance(part, bytes) else (part or '')
            for part in (exc.stdout, exc.stderr)
        )
        code = 124
    count = re.search(r'Ran (\d+) tests?', output)
    skipped = re.search(r'skipped=(\d+)', output)
    report = {
        'release': '3.6.6',
        'stage': 13,
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(time.monotonic() - started, 2),
        'python': sys.executable,
        'status': 'passed' if code == 0 else 'failed',
        'exit_code': code,
        'tests_run': int(count.group(1)) if count else None,
        'tests_skipped': int(skipped.group(1)) if skipped else 0,
        'output_tail': output[-5000:],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    print(RESULT)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
