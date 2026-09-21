"""Deterministic bubble segmentation and turn budget for Marina.

Bubble count is NOT capped by policy. Marina emits chat as a single string; this
module then splits that string into Telegram bubbles at natural conversational
pivots (opening interjection, reaction -> question, topic change, length
overflow) and coalesces stray single-word fragments so no bubble is confetti.
The prompt guides Marina toward these same pivots but does not tell her how many
bubbles to use — whatever she genuinely wanted, we deliver, up to a runtime
sanity ceiling (anti-runaway) and Telegram's 4096-code-unit transport limit.
"""
from dataclasses import dataclass, asdict
import logging
import re
import unicodedata

from config import settings

logger = logging.getLogger('ResponseRhythm')


# Anti-runaway ceiling. A healthy WhatsApp turn is rarely more than a handful of
# bubbles; beyond this we fold the tail so a hallucinated burst can't spam the
# user. Not a stylistic rule.
_SANITY_CEILING = 6

# Opening interjections / short laughs that deserve to stand alone as bubble #1
# when Marina emits them followed by more substance. Case-insensitive.
# Kept intentionally narrow: laughs and short exclamations only. Vocatives
# ("amor", "meu bem") are NOT interjections — they are direct address that
# usually belongs with the same beat as the substance.
_INTERJECTION_RE = re.compile(
    r"^(?:k{2,}|hah+a*|hehe+|heh+|nossa+|s[eé]rio\??|caraca|caramba|"
    r"ai+|ah+|opa+|ei+|uau+|eba+|oba+|puts|ixi|ui+|hmm+|ué|uai|"
    r"aff+|aiai|xi+)"
    r"[\s!?.,…]*$",
    re.IGNORECASE,
)

# Conjunctions/openers that mark a natural pivot between two beats when they
# start a follow-up sentence.
_PIVOT_CONJUNCTION_RE = re.compile(
    r"^(?:a[íi]|mas|e vo?c[eê]|e a[íi]|agora|enfim|resumindo|olha,?\s|"
    r"sabia que|adivinha|só que|porém|contudo|entretanto|a propósito|"
    r"aliás|falando nisso)\b",
    re.IGNORECASE,
)


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c))


def _is_interjection(text: str) -> bool:
    return bool(_INTERJECTION_RE.match((text or '').strip()))


@dataclass(frozen=True)
class ResponseStylePolicy:
    mode: str = 'casual_short'
    verbosity: str = 'low'
    # Natural burst energy hint for the LLM. Never a hard cap.
    cadence: str = 'brief'
    # target_bubbles / max_bubbles are retained as ADVISORY fields for callers
    # that still read them (bot.py, logs, tests). segment() no longer treats
    # max_bubbles as a hard cap: Marina decides bubble count within the
    # transport and sanity ceilings.
    target_bubbles: int = 1
    max_bubbles: int = 0
    soft_char_limit: int = 180
    prefer_open_turn: bool = True
    followup_question: str = 'optional'
    voice_soft_seconds: int = 15
    reason_code: str = 'casual_default'

    @property
    def token_budget(self):
        # Safety ceiling, not a length target. Leave room to finish a Portuguese
        # sentence without letting a 180-character casual turn become an essay.
        if self.mode == 'casual_short':
            return max(75, min(95, int(self.soft_char_limit / 2.1)))
        return max(96, min(640, int(self.soft_char_limit / 2) + 32))


