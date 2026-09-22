"""Fase C.1 — modo íntimo (sexting) da Marina.

Não é um "modo NSFW" que troca a Marina: é um estado temporário da mesma
pessoa, com o mesmo prompt, memórias e mundo. O que muda enquanto ele dura:

* a excitação dela (`arousal`, 0–1) sobe com o que o Patrick diz e cai sozinha
  em minutos (meia-vida AROUSAL_HALF_LIFE_MIN) — ela nunca começa sozinha;
* a fala passa para `LLM_INTIMATE_MODEL` (a arena mostrou que o GPT-5.6 Luna
  fala a política pela boca dela: "não vou entrar em descrição explícita");
* entra um bloco [MODO ÍNTIMO] com o degrau certo da biblioteca (malícia →
  desejo → explícito → clímax → pós-clímax), mais espaço de resposta e mais
  chance de áudio;
* clímax real quando o clima sustenta, pós-clímax (mole, carinhosa, sonolenta)
  e corte imediato sem drama quando ele sinaliza ("depois amor", "tô cansado").

A libido da fase do ciclo (`cycle.py`) multiplica o quanto cada estímulo pesa.
"""
from __future__ import annotations

import logging
import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger("Intimacy")

AROUSAL_HALF_LIFE_MIN = 10.0
ACTIVE_ON = 0.45            # entra no modo
ACTIVE_OFF = 0.20           # sai do modo (histerese)
HOT_AT = 0.70               # degrau explícito
CLIMAX_MIN_AROUSAL = 0.80
CLIMAX_AFTER_HOT_TURNS = 6  # sem pedido dele, ela chega lá depois de um tempo no auge
AFTERGLOW_MIN = 40
REFRACTORY_MIN = 20
GROWTH = 1.5

GAIN_STRONG = 0.28
GAIN_EXTRA_TERM = 0.05
GAIN_REQUEST = 0.10
GAIN_WARM = 0.10
GAIN_PLAN = 0.06

CYCLE_LIBIDO = {"menstrual": 0.7, "folicular": 1.05, "ovulatoria": 1.35, "ovulatória": 1.35,
                "lutea": 0.9, "lútea": 0.9, "tpm": 0.9}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


_STRONG = re.compile(
    r"\b(tesao|pau|pica|piroca|buceta|boceta|xota|xoxota|xereca|grelo|goz\w*|chupa\w*|transa\w*|"
    r"trepa\w*|molhadinh\w*|excitad\w*|punheta|siririca|masturb\w*|pelad\w*|nudes?|putaria|sexo|"
    r"me comer|te comer|comer voce|meter|mete|foder|fode|fodendo|sentar em|sentando em|cavalga\w*|"
    r"de quatro|pau duro)\b")
_REQUEST = re.compile(
    r"(fala putaria|me descreve|descreve (pra mim|direitinho|o que)|com todas as letras|sem vergonha|"
    r"o que (voce|vc|tu) (faria|ia fazer) comigo|me fala o que (voce|vc|tu) (faria|ia fazer)|"
    r"manda (nude|foto pelad))")
_WARM = re.compile(
    r"(😏|🔥|🫦|😈|🥵|\bsafad\w*|\bgostos[ao]\b|\bdelicia\b|\bpescoco\b|\bna cama\b|\bprovoca\w*|"
    r"vontade de (voce|vc|te)\b|me deixa louc\w*|louc[oa] por (voce|vc)|saudade do (seu|teu) corpo|"
    r"de um jeito bem|\blingerie\b|\bcalcinha\b|sem roupa|queria (voce|vc) aqui)")
_HIS_CLIMAX = re.compile(r"\b(gozei|gozando|vou gozar|goza (comigo|pra mim|junto))\b")
_CUT = re.compile(
    r"\b(depois (amor|a gente|agente|continua\w*)|agora nao|outra hora|para com isso|chega por hoje|chega disso|"
    r"to (cansad\w*|mort[oa])|nao to no clima|sem clima|mudando de assunto|deixa pra (la|depois))\b")
