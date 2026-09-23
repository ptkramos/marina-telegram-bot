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


def _hours(value: float) -> str:
    """5.5 -> "5h30", 6.0 -> "6h" (meia hora mais próxima)."""
    half_hours = int(round(value * 2))
    h, m = divmod(half_hours * 30, 60)
    return f"{h}h{m:02d}" if m else f"{h}h"


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
                if not r["resolved_at"]:
                    cooling_from = now
                else:
                    cooling_from = max(started, datetime.fromisoformat(r["resolved_at"]))
            minutes = max(0.0, (now - cooling_from).total_seconds() / 60)
            value = float(r["intensity"]) * 0.5 ** (minutes / max(1, r["half_life_min"]))
            if value >= ACTIVE_MIN:
                out.append(Episode(r["id"], r["family"], r["kind"], round(value, 3), float(r["intensity"]),
                                   r["cause"], r["target"], started, bool(r["sticky"])))
        return sorted(out, key=lambda e: e.intensity, reverse=True)

    # =========================================================== vínculo ==
    def _stored(self, key: str, default: float) -> float:
        try:
            return float(self.db.get_estado_emocional().get(key, {}).get("valor", default))
        except Exception:
            return default

    def bond(self) -> dict:
        state = self.db.get_estado_emocional()
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
        energy = self.energy(now)
        try:
            slept, awake_since, _, _ = self._sleep_facts(now)
        except Exception:
            slept, awake_since = None, None
        hunger = self._hunger(now)
        discomfort, why = self._discomfort(now)
        phase, _ = self._cycle(now)
        eps = self.episodes(now)
        bond = self.bond()
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
        return Feeling(now=now, energy=energy, hours_slept=slept, awake_since=awake_since, hunger=hunger,
                       discomfort=discomfort, discomfort_why=why, cycle_phase=phase,
                       valence=round(valence, 3), arousal=round(arousal, 3), playfulness=round(playfulness, 3),
                       episodes=eps, bond=bond, missing=self._missing(now), social_battery=social)

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
            lines.append(f"- Sentindo agora: {ep.word}{about} — {ep.cause}.")
        heart = []
        if f.bond["affection"] >= 0.8:
            heart.append("apaixonada e carinhosa")
        elif f.bond["affection"] < 0.55:
            heart.append("mais distante que o normal")
        if f.bond["romantic_intensity"] >= 0.85:
            heart.append("com desejo por ele")
        if f.missing >= 0.6:
            heart.append("com saudade (ele sumiu faz um tempo)")
        if f.bond["hurt"] >= 0.25:
            heart.append("chateada com ele (ainda não resolveu)")
        if heart:
            lines.append("- Com o Patrick: " + ", ".join(heart) + ".")
        lines.append("Isso muda o JEITO (mais curta, mais dengosa, mais elétrica), não vira assunto: "
                     "nunca diga \"estou me sentindo X\". O que é com o mundo não é com o Patrick — "
                     "você pode estar irritada com o dia e carinhosa com ele. Conte ou guarde o que "
                     "sente como uma pessoa de verdade faria.")
        return lines

    def summary(self, now: Optional[datetime] = None) -> str:
        """Texto do /emocao (só pro Patrick): camada por camada, com as causas."""
        f = self.feeling(now)
        out = [f"🫀 Como a Marina está ({f.now:%d/%m %H:%M})", "",
               f"Corpo: energia {f.energy:.2f}"
               + (f" · dormiu {f.hours_slept:.1f} h" if f.hours_slept is not None else "")
               + (f" · acordada desde {f.awake_since:%H:%M}" if f.awake_since else "")
               + f" · fome {f.hunger:.2f}" + (f" · {f.discomfort_why}" if f.discomfort_why else ""),
               f"Humor: {self.mood_words(f.valence, f.arousal)} (bem {f.valence:.2f} · agitação {f.arousal:.2f})"
               + (f" · fase {f.cycle_phase}" if f.cycle_phase else ""),
               f"Brincadeira: {f.playfulness:.2f} · bateria social {f.social_battery:.2f}", ""]
        if f.episodes:
            out.append("Sentindo:")
            out += [f"• {e.word} ({e.intensity:.2f}) — {e.cause}" + (" [até resolver]" if e.sticky else "")
                    for e in f.episodes[:6]]
        else:
            out.append("Sentindo: nada marcante agora")
        b = f.bond
        out += ["", f"Com o Patrick: carinho {b['affection']:.2f} · desejo {b['romantic_intensity']:.2f} · "
                    f"segurança {b['security']:.2f} · mágoa {b['hurt']:.2f} · saudade {f.missing:.2f}"]
        return "\n".join(out)


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
