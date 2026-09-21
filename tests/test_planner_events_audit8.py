"""Auditoria #8 — planner, eventos e lembretes.

Caso real (21/09 12:34): o debouncer juntou duas mensagens do Patrick:
    "A gente é né amor ksksksk tô falando exatamente isso, que qualquer coisa você me lembra"
    "Em falar em me lembrar, quarta-feira eu tenho dentista, 10h"
O evento saiu com a descrição = lote inteiro e, por causa do "a gente", como
compromisso do CASAL — dono Marina, confirmado, no apartamento dela. Na quarta
das 10h às 12h o mundo dela a colocaria "em um compromisso" (o dentista dele),
e o lembrete das 9h mandaria o texto cru.
"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from planner import InternalPlanner, detect_explicit_scheduled_event

LOTE_REAL = ("A gente é né amor ksksksk tô falando exatamente isso, que qualquer coisa você me lembra\n"
             "Em falar em me lembrar, quarta-feira eu tenho dentista, 10h")
REF = datetime(2026, 9, 21, 12, 34)


class ExplicitEventDetectorTests(unittest.TestCase):
    def test_lote_real_vira_dentista_do_patrick(self):
        ev = detect_explicit_scheduled_event(LOTE_REAL, reference_dt=REF)
        self.assertEqual(ev["description"], "dentista")
        self.assertEqual(ev["event_at"], "2026-09-23T10:00:00")
        self.assertEqual(ev["owner"], "patrick_ramos")

    def test_descricao_sem_dia_nem_hora(self):
        for texto, esperado in (
            ("vou ter prova quinta às 14h", "prova"),
            ("amanhã tenho consulta no cardiologista às 9", "consulta no cardiologista"),
            ("Amanhã às 18h tenho uma reunião de teste", "uma reunião de teste"),
        ):
            with self.subTest(texto=texto):
                self.assertEqual(detect_explicit_scheduled_event(texto, reference_dt=REF)["description"], esperado)

    def test_negacao_so_vale_no_trecho_do_compromisso(self):
        self.assertIsNone(detect_explicit_scheduled_event("Amanhã às 18h não tenho reunião", reference_dt=REF))
        lote = "não sei o que comer hoje\ntenho dentista amanhã às 10h"
        self.assertEqual(detect_explicit_scheduled_event(lote, reference_dt=REF)["description"], "dentista")


class EventOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "planner8.db")
        self.planner = InternalPlanner(db=self.db, llm_client=object())

    def tearDown(self):
        self.temp.cleanup()

    def test_compromisso_do_patrick_nao_ocupa_a_marina(self):
        from calendar_world import CalendarWorld
        ev = detect_explicit_scheduled_event(LOTE_REAL, reference_dt=REF)
        plan = {"creates_event": True, "event_details": ev, "should_offer_reminder": False}
        self.planner.apply_plan_effects(plan, conversation_id=None)
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM eventos_pendentes").fetchone()
        self.assertEqual(row["owner_character_key"], "patrick_ramos")
        self.assertEqual(row["confirmed"], 0)
        self.assertIsNone(row["location_key"])
        self.assertEqual(row["description"], "dentista")
        self.assertIsNone(CalendarWorld(self.db).current(datetime(2026, 9, 23, 10, 30), include_academic=False))

    def test_programa_do_casal_continua_sendo_do_casal(self):
        plan = {"creates_event": True, "should_offer_reminder": False,
                "event_details": {"event_type": "encontro", "description": "assistir ao filme juntos",
                                  "event_at": "2026-09-26T21:00:00"}}
        self.planner.apply_plan_effects(plan, conversation_id=None)
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT owner_character_key, confirmed FROM eventos_pendentes").fetchone()
        self.assertEqual((row["owner_character_key"], row["confirmed"]), ("marina", 1))


class ReplySafetyTests(unittest.TestCase):
    """Resposta-lixo sem salvamento era enviada assim mesmo."""

    def test_fallback_seguro_nunca_propoe_ligacao(self):
        import bot
        texto = bot._safe_fallback_reply(datetime(2026, 9, 23, 9, 30))
        self.assertIn("09:30", texto)
        self.assertIn("mensagem aqui no Telegram", texto)
        self.assertFalse(bot._proposes_live_call(texto))
        self.assertFalse(bot._proposes_live_call(bot._safe_fallback_reply()))

    def test_reconhece_horario_citado_em_varios_formatos(self):
        import bot
        nove_meia = datetime(2026, 9, 23, 9, 30)
        for texto in ("te aviso às 09:30", "fechado, 9:30 eu te chamo", "9h30 te mando msg"):
            with self.subTest(texto=texto):
                self.assertTrue(bot._mentions_clock(texto, nove_meia))
        self.assertFalse(bot._mentions_clock("pode deixar amor", nove_meia))
        self.assertFalse(bot._mentions_clock("às 19:30", nove_meia))
        self.assertTrue(bot._mentions_clock("te lembro 9h", datetime(2026, 9, 23, 9, 0)))


if __name__ == "__main__":
    unittest.main()
