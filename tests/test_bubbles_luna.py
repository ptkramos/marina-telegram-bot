"""Distribuição de balões com o GPT-5.6 Luna (soak 22/09).

Ele escreve tudo corrido e separa batidas com emoji: em 101 respostas, 89 vinham
sem nenhuma quebra de linha e 24 usavam emoji como divisor. Resultado no
Telegram: quase tudo em um balão só, nada parecido com conversa de WhatsApp.
"""
import unittest

import bot
from response_rhythm import segment, select_policy


class EmojiBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.policy = select_policy("oi amor")

    def test_emoji_separa_duas_batidas(self):
        falas = {
            "Bom dia, amor 😘 Bom trabalho pra você, vai com calma e se cuida.":
                ["Bom dia, amor 😘", "Bom trabalho pra você, vai com calma e se cuida."],
            "Kkkkk beleza nada, amor, aula de Cristianismo é teste de resistência 😭 Mas tô sobrevivendo aqui.":
                ["Kkkkk beleza nada, amor, aula de Cristianismo é teste de resistência 😭",
                 "Mas tô sobrevivendo aqui."],
        }
        for fala, esperado in falas.items():
            with self.subTest(fala=fala):
                self.assertEqual(segment(fala, self.policy), esperado)

    def test_emoji_no_fim_nao_quebra_nada(self):
        fala = "Tô na PUC ainda, amor, na aula até as 15h 😘"
        self.assertEqual(segment(fala, self.policy), [fala])

    def test_balao_com_emoji_sozinho_junta_na_fala(self):
        fala = "Fico feliz que ajudou, amor. Você não precisa passar por isso sozinho, tá?\n🖤"
        self.assertEqual(len(segment(fala, self.policy)), 1)

    def test_emoji_depois_da_pergunta_fica_com_a_pergunta(self):
        """Soak: "…agora? 🤨" virava dois balões, o segundo só com o emoji."""
        for fala in ("KKKKK meu amigo da PUC, amor. Tá com ciúme do Theo agora? 🤨",
                     "Eita, Paris do nada? Kkkkk eu toparia, mas tu tá falando sério? 😌 "):
            with self.subTest(fala=fala):
                baloes = segment(fala, self.policy)
                self.assertTrue(all(len(b.strip()) > 3 for b in baloes), baloes)
                self.assertTrue(baloes[-1].rstrip().endswith(("🤨", "😌")))


class CasualTwoBeatsTests(unittest.TestCase):
    def setUp(self):
        self.policy = select_policy("oi amor")

    def test_quando_quebra_o_corte_cai_entre_as_frases(self):
        """A quebra varia por fala, mas nunca pica uma frase no meio."""
        fala = "Tô na PUC, amor, na aula de O Cristianismo. Vai até às 15h, então tô aqui firme ainda."
        frases = ["Tô na PUC, amor, na aula de O Cristianismo.", "Vai até às 15h, então tô aqui firme ainda."]
        self.assertIn(segment(fala, self.policy), ([fala], frases))

    def test_fala_curta_continua_num_balao(self):
        self.assertEqual(segment("Oi amor! Tudo bem?", self.policy), ["Oi amor! Tudo bem?"])

    def test_decisao_e_estavel_para_a_mesma_fala(self):
        fala = "Comi uma saladinha com frango aqui em casa. Tava sem pique de cozinhar nada elaborado hoje."
        primeiro = segment(fala, self.policy)
        for _ in range(5):
            self.assertEqual(segment(fala, self.policy), primeiro)

    def test_nem_toda_fala_longa_quebra(self):
        """Gente não quebra sempre: a variação é determinística por fala."""
        falas = [
            "Acabei de sair da facul, amor. Tô morta, quero só deitar e não fazer mais nada hoje.",
            "Comi uma saladinha com frango aqui em casa. Tava sem pique de cozinhar nada elaborado hoje.",
            "Falei com a Bia ontem, ela tá naquela vibe de sempre. Depois te conto o babado direitinho.",
            "Tô indo pra academia agora, amor. Volto em uma hora e meia, no máximo duas.",
            "Hoje foi corrido na PUC, tive três aulas seguidas. Agora só quero um banho e a minha cama.",
            "Vou ver o jogo aqui em casa, amor. Se o Fogão ganhar eu vou gritar tanto que o vizinho reclama.",
        ]
        contagens = {len(segment(f, self.policy)) for f in falas}
        self.assertEqual(contagens, {1, 2}, "esperado misturar um e dois balões entre falas longas")


class TrailingGibberishTests(unittest.TestCase):
    """Luna colou palavra solta no fim de falas já terminadas (finish=stop)."""

    def test_palavra_solta_no_fim_e_removida(self):
        casos = {
            "Poxa, amor, plantão amanhã é puxado 🫠\nVai com calma hoje e tenta descansar, tá? extrair?":
                "Vai com calma hoje e tenta descansar, tá?",
            "Poxa, amor, plantão amanhã é puxado mesmo 🫠\nComo vai ser o turno? Baebele":
                "Como vai ser o turno?",
        }
        for fala, fim in casos.items():
            with self.subTest(fala=fala):
                self.assertTrue(bot.limpar_fala_marina(fala).endswith(fim))

    def test_fechamentos_legitimos_ficam(self):
        for fala in ("Tô com saudade. Vem me ver hoje? kkkk",
                     "Adoro quando você faz isso. Sério?",
                     "Te amo. Muito, amor",
                     "Vou tomar banho. Já volto, tá?"):
            with self.subTest(fala=fala):
                self.assertEqual(bot.limpar_fala_marina(fala), fala)


if __name__ == "__main__":
    unittest.main()
