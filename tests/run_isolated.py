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
        logging.disable(logging.CRITICAL)
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
        result = unittest.TextTestRunner(verbosity=0).run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
