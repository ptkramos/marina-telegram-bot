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
            return round(_clamp(e, 0.05, 1.0), 3)
        except Exception:
            return self._stored("energy", 0.7)
        finally:
            _guard.busy = False

    def _discomfort(self, now: datetime) -> tuple[float, str]:
        phase, day_of_cycle = self._cycle(now)
        if phase == "menstrual" and day_of_cycle <= 2:
            return 0.5, "cólica"
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
                   WHERE event_at<=? AND event_at>=?""",
                (now.isoformat(), (now - timedelta(hours=lookback_hours)).isoformat())).fetchall()
        tired = self.energy(now) < 0.5
        created = 0
        for r in rows:
            for fam, kind, intensity, cause, target in appraise_event(dict(r), tired=tired):
                at = datetime.fromisoformat(r["event_at"])
                created += self.feel(fam, kind, intensity, cause, at, target=target,
                                     source_key=f"ev:{r['event_key']}:{kind}")
        created += self._appraise_deadlines(now)
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
                created += self.feel("alegria", "alivio", 0.45, f"entregou o {a['kind']} de {a['course']}",
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
                                     f"{a['kind']} de {a['course']} pra entregar "
                                     f"{'amanhã' if days == 1 else 'hoje' if days == 0 else f'em {days} dias'}",
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
        """Saudade pelo silêncio dele (mesma taxa da proatividade)."""
        try:
            from proactivity_service import SAUDADE_RATE_PER_HOUR
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT timestamp FROM conversas WHERE role='user' ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return 0.0
            hours = max(0.0, (now - datetime.fromisoformat(row["timestamp"])).total_seconds() / 3600)
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
        libido, excitation, since = self._libido(now, phase, energy, discomfort, valence, bond, missing, eps)
        return Feeling(now=now, energy=energy, hours_slept=slept, awake_since=awake_since, hunger=hunger,
                       discomfort=discomfort, discomfort_why=why, cycle_phase=phase,
                       valence=round(valence, 3), arousal=round(arousal, 3), playfulness=round(playfulness, 3),
                       episodes=eps, bond=bond, missing=missing, social_battery=social,
                       libido=libido, excitation=excitation, hours_since_release=since)

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

    def _libido(self, now, phase, energy, discomfort, valence, bond, missing, eps) -> tuple:
        """Vontade (0–1): acumula com as horas sem gozar, sobe com ciclo fértil,
        saudade, dia bom e desejo por ele; cai com cansaço, cólica e mágoa."""
        from intimacy import CYCLE_LIBIDO
        cycle = next((v for k, v in CYCLE_LIBIDO.items() if phase and phase.startswith(k.split("_")[0])), 1.0)
        release = self.last_release(now)
        since = (now - release).total_seconds() / 3600 if release else None
        v = 0.12 + 0.35 * (cycle - 0.7) / 0.65
        v += min(0.35, 0.012 * (since if since is not None else 12.0))   # sem registro: meio dia
        v += 0.25 * (bond["romantic_intensity"] - 0.8) + 0.15 * (valence - 0.6) + 0.1 * (energy - 0.55)
        v += 0.08 * missing - 0.4 * discomfort - 0.6 * bond["hurt"]
        v += sum(0.1 * e.intensity for e in eps if e.target == PATRICK_TARGET and e.kind in ("diversao", "carinho"))
        excitation = 0.0
        try:
            from intimacy import IntimacyEngine
            excitation = IntimacyEngine(self.db).current(now).arousal
        except Exception:
            pass
        v += 0.5 * excitation
        if since is not None and since < 3:
            v *= 0.3   # acabou de gozar
        return round(_clamp(v), 3), round(excitation, 3), (round(since, 1) if since is not None else None)

    def maybe_release_alone(self, now: Optional[datetime] = None) -> Optional[str]:
        """Com tesão e sem o Patrick, antes de dormir ela se resolve sozinha — e às
        vezes conta pra ele depois (decisão do Patrick, 23/09)."""
        now = now or datetime.now()
        key = f"solo:{now.date().isoformat()}"
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
        summary = ("Antes de dormir, com tesão e pensando no Patrick, se resolveu sozinha"
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
        self.feel("alegria", "alivio", 0.3, "se resolveu sozinha antes de dormir", now, source_key=f"{key}:alivio")
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
        if f.discomfort_why:
            body.append(f.discomfort_why)
        if body:
            lines.append("- Corpo: " + ", ".join(body) + ".")
        lines.append(f"- Humor: {self.mood_words(f.valence, f.arousal)}.")
        for ep in f.episodes[:2]:
            about = f" com {ep.target}" if ep.target else ""
            lines.append(f"- Sentindo agora: {ep.word}{about} — {_short(ep.cause)}.")
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
        if any(e.kind == "ciume" for e in f.episodes):
            lines.append("  Ciuminho: implica de brincadeira (\"quem é essa aí?\"), sem cobrar nem controlar.")
        lines.append("Isso muda o JEITO (mais curta, dengosa, elétrica), não vira assunto: nunca diga "
                     "\"estou me sentindo X\". O que é com o mundo não é com o Patrick. Conte ou guarde "
                     "o que sente como gente de verdade.")
        return lines

    def summary(self, now: Optional[datetime] = None) -> str:
        """Texto do /emocao (só pro Patrick): camada por camada, com as causas.

        Layout de 23/09: barrinha + palavra em vez de número solto."""
        f = self.feeling(now)
        b = f.bond
        phase = PHASE_NAMES.get(f.cycle_phase, f.cycle_phase)
        sleep = []
        if f.hours_slept is not None:
            sleep.append(f"dormiu {_hours(f.hours_slept)}")
        if f.awake_since:
            sleep.append(f"acordada desde {f.awake_since:%H:%M}")
        out = [f"🫀 Marina por dentro · {f.now:%d/%m %H:%M}", "",
               "🧍 CORPO",
               f"Energia  {_bar(f.energy)}  {_word(f.energy, ENERGY_WORDS)}",
               f"Fome     {_bar(f.hunger)}  {_word(f.hunger, HUNGER_WORDS)}",
               f"Tesão    {_bar(f.libido)}  {_word(f.libido, LIBIDO_WORDS)}"
               + (f" · no clima agora" if f.excitation >= 0.45 else "")
               + (f" · última vez há {f.hours_since_release:.0f} h" if f.hours_since_release is not None else "")]
        if sleep:
            out.append("😴 " + " · ".join(sleep))
        if phase or f.discomfort_why:
            out.append("🌸 " + " · ".join(x for x in (phase, f.discomfort_why) if x))
        out += ["", "🌤 HUMOR", self.mood_words(f.valence, f.arousal).capitalize(),
                f"Brincadeira  {_bar(f.playfulness)}",
                f"Pique social {_bar(f.social_battery)}", "",
                "💭 SENTINDO AGORA"]
        if f.episodes:
            for e in f.episodes[:6]:
                who = f" com {e.target}" if e.target else ""
                tail = " (até resolver)" if e.sticky and e.intensity >= e.peak * 0.99 else ""
                out.append(f"• {e.word}{who} {_bar(e.intensity, 5)} — {_short(e.cause, 70)}{tail}")
        else:
            out.append("Nada marcante agora")
        out += ["", "💞 COM O PATRICK",
                f"Carinho   {_bar(b['affection'])}",
                f"Desejo    {_bar(b['romantic_intensity'])}",
                f"Segurança {_bar(b['security'])}",
                f"Saudade   {_bar(f.missing)}"]
        if b["hurt"] >= 0.05:
            out.append(f"Mágoa     {_bar(b['hurt'])}")
        return "\n".join(out)


def _person(participants_json: Optional[str]) -> Optional[str]:
    try:
        from social_day import short_name
        people = [p for p in json.loads(participants_json or "[]") if p != "marina"]
        return short_name(people[0]) if people else None
    except Exception:
        return None


# Milo: travessura que diverte, que irrita ou que derrete.
MILO_ANTICS = (("xixi no tapete", "raiva", "irritacao", 0.3), ("manha pedindo colo a noite", "raiva", "impaciencia", 0.25),
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
        cause = text.split(": ", 1)[-1]
        if "açaí" in low:
            out.append(("alegria", "diversao", 0.3, cause, None))
        else:
            out.append(("raiva", "irritacao", 0.4 + (0.15 if tired else 0.0) - (0.2 if "garoar" in low else 0.0),
                        cause, None))
    elif key.startswith("milo:") and key.endswith(":arte"):
        for needle, fam, kind, intensity in MILO_ANTICS:
            if needle in low:
                out.append((fam, kind, intensity + (0.1 if tired and fam == "raiva" else 0.0), text, None))
                break
    elif key.startswith("banho:"):
        out.append(("alegria", "alivio", 0.2, "banho quentinho, se sentiu gente de novo", None))
    elif key.startswith("tv:novo:") or low.startswith("saiu episódio novo"):
        out.append(("alegria", "empolgacao", 0.45, text, None))
    elif key.startswith("tv:"):
        if " e amou" in low:
            out.append(("alegria", "contentamento", 0.4, text.split("; ")[-1], None))
        elif "achou só ok" in low:
            out.append(("tristeza", "decepcao", 0.2, text.split("; ")[-1], None))
        elif low.startswith("viu "):
            out.append(("alegria", "diversao", 0.2, text.split("; ")[0], None))
    elif key.startswith("peso:"):
        if key.endswith(":agencia"):
            out.append(("medo", "inseguranca", 0.6, "a Lívia da agência cobrou o peso", "a Lívia"))
            out.append(("vergonha", "vergonha", 0.3, "levou bronca da agência pelo peso", None))
        elif key.endswith(":saude"):
            out.append(("medo", "preocupacao", 0.35, "sentiu tontura no treino", None))
    elif key.startswith("falta:"):
        out.append(("vergonha", "culpa", 0.35, text, None))
    elif key.startswith("atraso:"):
        out.append(("raiva", "frustracao", 0.4, "perdeu o despertador e chegou atrasada", None))
    elif key.startswith("facul:sessao:"):
        if "virando a noite" in low:
            out.append(("medo", "ansiedade", 0.5, "virando a noite no trabalho da facul", None))
        elif "enrolando" in low:
            out.append(("vergonha", "culpa", 0.2, "enrolou no trabalho da facul", None))
        elif "rendendo bem" in low:
            out.append(("alegria", "orgulho", 0.3, "rendeu bem no trabalho da facul", None))
    elif kind_ev == "social_invite":
        if key.endswith(":convite"):
            out.append(("alegria", "empolgacao", 0.35, text, who))
    elif kind_ev == "social_contact":
        if "henrique" in (ev.get("participants_json") or ""):
            if "dinheiro" in low:
                out.append(("alegria", "gratidao", 0.4, "o pai mandou o dinheiro da semana sem ela pedir", "o pai"))
            elif "saudade" in low or "ligou" in low or "ligação" in low:
                out.append(("afeto", "saudade_casa", 0.3, "falou com o pai", "o pai"))
            else:
                out.append(("afeto", "carinho", 0.25, "o pai deu bom dia e perguntou dela", "o pai"))
        elif "conflitos leves" in low:
            out.append(("raiva", "chateacao", 0.3, text, who))
        elif any(t in low for t in ("fofoca", "festas", "música", "moda", "fotografia", "humor")):
            out.append(("alegria", "diversao", 0.25, text, who))
    elif kind_ev == "meal" and "beliscou" not in low and "pulou" not in low:
        if "açaí" in low:
            out.append(("alegria", "contentamento", 0.35, text, None))
        elif any(t in low for t in ("shopping", "ifood", "japonesa", "hambúrguer", "pizza")):
            out.append(("alegria", "contentamento", 0.2, text, None))
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
    "grosseria":   ([("tristeza", "decepcao", 0.4)], {"hurt": 0.25, "security": -0.03}, True),
    "esqueceu_importante": ([("tristeza", "decepcao", 0.4)], {"hurt": 0.2}, True),
    "briga":       ([("raiva", "chateacao", 0.55)], {"hurt": 0.3, "security": -0.05}, True),
    "desculpa":    ([("afeto", "ternura", 0.3)], {"hurt": -0.35, "security": 0.03}, False),
    "sem_clima":   ([("raiva", "frustracao", 0.2)], {}, False),
}
KIND_WORDS["ciume"] = "com ciuminho"
DEFAULT_CAUSES = {"elogio": "ele te elogiou", "cuidado": "ele cuidou de você", "flerte": "ele flertou",
                  "provocacao": "ele te zoou de boa", "novidade_boa": "ele contou uma coisa boa",
                  "ele_mal": "ele não está bem", "ciume": "ele falou de outra garota",
                  "grosseria": "ele foi grosso com você", "esqueceu_importante": "ele esqueceu algo que importava",
                  "briga": "vocês discutiram", "desculpa": "ele pediu desculpa",
                  "sem_clima": "você quis e ele não entrou no clima"}


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
