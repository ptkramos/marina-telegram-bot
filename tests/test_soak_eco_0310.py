"""Soak, dia 5 (sábado 03/10, 14:16): a resposta adiada do banho entrou em laço dentro dela mesma.

Ele (13:56): "Vai lá correndo então, quando voltar não precisa nem se vestir". Ela, ao sair do banho, pelo modelo
principal: "Olha a pressa desse homem kkkkk / Vc quer me deixar sem condição de voltar pro quarto, né?- Juntos há 14
meses e 5 dias.- Juntos há 14 meses e 5 dias.- Juntos há 14 meses e 5 dias" — a frase nem existe no prompt.
"""
import unittest

from chat_naturalness import cortar_eco

REAL = ("Olha a pressa desse homem kkkkk\nVc quer me deixar sem condição de voltar pro quarto, né?- Juntos há 14 "
        "meses e 5 dias.- Juntos há 14 meses e 5 dias.- Juntos há 14 meses e 5 dias")


class CortarEcoTest(unittest.TestCase):
    def test_caso_real_termina_antes_do_laco(self):
        cortada, eco = cortar_eco(REAL)
        self.assertEqual(cortada, "Olha a pressa desse homem kkkkk\nVc quer me deixar sem condição de voltar pro "
                                  "quarto, né?")
        self.assertEqual(eco, "juntos ha 14 meses e 5 dias")

    def test_eco_em_linhas(self):
        cortada, _ = cortar_eco("Vem cá, amor\nTô morrendo de saudade de você\nTô morrendo de saudade de você")
        self.assertEqual(cortada, "Vem cá, amor")

    def test_fala_normal_passa(self):
        for fala in ("Apagar nada, amor...\nÁgua quente só me deixa mais dengosa kkkk\nE com você na cabeça, o fogo "
                     "só piora", "Te amo. Te amo. Te amo", "Vem cá vem. Vem cá vem"):
            self.assertIsNone(cortar_eco(fala), fala)

    def test_so_eco_nao_corta_tudo(self):
        self.assertIsNone(cortar_eco("Tô com saudade de você. Tô com saudade de você"))


if __name__ == "__main__":
    unittest.main()