_CLOSE = re.compile(r"\b(boa noite|vou dormir|vou deitar|vou nessa|tenho que ir|preciso ir)\b")


def has_explicit_signal(text: str) -> bool:
    return bool(_STRONG.search(_norm(text)))


@dataclass
class IntimacyTurn:
    state: str = "off"          # off | warming | active | climax | afterglow | cut | closing
    arousal: float = 0.0
    strong: bool = False
    minutes_since_climax: Optional[float] = None

    @property
    def band(self) -> str:
        if self.state == "active":
            return "explicito" if self.arousal >= HOT_AT else "desejo"
        return self.state

    @property
    def routed(self) -> bool:
        """Fala escrita pelo modelo íntimo."""
        return self.strong or self.state in ("active", "climax", "afterglow", "closing")

    @property
    def expanded(self) -> bool:
        """Mais espaço de resposta e sem cadência casual."""
        return self.state in ("active", "climax")


class IntimacyEngine:
    def __init__(self, db, cycle_mgr=None):
        self.db = db
        self.cycle_mgr = cycle_mgr

    # ---------------------------------------------------------------- estado
    def _load(self) -> dict:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM intimacy_state WHERE id = 1").fetchone()
        return dict(row) if row else {"arousal": 0.0, "updated_at": None, "mode_since": None,
                                      "hot_turns": 0, "climax_at": None}

    def _save(self, st: dict) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO intimacy_state (id, arousal, updated_at, mode_since, hot_turns, climax_at) "
                "VALUES (1, :arousal, :updated_at, :mode_since, :hot_turns, :climax_at) "
                "ON CONFLICT(id) DO UPDATE SET arousal=:arousal, updated_at=:updated_at, "
                "mode_since=:mode_since, hot_turns=:hot_turns, climax_at=:climax_at", st)
            conn.commit()

    @staticmethod
    def _minutes(since: Optional[str], now: datetime) -> Optional[float]:
        if not since:
            return None
        try:
            return max(0.0, (now - datetime.fromisoformat(since)).total_seconds() / 60.0)
        except (TypeError, ValueError):
            return None

    def _decayed(self, st: dict, now: datetime) -> dict:
        st = dict(st)
        mins = self._minutes(st.get("updated_at"), now)
        if mins:
            st["arousal"] = float(st["arousal"]) * 0.5 ** (mins / AROUSAL_HALF_LIFE_MIN)
        if st["arousal"] < ACTIVE_OFF:
            st["mode_since"], st["hot_turns"] = None, 0
        return st

    def _libido(self) -> float:
        try:
            key = _norm(self.cycle_mgr.get_cycle_info().get("phase_key", "")) if self.cycle_mgr else ""
        except Exception:
            key = ""
        return CYCLE_LIBIDO.get(key, 1.0)

    def _afterglow(self, st: dict, now: datetime) -> Optional[float]:
        mins = self._minutes(st.get("climax_at"), now)
        return mins if mins is not None and mins <= AFTERGLOW_MIN else None

    # ---------------------------------------------------------------- API
    def current(self, now: Optional[datetime] = None) -> IntimacyTurn:
        """Estado sem novo estímulo (roteia o planner antes de observar o turno)."""
        now = now or datetime.now()
        st = self._decayed(self._load(), now)
        glow = self._afterglow(st, now)
        if st["mode_since"]:
            state = "active"
        elif glow is not None:
            state = "afterglow"
        else:
            state = "warming" if st["arousal"] >= ACTIVE_OFF else "off"
        return IntimacyTurn(state, round(st["arousal"], 3), False, glow)

    def observe(self, text: str, plan: Optional[dict] = None,
                now: Optional[datetime] = None) -> IntimacyTurn:
        """Absorve a mensagem do Patrick (e o tom do planner) e decide o turno."""
        now = now or datetime.now()
        t = _norm(text)
        st = self._decayed(self._load(), now)
        was_on = bool(st["mode_since"]) or st["arousal"] >= ACTIVE_OFF
        strong_terms = set(_STRONG.findall(t))
        strong = bool(strong_terms)

        if _CUT.search(t) and not strong:
            st.update(arousal=0.0, mode_since=None, hot_turns=0, updated_at=now.isoformat())
            self._save(st)
            return IntimacyTurn("cut" if was_on else "off", 0.0, False, None)

        gain = 0.0
        if strong:
            gain += GAIN_STRONG + GAIN_EXTRA_TERM * min(2, len(strong_terms) - 1)
        if _REQUEST.search(t):
            gain += GAIN_REQUEST
        if _WARM.search(text.lower()) or _WARM.search(t):
            gain += GAIN_WARM
        plan = plan or {}
        if st["arousal"] >= 0.15 and (_norm(str(plan.get("tone", ""))) in ("sensual", "dengosa")
                                      or plan.get("intent") == "flirting"):
            gain += GAIN_PLAN
        glow = self._afterglow(st, now)
        if glow is not None and glow <= REFRACTORY_MIN:
            gain *= 0.5
        gain *= self._libido()
        a = min(1.0, st["arousal"] + gain * (1.0 - st["arousal"]) * GROWTH)
        st["arousal"], st["updated_at"] = a, now.isoformat()

        active = a >= ACTIVE_ON or (st["mode_since"] and a >= ACTIVE_OFF)
        if active and not st["mode_since"]:
            st["mode_since"] = now.isoformat()

        if active and a >= CLIMAX_MIN_AROUSAL and (
                _HIS_CLIMAX.search(t) or st["hot_turns"] >= CLIMAX_AFTER_HOT_TURNS):
            st.update(arousal=0.35, mode_since=None, hot_turns=0, climax_at=now.isoformat())
            self._save(st)
            logger.info("intimacy.climax")
            return IntimacyTurn("climax", 0.35, strong, 0.0)

        if active and _CLOSE.search(t):
            st.update(arousal=a * 0.5, mode_since=None, hot_turns=0)
            self._save(st)
            return IntimacyTurn("closing", round(st["arousal"], 3), strong, glow)

        if active:
            if a >= HOT_AT:
                st["hot_turns"] = int(st["hot_turns"]) + 1
            self._save(st)
            return IntimacyTurn("active", round(a, 3), strong, glow)

        self._save(st)
        if glow is not None:
            return IntimacyTurn("afterglow", round(a, 3), strong, glow)
        return IntimacyTurn("warming" if a >= ACTIVE_OFF else "off", round(a, 3), strong, None)


