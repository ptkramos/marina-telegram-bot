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
                          {"word": "grata", "target": "a Bia", "value": 0.4, "cause": "ele te elogiou", "count": 1,
                           "until_resolved": False}]}

    def test_dormindo_nao_aparece_exausta(self):
        e = w.emocao_view(self.PANEL, dormindo=True)
        self.assertEqual(e["body"][0]["word"], "dormindo")
        self.assertIn(["moon", "Sono", "dormindo agora"], e["linhas"])
        self.assertEqual(self.PANEL["body"][0]["word"], "exausta", "não altera o painel original")

    def test_linhas_rotuladas(self):
        e = w.emocao_view(self.PANEL, dormindo=False)
        self.assertIn(["moon", "Sono", "dormiu 8h40 · acordou às 9h05"], e["linhas"])
        self.assertIn(["heartbeat", "Último orgasmo", "há 30 h"], e["linhas"])
        self.assertIn(["bandage", "Desconforto", "Cólica"], e["linhas"])
        self.assertEqual(e["humor"], "Normal, nem lá nem cá")

    def test_sentimento_com_preposicao_e_na_voz_dela(self):
        s = w.emocao_view(self.PANEL, dormindo=False)["sentindo"]
        self.assertEqual((s[0]["texto"], s[0]["motivo"], s[0]["vezes"]), ("Com saudade dele", "Ele fez um Pix pra mim", 3))
        self.assertEqual((s[1]["texto"], s[1]["motivo"]), ("Grata à Bia", "Ele me elogiou"))

    def test_preposicoes(self):
        self.assertEqual(w._alguem("o Patrick", "chateada"), "com ele")
        self.assertEqual(w._alguem("o Patrick", "grata"), "a ele")
        self.assertEqual(w._alguem("o Theo", "orgulhosa"), "do Theo")
        self.assertEqual(w._alguem("o Patrick", "com culpa"), "")


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


if __name__ == "__main__":
    unittest.main()
