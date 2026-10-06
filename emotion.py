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
    detalhes: tuple = ()  # 06/10 (passo 5): (tipo, texto) do detalhe que vai à parte

    @property
    def word(self) -> str:
        return KIND_WORDS.get(self.kind, self.kind)

    @property
    def texto(self) -> str:
        """O motivo como o prompt lê: a frase com o detalhe emendado."""
        return texto_motivo(self.cause, self.detalhes)


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
        """Registra um sentimento com causa. `source_key` evita sentir duas vezes a mesma coisa.
        A causa feita por `_motivo` leva o detalhe junto (vai pra coluna `detalhe_json`)."""
        if family not in FAMILIES:
            raise ValueError(f"família emocional desconhecida: {family}")
        now = now or datetime.now()
        detalhe = json.dumps([list(d) for d in getattr(cause, "detalhes", ())], ensure_ascii=False) \
            if getattr(cause, "detalhes", ()) else None
        cause = str(cause)
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
                    conn.execute("UPDATE emotion_episodes SET intensity=?, cause=?, detalhe_json=?, started_at=? "
                                 "WHERE id=?", (round(merged, 3), cause, detalhe, now.isoformat(), row["id"]))
                    if source_key:
                        conn.execute("INSERT OR IGNORE INTO emotion_sources (source_key, episode_id, created_at) "
                                     "VALUES (?,?,?)", (source_key, row["id"], datetime.now().isoformat()))
                    conn.commit()
                    return True
            cur = conn.execute(
                """INSERT OR IGNORE INTO emotion_episodes
                   (family, kind, intensity, cause, target, source_key, started_at, half_life_min, sticky, created_at,
                    detalhe_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (family, kind, round(_clamp(intensity), 3), cause, target, source_key, now.isoformat(),
                 int(half_life_min or FAMILIES[family]["half_life"]), int(sticky), datetime.now().isoformat(),
                 detalhe))
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
                                   r["cause"], r["target"], started, bool(r["sticky"]),
                                   _detalhes(r["detalhe_json"])))
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
                # 06/10 (passo 5): "Tem casting na quarta" — o dia da semana não fica errado de um dia pro outro
                # (o episódio nasce uma vez e o "amanhã" de ontem à noite virava mentira de manhã)
                created += self.feel("medo", "ansiedade", 0.35 if job else 0.25,
                                     _motivo(f"Tem {'job' if job else 'casting'} {_no_dia(item['start'].date())}",
                                             _trabalho(item["what"])),
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
                created += self.feel("alegria", "alivio", 0.45, _motivo(_entregou(a["kind"]), _materias([a["course"]])),
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
                                     _motivo(f"Tem entrega {_no_dia(due)}", _materias([a["course"]])),
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
        self.feel("alegria", "alivio", 0.3, _motivo("Se masturbou antes de dormir"), now, source_key=f"{key}:alivio")
        if wanted_him:
            self.feel("raiva", "frustracao", 0.2, _motivo("Ficou querendo o Patrick e não rolou"), now, target=PATRICK_TARGET,
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
            lines.append(f"- Sentindo agora: {ep.word}{about} — {_short(ep.texto, 120)}{quando}.")
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
            heart.append("chateada com ele" + (f" ({_short(grievance.texto, 120)})" if grievance else ""))
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
                                 "cause": _short(e.cause, 70), "cause_raw": e.cause, "detalhes": e.detalhes,
                                 "count": n,
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
            "valence": f.valence, "arousal": f.arousal,      # 06/10 (passo 4): a grade do humor (só tela)
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
            rows = conn.execute("""SELECT kind, target, cause, detalhe_json, started_at, intensity FROM emotion_episodes
                                   WHERE started_at>=? AND started_at<? ORDER BY started_at DESC""",
                                (start.isoformat(), end.isoformat())).fetchall()
        out, vistos = [], set()
        for r in rows:
            chave = (r["kind"], r["target"] or "", r["cause"], r["started_at"][:16])
            if chave in vistos:
                continue
            vistos.add(chave)
            out.append({"word": KIND_WORDS.get(r["kind"], r["kind"]), "target": r["target"], "cause": r["cause"],
                        "detalhes": _detalhes(r["detalhe_json"]),
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


# 06/10 (Patrick, redesenho dos Bastidores, passo 5): o motivo de cada sentimento é UMA FRASE inteira, em 3ª pessoa:
# quem fez + verbo no passado + o quê ("O Patrick mandou comida de surpresa", "A Bia chamou ela pra sair"); coisa dela
# sem sujeito ("Furou o rolê"); o que vai acontecer com "Tem" ("Tem casting amanhã"); sem "·" nem parênteses. O
# detalhe vai à parte (coluna `detalhe_json`), cada um com o tipo — a tela põe o ícone — e com a preposição ("De R$
# 200", "Sobre fofocas", "No Quartinho Bar"). O prompt lê a frase com o detalhe emendado (`texto_motivo`).
# Antes (28/09): "fato · detalhe" numa string só ("Viu Paradise Kiss · eps 1 e 2"); a tela ainda entende os antigos.
DETALHE_ICONE = {"valor": "cash", "recado": "note", "pra": "shopping-cart", "materia": "book",
                 "assunto": "message-circle", "lugar": "map-pin", "atraso": "clock", "episodio": "device-tv",
                 "trabalho": "camera", "loja": "tools-kitchen-2", "app": "moped", "com": "users",
                 "caminho": "route", "audio": "microphone", "mensagem": "message", "brinquedo": "device-mobile-vibration"}
MOTIVO_MAX = 90
LUGAR_FEMININO = ("praia", "agência", "agencia", "enseada", "puc", "drogaria", "bodytech", "estação", "clínica",
                  "orla", "academia", "padaria", "farmácia", "ophicina", "officina", "kopenhagen", "novamed",
                  "faculdade", "rua", "casa de")


class Motivo(str):
    """A frase é a própria string (vai pra `cause` e pros testes); os detalhes viajam junto até o `feel`."""
    detalhes: tuple = ()

    def __new__(cls, frase: str, detalhes=()):
        obj = super().__new__(cls, frase)
        obj.detalhes = tuple((t, x) for t, x in detalhes if x)
        return obj


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _limpo(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().rstrip(".")


def _motivo(frase: str, *detalhes: tuple) -> Motivo:
    frase = _limpo(frase)
    if len(frase) > MOTIVO_MAX:
        frase = frase[:MOTIVO_MAX].rsplit(" ", 1)[0]
    return Motivo(_cap(frase), [(t, _cap(_limpo(x))) for t, x in detalhes if _limpo(x)])


def _detalhes(raw) -> tuple:
    try:
        return tuple((t, x) for t, x in json.loads(raw or "[]"))
    except (ValueError, TypeError):
        return ()


def texto_motivo(cause: str, detalhes=()) -> str:
    """Frase + detalhe emendado, como o prompt lê: 'O Patrick fez um Pix de presente, de R$ 200'."""
    partes = [cause]
    for tipo, x in detalhes:
        partes.append(f'com o recado "{x}"' if tipo == "recado" else x[:1].lower() + x[1:])
    return ", ".join(partes)


def _no(lugar: str) -> str:
    """'Quartinho Bar' → 'No Quartinho Bar'; 'PUC-Rio' → 'Na PUC-Rio'; o apê dela → 'Em casa'."""
    lugar = (lugar or "").split("/")[0].strip()
    if not lugar:
        return ""
    if lugar.lower().startswith(("apartamento da marina", "casa da marina")):
        return "Em casa"
    return ("Na " if lugar.lower().startswith(LUGAR_FEMININO) else "No ") + lugar


def _da(loja: str) -> str:
    return ("Da " if loja.lower().startswith(LUGAR_FEMININO) else "Do ") + loja


def _valor(text: str) -> tuple:
    m = re.search(r"R\$ ?([\d.,]+\d)", text or "")
    return ("valor", f"De R$ {m.group(1)}") if m else ("valor", "")


def _recado(text: str) -> tuple:
    """O recado que o Patrick escreve no Pix: "('Pra gastar no shopping')"."""
    m = re.search(r"\('([^']+)'\)", text or "")
    return ("recado", m.group(1)) if m else ("recado", "")


def _motivo_generico(text: str) -> Motivo:
    """Resumo do mundo → frase: o primeiro pedaço, sem parênteses; o assunto (se houver) vira o detalhe."""
    base, _, assunto = (text or "").partition("; assunto: ")
    base = re.sub(r"\s*\([^)]*\)", "", base.split("; ")[0]).split(" — ")[0]
    return _motivo(base, ("assunto", f"Sobre {assunto.split(',')[0]}" if assunto else ""))


def _motivo_contato(text: str, who: Optional[str], briga: bool) -> Motivo:
    """'Trocou mensagens com a Bia; assunto: festas' → 'Trocou mensagens com a Bia' + 'Sobre festas';
    'Encontrou a Júlia (PUC-Rio); assunto: fotografia' → 'Encontrou a Júlia' + 'Na PUC-Rio' + 'Sobre fotografia';
    briga: 'Se estranhou com a Bia' + 'Por áudio' (ou o lugar)."""
    base, _, assunto = text.partition("; assunto: ")
    par = re.search(r"\(([^)]+)\)", base)
    lugar = _no(par.group(1)) if par else ""
    base = re.sub(r"\s*\([^)]*\)", "", base).split(", ")[0]
    low = base.lower()
    if briga:
        canal = ("audio", "Por áudio") if "áudio" in low else ("mensagem", "Por mensagem") \
            if low.startswith("trocou mensagens") else ("lugar", lugar)
        return _motivo(f"Se estranhou com {who}" if who else "Se estranhou com uma amiga", canal)
    sobre = ("assunto", f"Sobre {_limpo(assunto.split(',')[0])}" if assunto else "")
    return _motivo(base, ("lugar", lugar), sobre)


def _motivo_convite(text: str) -> Motivo:
    """'A Bia te chamou: Saindo com a Bia no Quartinho Bar (hoje às 21:00)' → 'A Bia chamou ela pra sair' +
    'No Quartinho Bar'."""
    quem, _, resto = text.partition(" te chamou: ")
    resto = re.sub(r"\s*\([^)]*\)", "", resto)
    m = re.search(r"\b(?:no|na|em) ([A-ZÁÉÍÓÚ][^,;]*)$", resto)
    if not resto:
        return _motivo_generico(text)
    return _motivo(f"{quem} chamou ela pra sair", ("lugar", _no(m.group(1)) if m else ""))


def _episodios(a: str, b: Optional[str]) -> str:
    if not b or a == b:
        return f"Episódio {a}"
    return f"Episódios {a} e {b}" if int(b) == int(a) + 1 else f"Episódios {a} a {b}"


def _motivo_tv(text: str) -> Motivo:
    """'Viu episódios 1 a 2 de Paradise Kiss (…)' → 'Viu Paradise Kiss' + 'Episódios 1 e 2';
    'Saiu episódio novo de One Piece hoje (temporada 23, ep. 1180)' → 'Saiu episódio novo de One Piece' +
    'Episódio 1180'."""
    m = re.match(r"Saiu episódio novo de (.+?) hoje", text)
    if m:
        ep = re.search(r"ep\. ?(\d+)", text)
        return _motivo(f"Saiu episódio novo de {m.group(1)}", ("episodio", f"Episódio {ep.group(1)}" if ep else ""))
    m = re.match(r"Viu (?:o )?epis[óo]dios? (\d+)(?: a (\d+))? de ([^(;]+)", text)
    if m:
        return _motivo(f"Viu {m.group(3).strip()}", ("episodio", _episodios(m.group(1), m.group(2))))
    return _motivo_generico(text)


REFEICAO = {"almoço": "Almoçou", "jantar": "Jantou", "café": "Tomou café com", "lanche": "Lanchou"}


def _motivo_refeicao(text: str) -> Motivo:
    """'Almoço em casa: um poke pedido no iFood; comeu além da conta…' → 'Almoçou um poke e comeu demais' +
    'Pelo iFood'; 'Almoço no shopping: …' → o lugar embaixo."""
    head, _, rest = text.partition(": ")
    verbo = REFEICAO.get(head.split(" ")[0].lower())
    if not verbo or not rest:
        return _motivo_generico(text)
    low = text.lower()
    comida = re.sub(r" pedid[oa]s? no iFood", "", rest.split("; ")[0])
    comida = re.sub(r"\s*\([^)]*\)", "", comida)
    frase = f"{verbo} {comida}" + (" e comeu demais" if "além da conta" in low else "")
    lugar = _no(head.split(" no ", 1)[1]) if " no " in head else _no(head.split(" na ", 1)[1]) if " na " in head else ""
    return _motivo(frase, ("app", "Pelo iFood" if "ifood" in low else ""), ("lugar", lugar))


def _motivo_presente(text: str) -> tuple[Motivo, Motivo]:
    """'O Patrick mandou de surpresa X do Megamatte pelo app; …' → o carinho dele e o contentamento dela, com a
    loja embaixo ('Do Megamatte')."""
    m = re.search(r" d[oa] (.+?) pelo app", text)
    loja = ("loja", _da(m.group(1)) if m else "")
    return _motivo("O Patrick mandou comida de surpresa", loja), _motivo("Chegou a comida surpresa", loja)


def _motivo_pix(text: str) -> Motivo:
    """Os pix do Patrick (financas): de presente, pra cobrir o aperto, pelo uber, o prometido; valor e recado embaixo."""
    low = text.lower()
    frase = ("O Patrick fez o Pix que tinha prometido" if "tinha prometido" in low
             else "O Patrick fez um Pix pra cobrir o aperto" if "cobrir o aperto" in low
             else "O Patrick fez um Pix pelo uber" if "uber" in low
             else "O Patrick fez um Pix de presente" if "presente" in low else "O Patrick fez um Pix")
    return _motivo(frase, _valor(text), _recado(text))


def _materias(nomes: list[str]) -> tuple:
    nomes = [n.strip() for n in nomes if n.strip()]
    if not nomes:
        return ("materia", "")
    return ("materia", f"De {nomes[0]}" + (f" e mais {len(nomes) - 1}" if len(nomes) > 1 else ""))


def _trabalho(what: str) -> tuple:
    return ("trabalho", f"De {what}" if what else "")


def _o_que(text: str) -> str:
    """O job do freela entre parênteses ('Não passou no casting (vídeo pra uma marca de cosméticos)')."""
    m = re.search(r"\(([^)]+)\)", text)
    return m.group(1) if m else ""


DIAS_SEMANA = ("na segunda", "na terça", "na quarta", "na quinta", "na sexta", "no sábado", "no domingo")


def _no_dia(dia: date) -> str:
    return DIAS_SEMANA[dia.weekday()]


def _entregou(kind: str) -> str:
    """'Entregou o trabalho', 'Entregou a apresentação'; a entrega final vira 'Fez a entrega final'."""
    if kind == "entrega final":
        return "Fez a entrega final"
    return f"Entregou {'a' if kind.endswith('ção') else 'o'} {kind}"


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
        # "No caminho (voltando da PUC, de metrô e ônibus): perdeu o ônibus da integração por um minuto."
        m = re.match(r"No caminho \(([^,)]+)[^)]*\): (.+)$", text)
        cause = _motivo(m.group(2), ("caminho", m.group(1))) if m else _motivo_generico(text.split(": ", 1)[-1])
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
        out.append(("alegria", "alivio", 0.2, _motivo("Tomou um banho quentinho"), None))
    elif key.startswith("tv:novo:") or low.startswith("saiu episódio novo"):
        out.append(("alegria", "empolgacao", 0.45, _motivo_tv(text), None))
    elif key.startswith("tv:"):
        fim = text.split("; ")[-1]
        if " e amou" in low:
            out.append(("alegria", "contentamento", 0.4, _motivo(fim), None))
        elif "achou só ok" in low:
            out.append(("tristeza", "decepcao", 0.2, _motivo(fim.replace(", achou só ok", " e achou só ok")), None))
        elif low.startswith("viu "):
            out.append(("alegria", "diversao", 0.2, _motivo_tv(text), None))
    elif key.startswith("peso:"):
        if key.endswith(":agencia"):
            out.append(("medo", "inseguranca", 0.6, _motivo("A Lívia cobrou o peso dela"), "a Lívia"))
            out.append(("vergonha", "vergonha", 0.3, _motivo("Levou bronca da agência pelo peso"), None))
        elif key.endswith(":saude"):
            out.append(("medo", "preocupacao", 0.35, _motivo("Sentiu tontura no treino"), None))
    elif key.startswith("casa:"):             # D9 — casa e vida adulta
        step = key.rsplit(":", 1)[-1]
        if step == "roupa_esquecida":
            out.append(("raiva", "frustracao", 0.3 + (0.1 if tired else 0.0),
                        _motivo("Esqueceu a roupa na máquina"), None))
        elif step in ("geral", "bagunca"):
            out.append(("alegria", "alivio", 0.3, _motivo("O apê ficou arrumado e cheiroso"), None))
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
            what = text.split(": ", 1)[1] if ": " in text else ""
            out.append(("alegria", "empolgacao", 0.35, _motivo("A Lívia mandou um casting", _trabalho(what)),
                        "a Lívia"))
        elif step == "resultado" and "passou no casting" in low and "não passou" not in low:
            what = _trabalho(_o_que(text))
            if "abrir mão" in low:
                out.append(("tristeza", "decepcao", 0.4, _motivo("Passou no casting, mas batia com a facul", what),
                            None))
            else:
                out.append(("alegria", "empolgacao", 0.65, _motivo("Passou no casting", what), None))
                out.append(("alegria", "orgulho", 0.45, _motivo("Foi escolhida pro job", what), None))
        elif step == "resultado":
            out.append(("tristeza", "decepcao", 0.4, _motivo("Não passou no casting", _trabalho(_o_que(text))), None))
        elif step == "job":
            what = re.match(r"Fez o job: ([^.]+)", text)
            out.append(("alegria", "orgulho", 0.45, _motivo("Fez o job", _trabalho(what.group(1) if what else "")),
                        None))
        elif step in ("job_perdido", "casting_perdido"):
            out.append(("tristeza", "decepcao", 0.5 if step == "job_perdido" else 0.3,
                        _motivo(text.split(" (")[0].split(": ")[0], _trabalho(_o_que(text))), None))
        elif step in ("cache", "sinal"):
            frase = "A Lívia fez o Pix do resto do cachê" if step == "cache" else "A Lívia fez o Pix de metade do cachê"
            out.append(("alegria", "contentamento", 0.45 if step == "cache" else 0.35,
                        _motivo(frase, _valor(text)), None))
    elif key.endswith(":presente") or key.startswith("presente:"):   # delivery surpresa pelo Mini App (25/09)
        dele, dela = _motivo_presente(text)
        out.append(("afeto", "carinho", 0.6, dele, PATRICK))
        out.append(("alegria", "contentamento", 0.45, dela, None))
    elif key.startswith("financas:"):        # /pix e o dinheiro dela (24/09)
        step = key.rsplit(":", 1)[-1]
        if step == "emergencia":
            m = re.match(r"Aperto: (.+?) \(R\$", text)
            out.append(("medo", "preocupacao", 0.45, _motivo(m.group(1) if m else text, _valor(text)), None))
        elif step == "aperto":
            out.append(("medo", "preocupacao", 0.45, _motivo_generico(text), None))
        elif step == "pix":
            out.append(("afeto", "gratidao" if "presente" in low else "carinho", 0.5, _motivo_pix(text), PATRICK))
            if "aperto" in low:
                out.append(("alegria", "alivio", 0.45, _motivo("O Patrick cobriu o aperto dela"), None))
        elif step == "devolveu":
            out.append(("alegria", "alivio", 0.35, _motivo("Devolveu o empréstimo do Patrick", _valor(text)), None))
        elif step == "presente_usado":
            m = re.match(r"Usou o pix do Patrick: comprou (.+?) \(R\$", text)
            out.append(("alegria", "contentamento", 0.35,
                        _motivo(f"Usou o Pix do Patrick pra comprar {m.group(1)}" if m else text, _valor(text)), None))
    elif key.startswith("falta:"):
        # college: "Faltou a aula hoje (A, B, C): cólica forte, ficou em casa."
        m = re.match(r"Faltou a aula hoje \((.+?)\):", text)
        nomes = m.group(1).split(", ") if m else []
        out.append(("vergonha", "culpa", 0.35,
                    _motivo("Faltou às aulas de hoje" if len(nomes) > 1 else "Faltou à aula de hoje", _materias(nomes)),
                    None))
    elif key.startswith("atraso:"):
        # 28/09 (atraso.py): "Chegou 15 min atrasada na aula de Ergodesign — perdeu o despertador…"
        m = re.search(r"Chegou (\d+) min atrasada ((?:na |no |em )?.+?)(?: —|\.|$)", text)
        if m:
            n = int(m.group(1))
            out.append(("raiva", "frustracao", round(0.25 + min(0.3, n / 100), 2),
                        _motivo(f"Chegou atrasada {m.group(2)}",
                                ("atraso", f"Com {n} minuto{'s' if n != 1 else ''} de atraso")), None))
        else:
            out.append(("raiva", "frustracao", 0.4, _motivo("Perdeu a hora e chegou atrasada"), None))
    elif key.startswith("facul:sessao:"):
        # "Trabalhou na apresentação de Projeto (entrega 07/10), enrolando um pouco."
        m = re.match(r"Trabalhou (n[oa]) (.+?) de (.+?) \(entrega", text)
        no, tarefa, materia = (m.group(1), m.group(2), m.group(3)) if m else ("no", "trabalho", "")
        if "virando a noite" in low:
            out.append(("medo", "ansiedade", 0.5, _motivo(f"Virou a noite {no} {tarefa}", _materias([materia])), None))
        elif "enrolando" in low:
            out.append(("vergonha", "culpa", 0.2, _motivo(f"Enrolou {no} {tarefa}", _materias([materia])), None))
        elif "rendendo bem" in low:
            out.append(("alegria", "orgulho", 0.3, _motivo(f"Rendeu {no} {tarefa}", _materias([materia])), None))
    elif kind_ev == "social_invite":
        if key.endswith(":convite"):
            out.append(("alegria", "empolgacao", 0.35, _motivo_convite(text), who))
    elif kind_ev == "social_contact":
        if "henrique" in (ev.get("participants_json") or ""):
            if "dinheiro" in low:
                # 06/10 (Patrick, catálogo): igual ao Pix de presente dele; é o dinheiro da comida da semana
                out.append(("alegria", "gratidao", 0.4,
                            _motivo("O pai fez um Pix sem ela pedir", ("pra", "Pro mercado e a comida da semana")),
                            "o pai"))
            elif "saudade" in low or "ligou" in low or "ligação" in low or "telefone" in low:
                assunto = text.partition("; assunto: ")[2]
                out.append(("afeto", "saudade_casa", 0.3,
                            _motivo("Falou com o pai por telefone", ("assunto", f"Sobre {assunto}" if assunto else "")),
                            "o pai"))
            else:
                # 28/09: era "o pai deu bom dia e perguntou dela" a qualquer hora (21h15 inclusive)
                out.append(("afeto", "carinho", 0.25, _motivo("O pai perguntou dela"), "o pai"))
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
# 06/10 (passo 5): frase inteira, "O Patrick" + verbo no passado + o quê (a tela e o prompt mostram como está)
DEFAULT_CAUSES = {"elogio": "O Patrick elogiou ela", "cuidado": "O Patrick cuidou dela",
                  "flerte": "O Patrick flertou com ela", "provocacao": "O Patrick zoou ela",
                  "novidade_boa": "O Patrick contou uma novidade boa",
                  "ele_mal": "O Patrick contou que não está bem", "ciume": "O Patrick falou de outra garota",
                  "desconfiou": "O Patrick desconfiou dela",
                  "grosseria": "O Patrick foi grosso com ela",
                  "esqueceu_importante": "O Patrick esqueceu uma coisa importante",
                  "briga": "Discutiu com o Patrick", "desculpa": "O Patrick pediu desculpa",
                  "sem_clima": "O Patrick não entrou no clima"}


def _causa_do_planner(cause: str) -> str:
    """O planner escreve a frase; o que ainda vier no jeito antigo ("o Patrick elogiou ela · cabelo") vira frase
    com o detalhe emendado e maiúscula, sem parênteses."""
    cause = re.sub(r"\s*\([^)]*\)", "", (cause or "").strip()).replace(" · ", ", ").strip().rstrip(".")
    return _cap(cause)[:120]


def apply_patrick_event(db, event: dict, now: Optional[datetime] = None) -> bool:
    kind = (event or {}).get("kind")
    if kind not in PATRICK_EVENTS:
        return False
    now = now or datetime.now()
    cause = _causa_do_planner(str(event.get("cause") or "")) or DEFAULT_CAUSES[kind]
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
