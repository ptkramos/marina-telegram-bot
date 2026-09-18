"""Resolução mínima de estado/rotina v3.6, sem stories ou chamadas externas."""

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Optional

from db import DatabaseManager
from world_repository import WorldBibleRepository, WorldStateRepository


@dataclass(frozen=True)
class RoutineCandidate:
    activity: str
    place_key: str
    score: float
    source_key: str


class RoutineEngine:
    """Pontua rotinas canônicas; um calendário futuro informará os dias de aula."""

    _ACTIVITIES = {
        "wake": ("acordando e tomando café", "marina_apartment"),
        "university": ("na faculdade", "puc_rio"),
        "pet_walk": ("passeando com Milo", "enseada_botafogo"),
        "gym": ("treinando na academia", "bodytech_sao_clemente"),
        "home_evening": ("curtindo a noite em casa", "marina_apartment"),
        "sleep": ("dormindo", "marina_apartment"),
    }

    def __init__(self, db: DatabaseManager, rng: Optional[random.Random] = None):
        self.db = db
        self.rng = rng or random.Random()

    @staticmethod
    def _within_window(now: datetime, start: Optional[str], end: Optional[str]) -> bool:
        if not start or not end:
            return True
        current = now.hour * 60 + now.minute
        first_h, first_m = map(int, start.split(":"))
        last_h, last_m = map(int, end.split(":"))
        first = first_h * 60 + first_m
        last = last_h * 60 + last_m
        return first <= current <= last if first <= last else current >= first or current <= last

    @staticmethod
    def _day_applies(scope: Optional[str], now: datetime, has_class: Optional[bool]) -> bool:
        if scope == "class_day":
            return has_class is True
        if scope == "light_day":
            return has_class is not True
        if scope == "weekday":
            return now.weekday() < 5
        return scope in (None, "daily", "3_to_5_days_per_week")

    def candidates(
        self, now: datetime, *, has_class: Optional[bool] = None,
        heavy_rain: bool = False, energy: float = 0.7,
    ) -> list[RoutineCandidate]:
        if not 0 <= energy <= 1:
            raise ValueError("energy deve estar entre 0 e 1")
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM routine_patterns WHERE character_key = 'marina' AND active = 1"
            ).fetchall()
        result = []
        for row in rows:
            if not self._day_applies(row["day_scope"], now, has_class):
                continue
            if not self._within_window(now, row["window_start"], row["window_end"]):
                continue
            if row["routine_type"] == "pet_walk" and has_class and now.hour >= 9:
                continue
            activity, place_key = self._ACTIVITIES.get(row["routine_type"], (None, None))
            if not activity:
                continue
            score = float(row["probability"])
            if row["routine_type"] == "gym":
                score *= max(0.2, energy)
                if heavy_rain:
                    result.append(RoutineCandidate(
                        "treinando na academia do prédio", "marina_apartment",
                        min(1.0, score * 1.1), row["canonical_key"] + ":rain_fallback",
                    ))
                    score *= 0.1
            elif row["routine_type"] == "pet_walk" and heavy_rain:
                score *= 0.25
            result.append(RoutineCandidate(activity, place_key, score, row["canonical_key"]))
        return [candidate for candidate in result if candidate.score > 0]

    def choose(self, candidates: list[RoutineCandidate]) -> RoutineCandidate:
        # O fallback permite dias banais sem forçar uma rotina ou um plot.
        options = [*candidates, RoutineCandidate("tempo livre em casa", "marina_apartment", 0.2, "free_time")]
        return self.rng.choices(options, weights=[item.score for item in options], k=1)[0]


class WorldStateManager:
    """Compromisso > plano explícito > consequência recebida > rotina > fallback."""

    def __init__(
        self, db: DatabaseManager, *, routine: Optional[RoutineEngine] = None,
        stale_minutes: int = 60,
    ):
        if stale_minutes <= 0:
            raise ValueError("stale_minutes deve ser positivo")
        self.db = db
        self.routine = routine or RoutineEngine(db)
        self.states = WorldStateRepository(db)
        self.bible = WorldBibleRepository(db)
        self.stale_minutes = stale_minutes

    @staticmethod
    def _active_plan(plan: Optional[Mapping], now: datetime) -> bool:
        if not plan or not plan.get("activity"):
            return False
        start = plan.get("start_at")
        end = plan.get("end_at")
        if start and now < datetime.fromisoformat(start):
            return False
        if end and now >= datetime.fromisoformat(end):
            return False
        if start and not end and now >= datetime.fromisoformat(start) + timedelta(hours=1):
            return False
        return True

    def resolve(
        self, now: datetime, *, confirmed_commitment: Optional[Mapping] = None,
        explicit_plan: Optional[Mapping] = None,
        active_consequence: Optional[Mapping] = None,
        has_class: Optional[bool] = None, weather: Optional[Mapping] = None,
        energy: float = 0.7, force: bool = False,
    ) -> dict:
        if not 0 <= energy <= 1:
            raise ValueError("energy deve estar entre 0 e 1")
        reason = None
        chosen = None
        if confirmed_commitment and confirmed_commitment.get("start_at") and self._active_plan(confirmed_commitment, now):
            chosen = confirmed_commitment
            reason = "confirmed_commitment"
        elif self._active_plan(explicit_plan, now):
            chosen = explicit_plan
            reason = "explicit_plan"
        elif self._active_plan(active_consequence, now):
            chosen = active_consequence
            reason = "active_consequence"

        previous = self.states.latest()
        if chosen is None and previous and not force:
            observed = datetime.fromisoformat(previous["observed_at"])
            age = now - observed
            weather_changed = weather is not None and dict(weather) != json.loads(previous["weather_context_json"] or "null")
            previous_plan = json.loads(previous["current_plan_json"] or "null")
            plan_expired = previous_plan is not None and not self._active_plan(previous_plan, now)
            if (timedelta(0) <= age < timedelta(minutes=self.stale_minutes)
                    and not weather_changed and not plan_expired):
                return previous

        if chosen is None:
            heavy_rain = bool(weather and weather.get("heavy_rain"))
            candidates = self.routine.candidates(
                now, has_class=has_class, heavy_rain=heavy_rain, energy=energy,
            )
            selected = self.routine.choose(candidates)
            chosen = {"activity": selected.activity, "place_key": selected.place_key}
            reason = selected.source_key

        place_key = chosen.get("place_key")
        place = self.bible.get_place(place_key) if place_key else None
        return self.states.add_snapshot({
            "state_date": now.date().isoformat(),
            "observed_at": now.isoformat(),
            "location_place_id": place["id"] if place else None,
            "location_region": place["region"] if place else chosen.get("location_region"),
            "activity": chosen["activity"],
            "energy_level": energy,
            "weather_context_json": dict(weather) if weather else None,
            "current_plan_json": dict(chosen) if reason in ("confirmed_commitment", "explicit_plan") else None,
            "source_json": {"truth_type": "system", "reason": reason},
        })
