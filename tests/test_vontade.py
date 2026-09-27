"""Agenda única (Patrick, 26/09): o que ela decide na hora vira item da mesma agenda das saídas —
preparo a partir da decisão, caminho, lá (com o que consome, do cardápio real) e volta."""
import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from agenda import Agenda
from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from vontade import Vontade, no

T = datetime(2026, 9, 26, 16, 0)   # sábado, sem aula


class VontadeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "v.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        for alvo, kw in (("academia.Academia.plano", {"return_value": None}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("meals.Meals.day_plan", {"return_value": []}),
                         ("sleep_plan.SleepPlan.in_bed", {"return_value": False}),
                         # 27/09: o random.random()=0 dos testes sorteava uma virose, e doente (agenda viva) ela só
                         # quer farmácia — o corpo fica saudável aqui
                         ("emotion.EmotionEngine._discomfort", {"return_value": (0.0, "")})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        from seed_academic_v36 import seed_academic
        from social_day import SocialDay
        seed_academic(self.db)
        SocialDay(self.db)._floor(T - timedelta(hours=1))      # vida registrada começa antes

    def _sai(self, tipo):
        with patch("vontade.random.Random.random", return_value=0.0), \
                patch("vontade.random.Random.choices", side_effect=lambda pop, weights=None: [
                    tipo if tipo in pop else pop[0]]):
            return Vontade(self.db).talvez(T)

    def test_cafe_por_vontade_vira_etapas(self):
        self.assertIsNotNone(self._sai("cafe"))
        etapas = Agenda(self.db).etapas(T.date(), T)
        self.assertEqual([e.tipo for e in etapas], ["arrumando", "caminho", "la", "voltando"])
        prep, _, la, _ = etapas
        self.assertEqual(prep.inicio, T, "se arruma a partir da hora em que decidiu")
        self.assertTrue(prep.linha2.startswith("Vai sair pr"))
        self.assertEqual([p.texto for p in prep.passos][:2], ["Trocando de roupa", "Pegando a bolsa"])
        self.assertTrue(la.passos and all(p.valor for p in la.passos), "consumo do cardápio real, com preço")
        with self.db.get_connection() as conn:
            ev = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'vontade:%:decidiu'").fetchone()[0]
        self.assertIn("Deu vontade e foi", ev)

    def test_consumo_sai_do_saldo(self):
        import financas
        from consumo import Consumo
        financas._save(self.db, financas._init({}, T))
        saldo = financas._load(self.db)["saldo"]
        self._sai("cafe")
        la = next(e for e in Agenda(self.db).etapas(T.date(), T) if e.tipo == "la")
        Consumo(self.db).materialize(la.fim)
        financas.materialize(self.db, la.fim)
        self.assertEqual(financas._load(self.db)["saldo"], saldo - sum(p.valor for p in la.passos))

    def test_passeio_do_milo_e_o_mundo_acompanha(self):
        self._sai("milo")
        etapas = Agenda(self.db).etapas(T.date(), T)
        self.assertEqual([e.titulo for e in etapas], ["Se arrumando", "A caminho", "Na Enseada", "Voltando pra casa"])
        self.assertEqual([p.texto for p in etapas[0].passos][:2], ["Colocando a coleira", "Pegando os saquinhos"])
        from world_state import WorldStateManager
        la = etapas[2]
        snap = WorldStateManager(self.db).resolve(la.inicio + timedelta(minutes=3), force=True)
        self.assertEqual(snap["activity"], "Passeando com o Milo na Enseada")
        prep = WorldStateManager(self.db).resolve(T + timedelta(minutes=1), force=True)
        self.assertTrue(prep["activity"].startswith("se arrumando pra sair"), prep["activity"])

    def test_nao_sai_com_compromisso_logo(self):
        from calendar_world import CalendarWorld
        CalendarWorld(self.db).create_commitment(
            source_key="outing:2026-09-26:0", event_type="social", description="Saindo com a Bia",
            start_at=T + timedelta(minutes=90), end_at=T + timedelta(hours=4), location_key="quartinho_bar")
        self.assertIsNone(self._sai("cafe"))

    def test_limite_por_dia_e_sem_repetir_tipo(self):
        for n in range(3):
            with patch("vontade.random.Random.random", return_value=0.0):
                Vontade(self.db).talvez(T.replace(hour=8 + 4 * n))
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT metadata_json FROM eventos_pendentes WHERE source_key LIKE 'vontade:%'").fetchall()
        tipos = [json.loads(r[0])["tipo"] for r in rows]
        self.assertLessEqual(len(tipos), 3)
        self.assertEqual(len(tipos), len(set(tipos)))

    def test_artigo_do_lugar(self):
        self.assertEqual(no("Estação do Açaí"), "na Estação do Açaí")
        self.assertEqual(no("Starbucks"), "no Starbucks")
        self.assertEqual(no("Drogarias Pacheco"), "na Drogarias Pacheco")

    def test_disponibilidade(self):
        from response_availability import ResponseAvailabilityPolicy
        m = ResponseAvailabilityPolicy(self.db)._map_place_activity
        self.assertEqual(m("loja_starbucks_bf", "Tomando um café no Starbucks"), "OUT_SOLO")
        self.assertEqual(m("novamed_botafogo", "Na consulta na Novamed"), "CLASS")
        self.assertEqual(m("hospital_samaritano_botafogo", "No pronto-atendimento do Samaritano"), "CLASS")
        self.assertEqual(m("enseada_botafogo", "Passeando com o Milo na Enseada"), "PET_WALK")


