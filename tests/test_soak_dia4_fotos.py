"""Soak, dia 4 (02/10, 14:55 e 15:41): ele pediu foto duas vezes, as duas falharam e ela mandou o texto fixo "tentei
te mandar a fotinho agora mas a câmera do apê travou" — no açaí e no Rei do Mate —, que nem entrava no histórico.
A causa: o moderador do Civitai recusou a selfie normal pela expressão "a sultry half-lidded look and a slow teasing
smirk" (testado em 02/10: o mesmo pedido recusado de novo; sem a expressão, passou — 31 Buzz)."""
import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from db import DatabaseManager

PROMPT = ("marinaX, A close photo of a young Brazilian woman, her free hand raised to her lips, a sultry half-lidded "
          "look and a slow teasing smirk. She is wearing a red gingham summer dress.")


class SuavizarTest(unittest.TestCase):
    def test_troca_a_expressao_quente(self):
        import photo_director
        novo = photo_director.suavizar(PROMPT)
        self.assertNotIn("sultry", novo)
        self.assertIn("a soft playful smile", novo)
        self.assertIn("red gingham summer dress", novo)
        self.assertIsNone(photo_director.suavizar("marinaX, a bright excited smile"))

    def test_as_expressoes_quentes_sao_as_do_diretor(self):
        import photo_director
        from intimacy import HOT_AT
        for turn in (SimpleNamespace(state="active", arousal=0.55), SimpleNamespace(state="active", arousal=HOT_AT),
                     SimpleNamespace(state="warming", arousal=0.3)):
            self.assertIn(photo_director.expression(None, turn), photo_director.EXPRESSOES_QUENTES)


class RefazQuandoORecusamTest(unittest.TestCase):
    def _shot(self, nsfw=False):
        return SimpleNamespace(prompt=PROMPT, is_nsfw=nsfw, focus_angle="frontal", seed=1, lora_weights={},
                               pov=False, friend="", pose_id="unhas_selfie_rua", place_key="loja_rei_do_mate")

    def _gera(self, shot, respostas):
        import civitai_images
        import sd_client
        chamadas = []

        async def falso(prompt, **kw):
            chamadas.append(prompt)
            img, recusou = respostas.pop(0)
            civitai_images.ultima_recusa_sfw = recusou
            return img

        with patch("civitai_images.generate", side_effect=falso):
            res = asyncio.run(sd_client.ImageGeneratorClient().generate_directed(shot))
        return res, chamadas

    def test_recusada_pelo_moderador_vai_de_novo_com_sorriso(self):
        res, chamadas = self._gera(self._shot(), [(None, True), (io.BytesIO(b"jpg"), False)])
        self.assertEqual(len(chamadas), 2)
        self.assertIn("a soft playful smile", chamadas[1])
        self.assertIsNotNone(res.image)
        self.assertEqual(res.full_prompt, chamadas[1])

    def test_outra_falha_nao_refaz(self):
        res, chamadas = self._gera(self._shot(), [(None, False)])
        self.assertEqual(len(chamadas), 1)
        self.assertIsNone(res.image)

    def test_adulta_nao_refaz(self):
        _, chamadas = self._gera(self._shot(nsfw=True), [(None, True)])
        self.assertEqual(len(chamadas), 1)


class FotoNaoSaiuTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / "f.db")

    def _roda(self, fala_gerada):
        import bot
        enviado = AsyncMock()
        ctx = SimpleNamespace(bot=SimpleNamespace())
        camera = SimpleNamespace(activity="Tomando um café no Rei do Mate")
        with patch.object(bot, "memory_manager", SimpleNamespace(db=self.db)), \
                patch("bot.generate_dynamic_speech", return_value=fala_gerada) as gera, \
                patch("bot.send_human_messages", new=enviado):
            asyncio.run(bot._foto_nao_saiu(1, ctx, camera, "Tô até vendo vc sem ar nenhum"))
        return enviado.await_args[0][2], gera.call_args[0][0]

    def test_na_voz_dela_sabendo_onde_esta_e_no_historico(self):
        texto, instrucao = self._roda("Amor, a foto saiu toda borrada aqui no Rei do Mate kkk já já te mando outra")
        self.assertIn("Rei do Mate", instrucao)
        self.assertIn("Não culpe câmera", instrucao)
        self.assertNotIn("câmera do apê", texto)
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT content FROM conversas WHERE role='assistant' ORDER BY id DESC").fetchone()
        self.assertEqual(row["content"], texto)
        import promessa_foto
        self.assertEqual(promessa_foto.pending(self.db)["kind"], "selfie")

    def test_sem_fala_usa_a_reserva(self):
        import bot
        texto, _ = self._roda("")
        self.assertEqual(texto, bot.FOTO_NAO_SAIU_FALLBACK)


if __name__ == "__main__":
    unittest.main()
