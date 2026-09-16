"""
Testes Automatizados Offline para o InternalPlanner da Marina Seltin.
"""
import sys
import unittest
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from planner import InternalPlanner


class TestInternalPlanner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_planner.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.planner = InternalPlanner(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_plan_heuristics_greeting(self):
        """Saudações devem retornar plano imediato via heurística."""
        plan = self.planner.plan_heuristics("Oi amor!")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["intent"], "casual_chat")
        self.assertEqual(plan["reaction_emoji"], "🥰")
        self.assertFalse(plan["creates_event"])

    def test_plan_heuristics_love(self):
        """Declarações explícitas de amor devem ativar tom apaixonado e emoji de coração."""
        plan = self.planner.plan_heuristics("Te amo demais, minha vida")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["intent"], "flirting")
        self.assertEqual(plan["reaction_emoji"], "❤️")
        self.assertIn("affection", plan["emotional_deltas"])

    def test_apply_plan_effects_creates_pending_event(self):
        """Ao aplicar um plano que contém evento futuro, deve criar registro no SQLite."""
        plan = {
            "intent": "planning_future",
            "tone": "carinhosa",
            "response_goal": "Apoiar o Patrick na reunião",
            "creates_event": True,
            "event_details": {
                "event_type": "trabalho",
                "description": "Apresentação do projeto para a diretoria",
                "event_at": "amanhã às 14h",
                "follow_up_hint": "perguntar como foi a apresentação"
            },
            "emotional_deltas": {
                "affection": 0.03
            }
        }

        self.planner.apply_plan_effects(plan)

        # Verifica se evento pendente foi criado
        eventos = self.db.listar_eventos_pendentes()
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["event_type"], "trabalho")
        # Verifica se timestamps foram normalizados para formato ISO
        self.assertIsNotNone(eventos[0]["event_at"])
        self.assertIn("T", eventos[0]["event_at"])
        self.assertIsNotNone(eventos[0]["follow_up_after"])
        self.assertIn("T", eventos[0]["follow_up_after"])

        # Verifica se emoção affection subiu
        emocoes = self.db.get_estado_emocional()
        # baseline era 0.85, subiu para 0.88
        self.assertAlmostEqual(emocoes["affection"]["valor"], 0.88, places=2)

    def test_parse_iso_or_relative_datetime(self):
        """Valida que datas relativas e strings em português viram timestamps ISO rigorosos."""
        from datetime import datetime
        from planner import parse_iso_or_relative_datetime

        ref = datetime(2026, 9, 16, 10, 0, 0)  # Quarta-feira 10h

        # ISO direto
        iso_res = parse_iso_or_relative_datetime("2026-09-20T15:30:00", reference_dt=ref)
        self.assertEqual(iso_res, "2026-09-20T15:30:00")

        # Amanhã às 14h -> 2026-09-17T14:00:00
        amanha_res = parse_iso_or_relative_datetime("amanhã às 14h", reference_dt=ref)
        self.assertEqual(amanha_res, "2026-09-17T14:00:00")

        # Daqui a 3 horas -> 2026-09-16T13:00:00
        horas_res = parse_iso_or_relative_datetime("daqui a 3 horas", reference_dt=ref)
        self.assertEqual(horas_res, "2026-09-16T13:00:00")

        # Sexta às 18h -> 2026-09-18T18:00:00
        sexta_res = parse_iso_or_relative_datetime("sexta às 18h", reference_dt=ref)
        self.assertEqual(sexta_res, "2026-09-18T18:00:00")

        # Texto meramente descritivo sem marcadores temporais -> None
        desc_res = parse_iso_or_relative_datetime("perguntar como foi a apresentação", reference_dt=ref)
        self.assertIsNone(desc_res)

        outro_desc = parse_iso_or_relative_datetime("comprar presente pro Patrick", reference_dt=ref)
        self.assertIsNone(outro_desc)

    def test_follow_up_never_scheduled_before_event(self):
        """Valida que o follow-up nunca é agendado no passado ou antes do próprio evento."""
        from datetime import datetime
        ref = datetime(2026, 9, 16, 10, 0, 0)

        plan = {
            "intent": "planning_future",
            "tone": "carinhosa",
            "response_goal": "Acompanhar apresentação",
            "creates_event": True,
            "event_details": {
                "event_type": "trabalho",
                "description": "Reunião de negócios",
                "event_at": "amanhã às 14h",
                # Texto descritivo que antes caía em fallback de hoje 16h
                "follow_up_hint": "perguntar como foi a apresentação",
                "follow_up_prompt": "Como foi a reunião?"
            },
            "emotional_deltas": {}
        }

        self.planner.apply_plan_effects(plan)
        eventos = self.db.listar_eventos_pendentes()
        self.assertEqual(len(eventos), 1)
        ev = eventos[0]

        ev_dt = datetime.fromisoformat(ev["event_at"])
        f_dt = datetime.fromisoformat(ev["follow_up_after"])

        # O follow up deve ser estritamente posterior ao evento
        self.assertGreater(f_dt, ev_dt)
        # Deve ter sido agendado para amanhã às 16h (+2h pós-evento)
        self.assertEqual(f_dt.day, ev_dt.day)
        self.assertEqual(f_dt.hour, 16)


if __name__ == "__main__":
    unittest.main(verbosity=2)


