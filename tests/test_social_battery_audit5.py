"""Bateria social (Auditoria #5, desenho do Patrick em 21/09): pique pra GENTE,
gasto pela agenda real, recarregado em casa/dormindo, nunca pelo tamanho da
conversa com o Patrick."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from seed_academic_v36 import seed_academic
from world_state import WorldStateManager


class SocialBatteryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "sb.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        start = datetime(2026, 9, 21, 23, 0)  # segunda à noite
        with self.db.get_connection() as conn:
            conn.execute("UPDATE estado_emocional SET valor=0.9, updated_at=? "
                         "WHERE chave='social_battery'", (start.isoformat(),))
        self.db.set_estado_relacional("social_battery_accrued_at", start.isoformat())
        self.world = WorldStateManager(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _battery_at(self, day, hour):
        self.world.resolve(datetime(2026, 9, day, hour, 0))
        return self.db.get_estado_emocional()["social_battery"]["valor"]

    def test_dia_inteiro_na_puc_esvazia_e_casa_recarrega(self):
        chegada = self._battery_at(22, 15)  # terça: aula 7h–15h
        self.assertLess(chegada, 0.40)
        self.assertGreater(self._battery_at(22, 22), chegada)
        self.assertGreaterEqual(self._battery_at(23, 6), 0.95)  # dormiu

    def test_conta_nao_depende_de_quantas_vezes_foi_consultada(self):
        direto = self._battery_at(22, 15)
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        db2 = DatabaseManager(Path(other.name) / "sb2.db")
        seed_world_bible(db2)
        seed_academic(db2)
        start = datetime(2026, 9, 21, 23, 0)
        with db2.get_connection() as conn:
            conn.execute("UPDATE estado_emocional SET valor=0.9, updated_at=? "
                         "WHERE chave='social_battery'", (start.isoformat(),))
        db2.set_estado_relacional("social_battery_accrued_at", start.isoformat())
        w2 = WorldStateManager(db2)
        for hour in (7, 9, 11, 13, 15):
            w2.resolve(datetime(2026, 9, 22, hour, 0))
        self.assertAlmostEqual(db2.get_estado_emocional()["social_battery"]["valor"], direto, places=2)

    def test_conversa_longa_sem_delta_nao_gasta_bateria(self):
        """Sexta sem aula: horas de conversa em casa só recarregam."""
        inicio = self._battery_at(25, 10)
        for hour in range(11, 18):
            self.db.adicionar_mensagem("user", "oi amor", timestamp=datetime(2026, 9, 25, hour, 0).isoformat())
        self.assertGreaterEqual(self._battery_at(25, 18), inicio)

    def test_bateria_nao_relaxa_pelo_relogio(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE estado_emocional SET valor=0.3, updated_at=? WHERE chave='social_battery'",
                         (datetime(2026, 9, 22, 15).isoformat(),))
        valor = self.db.get_estado_emocional(now=datetime(2026, 9, 23, 3))["social_battery"]["valor"]
        self.assertAlmostEqual(valor, 0.3)

    def test_prompt_deixa_claro_que_nao_e_cansaco_do_patrick(self):
        root = Path(__file__).resolve().parent.parent
        ctx = (root / "world_context.py").read_text(encoding="utf-8")
        self.assertIn("NÃO é cansaço do Patrick", ctx)
        planner = (root / "planner.py").read_text(encoding="utf-8")
        self.assertIn("NUNCA mexa nela pelo tamanho da conversa", planner)


if __name__ == "__main__":
    unittest.main()
