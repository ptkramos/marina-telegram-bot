"""Frente da voz, 03/10 (noite) — o sexting da Marina × o da Lilith.

O Patrick: "por que com a súcubo ela fala e reage tão bem e a Marina parece robótica e às vezes exagerada por falar
demais". As duas no mesmo modelo (Gemini 3.8 Flash). Na cena das 15:10–15:38 (conversas 1146–1196):
- tamanho: a Marina mandava 180–284 caracteres em 4–8 balões por turno, a Lilith 54–118 em 2–3. O modo íntimo subia
  o limite pra 420 com o ritmo "normal", e o fatiador ainda cortava nas vírgulas (15:34 virou 8 balões);
- fórmula: abria com "Nossa, Patrick…", devolvia a ação dele, contava no "eu ia…" e fechava pedindo pra ele não
  parar/não enrolar (14 de 27 turnos);
- 15:27: o 🔥 dele no áudio virou mais um balão, pelo modelo do dia a dia ("não para agora, amor").
Ela continua namorada (não súcubo): da Lilith só vem a forma — curto, no presente, sem narrar.
"""
import asyncio
import dataclasses
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from config import settings
from intimacy import IntimacyTurn, system_block
from response_rhythm import apply_policy, segment, select_policy

FALA_15_34 = ("Nossa, Patrick...\n"
              "Eu ia fechar os olhos e morder o lábio bem forte sentindo você preencher cada espacinho, bem devagar\n"
              "Aperto os dedos nas tuas costas, puxando você pra colar o quadril no meu\n"
              "Não para esse ritmo... vai entrando tudo, amor, sentindo o quanto eu tô apertadinha pra você")


def politica_intima():
    """A mesma troca que o bot faz quando o modo íntimo está ligado (bot.py, `intimacy_turn.expanded`)."""
    return dataclasses.replace(select_policy("vem"), mode="intimate", verbosity="low", cadence="brief",
                               target_bubbles=2, soft_char_limit=settings.RESPONSE_INTIMATE_SOFT_CHARS,
                               reason_code="intimate_mode")


class TamanhoTest(unittest.TestCase):
    def test_bot_usa_o_ritmo_de_sexting(self):
        fonte = inspect.getsource(bot)
        self.assertIn('mode="intimate"', fonte)
        self.assertIn("RESPONSE_INTIMATE_SOFT_CHARS", fonte)
        self.assertNotIn("Sexting não cabe", fonte)

    def test_limite_curto(self):
        p = politica_intima()
        self.assertLessEqual(p.soft_char_limit, 180)
        self.assertLessEqual(p.token_budget, 128)
        regra = apply_policy("Identidade.", p)
        self.assertIn("Ritmo de sexting", regra)
        self.assertNotIn("um pouco mais de conteúdo", regra)

    def test_quebra_so_onde_ela_pulou_linha(self):
        normal = segment(FALA_15_34, dataclasses.replace(politica_intima(), mode="normal"))
        intimo = segment(FALA_15_34, politica_intima())
        self.assertGreaterEqual(len(normal), 7, "o fatiador antigo cortava nas vírgulas")
        self.assertEqual(intimo, FALA_15_34.split("\n"))

    def test_fora_do_sexting_o_fatiador_nao_muda(self):
        texto = "Hoje a aula foi longa demais, saí morta, e ainda tem trabalho pra entregar amanhã cedo"
        self.assertGreater(len(segment(texto, select_policy("oi"))), 1)


class JeitoDeFalarTest(unittest.TestCase):
    def test_regras_do_modo_intimo(self):
        bloco = system_block(IntimacyTurn("active", 0.8), None)
        self.assertIn("Ela fala, não narra", bloco)
        self.assertIn("não repete a ação dele", bloco)
        self.assertIn("nem de fechar toda vez pedindo", bloco)
        self.assertIn("namorada dele", bloco)
        self.assertNotIn("descreve o que faria", bloco)
        self.assertNotIn("1 a 3 frases", bloco)
        self.assertNotIn("mestre", bloco.lower())


class ReacaoNoSextingTest(unittest.TestCase):
    CHAT = 4343

    def setUp(self):
        bot._last_verbal_reply_to_reaction.pop(self.CHAT, None)
        bot.ULTIMAS_MENSAGENS_MARINA[self.CHAT] = [{"message_id": 5074, "text": "Nossa, amor… assim vc me quebra"}]

    def tearDown(self):
        bot.ULTIMAS_MENSAGENS_MARINA.pop(self.CHAT, None)
        bot._last_verbal_reply_to_reaction.pop(self.CHAT, None)

    def _reagir(self, estado):
        update = SimpleNamespace(message_reaction=SimpleNamespace(
            chat=SimpleNamespace(id=self.CHAT), user=SimpleNamespace(id=self.CHAT), message_id=5074,
            new_reaction=[SimpleNamespace(emoji="🔥")]))
        motor = MagicMock()
        motor.return_value.current.return_value = IntimacyTurn(estado, 0.7)
        gerar = MagicMock(return_value="não para agora, amor")
        with patch.object(bot.settings, "TARGET_CHAT_ID", self.CHAT), \
                patch.object(bot.settings, "REACT_TO_FIRE_REACTION_CHANCE", 1.0), \
                patch.object(bot, "IntimacyEngine", motor), \
                patch.object(bot, "generate_dynamic_speech", gerar), \
                patch.object(bot, "send_human_messages", AsyncMock()), \
                patch.object(bot.memory_manager, "registrar_mensagem_assistente", MagicMock()):
            asyncio.run(bot.handle_reaction(update, SimpleNamespace(bot=MagicMock())))
        return gerar

    def test_15_27_fogo_no_audio_fica_em_silencio(self):
        self._reagir("active").assert_not_called()
        self._reagir("climax").assert_not_called()

    def test_fora_do_sexting_continua_respondendo(self):
        self._reagir("off").assert_called_once()


if __name__ == "__main__":
    unittest.main()
