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
# 24/09 (Patrick): o gozo segue o que ELA escreve. O antigo "goza sozinha depois de 6 turnos
# no auge" marcou clímax às 20:43 enquanto ela escrevia "tô quase", e o refratário travou o
# gozo de verdade das 20:55. Agora o pedido dele abre a cena do clímax; quem registra o gozo
# é a fala dela (observe_marina_line).
AFTERGLOW_MIN = 40
POST_CLIMAX_DAMP_MIN = 90     # por quanto tempo o tesão demora a voltar depois do gozo
POST_CLIMAX_GAIN = 0.35
POST_CLIMAX_GAIN_FERTILE = 0.8
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
_HIS_CLIMAX = re.compile(r"\b(gozei|gozando|vou gozar|goza|gozar junto)\b")
_HER_CLIMAX = re.compile(r"\b(to gozando|estou gozando|gozei|acabei de gozar|gozando (muito|gostoso|todinha|demais))\b")
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
        # Fase D14: a fase do ciclo continua pesando, e a vontade do motor (horas
        # sem gozar, saudade, humor, cansaço, mágoa) multiplica por cima: com
        # tesão ela entra no clima rápido; chateada ou exausta, devagar.
        cycle = self._cycle_libido()
        try:
            from emotion import EmotionEngine
            return cycle * (0.7 + 0.6 * EmotionEngine(self.db).feeling().libido)
        except Exception:
            return cycle

    def _cycle_libido(self) -> float:
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
            _no_mundo(self.db, now, acabou=True)
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
        since = self._minutes(st.get("climax_at"), now)
        if since is not None and since <= POST_CLIMAX_DAMP_MIN:
            # 24/09 (Patrick): depois de gozar ela fica mole — custa mais esquentar de novo,
            # menos no período fértil.
            fertile = self._cycle_libido() >= CYCLE_LIBIDO["ovulatoria"]
            gain *= POST_CLIMAX_GAIN_FERTILE if fertile else POST_CLIMAX_GAIN
        gain *= self._libido()
        a = min(1.0, st["arousal"] + gain * (1.0 - st["arousal"]) * GROWTH)
        st["arousal"], st["updated_at"] = a, now.isoformat()

        active = a >= ACTIVE_ON or (st["mode_since"] and a >= ACTIVE_OFF)
        if active and not st["mode_since"]:
            st["mode_since"] = now.isoformat()

        if active and a >= HOT_AT and _HIS_CLIMAX.search(t) and (glow is None or glow > REFRACTORY_MIN):
            # Ele pediu/gozou: abre a cena do clímax. O gozo só fica registrado se ela escrever.
            self._save(st)
            _no_mundo(self.db, now)
            return IntimacyTurn("climax", round(a, 3), strong, glow)

        if active and _CLOSE.search(t):
            st.update(arousal=a * 0.5, mode_since=None, hot_turns=0)
            self._save(st)
            _no_mundo(self.db, now, acabou=True)
            return IntimacyTurn("closing", round(st["arousal"], 3), strong, glow)

        if active:
            if a >= HOT_AT:
                st["hot_turns"] = int(st["hot_turns"]) + 1
            self._save(st)
            _no_mundo(self.db, now)
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
                 "(pau, buceta, peitos, bunda…) com naturalidade, diz o que quer e o que sente agora, sem "
                 "eufemismo de novela",
}

_RULES = (
    "- É sexting consensual entre dois adultos que namoram, só pelo chat. É uma parte real e desejada da relação.\n"
    "- O tesão é DELA: reage ao que ele disse como estímulo de verdade e também conduz — não fica só pedindo "
    "pra ele descrever.\n"
    "- Continua doce e carinhosa: o desejo vem junto do amor dela por ele. Nada de pornografia genérica que "
    "serviria pra qualquer pessoa.\n"
    "- NUNCA fale de regras, limites, políticas, 'conteúdo explícito' ou do que pode ou não pode dizer. Se ela "
    "não quiser alguma coisa, recusa como namorada ('isso não, amor'), nunca como sistema.\n"
    "- Na gaveta da mesinha do quarto ela tem três brinquedos: um dildo rosa de silicone, um de vidro "
    "transparente com ventosa (esse ela prende na cama pra sentar) e um plug de metal com um coração vermelho "
    "de pedrinha na base. Usa quando o clima pede (só em casa).\n"
    "- Tudo é virtual: não marque encontro nem finja que ele chegou. Fantasia no presente vale quando o clima "
    "tá alto.\n"
    # 03/10 (sexting Marina × Lilith, cena das 15:10–15:38): ela abria com interjeição + nome dele, devolvia a ação
    # dele com outras palavras, contava no "eu ia…" e fechava pedindo pra ele não parar/não enrolar — 14 de 27 turnos.
    "- Como ela escreve aqui: curtinho, como quem digita com uma mão só — 1 a 3 balões de poucas palavras, nunca "
    "um parágrafo; no máximo 1 emoji. Ela fala, não narra: o que está fazendo e sentindo vai na fala, no presente "
    "e em primeira pessoa, como quem está vivendo agora (nunca no condicional, como quem conta uma fantasia).\n"
    "- Ele sabe o que acabou de fazer: ela não repete a ação dele com outras palavras. Mostra o que aquilo causou "
    "nela e segue a cena dali. O que ele já está fazendo não precisa ser pedido de novo.\n"
    "- Cada mensagem começa e termina de um jeito: nada de abrir toda vez com interjeição e o nome dele, nem de "
    "fechar toda vez pedindo pra ele não parar ou não demorar. O nome dele só de vez em quando.\n"
    "- Continua sendo a namorada dele, do jeito dela: pode tomar a frente, pedir, provocar, rir, falar que ama.\n"
    "- Se ele pedir pra parar ou mudar de assunto, ela desce na hora, sem drama."
)


