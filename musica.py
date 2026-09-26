"""Música de verdade (Patrick, 26/09 — etapa 1, mídia real).

* **Playlist dela**: quando o tempo livre é "ouvindo música", ela põe a playlist dela pra tocar —
  faixas **reais** (catálogo do iTunes, grátis e sem chave) dos artistas que ela curte e das
  músicas que ela adotou. A linha 2 do card acompanha o artista da faixa que está tocando e os
  passos são as faixas, com hora.
* **Catálogo**: vem do iTunes e fica guardado (renova por semana, fora do turno, no job do bot).
  Lançamento recente de artista dela vira novidade ("saiu música nova da Sabrina").
* **Música que o Patrick manda** (link do Apple Music, Spotify ou YouTube no chat): ela ouve de
  verdade no próximo momento livre em casa; se curtir, adota na playlist e pode comentar.
"""
from __future__ import annotations

import json
import logging
import random
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

CATALOGO_KEY = "musica_catalogo_json"
DELA_KEY = "musica_dela_json"
REFRESH_DAYS = 7
NOVIDADE_DIAS = 14
LIKE_BASE = 0.55                 # música dele de gênero que ela não curte muito
LIKE_GOSTO = 0.8                 # artista/gênero dela

ARTISTAS = ("Sabrina Carpenter", "Dua Lipa", "Taylor Swift", "Olivia Rodrigo", "Chappell Roan", "Anitta",
            "Luísa Sonza", "Marina Sena", "Pabllo Vittar", "Liniker", "YOASOBI", "Aimer", "Ado", "NewJeans",
            "BLACKPINK", "TWICE")
JAPONESES = ("YOASOBI", "Aimer", "Ado")
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")     # título que ela não leria no card
LINK_RE = re.compile(r"https?://(?:music\.apple\.com|open\.spotify\.com|(?:www\.|m\.)?youtube\.com|youtu\.be|"
                     r"music\.youtube\.com)/\S+", re.IGNORECASE)


def _get_json(url: str, timeout: int = 8) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MarinaBot)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        logger.warning("musica.fetch_falhou url=%s", url.split("?")[0])
        return None


def _faixa(r: dict) -> dict:
    return {"nome": r.get("trackName", ""), "artista": r.get("artistName", ""), "album": r.get("collectionName", ""),
            "ms": int(r.get("trackTimeMillis") or 200000), "lancamento": (r.get("releaseDate") or "")[:10],
            "id": r.get("trackId")}


