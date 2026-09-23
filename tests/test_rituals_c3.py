"""Fase C.3 — rituais de namorada (bom dia, boa noite, cotidiano)."""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import rituals
from db import DatabaseManager
from rituals import Rituals
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from social_day import SocialDay


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "c3.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.r = Rituals(self.db)
        # Dia de aula e dia livre reais da grade semeada.
        self.class_day = next(date(2026, 9, 21) + timedelta(days=i) for i in range(14)
                              if self.r._has_class(date(2026, 9, 21) + timedelta(days=i)))
        self.free_day = next(date(2026, 9, 21) + timedelta(days=i) for i in range(14)
                             if not self.r._has_class(date(2026, 9, 21) + timedelta(days=i)))
        for p in (patch.dict(rituals.DAILY_CHANCE, {"bom_dia": 1.0, "boa_noite": 1.0}),
                  patch.object(rituals, "COTIDIANO_CHANCE", 1.0)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _msg(self, role, content, when, initiative=0):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO conversas (timestamp, role, content, is_initiative) VALUES (?,?,?,?)",
                         (when.isoformat(), role, content, initiative))
            conn.commit()

    def _tick(self, now, state=("HOME_RELAXING", "tempo livre em casa")):
        with patch.object(Rituals, "_state", return_value=state):
            return self.r.tick(now)


class BomDiaTests(_Base):
    def test_acorda_e_da_bom_dia(self):
        wake = self.r.wake_at(self.class_day)
        self.assertEqual(wake.strftime("%H:%M"), "07:00")
        self.assertEqual(self.r.wake_at(self.free_day).strftime("%H:%M"), "08:30")
        ritual = self._tick(wake + timedelta(minutes=41), ("WAKING", "acordando"))
        self.assertEqual(ritual.kind, "bom_dia")
        self.assertIn("hoje tem aula", ritual.detail)

    def test_nao_da_bom_dia_antes_de_acordar_nem_duas_vezes(self):
        wake = self.r.wake_at(self.class_day)
        self.assertIsNone(self._tick(wake - timedelta(minutes=30), ("SLEEPING", "dormindo")))
        ritual = self._tick(wake + timedelta(minutes=41))
        self.r.mark(ritual, wake + timedelta(minutes=41))
        self.assertIsNone(self._tick(wake + timedelta(minutes=50)))

    def test_se_o_patrick_escreveu_de_madrugada_ela_responde_ele(self):
        """Soak 22/09: o bom dia dele às 05:37 é respondido pelo lote adiado, não por outro bom dia."""
        wake = self.r.wake_at(self.class_day)
        self._msg("user", "Bom dia princesa", datetime.combine(self.class_day, datetime.min.time()).replace(hour=5, minute=37))
        self.assertIsNone(self._tick(wake + timedelta(minutes=41)))


class BoaNoiteTests(_Base):
    def test_boa_noite_antes_de_deitar(self):
        bed = self.r.bed_at(self.class_day)
        self.assertEqual(bed, datetime.combine(self.class_day + timedelta(days=1), datetime.min.time()))
        ritual = self._tick(bed - timedelta(minutes=4))
        self.assertEqual(ritual.kind, "boa_noite")

    def test_patrick_ja_deu_boa_noite(self):
        bed = self.r.bed_at(self.class_day)
        self._msg("user", "boa noite amor, dorme bem", bed - timedelta(hours=1))
        self.assertIsNone(self._tick(bed - timedelta(minutes=4)))

    def test_na_rua_nao_manda(self):
        bed = self.r.bed_at(self.class_day)
        self.assertIsNone(self._tick(bed - timedelta(minutes=4), ("SOCIAL", "no Quartinho Bar com a Bia")))

    def test_conversa_em_andamento_vira_aviso(self):
        bed = self.r.bed_at(self.class_day)
        self._msg("user", "e aí, o que achou do filme?", bed - timedelta(minutes=10))
        ritual = self._tick(bed - timedelta(minutes=4))
        self.assertIn("estavam conversando", ritual.detail)


