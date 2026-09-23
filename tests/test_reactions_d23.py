"""Reações (feedback do Patrick, 23/09): risada que nunca saía, reação em tudo, e
"às vezes só uma reação ou uma risada bastam"."""
import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import bot


class ReactionTest(unittest.TestCase):
    def test_laugh_uses_the_emoji_telegram_accepts(self):
        self.assertEqual(bot._reaction_aliases["😂"], "🤣")
        self.assertIn("🤣", bot._safe_reactions)
        self.assertNotIn("😂", bot._safe_reactions)
        fake = MagicMock(set_message_reaction=AsyncMock(), get_chat=AsyncMock(return_value=MagicMock(available_reactions=[])))
        self.assertTrue(asyncio.run(bot.set_safe_message_reaction(fake, 1, 2, "😂")))
        self.assertEqual(fake.set_message_reaction.call_args.kwargs["reaction"][0].emoji, "🤣")

    def test_she_does_not_react_to_everything(self):
        bot._LAST_REACTION_AT.pop(7, None)
        self.assertLess(bot._reaction_chance(7, "vou almoçar agora", True), 0.5)
        self.assertGreaterEqual(bot._reaction_chance(7, "KKKKKKKK não acredito", True), 0.7)
        bot._LAST_REACTION_AT[7] = datetime.now() - timedelta(seconds=30)
        self.assertLess(bot._reaction_chance(7, "KKKKKKKK de novo", True), 0.3, "acabou de reagir")
        bot._LAST_REACTION_AT.pop(7, None)

    def test_reaction_only_turn_only_when_nothing_needs_an_answer(self):
        plan = {"resposta": "so_reacao", "intent": "casual_chat"}
        with patch.object(bot.random, "random", return_value=0.0):
            self.assertTrue(bot._is_reaction_only_turn(plan, "isso aí ksksksk"))
            self.assertFalse(bot._is_reaction_only_turn(plan, "isso aí, e você?"), "pergunta pede resposta")
            self.assertFalse(bot._is_reaction_only_turn({"resposta": "so_reacao", "intent": "support_needed"}, "aham"))
            self.assertFalse(bot._is_reaction_only_turn({"resposta": "texto"}, "aham"))
            self.assertFalse(bot._is_reaction_only_turn(plan, "manda uma foto"))


if __name__ == "__main__":
    unittest.main()
