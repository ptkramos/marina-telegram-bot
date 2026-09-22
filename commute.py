"""Fase C.4 — locomoção viva (tabela local).

Pedido do Patrick (22/09): "a gente aproveita as locomoções dela, de uber, a
pé, transporte público, carona, isso tudo cria margem pra ela ter tempo entre
os compromissos pra conversar e pra criar histórias."

Antes ela "teleportava": às 12:59 estava na aula, às 13:00 em casa. Agora os
trechos de ida e volta da faculdade e das saídas com as amigas viram estado
("voltando da PUC de ônibus"), com modo e duração sorteados por dia:

* **tempo** por região a partir de Botafogo (onde ela mora), com fator de pico;
* **modo** pesado por hora (noite → uber), chuva (sem ir a pé, mais uber),
  fim de mês (menos uber), cansaço (mais uber) e companhia (divide o uber com
  a amiga na volta da saída);
* **imprevistos** pequenos (ônibus lotado, uber errou o caminho) viram
  `life_events` do dia quando acontecem — ela pode contar depois.

Com `DISTANCE_MATRIX_KEY` no .env, o número de minutos vem da Distance Matrix
API (distancematrix.ai): trânsito previsto para o uber, horário de ônibus/metrô
para o transporte público, caminhada para a pé. Uma consulta por trecho, na hora
de decidir (a decisão fica gravada) — nunca por mensagem. Se a API falhar,
demorar ou devolver algo absurdo, vale a tabela.
"""
from __future__ import annotations

import json
import logging
import random
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

logger = logging.getLogger("Commute")

HOME_REGION = "Botafogo"

# Minutos por modo, de Botafogo até a região (fora do pico).
ROUTES = {
    "Botafogo": {"a_pe": 12},
    "Copacabana": {"metro": 15, "onibus": 22, "uber": 12},
    "Ipanema": {"metro": 22, "onibus": 32, "uber": 18},
    "Leblon": {"metro": 30, "onibus": 40, "uber": 22},
    "Gávea": {"onibus": 40, "metro_onibus": 45, "uber": 22},
}
BASE_WEIGHT = {"a_pe": 1.0, "metro": 0.45, "onibus": 0.45, "metro_onibus": 0.3, "uber": 0.25}
RUSH = ((time(7, 0), time(9, 30)), (time(17, 0), time(19, 30)))
RUSH_FACTOR = {"onibus": 1.35, "uber": 1.35, "metro_onibus": 1.25, "metro": 1.1, "a_pe": 1.0}
LABEL = {"a_pe": "a pé", "metro": "de metrô", "onibus": "de ônibus",
         "metro_onibus": "de metrô e ônibus", "uber": "de uber"}
# Carona (cânone do Patrick, 22/09: o Theo tem carro). Peso na ida/volta da PUC
# (ele é da mesma faculdade e passa por Botafogo vindo da Glória) e nas saídas
# em que ele está junto.
CARONA_WEIGHT_PUC = 0.25
CARONA_WEIGHT_OUTING = 0.9
# Margens que a agenda já reserva em volta da aula (world_state).
CLASS_GO_MAX_MIN = 50
CLASS_BACK_MAX_MIN = 45
API_URL = "https://api.distancematrix.ai/maps/api/distancematrix/json"
API_TIMEOUT_S = 4
API_MODE = {"uber": "driving", "carona": "driving", "onibus": "transit", "metro": "transit", "metro_onibus": "transit",
            "a_pe": "walking"}
API_TRANSIT = {"onibus": "bus", "metro": "subway", "metro_onibus": "bus|subway"}
API_CLAMP = (0.6, 2.5)      # em relação à tabela: fora disso é endereço mal geocodificado
HOME_QUERY = "Botafogo, Rio de Janeiro, RJ, Brasil"
ALLOW_LIVE_IN_TESTS = False    # só os testes da API ligam, com a rede simulada
INCIDENT_CHANCE = 0.12
INCIDENTS = {
    "onibus": ["o ônibus veio lotado", "o ônibus demorou uns 20 minutos pra passar"],
    "metro_onibus": ["o metrô tava lotado", "perdeu o ônibus da integração por um minuto"],
    "metro": ["o metrô tava lotado", "o metrô parou uns minutos entre as estações"],
    "uber": ["o motorista do uber errou o caminho", "o uber cancelou e ela teve que chamar outro"],
    "a_pe": ["começou a garoar no caminho"],
    "uber_dividido": ["o motorista do uber errou o caminho"],
    "carona": ["pegaram um trânsito chato no caminho", "pararam pra comprar um açaí no caminho"],
}


