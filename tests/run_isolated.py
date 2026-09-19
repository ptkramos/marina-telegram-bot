"""Roda a suíte com os singletons legados apontando para SQLite descartável."""

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="marina_tests_") as temp:
        os.environ["MARINA_DB_PATH"] = str(Path(temp) / "global_test.db")
        # Keep only operational/provider switches deterministic. Canonical
        # release features no longer read these environment variables.
        baseline_off = (
            'LIVING_WORLD_ENABLED', 'STORY_SEED_LIBRARY_ENABLED',
            'KNOWLEDGE_PRIVACY_ENABLED', 'RELATIONSHIP_WORLD_ENABLED',
            'CAMERA_WORLD_CONTINUITY_ENABLED', 'WORLD_HYGIENE_ENABLED',
            'RESPONSE_RHYTHM_ENABLED', 'VOICE_PROSODY_ENABLED',
            'VOICE_PROSODY_EMOTION_ENABLED', 'VOICE_PROSODY_PAUSES_ENABLED',
            'VOICE_PROSODY_SOUND_TAGS_ENABLED', 'VOICE_PROSODY_FILLERS_ENABLED',
            'VOICE_PROSODY_CONTINUOUS_SOUND_ENABLED', 'CALENDAR_CONTINUITY_ENABLED',
            'ACADEMIC_LIFE_ENABLED', 'ACADEMIC_AUTO_TERM_GENERATION',
            'REAL_CONTEXT_FETCH_ENABLED', 'FERIADOS_API_ENABLED',
            'REAL_WORLD_PLACE_LOOKUP_ENABLED', 'RESPONSE_AVAILABILITY_ENABLED',
            'HUMAN_REPLY_LATENCY_ENABLED', 'PENDING_CONVERSATION_BATCHING_ENABLED',
            'REAL_USAGE_TELEMETRY_ENABLED', 'SESSION_REFLECTION_ENABLED',
            'MEMORY_HYGIENE_ENABLED',
            'PHOTO_PROVIDER_MAINTENANCE',
        )
        for flag in baseline_off:
            os.environ[flag] = 'false'
        # Production cannot run with a half-seeded database. Give singleton
        # based integration tests the same canonical baseline as the bot.
        from db import DatabaseManager
        from seed_world_bible_v36 import seed_world_bible
        from seed_academic_v36 import seed_academic

        global_db = DatabaseManager(Path(os.environ["MARINA_DB_PATH"]))
        seed_world_bible(global_db)
        seed_academic(global_db)
        with global_db.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO world_bootstrap (key,value,updated_at)
                   VALUES ('clean_canonical_start_done','1','2026-09-18T00:00:00')"""
            )
        target = sys.argv[1] if len(sys.argv) > 1 else None
        if target:
            stem = Path(target).stem
            suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=f"{stem}.py")
        else:
            suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