def select_policy(message='', *, plan=None, voice=False, storytelling=False,
                  emotional_context=None, batch_size=1,
                  availability_budget_hint: str | None = None):
    plan = plan or {}
    text = normalized(message)
    intent = plan.get('intent', '')
    tone = normalized(str(plan.get('tone', '')))
    mode, reason = 'casual_short', 'casual_default'
    if availability_budget_hint == 'brief_due_to_availability':
        mode, reason = 'casual_short', 'brief_due_to_availability'
    elif re.search(r'\b(detalhadamente|passo a passo|em detalhes|explica|explique|analisa|analise)\b', text):
        mode, reason = 'explanatory', 'explicit_details'
    elif intent in ('relationship_conflict', 'serious', 'urgent') or re.search(
        r'\b(precisamos conversar|terminar nosso namoro|discussao seria|emergencia|urgente)\b', text):
        mode, reason = 'serious', 'serious_context'
    elif storytelling or intent == 'storytelling':
        mode, reason = 'storytelling', 'grounded_story'
    elif intent == 'support_needed' or re.search(
        r'\b(desabafar|to triste|estou triste|foi uma merda|dia horrivel)\b', text):
        mode, reason = 'supportive', 'support_needed'
    elif (intent == 'excited' or tone in ('excited', 'empolgada', 'empolgado')
          or re.search(r'\b(oba|consegui|ganhei|passei|deu certo|finalmente|not[ií]cia boa|novidade boa)\b|!{2,}', text)):
        mode, reason = 'excited', 'excited_context'
    elif intent == 'planning_future' or len(message) > 500 or batch_size > 3:
        mode, reason = 'normal', 'expanded_context'

    # (chars, seconds, verbosity, cadence, target_hint)
    limits = {
        'casual_short':  (settings.RESPONSE_CASUAL_SOFT_CHARS, settings.VOICE_CASUAL_SOFT_SECONDS,     'low',    'brief',     1),
        'normal':        (settings.RESPONSE_NORMAL_SOFT_CHARS, settings.VOICE_NORMAL_SOFT_SECONDS,     'medium', 'flowing',   2),
        'supportive':    (settings.RESPONSE_NORMAL_SOFT_CHARS, settings.VOICE_SUPPORTIVE_SOFT_SECONDS, 'low',    'brief',     1),
        'serious':       (settings.RESPONSE_LONG_SOFT_CHARS,   60,                                    'high',   'flowing',   1),
        'excited':       (settings.RESPONSE_NORMAL_SOFT_CHARS, 25,                                    'medium', 'burst',     2),
        'storytelling':  (settings.RESPONSE_LONG_SOFT_CHARS,   90,                                    'high',   'burst',     3),
        'explanatory':   (settings.RESPONSE_LONG_SOFT_CHARS,   120,                                   'high',   'expansive', 1),
    }
    chars, seconds, verbosity, cadence, target = limits[mode]
    if availability_budget_hint == 'brief_due_to_availability':
        chars = min(chars, settings.RESPONSE_CASUAL_SOFT_CHARS)
        cadence = 'brief'
        target = 1
        verbosity = 'low'
    question = 'required_for_action' if plan.get('needs_clarification') or plan.get('should_offer_reminder') else 'optional'
    if plan.get('followup_question') == 'none' and question == 'optional':
        question = 'not_required'
    if availability_budget_hint == 'brief_due_to_availability' and question == 'optional':
        question = 'not_required'

    policy = ResponseStylePolicy(
        mode=mode,
        verbosity=verbosity,
        cadence=cadence,
        target_bubbles=target,
        max_bubbles=0,          # advisory only; segment() does not cap on this.
        soft_char_limit=max(1, chars),
        prefer_open_turn=True,
        followup_question=question,
        voice_soft_seconds=seconds,
        reason_code=reason,
    )
    logger.info('response_policy.selected mode=%s reason_code=%s cadence=%s voice=%s',
                mode, reason, cadence, voice)
    return policy


_MODE_RULE = {
    'casual_short':
        'Ritmo casual de WhatsApp: no total, uma a três frases curtas de chat; '
        'em geral um balão só, quebra com uma linha nova só quando há um pivô '
        'real (reação e depois pergunta, riso e depois substância, um '
        'pensamento e depois outro claramente diferente).',
    'normal':
        'Ritmo de chat: duas a quatro frases. Quebre balões em pivôs de '
        'assunto reais; caso contrário, fique em um balão só.',
    'supportive':
        'Reaja como a namorada dele em uma frase quente — sem script de '
        'cuidadora, sem promessa genérica de estar disponível. No máximo uma '
        'pergunta real.',
    'serious':
        'Fale com calma e clareza. Nada de teatro, nada de melodrama. Só '
        'quebre balões se a mudança emocional for genuína.',
    'excited':
        'Vai com a energia — rajadas curtas, quebre livre entre reações e '
        'observações. Vários balões curtos são bem-vindos quando a empolgação '
        'é real.',
    'storytelling':
        'Reconte só o que foi explicitamente informado no contexto. Batidas '
        'curtas e sequenciais; vários balões cabem quando a história tem '
        'momentos separados. Sem diálogo, tempo ou gesto inventados.',
    'explanatory':
        'Responda direto em 2 a 4 frases conversacionais (~900 chars). '
        'Explicações longas podem quebrar naturalmente em pivôs de assunto.',
}


