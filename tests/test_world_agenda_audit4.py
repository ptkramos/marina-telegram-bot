"""Auditoria #4 — agenda diária determinística e fonte única de estado.

Antes: a rotina era re-sorteada a cada snapshot stale (60 min). Na janela de
academia (15:00–21:00) ela ficava "treinando" horas seguidas e todo dia; a
disponibilidade lia o snapshot antigo (UNKNOWN na 1ª mensagem após silêncio);
o anúncio de saída escolhia sozinho o que anunciar.
"""
import json
import random
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from seed_academic_v36 import seed_academic
from world_state import RoutineEngine, WorldStateManager
from response_availability import ResponseAvailabilityPolicy


class AgendaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "agenda.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.engine = RoutineEngine(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _gym_candidate(self, moment):
        return next((c for c in self.engine.candidates(moment, has_class=False)
                     if c.routine_type == "gym"), None)

    def _gym_day(self):
        """Primeiro dia (sem aula) a partir de 26/09 em que há slot de academia."""
        day = date(2026, 9, 26)
        for _ in range(21):
            moment = datetime.combine(day, datetime.min.time()).replace(hour=16)
            cand = self._gym_candidate(moment)
            if cand and self.engine.slot_for(moment, cand, has_class=False):
                return day, self.engine.slot_for(moment, cand, has_class=False)
            day += timedelta(days=1)
        self.fail("nenhum dia com academia em 3 semanas")

    def _fresh_manager(self, seed):
        return WorldStateManager(self.db, routine=RoutineEngine(self.db, random.Random(seed)))

    def test_estado_nao_depende_do_rng(self):
        day, (start, _end) = self._gym_day()
        moment = start + timedelta(minutes=5)
        atividades = set()
        for seed in range(6):
            with self.db.get_connection() as conn:
                conn.execute("DELETE FROM world_state")
            atividades.add(self._fresh_manager(seed).resolve(moment, has_class=False)["activity"])
        self.assertEqual(atividades, {"treinando na academia"})

    def test_academia_no_maximo_um_slot_de_90_min_por_dia(self):
        day, _ = self._gym_day()
        minutos = 0
        t = datetime.combine(day, datetime.min.time()).replace(hour=15)
        while t.hour < 21:
            cands = self.engine.candidates(t, has_class=False)
            chosen, _ = self.engine.pick(t, cands, has_class=False)
            if chosen.routine_type == "gym":
                minutos += 5
            t += timedelta(minutes=5)
        self.assertGreater(minutos, 0)
        self.assertLessEqual(minutos, 90)

    def test_cota_semanal_de_academia_respeitada(self):
        row = self.engine._routine_row("gym_weekly")
        monday = date(2026, 9, 21)
        for week in range(8):
            dias = sum(self.engine.happens_on(monday + timedelta(days=7 * week + d), row)
                       for d in range(7))
            with self.subTest(week=week):
                self.assertTrue(3 <= dias <= 5, dias)

    def test_fica_no_slot_ate_o_fim_mesmo_com_conversa(self):
        """Antes: Patrick começava a conversar e o re-sorteio a mandava pra casa."""
        day, (start, end) = self._gym_day()
        manager = self._fresh_manager(1)
        first = manager.resolve(start + timedelta(minutes=1), has_class=False)
        self.assertEqual(first["activity"], "treinando na academia")
        self.assertIsNotNone(json.loads(first["source_json"])["slot_end"])
        quase_fim = end - timedelta(minutes=2)
        self.db.adicionar_mensagem("user", "oi amor", timestamp=(quase_fim - timedelta(minutes=1)).isoformat())
        self.assertEqual(manager.resolve(quase_fim, has_class=False)["id"], first["id"])
        depois = manager.resolve(end + timedelta(minutes=1), has_class=False)
        self.assertNotEqual(depois["activity"], "treinando na academia")

    def test_disponibilidade_ve_o_slot_na_primeira_mensagem_apos_silencio(self):
        day, (start, _end) = self._gym_day()
        # Snapshot antigo (de manhã) deixa o estado stale.
        self._fresh_manager(2).resolve(start - timedelta(hours=3), has_class=False)
        policy = ResponseAvailabilityPolicy(self.db)
        activity, _source, _sid, freshness, _ = policy._resolve_activity(start + timedelta(minutes=5))
        self.assertEqual((activity, freshness), ("GYM", "fresh"))
        # E o prompt, logo depois, lê exatamente o mesmo snapshot.
        prompt_state = self._fresh_manager(3).resolve(start + timedelta(minutes=6), has_class=False)
        self.assertEqual(prompt_state["activity"], "treinando na academia")


class TransitionAnnouncementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "agenda_tr.db")
        seed_world_bible(self.db)
        seed_academic(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_anuncio_so_dentro_do_slot_e_termina_com_ele(self):
        from proactivity_service import ProactivityService
        helper = AgendaTests("test_estado_nao_depende_do_rng")
        helper.db, helper.engine = self.db, RoutineEngine(self.db)
        day, (start, end) = helper._gym_day()
        service = ProactivityService.__new__(ProactivityService)
        service.db = self.db
        fora = datetime.combine(day, datetime.min.time()).replace(hour=15)
        if fora + timedelta(minutes=10) < start:
            intent = service._detect_transition_intent(fora)
            self.assertTrue(intent is None or intent["routine_type"] != "gym")
        intent = service._detect_transition_intent(start)
        self.assertIsNotNone(intent)
        self.assertEqual(intent["routine_type"], "gym")
        self.assertEqual(intent["end_at"], end.isoformat())
        self.assertIsNone(service._detect_transition_intent(end + timedelta(minutes=1)))


class ProactiveInstructionTests(unittest.TestCase):
    def test_instrucoes_proativas_em_portugues(self):
        """Auditoria #2 traduziu os prompts de processamento, mas não estes."""
        src = (Path(__file__).resolve().parent.parent / "proactivity_service.py").read_text(encoding="utf-8")
        for marcador in ("Daypart is", "Send a spontaneous", "Ask how it went",
                         "Ask lightly", "Continue the shared topic"):
            with self.subTest(marcador=marcador):
                self.assertNotIn(marcador, src)

    def test_contexto_espontaneo_nao_usa_snapshot_velho(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "neutral.db")
        seed_world_bible(db)
        seed_academic(db)
        from proactivity_service import ProactivityService
        service = ProactivityService.__new__(ProactivityService)
        service.db = db
        madrugada = datetime(2026, 9, 26, 3, 0)
        WorldStateManager(db).resolve(madrugada, has_class=False)
        tarde = datetime(2026, 9, 26, 14, 0)
        contexto = service._build_neutral_context(tarde, "tarde")
        self.assertNotIn("dormindo", contexto)


class AgendaConditionsTests(unittest.TestCase):
    """Patrick, 21/09: 'se ela tiver tempo, encaixa o passeio onde for mais
    cômodo' e 'tempo ruim, vontade de ir ou não pra academia se mantém?'."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "cond.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.engine = RoutineEngine(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _slots(self, day, routine_types, **kw):
        from academic_life import AcademicLife
        has_class = bool(AcademicLife(self.db).blocks_on(day))
        found = {}
        t = datetime.combine(day, datetime.min.time()).replace(hour=7)
        while t.hour < 21:
            for c in self.engine.candidates(t, has_class=has_class, **kw):
                if c.routine_type in routine_types:
                    slot = self.engine.slot_for(t, c, has_class=has_class)
                    if slot:
                        found.setdefault(c.routine_type, slot)
            t += timedelta(minutes=15)
        return has_class, found

    def test_milo_passeia_em_dia_de_aula_fora_do_horario_da_faculdade(self):
        from academic_life import AcademicLife
        for offset in range(7):
            day = date(2026, 9, 21) + timedelta(days=offset)
            has_class, found = self._slots(day, {"pet_walk", "gym"})
            if not has_class:
                continue
            with self.subTest(day=day):
                self.assertIn("pet_walk", found)
                walk = found["pet_walk"]
                blocks = AcademicLife(self.db).blocks_on(day)
                first = min(datetime.fromisoformat(b["start_at"]) for b in blocks)
                last = max(datetime.fromisoformat(b["end_at"]) for b in blocks)
                self.assertTrue(walk[1] <= first - timedelta(minutes=60)
                                or walk[0] >= last + timedelta(minutes=45), walk)
                if "gym" in found:
                    gym = found["gym"]
                    self.assertTrue(walk[1] <= gym[0] or walk[0] >= gym[1])

    def test_cansada_vai_menos_a_academia(self):
        def dias_de_academia(energy):
            total = 0
            for offset in range(56):
                t = datetime(2026, 9, 21, 15, 30) + timedelta(days=offset)
                gym = next(c for c in self.engine.candidates(t, has_class=False, energy=energy)
                           if c.routine_type == "gym")
                total += self.engine.slot_for(t, gym, has_class=False) is not None
            return total
        self.assertLess(dias_de_academia(0.25), dias_de_academia(0.7))

    def test_chuva_forte_troca_academia_de_rua_pela_do_predio(self):
        for offset in range(14):
            day = date(2026, 9, 21) + timedelta(days=offset)
            _, found = self._slots(day, {"gym", "gym_indoor"}, heavy_rain=True)
            if "gym_indoor" not in found:
                continue
            t = found["gym_indoor"][0] + timedelta(minutes=5)
            from academic_life import AcademicLife
            hc = bool(AcademicLife(self.db).blocks_on(day))
            chosen, _ = self.engine.pick(t, self.engine.candidates(t, has_class=hc, heavy_rain=True), has_class=hc)
            self.assertEqual(chosen.routine_type, "gym_indoor")
            return
        self.fail("nenhum dia de academia em 2 semanas")


if __name__ == "__main__":
    unittest.main()