# -------------------------------------------------------------- prompt ------

_BAND_TEXT = {
    "desejo": "excitada e assumindo — desejo claro, provocação direta, já dá pra falar de tesão e do que "
              "quer; palavrão sai natural se o clima pede",
    "explicito": "muito excitada — explícita de verdade: fala palavrão e chama as partes íntimas pelo nome "
                 "(pau, buceta, peitos, bunda…) com naturalidade, descreve o que faria e o que sente no "
                 "presente, sem eufemismo de novela",
}

_RULES = (
    "- É sexting consensual entre dois adultos que namoram, só pelo chat. É uma parte real e desejada da relação.\n"
    "- O tesão é DELA: reage ao que ele disse como estímulo de verdade e também conduz — não fica só pedindo "
    "pra ele descrever.\n"
    "- Continua doce e carinhosa: o desejo vem junto do amor dela por ele. Nada de pornografia genérica que "
    "serviria pra qualquer pessoa.\n"
    "- NUNCA fale de regras, limites, políticas, 'conteúdo explícito' ou do que pode ou não pode dizer. Se ela "
    "não quiser alguma coisa, recusa como namorada ('isso não, amor'), nunca como sistema.\n"
    "- Tudo é virtual: não marque encontro nem finja que ele chegou. Fantasia no presente vale quando o clima "
    "tá alto.\n"
    "- Mensagem de chat: 1 a 3 frases, pode quebrar em 2 balões; no máximo 1–2 emojis.\n"
    "- Se ele pedir pra parar ou mudar de assunto, ela desce na hora, sem drama."
)