@dataclass
class Leg:
    key: str
    start: datetime
    end: datetime
    mode: str
    direction: str          # ida | volta
    destination: str        # nome curto do lugar
    region: str
    companion: str = ""     # amiga com quem divide o uber
    incident: str = ""
    incident_at: Optional[datetime] = None

    @property
    def how(self) -> str:
        if self.mode == "uber_dividido":
            return f"dividindo um uber com {self.companion}"
        if self.mode == "carona":
            return f"de carona com {self.companion}"
        return LABEL[self.mode]

    def activity(self, now: datetime) -> str:
        how = self.how
        where = (f"indo {self.destination}" if self.direction == "ida"
                 else f"voltando {self.destination} pra casa")
        text = f"{where} {how}"
        if self.incident and self.incident_at and now >= self.incident_at:
            text += f" ({self.incident})"
        return text


_FEMININE = ("praia", "agência", "agencia", "enseada", "puc")


def _pra(name: str) -> str:
    return f"pra {name}" if name.lower().startswith(_FEMININE) else f"pro {name}"


def _de(name: str) -> str:
    return f"da {name}" if name.lower().startswith(_FEMININE) else f"do {name}"


def _rng(day: date, name: str) -> random.Random:
    return random.Random(f"marina-commute:{day.isoformat()}:{name}")


def _in_rush(moment: datetime) -> bool:
    return moment.weekday() < 5 and any(a <= moment.time() < b for a, b in RUSH)