class Musica:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------ estado --
    def _load(self, key: str) -> dict:
        raw = self.db.get_estado_relacional(key)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _store(self, key: str, data: dict) -> None:
        self.db.set_estado_relacional(key, json.dumps(data, ensure_ascii=False))

    def dela(self) -> dict:
        d = self._load(DELA_KEY)
        d.setdefault("adotadas", [])
        d.setdefault("ouvir", [])
        d.setdefault("ouvidas", [])
        return d

    # ---------------------------------------------------------- catálogo --
    def buscar_artista(self, artista: str) -> list[dict]:
        pais = "US" if artista in JAPONESES else "BR"      # loja americana traz os títulos romanizados
        q = urllib.parse.urlencode({"term": artista, "entity": "song", "attribute": "artistTerm",
                                    "country": pais, "limit": 40})
        data = _get_json(f"https://itunes.apple.com/search?{q}")
        if not data:
            return []
        alvo = artista.casefold()
        out, vistos = [], set()
        for r in data.get("results", []):
            f = _faixa(r)
            nome = f["nome"].split(" (")[0].split(" - ")[0].casefold()
            if f["artista"].casefold() != alvo or nome in vistos or not f["nome"] or _CJK.search(f["nome"]):
                continue                                  # só dela (sem feat. de outro dono, sem repetida)
            vistos.add(nome)
            out.append(f)
        return out[:25]

    def aquecer(self, now: Optional[datetime] = None, *, limite: int = 3) -> int:
        """Job do bot (fora do turno): renova até `limite` artistas vencidos. Devolve quantos."""
        now = now or datetime.now()
        cat = self._load(CATALOGO_KEY)
        feitos = 0
        for artista in ARTISTAS:
            c = cat.get(artista)
            if c and now - datetime.fromisoformat(c["at"]) < timedelta(days=REFRESH_DAYS):
                continue
            faixas = self.buscar_artista(artista)
            if faixas:
                antigas = {f["nome"] for f in (c or {}).get("faixas", [])}
                cat[artista] = {"at": now.isoformat(), "faixas": faixas}
                self._store(CATALOGO_KEY, cat)
                if c:
                    self._novidades(artista, [f for f in faixas if f["nome"] not in antigas], now)
            feitos += 1
            if feitos >= limite:
                break
        return feitos

    def _novidades(self, artista: str, novas: list[dict], now: datetime) -> None:
        for f in novas:
            try:
                lanc = date.fromisoformat(f["lancamento"])
            except ValueError:
                continue
            if (now.date() - lanc).days > NOVIDADE_DIAS:
                continue
            with self.db.get_connection() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                       autonomy_level,importance,participants_json,share_worthy,created_at)
                       VALUES (?,?,'midia',?,?,'real_world',1,0.3,?,0.5,?)""",
                    (f"musica:nova:{f['id']}", now.isoformat(), f"música nova de {artista}",
                     f"Descobriu que saiu música nova de {artista}: \"{f['nome']}\" ({f['album']}).",
                     json.dumps(["marina"]), now.isoformat()))
                conn.commit()

    def faixas(self, artista: str) -> list[dict]:
        return self._load(CATALOGO_KEY).get(artista, {}).get("faixas", [])

    # ---------------------------------------------------------- playlist --
    def playlist(self, inicio: datetime, fim: datetime, rng: random.Random) -> list[dict]:
        """As faixas que tocam no bloco (reais), com hora de início. Primeiro o que o Patrick mandou
        e ela ainda não ouviu; depois as adotadas e os artistas dela, embaralhados."""
        dela = self.dela()
        pendentes = [dict(f, dele=True) for f in dela["ouvir"]]
        cat = self._load(CATALOGO_KEY)
        artistas = [a for a in ARTISTAS if cat.get(a, {}).get("faixas")]
        if not artistas and not pendentes and not dela["adotadas"]:
            return []
        favoritos = rng.sample(artistas, k=min(len(artistas), rng.randint(2, 4))) if artistas else []
        pool = [f for a in favoritos for f in cat[a]["faixas"][:12]] + [dict(f) for f in dela["adotadas"]]
        rng.shuffle(pool)
        out, t = [], inicio
        for f in pendentes + pool:
            if t >= fim:
                break
            out.append({**{k: f.get(k) for k in ("nome", "artista", "album", "ms", "id")}, "dele": bool(f.get("dele")),
                        "at": t.isoformat()})
            t += timedelta(milliseconds=f.get("ms") or 200000)
        return out

    @staticmethod
    def tocando(faixas: list[dict], now: datetime) -> Optional[dict]:
        atual = None
        for f in faixas or []:
            if datetime.fromisoformat(f["at"]) <= now:
                atual = f
        return atual

    def ouviu(self, faixas: list[dict], now: datetime) -> None:
        """Faixas do Patrick que já tocaram: ela decide se curtiu (e adota)."""
        dela = self.dela()
        mudou = False
        for f in faixas or []:
            if not f.get("dele") or datetime.fromisoformat(f["at"]) + timedelta(milliseconds=f.get("ms") or 0) > now:
                continue                                  # só conta quando a faixa acabou de tocar
            pend = next((p for p in dela["ouvir"] if p.get("id") == f.get("id") and p["nome"] == f["nome"]), None)
            if not pend:
                continue
            dela["ouvir"].remove(pend)
            rng = random.Random(f"musica:gosto:{f['nome']}:{f['artista']}")
            curtiu = rng.random() < (LIKE_GOSTO if f["artista"] in ARTISTAS else LIKE_BASE)
            ouvida = {**pend, "ouviu_em": f["at"], "curtiu": curtiu}
            dela["ouvidas"] = (dela["ouvidas"] + [ouvida])[-30:]
            if curtiu and not any(a["nome"] == f["nome"] for a in dela["adotadas"]):
                dela["adotadas"].append({k: pend.get(k) for k in ("nome", "artista", "album", "ms", "id")})
            mudou = True
            with self.db.get_connection() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                       autonomy_level,importance,participants_json,share_worthy,created_at)
                       VALUES (?,?,'midia',?,?,'simulated',1,0.3,?,0.7,?)""",
                    (f"musica:ouviu:{f.get('id') or f['nome']}", f["at"], "ouviu a música do Patrick",
                     f"Ouviu \"{f['nome']}\" ({f['artista']}), que o Patrick mandou: "
                     + ("curtiu e botou na playlist dela." if curtiu else "não curtiu muito."),
                     json.dumps(["marina", "patrick_ramos"]), now.isoformat()))
                conn.commit()
        if mudou:
            self._store(DELA_KEY, dela)

    # ----------------------------------------------------- link do Patrick --
    def resolver_link(self, url: str) -> Optional[dict]:
        """Link de música → faixa real (nome, artista, álbum, duração)."""
        m = re.search(r"[?&]i=(\d+)", url) or re.search(r"music\.apple\.com/\w+/song/[^/]+/(\d+)", url)
        if m:
            data = _get_json(f"https://itunes.apple.com/lookup?id={m.group(1)}&country=BR")
            res = [r for r in (data or {}).get("results", []) if r.get("wrapperType") == "track"]
            return _faixa(res[0]) if res else None
        m = re.search(r"music\.apple\.com/\w+/album/[^/]+/(\d+)", url)
        if m:
            data = _get_json(f"https://itunes.apple.com/lookup?id={m.group(1)}&entity=song&country=BR")
            res = [r for r in (data or {}).get("results", []) if r.get("wrapperType") == "track"]
            return _faixa(res[0]) if res else None
        titulo = None
        if "spotify.com" in url:
            data = _get_json("https://open.spotify.com/oembed?url=" + urllib.parse.quote(url, safe=""))
            titulo = (data or {}).get("title")
        elif "youtu" in url:
            data = _get_json("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe=""))
            titulo = (data or {}).get("title")
            if data and " - " not in (titulo or "") and data.get("author_name"):
                titulo = f"{data['author_name'].replace(' - Topic', '')} {titulo}"
        if not titulo:
            return None
        termo = re.sub(r"\(.*?(clipe|video|vídeo|oficial|official|lyric).*?\)|\[.*?\]", "", titulo, flags=re.I)
        data = _get_json("https://itunes.apple.com/search?" + urllib.parse.urlencode(
            {"term": termo.replace(" - ", " "), "entity": "song", "country": "BR", "limit": 1}))
        res = (data or {}).get("results", [])
        return _faixa(res[0]) if res else None

    def link_do_patrick(self, texto: str, now: Optional[datetime] = None) -> Optional[dict]:
        """Chamado quando o Patrick manda mensagem: se tem link de música, entra na fila dela."""
        m = LINK_RE.search(texto or "")
        if not m:
            return None
        f = self.resolver_link(m.group(0).rstrip(").,!"))
        if not f:
            return None
        now = now or datetime.now()
        dela = self.dela()
        if not any(p["nome"] == f["nome"] and p["artista"] == f["artista"] for p in dela["ouvir"]):
            dela["ouvir"].append({**f, "mandou_em": now.isoformat()})
            self._store(DELA_KEY, dela)
        logger.info("musica.link_do_patrick faixa=%s artista=%s", f["nome"], f["artista"])
        return f

    # ------------------------------------------------------------- prompt --
    def prompt_lines(self, now: datetime) -> list[str]:
        dela = self.dela()
        lines = []
        for p in dela["ouvir"][-3:]:
            lines.append(f"- O Patrick te mandou \"{p['nome']}\" ({p['artista']}) e você AINDA NÃO OUVIU: vai ouvir "
                         "quando estiver livre em casa. Não finja que já ouviu.")
        for o in dela["ouvidas"][-3:]:
            quando = datetime.fromisoformat(o["ouviu_em"])
            if now - quando < timedelta(days=3):
                lines.append(f"- Você ouviu \"{o['nome']}\" ({o['artista']}), que o Patrick mandou, às "
                             f"{quando:%H:%M} de {quando:%d/%m}: " + ("curtiu e botou na sua playlist."
                                                                     if o["curtiu"] else "não curtiu muito (seja sincera, com jeitinho)."))
        if dela["adotadas"]:
            nomes = ", ".join(f"\"{a['nome']}\" ({a['artista']})" for a in dela["adotadas"][-5:])
            lines.append(f"- Na sua playlist tem músicas que vieram dele: {nomes}.")
        try:
            from lastfm import LastFm
            lines += LastFm(self.db).prompt_lines(now)
        except Exception:
            pass
        return (["[MÚSICA — real; não invente faixa que não esteja aqui ou no seu dia]"] + lines) if lines else []
