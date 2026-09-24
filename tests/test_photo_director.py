"""C.1b — diretor de cena: nível, sessão com gancho, momentos, expressão, rua."""
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import photo_director as pd
from db import DatabaseManager
from intimacy import IntimacyTurn

NOW = datetime(2026, 9, 24, 22, 0)
HOME_CTX = SimpleNamespace(place_key="marina_apartment", presence_assertable=True, activity="", sublocation="",
                           weather=None, present_people=())


def ctx(**kw):
    base = dict(vars(HOME_CTX))
    base.update(kw)
    return SimpleNamespace(**base)


class DirectorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "d.db")
        self.rng = random.Random(7)

    def tearDown(self):
        self.temp.cleanup()

    def shot(self, request="", turn=None, now=NOW, camera=HOME_CTX, send=True, **kw):
        s = pd.direct(self.db, now, request=request, camera_ctx=camera, turn=turn or IntimacyTurn(),
                      rng=self.rng, **kw)
        if send:
            pd.confirm_sent(self.db, s)
        return s

    def test_asked_level(self):
        self.assertEqual(pd.asked_level("manda uma foto sua vestida"), 0)
        self.assertEqual(pd.asked_level("quero ver de calcinha"), 2)
        self.assertEqual(pd.asked_level("manda nude"), 3)
        self.assertEqual(pd.asked_level("abre a buceta pra mim"), 4)
        self.assertIsNone(pd.asked_level("manda uma foto"))

    def test_calm_moment_is_a_normal_photo_at_home(self):
        s = self.shot("manda uma foto")
        self.assertEqual(s.level, 0)
        self.assertFalse(s.is_nsfw)
        self.assertIn(s.room, ("quarto",), "22h: quarto")
        self.assertIn("She is wearing", s.prompt)

    def test_one_step_above_the_mood_when_he_asks(self):
        s = self.shot("manda nude", turn=IntimacyTurn(state="off"))
        self.assertEqual(s.level, 2, "fora do clima: lingerie, não pelada")
        s = pd.direct(self.db, NOW, request="manda nude", camera_ctx=HOME_CTX,
                      turn=IntimacyTurn(state="active", arousal=0.5), rng=random.Random(99))
        self.assertIn(s.level, (3,))

    def test_session_hook_keeps_pose_and_advances_the_hand(self):
        hot = IntimacyTurn(state="active", arousal=0.9)
        first = self.shot("me mostra a buceta", turn=hot)
        self.assertEqual(first.level, 4)
        pose = first.pose_id
        tags = [t for t, _ in pd.BY_ID[pose].beats]
        second = self.shot("mais uma", turn=hot, now=NOW + timedelta(minutes=3))
        self.assertEqual(second.pose_id, pose, "mesma posição")
        self.assertEqual(second.seed, first.seed, "mesma cena")
        if tags:
            self.assertGreater(tags.index(second.beat), tags.index(first.beat))
            lick = self.shot("lambe os dedos", turn=hot, now=NOW + timedelta(minutes=5))
            self.assertEqual(lick.beat, "lick")
            come = self.shot("goza pra mim", turn=hot, now=NOW + timedelta(minutes=7))
            self.assertEqual(come.beat, "climax")
            self.assertIn("right after she came", come.prompt)

    def test_asking_to_turn_around_changes_the_pose(self):
        hot = IntimacyTurn(state="active", arousal=0.9)
        first = self.shot("abre a buceta", turn=hot)
        changed = None
        for i in range(10):
            s = pd.direct(self.db, NOW + timedelta(minutes=2), request="fica de quatro", camera_ctx=HOME_CTX,
                          turn=hot, rng=random.Random(i))
            changed = changed or s.seed != first.seed
        self.assertTrue(changed)

    def test_session_expires(self):
        first = self.shot("manda uma foto")
        later = self.shot("manda uma foto", now=NOW + timedelta(minutes=pd.SESSION_TTL_MIN + 5), send=False)
        self.assertNotEqual(later.seed, first.seed)

    def test_undressing_keeps_the_scene(self):
        warm = IntimacyTurn(state="active", arousal=0.5)
        first = self.shot("de calcinha", turn=warm)
        second = self.shot("tira tudo", turn=warm, now=NOW + timedelta(minutes=2))
        if pd.BY_ID[first.pose_id].levels[1] >= 3:
            self.assertEqual(second.seed, first.seed)
            self.assertIsNone(second.outfit)
            self.assertIn("completely naked", second.prompt)

    def test_out_of_home_stays_clothed(self):
        street = ctx(place_key="botafogo_praia_shopping", present_people=())
        s = self.shot("manda nude", turn=IntimacyTurn(state="active", arousal=0.9), camera=street)
        self.assertLessEqual(s.level, 1)
        self.assertEqual(s.declined, "fora de casa")
        self.assertEqual(s.room, "fora")
        self.assertNotEqual(pd.BY_ID[s.pose_id].framing, "friend", "sozinha: sem 'amiga tirando'")

    def test_expression_follows_mood_and_arousal(self):
        self.assertIn("lustful", pd.expression(None, IntimacyTurn(state="active", arousal=0.9)))
        self.assertIn("pleasure", pd.expression(None, IntimacyTurn(state="climax")))
        ep = SimpleNamespace(kind="saudade", family="tristeza", intensity=0.6)
        feel = SimpleNamespace(episodes=[ep], discomfort=0.0, energy=0.7, libido=0.3, valence=0.5)
        self.assertIn("wistful", pd.expression(feel, IntimacyTurn()))
        tired = SimpleNamespace(episodes=[], discomfort=0.0, energy=0.2, libido=0.3, valence=0.6)
        self.assertIn("sleepy", pd.expression(tired, IntimacyTurn()))

    def test_room_follows_what_she_is_doing(self):
        s = self.shot("manda uma foto", camera=ctx(activity="tomando banho"))
        self.assertEqual(s.room, "banheiro")

    def test_every_pose_names_the_hands_and_has_no_negation(self):
        for pose in pd.POSES:
            texts = [pose.action] + [t for _, t in pose.beats]
            for t in texts:
                self.assertNotRegex(t.lower(), r"\b(no|not|without)\b", pose.id)
            if pose.framing in ("selfie", "mirror"):
                self.assertRegex(pose.action, r"right arm stretched|free hand", pose.id)

    def test_self_initiative_is_rationed(self):
        hot = IntimacyTurn(state="active", arousal=0.8)
        self.assertFalse(pd.may_self_initiate(self.db, NOW, IntimacyTurn()))
        self.assertTrue(pd.may_self_initiate(self.db, NOW, hot))
        pd.mark_self_initiated(self.db, NOW)
        self.assertFalse(pd.may_self_initiate(self.db, NOW + timedelta(minutes=5), hot))
        self.assertTrue(pd.may_self_initiate(self.db, NOW + timedelta(minutes=pd.SELF_PHOTO_GAP_MIN + 1), hot))

    def test_panties_go_as_adult_workflow(self):
        s = self.shot("manda uma foto", turn=IntimacyTurn(state="warming", arousal=0.35))
        if s.outfit and "panties" in s.outfit:
            self.assertTrue(s.is_nsfw)


if __name__ == "__main__":
    unittest.main()
