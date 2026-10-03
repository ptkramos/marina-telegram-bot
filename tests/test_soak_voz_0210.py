"""Frente da voz, 03/10 — item 25 do painel: a voz do áudio variando (/feedback 02/10 19:52) e o lote dos /ruim.

1. Voz variando: eram dois clones diferentes e o roteador trocava a cada áudio (o íntimo ~3,5 semitons mais agudo).
   Agora é uma voz só (o clone original, o do demo de 15/09); o perfil íntimo é o modo provocar dela: 0.95 e até
   duas pausas onde a frase fecha (o P2 que o Patrick escolheu). O sexting de verdade também usa esse modo.
2. /ruim 057 e 066: "eu sabia que era boa" (+ "ordinaries") quando ele reage com 🤣 — ela respondia sem saber a qual
   balão; agora lê o balão e a conversa, a fala passa pela limpeza e vai pro histórico.
3. /ruim 059: "e já tomei banho tb kkk" sem ninguém perguntar — o fato do banho só vale quando o assunto pede.
4. 23:34: "como foi o dia, mas devagar" virou o dia inteiro em 7 balões — devagar é por partes.
"""
import asyncio
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from chat_naturalness import contar_devagar_hint
from voice_engine import VoiceEngine
from voice_profile import PROFILE_INTIMATE, get_conversational_profile, get_intimate_profile
from voice_prosody import VoiceProsodyPolicy, capabilities_for, render_voice
from voice_router import VoiceRouter, VoiceSelectionContext


class VozUnicaTest(unittest.TestCase):
    def test_os_dois_perfis_sao_a_mesma_voz(self):
        conv, intim = get_conversational_profile(), get_intimate_profile()
        self.assertEqual(conv.voice_id, intim.voice_id)
        self.assertEqual(conv.speed, 1.0)
        self.assertEqual(intim.speed, 0.95)

    def test_sexting_usa_o_modo_provocar_mesmo_em_pergunta(self):
        perfil, motivo = VoiceRouter.route(VoiceSelectionContext(intent="question", tone="", sexting=True))
        self.assertEqual((perfil.name, motivo), (PROFILE_INTIMATE, "sexting"))
        perfil, _ = VoiceRouter.route({"intent": "question", "sexting": True})
        self.assertEqual(perfil.name, PROFILE_INTIMATE)
        perfil, _ = VoiceRouter.route(VoiceSelectionContext(intent="question"))
        self.assertNotEqual(perfil.name, PROFILE_INTIMATE)

    def test_modo_provocar_poe_ate_duas_pausas_onde_a_frase_fecha(self):
        texto = "Vem cá... tô deitada aqui só te esperando. Assim eu fico impaciente, sabia? Vem logo."
        plano = render_voice(texto, VoiceProsodyPolicy(pause_profile="provocar"), capabilities_for("novita", "speech-2.8-hd"))
        self.assertEqual(plano.render_text.count("<#"), 2)
        self.assertIn("Vem cá... <#0.35#> tô deitada", plano.render_text)
        self.assertIn("esperando. <#0.30#> Assim", plano.render_text)
        normal = render_voice(texto, VoiceProsodyPolicy(pause_profile="casual"), capabilities_for("novita", "speech-2.8-hd"))
        self.assertEqual(normal.render_text.count("<#"), 1)

    def test_audio_intimo_vai_na_mesma_voz_arrastando(self):
        engine = VoiceEngine()
        engine.novita_api_key = "x"
        enviados = []

        def falso_post(url, json=None, headers=None, timeout=None):
            enviados.append(json)
            return SimpleNamespace(status_code=500)

        texto = "Vem cá, tô deitada aqui só te esperando. Assim eu fico impaciente, sabia?"
        with patch("voice_engine.requests.post", side_effect=falso_post), \
                patch.object(engine, "_synthesize_elevenlabs", AsyncMock(return_value=False)), \
                patch.object(engine, "_synthesize_gemini", AsyncMock(return_value=False)):
            asyncio.run(engine.synthesize(texto, profile="intimate"))
            asyncio.run(engine.synthesize(texto, profile="conversational"))
        intimo, conversa = enviados
        self.assertEqual(intimo["voice_setting"]["voice_id"], conversa["voice_setting"]["voice_id"])
        self.assertEqual(intimo["voice_setting"]["speed"], 0.95)
        self.assertEqual(conversa["voice_setting"]["speed"], 1.0)
        self.assertIn("<#", intimo["text"])
        self.assertNotIn("timbre_weights", intimo)


