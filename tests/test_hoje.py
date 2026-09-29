import unittest
from datetime import datetime

from hoje import curto, dia_de, passado, _foi, _periodo


def ev(tipo, summary, title="", at="2026-09-26T12:00:00", end=None, key="k"):
    return {"event_type": tipo, "summary": summary, "title": title, "event_at": at, "end_at": end, "event_key": key}


class TextoCurtoTest(unittest.TestCase):
    """26/09 (Patrick): linha do tempo Hoje em linha de painel, sem texto interno do mundo."""

    def test_conversa_separa_assunto(self):
        c = curto(ev("social_contact", "Trocou mensagens com o pai; assunto: saudade dela."))
        self.assertEqual((c["ic"], c["texto"], c["sub"]), ("message-dots", "Trocou mensagens com o pai", "Assunto: saudade dela"))

    def test_encontro_sem_lugar_entre_parenteses(self):
        c = curto(ev("social_contact", "Encontrou a Carol (Bodytech São Clemente); assunto: alimentação."))
        self.assertEqual(c["texto"], "Encontrou a Carol")

    def test_consumo_vira_item_com_valor(self):
        c = curto(ev("consumo", "Pediu um gin tônica no Quartinho Bar (R$ 34)."))
        self.assertEqual((c["texto"], c["valor"]), ("Pediu um gin tônica", 34))

    def test_banho_com_fim(self):
        c = curto(ev("routine", "Tomou banho e lavou o cabelo (17:10–17:40).", at="2026-09-26T17:10:00"))
        self.assertEqual(c["texto"], "Tomou banho e lavou o cabelo")
        self.assertEqual(c["fim"], datetime(2026, 9, 26, 17, 40))

    def test_refeicao_curta(self):
        c = curto(ev("meal", "Almoço em casa: um poke pedido no iFood."))
        self.assertEqual((c["texto"], c["sub"]), ("Almoçou", "Poke do iFood"))

    def test_presente_do_patrick_em_voce(self):
        c = curto(ev("meal", "O Patrick mandou de surpresa Cappuccino do Rei do Mate pelo app; ela recebeu e foi comer."))
        self.assertEqual((c["texto"], c["sub"]), ("Comeu o Rei do Mate que você mandou", "Cappuccino"))

    def test_conheceu_so_o_nome(self):
        c = curto(ev("social_contact", "Conheceu a Gabi, tutora da spitz que brinca com o Milo (Enseada); assunto: o bairro."))
        self.assertEqual(c["texto"], "Conheceu a Gabi")

    def test_xixi_do_milo_vira_calcada(self):
        c = curto(ev("routine", "Desceu rapidinho com o Milo pro xixi da manhã.", title="Milo"))
        self.assertEqual((c["texto"], c["filhos"]), ("Foi pra calçada", [{"texto": "Necessidades do Milo"}]))

    def test_bloco_em_casa_usa_o_titulo(self):
        c = curto(ev("tempo_livre", "Ficou olhando o Instagram no quarto.", title="Olhando o Instagram"))
        self.assertEqual((c["ic"], c["texto"]), ("brand-instagram", "Olhou o Instagram"))

    def test_pix_na_voz_do_painel(self):
        c = curto(ev("money", "O Patrick fez um pix de R$ 300 pra ela de presente."))
        self.assertEqual((c["texto"], c["sub"], c["valor"]), ("Você fez um Pix pra ela", "De presente", 300))

    def test_acao_na_linha_detalhe_embaixo(self):
        """26/09 (Patrick): a ação na linha, a descrição curta menor e cinza embaixo, o valor na coluna."""
        casos = (
            (ev("gift", "Mandou Cappuccino do Rei do Mate pro Patrick pelo app de surpresa (R$ 18)."),
             ("Mandou um presente pra você", "Cappuccino do Rei do Mate", 18)),
            (ev("midia", 'Ouviu "Espresso" (Sabrina Carpenter), que o Patrick mandou: curtiu e botou na playlist dela.'),
             ("Ouviu a música que você mandou", '"Espresso", Sabrina Carpenter, curtiu', None)),
            (ev("consumo", "Cabelo na Ophicina: repicado (o Patrick escolheu) e escova · R$ 220."),
             ("Fez o cabelo", "Repicado e escova, você escolheu", 220)),
            (ev("consumo", "Fez as unhas em gel (mão e pé) na Ophicina do Cabelo: vermelho (R$ 180)."),
             ("Fez as unhas", "Gel, vermelho", 180)),
            (ev("tempo_livre", "Fez as unhas em casa, esmalte nude rosado.", title="Fez as unhas em casa"),
             ("Fez as unhas", "Esmalte nude rosado", None)),
            (ev("routine", "Trabalhou no seminário de Moda e Cultura (entrega 02/10), rendendo bem.", title="faculdade"),
             ("Trabalhou no seminário de Moda e Cultura", "Entrega 02/10, rendendo bem", None)),
            (ev("commute", "No caminho (ida, ônibus): ônibus veio lotado."), ("Ônibus veio lotado", "", None)),
            (ev("routine", "Desistiu de sair pro Starbucks: começou a chover.", title="agenda reativa"),
             ("Desistiu de sair pro Starbucks", "Começou a chover", None)),
        )
        for e, (texto, sub, valor) in casos:
            c = curto(e)
            self.assertEqual((c["texto"], c["sub"], c["valor"]), (texto, sub, valor), e["summary"])

    def test_sem_ponto_separador_e_atraso_em_amarelo(self):
        """28/09 (Patrick): atraso em amarelo na linha, embaixo o porquê enxuto; nada de "·" no Hoje."""
        c = curto(ev("routine", "Chegou 15 min atrasada na aula de Ergodesign — perdeu o despertador e o ônibus demorou.",
                     title="atraso"))
        self.assertEqual((c["texto"], c["sub"], c["aviso"]),
                         ("Chegou 15 min atrasada", "Ergodesign, perdeu o despertador, o ônibus demorou", True))
        c = curto(ev("routine", "Chegou 10 min atrasada no Quartinho Bar.", title="atraso"))
        self.assertEqual((c["texto"], c["sub"], c["aviso"]), ("Chegou 10 min atrasada", "", True))
        r = curto({"event_type": "agenda", "title": "agenda",
                   "summary": "Remarcou pra domingo às 18:00: Saindo com a Bia no Quartinho Bar (chovendo)."})
        self.assertEqual((r["texto"], r["sub"]), ("Remarcou", "Quartinho Bar, pra domingo 18:00"))
        p = curto(ev("routine", "Se pesou na academia: 54,4 kg."))
        self.assertEqual((p["texto"], p["sub"]), ("Se pesou", "54,4 kg"))

    def test_motivo_da_saida(self):
        self.assertEqual(curto(ev("routine", "Deu vontade e foi: café no Starbucks (tarde livre).", title="vontade"))["motivo"],
                         "Resolveu sair, tarde livre")
        self.assertEqual(curto(ev("routine", "O Patrick convenceu e ela saiu pra academia.", title="agenda reativa"))["motivo"],
                         "Você convenceu")


