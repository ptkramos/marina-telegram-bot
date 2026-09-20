"""
Serviço de Acompanhamento ao Vivo do Botafogo (API-Sports / API-Football).
Monitora as partidas do Glorioso em tempo real, gerencia rigorosamente a cota diária
gratuita (100 req/dia), deduplica eventos e identifica lances de alto impacto
emocional (gols, cartões vermelhos, intervalo e apito final) para reações da Marina.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Set, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from config import settings

logger = logging.getLogger("BotafogoService")

API_SPORTS_BASE_URL = "https://v3.football.api-sports.io"


class BotafogoLiveService:
    def __init__(self, team_id: Optional[int] = None, api_key: Optional[str] = None):
        self.team_id = team_id or getattr(settings, "BOTAFOGO_TEAM_ID", 120)
        self.api_key = api_key or getattr(settings, "APISPORTS_KEY", "")
        self.daily_requests: Dict[str, int] = {}
        self.max_daily_requests: int = 90  # Margem segura antes do teto 100
        self.seen_events: Set[str] = set()
        self.last_status: Dict[int, str] = {}
        self.last_score: Dict[int, Tuple[int, int]] = {}
        self.active_fixture: Optional[Dict[str, Any]] = None
        self.last_poll_time: Optional[datetime] = None

    def is_match_live(self) -> bool:
        """Retorna True se há partida do Botafogo em andamento agora."""
        if not self.active_fixture:
            return False
        st = self.active_fixture.get("status_short")
        return st in ("1H", "HT", "2H", "ET", "P", "LIVE", "BT")

    def should_poll(self, now: Optional[datetime] = None) -> bool:
        """Cadência adaptativa para economizar a cota diária de 100 requisições."""
        if not self.can_make_request():
            return False
        dt = now or datetime.now()
        if self.last_poll_time is None:
            return True

        elapsed_sec = (dt - self.last_poll_time).total_seconds()

        # Durante partida ao vivo: polling a cada 2 minutos (ou configurado)
        if self.is_match_live():
            interval = getattr(settings, "BOTAFOGO_POLL_INTERVAL_SECONDS", 120)
            return elapsed_sec >= interval

        # Fora de partida: madrugada/início da manhã (00h às 11h), checa a cada 1 hora
        if dt.hour < 11:
            return elapsed_sec >= 3600

        # Tarde/noite (11h às 23h59) sem partida ativa: checa a cada 15 minutos (900s)
        return elapsed_sec >= 900

    def _get_today_str(self) -> str:
        return date.today().isoformat()

    def get_requests_today(self) -> int:
        return self.daily_requests.get(self._get_today_str(), 0)

    def can_make_request(self) -> bool:
        if not self.api_key:
            return False
        return self.get_requests_today() < self.max_daily_requests

    def record_request(self) -> None:
        today = self._get_today_str()
        self.daily_requests[today] = self.daily_requests.get(today, 0) + 1

    def get_quota_status(self) -> Dict[str, Any]:
        return {
            "used_today": self.get_requests_today(),
            "safe_max_daily": self.max_daily_requests,
            "hard_limit": 100,
            "has_key": bool(self.api_key),
            "tracking_enabled": getattr(settings, "BOTAFOGO_TRACKING_ENABLED", True)
        }

    def fetch_live_fixture(self) -> Optional[Dict[str, Any]]:
        """Consulta a API-Sports para verificar se o Botafogo está jogando agora."""
        if not self.can_make_request():
            logger.warning("Cota diária da API-Sports atingiu o limite seguro (%s/90). Bloqueando requisição.", self.get_requests_today())
            return None

        url = f"{API_SPORTS_BASE_URL}/fixtures?live=all&team={self.team_id}"
        headers = {
            "x-apisports-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "MarinaSallesBot/3.7.0"
        }

        try:
            self.record_request()
            req = Request(url, headers=headers)
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            errors = data.get("errors")
            if errors:
                logger.error("API-Sports retornou erros: %s", errors)
                return None

            results = data.get("results", 0)
            if results > 0 and data.get("response"):
                return data["response"][0]

            return None
        except HTTPError as he:
            logger.error("HTTPError ao consultar API-Sports: %s %s", he.code, he.reason)
            return None
        except URLError as ue:
            logger.warning("URLError de conexão com API-Sports: %s", ue.reason)
            return None
        except Exception as exc:
            logger.error("Exceção inesperada na API-Sports: %s", exc, exc_info=True)
            return None

    def parse_fixture(self, fix: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza e extrai dados essenciais do payload do jogo."""
        fixture_info = fix.get("fixture", {})
        teams_info = fix.get("teams", {})
        goals_info = fix.get("goals", {})
        league_info = fix.get("league", {})

        home_id = teams_info.get("home", {}).get("id")
        home_name = teams_info.get("home", {}).get("name", "Casa")
        away_id = teams_info.get("away", {}).get("id")
        away_name = teams_info.get("away", {}).get("name", "Visitante")

        is_botafogo_home = (home_id == self.team_id)
        opponent = away_name if is_botafogo_home else home_name

        home_goals = goals_info.get("home") if goals_info.get("home") is not None else 0
        away_goals = goals_info.get("away") if goals_info.get("away") is not None else 0

        botafogo_goals = home_goals if is_botafogo_home else away_goals
        opponent_goals = away_goals if is_botafogo_home else home_goals

        status_obj = fixture_info.get("status", {})
        status_short = status_obj.get("short", "")
        status_long = status_obj.get("long", "")
        elapsed = status_obj.get("elapsed")

        score_display = f"Botafogo {botafogo_goals} x {opponent_goals} {opponent}"

        return {
            "fixture_id": fixture_info.get("id"),
            "status_short": status_short,
            "status_long": status_long,
            "elapsed": elapsed,
            "league_name": league_info.get("name", "Campeonato"),
            "is_botafogo_home": is_botafogo_home,
            "opponent": opponent,
            "botafogo_goals": botafogo_goals,
            "opponent_goals": opponent_goals,
            "score_display": score_display,
            "events": fix.get("events", [])
        }

    def check_live_updates(self, live_data: Optional[Dict[str, Any]] = None, force: bool = False) -> List[Dict[str, Any]]:
        """
        Processa atualizações da partida ao vivo e retorna lista de eventos de impacto para reagir.
        Se live_data for None, faz a chamada HTTP à API respeitando should_poll().
        """
        if not getattr(settings, "BOTAFOGO_TRACKING_ENABLED", True):
            return []

        if live_data is None:
            if not force and not self.should_poll():
                return []
            self.last_poll_time = datetime.now()
            raw_fix = self.fetch_live_fixture()
        else:
            raw_fix = live_data

        if not raw_fix:
            self.active_fixture = None
            return []

        parsed = self.parse_fixture(raw_fix)
        self.active_fixture = parsed

        fixture_id = parsed["fixture_id"]
        status_short = parsed["status_short"]
        elapsed = parsed["elapsed"] or 0
        opponent = parsed["opponent"]
        score_str = parsed["score_display"]
        bota_g = parsed["botafogo_goals"]
        opp_g = parsed["opponent_goals"]

        # Se for o primeiro contato com esta partida ao vivo, memoriza os eventos
        # que já aconteceram para não disparar lances atrasados em lote.
        is_initial_sync = (fixture_id not in self.last_status)
        if is_initial_sync and live_data is None:
            self.last_status[fixture_id] = status_short
            for ev in parsed.get("events", []):
                time_obj = ev.get("time", {})
                ev_elapsed = time_obj.get("elapsed", 0)
                ev_type = ev.get("type", "")
                ev_detail = ev.get("detail", "")
                team_id = ev.get("team", {}).get("id")
                player_name = ev.get("player", {}).get("name", "Jogador")
                self.seen_events.add(f"{fixture_id}:{ev_elapsed}:{ev_type}:{ev_detail}:{team_id}:{player_name}")
            logger.info("Sincronização inicial da partida %s (%s, %s): %s eventos passados memorizados.",
                        fixture_id, opponent, status_short, len(parsed.get("events", [])))
            return []

        impact_events: List[Dict[str, Any]] = []

        # 1. Checar transições de status
        prev_status = self.last_status.get(fixture_id)

        # Transição para Intervalo (HT)
        if status_short == "HT" and prev_status != "HT":
            event_key = f"{fixture_id}:status:HT"
            if event_key not in self.seen_events:
                self.seen_events.add(event_key)
                impact_events.append({
                    "type": "intervalo",
                    "headline": "Fim do Primeiro Tempo",
                    "description": f"Fim do primeiro tempo! O placar está {score_str}.",
                    "score": score_str,
                    "elapsed": 45,
                    "opponent": opponent,
                    "botafogo_goals": bota_g,
                    "opponent_goals": opp_g,
                })

        # Transição para Segundo Tempo (2H)
        elif status_short == "2H" and prev_status in ("HT", "1H") and prev_status != "2H":
            event_key = f"{fixture_id}:status:2H"
            if event_key not in self.seen_events:
                self.seen_events.add(event_key)
                impact_events.append({
                    "type": "inicio_2t",
                    "headline": "Início do Segundo Tempo",
                    "description": f"Começou o segundo tempo! Placar: {score_str}.",
                    "score": score_str,
                    "elapsed": 45,
                    "opponent": opponent,
                    "botafogo_goals": bota_g,
                    "opponent_goals": opp_g,
                })

        # Transição para Fim de Jogo (FT, AET, PEN)
        elif status_short in ("FT", "AET", "PEN") and prev_status not in ("FT", "AET", "PEN", None):
            event_key = f"{fixture_id}:status:FT"
            if event_key not in self.seen_events:
                self.seen_events.add(event_key)
                outcome = "venceu" if bota_g > opp_g else ("empatou" if bota_g == opp_g else "perdeu")
                impact_events.append({
                    "type": "fim_jogo",
                    "headline": "Fim de Jogo",
                    "description": f"Apito final! O Botafogo {outcome} a partida por {score_str}.",
                    "score": score_str,
                    "elapsed": 90,
                    "opponent": opponent,
                    "botafogo_goals": bota_g,
                    "opponent_goals": opp_g,
                })

        self.last_status[fixture_id] = status_short

        # 2. Checar eventos de jogo (Gols, Cartões Vermelhos, VAR)
        events = parsed.get("events", [])
        for ev in events:
            time_obj = ev.get("time", {})
            ev_elapsed = time_obj.get("elapsed", 0)
            ev_type = ev.get("type", "")
            ev_detail = ev.get("detail", "")
            team_info = ev.get("team", {})
            team_id = team_info.get("id")
            team_name = team_info.get("name", "")
            player_info = ev.get("player", {})
            player_name = player_info.get("name", "Jogador")

            # Assinatura única do lance
            ev_signature = f"{fixture_id}:{ev_elapsed}:{ev_type}:{ev_detail}:{team_id}:{player_name}"
            if ev_signature in self.seen_events:
                continue

            self.seen_events.add(ev_signature)

            # Caso A: Gol
            if ev_type == "Goal":
                if "Missed Penalty" in ev_detail:
                    continue

                if team_id == self.team_id:
                    # GOL DO BOTAFOGO!
                    impact_events.append({
                        "type": "gol_botafogo",
                        "headline": "GOL DO BOTAFOGO!",
                        "description": f"GOL DO BOTAFOGO! {player_name} marcou aos {ev_elapsed}'! Placar atual: {score_str}.",
                        "score": score_str,
                        "elapsed": ev_elapsed,
                        "opponent": opponent,
                        "player": player_name,
                        "botafogo_goals": bota_g,
                        "opponent_goals": opp_g,
                    })
                else:
                    # Gol do adversário
                    impact_events.append({
                        "type": "gol_adversario",
                        "headline": f"Gol do {opponent}",
                        "description": f"Gol do {opponent}. {player_name} marcou aos {ev_elapsed}'. Placar: {score_str}.",
                        "score": score_str,
                        "elapsed": ev_elapsed,
                        "opponent": opponent,
                        "player": player_name,
                        "botafogo_goals": bota_g,
                        "opponent_goals": opp_g,
                    })

            # Caso B: Cartão Vermelho
            elif ev_type == "Card" and "Red Card" in ev_detail:
                if team_id == self.team_id:
                    impact_events.append({
                        "type": "vermelho_botafogo",
                        "headline": "Expulsão no Botafogo",
                        "description": f"Cartão vermelho pro Botafogo! {player_name} foi expulso aos {ev_elapsed}'.",
                        "score": score_str,
                        "elapsed": ev_elapsed,
                        "opponent": opponent,
                        "player": player_name,
                        "botafogo_goals": bota_g,
                        "opponent_goals": opp_g,
                    })
                else:
                    impact_events.append({
                        "type": "vermelho_adversario",
                        "headline": f"Expulsão no {opponent}",
                        "description": f"Cartão vermelho pro {opponent}! {player_name} expulso aos {ev_elapsed}'.",
                        "score": score_str,
                        "elapsed": ev_elapsed,
                        "opponent": opponent,
                        "player": player_name,
                        "botafogo_goals": bota_g,
                        "opponent_goals": opp_g,
                    })

        return impact_events

    def simulate_event(
        self,
        event_type: str,
        opponent: str = "Mirassol",
        score: str = "Botafogo 1 x 1 Mirassol",
        elapsed: int = 68,
        player: str = "Luiz Henrique"
    ) -> Dict[str, Any]:
        """Gera um evento simulado sintético para validação e testes no soak."""
        clean_type = event_type.lower().strip()
        if clean_type in ("gol_pro", "gol_botafogo", "gol"):
            return {
                "type": "gol_botafogo",
                "headline": "GOL DO BOTAFOGO!",
                "description": f"GOL DO BOTAFOGO! {player} mandou pra rede aos {elapsed}'! Placar: {score}.",
                "score": score,
                "elapsed": elapsed,
                "opponent": opponent,
                "player": player,
                "botafogo_goals": 1,
                "opponent_goals": 1,
            }
        elif clean_type in ("gol_contra", "gol_adversario"):
            return {
                "type": "gol_adversario",
                "headline": f"Gol do {opponent}",
                "description": f"Gol do {opponent}. Marcaram aos {elapsed}'... Que zaga perdida! Placar: {score}.",
                "score": score,
                "elapsed": elapsed,
                "opponent": opponent,
                "player": "Atacante adversário",
                "botafogo_goals": 0,
                "opponent_goals": 1,
            }
        elif clean_type in ("intervalo", "ht"):
            return {
                "type": "intervalo",
                "headline": "Fim do Primeiro Tempo",
                "description": f"Intervalo de jogo! Fim do 1º tempo. O placar tá {score}.",
                "score": score,
                "elapsed": 45,
                "opponent": opponent,
                "player": "",
                "botafogo_goals": 0,
                "opponent_goals": 1,
            }
        elif clean_type in ("inicio_2t", "2h"):
            return {
                "type": "inicio_2t",
                "headline": "Início do Segundo Tempo",
                "description": f"Começou o segundo tempo! Bora virar esse jogo, Fogão! Placar: {score}.",
                "score": score,
                "elapsed": 45,
                "opponent": opponent,
                "player": "",
                "botafogo_goals": 0,
                "opponent_goals": 1,
            }
        elif clean_type in ("fim", "fim_jogo", "ft"):
            return {
                "type": "fim_jogo",
                "headline": "Fim de Jogo",
                "description": f"Acabou o jogo! Placar final: {score}.",
                "score": score,
                "elapsed": 90,
                "opponent": opponent,
                "player": "",
                "botafogo_goals": 2,
                "opponent_goals": 1,
            }
        elif clean_type in ("vermelho_botafogo", "expulsao_botafogo"):
            return {
                "type": "vermelho_botafogo",
                "headline": "Expulsão no Botafogo",
                "description": f"Vermelho direto pro Botafogo! {player} foi expulso aos {elapsed}'!",
                "score": score,
                "elapsed": elapsed,
                "opponent": opponent,
                "player": player,
                "botafogo_goals": 0,
                "opponent_goals": 1,
            }
        else:
            # Default para gol pro
            return self.simulate_event("gol_botafogo", opponent, score, elapsed, player)


botafogo_service = BotafogoLiveService()
