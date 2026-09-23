"""Fases D2 + D3 + D13 — sono variável, micro-despertares e manhã planejada de trás pra frente.

Antes: ela deitava **meia-noite em ponto** e acordava 07:00 (dia de aula) ou
08:30 (dia livre), todo dia, sem olhar a que horas era o primeiro compromisso
nem quanto tempo levava pra ficar pronta. Sono binário: dormindo, nada passa.

Agora (desenhado com o Patrick em 22–23/09):
* **D13 — manhã de trás pra frente.** Com compromisso (aula), a hora de acordar
  é: saída pro trajeto (C.4) − se arrumar (banho, skincare, cabelo, maquiagem,
  roupa e café — ela é vaidosa) − margem. Às vezes ela passa do despertador:
  acorda atrasada e corre (vira acontecimento do dia).
* **D2 — sono variável.** Com compromisso no dia seguinte ela **tenta** dormir
  8 h e quase sempre dorme menos (série, celular, cabeça cheia); sexta e sábado
  esticam; saída com as amigas empurra a hora de deitar. Sem compromisso, acorda
  quando o corpo pede, depois de 7h30–9h de sono.
* **D3 — micro-despertares** (plano B.6, aprovado em 20/09): 0 a 2 por noite,
  nunca no sono profundo (02:00–05:30), 3–8 min, por banheiro, sede, sonho ruim
  ou celular por reflexo. Se o Patrick escreveu, é aí que ela vê e responde
  curtinho antes de voltar a dormir.

Tudo determinístico por data. Kill switch: `SLEEP_PLAN_ENABLED=false` volta às
janelas fixas do cânone.
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from typing import Optional

PREP_MINUTES = (50, 80)           # banho + skincare + cabelo + maquiagem + roupa + café
MARGIN_MINUTES = (0, 10)
OVERSLEEP_CHANCE = 0.15
OVERSLEEP_MINUTES = (10, 30)
EARLIEST_WAKE = time(5, 0)        # aula às 7h + trajeto de ~45 min + se arrumar ≈ 5h10
TARGET_SLEEP_H = 8.0
BED_DELAY_MIN = (10, 75)          # tenta 8 h, dorme menos: série, celular, cabeça cheia
WEEKEND_NIGHT_EXTRA_MIN = (45, 150)
BED_EARLIEST = time(22, 30)
BED_LATEST = time(3, 30)          # do dia seguinte
FREE_SLEEP_H = (7.5, 9.0)
FREE_WAKE_WINDOW = (time(8, 0), time(11, 0))
WEEKEND_WAKE_WINDOW = (time(8, 30), time(11, 30))
DEEP_SLEEP = (time(2, 0), time(5, 30))
MICRO_WAKE_COUNT = ((0, 0.45), (1, 0.35), (2, 0.20))
MICRO_WAKE_MINUTES = (3, 8)
MICRO_WAKE_REASONS = (("foi ao banheiro", 0.5), ("acordou com sede e foi beber água", 0.2),
                      ("acordou de um sonho ruim", 0.1), ("pegou o celular por reflexo", 0.2))


def _rng(day: date, name: str) -> random.Random:
    return random.Random(f"marina-sono:{day.isoformat()}:{name}")


def enabled() -> bool:
    try:
        from config import settings
        return bool(getattr(settings, "SLEEP_PLAN_ENABLED", True))
    except Exception:
        return True


class SleepPlan:
    def __init__(self, db):
        self.db = db
        self._key = str(getattr(db, "db_path", id(db)))

    # --------------------------------------------------------- compromissos --
    def _first_commitment(self, day: date) -> Optional[datetime]:
        """Saída de casa pro primeiro compromisso da manhã (trajeto do C.4)."""
        return _first_departure(self._key, self.db, day)

    def target_wake(self, day: date) -> Optional[datetime]:
        """Hora em que o despertador toca (só em dia com compromisso)."""
        leave = self._first_commitment(day)
        if not leave:
            return None
        rng = _rng(day, "despertador")
        at = leave - timedelta(minutes=rng.randint(*PREP_MINUTES) + rng.randint(*MARGIN_MINUTES))
        return max(at, datetime.combine(day, EARLIEST_WAKE))

    def overslept(self, day: date) -> int:
        """Minutos que ela passou do despertador (0 = acordou na hora)."""
        if not self.target_wake(day):
            return 0
        rng = _rng(day, "atrasou")
        return rng.randint(*OVERSLEEP_MINUTES) if rng.random() < OVERSLEEP_CHANCE else 0

    # ------------------------------------------------------------- noite --
    def _outing_end(self, day: date) -> Optional[datetime]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT MAX(end_at) FROM eventos_pendentes WHERE source_key LIKE ? AND confirmed=1
                   AND status != 'cancelled'""", (f"outing:{day.isoformat()}:%",)).fetchone()
        try:
            return datetime.fromisoformat(row[0]) if row and row[0] else None
        except ValueError:
            return None

    def bed(self, day: date) -> datetime:
        """Hora em que ela pega no sono na noite de `day` (pode passar da meia-noite)."""
        rng = _rng(day, "deitar")
        tomorrow = day + timedelta(days=1)
        alarm = self.target_wake(tomorrow)
        if alarm:
            # Tenta dormir 8 h antes do compromisso; quase sempre passa do ponto.
            at = alarm - timedelta(hours=TARGET_SLEEP_H) + timedelta(minutes=rng.randint(*BED_DELAY_MIN))
        else:
            at = datetime.combine(day, time(23, 0)) + timedelta(minutes=rng.randint(0, 90))
            if day.weekday() in (4, 5):          # sexta e sábado esticam
                at += timedelta(minutes=rng.randint(*WEEKEND_NIGHT_EXTRA_MIN))
        outing = self._outing_end(day)
        if outing:
            at = max(at, outing + timedelta(minutes=rng.randint(40, 90)))
        lo = datetime.combine(day, BED_EARLIEST)
        hi = datetime.combine(tomorrow, BED_LATEST)
        if alarm:
            hi = min(hi, alarm - timedelta(hours=4))
        return max(lo, min(hi, at))

    def wake(self, day: date) -> datetime:
        """Hora em que ela acorda de fato na manhã de `day`."""
        alarm = self.target_wake(day)
        if alarm:
            return alarm + timedelta(minutes=self.overslept(day))
        rng = _rng(day, "acordar")
        weekend = day.weekday() >= 5
        lo, hi = WEEKEND_WAKE_WINDOW if weekend else FREE_WAKE_WINDOW
        at = self.bed(day - timedelta(days=1)) + timedelta(minutes=int(rng.uniform(*FREE_SLEEP_H) * 60))
        return max(datetime.combine(day, lo), min(datetime.combine(day, hi), at))

    def hours_slept(self, day: date) -> float:
        """Horas de sono da noite que termina na manhã de `day`."""
        return max(0.0, (self.wake(day) - self.bed(day - timedelta(days=1))).total_seconds() / 3600)

    # ------------------------------------------------------ micro-despertar --
    def micro_wakes(self, day: date) -> list[tuple[datetime, datetime, str]]:
        """Micro-despertares da noite de `day` (entre bed(day) e wake(day+1))."""
        start, end = self.bed(day), self.wake(day + timedelta(days=1))
        rng = _rng(day, "micro")
        roll, acc, count = rng.random(), 0.0, 0
        for n, p in MICRO_WAKE_COUNT:
            acc += p
            if roll < acc:
                count = n
                break
        deep_lo = datetime.combine(day + timedelta(days=1), DEEP_SLEEP[0])
        deep_hi = datetime.combine(day + timedelta(days=1), DEEP_SLEEP[1])
        zones = [(start + timedelta(minutes=45), min(deep_lo, end - timedelta(minutes=20))),
                 (max(deep_hi, start + timedelta(minutes=45)), end - timedelta(minutes=20))]
        zones = [(a, b) for a, b in zones if (b - a) >= timedelta(minutes=15)]
        result = []
        for _ in range(count):
            if not zones:
                break
            a, b = rng.choice(zones)
            at = a + timedelta(minutes=rng.randint(0, int((b - a).total_seconds() // 60) - 10))
            reasons, weights = zip(*MICRO_WAKE_REASONS)
            reason = rng.choices(reasons, weights=weights, k=1)[0]
            result.append((at, at + timedelta(minutes=rng.randint(*MICRO_WAKE_MINUTES)), reason))
        result.sort()
        # Dois despertares colados viram um só.
        merged = []
        for item in result:
            if merged and item[0] < merged[-1][1] + timedelta(minutes=30):
                continue
            merged.append(item)
        return merged

    # ------------------------------------------------------------ consultas --
    def nights_around(self, now: datetime) -> list[tuple[date, datetime, datetime]]:
        out = []
        for night in (now.date() - timedelta(days=1), now.date()):
            out.append((night, self.bed(night), self.wake(night + timedelta(days=1))))
        return out

    def windows_on(self, day: date) -> list[tuple[datetime, datetime]]:
        """Intervalos de sono dentro do dia de calendário `day`."""
        lo, hi = datetime.combine(day, time(0, 0)), datetime.combine(day + timedelta(days=1), time(0, 0))
        result = []
        for night in (day - timedelta(days=1), day):
            start, end = max(lo, self.bed(night)), min(hi, self.wake(night + timedelta(days=1)))
            if start < end:
                result.append((start, end))
        return result

    def micro_wake_at(self, now: datetime) -> Optional[str]:
        for night, _bed, _wake in self.nights_around(now):
            for start, end, reason in self.micro_wakes(night):
                if start <= now < end:
                    return reason
        return None

    def is_asleep(self, now: datetime) -> bool:
        asleep = any(bed <= now < wake for _n, bed, wake in self.nights_around(now))
        return asleep and self.micro_wake_at(now) is None

    def next_wake_boundary(self, now: datetime) -> Optional[datetime]:
        """Próximo momento em que ela vai estar acordada (micro-despertar ou manhã)."""
        for night, bed, wake in self.nights_around(now):
            if bed <= now < wake:
                upcoming = [s for s, _e, _r in self.micro_wakes(night) if s > now]
                return min(upcoming) if upcoming else wake
        return None

    # --------------------------------------------------------------- prompt --
    def prompt_lines(self, now: datetime) -> list[str]:
        day = now.date()
        wake = self.wake(day)
        if now < wake:
            return []
        bed = self.bed(day - timedelta(days=1))
        h = self.hours_slept(day)
        lines = [f"- Esta noite você dormiu das {bed:%H:%M} às {wake:%H:%M} (~{h:.0f}h de sono)."
                 + (" Foi pouco: está com sono e com menos paciência." if h < 6 else "")]
        late = self.overslept(day)
        if late:
            lines.append(f"- Passou {late} min do despertador e saiu correndo pra não chegar atrasada.")
        wakes = self.micro_wakes(day - timedelta(days=1))
        if wakes:
            lines.append("- De madrugada você " + " e depois ".join(
                f"{r} ({s:%H:%M})" for s, _e, r in wakes) + ".")
        return lines


_DEPARTURE_CACHE: dict = {}


def _first_departure(db_key: str, db, day: date) -> Optional[datetime]:
    try:
        from academic_life import AcademicLife
        blocks = AcademicLife(db).blocks_on(day)
    except Exception:
        return None
    if not blocks:
        return None
    first = min(datetime.fromisoformat(b["start_at"]) for b in blocks)
    sig = (db_key, day.isoformat(), first.isoformat())
    if sig not in _DEPARTURE_CACHE:
        if len(_DEPARTURE_CACHE) > 512:
            _DEPARTURE_CACHE.clear()
        leave = first - timedelta(minutes=40)
        try:
            from commute import Commute
            ida = [leg for leg in Commute(db).legs_on(day) if leg.key.endswith(":puc:ida")]
            if ida:
                leave = ida[0].start
        except Exception:
            pass
        _DEPARTURE_CACHE[sig] = leave
    return _DEPARTURE_CACHE[sig]
