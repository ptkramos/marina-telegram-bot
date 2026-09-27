"""Bugs abertos do mundo, limpos em 27/09 (frente do mundo), com os horários reais da produção.

- Belisco × portaria (26/09, 16:40): chegou da academia com fome e beliscou um chocolate, com o sanduíche que o
  Patrick mandou esperando na portaria desde 16:26.
- "Banhou já?" → "Ainda não" (27/09, 01:57) com banho às 00:31: o banho recente não era fato no prompt.
- Acordou 09:12 "acordando e tomando café" e o café da manhã planejado foi 10:37.
- "Montou looks" até 15:11 com a academia às 14:53; música atravessando o banho: o bloco em casa não era cortado.
- Convite da Bia registrado às 04:19 (a hora do reset), com ela dormindo.
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import delivery
from db import DatabaseManager
from meals import MealSlot, Meals
from seed_world_bible_v36 import seed_world_bible
from tempo_livre import Bloco, TempoLivre


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "m.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()


class BeliscoPortariaTest(Base):
    NOW = datetime(2026, 9, 26, 16, 40)

    def _belisca(self):
        with patch.object(Meals, "hunger", return_value=0.9), \
                patch.object(Meals, "day_plan", return_value=[]), \
                patch.object(Meals, "_at_home", return_value=True):
            return Meals(self.db)._belisca(self.NOW, self.NOW - timedelta(days=1))

    def test_presente_na_portaria_segura_o_belisco(self):
        delivery.gift(self.db, what="Sanduíche natural de frango", restaurant="Megamatte", price=40,
                      eta_min=(6, 6), note="", now=datetime(2026, 9, 26, 16, 20))
        delivery.gift_tick(self.db, datetime(2026, 9, 26, 16, 26), can_receive=False, why_not="fora")
        self.assertEqual(self._belisca(), 0)

    def test_pedido_dela_chegando_segura_o_belisco(self):
        delivery._save(self.db, {"by": "marina", "what": "açaí", "ordered_at": "2026-09-26T16:20:00",
                                 "eta_at": "2026-09-26T17:05:00", "arrived_at": None})
        self.assertEqual(self._belisca(), 0)

    def test_sem_nada_chegando_belisca(self):
        self.assertEqual(self._belisca(), 1)


class BanhoNoPromptTest(Base):
    def _banho(self, ini, fim, lavou=True):
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                            autonomy_level,importance,participants_json,share_worthy,created_at)
                            VALUES (?,?,'routine','banho',?,'simulated',1,0.05,'["marina"]',0.1,?)""",
                         (f"banho:{ini:%Y-%m-%dT%H%M}", ini.isoformat(),
                          f"Tomou banho{' e lavou o cabelo' if lavou else ''} ({ini:%H:%M}–{fim:%H:%M}).",
                          ini.isoformat()))
            conn.commit()

    def _ctx(self):
        from world_context import WorldContextBuilder
        return WorldContextBuilder.__new__(WorldContextBuilder)

    def test_banho_recente_vira_fato(self):
        self._banho(datetime(2026, 9, 27, 0, 31), datetime(2026, 9, 27, 1, 12))
        ctx = self._ctx()
        ctx.db = self.db
        linha = ctx._banho(datetime(2026, 9, 27, 1, 57))
        self.assertIn("[BANHO — FATO]", linha)
        self.assertIn("das 00:31 às 01:12", linha)
        self.assertIn("lavou o cabelo", linha)
        self.assertIn("há 45 min", linha)

    def test_no_banho_ou_banho_antigo_nao_entra(self):
        self._banho(datetime(2026, 9, 27, 0, 31), datetime(2026, 9, 27, 1, 12))
        ctx = self._ctx()
        ctx.db = self.db
        self.assertIsNone(ctx._banho(datetime(2026, 9, 27, 0, 50)), "ainda no banho")
        self.assertIsNone(ctx._banho(datetime(2026, 9, 27, 10, 0)), "mais de 8 h")


class AcordandoTest(Base):
    def _cafe(self, at):
        return [MealSlot("cafe", "meal:2026-09-27:cafe", at, 40, "casa", "pão na chapa")]

    def test_cafe_mais_tarde_nao_e_tomando_cafe(self):
        from world_state import RoutineEngine
        with patch.object(Meals, "day_plan", return_value=self._cafe(datetime(2026, 9, 27, 10, 37))):
            txt = RoutineEngine(self.db)._acordando(datetime(2026, 9, 27, 9, 12))
        self.assertNotIn("tomando café", txt)
        self.assertIn("10:37", txt)

    def test_cafe_agora_e_tomando_cafe(self):
        from world_state import RoutineEngine
        with patch.object(Meals, "day_plan", return_value=self._cafe(datetime(2026, 9, 27, 9, 15))):
            self.assertEqual(RoutineEngine(self.db)._acordando(datetime(2026, 9, 27, 9, 12)), "acordando e tomando café")


