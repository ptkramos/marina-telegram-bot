"""O que o Patrick está ouvindo (Patrick, 26/09): como ver o que os amigos ouvem no Spotify.

Lê o Last.fm dele (usuário e chave no .env; só leitura, sem o segredo). Serve pra ela puxar
assunto: "tá ouvindo o quê aí?", "amo essa". O job do bot atualiza fora do turno.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

import config  # noqa: F401  (carrega o .env)

logger = logging.getLogger(__name__)

KEY = "lastfm_patrick_json"
RECENTE = timedelta(minutes=30)


class LastFm:
    def __init__(self, db):
        self.db = db
        self.user = os.getenv("LASTFM_USER", "")
        self.api_key = os.getenv("LASTFM_API_KEY", "")

    def _load(self) -> dict:
        raw = self.db.get_estado_relacional(KEY)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def atualizar(self, now: Optional[datetime] = None) -> bool:
        if not (self.user and self.api_key):
            return False
        q = urllib.parse.urlencode({"method": "user.getrecenttracks", "user": self.user, "api_key": self.api_key,
                                    "format": "json", "limit": 5})
        try:
            with urllib.request.urlopen(f"https://ws.audioscrobbler.com/2.0/?{q}", timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception:
            logger.warning("lastfm.fetch_falhou")
            return False
        faixas = []
        for t in (data.get("recenttracks") or {}).get("track") or []:
            tocando = (t.get("@attr") or {}).get("nowplaying") == "true"
            uts = (t.get("date") or {}).get("uts")
            quando = datetime.fromtimestamp(int(uts)).isoformat() if uts else None
            faixas.append({"nome": t.get("name", ""), "artista": (t.get("artist") or {}).get("#text", ""),
                           "tocando": tocando, "quando": quando})
        self.db.set_estado_relacional(KEY, json.dumps({"at": (now or datetime.now()).isoformat(), "faixas": faixas},
                                                      ensure_ascii=False))
        return True

    def ouvindo(self, now: datetime) -> Optional[dict]:
        """A música que ele está ouvindo agora (ou acabou de ouvir, até 30 min)."""
        st = self._load()
        if not st.get("at") or now - datetime.fromisoformat(st["at"]) > timedelta(minutes=15):
            return None                                   # dado velho: não afirma nada
        for f in st.get("faixas", []):
            if f["tocando"]:
                return {**f, "agora": True}
            if f["quando"] and now - datetime.fromisoformat(f["quando"]) <= RECENTE:
                return {**f, "agora": False}
        return None

    def prompt_lines(self, now: datetime) -> list[str]:
        f = self.ouvindo(now)
        if not f:
            return []
        quando = "está ouvindo agora" if f["agora"] else "acabou de ouvir"
        return [f"- O Patrick {quando} \"{f['nome']}\" ({f['artista']}) — você vê isso no app de música, como "
                "amigo no Spotify. Pode puxar assunto se vier a calhar (sem repetir se já comentou)."]
