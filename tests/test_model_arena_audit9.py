"""Auditoria #9 — arena de modelos e o caminho da foto.

Caso real (21/09 19:02): Patrick mandou foto "Tô deitado assistindo Harry Potter"
logo depois da Marina perguntar "E o que seu chefe disse…?". A resposta foi
"Não contei, ele não sabe, eu só trabalho meio período mesmo" — o modelo
respondeu a própria pergunta no lugar do Patrick, porque o payload da foto
terminava na fala dela: a foto só existia no system prompt.
"""
import asyncio
import datetime as dtmod
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


class PhotoTurnTests(unittest.TestCase):
    def test_foto_e_o_ultimo_turno_do_patrick(self):
        import bot
        from config import settings

        captured = {}

        def fake_create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="Aiii que delícia, Harry Potter deitadinho 🥰"))])

        historico = [{"role": "system", "content": "prompt"},
                     {"role": "assistant", "content": "E o que seu chefe disse?"}]
        photo = SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace(
            download_as_bytearray=AsyncMock(return_value=bytearray(b"img")))))
        chat = SimpleNamespace(id=settings.TARGET_CHAT_ID)
        update = SimpleNamespace(effective_chat=chat, effective_user=chat,
                                 message=SimpleNamespace(message_id=1, photo=[photo],
                                                         caption="Tô deitado assistindo Harry Potter"))
        context = SimpleNamespace(bot=MagicMock(send_chat_action=AsyncMock()))
        with patch.object(bot, "build_messages_payload", side_effect=lambda **_: list(historico)), \
             patch.object(bot.vision_service, "analyze_image", AsyncMock(return_value={})), \
             patch.object(bot.vision_service, "format_vision_context", return_value="[VISÃO] cama, TV"), \
             patch.object(bot.planner, "plan_message", return_value={}), \
             patch.object(bot.llm_client.chat.completions, "create", side_effect=fake_create), \
             patch.object(bot, "send_human_messages", AsyncMock(return_value=None)):
            asyncio.run(bot.handle_photo_message(update, context))
        last = captured["messages"][-1]
        self.assertEqual(last["role"], "user")
        self.assertIn("Harry Potter", last["content"])


class PlannerSanitizeTests(unittest.TestCase):
    """Gemma 4 devolveu todos os campos do plano como -1; o turno morria."""

    def test_plano_com_tipos_errados_vira_padrao(self):
        from planner import _sanitize_plan
        campos = ["intent", "tone", "response_goal", "reaction_emoji", "creates_event", "event_details",
                  "reminder_candidate", "should_offer_reminder", "recommended_reminder_offset_minutes",
                  "direct_reminder", "creates_open_loop", "open_loop_details", "resolves_open_loop",
                  "resolved_loop_hint", "shared_topic", "emotional_deltas"]
        plan = _sanitize_plan({k: -1 for k in campos})
        self.assertEqual((plan["intent"], plan["tone"]), ("casual_chat", "carinhosa"))
        self.assertIsNone(plan["event_details"])
        self.assertIs(plan["creates_event"], False)
        self.assertIsNone(plan["reaction_emoji"])
        self.assertEqual(plan["emotional_deltas"], {})

    def test_plano_bom_passa_intacto(self):
        from planner import _sanitize_plan
        bom = {"intent": "desabafo", "tone": "acolhedora", "reaction_emoji": "🫂", "creates_event": False,
               "event_details": None, "emotional_deltas": {"affection": 0.02, "lixo": "x"}}
        plan = _sanitize_plan(dict(bom))
        self.assertEqual(plan["intent"], "desabafo")
        self.assertEqual(plan["reaction_emoji"], "🫂")
        self.assertEqual(plan["emotional_deltas"], {"affection": 0.02})

    def test_planner_com_json_lixo_nao_derruba(self):
        from planner import InternalPlanner
        resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"intent": -1, "event_details": -1, "creates_event": -1}'))])
        llm = MagicMock()
        llm.chat.completions.create.return_value = resp
        plan = InternalPlanner(db=MagicMock(), llm_client=llm).plan_message("tô meio pra baixo hoje")
        self.assertIsNone(plan["event_details"])
        self.assertEqual(plan["intent"], "casual_chat")


