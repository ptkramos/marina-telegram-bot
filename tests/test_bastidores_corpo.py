"""Redesenho dos Bastidores, passo 3 (PLANO_WEBAPP, "Redesenho dos Bastidores — plano"; 06/10).

A sub-aba Corpo do Por dentro em desenhos (`bastidores_corpo.py`): Agora com o Mal-estar, a faixa do sono, os 28
dias do ciclo, o velocímetro da vontade com as etiquetas do que a empurra e o calendário dos orgasmos. Só tela.
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import bastidores_corpo as bc
import bastidores_hist as bh
from db import DatabaseManager
from emotion import EmotionEngine

T0 = datetime(2026, 10, 5, 23, 40)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "corpo.db")

    def tearDown(self):
        self.temp.cleanup()


class MalEstarTests(unittest.TestCase):
    def test_a_primeira_coisa_do_motivo_vira_a_palavra(self):
        m = bc.mal_estar(0.4, "menstruada, cólica leve, dor de cabeça")
        self.assertEqual((m["word"], m["value"]), ("Cólica leve", 0.4))

    def test_a_fase_nao_repete(self):
        self.assertEqual(bc.mal_estar(0.2, "inchada da TPM")["word"], "Inchada")

    def test_sem_motivo_e_nenhum_com_barra_vazia(self):
        self.assertEqual(bc.mal_estar(0.05, ""), {"label": "Mal-estar", "value": 0.0, "word": "Nenhum"})


class CicloTests(unittest.TestCase):
    def test_proximo_marco(self):
        casos = {3: "Menstruação acaba em 2 dias", 4: "Menstruação acaba amanhã", 5: "Último dia de menstruação",
                 7: "Período fértil em 5 dias", 11: "Período fértil amanhã", 14: "Período fértil acaba em 2 dias",
                 16: "Último dia do período fértil", 24: "Menstruação em 5 dias", 28: "Menstruação amanhã"}
        for dia, txt in casos.items():
            self.assertEqual(bc._proximo_marco(dia, 28), txt, dia)


class SonoTests(Base):
    def setUp(self):
        super().setUp()
        from sleep_plan import SleepPlan
        plan = SleepPlan(self.db)
        self.bed, self.wake = plan.bed(T0.date() - timedelta(days=1)), plan.wake(T0.date())

    def test_noite_inteira_e_a_linha_so_da_noite(self):
        s = bc.sono(self.db, T0.replace(hour=14, minute=0), False)
        self.assertEqual(len(s["trechos"]), 1)
        self.assertNotIn("agora", s["trechos"][0]["rotulo"])
        self.assertTrue(s["linha"].startswith("Dormiu por volta de "))
        self.assertEqual(s["agora"], round(100 * 20 / 24, 2))       # 14:00 numa faixa de 18:00 a 18:00
        self.assertEqual(s["eixo"], ["18:00", "00:00", "06:00", "12:00", "18:00"])

    def test_dormindo_vai_ate_agora(self):
        now = self.bed + timedelta(hours=2, minutes=10)
        s = bc.sono(self.db, now, True)
        self.assertTrue(s["trechos"][0]["rotulo"].endswith("– agora"))
        self.assertEqual(s["trechos"][0]["fim"], s["agora"])
        self.assertEqual(s["linha"], "Dormindo há 2 horas e 10 minutos")

    def test_acordada_no_meio_da_noite_o_trecho_para_quando_acordou(self):
        from sleep_plan import SleepPlan
        ini = (self.bed + timedelta(hours=2)).replace(second=0, microsecond=0)
        with mock.patch.object(SleepPlan, "micro_wakes", return_value=[(ini, ini + timedelta(minutes=10), "sede")]):
            s = bc.sono(self.db, ini + timedelta(minutes=4), False)
        self.assertEqual(s["linha"], "Acordou no meio da noite")
        self.assertFalse(s["trechos"][0]["rotulo"].endswith("agora"))
        self.assertLess(s["trechos"][0]["fim"], s["agora"])


class EtiquetasTests(unittest.TestCase):
    MAL = {"word": "Nenhum"}

    def test_maiores_primeiro_e_no_maximo_quatro(self):
        t = {"ciclo": 0.1, "desejo": 0.05, "humor": -0.2, "energia": -0.04, "saudade": 0.06, "magoa": -0.01}
        e = bc.etiquetas(t, "ovulatoria", self.MAL)
        self.assertEqual([x["texto"] for x in e], ["Mau humor", "Período fértil", "Saudade do Patrick",
                                                   "Desejo pelo Patrick"])
        self.assertEqual([x["sobe"] for x in e], [False, True, True, True])

    def test_o_que_mexe_pouco_nao_aparece(self):
        self.assertEqual(bc.etiquetas({"ciclo": 0.02, "saudade": -0.029}, "folicular", self.MAL), [])

    def test_gozou_e_sem_gozar_com_as_horas(self):
        e = bc.etiquetas({"gozou": -0.5, "desde": 1.6}, "", self.MAL)
        self.assertEqual(e, [{"texto": "Gozou há 1 hora", "sobe": False}])
        e = bc.etiquetas({"sem_gozar": 0.3, "desde": 60.0}, "", self.MAL)
        self.assertEqual(e[0]["texto"], "2 dias sem gozar")

    def test_excitacao_nao_vira_etiqueta(self):
        # Patrick (06/10): o arco de dentro do velocímetro já mostra a excitação
        self.assertEqual(bc.etiquetas({"excitacao": 0.3}, "", self.MAL), [])

    def test_mal_estar_usa_a_palavra_da_barra(self):
        e = bc.etiquetas({"mal_estar": -0.2}, "", {"word": "Cólica forte"})
        self.assertEqual(e, [{"texto": "Cólica forte", "sobe": False}])


class TermosDaVontadeTests(Base):
    def test_a_conta_nao_muda_e_o_gozo_recente_puxa_pra_baixo(self):
        eng = EmotionEngine(self.db)
        bh.orgasmo(self.db, T0 - timedelta(hours=1), "patrick", "sexting")
        from emotion import RELEASE_KEY
        self.db.set_estado_relacional(RELEASE_KEY, (T0 - timedelta(hours=1)).isoformat())
        f = eng.feeling(T0)
        self.assertLess(f.libido_termos["gozou"], 0)
        self.assertAlmostEqual(f.libido_termos["desde"], 1.0, places=1)
        with mock.patch.object(eng, "_libido", wraps=eng._libido) as conta:
            eng.feeling(T0)
            sem = conta.call_args.args[:8]
        self.assertEqual(eng._libido(*sem)[0], f.libido)
        p = eng.panel(T0)
        self.assertEqual(p["libido"], f.libido)
        self.assertIn("gozou", p["libido_termos"])


class CalendarioTests(Base):
    def test_coracao_bolinha_detalhe_e_ultimo(self):
        bh.orgasmo(self.db, datetime(2026, 10, 1, 23, 50), "sozinha", "antes de dormir")
        bh.orgasmo(self.db, datetime(2026, 10, 4, 16, 20), "sozinha", "em casa", onde="no banho", brinquedos=["lush"])
        bh.orgasmo(self.db, datetime(2026, 10, 5, 22, 5), "patrick", "lovense")
        c = bc.calendario(self.db, T0)
        self.assertEqual((c["mes"], c["vazios"], len(c["dias"])), ("Outubro", 4, 31))   # 01/10/2026 é quinta
        d = {x["n"]: x for x in c["dias"]}
        self.assertTrue(d[1]["sozinha"] and not d[1]["patrick"])
        self.assertEqual(d[4]["detalhes"], ["16:20, sozinha, no banho, com o Lush"])
        self.assertEqual(d[5]["detalhes"], ["22:05, com o Patrick, pelo Lovense"])
        self.assertTrue(d[5]["patrick"] and d[5]["hoje"])
        self.assertTrue(d[6]["futuro"])
        self.assertEqual(c["ultimo"], "Último orgasmo: hoje às 22:05, com o Patrick")

    def test_ultimo_de_outro_dia(self):
        bh.orgasmo(self.db, datetime(2026, 10, 3, 0, 40), "sozinha", "antes de dormir")
        self.assertEqual(bc.calendario(self.db, T0)["ultimo"], "Último orgasmo: dia 3, sozinha")
        self.assertEqual(bc.calendario(self.db, datetime(2026, 10, 4, 9))["ultimo"],
                         "Último orgasmo: ontem às 00:40, sozinha")
        self.assertEqual(bc.calendario(self.db, datetime(2026, 11, 2, 9))["ultimo"],
                         "Último orgasmo: 3 de outubro, sozinha")

    def test_sem_nenhum_gozo(self):
        c = bc.calendario(self.db, T0)
        self.assertEqual(c["ultimo"], "")
        self.assertFalse(any(x["detalhes"] for x in c["dias"]))


class CorpoViewTests(Base):
    def test_uma_secao_com_erro_some_sozinha(self):
        panel = EmotionEngine(self.db).panel(T0)
        body = [{"label": "Energia", "value": 0.6, "word": "Normal"}, {"label": "Saciedade", "value": 0.7, "word": "Ok"},
                {"label": "Excitação", "value": 0.5, "word": "Aberta"}]
        with mock.patch.object(bc, "sono", side_effect=RuntimeError("x")), self.assertLogs("bastidores_corpo", "ERROR"):
            c = bc.corpo_view(self.db, T0, panel, body, False)
        self.assertIsNone(c["sono"])
        self.assertEqual([b["label"] for b in c["agora"]], ["Energia", "Saciedade", "Mal-estar"])
        self.assertIn("vontade", c["intimidade"])
        self.assertIsNone(c["intimidade"]["excitacao"])          # zero: o arco de dentro some

    def test_excitacao_acesa_com_o_desde(self):
        bh.gravar(self.db, "excitacao", T0 - timedelta(minutes=30), {"origem": "lovense"})
        panel = {**EmotionEngine(self.db).panel(T0), "excitation": 0.55}
        it = bc.intimidade(self.db, T0, panel, {"word": "Nenhum"})
        self.assertEqual(it["excitacao"], {"valor": 0.55, "palavra": "Molhada", "desde": "23:10", "origem": "lovense"})
        self.assertEqual(it["vontade"]["cortes"], [0.35, 0.55, 0.72, 0.85])


if __name__ == "__main__":
    unittest.main()