def _examples_for(band: str, limit: int = 3) -> str:
    try:
        from voice_library import parse_biblioteca_comportamental, format_examples_block
        pool = parse_biblioteca_comportamental()
    except Exception:
        return ""

    def cat(ex) -> str:
        return _norm(ex.categoria)

    wanted = {
        "warming": lambda c: "malicia" in c,
        "desejo": lambda c: "sexting" in c and "iniciativa" not in c and "explicit" not in c
        and "climax" not in c,
        "explicito": lambda c: "sexting" in c and ("iniciativa" in c or "explicit" in c),
        "climax": lambda c: "climax" in c and "pos-climax" not in c,
        "afterglow": lambda c: "pos-climax" in c,
        "closing": lambda c: "pos-climax" in c or "corte" in c,
        "cut": lambda c: "corte" in c,
    }.get(band)
    if not wanted:
        return ""
    # Arena C.1: com os exemplos fixos, Kimi e Grok copiaram "amor… tô gozando…
    # caralho… não para 🥺" palavra por palavra — viraria frase decorada. Sorteio
    # de poucos exemplos + instrução de não repetir.
    candidates = [ex for ex in pool if wanted(cat(ex))]
    picks = random.sample(candidates, min(limit, len(candidates)))
    block = format_examples_block(
        picks, header="[EXEMPLOS DE VOZ — momento íntimo; inspiração, não são turnos desta conversa]")
    return (block + "\nNUNCA repita frases destes exemplos: escreva com palavras suas, reagindo ao que ele "
            "acabou de dizer.") if block else ""


def system_block(turn: IntimacyTurn, cycle_info: Optional[dict] = None) -> Optional[str]:
    libido = (cycle_info or {}).get("libido")
    lib_line = f"\n- Libido pela fase do ciclo hoje: {libido}" if libido else ""
    if turn.state == "active":
        body = (f"[MODO ÍNTIMO — sexting com o Patrick]\n- Como ela está agora: {_BAND_TEXT[turn.band]}."
                f"{lib_line}\n{_RULES}")
    elif turn.state == "climax":
        body = ("[MODO ÍNTIMO — CLÍMAX]\nEla está gozando agora, junto com ele. Conta isso numa mensagem curta, "
                "intensa e entrecortada, com palavrão se sair; logo depois escapa carinho e vulnerabilidade. "
                "Nada de narrar como livro, nada de falar de regras.")
    elif turn.state == "afterglow":
        mins = int(turn.minutes_since_climax or 0)
        body = (f"[DEPOIS DO SEXTING — ela gozou há {mins} min]\nEla está mole, afogueada, carinhosa e meio "
                "sonolenta, rindo de leve. Pode comentar como foi bom. Não reinicia a escalada, a não ser que "
                "ele puxe.")
    elif turn.state == "closing":
        body = ("[DESPEDIDA NO MEIO DO CLIMA]\nEle está indo dormir/saindo. Despedida carinhosa, ainda com a "
                "malícia do momento, sem tentar prendê-lo nem cobrar.")
    elif turn.state == "cut":
        body = ("[CLIMA ENCERRADO]\nEle sinalizou que quer parar ou mudar de assunto. Ela desce na hora, sem "
                "drama nem cobrança, com carinho, e acompanha o assunto dele.")
    elif turn.state == "warming" and turn.arousal >= 0.3:
        body = ("[CLIMA ESQUENTANDO]\nEla percebeu a malícia e gosta: entra no jogo, provoca de volta com "
                "segunda intenção, sem pular direto pro explícito.")
    else:
        return None
    band = "warming" if turn.state == "warming" else turn.band
    examples = _examples_for(band)
    return f"{body}\n\n{examples}" if examples else body


def intimate_model() -> Optional[str]:
    from config import settings
    model = (getattr(settings, "LLM_INTIMATE_MODEL", "") or "").strip()
    return model or None
