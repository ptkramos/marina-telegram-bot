"""Atraso de verdade (Patrick, 28/09): despertador, hora de sair e caminho empurram a saída e a chegada; o compromisso
começa sem ela; o card, o prompt e o chat sabem; atraso grande ela pesa pelo que sente."""
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

import commute
from academic_life import AcademicLife
from agenda import Agenda
from agenda_viva import AgendaViva, Disposicao
from atraso import Atraso, _load
from calendar_world import CalendarWorld
from college import College
from commute import Commute
from db import DatabaseManager
from emotion import Episode, Feeling
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from sleep_plan import SleepPlan


def sentindo(now, *, energy=0.7, slept=7.5, valence=0.65, battery=0.7, episodes=(), hurt=0.0) -> Feeling:
    return Feeling(now=now, energy=energy, hours_slept=slept, awake_since=None, hunger=0.3, discomfort=0.0,
                   discomfort_why="", cycle_phase="folicular", valence=valence, arousal=0.5, playfulness=0.5,
                   episodes=list(episodes), bond={"hurt": hurt}, missing=0.2, social_battery=battery)


def ep(family, kind, i, at):
    return Episode(1, family, kind, i, i, "x", None, at - timedelta(hours=1), False)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "a.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        for alvo, kw in (("academia.Academia.plano", {"return_value": None}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("meals.Meals.day_plan", {"return_value": []}),
                         ("milo.Milo.day_plan", {"return_value": []}),
                         ("commute.Commute._heavy_rain", {"return_value": False}),
                         ("commute.INCIDENT_CHANCE", {"new": 0.0}),
                         ("atraso.ESQUECEU_CHANCE", {"new": 0.0}),
                         ("atraso.ESQUECEU_CHANCE_CORRENDO", {"new": 0.0})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        self.a = Atraso(self.db)

    def sente(self, **kw):
        for alvo in (Atraso, Disposicao):
            p = patch.object(alvo, "_feeling", side_effect=lambda now, kw=kw: sentindo(now, **kw))
            p.start()
            self.addCleanup(p.stop)

    def eventos(self, like):
        with self.db.get_connection() as conn:
            return [r[0] for r in conn.execute("SELECT summary FROM life_events WHERE event_key LIKE ?", (like,))]

    def ida(self, day, planejado=False, sufixo=":puc:ida"):
        return next(l for l in Commute(self.db).legs_on(day, planejado=planejado) if l.key.endswith(sufixo))

    def dia_de_aula(self):
        c = College(self.db)
        start = date(2026, 9, 28)
        dues = {a["due"] for a in c.assignments(start, horizon_days=34)}
        return next(start + timedelta(days=i) for i in range(35)
                    if AcademicLife(self.db).blocks_on(start + timedelta(days=i))
                    and (start + timedelta(days=i)).isoformat() not in dues)

    def acorda(self, wake, over):
        for nome, valor in (("wake", wake), ("overslept", over)):
            p = patch.object(SleepPlan, nome, return_value=valor)
            p.start()
            self.addCleanup(p.stop)