class CotidianoTests(_Base):
    def _at(self, h, m=0, day=None):
        return datetime.combine(day or self.class_day, datetime.min.time()).replace(hour=h, minute=m)

    def test_saiu_da_aula(self):
        self._tick(self._at(13, 0), ("CLASS", "na faculdade"))
        ritual = self._tick(self._at(13, 5), ("HOME_RELAXING", "tempo livre em casa"))
        self.assertEqual((ritual.kind, ritual.moment), ("cotidiano", "saiu_da_aula"))

    def test_teto_de_dois_por_dia_e_intervalo_minimo(self):
        sent = []
        cenas = [("CLASS", "na faculdade"), ("HOME_RELAXING", "em casa"),
                 ("PET_WALK", "passeando com o Milo"), ("HOME_RELAXING", "em casa"),
                 ("GYM", "treinando"), ("HOME_RELAXING", "em casa")]
        now = self._at(12, 0)
        for state in cenas:
            ritual = self._tick(now, state)
            if ritual and ritual.kind == "cotidiano":
                self.r.mark(ritual, now)
                self._msg("assistant", ritual.fallback, now, initiative=1)
                sent.append(ritual.moment)
            now += timedelta(minutes=50)
        self.assertEqual(len(sent), 2)

    def test_intervalo_minimo_depois_de_outra_iniciativa(self):
        self._msg("assistant", "oi amor", self._at(13, 0), initiative=1)
        self._tick(self._at(13, 1), ("CLASS", "na faculdade"))
        self.assertIsNone(self._tick(self._at(13, 10), ("HOME_RELAXING", "em casa")))

    def test_banho_depois_da_academia_some_de_verdade(self):
        from response_availability import ResponseAvailabilityPolicy
        self._tick(self._at(18, 0), ("GYM", "treinando na academia"))
        saiu = self._tick(self._at(18, 5), ("HOME_RELAXING", "em casa"))
        self.r.mark(saiu, self._at(18, 5))
        self._msg("assistant", "saí da academia", self._at(18, 5), initiative=1)
        planned = datetime.fromisoformat(self.r._get(f"ritual:{self.class_day.isoformat()}:banho_at"))
        self.assertTrue(self._at(18, 25) <= planned <= self._at(18, 45))
        with patch.object(rituals, "MIN_GAP_MIN", 0):
            banho = self._tick(planned + timedelta(minutes=1), ("HOME_RELAXING", "em casa"))
        self.assertEqual(banho.moment, "banho")
        self.r.mark(banho, planned + timedelta(minutes=1))
        data = json.loads(self.db.get_estado_relacional()["pending_transition_json"])
        self.assertEqual(data["activity"], "tomando banho")
        policy = ResponseAvailabilityPolicy(self.db)
        self.assertEqual(policy._map_place_activity("marina_apartment", "tomando banho"), "SHOWER")
        decision = policy.evaluate("amor?", now=planned + timedelta(minutes=5), telegram_message_id=7)
        self.assertEqual(decision.activity_type, "SHOWER")
        self.assertGreaterEqual((decision.selected_target_at - (planned + timedelta(minutes=5))).total_seconds(), 60)

    def _evening_slot(self, day=None):
        day = day or self.class_day
        for minute in range(0, 181, 5):
            now = self._at(19, 30, day) + timedelta(minutes=minute)
            if self.r._shower_due(now, day) == "banho_noite":
                return now
        self.fail("sem horário de banho à noite")

    def _transition(self):
        raw = self.db.get_estado_relacional().get("pending_transition_json")
        return json.loads(raw) if raw else None

    def test_soak_22_09_banho_acontece_mesmo_com_teto_e_conversa(self):
        """Aula e Milo gastaram o teto; o Patrick conversava na janela do banho. Antes: zero banhos."""
        for key in ("saiu_da_aula", "passeio_milo"):
            self.r._set(f"ritual:{self.class_day.isoformat()}:cotidiano:{key}", "sent", self._at(15))
        at = self._evening_slot()
        self._msg("user", "Uhum 😋", at - timedelta(minutes=3))
        ritual = self._tick(at)
        self.assertEqual(ritual.moment, "banho")
        self.assertIn("estavam conversando", ritual.detail)
        self.r.mark(ritual, at)
        self.assertEqual(self._transition()["activity"], "tomando banho")

    def test_sem_aviso_ela_toma_banho_quieta(self):
        at = self._evening_slot()
        with patch.object(rituals, "COTIDIANO_CHANCE", 0.0):
            self.assertIsNone(self._tick(at))
        self.assertEqual(self._transition()["activity"], "tomando banho")
        day = SocialDay(self.db).today_so_far(at + timedelta(minutes=40))
        self.assertTrue(any("Tomou banho" in e["summary"] for e in day))

    def test_banho_depois_do_treino_e_a_noite_nao_duplicam(self):
        self.r.start_shower(self._at(19, 0), 20)
        at = self._evening_slot()
        if at - self._at(19, 2) < rituals.SHOWER_MIN_GAP:
            self.assertIsNone(self._tick(at))
            self.assertEqual(self.r._get(f"ritual:{self.class_day.isoformat()}:cotidiano:banho_noite"),
                             "skipped:ja_tomou")

    def test_jantar_em_andamento_adia_o_banho(self):
        at = self._evening_slot()
        self.db.set_estado_relacional("pending_transition_json", json.dumps({
            "activity": "jantando em casa", "transition_at": at.isoformat(),
            "end_at": (at + timedelta(minutes=25)).isoformat()}))
        self.assertIsNone(self._tick(at))
        self.assertEqual(self._transition()["activity"], "jantando em casa")
        ritual = self._tick(at + timedelta(minutes=30))
        self.assertIsNotNone(self.r._get(f"ritual:{self.class_day.isoformat()}:banho_last")
                             or (ritual and ritual.moment == "banho"))

    def test_fala_vou_tomar_banho_vira_banho(self):
        now = self._at(21, 0)
        self.assertTrue(self.r.observe_marina_line("Vou tomar banho, já volto", now))
        self.assertEqual(self._transition()["activity"], "tomando banho")
        self.assertFalse(self.r.observe_marina_line("vou tomar banho agora", now + timedelta(minutes=40)))
        for fala in ("amanhã vou tomar banho cedo", "vou tomar banho amanhã cedo antes da aula"):
            self.assertFalse(Rituals(self.db).observe_marina_line(fala, now + timedelta(hours=5)))

    def test_malicia_so_com_humor_provocador(self):
        with patch.object(Rituals, "_flirty", return_value=True):
            self._tick(self._at(13, 0), ("CLASS", "na faculdade"))
            ritual = self._tick(self._at(13, 5), ("HOME_RELAXING", "em casa"))
        self.assertIn("malícia leve", ritual.detail)


if __name__ == "__main__":
    unittest.main()
