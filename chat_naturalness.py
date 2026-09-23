"""Naturalidade de chat — o que denuncia o bot mesmo quando a fala está boa.

Conversa com o Patrick de 22–23/09 (Luna):

* **Ponto final de fechamento.** "Tá bom, amor, vou comer direitinho sim." —
  no WhatsApp ninguém fecha balão com ponto; ele só aparece entre frases.
  `strip_closing_periods` (na resposta do turno, antes de gravar e enviar,
  pra o histórico também ensinar o modelo) tira o ponto do fim de cada linha e mantém o
  ponto que separa frases, as reticências e o "?"/"!".
* **Repetição da própria fala.** 13:05 e 13:07 saíram com a mesma frase
  ("agora você consegue beijar sem esse aparelho te sabotando"). O penalty do
  modelo não enxerga turnos anteriores. `repeated_run` acha um trecho de 6+
  palavras já dito nas últimas falas; `drop_repeated` corta a frase repetida
  quando sobra fala; senão o bot pede uma reescrita.
* **"amor" em todo turno.** Vocativo em toda resposta vira tique.
  `thin_vocative` tira o "amor" de enfeite quando os dois turnos anteriores
  já tinham.
* **Ela só reage.** O dia dela acontece (Theo, Júlia, almoço na Gávea) e ela
  nunca conta — o Patrick tem que perguntar. `share_nudge` escolhe, de vez em
  quando, uma coisa do dia que ela ainda não contou pra ela puxar sozinha.
* **Responder no meio do raciocínio.** Ele manda 5 balões sobre a mesma coisa
  e ela responde no 2º. O Telegram não avisa bot de "digitando…", então a
  janela de espera é lida do próprio texto: `debounce_delay`.

Nada aqui chama LLM ou rede.
"""
from __future__ import annotations

import json
import random
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Iterable, Optional


