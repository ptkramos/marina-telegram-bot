"""Bug 16 (28/09, ~18:57): inverdades no chat com ela na academia. Casos reais da produção:

A. 18:56 "Me pesei ,4 kg kkk": o modelo disse "Me pesei hoje: 54,4 kg" e o guard de artefato de debug leu
   "hoje: 54" como chave:valor; o salvamento cortou o "hoje: 54".
B. 18:43 "Se pesou na academia: 54,4 kg" com ela ainda a caminho da Bodytech: o preparo "(colocando roupa de
   treino)" contava como treino do dia.
C. 18:58 "Tô em casa, amor / Deitada no sofá com o Milo" treinando na Bodytech: o prompt chamava a academia planejada
   de "inferência de rotina (probabilística)", e o "derretida — O Milo dormiu encostado nela no sofá" das 17:21
   vinha como sentimento de agora, sem hora.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import bot
from db import DatabaseManager
from emotion import EmotionEngine
from meals import Meals
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from world_context import WorldContextBuilder

DIA = datetime(2026, 9, 28)


def at(h, m):
    return DIA.replace(hour=h, minute=m)


class PesoNaFalaTest(unittest.TestCase):
    def test_peso_com_dois_pontos_nao_e_artefato(self):
        for fala in ("Oi, meu dengo. Me pesei na academia hoje: 54,4 kg kkk",
                     "Oi, meu amor. Me pesei hoje: 54,4 kg kkk",
                     "saldo: 536 reais, tô rica kkk",
                     "resultado: 10 de 10"):
            with self.subTest(fala=fala):
                self.assertEqual(bot._needs_retry_for_junk(fala), (False, ""))

    def test_artefatos_continuam_pegos(self):
        for fala in ("oi amor temperature=0.85", "flag debug_mode: true", "htar_negative: 0",
                     "tudo certo aqui planejamento: true", "nota=10"):
            with self.subTest(fala=fala):
                self.assertTrue(bot._has_debug_artifact_leak(fala), fala)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "b16.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) "
                         "VALUES ('clean_canonical_start_done', '1', '2026-09-18T00:00:00')")

    def _state(self, when, activity, reason="routine", place=None):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_state (state_date, observed_at, location_place_id, activity, source_json) "
                         "VALUES (?,?,?,?,?)", (when.date().isoformat(), when.isoformat(), place, activity,
                                                json.dumps({"reason": reason})))
            conn.commit()

    def _pesagens(self):
        with self.db.get_connection() as conn:
            return [r[0] for r in conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'peso:%:peso'")]


class PesagemDepoisDoTreinoTest(Base):
    def test_preparo_e_ida_nao_sao_treino(self):
        meals = Meals(self.db)
        self.db.set_estado_relacional(Meals.WEIGHT_KEY, json.dumps({"kg": 54.4, "week": "2026-W40"}))
        self._state(at(18, 24), "se arrumando pra sair pro Bodytech São Clemente (colocando roupa de treino)",
                    "getting_ready")
        self._state(at(18, 43), "indo pra Bodytech a pé", "commute")
        meals._weigh_in(at(18, 43))
        self.assertEqual(self._pesagens(), [], "18:43 ainda a caminho")
        self._state(at(18, 50), "treinando na academia", "gym_weekly")
        meals._weigh_in(at(19, 30))
        self.assertEqual(self._pesagens(), [], "no meio do treino")
        self._state(at(20, 10), "voltando da Bodytech a pé", "commute")
        meals._weigh_in(at(20, 10))
        self.assertEqual(self._pesagens(), ["Se pesou na academia: 54,4 kg."])


class PromptNaAcademiaTest(Base):
    def _bodytech(self):
        with self.db.get_connection() as conn:
            return conn.execute("SELECT id FROM world_places WHERE canonical_key='bodytech_sao_clemente'").fetchone()[0]

    def _prompt(self, now, activity, reason, place):
        estado = {"location_place_id": place, "location_region": "Botafogo", "activity": activity,
                  "source_json": json.dumps({"reason": reason}), "weather_context_json": None}
        with patch("world_state.WorldStateManager.resolve", return_value=estado):
            return WorldContextBuilder(self.db).build(now=now, user_message="Tá onde agr?", control_language="pt-BR")

    def test_academia_planejada_e_fato(self):
        EmotionEngine(self.db).feel("afeto", "ternura", 0.4, "O Milo dormiu encostado nela no sofá.", at(17, 21))
        prompt = self._prompt(at(18, 58), "treinando na academia", "gym_weekly", self._bodytech())
        estado = prompt[prompt.index("[SEU ESTADO ATUAL"):prompt.index("[COMO VOCÊ ESTÁ POR DENTRO")]
        self.assertIn("Bodytech São Clemente", estado)
        self.assertNotIn("probabilística", estado)
        self.assertIn("NUNCA diga 'em casa'", estado)
        self.assertIn("derretida — O Milo dormiu encostado nela no sofá (às 17:21).", prompt)

    def test_preparo_nao_manda_ficar_em_casa(self):
        with self.db.get_connection() as conn:
            casa = conn.execute("SELECT id FROM world_places WHERE canonical_key='marina_apartment'").fetchone()[0]
        prompt = self._prompt(at(18, 26), "se arrumando pra sair pro Bodytech São Clemente (colocando roupa de "
                              "treino)", "getting_ready", casa)
        self.assertNotIn("não invente ida a lugar externo", prompt)
        self.assertIn("se arrumando pra sair (é fato)", prompt)

    def test_sentimento_recente_fica_sem_hora(self):
        EmotionEngine(self.db).feel("afeto", "ternura", 0.4, "O Milo dormiu encostado nela no sofá.", at(17, 21))
        linhas = "\n".join(EmotionEngine(self.db).prompt_lines(at(17, 30)))
        self.assertIn("derretida — O Milo dormiu encostado nela no sofá.", linhas)


if __name__ == "__main__":
    unittest.main()