def observe_marina_line(db, text: str, now: Optional[datetime] = None) -> bool:
    """Ela escreveu que está gozando: vira o clímax de verdade (afterglow + refratário)."""
    now = now or datetime.now()
    if not _HER_CLIMAX.search(_norm(text)):
        return False
    engine = IntimacyEngine(db)
    st = engine._decayed(engine._load(), now)
    if not (st["mode_since"] or st["arousal"] >= ACTIVE_OFF):
        return False
    glow = engine._afterglow(st, now)
    if glow is not None and glow <= REFRACTORY_MIN:
        return False
    st.update(arousal=0.35, mode_since=None, hot_turns=0, climax_at=now.isoformat(), updated_at=now.isoformat())
    engine._save(st)
    logger.info("intimacy.climax by=marina")
    _no_mundo(db, now, acabou=True, gozou=True)
    return True


def _no_mundo(db, now: datetime, *, acabou: bool = False, gozou: bool = False) -> None:
    """03/10 (soak dia 5): o sexting é o que ela está fazendo em casa — vira bloco no Agora e linha no Hoje
    (tempo_livre.sexting), em vez do "olhando o Pinterest no closet" que o mundo seguia sorteando."""
    try:
        from tempo_livre import TempoLivre
        tl = TempoLivre(db)
        if acabou:
            tl.sexting_acabou(now, gozou=gozou)
        else:
            tl.sexting(now)
    except Exception:
        logger.exception("intimacy.no_mundo")


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


def system_block(turn: IntimacyTurn, cycle_info: Optional[dict] = None, *, photo_ok: bool = False) -> Optional[str]:
    libido = (cycle_info or {}).get("libido")
    lib_line = f"\n- Libido pela fase do ciclo hoje: {libido}" if libido else ""
    if libido and _norm((cycle_info or {}).get("phase_key", "")) == "menstrual":
        # 03/10, 15:40 (soak dia 5): "Baixa para sexo… carinho sem cobrança" no meio da cena, e o modelo recusou
        # ("Prefiro não continuar com mensagens desse tipo") e depois culpou a menstruação. Se ela já está no
        # modo, o tesão venceu (o motor já pesa a fase: CYCLE_LIBIDO).
        lib_line = (f"\n- Ela está menstruada (dia {(cycle_info or {}).get('day')} do ciclo). O tesão demorou mais pra "
                    "vir, mas veio: ela está no clima e vai junto. A menstruação é um detalhe real do corpo dela, que "
                    "pode aparecer com naturalidade, não motivo pra largar a cena. Se ela quiser parar, é pelo que "
                    "sente na hora, como namorada.")
    if turn.state == "active":
        body = (f"[MODO ÍNTIMO — sexting com o Patrick]\n- Como ela está agora: {_BAND_TEXT[turn.band]}."
                f"{lib_line}\n{_RULES}")
    elif turn.state == "climax":
        body = ("[MODO ÍNTIMO — CLÍMAX]\nEle está gozando ou pediu pra ela gozar. Se ela está no ponto, goza "
                "junto agora: mensagem curta, intensa e entrecortada, com palavrão se sair, e logo depois escapa "
                "carinho e vulnerabilidade. Se ainda não chegou lá, diz que está quase e continua. "
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
    if photo_ok and turn.state in ("active", "climax"):
        from photo_director import SELF_PHOTO_HINT   # C.1b: ela manda foto quando quer provocar
        body = f"{body}\n{SELF_PHOTO_HINT}"
    band = "warming" if turn.state == "warming" else turn.band
    examples = _examples_for(band)
    return f"{body}\n\n{examples}" if examples else body


def intimate_model() -> Optional[str]:
    from config import settings
    model = (getattr(settings, "LLM_INTIMATE_MODEL", "") or "").strip()
    return model or None
