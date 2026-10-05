"""Lovense, passo 3 no bot (05/10): os comandos dele viram o que ela sente, em turno sem mensagem real.

A rajada de comandos (arrastando a barra) vira um turno só; o turno entra pelo mesmo buffer das mensagens dele,
sem roubar a citação da mensagem real; a linha do app não ensina o estilo dele.
"""
import asyncio
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

import bot
import lovense


class LovenseTurnoTest(unittest.IsolatedAsyncioTestCase):
    async def test_rajada_vira_um_turno_so_com_os_eventos_juntos(self):
        app = SimpleNamespace(bot=SimpleNamespace())
        sentir = mock.Mock(return_value={"texto": "[Brinquedo, pelo app do Patrick: Ele ligou o Lush]",
                                         "motivo": "mudou"})
        with mock.patch.object(lovense, "JUNTAR", timedelta(seconds=0.05)), \
                mock.patch.object(lovense.Lovense, "sentir", sentir), \
                mock.patch.object(bot, "_lovense_atividade", return_value="CLASS"), \
                mock.patch.object(bot, "_turno_do_app") as turno:
            now = datetime.now()
            for eventos in ([], [], ["respeitou"], []):
                await bot._webapp_lovense(app, eventos, now)
                await asyncio.sleep(0.01)
            for _ in range(100):                     # máquina carregada: espera o turno até 2 s
                await asyncio.sleep(0.02)
                if turno.called:
                    break
        sentir.assert_called_once()
        self.assertEqual(sentir.call_args.args[1], ["respeitou"])
        self.assertEqual(sentir.call_args.args[2], "CLASS")      # passo 4: onde ela está decide como ela recebe
        turno.assert_called_once_with(app, "[Brinquedo, pelo app do Patrick: Ele ligou o Lush]")

    async def test_sem_diferenca_nao_ha_turno(self):
        app = SimpleNamespace(bot=SimpleNamespace())
        with mock.patch.object(lovense, "JUNTAR", timedelta(seconds=0.01)), \
                mock.patch.object(lovense.Lovense, "sentir", mock.Mock(return_value=None)), \
                mock.patch.object(bot, "_lovense_atividade", return_value=None), \
                mock.patch.object(bot, "_turno_do_app") as turno:
            await bot._webapp_lovense(app, [], datetime.now())
            await asyncio.sleep(0.1)
        turno.assert_not_called()

    async def test_turno_do_app_vai_junto_com_a_mensagem_dele(self):
        chat = bot.settings.TARGET_CHAT_ID
        real = SimpleNamespace(message=SimpleNamespace(message_id=321))
        bot.debouncer.buffers[chat] = ["tá sentindo?"]
        bot.debouncer.latest_updates[chat] = real
        try:
            bot._turno_do_app(SimpleNamespace(bot=SimpleNamespace()), "[Brinquedo, pelo app do Patrick: Ele ligou o Lush]")
            self.assertEqual(bot.debouncer.buffers[chat],
                             ["tá sentindo?", "[Brinquedo, pelo app do Patrick: Ele ligou o Lush]"])
            self.assertIs(bot.debouncer.latest_updates[chat], real, "a resposta continua citando a mensagem dele")
        finally:
            task = bot.debouncer._waiting.pop(chat, None)
            if task:
                task.cancel()
            bot.debouncer.buffers.pop(chat, None)
            bot.debouncer.latest_updates.pop(chat, None)

    def test_linha_do_app_nao_e_fala_dele(self):
        self.assertTrue(bot._TURNO_DO_APP_RE.fullmatch("[Brinquedo, pelo app do Patrick: Ele ligou o Lush]"))
        self.assertTrue(bot._TURNO_DO_APP_RE.fullmatch("[Pix de R$ 50 do Patrick de presente, sem você pedir]"))
        self.assertFalse(bot._TURNO_DO_APP_RE.fullmatch("[Respondeu ao seu story do Instagram — praia] linda"))
        self.assertEqual(bot._falas_dele("[Brinquedo, pelo app do Patrick: Ele ligou o Lush]\ntá sentindo?"),
                         "tá sentindo?")


if __name__ == "__main__":
    unittest.main()
