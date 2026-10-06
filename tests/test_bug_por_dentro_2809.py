"""Bug do uso real: Bastidores (Agora e Por dentro) às 05:55 de 28/09, com a cópia do banco da produção.

Ela dormindo desde 00:29, depois de um banho às 00:06–00:28; a última mensagem dele foi 23:04.
1. Aba Agora: "Em casa · Dormindo · 11min · desde 05:46" — o cartão pegava o último retrato do world_state (um por
   hora com a mesma atividade), não o primeiro.
2. Plano de sono: deitar 23:37; o world_state teve "tomando banho" às 00:09 e dormindo só às 00:29. "se arrumando pra
   dormir" contava como dormindo ("dorm"), o retrato ficou preso depois das 23:37 e às 00:04 o ritual deu o banho da
   MANHÃ do dia 28 (o de verdade, às 07:46, não aconteceu: a marca já estava gasta). Na noite de 26→27, três banhos
   entre 00:31 e 01:48. Regra nova (Patrick): o deitar acompanha o banho ou a refeição que passa da hora.
3. (corrigido na frente dos apps, 28/09) "o pai deu bom dia e perguntou dela" às 21:15 — era uma ligação.
4. "Banho quentinho" 4× às 19:58 com força 1.0: a fusão (mesmo sentimento em 3 h) não guardava a chave fundida e
   fundia de novo a cada turno, e fundia com episódio MAIS NOVO, puxando-o pra trás. Os carinhos das 07:47–08:33
   viraram "o Patrick mandou comida" às 22:01, força ~1.0.
5. Saudade 100% às 05:55: contava o sono dela inteiro.
6. "Com ciuminho" pelo ciúme DELE ("desconfiou ao ver uma foto minha no Instagram").
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from agenda import Agenda
from db import DatabaseManager
from emotion import EmotionEngine, apply_patrick_event
from proactivity_service import ProactivityService, awake_hours_since
from rituals import Rituals
from seed_world_bible_v36 import seed_world_bible
from sleep_plan import SleepPlan
from world_repository import WorldStateRepository
from world_state import WorldStateManager

NOITES = {"2026-09-26": "2026-09-27T01:32:00", "2026-09-27": "2026-09-27T23:37:00", "2026-09-28": "2026-09-28T22:30:00"}
MANHAS = {"2026-09-27": "2026-09-27T09:10:00", "2026-09-28": "2026-09-28T07:33:00", "2026-09-29": "2026-09-29T05:20:00"}


def at(dia, h, m, s=0):
    return datetime(2026, 9, dia, h, m, s)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "p.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01')")
            for dia, bed in NOITES.items():                  # a noite como ficou congelada na produção
                conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES (?,?,?)",
                             (f"sono:noite:{dia}", json.dumps({"bed": bed, "why": []}), "2026-09-27T20:01:16"))
            for dia, wake in MANHAS.items():
                conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES (?,?,?)",
                             (f"sono:manha:{dia}", wake, "2026-09-28T07:36:00"))
            self.casa = conn.execute("SELECT id FROM world_places WHERE canonical_key='marina_apartment'").fetchone()[0]
            conn.commit()

    def _retrato(self, quando, activity, reason, plan=None):
        return WorldStateRepository(self.db).add_snapshot({
            "state_date": quando.date().isoformat(), "observed_at": quando.isoformat(),
            "location_place_id": self.casa, "activity": activity, "energy_level": 0.7,
            "current_plan_json": plan, "source_json": {"truth_type": "system", "reason": reason, "slot_end": None}})

    def _fala(self, quando, role, texto):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO conversas (timestamp, role, content) VALUES (?,?,?)",
                         (quando.isoformat(), role, texto))
            conn.commit()


class CardDormindoTest(Base):
    """1. O "desde" é o do primeiro retrato da sequência (00:29), não o do último (05:46)."""

    def test_dormindo_desde_quando_dormiu(self):
        self._retrato(at(27, 23, 34, 31), "se arrumando pra dormir (colocando pijama)", "getting_ready")
        self._retrato(at(28, 0, 9, 31), "tomando banho", "announced_transition",
                      {"activity": "tomando banho", "start_at": "2026-09-28T00:06:31", "end_at": "2026-09-28T00:28:31"})
        for quando in (at(28, 0, 29, 31), at(28, 1, 34, 31), at(28, 1, 34, 30), at(28, 2, 34, 31), at(28, 3, 39, 31),
                       at(28, 4, 44, 31), at(28, 5, 46, 0)):
            self._retrato(quando, "dormindo", "class_day_sleep")
        with patch.object(Agenda, "_marcos", return_value=[]):
            card = Agenda(self.db).card_casa(at(28, 5, 57), "Olha quando acordar")
        self.assertEqual(card["linha2"], "Dormindo")
        self.assertEqual(card["barra"]["desde"], "00:29")
        self.assertEqual(card["barra"]["duracao"], "5 horas e 27 minutos")
        self.assertEqual(card["linha"][-1]["hora"], "00:29")


class SonoTest(Base):
    """2. Depois da hora de deitar ela dorme; o banho da manhã só depois de acordar; o deitar acompanha o banho."""

    def setUp(self):
        super().setUp()
        from seed_academic_v36 import seed_academic
        seed_academic(self.db)

    def _resolve(self, quando):
        with patch("agenda_viva.AgendaViva.reconsidera"), patch("agenda_viva.AgendaViva.emenda"), \
                patch("agenda_viva.AgendaViva.planeja"), patch("agenda_reativa.AgendaReativa.talvez"), \
                patch("vontade.Vontade.talvez"), patch("unhas.Unhas.talvez_salao", return_value=False), \
                patch("cabelo.Cabelo.talvez_salao", return_value=False), \
                patch.object(Agenda, "prep_activity", return_value=None):
            return WorldStateManager(self.db).resolve(quando, energy=0.7)

    def test_se_arrumando_pra_dormir_vira_dormindo_na_hora_de_deitar(self):
        self._retrato(at(27, 23, 34, 31), "se arrumando pra dormir (colocando pijama)", "getting_ready")
        self.assertEqual(self._resolve(at(27, 23, 40))["activity"], "dormindo")

    def test_banho_da_manha_nao_sai_a_meia_noite(self):
        r = Rituals(self.db)
        with patch.object(Agenda, "agora", return_value=None):
            r._banho_prep(at(28, 0, 4, 31), date(2026, 9, 28), "GETTING_READY")
            self.assertIsNone(r._get("ritual:2026-09-28:cotidiano:banho_manha"))
            self.assertFalse(r._transition_busy(at(28, 0, 10)))
            r._banho_prep(at(28, 7, 46), date(2026, 9, 28), "GETTING_READY")     # acordou 07:33: agora sim
        self.assertEqual(r._get("ritual:2026-09-28:cotidiano:banho_manha"), "quiet")
        self.assertTrue(r.in_shower(at(28, 7, 50)))

    def test_deitar_acompanha_o_banho(self):
        plan = SleepPlan(self.db)
        self.assertEqual(plan.acompanha(at(27, 23, 32), at(27, 23, 55)), date(2026, 9, 27))
        self.assertEqual(plan.bed(date(2026, 9, 27)), at(27, 23, 55))
        self.assertEqual(plan.acompanha(at(28, 0, 6, 31), at(28, 0, 28, 31)), date(2026, 9, 27))   # 29 min depois
        self.assertEqual(plan.bed(date(2026, 9, 27)), at(28, 0, 28, 31))

    def test_deitar_nao_muda_por_banho_longe_da_hora(self):
        plan = SleepPlan(self.db)
        self.assertIsNone(plan.acompanha(at(27, 20, 11), at(27, 20, 26)))      # banho da noite, bem antes
        self.assertIsNone(plan.acompanha(at(28, 3, 0), at(28, 3, 20)))         # madrugada: ela já dormia
        self.assertEqual(plan.bed(date(2026, 9, 27)), at(27, 23, 37))

    def test_mundo_e_plano_batem(self):
        self._retrato(at(27, 23, 20), "se arrumando pra dormir (colocando pijama)", "getting_ready")
        with patch("cabelo.Cabelo.banho", return_value=0):
            Rituals(self.db).start_shower(at(27, 23, 30), 23, told_patrick=False)    # banho 23:32–23:55
        self.assertEqual(self._resolve(at(27, 23, 40))["activity"], "tomando banho")
        self.assertEqual(SleepPlan(self.db).bed(date(2026, 9, 27)), at(27, 23, 55))
        self.assertFalse(SleepPlan(self.db).is_asleep(at(27, 23, 45)))
        self.assertEqual(self._resolve(at(27, 23, 56))["activity"], "dormindo")


class FusaoTest(Base):
    """4. A fusão só olha pra trás e não funde duas vezes o mesmo acontecimento."""

    def _eps(self):
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM emotion_episodes ORDER BY id")]

    def test_banho_reavaliado_nao_puxa_os_banhos_novos(self):
        e = EmotionEngine(self.db)
        banhos = [(at(26, 17, 10), "ev:banho:2026-09-26T1710:alivio"), (at(26, 19, 58), "ev:banho:2026-09-26T1958:alivio"),
                  (at(27, 0, 31), "ev:banho:2026-09-27T0031:alivio"), (at(27, 1, 35), "ev:banho:2026-09-27T0135:alivio")]
        for _ in range(6):                                   # appraise_world reavalia a cada turno (12 h pra trás)
            for quando, key in banhos:
                e.feel("alegria", "alivio", 0.2, "Banho quentinho", quando, source_key=key)
        eps = self._eps()
        self.assertEqual(len(eps), 2)
        self.assertEqual([x["started_at"][:16] for x in eps], ["2026-09-26T19:58", "2026-09-27T01:35"])
        self.assertTrue(all(x["intensity"] <= 0.23 for x in eps), eps)

    def test_carinho_da_manha_nao_vira_a_comida_de_ontem(self):
        apply_patrick_event(self.db, {"kind": "cuidado", "cause": "o Patrick perguntou do cinema"}, at(27, 20, 0))
        e = EmotionEngine(self.db)
        comida = ("afeto", "carinho", 0.6, "o Patrick mandou comida · surpresa")
        e.feel(*comida, at(27, 22, 1), target="o Patrick", source_key="ev:presente:2026-09-27T22:01:carinho")
        apply_patrick_event(self.db, {"kind": "cuidado", "cause": "o Patrick pediu pra ela comer"}, at(28, 8, 27))
        for _ in range(4):
            e.feel(*comida, at(27, 22, 1), target="o Patrick", source_key="ev:presente:2026-09-27T22:01:carinho")
        manha = self._eps()[-1]
        self.assertEqual(manha["cause"], "O Patrick pediu pra ela comer")   # 06/10 (passo 5): frase com maiúscula
        self.assertEqual(manha["started_at"][:16], "2026-09-28T08:27")
        self.assertAlmostEqual(manha["intensity"], 0.4)
        self.assertAlmostEqual(self._eps()[0]["intensity"], 0.66)      # 0.6 + 10%, uma vez só

    def test_appraise_world_repetido_nao_infla(self):
        with self.db.get_connection() as conn:
            for key, quando in (("banho:2026-09-27T2011", at(27, 20, 11)), ("banho:2026-09-27T2130", at(27, 21, 30))):
                conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                                autonomy_level,importance,participants_json,share_worthy,created_at)
                                VALUES (?,?,'routine','banho','Tomou banho (20:11–20:26).','simulated',1,0.05,
                                '["marina"]',0.1,?)""", (key, quando.isoformat(), quando.isoformat()))
            conn.commit()
        e = EmotionEngine(self.db)
        with patch.object(EmotionEngine, "energy", return_value=0.7):
            for minuto in range(0, 60, 5):
                e.appraise_world(at(27, 22, minuto))
        eps = [x for x in self._eps() if x["kind"] == "alivio"]
        self.assertEqual(len(eps), 1)
        self.assertAlmostEqual(eps[0]["intensity"], 0.22)


