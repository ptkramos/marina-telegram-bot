"""Validation runner for stage 15 / release 3.7.0 Response Availability."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'data' / 'response_availability_validation.v370.json'
FAILURE_LOG = ROOT / 'data' / 'response_availability_test_failures.v370.txt'


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
            [sys.executable, str(ROOT / 'scripts/run_response_availability_simulation.py'),
             '24h', '72h', '7d'],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
        )
        sim_code = sim.returncode
        sim_path = ROOT / 'data' / 'response_availability_simulation.v370.json'
        if sim_path.exists():
            sim_report = json.loads(sim_path.read_text(encoding='utf-8'))
        output += '\n' + sim.stdout + sim.stderr
    except subprocess.TimeoutExpired as exc:
        sim_code = 124
        output += '\n' + ''.join(
            part.decode(errors='replace') if isinstance(part, bytes) else (part or '')
            for part in (exc.stdout, exc.stderr)
        )

    counts = re.findall(r'Ran (\d+) tests?', output)
    skipped = re.search(r'skipped=(\d+)', output)
    failure_match = re.search(r'FAILED \(([^)]+)\)', output)
    failure_fields = dict(re.findall(r'(failures|errors)=(\d+)', failure_match.group(1))) if failure_match else {}
    sims = sim_report.get('simulations', {})
    overall = code == 0 and sim_code == 0 and set(sims) == {'24h', '72h', '7d'}
    for payload in sims.values():
        if payload.get('pass') is not True:
            overall = False

    FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)
    if code != 0:
        FAILURE_LOG.write_text(output, encoding='utf-8')
    else:
        FAILURE_LOG.unlink(missing_ok=True)

    report = {
        'release': '3.7.0',
        'stage': 15,
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(time.monotonic() - started, 2),
        'python': sys.executable,
        'test_command': 'tests/run_isolated.py',
        'status': 'passed' if overall else 'failed',
        'exit_code': code if code else sim_code,
        'tests_run': int(counts[-1]) if counts else None,
        'tests_skipped': int(skipped.group(1)) if skipped else 0,
        'failures': int(failure_fields.get('failures', 0 if code == 0 else 1)),
        'errors': int(failure_fields.get('errors', 0 if code == 0 else 1)),
        'skipped': int(skipped.group(1)) if skipped else 0,
        'simulation_24h': sims.get('24h'),
        'simulation_72h': sims.get('72h'),
        'simulation_7d': sims.get('7d'),
        'lost_messages': sum(int(s.get('lost_messages') or 0) for s in sims.values()) if sims else None,
        'duplicate_replies': sum(int(s.get('duplicate_replies') or 0) for s in sims.values()) if sims else None,
        'stuck_pending': sum(int(s.get('stuck_pending') or 0) for s in sims.values()) if sims else None,
        'flags_default_off': True,
        'output_tail': output[-5000:],
        'failure_log': str(FAILURE_LOG.relative_to(ROOT)) if code != 0 else None,
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                      encoding='utf-8')
    print(RESULT)
    return 0 if overall else 1


if __name__ == '__main__':
    raise SystemExit(main())