class BlocoInterrompidoTest(Base):
    def _guarda(self, b: Bloco):
        tl = TempoLivre(self.db)
        st = tl._state()
        st.setdefault(tl._dia(b.inicio).isoformat(), {})["0"] = {
            **b.__dict__, "inicio": b.inicio.isoformat(), "fim": b.fim.isoformat()}
        tl._save(st, b.inicio)
        tl._registra(b, b.inicio)

    def test_banho_corta_a_musica(self):
        ini = datetime(2026, 9, 26, 22, 0)
        faixas = [{"nome": f"F{i}", "artista": "Dua Lipa", "album": "", "ms": 200000, "id": i, "dele": False,
                   "at": (ini + timedelta(minutes=4 * i)).isoformat()} for i in range(10)]
        self._guarda(Bloco("livre:2026-09-26:0", "musica", "Ouvindo Dua Lipa", "quarto", "som", False, ini,
                           ini + timedelta(minutes=40), False, faixas, None))
        tl = TempoLivre(self.db)
        self.assertTrue(tl.interrompe(ini + timedelta(minutes=13), ini + timedelta(minutes=15)))
        b = tl.do_dia(ini)[0]
        self.assertEqual(b.fim, ini + timedelta(minutes=13))
        self.assertEqual([f["nome"] for f in b.faixas], ["F0", "F1", "F2", "F3"])
        with self.db.get_connection() as conn:
            summary = conn.execute("SELECT summary FROM life_events WHERE event_key='livre:2026-09-26:0'").fetchone()[0]
        self.assertIn("\"F3\"", summary)
        self.assertIsNone(tl.atual(ini + timedelta(minutes=20)))

    def test_bloco_nao_passa_do_se_arrumando(self):
        from agenda import Agenda, Etapa
        prep = Etapa.__new__(Etapa)
        prep.inicio = datetime(2026, 9, 26, 14, 53)
        with patch.object(Agenda, "etapas", return_value=[prep]), patch.object(Meals, "day_plan", return_value=[]):
            fim = TempoLivre(self.db)._ate(datetime(2026, 9, 26, 14, 20), datetime(2026, 9, 26, 15, 11))
        self.assertEqual(fim, datetime(2026, 9, 26, 14, 53))

    def test_resolve_corta_o_bloco_quando_comeca_outra_coisa(self):
        ini = datetime(2026, 9, 26, 14, 20)
        self._guarda(Bloco("livre:2026-09-26:0", "looks", "Montando looks", "closet", "", False, ini,
                           datetime(2026, 9, 26, 15, 11), False, None, None))
        from seed_academic_v36 import seed_academic
        from world_state import WorldStateManager
        seed_academic(self.db)
        prep = {"activity": "se arrumando pra academia (colocando roupa de treino)", "place_key": "marina_apartment",
                "start_at": "2026-09-26T14:53:00", "end_at": "2026-09-26T15:05:00"}
        with patch.object(WorldStateManager, "_getting_ready", return_value=prep), \
                patch("academia.Academia.plano", return_value=None), \
                patch("academia.PasseioMilo.plano", return_value=None), \
                patch("meals.Meals.day_plan", return_value=[]), \
                patch("meals.Meals.hunger", return_value=0.2), \
                patch("sleep_plan.SleepPlan.in_bed", return_value=False):
            snap = WorldStateManager(self.db).resolve(datetime(2026, 9, 26, 14, 56), energy=0.7, force=True)
        self.assertTrue(snap["activity"].startswith("se arrumando"), snap["activity"])
        self.assertEqual(TempoLivre(self.db).do_dia(ini)[0].fim, datetime(2026, 9, 26, 14, 53))


class ConviteAoAcordarTest(Base):
    def test_convite_de_antes_do_reset_e_visto_ao_acordar(self):
        from social_day import SocialDay
        from sleep_plan import SleepPlan
        with patch.object(SleepPlan, "wake", return_value=datetime(2026, 9, 26, 9, 5)):
            visto = SocialDay(self.db)._visto_ao_acordar(datetime(2026, 9, 26, 4, 19), datetime(2026, 9, 26, 21, 0))
        self.assertEqual(visto, datetime(2026, 9, 26, 9, 5))

    def test_reset_de_tarde_fica_na_hora_do_reset(self):
        from social_day import SocialDay
        from sleep_plan import SleepPlan
        with patch.object(SleepPlan, "wake", return_value=datetime(2026, 9, 26, 9, 5)):
            visto = SocialDay(self.db)._visto_ao_acordar(datetime(2026, 9, 26, 15, 0), datetime(2026, 9, 26, 21, 0))
        self.assertEqual(visto, datetime(2026, 9, 26, 15, 0))


if __name__ == "__main__":
    unittest.main()
