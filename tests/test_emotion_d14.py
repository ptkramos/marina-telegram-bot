"""Fase D14a — núcleo do motor emocional (corpo, episódios com causa, humor, vínculo)."""
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import emotion
from db import DatabaseManager
from emotion import EmotionEngine, apply_planner_deltas

NOW = datetime(2026, 9, 23, 16, 0)


class EmotionCoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "emo.db")
        self.engine = EmotionEngine(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _sleep(self, slept, awake_since, debt=0.0, napped=False):
        return patch.object(EmotionEngine, "_sleep_facts", return_value=(slept, awake_since, debt, napped))

    # ---------------------------------------------------------------- corpo --
    def test_energy_comes_from_the_body_not_from_chat(self):
        with self._sleep(8.0, NOW.replace(hour=8)), patch.object(EmotionEngine, "_cycle", return_value=("", 0)):
            rested = self.engine.energy(NOW)
        with self._sleep(5.5, NOW.replace(hour=5), debt=3.0), patch.object(EmotionEngine, "_cycle", return_value=("", 0)):
            wrecked = self.engine.energy(NOW)
        self.assertGreater(rested, 0.7)
        self.assertLess(wrecked, 0.4, "dormiu 5h30, acordada desde as 5h, noites curtas antes")

    def test_the_day_weighs_and_a_nap_helps(self):
        with patch.object(EmotionEngine, "_cycle", return_value=("", 0)):
            with self._sleep(7.5, NOW.replace(hour=7)):
                morning = self.engine.energy(NOW.replace(hour=10))
                night = self.engine.energy(NOW.replace(hour=23))
            with self._sleep(7.5, NOW.replace(hour=7), napped=True):
                night_after_nap = self.engine.energy(NOW.replace(hour=23))
        self.assertGreater(morning, night)
        self.assertGreater(night_after_nap, night)

    def test_reentry_uses_the_stored_value_instead_of_looping(self):
        emotion._guard.busy = True
        try:
            self.assertEqual(self.engine.energy(NOW), self.engine._stored("energy", 0.7))
        finally:
            emotion._guard.busy = False

    # ------------------------------------------------------------ episódios --
    def test_feeling_has_a_cause_and_fades(self):
        self.assertTrue(self.engine.feel("raiva", "irritacao", 0.7, "o motorista do uber errou o caminho", NOW,
                                         source_key="commute:x"))
        self.assertFalse(self.engine.feel("raiva", "irritacao", 0.7, "de novo", NOW, source_key="commute:x"),
                         "a mesma causa não se sente duas vezes")
        now_ep = self.engine.episodes(NOW)[0]
        self.assertEqual((now_ep.word, now_ep.cause), ("irritada", "o motorista do uber errou o caminho"))
        later = self.engine.episodes(NOW + timedelta(minutes=90))[0]
        self.assertAlmostEqual(later.intensity, 0.35, places=2)   # meia-vida da raiva: 90 min
        self.assertEqual(self.engine.episodes(NOW + timedelta(hours=8)), [])

    def test_sticky_worry_only_fades_after_the_cause_resolves(self):
        self.engine.feel("medo", "ansiedade", 0.6, "entrega do trabalho de sexta", NOW, source_key="d7:entrega",
                         sticky=True)
        self.assertAlmostEqual(self.engine.episodes(NOW + timedelta(hours=20))[0].intensity, 0.6, places=2)
        self.engine.resolve("d7:entrega", NOW + timedelta(hours=20))
        self.assertLess(self.engine.episodes(NOW + timedelta(hours=26))[0].intensity, 0.3)

    # --------------------------------------------------------------- humor --
    def test_anger_lowers_mood_and_raises_arousal(self):
        with self._sleep(8.0, NOW.replace(hour=8)), patch.object(EmotionEngine, "_cycle", return_value=("", 0)), \
             patch.object(EmotionEngine, "_hunger", return_value=0.3):
            calm = self.engine.feeling(NOW)
            self.engine.feel("raiva", "irritacao", 0.9, "trânsito parado na Lagoa", NOW)
            angry = self.engine.feeling(NOW)
        self.assertLess(angry.valence, calm.valence)
        self.assertGreater(angry.arousal, calm.arousal)
        self.assertLess(angry.playfulness, calm.playfulness)

    def test_tpm_is_moderate(self):
        with self._sleep(8.0, NOW.replace(hour=8)), patch.object(EmotionEngine, "_hunger", return_value=0.3):
            with patch.object(EmotionEngine, "_cycle", return_value=("folicular", 8)):
                normal = self.engine.feeling(NOW)
            with patch.object(EmotionEngine, "_cycle", return_value=("tpm", 25)):
                tpm = self.engine.feeling(NOW)
        self.assertLess(tpm.valence, normal.valence)
        self.assertLess(normal.valence - tpm.valence, 0.15, "moderada, não caricatura")

    # -------------------------------------------------------------- vínculo --
    def test_planner_only_moves_the_bond_and_slowly(self):
        applied = apply_planner_deltas(self.db, {"affection": 0.05, "energy": 0.05, "playfulness": 0.05,
                                                 "social_battery": -0.02}, now=NOW)
        self.assertEqual(set(applied), {"affection", "social_battery"})
        self.assertAlmostEqual(applied["affection"], 0.02)

    def test_hurt_starts_at_zero(self):
        self.assertEqual(self.engine.bond()["hurt"], 0.0)
        self.db.ajustar_emocao("hurt", 0.3, now=NOW)
        self.assertAlmostEqual(self.engine.bond()["hurt"], 0.3, places=1)

    # --------------------------------------------------------------- prompt --
    def test_prompt_shows_cause_in_words_never_numbers(self):
        with self._sleep(5.5, NOW.replace(hour=5), debt=2.0), patch.object(EmotionEngine, "_cycle", return_value=("", 0)):
            self.engine.feel("raiva", "irritacao", 0.8, "o uber errou o caminho", NOW)
            lines = "\n".join(self.engine.prompt_lines(NOW))
        self.assertIn("irritada — o uber errou o caminho", lines)
        self.assertIn("exausta, dormiu só 5h30", lines)
        self.assertIn("nunca diga", lines)
        self.assertIsNone(re.search(r"\d\.\d", lines), "o modelo recebe palavras, não números")

    def test_summary_for_patrick_lists_every_layer(self):
        text = self.engine.summary(NOW)
        for part in ("Corpo:", "Humor:", "Sentindo", "Com o Patrick:"):
            self.assertIn(part, text)


class WorldFeelsTest(unittest.TestCase):
    """D14b — o dia dela vira sentimento com causa."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "w.db")
        self.engine = EmotionEngine(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _event(self, key, event_type, summary, at, participants='["marina"]'):
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO life_events (event_key,event_at,event_type,title,summary,source_type,
                            autonomy_level,importance,participants_json,share_worthy,created_at)
                            VALUES (?,?,?,?,?,'simulated',1,0.3,?,0.3,?)""",
                         (key, at.isoformat(), event_type, "t", summary, participants, at.isoformat()))
            conn.commit()

    def test_real_day_becomes_feelings_once(self):
        self._event("commute:2026-09-23:puc:volta:imprevisto", "commute",
                    "No caminho (voltando da PUC, de uber): o motorista do uber errou o caminho.", NOW - timedelta(minutes=20))
        self._event("milo:2026-09-23:arte", "routine", "O Milo dormiu encostado nela no sofá.", NOW - timedelta(minutes=10))
        self._event("outing:2026-09-26:c1:convite", "social_invite",
                    "A Bia te chamou: Saindo com a Bia no Quartinho Bar (sábado às 21:00).", NOW - timedelta(minutes=5),
                    '["marina", "bia_fontes"]')
        with patch.object(EmotionEngine, "energy", return_value=0.4):
            first = self.engine.appraise_world(NOW)
            again = self.engine.appraise_world(NOW)
        self.assertEqual((first, again), (3, 0), "cada acontecimento vira sentimento uma vez só")
        words = {e.word: e for e in self.engine.episodes(NOW)}
        self.assertEqual(words["irritada"].cause, "o motorista do uber errou o caminho")
        self.assertGreater(words["irritada"].intensity, 0.4, "cansada, o imprevisto irrita mais")
        self.assertIn("derretida", words)
        self.assertIn("empolgada", words)

    def test_agency_scolding_hurts_a_vain_girl(self):
        out = emotion.appraise_event({"event_key": "peso:2026-W39:agencia", "event_type": "routine",
                                      "summary": "A Lívia viu o peso e cobrou.", "participants_json": "[]"})
        self.assertEqual({(f, k) for f, k, *_ in out}, {("medo", "inseguranca"), ("vergonha", "vergonha")})

    def test_unknown_event_invents_nothing(self):
        self.assertEqual(emotion.appraise_event({"event_key": "x:1", "event_type": "routine",
                                                 "summary": "Arrumou a gaveta.", "participants_json": "[]"}), [])

    def test_deadline_worry_holds_until_she_delivers_then_relief(self):
        due = NOW.date() + timedelta(days=1)
        item = {"key": "2026.2:7:0", "course": "Práticas VI", "kind": "trabalho", "due": due.isoformat(),
                "pace": "ultima_hora"}
        with patch("college.College.assignments", return_value=[item]):
            self.engine._appraise_deadlines(NOW)
        worry = [e for e in self.engine.episodes(NOW) if e.kind == "ansiedade"][0]
        self.assertTrue(worry.sticky)
        self.assertIn("pra entregar amanhã", worry.cause)
        after = datetime.combine(due, NOW.time()).replace(hour=19)
        with patch("college.College.assignments", return_value=[item]):
            self.engine._appraise_deadlines(after)
        kinds = {e.kind for e in self.engine.episodes(after)}
        self.assertIn("alivio", kinds)

    def test_prompt_cause_is_short(self):
        self.engine.feel("alegria", "diversao", 0.5, "Conheceu o Caio (Starbucks do Shopping da Gávea); assunto: música",
                         NOW, target="o Caio")
        lines = "\n".join(self.engine.prompt_lines(NOW))
        self.assertIn("se divertindo com o Caio — Conheceu o Caio.", lines)


