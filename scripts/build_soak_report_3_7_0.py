"""Build RELATORIO_SOAK_MARINA_3_7_0.md skeleton from telemetry events."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import DatabaseManager


def _latencies(rows):
    vals = [float(r['actual_latency_seconds']) for r in rows
            if r['actual_latency_seconds'] is not None]
    if not vals:
        return {'median': None, 'p90': None, 'p95': None, 'max': None, 'n': 0}
    vals.sort()

    def pct(p):
        idx = min(len(vals) - 1, max(0, int(round(p * (len(vals) - 1)))))
        return vals[idx]

    return {
        'median': statistics.median(vals),
        'p90': pct(0.90),
        'p95': pct(0.95),
        'max': vals[-1],
        'n': len(vals),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    default_db = ROOT / 'marin_memory.db' if (ROOT / 'marin_memory.db').exists() else ROOT / 'data' / 'marina.db'
    parser.add_argument('--db', type=Path, default=default_db)
    parser.add_argument('--out', type=Path, default=ROOT / 'RELATORIO_SOAK_MARINA_3_7_0.md')
    parser.add_argument('--period', default='TBD (preencher após soak)')
    args = parser.parse_args()

    if not args.db.exists():
        report = (
            f'# Relatório Soak Marina 3.7.0\n\n'
            f'Período: {args.period}\n\n'
            f'DB `{args.db}` ainda sem telemetria. Rode após soak com '
            f'`REAL_USAGE_TELEMETRY_ENABLED=true`.\n'
        )
        args.out.write_text(report, encoding='utf-8')
        print(args.out)
        return 0

    db = DatabaseManager(args.db)
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT * FROM response_availability_events ORDER BY id'
        ).fetchall()]
        batches = [dict(r) for r in conn.execute(
            'SELECT status, COUNT(*) AS n FROM response_pending_batches GROUP BY status'
        ).fetchall()]

    decisions = Counter(r['decision'] for r in rows)
    by_activity = defaultdict(list)
    by_urgency = defaultdict(list)
    for r in rows:
        if r['actual_latency_seconds'] is not None:
            by_activity[r['activity_type']].append(float(r['actual_latency_seconds']))
            by_urgency[r['urgency']].append(float(r['actual_latency_seconds']))
    lat = _latencies(rows)
    total = sum(decisions.values()) or 1

    def pct(key):
        return round(100.0 * decisions.get(key, 0) / total, 1)

    lines = [
        '# Relatório Soak Marina 3.7.0',
        '',
        f'Gerado em: {datetime.utcnow().isoformat()}Z',
        f'Período: {args.period}',
        f'Eventos de telemetria: {len(rows)}',
        '',
        '## Latência',
        f'- median: {lat["median"]}',
        f'- P90: {lat["p90"]}',
        f'- P95: {lat["p95"]}',
        f'- max: {lat["max"]}',
        '',
        '## Decisões',
        f'- REPLY_NOW: {pct("REPLY_NOW")}%',
        f'- REPLY_BRIEFLY: {pct("REPLY_BRIEFLY")}%',
        f'- DEFER: {pct("DEFER")}%',
        '',
        '## Batches por status',
    ]
    for b in batches:
        lines.append(f'- {b["status"]}: {b["n"]}')
    lines.extend([
        '',
        f'Urgent overrides: {sum(1 for r in rows if r.get("urgent_override"))}',
        f'Batch merges: {sum(1 for r in rows if r.get("batch_merged"))}',
        f'Error flags: {sum(1 for r in rows if r.get("error_flag"))}',
        '',
        '## Feedback manual',
        '- (preencher)',
        '',
        '## P0 / P1 / P2',
        '- (preencher após gate Codex)',
        '',
        '## Gate final',
        '- PENDING independent validation',
        '',
    ])
    args.out.write_text('\n'.join(lines), encoding='utf-8')
    print(args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
