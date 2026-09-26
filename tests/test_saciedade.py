"""Saciedade e belisco (Patrick, 26/09): a fome cai em tempo real enquanto ela come; satisfeita ela larga
o prato, ou come tudo por gula e o excesso pesa; com fome em casa ela belisca."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import meals
from db import DatabaseManager
from meals import MealSlot, Meals
from seed_world_bible_v36 import seed_world_bible

T = datetime(2026, 9, 26, 20, 0)


class SaciedadeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "s.db")
        seed_world_bible(self.db)
        self.m = Meals(self.db)
        for alvo in ("_phase", "on_diet"):
            p = patch.object(Meals, alvo, return_value="" if alvo == "_phase" else False)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _jantar(self, fome, gula):
        slot = MealSlot("jantar", "meal:2026-09-26:jantar", T, 30, "casa", "yakisoba pedido no iFood")
        with patch.object(Meals, "hunger", return_value=fome), \
                patch("meals.random.Random.random", return_value=0.0 if gula else 0.99):
            return slot, self.m._record(slot, T)

    def test_com_fome_come_tudo(self):
        _, sac = self._jantar(0.9, gula=False)
        self.assertFalse(sac["larga"])
        self.assertEqual(sac["fim"], T + timedelta(minutes=30))
        self.assertEqual(sac["excesso"], 0.0)

    def test_sem_fome_larga_o_prato(self):
        _, sac = self._jantar(0.4, gula=False)
        self.assertTrue(sac["larga"])
        self.assertLess(sac["fim"], T + timedelta(minutes=30), "a refeição acaba antes")
        with self.db.get_connection() as conn:
            summary = conn.execute("SELECT summary FROM life_events").fetchone()[0]
        self.assertIn("largou o resto", summary)

    def test_gula_come_tudo_e_vira_excesso(self):
        _, sac = self._jantar(0.4, gula=True)
        self.assertFalse(sac["larga"])
        self.assertGreater(sac["excesso"], 0)
        with self.db.get_connection() as conn:
            summary = conn.execute("SELECT summary FROM life_events").fetchone()[0]
        self.assertIn("estufada", summary)
        self.assertLess(self.m.hunger(T + timedelta(minutes=31)), 0.05, "estufada: demora a ter fome")
        self.assertEqual(self.m.satiety_word(T + timedelta(minutes=40)), "estufada")

    def test_fome_cai_em_tempo_real(self):
        self._jantar(0.9, gula=False)
        inicio, meio, fim = (self.m.hunger(T + timedelta(minutes=m)) for m in (1, 15, 29))
        self.assertGreater(inicio, meio)
        self.assertGreater(meio, fim)
        self.assertEqual(self.m.satiety_word(T + timedelta(minutes=10)), "comendo")
        depois = [self.m.hunger(T + timedelta(hours=h)) for h in (1, 2, 3)]
        self.assertEqual(depois, sorted(depois), "depois de comer a fome volta a subir")

    def test_excesso_pesa_na_semana(self):
        base = self.m.weight()["kg"]
        self.m._save_weight({"kg": base, "week": "2026-W38"})
        with self.db.get_connection() as conn:
            for d in range(5):
                conn.execute("""INSERT INTO life_events(event_key,event_at,end_at,event_type,title,summary,source_type,
                                autonomy_level,metadata_json,created_at) VALUES (?,?,?,'meal','jantar','x','simulated',1,?,?)""",
                             (f"meal:e{d}", (T - timedelta(days=d)).isoformat(), T.isoformat(),
                              json.dumps({"excesso": 0.4}), T.isoformat()))
            conn.commit()
        with patch("meals.random.Random.uniform", return_value=0.0):
            self.m._weekly_weight(T)
        self.assertGreater(self.m.weight()["kg"], base)


class BeliscoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "b.db")
        seed_world_bible(self.db)
        self.m = Meals(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_com_fome_em_casa_belisca(self):
        now = datetime(2026, 9, 26, 16, 40)
        with patch.object(Meals, "hunger", return_value=0.7), \
                patch.object(Meals, "day_plan", return_value=[]), \
                patch.object(Meals, "_at_home", return_value=True):
            self.assertEqual(self.m._belisca(now, now - timedelta(days=1)), 1)
            self.assertEqual(self.m._belisca(now + timedelta(minutes=20), now - timedelta(days=1)), 0, "espaça")
        payload = json.loads(self.db.get_estado_relacional()["pending_transition_json"])
        self.assertEqual(payload["activity"], "beliscando em casa")
        with self.db.get_connection() as conn:
            meta = json.loads(conn.execute("SELECT metadata_json FROM life_events").fetchone()[0])
        self.assertEqual(meta["motivo"], "fome")

    def test_segura_pra_refeicao_perto(self):
        now = datetime(2026, 9, 26, 18, 40)
        jantar = MealSlot("jantar", "meal:2026-09-26:jantar", now + timedelta(minutes=30), 30, "casa", "x")
        with patch.object(Meals, "hunger", return_value=0.7), \
                patch.object(Meals, "day_plan", return_value=[jantar]), \
                patch.object(Meals, "_at_home", return_value=True):
            self.assertEqual(self.m._belisca(now, now - timedelta(days=1)), 0)

    def test_linha_do_tempo_mostra_beliscando(self):
        from agenda import Agenda
        self.assertEqual(Agenda.REFEICAO["lanche"], "Beliscando")
        self.assertEqual(meals.KIND_NAME["lanche"][1], "beliscando")


class PessoasNovasTest(unittest.TestCase):
    def test_proximidade_e_como_conheceu_guardado(self):
        from social_day import NPC_INDEX, SocialDay, Contact, proximidade
        self.assertEqual(proximidade("m"), "Conhecido")
        self.assertEqual(proximidade("f"), "Conhecida")
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "p.db")
        seed_world_bible(db)
        key = "npc_bruno_tavares"
        c = Contact(key=f"social:{key}", at=T, character_key=key, channel="presencial", topic="treino",
                    place_key="bodytech_sao_clemente")
        SocialDay(db)._record(c)
        painel = SocialDay(db).world_panel(T + timedelta(hours=1))
        bruno = next(p for p in painel["pessoas"] if p["nome"].startswith("Bruno"))
        self.assertEqual(bruno["quem"], "Conhecido")
        with db.get_connection() as conn:
            origem = json.loads(conn.execute("SELECT initial_state_json FROM world_characters WHERE canonical_key=?",
                                             (key,)).fetchone()[0])
        self.assertIn(NPC_INDEX[key][3], origem["como_conheceu"])
        self.assertIn("26/09", origem["como_conheceu"])


if __name__ == "__main__":
    unittest.main()


class EntregaDe26Test(unittest.TestCase):
    """26/09 16:39–16:41: chocolate registrado com ela voltando da academia a pé; o sanduíche que o
    Patrick mandou ficou sem saciedade."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "e.db")
        seed_world_bible(self.db)

    def _snap(self, at, activity, reason):
        from world_state import WorldStateManager
        WorldStateManager(self.db).states.add_snapshot({
            "state_date": at.date().isoformat(), "observed_at": at.isoformat(), "location_place_id": None,
            "location_region": "a caminho (Botafogo)" if reason == "commute" else "Botafogo", "activity": activity,
            "energy_level": 0.6, "weather_context_json": None, "current_plan_json": None,
            "source_json": {"reason": reason}})

    def test_lanche_com_ela_na_rua_acontece_quando_chega(self):
        dia = datetime(2026, 9, 26)
        lanche = MealSlot("lanche", "meal:2026-09-26:lanche:1", dia.replace(hour=16, minute=39), 6, "casa", "um chocolate")
        self._snap(dia.replace(hour=16, minute=30), "voltando da Bodytech pra casa a pé", "commute")
        self._snap(dia.replace(hour=16, minute=41), "em casa, olhando o Instagram (quarto)", "free_time")
        m = Meals(self.db)
        with patch.object(Meals, "day_plan", return_value=[lanche]), patch.object(Meals, "_floor",
                                                                                 return_value=dia), \
                patch.object(Meals, "_belisca", return_value=0), patch.object(Meals, "_weigh_in"):
            m.materialize(dia.replace(hour=16, minute=42))
        with self.db.get_connection() as conn:
            at = conn.execute("SELECT event_at FROM life_events WHERE event_key=?", (lanche.key,)).fetchone()[0]
        self.assertEqual(at[11:16], "16:42", "não foi às 16:39, na rua")

    def test_voltando_a_pe_e_fora_de_casa(self):
        self.assertTrue(Meals._fora({"activity": "voltando da Bodytech pra casa a pé", "source_json": {"reason": "commute"}}))
        self.assertFalse(Meals._fora({"activity": "em casa, olhando o Instagram (quarto)", "source_json": {}}))

    def test_presente_vira_refeicao_com_saciedade(self):
        import delivery
        t = datetime(2026, 9, 26, 16, 20)
        delivery.gift(self.db, what="Sanduíche natural de frango", restaurant="Megamatte", price=40,
                      eta_min=(20, 20), note="", now=t)
        with patch.object(Meals, "hunger", return_value=0.9):
            delivery.gift_tick(self.db, t + timedelta(minutes=21), can_receive=True)
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT end_at, metadata_json FROM life_events WHERE event_key LIKE 'meal:%:presente'").fetchone()
        self.assertIsNotNone(row["end_at"])
        self.assertEqual(json.loads(row["metadata_json"])["prato"], "Sanduíche natural de frango")
