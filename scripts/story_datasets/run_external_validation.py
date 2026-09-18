"""One-command validation handoff; execute from the repository with the project venv.

The runner writes a compact JSON result for review by a separate agent. It is
never imported or executed by the bot.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / 'data' / 'story_seeds' / 'validation_results.v1.json'
STEPS = (
    ('library_validator', 'scripts/story_datasets/validate_story_seed_library.py'),
    ('isolated_test_suite', 'tests/run_isolated.py'),
    ('long_simulation', 'scripts/story_datasets/simulate_story_seeds.py'),
)


def save(report):
    RESULT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
                      encoding='utf-8')


def main():
    report = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
              'python': sys.executable, 'steps': {}}
    save(report)
    for name, script in STEPS:
        start = time.monotonic()
        try:
            step_timeout = 600 if name == 'isolated_test_suite' else 360
            completed = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT,
                                       capture_output=True, text=True, timeout=step_timeout)
            output = completed.stdout + completed.stderr
            detail = {'exit_code': completed.returncode,
                      'duration_seconds': round(time.monotonic() - start, 2),
                      'output_tail': output[-2000:]}
            if name == 'isolated_test_suite':
                match = re.search(r'Ran (\d+) tests?', output)
                skipped = re.search(r'skipped=(\d+)', output)
                detail['tests_run'] = int(match.group(1)) if match else None
                detail['tests_skipped'] = int(skipped.group(1)) if skipped else 0
            if name == 'long_simulation' and completed.returncode == 0:
                simulation = json.loads((ROOT / 'data/story_seeds/simulation_report.v1.json').read_text(encoding='utf-8'))
                detail['simulation_checks'] = simulation['checks']
        except subprocess.TimeoutExpired as exc:
            detail = {'exit_code': None, 'duration_seconds': round(time.monotonic() - start, 2),
                      'error': f'timeout after {exc.timeout} seconds'}
        report['steps'][name] = detail
        save(report)
        if detail['exit_code'] != 0:
            report['status'] = 'failed'
            break
    else:
        report['status'] = 'passed'
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    save(report)
    print(RESULT)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
