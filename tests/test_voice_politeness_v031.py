"""Patch 031 — remoção de polidez de assistente na fala da Marina.

Casos reais do soak de 21/09 manhã:
  * "Ah, entendi." / "Ah, legal!"          → muleta de abertura
  * "Dormi também, obrigada por perguntar!" → polidez formal
  * "…fico de olho na gente. Beijos 😘"     → assinatura de despedida

O ponto delicado é NÃO tocar nas interjeições legítimas que já estão aprovadas
na biblioteca comportamental — "AH NÃO KKKKKKK" (registro 070) e
"ah então tempo vc teve né…" (registro 041) são voz da Marina, não muleta.
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import bot


class AhCrutchTests(unittest.TestCase):
    def test_casos_reais_do_soak(self):
        casos = [
            ("Ah, entendi. Tudo bem amor", "Entendi. Tudo bem amor"),
            ("Ah, legal! e mais tarde?", "Legal! e mais tarde?"),
            ("Ah, tá bom então", "Tá bom então"),
            ("Ah, sei...", "Sei..."),
        ]
        for entrada, esperado in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(bot._strip_assistant_politeness(entrada), esperado)

    def test_interjeicoes_da_biblioteca_ficam_intactas(self):
        """Exemplos aprovados pelo Patrick não podem ser mutilados."""
        for texto in (
            "AH NÃO KKKKKKK isso já tá virando tradição",          # registro 070
            "ah então tempo vc teve né… só esqueceu de mim mesmo…",  # registro 041
            "ihhh já começou a zika reversa? kkkkk",                # registro 069
            "Aaaahhh! é que horas?",                                # canônico
            "Ahhh que fofo vc",
            "ah meu Deus kkkkk nao acredito",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(bot._strip_assistant_politeness(texto), texto)


class ServicePolitenessTests(unittest.TestCase):
    def test_obrigada_por_perguntar_sai(self):
        saida = bot._strip_assistant_politeness(
            "Dormi também, obrigada por perguntar!")
        self.assertNotIn("obrigada por perguntar", saida.lower())
        self.assertIn("Dormi também", saida)

    def test_se_precisar_de_alguma_coisa_sai_quando_ha_resto(self):
        saida = bot._strip_assistant_politeness(
            "tô meio corrida hoje amor. Se precisar de alguma coisa, é só me chamar.")
        self.assertIn("corrida", saida)
        self.assertNotIn("só me chamar", saida.lower())

    def test_obrigada_afetivo_fica(self):
        for texto in (
            "obrigada amor, vc é o melhor",
            "obrigada por hoje, foi tão bom",
            "ai obrigada mesmo, me salvou",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(bot._strip_assistant_politeness(texto), texto)


class SignoffTests(unittest.TestCase):
    def test_assinatura_no_fim_sai(self):
        casos = [
            "Ok, pode deixar que eu fico de olho. Beijos 😘",
            "vou nessa então\nBeijos!",
            "combinado amor. Beijinhos",
        ]
        for entrada in casos:
            with self.subTest(entrada=entrada):
                saida = bot._strip_assistant_politeness(entrada)
                self.assertNotRegex(saida.lower(), r"beij\w*\s*[!.…]*\s*$")
                self.assertTrue(saida.strip(), "não pode ficar vazio")

    def test_beijos_no_meio_da_fala_fica(self):
        for texto in (
            "te enchendo de beijos agora",
            "manda beijo pro Milo por mim",
            "quero mil beijos seus quando te ver",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(bot._strip_assistant_politeness(texto), texto)


class NeverEmptyTests(unittest.TestCase):
    def test_resposta_inteiramente_polida_e_preservada(self):
        """Sem substância pra manter, é melhor o original do que vazio."""
        for texto in ("Fico à disposição!", "Beijos 😘", "obrigada por perguntar"):
            with self.subTest(texto=texto):
                saida = bot._strip_assistant_politeness(texto)
                self.assertTrue(saida.strip())

    def test_texto_vazio_nao_explode(self):
        self.assertEqual(bot._strip_assistant_politeness(""), "")
        self.assertEqual(bot._strip_assistant_politeness("   ").strip(), "")


class CombinadoComInterviewCloserTests(unittest.TestCase):
    def test_turno_real_completo_do_soak(self):
        """O turno das 08:04 tinha muleta + polidez + proposta de chamada."""
        bruto = ("Ah, entendi. Se precisar de alguma coisa ou quiser fazer "
                 "alguma coisa juntos mais tarde, é só me ligar, viu?")
        # O guard de chamada manda pra retry; se o retry falhar, o salvage corta.
        needs, reason = bot._needs_retry_for_junk(bruto)
        self.assertTrue(needs)
        self.assertEqual(reason, "live_call_proposal")
        salvo = bot._salvage_reply(bruto)
        self.assertIsNotNone(salvo)
        # Depois do salvage, a polidez restante também sai.
        final = bot._strip_assistant_politeness(salvo)
        self.assertNotIn("ligar", final.lower())
        self.assertTrue(final.strip())


if __name__ == "__main__":
    unittest.main()
