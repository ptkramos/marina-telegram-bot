"""25/09 (Patrick): ela nunca abreviava ("você" 159×, "vc" 0×). Mistura moderada, decidida na saída."""
import re
import unittest

from chat_naturalness import abbreviate

FALAS = [f"Oi amor, você vai sair hoje depois da aula? Também queria ficar comigo, porque tô com muita saudade ({i})"
         for i in range(200)]


def _conta(textos, palavra):
    return sum(len(re.findall(rf"(?<!\w){palavra}(?!\w)", t, re.IGNORECASE)) for t in textos)


class AbreviacoesTest(unittest.TestCase):
    def test_mistura_moderada(self):
        saida = [abbreviate(f) for f in FALAS]
        taxa = _conta(saida, "vc") / len(FALAS)
        self.assertTrue(0.2 < taxa < 0.5, taxa)
        self.assertGreater(_conta(saida, "você"), _conta(saida, "vc"), "a forma cheia continua maioria")
        for ab in ("hj", "dps", "tb", "cmg", "pq"):
            self.assertGreater(_conta(saida, ab), 0, ab)

    def test_mesma_fala_sai_igual(self):
        self.assertEqual(abbreviate(FALAS[0]), abbreviate(FALAS[0]))

    def test_conversa_seria_abrevia_menos(self):
        normal = sum(len(abbreviate(f)) for f in FALAS)
        seria = sum(len(abbreviate(f, serious=True)) for f in FALAS)
        self.assertGreater(seria, normal)

    def test_modelo_copiando_vc_do_historico_nao_sobe_a_taxa(self):
        copiando = [f.replace("você", "vc").replace("hoje", "hj") for f in FALAS]
        taxa = _conta([abbreviate(f) for f in copiando], "vc") / len(FALAS)
        self.assertLess(taxa, 0.5, taxa)

    def test_maiuscula_e_palavra_inteira(self):
        self.assertIn(abbreviate("Você é tudo").split()[0], ("Você", "Vc"))
        self.assertEqual(abbreviate("vocês são o máximo, porquinho"), abbreviate("vocês são o máximo, porquinho"))
        self.assertIn("porquinho", abbreviate("vocês são o máximo, porquinho"))
        self.assertIn("[FOTO]", abbreviate("[FOTO] olha que você vai gostar"))

    def test_nao_no_fim_da_frase_fica(self):
        for i in range(50):
            self.assertTrue(abbreviate(f"né não ({i})").startswith("né não"))


if __name__ == "__main__":
    unittest.main()
