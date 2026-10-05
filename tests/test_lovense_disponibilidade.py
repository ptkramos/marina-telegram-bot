"""Lovense, passo 4 (Patrick, 05/10): com o brinquedo, quando ela responde sai de como ela está recebendo.

Celular perto a sessão inteira (a ideia sendo dela ou dele); parado ou gostando, segundos; incomodada, reclama na
hora; curtindo, some aproveitando e fala quando ele para; com gente perto, curtinho e escondido. Dormindo e com o
celular impossível (casting) segue a atividade; no banho ela só sai do box pra reclamar de incômodo leve e volta.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from db import DatabaseManager
from lovense import Lovense
from response_availability import ResponseAvailabilityPolicy

T0 = datetime(2026, 10, 6, 14, 0)


def sentindo(libido=0.5, excitacao=0.0):
    return SimpleNamespace(libido=libido, excitation=excitacao, discomfort=0.0, energy=0.7,
                           hours_since_release=None, cycle_phase="folicular")


class DisponibilidadeComBrinquedoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "lov.db")
        with self.db.get_connection() as conn:
            conn.execute("UPDATE lovense_brinquedos SET bateria=1.0, bateria_em=?, onde='gaveta'", (T0.isoformat(),))
            conn.commit()
        self.lv = Lovense(self.db)

    def avaliar(self, atividade, msg="oi amor, como tá aí?", *, sente=None, excitacao=None, quando=None):
        pol = ResponseAvailabilityPolicy(self.db)
        pol._resolve_activity = lambda _now: (atividade, "WORLD_STATE", None, "fresh", True)
        sente = sente or sentindo()
        with patch("lovense._feeling", return_value=sente), \
                patch("intimacy.IntimacyEngine.current",
                      return_value=SimpleNamespace(arousal=sente.excitation if excitacao is None else excitacao)):
            d = pol.evaluate(msg, now=quando or T0 + timedelta(minutes=1), telegram_message_id=7)
        return d, round((d.selected_target_at - d.earliest_reply_at).total_seconds())

    def test_sem_brinquedo_nada_muda(self):
        d, _ = self.avaliar("CLASS", "amor me conta com calma como foi o seu dia hoje, tudo mesmo?")
        self.assertIn(d.decision, ("DEFER", "REPLY_BRIEFLY"))
        self.assertFalse(d.reason_code.startswith("lovense"))

    def test_parado_em_casa_responde_em_segundos(self):
        self.lv.colocar(T0, ["lush"])
        d, em = self.avaliar("HOME_RELAXING")
        self.assertEqual((d.decision, d.reason_code), ("REPLY_NOW", "lovense_parado"))
        self.assertLessEqual(em, 15)

    def test_na_aula_segundos_mas_curtinho(self):
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0 + timedelta(seconds=10), "lush", 5)
        d, em = self.avaliar("CLASS", "amor me conta com calma como foi o seu dia hoje, tudo mesmo?")
        self.assertEqual((d.decision, d.reason_code), ("REPLY_BRIEFLY", "lovense_gostando"))
        self.assertLessEqual(em, 25)
        self.assertEqual(d.activity_type, "CLASS")                 # o resto do sistema continua sabendo da aula

    def test_incomodada_reclama_na_hora(self):
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0 + timedelta(seconds=10), "lush", 20)
        d, em = self.avaliar("HOME_RELAXING", sente=sentindo(libido=0.3))
        self.assertEqual(d.reason_code, "lovense_incomodada")
        self.assertLessEqual(em, 10)

    def test_curtindo_some_aproveitando_e_volta_quando_ele_para(self):
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0 + timedelta(seconds=10), "lush", 14)
        d, em = self.avaliar("HOME_RELAXING", sente=sentindo(libido=0.8, excitacao=0.7))
        self.assertEqual((d.decision, d.reason_code), ("DEFER", "lovense_curtindo"))
        self.assertTrue(60 <= em <= 400, em)
        self.lv.comando(T0 + timedelta(seconds=50), "lush", 0)     # ele parou: a próxima conta já é na hora
        d, em = self.avaliar("HOME_RELAXING", sente=sentindo(libido=0.8, excitacao=0.7))
        self.assertEqual(d.reason_code, "lovense_parado")
        self.assertLessEqual(em, 15)

    def test_urgente_fura_o_curtindo(self):
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0 + timedelta(seconds=10), "lush", 14)
        d, em = self.avaliar("HOME_RELAXING", "amor preciso falar contigo, é sério",
                             sente=sentindo(libido=0.8, excitacao=0.95))
        self.assertLessEqual(em, 180)

    def test_casting_e_dormindo_seguem_a_atividade(self):
        self.lv.colocar(T0, ["lush"])
        for atividade in ("CASTING", "SLEEPING"):
            d, _ = self.avaliar(atividade)
            self.assertFalse(d.reason_code.startswith("lovense"), atividade)

    def _banho(self):
        fim = T0 + timedelta(minutes=10)
        self.db.set_estado_relacional("pending_transition_json", json.dumps(
            {"routine_type": "shower", "transition_at": T0.isoformat(), "end_at": fim.isoformat()}))
        return fim

    def test_banho_gostoso_responde_depois_de_sair(self):
        self._banho()
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0 + timedelta(seconds=10), "lush", 6)
        d, _ = self.avaliar("SHOWER")
        self.assertEqual(d.reason_code, "in_shower_until_dressed")

    def test_banho_incomodo_leve_sai_pra_reclamar_e_volta(self):
        fim = self._banho()
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0 + timedelta(seconds=10), "lush", 15)    # um pouco acima do ponto: incômodo leve
        d, em = self.avaliar("SHOWER")
        self.assertEqual((d.decision, d.reason_code), ("DEFER", "lovense_sai_do_banho"))
        self.assertTrue(25 <= em <= 60, em)
        novo_fim = datetime.fromisoformat(json.loads(self.db.get_estado_relacional("pending_transition_json"))["end_at"])
        self.assertEqual(novo_fim, fim + timedelta(minutes=2))      # o banho continua: um passo a mais
        self.avaliar("SHOWER", "e aí?")                             # a mesma pausa não estica de novo
        de_novo = datetime.fromisoformat(json.loads(self.db.get_estado_relacional("pending_transition_json"))["end_at"])
        self.assertEqual(de_novo, novo_fim)


if __name__ == "__main__":
    unittest.main()
