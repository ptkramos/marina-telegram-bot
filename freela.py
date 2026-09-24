"""Fase D10 — freela de modelo: a Lívia oferece, ela faz casting, espera, passa
(ou não), prova de roupa, job e o cachê (metade na aprovação, o resto até 1 dia depois do job).

Antes (24/09): a agência da Lívia existia no cânone (booker, Ipanema) e só
aparecia pra cobrar o peso (D1). Nenhum casting, nenhum job, nenhum cachê.

Como funciona (mesmo desenho do D8 e do D7):
- O PLANO de cada oferta sai da data (determinístico): em que dia a Lívia
  manda, quando é o casting, quando sai a resposta, se passou, quando é o job.
- O que já ACONTECEU vira acontecimento do dia (`life_events`, chave
  `freela:<dia da oferta>:<etapa>`) e o motor emocional sente (emotion.py).
- Casting, prova e job viram COMPROMISSO confirmado no CalendarWorld (tipo
  `trabalho`): ela fica "em casting", tem trajeto (commute) e o /status mostra.
  Nunca em cima da hora, nunca batendo com aula (o calendário recusa).
- Saúde (D11) entra: virose ou cólica forte no dia → perde o casting/job.
- Peso (D1) entra: acima do que a agência aceita, passa menos.

Decisões PROVISÓRIAS (Patrick dormindo em 24/09 pediu pra eu decidir e
catalogar — PLANO_VOZ, seção D10): ~2–3 castings por mês, ~1 em 3 vira job,
tipos de job e cachê da tabela JOBS.

Revisão do Patrick (24/09): D10 aprovado, com uma mudança: o cachê é pago 50%
quando ela é aprovada e o resto no máximo 1 dia depois do job — a Lívia faz o
pix pra ela.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta
from typing import Optional

OFFER_CHANCE = 0.12            # por dia útil → ~2,6 castings por mês
APPROVE_CHANCE = 0.35
APPROVE_OVERWEIGHT = 0.6       # acima do peso da agência, passa menos
APPROVE_IN_SHAPE = 1.15        # no peso ideal (≤ 54 kg), um pouco mais
PAY_REST_WITHIN_H = (2, 24)     # o resto do cachê: de 2 a 24 h depois do job (pix da Lívia)
PAY_AFTER_DAYS = 2              # só pra guardar o estado das ofertas por mais uns dias
LOOKBACK_DAYS = 60
STATE_KEY = "freela_state_json"
AGENCY = "boutique_agency"
STUDIO = ("estudio_botafogo", "Estúdio de fotografia em Botafogo", "Botafogo")
CASTING_SLOTS = (time(10, 0), time(11, 30), time(14, 0), time(15, 30), time(17, 0))
FITTING_SLOTS = (time(11, 0), time(16, 0), time(17, 30))
# (o que é, cachê R$ mín–máx, horas de set)
JOBS = (
    ("catálogo de e-commerce de uma loja de roupas", (600, 900), 6),
    ("campanha de moda praia", (1500, 2500), 6),
    ("fotos pra uma marca de biquíni", (900, 1500), 5),
    ("ensaio pra uma marca de roupa fitness", (800, 1200), 4),
    ("editorial pra uma revista pequena", (300, 500), 5),
    ("campanha de uma marca de óculos", (1200, 2000), 5),
    ("vídeo pra uma marca de cosméticos", (700, 1100), 4),
)
WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _rng(key: str) -> random.Random:
    return random.Random(f"marina-freela:{key}")


def _at(day: date, t: time) -> datetime:
    return datetime.combine(day, t)


class Freela:
    def __init__(self, db):
        self.db = db

    # -------------------------------------------------------------- plano --
    def offer_on(self, day: date) -> Optional[dict]:
        """O plano da oferta que a Lívia manda nesse dia (ou None). Só dia útil."""
        if day.weekday() >= 5:
            return None
        rng = _rng(f"oferta:{day.isoformat()}")
        if rng.random() >= OFFER_CHANCE:
            return None
        what, (lo, hi), hours = rng.choice(JOBS)
        casting_day = day + timedelta(days=rng.randint(2, 5))
        if casting_day.weekday() == 6:
            casting_day += timedelta(days=1)
        return {
            "key": f"freela:{day.isoformat()}",
            "what": what,
            "offer_at": _at(day, time(10, 0)) + timedelta(minutes=rng.randint(0, 8 * 60)),
            "casting_day": casting_day,
            "result_days": rng.randint(2, 4),
            "result_minutes": rng.randint(0, 8 * 60),
            "approve_roll": rng.random(),
            "job_after_days": rng.randint(4, 12),
            "fitting_before_days": rng.randint(1, 3),
            "job_start": time(8, 30) if rng.random() < 0.5 else time(9, 30),
            "hours": hours,
            "pay": int(round(rng.randint(lo, hi), -1)),
        }

    def _approve_chance(self) -> float:
        chance = APPROVE_CHANCE
        try:
            from meals import Meals
            meals = Meals(self.db)
            kg = float(meals.weight()["kg"])
            if kg > meals.AGENCY_MAX_KG:
                chance *= APPROVE_OVERWEIGHT
            elif kg <= 54.0:
                chance *= APPROVE_IN_SHAPE
        except Exception:
            pass
        return chance

    # ------------------------------------------------------------- estado --
    def _state(self) -> dict:
        raw = self.db.get_estado_relacional().get(STATE_KEY)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _save(self, data: dict, now: datetime) -> None:
        cutoff = (now.date() - timedelta(days=LOOKBACK_DAYS + PAY_AFTER_DAYS)).isoformat()
        data = {k: v for k, v in data.items() if k.split(":")[1] >= cutoff}
        self.db.set_estado_relacional(STATE_KEY, json.dumps(data, ensure_ascii=False, default=str))

    def _log(self, key: str, at: datetime, summary: str, *, livia: bool = False, share: float = 0.6) -> bool:
        people = ["marina", "livia_vasconcelos"] if livia else ["marina"]
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'work','freela de modelo',?,'simulated',1,0.5,?,?,?)""",
                (key, at.isoformat(), summary, json.dumps(people), share, datetime.now().isoformat()))
            conn.commit()
            return bool(cur.rowcount)

    def _book(self, key: str, kind: str, description: str, start: datetime, end: datetime,
              place: str) -> Optional[int]:
        from calendar_world import CalendarWorld
        try:
            return CalendarWorld(self.db).create_commitment(
                source_key=f"freela:{start.date().isoformat()}:{kind}:{key.split(':')[1]}",
                event_type="trabalho", description=description, start_at=start, end_at=end,
                location_key=place, metadata={"origin": "freela", "offer": key})
        except ValueError:
            return None   # aula, outro compromisso, ou replay

    def _book_first_free(self, key: str, kind: str, description: str, days: list[date],
                         slots: tuple, minutes: int, place: str, now: datetime) -> Optional[tuple[int, datetime]]:
        for day in days:
            for t in slots:
                start = _at(day, t)
                if start <= now + timedelta(hours=3):
                    continue   # nada marcado em cima da hora
                event_id = self._book(key, kind, description, start, start + timedelta(minutes=minutes), place)
                if event_id:
                    return event_id, start
        return None

    def _cancel(self, event_id: Optional[int]) -> None:
        if not event_id:
            return
        try:
            from calendar_world import CalendarWorld
            CalendarWorld(self.db).cancel(event_id)
        except Exception:
            pass

    def _health_blocks(self, day: date) -> Optional[str]:
        try:
            from health import Health
            h = Health(self.db)
            sick = h.illness(day)
            if sick and sick[0] == "virose":
                return "pegou uma virose"
            if h.cramps(day) == 3:
                return "cólica forte, não conseguiu levantar"
        except Exception:
            pass
        return None

    def _studio(self, now: datetime) -> str:
        try:
            from social_world import SocialWorld
            key, name, region = STUDIO
            SocialWorld(self.db).discover_place(key, name, region, observed_at=now.isoformat())
            return key
        except Exception:
            return AGENCY

    # -------------------------------------------------------- acontecer --
    def materialize(self, now: datetime) -> int:
        """Avança cada oferta até onde o relógio já chegou. Idempotente."""
        with self.db.get_connection() as conn:
            clean = conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone()
        if not clean:
            return 0
        try:
            from social_day import SocialDay
            floor = SocialDay(self.db)._floor(now)
        except Exception:
            floor = now - timedelta(days=1)
        data = self._state()
        done = 0
        for back in range(LOOKBACK_DAYS, -1, -1):
            plan = self.offer_on(now.date() - timedelta(days=back))
            if not plan or plan["offer_at"] > now:
                continue
            st = data.get(plan["key"])
            if st is None:
                if plan["offer_at"] < floor:
                    continue   # antes da vida registrada: não inventa passado
                st = data[plan["key"]] = {"what": plan["what"], "step": "oferta"}
            before = st["step"]
            self._advance(plan, st, now)
            done += st["step"] != before
        if done:
            self._save(data, now)
        return done

    def _advance(self, plan: dict, st: dict, now: datetime) -> None:
        key, what = plan["key"], plan["what"]
        if st["step"] == "oferta":
            self._log(f"{key}:oferta", plan["offer_at"],
                      f"A Lívia da agência mandou um casting: {what}.", livia=True)
            days = [plan["casting_day"] + timedelta(days=k) for k in range(3)]
            booked = self._book_first_free(key, "casting", f"Casting na agência: {what}", days,
                                           CASTING_SLOTS, 90, AGENCY, max(now, plan["offer_at"]))
            if not booked:
                self._log(f"{key}:sem_horario", plan["offer_at"] + timedelta(minutes=20),
                          f"Não conseguiu encaixar o casting ({what}) — batia com aula.", livia=True, share=0.3)
                st["step"] = "fim"
                return
            st["casting_id"], st["casting_at"] = booked[0], booked[1].isoformat()
            st["step"] = "casting_marcado"
        if st["step"] == "casting_marcado":
            start = datetime.fromisoformat(st["casting_at"])
            end = start + timedelta(minutes=90)
            if now < start:
                return
            blocked = self._health_blocks(start.date())
            if blocked:
                self._cancel(st.get("casting_id"))
                self._log(f"{key}:casting_perdido", start, f"Perdeu o casting ({what}): {blocked}.")
                st["step"] = "fim"
                return
            if now < end:
                return
            self._log(f"{key}:casting", end, f"Fez o casting na agência: {what}. Agora é esperar a resposta.")
            st["result_at"] = (_at(end.date() + timedelta(days=plan["result_days"]), time(10, 0))
                               + timedelta(minutes=plan["result_minutes"])).isoformat()
            st["step"] = "esperando"
        if st["step"] == "esperando":
            result_at = datetime.fromisoformat(st["result_at"])
            if now < result_at:
                return
            if plan["approve_roll"] >= self._approve_chance():
                self._log(f"{key}:resultado", result_at,
                          f"A Lívia avisou: não passou no casting ({what}). Escolheram outra menina.", livia=True)
                st["step"] = "fim"
                return
            job_day = result_at.date() + timedelta(days=plan["job_after_days"])
            place = self._studio(now)
            job = None
            for k in range(10):   # um dia sem aula (sábado é comum pra set)
                d = job_day + timedelta(days=k)
                start = _at(d, plan["job_start"])
                if start <= now + timedelta(hours=12):
                    continue
                job = self._book(key, "job", f"Sessão de fotos: {what}", start,
                                 start + timedelta(hours=plan["hours"]), place)
                if job:
                    break
            if not job:
                self._log(f"{key}:resultado", result_at,
                          f"Passou no casting ({what}), mas a data do job batia com a faculdade e ela teve que "
                          "abrir mão.", livia=True)
                st["step"] = "fim"
                return
            self._log(f"{key}:resultado", result_at,
                      f"A Lívia avisou: PASSOU no casting ({what})! Job marcado pra {start:%d/%m} às {start:%H:%M}, "
                      f"cachê de R$ {plan['pay']}.", livia=True, share=0.9)
            half = plan["pay"] // 2
            self._log(f"{key}:sinal", result_at + timedelta(minutes=40),
                      f"A Lívia fez o pix de metade do cachê ({what}): R$ {half}.", livia=True, share=0.6)
            st.update(step="job_marcado", job_id=job, job_at=start.isoformat(), pay=plan["pay"],
                      rest=plan["pay"] - half)
            fit_days = [start.date() - timedelta(days=plan["fitting_before_days"] - k)
                        for k in range(plan["fitting_before_days"])]
            fit = self._book_first_free(key, "prova", f"Prova de roupa pro job: {what}", fit_days,
                                        FITTING_SLOTS, 60, place, now)
            if fit:
                st["fitting_id"], st["fitting_at"] = fit[0], fit[1].isoformat()
        if st["step"] == "job_marcado":
            if st.get("fitting_at") and not st.get("fitting_done"):
                fit_end = datetime.fromisoformat(st["fitting_at"]) + timedelta(minutes=60)
                if now >= fit_end:
                    self._log(f"{key}:prova", fit_end, f"Fez a prova de roupa pro job ({what}).", share=0.5)
                    st["fitting_done"] = True
            start = datetime.fromisoformat(st["job_at"])
            end = start + timedelta(hours=plan["hours"])
            if now < start:
                return
            blocked = self._health_blocks(start.date())
            if blocked:
                self._cancel(st.get("job_id"))
                self._log(f"{key}:job_perdido", start,
                          f"Perdeu o job ({what}): {blocked}. A agência mandou outra menina no lugar.", livia=True)
                st["step"] = "fim"
                return
            if now < end:
                return
            self._log(f"{key}:job", end, f"Fez o job: {what}. {plan['hours']} horas de set, cansada mas feliz.",
                      share=0.9)
            hours = _rng(f"pix:{key}").randint(*PAY_REST_WITHIN_H)
            st["pay_at"] = (end + timedelta(hours=hours)).isoformat()
            st["step"] = "a_receber"
        if st["step"] == "a_receber":
            pay_at = datetime.fromisoformat(st["pay_at"])
            if now < pay_at:
                return
            rest = st.get("rest", st["pay"])
            self._log(f"{key}:cache", pay_at, f"A Lívia fez o pix do resto do cachê ({what}): R$ {rest}.",
                      livia=True, share=0.7)
            st["step"] = "fim"

    # -------------------------------------------------------- perguntas --
    def upcoming(self, now: datetime, horizon_days: int = 10) -> list[dict]:
        """Compromissos de trabalho marcados à frente (casting, prova, job)."""
        out = []
        for st in self._state().values():
            for kind, field, minutes in (("casting", "casting_at", 90), ("prova", "fitting_at", 60),
                                         ("job", "job_at", None)):
                at = st.get(field)
                if not at or st["step"] == "fim":
                    continue
                start = datetime.fromisoformat(at)
                if now < start + timedelta(minutes=minutes or 0) and start <= now + timedelta(days=horizon_days):
                    if kind == "casting" and st["step"] != "casting_marcado":
                        continue
                    if kind == "prova" and st.get("fitting_done"):
                        continue
                    out.append({"kind": kind, "what": st["what"], "start": start})
        return sorted(out, key=lambda x: x["start"])

    def prompt_lines(self, now: datetime) -> list[str]:
        data = self._state()
        items = self.upcoming(now)
        waiting = [st for st in data.values() if st["step"] == "esperando"]
        to_receive = [st for st in data.values() if st["step"] == "a_receber"]
        if not items and not waiting and not to_receive:
            return []
        names = {"casting": "casting", "prova": "prova de roupa", "job": "JOB (sessão de fotos)"}

        def quando(dt: datetime) -> str:
            gap = (dt.date() - now.date()).days
            dia = "hoje" if gap == 0 else "amanhã" if gap == 1 else f"{WEEKDAYS[dt.weekday()]} ({dt:%d/%m})"
            return f"{dia} às {dt:%H:%M}"

        lines = ["[TRABALHO DE MODELO (agência da Lívia) — agenda real; não invente casting nem job fora daqui]"]
        lines += [f"- {names[i['kind']]}: {i['what']} — {quando(i['start'])}" for i in items[:4]]
        lines += [f"- Esperando a resposta do casting: {st['what']}" for st in waiting[:2]]
        lines += [f"- Falta a Lívia mandar o resto do cachê: R$ {st.get('rest', st['pay'])} ({st['what']}), "
                  f"até {datetime.fromisoformat(st['pay_at']):%d/%m %H:%M}" for st in to_receive[:2]]
        pendentes = [st for st in data.values() if st["step"] == "job_marcado" and st.get("rest")]
        lines += [f"- Já recebeu metade do cachê (R$ {st['pay'] - st['rest']}) do job {st['what']}; o resto "
                  "cai depois do job." for st in pendentes[:2]]
        return lines
