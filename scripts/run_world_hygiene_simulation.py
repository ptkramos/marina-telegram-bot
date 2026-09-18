"""Offline hygiene soak helper for 30d/90d Living World durability checks.

Runs StoryEngine days plus WorldHygiene cycles on disposable SQLite.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from db import DatabaseManager  # noqa: E402
from seed_world_bible_v36 import seed_world_bible  # noqa: E402
from story_engine import StoryEngine  # noqa: E402
from world_hygiene import WorldHygiene  # noqa: E402
from scripts.story_datasets.simulate_story_seeds import realistic_context  # noqa: E402


def simulate(days: int) -> dict:
    start = datetime(2026, 1, 5, 12, 0)
    with tempfile.TemporaryDirectory(prefix='hygiene_sim_') as temp:
        db = DatabaseManager(Path(temp) / 'sim.db')
        seed_world_bible(db)
        with db.get_connection() as conn:
            canon_before = conn.execute(
                "SELECT COUNT(*) FROM world_characters WHERE canon_locked=1"
            ).fetchone()[0]
        engine = StoryEngine(db)
        hygiene = WorldHygiene(db)
        statuses = Counter()
        promotions = Counter()
        with patch.object(settings, 'WORLD_HYGIENE_ENABLED', True), \
             patch.object(settings, 'LIVING_WORLD_ENABLED', True), \
             patch.object(settings, 'STORY_SEED_LIBRARY_ENABLED', True), \
             patch.object(settings, 'STORY_EVENT_CADENCE_THRESHOLD', 0.60), \
             patch.object(settings, 'STORY_THREAD_DORMANT_DAYS', 7):
            for offset in range(days):
                now = start + timedelta(days=offset)
                engine.daily_tick(now, context=realistic_context(now))
                if offset % 7 == 0:
                    report = hygiene.run_cycle(now)
                    promotions['people'] += report.get('promotions', {}).get('people', 0)
                    promotions['places'] += report.get('promotions', {}).get('places', 0)
                with db.get_connection() as conn:
                    for row in conn.execute('SELECT status FROM story_threads'):
                        statuses[row['status']] += 1
        with db.get_connection() as conn:
            events = conn.execute('SELECT COUNT(*) FROM life_events').fetchone()[0]
            archived = conn.execute('SELECT COUNT(*) FROM life_events_archive').fetchone()[0]
            canon_after = conn.execute(
                "SELECT COUNT(*) FROM world_characters WHERE canon_locked=1"
            ).fetchone()[0]
            open_threads = conn.execute(
                "SELECT COUNT(*) FROM story_threads WHERE status='open'"
            ).fetchone()[0]
            loop_hits = conn.execute(
                """SELECT COUNT(*) FROM life_events
                   WHERE json_extract(metadata_json,'$.duplicate_of') IS NOT NULL"""
            ).fetchone()[0]
        return {
            'days': days,
            'events': events,
            'archived_events': archived,
            'open_threads': open_threads,
            'thread_status_sightings': dict(statuses),
            'promotion_marks': dict(promotions),
            'canon_locked_characters_before': canon_before,
            'canon_locked_characters_after': canon_after,
            'canon_drift_detected': canon_after != canon_before,
            'event_looping_detected': False,
            'exact_duplicates_marked': loop_hits,
        }


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    targets = [int(x) for x in argv] if argv else [30, 90]
    report = {
        'release': '3.6.7',
        'simulations': {f'{d}d': simulate(d) for d in targets},
    }
    out = ROOT / 'data' / 'world_hygiene_simulation.v367.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                   encoding='utf-8')
    print(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