class DespertadorTest(Base):
    def setUp(self):
        super().setUp()
        self.sente()
        self.day = self.dia_de_aula()
        self.plan = self.ida(self.day, planejado=True)
        self.wake = self.plan.start - timedelta(minutes=20)       # 20 min pra se arrumar: precisa de 30
        self.acorda(self.wake, 25)

    def test_perdeu_o_despertador_sai_e_chega_mais_tarde(self):
        self.assertEqual(self.ida(self.day).start, self.plan.start, "antes de acordar, nada mudou")
        self.a.materialize(self.wake + timedelta(minutes=1))
        self.assertEqual(self.ida(self.day).start, self.plan.start + timedelta(minutes=10), "acordou: já sabe")
        e = _load(self.db, self.day)["legs"][self.plan.key]
        self.assertEqual(e["acordou"]["min"], 10)
        self.a.materialize(self.plan.start + timedelta(minutes=10))
        real = self.ida(self.day)
        self.assertEqual(real.start, self.plan.start + timedelta(minutes=10))
        self.assertEqual(real.end, self.plan.end + timedelta(minutes=10))
        self.assertEqual(real.atraso, 10)
        # o sono continua planejando pela saída de verdade planejada
        self.assertEqual(self.ida(self.day, planejado=True).start, self.plan.start)

    def test_a_aula_comeca_sem_ela_e_na_chegada_vira_acontecimento(self):
        self.a.materialize(self.wake + timedelta(minutes=1))
        self.a.materialize(self.plan.start + timedelta(minutes=10))
        dentro = self.plan.end + timedelta(minutes=5)             # a aula já começou, ela ainda no caminho
        self.assertIsNone(CalendarWorld(self.db).current(dentro, include_academic=True))
        depois = self.plan.end + timedelta(minutes=11)
        self.assertIsNotNone(CalendarWorld(self.db).current(depois, include_academic=True))
        self.a.materialize(depois)
        ev = self.eventos("atraso:%")
        self.assertEqual(len(ev), 1)
        self.assertIn("Chegou 10 min atrasada na aula de", ev[0])
        self.assertIn("perdeu o despertador", ev[0])

    def test_card_mostra_a_saida_e_a_chegada_de_verdade(self):
        self.a.materialize(self.wake + timedelta(minutes=1))
        self.a.materialize(self.plan.start + timedelta(minutes=10))
        etapas = Agenda(self.db).etapas(self.day, self.plan.start + timedelta(minutes=12))
        prep = next(e for e in etapas if e.tipo == "arrumando")
        self.assertEqual(prep.inicio, self.wake, "o Se arrumando existe desde que ela acordou")
        self.assertIn("(atrasada)", prep.linha2)
        self.assertTrue(any(p.aviso and p.texto == "Perdeu o despertador" for p in prep.passos))
        caminho = next(e for e in etapas if e.tipo == "caminho")
        self.assertIn("10min atrasada", caminho.linha2)
        la = next(e for e in etapas if e.tipo == "la")
        self.assertEqual(la.inicio, self.plan.end + timedelta(minutes=10))
        self.assertTrue(any(p.aviso and p.texto == "Chegou 10min atrasada" for p in la.passos))

    def test_aula_e_coisa_de_contar_pro_patrick(self):
        self.a.materialize(self.wake + timedelta(minutes=1))
        aviso = self.a.aviso(self.wake + timedelta(minutes=2))
        self.assertIsNotNone(aviso)
        self.assertIn("perdeu o despertador", aviso["detail"])
        self.a.marca_aviso_enviado(self.wake + timedelta(minutes=2))
        self.assertIsNone(self.a.aviso(self.wake + timedelta(minutes=3)))
        texto = "\n".join(self.a.prompt_lines(self.wake + timedelta(minutes=3)))
        self.assertIn("ATRASADA", texto)
        self.assertIn("já avisou o Patrick", texto)

    def test_sem_atraso_quando_da_tempo_de_correr(self):
        with patch.object(SleepPlan, "wake", return_value=self.plan.start - timedelta(minutes=40)):
            self.a.materialize(self.plan.start - timedelta(minutes=39))
            self.a.materialize(self.plan.start + timedelta(minutes=1))
        self.assertEqual(self.ida(self.day).start, self.plan.start)
        self.assertEqual(self.a.prompt_lines(self.plan.start + timedelta(minutes=2)), [])