def apply_policy(prompt, policy):
    prompt = prompt.split('[RITMO DE RESPOSTA]')[0].split('[RESPONSE RHYTHM]')[0].rstrip()
    # Strip legacy rhythm constraints; style vocabulary remains authoritative.
    lines = prompt.splitlines()
    conflicts = (
        'ritmo: múltiplos balões', 'ritmo: multiplos baloes',
        'múltiplos balões', 'multiplos baloes',
        'concisão absoluta', 'nunca envie redações',
        'varie naturalmente a quantidade de mensagens',
        'máximo de 2 balões', 'maximo de 2 baloes',
        'maximum of 2 bubbles', 'maximum 2 bubbles',
    )
    prompt = '\n'.join(line for line in lines if not any(x in line.casefold() for x in conflicts))
    mode_rule = _MODE_RULE.get(policy.mode, '')
    guidance = [
        '[RITMO DE RESPOSTA]',
        "Responda como Marina. Só quebre em balões separados com quebra de "
        "linha ('\\n') onde a batida realmente muda: interjeição curta antes "
        "da substância (\"kkkk\" e depois a resposta), reação antes de uma "
        "pergunta de acompanhamento, um pensamento antes de outro claramente "
        "diferente. Fora disso, fique em um balão só. Não existe contagem "
        "fixa de balões — mande quantos ou quão poucos o momento realmente "
        "pedir.",
        'Não simule ritmo de digitação picando um pensamento no meio, e não '
        'force um balão só pra parecer humana. Um único riso ou interjeição '
        'pode ser um turno completo sozinho.',
        'Otimize para o próximo turno da conversa, não para completude desta '
        'resposta. Pule tranquilizações prontas ("estou aqui se precisar") e '
        'conselho a menos que este turno peça.',
        'Para saudações, piadas, updates de rotina e reações simples, em '
        'geral termine sem pergunta. Só pergunte quando a resposta importa '
        'agora.',
        'Escreva só o que Marina mandaria no chat: sem direções de cena, '
        'gestos narrados, asteriscos, títulos, listas markdown ou marcadores '
        'de roleplay.',
        'Mantenha o português brasileiro natural que você já usa, sem '
        'inserir gíria, emoji ou palavrão mecanicamente.',
        'Para histórias, descreva só eventos explicitamente informados no '
        'contexto. Sem diálogo, tempo, cenário, gesto ou backstory '
        'inventados. Se faltarem detalhes, uma frase curta e ancorada basta.',
        'Para voz, escreva uma mensagem falada espontânea, não um ensaio. '
        'Perfil vocal não aumenta o orçamento.',
        'Perguntas obrigatórias para uma ação (como agendar lembrete) '
        'seguem prioridade.',
        'Limites soft são orientação, nunca corte uma frase.',
        mode_rule,
        ' '.join(f'{k}={v}' for k, v in asdict(policy).items()),
    ]
    return prompt + '\n' + '\n'.join(guidance)


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

def _coalesce_paragraphs(paragraphs):
    """Merge stray single-word fragments into their neighbor so no bubble is
    confetti. An intentional opening interjection is preserved as its own
    bubble — Marina saying "kkkk" then "nossa amor" IS two bubbles."""
    if not paragraphs:
        return []
    result = [paragraphs[0]]
    for p in paragraphs[1:]:
        prev = result[-1]
        prev_words = len(prev.split())
        p_words = len(p.split())
        # Keep the first bubble standalone if it's an interjection lead — do
        # not merge substance INTO an opening laugh/exclamation.
        opening_interjection = (len(result) == 1 and _is_interjection(prev))
        if not opening_interjection and (p_words == 1 or prev_words == 1):
            result[-1] = f'{prev} {p}'
        else:
            result.append(p)
    return result


