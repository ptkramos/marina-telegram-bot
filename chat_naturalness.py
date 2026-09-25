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


# ------------------------------------------------------------ abreviações --
# 25/09 (Patrick): de 20 a 25/09 ela escreveu "você" 159 vezes e "vc" nenhuma —
# tudo por extenso é assinatura de IA; gente mistura ("vc" aqui, "você" ali).
# O Patrick quase não abrevia, então a dose é moderada. Decidido na SAÍDA, não
# no prompt (o modelo ignora ou exagera), e as duas formas passam pelo mesmo
# sorteio: se o modelo começar a copiar "vc" do histórico, a taxa não sobe.
ABBREVIATIONS = (
    # (regex da forma cheia OU da abreviada, abreviação, taxa)
    (r"voc[eê]s|vcs", "vcs", 0.35),
    (r"voc[eê]|vc", "vc", 0.35),
    (r"tamb[eé]m|tbm?", "tb", 0.35),
    (r"porque|por que|pq", "pq", 0.35),
    (r"muit[oa]|mto|mt", "mt", 0.30),
    (r"hoje|hj", "hj", 0.35),
    (r"depois|dps", "dps", 0.35),
    (r"comigo|cmg", "cmg", 0.35),
    (r"que|q", "q", 0.06),
    (r"n[aã]o(?=\s+\w)|n(?=\s+\w)", "n", 0.05),   # "não" no fim ("né não") fica
)
ABBREVIATION_SERIOUS_FACTOR = 0.3      # briga, ele doente: escreve mais inteiro
_FULL = {"vcs": "vocês", "vc": "você", "tb": "também", "pq": "porque", "mt": "muito",
         "hj": "hoje", "dps": "depois", "cmg": "comigo", "q": "que", "n": "não"}
_ABBR_RES = [(re.compile(rf"(?<![\w\[])(?:{pat})(?![\w\]])", re.IGNORECASE), ab, rate)
             for pat, ab, rate in ABBREVIATIONS]


def _match_case(model: str, word: str) -> str:
    if model.isupper() and len(model) > 1:
        return word.upper()
    return word[0].upper() + word[1:] if model[:1].isupper() else word


def abbreviate(text: str, *, serious: bool = False) -> str:
    """Abrevia parte das palavras (e desabrevia o excesso), sorteio fixo por fala."""
    if not text:
        return text
    import hashlib
    factor = ABBREVIATION_SERIOUS_FACTOR if serious else 1.0
    counter = [0]

    for regex, ab, rate in _ABBR_RES:
        def swap(m, ab=ab, rate=rate):
            counter[0] += 1
            seed = hashlib.sha256(f"{text}|{ab}|{counter[0]}".encode("utf-8")).hexdigest()[:8]
            short = int(seed, 16) % 1000 < rate * factor * 1000
            word = m.group(0)
            if short:
                return _match_case(word, ab)
            # O modelo abreviou e o sorteio disse que não. "mt" fica: não dá pra saber se era muito ou muita.
            if word.casefold() in (ab, "tbm") and ab != "mt":
                return _match_case(word, _FULL[ab])
            return word
        text = regex.sub(swap, text)
    return text


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


# ------------------------------------------------------- mesma ideia de novo --
# Feedback do Patrick (22/09): "Não repita mensagens como 'se cuida no caminho'
# ou 'vai com calma no caminho' se já tiver falado uma vez no ciclo" e "ser
# repetitiva nos ciclos das conversas é um problema sério". A frase muda, a
# ideia é a mesma — o filtro de trecho repetido não pegava.
IDEAS = {
    "cuidado": re.compile(r"\b(?:se\s+cuida|vai\s+com\s+(?:calma|cuidado|deus)|toma\s+cuidado|cuidado\s+no\s+caminho"
                          r"|vai\s+com\s+cuidado)\b", re.I),
    "avisa_chegar": re.compile(r"\b(?:me\s+avisa|avisa\s+(?:quando|assim\s+que)|me\s+(?:d[aá]|manda)\s+um\s+(?:toque|sinal))"
                               r"[^.!?\n]{0,30}\bcheg", re.I),
    "come_direito": re.compile(r"\b(?:come|almo[çc]a|janta|se\s+alimenta)\s+direitinho\b|\bse\s+alimenta\b", re.I),
    "descansa": re.compile(r"\b(?:descansa(?:\s+um\s+pouco)?|voc[eê]\s+merece\s+(?:esse\s+)?descans)", re.I),
    "saga": re.compile(r"\bsaga\b", re.I),
    # 25/09 (ele com amigdalite): "se piorar, vai no médico" em 3 respostas seguidas.
    "medico": re.compile(r"\b(?:vai|ir|vá|procura|passa)\b[^.!?\n]{0,25}\bm[eé]dic", re.I),
    "hidrata": re.compile(r"\bse\s+hidrat|\b(?:beb[ea]|toma)\s+(?:bastante\s+|muita\s+)?[aá]gua\b", re.I),
}