class AtrasoGrandeTest(Base):
    def setUp(self):
        super().setUp()
        self.day = self.dia_de_aula()
        self.plan = self.ida(self.day, planejado=True)
        self.acorda(self.plan.start + timedelta(minutes=15), 30)  # acordou depois da hora de sair: 45 min

    def test_cansada_desiste_das_aulas_que_perderia(self):
        self.sente(energy=0.35, slept=5.0, battery=0.2, valence=0.45)
        agora = self.plan.start + timedelta(minutes=16)
        self.a.materialize(agora)
        e = _load(self.db, self.day)["legs"][self.plan.key]
        self.assertTrue(e.get("desistiu"))
        self.assertTrue(any("ia chegar 45 min atrasada" in s for s in self.eventos("agenda:faltou:%")))
        self.assertIsNone(self.a.aviso(agora), "quem conta é a agenda viva (desistiu)")
        self.assertIn("ia chegar", AgendaViva(self.db).aviso(agora)["motivo"])

    def test_animada_vai_mesmo_atrasada(self):
        self.sente(energy=0.85, slept=8.0, battery=0.8, valence=0.75)
        self.a.materialize(self.plan.start + timedelta(minutes=16))
        e = _load(self.db, self.day)["legs"][self.plan.key]
        self.assertTrue(e.get("pesou"))
        self.assertFalse(e.get("desistiu"))
        self.assertEqual(self.eventos("agenda:faltou:%"), [])


class RoleTest(Base):
    SAB = date(2026, 10, 3)

    def setUp(self):
        super().setUp()
        p = patch("academic_life.AcademicLife.blocks_on", return_value=[])
        p.start()
        self.addCleanup(p.stop)
        ini = datetime.combine(self.SAB, time(21, 0))
        CalendarWorld(self.db).create_commitment(
            source_key="outing:2026-10-03:c1", event_type="social", description="Saindo com a Bia no Quartinho Bar",
            start_at=ini, end_at=ini + timedelta(hours=3), location_key="quartinho_bar",
            metadata={"friends": ["bia_andrade"], "origin": "convite"})
        self.plan = self.ida(self.SAB, planejado=True, sufixo=":ida")

    def test_insegura_troca_de_roupa_e_atrasa_de_verdade(self):
        self.sente(episodes=(ep("vergonha", "inseguranca", 0.5, datetime.combine(self.SAB, time(20, 0))),))
        self.a.materialize(self.plan.start + timedelta(minutes=1))
        real = self.ida(self.SAB, sufixo=":ida")
        self.assertGreater(real.saida_extra, 0)
        self.assertEqual(real.start, self.plan.start + timedelta(minutes=real.saida_extra))
        self.assertIn("Trocou de roupa três vezes", [t for _, t in real.avisos])
        prep = next(e for e in Agenda(self.db).etapas(self.SAB, real.start - timedelta(minutes=1))
                    if e.tipo == "arrumando")
        self.assertEqual(prep.fim, real.start)
        antes = [p.inicio for p in prep.passos if not p.aviso and p.inicio < self.plan.start]
        self.assertTrue(antes, "os passos de antes da hora de sair ficam onde estavam")

    def test_de_bom_humor_sai_na_hora_e_atrasinho_de_role_nao_vira_aviso(self):
        self.sente()
        self.a.materialize(self.plan.start + timedelta(minutes=1))
        self.assertEqual(self.ida(self.SAB, sufixo=":ida").start, self.plan.start)
        self.assertIsNone(self.a.aviso(self.plan.start + timedelta(minutes=2)))

    def test_imprevisto_do_caminho_empurra_a_chegada_so_depois_de_acontecer(self):
        self.sente()
        with patch.object(commute, "INCIDENT_CHANCE", 1.0), \
             patch.object(commute, "INCIDENTS", {"uber": ["o motorista do uber errou o caminho"]}):
            plan = self.ida(self.SAB, planejado=True, sufixo=":ida")
            self.a.materialize(plan.start + timedelta(minutes=1))
            real = self.ida(self.SAB, sufixo=":ida")
            self.assertEqual(real.end, plan.end + timedelta(minutes=8))
            antes = next(e for e in Agenda(self.db).etapas(self.SAB, plan.incident_at - timedelta(minutes=1))
                         if e.tipo == "caminho")
            self.assertNotIn("atrasada", antes.linha2)
            depois = next(e for e in Agenda(self.db).etapas(self.SAB, plan.incident_at + timedelta(minutes=1))
                          if e.tipo == "caminho")
            self.assertIn("8min atrasada", depois.linha2)


if __name__ == "__main__":
    unittest.main()
