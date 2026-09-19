"""
Testes unitários para o comando /status e interatividade do botão '🗑️ Apagar' (v3.7.0).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
from bot import status_command, status_callback_handler


class TestStatusCommand(unittest.IsolatedAsyncioTestCase):
    async def test_status_command_sends_panel_with_delete_button(self):
        update = MagicMock()
        update.effective_chat.id = settings.TARGET_CHAT_ID
        update.effective_user.id = settings.TARGET_CHAT_ID
        update.message.message_id = 100

        context = MagicMock()
        context.bot.delete_message = AsyncMock()
        context.bot.send_chat_action = AsyncMock()
        context.bot.send_message = AsyncMock()

        sent_mock = MagicMock()
        sent_mock.message_id = 101
        context.bot.send_message.return_value = sent_mock

        with patch("bot.delete_after_delay", new_callable=AsyncMock) as mock_delete:
            await status_command(update, context)

        # Valida que o comando original do Patrick foi deletado
        context.bot.delete_message.assert_awaited_with(
            chat_id=settings.TARGET_CHAT_ID,
            message_id=100
        )

        # Valida que o painel de status foi enviado
        context.bot.send_message.assert_awaited_once()
        _, kwargs = context.bot.send_message.call_args

        self.assertEqual(kwargs["chat_id"], settings.TARGET_CHAT_ID)
        self.assertEqual(kwargs["parse_mode"], "Markdown")
        text = kwargs["text"]

        # Valida seções do layout v3.7
        self.assertIn("Status de Marina Salles", text)
        self.assertIn("Vida & Rotina", text)
        self.assertIn("Cérebro & Memória", text)
        self.assertIn("Mídia & Conexão", text)
        self.assertIn("Disponibilidade", text)
        self.assertIn("Ciclo biológico", text)

        # Valida o botão inline de apagar
        reply_markup = kwargs.get("reply_markup")
        self.assertIsNotNone(reply_markup)
        self.assertEqual(len(reply_markup.inline_keyboard), 1)
        btn = reply_markup.inline_keyboard[0][0]
        self.assertEqual(btn.text, "🗑️ Apagar")
        self.assertEqual(btn.callback_data, "status_delete")

    async def test_status_callback_handler_deletes_message(self):
        update = MagicMock()
        update.effective_chat.id = settings.TARGET_CHAT_ID
        update.effective_user.id = settings.TARGET_CHAT_ID

        query = MagicMock()
        query.data = "status_delete"
        query.answer = AsyncMock()
        query.message.delete = AsyncMock()
        update.callback_query = query

        context = MagicMock()

        await status_callback_handler(update, context)

        query.answer.assert_awaited_once_with("Status fechado! 🧹")
        query.message.delete.assert_awaited_once()

    async def test_status_callback_handler_unauthorized(self):
        update = MagicMock()
        update.effective_chat.id = 99999999
        update.effective_user.id = 99999999

        query = MagicMock()
        query.data = "status_delete"
        query.answer = AsyncMock()
        query.message.delete = AsyncMock()
        update.callback_query = query

        context = MagicMock()

        await status_callback_handler(update, context)

        query.answer.assert_awaited_once_with("Não autorizado.", show_alert=True)
        query.message.delete.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
