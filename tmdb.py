"""Fase D6 parte 2 — cliente do TMDB (The Movie Database).

Dá realidade ao que ela assiste: título oficial em pt-BR, se é anime, dorama,
série ou filme, quantos episódios, quanto dura, onde está passando no Brasil,
recomendações parecidas com o que ela amou, o que está popular por aqui e o
próximo episódio de quem ainda está no ar.

This product uses the TMDB API but is not endorsed or certified by TMDB.
(Uso não comercial com crédito — ver README.)

* Cache em `tmdb_cache` (migration 024): cada resposta vale dias; a API é
  consultada poucas vezes por dia.
* A suíte de testes nunca chama a API real (`ALLOW_LIVE_IN_TESTS`).
* Sem chave, offline ou erro: `available()` falso / `None`, e o watch.py cai
  na lista fixa de antes.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

API_URL = "https://api.themoviedb.org/3"
API_TIMEOUT_S = 8
ALLOW_LIVE_IN_TESTS = False
LANGUAGE = "pt-BR"
REGION = "BR"
TTL = {"search": 30, "details": 1, "recs": 14, "providers": 3, "discover": 1}   # dias (details: próximo episódio)
ANIMATION = 16
NOT_HER_GENRES = "10764,10767,10762,10759,80"   # reality, talk, kids, ação & aventura, crime
UNAVAILABLE = object()      # sentinela: API fora do ar (≠ "não encontrado")


def _settings():
    from config import settings
    return settings


class TMDB:
    def __init__(self, db):
        self.db = db

    # ---------------------------------------------------------------- base --
    @staticmethod
    def available() -> bool:
        s = _settings()
        if not getattr(s, "TMDB_ENABLED", True):
            return False
        if not (getattr(s, "TMDB_API_TOKEN", "") or getattr(s, "TMDB_API_KEY", "")):
            return False
        from db import _running_under_tests
        return not (_running_under_tests() and not ALLOW_LIVE_IN_TESTS)

    def _cached(self, key: str) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT payload_json, expires_at FROM tmdb_cache WHERE cache_key=?",
                               (key,)).fetchone()
        if row and row["expires_at"] > datetime.now().isoformat():
            return json.loads(row["payload_json"])
        return None

    def _store(self, key: str, payload: dict, days: int) -> None:
        now = datetime.now()
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO tmdb_cache (cache_key, payload_json, fetched_at, expires_at)
                            VALUES (?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET
                            payload_json=excluded.payload_json, fetched_at=excluded.fetched_at,
                            expires_at=excluded.expires_at""",
                         (key, json.dumps(payload, ensure_ascii=False), now.isoformat(),
                          (now + timedelta(days=days)).isoformat()))
            conn.commit()

    def _get(self, path: str, params: dict, ttl_kind: str):
        """GET com cache. Devolve o JSON, ou UNAVAILABLE se não deu pra consultar."""
        params = {"language": LANGUAGE, **params}
        key = f"{path}?{urllib.parse.urlencode(sorted(params.items()))}"
        hit = self._cached(key)
        if hit is not None:
            return hit
        if not self.available():
            return UNAVAILABLE
        s = _settings()
        headers = {"accept": "application/json"}
        token = getattr(s, "TMDB_API_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            params["api_key"] = s.TMDB_API_KEY
        req = urllib.request.Request(f"{API_URL}{path}?{urllib.parse.urlencode(params)}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("tmdb.unavailable path=%s error=%s", path, type(exc).__name__)
            return UNAVAILABLE
        self._store(key, data, TTL[ttl_kind])
        return data

    # ---------------------------------------------------------- normalizar --
    @staticmethod
    def kind_of(media: str, genre_ids: list, countries: list, language: str = "") -> str:
        if media == "movie":
            return "filme"
        if ANIMATION in genre_ids and ("JP" in countries or language == "ja"):
            return "anime"
        if "KR" in countries or language == "ko":
            return "dorama"
        return "série"

    def details(self, media: str, tmdb_id: int):
        data = self._get(f"/{media}/{tmdb_id}", {}, "details")
        if data is UNAVAILABLE:
            return UNAVAILABLE
        genres = [g["id"] for g in data.get("genres", [])]
        countries = data.get("origin_country") or [c.get("iso_3166_1") for c in
                                                    data.get("production_countries", [])]
        kind = self.kind_of(media, genres, countries, data.get("original_language", ""))
        if media == "movie":
            episodes, minutes = 1, int(data.get("runtime") or 110)
        else:
            episodes = int(data.get("number_of_episodes") or 12)
            runtimes = data.get("episode_run_time") or []
            minutes = int(runtimes[0]) if runtimes else {"anime": 24, "dorama": 65}.get(kind, 45)
        nxt = data.get("next_episode_to_air") or {}
        return {"id": tmdb_id, "media": media, "title": data.get("name") or data.get("title"),
                "original": data.get("original_name") or data.get("original_title"),
                "kind": kind, "episodes": episodes, "minutes": minutes,
                "in_production": bool(data.get("in_production")),
                "next_air_date": nxt.get("air_date"), "next_episode": nxt.get("episode_number"),
                "next_season": nxt.get("season_number")}

    # ------------------------------------------------------------- consultas --
    def find(self, title: str, kind_hint: Optional[str] = None):
        """Obra real com esse nome, ou None se não existe; UNAVAILABLE se não deu pra saber.

        `kind_hint` desempata: "One Piece" anime ≠ a série live-action da Netflix."""
        data = self._get("/search/multi", {"query": title, "include_adult": "false"}, "search")
        if data is UNAVAILABLE:
            return UNAVAILABLE
        wanted = title.casefold().strip()
        results = [r for r in data.get("results", []) if r.get("media_type") in ("tv", "movie")]
        if kind_hint in ("anime", "dorama", "série", "filme"):
            typed = [r for r in results if self.kind_of(r["media_type"], r.get("genre_ids", []),
                                                        r.get("origin_country", []),
                                                        r.get("original_language", "")) == kind_hint]
            results = typed or results
        if not results:
            return None
        exact = [r for r in results if wanted in {(r.get("name") or r.get("title") or "").casefold(),
                                                  (r.get("original_name") or r.get("original_title") or "").casefold()}]
        best = (exact or sorted(results, key=lambda r: r.get("popularity", 0), reverse=True))[0]
        return self.details(best["media_type"], best["id"])

    def recommendations(self, media: str, tmdb_id: int) -> list[dict]:
        data = self._get(f"/{media}/{tmdb_id}/recommendations", {}, "recs")
        if data is UNAVAILABLE:
            return []
        out = []
        for r in data.get("results", [])[:10]:
            m = r.get("media_type") or media
            out.append({"id": r["id"], "media": m, "title": r.get("name") or r.get("title"),
                        "kind": self.kind_of(m, r.get("genre_ids", []), r.get("origin_country", []),
                                             r.get("original_language", ""))})
        return out

    def popular_in_brazil(self, kind: str) -> list[dict]:
        """O que está popular nos streamings do Brasil agora, pro gosto dela."""
        params = {"watch_region": REGION, "with_watch_monetization_types": "flatrate",
                  "sort_by": "popularity.desc", "vote_count.gte": 50,
                  # fora: reality, talk show, infantil, ação e crime — não é o gosto dela
                  "without_genres": NOT_HER_GENRES}
        if kind == "anime":
            # anime de ação (Dandadan, Frieren) é gosto dela: só tira reality/talk/infantil
            params.update({"with_genres": ANIMATION, "with_original_language": "ja",
                           "without_genres": "10764,10767,10762"})
        elif kind == "dorama":
            params.update({"with_original_language": "ko", "with_genres": "18|35"})
        else:
            params.update({"with_genres": "35|18", "without_genres": f"{NOT_HER_GENRES},{ANIMATION}"})
        data = self._get("/discover/tv", params, "discover")
        if data is UNAVAILABLE:
            return []
        return [{"id": r["id"], "media": "tv", "title": r.get("name"),
                 "kind": self.kind_of("tv", r.get("genre_ids", []), r.get("origin_country", []),
                                      r.get("original_language", ""))}
                for r in data.get("results", [])[:15]]

    def where_to_watch(self, media: str, tmdb_id: int) -> list[str]:
        data = self._get(f"/{media}/{tmdb_id}/watch/providers", {}, "providers")
        if data is UNAVAILABLE:
            return []
        br = (data.get("results") or {}).get(REGION) or {}
        return [p["provider_name"] for p in br.get("flatrate", [])][:3]
