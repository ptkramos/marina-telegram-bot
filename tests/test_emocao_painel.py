"""25/09 (/emocao): carinho repetido não vira 23 linhas nem tesão; vínculo não gruda no teto;
exausta e logo depois de gozar ela não aparece 'esquentando'."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from db import DatabaseManager
from emotion import EmotionEngine, PATRICK_TARGET

T = datetime(2026, 9, 24, 19, 0)


class EmocaoPainelTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "e.db")
        self.eng = EmotionEngine(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_same_feeling_merges_instead_of_repeating(self):
        for i in range(10):
            self.eng.feel("afeto", "carinho", 0.4, f"ele foi fofo ({i})", T + timedelta(minutes=10 * i),
                          target=PATRICK_TARGET, source_key=f"planner:{i}")
        with self.db.get_connection() as conn:
            n = conn.execute("SELECT COUNT(*) FROM emotion_episodes WHERE kind='carinho'").fetchone()[0]
        self.assertEqual(n, 1)
        ep = self.eng.episodes(T + timedelta(minutes=95))[0]
        self.assertIn("(9)", ep.cause, "a causa é a mais recente")
        self.assertFalse(self.eng.feel("afeto", "carinho", 0.4, "x", T, target=PATRICK_TARGET,
                                       source_key="planner:0"), "mesma fonte não sente de novo")

    def test_bond_does_not_stick_to_the_ceiling(self):
        for i in range(60):   # uma noite inteira de conversa boa
            self.db.ajustar_emocao("affection", 0.04 * 0.4, now=T + timedelta(minutes=2 * i))
        with self.db.get_connection() as conn:
            v = conn.execute("SELECT valor FROM estado_emocional WHERE chave='affection'").fetchone()[0]
        self.assertLess(v, 0.95)

    def test_exhausted_right_after_coming_is_not_horny(self):
        from unittest.mock import patch
        with patch.object(EmotionEngine, "last_release", return_value=T - timedelta(hours=4)):
            v, _, _ = self.eng._libido(T, "tpm", 0.2, 0.0, 0.65, {"romantic_intensity": 0.98, "hurt": 0.0}, 0.1, [])
        self.assertLess(v, 0.35)


if __name__ == "__main__":
    unittest.main()
