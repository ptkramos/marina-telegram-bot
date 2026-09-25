"""C.1b — diretor de cena: nível, sessão com gancho, momentos, expressão, rua."""
import random
import tempfile
import unittest
import unittest.mock
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
            self.assertIn("squirting hands-free" if come.special else "right after she came", come.prompt)

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
        self.assertTrue(pd.may_self_initiate(self.db, NOW, IntimacyTurn()), "dia a dia: liberado com limite")
        self.assertFalse(pd.may_self_initiate(self.db, NOW, IntimacyTurn(state="cut")))
        self.assertTrue(pd.may_self_initiate(self.db, NOW, hot))
        pd.mark_self_initiated(self.db, NOW)
        self.assertFalse(pd.may_self_initiate(self.db, NOW + timedelta(minutes=2), hot))
        self.assertTrue(pd.may_self_initiate(self.db, NOW + timedelta(minutes=pd.SELF_PHOTO_GAP_MIN + 1), hot))
        self.assertFalse(pd.may_self_initiate(self.db, NOW + timedelta(minutes=30), IntimacyTurn()), "1 por hora")

    def test_position_she_described_wins(self):
        """24/09: ela disse 'de quatro na cama' e o sorteio mandou de costas no espelho."""
        hot = IntimacyTurn(state="active", arousal=0.6)
        s = self.shot("mostra pro seu amor em que posição", turn=hot,
                      her_line="De quatro na cama, amor... com a bunda empinada pra você", her_initiative=True)
        self.assertEqual(s.pose_id, "cama_de_quatro")
        self.assertEqual(s.room, "quarto")
        self.assertNotIn("espelho_costas", pd.BY_ID)

    def test_after_she_comes_the_photo_is_the_aftermath(self):
        s = self.shot("", turn=IntimacyTurn(state="climax", arousal=0.95), her_initiative=True,
                      her_line="Tô gozando... tô gozando muito em você agora")
        self.assertEqual(s.pose_id, "pos_gozo")
        self.assertIn("right after she came", s.prompt)

    def test_food_photo_shows_what_she_promised(self):
        s = self.shot("", her_line="O açaí chegou! olha que coisa linda", her_initiative=True,
                      now=datetime(2026, 9, 24, 20, 20))
        self.assertEqual(s.pose_id, "mostrando_comida")
        self.assertIn("açaí", s.prompt)
        self.assertFalse(s.is_nsfw)

    def test_tripod_frees_both_hands(self):
        import civitai_images as ci
        pose = pd.BY_ID["cama_tripe_duas_maos"]
        self.assertEqual(pose.framing, "timer")
        fingers = dict(pose.beats)["fingers"]
        self.assertIn("inside her wet pussy", fingers)
        self.assertIn("squeezing her breast", fingers)
        loras, _ = ci.conditional_loras(fingers, is_nsfw=True)
        self.assertIn(ci.KREA2_SQUEEZE, loras, "o LoRA de apertar entra sozinho")
        self.assertNotIn("squeezing", dict(pd.BY_ID["cama_pernas_abertas"].beats)["fingers"], "selfie: uma mão")

    def test_penetration_loras_approved_by_patrick(self):
        """24/09: dedo = Fingering 1.0; dildo = texto + Grippy 1.0 (3 rodadas de teste)."""
        import civitai_images as ci
        beats = dict(pd.BY_ID["cama_tripe_duas_maos"].beats)
        fingers, _ = ci.conditional_loras(beats["fingers"], is_nsfw=True)
        self.assertEqual(fingers.get(ci.KREA2_FINGERING), 1.0)
        self.assertNotIn(ci.KREA2_GRIPPY, fingers)
        dildo, triggers = ci.conditional_loras(beats["dildo"], is_nsfw=True)
        self.assertEqual(dildo.get(ci.KREA2_GRIPPY), 1.0)
        self.assertNotIn(ci.KREA2_FINGERING, dildo)
        self.assertTrue(any("GrippyPussy" in t for t in triggers))
        touch, _ = ci.conditional_loras(beats["touch"], is_nsfw=True)
        self.assertNotIn(ci.KREA2_FINGERING, touch, "se tocando por fora não liga o Fingering")
        sfw, _ = ci.conditional_loras("a dildo on the shelf", is_nsfw=False)
        self.assertEqual(sfw, {}, "nunca em foto normal")

    def test_creamy_grows_with_arousal_while_fingering(self):
        """24/09: sem Creamy no começo; se dedilhando sobe de 0.3 a 0.7; no gozo, 0.7."""
        self.assertEqual(pd.creamy_weight("fingers", 0.5), 0.0)
        self.assertEqual(pd.creamy_weight("fingers", 0.7), 0.3)
        self.assertEqual(pd.creamy_weight("fingers", 1.0), 0.7)
        self.assertEqual(pd.creamy_weight("climax", 0.35), 0.7)
        self.assertEqual(pd.creamy_weight("dildo", 0.95), 0.0)
        import civitai_images as ci
        s = self.shot("se dedilha de costas pra mim", turn=IntimacyTurn(state="active", arousal=0.85))
        self.assertEqual(s.pose_id, "cama_costas_dedando")
        if s.beat in pd.CREAMY_BEATS:
            w = s.lora_weights[ci.KREA2_CREAMY]
            self.assertTrue(0.3 < w < 0.7)
            body = ci.build_workflow_krea2(s.prompt, is_nsfw=True, seed=1, lora_weights=s.lora_weights)
            self.assertEqual(body["steps"][0]["input"]["loras"][ci.KREA2_CREAMY], w, "o peso do diretor vence")

    def test_sitting_on_the_clear_dildo(self):
        """24/09 (teste X): 'senta nele' → agachada no dildo transparente, só com o Grippy."""
        import civitai_images as ci
        hot = IntimacyTurn(state="active", arousal=0.9)
        s = self.shot("senta nesse dildo pra mim", turn=hot)
        self.assertEqual(s.pose_id, "sentando_dildo")
        self.assertEqual(s.beat, "dildo")
        self.assertIn("clear transparent", s.prompt)
        loras, _ = ci.conditional_loras(s.prompt, is_nsfw=True)
        self.assertEqual(loras.get(ci.KREA2_GRIPPY), 1.0)
        self.assertNotIn(ci.KREA2_FINGERING, loras)
        come = self.shot("goza sentando", turn=IntimacyTurn(state="climax", arousal=0.95),
                         now=NOW + timedelta(minutes=3))
        self.assertEqual((come.pose_id, come.beat), ("sentando_dildo", "climax"))

    def test_riding_reclined_on_the_clear_dildo(self):
        s = self.shot("cavalga nele pra mim", turn=IntimacyTurn(state="active", arousal=0.9))
        self.assertEqual((s.pose_id, s.beat), ("cavalgando_reclinada", "dildo"))
        self.assertIn("clear transparent", s.prompt)
        self.assertNotIn("light blue", s.prompt, "só dois dildos: rosa e transparente")

    def test_special_climax_squirts_without_creamy(self):
        """25/09 (teste MM): às vezes o gozo se dedilhando é o especial, com esguicho e sem Creamy."""
        import civitai_images as ci
        hot = IntimacyTurn(state="active", arousal=0.9)
        self.shot("se dedilha pra mim, abre as pernas", turn=hot)
        with unittest.mock.patch.object(pd, "SPECIAL_CLIMAX_CHANCE", 1.0):
            come = self.shot("goza pra mim", turn=IntimacyTurn(state="climax", arousal=0.95),
                             now=NOW + timedelta(minutes=3))
        self.assertTrue(come.special)
        self.assertIn("squirting hands-free", come.prompt)
        self.assertIn("both hands squeezing her breasts", come.prompt)
        self.assertTrue(any(e.split(":")[0].split(",")[0] in come.prompt for e in pd.SPECIAL_EXPRESSIONS))
        body = ci.build_workflow_krea2(come.prompt, is_nsfw=True, seed=1, lora_weights=come.lora_weights)
        loras = body["steps"][0]["input"]["loras"]
        self.assertEqual(loras.get(ci.KREA2_SQUIRT), 1.5)
        self.assertNotIn(ci.KREA2_FINGERING, loras)
        self.assertEqual(loras.get(ci.KREA2_SQUEEZE), 0.6, "as duas mãos nos seios")
        self.assertNotIn(ci.KREA2_CREAMY, loras, "o Creamy embranquece o jato")
        self.assertNotIn("creamythings", body["steps"][0]["input"]["prompt"])
        after = self.shot("", turn=IntimacyTurn(state="afterglow", arousal=0.35), force_pose="pos_gozo",
                          expression_override=pd.AFTER_SPECIAL_EXPRESSION, now=NOW + timedelta(minutes=4))
        self.assertEqual(after.pose_id, "pos_gozo")
        self.assertIn("half-closed sleepy eyes", after.prompt)

    def test_sucking_the_dildo_uses_suck_not_grippy(self):
        import civitai_images as ci
        s = self.shot("faz um boquete no teu dildo pra mim", turn=IntimacyTurn(state="active", arousal=0.8))
        self.assertEqual(s.pose_id, "boquete_dildo")
        loras, triggers = ci.conditional_loras(s.prompt, is_nsfw=True)
        self.assertEqual(loras.get(ci.KREA2_SUCK), 0.5)
        self.assertEqual(loras.get(ci.KREA2_POVBJ), 0.8, "canon do Patrick: POV 0.8 + Suck 0.5 (ZB/ZE)")
        self.assertNotIn(ci.KREA2_GRIPPY, loras)
        self.assertFalse(any("GrippyPussy" in t for t in triggers))
        side = self.shot("chupa de lado o dildo preso na cama", turn=IntimacyTurn(state="active", arousal=0.8),
                         now=NOW + timedelta(minutes=2))
        self.assertEqual(side.pose_id, "boquete_de_lado")
        loras, _ = ci.conditional_loras(side.prompt, is_nsfw=True)
        self.assertEqual((loras.get(ci.KREA2_POVBJ), loras.get(ci.KREA2_SUCK)), (0.8, 0.5))

    def test_pov_watermark_strip_is_cropped(self):
        import io
        import civitai_images as ci
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (100, 200), "white").save(buf, format="JPEG")
        out = Image.open(io.BytesIO(ci._crop_bottom(buf.getvalue(), ci.WATERMARK_CROP)))
        self.assertEqual(out.size, (100, 188))

    def test_asking_for_the_dildo(self):
        hot = IntimacyTurn(state="active", arousal=0.9)
        s = self.shot("pega teu dildo e usa pra mim", turn=hot)
        self.assertEqual(s.level, 4)
        if pd.BY_ID[s.pose_id].beats:
            self.assertEqual(s.beat, "dildo")
            self.assertIn("dildo", s.prompt)

    def test_panties_go_as_adult_workflow(self):
        s = self.shot("manda uma foto", turn=IntimacyTurn(state="warming", arousal=0.35))
        if s.outfit and "panties" in s.outfit:
            self.assertTrue(s.is_nsfw)


if __name__ == "__main__":
    unittest.main()
