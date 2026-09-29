"""Rotinas que viram compromisso do dia (Patrick, 26/09: "ela foi treinar e não teve preparação?").

Antes academia e passeio do Milo eram rotinas sorteadas na hora: ela pulava de casa pra Bodytech
ou pra Enseada, sem se arrumar, sem caminho e sem hora de voltar no card — e a conversa ativa
cancelava no meio. Agora cada uma é decidida uma vez por dia (cota da semana, primeiro horário
livre, energia prevista pra hora) e fica guardada: tem preparo, ida, lá e volta, como as saídas.
É o "planejado" da agenda única; o que ela decide na hora por vontade está em `vontade.py`.
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

# tipo → (rotina canônica, tipo da rotina, lugar, minutos a pé, chave guardada)
ROTINAS = {
    "academia": ("gym_weekly", "gym", LUGAR, IDA_MIN, KEY),
    "milo": ("milo_morning_walk", "pet_walk", "enseada_botafogo", 4, "passeio_milo_json"),
}


class Planejada:
    tipo = "academia"

    def __init__(self, db):
        self.db = db
        self.rotina, self.routine_type, self.lugar, self.ida_min, self.key = ROTINAS[self.tipo]

    def _load(self) -> dict:
        raw = self.db.get_estado_relacional(self.key)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def plano(self, day: date, now: Optional[datetime] = None) -> Optional[dict]:
        """O compromisso do dia ({inicio, fim, onde}) ou None. Hoje fica guardado na primeira consulta."""
        st = self._load()
        if day.isoformat() in st:
            p = st[day.isoformat()]
            return {**p, "inicio": datetime.fromisoformat(p["inicio"]), "fim": datetime.fromisoformat(p["fim"])} if p else None
        p = self._decide(day)
        today = (now or datetime.now()).date()
        if day <= today:
            # 27/09: o que ela combinou pra amanhã fica; 29/09: e o dia consultado também (relatório de um dia antigo)
            desde = (min(today, day) - timedelta(days=2)).isoformat()
            st = {k: v for k, v in st.items() if k >= desde}
            st[day.isoformat()] = ({**p, "inicio": p["inicio"].isoformat(), "fim": p["fim"].isoformat()} if p else None)
            self.db.set_estado_relacional(self.key, json.dumps(st))
        return p

    def _decide(self, day: date) -> Optional[dict]:
        from world_state import RoutineEngine, _within_opening_hours
        engine = RoutineEngine(self.db)
        row = engine._routine_row(self.rotina)
        if not row:
            return None
        slot = engine._placement(day, row, self.routine_type, None)
        if not slot:
            return None
        chuva = self._chuva_forte()
        roll = random.Random(f"marina-agenda:{day.isoformat()}:{row['canonical_key']}:vontade").random()
        if self.tipo == "milo":
            if chuva and roll >= 0.25:
                return None                               # chuva forte: só o xixi rapidinho
            return {"inicio": slot[0], "fim": slot[1], "onde": "rua"}
        try:
            from emotion import EmotionEngine
            energia = EmotionEngine(self.db).energy(slot[0])
        except Exception:
            energia = REF_ENERGIA
        if roll >= min(1.0, max(0.2, energia) / REF_ENERGIA):
            return None                                   # cansada: hoje não vai
        horas = engine._place_opening_hours(self.lugar)
        onde = "predio" if chuva else "rua"
        if onde == "rua" and not (_within_opening_hours(slot[0], horas)
                                  and _within_opening_hours(slot[1] - timedelta(minutes=1), horas)):
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


class Academia(Planejada):
    tipo = "academia"


class PasseioMilo(Planejada):
    tipo = "milo"


def planejada(routine_type: str, db) -> Optional[Planejada]:
    return {"gym": Academia, "gym_indoor": Academia, "pet_walk": PasseioMilo}.get(routine_type, lambda _db: None)(db)