class RevisaoTest(unittest.TestCase):
    """26/09 (Patrick): textos crus do mundo em linha de painel."""

    def test_masturbacao_em_casa(self):
        c = curto(ev("routine", "Com tesão, se masturbou no quarto pensando no Patrick. Guardou só pra ela: não conta pro Patrick.",
                     title="sozinha"))
        self.assertEqual((c["ic"], c["texto"], c["sub"]), ("masturbacao", "Se masturbou no quarto", "Pensando em você"))

    def test_masturbacao_chamando_ele(self):
        c = curto(ev("routine", "Com tesão e querendo o Patrick, se masturbou no quarto e chamou ele pra entrar no clima junto (sexting)."))
        self.assertEqual((c["texto"], c["sub"]), ("Se masturbou no quarto", "Chamou você pra entrar no clima"))

    def test_tesao_fora_de_casa(self):
        c = curto(ev("routine", "Bateu um tesão que não dava pra segurar: se trancou no banheiro do bar e se tocou pensando no Patrick."))
        self.assertEqual((c["texto"], c["sub"]), ("Se masturbou no banheiro do bar", "Tesão muito alto"))

    def test_antes_de_dormir(self):
        c = curto(ev("routine", "Antes de dormir, com tesão e pensando no Patrick, se masturbou. Guardou só pra ela: não conta pro Patrick."))
        self.assertEqual(c["texto"], "Se masturbou antes de dormir")

    def test_casa_milo(self):
        self.assertEqual((curto(ev("routine", "Cuidou da bagunça dela: trocou a roupa de cama."))["texto"],
                          curto(ev("routine", "Cuidou da bagunça dela: trocou a roupa de cama."))["sub"]),
                         ("Arrumou a casa", "Trocou a roupa de cama"))
        c = curto(ev("routine", "O Milo fez xixi no tapete do banheiro.", title="Milo"))
        self.assertEqual((c["texto"], c["sub"]), ("Arte do Milo", "Fez xixi no tapete do banheiro"))
        c = curto(ev("routine", "Pagou o passeador pra levar o Milo hoje — dia puxado.", title="Milo"))
        self.assertEqual((c["texto"], c["sub"]), ("Pagou o passeador do Milo", "Dia puxado"))