class MedicoTest(unittest.TestCase):
    def test_consulta_vira_item_com_uber(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "m.db")
        seed_world_bible(db)
        at = T.replace(hour=15)
        Vontade(db).medico(at, "o pai", T.replace(hour=13))
        with patch("academia.Academia.plano", return_value=None), \
                patch("academia.PasseioMilo.plano", return_value=None), \
                patch("meals.Meals.day_plan", return_value=[]):
            etapas = Agenda(db).etapas(T.date(), T)
        self.assertEqual([e.titulo for e in etapas], ["Se arrumando", "A caminho", "Na Novamed", "Voltando pra casa"])
        self.assertEqual(etapas[1].como, "Uber")
        self.assertEqual([p.texto for p in etapas[2].passos], ["Na recepção", "Na consulta", "Pegando a receita"])


class MiloPlanejadoTest(unittest.TestCase):
    def test_conversa_nao_cancela_o_passeio_da_manha(self):
        from world_state import RoutineEngine
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "p.db")
        seed_world_bible(db)
        eng = RoutineEngine(db)
        dia = T.date()
        plano = {"inicio": T.replace(hour=9), "fim": T.replace(hour=9, minute=30), "onde": "rua"}
        with patch("academia.PasseioMilo.plano", return_value=plano):
            t = plano["inicio"] + timedelta(minutes=5)
            cands = eng.candidates(t, has_class=False, conversation_active=True)
            walk = next(c for c in cands if c.routine_type == "pet_walk")
            self.assertEqual(eng.slot_for(t, walk, has_class=False), (plano["inicio"], plano["fim"]))


if __name__ == "__main__":
    unittest.main()


class ProntoAtendimentoTest(unittest.TestCase):
    def test_virose_vai_pro_samaritano(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "s.db")
        seed_world_bible(db)
        at = T.replace(hour=15)
        Vontade(db).medico(at, "o pai", T.replace(hour=13), kind="virose")
        with patch("academia.Academia.plano", return_value=None), \
                patch("academia.PasseioMilo.plano", return_value=None), \
                patch("meals.Meals.day_plan", return_value=[]):
            la = next(e for e in Agenda(db).etapas(T.date(), T) if e.tipo == "la")
        self.assertEqual(la.titulo, "No Samaritano")
        self.assertEqual(la.passos[0].texto, "Na triagem")
        from health import onde_consulta, PLANO
        self.assertEqual(onde_consulta("virose")[0], "hospital_samaritano_botafogo")
        self.assertIn("Bradesco Saúde Top Nacional", PLANO)
