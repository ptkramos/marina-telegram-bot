"""25/09 (Patrick com amigdalite): a mesma ideia com outras palavras em respostas seguidas."""
import unittest

from chat_naturalness import drop_paraphrased, drop_repeated_ideas, recent_ideas_hint

PRIMEIRA = ("Poxa, meu dodói…\nQueria estar aí fazendo carinho na sua cabeça e levando um suco geladinho pra "
            "você. Conseguiu tomar água?")
SEGUNDA = ("Ai, meu bem… ainda bem. Continua quietinho e se hidratando, tá?\nQueria te levar um suco geladinho "
           "e ficar fazendo carinho nessa cabeça dodói. Se piorar, você vai no médico, por favor")


class IdeiaParafraseadaTest(unittest.TestCase):
    def test_suco_e_carinho_de_novo_com_outras_palavras_sai(self):
        out = drop_paraphrased(SEGUNDA, [PRIMEIRA])
        self.assertNotIn("suco", out)
        self.assertIn("se hidratando", out)
        self.assertIn("médico", out, "médico ainda não tinha sido dito")

    def test_medico_na_terceira_vez_sai(self):
        terceira = "Tomara, amor… fica bem quietinho\nSe continuar ruim amanhã, vai no médico pra eu ficar tranquila, tá?"
        out = drop_repeated_ideas(terceira, [SEGUNDA])
        self.assertNotIn("médico", out)

    def test_resposta_legitima_com_palavras_da_pergunta_fica(self):
        pergunta = "Amor, lembrei daquele convite da Bia pro Quartinho no sábado… apareceu alguma novidade ou ainda tá em aberto?"
        resposta = ("Quero ir sim. O convite da Bia ainda tá em aberto, mas acho que vou topar o Quartinho no sábado "
                    "às 21h")
        self.assertEqual(drop_paraphrased(resposta, [pergunta]), resposta)

    def test_frase_curta_ou_nova_nao_e_cortada(self):
        self.assertEqual(drop_paraphrased("Te amo, amor", ["Te amo muito, amor"]), "Te amo, amor")
        self.assertEqual(drop_paraphrased("Se piorar, me chama", [SEGUNDA]), "Se piorar, me chama")

    def test_se_nao_sobra_fala_devolve_inteira(self):
        so_repeticao = "Queria te levar um suco geladinho e fazer carinho nessa cabeça"
        self.assertEqual(drop_paraphrased(so_repeticao, [PRIMEIRA]), so_repeticao)

    def test_aviso_antes_de_gerar(self):
        hint = recent_ideas_hint(["oi", PRIMEIRA, SEGUNDA])
        self.assertIn("suco geladinho", hint)
        self.assertNotIn("«oi»", hint, "só as duas últimas")
        self.assertEqual(recent_ideas_hint([]), "")


if __name__ == "__main__":
    unittest.main()
