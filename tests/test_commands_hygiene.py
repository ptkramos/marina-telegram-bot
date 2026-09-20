"""
Testes unitários para validar a política de 'Chat 100% Limpo' (deleção do comando gatilho recebido).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
from bot import (
    lembretes_command,
    cancelar_lembrete_command,
    memory_hygiene_command,
    refletir_command,
    audio_command,
)


class TestCommandsHygiene(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.update = MagicMock()
        self.update.effective_chat.id = settings.TARGET_CHAT_ID
        self.update.effective_user.id = settings.TARGET_CHAT_ID
        self.update.message.message_id = 555
        self.context = MagicMock()
        self.context.bot.delete_message = AsyncMock()
        self.context.bot.send_message = AsyncMock()
        self.context.args = []

    async def test_lembretes_command_deletes_trigger(self):
        with patch("bot.delete_after_delay", new_callable=AsyncMock):
            await lembretes_command(self.update, self.context)

        self.context.bot.delete_message.assert_awaited_with(
            chat_id=settings.TARGET_CHAT_ID,
            message_id=555
        )

    async def test_cancelar_lembrete_command_deletes_trigger(self):
        with patch("bot.delete_after_delay", new_callable=AsyncMock):
            await cancelar_lembrete_command(self.update, self.context)

        self.context.bot.delete_message.assert_awaited_with(
            chat_id=settings.TARGET_CHAT_ID,
            message_id=555
        )

    async def test_memory_hygiene_command_deletes_trigger(self):
        with patch("bot.delete_after_delay", new_callable=AsyncMock), \
             patch("bot.memory_hygiene_service.run_hygiene_cycle", return_value={}):
            await memory_hygiene_command(self.update, self.context)

        self.context.bot.delete_message.assert_awaited_with(
            chat_id=settings.TARGET_CHAT_ID,
            message_id=555
        )

    async def test_refletir_command_deletes_trigger(self):
        with patch("bot.delete_after_delay", new_callable=AsyncMock), \
             patch("bot.session_reflector.check_and_trigger_reflection", return_value=None):
            await refletir_command(self.update, self.context)

        self.context.bot.delete_message.assert_awaited_with(
            chat_id=settings.TARGET_CHAT_ID,
            message_id=555
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
