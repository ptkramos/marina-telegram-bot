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
        # 25/09: o balão também quebra dentro da frase; o emoji continua fechando a batida.
        falas = {
            "Bom dia, amor 😘 Bom trabalho pra você, vai com calma e se cuida.": ("😘", "Bom trabalho"),
            "Kkkkk beleza nada, amor, aula de Cristianismo é teste de resistência 😭 Mas tô sobrevivendo aqui.":
                ("😭", "Mas tô sobrevivendo"),
        }
        for fala, (fim, comeco) in falas.items():
            with self.subTest(fala=fala):
                baloes = segment(fala, self.policy)
                i = next(i for i, b in enumerate(baloes) if b.endswith(fim))
                self.assertTrue(baloes[i + 1].startswith(comeco), baloes)

    def test_emoji_no_fim_nao_quebra_nada(self):
        fala = "Tô na PUC ainda, amor, na aula até as 15h 😘"
        self.assertEqual(segment(fala, self.policy), [fala])

    def test_balao_com_emoji_sozinho_junta_na_fala(self):
        fala = "Fico feliz que ajudou, amor. Você não precisa passar por isso sozinho, tá?\n🖤"
        baloes = segment(fala, self.policy)
        self.assertTrue(all(any(c.isalpha() for c in b) for b in baloes), baloes)

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

    def test_corte_cai_em_pedaco_de_pensamento(self):
        """25/09: pode quebrar dentro da frase, mas em vírgula/conjunção, nunca no meio de palavra
        nem deixando vírgula pendurada no fim do balão."""
        fala = "Tô na PUC, amor, na aula de O Cristianismo. Vai até às 15h, então tô aqui firme ainda."
        baloes = segment(fala, self.policy)
        self.assertGreater(len(baloes), 1)
        self.assertTrue(all(not b.endswith(",") and len(b) >= 10 for b in baloes), baloes)
        tira = lambda t: t.replace(",", "").replace(".", "")      # 26/09: ponto entre frases vira corte
        self.assertEqual(tira(" ".join(baloes)).split(), tira(fala).split())

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
        self.assertGreaterEqual(len(contagens), 2, "o número de balões varia entre falas")
        self.assertNotEqual(contagens, {2}, "não pode sair sempre em exatamente dois")


class PedacoDePensamentoTests(unittest.TestCase):
    """25/09 (Patrick, prints de casais no WhatsApp): ~23 caracteres por balão e
    a continuação da frase no balão de baixo ("tão confortável", "ou início de manhã")."""

    def setUp(self):
        self.policy = select_policy("oi amor")

    def test_fala_comprida_vira_pedacos_curtos(self):
        fala = ("Tô aqui jogada, com o cabelo todo bagunçado no travesseiro e a bochecha vermelha de tanto "
                "que você me fez suspirar... A culpa é todinha sua que eu tô nesse estado mole, sabia?")
        baloes = segment(fala, self.policy)
        self.assertGreaterEqual(len(baloes), 3)
        self.assertTrue(all(len(b) <= 80 for b in baloes), baloes)

    def test_risada_na_frente_sai_sozinha(self):
        baloes = segment("Kkkk nem vem! Você ia rir da minha cara de destruída", self.policy)
        self.assertEqual(baloes[0], "Kkkk")

    def test_nao_separa_o_complemento_do_verbo(self):
        fala = "Fode mais rápido, por favor... me bate gostoso com o quadril até eu gozar todinha no seu pau!"
        self.assertFalse(any(b.startswith("com o quadril") for b in segment(fala, self.policy)))


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


class PontoNoMeioTests(unittest.TestCase):
    """26/09 (Patrick): "Meu dia começou perfeito, seu lindo. Te amo demais" saiu num balão só."""

    def setUp(self):
        self.policy = select_policy("oi amor")

    def test_ponto_entre_frases_vira_balao(self):
        self.assertEqual(segment("Meu dia começou perfeito, seu lindo. Te amo demais", self.policy),
                         ["Meu dia começou perfeito, seu lindo", "Te amo demais"])

    def test_pedaco_curto_vira_virgula(self):
        self.assertEqual(segment("Ah. Tá bom então", self.policy), ["Ah, tá bom então"])

    def test_nao_mexe_no_que_nao_e_fim_de_frase(self):
        for fala in ("Falei com o Dr. Paulo hoje", "Hmm... sei lá", "Custou R$ 1.500 viu", "Oi amor! Tudo bem?"):
            with self.subTest(fala=fala):
                self.assertEqual(segment(fala, self.policy), [fala])

    def test_nenhum_balao_com_ponto_no_meio(self):
        fala = "Aaaaah amor 😭\nTô comendo agora e vc me mandou cappuccino de surpresa???\nMeu dia começou perfeito. Te amo demais"
        for b in segment(fala, self.policy):
            self.assertNotRegex(b, r"\w\.\s+\w", b)
