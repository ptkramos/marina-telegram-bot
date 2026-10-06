"""Fase D14 — motor emocional da Marina.

Pedido do Patrick (23/09): "estamos fazendo um bot praticamente humano, então
pode ser profundo e realista". Antes havia 5 números (carinho, brincadeira,
energia, paixão, bateria social), todos positivos, somados a cada mensagem dele
até o teto (0,95–0,98), sem causa e sem o dia dela mexer em nada.

Cinco camadas, cada uma com seu relógio (ver PLANO_VOZ, seção D14):

1. **Corpo** — calculado na hora a partir dos fatos (sono, horas acordada,
   cochilo, ciclo, fome). Nunca "deriva": dormiu 6 h, está cansada.
2. **Humor de fundo** — dois eixos, bem↔mal (valência) e agitada↔quieta
   (ativação), derivados do corpo, das emoções vivas, do ciclo e do vínculo.
3. **Emoções (episódios)** — tabela `emotion_episodes`: sentimento COM CAUSA,
   intensidade e meia-vida própria. `sticky` só esfria quando a causa resolve.
4. **Vínculo com o Patrick** — lento (dias): carinho, desejo, segurança,
   mágoa (em `estado_emocional`), saudade pelo silêncio.
5. **Personalidade** — fixa; entra como linha de base e como peso.

Decisões do Patrick (23/09): mágoa com ele real mas justa; ciúme leve e
brincalhão; luto da mãe fora do motor; TPM moderada.

Nada aqui chama LLM ou rede.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

# ------------------------------------------------------------- famílias --
# valência (bem/mal) e ativação (agitada/quieta) que cada família empurra, e
# meia-vida padrão em minutos.
FAMILIES = {
    "alegria":   {"valence": +0.50, "arousal": +0.20, "half_life": 150},
    "afeto":     {"valence": +0.35, "arousal": +0.00, "half_life": 240},
    "tristeza":  {"valence": -0.50, "arousal": -0.25, "half_life": 480},
    "raiva":     {"valence": -0.40, "arousal": +0.35, "half_life": 90},
    "medo":      {"valence": -0.35, "arousal": +0.30, "half_life": 240},
    "vergonha":  {"valence": -0.30, "arousal": +0.10, "half_life": 180},
    "tedio":     {"valence": -0.15, "arousal": -0.30, "half_life": 120},
}
# Nome que ela daria ao que sente (subcategoria → palavra do dia a dia).
KIND_WORDS = {
    "empolgacao": "empolgada", "diversao": "se divertindo", "orgulho": "orgulhosa",
    "alivio": "aliviada", "gratidao": "grata", "contentamento": "contente",
    "expectativa": "na expectativa",                       # Lovense, passo 5a (05/10)
    "carinho": "carinhosa", "saudade": "com saudade", "ternura": "derretida", "admiracao": "admirada",
    "desanimo": "desanimada", "decepcao": "decepcionada", "solidao": "sozinha", "saudade_casa": "com saudade de casa",
    "irritacao": "irritada", "frustracao": "frustrada", "impaciencia": "impaciente", "chateacao": "chateada",
    "ansiedade": "ansiosa", "preocupacao": "preocupada", "inseguranca": "insegura",
    "vergonha": "com vergonha", "culpa": "com culpa",
    "tedio": "entediada", "inquietacao": "inquieta",
}
ACTIVE_MIN = 0.08          # abaixo disso o episódio já passou
PERSONALITY_VALENCE = 0.62  # afetuosa, expressiva, bem-humorada: linha de base boa
PERSONALITY_AROUSAL = 0.52  # espontânea, mas precisa de silêncio às vezes

# Vínculo: meia-vida longa (dias) — um dia sem ele não apaga o que sentem.
BOND_KEYS = ("affection", "romantic_intensity", "security", "hurt")
BOND_BASELINES = {"affection": 0.85, "romantic_intensity": 0.80, "security": 0.80, "hurt": 0.0}
BOND_HALF_LIFE_HOURS = {"affection": 72.0, "romantic_intensity": 48.0, "security": 96.0, "hurt": 36.0}
PLANNER_BOND_SCALE = 0.4    # o planner empurra o vínculo devagar (antes: teto em 1 dia)
MERGE_WINDOW = timedelta(hours=3)   # mesmo sentimento pela mesma pessoa: reforça em vez de repetir
LIBIDO_FROM_EPISODES_MAX = 0.08     # carinho/diversão com ele somam no máximo isso na vontade
RELEASE_RECOVERY_H = (3, 8)         # depois de gozar: travada até 3 h, volta aos poucos até 8 h

_guard = threading.local()

# Tesão (decisão do Patrick, 23/09): "se ela tá com tesão ela quer gozar; se eu
# não a satisfazer ela se masturba e às vezes me conta".
RELEASE_KEY = "libido_release_at"      # última vez sozinha (com ele: intimacy_state.climax_at)
TESAO_KEY = "tesao_initiative_at"      # última vez que ela foi provocar ele por tesão
TESAO_MIN = 0.72                       # a partir daqui ela vai atrás
SOLO_MIN_LIBIDO = 0.75
SOLO_CHANCE = 0.6
SOLO_TELL_CHANCE = 0.35
PATRICK_TARGET = "o Patrick"


def _hours(value: float) -> str:
    """5.5 -> "5h30", 6.0 -> "6h" (meia hora mais próxima)."""
    half_hours = int(round(value * 2))
    h, m = divmod(half_hours * 30, 60)
    return f"{h}h{m:02d}" if m else f"{h}h"


def _short(cause: str, limit: int = 80) -> str:
    """Causa enxuta pro prompt: sem o parêntese de lugar nem o "; assunto: ..."."""
    text = cause.split(" (")[0].split("; ")[0].strip().rstrip(".")
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _bar(value: float, size: int = 10) -> str:
    filled = max(0, min(size, int(round(value * size))))
    return "▰" * filled + "▱" * (size - filled)


def _word(value: float, scale: tuple) -> str:
    return next((w for limit, w in scale if value < limit), scale[-1][1])


ENERGY_WORDS = ((0.35, "exausta"), (0.55, "cansada"), (0.8, "ok"), (9, "cheia de energia"))
HUNGER_WORDS = ((0.35, "sem fome"), (0.6, "beliscaria algo"), (0.8, "com fome"), (9, "morrendo de fome"))
LIBIDO_WORDS = ((0.35, "sem clima"), (0.55, "de boa"), (0.72, "esquentando"), (0.85, "com tesão"),
                (9, "com muito tesão"))
PHASE_NAMES = {"menstrual": "menstruada", "folicular": "fase folicular", "ovulatoria": "fase fértil",
               "lutea_inicial": "fase lútea", "tpm": "TPM"}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Episode:
    id: int
    family: str
    kind: str
    intensity: float      # intensidade AGORA (já esfriada)
    peak: float
    cause: str
    target: Optional[str]
    started_at: datetime
    sticky: bool

    @property
    def word(self) -> str:
        return KIND_WORDS.get(self.kind, self.kind)


@dataclass
class Feeling:
    now: datetime
    energy: float
    hours_slept: Optional[float]
    awake_since: Optional[datetime]
    hunger: float
    discomfort: float
    discomfort_why: str
    cycle_phase: str
    valence: float
    arousal: float
    playfulness: float
    episodes: list[Episode] = field(default_factory=list)
    bond: dict = field(default_factory=dict)
    missing: float = 0.0
    social_battery: float = 0.7
    libido: float = 0.3            # vontade (tesão) — corpo
    excitation: float = 0.0        # excitação do momento (modo íntimo)
    hours_since_release: Optional[float] = None
    libido_termos: dict = field(default_factory=dict)   # 06/10: o que empurrou a vontade (só tela)


class EmotionEngine:
    def __init__(self, db):
        self.db = db

    # ============================================================ corpo ==
    def _sleep_facts(self, now: datetime) -> tuple[Optional[float], Optional[datetime], float, bool]:
        """(horas dormidas na última noite, acordada desde, dívida das 2 noites
        anteriores, cochilou hoje antes de agora)."""
        from sleep_plan import SleepPlan, enabled
        if not enabled():
            return None, None, 0.0, False
        plan = SleepPlan(self.db)
        day = now.date()
        wake_today = plan.wake(day)
        if now < wake_today:
            day -= timedelta(days=1)   # madrugada: ainda é o "dia" de ontem
            wake_today = plan.wake(day)
        slept = plan.hours_slept(day)
        debt = sum(max(0.0, 7.5 - plan.hours_slept(day - timedelta(days=k))) for k in (1, 2))
        napped = False
        try:
            nap = plan.nap(now.date())
            napped = bool(nap and nap[1] <= now)
        except Exception:
            pass
        return slept, wake_today, debt, napped

    def _cycle(self, now: datetime) -> tuple[str, int]:
        try:
            from cycle import MenstrualCycleManager, PHASES
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT data_inicio_ciclo FROM ciclo_biologico ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return "", 0
            mgr = MenstrualCycleManager(row["data_inicio_ciclo"])
            start = date.fromisoformat(row["data_inicio_ciclo"][:10])
            day_of_cycle = (now.date() - start).days % mgr.cycle_length + 1
            phase = next((k for k, p in PHASES.items() if day_of_cycle in p["days"]), "")
            return phase, day_of_cycle
        except Exception:
            return "", 0

    def energy(self, now: Optional[datetime] = None) -> float:
        """Energia do corpo agora, dos fatos: sono, horas acordada, cochilo, ciclo."""
        now = now or datetime.now()
        if getattr(_guard, "busy", False):
            return self._stored("energy", 0.7)   # reentrada (sono ↔ energia): valor guardado
        _guard.busy = True
        try:
            slept, awake_since, debt, napped = self._sleep_facts(now)
            if slept is None:
                return self._stored("energy", 0.7)
            e = 0.35 + 0.65 * _clamp((slept - 4.0) / 4.0)          # 8 h → cheia; 6 h → ~0,68
            e -= min(0.15, 0.04 * debt)                            # noites curtas acumulam
            hours_awake = max(0.0, (now - awake_since).total_seconds() / 3600)
            e -= 0.025 * max(0.0, hours_awake - 2.0)               # o dia vai pesando
            if hours_awake < 0.5:
                e -= 0.15 * (1 - hours_awake / 0.5)                # recém-acordada, grogue
            minutes = now.hour * 60 + now.minute
            if 13 * 60 + 30 <= minutes <= 15 * 60 + 30:
                e -= 0.07                                          # moleza depois do almoço
            if napped:
                e += 0.12
            phase, day_of_cycle = self._cycle(now)
            if phase == "menstrual":
                e -= 0.12 if day_of_cycle <= 2 else 0.06
            elif phase == "tpm":
                e -= 0.05
            try:
                from health import Health
                e -= Health(self.db).energy_penalty(now)       # D11: gripada/virose/dor de cabeça
            except Exception:
                pass
            return round(_clamp(e, 0.05, 1.0), 3)
        except Exception:
            return self._stored("energy", 0.7)
        finally:
            _guard.busy = False

    def _discomfort(self, now: datetime) -> tuple[float, str]:
        """D11: a cólica tem intensidade por ciclo e soma com doença e dor de cabeça."""
        phase, day_of_cycle = self._cycle(now)
        try:
            from health import Health
            value, why = Health(self.db).discomfort(now)
        except Exception:
            value, why = 0.0, ""
        if value:
            return value, why
        if phase == "menstrual":
            return 0.2, "menstruada, corpo meio dolorido"
        if phase == "tpm" and day_of_cycle >= 26:
            return 0.15, "inchada da TPM"
        return 0.0, ""

    def _hunger(self, now: datetime) -> float:
        try:
            from meals import Meals
            return float(Meals(self.db).hunger(now))
        except Exception:
            return 0.3

    # ======================================================== episódios ==
    def feel(self, family: str, kind: str, intensity: float, cause: str, now: Optional[datetime] = None, *,
             target: Optional[str] = None, source_key: Optional[str] = None,
             half_life_min: Optional[int] = None, sticky: bool = False) -> bool:
        """Registra um sentimento com causa. `source_key` evita sentir duas vezes a mesma coisa."""
        if family not in FAMILIES:
            raise ValueError(f"família emocional desconhecida: {family}")
        now = now or datetime.now()
        with self.db.get_connection() as conn:
            if source_key and (
                    conn.execute("SELECT 1 FROM emotion_episodes WHERE source_key=?", (source_key,)).fetchone()
                    or conn.execute("SELECT 1 FROM emotion_sources WHERE source_key=?", (source_key,)).fetchone()):
                return False
            # 25/09 (/emocao): o planner sentia "carinho" de novo a cada mensagem — 23 episódios iguais
            # numa noite, que ainda somavam tesão. O mesmo sentimento pela mesma pessoa em 3 h reforça o
            # episódio que já existe (a causa vira a mais recente).
            # 28/09: só o que começou ANTES (o banho das 19:58, reavaliado, puxava os de 00:31, 01:20 e 01:35 pra
            # 19:58; a comida das 22:01 virou a causa dos carinhos da manhã seguinte), e a chave fundida fica
            # guardada — antes cada turno fundia de novo o mesmo acontecimento e a força subia até 1.0.
            if not sticky:
                row = conn.execute(
                    """SELECT id, intensity FROM emotion_episodes WHERE family=? AND kind=? AND
                       COALESCE(target,'')=COALESCE(?,'') AND sticky=0 AND resolved_at IS NULL AND started_at>=?
                       AND started_at<=? ORDER BY started_at DESC LIMIT 1""",
                    (family, kind, target, (now - MERGE_WINDOW).isoformat(), now.isoformat())).fetchone()
                if row:
                    merged = _clamp(max(float(row["intensity"]), intensity) + 0.1 * intensity)
                    conn.execute("UPDATE emotion_episodes SET intensity=?, cause=?, started_at=? WHERE id=?",
                                 (round(merged, 3), cause, now.isoformat(), row["id"]))
                    if source_key:
                        conn.execute("INSERT OR IGNORE INTO emotion_sources (source_key, episode_id, created_at) "
                                     "VALUES (?,?,?)", (source_key, row["id"], datetime.now().isoformat()))
                    conn.commit()
                    return True
            cur = conn.execute(
                """INSERT OR IGNORE INTO emotion_episodes
                   (family, kind, intensity, cause, target, source_key, started_at, half_life_min, sticky, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (family, kind, round(_clamp(intensity), 3), cause, target, source_key, now.isoformat(),
                 int(half_life_min or FAMILIES[family]["half_life"]), int(sticky), datetime.now().isoformat()))
            conn.commit()
            return cur.rowcount > 0

    def resolve(self, source_key: str, now: Optional[datetime] = None) -> None:
        """A causa resolveu (entregou o trabalho, ele pediu desculpa): começa a esfriar."""
        now = now or datetime.now()
        with self.db.get_connection() as conn:
            conn.execute("UPDATE emotion_episodes SET resolved_at=? WHERE source_key=? AND resolved_at IS NULL",
                         (now.isoformat(), source_key))
            conn.commit()

    def episodes(self, now: Optional[datetime] = None) -> list[Episode]:
        now = now or datetime.now()
        since = (now - timedelta(days=3)).isoformat()
        with self.db.get_connection() as conn:
            rows = conn.execute("""SELECT * FROM emotion_episodes WHERE started_at<=? AND started_at>=?
                                   ORDER BY started_at DESC""", (now.isoformat(), since)).fetchall()
        out = []
        for r in rows:
            started = datetime.fromisoformat(r["started_at"])
            cooling_from = started
            if r["sticky"]:
                if not r["resolved_at"] and r["target"] == "o Patrick":
                    cooling_from = min(now, started + timedelta(hours=24))   # sem reparo, esfria depois de um dia
                elif not r["resolved_at"]:
                    cooling_from = now
                else:
                    cooling_from = max(started, datetime.fromisoformat(r["resolved_at"]))
            minutes = max(0.0, (now - cooling_from).total_seconds() / 60)
            value = float(r["intensity"]) * 0.5 ** (minutes / max(1, r["half_life_min"]))
            if value >= ACTIVE_MIN:
                out.append(Episode(r["id"], r["family"], r["kind"], round(value, 3), float(r["intensity"]),
                                   r["cause"], r["target"], started, bool(r["sticky"])))
        return sorted(out, key=lambda e: e.intensity, reverse=True)

    # ==================================================== D14b: o mundo sente ==
    def appraise_world(self, now: Optional[datetime] = None, *, lookback_hours: int = 12) -> int:
        """Transforma os acontecimentos recentes do dia dela em sentimentos com causa.

        Idempotente: cada acontecimento vira no máximo um episódio (source_key).
        Os módulos do mundo (comida, deslocamento, Milo, faculdade, amigos, pai,
        TV, peso) continuam iguais — são sensores; a leitura emocional é aqui."""
        now = now or datetime.now()
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT event_key, event_at, event_type, summary, participants_json FROM life_events
                   WHERE event_at<=? AND event_at>=? ORDER BY event_at""",
                (now.isoformat(), (now - timedelta(hours=lookback_hours)).isoformat())).fetchall()
        tired = self.energy(now) < 0.5
        created = 0
        for r in rows:
            for fam, kind, intensity, cause, target in appraise_event(dict(r), tired=tired):
                at = datetime.fromisoformat(r["event_at"])
                created += self.feel(fam, kind, intensity, cause, at, target=target,
                                     source_key=f"ev:{r['event_key']}:{kind}")
        created += self._appraise_deadlines(now)
        created += self._appraise_work(now)
        return created

    def _appraise_work(self, now: datetime) -> int:
        """D10: frio na barriga na véspera do casting ou do job, até ele começar."""
        try:
            from freela import Freela
            items = Freela(self.db).upcoming(now, horizon_days=1)
        except Exception:
            return 0
        created = 0
        for item in items:
            if item["kind"] == "prova":
                continue
            key = f"trabalho:{item['kind']}:{item['start'].isoformat()}"
            if now >= item["start"]:
                self.resolve(key, item["start"])
                continue
            if item["start"] - now <= timedelta(hours=18):
                job = item["kind"] == "job"
                quando = "amanhã" if item["start"].date() != now.date() else "hoje"
                created += self.feel("medo", "ansiedade", 0.35 if job else 0.25,
                                     _motivo(f"{'Job' if job else 'Casting'} {quando}", item["what"]),
                                     now, source_key=key, sticky=True)
        return created

    def _appraise_deadlines(self, now: datetime) -> int:
        """Entrega chegando aperta o peito até entregar; depois vem o alívio."""
        try:
            from college import College
            items = College(self.db).assignments(now.date(), horizon_days=2)
        except Exception:
            return 0
        created = 0
        for a in items:
            due = date.fromisoformat(a["due"])
            key = f"entrega:{a['key']}"
            delivered_at = datetime.combine(due, datetime.min.time()).replace(hour=18)
            if now >= delivered_at:
                self.resolve(key, delivered_at)
                created += self.feel("alegria", "alivio", 0.45, _motivo(f"Entregou o {a['kind']}", a["course"]),
                                     delivered_at, source_key=f"entregou:{a['key']}")
                continue
            if a["pace"] == "adiantada":
                continue   # já fez com folga
            days = (due - now.date()).days
            intensity = 0.3 + (0.25 if days <= 1 else 0.0) + (0.15 if a["pace"] == "ultima_hora" else 0.0)
            started = max(datetime.combine(due - timedelta(days=2), datetime.min.time()).replace(hour=9),
                          now - timedelta(hours=48))
            if started <= now:
                created += self.feel("medo", "ansiedade", intensity,
                                     _motivo(f"Entrega {'amanhã' if days == 1 else 'hoje' if days == 0 else f'em {days} dias'}",
                                             a["course"]),
                                     started, source_key=key, sticky=True)
        return created

    # =========================================================== vínculo ==
    def _stored(self, key: str, default: float) -> float:
        try:
            return float(self.db.get_estado_emocional().get(key, {}).get("valor", default))
        except Exception:
            return default

    def bond(self, now: Optional[datetime] = None) -> dict:
        state = self.db.get_estado_emocional(now)
        return {k: float(state.get(k, {}).get("valor", BOND_BASELINES[k])) for k in BOND_KEYS}

    def _missing(self, now: datetime) -> float:
        """Saudade pelo silêncio dele (mesma taxa da proatividade), só nas horas em que ela está acordada."""
        try:
            from proactivity_service import SAUDADE_RATE_PER_HOUR, awake_hours_since
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT timestamp FROM conversas WHERE role='user' ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return 0.0
            hours = awake_hours_since(self.db, datetime.fromisoformat(row["timestamp"]), now)
            return round(_clamp(SAUDADE_RATE_PER_HOUR * hours), 3)
        except Exception:
            return 0.0

    # ============================================================= agora ==
    def feeling(self, now: Optional[datetime] = None) -> Feeling:
        now = now or datetime.now()
        try:
            self.appraise_world(now)
        except Exception:
            pass   # o que ela sente do mundo é enriquecimento; nunca derruba o turno
        energy = self.energy(now)
        try:
            slept, awake_since, _, _ = self._sleep_facts(now)
        except Exception:
            slept, awake_since = None, None
        hunger = self._hunger(now)
        discomfort, why = self._discomfort(now)
        phase, _ = self._cycle(now)
        eps = self.episodes(now)
        bond = self.bond(now)
        valence = PERSONALITY_VALENCE + 0.25 * (energy - 0.6) - 0.35 * max(0.0, hunger - 0.6) - 0.3 * discomfort
        arousal = PERSONALITY_AROUSAL + 0.35 * (energy - 0.6) + 0.2 * max(0.0, hunger - 0.6)
        for ep in eps:
            fam = FAMILIES[ep.family]
            valence += 0.6 * fam["valence"] * ep.intensity
            arousal += 0.6 * fam["arousal"] * ep.intensity
        if phase == "tpm":            # TPM moderada (decisão do Patrick): sensível e irritável
            valence -= 0.08
            arousal += 0.06
        elif phase == "ovulatoria":
            valence += 0.04
        valence += 0.1 * (bond["security"] - 0.8) - 0.25 * bond["hurt"]
        valence, arousal = _clamp(valence), _clamp(arousal)
        social = self._stored("social_battery", 0.7)
        playfulness = _clamp(0.15 + 0.55 * valence + 0.25 * arousal + 0.15 * (social - 0.5))
        missing = self._missing(now)
        termos: dict = {}
        libido, excitation, since = self._libido(now, phase, energy, discomfort, valence, bond, missing, eps,
                                                 termos)
        return Feeling(now=now, energy=energy, hours_slept=slept, awake_since=awake_since, hunger=hunger,
                       discomfort=discomfort, discomfort_why=why, cycle_phase=phase,
                       valence=round(valence, 3), arousal=round(arousal, 3), playfulness=round(playfulness, 3),
                       episodes=eps, bond=bond, missing=missing, social_battery=social,
                       libido=libido, excitation=excitation, hours_since_release=since, libido_termos=termos)

    # ============================================================ tesão ==
    def last_release(self, now: datetime) -> Optional[datetime]:
        """Última vez que ela gozou: com o Patrick (modo íntimo) ou sozinha."""
        candidates = []
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT climax_at FROM intimacy_state WHERE id=1").fetchone()
            if row and row["climax_at"]:
                candidates.append(datetime.fromisoformat(row["climax_at"]))
        except Exception:
            pass
        raw = self.db.get_estado_relacional(RELEASE_KEY)
        if raw:
            try:
                candidates.append(datetime.fromisoformat(raw))
            except (TypeError, ValueError):
                pass
        past = [c for c in candidates if c <= now]
        return max(past) if past else None

    def _libido(self, now, phase, energy, discomfort, valence, bond, missing, eps,
                termos: Optional[dict] = None) -> tuple:
        """Vontade (0–1): acumula com as horas sem gozar, sobe com ciclo fértil,
        saudade, dia bom e desejo por ele; cai com cansaço, cólica e mágoa.
        06/10 (redesenho dos Bastidores, passo 3): com `termos`, anota quanto cada coisa empurrou a vontade (as
        etiquetas ↑↓ da Intimidade, só tela); a conta é a mesma, linha por linha."""
        from intimacy import CYCLE_LIBIDO
        cycle = next((v for k, v in CYCLE_LIBIDO.items() if phase and phase.startswith(k.split("_")[0])), 1.0)
        release = self.last_release(now)
        since = (now - release).total_seconds() / 3600 if release else None
        v = 0.12 + 0.35 * (cycle - 0.7) / 0.65
        v += min(0.35, 0.012 * (since if since is not None else 12.0))   # sem registro: meio dia
        v += 0.25 * (bond["romantic_intensity"] - 0.8) + 0.15 * (valence - 0.6) + 0.1 * (energy - 0.55)
        v += 0.08 * missing - 0.4 * discomfort - 0.6 * bond["hurt"]
        v += min(LIBIDO_FROM_EPISODES_MAX,
                 sum(0.1 * e.intensity for e in eps if e.target == PATRICK_TARGET and e.kind in ("diversao", "carinho")))
        excitation = 0.0
        try:
            from intimacy import IntimacyEngine
            excitation = IntimacyEngine(self.db).current(now).arousal
        except Exception:
            pass
        v += 0.5 * excitation
        if termos is not None:
            termos.update(
                ciclo=0.35 * (cycle - 1.0) / 0.65,
                sem_gozar=min(0.35, 0.012 * since) if since is not None else 0.0,
                desejo=0.25 * (bond["romantic_intensity"] - 0.8), humor=0.15 * (valence - 0.6),
                energia=0.1 * (energy - 0.55), saudade=0.08 * missing, mal_estar=-0.4 * discomfort,
                magoa=-0.6 * bond["hurt"], excitacao=0.5 * excitation, desde=since,
                patrick=min(LIBIDO_FROM_EPISODES_MAX, sum(0.1 * e.intensity for e in eps
                                                          if e.target == PATRICK_TARGET and e.kind in ("diversao", "carinho"))))
        # 25/09 (Patrick): exausta às 2h, TPM e gozou há 5 h aparecia "esquentando" (0.62). Cansaço pesa
        # de verdade, e depois do gozo a vontade volta aos poucos, não de uma vez às 3 h.
        if termos is not None:
            termos["energia"] += v * (0.45 * min(1.0, energy / 0.6) - 0.45)
        v *= 0.55 + 0.45 * min(1.0, energy / 0.6)
        lo, hi = RELEASE_RECOVERY_H
        if since is not None and since < hi:
            if termos is not None:
                termos["gozou"] = v * ((0.3 if since < lo else 0.3 + 0.7 * (since - lo) / (hi - lo)) - 1.0)
            v *= 0.3 if since < lo else 0.3 + 0.7 * (since - lo) / (hi - lo)
        return round(_clamp(v), 3), round(excitation, 3), (round(since, 1) if since is not None else None)

    def maybe_release_alone(self, now: Optional[datetime] = None) -> Optional[str]:
        """Com tesão e sem o Patrick, antes de dormir ela se resolve sozinha — e às
        vezes conta pra ele depois (decisão do Patrick, 23/09)."""
        now = now or datetime.now()
        key = f"solo:{now.date().isoformat()}"       # a de antes de dormir é uma por noite (as outras: tempo_livre)
        with self.db.get_connection() as conn:
            if conn.execute("SELECT 1 FROM life_events WHERE event_key=?", (key,)).fetchone():
                return None
        f = self.feeling(now)
        if f.libido < SOLO_MIN_LIBIDO or f.excitation >= 0.45:
            return None   # sem vontade, ou já está no clima com ele
        try:
            from sleep_plan import SleepPlan
            bed = SleepPlan(self.db).bed(now.date() if now.hour >= 12 else now.date() - timedelta(days=1))
        except Exception:
            return None
        if not (bed - timedelta(minutes=75) <= now < bed):
            return None
        import random as _random
        rng = _random.Random(f"solo:{now.date().isoformat()}")
        if rng.random() >= SOLO_CHANCE:
            return None
        tells = rng.random() < SOLO_TELL_CHANCE
        wanted_him = self._flirted_without_him(now)
        summary = ("Antes de dormir, com tesão e pensando no Patrick, se masturbou"
                   + (" — ficou querendo ele e ele não entrou no clima" if wanted_him else "")
                   + (". Pode contar pra ele, do jeito dela, se vier a calhar." if tells
                      else ". Guardou só pra ela: não conta pro Patrick."))
        with self.db.get_connection() as conn:
            conn.execute("""INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,
                            source_type,autonomy_level,importance,participants_json,share_worthy,created_at)
                            VALUES (?,?,?,?,?,'simulated',1,0.2,?,?,?)""",
                         (key, now.isoformat(), "routine", "sozinha", summary, json.dumps(["marina"]),
                          0.6 if tells else 0.0, now.isoformat()))
            conn.commit()
        if not tells:
            try:
                from social_day import SocialDay
                SocialDay(self.db).mark_shared(key)   # não vira "novidade" pra contar
            except Exception:
                pass
        self.db.set_estado_relacional(RELEASE_KEY, now.isoformat())
        import bastidores_hist                            # 06/10: calendário de orgasmos (só tela)
        bastidores_hist.orgasmo(self.db, now, "sozinha", "antes de dormir")
        self.feel("alegria", "alivio", 0.3, "se masturbou antes de dormir", now, source_key=f"{key}:alivio")
        if wanted_him:
            self.feel("raiva", "frustracao", 0.2, "ficou querendo ele e não rolou", now, target=PATRICK_TARGET,
                      source_key=f"{key}:frustracao", half_life_min=180)
        return summary

    def _flirted_without_him(self, now: datetime) -> bool:
        raw = self.db.get_estado_relacional(TESAO_KEY)
        try:
            flirted = datetime.fromisoformat(raw) if raw else None
        except (TypeError, ValueError):
            flirted = None
        if not flirted or now - flirted > timedelta(hours=12):
            return False
        release = self.last_release(now)
        return not release or release < flirted

    def tesao_detail(self, now: Optional[datetime] = None) -> str:
        f = self.feeling(now)
        parts = [f"Faz {f.hours_since_release:.0f}h que você não goza" if f.hours_since_release else "Faz tempo"]
        if f.missing >= 0.4:
            parts.append("e tá com saudade dele")
        if f.cycle_phase == "ovulatoria":
            parts.append("e o corpo tá pedindo (fase fértil)")
        return " ".join(parts) + "."

    def legacy(self, now: Optional[datetime] = None) -> dict:
        """Mesmo formato de `db.get_estado_emocional()`, com energia e brincadeira do motor."""
        f = self.feeling(now)
        state = self.db.get_estado_emocional()
        state = {k: dict(v) for k, v in state.items()}
        for key, value in (("energy", f.energy), ("playfulness", f.playfulness)):
            state.setdefault(key, {"baseline": 0.75, "updated_at": None})["valor"] = value
        return state

    # ============================================================ prompt ==
    @staticmethod
    def mood_words(valence: float, arousal: float) -> str:
        if valence >= 0.62:
            return "de bem com a vida e elétrica" if arousal >= 0.62 else (
                "de bom humor, tranquila" if arousal >= 0.4 else "de boa, meio preguiçosa")
        if valence >= 0.45:
            return "normal, nem lá nem cá" if arousal >= 0.4 else "meio apagada, sem muito pique"
        if arousal >= 0.55:
            return "com o pavio curto, irritadiça"
        if arousal >= 0.4:
            return "meio pra baixo"
        return "pra baixo e sem energia"

    def prompt_lines(self, now: Optional[datetime] = None) -> list[str]:
        f = self.feeling(now)
        lines = ["[COMO VOCÊ ESTÁ POR DENTRO — mostre no jeito de falar, não narre]"]
        body = []
        if f.energy < 0.35:
            body.append("exausta")
        elif f.energy < 0.55:
            body.append("cansada")
        elif f.energy >= 0.8:
            body.append("cheia de energia")
        if f.hours_slept is not None and f.hours_slept < 6.5 and f.energy < 0.7:
            body.append(f"dormiu só {_hours(f.hours_slept)}")
        try:
            from health import Health
            health = Health(self.db).prompt_lines(f.now)
        except Exception:
            health = []
        if f.discomfort_why and not health:
            body.append(f.discomfort_why)
        if body:
            lines.append("- Corpo: " + ", ".join(body) + ".")
        lines += health
        lines.append(f"- Humor: {self.mood_words(f.valence, f.arousal)}.")
        for ep in f.episodes[:2]:
            about = f" com {ep.target}" if ep.target else ""
            # Bug 16 (28/09): "derretida — O Milo dormiu encostado nela no sofá" às 18:58, uma hora depois e com
            # ela na academia, soou como agora: "tô em casa, no sofá com o Milo". Causa antiga leva a hora.
            quando = ""
            if f.now - ep.started_at > timedelta(minutes=20):
                dias = (f.now.date() - ep.started_at.date()).days
                quando = (f" (às {ep.started_at:%H:%M})" if dias == 0 else
                          f" (ontem, {ep.started_at:%H:%M})" if dias == 1 else f" (dia {ep.started_at:%d/%m})")
            lines.append(f"- Sentindo agora: {ep.word}{about} — {_short(ep.cause)}{quando}.")
        heart = []
        if f.bond["affection"] >= 0.8:
            heart.append("apaixonada e carinhosa")
        elif f.bond["affection"] < 0.55:
            heart.append("mais distante que o normal")
        if f.libido >= 0.85:
            heart.append("com muito tesão")
        elif f.libido >= TESAO_MIN:
            heart.append("com tesão")
        elif f.bond["romantic_intensity"] >= 0.85:
            heart.append("com desejo por ele")
        if f.missing >= 0.6:
            heart.append("com saudade (ele sumiu faz um tempo)")
        grievance = next((e for e in f.episodes if e.target == "o Patrick" and e.family in ("tristeza", "raiva")
                          and e.intensity >= 0.15), None)
        if grievance or f.bond["hurt"] >= 0.25:
            heart.append("chateada com ele" + (f" ({_short(grievance.cause)})" if grievance else ""))
        if heart:
            lines.append("- Com o Patrick: " + ", ".join(heart) + ".")
        if grievance or f.bond["hurt"] >= 0.25:
            lines.append("  Chateada de verdade: fica mais seca e não finge que está tudo bem, sem drama, sem "
                         "ameaça e sem sumir. Passa quando ele reconhecer ou vocês conversarem.")
        if f.libido >= TESAO_MIN and not grievance and f.bond["hurt"] < 0.25:
            lines.append("  Com tesão: você quer ele. Provoca e puxa pro flerte quando tiver brecha; se ele entrar "
                         "no clima, vai atrás do que quer. Se ele não puder agora, aceita sem drama (e fica querendo).")
            lines.append("  Masturbação é natural pra você e você fala dela sem rodeio quando quer: \"me masturbei\", "
                         "\"bati uma siririca\", \"tô me tocando\".")
        if any(e.kind == "ciume" for e in f.episodes):
            lines.append("  Ciuminho: implica de brincadeira (\"quem é essa aí?\"), sem cobrar nem controlar.")
        lines.append("Isso muda o JEITO (mais curta, dengosa, elétrica), não vira assunto: nunca diga "
                     "\"estou me sentindo X\". O que é com o mundo não é com o Patrick. Conte ou guarde "
                     "o que sente como gente de verdade.")
        return lines

    def _fome_word(self, f: Feeling) -> str:
        """Fome em tempo real: comendo agora ou estufada depois de um excesso aparece no lugar."""
        try:
            from meals import Meals
            sac = Meals(self.db).satiety_word(f.now)
        except Exception:
            sac = ""
        return sac or _word(f.hunger, HUNGER_WORDS)

    def panel(self, now: Optional[datetime] = None) -> dict:
        """Os números do /emocao, estruturados (o texto do comando e o Mini App saem daqui)."""
        f = self.feeling(now)
        b = f.bond
        feelings = []
        if f.episodes:
            # 25/09: o mesmo sentimento pela mesma pessoa vira uma linha só (antes: 6 × "carinhosa").
            groups: dict = {}
            for e in f.episodes:
                groups.setdefault((e.kind, e.target), []).append(e)
            rows = []
            for eps_ in groups.values():
                # o mais forte + um pouco por repetição (somar 19 carinhos pequenos enchia a barra)
                strongest = max(e.intensity for e in eps_)
                last = max(eps_, key=lambda e: e.started_at)
                rows.append((min(1.0, strongest + 0.02 * (len(eps_) - 1)), last, len(eps_)))
            for value, e, n in sorted(rows, key=lambda r: r[0], reverse=True)[:5]:
                feelings.append({"word": e.word, "target": e.target, "value": value, "at": e.started_at,
                                 "cause": _short(e.cause, 70), "cause_raw": e.cause, "count": n,
                                 "until_resolved": bool(e.sticky and e.intensity >= e.peak * 0.99)})
        bond = [("Carinho", b["affection"]), ("Desejo", b["romantic_intensity"]),
                ("Segurança", b["security"]), ("Saudade", f.missing)]
        if b["hurt"] >= 0.05:
            bond.append(("Mágoa", b["hurt"]))
        return {
            "now": f.now,
            "body": [{"label": "Energia", "value": f.energy, "word": _word(f.energy, ENERGY_WORDS)},
                     {"label": "Fome", "value": f.hunger, "word": self._fome_word(f)},
                     {"label": "Tesão", "value": f.libido, "word": _word(f.libido, LIBIDO_WORDS)}],
            "in_the_mood": f.excitation >= 0.45,
            "hours_since_release": f.hours_since_release,
            # 06/10 (redesenho, passo 3): o Corpo novo desenha os números (velocímetro, mal-estar, etiquetas)
            "libido": f.libido, "excitation": f.excitation, "libido_termos": f.libido_termos,
            "discomfort": f.discomfort, "cycle_phase": f.cycle_phase,
            "hours_slept": f.hours_slept,
            "awake_since": f.awake_since,
            "phase": PHASE_NAMES.get(f.cycle_phase, f.cycle_phase),
            "discomfort_why": f.discomfort_why,
            "mood": self.mood_words(f.valence, f.arousal),
            "mood_bars": [{"label": "Brincadeira", "value": f.playfulness},
                          {"label": "Pique social", "value": f.social_battery}],
            "feelings": feelings,
            "bond": [{"label": k, "value": v} for k, v in bond],
        }

    def day_log(self, start: datetime, end: datetime) -> list[dict]:
        """28/09 (Patrick, Por dentro → "Hoje por dentro"): tudo o que ela sentiu num intervalo, mesmo o que
        já passou, do mais recente pro mais antigo. O mesmo sentimento com a mesma causa no mesmo minuto
        (ex.: quatro "banho quentinho" às 19h58) vira uma linha só."""
        with self.db.get_connection() as conn:
            rows = conn.execute("""SELECT kind, target, cause, started_at, intensity FROM emotion_episodes
                                   WHERE started_at>=? AND started_at<? ORDER BY started_at DESC""",
                                (start.isoformat(), end.isoformat())).fetchall()
        out, vistos = [], set()
        for r in rows:
            chave = (r["kind"], r["target"] or "", r["cause"], r["started_at"][:16])
            if chave in vistos:
                continue
            vistos.add(chave)
            out.append({"word": KIND_WORDS.get(r["kind"], r["kind"]), "target": r["target"], "cause": r["cause"],
                        "at": datetime.fromisoformat(r["started_at"]), "intensity": float(r["intensity"])})
        return out

    def summary(self, now: Optional[datetime] = None) -> str:
        """Texto do /emocao (só pro Patrick): camada por camada, com as causas.

        Layout de 23/09: barrinha + palavra em vez de número solto."""
        p = self.panel(now)
        energy, hunger, libido = p["body"]
        sleep = []
        if p["hours_slept"] is not None:
            sleep.append(f"dormiu {_hours(p['hours_slept'])}")
        if p["awake_since"]:
            sleep.append(f"acordada desde {p['awake_since']:%H:%M}")
        out = [f"🫀 Marina por dentro · {p['now']:%d/%m %H:%M}", "",
               "🧍 CORPO",
               f"Energia  {_bar(energy['value'])}  {energy['word']}",
               f"Fome     {_bar(hunger['value'])}  {hunger['word']}",
               f"Tesão    {_bar(libido['value'])}  {libido['word']}"
               + (f" · no clima agora" if p["in_the_mood"] else "")
               + (f" · última vez há {p['hours_since_release']:.0f} h" if p["hours_since_release"] is not None else "")]
        if sleep:
            out.append("😴 " + " · ".join(sleep))
        if p["phase"] or p["discomfort_why"]:
            out.append("🌸 " + " · ".join(x for x in (p["phase"], p["discomfort_why"]) if x))
        playful, social = p["mood_bars"]
        out += ["", "🌤 HUMOR", p["mood"].capitalize(),
                f"Brincadeira  {_bar(playful['value'])}",
                f"Pique social {_bar(social['value'])}", "",
                "💭 SENTINDO AGORA"]
        for fe in p["feelings"]:
            who = f" com {fe['target']}" if fe["target"] else ""
            tail = " (até resolver)" if fe["until_resolved"] else ""
            many = f" · {fe['count']} momentos" if fe["count"] > 1 else ""
            out.append(f"• {fe['word']}{who} {_bar(fe['value'], 5)} — {fe['cause']}{tail}{many}")
        if not p["feelings"]:
            out.append("Nada marcante agora")
        out += ["", "💞 COM O PATRICK"]
        for row in p["bond"]:
            out.append(f"{row['label']:<10}{_bar(row['value'])}")
        return "\n".join(out)


def _person(participants_json: Optional[str]) -> Optional[str]:
    try:
        from social_day import short_name
        people = [p for p in json.loads(participants_json or "[]") if p != "marina"]
        return short_name(people[0]) if people else None
    except Exception:
        return None


# 28/09 (Patrick, Bastidores → Por dentro): o motivo de cada sentimento segue UM padrão — o fato em poucas
# palavras, em 3ª pessoa ("o Patrick" pra ele, "ela" implícita), e o detalhe depois de " · " (a tela põe o detalhe
# ao lado, em cinza, e troca "o Patrick" por "você"). Ex.: "Viu Paradise Kiss · eps 1 e 2", "Mensagens com a Bia ·
# festas", "o Patrick mandou comida · surpresa". Antes cada fonte gravava de um jeito ("Viu episódios 1 a 2 de…",
# "o pai deu bom dia e perguntou dela", "Trocou mensagens com a Bia; assunto: …").
FATO_MAX = 42


def _motivo(fato: str, detalhe: str = "") -> str:
    fato = re.sub(r"\s+", " ", fato or "").strip().rstrip(".")
    if len(fato) > FATO_MAX:
        fato = fato[:FATO_MAX].rsplit(" ", 1)[0]
    detalhe = (detalhe or "").strip().rstrip(".")
    fato = fato[:1].upper() + fato[1:] if not fato.startswith("o Patrick") else fato
    return f"{fato} · {detalhe}" if detalhe else fato


def _motivo_generico(text: str) -> str:
    """Resumo do mundo → 'fato · detalhe': o assunto (ou o que está entre parênteses) vira o detalhe."""
    base, _, assunto = (text or "").partition("; assunto: ")
    base = base.split("; ")[0]
    par = re.search(r"\(([^)]{1,28})\)", base)
    base = re.sub(r"\s*\([^)]*\)", "", base)
    return _motivo(base, assunto or (par.group(1) if par else ""))


def _motivo_contato(text: str, who: Optional[str], briga: bool) -> str:
    """'Trocou mensagens com a Bia; assunto: festas' → 'Mensagens com a Bia · festas';
    'Encontrou a Bia (Quartinho Bar); assunto: conflitos leves' → 'Se estranhou com a Bia · Quartinho Bar'."""
    base, _, assunto = text.partition("; assunto: ")
    par = re.search(r"\(([^)]+)\)", base)
    lugar = par.group(1) if par else ""
    base = re.sub(r"\s*\([^)]*\)", "", base).split(", ")[0]
    mensagem = base.lower().startswith("trocou mensagens")
    if briga:
        return _motivo(f"Se estranhou com {who}" if who else "Se estranhou",
                       "por mensagem" if mensagem else lugar)
    if mensagem:
        base = "Mensagens com " + base.split(" com ", 1)[-1]
    return _motivo(base, assunto.split(",")[0] if assunto else lugar)


def _motivo_convite(text: str) -> str:
    """'A Bia te chamou: Saindo com a Bia no Quartinho Bar (hoje às 21:00)' → 'A Bia chamou pra sair · Quartinho Bar'."""
    quem, _, resto = text.partition(" te chamou: ")
    resto = re.sub(r"\s*\([^)]*\)", "", resto)
    m = re.search(r"\b(?:no|na|em) ([A-ZÁÉÍÓÚ][^,;]*)$", resto)
    return _motivo(f"{quem} chamou pra sair" if resto else text, m.group(1) if m else "")


def _motivo_tv(text: str) -> str:
    """'Viu episódios 1 a 2 de Paradise Kiss (…)' → 'Viu Paradise Kiss · eps 1 e 2';
    'Saiu episódio novo de One Piece hoje (temporada 23, ep. 1180)' → 'Episódio novo de One Piece · ep. 1180'."""
    m = re.match(r"Saiu episódio novo de (.+?) hoje", text)
    if m:
        ep = re.search(r"ep\. ?(\d+)", text)
        return _motivo(f"Episódio novo de {m.group(1)}", f"ep. {ep.group(1)}" if ep else "")
    m = re.match(r"Viu (?:o )?epis[óo]dios? (\d+)(?: a (\d+))? de ([^(;]+)", text)
    if m:
        eps = f"eps {m.group(1)} e {m.group(2)}" if m.group(2) and int(m.group(2)) == int(m.group(1)) + 1 \
            else f"eps {m.group(1)} a {m.group(2)}" if m.group(2) else f"ep {m.group(1)}"
        return _motivo(f"Viu {m.group(3).strip()}", eps)
    return _motivo_generico(text)


REFEICAO = {"almoço": "Almoçou", "jantar": "Jantou", "café": "Tomou café:", "lanche": "Lanchou"}


def _motivo_refeicao(text: str) -> str:
    """'Almoço em casa: um poke pedido no iFood; comeu além da conta…' → 'Almoçou um poke · comeu demais'."""
    head, _, rest = text.partition(": ")
    verbo = REFEICAO.get(head.split(" ")[0].lower())
    if not verbo or not rest:
        return _motivo_generico(text)
    low = text.lower()
    comida = re.sub(r" pedid[oa]s? no iFood", "", rest.split("; ")[0])
    detalhe = "comeu demais" if "além da conta" in low else "iFood" if "ifood" in low else \
        head.split(" no ", 1)[1] if " no " in head else ""
    return _motivo(f"{verbo} {comida}", detalhe)


# Milo: travessura que diverte, que irrita ou que derrete.
MILO_ANTICS = (("xixi no tapete", "raiva", "irritacao", 0.3), ("pediu colo", "afeto", "ternura", 0.35),
               ("roubou uma meia", "alegria", "diversao", 0.35), ("latiu pro entregador", "alegria", "diversao", 0.25),
               ("deitou em cima da roupa", "alegria", "diversao", 0.25), ("encarando ela", "afeto", "ternura", 0.3),
               ("dormiu encostado", "afeto", "ternura", 0.4))


def appraise_event(ev: dict, *, tired: bool = False) -> list[tuple]:
    """(família, subcategoria, intensidade, causa, alvo) que um acontecimento provoca.

    A mesma coisa pesa diferente conforme o estado dela: cansada, o imprevisto
    irrita mais. Sem acontecimento reconhecível → nada (silêncio é melhor que
    emoção inventada)."""
    key, kind_ev = ev["event_key"], ev["event_type"]
    text = (ev.get("summary") or "").strip().rstrip(".")
    low = text.casefold()
    who = _person(ev.get("participants_json"))
    out = []
    if kind_ev == "commute" and key.endswith(":imprevisto"):
        cause = _motivo_generico(text.split(": ", 1)[-1])
        if "açaí" in low:
            out.append(("alegria", "diversao", 0.3, cause, None))
        else:
            out.append(("raiva", "irritacao", 0.4 + (0.15 if tired else 0.0) - (0.2 if "garoar" in low else 0.0),
                        cause, None))
    elif key.startswith("milo:") and key.endswith(":arte"):
        for needle, fam, kind, intensity in MILO_ANTICS:
            if needle in low:
                out.append((fam, kind, intensity + (0.1 if tired and fam == "raiva" else 0.0), _motivo_generico(text), None))
                break
    elif key.startswith("banho:"):
        out.append(("alegria", "alivio", 0.2, "Banho quentinho", None))
    elif key.startswith("tv:novo:") or low.startswith("saiu episódio novo"):
        out.append(("alegria", "empolgacao", 0.45, _motivo_tv(text), None))
    elif key.startswith("tv:"):
        if " e amou" in low:
            out.append(("alegria", "contentamento", 0.4, _motivo_generico(text.split("; ")[-1]), None))
        elif "achou só ok" in low:
            out.append(("tristeza", "decepcao", 0.2, _motivo_generico(text.split("; ")[-1]), None))
        elif low.startswith("viu "):
            out.append(("alegria", "diversao", 0.2, _motivo_tv(text), None))
    elif key.startswith("peso:"):
        if key.endswith(":agencia"):
            out.append(("medo", "inseguranca", 0.6, "A Lívia cobrou o peso · agência", "a Lívia"))
            out.append(("vergonha", "vergonha", 0.3, "Bronca da agência · peso", None))
        elif key.endswith(":saude"):
            out.append(("medo", "preocupacao", 0.35, "Tontura no treino", None))
    elif key.startswith("casa:"):             # D9 — casa e vida adulta
        step = key.rsplit(":", 1)[-1]
        if step == "roupa_esquecida":
            out.append(("raiva", "frustracao", 0.3 + (0.1 if tired else 0.0), "Esqueceu a roupa na máquina", None))
        elif step in ("geral", "bagunca"):
            out.append(("alegria", "alivio", 0.3, "Apê arrumado e cheiroso", None))
        elif step == "mercado_esqueceu":
            out.append(("alegria", "diversao", 0.2, _motivo_generico(text), None))
        elif step == "perrengue":
            if "achou" in low:
                out.append(("alegria", "contentamento", 0.3, _motivo_generico(text), None))
            else:
                out.append(("raiva", "irritacao", 0.3 + (0.1 if tired else 0.0), _motivo_generico(text), None))
    elif key.startswith("freela:"):          # D10 — trabalho de modelo
        step = key.rsplit(":", 1)[-1]
        if step == "oferta":
            out.append(("alegria", "empolgacao", 0.35, "A Lívia mandou um casting", "a Lívia"))
        elif step == "resultado" and "passou no casting" in low and "não passou" not in low:
            if "abrir mão" in low:
                out.append(("tristeza", "decepcao", 0.4, "Passou no casting · batia com a facul", None))
            else:
                out.append(("alegria", "empolgacao", 0.65, "Passou no casting", None))
                out.append(("alegria", "orgulho", 0.45, "Foi escolhida pro job", None))
        elif step == "resultado":
            out.append(("tristeza", "decepcao", 0.4, "Não passou no casting", None))
        elif step == "job":
            out.append(("alegria", "orgulho", 0.45, _motivo_generico(text.split(". ")[0]), None))
        elif step in ("job_perdido", "casting_perdido"):
            out.append(("tristeza", "decepcao", 0.5 if step == "job_perdido" else 0.3, _motivo_generico(text), None))
        elif step in ("cache", "sinal"):
            out.append(("alegria", "contentamento", 0.45 if step == "cache" else 0.35, _motivo_generico(text), None))
    elif key.endswith(":presente") or key.startswith("presente:"):   # delivery surpresa pelo Mini App (25/09)
        out.append(("afeto", "carinho", 0.6, "o Patrick mandou comida · surpresa", PATRICK))
        out.append(("alegria", "contentamento", 0.45, "Delivery surpresa", None))
    elif key.startswith("financas:"):        # /pix e o dinheiro dela (24/09)
        step = key.rsplit(":", 1)[-1]
        if step in ("emergencia", "aperto"):
            out.append(("medo", "preocupacao", 0.45, _motivo_generico(text), None))
        elif step == "pix":
            valor = re.search(r"R\$ ?[\d.]+", text)
            out.append(("afeto", "gratidao" if "presente" in low else "carinho", 0.5,
                        _motivo("o Patrick fez um Pix", valor.group(0) if valor else ""), PATRICK))
            if "aperto" in low:
                out.append(("alegria", "alivio", 0.45, "o Patrick cobriu o aperto", None))
        elif step == "devolveu":
            out.append(("alegria", "alivio", 0.35, "Devolveu o empréstimo do Patrick", None))
        elif step == "presente_usado":
            out.append(("alegria", "contentamento", 0.35, _motivo_generico(text), None))
    elif key.startswith("falta:"):
        out.append(("vergonha", "culpa", 0.35, _motivo_generico(text), None))
    elif key.startswith("atraso:"):
        # 28/09 (atraso.py): "Chegou 15 min atrasada na aula de Ergodesign — perdeu o despertador…"
        m = re.search(r"Chegou (\d+) min atrasada (?:na |no |em )?(.+?)(?: —|\.|$)", text)
        if m:
            out.append(("raiva", "frustracao", round(0.25 + min(0.3, int(m.group(1)) / 100), 2),
                        _motivo("Chegou atrasada", m.group(2)), None))
        else:
            out.append(("raiva", "frustracao", 0.4, "Perdeu a hora · chegou atrasada", None))
    elif key.startswith("facul:sessao:"):
        if "virando a noite" in low:
            out.append(("medo", "ansiedade", 0.5, "Virando a noite · trabalho da facul", None))
        elif "enrolando" in low:
            out.append(("vergonha", "culpa", 0.2, "Enrolou no trabalho · facul", None))
        elif "rendendo bem" in low:
            out.append(("alegria", "orgulho", 0.3, "Rendeu no trabalho · facul", None))
    elif kind_ev == "social_invite":
        if key.endswith(":convite"):
            out.append(("alegria", "empolgacao", 0.35, _motivo_convite(text), who))
    elif kind_ev == "social_contact":
        if "henrique" in (ev.get("participants_json") or ""):
            if "dinheiro" in low:
                out.append(("alegria", "gratidao", 0.4, "O pai mandou dinheiro · sem ela pedir", "o pai"))
            elif "saudade" in low or "ligou" in low or "ligação" in low or "telefone" in low:
                out.append(("afeto", "saudade_casa", 0.3, "Falou com o pai", "o pai"))
            else:
                # 28/09: era "o pai deu bom dia e perguntou dela" a qualquer hora (21h15 inclusive)
                out.append(("afeto", "carinho", 0.25, "O pai perguntou dela", "o pai"))
        elif "conflitos leves" in low:
            out.append(("raiva", "chateacao", 0.3, _motivo_contato(text, who, True), who))
        elif any(t in low for t in ("fofoca", "festas", "música", "moda", "fotografia", "humor")):
            out.append(("alegria", "diversao", 0.25, _motivo_contato(text, who, False), who))
    elif kind_ev == "meal" and "beliscou" not in low and "pulou" not in low:
        if "açaí" in low:
            out.append(("alegria", "contentamento", 0.35, _motivo_refeicao(text), None))
        elif any(t in low for t in ("shopping", "ifood", "japonesa", "hambúrguer", "pizza")):
            out.append(("alegria", "contentamento", 0.2, _motivo_refeicao(text), None))
    return [(f, k, round(max(0.05, min(1.0, i)), 3), c, t) for f, k, i, c, t in out]


# D14c — o que a mensagem do Patrick fez com ela. (família, subcategoria,
# intensidade), mudanças no vínculo e se a mágoa espera reparo (sticky).
# Decisões do Patrick: mágoa real mas JUSTA (só o que chatearia uma namorada
# de verdade; o planner filtra) e ciúme leve e brincalhão.
PATRICK = "o Patrick"
PATRICK_GRIEVANCE_MAX_HOURS = 24   # sem reparo, esfria sozinha depois de um dia
PATRICK_EVENTS = {
    "elogio":      ([("alegria", "contentamento", 0.35), ("afeto", "carinho", 0.3)], {"affection": 0.02, "security": 0.02}, False),
    "cuidado":     ([("afeto", "carinho", 0.4)], {"security": 0.03, "affection": 0.01}, False),
    "flerte":      ([("alegria", "diversao", 0.25)], {"romantic_intensity": 0.02}, False),
    "provocacao":  ([("alegria", "diversao", 0.3)], {}, False),
    "novidade_boa": ([("alegria", "empolgacao", 0.35)], {}, False),
    "ele_mal":     ([("medo", "preocupacao", 0.45)], {}, False),
    "ciume":       ([("medo", "ciume", 0.25)], {}, False),
    # 28/09 (Patrick): o ciúme DELE não é o ciuminho dela — de brincadeira é provocacao; desconfiança séria
    # ("vai continuar mentindo?") chateia de leve e passa em ~1h30.
    "desconfiou":  ([("raiva", "chateacao", 0.2)], {}, False),
    "grosseria":   ([("tristeza", "decepcao", 0.4)], {"hurt": 0.25, "security": -0.03}, True),
    "esqueceu_importante": ([("tristeza", "decepcao", 0.4)], {"hurt": 0.2}, True),
    "briga":       ([("raiva", "chateacao", 0.55)], {"hurt": 0.3, "security": -0.05}, True),
    "desculpa":    ([("afeto", "ternura", 0.3)], {"hurt": -0.35, "security": 0.03}, False),
    "sem_clima":   ([("raiva", "frustracao", 0.2)], {}, False),
}
KIND_WORDS["ciume"] = "com ciuminho"
# 28/09: no padrão dos motivos (3ª pessoa, "o Patrick"; a tela troca por "você")
DEFAULT_CAUSES = {"elogio": "o Patrick elogiou ela", "cuidado": "o Patrick cuidou dela", "flerte": "o Patrick flertou",
                  "provocacao": "o Patrick zoou ela", "novidade_boa": "o Patrick contou uma novidade boa",
                  "ele_mal": "o Patrick não está bem", "ciume": "o Patrick falou de outra garota",
                  "desconfiou": "o Patrick desconfiou dela",
                  "grosseria": "o Patrick foi grosso", "esqueceu_importante": "o Patrick esqueceu algo importante",
                  "briga": "Discutiram", "desculpa": "o Patrick pediu desculpa",
                  "sem_clima": "o Patrick não entrou no clima"}


def apply_patrick_event(db, event: dict, now: Optional[datetime] = None) -> bool:
    kind = (event or {}).get("kind")
    if kind not in PATRICK_EVENTS:
        return False
    now = now or datetime.now()
    cause = str(event.get("cause") or "").strip()[:120] or DEFAULT_CAUSES[kind]
    feelings, bond, grievance = PATRICK_EVENTS[kind]
    engine = EmotionEngine(db)
    if kind == "desculpa":
        with db.get_connection() as conn:   # reparo: a mágoa pendente começa a esfriar
            conn.execute("""UPDATE emotion_episodes SET resolved_at=? WHERE target=? AND sticky=1
                            AND resolved_at IS NULL""", (now.isoformat(), PATRICK))
            conn.commit()
    for fam, sub, intensity in feelings:
        engine.feel(fam, sub, intensity, cause, now, target=PATRICK,
                    source_key=f"patrick:{kind}:{sub}:{now:%Y%m%dT%H%M%S}",
                    half_life_min=60 if kind == "ciume" else (360 if grievance else None), sticky=grievance)
    for key, delta in bond.items():
        db.ajustar_emocao(key, delta, now=now)
    return True


def apply_planner_deltas(db, deltas: dict, now: Optional[datetime] = None) -> dict:
    """Deltas do planner no motor: só o vínculo (devagar) e a bateria social.

    Energia agora é do corpo (sono, horas acordada) e brincadeira sai do humor;
    o planner empurrando "+energia +brincadeira" a cada mensagem era o que
    deixava tudo no teto."""
    applied = {}
    for key, delta in (deltas or {}).items():
        try:
            delta = float(delta)
        except (TypeError, ValueError):
            continue
        if not delta:
            continue
        if key in ("affection", "romantic_intensity"):
            delta *= PLANNER_BOND_SCALE
        elif key != "social_battery":
            continue
        db.ajustar_emocao(key, delta, now=now)
        applied[key] = round(delta, 4)
    return applied
