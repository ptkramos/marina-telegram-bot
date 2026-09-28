"""Bastidores com texto de gente (Patrick, 26/09): voz híbrida — rótulos e dados falam como
painel ("você"), o que é sentimento fala do jeito dela. Nada de código cru, emoji ou 3ª pessoa."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import webapp_server as w
from db import DatabaseManager

SNAP = {"local": "Apartamento da Marina (Botafogo)", "atividade": "dormindo",
        "disponivel": "Dormindo 🌙 (responde quando acordar)", "ciclo_dia": 24, "ciclo_fase": "fase pré-menstrual / tpm",
        "saude": [("gripe", "chá e dipirona")], "proximo": ("aula de Projeto", "segunda 14:00"),
        "planos": [("bar com o Theo", "sábado 20:30")]}


class StatusTest(unittest.TestCase):
    def test_status_em_frase_de_gente(self):
        s = w.status_view(SNAP)
        self.assertEqual(s["atividade"], "Dormindo")
        self.assertEqual(s["local"], "Em casa · Botafogo")
        self.assertEqual(s["celular"], "Olha quando acordar")
        self.assertTrue(s["dormindo"])
        self.assertEqual(s["ciclo"], "Dia 24 · TPM")
        self.assertEqual(s["saude"], ["Gripe · chá e dipirona"])
        self.assertEqual(s["proximo"], "Aula de Projeto, segunda 14h")
        self.assertEqual(s["planos"], ["Bar com o Theo, sábado 20h30"])

    def test_lugar_fora_de_casa(self):
        self.assertEqual(w.status_view({**SNAP, "local": "PUC-Rio (Gávea)"})["local"], "PUC-Rio · Gávea")


class EmocaoTest(unittest.TestCase):
    PANEL = {"body": [{"label": "Energia", "value": 0.3, "word": "exausta"}], "in_the_mood": True,
             "hours_since_release": 30.2, "hours_slept": 8.66, "awake_since": "2026-09-26 09:05:00",
             "discomfort_why": "cólica", "mood": "normal, nem lá nem cá", "mood_bars": [], "bond": [],
             "feelings": [{"word": "com saudade", "target": "o Patrick", "value": 0.5, "cause": "O Patrick fez um pix pra ela",
                           "count": 3, "until_resolved": False},
                          {"word": "grata", "target": "a Bia", "value": 0.4, "cause": "A Bia elogiou o look · Instagram", "count": 1,
                           "until_resolved": False}]}

    def test_dormindo_nao_aparece_exausta(self):
        e = w.emocao_view(self.PANEL, dormindo=True)
        self.assertEqual(e["body"][0]["word"], "Dormindo")
        self.assertIn(["moon", "Sono", "Dormindo agora"], e["linhas"])
        self.assertEqual(self.PANEL["body"][0]["word"], "exausta", "não altera o painel original")

    def test_linhas_rotuladas(self):
        # 28/09 (Patrick): palavras com maiúscula em toda a aba
        e = w.emocao_view(self.PANEL, dormindo=False)
        self.assertEqual(e["body"][0]["word"], "Exausta")
        self.assertIn(["moon", "Sono", "Dormiu 8h40 · acordou às 9h05"], e["linhas"])
        self.assertIn(["heartbeat", "Último orgasmo", "Há 30 h"], e["linhas"])
        self.assertIn(["bandage", "Desconforto", "Cólica"], e["linhas"])
        self.assertEqual(e["humor"], "Normal, nem lá nem cá")

    def test_ciclo_e_desconforto_sem_repetir_a_fase(self):
        # 28/09 (Patrick): "Dia 27 de 28 · TPM" no Corpo; o desconforto perde o "da TPM"
        s = w.status_view({**SNAP, "ciclo_dia": 27, "ciclo_len": 28})
        self.assertEqual((s["ciclo"], s["ciclo_fase"]), ("Dia 27 de 28 · TPM", "TPM"))
        e = w.emocao_view({**self.PANEL, "discomfort_why": "inchada da TPM"}, False, ciclo=s["ciclo"], fase="TPM")
        self.assertEqual([l[1] for l in e["linhas"]], ["Sono", "Ciclo", "Último orgasmo", "Desconforto"])
        self.assertIn(["bandage", "Desconforto", "Inchada"], e["linhas"])
        e = w.emocao_view({**self.PANEL, "discomfort_why": "menstruada, corpo meio dolorido"}, False,
                          ciclo="Dia 2 de 28 · Menstruada", fase="Menstruada")
        self.assertIn(["bandage", "Desconforto", "Corpo meio dolorido"], e["linhas"])

    def test_sentindo_agora_diz_quando(self):
        at = datetime(2026, 9, 27, 22, 1)
        panel = {**self.PANEL, "feelings": [{**self.PANEL["feelings"][0], "at": at}]}
        s = w.emocao_view(panel, False, datetime(2026, 9, 28, 5, 55))["sentindo"]
        self.assertEqual(s[0]["quando"], "ontem, 22h01")

    def test_motivo_fato_curto_e_detalhe_ao_lado(self):
        # 28/09 (Patrick): um padrão só — fato curto em voz de painel, detalhe ao lado; os antigos passam pelo molde
        m = lambda c, t="": w.motivo_tela(c, t)
        self.assertEqual(m("o Patrick mandou comida · surpresa", "o Patrick"), {"motivo": "Você mandou comida", "detalhe": "surpresa"})
        self.assertEqual(m("Viu Paradise Kiss · eps 1 e 2"), {"motivo": "Viu Paradise Kiss", "detalhe": "eps 1 e 2"})
        self.assertEqual(m("Trocou mensagens com a Bia; assunto: conflitos leves"),   # antigo, pelo molde novo
                         {"motivo": "Se estranhou com a Bia", "detalhe": "por mensagem"})
        self.assertEqual(m("banho quentinho, se sentiu gente de novo"), {"motivo": "Banho quentinho", "detalhe": ""})
        self.assertEqual(m("Viu episódios 1 a 2 de Paradise Kiss (começou essa semana)"),
                         {"motivo": "Viu Paradise Kiss", "detalhe": "eps 1 e 2"})
        self.assertEqual(m("Ele recuou, dizendo que não queria atrapalhar", "o Patrick"),
                         {"motivo": "Você recuou", "detalhe": "dizendo que não queria…"})
        self.assertEqual(m("Encontrou a Bia (Quartinho Bar); assunto: festas"), {"motivo": "Encontrou a Bia", "detalhe": "festas"})
        self.assertEqual(m("Ele desconfiou de uma foto minha", "o Patrick")["motivo"], "Você desconfiou de uma foto dela")

    def test_sentimento_em_voz_de_painel(self):
        s = w.emocao_view(self.PANEL, dormindo=False)["sentindo"]
        self.assertEqual((s[0]["texto"], s[0]["motivo"], s[0]["vezes"]), ("Com saudade de você", "Você fez um Pix pra ela", 3))
        self.assertEqual((s[1]["texto"], s[1]["motivo"], s[1]["detalhe"]), ("Grata à Bia", "A Bia elogiou o look", "Instagram"))

    def test_preposicoes(self):
        self.assertEqual(w._alguem("o Patrick", "chateada"), "com você")
        self.assertEqual(w._alguem("o Patrick", "grata"), "a você")
        self.assertEqual(w._alguem("o Theo", "orgulhosa"), "do Theo")
        self.assertEqual(w._alguem("o Patrick", "com culpa"), "")
        self.assertEqual(w._alguem("o Patrick", "com ciuminho"), "de você")
        self.assertEqual(w._alguem("o pai", "com saudade de casa"), "", "o motivo já diz: Falou com o pai")

    def test_mundo_grava_no_padrao(self):
        from emotion import appraise_event
        ev = lambda k, t, s, p="[]": [(c, tg) for _f, _k, _i, c, tg in appraise_event(
            {"event_key": k, "event_type": t, "summary": s, "participants_json": p})]
        self.assertEqual(ev("tv:2026-09-27", "routine", "Viu episódios 1 a 2 de Paradise Kiss (começou essa semana)"),
                         [("Viu Paradise Kiss · eps 1 e 2", None)])
        self.assertEqual(ev("social:1", "social_contact", "Trocou mensagens com a Bia; assunto: festas",
                            '["marina","bia_andrade"]')[0][0], "Mensagens com a Bia · festas")
        self.assertEqual(ev("social:2", "social_contact", "Trocou mensagens com a Bia; assunto: conflitos leves",
                            '["marina","bia_andrade"]')[0][0], "Se estranhou com a Bia · por mensagem")
        self.assertEqual(ev("outing:1:convite", "social_invite",
                            "A Bia te chamou: Saindo com a Bia no Quartinho Bar (hoje às 21:00)", '["marina","bia_andrade"]')[0][0],
                         "A Bia chamou pra sair · Quartinho Bar")
        self.assertEqual(ev("meal:1:almoco", "meal", "Almoço em casa: um poke pedido no iFood; comeu além da conta")[0][0],
                         "Almoçou um poke · comeu demais")
        self.assertEqual(ev("social:3", "social_contact", "O pai mandou mensagem", '["marina","henrique_salles"]')[0][0],
                         "O pai perguntou dela", "nada de 'bom dia' às 21h")
        self.assertEqual(ev("presente:2026-09-27T22:01", "gift", "O Patrick mandou de surpresa um lanche")[0],
                         ("o Patrick mandou comida · surpresa", "o Patrick"))


class PorDentroTest(unittest.TestCase):
    """28/09 (Patrick): Hoje por dentro, Na cabeça e Vocês dois (por_dentro.py)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.tmp.name) / "p.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_quando(self):
        import por_dentro as pd
        now = datetime(2026, 9, 28, 15, 0)
        self.assertEqual(pd.quando(datetime(2026, 9, 28, 14, 40), now), "há 20 min")
        self.assertEqual(pd.quando(datetime(2026, 9, 28, 9, 0), now), "hoje, 9h")
        self.assertEqual(pd.quando(datetime(2026, 9, 27, 22, 1), now), "ontem, 22h01")
        self.assertEqual(pd.quando(datetime(2026, 9, 26, 18, 0), now), "sáb, 18h")
        self.assertEqual(pd.adiante(datetime(2026, 9, 29, 7, 0), now), "amanhã, 7h")

    def test_diario_guarda_o_que_ja_passou_e_vira_as_5h(self):
        import por_dentro as pd
        from emotion import EmotionEngine
        eng = EmotionEngine(self.db)
        eng.feel("alegria", "diversao", 0.4, "Trocou mensagens com a Bia; assunto: festas",
                 datetime(2026, 9, 27, 18, 0), target="a Bia")
        eng.feel("medo", "ciume", 0.25, "Ele falou de outra garota", datetime(2026, 9, 27, 23, 2), target="o Patrick")
        for _ in range(3):                    # o mesmo banho no mesmo minuto vira uma linha só
            eng.feel("alegria", "alivio", 0.2, "banho quentinho", datetime(2026, 9, 28, 0, 6), source_key=None)
        d = pd.diario_view(self.db, datetime(2026, 9, 28, 5, 55))
        self.assertEqual(d["titulo"], "Ontem por dentro", "madrugada ainda é a noite anterior; hoje está vazio")
        self.assertEqual([x["hora"] for x in d["itens"]], ["00:06", "23:02", "18:00"])
        self.assertEqual(d["itens"][1]["texto"], "Com ciuminho de você")
        self.assertEqual((d["itens"][2]["motivo"], d["itens"][2]["detalhe"]), ("Mensagens com a Bia", "festas"))
        eng.feel("alegria", "empolgacao", 0.4, "saiu episódio novo", datetime(2026, 9, 28, 9, 0))
        d = pd.diario_view(self.db, datetime(2026, 9, 28, 10, 0))
        self.assertEqual((d["titulo"], len(d["itens"])), ("Hoje por dentro", 1))

    def test_voces_conversa_e_pendente(self):
        import por_dentro as pd
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO conversas(role, content, timestamp) VALUES ('assistant', 'boa noite', ?)",
                         ("2026-09-27T23:04:00",))
            conn.commit()
        now = datetime(2026, 9, 28, 5, 55)
        self.assertEqual(pd.voces_linhas(self.db, now),
                         [["message-circle", "Conversa", "Ontem, 23h04"], ["hourglass", "Pendente", "Nada"]])
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO conversas(role, content, timestamp) VALUES ('user', 'bom dia', ?)",
                         ("2026-09-28T05:50:00",))
            conn.commit()
        self.assertEqual(pd.voces_linhas(self.db, now)[1], ["hourglass", "Pendente", "Resposta dela"])


