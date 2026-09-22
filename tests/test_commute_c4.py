"""Fase C.4 — locomoção viva (tabela local)."""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import commute
from commute import Commute
from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible


class CommuteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "c4.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.c = Commute(self.db)
        from academic_life import AcademicLife
        life = AcademicLife(self.db)
        self.class_day = next(date(2026, 9, 21) + timedelta(days=i) for i in range(14)
                              if life.blocks_on(date(2026, 9, 21) + timedelta(days=i)))
        blocks = life.blocks_on(self.class_day)
        self.first = min(datetime.fromisoformat(b["start_at"]) for b in blocks)
        self.last = max(datetime.fromisoformat(b["end_at"]) for b in blocks)

    def tearDown(self):
        self.temp.cleanup()

    def test_ida_e_volta_da_puc(self):
        ida, volta = [l for l in self.c.legs_on(self.class_day) if "puc" in l.key]
        self.assertEqual(ida.end, self.first)
        self.assertEqual(volta.start, self.last)
        self.assertLessEqual((ida.end - ida.start).total_seconds() / 60, commute.CLASS_GO_MAX_MIN)
        self.assertLessEqual((volta.end - volta.start).total_seconds() / 60, commute.CLASS_BACK_MAX_MIN)
        self.assertIn(ida.mode, ("onibus", "metro_onibus", "uber"))
        self.assertTrue(volta.activity(volta.start).startswith("voltando da PUC pra casa"))

    def test_escolha_gravada_nao_muda_no_meio_do_caminho(self):
        before = [(l.mode, l.end) for l in self.c.legs_on(self.class_day)]
        with patch.object(Commute, "_energy", return_value=0.1), \
             patch.object(Commute, "_heavy_rain", return_value=True):
            after = [(l.mode, l.end) for l in self.c.legs_on(self.class_day)]
        self.assertEqual(before, after)

    def test_noite_e_chuva(self):
        noite = datetime(2026, 9, 26, 23, 30)
        modes = {Commute(self.db)._decide(noite.date(), f"t{i}", "Botafogo", noite)[0] for i in range(20)}
        self.assertNotIn("a_pe", modes)
        with patch.object(Commute, "_heavy_rain", return_value=True):
            dia = datetime(2026, 9, 26, 15, 0)
            modes = {self.c._decide(dia.date(), f"c{i}", "Copacabana", dia)[0] for i in range(30)}
        self.assertNotIn("a_pe", modes)

    def test_pico_alonga_o_onibus(self):
        pico = datetime(2026, 9, 23, 8, 0)
        fora = datetime(2026, 9, 23, 14, 0)
        with patch.object(commute, "BASE_WEIGHT", {"onibus": 1.0, "metro_onibus": 0.0, "uber": 0.0}):
            _, m_pico = self.c._decide(pico.date(), "x", "Gávea", pico)
            _, m_fora = self.c._decide(fora.date(), "x", "Gávea", fora)
        self.assertGreater(m_pico, m_fora)

    def test_saida_com_amiga_tem_ida_e_volta(self):
        from calendar_world import CalendarWorld
        day = date(2026, 9, 26)
        CalendarWorld(self.db).create_commitment(
            source_key=f"outing:{day.isoformat()}:1", event_type="social",
            description="Saindo com a Bia no Quartinho Bar", start_at=datetime(2026, 9, 26, 21, 0),
            end_at=datetime(2026, 9, 26, 23, 30), location_key="quartinho_bar",
            metadata={"friends": ["bia_andrade"], "origin": "social_day"})
        legs = [l for l in self.c.legs_on(day) if "outing" in l.key]
        self.assertEqual(len(legs), 2)
        self.assertEqual(legs[0].end, datetime(2026, 9, 26, 21, 0))
        self.assertIn("pro Quartinho Bar", legs[0].activity(legs[0].start))
        self.assertIn("do Quartinho Bar pra casa", legs[1].activity(legs[1].start))

    def test_resolve_mostra_ela_a_caminho(self):
        from response_availability import ResponseAvailabilityPolicy
        from world_state import WorldStateManager
        volta = [l for l in self.c.legs_on(self.class_day) if l.key.endswith("puc:volta")][0]
        meio = volta.start + (volta.end - volta.start) / 2
        snap = WorldStateManager(self.db).resolve(meio, force=True)
        self.assertTrue(snap["activity"].startswith("voltando da PUC pra casa"))
        self.assertEqual(json.loads(snap["source_json"])["reason"], "commute")
        kind = ResponseAvailabilityPolicy(self.db)._map_place_activity(None, snap["activity"])
        self.assertEqual(kind, "COMMUTE")

    def test_sem_largada_limpa_nao_grava_nada(self):
        with patch.object(commute, "INCIDENT_CHANCE", 1.0):
            self.assertEqual(self.c.materialize(datetime.combine(self.class_day, datetime.max.time())), 0)

    def test_imprevisto_vira_acontecimento_so_depois_de_acontecer(self):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        with patch.object(commute, "INCIDENT_CHANCE", 1.0):
            leg = [l for l in self.c.legs_on(self.class_day) if l.key.endswith("puc:volta")][0]
            self.assertTrue(leg.incident)
            self.c.materialize(leg.incident_at - timedelta(minutes=1))
            key = f"{leg.key}:imprevisto"
            with self.db.get_connection() as conn:
                n0 = conn.execute("SELECT COUNT(*) FROM life_events WHERE event_key=?", (key,)).fetchone()[0]
            self.c.materialize(leg.end)
            self.c.materialize(leg.end + timedelta(minutes=5))
            with self.db.get_connection() as conn:
                rows = conn.execute("SELECT summary FROM life_events WHERE event_key=?", (key,)).fetchall()
        self.assertEqual(n0, 0)
        self.assertEqual(len([r for r in rows if leg.incident in r["summary"]]), 1)
        self.assertIn(leg.incident, leg.activity(leg.incident_at))


