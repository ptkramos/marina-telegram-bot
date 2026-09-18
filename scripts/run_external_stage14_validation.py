"""Validation runner for stage 14 / release 3.6.7 World Hygiene."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'data' / 'world_hygiene_validation.v367.json'


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

    sim_report = {}
    sim_code = 0
    try:
        sim = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/run_world_hygiene_simulation.py'), '30', '90'],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
        )
        sim_code = sim.returncode
        sim_path = ROOT / 'data' / 'world_hygiene_simulation.v367.json'
        if sim_path.exists():
            sim_report = json.loads(sim_path.read_text(encoding='utf-8'))
        output += '\n' + sim.stdout + sim.stderr
    except subprocess.TimeoutExpired as exc:
        sim_code = 124
        output += '\n' + ''.join(
            part.decode(errors='replace') if isinstance(part, bytes) else (part or '')
            for part in (exc.stdout, exc.stderr)
        )

    count = re.search(r'Ran (\d+) tests?', output)
    skipped = re.search(r'skipped=(\d+)', output)
    sims = sim_report.get('simulations', {})
    overall = code == 0 and sim_code == 0
    for payload in sims.values():
        if payload.get('canon_drift_detected') or payload.get('event_looping_detected'):
            overall = False
    report = {
        'release': '3.6.7',
        'stage': 14,
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(time.monotonic() - started, 2),
        'python': sys.executable,
        'test_command': 'tests/run_isolated.py',
        'status': 'passed' if overall else 'failed',
        'exit_code': code if code else sim_code,
        'tests_run': int(count.group(1)) if count else None,
        'tests_skipped': int(skipped.group(1)) if skipped else 0,
        'failures': 0 if code == 0 else 1,
        'errors': 0 if code == 0 else 1,
        'skipped': int(skipped.group(1)) if skipped else 0,
        'simulation_30d': sims.get('30d'),
        'simulation_90d': sims.get('90d'),
        'canon_drift_detected': any(
            s.get('canon_drift_detected') for s in sims.values()) if sims else None,
        'event_looping_detected': any(
            s.get('event_looping_detected') for s in sims.values()) if sims else None,
        'promotion_anomalies': None,
        'preference_decay_anomalies': None,
        'output_tail': output[-5000:],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                      encoding='utf-8')
    print(RESULT)
    return 0 if overall else 1


if __name__ == '__main__':
    raise SystemExit(main())
