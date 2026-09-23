"""Fase D6 (parte 1) — o que ela está assistindo, e o que ela descobre sozinha.

Cânone de gostos decidido pelo Patrick em 23/09 (migration 023): romance e
comédia romântica, doramas, animes com a Marin Kitagawa como inspiração (não
cópia), um lado ecchi/shonen, e One Piece — que ela começou por causa dele.
"É importante que o gosto dela faça ela procurar assistir coisas novas
sozinha": quando termina um título, ela escolhe o próximo numa lista de títulos
**reais** parecidos com o que ela gosta; se curtir, vira gosto dela.

* Noites em casa: 1 a 3 episódios depois do jantar, antes de deitar — vira
  estado ("vendo Paradise Kiss no sofá") e acontecimento do dia.
* One Piece: um episódio em algumas noites, devagar.
* Prompt: o que ela está vendo, em que episódio, e o que já viu. Título fora
  desta lista não existe pra ela (o prompt proíbe inventar título).
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta
from typing import Optional

STATE_KEY = "marina_watch_json"

# (título, tipo, episódios, minutos por episódio, de onde ela tirou a ideia)
DISCOVERY_POOL = (
    ("Paradise Kiss", "anime", 12, 23, "estudante virando modelo e estilista — viu um edit no TikTok"),
    ("Nana", "anime", 47, 23, "a Bia disse que era a cara dela, pelos looks"),
    ("Horimiya", "anime", 13, 23, "apareceu no TikTok de romance"),
    ("Toradora!", "anime", 25, 23, "indicação de comédia romântica clássica"),
    ("Spy x Family", "anime", 25, 24, "todo mundo comentando"),
    ("Oshi no Ko", "anime", 11, 24, "curiosidade sobre o mundo das idols"),
    ("Chainsaw Man", "anime", 12, 24, "mesma pegada doida de Dandadan"),
    ("Jujutsu Kaisen", "anime", 24, 24, "shonen que o Theo vive citando"),
    ("Shikimori's Not Just a Cutie", "anime", 12, 23, "romance fofinho pra ver antes de dormir"),
    ("Heartstopper", "série", 8, 30, "a Bia assistiu e amou"),
    ("XO, Kitty", "série", 10, 30, "spin-off de Para Todos os Garotos"),
    ("Sex Education", "série", 8, 50, "comentada na turma da PUC"),
    ("Uma Advogada Extraordinária", "dorama", 16, 70, "dorama que todo mundo recomenda"),
    ("Rainha das Lágrimas", "dorama", 16, 80, "o dorama do momento"),
    ("Hometown Cha-Cha-Cha", "dorama", 16, 70, "comédia romântica de praia"),
)
# Obra citada pelo Patrick (episódios, minutos) — sem catálogo, um tamanho típico.
MENTION_DEFAULTS = {"anime": (12, 24), "série": (8, 45), "dorama": (16, 65), "filme": (1, 110)}
MENTION_PRIORITY = 0.65          # na próxima escolha, o que ele falou costuma ganhar
TMDB_DISCOVERY_SHARE = 0.65      # com TMDB: 65% das descobertas vêm dele, o resto da lista fixa
MAX_EPISODES = 60                # obra enorme não vira "o que ela está vendo"
FOLLOWED_ONGOING = ("One Piece", "Dandadan")   # ela acompanha: episódio novo vira notícia
ONE_PIECE = ("One Piece", "anime", 1100, 24)
ONE_PIECE_START_EP = 95          # começou por causa do Patrick; está no começo de Alabasta
ONE_PIECE_NIGHT_CHANCE = 0.3
WATCH_NIGHT_CHANCE = 0.65
LIKE_CHANCE = 0.7


def _rng(day: date, name: str) -> random.Random:
    return random.Random(f"marina-tv:{day.isoformat()}:{name}")


class Watching:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------ estado --
    def state(self) -> dict:
        raw = self.db.get_estado_relacional().get(STATE_KEY)
        try:
            data = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            data = {}
        if not data:
            data = {"current": self._pick_next([], date(2026, 9, 23)), "one_piece_ep": ONE_PIECE_START_EP,
                    "finished": [], "done_days": []}
        return data

    def _save(self, data: dict) -> None:
        data["done_days"] = data.get("done_days", [])[-14:]
        self.db.set_estado_relacional(STATE_KEY, json.dumps(data, ensure_ascii=False))

    def add_patrick_mention(self, title: str, kind: Optional[str], now: Optional[datetime] = None) -> bool:
        """O Patrick falou de uma obra: como namorada, ela fica curiosa e anota pra ver.

        Jogo não entra na fila de assistir. Obra que ela já viu, está vendo ou já
        anotou é ignorada."""
        title = (title or "").strip()
        kind = (kind or "série").strip().casefold()
        if not title or kind == "jogo":
            return False
        data = self.state()
        known = {t.casefold() for t in data.get("finished", [])}
        known.add(data["current"]["title"].casefold())
        known |= {m["title"].casefold() for m in data.get("patrick_mentions", [])}
        with self.db.get_connection() as conn:
            known |= {r[0].split(" (")[0].casefold() for r in conn.execute(
                "SELECT value FROM character_preferences WHERE character_key='marina' AND category LIKE 'watched_%'")}
        if title.casefold() in known:
            return False
        entry = {"title": title, "kind": kind if kind in MENTION_DEFAULTS else "série",
                 "at": (now or datetime.now()).isoformat()}
        # D6 parte 2: com o TMDB, a obra vira dado real (título oficial, episódios,
        # duração) — e o que não existe não entra.
        from tmdb import TMDB, UNAVAILABLE
        tmdb = TMDB(self.db)
        if tmdb.available():
            info = tmdb.find(title, entry["kind"])
            if info is None:
                return False
            if info is not UNAVAILABLE:
                if info["title"].casefold() in known:
                    return False
                entry.update(title=info["title"], kind=info["kind"], episodes=info["episodes"],
                             minutes=info["minutes"], tmdb=[info["media"], info["id"]])
        data.setdefault("patrick_mentions", []).append(entry)
        data["patrick_mentions"] = data["patrick_mentions"][-10:]
        self._save(data)
        return True

    def _pick_next(self, finished: list, day: date, mentions: Optional[list] = None) -> dict:
        mentions = [m for m in (mentions or []) if m["title"] not in finished]
        rng = _rng(day, f"descoberta:{len(finished)}")
        if mentions and rng.random() < MENTION_PRIORITY:
            m = mentions[0]
            eps, minutes = m.get("episodes"), m.get("minutes")
            if not eps:
                eps, minutes = MENTION_DEFAULTS[m["kind"]]
            return self._with_where({"title": m["title"], "kind": m["kind"], "episodes": min(eps, MAX_EPISODES),
                                     "minutes": minutes, "ep": 0, "why": "o Patrick falou dele e ela ficou curiosa",
                                     "started": day.isoformat(), "from_patrick": True, "tmdb": m.get("tmdb")})
        live = self._pick_from_tmdb(finished, day, rng)
        if live:
            return live
        options = [t for t in DISCOVERY_POOL if t[0] not in finished]
        if not options:
            options = list(DISCOVERY_POOL)
        # Anime pesa mais (é o gosto mais forte dela), depois série e dorama.
        weights = [3 if t[1] == "anime" else 2 if t[1] == "série" else 1.5 for t in options]
        title, kind, eps, minutes, why = rng.choices(options, weights=weights, k=1)[0]
        return {"title": title, "kind": kind, "episodes": eps, "minutes": minutes, "ep": 0,
                "why": why, "started": day.isoformat()}

    # --------------------------------------------------------------- TMDB --
    def _seen_titles(self, finished: list) -> set:
        with self.db.get_connection() as conn:
            canon = {r[0].split(" (")[0].casefold() for r in conn.execute(
                "SELECT value FROM character_preferences WHERE character_key='marina' AND category LIKE 'watched_%'")}
        return canon | {t.casefold() for t in finished}

    def _pick_from_tmdb(self, finished: list, day: date, rng: random.Random) -> Optional[dict]:
        """Descoberta viva: parecido com o que ela amou, ou em alta no streaming do Brasil."""
        from tmdb import TMDB, UNAVAILABLE
        tmdb = TMDB(self.db)
        if not tmdb.available() or rng.random() >= TMDB_DISCOVERY_SHARE:
            return None
        seen = self._seen_titles(finished)
        with self.db.get_connection() as conn:
            loved = [(r[0].split(" (")[0], r[1]) for r in conn.execute(
                """SELECT value, category FROM character_preferences WHERE character_key='marina' AND active=1
                   AND category IN ('watched_anime','watched_series','watched_dorama') AND strength >= 0.8""")]
        candidates = []
        if loved and rng.random() < 0.65:
            seed, category = rng.choice(loved)
            hint = {"watched_anime": "anime", "watched_dorama": "dorama"}.get(category, "série")
            info = tmdb.find(seed, hint)
            if info and info is not UNAVAILABLE:
                candidates = [(c, f"parecido com {seed}, que ela amou") for c in
                              tmdb.recommendations(info["media"], info["id"])]
        if not candidates:
            kind = rng.choices(("anime", "série", "dorama"), weights=(3, 2, 1.5), k=1)[0]
            candidates = [(c, "tá em alta no streaming aqui") for c in tmdb.popular_in_brazil(kind)]
        candidates = [(c, why) for c, why in candidates if c["title"] and c["title"].casefold() not in seen]
        rng.shuffle(candidates)
        for cand, why in candidates[:5]:
            info = tmdb.details(cand["media"], cand["id"])
            if info is UNAVAILABLE or info["episodes"] > MAX_EPISODES:
                continue          # 300 episódios de Bleach não viram "o que ela está vendo"
            return self._with_where({"title": info["title"], "kind": info["kind"], "episodes": info["episodes"],
                                     "minutes": info["minutes"], "ep": 0, "why": why, "started": day.isoformat(),
                                     "tmdb": [info["media"], info["id"]]})
        return None

    def _with_where(self, item: dict) -> dict:
        """Onde está passando no Brasil (TMDB), pra ela falar "tô vendo na Netflix"."""
        if item.get("tmdb"):
            from tmdb import TMDB
            try:
                where = TMDB(self.db).where_to_watch(*item["tmdb"])
            except Exception:
                where = []
            if where:
                item["where"] = where[0]
        return item

    # ------------------------------------------------------------ noites --
    def night_plan(self, day: date) -> Optional[dict]:
        """Sessão da noite: depois do jantar, antes de deitar, se ela for ficar em casa."""
        rng = _rng(day, "sessao")
        if rng.random() >= WATCH_NIGHT_CHANCE:
            return None
        work = None
        try:
            from college import College
            work = College(self.db).session_on(day)
        except Exception:
            pass
        if work and work["vespera"] and work["assignment"]["pace"] == "ultima_hora":
            return None              # Fase D7: virando a noite no trabalho, nada de série
        try:
            from meals import Meals
            dinner = next((s for s in Meals(self.db).day_plan(day) if s.kind == "jantar"), None)
            start = (dinner.end if dinner else datetime.combine(day, time(20, 30))) \
                + timedelta(minutes=rng.randint(10, 40))
        except Exception:
            start = datetime.combine(day, time(20, 30))
        try:
            from rituals import Rituals
            bed = Rituals(self.db).bed_at(day) or datetime.combine(day, time(23, 30))
        except Exception:
            bed = datetime.combine(day, time(23, 30))
        if work:
            start = max(start, work["end"] + timedelta(minutes=15))   # série depois do trabalho
        one_piece = rng.random() < ONE_PIECE_NIGHT_CHANCE
        return {"start": start, "bed": bed, "episodes": rng.choice((1, 2, 2, 3)), "one_piece": one_piece}

    def new_episodes(self, now: datetime) -> int:
        """Episódio novo de quem ela acompanha saiu hoje (TMDB) → acontecimento do dia."""
        from tmdb import TMDB, UNAVAILABLE
        tmdb = TMDB(self.db)
        if not tmdb.available() or now.hour < 9:
            return 0
        followed = [(t, "anime") for t in FOLLOWED_ONGOING]
        cur = self.state()["current"]
        if cur.get("tmdb"):
            followed.append((cur["title"], cur["kind"]))
        created = 0
        for title, hint in followed:
            info = tmdb.find(title, hint)
            if not info or info is UNAVAILABLE or info.get("next_air_date") != now.date().isoformat():
                continue
            ep = f" (temporada {info['next_season']}, ep. {info['next_episode']})" if info.get("next_episode") else ""
            with self.db.get_connection() as conn:
                cur_ins = conn.execute(
                    """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,
                       source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                       VALUES (?,?,?,?,?,'simulated',1,0.1,?,0.4,?)""",
                    (f"tv:novo:{info['id']}:{now.date().isoformat()}", now.isoformat(), "routine", "tv",
                     f"Saiu episódio novo de {info['title']} hoje{ep}.", json.dumps(["marina"]), now.isoformat()))
                conn.commit()
                created += cur_ins.rowcount or 0
        return created

    def materialize(self, now: datetime) -> int:
        from meals import Meals
        meals = Meals(self.db)
        floor = meals._floor(now)
        if floor is None:
            return 0
        try:
            self.new_episodes(now)
        except Exception:
            pass
        day = now.date()
        data = self.state()
        if day.isoformat() in data.get("done_days", []):
            return 0
        plan = self.night_plan(day)
        if not plan or now < plan["start"] or plan["start"] < floor:
            return 0
        if not meals._at_home() or meals._transition_busy(now):
            return 0          # na rua ou ocupada na hora: tenta no próximo tick
        # Chegou em casa depois do horário planejado: a sessão começa agora.
        start = plan["start"] if now - plan["start"] < timedelta(minutes=10) else now
        room = max(0, int((plan["bed"] - start).total_seconds() // 60) - 15)
        events = []
        minutes_total = 0
        if plan["one_piece"] and room >= ONE_PIECE[3]:
            data["one_piece_ep"] = data.get("one_piece_ep", ONE_PIECE_START_EP) + 1
            events.append(f"Viu o episódio {data['one_piece_ep']} de One Piece (a série que ela começou por "
                          "causa do Patrick)")
            minutes_total += ONE_PIECE[3]
        cur = data["current"]
        cur_title = cur["title"]
        n = min(plan["episodes"], max(0, (room - minutes_total) // cur["minutes"]),
                cur["episodes"] - cur["ep"])
        if n > 0:
            first = cur["ep"] + 1
            cur["ep"] += n
            eps = f"episódio {first}" if n == 1 else f"episódios {first} a {cur['ep']}"
            novo = f" (começou essa semana: {cur['why']})" if first == 1 else ""
            events.append(f"Viu {eps} de {cur['title']}{novo}")
            minutes_total += n * cur["minutes"]
            if cur["ep"] >= cur["episodes"]:
                liked = _rng(day, f"gostou:{cur['title']}").random() < LIKE_CHANCE
                events.append(f"Terminou {cur['title']}" + (" e amou" if liked else ", achou só ok"))
                data.setdefault("finished", []).append(cur["title"])
                if liked:
                    self._remember_liked(cur, now)
                data["current"] = self._pick_next(data["finished"], day, data.get("patrick_mentions"))
                if data["current"].get("from_patrick"):
                    data["patrick_mentions"] = [m for m in data.get("patrick_mentions", [])
                                                if m["title"] != data["current"]["title"]]
        data.setdefault("done_days", []).append(day.isoformat())
        self._save(data)
        if not events:
            return 0
        end = start + timedelta(minutes=minutes_total)
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,
                   source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,?,?,?,'simulated',1,0.1,?,0.4,?)""",
                (f"tv:{day.isoformat()}", start.isoformat(), "routine", "tv",
                 "; ".join(events) + ".", json.dumps(["marina"]), now.isoformat()))
            conn.commit()
        if now < end:
            title = cur_title if n > 0 else "One Piece"
            payload = {"routine_type": "watching", "activity": f"vendo {title} no sofá",
                       "place_key": "marina_apartment", "announced_at": now.isoformat(),
                       "transition_at": start.isoformat(), "end_at": end.isoformat()}
            self.db.set_estado_relacional("pending_transition_json", json.dumps(payload, ensure_ascii=False))
        return 1

    def _remember_liked(self, cur: dict, now: datetime) -> None:
        category = {"anime": "watched_anime", "série": "watched_series", "dorama": "watched_dorama"}[cur["kind"]]
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO character_preferences
                   (character_key, category, value, preference_type, strength, confidence, first_seen_at,
                    last_seen_at, times_reinforced, canon_locked, active)
                   VALUES ('marina', ?, ?, 'discovered_preference', 0.7, 0.9, ?, ?, 1, 0, 1)""",
                (category, f"{cur['title']} (descobriu sozinha)", now.isoformat(), now.isoformat()))
            conn.commit()

    # ------------------------------------------------------------- prompt --
    def prompt_lines(self) -> list[str]:
        data = self.state()
        cur = data["current"]
        with self.db.get_connection() as conn:
            seen = [r[0] for r in conn.execute(
                """SELECT value FROM character_preferences WHERE character_key='marina' AND active=1
                   AND category IN ('watched_series','watched_dorama','watched_anime') ORDER BY strength DESC""")]
        lines = ["[O QUE VOCÊ ASSISTE — real; não cite título fora desta lista]"]
        onde = f", na {cur['where']}" if cur.get("where") else ""
        if cur["ep"]:
            lines.append(f"- Vendo agora: {cur['title']} ({cur['kind']}{onde}), parou no episódio {cur['ep']} de "
                         f"{cur['episodes']}. Começou porque: {cur['why']}.")
        else:
            lines.append(f"- Quer começar: {cur['title']} ({cur['kind']}{onde}) — {cur['why']}.")
        lines.append(f"- One Piece: está no episódio {data.get('one_piece_ep', ONE_PIECE_START_EP)} "
                     "(começou por causa do Patrick; ele manja muito mais).")
        mentions = [m["title"] for m in data.get("patrick_mentions", [])]
        if mentions:
            lines.append("- O Patrick já falou de " + ", ".join(mentions)
                         + ": você ficou curiosa e anotou pra ver (ainda não viu).")
        if seen:
            lines.append("- Já viu e curte: " + ", ".join(seen[:14]) + ".")
        return lines
