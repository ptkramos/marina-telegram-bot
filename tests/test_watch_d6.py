"""Fase D6 (parte 1) — o que ela assiste, cânone de gostos e descoberta sozinha (23/09)."""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import watch
from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from watch import DISCOVERY_POOL, STATE_KEY, Watching


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "tv.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        self.tv = Watching(self.db)
        self.days = [date(2026, 9, 21) + timedelta(days=i) for i in range(21)]
        p = patch.object(watch, "WATCH_NIGHT_CHANCE", 1.0)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _roomy_night(self, skip=0):
        """Noite com tempo de sobra (véspera de aula às 7h ela deita 22h30 e não assiste nada)."""
        roomy = [d for d in self.days
                 if (lambda p: p and (p["bed"] - p["start"]) >= timedelta(minutes=180))(self.tv.night_plan(d))]
        return roomy[skip]

    def test_taste_canon_from_migration(self):
        with self.db.get_connection() as conn:
            rows = dict(conn.execute("SELECT value, preference_type FROM character_preferences "
                                     "WHERE category LIKE 'watched_%' OR category='games'").fetchall())
        for title in ("Elite (viu na época do auge)", "Sono Bisque Doll (My Dress-Up Darling)", "Dandadan",
                      "High School DxD", "Pousando no Amor", "It Takes Two", "The Sims"):
            self.assertIn(title, rows)
        self.assertEqual(rows["One Piece (começou por causa do Patrick)"], "current_interest")

    def test_night_session_becomes_state_and_event_once(self):
        day = self._roomy_night()
        plan = self.tv.night_plan(day)
        now = plan["start"] + timedelta(minutes=2)
        self.assertEqual(self.tv.materialize(now), 1)
        state = json.loads(self.db.get_estado_relacional()["pending_transition_json"])
        self.assertTrue(state["activity"].startswith("vendo "))
        self.assertTrue(state["activity"].endswith(" no sofá"))
        self.assertEqual(self.tv.materialize(now + timedelta(minutes=20)), 0, "uma sessão por noite")
        with self.db.get_connection() as conn:
            self.assertTrue(conn.execute("SELECT 1 FROM life_events WHERE event_key=?",
                                         (f"tv:{day.isoformat()}",)).fetchone())

    def test_finishing_a_title_she_discovers_the_next_one_alone(self):
        data = self.tv.state()
        cur = data["current"]
        cur["ep"] = cur["episodes"] - 1
        self.db.set_estado_relacional(STATE_KEY, json.dumps(data, ensure_ascii=False))
        day = self._roomy_night(1)
        with patch.object(watch, "LIKE_CHANCE", 1.0):
            self.tv.materialize(self.tv.night_plan(day)["start"] + timedelta(minutes=1))
        after = self.tv.state()
        self.assertIn(cur["title"], after["finished"])
        self.assertNotEqual(after["current"]["title"], cur["title"])
        self.assertIn(after["current"]["title"], [t[0] for t in DISCOVERY_POOL])
        with self.db.get_connection() as conn:
            liked = conn.execute("SELECT preference_type FROM character_preferences WHERE value=?",
                                 (f"{cur['title']} (descobriu sozinha)",)).fetchone()
        self.assertEqual(liked[0], "discovered_preference")

    def test_weeks_of_nights_advance_and_never_repeat_a_finished_title(self):
        for day in self.days:
            plan = self.tv.night_plan(day)
            if plan:
                self.tv.materialize(plan["start"] + timedelta(minutes=1))
        data = self.tv.state()
        self.assertEqual(len(data["finished"]), len(set(data["finished"])))
        self.assertGreater(data["one_piece_ep"], watch.ONE_PIECE_START_EP)
        self.assertNotIn(data["current"]["title"], data["finished"])

    def test_no_binge_on_the_night_before_a_7am_class(self):
        tight = [d for d in self.days
                 if (lambda p: p and (p["bed"] - p["start"]) < timedelta(minutes=30))(self.tv.night_plan(d))]
        for day in tight:
            self.assertEqual(self.tv.materialize(self.tv.night_plan(day)["start"] + timedelta(minutes=1)), 0)

    def test_patrick_mentions_become_her_curiosity(self):
        self.assertTrue(self.tv.add_patrick_mention("Frieren", "anime"))
        self.assertFalse(self.tv.add_patrick_mention("Frieren", "anime"), "não anota duas vezes")
        self.assertFalse(self.tv.add_patrick_mention("Elite", "série"), "ela já viu")
        self.assertFalse(self.tv.add_patrick_mention("Elden Ring", "jogo"), "jogo não entra na fila de ver")
        self.assertIn("O Patrick já falou de Frieren", "\n".join(self.tv.prompt_lines()))
        with patch.object(watch, "MENTION_PRIORITY", 1.0):
            nxt = self.tv._pick_next([], self.days[0], self.tv.state()["patrick_mentions"])
        self.assertEqual(nxt["title"], "Frieren")
        self.assertIn("Patrick", nxt["why"])

    def test_planner_only_keeps_titles_he_really_wrote(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from planner import InternalPlanner

        def planner_saying(title):
            llm = MagicMock()
            llm.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(
                    {"intent": "casual_chat", "tone": "carinhosa",
                     "media_mentioned": {"title": title, "kind": "anime"}})))])
            return InternalPlanner(db=self.db, llm_client=llm)

        msg = "amor terminei de ver frieren ontem, que anime lindo"
        self.assertEqual(planner_saying("Frieren").plan_message(msg)["media_mentioned"]["title"], "Frieren")
        self.assertIsNone(planner_saying("Frieren: Beyond Journey's End").plan_message(msg)["media_mentioned"])
        self.assertIsNone(planner_saying("Naruto").plan_message(msg)["media_mentioned"])

    def test_prompt_lists_only_real_titles(self):
        text = "\n".join(self.tv.prompt_lines())
        self.assertIn("não cite título fora desta lista", text)
        self.assertIn("One Piece", text)
        self.assertIn("Elite", text)
        self.assertIn(self.tv.state()["current"]["title"], text)


if __name__ == "__main__":
    unittest.main()