class LlmOptionsTests(unittest.TestCase):
    def test_raciocinio_desligado_por_padrao(self):
        from config import settings
        from llm_options import llm_kwargs
        with patch.object(settings, "LLM_REASONING", "off"):
            kw = llm_kwargs(160)
        self.assertEqual(kw["max_tokens"], 160)
        self.assertEqual(kw["extra_body"], {"reasoning": {"enabled": False}})

    def test_raciocinio_obrigatorio_ganha_orcamento_extra(self):
        from config import settings
        from llm_options import llm_kwargs, REASONING_EXTRA_TOKENS
        with patch.object(settings, "LLM_REASONING", "low"):
            kw = llm_kwargs(160)
        self.assertEqual(kw["max_tokens"], 160 + REASONING_EXTRA_TOKENS)
        self.assertEqual(kw["extra_body"]["reasoning"], {"effort": "low", "exclude": True})


class ReplyGuardArenaTests(unittest.TestCase):
    def test_canares_e_outros_alfabetos_disparam_retry(self):
        import bot
        self.assertTrue(bot._has_foreign_script_leak("Como foi a conversa com ele? ್ದೇಶ"))
        self.assertTrue(bot._has_foreign_script_leak("tudo bem ধন্য"))
        self.assertFalse(bot._has_foreign_script_leak("Mano, sério? Fiquei muito feliz 🥹🖤 ação, pão"))

    def test_horario_ja_citado_nao_ganha_frase_repetida(self):
        import bot
        nove = dtmod.datetime(2026, 9, 28, 9, 0)
        for texto in ("te dou esse toque às 09h", "combinado, te lembro às 9 🤍", "9 da manhã em ponto"):
            with self.subTest(texto=texto):
                self.assertTrue(bot._mentions_clock(texto, nove))
        self.assertFalse(bot._mentions_clock("às 19:00", nove))
        self.assertFalse(bot._mentions_clock("às 9:30", nove))


class FeedbackContextTests(unittest.TestCase):
    def test_ruim_grava_a_fala_que_ela_respondia(self):
        """Evitar 015: a resposta era ao 'Eu trabalho amanhã', não à foto que veio depois."""
        import bot
        sessao = [
            {"role": "user", "content": "Eu trabalho amanhã, dia de plantão 🫠"},
            {"role": "assistant", "content": "Ah, que chato! E o que seu chefe disse quando você contou?"},
            {"role": "user", "content": "[Foto enviada pelo Patrick: Tô deitado assistindo Harry Potter]"},
            {"role": "assistant", "content": "Não contei, ele não sabe"},
        ]
        with patch.object(bot.memory_manager.db, "get_mensagens_sessao", return_value=sessao):
            self.assertEqual(bot._last_patrick_line("E o que seu chefe disse quando você contou?"),
                             "Eu trabalho amanhã, dia de plantão 🫠")
            self.assertTrue(bot._last_patrick_line("Não contei, ele não sabe").startswith("[Foto"))
            self.assertTrue(bot._last_patrick_line().startswith("[Foto"))


class ArenaClockTests(unittest.TestCase):
    def test_relogio_congelado_vale_para_imports_posteriores(self):
        import importlib
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        real_dt, real_date = dtmod.datetime, dtmod.date
        try:
            clock = importlib.import_module("scripts_clock").install_clock(dtmod)
            clock.set(real_dt(2026, 9, 27, 18, 48))
            from datetime import datetime  # import feito DEPOIS da instalação
            self.assertEqual(datetime.now().strftime("%d/%m %H:%M"), "27/09 18:48")
            self.assertEqual(dtmod.date.today().day, 27)
        finally:
            dtmod.datetime, dtmod.date = real_dt, real_date


if __name__ == "__main__":
    unittest.main()
