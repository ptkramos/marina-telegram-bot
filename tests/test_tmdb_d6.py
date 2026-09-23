"""Fase D6 parte 2 — TMDB, com a rede simulada (a suíte nunca chama a API real)."""
import io
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import tmdb
import watch
from config import settings
from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from tmdb import TMDB, UNAVAILABLE
from watch import Watching

TODAY = date.today().isoformat()
FAKE = {
    "/search/multi": {
        "one piece": {"results": [
            {"media_type": "tv", "id": 111, "name": "ONE PIECE: A Série", "original_name": "ONE PIECE",
             "genre_ids": [10759], "origin_country": ["US"], "original_language": "en", "popularity": 900},
            {"media_type": "tv", "id": 37854, "name": "One Piece", "original_name": "ワンピース",
             "genre_ids": [16, 10759], "origin_country": ["JP"], "original_language": "ja", "popularity": 500}]},
        "frieren": {"results": [
            {"media_type": "tv", "id": 209867, "name": "Frieren e a Jornada para o Além", "original_name": "葬送のフリーレン",
             "genre_ids": [16], "origin_country": ["JP"], "original_language": "ja", "popularity": 300}]},
        "dandadan": {"results": [
            {"media_type": "tv", "id": 240411, "name": "DAN DA DAN", "original_name": "ダンダダン",
             "genre_ids": [16], "origin_country": ["JP"], "original_language": "ja", "popularity": 300}]},
        "naruto uzumaki shippuden xyz": {"results": []},
    },
    "/tv/37854": {"name": "One Piece", "genres": [{"id": 16}], "origin_country": ["JP"], "original_language": "ja",
                  "number_of_episodes": 1181, "episode_run_time": [24], "in_production": True,
                  "next_episode_to_air": {"air_date": TODAY, "episode_number": 7, "season_number": 23}},
    "/tv/209867": {"name": "Frieren e a Jornada para o Além", "genres": [{"id": 16}], "origin_country": ["JP"],
                   "original_language": "ja", "number_of_episodes": 38, "episode_run_time": [25]},
    "/tv/240411": {"name": "DAN DA DAN", "genres": [{"id": 16}], "origin_country": ["JP"],
                   "original_language": "ja", "number_of_episodes": 24, "episode_run_time": [24]},
    "/tv/240411/recommendations": {"results": [
        {"id": 46260, "name": "Bleach", "genre_ids": [16], "origin_country": ["JP"], "original_language": "ja"},
        {"id": 65930, "name": "Mob Psycho 100", "genre_ids": [16], "origin_country": ["JP"], "original_language": "ja"}]},
    "/tv/46260": {"name": "Bleach", "genres": [{"id": 16}], "origin_country": ["JP"], "original_language": "ja",
                  "number_of_episodes": 366, "episode_run_time": [24]},
    "/tv/65930": {"name": "Mob Psycho 100", "genres": [{"id": 16}], "origin_country": ["JP"],
                  "original_language": "ja", "number_of_episodes": 37, "episode_run_time": [24]},
    "/tv/65930/watch/providers": {"results": {"BR": {"flatrate": [{"provider_name": "Crunchyroll"}]}}},
    "/tv/209867/watch/providers": {"results": {"BR": {"flatrate": [{"provider_name": "Netflix"}]}}},
}


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TmdbTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "tmdb.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.calls = []
        for p in (patch.object(tmdb, "ALLOW_LIVE_IN_TESTS", True),
                  patch.multiple(settings, TMDB_API_KEY="fake", TMDB_API_TOKEN="", TMDB_ENABLED=True),
                  patch.object(tmdb.urllib.request, "urlopen", side_effect=self._fake)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _fake(self, req, timeout=None):
        url = urlparse(req.full_url)
        path = url.path.replace("/3", "", 1)
        self.calls.append(path)
        data = FAKE.get(path)
        if path == "/search/multi":
            data = data.get(parse_qs(url.query)["query"][0].casefold(), {"results": []})
        if data is None:
            data = {"results": []}
        return _FakeResp(json.dumps(data).encode("utf-8"))

    def test_kind_hint_picks_the_anime_not_the_live_action(self):
        info = TMDB(self.db).find("One Piece", "anime")
        self.assertEqual((info["id"], info["kind"], info["episodes"]), (37854, "anime", 1181))

    def test_unknown_title_is_rejected_and_cache_avoids_repeat_calls(self):
        t = TMDB(self.db)
        self.assertIsNone(t.find("Naruto Uzumaki Shippuden XYZ"))
        before = len(self.calls)
        t.find("Frieren", "anime")
        t.find("Frieren", "anime")
        self.assertEqual(len(self.calls) - before, 2, "search + details, e depois só cache")

    def test_patrick_mention_becomes_real_data_or_nothing(self):
        tv = Watching(self.db)
        self.assertTrue(tv.add_patrick_mention("frieren", "anime"))
        m = tv.state()["patrick_mentions"][0]
        self.assertEqual((m["title"], m["episodes"], m["minutes"]), ("Frieren e a Jornada para o Além", 38, 25))
        self.assertFalse(tv.add_patrick_mention("Naruto Uzumaki Shippuden XYZ", "anime"), "obra que não existe")

    def test_offline_falls_back_to_the_old_behaviour(self):
        with patch.object(tmdb.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertIs(TMDB(self.db).find("Frieren"), UNAVAILABLE)
            self.assertTrue(Watching(self.db).add_patrick_mention("Frieren", "anime"))

    def test_discovery_from_something_she_loved(self):
        tv = Watching(self.db)
        with patch.object(watch, "TMDB_DISCOVERY_SHARE", 1.0), \
             patch.object(tv, "_seen_titles", return_value={"dan da dan"}), \
             patch("random.Random.random", return_value=0.0), \
             patch("random.Random.choice", side_effect=lambda seq: next(s for s in seq if s[0] == "Dandadan")
                   if isinstance(seq[0], tuple) else seq[0]):
            pick = tv._pick_next([], date(2026, 9, 23))
        self.assertEqual(pick["title"], "Mob Psycho 100", "Bleach tem 366 eps e fica de fora")
        self.assertIn("parecido com Dandadan", pick["why"])
        self.assertEqual(pick["where"], "Crunchyroll")

    def test_new_episode_of_what_she_follows_is_news(self):
        created = Watching(self.db).new_episodes(datetime.combine(date.today(), datetime.min.time()).replace(hour=12))
        self.assertEqual(created, 1)
        with self.db.get_connection() as conn:
            text = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'tv:novo:%'").fetchone()[0]
        self.assertIn("Saiu episódio novo de One Piece", text)


if __name__ == "__main__":
    unittest.main()
