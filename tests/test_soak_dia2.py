"""Soak, dia 2 (quarta 30/09, manhã — antes do deploy das correções do dia 1): "ela tá completamente alucinada".

1. 07:12 ele: "Tá dodói? O que houve?" (ela com cólica) → entrou o [ELE ESTÁ DOENTE] e às 08:38 ela: "vc que tá dodói".
2. Ela faltou por cólica (05:22) e o prompt dizia "Hoje NÃO tem aula (dia livre)": "ainda bem que hoje não tem aula".
3. 08:36 "lembrei daquele papo do meu peso, tem alguma novidade por aí?" — o assunto em aberto era o peso dela.
4. "Regando as plantas" 07:01, 07:26, 07:39, 07:49 (a das 07:26 no fim do banho, 07:03–07:30).
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from college import College
from db import DatabaseManager
from health import PATRICK_SICK_HINT, patrick_sick_hint
from tempo_livre import TempoLivre

DIA = datetime(2026, 9, 30)


def at(h, m):
    return DIA.replace(hour=h, minute=m)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "d.db")


class ElePerguntaDelaTest(unittest.TestCase):
    def test_pergunta_sobre_ela_nao_e_ele_doente(self):
        for t in ("Tá dodói? O que houve?", "vc tá doente amor?", "tá passando mal, princesa", "Cê tá com febre?"):
            self.assertEqual(patrick_sick_hint([t]), "", t)

    def test_ele_contando_que_esta_mal_continua(self):
        for t in ("acordei dodói", "Tá dodói? Eu também tô gripado.", "tô passando mal aqui"):
            self.assertEqual(patrick_sick_hint([t]), PATRICK_SICK_HINT, t)


class FaltouNaoEDiaLivreTest(Base):
    def test_falta_do_dia(self):
        self.assertIsNone(College(self.db).falta(DIA.date()))
        College(self.db)._log("falta:2026-09-30", at(5, 22), "Faltou a aula hoje (Acessórios de Moda): cólica forte.")
        self.assertEqual(College(self.db).falta(DIA.date()), "Faltou a aula hoje (Acessórios de Moda): cólica forte.")


class AssuntoDelaNaoViraPerguntaTest(Base):
    def test_checkin_so_com_assunto_que_envolve_ele(self):
        antes = datetime.now() - timedelta(days=1)
        for texto in ("Esclarecer se o peso mencionado por Marina aumentou ou diminuiu.",
                      "Marina quer saber como está o dia de Patrick quando ele voltar."):
            lid = self.db.adicionar_open_loop("waiting_reply", texto)
            with self.db.get_connection() as conn:
                conn.execute("UPDATE open_loops SET next_check_after=? WHERE id=?", (antes.isoformat(), lid))
                conn.commit()
        prontos = [l["content"] for l in self.db.get_open_loops_para_checkin(now=datetime.now())]
        self.assertEqual(prontos, ["Marina quer saber como está o dia de Patrick quando ele voltar."])


class PlantasUmaVezTest(Base):
    def setUp(self):
        super().setUp()
        for alvo, kw in (("tempo_livre.TempoLivre._ate", {"side_effect": lambda ini, fim: fim}),
                         ("tempo_livre.TempoLivre._chuva", {"return_value": False}),
                         ("tempo_livre.TempoLivre._musica_dele", {"return_value": False}),
                         ("agenda_reativa.AgendaReativa.alivio_em_casa", {"return_value": None}),
                         ("unhas.Unhas.quer_em_casa", {"return_value": False}),
                         ("cabelo.Cabelo.quer_umectar", {"return_value": False})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)

    def test_depois_de_regar_as_plantas_nao_rega_de_novo(self):
        tl = TempoLivre(self.db)
        with patch.object(TempoLivre, "_state", return_value={"2026-09-30": {"4": {
                "tipo": "plantas", "inicio": at(7, 1).isoformat(), "fim": at(7, 13).isoformat()}}}):
            for n in range(8):
                b = tl._escolhe(at(7, 26), f"4{'abcdefgh'[n]}", at(7, 26), at(8, 0), registrar=False)
                self.assertNotEqual(b.tipo, "plantas", n)

    def test_bloco_nao_comeca_dentro_do_banho(self):
        self.db.set_estado_relacional("pending_transition_json", json.dumps(
            {"routine_type": "shower", "transition_at": at(7, 3).isoformat(), "end_at": at(7, 30).isoformat()}))
        with patch("commute.Commute.ultima_volta", return_value=None):
            self.assertEqual(TempoLivre(self.db)._chegou(at(7, 31)), at(7, 30))


class SalaoComColicaTest(Base):
    """11:03 decidiu escova na Ophicina (11:22) com cólica forte; a saída atrasou (ida 11:45–11:55); às 11:36 a
    canja chegou, ela comeu em casa e o "passando mal" fez ela "sair mais cedo da Ophicina" — uber e escova cobrados."""

    def test_nao_esta_la_antes_de_chegar(self):
        from agenda_reativa import AgendaReativa
        from commute import Leg
        ida = Leg("commute:cabelo:2026-09-30:1103:ida", at(11, 45), at(11, 55), "a_pe", "ida", "pro Ophicina",
                  "Botafogo")
        volta = Leg("commute:cabelo:2026-09-30:1103:volta", at(12, 7), at(12, 17), "a_pe", "volta", "do Ophicina",
                    "Botafogo")
        c = {"tipo": "cabelo", "key": "cabelo:2026-09-30:1103", "place": "ophicina_do_cabelo",
             "inicio": at(11, 22), "fim": at(12, 7), "ida": ida, "volta": volta}
        with patch("agenda.Agenda._compromissos", side_effect=lambda d: [c] if d == DIA.date() else []):
            r = AgendaReativa(self.db)
            self.assertIsNone(r._atual(at(11, 36)))                         # ainda em casa, se arrumando
            self.assertIsNone(r.interromper(at(11, 36), "passando_mal"))
            self.assertEqual(r._atual(at(11, 58))["key"], "cabelo:2026-09-30:1103")

    def test_mal_na_hora_da_aula_que_faltou_ou_com_comida_chegando_nao_sai(self):
        from types import SimpleNamespace
        from vontade import Vontade
        bem = SimpleNamespace(discomfort=0.1)
        with patch("emotion.EmotionEngine.feeling", return_value=SimpleNamespace(discomfort=0.8)):
            self.assertTrue(Vontade(self.db)._sem_condicao(at(11, 3)))
            self.assertIsNone(Vontade(self.db)._livre_ate(at(11, 3)))
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO eventos_pendentes (event_type, description, event_at, end_at, source_key, "
                         "confirmed, status, created_at) VALUES ('falta', 'falta', ?, ?, 'falta:2026-09-30:2', 1, "
                         "'pending', ?)",
                         (at(11, 0).isoformat(), at(13, 0).isoformat(), at(5, 22).isoformat()))
            conn.commit()
        with patch("emotion.EmotionEngine.feeling", return_value=bem), \
                patch("meals.Meals._comida_chegando", return_value=False):
            self.assertTrue(Vontade(self.db)._sem_condicao(at(11, 3)))       # hora da aula que ela faltou
            self.assertFalse(Vontade(self.db)._sem_condicao(at(13, 30)))
        with patch("emotion.EmotionEngine.feeling", return_value=bem), \
                patch("meals.Meals._comida_chegando", return_value=True):
            self.assertTrue(Vontade(self.db)._sem_condicao(at(13, 30)))      # comida a caminho


class TrabalhoDitoViraMundoTest(Base):
    """13:34 "vou pegar firme nele", 13:45 "tô fechando o trabalho agora" — a sessão só estava às 20:21."""

    def setUp(self):
        super().setUp()
        sessao = {"assignment": {"course": "Práticas Experimentais VI"}, "start": at(20, 21), "end": at(21, 21),
                  "vespera": True}
        for alvo, kw in (("meals.Meals._at_home", {"return_value": True}),
                         ("meals.Meals._transition_busy", {"return_value": False})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        self.sessao = sessao

    def test_disse_que_vai_fazer_agora_a_sessao_comeca(self):
        c = College(self.db)
        with patch.object(College, "assignments", return_value=[]):
            self.assertFalse(c.observe_marina_line("Tô fechando o trabalho agora, amor kkk", at(13, 45)))  # sem trabalho
        with patch.object(College, "session_on", side_effect=lambda d: self.sessao):
            self.assertFalse(c.observe_marina_line("Hmmm, hoje eu iria de hambúrguer kkk", at(13, 40)))
            self.assertFalse(c.observe_marina_line("vou fazer o trabalho mais tarde", at(13, 40)))
            self.assertTrue(c.observe_marina_line("Tô aqui com o croqui aberto, vou parar de enrolar e pegar firme nele",
                                                  at(13, 34)))
        self.assertEqual(c._adiantou(DIA.date()), at(13, 34))

    def test_frases_que_contam(self):
        for t in ("Tô fechando o trabalho agora, amor kkk", "Vou salvar e abrir o arquivo agora, sem Stardew no meio",
                  "agora vou fazer o trabalho de verdade", "voltei pro arquivo, juro", "tô no trabalho, amor"):
            self.assertTrue(College.FAZ_AGORA.search(t), t)
        for t in ("Vou terminar isso e dps te dou atenção", "o trabalho tá se achando importante demais"):
            self.assertFalse(College.FAZ_AGORA.search(t), t)


class DiaCheioDeAmanhaTest(Base):
    """01/10 planejado: aula 07–15h, casting 15:30–17:00 e outro 17:00–18:30 na mesma agência."""

    def test_dois_compromissos_no_mesmo_lugar_ela_fica_la(self):
        from commute import Commute, Leg
        ag = "Agência boutique da Lívia (fictícia)"
        volta_puc = Leg("commute:2026-10-01:puc:volta", at(15, 0), at(15, 42), "onibus", "volta", "da PUC", "Gávea")
        ida1 = Leg("commute:outing:2026-10-01:casting:a:ida", at(14, 58), at(15, 30), "onibus", "ida", f"pra {ag}", "Centro")
        volta1 = Leg("commute:outing:2026-10-01:casting:a:volta", at(17, 0), at(17, 39), "onibus", "volta", f"da {ag}",
                     "Centro")
        ida2 = Leg("commute:outing:2026-10-01:casting:b:ida", at(16, 37), at(17, 0), "metro", "ida", f"pra {ag}", "Centro")
        volta2 = Leg("commute:outing:2026-10-01:casting:b:volta", at(18, 30), at(18, 55), "metro", "volta", f"da {ag}",
                     "Centro")
        out = Commute._emendas([volta_puc, ida1, volta1, ida2, volta2])
        self.assertEqual([(l.key.rsplit(":", 2)[-2] + ":" + l.direction, l.start, l.origem) for l in out],
                         [("a:ida", at(15, 0), "da PUC"), ("b:volta", at(18, 30), "")])

    def test_saidas_emendadas_contam_como_uma(self):
        from meals import Meals
        with self.db.get_connection() as conn:
            for k, ini, fim in (("freela:2026-10-01:casting:a", at(15, 30), at(17, 0)),
                                ("freela:2026-10-01:casting:b", at(17, 0), at(18, 30))):
                conn.execute("INSERT INTO eventos_pendentes (event_type, description, event_at, end_at, source_key, "
                             "confirmed, status, created_at) VALUES ('freela', 'casting', ?, ?, ?, 1, 'pending', ?)",
                             (ini.isoformat(), fim.isoformat(), k, at(8, 0).isoformat()))
            conn.commit()
        from datetime import date
        self.assertEqual(Meals(self.db)._saidas(date(2026, 10, 1)), [(at(15, 30), at(18, 30))])


class LancheSemCenaTest(unittest.TestCase):
    def test_lanche_nao_inventa_o_que_ela_estava_fazendo(self):
        """10:03 e 18:41: "Beliscou pipoca vendo série" com ela no closet e no TikTok."""
        import inspect
        import meals
        self.assertFalse([d for d in meals.MENU["lanche"] if "vendo" in d])
        self.assertNotIn("vendo série", inspect.getsource(meals.Meals.day_plan))


if __name__ == "__main__":
    unittest.main()