# 25/09: a mesma ideia com outras palavras ("queria estar aí fazendo carinho na sua cabeça e
# levando um suco geladinho" / "queria te levar um suco geladinho e ficar fazendo carinho nessa
# cabeça dodói") passava pelos dois filtros. Mesma ideia = muitas palavras de conteúdo em comum
# com um trecho de uma fala recente dela, independente da ordem.
_STOP = set("""a o as os um uma uns umas de do da dos das no na nos nas em pra pro pras pros para por com sem
e ou mas que se me te lhe nos vos eu tu ele ela voce vc vcs a gente meu minha meus minhas seu sua seus suas teu tua
isso isto esse essa este esta aquele aquela aqui ai la ja so tambem tb muito mt mais menos bem tao ta to tava
estou esta estar ser foi era sou vai vou ir ter tem tenho fica ficar fico mesmo ainda agora depois hoje entao
nao sim ne amor amorzinho vida bebe meu bem kkk kkkk kkkkk haha pq porque como quando onde quem qual tudo nada
coisa jeito sempre pouco pouquinho ne viu hein ok""".split())
# Medido em 125 falas reais (23–25/09): com 3/0.5 cortava respostas legítimas ("vou topar o
# Quartinho", respondendo a pergunta dele com as palavras da pergunta dela); com 4/0.6 sobram só
# as repetições de verdade. O que escapa daqui fica com o recent_ideas_hint, antes de gerar.
IDEA_OVERLAP_MIN = 4
IDEA_OVERLAP_RATIO = 0.6


def _stems(text: str) -> set:
    return {w[:5] for w in _norm_words(text) if w not in _STOP and len(w) > 2}


def _same_idea(piece: str, previous: Iterable[str]) -> bool:
    mine = _stems(piece)
    if len(mine) < IDEA_OVERLAP_MIN:
        return False
    for old in previous:
        for clause in _clauses(old or ""):
            common = mine & _stems(clause)
            if len(common) >= IDEA_OVERLAP_MIN and len(common) / len(mine) >= IDEA_OVERLAP_RATIO:
                return True
    return False


def repeated_ideas(reply: str, previous: Iterable[str]) -> set:
    """Ideias (cuidado, avisa quando chegar, come direito…) que ela já falou nas últimas falas."""
    said = {name for name, rx in IDEAS.items() for p in previous if rx.search(p or "")}
    return {name for name, rx in IDEAS.items() if name in said and rx.search(reply or "")}


def drop_paraphrased(reply: str, previous: Iterable[str]) -> str:
    """Tira as frases que repetem, com outras palavras, uma ideia das falas recentes dela.
    Se não sobra fala, devolve a resposta como estava."""
    previous = [p for p in previous if p]
    if not previous:
        return reply
    out_lines = []
    for line in reply.split("\n"):
        kept = [s for s in re.split(r"(?<=[.!?…])\s+", line) if s.strip() and not _same_idea(s, previous)]
        joined = " ".join(kept).strip()
        if joined:
            out_lines.append(joined[0].upper() + joined[1:])
    result = "\n".join(out_lines).strip()
    return result if len(_norm_words(result)) >= 3 else reply


def recent_ideas_hint(previous: list[str], limit: int = 2) -> str:
    """Antes de gerar: o que ela acabou de dizer, pra não voltar nisso com outras palavras."""
    recent = [p.replace("\n", " / ").strip()[:220] for p in previous[-limit:] if p and p.strip()]
    if not recent:
        return ""
    return ("[NÃO SE REPITA] Nas suas últimas respostas você já disse: "
            + " | ".join(f"«{r}»" for r in recent)
            + ". Não volte a essas ideias nem com outras palavras (oferta, conselho, carinho, desejo): "
              "diga algo novo ou só reaja ao que ele disse agora.")


def drop_repeated_ideas(reply: str, previous: Iterable[str]) -> str:
    """Tira da resposta o pedaço (frase ou trecho entre vírgulas) que repete uma ideia.
    Se não sobra fala, devolve a resposta como estava."""
    ideas = repeated_ideas(reply, list(previous))
    if not ideas:
        return reply
    rxs = [IDEAS[name] for name in ideas]
    out_lines = []
    for line in reply.split("\n"):
        sentences = re.split(r"(?<=[.!?…])\s+", line)
        kept_sentences = []
        for sentence in sentences:
            original = sentence.split(", ")
            parts = [p for p in original if not any(rx.search(p) for rx in rxs)]
            if len(parts) < len(original):
                # "…quando chegar, tá?" sem o pedido vira um "tá?" pendurado
                parts = [p for p in parts if _norm_words(p) not in (["ta"], ["viu"], ["ok"], ["ne"], ["hein"])]
            text = ", ".join(parts).strip()
            if text and len(_norm_words(text)) > 0:
                if parts and len(parts) < len(sentence.split(", ")) and not re.search(r"[.!?…]$", text):
                    text += "."   # a pergunta/ênfase era do pedaço que saiu
                kept_sentences.append(text)
        joined = " ".join(kept_sentences).strip()
        if joined:
            out_lines.append(joined[0].upper() + joined[1:])
    result = "\n".join(out_lines).strip()
    return result if len(_norm_words(result)) >= 3 else reply


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
