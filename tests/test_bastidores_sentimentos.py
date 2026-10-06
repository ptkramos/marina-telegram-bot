"""Redesenho dos Bastidores, passo 4 (PLANO_WEBAPP, "Redesenho dos Bastidores — plano"; 06/10).

A sub-aba Sentimentos do Por dentro (`bastidores_sentimentos.py`): humor em grade 3×3 com o caminho do dia em
setinhas, Brincadeira e Bateria social, Sentindo agora por pessoa (bolinhas, força, desde, tendência) e o que já
passou hoje. Só tela.
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import bastidores_hist as bh
import bastidores_sentimentos as bs
from db import DatabaseManager
from emotion import EmotionEngine

T0 = datetime(2026, 10, 5, 22, 50)
DIA = datetime(2026, 10, 5, 5, 0)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "sentimentos.db")

    def tearDown(self):
        self.temp.cleanup()


class CasaTests(unittest.TestCase):
    def test_cortes_da_grade(self):
        casos = {(0.70, 0.70): (0, 2), (0.70, 0.50): (1, 2), (0.70, 0.30): (2, 2), (0.50, 0.70): (0, 1),
                 (0.50, 0.50): (1, 1), (0.50, 0.30): (2, 1), (0.30, 0.70): (0, 0), (0.30, 0.50): (1, 0),
                 (0.30, 0.30): (2, 0), (0.62, 0.62): (0, 2), (0.45, 0.40): (1, 1)}
        for (v, a), esperado in casos.items():
            self.assertEqual(bs.casa(v, a), esperado, (v, a))

    def test_as_palavras_de_cada_casa(self):
        self.assertEqual([p for linha in bs.GRADE for p, _ in linha],
                         ["Irritada", "Inquieta", "Animada", "Chateada", "Normal", "Feliz",
                          "Desanimada", "Preguiçosa", "Relaxada"])


class PassosTests(unittest.TestCase):
    def test_vizinha_reta_e_diagonal(self):
        self.assertEqual(bs._passos([(1, 1), (1, 2)]), [{"l": 1, "c": 1, "dl": 0, "dc": 1}])
        self.assertEqual(bs._passos([(1, 1), (0, 0)]), [{"l": 1, "c": 1, "dl": -1, "dc": -1}])

    def test_salto_vira_uma_seta_por_casa(self):
        self.assertEqual(bs._passos([(2, 0), (0, 1)]), [{"l": 2, "c": 0, "dl": -1, "dc": 1},
                                                         {"l": 1, "c": 1, "dl": -1, "dc": 0}])

    def test_so_os_ultimos_quatro(self):
        setas = bs._passos([(2, 0), (2, 2), (0, 2), (0, 0)])       # 6 passos
        self.assertEqual(len(setas), 4)
        self.assertEqual(setas[-1], {"l": 0, "c": 1, "dl": 0, "dc": -1})

    def test_ida_e_volta_pelo_mesmo_vao_vira_uma_seta(self):
        setas = bs._passos([(1, 2), (0, 2), (1, 2)])
        self.assertEqual(setas, [{"l": 0, "c": 2, "dl": 1, "dc": 0, "ida_volta": True}])


class HumorTests(Base):
    def _grava(self, *pontos):
        for hm, l, c in pontos:
            bh.humor(self.db, T0.replace(hour=int(hm[:2]), minute=int(hm[3:])), l, c)

    def test_o_caminho_do_dia_com_as_horas(self):
        self._grava(("07:00", 1, 1), ("09:00", 0, 2), ("21:20", 1, 2), ("21:40", 0, 1))
        h = bs.humor(self.db, T0, 0.7, 0.7, DIA)                 # agora: Animada
        casas = {c["palavra"]: c for c in h["grade"]}
        self.assertTrue(casas["Animada"]["agora"])
        self.assertEqual(h["desde"], "desde 22:50")
        self.assertEqual(casas["Normal"]["hora"], "07:00")
        self.assertEqual(casas["Inquieta"]["hora"], "21:40")
        self.assertEqual(casas["Feliz"]["hora"], "21:20")
        self.assertEqual(casas["Irritada"]["hora"], "")
        self.assertEqual(len(h["setas"]), 4)

    def test_mesma_casa_nao_grava_de_novo(self):
        self._grava(("09:00", 0, 2), ("09:10", 0, 2), ("09:20", 0, 2))
        self.assertEqual(len(bh.lista(self.db, "humor", DIA)), 1)
        h = bs.humor(self.db, T0, 0.7, 0.7, DIA)
        self.assertEqual(h["desde"], "desde 09:00")
        self.assertEqual(h["setas"], [])

    def test_sem_historia_nao_inventa_o_desde(self):
        h = bs.humor(self.db, T0, 0.7, 0.7, DIA)
        self.assertEqual(h["desde"], "")
        self.assertEqual([c["hora"] for c in h["grade"] if c["agora"]], [""])
        self.assertEqual(len(bh.lista(self.db, "humor", DIA)), 1)          # a partir daqui o caminho existe

    def test_de_ontem_nao_mostra_hora(self):
        bh.humor(self.db, DIA - timedelta(hours=3), 1, 1)                  # Normal desde as 2 da manhã
        h = bs.humor(self.db, T0, 0.7, 0.7, DIA)
        casas = {c["palavra"]: c for c in h["grade"]}
        self.assertEqual(casas["Normal"]["hora"], "")
        self.assertEqual(h["setas"], [{"l": 1, "c": 1, "dl": -1, "dc": 1}])  # Normal → Animada, na diagonal

    def test_dormindo_fica_a_casa_de_antes_de_dormir(self):
        self._grava(("07:00", 1, 1), ("21:40", 0, 1))
        dormiu = T0.replace(hour=22, minute=30)
        h = bs.humor(self.db, T0 + timedelta(hours=3), 0.3, 0.3, DIA, dormiu)   # o motor diria Desanimada
        self.assertEqual(h["palavra"], "Inquieta")
        self.assertEqual((h["desde"], h["dormindo"]), ("até 22:30", "Dormindo desde 22:30"))
        self.assertEqual(len(bh.lista(self.db, "humor", DIA)), 2)          # dormindo não grava

    def test_retrato_nao_grava_dormindo(self):
        with mock.patch("webapp_server._dormiu_em", return_value=T0):
            bh.retrato(self.db, T0)
        self.assertIsNone(bh.ultimo(self.db, "humor", T0))
        with mock.patch("webapp_server._dormiu_em", return_value=None):
            bh.retrato(self.db, T0)
        self.assertIsNotNone(bh.ultimo(self.db, "humor", T0))


class SentindoTests(Base):
    def setUp(self):
        super().setUp()
        self.eng = EmotionEngine(self.db)

    def test_por_pessoa_patrick_primeiro_e_dela_no_fim(self):
        self.eng.feel("alegria", "diversao", 0.9, "o Patrick provocou · de brincadeira", T0 - timedelta(minutes=5),
                      target="o Patrick")
        self.eng.feel("raiva", "chateacao", 0.6, "Se estranhou com a Bia · por mensagem", T0 - timedelta(minutes=30),
                      target="a Bia")
        self.eng.feel("vergonha", "culpa", 0.3, "Enrolou no trabalho · facul", T0 - timedelta(minutes=40))
        grupos = bs.sentindo(self.db, T0)
        self.assertEqual([g["nome"] for g in grupos], ["Patrick", "Bia", "Dela"])
        f = grupos[0]["sentimentos"][0]
        self.assertEqual((f["nome"], f["bolinhas"], f["forca"], f["bom"]), ("Diversão", 5, "Intensa", True))
        self.assertEqual((f["motivo"], f["detalhe"], f["desde"]), ("O Patrick provocou", "de brincadeira", "Desde 22:45"))
        self.assertFalse(grupos[1]["sentimentos"][0]["bom"])
        self.assertEqual(grupos[2]["icone"], "user")

    def test_tendencia(self):
        self.eng.feel("alegria", "empolgacao", 0.5, "Novo", T0 - timedelta(minutes=10), target="o Patrick")
        self.eng.feel("tristeza", "desanimo", 0.6, "Antigo", T0 - timedelta(hours=3))      # meia-vida 8 h
        self.eng.feel("raiva", "irritacao", 0.6, "Esfriando", T0 - timedelta(hours=2))      # meia-vida 1h30
        tend = {f["motivo"]: f["tendencia"] for g in bs.sentindo(self.db, T0) for f in g["sentimentos"]}
        self.assertEqual(tend, {"Novo": "crescendo", "Antigo": "estavel", "Esfriando": "passando"})

    def test_ate_resolver_um_por_causa(self):
        self.eng.feel("medo", "ansiedade", 0.3, "Entrega em 2 dias · Projeto", T0 - timedelta(hours=12), sticky=True,
                      source_key="entrega")
        self.eng.feel("medo", "ansiedade", 0.25, "Casting amanhã · óculos", T0 - timedelta(hours=1), sticky=True,
                      source_key="casting")
        dela = bs.sentindo(self.db, T0)[0]["sentimentos"]
        self.assertEqual([(f["motivo"], f["tendencia"]) for f in dela],
                         [("Entrega em 2 dias", "ate_resolver"), ("Casting amanhã", "ate_resolver")])

    def test_motivo_e_detalhe_sem_cortar(self):
        self.eng.feel("medo", "ansiedade", 0.4, "Entrega em 2 dias · Projeto: Projetar em Sociedade",
                      T0 - timedelta(minutes=5))
        f = bs.sentindo(self.db, T0)[0]["sentimentos"][0]
        self.assertEqual(f["detalhe"], "Projeto: Projetar em Sociedade")

    def test_desde_de_ontem(self):
        self.eng.feel("tristeza", "desanimo", 0.8, "Antigo", T0 - timedelta(hours=26))
        self.assertEqual(bs.sentindo(self.db, T0)[0]["sentimentos"][0]["desde"], "Desde ontem, 20:50")

    def test_ja_passou_sem_repetir_o_de_cima(self):
        self.eng.feel("raiva", "irritacao", 0.4, "Perdeu o ônibus", T0.replace(hour=8))     # já esfriou
        self.eng.feel("alegria", "diversao", 0.9, "Agora", T0 - timedelta(minutes=5))
        self.eng.feel("alegria", "diversao", 0.3, "De manhã", T0.replace(hour=9))          # mesmo sentimento: ativo
        passou = bs.ja_passou(self.db, T0, DIA)
        self.assertEqual([(x["hora"], x["texto"], x["motivo"]) for x in passou], [("08:50", "Irritação", "Perdeu o ônibus")])


class TelaTests(Base):
    def test_uma_secao_com_erro_some_sozinha(self):
        panel = EmotionEngine(self.db).panel(T0)
        with mock.patch.object(bs, "sentindo", side_effect=RuntimeError("x")):
            v = bs.sentimentos_view(self.db, T0, panel)
        self.assertIsNone(v["sentindo"])
        self.assertEqual([b["label"] for b in v["barras"]], ["Brincadeira", "Bateria social"])
        self.assertIn("grade", v["humor"])

    def test_painel_manda_os_eixos_e_o_prompt_nao_muda(self):
        eng = EmotionEngine(self.db)
        p, f = eng.panel(T0), eng.feeling(T0)
        self.assertEqual((p["valence"], p["arousal"]), (f.valence, f.arousal))
        self.assertEqual(p["mood"], eng.mood_words(f.valence, f.arousal))


if __name__ == "__main__":
    unittest.main()
