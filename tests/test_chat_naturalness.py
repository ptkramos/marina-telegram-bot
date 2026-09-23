"""Naturalidade de chat — casos reais da conversa com o Patrick de 22–23/09."""
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from chat_naturalness import (debounce_delay, drop_repeated, mark_nudged, repeated_run, share_nudge,
                              strip_closing_periods, thin_vocative)
from db import DatabaseManager


class ClosingPeriodTest(unittest.TestCase):
    def test_closing_period_goes_separator_stays(self):
        self.assertEqual(strip_closing_periods("Tá bom, amor, vou comer direitinho sim."),
                         "Tá bom, amor, vou comer direitinho sim")
        self.assertEqual(strip_closing_periods("Tá bom. Vou jantar agora."), "Tá bom. Vou jantar agora")
        self.assertEqual(strip_closing_periods("Vou jantar agora. 😘"), "Vou jantar agora 😘")
        self.assertEqual(strip_closing_periods("Aeee!\nAgora respira e descansa."), "Aeee!\nAgora respira e descansa")

    def test_ellipsis_question_and_exclamation_are_kept(self):
        for text in ("Hmm...", "Aí você apela, amor…", "Doeu?", "Aeee!"):
            self.assertEqual(strip_closing_periods(text), text)


class SelfRepetitionTest(unittest.TestCase):
    PREV = ["Kkkkk ela te entregou vermelho e chamou de laranja, foi isso?",
            "Ainda bem, amor, já tava na hora dessa boca parar de sofrer kkk. "
            "Agora você consegue beijar sem esse aparelho te sabotando."]

    def test_the_real_13h07_repeat_is_caught_and_cut(self):
        reply = ("Hmmm, agora você consegue beijar sem esse aparelho te sabotando… então vou cobrar "
                 "esses vários beijos quando a gente se encontrar, hein 😏")
        self.assertIsNotNone(repeated_run(reply, self.PREV))
        self.assertEqual(drop_repeated(reply, self.PREV),
                         "Então vou cobrar esses vários beijos quando a gente se encontrar, hein 😏")

    def test_short_common_phrases_are_not_repetition(self):
        self.assertIsNone(repeated_run("Kkkkk tá bom, amor", self.PREV))
        self.assertIsNone(repeated_run("Vai ser boa mesmo, quero ver você manter essa confiança", self.PREV))

    def test_nothing_left_means_rewrite(self):
        self.assertIsNone(drop_repeated("Agora você consegue beijar sem esse aparelho te sabotando.", self.PREV))


class VocativeTest(unittest.TestCase):
    def test_amor_every_turn_gets_thinned(self):
        prev = ["Boa, amor, agora falta só essa última van.", "Kkkkk boa, amor. Agora é só a última etapa."]
        self.assertEqual(thin_vocative("Aeee, amor, finalmente em casa!", prev), "Aeee, finalmente em casa!")
        self.assertEqual(thin_vocative("Tá bom, amor. Vou jantar", prev), "Tá bom. Vou jantar")
        self.assertEqual(thin_vocative("Amor, você comeu?", prev), "Você comeu?")

    def test_amor_is_kept_when_it_was_not_in_every_turn(self):
        prev = ["Boa, agora falta só essa última van.", "Kkkkk boa, amor."]
        self.assertEqual(thin_vocative("Aeee, amor, finalmente em casa!", prev), "Aeee, amor, finalmente em casa!")

    def test_meaningful_amor_is_not_touched(self):
        prev = ["amor", "amor"]
        self.assertEqual(thin_vocative("Eu te amo, meu amor da vida", prev), "Eu te amo, meu amor da vida")


class DebounceTest(unittest.TestCase):
    def test_dangling_bubble_waits_longer_than_a_closed_one(self):
        dangling = debounce_delay(["Amor, hoje aconteceu uma coisa no plantão e"], 3.8)
        closed = debounce_delay(["Oi princesa, bom dia! Obrigado por me lembrar 🥰"], 3.8)
        self.assertGreaterEqual(dangling, 10)
        self.assertLessEqual(closed, 4.5)

    def test_burst_waits_more_and_laugh_closes(self):
        self.assertGreater(debounce_delay(["Então", "o chefe saiu cedo hoje"], 3.8),
                           debounce_delay(["o chefe saiu cedo hoje"], 3.8))
        self.assertLessEqual(debounce_delay(["isso aí ksksksk"], 3.8), 4.5)

    def test_always_capped(self):
        self.assertLessEqual(debounce_delay(["a", "e", "mas", "tipo,"], 3.8), 14.0)


class ShareNudgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "n.db")
        self.now = datetime(2026, 9, 23, 13, 20)
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO life_events (event_key,event_at,event_type,title,summary,source_type,
                            autonomy_level,importance,participants_json,share_worthy,created_at)
                            VALUES ('meal:almoco','2026-09-23T13:16:00','meal','Almoço',
                            'Almoço no Shopping da Gávea: comida japonesa.','simulated',2,0.3,'[]',0.4,?)""",
                         (self.now.isoformat(),))
            conn.commit()

    def tearDown(self):
        self.temp.cleanup()

    def _talk(self, n):
        for i in range(n):
            self.db.adicionar_mensagem(role="assistant", content=f"fala {i}")

    def test_she_brings_something_of_hers_then_waits_before_again(self):
        always = random.Random(0)
        always.random = lambda: 0.0
        news = share_nudge(self.db, self.now, intent="casual_chat", rng=always)
        self.assertIn("comida japonesa", news["summary"])
        mark_nudged(self.db, self.now, news["event_key"])
        self.assertIsNone(share_nudge(self.db, self.now + timedelta(minutes=30), intent="casual_chat", rng=always),
                          "já contou e ainda não passaram 5 falas")

    def test_not_while_he_needs_support_or_flirting(self):
        always = random.Random(0)
        always.random = lambda: 0.0
        for intent in ("support_needed", "flirting", "photo_request"):
            self.assertIsNone(share_nudge(self.db, self.now, intent=intent, rng=always))


class TodayAfterRestartTest(unittest.TestCase):
    """23/09 13:59, logo depois do restart."""

    def test_split_bubble_does_not_keep_the_separator_period(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        import bot
        from response_rhythm import select_policy
        fake = MagicMock(send_message=AsyncMock(), send_chat_action=AsyncMock())
        with patch("bot.asyncio.sleep", new=AsyncMock()):
            asyncio.run(bot.send_human_messages(
                987, fake, "Tô em casa, descansando um pouquinho depois da facul. O Milo tá aqui comigo fazendo companhia kkk",
                response_policy=select_policy("tá por onde minha princesa?")))
        sent = [c.kwargs["text"] for c in fake.send_message.call_args_list]
        self.assertTrue(all(not t.endswith(".") for t in sent), sent)

    def test_quiet_shower_is_told_when_he_shows_up(self):
        import json
        from unittest.mock import patch
        import bot
        now = datetime(2026, 9, 23, 13, 59, 5)
        pending = {"routine_type": "shower", "activity": "tomando banho", "announced_at": "2026-09-23T13:57:23",
                   "transition_at": "2026-09-23T13:59:23", "end_at": "2026-09-23T14:14:23", "told_patrick": False}
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(Path(tmp) / "t.db")
            with patch.object(bot.memory_manager, "db", db):
                hint = bot._quiet_transition_hint(dict(pending), now)
                self.assertIn("vai tomar banho", hint)
                told = json.loads(db.get_estado_relacional("pending_transition_json"))
                self.assertTrue(told["told_patrick"])
                self.assertIsNone(bot._quiet_transition_hint(told, now), "avisa uma vez só")
                inside = bot._quiet_transition_hint(dict(pending), now.replace(minute=5, hour=14))
                self.assertIsNone(inside, "no banho ela não pega o celular")
                self.assertIsNone(bot._quiet_transition_hint({**pending, "told_patrick": True}, now))


    def test_message_during_shower_is_answered_after_she_gets_dressed(self):
        import json
        from response_availability import ResponseAvailabilityPolicy
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(Path(tmp) / "a.db")
            db.set_estado_relacional("pending_transition_json", json.dumps(
                {"routine_type": "shower", "activity": "tomando banho", "transition_at": "2026-09-23T13:59:00",
                 "end_at": "2026-09-23T14:14:00", "told_patrick": False}))
            pol = ResponseAvailabilityPolicy(db)
            now = datetime(2026, 9, 23, 14, 2)
            with patch.object(pol, "_resolve_activity", return_value=("SHOWER", "ANNOUNCED", 1, "fresh", True)):
                d = pol.evaluate("tá por onde?", now=now)
            self.assertEqual(d.decision, "DEFER")
            target = d.selected_target_at.replace(tzinfo=None)
            self.assertGreaterEqual(target, datetime(2026, 9, 23, 14, 16))
            self.assertLessEqual(target, datetime(2026, 9, 23, 14, 22))


if __name__ == "__main__":
    unittest.main()
