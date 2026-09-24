"""Problemas da conversa de 23–24/09 (revisão com o Patrick)."""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import rituals
import since_last
from commute import Leg
from db import DatabaseManager
from rituals import Rituals
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible

VOLTA = Leg("commute:outing:2026-09-23:1:volta", datetime(2026, 9, 23, 16, 45), datetime(2026, 9, 23, 17, 25),
            "metro_onibus", "volta", "do Starbucks do Shopping da Gávea", "Gávea")


class _Db(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "c.db")

    def tearDown(self):
        self.temp.cleanup()

    def _msg(self, role, content, when, initiative=0):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO conversas (timestamp, role, content, is_initiative) VALUES (?,?,?,?)",
                         (when.isoformat(), role, content, initiative))
            conn.commit()


class SinceLastTest(_Db):
    """18:11: 'ainda tô aqui com a Júlia' — ela já estava em casa desde 17:25."""

    def setUp(self):
        super().setUp()
        self._msg("assistant", "Esqueci mesmo, amor, tô aqui com a Júlia", datetime(2026, 9, 23, 16, 10))
        for p in (patch("commute.Commute.legs_on", side_effect=lambda d: [VOLTA] if d == date(2026, 9, 23) else []),
                  patch.object(since_last, "_now_activity", return_value="tempo livre em casa")):
            p.start()
            self.addCleanup(p.stop)

    def test_she_knows_she_went_home(self):
        lines = "\n".join(since_last.prompt_lines(self.db, datetime(2026, 9, 23, 18, 11)))
        self.assertIn("(às 16:10)", lines)
        self.assertIn("17:25 — chegou em casa", lines)
        self.assertIn("AGORA você está: tempo livre em casa", lines)

    def test_quiet_when_they_are_talking(self):
        self.assertEqual(since_last.prompt_lines(self.db, datetime(2026, 9, 23, 16, 20)), [])


class ShowerTest(_Db):
    """05:19: bom dia de dentro do box (banho 05:10–05:29)."""

    def setUp(self):
        super().setUp()
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.r = Rituals(self.db)
        p = patch.dict(rituals.DAILY_CHANCE, {"bom_dia": 1.0, "boa_noite": 1.0})
        p.start()
        self.addCleanup(p.stop)

    def test_nothing_from_inside_the_shower(self):
        now = datetime(2026, 9, 24, 5, 19)
        self.db.set_estado_relacional("pending_transition_json", json.dumps({
            "routine_type": "shower", "activity": "tomando banho", "transition_at": "2026-09-24T05:10:00",
            "end_at": "2026-09-24T05:29:00"}))
        self.assertTrue(self.r.in_shower(now))
        with patch.object(Rituals, "_state", side_effect=AssertionError("nem olha o estado")):
            self.assertIsNone(self.r.tick(now))
        self.assertFalse(self.r.in_shower(datetime(2026, 9, 24, 5, 30)), "saiu do banho: pode falar")


class SlangAndMealTest(_Db):
    def test_she_knows_papar_and_what_she_ate(self):
        from meals import Meals
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                            autonomy_level,importance,participants_json,share_worthy,created_at)
                            VALUES ('meal:2026-09-23:almoco','2026-09-23T13:16:00','meal','almoço',
                            'Almoço no Shopping da Gávea: comida japonesa','simulated',1,0.3,'[]',0.3,'2026-09-23')""")
            conn.commit()
        lines = "\n".join(Meals(self.db).prompt_lines(datetime(2026, 9, 23, 14, 52)))
        self.assertIn("comeu/almoçou/jantou/papou: SIM — a última foi às 13:16", lines)
        import world_context
        src = open(world_context.__file__, encoding="utf-8").read()
        self.assertIn("papar = comer ('já papou?'", src)


class InitiativeTest(_Db):
    """20:53: 'sumiu hein?' sem saber do aniversário; iniciativas repetindo o jeito."""

    def test_initiative_sees_the_conversation_and_her_last_initiatives(self):
        import bot
        self._msg("user", "Daqui a pouco vou dar uma saída, aniversário numa hamburgueria", datetime(2026, 9, 23, 18, 24))
        self._msg("assistant", "Amor, sumiu hein? Tá vivo? kkk", datetime(2026, 9, 23, 18, 5), initiative=1)
        with patch.object(bot.memory_manager, "db", self.db):
            ctx = bot._initiative_context(datetime(2026, 9, 23, 20, 53))
        self.assertIn("A última mensagem dele foi há 2h29 (às 18:24)", ctx)
        self.assertIn('"Amor, sumiu hein? Tá vivo? kkk"', ctx)
        self.assertIn("Não repita o jeito", ctx)
        self.assertNotIn("'tá vivo?'", bot._PROACTIVE_INSTRUCTIONS["saudade"], "a fala é dela, não nossa")

    def test_ten_short_bubbles_are_allowed(self):
        import response_rhythm
        self.assertGreaterEqual(response_rhythm._SANITY_CEILING, 10)


if __name__ == "__main__":
    unittest.main()
