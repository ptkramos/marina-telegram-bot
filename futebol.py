"""Jogos do Botafogo de verdade (Patrick, 26/09 — etapa 1, mídia real).

A agenda e os lances vêm da ESPN (grátis, sem chave, cobre 2026: Brasileirão, Copa do Brasil,
Sul-Americana e Libertadores). Os lances ao vivo pra ela reagir no chat continuam no
`botafogo_service` (API-Sports, que funciona ao vivo no plano grátis); a ESPN não tem cota e
também serve de linha do tempo do jogo no card.

Onde ela vê (decidido com o Patrick): em casa na TV (padrão), às vezes num bar com os amigos ou no
Nilton Santos (convite, com preparo, trajeto e consumo), e pelo celular se estiver fora.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

AGENDA_KEY = "futebol_agenda_json"
LANCES_KEY = "futebol_lances_json"
TEAM_ID = "6086"
LIGAS = {"bra.1": "Brasileirão", "bra.copa_do_brazil": "Copa do Brasil",
         "conmebol.sudamericana": "Sul-Americana", "conmebol.libertadores": "Libertadores"}
REFRESH_H = 6
UTC_OFFSET = timedelta(hours=-3)          # Brasília, sem horário de verão
DURACAO = timedelta(minutes=115)          # apito inicial ao final, com intervalo e acréscimos
CLASSICOS = ("Flamengo", "Fluminense", "Vasco")
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"


def _get(url: str) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})   # a ESPN recusa UA de navegador
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        logger.warning("futebol.fetch_falhou url=%s", url)
        return None


def _local(iso_utc: str) -> datetime:
    return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).replace(tzinfo=None) + UTC_OFFSET


def _curto(nome: str) -> str:
    return {"Vasco da Gama": "Vasco", "Atlético-MG": "Atlético-MG", "Red Bull Bragantino": "Bragantino"}.get(nome, nome)


class Futebol:
    def __init__(self, db):
        self.db = db

    def _load(self, key: str) -> dict:
        raw = self.db.get_estado_relacional(key)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _store(self, key: str, data: dict) -> None:
        self.db.set_estado_relacional(key, json.dumps(data, ensure_ascii=False))

    # ------------------------------------------------------------ agenda --
    def atualizar(self, now: Optional[datetime] = None, *, force: bool = False) -> bool:
        """Job do bot (fora do turno): agenda a cada 6 h; lances durante e logo depois do jogo."""
        now = now or datetime.now()
        ag = self._load(AGENDA_KEY)
        mudou = False
        if force or not ag.get("at") or now - datetime.fromisoformat(ag["at"]) > timedelta(hours=REFRESH_H):
            jogos = []
            for liga, nome in LIGAS.items():
                data = _get(f"{BASE}/{liga}/teams/{TEAM_ID}/schedule?fixture=true") or {}
                passados = _get(f"{BASE}/{liga}/teams/{TEAM_ID}/schedule") or {}
                for e in (data.get("events") or []) + (passados.get("events") or []):
                    j = self._jogo(e, liga, nome)
                    if j and not any(x["id"] == j["id"] for x in jogos):
                        jogos.append(j)
            if jogos:
                self._store(AGENDA_KEY, {"at": now.isoformat(), "jogos": sorted(jogos, key=lambda j: j["inicio"])})
                mudou = True
        for j in self.jogos():
            ini = datetime.fromisoformat(j["inicio"])
            if ini - timedelta(minutes=5) <= now <= ini + DURACAO + timedelta(minutes=30):
                mudou |= self._lances(j)
        return mudou

    @staticmethod
    def _jogo(e: dict, liga: str, nome_liga: str) -> Optional[dict]:
        try:
            c = e["competitions"][0]
            times = {t["homeAway"]: t for t in c["competitors"]}
            casa, fora = times["home"], times["away"]
            placar = [(t.get("score") or {}).get("displayValue") if isinstance(t.get("score"), dict) else t.get("score")
                      for t in (casa, fora)]
            return {"id": e["id"], "liga": liga, "competicao": nome_liga, "inicio": _local(e["date"]).isoformat(),
                    "casa": _curto(casa["team"].get("shortDisplayName") or casa["team"]["displayName"]),
                    "fora": _curto(fora["team"].get("shortDisplayName") or fora["team"]["displayName"]),
                    "mandante": casa["team"]["id"] == TEAM_ID,
                    "estadio": (c.get("venue") or {}).get("fullName", ""),
                    "status": c["status"]["type"]["name"], "placar": placar}
        except (KeyError, IndexError, TypeError):
            return None

    def jogos(self) -> list[dict]:
        return self._load(AGENDA_KEY).get("jogos", [])

    @staticmethod
    def titulo(j: dict) -> str:
        return f"{j['casa']} x {j['fora']}"

    @staticmethod
    def adversario(j: dict) -> str:
        return j["fora"] if j["mandante"] else j["casa"]

    def classico(self, j: dict) -> bool:
        return any(c in self.adversario(j) for c in CLASSICOS)

    def do_dia(self, day: date) -> list[dict]:
        return [j for j in self.jogos() if datetime.fromisoformat(j["inicio"]).date() == day]

    def jogo_em(self, now: datetime) -> Optional[dict]:
        for j in self.jogos():
            ini = datetime.fromisoformat(j["inicio"])
            if ini - timedelta(minutes=5) <= now < ini + DURACAO:
                return j
        return None

    def proximo(self, now: datetime) -> Optional[dict]:
        return next((j for j in self.jogos() if datetime.fromisoformat(j["inicio"]) > now), None)

    def ultimo(self, now: datetime) -> Optional[dict]:
        feitos = [j for j in self.jogos() if datetime.fromisoformat(j["inicio"]) + DURACAO <= now
                  and all(p not in (None, "") for p in j["placar"])]
        return feitos[-1] if feitos else None

    # ------------------------------------------------------------ lances --
    def _lances(self, j: dict) -> bool:
        data = _get(f"{BASE}/{j['liga']}/summary?event={j['id']}")
        if not data:
            return False
        ini = datetime.fromisoformat(j["inicio"])
        out = []
        for k in data.get("keyEvents") or []:
            tipo = (k.get("type") or {}).get("text", "")
            clock = (k.get("clock") or {}).get("displayValue", "")
            try:
                minuto = int(clock.split("'")[0]) if clock else 0
                extra = int(clock.split("+")[1].rstrip("'")) if "+" in clock else 0
            except ValueError:
                minuto, extra = 0, 0
            segundo_tempo = minuto > 45 or tipo == "Start 2nd Half"
            at = ini + timedelta(minutes=minuto + extra + (15 if segundo_tempo else 0))
            time_ = ((k.get("team") or {}).get("displayName") or "")
            nosso = "Botafogo" in time_
            quem = "Botafogo" if nosso else _curto(time_)
            if tipo.startswith("Own Goal"):
                texto = f"Gol contra do {quem}"
            elif tipo.startswith("Goal") or tipo == "Penalty - Scored":
                texto = f"Gol do {quem}"
            elif tipo.startswith("Red Card"):
                texto = f"Expulsão no {quem}"
            else:
                texto = {"Halftime": "Intervalo", "Kickoff": "1º tempo", "Start 2nd Half": "2º tempo",
                         "End Regular Time": "Fim de jogo"}.get(tipo)
            if texto and not any(x["texto"] == texto and x["minuto"] == clock for x in out):
                out.append({"texto": texto, "minuto": clock, "at": at.isoformat(), "nosso": nosso})
        placar = None
        try:
            comp = data["header"]["competitions"][0]
            times = {t["homeAway"]: t for t in comp["competitors"]}
            placar = [times["home"].get("score"), times["away"].get("score")]
        except (KeyError, IndexError, TypeError):
            pass
        cache = self._load(LANCES_KEY)
        cache = {k: v for k, v in cache.items() if k in {x["id"] for x in self.jogos()}}
        cache[j["id"]] = {"lances": out, "placar": placar, "at": datetime.now().isoformat()}
        self._store(LANCES_KEY, cache)
        return True

    def lances(self, j: dict) -> dict:
        return self._load(LANCES_KEY).get(j["id"], {"lances": [], "placar": None})

    def placar_texto(self, j: dict) -> str:
        p = self.lances(j).get("placar") or j.get("placar") or [None, None]
        if any(x in (None, "") for x in p):
            return f"{j['casa']} 0 x 0 {j['fora']}"
        return f"{j['casa']} {p[0]} x {p[1]} {j['fora']}"

    # ------------------------------------------------------------ prompt --
    def prompt_lines(self, now: datetime) -> list[str]:
        linhas = []
        u = self.ultimo(now)
        if u and now - datetime.fromisoformat(u["inicio"]) < timedelta(days=10):
            linhas.append(f"- Último jogo: {self.placar_texto(u)} ({u['competicao']}, "
                          f"{datetime.fromisoformat(u['inicio']):%d/%m}).")
        agora = self.jogo_em(now)
        if agora:
            linhas.append(f"- AGORA: {self.titulo(agora)} ({agora['competicao']}), placar {self.placar_texto(agora)}.")
        p = self.proximo(now)
        if p and not agora:
            ini = datetime.fromisoformat(p["inicio"])
            dia = "hoje" if ini.date() == now.date() else "amanhã" if ini.date() == now.date() + timedelta(days=1) \
                else f"{('seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom')[ini.weekday()]} {ini:%d/%m}"
            linhas.append(f"- Próximo jogo: {self.titulo(p)} ({p['competicao']}), {dia} às {ini:%H:%M}.")
        return (["[BOTAFOGO — real (ESPN); você torce; não invente jogo, placar nem data]"] + linhas) if linhas else []
