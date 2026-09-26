"""26/09: o reset apagava os /feedback do Patrick e deixava os episódios de emoção."""
import tempfile
import unittest
from pathlib import Path

from db import DatabaseManager


class ResetSoakTest(unittest.TestCase):
    def test_feedback_fica_e_emocao_sai(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(Path(tmp) / "r.db")
            db.salvar_feedback("FB-1", "tirar o zoom do app")
            db.adicionar_mensagem("user", "oi")
            with db.get_connection() as conn:
                conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('sono:noite:2026-09-25', '{}', '2026-09-25')")
                conn.commit()
            db.reset_soak_learning()
            self.assertEqual([f["id"] for f in db.listar_feedbacks()], ["FB-1"])
            with db.get_connection() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM conversas").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM emotion_episodes").fetchone()[0], 0)
                self.assertIsNone(conn.execute("SELECT 1 FROM world_bootstrap WHERE key LIKE 'sono:%'").fetchone())


if __name__ == "__main__":
    unittest.main()
