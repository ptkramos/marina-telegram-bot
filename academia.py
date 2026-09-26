"""Academia como compromisso do dia (Patrick, 26/09: "ela foi treinar e não teve preparação?").

Antes a academia era rotina sorteada na hora: ela pulava do closet pra Bodytech, sem se arrumar,
sem caminho e sem hora de voltar no card — e a conversa ativa podia cancelar o treino no meio.
Agora o treino do dia é decidido uma vez (de manhã, pela cota da semana, pelo horário livre e pela
energia prevista pra hora do treino) e fica guardado: tem preparo, ida a pé, treino e volta, como
as saídas. Chuva forte na hora da decisão: academia do prédio (sem trajeto).
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from typing import Optional

KEY = "academia_json"
LUGAR = "bodytech_sao_clemente"
IDA_MIN = 12                       # Botafogo a pé (commute.ROUTES)
REF_ENERGIA = 0.7                  # com disposição normal ela vai nos dias da cota


class Academia:
    def __init__(self, db):
        self.db = db

    def _load(self) -> dict:
        raw = self.db.get_estado_relacional(KEY)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def plano(self, day: date, now: Optional[datetime] = None) -> Optional[dict]:
        """O treino do dia ({inicio, fim, onde}) ou None. Hoje fica guardado na primeira consulta."""
        st = self._load()
        if day.isoformat() in st:
            p = st[day.isoformat()]
            return {**p, "inicio": datetime.fromisoformat(p["inicio"]), "fim": datetime.fromisoformat(p["fim"])} if p else None
        p = self._decide(day)
        today = (now or datetime.now()).date()
        if day <= today:
            keep = {(today - timedelta(days=d)).isoformat() for d in range(3)}
            st = {k: v for k, v in st.items() if k in keep}
            st[day.isoformat()] = ({**p, "inicio": p["inicio"].isoformat(), "fim": p["fim"].isoformat()} if p else None)
            self.db.set_estado_relacional(KEY, json.dumps(st))
        return p

    def _decide(self, day: date) -> Optional[dict]:
        from world_state import RoutineEngine, _within_opening_hours
        engine = RoutineEngine(self.db)
        row = engine._routine_row("gym_weekly")
        if not row:
            return None
        slot = engine._placement(day, row, "gym", None)
        if not slot:
            return None
        try:
            from emotion import EmotionEngine
            energia = EmotionEngine(self.db).energy(slot[0])
        except Exception:
            energia = REF_ENERGIA
        roll = random.Random(f"marina-agenda:{day.isoformat()}:{row['canonical_key']}:vontade").random()
        if roll >= min(1.0, max(0.2, energia) / REF_ENERGIA):
            return None                                   # cansada: hoje não vai
        horas = engine._place_opening_hours(LUGAR)
        onde = "predio" if self._chuva_forte() else "rua"
        if onde == "rua" and not (_within_opening_hours(slot[0], horas) and _within_opening_hours(slot[1] - timedelta(minutes=1), horas)):
            onde = "predio"
        return {"inicio": slot[0], "fim": slot[1], "onde": onde}

    def _chuva_forte(self) -> bool:
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT weather_context_json FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
            w = json.loads(row["weather_context_json"] or "null") if row else None
            return bool(w and w.get("heavy_rain"))
        except Exception:
            return False
