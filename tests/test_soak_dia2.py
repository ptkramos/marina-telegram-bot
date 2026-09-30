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


if __name__ == "__main__":
    unittest.main()