class PatrickFeelsTest(unittest.TestCase):
    """D14c — o que a mensagem dele faz com ela; mágoa real mas justa, ciúme leve."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "p.db")
        self.engine = EmotionEngine(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_care_warms_and_builds_security(self):
        before = self.engine.bond()["security"]
        self.assertTrue(emotion.apply_patrick_event(self.db, {"kind": "cuidado", "cause": "ele mandou ela comer"}, NOW))
        self.assertGreater(self.engine.bond()["security"], before)
        self.assertEqual(self.engine.episodes(NOW)[0].word, "carinhosa")

    def test_rudeness_hurts_until_he_repairs(self):
        emotion.apply_patrick_event(self.db, {"kind": "grosseria", "cause": "ele respondeu seco e desdenhou do trabalho dela"}, NOW)
        self.assertGreater(self.engine.bond()["hurt"], 0.2)
        hours_later = NOW + timedelta(hours=6)
        grievance = [e for e in self.engine.episodes(hours_later) if e.target == "o Patrick"][0]
        self.assertAlmostEqual(grievance.intensity, 0.4, places=2, msg="sem reparo, a mágoa não passa sozinha em horas")
        lines = "\n".join(self.engine.prompt_lines(hours_later))
        self.assertIn("chateada com ele (ele respondeu seco e desdenhou do trabalho dela)", lines)
        self.assertIn("sem drama", lines)
        emotion.apply_patrick_event(self.db, {"kind": "desculpa", "cause": "ele pediu desculpa"}, hours_later)
        self.assertLess(self.engine.bond()["hurt"], 0.05)
        later = [e for e in self.engine.episodes(hours_later + timedelta(hours=12))
                 if e.target == "o Patrick" and e.family == "tristeza"]
        self.assertTrue(not later or later[0].intensity < 0.2, "depois do reparo, esfria")

    def test_grievance_cools_by_itself_after_a_day(self):
        emotion.apply_patrick_event(self.db, {"kind": "briga"}, NOW)
        next_days = [e for e in self.engine.episodes(NOW + timedelta(hours=60)) if e.target == "o Patrick"]
        self.assertEqual(next_days, [], "real, mas não guarda rancor pra sempre")

    def test_jealousy_is_light_and_playful(self):
        emotion.apply_patrick_event(self.db, {"kind": "ciume", "cause": "ele comentou da colega nova do trabalho"}, NOW)
        self.assertEqual(self.engine.bond()["hurt"], 0.0, "ciuminho não vira mágoa")
        lines = "\n".join(self.engine.prompt_lines(NOW))
        self.assertIn("implica de brincadeira", lines)
        self.assertEqual([e for e in self.engine.episodes(NOW + timedelta(hours=5)) if e.kind == "ciume"], [])

    def test_unknown_or_none_does_nothing(self):
        self.assertFalse(emotion.apply_patrick_event(self.db, {"kind": "nenhum"}, NOW))
        self.assertFalse(emotion.apply_patrick_event(self.db, {"kind": "odio_mortal"}, NOW))


class DesireTest(unittest.TestCase):
    """Tesão no motor (Patrick, 23/09): acumula, faz ela ir atrás, e sem ele ela se resolve sozinha."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "d.db")
        self.engine = EmotionEngine(self.db)
        self.patches = [patch.object(EmotionEngine, "_sleep_facts", return_value=(8.0, NOW.replace(hour=8), 0.0, False)),
                        patch.object(EmotionEngine, "_cycle", return_value=("folicular", 8)),
                        patch.object(EmotionEngine, "_hunger", return_value=0.3),
                        patch.object(EmotionEngine, "_missing", return_value=0.3)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _released(self, hours_ago):
        self.db.set_estado_relacional(emotion.RELEASE_KEY, (NOW - timedelta(hours=hours_ago)).isoformat())

    def test_desire_builds_with_time_and_drops_after_release(self):
        self._released(40)
        built = self.engine.feeling(NOW).libido
        self._released(1)
        just = self.engine.feeling(NOW).libido
        self.assertGreater(built, 0.55)
        self.assertLess(just, 0.25)

    def test_hurt_and_cramps_kill_the_mood(self):
        self._released(40)
        normal = self.engine.feeling(NOW).libido
        self.db.ajustar_emocao("hurt", 0.4, now=NOW)
        hurt = self.engine.feeling(NOW).libido
        self.assertLess(hurt, normal - 0.15)
        self.assertEqual(self.engine.feeling(NOW).libido < emotion.TESAO_MIN, True)

    def test_prompt_and_summary_show_desire(self):
        self._released(40)
        with patch.object(EmotionEngine, "_libido", return_value=(0.8, 0.0, 40.0)):
            lines = "\n".join(self.engine.prompt_lines(NOW))
            text = self.engine.summary(NOW)
        self.assertIn("com tesão", lines)
        self.assertIn("Provoca e puxa pro flerte", lines)
        self.assertIn("Tesão: vontade 0.80", text)

    def test_without_him_she_takes_care_of_it_before_bed(self):
        bed = NOW.replace(hour=23, minute=30)
        with patch.object(EmotionEngine, "_libido", return_value=(0.85, 0.0, 30.0)), \
             patch("sleep_plan.SleepPlan.bed", return_value=bed), \
             patch("random.Random.random", return_value=0.1):
            self.assertIsNone(self.engine.maybe_release_alone(NOW.replace(hour=20)), "ainda não é hora de dormir")
            summary = self.engine.maybe_release_alone(bed - timedelta(minutes=30))
            again = self.engine.maybe_release_alone(bed - timedelta(minutes=20))
        self.assertIn("se resolveu sozinha", summary)
        self.assertIn("Pode contar pra ele", summary)
        self.assertIsNone(again, "uma vez por noite")
        self.assertEqual(self.engine.last_release(bed), bed - timedelta(minutes=30))

    def test_intimacy_uses_the_engine_desire(self):
        from intimacy import IntimacyEngine
        with patch.object(EmotionEngine, "_libido", return_value=(0.9, 0.0, 40.0)):
            hot = IntimacyEngine(self.db)._libido()
        with patch.object(EmotionEngine, "_libido", return_value=(0.1, 0.0, 1.0)):
            cold = IntimacyEngine(self.db)._libido()
        self.assertGreater(hot, 1.2)
        self.assertLess(cold, 0.8)

    def test_she_goes_after_him_but_not_when_hurt(self):
        from proactivity_service import ProactivityService
        svc = ProactivityService(self.db)
        with patch.object(EmotionEngine, "_libido", return_value=(0.85, 0.0, 40.0)), \
             patch.object(svc, "_compute_state_factor", return_value=(1.0, "free_time")), \
             patch.object(svc, "get_last_messages_timestamps", return_value=(NOW - timedelta(hours=2), None)), \
             patch("proactivity_service.random.random", return_value=0.0):
            self.assertTrue(svc.tesao_initiative(NOW))
            emotion.apply_patrick_event(self.db, {"kind": "grosseria"}, NOW)
            self.assertFalse(svc.tesao_initiative(NOW + timedelta(minutes=5)), "chateada com ele não vai atrás")


class FeelingsChangeBehaviourTest(unittest.TestCase):
    """D14d — o que ela sente muda o que ela faz."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "b.db")

    def tearDown(self):
        self.temp.cleanup()

    def _worry(self, family="medo", intensity=0.6, target=None):
        return emotion.Episode(1, family, "ansiedade", intensity, intensity, "trabalho pra entregar amanhã",
                               target, NOW, True)

    def test_a_worried_mind_falls_asleep_later(self):
        from sleep_plan import SleepPlan
        plan = SleepPlan(self.db)
        with patch.object(EmotionEngine, "episodes", return_value=[]):
            calm, _ = plan._onset(NOW.date(), live=True)
        with patch.object(EmotionEngine, "episodes", return_value=[self._worry()]):
            worried, why = plan._onset(NOW.date(), live=True)
        self.assertGreaterEqual(worried - calm, 20)
        self.assertIn("pensando nisso: trabalho pra entregar amanhã", " ".join(why))

    def test_anxious_glutton_gets_hungry_faster(self):
        from meals import Meals
        meals = Meals(self.db)
        with patch.object(EmotionEngine, "episodes", return_value=[]):
            calm = meals.hunger(NOW)
        with patch.object(EmotionEngine, "episodes", return_value=[self._worry()]):
            anxious = meals.hunger(NOW)
        self.assertGreaterEqual(anxious, calm)


if __name__ == "__main__":
    unittest.main()
