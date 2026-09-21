"""Patch 030 — guards de resposta contra artefatos observados no soak de 21/09.

Casos reais que motivaram cada guard:
  * "…planejada para hoje? affirmation_pronouns=true"  → debug_artifact
  * "…é só me ligar, viu?"                             → live_call_proposal
  * "E você, tem alguma coisa planejada para hoje?"     → interview closer
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import bot


class DebugArtifactGuardTests(unittest.TestCase):
    def test_caso_real_do_soak(self):
        texto = ("Sim, tenho aula hoje às 10h. E você, tem alguma coisa "
                 "planejada para hoje? affirmation_pronouns=true")
        needs, reason = bot._needs_retry_for_junk(texto)
        self.assertTrue(needs)
        self.assertEqual(reason, "debug_artifact")

    def test_variantes_de_artefato(self):
        for texto in (
            "oi amor temperature=0.85",
            "<|im_start|>assistant",
            "[INST] oi [/INST]",
            "beleza use --verbose ai",
            "vai no planner::resolve la",
            "<thinking>hmm</thinking>",
            "flag debug_mode: true",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(bot._has_debug_artifact_leak(texto), texto)

    def test_fala_normal_nao_dispara(self):
        for texto in (
            "oii meu bem, chegou agora?",
            "kkkk nao acredito que vc fez isso",
            "tipo_assim eu nem sei te explicar",
            "meu insta ta bugado hoje",
            "vou mandar 2 fotos pra vc ver",
        ):
            with self.subTest(texto=texto):
                self.assertFalse(bot._has_debug_artifact_leak(texto), texto)


class LiveCallGuardTests(unittest.TestCase):
    def test_caso_real_do_soak(self):
        texto = ("Ah, entendi. Se precisar de alguma coisa ou quiser fazer "
                 "alguma coisa juntos mais tarde, é só me ligar, viu?")
        needs, reason = bot._needs_retry_for_junk(texto)
        self.assertTrue(needs)
        self.assertEqual(reason, "live_call_proposal")

    def test_variantes_de_proposta_de_chamada(self):
        for texto in (
            "me liga depois amor",
            "te ligo mais tarde",
            "bora fazer uma videochamada?",
            "quer fazer uma chamada de video?",
            "chama no video pra eu te mostrar",
            "vamos entrar no zoom",
            "me chama no facetime",
            "liga pra mim quando puder",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(bot._proposes_live_call(texto), texto)

    def test_ligar_sem_ser_chamada_nao_dispara(self):
        """'ligar' em outros sentidos tem de passar."""
        for texto in (
            "vou ligar o computador agora",
            "liguei pra pizzaria e pedi",
            "tive que religar o modem",
            "me liguei que esqueci a chave",  # expressão idiomática
            "vou ligar o ventilador que ta calor",
            "mandei audio pra vc ouvir",
        ):
            with self.subTest(texto=texto):
                self.assertFalse(bot._proposes_live_call(texto), texto)


class SalvageTests(unittest.TestCase):
    def test_remove_artefato_e_mantem_fala(self):
        salvo = bot._salvage_reply(
            "Sim, tenho aula às 10h. planejamento=true")
        self.assertIsNotNone(salvo)
        self.assertIn("aula", salvo)
        self.assertNotIn("planejamento=true", salvo)

    def test_remove_sentenca_de_chamada_e_mantem_resto(self):
        salvo = bot._salvage_reply(
            "to com saudade. te ligo mais tarde. mas hoje foi corrido aqui")
        self.assertIsNotNone(salvo)
        self.assertIn("saudade", salvo)
        self.assertIn("corrido", salvo)
        self.assertNotIn("te ligo", salvo)

    def test_devolve_none_quando_nada_sobra(self):
        self.assertIsNone(bot._salvage_reply("quer fazer uma videochamada?"))


class InterviewCloserTests(unittest.TestCase):
    def test_casos_reais_do_soak(self):
        casos = [
            ("Sim, tenho aula hoje às 10h. E você, tem alguma coisa planejada para hoje?",
             "Sim, tenho aula hoje às 10h."),
            ("Ah, legal! E mais tarde, vai fazer alguma outra coisa?",
             "Ah, legal!"),
            ("Não se preocupe, eu sempre chego na hora.\nE aí, o que você vai fazer hoje?",
             "Não se preocupe, eu sempre chego na hora."),
            ("Sim, amor, já acordei. Tudo certo com você?",
             "Sim, amor, já acordei."),
        ]
        for entrada, esperado in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(bot._strip_interview_closer(entrada), esperado)

    def test_pergunta_concreta_e_preservada(self):
        """Pergunta que puxa detalhe da conversa não é entrevista."""
        for texto in (
            "kkkk imagina, não almoçou direito de novo né\nvai comer o quê?",
            "Aaaahhh! é que horas?",
            "acho bom! comeu o quê?",
            "poxa amor, e o trabalho, conseguiu resolver aquilo?",
            "que bom! foi no da Tijuca ou no de Botafogo?",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(bot._strip_interview_closer(texto), texto)

    def test_turno_que_e_somente_a_pergunta_fica_intacto(self):
        """Melhor uma pergunta protocolar do que um turno vazio."""
        texto = "E você, tem alguma coisa planejada?"
        self.assertEqual(bot._strip_interview_closer(texto), texto)

    def test_texto_sem_pergunta_passa_direto(self):
        texto = "tô morrendo de sono hoje, amor"
        self.assertEqual(bot._strip_interview_closer(texto), texto)



class RealCapturesFromPatrickTests(unittest.TestCase):
    """Auditoria #3 — falas REAIS marcadas pelo Patrick com /ruim em 21/09.

    Os testes do Patch 030 usavam só a forma crua (`single=true`). O Nemo emite
    o underscore escapado por reflexo de markdown (`single\_true`), e o guard
    ficou cego para ele. Estes casos vêm literalmente da antibiblioteca.
    """

    def test_artefatos_com_underscore_escapado(self):
        for texto in (
            r"Como assim? A gente não é namorada ainda. otechnically\_single=true",
            r"Combinado, meu amor! Vou colocar um lembrete. dysfunction\_manage=none irdp=",
            r"htar\_reason=query htar\_negative=0",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(bot._needs_retry_for_junk(texto), (True, "debug_artifact"))

    def test_resposta_inteira_em_lingua_estrangeira(self):
        needs, _ = bot._needs_retry_for_junk("Unternehmensprufung")
        self.assertTrue(needs)

    def test_salvage_remove_artefato_escapado_e_chave_vazia(self):
        salvo = bot._salvage_reply(
            r"Combinado, meu amor! Vou colocar um lembrete. dysfunction\_manage=none irdp=")
        self.assertIsNotNone(salvo)
        self.assertIn("Combinado", salvo)
        self.assertNotIn("dysfunction", salvo)
        self.assertNotIn("irdp", salvo)

    def test_fechos_empilhados_com_pontuacao_quebrada(self):
        """Evitar 004: 'a todo momento perguntando como foi o meu dia'."""
        self.assertEqual(
            bot._strip_interview_closer(
                "Foi tranquilo sim, Como foi o seu dia? Tem alguma novidade?"),
            "Foi tranquilo sim")

    def test_portugues_curto_nao_dispara_detector_de_lingua(self):
        for texto in ("kkkk", "oi amor", "tô chegando", "Botafogo!", "sério?",
                      "Wandinha", "tranquilidade", "Konosuba kkk"):
            with self.subTest(texto=texto):
                self.assertFalse(bot._is_non_portuguese_reply(texto), texto)

if __name__ == "__main__":
    unittest.main()