def _norm_words(text: str) -> list[str]:
    t = unicodedata.normalize("NFD", (text or "").casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", t)


# ------------------------------------------------------------ ponto final --
_CLOSING_PERIOD_RE = re.compile(r"(?<![.\s])\.(?!\.)(?=[ \t]*(?:[^\w\s.]{0,4}[ \t]*)?$)", re.MULTILINE)


def strip_closing_periods(text: str) -> str:
    """Tira o ponto que FECHA o balão/linha; o que separa frases fica.

    "Tá bom. Vou jantar agora." -> "Tá bom. Vou jantar agora"
    "Descansa, tá? 🖤" / "Hmm..." -> inalterados
    "Vou jantar agora. 😘" -> "Vou jantar agora 😘"
    """
    if not text:
        return text
    return _CLOSING_PERIOD_RE.sub("", text)


# -------------------------------------------------------------- repetição --
REPEAT_MIN_WORDS = 6
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")


def repeated_run(reply: str, previous: Iterable[str], *, min_words: int = REPEAT_MIN_WORDS) -> Optional[str]:
    """Primeiro trecho de `min_words`+ palavras da resposta que já saiu antes."""
    words = _norm_words(reply)
    if len(words) < min_words:
        return None
    seen = set()
    for old in previous:
        w = _norm_words(old)
        seen.update(tuple(w[i:i + min_words]) for i in range(len(w) - min_words + 1))
    for i in range(len(words) - min_words + 1):
        gram = tuple(words[i:i + min_words])
        if gram in seen:
            return " ".join(gram)
    return None


def _clauses(text: str) -> list[str]:
    # "…" no meio da fala também separa ("...sabotando… então vou cobrar")
    parts = re.split(r"(?<=[.!?…])\s+|\n+|…\s*", text)
    return [p.strip() for p in parts if p and p.strip()]


def drop_repeated(reply: str, previous: Iterable[str], *, min_words: int = REPEAT_MIN_WORDS) -> Optional[str]:
    """Corta as frases repetidas. None se o que sobra não é uma fala."""
    previous = list(previous)
    kept = [c for c in _clauses(reply) if not repeated_run(c, previous, min_words=min_words)]
    rest = " ".join(kept).strip()
    if len(_norm_words(rest)) < 4:
        return None
    return rest[0].upper() + rest[1:]


def repetition_constraint(run: str) -> str:
    return ("[TURN CONSTRAINT — NÃO SE REPITA]\n"
            f"Você já disse isto há pouco: \"{run}\". Repetir a própria frase denuncia que "
            "não é uma pessoa. Responda de novo ao Patrick com outras palavras e outra "
            "ideia — reaja ao que ele acabou de dizer, sem reaproveitar frases suas.")


# ---------------------------------------------------------------- vocativo --
_VOCATIVE_RE = re.compile(r",\s*amor(?=\s*[,.!?…]|\s*$)|^amor,\s*|(?<=[.!?…]\s)amor,\s*",
                          re.IGNORECASE | re.MULTILINE)


def thin_vocative(reply: str, previous: list[str]) -> str:
    """Se as duas últimas falas já tinham "amor", esta sai sem o vocativo."""
    last = previous[-2:]
    if len(last) < 2 or not all(re.search(r"\bamor\b", p, re.IGNORECASE) for p in last):
        return reply
    out = _VOCATIVE_RE.sub("", reply)
    out = re.sub(r"(^|\n)\s*([a-zà-ÿ])", lambda m: m.group(1) + m.group(2).upper(), out)
    return out if len(_norm_words(out)) >= 2 else reply


# ------------------------------------------------------ contar do dia dela --
SHARE_KEY = "share_nudge_json"
SHARE_MIN_TURNS = 5             # falas dela desde a última vez que puxou assunto próprio
SHARE_MIN_GAP = timedelta(minutes=20)
SHARE_CHANCE = 0.5
SHARE_INTENTS = {"casual_chat", "sharing_day", "question", "planning_future", "other"}
SHARE_WITHIN = timedelta(hours=6)


def share_nudge(db, now: datetime, *, intent: Optional[str], rng=random) -> Optional[dict]:
    """Uma coisa do dia dela que ainda não contou, se é hora de puxar."""
    if intent not in SHARE_INTENTS:
        return None
    raw = db.get_estado_relacional(SHARE_KEY)
    try:
        last = json.loads(raw).get("at") if raw else None
    except (TypeError, ValueError, AttributeError):
        last = None
    if last:
        if now - datetime.fromisoformat(last) < SHARE_MIN_GAP:
            return None
        with db.get_connection() as conn:
            turns = conn.execute("SELECT COUNT(*) FROM conversas WHERE role='assistant' AND timestamp>?",
                                 (last,)).fetchone()[0]
        if turns < SHARE_MIN_TURNS:
            return None
    chance = SHARE_CHANCE
    try:
        # Fase D14d: empolgada ou se divertindo, ela conta mais coisas do dia.
        from emotion import EmotionEngine
        if any(e.family == "alegria" and e.intensity >= 0.3 for e in EmotionEngine(db).episodes(now)):
            chance = min(0.8, chance + 0.2)
    except Exception:
        pass
    if rng.random() >= chance:
        return None
    from social_day import SocialDay
    news = SocialDay(db).fresh_news(now, within=SHARE_WITHIN)
    if not news:
        return None
    return news


def mark_nudged(db, now: datetime, event_key: str) -> None:
    from social_day import SocialDay
    SocialDay(db).mark_shared(event_key)
    db.set_estado_relacional(SHARE_KEY, json.dumps({"at": now.isoformat(), "event": event_key}))


def share_constraint(news: dict) -> str:
    return ("[TURN CONSTRAINT — SUA VIDA TAMBÉM ENTRA NA CONVERSA]\n"
            "Namorada de verdade não espera ser perguntada pra contar do dia. Depois de "
            "reagir ao que o Patrick disse, puxe naturalmente esta coisa SUA, com suas "
            f"palavras e seu jeito (sem soar relatório, sem data/hora): {news['summary']}\n"
            "Se o que ele disse pede toda a sua atenção, guarde isso pra depois e não conte.")


# ------------------------------------------------------ esperar ele terminar --
DEBOUNCE_MIN_S = 3.0
DEBOUNCE_MAX_S = 14.0
_UNFINISHED_END_RE = re.compile(
    r"(?:[,:;\-–]|\.\.\.?|…|\b(?:e|mas|porque|pq|que|tipo|a[ií]|ent[aã]o|s[oó]\s+que|ou|pra|com|de|do|da|"
    r"no|na|o|a|um|uma|quando|se|sabe)\b)\s*$", re.IGNORECASE)
_CLOSED_END_RE = re.compile(r"[?!]\s*$|[\U0001F300-\U0001FAFF☀-➿]\s*$|\b(?:k[ks]{2,}|haha+|rs+)\s*$",
                            re.IGNORECASE)


def debounce_delay(messages: list[str], base: float) -> float:
    """Quanto esperar depois da última bolha do Patrick antes de responder.

    O Telegram não conta pro bot que ele está digitando, então a pista é o texto:
    bolha que termina pendurada ("e", "porque", vírgula, "...") ou curtinha no
    meio de uma rajada quer dizer que vem mais; pergunta, risada ou emoji no fim
    fecham o raciocínio.
    """
    last = (messages[-1] if messages else "").strip()
    delay = max(base, 6.0)
    if _UNFINISHED_END_RE.search(last):
        delay += 6.0
    elif _CLOSED_END_RE.search(last):
        delay = max(base, DEBOUNCE_MIN_S) if len(messages) == 1 else delay - 1.5
    if len(messages) >= 2:
        delay += 2.0          # rajada: costuma vir mais uma
    if len(_norm_words(last)) <= 3 and not _CLOSED_END_RE.search(last):
        delay += 1.5
    return max(DEBOUNCE_MIN_S, min(DEBOUNCE_MAX_S, delay))