class LiveTimesTests(unittest.TestCase):
    """Distance Matrix API: rede simulada — a suíte nunca chama a API real."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "c4live.db")
        seed_world_bible(self.db)
        self.c = Commute(self.db)
        from config import settings
        for p in (patch.object(settings, "DISTANCE_MATRIX_KEY", "chave-teste"),
                  patch.object(settings, "COMMUTE_LIVE_TIMES", True),
                  patch.object(commute, "ALLOW_LIVE_IN_TESTS", True),
                  patch.object(commute, "BASE_WEIGHT", {"onibus": 0.0, "metro_onibus": 0.0, "uber": 1.0})):
            p.start()
            self.addCleanup(p.stop)
        self.when = datetime.now() + timedelta(days=1)
        self.when = self.when.replace(hour=14, minute=0)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _resp(seconds, status="OK"):
        body = json.dumps({"rows": [{"elements": [{"status": status, "duration": {"value": seconds},
                                                   "duration_in_traffic": {"value": seconds}}]}]})

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body.encode()
        return R()

    def test_minutos_vem_da_api_com_transito(self):
        place = {"name": "PUC-Rio", "region": "Gávea", "truth_type": "real"}
        with patch("urllib.request.urlopen", return_value=self._resp(31 * 60)) as net:
            mode, minutes = self.c._decide(self.when.date(), "x", "Gávea", self.when, place=place)
        self.assertEqual((mode, minutes), ("uber", 31))
        url = net.call_args[0][0]
        self.assertIn("mode=driving", url)
        self.assertIn("PUC-Rio", urllib_unquote(url))
        self.assertIn("departure_time=", url)

    def test_valor_absurdo_fica_no_limite_da_tabela(self):
        with patch("urllib.request.urlopen", return_value=self._resp(240 * 60)):
            _, minutes = self.c._decide(self.when.date(), "x", "Gávea", self.when,
                                        place={"name": "PUC-Rio", "region": "Gávea"})
        self.assertEqual(minutes, int(22 * commute.API_CLAMP[1]))

    def test_falha_da_api_cai_na_tabela(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError()):
            _, minutes = self.c._decide(self.when.date(), "x", "Gávea", self.when,
                                        place={"name": "PUC-Rio", "region": "Gávea"})
        self.assertTrue(18 <= minutes <= 26)
        with patch("urllib.request.urlopen", return_value=self._resp(0, status="ZERO_RESULTS")):
            _, minutes = self.c._decide(self.when.date(), "y", "Gávea", self.when,
                                        place={"name": "PUC-Rio", "region": "Gávea"})
        self.assertTrue(18 <= minutes <= 26)

    def test_lugar_ficticio_vai_so_pela_regiao(self):
        q = Commute._query({"name": "Agência boutique da Lívia (fictícia)", "region": "Ipanema"})
        self.assertEqual(q, "Ipanema, Rio de Janeiro, RJ, Brasil")

    def test_sem_liberacao_a_suite_nunca_chama_a_api(self):
        with patch.object(commute, "ALLOW_LIVE_IN_TESTS", False), \
             patch("urllib.request.urlopen") as net:
            self.c._decide(self.when.date(), "z", "Gávea", self.when, place={"name": "PUC-Rio", "region": "Gávea"})
        net.assert_not_called()


def urllib_unquote(url):
    from urllib.parse import unquote_plus
    return unquote_plus(url)


if __name__ == "__main__":
    unittest.main()
