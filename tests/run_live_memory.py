"""Run only the three synthetic LLM fixtures against the configured provider.

No production database or conversation is read. Skips count as a failed gate.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix='marina_synthetic_llm_') as td:
        os.environ['MARINA_DB_PATH'] = str(Path(td) / 'test.db')
        from tests.test_memory_consolidator import TestMemoryConsolidatorLLM
        original_setup = TestMemoryConsolidatorLLM.setUpClass.__func__

        def bounded_setup(cls):
            original_setup(cls)
            cls.consolidator.llm = cls.consolidator.llm.with_options(timeout=45, max_retries=0)
        TestMemoryConsolidatorLLM.setUpClass = classmethod(bounded_setup)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestMemoryConsolidatorLLM)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
