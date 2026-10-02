"""28/09 — foto de grupo de ponta a ponta: agenda → câmera → diretor → troca de rosto da amiga."""
import asyncio
import io
import random
import tempfile
import unittest
import unittest.mock
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import photo_director as pd
from db import DatabaseManager
from intimacy import IntimacyTurn

NOW = datetime(2026, 9, 27, 16, 0)   # domingo: sem aula no caminho


def street(people=()):
    return SimpleNamespace(place_key="shopping_gavea", presence_assertable=True, activity="", sublocation="",
                           weather=None, present_people=tuple(people))


class FotoGrupoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "g.db")

    def tearDown(self):
        self.temp.cleanup()

    def shot(self, request, camera, seed=7):
        return pd.direct(self.db, NOW, request=request, camera_ctx=camera, turn=IntimacyTurn(),
                         rng=random.Random(seed))

    def test_agenda_leva_a_amiga_ate_a_camera(self):
        from calendar_world import CalendarWorld
        from camera_world import CameraWorldBuilder
        CalendarWorld(self.db).create_commitment(
            source_key="outing:2026-09-27:c3", event_type="social",
            description="Cinema e shopping com a Bia no Shopping da Gávea",
            start_at=datetime(2026, 9, 27, 15, 0), end_at=datetime(2026, 9, 27, 19, 0),
            location_key="shopping_gavea", metadata={"friends": ["bia_andrade"], "origin": "convite"})
        self.assertEqual(CalendarWorld(self.db).current(NOW)["people"], ["bia_andrade"])
        self.assertIn("bia_andrade", CameraWorldBuilder(self.db).build(NOW).present_people)

    def test_pedido_com_a_amiga_vira_selfie_das_duas(self):
        s = self.shot("manda uma foto sua com a Bia", street(["bia_andrade"]))
        self.assertIn(s.pose_id, pd.GROUP_POSES)
        self.assertEqual(s.friend, "bia_andrade")
        self.assertIn("On the right side of the photo", s.prompt)
        self.assertIn("light olive skin", s.prompt, "a Bia descrita pelo cânone")
        self.assertNotIn("{friend}", s.prompt)
        self.assertIn("a Bia", s.facts)

    def test_a_citada_no_pedido_entra(self):
        s = self.shot("tira uma com a Carol", street(["bia_andrade", "carol_menezes"]))
        self.assertEqual(s.friend, "carol_menezes")
        self.assertIn("honey-blonde", s.prompt)

    def test_theo_e_o_amigo(self):
        s = self.shot("foto de vocês dois", street(["theo_martins"]))
        self.assertEqual(s.friend, "theo_martins")
        self.assertIn("young Brazilian man", s.prompt)

    def test_sozinha_ou_sem_rg_nunca_foto_de_grupo(self):
        for people in ((), ("gabi_freitas",)):
            for seed in range(40):
                s = self.shot("manda uma foto", street(people), seed=seed)
                self.assertNotIn(s.pose_id, pd.GROUP_POSES, people)
                self.assertEqual(s.friend, "")
                self.assertNotIn("{friend}", s.prompt)

    def test_em_casa_sem_foto_de_grupo(self):
        home = SimpleNamespace(place_key="marina_apartment", presence_assertable=True, activity="", sublocation="",
                               weather=None, present_people=("bia_andrade",))
        s = self.shot("manda uma foto com a Bia", home)
        self.assertNotIn(s.pose_id, pd.GROUP_POSES)

    def test_roupa_da_amiga_e_outra(self):
        for seed in range(20):
            s = self.shot("manda uma foto sua com a Bia", street(["bia_andrade"]), seed=seed)
            self.assertTrue(s.session["friend_outfit"])
            self.assertNotEqual(s.session["friend_outfit"], s.outfit)

    def test_cabecas_um_pouco_separadas(self):
        """Patrick: sem colar os rostos — a costura da troca precisa de um vão entre as duas."""
        for pid in pd.GROUP_POSES:
            self.assertRegex(pd.BY_ID[pid].action, r"space between their heads|heads a little apart", pid)
        s = self.shot("manda uma foto sua com a Bia", street(["bia_andrade"]))
        self.assertNotIn("pressed close", s.prompt)

    def test_cara_vem_do_sentimento_nao_da_pose(self):
        """28/09 a inclinada pra câmera tinha a mordida fixa. 02/10 (Patrick): "nenhuma pose tem cara fixa, assim
        como nenhuma cara fixa tem pose — decidido única e exclusivamente pelo feeling"."""
        home = SimpleNamespace(place_key="marina_apartment", presence_assertable=True, activity="",
                               sublocation="quarto", weather=None, present_people=())
        turn = IntimacyTurn(state="active", arousal=0.6)
        s = pd.direct(self.db, datetime(2026, 9, 27, 22, 30), request="manda uma foto pelada", camera_ctx=home,
                      turn=turn, rng=random.Random(11), force_pose="inclinada_pra_camera")
        self.assertIn(pd.expression(None, turn), s.prompt)
        self.assertIn("eyes looking away from the camera", s.prompt, "pra onde ela olha é da pose")

    def test_geracao_troca_o_rosto_da_amiga(self):
        import sd_client
        s = self.shot("manda uma foto sua com a Bia", street(["bia_andrade"]))
        gen = unittest.mock.AsyncMock(return_value=io.BytesIO(b"original"))
        swap = unittest.mock.AsyncMock(return_value=b"trocada")
        with unittest.mock.patch("civitai_images.generate", gen), \
                unittest.mock.patch("civitai_images.swap_friend_face", swap):
            out = asyncio.run(sd_client.ImageGeneratorClient().generate_directed(s))
        self.assertEqual(out.image.getvalue(), b"trocada")
        self.assertEqual(swap.call_args.args, (b"original", "bia_andrade"))
        self.assertEqual(swap.call_args.kwargs["side"], "right")

    def test_troca_falhou_vai_a_original_e_sozinha_nem_tenta(self):
        import sd_client
        s = self.shot("manda uma foto sua com a Bia", street(["bia_andrade"]))
        gen = unittest.mock.AsyncMock(return_value=io.BytesIO(b"original"))
        swap = unittest.mock.AsyncMock(return_value=None)
        with unittest.mock.patch("civitai_images.generate", gen), \
                unittest.mock.patch("civitai_images.swap_friend_face", swap):
            out = asyncio.run(sd_client.ImageGeneratorClient().generate_directed(s))
            self.assertEqual(out.image.getvalue(), b"original")
            alone = self.shot("manda uma foto", street(()))
            gen.return_value = io.BytesIO(b"sozinha")
            swap.reset_mock()
            asyncio.run(sd_client.ImageGeneratorClient().generate_directed(alone))
        swap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