class Commute:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------ contexto --
    def _place(self, key: Optional[str]) -> Optional[dict]:
        if not key:
            return None
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT name, region, truth_type FROM world_places WHERE canonical_key=?",
                               (key,)).fetchone()
        return dict(row) if row else None

    def _heavy_rain(self, moment: datetime) -> bool:
        try:
            from calendar_world import CalendarWorld
            obs = CalendarWorld(self.db).context.get("weather:rio", now=moment)
            return bool(obs and obs["payload"].get("heavy_rain"))
        except Exception:
            return False

    def _energy(self) -> float:
        try:
            from world_state import current_energy
            return current_energy(self.db)
        except Exception:
            return 0.7

    def _driver(self, among: Optional[list] = None) -> tuple[str, str]:
        """(chave, nome curto) de quem do círculo tem carro — cânone em
        world_characters.initial_state_json.has_car."""
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT canonical_key FROM world_characters WHERE active=1 AND "
                                "json_extract(initial_state_json, '$.has_car') = 1").fetchall()
        keys = [r["canonical_key"] for r in rows if among is None or r["canonical_key"] in among]
        if not keys:
            return "", ""
        from social_day import short_name
        key = sorted(keys)[0]
        return key, short_name(key)  # já vem com artigo ("o Theo")

    # ------------------------------------------------------------ escolha --
    def _choose(self, day: date, name: str, region: str, moment: datetime, companion: str = "",
                place: Optional[dict] = None, outbound: bool = True,
                carona_weight: float = 0.0) -> tuple[str, int]:
        """Modo e minutos do trecho. Decidido uma vez e gravado: a energia e a
        chuva mudam ao longo do dia, e o ônibus não pode virar uber no meio."""
        key = f"commute:{day.isoformat()}:{name}"
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT value FROM world_bootstrap WHERE key=?", (key,)).fetchone()
        if row:
            mode, minutes = row["value"].split("|")
            return mode, int(minutes)
        mode, minutes = self._decide(day, name, region, moment, companion, place, outbound, carona_weight)
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at) VALUES (?, ?, ?)",
                         (key, f"{mode}|{minutes}", datetime.now().isoformat()))
            conn.commit()
        return mode, minutes

    def _decide(self, day: date, name: str, region: str, moment: datetime, companion: str = "",
                place: Optional[dict] = None, outbound: bool = True,
                carona_weight: float = 0.0) -> tuple[str, int]:
        options = dict(ROUTES.get(region) or ROUTES["Copacabana"])
        if carona_weight > 0:
            options["carona"] = options.get("uber") or 10
        rain = self._heavy_rain(moment)
        night = moment.time() >= time(22, 0) or moment.time() < time(6, 0)
        if rain or night:
            options.pop("a_pe", None)
            if len(options) == 0:
                options = {"uber": 10}
        weights = {}
        for mode in options:
            w = BASE_WEIGHT.get(mode, 0.3)
            if mode == "uber":
                w *= (2.5 if night else 1.0) * (2.0 if rain else 1.0) * (1.5 if self._energy() < 0.4 else 1.0)
                w *= 0.6 if day.day >= 24 else 1.0
            elif mode == "carona":
                w = carona_weight * (2.0 if rain else 1.0) * (1.5 if night else 1.0)
            elif night and mode in ("onibus", "metro_onibus"):
                w *= 0.2
            weights[mode] = w
        rng = _rng(day, name)
        mode = rng.choices(list(weights), weights=list(weights.values()))[0]
        minutes = options[mode] * (RUSH_FACTOR.get(mode, 1.0) if _in_rush(moment) else 1.0)
        minutes = int(round(minutes * rng.uniform(0.9, 1.15)))
        live = self._live_minutes(mode, place or {"name": "", "region": region}, outbound, moment)
        if live is not None:
            base = options[mode]
            minutes = int(min(max(live, base * API_CLAMP[0]), base * API_CLAMP[1]))
            logger.info("commute.live leg=%s mode=%s minutes=%s tabela=%s", name, mode, minutes, base)
        if mode == "uber" and companion and rng.random() < 0.5:
            mode = "uber_dividido"
        return mode, max(5, minutes)

    # ------------------------------------------------------------ API --
    @staticmethod
    def _query(place: dict) -> str:
        region = place.get("region") or ""
        fictional = (place.get("truth_type") or "").startswith("fic") or "fictícia" in (place.get("name") or "")
        parts = ([] if fictional or not place.get("name") else [place["name"]]) + [region, "Rio de Janeiro, RJ, Brasil"]
        return ", ".join(p for p in parts if p)

    def _live_minutes(self, mode: str, place: dict, outbound: bool, moment: datetime) -> Optional[int]:
        from config import settings
        key = (getattr(settings, "DISTANCE_MATRIX_KEY", "") or "").strip()
        if not key or not getattr(settings, "COMMUTE_LIVE_TIMES", True) or mode not in API_MODE:
            return None
        from db import _running_under_tests
        if _running_under_tests() and not ALLOW_LIVE_IN_TESTS:
            return None  # a suíte nunca chama a API real (dezenas de resolves por rodada)
        from zoneinfo import ZoneInfo
        depart = max(moment, datetime.now() + timedelta(minutes=1))
        dest = self._query(place)
        params = {"origins": HOME_QUERY if outbound else dest, "destinations": dest if outbound else HOME_QUERY,
                  "mode": API_MODE[mode], "language": "pt-BR", "key": key,
                  "departure_time": int(depart.replace(tzinfo=ZoneInfo("America/Sao_Paulo")).timestamp())}
        if mode in API_TRANSIT:
            params["transit_mode"] = API_TRANSIT[mode]
        try:
            with urllib.request.urlopen(f"{API_URL}?{urllib.parse.urlencode(params)}",
                                        timeout=API_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            element = data["rows"][0]["elements"][0]
            if element.get("status") != "OK":
                return None
            seconds = (element.get("duration_in_traffic") or element["duration"])["value"]
            return max(1, round(seconds / 60))
        except Exception as exc:
            # A chave vai na URL: nunca logar a URL nem a exceção crua.
            logger.warning("commute.live_failed mode=%s erro=%s", mode, type(exc).__name__)
            return None

    def _incident(self, leg: Leg) -> Leg:
        rng = _rng(leg.start.date(), f"{leg.key}:imprevisto")
        if rng.random() < INCIDENT_CHANCE:
            leg.incident = rng.choice(INCIDENTS.get(leg.mode, INCIDENTS["uber"]))
            span = max(1, int((leg.end - leg.start).total_seconds() // 60) - 2)
            leg.incident_at = leg.start + timedelta(minutes=rng.randint(1, span))
        return leg

    # ------------------------------------------------------------ trechos --
    def legs_on(self, day: date) -> list[Leg]:
        legs: list[Leg] = []
        from academic_life import AcademicLife
        blocks = AcademicLife(self.db).blocks_on(day)
        if blocks:
            first = min(datetime.fromisoformat(b["start_at"]) for b in blocks)
            last = max(datetime.fromisoformat(b["end_at"]) for b in blocks)
            puc = self._place("puc_rio") or {"name": "PUC-Rio", "region": "Gávea"}
            _key, driver = self._driver()
            w = CARONA_WEIGHT_PUC if driver else 0.0
            mode, mins = self._choose(day, "puc:ida", "Gávea", first - timedelta(minutes=40), place=puc,
                                      carona_weight=w)
            mins = min(mins, CLASS_GO_MAX_MIN)
            legs.append(self._incident(Leg(f"commute:{day.isoformat()}:puc:ida", first - timedelta(minutes=mins),
                                           first, mode, "ida", _pra("PUC"), "Gávea",
                                           driver if mode == "carona" else "")))
            mode, mins = self._choose(day, "puc:volta", "Gávea", last, place=puc, outbound=False,
                                      carona_weight=w)
            mins = min(mins, CLASS_BACK_MAX_MIN)
            legs.append(self._incident(Leg(f"commute:{day.isoformat()}:puc:volta", last,
                                           last + timedelta(minutes=mins), mode, "volta", _de("PUC"), "Gávea",
                                           driver if mode == "carona" else "")))
        with self.db.get_connection() as conn:
            outings = [dict(r) for r in conn.execute(
                """SELECT source_key, event_at, end_at, location_key, metadata_json FROM eventos_pendentes
                   WHERE source_key LIKE ? AND confirmed=1 AND status != 'cancelled' ORDER BY event_at""",
                (f"outing:{day.isoformat()}:%",))]
        for o in outings:
            place = self._place(o["location_key"])
            if not place or not o["end_at"]:
                continue
            start, end = datetime.fromisoformat(o["event_at"]), datetime.fromisoformat(o["end_at"])
            friends = (json.loads(o["metadata_json"] or "{}") or {}).get("friends") or []
            try:
                from social_day import short_name
                companion = short_name(friends[0]) if friends else ""
            except Exception:
                companion = ""
            region = place["region"] or "Copacabana"
            tag = o["source_key"].split(":", 1)[1]
            _key, driver = self._driver(among=friends)
            w = CARONA_WEIGHT_OUTING if driver else 0.0
            mode, mins = self._choose(day, f"{tag}:ida", region, start, place=place, carona_weight=w)
            legs.append(self._incident(Leg(f"commute:outing:{tag}:ida", start - timedelta(minutes=mins), start,
                                           mode, "ida", _pra(place["name"]), region,
                                           driver if mode == "carona" else "")))
            mode, mins = self._choose(day, f"{tag}:volta", region, end, companion, place=place, outbound=False,
                                      carona_weight=w)
            legs.append(self._incident(Leg(f"commute:outing:{tag}:volta", end, end + timedelta(minutes=mins),
                                           mode, "volta", _de(place["name"]), region,
                                           driver if mode == "carona" else companion)))
        return legs

    def leg_at(self, now: datetime) -> Optional[Leg]:
        for day in (now.date(), now.date() - timedelta(days=1)):   # volta que passa da meia-noite
            for leg in self.legs_on(day):
                if leg.start <= now < leg.end:
                    return leg
        return None

    # ------------------------------------------------------------ memória --
    def materialize(self, now: datetime) -> int:
        """Imprevistos já acontecidos viram acontecimentos do dia (idempotente).

        Mesmas travas do dia social: nada antes do bootstrap limpo terminar
        (ele exige zero memória) e nada antes do início da vida registrada."""
        created = 0
        with self.db.get_connection() as conn:
            clean = conn.execute(
                "SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone()
        if not clean:
            return created
        from social_day import SocialDay
        floor = SocialDay(self.db)._floor(now)
        for day in (now.date() - timedelta(days=1), now.date()):
            for leg in self.legs_on(day):
                if not leg.incident or not leg.incident_at or not (floor <= leg.incident_at <= now):
                    continue
                how = leg.how
                trecho = f"indo {leg.destination}" if leg.direction == "ida" else f"voltando {leg.destination}"
                summary = f"No caminho ({trecho}, {how}): {leg.incident}."
                with self.db.get_connection() as conn:
                    cur = conn.execute(
                        """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,
                           source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                           VALUES (?,?,?,?,?,'simulated',1,0.1,?,0.3,?)""",
                        (f"{leg.key}:imprevisto", leg.incident_at.isoformat(), "commute", "imprevisto no caminho",
                         summary, json.dumps(["marina"]), now.isoformat()))
                    conn.commit()
                    created += cur.rowcount or 0
        return created
