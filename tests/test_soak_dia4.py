"""Soak, dia 4 (sexta 02/10) — olhado à tarde, antes do Quartinho (pedido do Patrick).

1. 13:53 "distração g-relacionada" e 14:22 "capricha no desfile, hein GATE_CHANNEL" — rótulo de prompt na fala.
2. 14:23 o /ruim 055 sem confirmação: o "_" de GATE_CHANNEL quebrou o Markdown do Telegram.
3. 13:48 "aqui tá sequinho", 15:03 "dia quente" — chuvisco desde as 10h e 18 °C; o mundo só sabia de chuva forte,
   o ponto do tempo era o Corcovado (558 m) e três módulos liam um campo "rain" que ninguém gravava.
4. 15:01 a foto dele sem leitura: a visão foi cortada em 300 e em 500 tokens.
"""
import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from db import DatabaseManager


class CodigoNaFalaTest(unittest.TestCase):
    def test_rotulo_em_caixa_alta_refaz(self):
        import bot
        self.assertEqual(bot._needs_retry_for_junk("Kkkkk então capricha no desfile, hein GATE_CHANNEL"),
                         (True, "debug_artifact"))
        for ok in ("Kkkkk TPM é fogo", "Mandei o PIX agora, amor", "Vou na UFRJ amanhã", "SOCORRO kkkk",
                   "fica de boa_ amor"):
            self.assertEqual(bot._needs_retry_for_junk(ok), (False, ""), ok)


class ConfirmacaoDoRuimTest(unittest.TestCase):
    def test_markdown_quebrado_manda_sem_formatacao(self):
        import bot
        from telegram.error import BadRequest
        enviado = SimpleNamespace(message_id=7)
        send = AsyncMock(side_effect=[BadRequest("Can't parse entities: can't find end of the entity"), enviado])
        ctx = SimpleNamespace(bot=SimpleNamespace(send_message=send))
        with patch("bot.delete_after_delay", new=AsyncMock()):
            async def roda():
                await bot._wizard_send(ctx, 1, "Anotado: «hein GATE_CHANNEL»")
                await asyncio.sleep(0)
            asyncio.run(roda())
        self.assertEqual(send.await_count, 2)
        self.assertNotIn("parse_mode", send.await_args_list[1].kwargs)


class TempoDeVerdadeTest(unittest.TestCase):
    def test_codigo_vira_condicao(self):
        from real_context_provider import _condicao
        self.assertEqual(_condicao(51, 0.1), "drizzle")       # 02/10 13:00
        self.assertEqual(_condicao(55, 1.1), "drizzle")
        self.assertEqual(_condicao(63, 2.0), "rain")
        self.assertEqual(_condicao(53, 3.4), "rain")
        self.assertEqual(_condicao(95, 0), "storm")
        self.assertEqual(_condicao(3, 0), "cloudy")
        self.assertEqual(_condicao(0, 0), "clear")
        self.assertEqual(_condicao(None, 0.2), "rain")

    def test_provedor_grava_a_condicao_e_e_botafogo(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        from real_context_provider import RealContextProvider
        provider = RealContextProvider(DatabaseManager(Path(temp.name) / "c.db"))
        now = datetime(2026, 10, 2, 13, 0)
        with patch("real_context_provider._read_json", return_value={"current": {
                "time": "2026-10-02T13:00", "rain": 0.1, "showers": 0, "temperature_2m": 21.1,
                "weather_code": 51}}) as ler:
            self.assertTrue(provider.refresh_weather(now))
        self.assertIn("longitude=-43.1868", ler.call_args[0][0])
        self.assertEqual(provider.cache.get("weather:rio", now=now)["payload"],
                         {"heavy_rain": False, "temperature_c": 21.1, "condition": "drizzle"})

    def test_prompt_diz_o_tempo(self):
        from world_context import tempo_agora
        self.assertIn("21 °C, chuvisco", tempo_agora({"heavy_rain": False, "temperature_c": 21.1,
                                                      "condition": "drizzle"}))
        self.assertIn("18 °C.", tempo_agora({"heavy_rain": False, "temperature_c": 17.8}))
        self.assertEqual(tempo_agora({}), "")

    def test_chuva_dos_modulos_le_a_condicao(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "w.db")
        from agenda_viva import Disposicao
        from tempo_livre import TempoLivre
        from vontade import Vontade
        for cond, esperado in (("drizzle", False), ("rain", True), ("storm", True), ("cloudy", False)):
            w = json.dumps({"heavy_rain": False, "temperature_c": 21, "condition": cond})
            with patch.object(db, "get_connection") as gc:
                gc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {
                    "weather_context_json": w}
                for mod in (Vontade(db), TempoLivre(db)):
                    self.assertEqual(mod._chuva(), esperado, (type(mod).__name__, cond))
                self.assertEqual(Disposicao(db)._chuva(), esperado, ("Disposicao", cond))

    def test_foto_em_casa_so_chove_quando_chove(self):
        import inspect
        import photo_director
        trecho = inspect.getsource(photo_director)
        self.assertNotIn('or "rain" in json.dumps(weather)', trecho)
        self.assertIn('weather.get("condition") in ("drizzle", "rain", "storm")', trecho)


class VisaoComEspacoTest(unittest.TestCase):
    def test_mais_tokens_e_listas_curtas(self):
        import inspect
        import vision_service
        self.assertIn("max_tokens=800 if tentativa == 0 else 1500", inspect.getsource(vision_service))
        self.assertIn("no máximo 5 itens por lista", vision_service.VISION_PROMPT)


if __name__ == "__main__":
    unittest.main()