class SaudadeTest(Base):
    """5. A saudade só cresce com ela acordada (painel e mensagem de saudade)."""

    def setUp(self):
        super().setUp()
        self._fala(at(27, 23, 4, 25), "user", "Marina, vou dormir, boa noite tá?")

    def test_dormindo_nao_enche_a_saudade(self):
        self.assertAlmostEqual(awake_hours_since(self.db, at(27, 23, 4, 25), at(28, 5, 55)), 0.543, places=2)
        self.assertLess(EmotionEngine(self.db)._missing(at(28, 5, 55)), 0.15)

    def test_acordada_volta_a_crescer(self):
        self.assertAlmostEqual(EmotionEngine(self.db)._missing(at(28, 9, 33)), 0.18 * (0.543 + 2.0), places=2)

    def test_sem_sono_no_meio_e_o_relogio(self):
        self.assertAlmostEqual(awake_hours_since(self.db, at(28, 14, 0), at(28, 17, 0)), 3.0)

    def test_mensagem_de_saudade_usa_a_mesma_conta(self):
        with patch.object(ProactivityService, "_compute_state_factor", return_value=(1.0, "home")):
            s = ProactivityService(self.db).saudade(at(28, 8, 30))
        self.assertLess(s["level"], 0.6)
        self.assertFalse(s["trigger"])
        self.assertGreater(s["hours"], 9)                   # o "faz 9h que ele não fala" continua o relógio


class CiumeDeleTest(Base):
    """6. O ciúme dele não é o ciuminho dela."""

    def test_desconfianca_seria_chateia_leve(self):
        apply_patrick_event(self.db, {"kind": "desconfiou", "cause": "o Patrick desconfiou de uma foto · Instagram"},
                            at(27, 23, 3))
        with self.db.get_connection() as conn:
            ep = dict(conn.execute("SELECT * FROM emotion_episodes").fetchone())
        self.assertEqual((ep["family"], ep["kind"], ep["target"]), ("raiva", "chateacao", "o Patrick"))
        self.assertAlmostEqual(ep["intensity"], 0.2)
        self.assertEqual(ep["half_life_min"], 90)
        self.assertEqual(ep["sticky"], 0)

    def test_planner_sabe_de_quem_e_o_ciume(self):
        from planner import PLANNER_SYSTEM_PROMPT as p
        self.assertIn("|ciume|desconfiou|", p)
        self.assertIn("O ciúme DELE nunca é ciume", p)
        self.assertNotIn("desconfiou de uma foto", p)


if __name__ == "__main__":
    unittest.main()