class RespostaAReacaoTest(unittest.TestCase):
    CHAT = 4242

    def setUp(self):
        bot._last_verbal_reply_to_reaction.pop(self.CHAT, None)
        bot.ULTIMAS_MENSAGENS_MARINA[self.CHAT] = [
            {"message_id": 10, "text": "Eu só sou a acompanhante oficial do passeio do Milo"},
            {"message_id": 11, "text": "ele me olha como se eu tivesse cometido um crime"},
        ]

    def tearDown(self):
        bot.ULTIMAS_MENSAGENS_MARINA.pop(self.CHAT, None)
        bot._last_verbal_reply_to_reaction.pop(self.CHAT, None)

    def _reagir(self, message_id, fala="eu sabia que era boa ordinaries"):
        update = SimpleNamespace(message_reaction=SimpleNamespace(
            chat=SimpleNamespace(id=self.CHAT), user=SimpleNamespace(id=self.CHAT), message_id=message_id,
            new_reaction=[SimpleNamespace(emoji="🤣")]))
        gerar = MagicMock(return_value=fala)
        enviar = AsyncMock()
        registrar = MagicMock()
        with patch.object(bot.settings, "TARGET_CHAT_ID", self.CHAT), \
                patch.object(bot.settings, "REACT_TO_LAUGH_REACTION_CHANCE", 1.0), \
                patch.object(bot, "generate_dynamic_speech", gerar), \
                patch.object(bot, "send_human_messages", enviar), \
                patch.object(bot.memory_manager, "registrar_mensagem_assistente", registrar):
            asyncio.run(bot.handle_reaction(update, SimpleNamespace(bot=MagicMock())))
        return gerar, enviar, registrar

    def test_ela_sabe_em_qual_balao_ele_riu_e_a_fala_sai_limpa_e_vai_pro_historico(self):
        gerar, enviar, registrar = self._reagir(11)
        instrucao = gerar.call_args.args[0]
        self.assertIn("cometido um crime", instrucao)
        self.assertNotIn("sabia que", instrucao, "exemplo negativo puxava a própria frase")
        self.assertTrue(gerar.call_args.kwargs.get("with_history"))
        self.assertEqual(enviar.call_args.args[2], "eu sabia que era boa")
        registrar.assert_called_once_with("eu sabia que era boa")

    def test_balao_desconhecido_fica_em_silencio(self):
        gerar, enviar, registrar = self._reagir(999)
        gerar.assert_not_called()
        enviar.assert_not_called()
        registrar.assert_not_called()


class BanhoEDevagarTest(unittest.TestCase):
    def test_limpeza_tira_ordinaries(self):
        self.assertEqual(bot.limpar_fala_marina("eu sabia que era boa ordinaries"), "eu sabia que era boa")

    def test_fato_do_banho_nao_vira_assunto(self):
        from world_context import WorldContextBuilder
        import inspect
        fonte = inspect.getsource(WorldContextBuilder._banho)
        self.assertIn("mencione o banho sem ele ter tocado no tema", fonte)

    def test_contar_devagar_e_por_partes(self):
        self.assertIn("[DEVAGAR]", contar_devagar_hint("Então fala pro seu namorado, como foi o dia hoje, mas devagar ksksks"))
        self.assertIn("[DEVAGAR]", contar_devagar_hint("me conta com calma o que aconteceu"))
        self.assertEqual(contar_devagar_hint("vai devagar na chuva"), "")
        self.assertEqual(contar_devagar_hint("conta como foi o dia"), "")


if __name__ == "__main__":
    unittest.main()
