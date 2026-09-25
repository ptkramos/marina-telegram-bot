"""25/09 (Patrick): "na maioria das vezes um balão com 2 a 3 palavras já resolve"."""
import unittest

from chat_naturalness import keep_short, short_turn


class TurnoCurtinhoTest(unittest.TestCase):
    def test_chuva_depois_da_resposta_sai(self):
        fala = ("Tenho sim, amor, fica sussa\nTô com uma graninha guardada dos últimos jobs\n"
                "Dá e sobra pra tomar uns drinks com o pessoal mais tarde kkk\nPreocupa com isso não")
        self.assertEqual(keep_short(fala), "Tenho sim, amor, fica sussa")

    def test_riso_de_abertura_fica(self):
        self.assertEqual(keep_short("kkkkk\nolha ele\nfiscal do bolo\nvou descer com o Milo"), "kkkkk\nolha ele")
        self.assertEqual(keep_short("😭\nAMOR\nobrigada"), "😭\nAMOR")

    def test_tag_nao_e_cortada(self):
        fala = "Já te lembro sim\n[LEMBRETE: remédio 20h]"
        self.assertEqual(keep_short(fala), fala)

    def test_sorteio_so_na_conversa_casual(self):
        casual = sum(short_turn("Tá 🫶", "casual_short", str(i)) for i in range(200))
        self.assertTrue(90 < casual < 170, casual)
        self.assertFalse(any(short_turn("Tá 🫶", "serious", str(i)) for i in range(50)))
        self.assertFalse(any(short_turn("tb te amo", "excited", str(i)) for i in range(50)))

    def test_quando_ele_pede_conteudo_ou_manda_varias_coisas(self):
        for his in ("me conta como foi o ensaio", "por que vc tá triste?",
                    "Mulher esse valor é pro açaí e um mimo\nSe controla em\nJá almoçou?",
                    "Falar nisso\nVai na academia hj?"):
            self.assertFalse(any(short_turn(his, "casual_short", str(i)) for i in range(50)), his)
        self.assertTrue(any(short_turn("Quer q eu mande?", "casual_short", str(i)) for i in range(20)))


if __name__ == "__main__":
    unittest.main()
