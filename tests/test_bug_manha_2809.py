"""Bug do uso real: manhã de 28/09 (faculdade), com os horários do caso.

1. O Se arrumando da faculdade dizia "Tomando café" 07:36–07:46 e "Tomando banho" 07:46–08:06, mas ela pulou o café
   (meals, 07:52) e desceu com o Milo pro xixi às 07:58 — no meio do "banho". O café vem do meals (1º passo, na hora
   real; pulou, sem passo) e a descida do Milo vira passo (decisão do Patrick: "café dentro").
2. Ele escreveu às 05:52 ("Indo pro plantão"), ela respondeu às 07:47 ("Bom plantão, amor") e às 07:51 puxou
   "como tá o plantão até agora?" (open_loop_checkin): a espera só olhava a última mensagem dele.
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from agenda import Agenda, Passo
from commute import Leg
from db import DatabaseManager
from meals import MealSlot
from milo import Milo
from proactivity_service import ProactivityService
from seed_world_bible_v36 import seed_world_bible

DIA = datetime(2026, 9, 28)


def at(h, m, s=0):
    return DIA.replace(hour=h, minute=m, second=s)


IDA = Leg("commute:2026-09-28:puc:ida", at(8, 21), at(8, 58), "metro_onibus", "ida", "pra PUC", "Gávea")
AULA = [{"start_at": "2026-09-28T09:00:00", "end_at": "2026-09-28T10:40:00",
         "display_name": "Projeto: Projetar em Sociedade"}]
CAFE_PULADO = MealSlot("cafe", "meal:2026-09-28:cafe", at(7, 52), 13, "casa", "pão na chapa", skipped=True)
XIXI = {"key": "milo:2026-09-28:manha", "at": at(7, 58), "minutes": 12, "state": False, "summary": "xixi"}


class Base(unittest.TestCase):
    cafe = CAFE_PULADO
    milo = [XIXI]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "m.db")
        seed_world_bible(self.db)
        for alvo, kw in (("commute.Commute.legs_on", {"side_effect": lambda d: [IDA] if d == DIA.date() else []}),
                         ("academic_life.AcademicLife.blocks_on",
                          {"side_effect": lambda d: AULA if d == DIA.date() else []}),
                         ("academia.Academia.plano", {"return_value": None}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("sleep_plan.SleepPlan.wake", {"return_value": at(7, 36)}),
                         ("sleep_plan.SleepPlan.bed", {"return_value": at(23, 30)}),
                         ("meals.Meals.day_plan", {"side_effect": lambda d: [self.cafe] if d == DIA.date() else []}),
                         ("milo.Milo.day_plan", {"side_effect": lambda d: self.milo if d == DIA.date() else []}),
                         ("agenda.FACULDADE_CABELO_CHANCE", {"new": 0.0})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)

    def prep(self, now):
        return next(e for e in Agenda(self.db).etapas(DIA.date(), now) if e.tipo == "arrumando")


class CafePuladoEMiloTest(Base):
    def test_sem_cafe_e_com_o_milo_na_hora_dele(self):
        prep = self.prep(at(7, 40))
        self.assertEqual(prep.inicio, at(7, 36))
        self.assertEqual([p.texto for p in prep.passos],
                         ["Tomando banho", "Descendo com o Milo", "Escolhendo roupa", "Saindo"])
        milo = next(p for p in prep.passos if p.texto == "Descendo com o Milo")
        self.assertEqual(milo.inicio, at(7, 58))
        self.assertEqual(prep.passos[2].inicio, at(8, 10))          # a roupa espera ela subir

    def test_mundo_diz_o_que_ela_faz_minuto_a_minuto(self):
        ag = Agenda(self.db)
        for minuto in range(36, 36 + 45):
            t = at(7, 0) + timedelta(minutes=minuto)
            act = ag.prep_activity(t)["activity"]
            self.assertNotIn("café", act, t)
            if at(7, 58) <= t < at(8, 10):
                self.assertIn("(descendo com o Milo)", act, t)
                self.assertNotIn("banho", act, t)

    def test_card_mostra_a_descida(self):
        card = Agenda(self.db).card(at(8, 0))
        agora = [p["texto"] for i in card["linha"] for p in i["passos"] if p["estado"] == "agora"]
        self.assertEqual(agora, ["Descendo com o Milo"])


class CafeComidoTest(Base):
    cafe = MealSlot("cafe", "meal:2026-09-28:cafe", at(7, 55), 10, "casa", "pão na chapa")
    milo = [dict(XIXI, at=at(7, 40))]                              # desceu antes do café: fora do Se arrumando

    def test_cafe_e_o_primeiro_passo_na_hora_real(self):
        prep = self.prep(at(8, 0))
        self.assertEqual(prep.inicio, at(7, 55))
        self.assertEqual((prep.passos[0].texto, prep.passos[0].inicio), ("Tomando café", at(7, 55)))
        self.assertEqual((prep.passos[1].texto, prep.passos[1].inicio), ("Tomando banho", at(8, 5)))
        self.assertEqual([p.texto for p in prep.passos].count("Tomando café"), 1)
        self.assertNotIn("Descendo com o Milo", [p.texto for p in prep.passos])
        self.assertIsNone(Agenda(self.db).prep_activity(at(7, 50)))   # antes do café ela ainda não se arruma


class EncaixaTest(unittest.TestCase):
    def test_banho_nao_volta_depois_da_descida(self):
        lista = [Passo("Tomando banho", at(7, 36)), Passo("Escolhendo roupa", at(8, 5)), Passo("Saindo", at(8, 15))]
        out = Agenda._encaixa(lista, "Descendo com o Milo", at(7, 50), at(8, 0), at(8, 21))
        self.assertEqual([(p.texto, p.inicio) for p in out],
                         [("Tomando banho", at(7, 36)), ("Descendo com o Milo", at(7, 50)),
                          ("Escolhendo roupa", at(8, 0)), ("Saindo", at(8, 15))])

    def test_outro_passo_volta_depois(self):
        lista = [Passo("Escolhendo roupa", at(7, 36)), Passo("Saindo", at(8, 15))]
        out = Agenda._encaixa(lista, "Descendo com o Milo", at(7, 50), at(8, 0), at(8, 21))
        self.assertEqual([p.texto for p in out], ["Escolhendo roupa", "Descendo com o Milo", "Escolhendo roupa",
                                                  "Saindo"])


class MiloNaoAtropelaOCafeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "c.db")
        self.cafe = None
        for alvo, kw in (("rituals.Rituals.wake_at", {"return_value": at(7, 36)}),
                         ("rituals.Rituals.bed_at", {"return_value": at(23, 30)}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("milo.Milo.walker_today", {"return_value": False}),
                         ("meals.Meals.day_plan", {"side_effect": lambda d: [self.cafe] if self.cafe else []})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)

    def _xixi(self):
        return next(d for d in Milo(self.db).day_plan(DIA.date()) if d["key"].endswith(":manha"))

    def test_desce_fora_do_cafe(self):
        base = self._xixi()
        for desloca in (-5, 0, 5, 20):                  # cafés que atropelariam a descida
            self.cafe = MealSlot("cafe", "meal:2026-09-28:cafe", base["at"] + timedelta(minutes=desloca), 12,
                                 "casa", "pão na chapa")
            x = self._xixi()
            fim = x["at"] + timedelta(minutes=x["minutes"])
            self.assertTrue(fim <= self.cafe.at or x["at"] >= self.cafe.end, (desloca, x["at"]))
            self.assertGreaterEqual(x["at"], at(7, 39))

    def test_cafe_pulado_nao_mexe(self):
        base = self._xixi()
        self.cafe = MealSlot("cafe", "meal:2026-09-28:cafe", base["at"], 12, "casa", "pão", skipped=True)
        self.assertEqual(self._xixi()["at"], base["at"])


class IniciativaColadaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "p.db")
        self.db.adicionar_mensagem(role="user", content="Bom dia! Indo pro plantão, boa facul hj 😘",
                                   timestamp="2026-09-28T05:52:34")
        self.db.adicionar_mensagem(role="assistant", content="Bom plantão, amor. Boa facul pra mim também kkk",
                                   timestamp="2026-09-28T07:47:46")
        for alvo, kw in (("proactivity_service.ProactivityService.check_sleep_window", {"return_value": False}),
                         ("sleep_plan.SleepPlan.in_bed", {"return_value": False}),
                         ("proactivity_service.ProactivityService.tesao_initiative", {"return_value": False}),
                         ("proactivity_service.ProactivityService.determine_living_world_candidate",
                          {"return_value": {"rank": 80, "reason": "open_loop_checkin"}})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        self.svc = ProactivityService(db=self.db)

    def test_nao_puxa_assunto_4_min_depois_de_responder(self):
        self.assertEqual(self.svc.should_trigger(at(7, 51, 8)), (False, "esperando_ele"))
        self.assertEqual(self.svc.should_trigger(at(8, 40)), (True, "open_loop_checkin"))

    def test_saudade_tambem_espera(self):
        saudade = {"trigger": True, "level": 1.0, "hours": 2.0, "unanswered": 0}
        with patch("proactivity_service.ProactivityService.saudade", return_value=saudade):
            self.assertEqual(self.svc.should_trigger(at(7, 51, 8)), (False, "esperando_ele"))
            self.assertEqual(self.svc.should_trigger(at(8, 40)), (True, "saudade"))


if __name__ == "__main__":
    unittest.main()
