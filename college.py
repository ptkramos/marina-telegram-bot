"""Fase D7 — faculdade além da grade: trabalhos, noites de trabalho, véspera, faltas e atrasos.

Antes: a faculdade era só a grade de aulas. Nenhum prazo, nenhuma noite de
trabalho, nenhuma falta — e o despertador perdido (D13) nunca virava atraso.

* **Trabalhos**: cada disciplina do período tem entregas a cada 3–4 semanas,
  numa aula dela; o tamanho segue os créditos. Cada trabalho tem um ritmo
  sorteado — adiantada, normal ou **última hora** (humana).
* **Noites de trabalho**: nas noites antes da entrega ela trabalha ("fazendo o
  trabalho de Ergodesign") — vira estado (disponibilidade `WORK`) e acontecimento.
* **Véspera**: última hora → vira a noite; senão, ansiedade leve pra dormir
  (gancho `college_onset` usado pelo `sleep_plan`).
* **Faltar aula por conta própria** (pedido do Patrick, 23/09): decidido de
  manhã, depois de acordar — dormiu muito mal, chuva forte, cólica no começo da
  menstruação, ou preguiça (raro). Nunca em dia de entrega; no máximo 2 faltas
  por disciplina em 30 dias. Vira acontecimento com o motivo.
* **Atraso de verdade**: desde 28/09 no `atraso.py` (perdeu o despertador, enrolou,
  o ônibus demorou — a ida sai e chega mais tarde de verdade).

Determinístico por data; nada de chamada de modelo.
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import date, datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

ASSIGNMENT_EVERY_WEEKS = (4, 6)  # 9 disciplinas: ~1,5 entrega por semana, não uma por noite
FIRST_ASSIGNMENT_WEEK = 3
PACE = (("adiantada", 0.30, 5), ("normal", 0.45, 3), ("ultima_hora", 0.25, 1))
SESSION_WINDOW = (time(19, 30), time(23, 30))
SESSION_MINUTES = (60, 150)
SESSAO_ATRASO_MAX = timedelta(minutes=10)     # até 10 min atrasada (o mundo roda de 5 em 5), a hora planejada vale
SESSAO_MIN_RESTANTE = timedelta(minutes=20)   # sobrou menos que isso até a hora de parar: hoje não senta
SKIP_CHANCE_BASE = 0.03
SKIP_CHANCE_BAD_SLEEP = 0.35      # dormiu menos de 5h30
SKIP_CHANCE_RAIN = 0.10
SKIP_MAX_PER_COURSE_30D = 2


def _rng(key: str) -> random.Random:
    return random.Random(f"marina-facul:{key}")


class College:
    def __init__(self, db):
        self.db = db

    # --------------------------------------------------------- disciplinas --
    def _term(self, day: date) -> Optional[dict]:
        from academic_life import AcademicLife
        return AcademicLife(self.db)._active_term_on(day)

    def _courses(self, term_id: int) -> list[dict]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT c.id, c.display_name, c.metadata_json,
                          (SELECT GROUP_CONCAT(b.weekday) FROM academic_schedule_blocks b
                            WHERE b.academic_course_id=c.id AND b.active=1) AS weekdays
                   FROM academic_courses c WHERE c.academic_term_id=? AND c.status='ENROLLED'""",
                (term_id,)).fetchall()
        out = []
        for r in rows:
            if not r["weekdays"]:
                continue
            credits = (json.loads(r["metadata_json"] or "{}") or {}).get("credits", 2)
            out.append({"id": r["id"], "name": r["display_name"], "credits": credits,
                        "weekdays": sorted({int(w) for w in str(r["weekdays"]).split(",")})})
        return out

    def assignments(self, day: date, horizon_days: int = 14) -> list[dict]:
        """Trabalhos com entrega entre `day - 1` e `day + horizon_days`."""
        term = self._term(day)
        if not term:
            return []
        start = date.fromisoformat(term["start_date"])
        end = date.fromisoformat(term["end_date"])
        out = []
        for course in self._courses(term["id"]):
            rng = _rng(f"{term['term_key']}:{course['id']}:agenda")
            week = FIRST_ASSIGNMENT_WEEK + rng.randint(0, 1)
            n = 0
            while True:
                monday = start + timedelta(weeks=week) - timedelta(days=start.weekday())
                due_day = monday + timedelta(days=course["weekdays"][n % len(course["weekdays"])])
                if due_day > end:
                    break
                if day - timedelta(days=1) <= due_day <= day + timedelta(days=horizon_days):
                    prng = _rng(f"{term['term_key']}:{course['id']}:{n}")
                    roll, acc, pace, lead = prng.random(), 0.0, "normal", 3
                    for name, p, days in PACE:
                        acc += p
                        if roll < acc:
                            pace, lead = name, days
                            break
                    final = (end - due_day).days <= 21
                    kind = "entrega final" if final else prng.choice(("trabalho", "exercício", "apresentação"))
                    size = 2.0 if final else 0.5 if kind == "exercício" else 1.2
                    hours = round(course["credits"] * size * prng.uniform(0.8, 1.3), 1)
                    if kind == "exercício":
                        pace, lead = "normal", 1   # exercício cabe numa noite
                    out.append({"key": f"{term['term_key']}:{course['id']}:{n}", "course": course["name"],
                                "course_id": course["id"], "due": due_day.isoformat(), "kind": kind,
                                "hours": hours, "pace": pace, "lead_days": lead})
                week += rng.randint(*ASSIGNMENT_EVERY_WEEKS)
                n += 1
        return sorted(out, key=lambda a: a["due"])

    # ------------------------------------------------------ noites de trabalho --
    def session_on(self, day: date) -> Optional[dict]:
        """Noite de trabalho em `day` (o trabalho mais urgente cuja janela inclui hoje)."""
        for a in self.assignments(day, horizon_days=6):
            due = date.fromisoformat(a["due"])
            if not (due - timedelta(days=a["lead_days"]) <= day < due):
                continue
            if day.weekday() == 5 and due - day > timedelta(days=1):
                continue          # sábado à noite é dela, a não ser que seja véspera
            rng = _rng(f"{a['key']}:sessao:{day.isoformat()}")
            nights = a["lead_days"]
            minutes = min(SESSION_MINUTES[1] + (90 if a["pace"] == "ultima_hora" else 0),
                          max(SESSION_MINUTES[0], int(a["hours"] * 60 / nights)))
            lo = datetime.combine(day, SESSION_WINDOW[0])
            start = lo + timedelta(minutes=rng.randint(0, 60))
            adiantou = self._adiantou(day)
            if adiantou and adiantou < start:
                start = adiantou                          # soak, dia 2: ela disse que ia fazer agora
            return {"assignment": a, "start": start, "end": start + timedelta(minutes=minutes),
                    "vespera": due - day == timedelta(days=1)}
        return None

    # Soak, dia 2 (30/09): "vou pegar firme nele", "tô fechando o trabalho agora" (13:34–15:11) com a sessão só às
    # 20:21 e ela lendo, vendo desfile e jogando Stardew. Decisão do Patrick: a fala vira mundo — livre em casa, a
    # sessão da noite começa agora.
    FAZ_AGORA = re.compile(
        r"\b(?:vou|j[aá] vou|agora vou|bora|t[oô] indo|voltei|t[oô])\b[^.!?\n]{0,35}?"
        r"\b(?:pegar firme|fazer|fechar|terminar|voltar pr[oa]|abrir|focar n[oa]|fechando|terminando|fazendo)\b"
        r"[^.!?\n]{0,25}?\b(?:trabalho|arquivo|projeto)\b"
        r"|\b(?:vou|agora vou|bora)\b[^.!?\n]{0,30}?\bpegar firme\b"
        # 30/09, 19:56: "voltei pro arquivo, juro" (ela estava no Instagram) — voltar/estar no trabalho também conta
        r"|\b(?:voltei|t[oô] de volta|j[aá] t[oô]|t[oô])\s+(?:aqui\s+)?(?:pr[oa]|n[oa])\s+(?:o\s+|meu\s+)?"
        r"(?:trabalho|arquivo|projeto)\b", re.IGNORECASE)
    DEPOIS = re.compile(r"\b(?:mais tarde|depois|amanh[aã]|de noite|à noite|a noite|antes de dormir|daqui a pouco)\b",
                        re.IGNORECASE)

    def _adiantou(self, day: date) -> Optional[datetime]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT value FROM world_bootstrap WHERE key=?",
                               (f"facul:adiantou:{day.isoformat()}",)).fetchone()
        return datetime.fromisoformat(row["value"]) if row else None

    def observe_marina_line(self, fala: str, now: datetime) -> bool:
        """Ela disse que vai fazer (ou está fazendo) o trabalho agora: a sessão do dia começa agora, se ela está
        livre em casa e ainda não sentou pra ele hoje. Devolve se adiantou."""
        for frase in re.split(r"(?<=[.!?\n])", fala or ""):
            if self.FAZ_AGORA.search(frase) and not self.DEPOIS.search(frase):
                break
        else:
            return False
        s = self.session_on(now.date())
        if not s or now >= s["start"] or self._adiantou(now.date()):
            return False
        from meals import Meals
        meals = Meals(self.db)
        if not meals._at_home() or meals._transition_busy(now):
            return False
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at) VALUES (?, ?, ?)",
                         (f"facul:adiantou:{now.date().isoformat()}", now.isoformat(timespec="seconds"),
                          now.isoformat()))
            conn.commit()
        logger.info("college.adiantou sessao=%s agora=%s", s["assignment"]["course"], now.strftime("%H:%M"))
        return True

    def onset(self, day: date) -> tuple[int, list[str]]:
        """Gancho do sono (D2): véspera de entrega mexe na hora de pegar no sono."""
        s = self.session_on(day)
        if not s or not s["vespera"]:
            return 0, []
        a = s["assignment"]
        rng = _rng(f"{a['key']}:vespera")
        if a["pace"] == "ultima_hora":
            return rng.randint(60, 120), [f"virou a noite terminando o {a['kind']} de {a['course']}"]
        return rng.randint(0, 30), [f"ficou ansiosa com a entrega de {a['course']}"]

    # ------------------------------------------------------------- manhã --
    def _skips_last_30d(self, course_name: str, day: date) -> int:
        with self.db.get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM life_events WHERE event_key LIKE 'falta:%' AND event_at>=? AND summary LIKE ?",
                ((day - timedelta(days=30)).isoformat(), f"%{course_name}%")).fetchone()[0]

    def skip_reason(self, day: date, blocks: list[dict]) -> Optional[str]:
        """Ela falta hoje? Decisão dela, pelo corpo e pelo dia (determinística por data)."""
        if not blocks:
            return None
        if any(a["due"] == day.isoformat() for a in self.assignments(day, horizon_days=0)):
            return None          # dia de entrega: vai de qualquer jeito
        if any(self._skips_last_30d(b["display_name"], day) >= SKIP_MAX_PER_COURSE_30D for b in blocks):
            return None
        rng = _rng(f"falta:{day.isoformat()}")
        options = [(SKIP_CHANCE_BASE, "bateu uma preguiça e ela ficou em casa")]
        try:
            from sleep_plan import SleepPlan
            if SleepPlan(self.db).hours_slept(day) < 5.5:
                options.append((SKIP_CHANCE_BAD_SLEEP, "dormiu muito mal e não teve condição"))
        except Exception:
            pass
        try:
            from health import Health   # D11: cólica pela intensidade do ciclo, virose, resfriado forte
            sick = Health(self.db).skip_option(day)
            if sick:
                options.append(sick)
        except Exception:
            pass
        try:
            from calendar_world import CalendarWorld
            observed = CalendarWorld(self.db).context.get("weather:rio", now=datetime.combine(day, time(7, 0)))
            if observed and observed["payload"].get("heavy_rain"):
                options.append((SKIP_CHANCE_RAIN, "chuva forte e ela desistiu de sair"))
        except Exception:
            pass
        chance, reason = max(options)
        return reason if rng.random() < chance else None

    def morning(self, now: datetime) -> Optional[str]:
        """Depois de acordar: decide se falta."""
        from academic_life import AcademicLife
        from sleep_plan import SleepPlan
        day = now.date()
        key = f"facul:manha:{day.isoformat()}"
        with self.db.get_connection() as conn:
            if conn.execute("SELECT 1 FROM world_bootstrap WHERE key=?", (key,)).fetchone():
                return None
        life = AcademicLife(self.db)
        blocks = life.blocks_on(day)
        if not blocks:
            return None
        wake = SleepPlan(self.db).wake(day)
        first = min(datetime.fromisoformat(b["start_at"]) for b in blocks)
        if now < wake or now >= first:
            return None
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at) VALUES (?, 'done', ?)",
                         (key, now.isoformat()))
            conn.commit()
        reason = self.skip_reason(day, blocks)
        if reason:
            SleepPlan(self.db).freeze_wake(day, wake)   # a manhã que já aconteceu não muda
            for b in blocks:
                try:
                    life.cancel_class_occurrence(b["id"], day, source_key=f"falta:{day.isoformat()}:{b['id']}")
                except ValueError:
                    continue
            names = " e ".join(dict.fromkeys(b["display_name"] for b in blocks))
            self._log(f"falta:{day.isoformat()}", wake + timedelta(minutes=10),
                      f"Faltou a aula hoje ({names}): {reason}.")
            return "falta"
        # 28/09: o atraso de verdade (despertador, saída, caminho) é do `atraso.py` — empurra a ida e a chegada.
        return None

    # ------------------------------------------------------------ mundo --
    def materialize(self, now: datetime) -> int:
        from meals import Meals
        meals = Meals(self.db)
        floor = meals._floor(now)
        if floor is None:
            return 0
        done = 0
        if self.morning(now):
            done += 1
        s = self.session_on(now.date())
        if s and s["start"] <= now and s["start"] >= floor and meals._at_home() and not meals._transition_busy(now):
            # 28/09 (auditoria, rodada 3): a sessão das 19:59 foi gravada às 20:29, quando ela chegou da academia,
            # com a hora das 19:59 (o Hoje pôs o trabalho dentro do treino). Na rua, comendo ou no banho, a sessão
            # espera; começa quando ela está livre em casa e vai até a hora planejada de parar.
            start = s["start"] if now - s["start"] <= SESSAO_ATRASO_MAX else now
            if s["end"] - start < SESSAO_MIN_RESTANTE:
                return done       # não sobrou noite pra sentar e trabalhar
            s = {**s, "start": start}
            a = s["assignment"]
            rng = _rng(f"{a['key']}:sessao:{now.date().isoformat()}:texto")
            vibe = ("virando a noite" if s["vespera"] and a["pace"] == "ultima_hora"
                    else rng.choice(("focada", "enrolando um pouco", "rendendo bem")))
            summary = (f"Trabalhou no {a['kind']} de {a['course']} (entrega "
                       f"{'amanhã' if s['vespera'] else date.fromisoformat(a['due']).strftime('%d/%m')}), {vibe}.")
            if self._log(f"facul:sessao:{now.date().isoformat()}", s["start"], summary):
                done += 1
                if now < s["end"] and not meals._transition_busy(now):
                    payload = {"routine_type": "study",
                               "activity": f"fazendo o trabalho de {a['course']} em casa",
                               "place_key": "marina_apartment", "announced_at": now.isoformat(),
                               "transition_at": s["start"].isoformat(), "end_at": s["end"].isoformat()}
                    self.db.set_estado_relacional("pending_transition_json", json.dumps(payload, ensure_ascii=False))
        return done

    def _log(self, key: str, at: datetime, summary: str) -> bool:
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'routine','faculdade',?,'simulated',1,0.3,?,0.5,?)""",
                (key, at.isoformat(), summary, json.dumps(["marina"]), datetime.now().isoformat()))
            conn.commit()
            return bool(cur.rowcount)

    def falta(self, day: date) -> Optional[str]:
        """O "Faltou a aula hoje (…): motivo." do dia, se ela faltou. Soak, dia 2 (30/09): faltar cancela as aulas e
        o prompt passava a dizer "Hoje NÃO tem aula (dia livre)" — ela disse "ainda bem que hoje não tem aula"."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT summary FROM life_events WHERE event_key=?",
                               (f"falta:{day.isoformat()}",)).fetchone()
        return row["summary"] if row else None

    # ------------------------------------------------------------- prompt --
    def prompt_lines(self, now: datetime) -> list[str]:
        items = self.assignments(now.date(), horizon_days=7)
        items = [a for a in items if a["due"] >= now.date().isoformat()]
        if not items:
            return []
        dias = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
        lines = ["[FACULDADE — prazos reais; não invente trabalho fora desta lista]"]
        for a in items[:4]:
            due = date.fromisoformat(a["due"])
            quando = "amanhã" if (due - now.date()).days == 1 else "hoje" if due == now.date() else dias[due.weekday()]
            start_work = due - timedelta(days=a["lead_days"])
            if now.date() < start_work:
                status = "ainda nem começou" + (" (vai deixar pra última hora)" if a["pace"] == "ultima_hora" else "")
            elif now.date() < due - timedelta(days=1):
                status = "já começou"
            else:
                status = "na reta final"
            lines.append(f"- {a['kind'].capitalize()} de {a['course']}: entrega {quando} ({due:%d/%m}) — {status}.")
        return lines
