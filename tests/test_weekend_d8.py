"""Fase D8 — fim de semana: convites dos amigos, e ela decide no dia pelo emocional (23/09)."""
import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from social_day import INVITES_KEY, SocialDay


def _emo(battery, energy):
    return {"social_battery": {"valor": battery}, "energy": {"valor": energy},
            "affection": {"valor": 0.8}, "playfulness": {"valor": 0.7}, "romantic_intensity": {"valor": 0.8}}


class WeekendInvitesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "fds.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        self.day = SocialDay(self.db)
        self.weekends = [date(2026, 9, 26) + timedelta(days=7 * w + d) for w in range(8) for d in (0, 1)]
        self.plans = [inv for d in self.weekends for inv in self.day._invite_plan(d)]

    def tearDown(self):
        self.temp.cleanup()

    def _events(self, like):
        with self.db.get_connection() as conn:
            return [r[0] for r in conn.execute("SELECT summary FROM life_events WHERE event_key LIKE ?", (like,))]

    def test_friends_invite_her_often_on_weekends(self):
        self.assertGreater(len(self.plans), len(self.weekends))
        for inv in self.plans:
            self.assertLess(inv["invite_at"], inv["start"])
            self.assertLessEqual(inv["invite_at"], inv["decide_at"])
            self.assertLess(inv["decide_at"], inv["start"])

    def test_invite_arrives_then_she_decides_on_the_day(self):
        inv = self.plans[0]
        invite_at = datetime.fromisoformat(inv["invite_at"])
        with patch.object(self.db, "get_estado_emocional", return_value=_emo(0.9, 0.8)):
            self.day.process_invites(invite_at - timedelta(minutes=5))
            self.assertEqual(self.day.pending_invites(invite_at), [])
            self.day.process_invites(invite_at + timedelta(minutes=5))
            self.assertEqual([i["key"] for i in self.day.pending_invites(invite_at + timedelta(minutes=5))],
                             [inv["key"]])
            self.assertTrue(any("te chamou" in s for s in self._events(f"{inv['key']}:convite")))

    def test_rested_and_social_she_goes(self):
        inv = next(i for i in self.plans if "bia_andrade" in i["friends"])
        decide = datetime.fromisoformat(inv["decide_at"]) + timedelta(minutes=1)
        with patch.object(self.db, "get_estado_emocional", return_value=_emo(0.95, 0.9)), \
             patch("sleep_plan.SleepPlan.hours_slept", return_value=8.0), \
             patch("social_day.INVITE_BASE_YES", 0.95):
            self.day.process_invites(decide)
        status = json.loads(self.db.get_estado_relacional()[INVITES_KEY])[inv["key"]]["status"]
        self.assertEqual(status, "accepted")
        with self.db.get_connection() as conn:
            self.assertTrue(conn.execute("SELECT 1 FROM eventos_pendentes WHERE source_key=? AND confirmed=1",
                                         (inv["key"],)).fetchone())

    def test_drained_she_declines_and_says_why(self):
        inv = self.plans[0]
        decide = datetime.fromisoformat(inv["decide_at"]) + timedelta(minutes=1)
        # 27/09: quem decide é o que ela sente (agenda_viva.Disposicao), não mais o INVITE_BASE_YES
        from emotion import Feeling
        esgotada = Feeling(now=decide, energy=0.15, hours_slept=5.0, awake_since=None, hunger=0.3, discomfort=0.0,
                           discomfort_why="", cycle_phase="folicular", valence=0.35, arousal=0.4, playfulness=0.3,
                           social_battery=0.1)
        with patch("agenda_viva.Disposicao._feeling", return_value=esgotada):
            self.day.process_invites(decide)
        data = json.loads(self.db.get_estado_relacional()[INVITES_KEY])[inv["key"]]
        self.assertEqual(data["status"], "declined")
        self.assertTrue(any("Recusou o convite" in s for s in self._events(f"{inv['key']}:resposta")))
        with self.db.get_connection() as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM eventos_pendentes WHERE source_key=?",
                                          (inv["key"],)).fetchone())

    def test_decision_is_hers_not_always_yes(self):
        decisions = []
        with patch.object(self.db, "get_estado_emocional", return_value=_emo(0.6, 0.6)):
            for inv in self.plans:
                decisions.append(self.day._willing(inv, datetime.fromisoformat(inv["decide_at"]))[0])
        self.assertTrue(any(decisions) and not all(decisions))

    def test_prompt_shows_open_invites(self):
        from world_context import WorldContextBuilder
        inv = self.plans[0]
        at = datetime.fromisoformat(inv["invite_at"]) + timedelta(minutes=5)
        with patch.object(self.db, "get_estado_emocional", return_value=_emo(0.9, 0.8)):
            self.day.process_invites(at)
        text = "\n".join(WorldContextBuilder(self.db)._social_day_block(at))
        self.assertIn("Convite em aberto", text)


if __name__ == "__main__":
    unittest.main()


class ConviteAntesDoResetTest(unittest.TestCase):
    """26/09: o reset do soak (04:19) apagou o bar de sábado e o cinema de domingo — os convites
    tinham "chegado" dias antes, antes do início da vida registrada, e eram descartados."""

    def test_role_futuro_com_convite_antigo_ainda_chega(self):
        import tempfile
        from pathlib import Path
        from db import DatabaseManager
        from social_day import SocialDay
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "r.db")
        reset = datetime(2026, 9, 26, 4, 19)
        with db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), ('social_day_start', ?, ?)",
                         (reset.isoformat(), reset.isoformat()))
            conn.commit()
        day = SocialDay(db)
        plano = day._invite_plan(reset.date())
        antigos = [i for i in plano if datetime.fromisoformat(i["invite_at"]) < reset
                   and datetime.fromisoformat(i["start"]) > reset + timedelta(hours=1)]
        if not antigos:
            self.skipTest("sem convite antigo nesse sábado")
        # 27/09: ela vê o convite quando acorda (antes ficava registrado às 04:19, com ela dormindo)
        acorda = datetime(2026, 9, 26, 9, 5)
        with patch("sleep_plan.SleepPlan.wake", return_value=acorda):
            day.process_invites(reset + timedelta(minutes=5))
            self.assertNotIn(antigos[0]["key"], day._invites(), "dormindo: ainda não viu")
            day.process_invites(acorda + timedelta(minutes=5))
        guardados = day._invites()
        self.assertIn(antigos[0]["key"], guardados)
        self.assertEqual(guardados[antigos[0]["key"]]["invite_at"], acorda.isoformat())