def _split_sentences(text):
    """Sentence tokens keeping terminators. Good enough for chat PT-BR."""
    sentences = re.findall(r'[^.!?…]+[.!?…]+|[^.!?…]+$', text)
    return [s.strip() for s in sentences if s.strip()]


def _balanced_split_index(sentences):
    """Index that most evenly splits `sentences` by aggregate char length."""
    total = sum(len(s) for s in sentences)
    best_idx, best_gap = 1, total + 1
    for i in range(1, len(sentences)):
        left = sum(len(s) for s in sentences[:i])
        gap = abs(left - (total - left))
        if gap < best_gap:
            best_gap, best_idx = gap, i
    return best_idx


def _semantic_split(text, policy):
    """Split a single-paragraph prose reply on natural conversational pivots.
    Returns (bubbles, reason_code)."""
    text = text.strip()
    if len(text) < 25:
        return [text], 'too_short'

    sentences = _split_sentences(text)
    if len(sentences) < 2:
        return [text], 'single_sentence'

    # 1) Opening interjection: "kkkk. Hoje foi muito engraçado." -> two bubbles.
    #    If there is a further closing question, promote it to a third bubble.
    if _is_interjection(sentences[0]) and len(sentences) >= 2:
        rest = sentences[1:]
        if len(rest) >= 2 and rest[-1].rstrip().endswith('?') and not rest[0].rstrip().endswith('?'):
            return (
                [sentences[0], ' '.join(rest[:-1]).strip(), rest[-1].strip()],
                'interjection_then_question',
            )
        return [sentences[0], ' '.join(rest).strip()], 'interjection_lead'

    # 2) Statement(s) -> closing question: "Que legal amor. Como foi?" -> two.
    if sentences[-1].rstrip().endswith('?') and not sentences[0].rstrip().endswith('?'):
        statement = ' '.join(sentences[:-1]).strip()
        question = sentences[-1].strip()
        if len(statement) >= 4:
            return [statement, question], 'question_pivot_tail'

    # 3) Mid-turn question mark separating declarative from follow-up.
    for i, s in enumerate(sentences[:-1]):
        if s.rstrip().endswith('?') and i > 0:
            first = ' '.join(sentences[:i + 1]).strip()
            rest = ' '.join(sentences[i + 1:]).strip()
            return [first, rest], 'question_pivot_mid'

    # 4) Excited / storytelling: burst cadence even without a strong pivot.
    if policy.mode in ('excited', 'storytelling') and len(sentences) >= 2:
        # For a story with clear sequential beats, one bubble per beat trio.
        if policy.mode == 'storytelling' and len(sentences) >= 3:
            third = max(1, len(sentences) // 3)
            return (
                [
                    ' '.join(sentences[:third]).strip(),
                    ' '.join(sentences[third:2 * third]).strip(),
                    ' '.join(sentences[2 * third:]).strip(),
                ],
                'storytelling_beats',
            )
        idx = _balanced_split_index(sentences)
        first = ' '.join(sentences[:idx]).strip()
        rest = ' '.join(sentences[idx:]).strip()
        return [first, rest], f'{policy.mode}_burst'

    # 5) Conjunctive pivot at sentence start ("mas", "aí", "e você", "agora"…).
    for i in range(1, len(sentences)):
        if _PIVOT_CONJUNCTION_RE.match(sentences[i]):
            first = ' '.join(sentences[:i]).strip()
            rest = ' '.join(sentences[i:]).strip()
            if len(first) >= 12 and len(rest) >= 8:
                return [first, rest], 'conjunctive_pivot'

    # 6) Length overflow. A very long turn (>2x soft) with enough sentences
    # gets 3 bubbles; a moderately long one gets 2.
    if len(text) > policy.soft_char_limit:
        if len(text) > policy.soft_char_limit * 2 and len(sentences) >= 4:
            third = max(1, len(sentences) // 3)
            return (
                [
                    ' '.join(sentences[:third]).strip(),
                    ' '.join(sentences[third:2 * third]).strip(),
                    ' '.join(sentences[2 * third:]).strip(),
                ],
                'length_balance_3',
            )
        idx = _balanced_split_index(sentences)
        first = ' '.join(sentences[:idx]).strip()
        rest = ' '.join(sentences[idx:]).strip()
        return [first, rest], 'length_balance'

    # 7) No pivot, comfortable length: one coherent bubble.
    return [text], 'coherent_single'


def _apply_transport_limit(parts):
    """Respect Telegram's 4096 UTF-16 code-unit ceiling per message. Prefer
    whitespace boundaries so words are not cut mid-way."""
    result = []
    for part in parts:
        while len(part.encode('utf-16-le')) // 2 > 4096:
            stop = 0
            units = 0
            for char in part:
                units += 2 if ord(char) > 0xffff else 1
                if units > 4096:
                    break
                stop += 1
            boundary = max(part.rfind('\n', 0, stop + 1), part.rfind(' ', 0, stop + 1))
            cut = boundary if boundary > 0 else stop
            result.append(part[:cut])
            part = part[cut:].lstrip()
        if part:
            result.append(part)
    return result


def segment(text, policy):
    """Turn Marina's raw reply into a list of Telegram-ready chat bubbles.

    Marina decides bubble count. This function only enforces:
      - coalescing of stray single-word fragments (anti-confetti),
      - a sanity ceiling against runaway generation,
      - Telegram's 4096-code-unit hard transport limit.
    When Marina emits explicit \n between beats, those are respected. When she
    emits prose, natural conversational pivots (interjection, reaction ->
    question, topic change, length overflow) determine bubble boundaries.
    """
    text = text.replace('\\n', '\n').strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]

    if len(paragraphs) > 1:
        coalesced = _coalesce_paragraphs(paragraphs)
        if len(coalesced) > 1:
            bubbles, reason = coalesced, 'llm_newlines'
        else:
            # Everything collapsed into a single coherent thought — keep the
            # original text (its internal \n is a soft line break inside one
            # Telegram bubble, not a separate message).
            bubbles, reason = [text], 'llm_newlines_coalesced'
    else:
        bubbles, reason = _semantic_split(paragraphs[0], policy)

    # Anti-runaway sanity ceiling. Fold the tail into the last kept bubble so
    # nothing is lost.
    if len(bubbles) > _SANITY_CEILING:
        head = bubbles[: _SANITY_CEILING - 1]
        tail = ' '.join(bubbles[_SANITY_CEILING - 1:])
        bubbles = head + [tail]
        reason = f'{reason}+sanity_fold'

    result = _apply_transport_limit(bubbles)
    logger.info(
        'response_policy.segmented mode=%s bubbles=%d chars=%d reason=%s',
        policy.mode, len(result), len(text), reason,
    )
    return result


def log_output(text, policy, *, voice=False):
    if len(text) > policy.soft_char_limit * 2:
        logger.info(
            'response_policy.override reason_code=soft_limit_exceeded mode=%s chars=%d',
            policy.mode, len(text),
        )
    if voice:
        logger.info('voice.duration_estimated seconds=%.1f', len(text.split()) / 2.5)


def needs_verbosity_retry(text, policy):
    """Allow one rewrite only when the draft greatly exceeds the soft budget."""
    return bool(text and policy and len(text) > policy.soft_char_limit * 2)


def verbosity_retry_constraint(text, policy):
    """Build a bounded rewrite request without truncating the draft."""
    return (
        "Your draft is much longer than this conversational turn warrants. "
        f"Rewrite it as Marina in natural Brazilian Portuguese, aiming for about "
        f"{policy.soft_char_limit} characters. "
        "Keep the one essential reaction or answer, preserve any necessary fact, "
        "and end complete sentences. Do not mention editing, limits, drafts, "
        "policies, or these instructions. Return only the replacement message.\n"
        "[DRAFT TO REWRITE]\n" + text
    )
