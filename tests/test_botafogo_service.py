"""
Testes Unitários Offline para o BotafogoLiveService (API-Sports).
Valida parsing de payloads, detecção e deduplicação de eventos, transições de status,
controle estrito de cota diária e métodos de simulação.
"""
import unittest
from unittest.mock import patch, MagicMock

from botafogo_service import BotafogoLiveService


class TestBotafogoService(unittest.TestCase):
    def setUp(self):
        self.service = BotafogoLiveService(team_id=120, api_key="fake_key_123")

    def test_quota_guard(self):
        # Initial requests
        self.assertEqual(self.service.get_requests_today(), 0)
        self.assertTrue(self.service.can_make_request())

        # Simulate 90 requests
        today = self.service._get_today_str()
        self.service.daily_requests[today] = 90
        self.assertFalse(self.service.can_make_request())

        # fetch_live_fixture should be blocked without network call
        with patch("botafogo_service.urlopen") as mock_url:
            result = self.service.fetch_live_fixture()
            self.assertIsNone(result)
            mock_url.assert_not_called()

    def test_parse_fixture(self):
        sample_fixture = {
            "fixture": {
                "id": 1492385,
                "status": {"short": "1H", "long": "First Half", "elapsed": 44}
            },
            "teams": {
                "home": {"id": 7848, "name": "Mirassol"},
                "away": {"id": 120, "name": "Botafogo"}
            },
            "goals": {"home": 1, "away": 0},
            "league": {"name": "Brasileirão"},
            "events": [
                {
                    "time": {"elapsed": 16},
                    "team": {"id": 7848, "name": "Mirassol"},
                    "player": {"name": "Carlos Eduardo"},
                    "type": "Goal",
                    "detail": "Normal Goal"
                }
            ]
        }

        parsed = self.service.parse_fixture(sample_fixture)
        self.assertEqual(parsed["fixture_id"], 1492385)
        self.assertFalse(parsed["is_botafogo_home"])
        self.assertEqual(parsed["opponent"], "Mirassol")
        self.assertEqual(parsed["botafogo_goals"], 0)
        self.assertEqual(parsed["opponent_goals"], 1)
        self.assertEqual(parsed["status_short"], "1H")
        self.assertEqual(parsed["elapsed"], 44)

    def test_event_detection_and_deduplication(self):
        sample_fixture = {
            "fixture": {
                "id": 1492385,
                "status": {"short": "1H", "long": "First Half", "elapsed": 30}
            },
            "teams": {
                "home": {"id": 7848, "name": "Mirassol"},
                "away": {"id": 120, "name": "Botafogo"}
            },
            "goals": {"home": 1, "away": 1},
            "league": {"name": "Brasileirão"},
            "events": [
                {
                    "time": {"elapsed": 16},
                    "team": {"id": 7848, "name": "Mirassol"},
                    "player": {"name": "Carlos Eduardo"},
                    "type": "Goal",
                    "detail": "Normal Goal"
                },
                {
                    "time": {"elapsed": 28},
                    "team": {"id": 120, "name": "Botafogo"},
                    "player": {"name": "Igor Jesus"},
                    "type": "Goal",
                    "detail": "Normal Goal"
                }
            ]
        }

        # First run detects 2 goals
        events = self.service.check_live_updates(live_data=sample_fixture)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "gol_adversario")
        self.assertEqual(events[1]["type"], "gol_botafogo")
        self.assertIn("Igor Jesus", events[1]["description"])

        # Second run with same data must yield 0 new events
        events_again = self.service.check_live_updates(live_data=sample_fixture)
        self.assertEqual(len(events_again), 0)

    def test_halftime_and_fulltime_transitions(self):
        # Halftime transition
        ht_fixture = {
            "fixture": {
                "id": 1492385,
                "status": {"short": "HT", "long": "Halftime", "elapsed": 45}
            },
            "teams": {
                "home": {"id": 7848, "name": "Mirassol"},
                "away": {"id": 120, "name": "Botafogo"}
            },
            "goals": {"home": 1, "away": 0},
            "league": {"name": "Brasileirão"},
            "events": []
        }

        # Simulate we came from 1H
        self.service.last_status[1492385] = "1H"
        events = self.service.check_live_updates(live_data=ht_fixture)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "intervalo")

        # Fulltime transition
        ft_fixture = {
            "fixture": {
                "id": 1492385,
                "status": {"short": "FT", "long": "Match Finished", "elapsed": 90}
            },
            "teams": {
                "home": {"id": 7848, "name": "Mirassol"},
                "away": {"id": 120, "name": "Botafogo"}
            },
            "goals": {"home": 1, "away": 2},
            "league": {"name": "Brasileirão"},
            "events": []
        }
        self.service.last_status[1492385] = "2H"
        events_ft = self.service.check_live_updates(live_data=ft_fixture)
        self.assertEqual(len(events_ft), 1)
        self.assertEqual(events_ft[0]["type"], "fim_jogo")
        self.assertIn("venceu", events_ft[0]["description"])

    def test_simulate_event(self):
        sim = self.service.simulate_event("gol_pro", opponent="Flamengo", score="Botafogo 2 x 1 Flamengo", elapsed=89, player="Luiz Henrique")
        self.assertEqual(sim["type"], "gol_botafogo")
        self.assertEqual(sim["opponent"], "Flamengo")
        self.assertIn("Luiz Henrique", sim["description"])

        sim_contra = self.service.simulate_event("gol_contra", opponent="Palmeiras")
        self.assertEqual(sim_contra["type"], "gol_adversario")
        self.assertEqual(sim_contra["opponent"], "Palmeiras")


if __name__ == "__main__":
    unittest.main()
