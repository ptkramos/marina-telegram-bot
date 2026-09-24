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

import json
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
BED_EARLIEST_TIRED = time(21, 30)  # exausta, capota mais cedo
ONSET_TROUBLE_CHANCE = 0.12        # às vezes demora pra pegar no sono
ONSET_TROUBLE_TPM = 0.20
BED_LATEST = time(3, 30)          # do dia seguinte
FREE_SLEEP_H = (7.5, 9.0)
FREE_WAKE_WINDOW = (time(8, 0), time(11, 0))
WEEKEND_WAKE_WINDOW = (time(8, 30), time(11, 30))
DEEP_SLEEP = (time(2, 0), time(5, 30))
MICRO_WAKE_COUNT = ((0, 0.45), (1, 0.35), (2, 0.20))
MICRO_WAKE_MINUTES = (3, 8)
NAP_SHORT_H, NAP_CHANCE_SHORT = 6.0, 0.7    # noite curta: quase sempre cochila
NAP_MEH_H, NAP_CHANCE_MEH = 6.5, 0.35
NAP_MINUTES = (20, 60)
NAP_WINDOW = (time(13, 30), time(17, 30))
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

    # ---------------------------------------------------- pegar no sono --
    def _phase_on(self, day: date) -> str:
        try:
            from cycle import MenstrualCycleManager
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT data_inicio_ciclo FROM ciclo_biologico ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return ""
            mgr = MenstrualCycleManager(row["data_inicio_ciclo"])
            start = date.fromisoformat(row["data_inicio_ciclo"][:10])
            day_of_cycle = (day - start).days % mgr.cycle_length + 1
            from cycle import PHASES
            return next((k for k, p in PHASES.items() if day_of_cycle in p["days"]), "")
        except Exception:
            return ""

    def _gym_on(self, day: date) -> bool:
        lo = datetime.combine(day, time(0, 0)).isoformat()
        hi = datetime.combine(day + timedelta(days=1), time(0, 0)).isoformat()
        try:
            with self.db.get_connection() as conn:
                return bool(conn.execute(
                    "SELECT 1 FROM world_state WHERE observed_at>=? AND observed_at<? AND "
                    "(activity LIKE '%academia%' OR activity LIKE '%trein%') LIMIT 1", (lo, hi)).fetchone())
        except Exception:
            return False

    def _onset(self, day: date, live: bool) -> tuple[int, list[str]]:
        """Quanto mais cedo (−) ou mais tarde (+) ela pega no sono na noite de `day`, e por quê.

        Decisão do Patrick (23/09): "tudo depende do emocional, saúde e do que tá
        rolando no mundo dela". Cansaço e corpo antecipam; TPM e cabeça cheia
        atrasam. Doença (D11) e ansiedade de prova (D7) entram aqui quando existirem."""
        rng = _rng(day, "pegar_no_sono")
        minutes, why = 0, []
        if self._approx_hours_slept(day) < 6.5:
            minutes -= rng.randint(30, 60)
            why.append("dormiu pouco na noite anterior e capotou mais cedo")
        if self._gym_on(day):
            minutes -= 15
            why.append("treinou e o corpo pediu cama")
        phase = self._phase_on(day)
        if phase == "menstrual":
            minutes -= 20
            why.append("menstruada, mais cansada")
        if live:
            try:
                from world_state import current_energy
                energy = current_energy(self.db, min(datetime.now(), datetime.combine(day, time(22, 0))))
                if energy < 0.35:
                    minutes -= 30
                    why.append("estava sem energia nenhuma")
            except Exception:
                pass
        try:
            # Fase D7: véspera de entrega — última hora vira a noite, senão ansiedade leve.
            from college import College
            extra, reasons = College(self.db).onset(day)
            minutes += extra
            why += reasons
        except Exception:
            pass
        if live:
            try:
                # Fase D14d: cabeça cheia de verdade (ansiedade, preocupação, mágoa) atrasa o sono.
                from emotion import EmotionEngine
                ref = min(datetime.now(), datetime.combine(day, time(23, 0)))   # a noite DAQUELE dia
                worry = next((e for e in EmotionEngine(self.db).episodes(ref)
                              if e.family in ("medo", "tristeza", "raiva") and e.intensity >= 0.35), None)
                if worry:
                    minutes += 20 + int(40 * min(1.0, worry.intensity))
                    why.append(f"demorou pra dormir pensando nisso: {worry.cause}")
            except Exception:
                pass
        chance = ONSET_TROUBLE_CHANCE + (ONSET_TROUBLE_TPM if phase == "tpm" else 0.0)
        if rng.random() < chance:
            minutes += rng.randint(20, 60)
            why.append("demorou pra pegar no sono" + (" (TPM)" if phase == "tpm" else ", cabeça cheia"))
        return minutes, why

    def _bed_simple(self, day: date) -> datetime:
        """A noite de `day` sem os fatores do corpo (ou a congelada) — corta a
        cadeia noite → noite anterior → … que o fator 'dormiu pouco' criaria."""
        frozen = self._frozen(day)
        if frozen:
            return datetime.fromisoformat(frozen["bed"])
        at, _ = self._base_bed(day)
        return max(datetime.combine(day, BED_EARLIEST), min(self._bed_ceiling(day), at))

    def _approx_hours_slept(self, day: date) -> float:
        alarm = self.target_wake(day)
        prev = self._bed_simple(day - timedelta(days=1))
        if alarm:
            wake = alarm + timedelta(minutes=self.overslept(day))
        else:
            wake = self._free_wake(day, prev)
        return max(0.0, (wake - prev).total_seconds() / 3600)

    def _frozen(self, day: date) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT value FROM world_bootstrap WHERE key=?",
                               (f"sono:noite:{day.isoformat()}",)).fetchone()
        try:
            return json.loads(row["value"]) if row else None
        except (TypeError, ValueError):
            return None

    def _freeze(self, day: date, bed: datetime, why: list[str]) -> None:
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at) VALUES (?, ?, ?)",
                         (f"sono:noite:{day.isoformat()}",
                          json.dumps({"bed": bed.isoformat(), "why": why}, ensure_ascii=False),
                          datetime.now().isoformat()))
            conn.commit()

    def bed_why(self, day: date) -> list[str]:
        frozen = self._frozen(day)
        return frozen["why"] if frozen else self._onset(day, live=False)[1]

    def bed(self, day: date) -> datetime:
        """Hora em que ela pega no sono na noite de `day` (pode passar da meia-noite).

        O que depende do estado de agora (energia) só entra na noite de hoje, a
        partir das 20h, e aí a hora fica **congelada**: uma emoção que muda de
        madrugada não pode "acordá-la" nem mudar a noite que já passou."""
        frozen = self._frozen(day)
        if frozen:
            return datetime.fromisoformat(frozen["bed"])
        now = datetime.now()
        live = now >= datetime.combine(day, time(20, 0))
        at, why = self._base_bed(day)
        delta, reasons = self._onset(day, live)
        tired = delta < 0
        lo = datetime.combine(day, BED_EARLIEST_TIRED if tired else BED_EARLIEST)
        at = max(lo, min(self._bed_ceiling(day), at + timedelta(minutes=delta)))
        outing = self._outing_end(day)
        if outing:
            at = max(at, outing + timedelta(minutes=30))   # cansada ou não, só dorme depois de voltar
        if live:
            self._freeze(day, at, reasons)
            # D14: a conta da energia pode ter congelado esta mesma noite no meio
            # do caminho (energia → dívida de sono → noites anteriores). O que
            # ficou gravado é a verdade; devolver outro valor dava duas horas.
            frozen = self._frozen(day)
            if frozen:
                return datetime.fromisoformat(frozen["bed"])
        return at

    def _bed_ceiling(self, day: date) -> datetime:
        hi = datetime.combine(day + timedelta(days=1), BED_LATEST)
        alarm = self.target_wake(day + timedelta(days=1))
        return min(hi, alarm - timedelta(hours=4)) if alarm else hi

    def _base_bed(self, day: date) -> tuple[datetime, list[str]]:
        """Hora-base de deitar, sem o estado do corpo (determinística por data)."""
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
        return at, []

    def wake(self, day: date) -> datetime:
        """Hora em que ela acorda de fato na manhã de `day`.

        Depois que a manhã aconteceu, fica congelada: se ela decide faltar a aula
        (D7) às 6h, o despertador daquele dia não pode "sumir" retroativamente."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT value FROM world_bootstrap WHERE key=?",
                               (f"sono:manha:{day.isoformat()}",)).fetchone()
        if row:
            return datetime.fromisoformat(row["value"])
        alarm = self.target_wake(day)
        if alarm:
            at = alarm + timedelta(minutes=self.overslept(day))
        else:
            at = self._free_wake(day, self.bed(day - timedelta(days=1)))
        if datetime.now() >= at:
            self.freeze_wake(day, at)
        return at

    def freeze_wake(self, day: date, at: datetime) -> None:
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at) VALUES (?, ?, ?)",
                         (f"sono:manha:{day.isoformat()}", at.isoformat(), datetime.now().isoformat()))
            conn.commit()

    def _free_wake(self, day: date, bed: datetime) -> datetime:
        rng = _rng(day, "acordar")
        weekend = day.weekday() >= 5
        lo, hi = WEEKEND_WAKE_WINDOW if weekend else FREE_WAKE_WINDOW
        at = bed + timedelta(minutes=int(rng.uniform(*FREE_SLEEP_H) * 60))
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

    # --------------------------------------------------------------- cochilo --
    def nap(self, day: date) -> Optional[tuple[datetime, datetime]]:
        """Cochilo da tarde depois de noite curta (decisão do Patrick, 23/09:
        "às vezes nosso corpo simplesmente precisa disso"). Só em tarde livre."""
        slept = self.hours_slept(day)
        chance = NAP_CHANCE_SHORT if slept < NAP_SHORT_H else (NAP_CHANCE_MEH if slept < NAP_MEH_H else 0.0)
        rng = _rng(day, "cochilo")
        if rng.random() >= chance:
            return None
        busy = []
        try:
            from academic_life import AcademicLife
            for b in AcademicLife(self.db).blocks_on(day):
                busy.append((datetime.fromisoformat(b["start_at"]) - timedelta(minutes=60),
                             datetime.fromisoformat(b["end_at"]) + timedelta(minutes=60)))
        except Exception:
            pass
        minutes = rng.randint(*NAP_MINUTES)
        lo, hi = datetime.combine(day, NAP_WINDOW[0]), datetime.combine(day, NAP_WINDOW[1])
        for _ in range(8):
            start = lo + timedelta(minutes=rng.randint(0, int((hi - lo).total_seconds() // 60) - minutes))
            end = start + timedelta(minutes=minutes)
            if not any(start < b_end and end > b_start for b_start, b_end in busy):
                return start, end
        return None

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
        nap = self.nap(day)
        if nap:
            result.append(nap)
        return sorted(result)

    def micro_wake_at(self, now: datetime) -> Optional[str]:
        for night, _bed, _wake in self.nights_around(now):
            for start, end, reason in self.micro_wakes(night):
                if start <= now < end:
                    return reason
        return None

    def napping(self, now: datetime) -> bool:
        nap = self.nap(now.date())
        return bool(nap and nap[0] <= now < nap[1])

    def is_asleep(self, now: datetime) -> bool:
        if self.napping(now):
            return True
        asleep = any(bed <= now < wake for _n, bed, wake in self.nights_around(now))
        return asleep and self.micro_wake_at(now) is None

    def next_wake_boundary(self, now: datetime) -> Optional[datetime]:
        """Próximo momento em que ela vai estar acordada (fim do cochilo, micro-despertar ou manhã)."""
        nap = self.nap(now.date())
        if nap and nap[0] <= now < nap[1]:
            return nap[1]
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
        why = self.bed_why(day - timedelta(days=1))
        if why:
            lines.append("- Ontem à noite você " + "; ".join(why) + ".")
        late = self.overslept(day)
        if late:
            lines.append(f"- Passou {late} min do despertador e saiu correndo pra não chegar atrasada.")
        wakes = self.micro_wakes(day - timedelta(days=1))
        if wakes:
            lines.append("- De madrugada você " + " e depois ".join(
                f"{r} ({s:%H:%M})" for s, _e, r in wakes) + ".")
        nap = self.nap(day)
        if nap and now >= nap[1]:
            lines.append(f"- Cochilou das {nap[0]:%H:%M} às {nap[1]:%H:%M} — o corpo pediu.")
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