class VozTest(unittest.TestCase):
    def test_painel_fala_com_voce(self):
        self.assertEqual(w.voz_painel("O Patrick fez um pix de R$ 150 pra ela"), "Você fez um Pix de R$ 150 pra ela")
        self.assertEqual(w.voz_painel("Devolveu o empréstimo do Patrick"), "Devolveu o seu empréstimo")
        self.assertEqual(w.voz_painel("Pediu comida pro Patrick"), "Pediu comida pra você")

    def test_extrato(self):
        self.assertEqual(w.mov_desc("pix do Patrick: pro açaí"), "Seu Pix · pro açaí")
        self.assertEqual(w.mov_desc("presente do Patrick: um jantar (ele disse: aproveita)"), "Seu presente: um jantar")
        self.assertEqual(w.mov_desc("contas dela (celular e streamings)"), "Celular e streamings")
        self.assertEqual(w.mov_desc("delivery pro Patrick: suco verde"), "Delivery pra você: suco verde")
        self.assertEqual(w.mov_desc("cachê do freela"), "Cachê do freela")


class MundoTest(unittest.TestCase):
    def test_pessoas_com_quem_e_e_ultimo_contato(self):
        import canon_extras
        from seed_world_bible_v36 import seed_world_bible
        from social_day import SocialDay
        from social_world import seed_social
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(Path(tmp) / "m.db")
            seed_world_bible(db)
            seed_social(db)
            canon_extras.ensure(db)
            now = datetime(2026, 9, 26, 12, 0)
            with db.get_connection() as conn:
                conn.execute("UPDATE social_relationships SET last_interaction_at=?, contact_frequency=4 "
                             "WHERE character_key='bia_andrade'", ("2026-09-26T08:15:00",))
            m = SocialDay(db).world_panel(now)
            por_nome = {p["nome"]: p for p in m["pessoas"]}
            self.assertEqual(m["pessoas"][0]["nome"], "Bia Andrade", "quem falou por último vem primeiro")
            self.assertEqual((por_nome["Bia Andrade"]["quem"], por_nome["Bia Andrade"]["falaram"],
                              por_nome["Bia Andrade"]["vezes_30d"]), ("melhor amiga", "hoje, 08:15", 4))
            self.assertEqual(por_nome["Henrique Salles"]["quem"], "pai")
            self.assertIsNone(por_nome["Henrique Salles"]["falaram"])
            self.assertEqual(por_nome["Seu Jorge Almeida"]["iniciais"], "JA")
            self.assertEqual(por_nome["Dona Neide Souza"]["vezes_30d"], 0, "'weekly' do cânone não é contagem")
            self.assertTrue(all(p["quem"] for p in m["pessoas"]))
            # 28/09: foto de perfil das amigas com RG; quem não tem fica nas iniciais
            for nome, key in (("Bia Andrade", "bia_andrade"), ("Carol Menezes", "carol_menezes"),
                              ("Júlia Azevedo", "julia_azevedo"), ("Theo Martins", "theo_martins")):
                self.assertEqual(por_nome[nome]["foto"], f"avatars/{key}.jpg")
                self.assertTrue((Path(__file__).resolve().parents[1] / "webapp" / por_nome[nome]["foto"]).is_file())
            self.assertIsNone(por_nome["Seu Jorge Almeida"]["foto"])


