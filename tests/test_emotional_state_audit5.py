"""Auditoria #5 — estado emocional.

Em 20–21/09 a Marina não mandou nenhuma mensagem espontânea; o retorno ao
baseline só rodava nesse caminho. 56 turnos de deltas positivos travaram
carinho, brincadeira e intensidade romântica em 1,0.
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager


class EmotionalDynamicsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "emo.db")
        self.t0 = datetime(2026, 9, 21, 9, 0)
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM estado_emocional")
            conn.execute("INSERT INTO estado_emocional VALUES ('affection', 0.85, 0.85, ?)",
                         (self.t0.isoformat(),))

    def tearDown(self):
        self.temp.cleanup()

    def _val(self, when):
        return self.db.get_estado_emocional(now=when)["affection"]["valor"]

    def test_emocao_volta_ao_baseline_com_o_tempo_sem_proatividade(self):
        # D14: carinho é vínculo — volta devagar (meia-vida de 72 h), não em 6 h.
        with self.db.get_connection() as conn:
            conn.execute("UPDATE estado_emocional SET valor=1.0")
        self.assertAlmostEqual(self._val(self.t0 + timedelta(hours=72)), 0.925, places=2)
        self.assertLess(self._val(self.t0 + timedelta(days=10)), 0.87)

    def test_conversa_longa_nao_trava_no_teto(self):
        # D14: o planner só mexe no vínculo, devagar; energia e brincadeira
        # (as que travavam em 1,0) saem do corpo e do humor.
        from emotion import apply_planner_deltas
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO estado_emocional VALUES ('energy', 0.75, 0.75, ?)", (self.t0.isoformat(),))
        for i in range(56):
            applied = apply_planner_deltas(self.db, {"affection": 0.05, "energy": 0.05, "playfulness": 0.05},
                                           now=self.t0 + timedelta(minutes=5 * i))
            self.assertEqual(set(applied), {"affection"})
        fim = self.t0 + timedelta(minutes=5 * 55)
        self.assertLess(self._val(fim), 1.0)
        self.assertEqual(self.db.get_estado_emocional(now=self.t0)["energy"]["valor"], 0.75)

    def test_briga_derruba_mesmo_no_alto(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE estado_emocional SET valor=0.98, updated_at=?", (self.t0.isoformat(),))
        self.db.ajustar_emocao("affection", -0.05, now=self.t0)
        self.assertAlmostEqual(self._val(self.t0), 0.93, places=3)

    def test_decay_legado_nao_desfaz_relaxamento(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE estado_emocional SET valor=1.0")
        later = self.t0 + timedelta(hours=12)
        antes = self._val(later)
        with patch("db.datetime") as fake:
            fake.now.return_value = later
            fake.fromisoformat = datetime.fromisoformat
            self.db.aplicar_decay_emocional(taxa=0.05)
        self.assertLessEqual(self._val(later), antes)


class EnergyAndLabelsTests(unittest.TestCase):
    def test_energia_da_rotina_usa_a_fase_do_ciclo_como_o_prompt(self):
        # D14: rotina e prompt leem a mesma energia (a do corpo), e a menstruação pesa.
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "en.db")
        from world_state import current_energy
        from emotion import EmotionEngine
        now = datetime(2026, 9, 23, 11, 0)
        self.assertEqual(current_energy(db, now), EmotionEngine(db).energy(now))
        with patch.object(EmotionEngine, "_cycle", return_value=("menstrual", 1)):
            menstruada = current_energy(db, now)
        with patch.object(EmotionEngine, "_cycle", return_value=("folicular", 8)):
            folicular = current_energy(db, now)
        self.assertLess(menstruada, folicular)

    def test_playfulness_tem_rotulo_em_portugues(self):
        src = (Path(__file__).resolve().parent.parent / "world_context.py").read_text(encoding="utf-8")
        self.assertIn("'playfulness': 'vontade de brincar e provocar'", src)


if __name__ == "__main__":
    unittest.main()
