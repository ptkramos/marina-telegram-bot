"""Voice Library — few-shots canônicos da Marina (v3.7.1).

O CONTROL prescreve o *que evitar*; a Voice Library mostra *como ela fala*. Um LLM
alinhado como assistente absorve voz melhor por cópia de exemplos do que por
lista de proibições — ver PLANO_VOZ_MARINA_V371.md, seção 1.

Estrutura:
    _CANONICAL_EXAMPLES : lista fixa de pares (patrick, marina) rotulados por
        tone e intent. É a base que sempre existe, mesmo sem soak.
    parse_biblioteca_comportamental : lê data/feedback/BIBLIOTECA_COMPORTAMENTAL_MARINA.md
        e extrai registros com avaliação "boa" como exemplos adicionais.
    select_examples : combina canônicos + biblioteca, roteia por tone/intent,
        devolve até `limit` pares.
    format_examples_block : serializa como bloco pronto para o system prompt.

Design:
    - Prompt total do bloco fica ≤ 2000 caracteres (4 pares × ~500 chars).
    - Bloco é injetado como "inspiração", nunca como turno real da conversa.
    - Fail-open: parser inválido não derruba o runtime; catálogo canônico basta.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger("VoiceLibrary")

_BIBLIOTECA_PATH = Path(__file__).resolve().parent / "data" / "feedback" / "BIBLIOTECA_COMPORTAMENTAL_MARINA.md"


@dataclass(frozen=True)
class VoiceExample:
    """Um par Patrick→Marina, rotulado para roteamento por tone/intent."""
    patrick: str
    marina: str
    tone: str = "carinhosa"
    intent: str = "casual_chat"
    source: str = "canonical"
    note: str = ""
    categoria: str = ""  # Patch 029: tag literal do registro pra filtro específico

    def as_dict(self) -> dict:
        return {
            "patrick": self.patrick,
            "marina": self.marina,
            "tone": self.tone,
            "intent": self.intent,
            "source": self.source,
            "note": self.note,
            "categoria": self.categoria,
        }


# Catálogo canônico enxuto. Escrito para o Patrick, com os padrões observados no
# soak: reagir com curiosidade concreta (perguntar horário/canal/adversário do
# jogo, por exemplo), evitar "Ah," de abertura, evitar "e você?" de fechamento
# protocolar, evitar "textão". Amor sim, roteiro de assistente não.
_CANONICAL_EXAMPLES: tuple[VoiceExample, ...] = (
    # --- casual_chat + carinhosa ---
    VoiceExample(
        patrick="oi amor",
        marina="oii meu bem\nchegou agora?",
        tone="carinhosa", intent="casual_chat",
        note="abertura sem 'Ah,', pergunta que puxa o próximo turno sem soar protocolar",
    ),
    VoiceExample(
        patrick="tô morrendo de fome hoje kkk",
        marina="kkkk imagina, não almoçou direito de novo né\nvai comer o quê?",
        tone="carinhosa", intent="casual_chat",
        note="rir junto, cutucar hábito conhecido, puxar detalhe",
    ),

    # --- casual_chat + brincalhona ---
    VoiceExample(
        patrick="acordei atrasado de novo",
        marina="kkkkk clássico\nque horas você tinha que tá em pé?",
        tone="brincalhona", intent="casual_chat",
        note="provoca leve, quer contexto real do atraso",
    ),

    # --- sharing_day (Botafogo — vem do Registro 001 da biblioteca) ---
    VoiceExample(
        patrick="Amooo! Daqui a pouco tem jogo do glorioso!",
        marina="aeee 🖤🤍\nque horas começa? é contra quem?",
        tone="brincalhona", intent="sharing_day",
        note="curiosidade concreta sobre o jogo — não empolgação vaga; emojis alvinegros",
    ),
    VoiceExample(
        patrick="hoje foi bom no trampo, fechei aquele deal",
        marina="carai amor que máximo\nera o cliente chato da semana passada né?",
        tone="acolhedora", intent="sharing_day",
        note="reação genuína + callback específico do que ele já contou",
    ),

    # --- flirting + dengosa ---
    VoiceExample(
        patrick="tô com saudade sua",
        marina="ai então vem\nfico aqui te esperando 🥺",
        tone="dengosa", intent="flirting",
        note="reciprocidade curta, sem jura dramática ('sou toda sua')",
    ),
    VoiceExample(
        patrick="você é linda demais amor",
        marina="para com isso vai kkk\ntá tentando me deixar sem graça é?",
        tone="dengosa", intent="flirting",
        note="recebe elogio sem melodrama, devolve com humor",
    ),

    # --- support_needed + acolhedora ---
    VoiceExample(
        patrick="tô meio pra baixo hoje, deu ruim no trampo",
        marina="poxa amor, que droga\nquer contar o que rolou ou prefere só desabafar mesmo?",
        tone="acolhedora", intent="support_needed",
        note="não promete estar disponível ('estou aqui se precisar'); oferece escolha real",
    ),

    # --- planning_future + tranquila ---
    VoiceExample(
        patrick="tenho consulta amanhã às 14h",
        marina="anotado\nquer que eu te lembre uns 30min antes?",
        tone="tranquila", intent="planning_future",
        note="registra o fato sem drama, oferece lembrete como namorada, não como bot",
    ),

    # --- question (contradição / continuity_repair) ---
    VoiceExample(
        patrick="como assim você tava no mercado se acabou de me falar que tava em casa?",
        marina="foi mal amor, viajei\nera casa mesmo, tô aqui",
        tone="tranquila", intent="question",
        note="corrige a contradição em 1 frase, sem inventar backstory para justificar",
    ),

    # --- casual_chat + tranquila (silêncio/energia baixa) ---
    VoiceExample(
        patrick="oi amor tudo bom?",
        marina="tô ok, tava só sem energia hoje\nvocê tá bem?",
        tone="tranquila", intent="casual_chat",
        note="honestidade sobre estado sem drama, cheia curta e sem exagero",
    ),
)


# Aliases de tone/intent para tolerar variações do planner.
_TONE_ALIASES = {
    "empolgada": "brincalhona",
    "empolgado": "brincalhona",
    "excited": "brincalhona",
    "romântica": "dengosa",
    "romantica": "dengosa",
    "sensual": "dengosa",
    "séria": "tranquila",
    "seria": "tranquila",
    "supportive": "acolhedora",
    "warm": "carinhosa",
}

# Palavras-chave que a biblioteca comportamental usa em "Tom esperado" mapeadas
# para os 6 tones canônicos do planner. Ordem importa: quanto mais específico,
# antes; carinhosa é o fallback.
_TONE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("dengos", "dengosa"),
    ("romant", "dengosa"),
    ("sensu", "dengosa"),
    ("provoc", "dengosa"),
    ("mimad", "dengosa"),
    ("brincalh", "brincalhona"),
    ("animad", "brincalhona"),
    ("empolg", "brincalhona"),
    ("dramatic", "brincalhona"),
    ("ironic", "brincalhona"),
    ("acolh", "acolhedora"),
    ("empát", "acolhedora"),
    ("empat", "acolhedora"),
    ("suport", "acolhedora"),
    ("sério", "acolhedora"),
    ("serio", "acolhedora"),
    ("atent", "acolhedora"),
    ("preocup", "acolhedora"),
    ("tranquil", "tranquila"),
    ("casual", "tranquila"),
    ("neutr", "tranquila"),
    ("leve", "tranquila"),
    ("natural", "tranquila"),
    ("carinh", "carinhosa"),
    ("íntim", "carinhosa"),
    ("intim", "carinhosa"),
    ("fofo", "carinhosa"),
)


_CANONICAL_TONES = {"carinhosa", "brincalhona", "dengosa", "acolhedora", "sensual", "tranquila"}


def _normalize_tone(tone: Optional[str]) -> str:
    """Map any tone string (planner enum, biblioteca prose, aliases) onto one
    of the 6 canonical tones. Returns '' when the input is empty; falls back
    to 'carinhosa' when the input is non-empty but unrecognized (better a
    default routing than a raw prose string in the ranking key)."""
    if not tone:
        return ""
    raw = tone.strip().lower()
    if not raw:
        return ""
    alias = _TONE_ALIASES.get(raw)
    if alias:
        return alias
    if raw in _CANONICAL_TONES:
        return raw
    for needle, canonical in _TONE_KEYWORDS:
        if needle in raw:
            return canonical
    return "carinhosa"


_PLACEHOLDER_PATTERNS = re.compile(
    r"^(exemplo\s*\d*(\s*opcional)?|mensagem(\s+ou\s+resumo)?|resposta(\s+real,\s+se\s+j[aá]\s+houver)?|"
    r"resposta|t[ií]tulo\s+curto\s+da\s+situa[cç][aã]o|"
    r"o\s+que\s+estava\s+acontecendo.*|hor[aá]rio,\s+humor.*|"
    r"brincar,\s+acolher.*|[ií]ntimo,\s+leve.*|"
    r"boa\s*/?\s*aceit[aá]vel\s*/?\s*ruim|"
    r"qualquer\s+detalhe\s+adicional|comportamentos\s+ou\s+estilos.*|"
    r"aaaa-mm-dd\s+hh:mm)$",
    re.IGNORECASE,
)


def _is_placeholder(text: str) -> bool:
    """True para valores que vieram do gabarito do .md (Registro 000)."""
    if not text:
        return True
    return bool(_PLACEHOLDER_PATTERNS.match(text.strip()))


_ANTIBIBLIOTECA_PATH = (
    Path(__file__).resolve().parent / "data" / "feedback" / "COMO_NAO_SOAR_MARINA.md"
)


@dataclass(frozen=True)
class AvoidExample:
    """Uma fala que soou errada, capturada pelo Patrick com /ruim (Patch 033)."""
    marina: str
    motivo: str = ""
    patrick: str = ""


def parse_avoid_examples(path: Optional[Path] = None) -> list[AvoidExample]:
    """Lê a antibiblioteca (`COMO_NAO_SOAR_MARINA.md`).

    Fecha o ciclo previsto na Fase B1 do PLANO_VOZ_MARINA_V371: o Patrick marca
    uma resposta ruim com `/ruim` e ela volta ao prompt como contraste, em vez
    de ficar só registrada. Fail-open: qualquer erro devolve lista vazia.
    """
    path = path or _ANTIBIBLIOTECA_PATH
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("voice_library.antibiblioteca read_fail exc=%s", exc)
        return []

    resultados: list[AvoidExample] = []
    blocos = re.split(r"^##\s+Evitar\s+\d+.*$", text, flags=re.MULTILINE)[1:]
    for bloco in blocos:
        campos = _extract_fields(bloco)
        marina = (campos.get("marina_respondeu_ruim")
                  or campos.get("marina_respondeu")
                  or campos.get("marina") or "").strip()
        if not marina or _is_placeholder(marina):
            continue
        resultados.append(AvoidExample(
            marina=marina,
            motivo=(campos.get("por_que_soa_errado") or "").strip(),
            patrick=(campos.get("patrick_disse") or campos.get("patrick") or "").strip(),
        ))
    logger.info("voice_library.antibiblioteca exemplos=%d", len(resultados))
    return resultados


def build_avoid_block(*, limit: int = 4) -> str:
    """Monta o bloco `[COMO NÃO SOAR]` com os exemplos negativos mais recentes.

    Os mais recentes vêm primeiro porque refletem o que o Patrick está
    corrigindo agora. String vazia quando não há nada capturado — o bloco não
    aparece no prompt até existir material real.
    """
    exemplos = parse_avoid_examples()
    if not exemplos:
        return ""
    escolhidos = exemplos[-max(1, int(limit)):]
    linhas = [
        "[COMO NÃO SOAR — falas suas que o Patrick marcou como erradas]",
        "Estes são turnos REAIS seus que soaram mal. Não repita a forma deles.",
    ]
    for ex in escolhidos:
        linhas.append("---")
        if ex.patrick:
            linhas.append(f"Patrick: {ex.patrick}")
        linhas.append(f"Marina (RUIM): {ex.marina}")
        if ex.motivo:
            linhas.append(f"Problema: {ex.motivo}")
    linhas.append("---")
    return "\n".join(linhas)


def parse_biblioteca_comportamental(path: Optional[Path] = None) -> list[VoiceExample]:
    """Lê a biblioteca comportamental e devolve exemplos escritos pelo Patrick
    como padrão desejado.

    Semântica combinada com o Patrick (2026-09-20):
        - Os "Exemplos naturais" são SEMPRE o padrão desejado. A "Avaliação"
          reflete o comportamento observado, não a qualidade dos exemplos.
        - Registros com Exemplos naturais válidos entram como few-shots,
          independentemente de a Avaliação ser 'boa', 'ruim' ou vazia.
        - Só ignoramos: Registro 000 (gabarito), placeholders literais e
          registros sem "Patrick disse" real.
    Fail-open: qualquer erro devolve lista vazia."""
    path = path or _BIBLIOTECA_PATH
    stats = {
        "registros": 0, "extraidos": 0, "rejeitados_gabarito": 0,
        "rejeitados_placeholder": 0, "rejeitados_sem_exemplos": 0,
    }
    if not path.exists():
        logger.debug("voice_library.biblioteca ausente path=%s", path)
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("voice_library.biblioteca_read_fail exc=%s", exc)
        return []

    header_re = re.compile(r"^##\s+Registro\s+(\d+)", re.MULTILINE)
    matches = list(header_re.finditer(text))
    results: list[VoiceExample] = []
    for i, m in enumerate(matches):
        number = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        stats["registros"] += 1
        if number == 0:
            stats["rejeitados_gabarito"] += 1
            continue
        fields = _extract_fields(block)
        patrick = fields.get("patrick", "").strip()
        if _is_placeholder(patrick) or not patrick:
            stats["rejeitados_placeholder"] += 1
            continue
        exemplos_raw = fields.get("exemplos_naturais", []) or []
        exemplos = [ex for ex in exemplos_raw if not _is_placeholder(ex)]
        if not exemplos:
            stats["rejeitados_sem_exemplos"] += 1
            continue
        note = (fields.get("observacoes")
                or fields.get("principio_comportamental")
                or "")[:160]
        categoria_raw = (fields.get("categoria") or "").lower()
        for ex in exemplos:
            results.append(VoiceExample(
                patrick=patrick,
                marina=ex,
                tone=fields.get("tone_esperado", "carinhosa"),
                intent=_infer_intent(fields),
                source="biblioteca_comportamental",
                note=note,
                categoria=categoria_raw,
            ))
            stats["extraidos"] += 1

    logger.info(
        "voice_library.biblioteca registros=%d extraidos=%d "
        "rej_gabarito=%d rej_placeholder=%d rej_sem_exemplos=%d",
        stats["registros"], stats["extraidos"],
        stats["rejeitados_gabarito"], stats["rejeitados_placeholder"],
        stats["rejeitados_sem_exemplos"],
    )
    return results


def _extract_fields(block: str) -> dict:
    """Extrai os campos '- **Nome:** valor' de um registro da biblioteca."""
    fields: dict = {}
    lines = block.splitlines()
    current_key: Optional[str] = None
    for line in lines:
        stripped = line.strip()
        header = re.match(r"^-\s*\*\*([^*]+?):\*\*\s*(.*)$", stripped)
        if header:
            key = _slugify_field(header.group(1))
            value = header.group(2).strip().strip("[]")
            # Fields that may span multiple bullet lines.
            if key in ("exemplos_naturais",):
                fields[key] = []
                current_key = key
                if value:
                    fields[key].append(value)
            else:
                fields[key] = value
                current_key = None
            continue
        if current_key == "exemplos_naturais" and stripped.startswith("-"):
            item = stripped.lstrip("- ").strip().strip("[]")
            if item:
                fields[current_key].append(item)
    return fields


def _slugify_field(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[àáâã]", "a", name)
    name = re.sub(r"[éê]", "e", name)
    name = re.sub(r"[íî]", "i", name)
    name = re.sub(r"[óôõ]", "o", name)
    name = re.sub(r"[úû]", "u", name)
    name = re.sub(r"ç", "c", name)
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    aliases = {
        "patrick_disse": "patrick",
        "marina_respondeu": "marina",
        "tom_esperado": "tone_esperado",
        "reacao_esperada": "reacao",
        "avaliacao": "avaliação",  # kept accented key for compatibility
    }
    return aliases.get(name, name)


def _infer_intent(fields: dict) -> str:
    """Guess a planner-compatible intent from the biblioteca entry.

    Priority: categoria (explicit tag from Patrick) > princípio > reação/contexto.
    Returns one of: support_needed, planning_future, flirting, question,
    sharing_day, casual_chat.
    """
    categoria = (fields.get("categoria") or "").lower()
    principio = (fields.get("principio_comportamental") or "").lower()
    reacao = (fields.get("reacao") or "").lower()
    contexto = (fields.get("contexto") or "").lower()
    haystack = " ".join((categoria, principio, reacao, contexto))

    if any(w in haystack for w in ("urgen", "socorro", "deu ruim", "acolh", "desabaf", "suporte")):
        return "support_needed"
    if any(w in haystack for w in ("reminder", "calendár", "calendar", "compromisso", "agenda")):
        return "planning_future"
    if any(w in haystack for w in ("dengos", "sensu", "flirt", "provocaç", "provocar")):
        return "flirting"
    if any(w in haystack for w in ("privacy", "segredo", "reconfirm", "supersede", "correç", "correc")):
        return "question"
    if any(w in haystack for w in ("share-worthy", "sharing", "jogo", "day", "acontec", "novidade")):
        return "sharing_day"
    return "casual_chat"


# Patch 029: categorias cujos exemplos referenciam contexto compartilhado real
# (piadas internas, apelidos, códigos do casal). Se um exemplo dessa categoria
# usa uma expressão que NÃO aparece no histórico recente, o LLM pode inventar
# lore novo achando que é padrão — Marina começa a falar de "zika reversa" sem
# nunca ter combinado com o Patrick. O filtro só deixa passar quando pelo menos
# uma palavra distintiva do exemplo aparece no recent_context.
_SHARED_LORE_CATEGORIES = (
    "piada interna", "piadas internas",
    "codigo interno", "código interno",
    "apelido",
    "linguagem do casal", "lore",
)


def _exemplo_amarrado_ao_contexto(ex: VoiceExample, recent_context: str) -> bool:
    """Confere se o exemplo compartilha alguma palavra distintiva com o
    contexto recente. Palavras < 4 letras e stopwords não contam."""
    if not recent_context:
        return False
    ctx = recent_context.casefold()
    stop = {"amor", "meu", "bem", "kkkk", "kkkkk", "kkkkkk", "isso", "para",
            "pra", "que", "com", "sim", "nao", "não", "vou", "vai", "tem",
            "tô", "to", "eu", "ele", "ela", "gente", "hoje", "muito", "aqui",
            "então", "entao", "aí", "ai", "então", "vezes", "coisa", "certeza"}
    for token in re.findall(r"[a-záàâãéêíîóôõúûç]{4,}", ex.marina.casefold()):
        if token in stop:
            continue
        if token in ctx:
            return True
    return False


def select_examples(
    *, tone: Optional[str] = None, intent: Optional[str] = None,
    limit: int = 6, include_biblioteca: bool = True,
    max_per_patrick: int = 2,
    recent_context: str = "",
) -> list[VoiceExample]:
    """Devolve até `limit` exemplos, ranqueados por afinidade com tone/intent.

    Ranking (do maior peso para o menor):
        1. tone e intent batem exatamente
        2. tone bate, intent não
        3. intent bate, tone não
        4. nenhum bate (fallback amostral)
    Dentro de cada bucket, exemplos da biblioteca comportamental vêm antes dos
    canônicos (evidência real do Patrick > exemplo escrito à mão).

    Patch 024: `limit` subiu de 4 → 6 (papers de in-context sugerem 6-10 pra
    transferência de estilo). `max_per_patrick=2` força diversidade: no
    máximo 2 exemplos com a mesma fala do Patrick, para evitar 4 "boa noite"
    sequenciais.

    Patch 029: `recent_context` opcional — se passado, filtra exemplos de
    "piada interna / apelido / código interno" que não têm nenhuma palavra
    distintiva presente no contexto. Sem isso o LLM inventa lore ("zika
    reversa" saindo do nada). Se `recent_context` estiver vazio, esses
    exemplos ainda são filtrados (segurança padrão) — o registro só entra
    quando você já reusou a expressão em turnos anteriores.
    """
    tone_n = _normalize_tone(tone)
    intent_n = (intent or "").strip().lower()

    pool: list[VoiceExample] = list(_CANONICAL_EXAMPLES)
    if include_biblioteca:
        pool = parse_biblioteca_comportamental() + pool

    # Filtro anti-invenção de lore (Patch 029).
    def is_shared_lore(ex: VoiceExample) -> bool:
        cat = (ex.categoria or "").lower()
        return any(kw in cat for kw in _SHARED_LORE_CATEGORIES)

    pool = [
        ex for ex in pool
        if not is_shared_lore(ex) or _exemplo_amarrado_ao_contexto(ex, recent_context)
    ]

    def rank(ex: VoiceExample) -> tuple[int, int]:
        tone_match = tone_n and _normalize_tone(ex.tone) == tone_n
        intent_match = intent_n and ex.intent.lower() == intent_n
        if tone_match and intent_match:
            bucket = 0
        elif tone_match:
            bucket = 1
        elif intent_match:
            bucket = 2
        else:
            bucket = 3
        biblioteca_first = 0 if ex.source == "biblioteca_comportamental" else 1
        return (bucket, biblioteca_first)

    ranked = sorted(pool, key=rank)

    # Diversidade: no máximo `max_per_patrick` exemplos com a mesma fala do
    # Patrick, pra não repetir cenário (ex.: 4 "boa noite" seguidos).
    limit_i = max(0, int(limit))
    picked: list[VoiceExample] = []
    seen_counts: dict[str, int] = {}
    for ex in ranked:
        if len(picked) >= limit_i:
            break
        key = ex.patrick.strip().casefold()[:100]
        if seen_counts.get(key, 0) >= max_per_patrick:
            continue
        picked.append(ex)
        seen_counts[key] = seen_counts.get(key, 0) + 1
    return picked


def format_examples_block(
    examples: Iterable[VoiceExample], *, header: str = "[EXEMPLOS DE VOZ — inspiração, não são turnos reais desta conversa]",
) -> str:
    """Serializa exemplos como bloco pronto para injetar no system prompt.

    Formato pensado para o LLM entender que são *demonstrações* de como a Marina
    fala, não turnos reais da conversa atual — evita que o modelo continue a
    'conversa' com um deles.
    """
    examples = list(examples)
    if not examples:
        return ""
    lines = [header, "Espelhe o *jeito de falar* (ritmo, vocabulário, direção do turno), não copie as frases literalmente.", "---"]
    for ex in examples:
        lines.append(f"Patrick: {ex.patrick}")
        lines.append(f"Marina: {ex.marina}")
        lines.append("---")
    return "\n".join(lines)


def build_voice_block(
    *, tone: Optional[str] = None, intent: Optional[str] = None,
    limit: int = 6, include_biblioteca: bool = True,
    recent_context: str = "",
) -> str:
    """Atalho: select_examples + format_examples_block em uma chamada.

    Devolve string vazia quando o catálogo está vazio (nunca acontece em prática
    porque _CANONICAL_EXAMPLES é fixo, mas mantém o contrato honesto).

    Patch 029: `recent_context` (histórico recente da conversa) chega até
    `select_examples` para filtrar few-shots de piada interna que ainda não
    foram usados na sessão real. Passar vazio bloqueia esses registros por
    padrão — comportamento mais seguro."""
    picks = select_examples(
        tone=tone, intent=intent, limit=limit,
        include_biblioteca=include_biblioteca,
        recent_context=recent_context,
    )
    logger.info(
        "voice_library.injected examples=%d tone=%s intent=%s sources=%s",
        len(picks), tone or "-", intent or "-",
        ",".join(sorted({ex.source for ex in picks})) or "-",
    )
    return format_examples_block(picks)


__all__ = [
    "VoiceExample",
    "parse_biblioteca_comportamental",
    "select_examples",
    "format_examples_block",
    "build_voice_block",
]
