"""Catálogo de textos, lote 1 (01/10): Hoje e card do Agora com os textos decididos pelo Patrick.
Só a tela muda; o mundo grava o mesmo texto."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import hoje
from agenda import Agenda, celular_tela, duracao, futuro, por_volta
from hoje import curto


def ev(tipo, summary, title="", at="2026-09-30T12:00:00", end=None, key="k"):
    return {"event_type": tipo, "summary": summary, "title": title, "event_at": at, "end_at": end, "event_key": key}


class RegrasGeraisTest(unittest.TestCase):
    def test_por_volta_e_duracao_por_extenso(self):
        self.assertEqual(por_volta(datetime(2026, 9, 30, 9, 28)), "por volta das 09:30")
        self.assertEqual(duracao(timedelta(minutes=1)), "1 minuto")
        self.assertEqual(duracao(timedelta(minutes=80)), "1 hora e 20 minutos")
        self.assertEqual(duracao(timedelta(minutes=121)), "2 horas e 1 minuto")

    def test_o_que_vem_em_casa_fica_no_futuro(self):
        for antes, depois in (("Vendo série", "Vai ver série"), ("Dormindo", "Vai dormir"), ("Comendo", "Vai comer"),
                              ("Se arrumando", "Vai se arrumar"), ("Olhando o Instagram", "Vai olhar o Instagram"),
                              ("Indo dormir", "Vai dormir"), ("No Quartinho", "No Quartinho")):
            self.assertEqual(futuro(antes), depois)

    def test_celular_na_tela_e_interno_no_bot(self):
        self.assertEqual(celular_tela("Olha com frequência"), "Na mão")
        self.assertEqual(celular_tela("Olha depois do filme"), "Na bolsa, silenciado")
        import webapp_server
        self.assertEqual(webapp_server.CELULAR_POR_ATIVIDADE["COMMUTE"], "Olha com frequência")   # o bot compara este

    def test_nome_do_lugar_sem_marca_do_banco(self):
        self.assertEqual(Agenda._pra("Agência boutique da Lívia (fictícia)"), "para a Agência boutique da Lívia")
        self.assertEqual(Agenda._pra("Quartinho Bar"), "para o Quartinho Bar")

    def test_o_patrick_nunca_voce(self):
        for s in ("O Patrick fez um pix de R$ 300 pra ela de presente.",
                  "Usou o pix do Patrick: comprou um açaí (R$ 20)."):
            c = curto(ev("money", s))
            self.assertNotIn("você", (c["texto"] + c["sub"]).lower())
            self.assertIn("Patrick", c["texto"])


class AninhadoTest(unittest.TestCase):
    def test_ifood_do_patrick_um_item_por_linha(self):
        c = curto(ev("gift", "O Patrick mandou Suco de laranja 500 ml e Açaí 300 ml do Megamatte pelo app; ela recebeu "
                             "e guardou pra depois, porque tinha acabado de comer."))
        self.assertEqual((c["texto"], c["sub"]), ("O Patrick mandou um iFood", "De Megamatte"))
        self.assertEqual([f["texto"] for f in c["filhos"]], ["Suco de laranja 500 ml", "Açaí 300 ml"])
        c = curto(ev("meal", "O Patrick mandou de surpresa Cappuccino e 2x Pão de queijo 4 un do Rei do Mate pelo app; "
                             "ela recebeu e foi comer.", end="2026-09-30T12:20:00"))
        self.assertEqual([f["texto"] for f in c["filhos"]], ["Cappuccino", "2x Pão de queijo 4 un"])

    def test_faltou_o_dia_com_as_aulas_em_amarelo(self):
        nomes = ("Acessórios de Moda e Extensões do Corpo e Conteúdos Estruturantes: Projetar para a Sociedade e "
                 "Projeto: Projetar em Sociedade")

        class Db:
            def get_connection(self):
                import sqlite3
                conn = sqlite3.connect(":memory:")
                conn.execute("CREATE TABLE academic_courses (display_name TEXT)")
                conn.executemany("INSERT INTO academic_courses VALUES (?)", [
                    ("Acessórios de Moda e Extensões do Corpo",), ("Conteúdos Estruturantes: Projetar para a Sociedade",),
                    ("Projeto: Projetar em Sociedade",), ("Desenho Técnico",)])
                return conn

        c = curto(ev("routine", f"Faltou a aula hoje ({nomes}): cólica forte, ficou em casa.", title="faculdade"), Db())
        self.assertEqual(c["texto"], "Faltou a facul hoje, cólica forte, ficou em casa")
        self.assertEqual([(f["texto"], f["aviso"]) for f in c["filhos"]],
                         [("Acessórios de Moda e Extensões do Corpo", True),
                          ("Conteúdos Estruturantes: Projetar para a Sociedade", True),
                          ("Projeto: Projetar em Sociedade", True)])

    def test_faltou_uma_aula(self):
        c = curto({"event_type": "agenda", "title": "agenda",
                   "summary": "Faltou a aula de hoje (Moda e Corpo): dormiu mal. Vai pegar a matéria com a Júlia depois."})
        self.assertEqual((c["texto"], c["sub"]), ("Faltou a aula, dormiu mal", "Moda e Corpo"))


class EnquantoAconteceTest(unittest.TestCase):
    def _view(self, eventos, now, fins=None):
        with patch.object(hoje, "_saidas", return_value=[]), patch.object(hoje, "_eventos", return_value=eventos), \
                patch.object(hoje, "_blocos", return_value=fins or {}), patch.object(hoje, "_previstos", return_value=[]):
            return hoje.hoje_view(None, now)

    def test_banho_com_cabelo_no_gerundio_e_depois_no_passado(self):
        e = ev("routine", "Tomou banho e lavou o cabelo (17:10–17:40).", at="2026-09-30T17:10:00", key="banho:x")
        agora = self._view([e], datetime(2026, 9, 30, 17, 20))["periodos"][0]["itens"][-1]
        self.assertEqual((agora["texto"], [f["texto"] for f in agora["filhos"]]), ("Tomando banho", ["Lavando o cabelo"]))
        depois = self._view([e], datetime(2026, 9, 30, 18, 0))["periodos"][0]["itens"][-1]
        self.assertEqual((depois["texto"], [f["texto"] for f in depois["filhos"]]), ("Tomou banho", ["Lavou o cabelo"]))

    def test_trabalho_da_facul(self):
        e = ev("routine", "Trabalhou no trabalho de Práticas Experimentais VI (entrega amanhã), focada.",
               title="faculdade", at="2026-09-30T19:56:00", end="2026-09-30T20:56:00", key="facul:sessao:x")
        it = self._view([e], datetime(2026, 9, 30, 20, 10))["periodos"][0]["itens"][-1]
        self.assertEqual((it["texto"], it["sub"]), ("Fazendo trabalho da facul para amanhã",
                                                    "Trabalho de Práticas Experimentais VI, focada"))
        it = self._view([e], datetime(2026, 9, 30, 21, 30))["periodos"][0]["itens"][-1]
        self.assertEqual(it["texto"], "Fez trabalho da facul para amanhã")

    def test_artistas_um_por_linha_enquanto_ouve(self):
        e = ev("tempo_livre", 'Ficou ouvindo a playlist dela no closet: "New Rules" (Dua Lipa), "VELUDO MARROM" (Liniker).',
               title="Ouvindo Dua Lipa", at="2026-09-30T20:00:00", key="livre:x")
        it = self._view([e], datetime(2026, 9, 30, 20, 10), {"livre:x": datetime(2026, 9, 30, 20, 40)})
        it = it["periodos"][0]["itens"][-1]
        self.assertEqual((it["texto"], it["sub"], [f["texto"] for f in it["filhos"]]),
                         ("Ouvindo a playlist dela", "", ["Dua Lipa", "Liniker"]))

    def test_masturbacao_fantasiando(self):
        e = ev("routine", "Com tesão, se masturbou no quarto pensando no Patrick. Guardou só pra ela.",
               title="sozinha", at="2026-09-30T23:00:00", end="2026-09-30T23:15:00", key="m:x")
        it = self._view([e], datetime(2026, 9, 30, 23, 5))["periodos"][0]["itens"][-1]
        self.assertEqual((it["texto"], it["sub"]), ("Se masturbando no quarto", "Fantasiando com o Patrick"))


class DecisaoTest(unittest.TestCase):
    def test_icone_da_desistencia_pelo_motivo(self):
        c = curto(ev("routine", "Desistiu de sair pro Starbucks: começou a chover.", title="agenda reativa"))
        self.assertEqual(c["ic"], "cloud-rain")
        c = curto({"event_type": "agenda", "title": "agenda", "summary": "Desistiu de treinar hoje (sem energia)."})
        self.assertEqual(c["ic"], "battery-1")

    def test_chamou_com_ele_ou_ela(self):
        c = curto({"event_type": "agenda", "title": "agenda",
                   "summary": "Chamou o Theo pra sair sexta, mas o Theo não podia"})
        self.assertEqual((c["texto"], c["sub"]), ("Chamou o Theo para sair", "Sexta, ele não pôde"))

    def test_casting_e_seu_jorge(self):
        c = curto(ev("work", "A Lívia da agência mandou um casting: vídeo pra uma marca de cosméticos."))
        self.assertEqual((c["texto"], c["sub"]), ("A Lívia enviou um Casting", "Participar do vídeo de uma marca de cosméticos"))
        c = curto(ev("work", "A Lívia da agência mandou um casting: campanha de moda praia."))
        self.assertEqual(c["sub"], "Participar da campanha de moda praia")
        c = curto(ev("routine", "O Seu Jorge contou uma fofoca do prédio quando ela passou pela portaria.", title="casa"))
        self.assertEqual((c["texto"], c["sub"]), ("Conversou com o Seu Jorge", "Contou uma fofoca do prédio"))

    def test_serie_e_leitura(self):
        c = curto(ev("routine", "Saiu episódio novo de One Piece hoje (temporada 23, ep. 1180).", title="tv"))
        self.assertEqual((c["texto"], c["sub"]), ("Viu que saiu episódio novo", "De One Piece, temporada 23, episódio 1180"))
        c = curto(ev("routine", "Viu episódios 1 a 2 de Paradise Kiss (começou essa semana: viu um edit no TikTok).",
                     title="tv"))
        self.assertEqual((c["texto"], c["sub"]), ("Assistiu Paradise Kiss", "Episódios 1 e 2"))
        c = curto(ev("midia", "Terminou de ler My Dress-Up Darling vol. 9."))
        self.assertEqual((c["texto"], c["sub"]), ("Terminou de ler My Dress-Up Darling", "Volume 9"))


if __name__ == "__main__":
    unittest.main()
