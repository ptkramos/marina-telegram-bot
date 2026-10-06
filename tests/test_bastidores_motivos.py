"""Redesenho dos Bastidores, passo 5 (06/10): os motivos na origem.

Decidido pelo Patrick no catálogo: o motivo é UMA FRASE inteira (quem fez + verbo no passado + o quê; coisa dela
sem sujeito; o que vem com "Tem"), sem "·" nem parênteses; o detalhe vai à parte, com ícone pelo tipo e a
preposição ("De R$ 200", "Sobre fofocas", "No Quartinho Bar"). O pai manda dinheiro como o Pix do Patrick; o
brinquedo é dito pelo nome. O prompt dela lê a frase com o detalhe emendado.
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

import bastidores_sentimentos as bs
import emotion
import lovense
from db import DatabaseManager
from emotion import DEFAULT_CAUSES, EmotionEngine, appraise_event, texto_motivo

T0 = datetime(2026, 10, 5, 22, 30)


def ev(key, tipo, summary, part="[]"):
    return [(c, tg) for _f, _k, _i, c, tg in appraise_event(
        {"event_key": key, "event_type": tipo, "summary": summary, "participants_json": part})]


def frase(r):
    return str(r[0]), r[0].detalhes


class CatalogoTests(unittest.TestCase):
    """Os casos do catálogo, com os resumos reais da produção."""

    def test_o_patrick_pelo_mundo(self):
        self.assertEqual(frase(ev("financas:2026-10-02T153436:pix", "money",
                                  "O Patrick fez um pix de R$ 1000 pra ela ('Pra gastar no shopping') de presente.")[0]),
                         ("O Patrick fez um Pix de presente",
                          (("valor", "De R$ 1000"), ("recado", "Pra gastar no shopping"))))
        dele, dela = ev("meal:2026-10-01:jantar:presente", "meal",
                        "O Patrick mandou Tigela Fit do Estação do Açaí pelo app; ela recebeu e foi comer.")
        self.assertEqual((frase(dele), dele[1]),
                         (("O Patrick mandou comida de surpresa", (("loja", "Da Estação do Açaí"),)), "o Patrick"))
        self.assertEqual(frase(dela), ("Chegou a comida surpresa", (("loja", "Da Estação do Açaí"),)))

    def test_pessoas(self):
        self.assertEqual(frase(ev("social:1", "social_contact", "Encontrou a Júlia (PUC-Rio); assunto: fotografia.",
                                  '["marina","julia_azevedo"]')[0]),
                         ("Encontrou a Júlia", (("lugar", "Na PUC-Rio"), ("assunto", "Sobre fotografia"))))
        self.assertEqual(frase(ev("social:2", "social_contact", "Trocou áudios com a Bia; assunto: conflitos leves.",
                                  '["marina","bia_andrade"]')[0]),
                         ("Se estranhou com a Bia", (("audio", "Por áudio"),)))
        # Patrick: o dinheiro do pai vem igual ao Pix de presente dele (o valor fica fora do saldo dela, não existe)
        self.assertEqual(frase(ev("social:3", "social_contact", "Trocou mensagens com o pai; assunto: mandou o dinheiro "
                                  "do mercado e da comida da semana, sem ela pedir.", '["marina","henrique_salles"]')[0]),
                         ("O pai fez um Pix sem ela pedir", (("pra", "Pro mercado e a comida da semana"),)))
        self.assertEqual(frase(ev("social:4", "social_contact", "Encontrou a Dona Célia (Apartamento da Marina); "
                                  "assunto: fofoca.", '["marina","celia_ribeiro"]')[0])[1][0], ("lugar", "Em casa"))

    def test_casa_rua_series(self):
        self.assertEqual(str(ev("milo:2026-10-01:arte", "routine", "O Milo ficou encarando ela até ganhar um petisco.")[0][0]),
                         "O Milo ficou encarando ela até ganhar um petisco", "não corta mais no meio")
        self.assertEqual(frase(ev("commute:2026-10-05:puc:volta:imprevisto", "commute", "No caminho (voltando da PUC, "
                                  "de metrô e ônibus): perdeu o ônibus da integração por um minuto.")[0]),
                         ("Perdeu o ônibus da integração por um minuto", (("caminho", "Voltando da PUC"),)))
        self.assertEqual(str(ev("banho:1", "routine", "Banho.")[0][0]), "Tomou um banho quentinho")
        self.assertEqual(frase(ev("tv:novo:1", "routine", "Saiu episódio novo de One Piece hoje (temporada 23, ep. 1180).")[0]),
                         ("Saiu episódio novo de One Piece", (("episodio", "Episódio 1180"),)))

    def test_faculdade_e_trabalho(self):
        self.assertEqual(frase(ev("falta:2026-09-30", "routine", "Faltou a aula hoje (Acessórios de Moda e Extensões do "
                                  "Corpo, Projeto: Projetar em Sociedade, Desenho Técnico): cólica forte, ficou em casa.")[0]),
                         ("Faltou às aulas de hoje", (("materia", "De Acessórios de Moda e Extensões do Corpo e mais 2"),)))
        self.assertEqual(frase(ev("atraso:commute:outing:1", "routine",
                                  "Chegou 22 min atrasada no Quartinho — tava empolgada e trocou de look.")[0]),
                         ("Chegou atrasada no Quartinho", (("atraso", "Com 22 minutos de atraso"),)))
        self.assertEqual(frase(ev("facul:sessao:2026-10-05", "routine", "Trabalhou na apresentação de Projeto: Projetar "
                                  "em Sociedade (entrega 07/10), enrolando um pouco.")[0]),
                         ("Enrolou na apresentação", (("materia", "De Projeto: Projetar em Sociedade"),)))
        self.assertEqual(frase(ev("freela:1:oferta", "work",
                                  "A Lívia da agência mandou um casting: campanha de uma marca de óculos.")[0]),
                         ("A Lívia mandou um casting", (("trabalho", "De campanha de uma marca de óculos"),)))
        self.assertEqual(frase(ev("freela:1:resultado", "work", "A Lívia avisou: não passou no casting (vídeo pra uma "
                                  "marca de cosméticos). Escolheram outra menina.")[0]),
                         ("Não passou no casting", (("trabalho", "De vídeo pra uma marca de cosméticos"),)))

    def test_padrao_vale_pra_tudo(self):
        for c in DEFAULT_CAUSES.values():
            self.assertTrue(c[:1].isupper(), c)
            self.assertNotIn("·", c)
        self.assertEqual(emotion._causa_do_planner("o Patrick elogiou ela · voz, sorriso e olhos"),
                         "O Patrick elogiou ela, voz, sorriso e olhos")
        self.assertEqual(emotion._causa_do_planner("o Patrick implicou com o vestido (quase pelada)"),
                         "O Patrick implicou com o vestido")


class PromptTests(unittest.TestCase):
    def test_o_prompt_le_a_frase_com_o_detalhe(self):
        self.assertEqual(texto_motivo("O Patrick fez um Pix de presente",
                                      (("valor", "De R$ 200"), ("recado", "Pra gastar no shopping"))),
                         'O Patrick fez um Pix de presente, de R$ 200, com o recado "Pra gastar no shopping"')
        self.assertEqual(texto_motivo("Trocou mensagens com a Bia"), "Trocou mensagens com a Bia")


class GuardaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "motivos.db")
        self.eng = EmotionEngine(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_o_detalhe_vai_pra_coluna_e_volta(self):
        causa = emotion._motivo("O Patrick fez um Pix de presente", ("valor", "De R$ 200"))
        self.eng.feel("afeto", "gratidao", 0.6, causa, T0 - timedelta(minutes=5), target="o Patrick")
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT cause, detalhe_json FROM emotion_episodes").fetchone()
        self.assertEqual((row["cause"], json.loads(row["detalhe_json"])),
                         ("O Patrick fez um Pix de presente", [["valor", "De R$ 200"]]))
        ep = self.eng.episodes(T0)[0]
        self.assertEqual((ep.detalhes, ep.texto),
                         ((("valor", "De R$ 200"),), "O Patrick fez um Pix de presente, de R$ 200"))
        self.assertIn("— O Patrick fez um Pix de presente, de R$ 200.", "\n".join(self.eng.prompt_lines(T0)))
        self.assertEqual(self.eng.day_log(T0 - timedelta(hours=1), T0)[0]["detalhes"], (("valor", "De R$ 200"),))

    def test_a_fusao_troca_o_detalhe_junto(self):
        self.eng.feel("afeto", "gratidao", 0.5, emotion._motivo("O Patrick fez um Pix", ("valor", "De R$ 50")),
                      T0 - timedelta(minutes=50), target="o Patrick")
        self.eng.feel("afeto", "gratidao", 0.5, emotion._motivo("O Patrick fez um Pix de presente"),
                      T0 - timedelta(minutes=10), target="o Patrick")
        eps = self.eng.episodes(T0)
        self.assertEqual([(e.cause, e.detalhes) for e in eps], [("O Patrick fez um Pix de presente", ())])

    def test_texto_solto_continua_valendo(self):
        self.eng.feel("alegria", "alivio", 0.3, "Chegou o Lovense que o Patrick encomendou", T0 - timedelta(minutes=5))
        self.assertEqual(self.eng.episodes(T0)[0].detalhes, ())

    def test_sentindo_agora_manda_o_icone(self):
        self.eng.feel("alegria", "diversao", 0.5, emotion._motivo("Trocou mensagens com a Bia", ("assunto", "Sobre fofocas")),
                      T0 - timedelta(minutes=5), target="a Bia")
        bia = next(p for p in bs.sentindo(self.db, T0) if p["chave"] == "a Bia")
        s = bia["sentimentos"][0]
        self.assertEqual((s["motivo"], s["detalhes"]),
                         ("Trocou mensagens com a Bia", [{"icone": "message-circle", "texto": "Sobre fofocas"}]))

    def test_entrega_e_casting_pelo_dia_da_semana(self):
        # o episódio nasce uma vez e fica: "amanhã" de ontem à noite virava mentira de manhã
        self.assertEqual(emotion._no_dia(date(2026, 10, 7)), "na quarta")
        self.assertEqual(emotion._no_dia(date(2026, 10, 10)), "no sábado")
        self.assertEqual(emotion._entregou("apresentação"), "Entregou a apresentação")
        self.assertEqual(emotion._entregou("entrega final"), "Fez a entrega final")


class LovenseTests(unittest.TestCase):
    def test_o_brinquedo_pelo_nome(self):
        self.assertEqual(lovense._quais(["lush"]), "o Lush")
        self.assertEqual(lovense._quais(["lush", "hush"]), "o Lush e o Hush")
        self.assertEqual(lovense._quais(["lush"], "no"), "no Lush")
        self.assertEqual(lovense._quais([]), "o brinquedo")

    def test_raiva_do_brinquedo_nao_vira_briga(self):
        # antes o filtro achava "brinquedo" na causa; agora o nome vem no lugar e a pressão do Hush segue contando
        dentro = lambda c: any(t in c for t in lovense.CAUSA_DO_BRINQUEDO)
        self.assertTrue(dentro("O Patrick exagerou no Lush"))
        self.assertTrue(dentro("O Patrick sumiu do app com o Lush nela"))
        self.assertFalse(dentro("O Patrick insistiu no Hush depois do não dela"))
        self.assertFalse(dentro("O Patrick foi grosso com ela"))


if __name__ == "__main__":
    unittest.main()