class NaCabecaTest(unittest.TestCase):
    """28/09 (Patrick): Na cabeça — título | quando; estado | barra | motivo, tudo curto."""

    def test_nomes_curtos(self):
        import por_dentro as pd
        self.assertEqual(pd.materia("Projeto: Projetar em Sociedade"), "Projeto")
        self.assertEqual(pd.materia("Práticas Experimentais VI"), "Práticas VI")
        aula = {"tipo": "aula", "texto": "", "blocos": [{"display_name": "Práticas Experimentais II"},
                                                          {"display_name": "Linguagem Visual"}]}
        self.assertEqual(pd._titulo_agenda(aula), ("2 aulas", "Práticas II e +1"))
        self.assertEqual(pd._titulo_agenda({"tipo": "academia", "texto": "Treino na Bodytech"}), ("Treino", ""))
        role = {"tipo": "role", "texto": "Saindo com a Bia no Quartinho Bar", "com": ("bia_andrade",)}
        self.assertEqual(pd._titulo_agenda(role), ("Rolê com a Bia", "Quartinho Bar"))

    def test_estado_pela_agenda_viva(self):
        import por_dentro as pd
        from agenda_viva import Avaliacao
        from datetime import timedelta

        class Disp:
            def __init__(self, v, fat):
                self.a = Avaliacao(v, fat)

            def avaliar(self, *a, **k):
                return self.a

        class Av:
            def __init__(self, v, fat):
                self.disp = Disp(v, fat)

            def _peso(self, *a):
                return 0.38

            def _state(self):
                return {}

        now = datetime(2026, 9, 28, 16, 0)
        it = {"key": "gym:2026-09-28", "tipo": "academia", "inicio": now + timedelta(hours=2), "com": (), "origem": "planejado"}
        f = object()
        self.assertEqual(pd._estado(Av(0.3, [("energia", "sem energia", -0.11)]), it, now, f, {}), ("Quer pular", 0.3, "Sem energia"))
        self.assertEqual(pd._estado(Av(0.8, [("amiga", "é com a Bia", 0.15)]), it, now, f, {}), ("Animada", 0.8, "É com a Bia"))
        self.assertEqual(pd._estado(Av(0.3, []), it, now, None, {}), ("", None, ""), "dormindo: ainda não pensou")
        longe = {**it, "inicio": now + timedelta(hours=6)}
        self.assertEqual(pd._estado(Av(0.3, []), longe, now, f, {}), ("", None, ""), "longe da hora: ainda não pensou")
        self.assertEqual(pd._estado(Av(0.3, []), it, now, f, {it["key"]: {"vai": True, "vontade": 0.62}}), ("Vai", 0.62, ""))


if __name__ == "__main__":
    unittest.main()