class PassadoTest(unittest.TestCase):
    def test_gerundio_vira_passado(self):
        for antes, depois in (("Olhando o Instagram", "Olhou o Instagram"), ("Ouvindo Dua Lipa", "Ouviu Dua Lipa"),
                              ("Vendo o desfile da Chanel", "Viu o desfile da Chanel"), ("Lendo Duna", "Leu Duna"),
                              ("Fazendo as unhas", "Fez as unhas"), ("Tomando sol", "Tomou sol"),
                              ("Se maquiando", "Se maquiou"), ("Deitada à toa", "Ficou à toa"), ("Beliscou pipoca", "Beliscou pipoca")):
            self.assertEqual(passado(antes), depois)

    def test_icones_dos_blocos(self):
        from hoje import _ic_midia
        for texto, ic in (("Olhando o X", "brand-x"), ("Olhando o TikTok", "brand-tiktok"), ("Desenhando croqui", "pencil"),
                          ("Arrumando o quarto", "home-check"), ("Brincando com o Milo", "dog"),
                          ("Regando as plantas", "plant"), ("Tomando sol", "sun"), ("Deitada à toa", "sofa"),
                          ("Organizando o closet", "hanger")):
            self.assertEqual(_ic_midia(texto), ic, texto)

    def test_saida_no_passado(self):
        self.assertEqual(_foi("No Quartinho"), "Foi pro Quartinho")
        self.assertEqual(_foi("Na academia"), "Foi pra academia")

    def test_convite(self):
        c = curto(ev("social_invite", "A Bia te chamou: Saindo com a Bia no Quartinho Bar (hoje às 21:00)."))
        self.assertEqual(c["texto"], "A Bia chamou pro Quartinho Bar")
        c = curto(ev("social_invite", "Topou o convite: Saindo com a Bia no Quartinho Bar."))
        self.assertEqual(c["texto"], "Topou ir pro Quartinho Bar")


class DiaTest(unittest.TestCase):
    def test_madrugada_e_de_ontem(self):
        self.assertEqual(dia_de(datetime(2026, 9, 27, 1, 30)).day, 26)

    def test_periodos(self):
        d = datetime(2026, 9, 26).date()
        self.assertEqual(_periodo(datetime(2026, 9, 26, 9), d), "Manhã")
        self.assertEqual(_periodo(datetime(2026, 9, 26, 13), d), "Tarde")
        self.assertEqual(_periodo(datetime(2026, 9, 27, 1), d), "Noite")


if __name__ == "__main__":
    unittest.main()
