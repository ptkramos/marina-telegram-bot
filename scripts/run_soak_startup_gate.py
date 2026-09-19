"""Exercise health and scheduled-job registration on a copy of production data."""
import asyncio
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def startup():
    import bot
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    fake_bot = AsyncMock()
    try:
        with patch.object(bot, 'AsyncIOScheduler', return_value=scheduler):
            await bot.post_init(SimpleNamespace(bot=fake_bot))
        jobs = {job.func.__name__ for job in scheduler.get_jobs()}
        required = {'autonomous_routine', 'reminders_routine', 'pending_response_routine',
                    'memory_hygiene_routine', 'session_reflection_routine'}
        assert required <= jobs, f'Missing startup jobs: {required - jobs}'
        assert not fake_bot.mock_calls, 'Startup unexpectedly attempted Telegram delivery'
        print('[PASS] All five production jobs registered; no Telegram messages sent.')
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            await asyncio.sleep(0)


def main():
    source = Path(os.environ.get('MARINA_DB_PATH') or ROOT / 'marin_memory.db').resolve()
    with tempfile.TemporaryDirectory(prefix='marina_startup_gate_') as td:
        target = Path(td) / 'copy.db'
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
        os.environ['MARINA_DB_PATH'] = str(target)
        from healthcheck import HealthChecker
        if HealthChecker().run():
            return 1
        asyncio.run(startup())
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
