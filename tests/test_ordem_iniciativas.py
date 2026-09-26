"""Mensagens fora de ordem (Patrick, 26/09 16:41): a entrega do sanduíche e uma saudade saíram no
mesmo segundo e os balões se intercalaram no chat."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from config import settings

_CEDE = asyncio.sleep                     # o de verdade (o teste troca o do bot)


class OrdemTest(unittest.TestCase):
    def test_duas_mensagens_ao_mesmo_tempo_nao_se_intercalam(self):
        enviados = []

        async def send_message(chat_id, text, reply_to_message_id=None):
            enviados.append(text)
            await _CEDE(0)                               # cede a vez, como a rede faria
            return SimpleNamespace(message_id=len(enviados))

        fake = MagicMock(send_message=send_message, send_chat_action=AsyncMock())
        a = "Amor, o sanduíche chegou\nFicou na portaria\nVc me mima demais"
        b = "Meu príncipe evaporou?\nLembrei de você agora\nVolta logo"

        async def os_dois():
            await asyncio.gather(bot.send_human_messages(4321, fake, a), bot.send_human_messages(4321, fake, b))

        with patch("bot.asyncio.sleep", new=AsyncMock()):
            asyncio.run(os_dois())
        primeiro = [t for t in enviados if t in a]
        self.assertEqual(enviados[:len(primeiro)], primeiro, enviados)   # a primeira sai inteira antes

    def test_iniciativa_opcional_desiste_se_outra_acabou_de_sair(self):
        fake_bot = MagicMock(send_message=AsyncMock(return_value=SimpleNamespace(message_id=5)),
                             send_chat_action=AsyncMock())
        service = MagicMock()
        service.should_trigger.return_value = (True, "saudade")
        with patch.object(settings, "TARGET_CHAT_ID", 123), patch("bot.proactivity_service", service), \
                patch("bot._minutos_desde_iniciativa", return_value=0.3), \
                patch("calendar_world.CalendarWorld.current", return_value=None), \
                patch("bot._proactive_text_raw", return_value="oi") as gera:
            asyncio.run(bot.autonomous_routine_v36(SimpleNamespace(bot=fake_bot)))
        gera.assert_not_called()
        fake_bot.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
