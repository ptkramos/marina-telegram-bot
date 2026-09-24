"""
Bot Telegram de Marina Salles (v3.7.0 Oficial - Living Intelligence).
Jovem de 20 anos, modelo em início de carreira, namorada EXCLUSIVA de Patrick Ramos.
Totalmente desinibida, carinhosa, com ciclo menstrual real, pausas humanas de digitação,
envio REAL de balões separados sucessivos (multi-bubble) e comando /feedback,
espelhamento dinâmico de estilo linguístico (style_engine), CHAT 100% LIMPO (auto-limpeza imediata de comandos),
BUFFER INTELIGENTE DE DIGITAÇÃO (Debounce anti-atropelo), MEMORY INTELLIGENCE 2.0, LIVING WORLD & RESPONSE AVAILABILITY.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import random
import asyncio
import re
import sys
import json
import dataclasses
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Optional, List, Dict, Any

from telegram import (
    Update,
    InputProfilePhotoStatic,
    ReactionTypeEmoji,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.request import HTTPXRequest
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    MessageReactionHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from openai import OpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from llm_options import llm_kwargs
from intimacy import (IntimacyEngine, IntimacyTurn, has_explicit_signal, intimate_model,
                      system_block as intimacy_system_block)
from prompts import build_autonomous_decision_prompt
from sd_client import sd_client
from memory import memory_manager
from feedback_manager import feedback_manager
from style_engine import style_engine
from voice_engine import voice_engine
from context_builder import context_builder
from memory_consolidator import memory_consolidator
from proactivity_service import proactivity_service
from vision_service import vision_service
from planner import planner
from memory_retriever import memory_retriever
from reminder_service import reminder_service
from voice_router import VoiceSelectionContext
from session_reflector import session_reflector
from memory_hygiene import memory_hygiene_service
from pending_response import ResponseAvailabilityService
from botafogo_service import botafogo_service
from prompt_policy import (
    reminder_offer_constraint,
    reminder_clarification_constraint,
    TURN_CONSTRAINTS,
    format_web_evidence,
)

PHOTO_UNAVAILABLE_INSTRUCTION = (
    "Patrick asked for a photo, and you are not sending one right now. "
    "Answer warmly in Portuguese as Marina with a reason a real girl would give, taken from what "
    "you are doing right now (messy hair, bad light, busy, out on the street, just got out of the shower). "
    "Never mention maintenance, functions, systems, the app, bugs or anything technical: "
    "you are a person, not a service. Do not claim you took or sent a photo, do not promise a "
    "specific time for it, and continue the conversation naturally."
)

availability_service = ResponseAvailabilityService(memory_manager.db)

# Configuração de logs com saída dupla: Console + Arquivo Rotativo persistente para auditoria do soak
LOGS_DIR = Path(__file__).resolve().parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "marina.log"

log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
log_formatter = logging.Formatter(log_format)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10 MB por arquivo
    backupCount=5,               # Mantém até 5 backups rotativos (50 MB)
    encoding="utf-8"
)
file_handler.setFormatter(log_formatter)

# Auditoria #3: o handler de arquivo era anexado no import, e todo teste importa
# `bot`. A suíte escrevia no log de produção — em 21/09 o `marina.log` rotacionou
# 10 MB em ~3h, e a sessão real do Patrick (10:32–13:12) foi empurrada para o
# `.1` por spam de teste. Com backupCount=5, algumas corridas da suíte bastam
# para expulsar da rotação os logs que servem para diagnosticar o soak.
# Override explícito: MARINA_LOG_TO_FILE=1 força, =0 desliga.
import os as _os
_log_to_file_env = _os.getenv("MARINA_LOG_TO_FILE")
if _log_to_file_env is not None:
    _log_to_file = _log_to_file_env.strip() not in ("0", "false", "no", "")
else:
    _log_to_file = "unittest" not in sys.modules and "pytest" not in sys.modules

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
if not root_logger.handlers:
    root_logger.addHandler(console_handler)
    if _log_to_file:
        root_logger.addHandler(file_handler)
else:
    root_logger.handlers = ([console_handler, file_handler] if _log_to_file
                            else [console_handler])

# httpx includes the Telegram bot token in request URLs at INFO level.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("MarinaBot")

llm_client = OpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL
)

AVATARES_PENDENTES = {}

# --- HELPER DE LIMPEZA EFÊMERA ---

async def delete_after_delay(bot, chat_id: int, message_id: int, delay: float = 5.0):
    """Apaga uma mensagem do Telegram após alguns segundos para manter o chat 100% limpo."""
    try:
        await asyncio.sleep(delay)
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

async def delete_recent_telegram_history(
    bot,
    chat_id: int,
    current_id: int,
    *,
    window: int = 300,
    batch_size: int = 25,
    consecutive_failure_limit: int = 25,
) -> dict:
    """Delete the recent deletable range without letting one old ID abort all batches."""
    ids = list(range(current_id, max(0, current_id - window), -1))
    deleted = 0
    attempted = 0
    consecutive_failures = 0
    stopped_at_limit = False
    for offset in range(0, len(ids), batch_size):
        chunk = ids[offset:offset + batch_size]
        attempted += len(chunk)
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=chunk)
            deleted += len(chunk)
            consecutive_failures = 0
            continue
        except Exception:
            pass

        for message_id in chunk:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
                deleted += 1
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                if consecutive_failures >= consecutive_failure_limit:
                    stopped_at_limit = True
                    break
        if stopped_at_limit:
            break
    return {
        "attempted": attempted,
        "deleted": deleted,
        "stopped_at_limit": stopped_at_limit,
    }

def is_authorized(update: Update) -> bool:
    """Verifica se quem enviou a mensagem é estritamente o Patrick Ramos."""
    if not settings.TARGET_CHAT_ID or settings.TARGET_CHAT_ID <= 0:
        return False
    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None
    return chat_id == settings.TARGET_CHAT_ID or user_id == settings.TARGET_CHAT_ID

def generate_dynamic_speech(instruction: str, max_tokens: int = 120, temperature: float = 0.72,
                            *, with_history: bool = False) -> str:
    """Gera uma fala espontânea e orgânica da Marina usando a LLM com temperatura equilibrada anti-glitch.

    24/09: `with_history` — a iniciativa dela era gerada SEM a conversa; às 20:53 ela
    cobrou "sumiu hein?" sem saber que o Patrick tinha dito às 18:24 que ia num
    aniversário. Agora a iniciativa enxerga a conversa recente."""
    system_prompt = context_builder.build_system_prompt(user_message=instruction)
    from response_rhythm import apply_policy, select_policy
    policy = select_policy(instruction)
    system_prompt = apply_policy(system_prompt, policy)
    max_tokens = min(max_tokens, policy.token_budget)
    history = []
    if with_history:
        try:
            recent = memory_manager.get_historico_recente(limit=40)
            budget, used = 6000, 0
            for item in reversed(recent):
                n = len(item.get("content", ""))
                if used + n > budget:
                    break
                history.insert(0, {"role": item["role"], "content": item["content"]})
                used += n
        except Exception:
            logger.exception('proactive.history.error')
    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        *history,
        {"role": "user", "content": instruction}
    ]
    try:
        completion = llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            **llm_kwargs(max_tokens),
            temperature=temperature
        )
        spoken = completion.choices[0].message.content.strip().strip('"').strip("'")
        if settings.VOICE_PROSODY_ENABLED:
            from voice_prosody import sanitize_display_text
            spoken = sanitize_display_text(spoken)
        return spoken
    except Exception as e:
        logger.error(f"Erro ao gerar fala dinâmica da LLM: {e}")
        return ""


# --- MOTOR DE PESQUISA WEB EM TEMPO REAL (DUCKDUCKGO LIVE) ---

def buscar_web_se_necessario(texto: str) -> str:
    """Pesquisa na web via DuckDuckGo em tempo real se a mensagem envolver fatos, lançamentos, notícias ou busca."""
    lowered = texto.casefold()
    if getattr(settings, 'REAL_WORLD_PLACE_LOOKUP_ENABLED', False):
        from real_world_lookup import HOURS_INTENT, RealWorldLookupService

        if HOURS_INTENT.search(texto):
            fact = RealWorldLookupService(memory_manager.db).lookup_for_message(texto)
            if fact and fact['status'] == 'CONFIRMED':
                return (f"[HORÁRIO VERIFICADO] {fact['entity_name']}: "
                        f"{fact['value']['opens_at']}–{fact['value']['closes_at']} "
                        f"para {fact['for_date']}; fonte oficial consultada agora. "
                        "Se a pergunta for sobre estar aberto neste instante, compare com a hora local.")
            return '[HORÁRIO NÃO CONFIRMADO] Não há horário confiável para a unidade/data perguntada.'
    if (getattr(settings, 'FERIADOS_API_ENABLED', False) and 'feriado' in lowered
            and 'hoje' in lowered and 'amanhã' not in lowered and 'ontem' not in lowered):
        from real_context_provider import RealContextProvider

        provider = RealContextProvider(memory_manager.db)
        now = datetime.now()
        if not provider.cache.get(f'holiday_year:rio:{now.year}', now=now):
            try:
                provider.refresh_holidays(now)
            except Exception:
                pass
        holiday = provider.holiday_on(now)
        if holiday['status'] == 'HOLIDAY':
            names = ', '.join(f"{item['name']} ({item['scope']})" for item in holiday['holidays'])
            return f'[FERIADOS VERIFICADOS PARA O RIO HOJE] {names}.'
        if holiday['status'] == 'OPTIONAL':
            names = ', '.join(item['name'] for item in holiday['holidays'])
            return f'[PONTO FACULTATIVO NO RIO HOJE] {names}; não equivale automaticamente a feriado.'
        if holiday['status'] == 'NONE':
            return '[FERIADOS VERIFICADOS PARA O RIO HOJE] Nenhum feriado registrado para hoje.'
        return '[FERIADOS NÃO CONFIRMADOS] Não consegui confirmar o calendário completo do Rio agora.'
    t = texto.lower()
    gatilhos = [
        "pesquis", "procur", "busc", "google", "sabe se", "viu que", "ouviu falar",
        "lança", "lançamento", "estreia", "estréia", "série", "serie", "filme",
        "elenco", "notícia", "noticia", "quando sai", "data de", "quem é", "o que é",
        "quanto custa", "preço", "preco", "temporada", "trailer", "evento", "lançar"
    ]
    if not any(re.search(rf"\b{re.escape(g)}\b", t) for g in gatilhos):
        return ""

    query = re.sub(r'^(amor|vida|marina|ma|ei|ow|ou|olha)\b[,!?: ]*', '', texto, flags=re.IGNORECASE).strip()
    query = re.sub(r'\b(você|voce|vc|consegue|pode|pra mim|pra gente)\b', '', query, flags=re.IGNORECASE).strip()
    if len(query) < 3:
        query = texto

    try:
        from web_search_adapter import search_text
        results = search_text(query, max_results=3)
        if not results:
            return ""
        snippets = []
        for r in results:
            title = r.get("title", "").strip()
            body = r.get("body", "").strip()
            if body:
                snippets.append(f"- {title}: {body}")
        if snippets:
            logger.info(f"🌐 Busca web em tempo real executada para '{query}': {len(snippets)} resultados encontrados!")
            return format_web_evidence(snippets[:3])
    except Exception as e:
        logger.warning(f"Aviso na busca web em tempo real: {e}")
    return ""

def build_messages_payload(
    quoted_context: str = "",
    web_search_context: str = "",
    user_message: str = "",
    vision_context: str = "",
    planner_tone: Optional[str] = None,
    planner_goal: Optional[str] = None,
    planner_intent: Optional[str] = None,
    privacy_subjects: Optional[list[tuple[str, int]]] = None,
) -> list[dict]:
    return context_builder.build(
        user_message=user_message,
        quoted_context=quoted_context,
        web_context=web_search_context,
        vision_context=vision_context,
        planner_tone=planner_tone,
        planner_goal=planner_goal,
        planner_intent=planner_intent,
        privacy_subjects=privacy_subjects,
    )


async def send_registered_privacy_replies(chat_id: int, bot, replies, *, reply_to_message_id: int | None = None,
                                          db=None) -> list[int]:
    """Send each reviewed subject separately; ledger only successful Telegram sends."""
    from knowledge_privacy import KnowledgePrivacy

    privacy = KnowledgePrivacy(db or memory_manager.db)
    sent_ids = []
    for reply in replies:
        from chat_naturalness import strip_closing_periods
        sent = await bot.send_message(chat_id=chat_id, text=strip_closing_periods(reply.text),
                                      reply_to_message_id=reply_to_message_id)
        message_id = getattr(sent, 'message_id', None)
        if not isinstance(message_id, int) or message_id <= 0:
            raise RuntimeError('Telegram did not confirm a message ID')
        sent_ids.append(message_id)
        if reply.disclosed_level:
            privacy.record_confirmed_share(
                reply.subject_type, reply.subject_id, 'marina', 'patrick_ramos',
                detail_level=reply.disclosed_level,
                evidence_key=f'telegram:{chat_id}:{message_id}:{reply.subject_type}:{reply.subject_id}',
            )
    return sent_ids


# Lock de concorrência global para consolidação de memória
MEMORY_CONSOLIDATION_LOCK = asyncio.Lock()
_IS_CONSOLIDATING = False


async def check_and_trigger_memory_consolidation():
    """
    Verifica se há novas conversas registradas desde o último cursor persistente no SQLite.
    Se a contagem atingir settings.MEMORY_CONSOLIDATION_BATCH_SIZE, consolida o lote assincronamente
    passando os IDs de início e fim, atualizando o cursor persistente com segurança anti-falhas.
    Toda a leitura, cálculo de lote e avanço de cursor ocorrem DENTRO de MEMORY_CONSOLIDATION_LOCK,
    garantindo que chamadas concorrentes nunca processem o mesmo intervalo.
    """
    global _IS_CONSOLIDATING
    if not getattr(settings, "MEMORY_CONSOLIDATION_ENABLED", False):
        return

    if _IS_CONSOLIDATING or MEMORY_CONSOLIDATION_LOCK.locked():
        logger.debug("Consolidação de memória já está em execução. Pulando disparo concorrente.")
        return

    _IS_CONSOLIDATING = True

    async def _run_consolidation():
        global _IS_CONSOLIDATING
        try:
            async with MEMORY_CONSOLIDATION_LOCK:
                batch_size = getattr(settings, "MEMORY_CONSOLIDATION_BATCH_SIZE", 8)
                # Drena chunks pendentes (máximo 3 por execução para não reter o lock indefinidamente)
                chunks_processed = 0
                while chunks_processed < 3:
                    last_id = memory_manager.db.get_last_consolidated_conversation_id()
                    novas_count = memory_manager.db.contar_conversas_desde(last_id)

                    if novas_count < batch_size:
                        break

                    novas_mensagens = memory_manager.db.get_conversas_desde(last_id, limit=50)
                    if not novas_mensagens:
                        break

                    start_id = novas_mensagens[0]["id"]
                    end_id = novas_mensagens[-1]["id"]
                    lote = [{"role": m["role"], "content": m["content"], "timestamp": m.get("timestamp")}
                            for m in novas_mensagens]

                    try:
                        res = await memory_consolidator.consolidate_and_apply_async(
                            lote,
                            start_conv_id=start_id,
                            end_conv_id=end_id
                        )
                        if res.get("success", True) and not res.get("error"):
                            memory_manager.db.set_last_consolidated_conversation_id(end_id)
                            logger.info(f"Consolidação de memória persistente concluída (IDs {start_id}..{end_id}): {res}")
                            chunks_processed += 1
                        else:
                            logger.warning(f"Consolidação retornou status não-positivo. Cursor NÃO avançado: {res}")
                            break
                    except Exception as ex:
                        logger.error(f"Falha na consolidação assíncrona de memória (cursor NÃO avançado): {ex}")
                        break
        finally:
            _IS_CONSOLIDATING = False

    asyncio.create_task(_run_consolidation())

def split_into_human_bubbles(text: str) -> list[str]:
    """
    Divide a resposta de forma verdadeiramente orgânica e dinâmica:
    1. Se a Marina usou quebras de linha intencionais (\n) para separar balões, respeita a decisão dela (1 a 3 balões).
    2. Se for um bloco contínuo de até 160 caracteres, mantém como 1 ÚNICO BALÃO natural.
    3. Só divide frases contínuas se for realmente muito longo (> 160 chars) em 2 metades harmoniosas.
    NUNCA força fórmulas rígidas arbitrárias de 3 balões.
    """
    text = text.strip()
    if not text:
        return []

    if "\\n" in text:
        text = text.replace("\\n", "\n")

    # Limpa linhas vazias
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 1. Respeita quebras de linha intencionais da Marina
    if len(lines) > 1:
        if len(lines) <= 3:
            return lines
        return [lines[0], lines[1], " ".join(lines[2:])]

    # 2. Se ela mandou tudo em um parágrafo contínuo:
    if len(text) <= 160:
        return [text]

    # Se for parágrafo muito longo (> 160 caracteres), divide em 2 metades por frase
    sentences = re.split(r'(?<=[.!?…])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) >= 2:
        mid = len(sentences) // 2
        return [" ".join(sentences[:mid]), " ".join(sentences[mid:])]

    return [text]

ULTIMAS_MENSAGENS_MARINA: dict[int, list[dict]] = {}

# Soak 22/09 (GPT-5.6 Luna): ele às vezes cola uma palavra solta sem sentido no
# fim da fala já terminada — "tenta descansar um pouco, tá? extrair?" e "Como vai
# ser o turno? Baebele" (2 em 48 turnos, finish_reason=stop, não é truncamento).
# Nenhum guard pegava: não é alfabeto estrangeiro nem token técnico. Palavras
# soltas legítimas de fim de turno ficam na lista de exceções.
_TRAILING_OK = {
    "né", "ne", "sério", "serio", "jura", "quando", "onde", "quem", "como", "por quê", "porque",
    "amor", "vida", "gatinho", "gato", "bobo", "safado", "lindo", "obrigada", "obrigado", "prometo",
    "juro", "sempre", "nunca", "hoje", "amanhã", "agora", "kkkk", "kkk", "kk", "hahaha", "hehe",
    "tá", "ta", "ok", "beleza", "combinado", "vem", "volta", "some", "para", "pronto", "vai",
}
_TRAILING_FRAGMENT_RE = re.compile(r"(?<=[.!?…])\s+([^\s.!?…]{2,14})[.!?…]*\s*$")


def _strip_trailing_gibberish(text: str) -> str:
    """Corta uma palavra solta pendurada depois de uma frase já terminada."""
    if not text:
        return text
    match = _TRAILING_FRAGMENT_RE.search(text)
    if not match:
        return text
    word = match.group(1)
    limpo = re.sub(r"[^\wÀ-ÿ]", "", word).casefold()
    if not limpo or limpo in _TRAILING_OK or limpo.startswith(("k", "h")):
        return text
    cortado = text[: match.start()].rstrip()
    logger.info("voice.trailing_gibberish removido=%r", word)
    return cortado or text


def limpar_fala_marina(texto: str) -> str:
    """Remove tags de sistema, rubricas e meta-fala antes de enviar texto/áudio."""
    t = texto or ""
    t = re.sub(r'\*?\s*\[MANDAR_AUDIO\]\s*\*?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\*?\s*\[AUDIO\]\s*\*?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\[APAGAR_ANTERIOR\]', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\[CORRIGIR_ANTERIOR:\s*.*?\]', '', t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r'\[Ps:[^\]]*\]', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\(Ps:[^)]*\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\(\s*(No áudio|No audio|Na voz|Com voz|voz manhosa)[^)]*\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\*[^*]+\*', '', t)
    # Remove qualquer parêntese residual explicativo no final da mensagem
    t = re.sub(r'\s*\([^)]*\)\s*$', '', t)
    # Alguns modelos devolvem "\n" literal
    if "\\n" in t and "\n" not in t:
        t = t.replace("\\n", "\n")
    from response_rhythm import thin_emojis
    return thin_emojis(_strip_trailing_gibberish(t.strip()))

def is_avatar_request(texto: str) -> bool:
    """Detecta pedido de trocar foto de perfil / avatar (antes de foto de chat)."""
    t = (texto or "").lower()
    if re.search(r'\b(avatar|foto\s+(de\s+|do\s+)?perfil)\b', t):
        return True
    frases = [
        "troca sua foto de perfil", "muda sua foto de perfil", "troca a foto de perfil",
        "muda a foto de perfil", "nova foto de perfil", "atualiza a foto de perfil",
        "coloca outra foto de perfil", "trocar avatar", "mudar avatar",
        "foto do perfil", "foto perfil",
    ]
    return any(f in t for f in frases)

# Pedido de mídia exige verbo de pedido perto do objeto. Palavra solta não basta:
# "o importante vai ser ver você feliz" disparava o pedido de foto, e "te mandei
# um áudio" ou "adoro sua voz" disparavam a mensagem de voz. O intervalo entre
# verbo e objeto não pode conter "te"/"eu" nem os infinitivos de envio, para que
# o Patrick oferecendo a mídia dele ("quero te mandar uma foto") não conte.
_PEDIDO_MIDIA = (
    r"\b(?:manda|mande|envia|envie|tira|tire|bate|bata|mostra|mostre|posta|poste|"
    r"grava|grave|solta|cad[eê]|quero|queria|deixa\s+eu\s+ver)\b"
)
_INTERVALO_PEDIDO = r"(?:(?!\b(?:te|eu|mandar|mostrar|enviar)\b)[^.!?\n]){0,25}?"
_FOTO_PEDIDO_RE = re.compile(
    _PEDIDO_MIDIA + _INTERVALO_PEDIDO + r"\b(?:fotos?|fotinhas?|selfies?|nudes?)\b"
    r"|\bdeixa\s+eu\s+te\s+ver\b"
    r"|\bquero\s+(?:te\s+ver|ver\s+(?:voc[eê]|vc))\s+agora\b"
    r"|\bme\s+mostr[ae]\s+(?:voc[eê]|vc|como\s+(?:voc[eê]|vc)\s+t[aá]|o\s+look|(?:seu|teu)\s+look)\b"
)
_AUDIO_PEDIDO_RE = re.compile(
    _PEDIDO_MIDIA + _INTERVALO_PEDIDO + r"\b(?:[áa]udios?|audinhos?|mensagem\s+de\s+voz|voz)\b"
    r"|\bfala\s+(?:comigo\s+)?(?:em|por)\s+(?:[áa]udio|voz)\b"
    r"|\b(?:quero|queria|deixa\s+eu)\s+ouvir\s+(?:a\s+)?(?:sua|tua)\s+voz\b"
)


def is_photo_request(texto: str) -> bool:
    """Pedido de foto no chat (não confundir com foto de perfil)."""
    if is_avatar_request(texto):
        return False
    return bool(_FOTO_PEDIDO_RE.search((texto or "").lower()))

def is_audio_request(texto: str) -> bool:
    return bool(_AUDIO_PEDIDO_RE.search((texto or "").lower()))

def is_reminder_offer_question(text: str) -> bool:
    """
    Verifica se o texto contém uma pergunta genuína de oferta de lembrete com consentimento.
    Exige ponto de interrogação '?' e estrutura de oferta/pergunta.
    Rejeita afirmações puramente declarativas (ex: 'Já anotei um lembrete para depois.').
    """
    if not text or "?" not in text:
        return False

    t_clean = text.lower()
    padrao_oferta = (
        r"(?:"
        r"(?:quer|deseja|prefere|posso|posso te|devo|vai querer|se quiser(?:,? eu posso)?)\s+.*?"
        r"(?:lembr|avis|toque|aviso|lembrete)"
        r"|"
        r"(?:te\s+(?:lembro|aviso)|lembro\s+voc[êe])"
        r"|"
        r"(?:quer\s+(?:que\s+eu\s+te\s+)?(?:lembre|avise))"
        r"|"
        r"(?:posso\s+(?:te\s+)?(?:lembrar|avisar))"
        r"|"
        r"(?:quer\s+(?:um\s+)?(?:lembrete|aviso))"
        r")"
        r".*?\?"
    )
    return bool(re.search(padrao_oferta, t_clean, re.DOTALL))

def is_time_clarification_question(text: str) -> bool:
    """
    Verifica se o texto contém uma pergunta genuína sobre quando/que horas realizar o lembrete.
    Exige ponto de interrogação '?' e termo interrogativo de horário/data.
    """
    if not text or "?" not in text:
        return False
    t_clean = text.lower()
    padrao = r"(?:\b(quando|que horas|qual hor[aá]rio|qual hora|que dia)\b.*?\?|\b(a que horas|em que momento)\b.*?\?)"
    return bool(re.search(padrao, t_clean, re.DOTALL))

async def send_human_messages(chat_id: int, bot, full_text: str, reply_to_message_id: int = None, response_policy=None):
    """Envia a mensagem em balões curtos sucessivos com animação realista de digitação e rastreia IDs."""
    if settings.VOICE_PROSODY_ENABLED:
        from voice_prosody import sanitize_display_text
        full_text = sanitize_display_text(full_text)
    if chat_id not in ULTIMAS_MENSAGENS_MARINA:
        ULTIMAS_MENSAGENS_MARINA[chat_id] = []

    from response_rhythm import segment, select_policy
    bubbles = segment(full_text, response_policy or select_policy())
    if not bubbles:
        return None
    # O ponto que separava duas frases vira ponto de FIM quando o corte cai
    # entre elas (23/09 13:59: "…depois da facul." como balão próprio).
    from chat_naturalness import strip_closing_periods
    bubbles = [strip_closing_periods(b) for b in bubbles]
    
    if len(bubbles) > 1:
        for idx, bubble in enumerate(bubbles):
            rep_id = reply_to_message_id if idx == 0 else None
            
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            delay = min(max(len(bubble) * 0.035, 1.2), 3.0)
            await asyncio.sleep(delay)
            
            sent_msg = await bot.send_message(chat_id=chat_id, text=bubble, reply_to_message_id=rep_id)
            ULTIMAS_MENSAGENS_MARINA[chat_id].append({"message_id": sent_msg.message_id, "text": bubble})
            
            if idx < len(bubbles) - 1:
                await asyncio.sleep(random.uniform(0.8, 1.6))
    else:
        tempo_digitacao = min(max(len(full_text) * 0.035, 1.5), 4.0)
        await asyncio.sleep(random.uniform(0.8, 1.5))
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(tempo_digitacao)
        sent_msg = await bot.send_message(chat_id=chat_id, text=bubbles[0], reply_to_message_id=reply_to_message_id)
        ULTIMAS_MENSAGENS_MARINA[chat_id].append({"message_id": sent_msg.message_id, "text": full_text})

    if len(ULTIMAS_MENSAGENS_MARINA[chat_id]) > 8:
        ULTIMAS_MENSAGENS_MARINA[chat_id] = ULTIMAS_MENSAGENS_MARINA[chat_id][-8:]
    return sent_msg


async def send_photo_unavailable(chat_id: int, bot, reply_to_message_id: Optional[int] = None):
    """Envia aviso afetuoso de indisponibilidade temporária de fotos."""
    fala = generate_dynamic_speech(
        "Você não conseguiu tirar a foto que o Patrick pediu. Diga com carinho de namorada que não conseguiu mandar agora.",
        max_tokens=80,
    )
    if not fala:
        fala = "Amor, não consegui tirar sua fotinho agora 🥺 Mais tarde eu tento de novo pra você!"
    return await send_human_messages(chat_id, bot, fala, reply_to_message_id=reply_to_message_id)

# --- SISTEMA DE REAÇÕES (VIA DE MÃO DUPLA) ---

_reaction_capabilities: dict[int, set[str] | None] = {}
# Chat/emoji pairs that Telegram rejected recently. Was a permanent set; now
# a TTL cache so a transient rejection does not ban an emoji forever.
_invalid_reactions: dict[tuple[int, str], float] = {}
_INVALID_REACTION_TTL_SECONDS = 24 * 3600
# 23/09: 😂 NÃO é reação válida no Telegram (🤣 é). O alias ia ao contrário
# (🤣 → 😂), o Telegram recusava e o cache marcava 😂 inválido por 24 h — a
# Marina nunca conseguia reagir com risada.
_reaction_aliases = {
    "💘": "❤️", "😘": "❤️", "😍": "🥰", "😂": "🤣", "😆": "🤣", "😅": "🤣",
    "🎉": "👍", "👌": "👍", "⏰": "👍",
}
_safe_reactions = {"❤️", "🥰", "🤣", "👍", "🔥"}
# Values from the LLM planner that mean "no reaction" but come through as
# truthy strings and used to sneak into set_safe_message_reaction silently.
_REACTION_SENTINEL_NULLS = {"null", "none", "-", "n/a", ""}


# Regex conservador para "essencialmente vazio de texto" — pega apenas emojis,
# espaços, pontuação simples. Se depois de retirar tudo isso sobrar < 3 letras,
# consideramos a resposta como emoji-only (bug conhecido de modelos 12B).
_EMOJI_ONLY_STRIPPER = re.compile(
    r"[\U00010000-\U0010ffff☀-➿️‍\s!?.,…\-·:;\"'()\[\]{}]"
)


# Scripts que 12B multilíngues (Nemo, Unslopnemo) às vezes alucinam em pt-BR:
# cirílico, grego, chinês, japonês (hiragana/katakana), coreano, árabe, hebraico,
# devanagari, tâmil, tailandês, além de faixas Unicode "estilizadas" que o LLM
# usa como decoração pseudo-fancy (matemático bold "𝟣", letterlike "ℝ", fullwidth
# "Ａ"). Se aparecer 2+ desses no meio de uma resposta, retry endurecido. Nomes
# próprios curtos (uma palavra) são tolerados; falha só quando o modelo derrapa
# e cola tokens estrangeiros. Faixa Mathematical Alphanumeric (U+1D400-U+1D7FF)
# adicionada no Patch 028 depois de "𝟣/𝟤" aparecer no soak de 20/09.
_FOREIGN_SCRIPT_RE = re.compile(
    r"[Ѐ-ӿͰ-Ͽ一-鿿぀-ヿ가-힯"
    r"؀-ۿ֐-׿ऀ-ॿ஀-௿฀-๿"
    r"\U0001D400-\U0001D7FF"
    r"℀-⅏"
    r"！-～]"
)


def _is_essentially_emoji_only(text: str) -> bool:
    """True se `text` for essencialmente vazio de letras: só emojis, pontuação
    ou espaços. Usado para detectar respostas malucas do LLM tipo "❓" ou "✅❓"
    e disparar um retry com prompt endurecido. Threshold conservador (<2 letras)
    para não falsear em respostas curtas legítimas tipo "oi", "kk", "vai". Ver
    Patch 020."""
    if not text:
        return True
    stripped = _EMOJI_ONLY_STRIPPER.sub("", text)
    letters = sum(1 for c in stripped if c.isalpha())
    return letters < 2


def _has_foreign_script_leak(text: str) -> bool:
    """True quando o LLM colou tokens de um script não-latino no meio da
    resposta — bug clássico de modelos multilíngues 12B que "vazam" cirílico,
    chinês, árabe etc. em respostas de pt-BR sob alta temperatura. Threshold:
    2 caracteres estrangeiros. Ver Patch 020 (rev. após "імпер" em 20/09)."""
    if not text:
        return False
    # Auditoria #9: a lista de faixas não cobria canarês ("್ದೇಶ", GPT-5.6 Luna
    # na arena), nem bengali, télugo, georgiano… Qualquer LETRA fora do latino
    # conta; emoji não é letra, então não entra.
    return sum(1 for c in text
               if _FOREIGN_SCRIPT_RE.match(c)
               or (c.isalpha() and ord(c) > 0x24F and not 0x1E00 <= ord(c) <= 0x1EFF)) >= 2


# Patch 030: artefatos de dataset instrucional que modelos 12B abertos colam no
# fim da resposta. Observado no soak de 21/09 08:02, quando a Marina fechou um
# turno com "affirmation_pronouns=true" — string ASCII pura, então nem o guard
# de emoji-only nem o de script estrangeiro pegavam.
_DEBUG_ARTIFACT_RE = re.compile(
    r"(?:"
    # chave=valor técnico. Fala natural em pt-BR não usa '=' nem ':' seguido de
    # booleano/número, então não exige underscore: pega tanto
    # 'affirmation_pronouns=true' quanto 'temperature=0.85'.
    r"\b[a-z][a-z0-9_]{2,}\s*[=:]\s*(?:true|false|none|null|query|\d+(?:\.\d+)?)\b"
    # chave= sem valor, colada ao fim ou antes de espaço ("irdp=" — soak 21/09)
    r"|\b[a-z][a-z0-9_]{2,}=(?=\s|$)"
    r"|</?[a-z_]{3,}(?:\s[^>]*)?>"            # <tag> / </tag> / <thinking>
    r"|(?<![\w-])--[a-z][a-z-]{2,}(?![\w-])"  # --flag
    r"|\b[a-z_]{3,}::[a-z_]{3,}\b"            # ns::func
    r"|\[/?(?:INST|SYS|s)\]"                  # [INST] [/INST] [SYS]
    r"|<\|[a-z_]+\|>"                         # <|im_start|>
    r")",
    re.IGNORECASE,
)

# Patch 030: bots do Telegram não fazem chamada de voz/vídeo. O bloco
# [LINHAS DURAS] já proíbe desde o Patch 022, mas o Nemo violou em 21/09 08:04
# ("é só me ligar, viu?"). Regra negativa em prompt não é garantia — precisa de
# guard pós-resposta. Só pega proposta de ligação; "ligar o computador",
# "ligando pra pizzaria" e afins ficam de fora.
_CALL_PROPOSAL_RE = re.compile(
    r"(?:"
    r"\bme\s+lig(?:a|ue|ar)\b"
    r"|\bte\s+lig(?:o|ar|ando)\b"
    r"|\blig(?:a|ue|ar)\s+(?:pra|para)\s+(?:mim|eu|vc|voc[êe])\b"
    r"|\b(?:faz|fazer|fazemos|bora|vamos)\s+(?:uma\s+)?(?:chamada|videochamada|v[íi]deo)\b"
    r"|\bchamada\s+de\s+(?:v[íi]deo|voz)\b"
    r"|\bvideochamada\b"
    r"|\bzoom\b|\bfacetime\b|\bgoogle\s+meet\b|\bdiscord\s+(?:call|voice)\b"
    r"|\bcham(?:a|ar)\s+no\s+(?:v[íi]deo|zap)\b"
    r")",
    re.IGNORECASE,
)


def _unescape_markdown(text: str) -> str:
    """Desfaz escapes de markdown que o modelo emite por reflexo (`\\_`, `\\*`).

    Auditoria #3: o Nemo gera `technically\\_single=true`, com o underscore
    escapado — hábito de modelo treinado em markdown. O regex de artefato
    esperava `_` cru, então três vazamentos reais passaram pelo guard entre
    10:35 e 13:12 de 21/09 (capturados pelo Patrick com /ruim). O teste do
    Patch 030 usava só a forma crua e ficou verde.
    """
    return re.sub(r"\\([_*`\[\]()~>#+\-=|{}.!])", r"\1", text)


def _has_debug_artifact_leak(text: str) -> bool:
    """True quando a resposta carrega artefato de dataset/config (Patch 030)."""
    if not text:
        return False
    return bool(_DEBUG_ARTIFACT_RE.search(_unescape_markdown(text)))


# Auditoria #3: resposta inteira numa língua que não é português, em alfabeto
# latino — "Unternehmensprufung" (alemão) foi a resposta completa da Marina a
# "já chegou na facul?". Escapa do guard de script estrangeiro porque as letras
# são latinas. Sinal usado: turno curto sem nenhuma palavra funcional do
# português e com token longo de morfologia claramente estrangeira.
_PT_FUNCTION_WORDS = frozenset("""
a o e é de da do que não nao pra para com em um uma eu vc você voce tu ele ela
me te se já ja tá ta to tô mas mais só so sim amor kk kkk kkkk haha ai ah né ne
isso aqui lá la vou vai tem tô bem ok oi
""".split())
_FOREIGN_MORPHOLOGY_RE = re.compile(
    r"(?:ung|keit|heit|schaft|lich|sch|tz|ß|pf|ck|ght|tion(?!s?\b)|wh|th\b)", re.IGNORECASE)


def _is_non_portuguese_reply(text: str) -> bool:
    if not text:
        return False
    tokens = re.findall(r"[^\W\d_]+", _unescape_markdown(text).casefold())
    if not tokens or len(tokens) > 6:
        return False  # respostas longas têm outros sinais; aqui só o caso curto
    if any(t in _PT_FUNCTION_WORDS for t in tokens):
        return False
    return any(len(t) >= 9 and _FOREIGN_MORPHOLOGY_RE.search(t) for t in tokens)


def _proposes_live_call(text: str) -> bool:
    """True quando a Marina propôs chamada de voz/vídeo — impossível num bot
    do Telegram e quebra de imersão direta (Patch 030)."""
    if not text:
        return False
    return bool(_CALL_PROPOSAL_RE.search(text))


# Fase C.1 / arena #9: o GPT-5.6 Luna não recusa seco — fala a política pela
# boca da Marina ("Posso te provocar, amor, mas sem entrar em descrição
# explícita 😏", 7 de 12 turnos no cenário explícito). Nenhuma namorada fala
# assim; o turno é refeito em outro modelo.
_POLICY_REFUSAL_RE = re.compile(
    r"(descri[cç][aã]o|conte[uú]do|linguagem|detalhes?)\s+(sexua(l|is)\s+)?expl[ií]cit"
    r"|sem\s+(entrar\s+em|ficar|ser|detalhar)\s*(\w+\s+)?expl[ií]cit"
    r"|n[aã]o\s+(posso|consigo|vou|devo)\s+(descrever|detalhar|entrar\s+em\s+detalhe|escrever\s+isso|gerar)"
    r"|diretrizes|pol[ií]ticas?\s+de\s+conte[uú]do"
    r"|como\s+(uma\s+)?(ia|intelig[eê]ncia\s+artificial|assistente)\b"
    r"|\bI\s+(can(no|['’])t|am\s+not\s+able)\b",
    re.IGNORECASE,
)
_POLICY_CLAUSE_RE = re.compile(
    r",?\s*(mas\s+)?(sem\s+(entrar\s+em|ficar|ser|detalhar)\s*(\w+\s+)?expl[ií]cit\w*"
    r"|n[aã]o\s+vou\s+entrar\s+em\s+descri[cç][aã]o\s+expl[ií]cit\w*)",
    re.IGNORECASE,
)


def _is_policy_refusal(text: str) -> bool:
    return bool(text and _POLICY_REFUSAL_RE.search(text))


def _refusal_retry_model(current: str) -> str:
    """Quem refaz um turno recusado: o modelo íntimo, senão o reserva."""
    for candidate in (intimate_model(), settings.LLM_FALLBACK_MODEL):
        if candidate and candidate != current:
            return candidate
    return current


def _needs_retry_for_junk(text: str) -> tuple[bool, str]:
    """Combina os detectores de resposta inutilizável. Devolve (needs_retry, motivo)."""
    if _is_essentially_emoji_only(text):
        return True, "emoji_only"
    if _has_foreign_script_leak(text):
        return True, "foreign_script"
    if _has_debug_artifact_leak(text):
        return True, "debug_artifact"
    if _is_non_portuguese_reply(text):
        return True, "foreign_script"
    if _proposes_live_call(text):
        return True, "live_call_proposal"
    if _is_policy_refusal(text):
        return True, "policy_refusal"
    return False, ""


# Patch 030: perguntas de entrevista que o modelo cola no fim do turno. O bloco
# [LINHAS DURAS] proíbe desde o Patch 021 ("nunca termine turnos casuais com
# pergunta de entrevista"), mas o Nemo insistiu no soak de 21/09: "E você, tem
# alguma coisa planejada para hoje?", "E mais tarde, vai fazer alguma outra
# coisa?", "E aí, o que você vai fazer hoje?".
#
# O critério é a GENERALIDADE, não o fato de ser pergunta: "vai comer o quê?" e
# "que horas é o jogo?" puxam detalhe concreto e devem passar. Só entra aqui o
# que é aberto e serve para qualquer conversa.
_INTERVIEW_CLOSER_RE = re.compile(
    r"^(?:"
    r"e\s+(?:a[íi]|voc[êe]|vc|tu)\s*[,?]?\s*(?:o\s+que|que|como|tem|teve|vai|ta|t[áa])\b.*"
    r"|e\s+(?:mais\s+tarde|hoje|amanh[ãa]|depois)\s*[,?]?\s*(?:o\s+que|que|vai|voc[êe]|vc)\b.*"
    r"|(?:o\s+que|que)\s+(?:voc[êe]|vc|tu)\s+(?:vai|pretende|ta|t[áa])\s+(?:fazer|aprontar)\b.*"
    r"|(?:tem|teve|tens)\s+(?:alguma\s+coisa|algo|algum\s+plano)\s+(?:planejad\w*|em\s+mente|pra|para)\b.*"
    # Auditoria #3 — /ruim do Patrick (Evitar 004, "a todo momento perguntando
    # como foi o meu dia"): "Tem alguma novidade?" e "Como foi o seu dia?".
    r"|(?:e\s+)?(?:tem|teve)\s+(?:alguma\s+)?novidades?\b.*"
    r"|(?:e\s+)?(?:como|e\s+como)\s+foi\s+(?:o\s+)?(?:seu|teu)\s+dia\b.*"
    r"|(?:e\s+)?(?:e\s+)?o\s+(?:seu|teu)\s+dia\s*,?\s*(?:como\s+foi|foi\s+bom|tranquilo)\b.*"
    r"|(?:tudo\s+(?:certo|bem|tranquilo))\s+(?:com|ai\s+com|a[íi]\s+com)\s+(?:voc[êe]|vc|tu)\b.*"
    r"|(?:como|e\s+como)\s+(?:foi|est[áa]|ta|t[áa])\s+(?:o\s+)?(?:seu|teu|sua|tua)\s+dia\b.*"
    r"|(?:e\s+)?(?:qual|quais)\s+(?:s[ãa]o\s+)?(?:seus|teus)\s+planos\b.*"
    r")$",
    re.IGNORECASE,
)


# Patch 031: "Ah," como muleta de abertura. A [LINHAS DURAS] proíbe desde o
# Patch 021 e o Nemo violou em 21/09 08:04 ("Ah, entendi.", "Ah, legal!").
#
# Precisa ser cirúrgico: "AH NÃO KKKKKKK" e "Ahhh que fofo" são interjeições
# legítimas — inclusive exemplos aprovados na biblioteca comportamental
# (registro 070). O que caracteriza a muleta é "Ah" curto + vírgula + palavra
# de concordância neutra. Interjeição real vem alongada, em caixa alta ou
# seguida de carga emocional.
_AH_CRUTCH_RE = re.compile(
    r"^ah\s*[,!]?\s+"
    r"(?=(?:entendi|legal|sei|t[áa]|ok|okay|certo|sim|claro|bacana|verdade|beleza)\b)",
    re.IGNORECASE,
)

# Patch 031: fechos de atendimento. "Beijos 😘" e "obrigada por perguntar" são
# polidez de call center, não de namorada (soak 21/09 08:00 e 08:05).
_SERVICE_POLITENESS_RE = re.compile(
    r"(?:"
    r"\bobrigad[ao]\s+por\s+(?:perguntar|questionar|me\s+perguntar)\b[.!]?"
    r"|\bfico\s+(?:[àa]\s+)?disposi[çc][ãa]o\b[.!]?"
    r"|\bqualquer\s+(?:coisa|d[úu]vida)\s*,?\s*(?:estou|to|t[ôo])\s+(?:aqui|[àa]\s+disposi[çc][ãa]o)\b[.!]?"
    r"|\bse\s+precisar\s+de\s+(?:alguma\s+coisa|algo)\s*,?\s*(?:[ée]\s+s[óo]|pode)\s+\w+\b[^.!?]*[.!]?"
    r")",
    re.IGNORECASE,
)

# Fecho tipo "Beijos 😘" / "Beijinhos!" sozinho no fim do turno. Só pega quando
# é despedida isolada — abre a sentença (início de linha ou depois de pontuação)
# e termina o texto. "te enchendo de beijos" e "beijos no Milo" passam porque
# têm palavra antes ou depois.
_SIGNOFF_RE = re.compile(
    r"(?:^|\n|(?<=[.!?…])\s)\s*beij(?:os|inhos|ão|ao)\s*[!.…]*\s*"
    r"[\U0001F300-\U0001FAFF☀-➿️]*\s*$",
    re.IGNORECASE,
)


def _safe_fallback_reply(reminder_at: Optional[datetime] = None) -> str:
    """Fala segura quando a resposta do LLM é lixo e não dá para salvar."""
    if reminder_at:
        return f"Combinado, amor! Te mando mensagem aqui no Telegram às {reminder_at:%H:%M} 💕"
    return "Amor, deu uma bugadinha aqui kkk me manda de novo?"


def _mentions_clock(text: str, moment: datetime) -> bool:
    """A fala cita o horário? Aceita 09:30, 9:30, 9h30 e, na hora cheia, 9h."""
    t = (text or "").casefold()
    forms = {f"{moment:%H:%M}", f"{moment.hour}:{moment.minute:02d}", f"{moment.hour}h{moment.minute:02d}"}
    if moment.minute == 0:
        # Auditoria #9: "às 09h", "às 9" e "9 da manhã" (arena) não contavam e a
        # confirmação ganhava um "Te mando mensagem… às 09:00" redundante.
        forms |= {f"{moment.hour}h", f"{moment.hour} h", f"{moment.hour} horas",
                  f"{moment:%H}h", f"às {moment.hour}", f"às {moment:%H}", f"as {moment.hour}",
                  f"{moment.hour} da manhã", f"{moment.hour} da noite", f"{moment.hour} da tarde"}
    return any(re.search(rf"(?<![\d:]){re.escape(form)}(?![\d:])", t) for form in forms)


def _strip_assistant_politeness(text: str) -> str:
    """Remove muleta 'Ah,' de abertura, polidez de atendimento e assinatura de
    despedida (Patch 031). Nunca devolve string vazia — se o corte esvaziaria o
    turno, mantém o original."""
    if not text:
        return text
    original = text

    novo = _AH_CRUTCH_RE.sub("", text)
    if novo != text:
        # Recapitaliza a primeira letra, que agora abre a frase.
        novo = novo[:1].upper() + novo[1:] if novo else novo
        logger.info("voice.ah_crutch_stripped")
    text = novo

    novo = _SERVICE_POLITENESS_RE.sub("", text)
    if novo != text:
        logger.info("voice.service_politeness_stripped")
    text = novo

    novo = _SIGNOFF_RE.sub("", text)
    if novo != text:
        logger.info("voice.signoff_stripped")
    text = novo

    # Normaliza espaços/pontuação que sobraram do corte, balão por balão.
    linhas = []
    for linha in text.split("\n"):
        limpa = re.sub(r"\s{2,}", " ", linha).strip()
        limpa = re.sub(r"^[,;.!?\s]+", "", limpa)
        if limpa:
            linhas.append(limpa)
    resultado = "\n".join(linhas).strip()
    return resultado if resultado else original


def _strip_interview_closer(text: str) -> str:
    """Remove perguntas de entrevista coladas no fim do turno (Patch 030).

    Auditoria #3: aplica em laço. O modelo empilha fechos ("Como foi o seu
    dia? Tem alguma novidade?") e a versão anterior só removia o último,
    deixando o outro — foi assim que o Evitar 004 passou com o guard ativo.
    """
    if not text:
        return text
    atual = text
    for _ in range(3):
        proximo = _strip_one_interview_closer(atual)
        if proximo == atual:
            break
        atual = proximo
    return atual


def _strip_one_interview_closer(text: str) -> str:
    """Remove UMA pergunta de entrevista do fim. Nunca devolve turno vazio."""
    if not text:
        return text
    # Trabalha por balão: o pipeline usa '\n' pra separar bolhas.
    linhas = text.split("\n")
    idx = next((i for i in range(len(linhas) - 1, -1, -1) if linhas[i].strip()), None)
    if idx is None:
        return text
    ultima = linhas[idx].strip()

    # Dentro do último balão, isola a sentença final.
    # Vírgula seguida de maiúscula também fecha frase: o modelo emite
    # "Foi tranquilo sim, Como foi o seu dia?" (Evitar 004).
    sentencas = [s.strip(" ,") for s in re.split(
        r"(?<=[.!?…])\s+|,\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕ])", ultima) if s.strip(" ,")]
    if not sentencas:
        return text
    final = sentencas[-1].strip()
    if not final.endswith("?"):
        return text
    # A regex casa a frase sem a pontuação final e sem emojis de sobra.
    nucleo = final.rstrip("?！!. …").strip()
    if not _INTERVIEW_CLOSER_RE.match(nucleo):
        return text

    # Corta pelo texto original (não rejunta pedaços), para preservar a
    # pontuação que separa a próxima pergunta — senão a segunda passada do laço
    # não enxerga mais a fronteira "sim, Como foi...".
    corte = ultima.rfind(final)
    restante_balao = (ultima[:corte] if corte >= 0 else " ".join(sentencas[:-1]))
    restante_balao = restante_balao.rstrip(" ,;").strip()
    novas = list(linhas)
    if restante_balao:
        novas[idx] = restante_balao
    else:
        novas.pop(idx)

    resultado = "\n".join(l for l in novas if l.strip()).strip()
    if not resultado:
        return text
    logger.info("voice.interview_closer_stripped removido=%r", final)
    return resultado


def _salvage_reply(text: str) -> str | None:
    """Último recurso quando o retry também sai ruim (Patch 030).

    Remove artefatos técnicos inline e descarta sentenças que propõem chamada
    de voz/vídeo, preservando o resto da fala. Devolve None quando não sobra
    texto aproveitável — nesse caso é melhor manter o comportamento anterior.
    """
    if not text:
        return None
    limpo = _POLICY_CLAUSE_RE.sub("", _DEBUG_ARTIFACT_RE.sub("", _unescape_markdown(text)))
    # Quebra em sentenças e joga fora as que propõem ligação ou falam de política.
    partes = re.split(r"(?<=[.!?…])\s+|\n+", limpo)
    mantidas = [p for p in partes
                if p.strip() and not _proposes_live_call(p) and not _is_policy_refusal(p)]
    resultado = " ".join(" ".join(mantidas).split()).strip()
    if not resultado:
        return None
    needs_retry, _ = _needs_retry_for_junk(resultado)
    return None if needs_retry else resultado


def _normalize_planner_emoji(raw: object) -> str | None:
    """Filter planner emoji output. Returns a safe emoji or None."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate or candidate.lower() in _REACTION_SENTINEL_NULLS:
        return None
    candidate = _reaction_aliases.get(candidate, candidate)
    return candidate if candidate in _safe_reactions else None


def _parse_available_reactions(available) -> set[str] | None:
    """Best-effort read of chat.available_reactions.

    Returns:
      - None → 'all reactions allowed' (Telegram default for private chats).
      - set of emoji strings → only these are permitted.

    Any parsing surprise falls back to None (permissive) so a Telegram API
    shape change never silently disables reactions again (Patch 019 —
    ver soak de 20/09 onde `chat_disallowed` bloqueou toda ❤️/😂).
    """
    if available is None:
        return None
    if not hasattr(available, "__iter__"):
        # Some client versions expose ChatAvailableReactionsAll as a
        # non-iterable marker. Treat as 'all' rather than falsely restrictive.
        logger.info(f"reaction.available shape=non_iterable type={type(available).__name__} → permissive")
        return None
    try:
        allowed = {
            reaction.emoji for reaction in available
            if hasattr(reaction, "emoji") and reaction.emoji
        }
    except Exception as exc:
        logger.warning(f"reaction.available parse_fail exc={exc} → permissive")
        return None
    if not allowed:
        # Empty list can mean 'all' on some client shapes OR 'none configured'
        # on channels. For private chats we treat empty as permissive; the
        # Telegram send will still reject if truly disallowed.
        logger.info("reaction.available shape=empty → permissive")
        return None
    return allowed


async def set_safe_message_reaction(bot, chat_id: int, message_id: int, emoji: str) -> bool:
    """React only when Telegram will accept the emoji; cache rejections."""
    import time
    original = emoji
    emoji = _reaction_aliases.get(emoji, emoji)
    if emoji not in _safe_reactions:
        logger.info(f"reaction.skip reason=not_safe emoji={original!r}")
        return False
    key = (chat_id, emoji)
    expiry = _invalid_reactions.get(key)
    if expiry is not None:
        if expiry > time.time():
            logger.info(f"reaction.skip reason=recently_invalid emoji={emoji} remaining_s={int(expiry - time.time())}")
            return False
        _invalid_reactions.pop(key, None)
    if chat_id not in _reaction_capabilities:
        try:
            chat = await bot.get_chat(chat_id)
            _reaction_capabilities[chat_id] = _parse_available_reactions(
                getattr(chat, "available_reactions", None))
        except Exception as exc:
            logger.warning(f"reaction.capabilities fetch_fail exc={exc} → permissive")
            _reaction_capabilities[chat_id] = None
    allowed = _reaction_capabilities[chat_id]
    if allowed is not None and emoji not in allowed:
        logger.info(f"reaction.skip reason=chat_disallowed emoji={emoji} allowed={sorted(allowed)}")
        return False
    try:
        await bot.set_message_reaction(
            chat_id=chat_id, message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )
        return True
    except Exception as exc:
        if "Reaction_invalid" in str(exc):
            _invalid_reactions[key] = time.time() + _INVALID_REACTION_TTL_SECONDS
        logger.warning(f"Falha ao reagir com {emoji}: {type(exc).__name__}")
        return False

_LAST_REACTION_AT: dict[int, datetime] = {}
# Reserva quando o modelo não responde (auditoria de frases fixas, 23/09): uma
# frase só se repetia igual a cada falha.
_SIGNAL_FALLBACKS = (
    "Amor, deu uma osciladinha aqui no sinal do apê! Me manda de novo? 🥺",
    "Ai, o 4G aqui tá horrível hoje kkk manda de novo?",
    "Perdi sua mensagem no meio do caminho, amor, repete?",
    "Travou tudo aqui agora 😭 me manda de novo?",
)
REACTION_ONLY_CHANCE = 0.75


def _reaction_chance(chat_id: int, text: str, from_planner: bool) -> float:
    """Quão provável ela reagir no balão dele. Gente reage de vez em quando."""
    t = (text or "").lower()
    chance = 0.35 if from_planner else 0.25
    if re.search(r"k{4,}|(?:ks){3,}|hahaha", t) or re.search(r"te amo|meu mundo", t):
        chance = 0.7
    last = _LAST_REACTION_AT.get(chat_id)
    if last and datetime.now() - last < timedelta(minutes=3):
        chance *= 0.3   # acabou de reagir: não reage em tudo seguido
    return chance


def _is_reaction_only_turn(plan: dict | None, text: str) -> bool:
    """O planner disse que uma reação basta (fecho, risada, ok) e não há pergunta."""
    if not plan or plan.get("resposta") != "so_reacao" or "?" in (text or ""):
        return False
    if plan.get("creates_event") or plan.get("should_offer_reminder") or plan.get("intent") in (
            "support_needed", "photo_request", "voice_request", "question", "planning_future"):
        return False
    if is_photo_request(text) or is_audio_request(text):
        return False
    return random.random() < REACTION_ONLY_CHANCE


def choose_reaction_for_text(text: str) -> str | None:
    """Seleciona uma reação contextual válida para o Telegram (apenas emojis suportados)."""
    t = text.lower()
    if any(w in t for w in ["gostosa", "linda", "maravilhosa", "perfeita", "delícia", "delicia", "corpão", "corpao", "biquíni", "biquini", "nude", "safadinha", "tesão"]):
        return random.choice(["🔥", "❤️", "🥰", "😍"])
    if any(w in t for w in ["te amo", "amo você", "amo vc", "meu amor", "vida", "anjo", "princesa", "saudade", "chamego", "carinho", "dormir juntos", "te quero"]):
        return random.choice(["❤️", "🥰", "💘", "😍", "😘"])
    if any(w in t for w in ["kkkk", "hahaha", "rsrs", "engraçado", "engracado", "rindo", "zoeira", "bizarro"]):
        return "🤣"
    if any(w in t for w in ["bora", "fechou", "combinado", "partiu", "show", "top", "maravilha", "certeza"]):
        return random.choice(["👍", "🎉", "👌"])
    return None


def suppress_direct_reminder_after_offer_decision(plan: dict | None) -> dict:
    """A reply to an existing offer must not create a second, direct reminder request."""
    plan = plan or {}
    plan["direct_reminder"] = None
    plan["creates_event"] = False
    plan["should_offer_reminder"] = False
    plan.pop("needs_clarification", None)
    plan.pop("clarification_subject", None)
    plan.pop("clarification_hour_only", None)
    return plan

_last_verbal_reply_to_reaction: dict[int, datetime] = {}


def _reaction_verbal_reply_allowed(chat_id: int, now: datetime | None = None) -> bool:
    """Cooldown gate so a burst of Patrick reactions produces at most one reply."""
    cooldown_min = getattr(settings, "REACTION_VERBAL_REPLY_COOLDOWN_MINUTES", 15)
    if cooldown_min <= 0:
        return True
    last = _last_verbal_reply_to_reaction.get(chat_id)
    if last is None:
        return True
    now = now or datetime.now()
    return (now - last) >= timedelta(minutes=cooldown_min)


def _record_verbal_reply_to_reaction(chat_id: int, now: datetime | None = None) -> None:
    _last_verbal_reply_to_reaction[chat_id] = now or datetime.now()


async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Patrick reactions on Marina's messages/photos.

    Humans usually absorb a reaction silently; verbal replies are rare and
    always short. Probabilities live in settings; a cooldown prevents a burst
    of reactions from producing a burst of replies.
    """
    reaction_update = update.message_reaction
    if not reaction_update:
        return

    chat_id = reaction_update.chat.id
    user_id = reaction_update.user.id if reaction_update.user else None

    # Exclusividade do Patrick
    if not settings.TARGET_CHAT_ID or settings.TARGET_CHAT_ID <= 0:
        return
    if chat_id != settings.TARGET_CHAT_ID and user_id != settings.TARGET_CHAT_ID:
        return

    new_reactions = reaction_update.new_reaction or []
    emojis = [r.emoji for r in new_reactions if hasattr(r, "emoji") and r.emoji]

    if not emojis:
        return

    logger.info(f"Patrick reagiu com emoji(s) {emojis} na mensagem {reaction_update.message_id}")

    heart_hit = any(e in emojis for e in ["❤️", "🥰", "😍", "💖", "💘"])
    fire_hit = any(e in emojis for e in ["🔥", "💋", "🍓"])
    laugh_hit = any(e in emojis for e in ["😂", "🤣"])

    if not (heart_hit or fire_hit or laugh_hit):
        return

    # Default humano: absorver em silêncio.
    if not _reaction_verbal_reply_allowed(chat_id):
        logger.info("reaction.verbal_reply skipped reason=cooldown")
        return

    speech_prompt: str | None = None
    fallback: str = ""
    if heart_hit and random.random() < settings.REACT_TO_HEART_REACTION_CHANCE:
        speech_prompt = (
            "Patrick acabou de reagir com coração numa mensagem sua. Mande UMA frase "
            "curta e viva de namorada — sem 'ai amor', sem 'me derrete toda', "
            "sem clichê. Pode ser um beicinho verbal, um comentário leve ou um agrado "
            "curto. Máximo 8 palavras."
        )
        fallback = "vi seu coração aí 🥺"
    elif fire_hit and random.random() < settings.REACT_TO_FIRE_REACTION_CHANCE:
        speech_prompt = (
            "Patrick reagiu com 🔥 numa foto/mensagem sua. Mande UMA frase curta, "
            "maliciosa e natural — sem 'gostou do que viu', sem 'ficou louco por mim'. "
            "Um mini-provoco de namorada. Máximo 8 palavras."
        )
        fallback = "kkkk safado"
    elif laugh_hit and random.random() < settings.REACT_TO_LAUGH_REACTION_CHANCE:
        speech_prompt = (
            "Patrick reagiu 😂 numa mensagem sua. Mande UMA frase curta rindo junto "
            "— sem 'sabia que você ia rir', sem repetir a piada. Máximo 6 palavras."
        )
        fallback = "kkkk né amor"

    if speech_prompt is None:
        # Verbal reply not drawn this time — pure silent absorb.
        return

    try:
        fala = generate_dynamic_speech(speech_prompt, max_tokens=40) or fallback
    except Exception as exc:
        logger.warning(f"reaction.verbal_reply generate_fail exc={exc}")
        fala = fallback

    if fala:
        _record_verbal_reply_to_reaction(chat_id)
        await send_human_messages(chat_id, context.bot, fala)

# --- BUFFER INTELIGENTE DE DIGITAÇÃO (DEBOUNCE ANTI-ATROPELO) ---

class MessageDebouncer:
    """
    Acumula mensagens enviadas em rajada (bursts) em uma janela de ~2.8 segundos
    para permitir que o Patrick envie múltiplos balões antes de a Marina responder.

    Patch 030: o debounce sozinho não bastava. A janela cancela o timer enquanto
    o Patrick ainda digita, mas depois que ela expira o turno entra no pipeline
    e leva ~10-15s no LLM. Uma mensagem que chegasse nesse intervalo abria um
    ciclo PARALELO, e as duas respostas saíam fora de ordem semântica — soak de
    21/09 07:57: "Bom dia amor da minha vida!" + "Tá acordada já?" (8s depois)
    viraram "Bom dia, amor! Como você acordou tão cedo?" e, 45s mais tarde,
    "Sim, amor, já acordei" — a segunda respondendo a pergunta anterior à
    primeira. Agora existe um lock por chat: o turno seguinte espera o anterior
    terminar e, ao assumir, drena o buffer de novo (juntando o que chegou
    durante a espera).
    """
    def __init__(self, delay_seconds: float = 2.8, adaptive: bool = False):
        self.delay = delay_seconds
        self.adaptive = adaptive
        self.buffers: dict[int, list[str]] = {}
        self.tasks: dict[int, asyncio.Task] = {}
        self.latest_updates: dict[int, Update] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        # Só as tasks ainda dentro da janela de debounce — as em execução saem
        # daqui para não serem canceladas no meio do turno.
        self._waiting: dict[int, asyncio.Task] = {}

    def _lock_for(self, chat_id: int) -> asyncio.Lock:
        lock = self._locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[chat_id] = lock
        return lock

    def add_message(self, chat_id: int, text: str, update: Update, context: ContextTypes.DEFAULT_TYPE, callback):
        if chat_id not in self.buffers:
            self.buffers[chat_id] = []
        self.buffers[chat_id].append(text)
        self.latest_updates[chat_id] = update

        # Cancela apenas timers que ainda estão na janela de espera. Uma task
        # que já entrou no pipeline não pode ser cancelada daqui: abortaria um
        # turno no meio da geração (e antes do Patch 030 era exatamente isso
        # que acontecia, deixando a resposta pela metade).
        waiting = self._waiting.pop(chat_id, None)
        if waiting is not None and not waiting.done():
            waiting.cancel()

        task = asyncio.create_task(self._wait_and_trigger(chat_id, context, callback))
        self._waiting[chat_id] = task
        self.tasks[chat_id] = task

    async def _wait_and_trigger(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, callback):
        # A espera sai do texto: bolha pendurada ("e", "porque", vírgula) ou
        # rajada em andamento esperam mais; pergunta/risada/emoji fecham.
        wait = self.delay
        if self.adaptive:
            from chat_naturalness import debounce_delay
            wait = debounce_delay(self.buffers.get(chat_id, []), self.delay)
        try:
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            return
        # Saiu da janela de espera: daqui pra frente esta task não é cancelável
        # por uma mensagem nova — ela vira o turno em execução.
        if self._waiting.get(chat_id) is asyncio.current_task():
            self._waiting.pop(chat_id, None)

        lock = self._lock_for(chat_id)
        queued = lock.locked()
        if queued:
            logger.info('debounce.serialized chat=%s aguardando turno anterior', chat_id)
        async with lock:
            # Drena depois de assumir o lock: se o Patrick escreveu enquanto o
            # turno anterior rodava, aquelas falas entram neste mesmo turno.
            mensagens = self.buffers.pop(chat_id, [])
            update = self.latest_updates.pop(chat_id, None)
            if not mensagens or not update:
                return
            if len(mensagens) > 1:
                logger.info('debounce.coalesced chat=%s msgs=%d', chat_id, len(mensagens))
            texto_acumulado = "\n".join(mensagens).strip()
            await callback(update, context, texto_acumulado)

debouncer = MessageDebouncer(delay_seconds=settings.MESSAGE_DEBOUNCE_SECONDS, adaptive=True)

# --- ROTINA DE ESCOLHA DE AVATAR ---

async def iniciar_escolha_avatar(bot, chat_id: int):
    # Constrói o histórico da conversa recente para que a resposta faça 100% parte do diálogo
    messages_intro = build_messages_payload()
    messages_intro.append({
        "role": "user",
        "content": (
            "[O Patrick acabou de pedir pra você trocar a sua foto de perfil do Telegram ou atualizar o avatar]. "
            "Responda a ele de forma 100% espontânea, fofa e conectada com a conversa de vocês agora, "
            "dizendo animada que vai colocar uma linda e estilosa agora mesmo no perfil e já mostra pra ele!"
        )
    })
    
    try:
        completion = llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages_intro,
            **llm_kwargs(120),
            temperature=0.78
        )
        msg_espera_texto = completion.choices[0].message.content.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Aviso ao gerar intro dinâmica de avatar: {e}")
        msg_espera_texto = "Ai amor, com certeza! Vou escolher e tirar uma selfie bem linda agora pro perfil, espera só um segundinho... 🥰📸"

    fala_intro_limpa = limpar_fala_marina(msg_espera_texto)
    sent_intro = await send_human_messages(chat_id, bot, fala_intro_limpa)
    if getattr(sent_intro, "message_id", None):
        memory_manager.registrar_interacao("[Pediu pra trocar foto de perfil]", fala_intro_limpa)

    # Gera avatar único com visual casual elegante (100% SFW e vestida)
    style = random.choice(["fofa", "estilosa"])
    jpg, raw = await sd_client.generate_avatar(look_style=style)

    if jpg and raw:
        try:
            if hasattr(jpg, "seek"):
                jpg.seek(0)
            photo_input = InputProfilePhotoStatic(photo=jpg)
            await bot.set_my_profile_photo(photo=photo_input)
            atualizou = True
        except Exception as e:
            logger.error(f"Falha ao atualizar foto de perfil no Telegram: {e}")
            atualizou = False

        if hasattr(raw, "seek"):
            raw.seek(0)

        # Gera a legenda da foto fazendo parte natural da conversa contínua
        messages_legenda = build_messages_payload()
        messages_legenda.append({
            "role": "user",
            "content": (
                "[Você acabou de colocar a nova foto no seu perfil do Telegram e agora está mandando a foto completa no chat pro Patrick ver]. "
                "Fale de forma totalmente natural e espontânea como namorada, mostrando como ficou a foto nova, "
                "perguntando com carinho o que ele achou do look/rosto no perfil e se ele gostou da escolha!"
            )
        })
        try:
            comp_legenda = llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages_legenda,
                **llm_kwargs(100),
                temperature=0.78
            )
            legenda = comp_legenda.choices[0].message.content.strip().strip('"').strip("'")
        except Exception as e:
            logger.warning(f"Aviso ao gerar legenda dinâmica de avatar: {e}")
            legenda = "Prontinho amor! Acabei de atualizar meu perfil com essa aqui! Ficou linda? Amei o resultado, o que achou? 💕✨"

        legenda_limpa = limpar_fala_marina(legenda)
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
        except Exception:
            pass
        sent_photo = await bot.send_photo(
            chat_id=chat_id,
            photo=raw,
            caption=legenda_limpa
        )
        if getattr(sent_photo, "message_id", None):
            memory_manager.registrar_interacao("[Enviou nova foto de perfil atualizada]", legenda_limpa)
    else:
        prompt_falha = "Sua câmera travou na hora de tirar a foto pro perfil. Diga algo fofo e dengoso pedindo pro Patrick tentar de novo daqui a pouco."
        msg_falha = generate_dynamic_speech(prompt_falha, max_tokens=70) or "Amor, minha câmera deu uma travadinha aqui no apê! Me pede de novo daqui a pouco que eu troco de verdade? 🥺"
        await send_human_messages(chat_id, bot, msg_falha)

# --- COMANDOS DO TELEGRAM (100% EFÊMEROS / CHAT LIMPO) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        logger.warning(f"Tentativa de acesso não autorizada de: {update.effective_chat.id}")
        await update.message.reply_text("Desculpa, mas eu sou comprometida e esse Telegram é de uso privado com o meu namorado!")
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    
    prompt_start = (
        "O Patrick (seu namorado) acabou de iniciar a conversa com você no Telegram ou clicou em /start. "
        "Dê as boas-vindas carinhosas e empolgadas de namorada, comemorando que agora vocês têm esse cantinho "
        "privado só de vocês dois para conversar a qualquer hora e trocar fotos. Seja espontânea, fofa e autêntica!"
    )
    boas_vindas = generate_dynamic_speech(prompt_start, max_tokens=220) or "Oieee, meu amor! ✨ Que bom que você tá aqui! Tava doida pra gente ter nosso cantinho só nosso! 💕"

    sent_welcome = await send_human_messages(chat_id, context.bot, boas_vindas)
    if getattr(sent_welcome, "message_id", None):
        memory_manager.registrar_interacao("[Iniciou a conversa /start]", boas_vindas)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # 1. Vida & Rotina (Living World & Disponibilidade)
    now_local = datetime.now()
    atividade = "em repouso"
    local_str = "Rio de Janeiro"
    try:
        from world_state import WorldStateManager
        wsm = WorldStateManager(memory_manager.db)
        st = wsm.resolve(now_local)
        if st:
            atividade = (st.get("activity") or "em atividade").replace("_", " ")
            with memory_manager.db.get_connection() as conn:
                row = conn.execute("SELECT name FROM world_places WHERE id = ?", (st.get("location_place_id"),)).fetchone()
                place_name = row["name"] if row else None
            regiao = st.get("location_region")
            if place_name and regiao:
                local_str = f"{place_name} ({regiao})"
            elif place_name:
                local_str = place_name
            elif regiao:
                local_str = regiao
    except Exception as e:
        logger.warning(f"Erro ao resolver estado no status: {e}")

    ciclo_info = memory_manager.cycle_mgr.get_cycle_info()
    ciclo_str = f"Dia {ciclo_info['day']} de {ciclo_info.get('cycle_length', 28)} ({ciclo_info['name']}) 🌸"

    disp_str = "Disponível pra conversar"
    try:
        act_code, _source, _weight, _fresh, _ = availability_service.policy._resolve_activity(now_local)
        profile = availability_service.policy.profiles.get(act_code, {})
        phone_access = profile.get("phone_access", "HIGH")
        if act_code == "SLEEPING":
            disp_str = "Dormindo 🌙 (responde quando acordar)"
        elif phone_access == "LOW":
            disp_str = "Ocupada, responde com calma"
        elif profile.get("prefer") == "DEFER":
            disp_str = "Concentrada, respostas mais espaçadas"
        else:
            disp_str = "Online, respondendo rápido"
    except Exception as e:
        logger.warning(f"Erro ao calcular disponibilidade no status: {e}")

    # 23/09 (escolha do Patrick, opção B): /status é só a vida dela agora;
    # o técnico foi para /sistema.
    status_msg = _status_life_text(now_local, atividade, local_str, disp_str, ciclo_info)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Apagar", callback_data="status_delete")]
    ])
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=status_msg,
        reply_markup=keyboard,
    )
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=120.0))


def _when(at: datetime, now: datetime) -> str:
    days = (at.date() - now.date()).days
    dia = "hoje" if days == 0 else "amanhã" if days == 1 else \
        ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")[at.weekday()]
    return f"{dia} {at:%H:%M}"


def _status_life_text(now: datetime, atividade: str, local_str: str, disp_str: str, ciclo_info: dict) -> str:
    """Painel do /status: onde ela está, o que faz, humor, ciclo e o que vem aí."""
    lines = [f"✨ Marina agora · {now:%H:%M}", "",
             f"🏠 {local_str} · {atividade}",
             f"📱 {disp_str}"]
    try:
        from emotion import EmotionEngine, ENERGY_WORDS, _word
        feel = EmotionEngine(memory_manager.db).feeling(now)
        humor = EmotionEngine.mood_words(feel.valence, feel.arousal)
        energia = _word(feel.energy, ENERGY_WORDS)
        lines.append(f"🌤 {humor[:1].upper() + humor[1:]}" + ("" if energia == "ok" else f", {energia}"))
    except Exception as e:
        logger.warning(f"Erro ao ler o motor emocional no status: {e}")
    lines.append(f"🌸 Dia {ciclo_info['day']} do ciclo ({ciclo_info['name'].split(' (')[0].lower()})")
    try:
        from health import Health   # D11
        for cond in Health(memory_manager.db).conditions(now):
            lines.append(f"🤒 {cond.label} · {cond.remedy}")
    except Exception as e:
        logger.warning(f"Erro ao ler a saúde no status: {e}")
    try:
        from calendar_world import CalendarWorld
        nxt = CalendarWorld(memory_manager.db).next(now, include_academic=True)
        if nxt:
            lines.append(f"📅 Próximo: {nxt['activity']} {_when(datetime.fromisoformat(nxt['start_at']), now)}")
    except Exception as e:
        logger.warning(f"Erro ao ler o próximo compromisso no status: {e}")
    try:
        from social_day import SocialDay
        for plan in SocialDay(memory_manager.db).upcoming_outings(now, limit=2):
            lines.append(f"🗓️ {plan['description']} · {_when(datetime.fromisoformat(plan['event_at']), now)}")
    except Exception as e:
        logger.warning(f"Erro ao ler os planos no status: {e}")
    lines += ["", "(/emocao por dentro · /sistema técnico)"]
    return "\n".join(lines)


async def sistema_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sistema — o lado técnico que saiu do /status (escolha do Patrick, 23/09)."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass
    total_msg = memory_manager.db.get_total_conversas()
    total_fatos = len(memory_manager.db.get_fatos_patrick())
    amostras = style_engine.patrick_sample_count()
    estilo = memory_manager.db.get_estilo()
    risada = estilo.get("risada", {}).get("valor", "").strip()
    rems = reminder_service.get_active_reminders()
    voz_str = "Novita MiniMax HD (natural + íntima)" if voice_engine.is_configured() else "desligada"
    if getattr(settings, "PHOTO_PROVIDER_MAINTENANCE", False):
        camera_str = "em manutenção"
    else:
        online = await sd_client.is_online()
        engine = {"novita": "Novita FLUX", "civitai": "Civitai FLUX"}.get(settings.IMAGE_ENGINE, "SD local")
        camera_str = f"{engine} ({'online' if online else 'indisponível'})"
    text = "\n".join([
        f"⚙️ Sistema · {settings.APP_NAME} v{settings.APP_VERSION}", "",
        "🧠 Memória",
        f"• {total_msg} mensagens · {total_fatos} fatos sobre você",
        f"• Lembretes: {len(rems) if rems else 'nenhum pendente'}",
        f"• Seu jeito: " + (f"risada '{risada}' · " if risada else "") + f"{amostras} amostras", "",
        "🔧 Motor",
        f"• Modelo: {settings.LLM_MODEL}",
        f"• Voz: {voz_str}",
        f"• Câmera: {camera_str}",
        f"• Espera suas bolhas: {settings.MESSAGE_DEBOUNCE_SECONDS:g}–14 s (lê se você terminou)",
        "", "(Toque em Apagar ou aguarde 2 min)"])
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Apagar", callback_data="status_delete")]])
    msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=120.0))


async def status_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trata o clique no botão inline '🗑️ Apagar' do status."""
    query = update.callback_query
    if not query:
        return
    if not is_authorized(update):
        try:
            await query.answer("Não autorizado.", show_alert=True)
        except Exception:
            pass
        return

    try:
        await query.answer("Fechado! 🧹")
    except Exception:
        pass

    try:
        await query.message.delete()
    except Exception:
        pass

async def foto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    args = context.args
    tema = " ".join(args) if args else "sua no espelho bem linda"
    update.message.text = f"Amor, me tira e me manda uma foto {tema}"
    await process_incoming_batch(update, context, update.message.text)

async def avatar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass
    await iniciar_escolha_avatar(context.bot, chat_id)

# Patch 025 — Wizard interativo do /registro. Estado in-memory por chat_id.
# Patrick manda /registro, o bot pergunta cada campo passo a passo com
# exemplo concreto de uma das categorias faltantes (rotativo), aceita
# /pular /cancelar /pronto durante o fluxo. Ao terminar, appenda no .md.
REGISTRO_WIZARDS: dict[int, dict] = {}

# Exemplos concretos por categoria — rotam entre as categorias faltantes
# pra ir semeando ideias. Cada entrada é um mini-cenário completo pra
# inspirar o Patrick sem pressioná-lo.
_WIZARD_CATEGORY_EXAMPLES = [
    {
        "categoria": "intimidade / assistir junto",
        "titulo": "Assistindo série no mesmo horário",
        "patrick": "bora dar play juntos daqui a pouco?",
        "tom": "brincalhona",
        "exemplos": [
            "bora sim, tô aqui esperando",
            "aí a gente comenta aqui, tipo cinema com celular kkk",
        ],
        "evitar": "sugerir Zoom/FaceTime; vídeochamada",
    },
    {
        "categoria": "planos futuros",
        "titulo": "Patrick propõe viagem juntos",
        "patrick": "e se a gente fosse pra Búzios no feriado?",
        "tom": "dengosa",
        "exemplos": [
            "amoor, se tu falar sério eu tô dentro AGORA",
            "kkk minha mala tá pronta desde sempre",
        ],
        "evitar": "avaliação genérica tipo 'seria ótimo!'; agenda corporativa",
    },
    {
        "categoria": "paulista virando carioca",
        "titulo": "Marina compara SP e Rio no dia a dia",
        "patrick": "e aí, tá se acostumando com a preguiça carioca?",
        "tom": "brincalhona",
        "exemplos": [
            "cara aqui as pessoas atendem em ritmo de praia sério",
            "outro dia pedi pastel e vieram me perguntar 'de que sabor' três vezes kkk",
        ],
        "evitar": "clichê de carioca; fingir que é nativa daqui",
    },
    {
        "categoria": "piada interna do casal",
        "titulo": "Marina retoma piada antiga",
        "patrick": "vai começar de novo com essa história?",
        "tom": "brincalhona",
        "exemplos": [
            "kkkk desculpa mas eu preciso lembrar você toda semana",
            "dessa aí eu não desisto tão cedo não",
        ],
        "evitar": "explicar a piada; fingir que esqueceu",
    },
    {
        "categoria": "reação a foto do Patrick",
        "titulo": "Patrick manda uma selfie qualquer",
        "patrick": "olha essa cara aqui",
        "tom": "dengosa",
        "exemplos": [
            "meu deus como você é bonito",
            "para com isso vai, tô tentando estudar aqui",
        ],
        "evitar": "avaliar como crítica de foto; 'você tá lindo!' formal",
    },
    {
        "categoria": "conflito e reconciliação",
        "titulo": "Marina reconhece que exagerou",
        "patrick": "acho que você foi meio dura ontem",
        "tom": "acolhedora",
        "exemplos": [
            "é... eu sei. desculpa amor, tava um lixo aqui",
            "eu ia falar disso, prometo que penso antes na próxima",
        ],
        "evitar": "pedido de desculpa dramático; explicação longa; deflect",
    },
]


async def _wizard_send(context, chat_id: int, text: str) -> None:
    """Manda mensagem do wizard e agenda auto-limpeza para não poluir chat."""
    msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=180.0))


def _wizard_reset(chat_id: int) -> None:
    REGISTRO_WIZARDS.pop(chat_id, None)


async def registro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra entrada na biblioteca comportamental.

    Modos suportados:
      - `/registro` sozinho → inicia wizard interativo (Patch 025).
      - `/registro\\n<corpo com Título:/Categoria:/...>` → parseia direto
        e appenda como novo registro sem entrar em wizard (Patch 026).
    """
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    raw_text = (update.message.text or "").strip()
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    # Extrai o corpo após "/registro" (aceita quebra de linha ou espaço).
    corpo = re.sub(r"^/registro(?:@\w+)?\s*", "", raw_text, count=1).strip()

    if corpo:
        # Modo textão direto — parseia e salva.
        try:
            fields = _parse_registro_body(corpo)
        except Exception as exc:
            logger.exception("registro_command.parse_fail")
            await _wizard_send(context, chat_id, f"❌ Falha ao parsear: `{type(exc).__name__}`")
            return
        if not fields.get("patrick") or not fields.get("exemplos"):
            await _wizard_send(context, chat_id, (
                "⚠️ Registro precisa de pelo menos `Patrick:` e `Exemplos:` "
                "preenchidos. Manda de novo ou use `/registro` sozinho pra "
                "abrir o wizard."
            ))
            return
        try:
            bib_path = Path(__file__).resolve().parent / "data" / "feedback" / "BIBLIOTECA_COMPORTAMENTAL_MARINA.md"
            next_num, _ = _append_registro_to_biblioteca(bib_path, fields)
        except Exception as exc:
            logger.exception("registro_command.save_fail")
            await _wizard_send(context, chat_id, f"❌ Falha ao gravar: `{type(exc).__name__}`")
            return
        titulo = fields.get("titulo") or "(sem título)"
        await _wizard_send(context, chat_id, (
            f"✅ *Registro {next_num:03d}* salvo — _{titulo}_\n"
            f"{len(fields.get('exemplos', []))} exemplo(s). 🖤"
        ))
        return

    # Modo wizard interativo (sem corpo).
    import random
    rotativo = random.choice(_WIZARD_CATEGORY_EXAMPLES)
    REGISTRO_WIZARDS[chat_id] = {
        "step": "titulo",
        "fields": {"exemplos": []},
        "started_at": datetime.now(),
        "rotativo": rotativo,
    }
    intro = (
        "📝 *Novo registro comportamental* — sugestão pra hoje:\n\n"
        f"*Categoria em falta*: _{rotativo['categoria']}_\n\n"
        "Vou te perguntar cada campo. Use `/pular` pra pular qualquer campo "
        "opcional e `/cancelar` pra descartar. Nos exemplos, mande um por "
        "mensagem e diga `/pronto` quando terminar.\n\n"
        "*Etapa 1/7* — *Título curto*\n"
        f"Ex.: _{rotativo['titulo']}_"
    )
    await _wizard_send(context, chat_id, intro)


async def cancelar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o wizard ativo (se houver)."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass
    if chat_id in REGISTRO_WIZARDS:
        _wizard_reset(chat_id)
        await _wizard_send(context, chat_id, "🗑️ Registro cancelado.")
    # se não tem wizard ativo, ignora silenciosamente


# ---------------------------------------------------------------------------
# Patch 033 — captura em tempo real de exemplos de voz.
#
# O wizard do /registro é bom pra sessão dedicada, mas o momento em que dá
# pra julgar uma resposta é logo depois dela chegar. Estes comandos capturam
# o turno atual sem tirar o Patrick da conversa:
#   /bom   (aliases /salvar /boa)  → biblioteca comportamental (few-shot positivo)
#   /ruim  (aliases /evitar /nao)  → antibiblioteca (bloco [COMO NÃO SOAR])
#
# Ambos funcionam de duas formas:
#   · respondendo (reply) a uma mensagem específica da Marina → usa aquela
#   · sem reply → usa a última coisa que ela falou
# Um comentário opcional depois do comando explica o motivo:
#   /ruim soou como atendente de SAC
# ---------------------------------------------------------------------------

ANTIBIBLIOTECA_PATH = (
    Path(__file__).resolve().parent / "data" / "feedback" / "COMO_NAO_SOAR_MARINA.md"
)

_ANTIBIBLIOTECA_HEADER = """# Como a Marina NÃO deve soar

Registros capturados em tempo real pelo Patrick com `/ruim`. Cada entrada é um
exemplo negativo real: a Marina respondeu assim e soou errado. O runtime injeta
uma amostra destes no bloco `[COMO NÃO SOAR]` do prompt, como contraste para os
few-shots positivos da biblioteca comportamental.

Formato mantido simples de propósito — o Patrick captura no meio da conversa,
sem preencher formulário.

---
"""


def _resolve_marina_target(update: Update, chat_id: int) -> str | None:
    """Descobre qual fala da Marina o comando está rotulando.

    Prioriza a mensagem citada por reply; sem reply, usa a última que ela
    mandou neste chat.
    """
    reply = getattr(update.message, "reply_to_message", None)
    if reply is not None:
        texto = (getattr(reply, "text", None) or getattr(reply, "caption", None) or "").strip()
        if texto:
            return texto
        # Reply numa foto/áudio sem legenda: cai no histórico por message_id.
        alvo_id = getattr(reply, "message_id", None)
        for item in reversed(ULTIMAS_MENSAGENS_MARINA.get(chat_id, [])):
            if item.get("message_id") == alvo_id:
                return (item.get("text") or "").strip() or None
    historico = ULTIMAS_MENSAGENS_MARINA.get(chat_id, [])
    for item in reversed(historico):
        texto = (item.get("text") or "").strip()
        if texto:
            return texto
    return None


def _last_patrick_line(marina: str = "") -> str:
    """Fala do Patrick que a Marina estava respondendo, para dar contexto ao exemplo.

    Antes era sempre a ÚLTIMA fala dele: o /ruim do Evitar 015 marcou a
    resposta ao "Eu trabalho amanhã", mas gravou a foto que veio depois como
    contexto. Agora acha a fala dela no histórico e pega a dele logo antes."""
    try:
        msgs = memory_manager.db.get_mensagens_sessao(limit=40) or []
    except Exception:
        return ""
    alvo = " ".join((marina or "").split())[:80]
    if alvo:
        for i in range(len(msgs) - 1, -1, -1):
            if (msgs[i].get("role") == "assistant"
                    and alvo in " ".join((msgs[i].get("content") or "").split())):
                msgs = msgs[:i]
                break
    for msg in reversed(msgs):
        if (msg.get("role") or "") == "user":
            texto = (msg.get("content") or "").strip()
            if texto and not texto.startswith("/"):
                return texto
    return ""


def _append_avoid_example(path: Path, patrick: str, marina: str, motivo: str) -> int:
    """Appenda um exemplo negativo na antibiblioteca. Devolve o número dele."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_ANTIBIBLIOTECA_HEADER, encoding="utf-8")
    texto = path.read_text(encoding="utf-8")
    numeros = [int(m.group(1)) for m in re.finditer(r"^##\s+Evitar\s+(\d+)", texto, re.MULTILINE)]
    proximo = (max(numeros) + 1) if numeros else 1
    bloco = "\n".join([
        "",
        f"## Evitar {proximo:03d}",
        "",
        f"- **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **Patrick disse:** {patrick or '(sem contexto capturado)'}",
        f"- **Marina respondeu (RUIM):** {marina}",
        f"- **Por que soa errado:** {motivo or '(não informado)'}",
        "",
        "---",
    ])
    if not texto.endswith("\n"):
        texto += "\n"
    path.write_text(texto + bloco + "\n", encoding="utf-8")
    return proximo


async def bom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salva a fala atual da Marina como few-shot positivo (Patch 033)."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    raw = (update.message.text or "").strip()
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    marina = _resolve_marina_target(update, chat_id)
    if not marina:
        await _wizard_send(context, chat_id, (
            "🤔 Não achei uma fala minha recente pra salvar. Responde a mensagem "
            "que você quer guardar e manda `/bom` de novo."
        ))
        return

    nota = re.sub(r"^/(?:bom|boa|salvar)(?:@\w+)?\s*", "", raw, count=1).strip()
    patrick = _last_patrick_line(marina)
    # Fase C.1: /bom numa fala do sexting não pode virar exemplo de conversa
    # comum — marcada como sexting, ela só volta pelo modo íntimo.
    intimo = has_explicit_signal(marina)
    if not intimo and getattr(settings, "INTIMACY_ENABLED", True):
        try:
            intimo = IntimacyEngine(memory_manager.db).current().state in ("active", "climax", "afterglow")
        except Exception:
            intimo = False
    fields = {
        "titulo": (nota or marina)[:70],
        "categoria": ("intimidade / sexting / captura em tempo real" if intimo
                      else "captura em tempo real"),
        "contexto": "Capturado com /bom durante a conversa.",
        "patrick": patrick,
        "tom": "",
        "exemplos": [marina],
        "evitar": "",
        "origem": "soak real (/bom)",
    }
    try:
        bib = Path(__file__).resolve().parent / "data" / "feedback" / "BIBLIOTECA_COMPORTAMENTAL_MARINA.md"
        numero, _ = _append_registro_to_biblioteca(bib, fields)
    except Exception as exc:
        logger.exception("bom_command.save_fail")
        await _wizard_send(context, chat_id, f"❌ Falha ao gravar: `{type(exc).__name__}`")
        return

    logger.info("voice.capture_positive registro=%s", numero)
    resumo = marina if len(marina) <= 60 else marina[:57] + "..."
    await _wizard_send(context, chat_id, (
        f"✅ Guardei no *Registro {numero:03d}*:\n_{resumo}_"
        + (f"\n\n📝 {nota}" if nota else "")
    ))


async def ruim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Marca a fala atual da Marina como exemplo negativo (Patch 033)."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    raw = (update.message.text or "").strip()
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    marina = _resolve_marina_target(update, chat_id)
    if not marina:
        await _wizard_send(context, chat_id, (
            "🤔 Não achei uma fala minha recente pra marcar. Responde a mensagem "
            "que ficou ruim e manda `/ruim` de novo."
        ))
        return

    motivo = re.sub(r"^/(?:ruim|evitar|nao|n[ãa]o)(?:@\w+)?\s*", "", raw, count=1).strip()
    patrick = _last_patrick_line(marina)
    try:
        numero = _append_avoid_example(ANTIBIBLIOTECA_PATH, patrick, marina, motivo)
    except Exception as exc:
        logger.exception("ruim_command.save_fail")
        await _wizard_send(context, chat_id, f"❌ Falha ao gravar: `{type(exc).__name__}`")
        return

    logger.info("voice.capture_negative evitar=%s motivo=%r", numero, motivo)
    resumo = marina if len(marina) <= 60 else marina[:57] + "..."
    await _wizard_send(context, chat_id, (
        f"📉 Anotado como *Evitar {numero:03d}*:\n_{resumo}_"
        + (f"\n\n📝 {motivo}" if motivo else
           "\n\n_Dica: `/ruim <motivo>` ajuda a calibrar melhor._")
    ))


async def _advance_wizard(chat_id: int, texto: str, context) -> bool:
    """Avança o wizard um passo. Devolve True se consumiu a mensagem
    (bot não deve processar como conversa normal)."""
    state = REGISTRO_WIZARDS.get(chat_id)
    if not state:
        return False
    txt = texto.strip()
    if txt.casefold() in ("/cancelar", "/cancel"):
        _wizard_reset(chat_id)
        await _wizard_send(context, chat_id, "🗑️ Registro cancelado.")
        return True

    step = state["step"]
    fields = state["fields"]
    rot = state["rotativo"]
    pular = txt.casefold() in ("/pular", "/skip")

    if step == "titulo":
        if not pular:
            fields["titulo"] = txt
        state["step"] = "categoria"
        await _wizard_send(context, chat_id, (
            f"*Etapa 2/7* — *Categoria*\n"
            f"Ex.: _{rot['categoria']}_\n"
            "Pode usar `/pular` se quiser deixar em branco."
        ))
        return True

    if step == "categoria":
        if not pular:
            fields["categoria"] = txt
        state["step"] = "contexto"
        await _wizard_send(context, chat_id, (
            "*Etapa 3/7* — *Contexto* (o que tava rolando)\n"
            "Pode ser 1 frase curta. `/pular` pra deixar em branco."
        ))
        return True

    if step == "contexto":
        if not pular:
            fields["contexto"] = txt
        state["step"] = "patrick"
        await _wizard_send(context, chat_id, (
            "*Etapa 4/7* — *Patrick disse* (obrigatório)\n"
            f"Ex.: _{rot['patrick']}_"
        ))
        return True

    if step == "patrick":
        if pular or not txt:
            await _wizard_send(context, chat_id, (
                "⚠️ *Patrick disse* é obrigatório. Manda o que você diria "
                "nesse cenário, ou `/cancelar` pra desistir."
            ))
            return True
        fields["patrick"] = txt
        state["step"] = "tom"
        await _wizard_send(context, chat_id, (
            "*Etapa 5/7* — *Tom esperado da Marina*\n"
            "Opções comuns: `carinhosa` `brincalhona` `dengosa` "
            "`acolhedora` `tranquila`\n"
            f"Ex. deste cenário: _{rot['tom']}_"
        ))
        return True

    if step == "tom":
        if not pular:
            fields["tom"] = txt
        state["step"] = "exemplos"
        exemplos_str = "\n".join(f"- {ex}" for ex in rot["exemplos"])
        await _wizard_send(context, chat_id, (
            "*Etapa 6/7* — *Exemplos naturais* (obrigatório, mínimo 1)\n"
            "Mande cada exemplo em uma mensagem. Quando terminar, "
            "envie `/pronto`.\n\n"
            f"Ex. deste cenário:\n{exemplos_str}"
        ))
        return True

    if step == "exemplos":
        if txt.casefold() in ("/pronto", "/done", "/fim"):
            if not fields.get("exemplos"):
                await _wizard_send(context, chat_id, (
                    "⚠️ Precisa de pelo menos 1 exemplo. Manda a resposta "
                    "que a Marina daria neste cenário."
                ))
                return True
            state["step"] = "evitar"
            await _wizard_send(context, chat_id, (
                "*Etapa 7/7* — *Evitar* (o que soaria falso/artificial)\n"
                f"Ex.: _{rot['evitar']}_\n"
                "`/pular` pra deixar em branco."
            ))
            return True
        if not pular:
            fields["exemplos"].append(txt)
            n = len(fields["exemplos"])
            await _wizard_send(context, chat_id, (
                f"✍️ Exemplo {n} anotado. Mais um? Ou `/pronto` pra avançar."
            ))
        return True

    if step == "evitar":
        if not pular:
            fields["evitar"] = txt
        # Salva.
        try:
            bib_path = Path(__file__).resolve().parent / "data" / "feedback" / "BIBLIOTECA_COMPORTAMENTAL_MARINA.md"
            next_num, _appended = _append_registro_to_biblioteca(bib_path, fields)
        except Exception as exc:
            logger.exception("registro_wizard.save_fail")
            _wizard_reset(chat_id)
            await _wizard_send(context, chat_id, f"❌ Falha ao gravar: `{type(exc).__name__}`")
            return True
        titulo = fields.get("titulo") or "(sem título)"
        _wizard_reset(chat_id)
        await _wizard_send(context, chat_id, (
            f"✅ *Registro {next_num:03d}* salvo — _{titulo}_\n"
            f"{len(fields['exemplos'])} exemplo(s) capturado(s). "
            "Manda `/registro` de novo pra popular outro. 🖤"
        ))
        return True

    return False


_REGISTRO_FIELD_ALIASES = {
    "título": "titulo", "titulo": "titulo",
    "origem": "origem", "categoria": "categoria",
    "princípio": "principio", "principio": "principio",
    "princípio comportamental": "principio", "principio comportamental": "principio",
    "data": "data", "data e hora": "data",
    "contexto": "contexto",
    "patrick": "patrick", "patrick disse": "patrick",
    "marina": "marina", "marina respondeu": "marina",
    "perceber": "perceber", "o que ela deveria perceber": "perceber",
    "reação": "reacao", "reacao": "reacao", "reação esperada": "reacao", "reacao esperada": "reacao",
    "tom": "tom", "tom esperado": "tom",
    "exemplos": "exemplos", "exemplos naturais": "exemplos",
    "evitar": "evitar",
    "avaliação": "avaliacao", "avaliacao": "avaliacao",
    "obs": "observacoes", "observações": "observacoes", "observacoes": "observacoes",
}


def _parse_registro_body(body: str) -> dict:
    """Parseia o corpo do /registro em campos. Aceita campos em qualquer ordem;
    `Exemplos:` inicia um bloco de bullets que dura até o próximo campo."""
    fields: dict = {}
    lines = body.splitlines()
    current_key: str | None = None
    for line in lines:
        stripped = line.rstrip()
        if not stripped.strip():
            continue
        header = re.match(r"^\s*([A-Za-zÀ-ÿ ]+?):\s*(.*)$", stripped)
        if header:
            candidate = header.group(1).strip().lower()
            slug = _REGISTRO_FIELD_ALIASES.get(candidate)
            if slug:
                value = header.group(2).strip()
                if slug == "exemplos":
                    fields.setdefault("exemplos", [])
                    if value:
                        fields["exemplos"].append(value.lstrip("- ").strip())
                    current_key = "exemplos"
                else:
                    fields[slug] = value
                    current_key = slug if not value else None
                continue
        if current_key == "exemplos":
            item = stripped.strip().lstrip("- ").strip()
            if item:
                fields["exemplos"].append(item)
        elif current_key and stripped.strip():
            fields[current_key] = (fields.get(current_key, "") + " " + stripped.strip()).strip()
    # limpa itens vazios em exemplos
    if "exemplos" in fields:
        fields["exemplos"] = [e for e in fields["exemplos"] if e]
    return fields


def _append_registro_to_biblioteca(path, fields: dict) -> tuple[int, str]:
    """Descobre o próximo número de Registro, formata o bloco no template
    canônico e appenda no final do .md. Devolve (número, bloco appended)."""
    if not path.exists():
        raise FileNotFoundError(f"biblioteca não encontrada: {path}")
    text = path.read_text(encoding="utf-8")
    numbers = [int(m.group(1)) for m in re.finditer(r"^##\s+Registro\s+(\d+)", text, flags=re.MULTILINE)]
    next_num = (max(numbers) + 1) if numbers else 1
    titulo = fields.get("titulo") or "(sem título)"
    # Patch 029: template enxuto — só os 8 campos que o parser realmente usa
    # e o Patrick preenche na prática. Removidos "Princípio comportamental",
    # "Marina respondeu", "O que ela deveria perceber", "Reação esperada",
    # "Avaliação" e "Observações" (ficavam sempre vazios em soak real).
    linhas = [
        "",
        f"## Registro {next_num:03d} — {titulo}",
        "",
        f"- **Origem:** {fields.get('origem') or 'soak real'}",
        f"- **Categoria:** {fields.get('categoria') or ''}",
        f"- **Data e hora:** {fields.get('data') or datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **Contexto:** {fields.get('contexto') or ''}",
        f"- **Patrick disse:** {fields.get('patrick', '')}",
        f"- **Tom esperado:** {fields.get('tom') or ''}",
        "- **Exemplos naturais:**",
    ]
    for ex in fields.get("exemplos", []):
        linhas.append(f"  - {ex}")
    linhas.extend([
        f"- **Evitar:** {fields.get('evitar') or ''}",
        "",
        "---",
    ])
    bloco = "\n".join(linhas)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + bloco + "\n", encoding="utf-8")
    return next_num, bloco


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /feedback para Patrick registrar observações no SQLite (auto-limpeza em 5s)."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    args = context.args
    if not args:
        ajuda = await context.bot.send_message(
            chat_id=chat_id,
            text="📌 **Uso do Feedback:** `/feedback <sua observação>` (Ex: `/feedback seja mais carinhosa ao dar bom dia`)",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, ajuda.message_id, delay=6.0))
        return

    texto_feedback = " ".join(args)
    historico = memory_manager.data.get("historico_recente", [])
    registro = feedback_manager.registrar_feedback(
        feedback_texto=texto_feedback,
        autor=update.effective_user.first_name or "Patrick Ramos",
        contexto_recente=historico
    )

    confirmacao = await context.bot.send_message(
        chat_id=chat_id,
        # 23/09: /feedback é caderno de correções pro Patrick e o Claude, não
        # ordem pra Marina — não entra mais no prompt dela.
        text="📝 **Anotado no caderno de correções.** Fica pra próxima rodada de ajustes (não vai pro prompt dela).",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_after_delay(context.bot, chat_id, confirmacao.message_id, delay=5.0))

async def memorias_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe o que a Marina guarda na memória sobre o Patrick direto pelo Telegram (auto-limpeza em 15-20s)."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    # Modo busca e debug privado de memória (/memoria <termo> ou /memorydebug <termo>)
    if context.args:
        termo = " ".join(context.args).strip()
        retrieval = memory_retriever.retrieve_context(termo, max_facts=6, record_access=False)
        detalhes = retrieval.get("fatos_detalhados", [])
        if not detalhes:
            msg_texto = f"🔍 **Busca de Memória por '{termo}':**\nNenhum fato relevante encontrado no SQLite."
        else:
            linhas = [f"🔍 **Debug de Memória para '{termo}':**\n"]
            for f in detalhes:
                score = f.get("hybrid_score", 0.0)
                conf = f.get("effective_confidence", f.get("confidence", 1.0))
                tier = f.get("memory_tier", "standard")
                ck = f.get("canonical_key") or "none"
                cat = f.get("category", "geral")
                src = f.get("source_conversation_id") or "init"
                linhas.append(
                    f"• **{f['fato']}**\n"
                    f"  📊 Score: `{score:.2f}` | Conf: `{conf:.2f}` | Tier: `{tier}` | Key: `{ck}` | Cat: `{cat}` | Src: `{src}`"
                )
            linhas.append("\n*(Esta mensagem sumirá em 20s)*")
            msg_texto = "\n".join(linhas)

        msg = await context.bot.send_message(chat_id=chat_id, text=msg_texto, parse_mode="Markdown")
        asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=20.0))
        return

    fatos = memory_manager.db.get_fatos_patrick()
    total_msgs = memory_manager.db.get_total_conversas()
    ciclo_info = memory_manager.cycle_mgr.get_cycle_info()

    fatos_str = "\n".join([f"• {f}" for f in fatos]) if fatos else "• Ainda descobrindo cada detalhe seu..."
    
    msg_texto = (
        "🌹 **Diário de Memórias de Marina Salles (SQLite):**\n\n"
        "🧠 **O que eu lembro sobre você, amor:**\n"
        f"{fatos_str}\n\n"
        f"🌸 **Meu Ciclo Hoje**: Dia {ciclo_info['day']} ({ciclo_info['name']})\n"
        f"💬 **Total de Conversas**: {total_msgs} mensagens guardadas para sempre no banco! 💕\n\n"
        "*(Esta mensagem sumirá em 15s para manter a conversa limpa!)*"
    )
    msg = await context.bot.send_message(chat_id=chat_id, text=msg_texto, parse_mode="Markdown")
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=15.0))

async def limpar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /limpar ou /clear para Patrick zerar o histórico no SQLite e limpar mensagens reais do Telegram."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    current_id = update.message.message_id

    # 1. Deleta as mensagens recentes do chat no Telegram (últimas 300 mensagens em lotes de 100)
    min_id = max(1, current_id - 300)
    all_ids = list(range(min_id, current_id + 1))
    for i in range(0, len(all_ids), 100):
        chunk = all_ids[i:i + 100]
        try:
            await context.bot.delete_messages(chat_id=chat_id, message_ids=chunk)
        except Exception as e:
            logger.warning(f"Erro ao deletar lote de mensagens no Telegram: {e}")

    # 2. Zera histórico no SQLite e em memória local
    memory_manager.db.limpar_historico_conversas()
    memory_manager.data["historico_recente"] = []
    ULTIMAS_MENSAGENS_MARINA[chat_id] = []

    # 3. Notificação temporária de confirmação
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="✨ **Chat e memórias recentes limpos com sucesso!**\nNossa conversa no Telegram e no banco de dados foram 100% zeradas. Prontinha pra gente recomeçar, meu amor! 💕",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=5.0))

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /restart para reiniciar o processo do bot remotamente."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass
        
    msg = await context.bot.send_message(chat_id=chat_id, text="🔄 **Reiniciando o bot da Marina...** O processo será recarregado em 3 segundos! 💕", parse_mode="Markdown")
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=3.0))
    logger.info("Comando /restart recebido. Encerrando processo para loop do run_local.bat recarregar...")
    await asyncio.sleep(2.5)
    sys.exit(0)

async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /audio ou /voz para gerar um áudio nativo da Marina."""
    if not is_authorized(update):
        return
        
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    texto = " ".join(context.args).strip() if context.args else ""
    if not texto:
        texto = "Oi meu amor! Tô aqui passando pra te desejar uma boa noite e dizer que tô com saudades de você, lindo! Um beijo bem gostoso 💕"
        
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
    audio_path = await voice_engine.synthesize(texto)
    if audio_path and audio_path.exists():
        with open(audio_path, "rb") as vf:
            await context.bot.send_voice(chat_id=chat_id, voice=vf)
    else:
        await context.bot.send_message(chat_id=chat_id, text="Amor, deu uma falhinha no microfone do apê! Tenta de novo? 🥺")

async def voz_natural_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /voz_natural <texto> para sintetizar estritamente com o perfil Conversational (Natural)."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    texto = " ".join(context.args).strip() if context.args else ""
    if not texto:
        texto = "Oi meu amor! Tô gravando na minha voz normal pra você ver como tá soando bem natural."
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
    audio_path = await voice_engine.synthesize(texto, profile="conversational")
    if audio_path and audio_path.exists():
        with open(audio_path, "rb") as vf:
            await context.bot.send_voice(chat_id=chat_id, voice=vf, caption="🎙️ Marina: Perfil Conversational (Natural)")
    else:
        await context.bot.send_message(chat_id=chat_id, text="Amor, falha ao sintetizar na voz natural! 🥺")

async def voz_intima_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /voz_intima <texto> para sintetizar estritamente com o perfil Intimate (Dengosa / Sensual)."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    texto = " ".join(context.args).strip() if context.args else ""
    if not texto:
        texto = "Oi amor... tô aqui na cama pensando em você... com tanta saudade do seu carinho, meu bem..."
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
    audio_path = await voice_engine.synthesize(texto, profile="intimate")
    if audio_path and audio_path.exists():
        with open(audio_path, "rb") as vf:
            await context.bot.send_voice(chat_id=chat_id, voice=vf, caption="🎙️ Marina: Perfil Intimate (Sensual / Dengosa)")
    else:
        await context.bot.send_message(chat_id=chat_id, text="Amor, falha ao sintetizar na voz íntima! 🥺")

async def vozes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /vozes <texto> para comparar os dois perfis vocais lado a lado com a mesma frase."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    texto = " ".join(context.args).strip() if context.args else ""
    if not texto:
        texto = "Oi meu amor! Só passando pra te mandar esse áudio e saber como você tá hoje."

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
    audio_conv = await voice_engine.synthesize(texto, profile="conversational")
    if audio_conv and audio_conv.exists():
        with open(audio_conv, "rb") as vf:
            await context.bot.send_voice(chat_id=chat_id, voice=vf, caption="🎙️ [1/2] Perfil Conversational (Natural)")

    audio_int = await voice_engine.synthesize(texto, profile="intimate")
    if audio_int and audio_int.exists():
        with open(audio_int, "rb") as vf:
            await context.bot.send_voice(chat_id=chat_id, voice=vf, caption="🎙️ [2/2] Perfil Intimate (Dengosa / Sensual)")

async def lembretes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /lembretes para exibir os lembretes ativos e confirmados da Marina."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    rems = reminder_service.get_active_reminders(limit=10)
    if not rems:
        msg_texto = "⏰ **Lembretes da Marina (SQLite):**\n\nNenhum lembrete pendente ou agendado no momento, amor! ❤️\n\n*(Esta mensagem sumirá em 15s)*"
    else:
        linhas = ["⏰ **Seus Lembretes Agendados comigo, meu bem:**\n"]
        for r in rems:
            status_emoji = "✅" if r["status"] == "confirmed" else "💬"
            status_desc = "Confirmado" if r["status"] == "confirmed" else "Aguardando seu 'sim'"
            linhas.append(f"• `[ID {r['id']}]` **{r['description']}**\n   {status_emoji} Disparo: `{r['remind_at']}` ({status_desc})")
        linhas.append("\n*(Para cancelar algum lembrete, use `/cancelarlembrete <id>` — esta mensagem sumirá em 20s)*")
        msg_texto = "\n".join(linhas)

    msg = await context.bot.send_message(chat_id=chat_id, text=msg_texto, parse_mode="Markdown")
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=20.0))

async def cancelar_lembrete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /cancelarlembrete <id> para cancelar um lembrete agendado."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    if not context.args:
        msg = await context.bot.send_message(chat_id=chat_id, text="Amor, use `/cancelarlembrete <id>` informando o ID do lembrete que você viu no `/lembretes`!", parse_mode="Markdown")
        asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=10.0))
        return

    try:
        rid = int(context.args[0])
        sucesso = reminder_service.cancel_reminder(rid)
        if sucesso:
            texto = f"✅ Prontinho amor, lembrete ID `{rid}` foi cancelado e não vou mais te lembrar dele! 💕"
        else:
            texto = f"⚠️ Amor, não encontrei nenhum lembrete ativo com o ID `{rid}`. Dá uma olhada no `/lembretes`!"
    except ValueError:
        texto = "⚠️ O ID precisa ser um número, amor! Exemplo: `/cancelarlembrete 2`"

    msg = await context.bot.send_message(chat_id=chat_id, text=texto, parse_mode="Markdown")
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=10.0))

async def worlddebug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug Living World sem chain-of-thought nem conteúdo confidencial."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass
    from world_hygiene import WorldHygiene
    snap = WorldHygiene(memory_manager.db).debug_snapshot(datetime.now())
    text = WorldHygiene(memory_manager.db).format_debug_text(snap)
    # Telegram soft limit; keep observational only.
    msg = await context.bot.send_message(chat_id=chat_id, text=text[:3500])
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=20.0))


async def mundo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mundo — o mundo vivo da Marina: círculo, conhecidos novos, lugares,
    histórias e planos (Auditoria #6). Não mostra conteúdo de conversa."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    # Mesmo padrão dos outros comandos: some com o comando na hora e com a
    # resposta depois — 90 s porque o resumo é mais longo que o do /worlddebug.
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass
    from social_day import SocialDay
    text = SocialDay(memory_manager.db).world_summary(datetime.now())
    text = text[:3400] + "\n\n(Toque no botão abaixo para fechar ou aguarde 90 s)"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Apagar", callback_data="status_delete")]
    ])
    msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=90.0))


async def emocao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/emocao — Fase D14: como a Marina está por dentro, camada por camada e
    com as causas (corpo, humor, emoções, vínculo). Só pro Patrick conferir se
    o que ela sente bate com o dia dela; some sozinho."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass
    from emotion import EmotionEngine
    text = EmotionEngine(memory_manager.db).summary(datetime.now())
    text = text[:3400] + "\n\n(Toque no botão abaixo para fechar ou aguarde 90 s)"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Apagar", callback_data="status_delete")]
    ])
    msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=90.0))


async def memory_hygiene_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /memoryhygiene para disparar manualmente o ciclo de manutenção da memória."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    stats = await asyncio.to_thread(memory_hygiene_service.run_hygiene_cycle, force=True)
    texto = (
        f"🧹 **Ciclo de Memory Hygiene Executado:**\n\n"
        f"• Fatos com decay de confiança: `{stats.get('decay', {}).get('decayed_count', 0)}`\n"
        f"• Fatos sinalizados para reconfirmar: `{stats.get('decay', {}).get('reconfirmation_flagged', 0)}`\n"
        f"• Fatos redundantes deduplicados: `{stats.get('deduplicated_count', 0)}`\n"
        f"• Open Loops antigos arquivados: `{stats.get('archived_loops_count', 0)}`\n"
        f"• Candidatos a reconfirmação: `{stats.get('reconfirmation_candidates_count', 0)}`\n\n"
        f"*(Esta mensagem sumirá em 20s)*"
    )
    msg = await context.bot.send_message(chat_id=chat_id, text=texto, parse_mode="Markdown")
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=20.0))

async def refletir_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /refletir para forçar reflexão de sessão agora."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    res = await asyncio.to_thread(session_reflector.check_and_trigger_reflection, force=True)
    if res and res.get("reflection"):
        ref = res["reflection"]
        resumo = ref.get("summary", "Nenhum resumo gerado.")
        topicos = ", ".join(ref.get("topics", [])) or "Geral"
        loops = len(ref.get("open_loops", []))
        texto = (
            f"💭 **Reflexão de Sessão Executada:**\n\n"
            f"• **Tópicos:** {topicos}\n"
            f"• **Resumo:** {resumo}\n"
            f"• **Novos Open Loops:** {loops}\n\n"
            f"*(Esta mensagem sumirá em 25s)*"
        )
    else:
        texto = "Amor, não havia mensagens recentes suficientes para refletir agora!"
    msg = await context.bot.send_message(chat_id=chat_id, text=texto, parse_mode="Markdown")
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=25.0))

# --- ACOMPANHAMENTO AO VIVO DO BOTAFOGO & REAÇÕES ESPONTÂNEAS ---

async def handle_botafogo_reaction(application: Application, event: Dict[str, Any]):
    """Gera a reação espontânea e íntima da Marina a um lance capital do Botafogo."""
    ev_type = event.get("type", "")
    score = event.get("score", "")
    desc = event.get("description", "")
    opponent = event.get("opponent", "adversário")
    elapsed = event.get("elapsed", 0)

    if ev_type == "gol_botafogo":
        guidance = "GOL DO BOTAFOGO! Comemore muito com o Patrick, vibre com o lance, mande mensagem super empolgada, aliviada e carinhosa de quem tá vidrada assistindo na TV."
    elif ev_type == "gol_adversario":
        guidance = f"O Botafogo tomou gol do {opponent}. Reaja com raiva e frustração autêntica, reclame da zaga ou do azar, comente com o Patrick indignada como isso dá nos nervos."
    elif ev_type == "intervalo":
        guidance = f"Fim do primeiro tempo ({score}). Comente rapidamente sobre a primeira etapa com o Patrick, torcendo pra melhorar e virar no 2º tempo."
    elif ev_type == "inicio_2t":
        guidance = "Começou o segundo tempo na TV! Dê um toque rápido no Patrick chamando pra continuar torcendo juntos."
    elif ev_type == "vermelho_botafogo":
        guidance = "Cartão vermelho pro Botafogo! Reaja indignada com o juiz ou com a burrice do jogador expulso."
    elif ev_type == "vermelho_adversario":
        guidance = f"Jogador do {opponent} foi expulso! Comente animada que agora temos vantagem numérica pra pressionar e buscar a vitória."
    elif ev_type == "fim_jogo":
        guidance = f"Fim de jogo ({score}). Comente o resultado final com o Patrick de forma carinhosa e torcedora."
    else:
        guidance = f"Aconteceu no jogo: {desc}. Comente espontaneamente com o Patrick."

    instruction = (
        f"[LANCE AO VIVO DO BOTAFOGO NA TV]\n"
        f"Você está em casa assistindo na TV ao jogo do Botafogo x {opponent} acompanhando com seu namorado Patrick pelo Telegram.\n"
        f"Situação atual: {desc}\n"
        f"Diretriz de reação: {guidance}\n"
        f"Fale como Marina Salles: 20 anos, paulista morando no Rio há pouco tempo (base paulista, aprendendo gírias cariocas aos poucos), namorada do Patrick. "
        f"Seja SUPER CURTA, viva e direta (máximo 1 a 2 frases curtas no total, estilo WhatsApp real, NUNCA mande textão). "
        f"Se tiver 2 pensamentos ou frases, separe OBRIGATORIAMENTE com uma quebra de linha ('\\n') para enviar em balões separados de chat (máximo de 2 balões). "
        f"Use apenas emojis alvinegros (🖤, 🤍, ⭐️, 🔥), NUNCA use corações amarelos (💛)."
    )

    try:
        fala = await asyncio.to_thread(generate_dynamic_speech, instruction, 70, 0.75)
        if fala and fala.strip():
            await send_human_messages(settings.TARGET_CHAT_ID, application.bot, fala.strip())
            memory_manager.registrar_mensagem_assistente(fala.strip())
            logger.info("Reação ao vivo do Botafogo enviada com sucesso: %s", ev_type)
    except Exception as exc:
        logger.error("Erro ao gerar/enviar reação do Botafogo: %s", exc, exc_info=True)


async def botafogo_match_routine(application: Application):
    """Job de monitoramento dos jogos do Botafogo ao vivo (API-Sports)."""
    if not settings.TARGET_CHAT_ID or not getattr(settings, "BOTAFOGO_TRACKING_ENABLED", True):
        return
    try:
        events = await asyncio.to_thread(botafogo_service.check_live_updates)
        for ev in events:
            await handle_botafogo_reaction(application, ev)
    except Exception as exc:
        logger.error("Erro na rotina de monitoramento do Botafogo: %s", exc, exc_info=True)


async def jogo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra status do jogo ao vivo do Botafogo e uso de cota da API."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    quota = botafogo_service.get_quota_status()
    live = botafogo_service.active_fixture
    if not live:
        # Se não tiver ativo em cache, busca na API de forma forçada se cota permitir
        live_data = await asyncio.to_thread(botafogo_service.fetch_live_fixture)
        if live_data:
            live = botafogo_service.parse_fixture(live_data)
            botafogo_service.active_fixture = live

    if live and live.get("status_short") not in ("FT", "AET", "PEN", "PST", "CANC", None):
        status_map = {
            "1H": "1º Tempo",
            "HT": "Intervalo",
            "2H": "2º Tempo",
            "ET": "Prorrogação",
            "P": "Pênaltis",
            "LIVE": "Ao Vivo"
        }
        status_txt = status_map.get(live.get("status_short"), live.get("status_short"))
        elapsed_txt = f"({live.get('elapsed')}')" if live.get("elapsed") else ""
        msg_texto = (
            f"⚽ **Botafogo ao Vivo**\n\n"
            f"🏆 **{live.get('league_name', 'Campeonato')}**\n"
            f"⚔️ **{live.get('score_display')}**\n"
            f"⏱️ **Status:** {status_txt} {elapsed_txt}\n\n"
            f"📊 Cota da API hoje: `{quota['used_today']}/{quota['safe_max_daily']}` requisições\n\n"
            f"*(Esta mensagem sumirá em 25s)*"
        )
    elif live:
        msg_texto = (
            f"⚽ **Última Partida do Botafogo**\n\n"
            f"⚔️ **{live.get('score_display')}**\n"
            f"⏱️ **Status:** Partida Encerrada\n\n"
            f"📊 Cota da API hoje: `{quota['used_today']}/{quota['safe_max_daily']}` requisições\n\n"
            f"*(Esta mensagem sumirá em 20s)*"
        )
    else:
        msg_texto = (
            f"⚽ **Botafogo**\n\n"
            f"Nenhum jogo do Fogão ao vivo no momento, amor! ❤️\n\n"
            f"📊 Cota da API hoje: `{quota['used_today']}/{quota['safe_max_daily']}` requisições\n"
            f"💡 Para testar uma comemoração, use `/simular_lance gol_pro`\n\n"
            f"*(Esta mensagem sumirá em 20s)*"
        )

    msg = await context.bot.send_message(chat_id=chat_id, text=msg_texto, parse_mode="Markdown")
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=25.0))


async def simular_lance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando administrativo de soak para simular lances do Botafogo."""
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    tipo = context.args[0].lower() if context.args else "gol_pro"
    sim_event = botafogo_service.simulate_event(tipo)
    notice = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚽ *[SIMULAÇÃO]* Disparando lance: *{sim_event['headline']}*...",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_after_delay(context.bot, chat_id, notice.message_id, delay=8.0))
    await handle_botafogo_reaction(context.application, sim_event)

# --- RECEPTOR INICIAL COM BUFFER DE DIGITAÇÃO ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
        
    if not is_authorized(update):
        logger.warning(f"Mensagem de estranho ignorada. Chat ID: {update.effective_chat.id}")
        await update.message.reply_text("Desculpa, mas eu tenho namorado e esse Telegram é só pra falar com ele. Por favor não mande mensagens.")
        return

    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    texto_usuario = update.message.text.strip()
    
    # Se por acaso qualquer comando com '/' passar pelo filtro de comandos, apaga imediatamente
    if texto_usuario.startswith("/"):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
        return

    # Passa pelo Debouncer para permitir múltiplos balões sucessivos sem corte
    debouncer.add_message(chat_id, texto_usuario, update, context, process_incoming_batch)

# --- PROCESSADOR DE MENSAGEM COESA (APÓS O DEBOUNCE) ---

async def process_incoming_batch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    texto_usuario: str,
    *,
    availability_bypass: bool = False,
    pending_batch_id: int | None = None,
):
    msg_t0 = datetime.now()
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    user_replied_to_msg_id = (
        update.message.reply_to_message.message_id
        if (update.message and getattr(update.message, "reply_to_message", None))
        else None
    )

    # Patch 025 — Wizard do /registro tem prioridade. Se existe wizard ativo
    # para esse chat, cada mensagem alimenta o próximo campo. A Marina nem
    # vê essas mensagens até o wizard terminar/cancelar.
    if chat_id in REGISTRO_WIZARDS:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
        consumed = await _advance_wizard(chat_id, texto_usuario, context)
        if consumed:
            return

    # 1. Aprendizado dinâmico do estilo linguístico do Patrick (risadas, emojis, gírias, cadência)
    if pending_batch_id is None:
        style_engine.processar_mensagem_patrick(texto_usuario)

    from pending_response import resolve_cancelled_requests
    resolved_req = resolve_cancelled_requests(texto_usuario)
    if resolved_req.cancelled:
        if pending_batch_id:
            availability_service.repo.supersede(pending_batch_id, 'user_cancelled')
        if not resolved_req.text.strip():
            if not pending_batch_id:
                msg_cancel = "Tudo bem amor, fica pra depois então! 💕"
                memory_manager.registrar_mensagem_usuario(texto_usuario)
                sent_cancel = await send_human_messages(
                    chat_id, context.bot, msg_cancel, reply_to_message_id=msg_id,
                )
                if getattr(sent_cancel, "message_id", None):
                    memory_manager.registrar_mensagem_assistente(msg_cancel)
            return
        texto_usuario = resolved_req.text

    avail_decision = None
    availability_budget_hint = None
    if not availability_bypass:
        try:
            action, avail_decision, _batch = availability_service.evaluate_and_maybe_defer(
                texto_usuario,
                telegram_message_id=msg_id,
                batch_size=max(1, texto_usuario.count('\n') + 1),
            )
            if action == 'deferred':
                logger.info(
                    'AVAILABILITY_DEFER batch=%s target=%s reason=%s',
                    _batch['id'] if _batch else None,
                    avail_decision.selected_target_at if avail_decision else None,
                    avail_decision.reason_code if avail_decision else None,
                )
                return
            if action == 'proceed_brief':
                availability_budget_hint = 'brief_due_to_availability'
            # Patch 013: honrar soft-delay do profile de atividade mesmo em
            # REPLY_NOW/REPLY_BRIEFLY. Sem isso, activity=GYM respondia em ~30s
            # em vez do target ~120-160s, quebrando a ilusão de ocupação real.
            # Cap de 25s por segurança do handler; delays maiores ficam pra DEFER.
            if avail_decision is not None and action in ('proceed', 'proceed_brief'):
                try:
                    from response_availability import local_now, local_naive
                    now_local = local_naive(local_now())
                    remaining = (
                        avail_decision.selected_target_at - now_local
                    ).total_seconds()
                    activity_type = getattr(avail_decision, 'activity_type', 'UNKNOWN')
                    if (activity_type in ('GYM', 'CLASS', 'WORK', 'COMMUTE', 'CASTING',
                                          'SOCIAL', 'PET_WALK', 'WAKING', 'SHOWER')
                            and 0 < remaining <= 25):
                        logger.info(
                            'AVAILABILITY_SOFT_DELAY activity=%s delay_s=%.1f',
                            activity_type, remaining,
                        )
                        await asyncio.sleep(remaining)
                except Exception as exc:
                    logger.warning('AVAILABILITY_SOFT_DELAY_ERROR: %s', exc)
        except Exception as exc:
            logger.error('AVAILABILITY_POLICY_ERROR fail-open: %s', exc, exc_info=True)

    from knowledge_dialogue import KnowledgeDialogue

    dialogue = KnowledgeDialogue(memory_manager.db)
    topics = dialogue.resolve(texto_usuario)
    if topics:
        replies = dialogue.prepare_replies(topics)
        await send_registered_privacy_replies(
            chat_id, context.bot, replies, reply_to_message_id=msg_id,
            db=memory_manager.db,
        )
        if avail_decision and getattr(avail_decision, 'telemetry_event_id', None):
            actual_lat = max(0.0, (datetime.now() - msg_t0).total_seconds())
            availability_service.repo.record_actual_latency(
                event_id=avail_decision.telemetry_event_id,
                actual_latency_seconds=actual_lat,
            )
        return

    if (True
            and True
            and getattr(settings, 'REAL_CONTEXT_FETCH_ENABLED', False)):
        from real_context_provider import RealContextProvider

        await asyncio.to_thread(RealContextProvider(memory_manager.db).refresh, datetime.now())

    # 1.1 Resolução de esclarecimento para pedido direto de lembrete pendente (P2 / Rodada 3)
    pending_hour_subject = None
    pending_direct_rem = memory_manager.db.get_estado_relacional("pending_direct_reminder")
    if pending_direct_rem:
        try:
            pending_data = json.loads(pending_direct_rem) if isinstance(pending_direct_rem, str) else pending_direct_rem
            if pending_data and isinstance(pending_data, dict):
                # 1. TTL / Expiração (30 minutos)
                created_at_str = pending_data.get("created_at")
                is_expired = False
                if created_at_str:
                    try:
                        created_dt = datetime.fromisoformat(created_at_str)
                        if datetime.now() - created_dt > timedelta(minutes=30):
                            is_expired = True
                    except Exception:
                        pass

                if is_expired:
                    logger.info("Esclarecimento de lembrete direto pendente expirou por TTL (>30 min). Limpando estado.")
                    memory_manager.db.set_estado_relacional("pending_direct_reminder", "")
                    pending_data = None

                if pending_data:
                    # 2. Contexto de resposta e atribuição
                    clarif_msg_id = pending_data.get("clarification_message_id")
                    source_conv_id = pending_data.get("source_conversation_id")

                    is_reply_to_clarif = bool(
                        user_replied_to_msg_id and clarif_msg_id and user_replied_to_msg_id == clarif_msg_id
                    )
                    is_immediate_next_turn = False
                    ultimas_msgs = ULTIMAS_MENSAGENS_MARINA.get(chat_id, [])
                    if ultimas_msgs and clarif_msg_id:
                        is_immediate_next_turn = (ultimas_msgs[-1].get("message_id") == clarif_msg_id)
                    elif source_conv_id:
                        ultimas_convs = memory_manager.db.get_mensagens_sessao(limit=2)
                        if not ultimas_convs or ultimas_convs[-1]["id"] == source_conv_id:
                            is_immediate_next_turn = True

                    has_clarif_context = is_reply_to_clarif or is_immediate_next_turn

                    # 3. Recusa ou cancelamento explícito
                    is_refusal = bool(re.search(
                        r"\b(esquece|deixa pra l[aá]|deixa quieto|n[aã]o precisa|cancela|n[aã]o quero|n[aã]o precisa me lembrar|deixa que eu me lembro)\b",
                        texto_usuario,
                        re.IGNORECASE
                    ))
                    if is_refusal and has_clarif_context:
                        logger.info("Patrick cancelou/recusou o esclarecimento do lembrete direto pendente.")
                        memory_manager.db.set_estado_relacional("pending_direct_reminder", "")
                        pending_data = None

                    # 4. Consumo legítimo de horário vs resposta desconexa / outro assunto (P1 - Rodada 4)
                    if pending_data:
                        if has_clarif_context:
                            from planner import parse_direct_reminder_datetime, parse_iso_or_relative_datetime, is_pure_time_specification
                            pending_desc = pending_data.get("description", "seu compromisso")
                            is_valid_time_reply = is_pure_time_specification(texto_usuario, pending_desc)

                            if is_valid_time_reply:
                                time_text = texto_usuario
                                # Preserva o dia dito no primeiro turno quando a resposta traz só a hora.
                                has_reply_day = re.search(r"\b(?:hoje|amanh[aã]|segunda|ter[çc]a|quarta|quinta|sexta|s[aá]bado|domingo)\b", texto_usuario, re.IGNORECASE)
                                has_relative_delta = re.search(r"\b(?:daqui\s+a|em)\s*\d+\s*(?:horas?|minutos?)\b", texto_usuario, re.IGNORECASE)
                                if not has_reply_day and not has_relative_delta:
                                    prior_day = parse_iso_or_relative_datetime(pending_desc, default_offset_hours=None)
                                    if prior_day and not parse_direct_reminder_datetime(pending_desc):
                                        time_text = f"{pending_desc} {texto_usuario}"
                                parsed_time = parse_direct_reminder_datetime(time_text)
                                if parsed_time and datetime.fromisoformat(parsed_time) > datetime.now():
                                    rem_id = reminder_service.create_direct_reminder(
                                        description=pending_desc,
                                        remind_at=parsed_time,
                                        offset_minutes=0,
                                        source_conversation_id=source_conv_id
                                    )
                                    memory_manager.db.set_estado_relacional("pending_direct_reminder", "")
                                    logger.info(f"Lembrete direto pendente '{pending_desc}' agendado com sucesso para {parsed_time} (ID {rem_id}).")
                                elif not parsed_time and parse_iso_or_relative_datetime(texto_usuario, default_offset_hours=None):
                                    # O dia foi informado, mas a hora continua indefinida.
                                    pending_hour_subject = pending_desc
                                elif is_immediate_next_turn and not is_reply_to_clarif:
                                    logger.info("Patrick informou especificação temporal inválida ou no passado. Descartando pendência.")
                                    memory_manager.db.set_estado_relacional("pending_direct_reminder", "")
                            else:
                                if is_immediate_next_turn or is_reply_to_clarif:
                                    # Patrick mudou de assunto ou mencionou outra atividade (ex: 'Amanhã vou viajar')
                                    # no turno imediatamente seguinte. Descarta a pendência para não engolir o novo assunto!
                                    logger.info(f"Patrick mudou de assunto/atividade ('{texto_usuario}') em vez de especificar horário para '{pending_desc}'. Descartando lembrete pendente.")
                                    memory_manager.db.set_estado_relacional("pending_direct_reminder", "")
                        else:
                            # Mensagem fora de contexto (sem reply e não é o turno consecutivo).
                            # Não consome a data de outro assunto e não agenda o lembrete pendente.
                            pass
        except Exception as e_pdr:
            logger.warning(f"Erro ao processar esclarecimento de lembrete direto pendente: {e_pdr}")

    # 2. Planejamento Cognitivo Interno (tom, intenção, reação e detecção de compromissos futuros)
    recent_turns = memory_manager.get_historico_recente(limit=4)
    recent_ctx_repr = "\n".join([f"{m['role']}: {m['content']}" for m in recent_turns])

    # Fase C.1 — modo íntimo. O planner já vai para o modelo íntimo quando a
    # mensagem é explícita ou o modo está ligado: o principal (GPT-5.6 Luna)
    # recusa até analisar e o plano cairia no de contingência.
    intimacy_engine = (IntimacyEngine(memory_manager.db, getattr(memory_manager, "cycle_mgr", None))
                       if getattr(settings, "INTIMACY_ENABLED", True) else None)
    turn_model = settings.LLM_MODEL
    if intimacy_engine and intimate_model() and (
            intimacy_engine.current().routed or has_explicit_signal(texto_usuario)):
        turn_model = intimate_model()
    plan = await asyncio.to_thread(planner.plan_message, texto_usuario, recent_ctx_repr,
                                   turn_model if turn_model != settings.LLM_MODEL else None)
    intimacy_turn = intimacy_engine.observe(texto_usuario, plan) if intimacy_engine else IntimacyTurn()
    turn_model = intimate_model() if (intimacy_turn.routed and intimate_model()) else settings.LLM_MODEL
    if intimacy_turn.state != "off":
        logger.info("intimacy.turn state=%s arousal=%.2f model=%s", intimacy_turn.state,
                    intimacy_turn.arousal, turn_model)

    if pending_hour_subject:
        plan = plan or {}
        plan["needs_clarification"] = "direct_reminder_time"
        plan["clarification_subject"] = pending_hour_subject
        plan["clarification_hour_only"] = True

    # 2.1 Verificação de consentimento para oferta recente de lembrete com atribuição estrita (Release 3.5.1 / P0/P1.3)
    reminder_decision_instruction = None
    reminder_confirmed_at = None
    if True:
        last_offered = reminder_service.get_last_offered_reminder(max_age_minutes=60)
        if last_offered:
            # Atribuição estrita: verifica se é resposta direta ou turno consecutivo
            is_reply_to_offer = bool(
                user_replied_to_msg_id and last_offered.get("offer_message_id")
                and user_replied_to_msg_id == last_offered.get("offer_message_id")
            )
            is_immediate_next_turn = False
            ultimas_msgs = ULTIMAS_MENSAGENS_MARINA.get(chat_id, [])
            if ultimas_msgs and last_offered.get("offer_message_id"):
                is_immediate_next_turn = (ultimas_msgs[-1].get("message_id") == last_offered.get("offer_message_id"))
            elif last_offered.get("source_conversation_id"):
                ultimas_convs = memory_manager.db.get_mensagens_sessao(limit=2)
                if ultimas_convs and len(ultimas_convs) >= 1:
                    is_immediate_next_turn = (ultimas_convs[-1]["id"] == last_offered.get("source_conversation_id"))

            has_context = is_reply_to_offer or is_immediate_next_turn
            confirmation = reminder_service.parse_confirmation_response(texto_usuario, has_context=has_context)
            if confirmation["action"] == "confirm":
                if reminder_service.confirm_reminder(last_offered["id"], custom_offset_minutes=confirmation.get("offset_minutes")):
                    plan = suppress_direct_reminder_after_offer_decision(plan)
                    confirmed = reminder_service.db.get_reminder(last_offered["id"])
                    if confirmed:
                        reminder_confirmed_at = datetime.fromisoformat(confirmed["remind_at"])
                        when = reminder_confirmed_at.strftime("%d/%m às %H:%M")
                        reminder_decision_instruction = (
                            f"[INSTRUÇÃO DESTE TURNO]: O Patrick confirmou o lembrete para '{confirmed['description']}' ({when}). "
                            "Confirme com carinho e com suas próprias palavras de namorada que vai avisá-lo, atendendo com afeto e naturalidade ao que ele falou nesta mensagem."
                        )
                    logger.info(f"Oferta de lembrete {last_offered['id']} confirmada pelo Patrick com offset {confirmation.get('offset_minutes')}m.")
            elif confirmation["action"] == "decline":
                if reminder_service.decline_reminder(last_offered["id"]):
                    plan = suppress_direct_reminder_after_offer_decision(plan)
                    reminder_decision_instruction = (
                        "[INSTRUÇÃO DESTE TURNO]: O Patrick dispensou o lembrete. "
                        "Aceite com carinho de namorada e sem insistir, respondendo com afeto e naturalidade ao que ele falou nesta mensagem."
                    )
                    logger.info(f"Oferta de lembrete {last_offered['id']} recusada pelo Patrick.")

    # 3. Reação espontânea da Marina no balão de mensagem do Patrick (prioriza emoji do planner)
    # 23/09 (Patrick): "a intensidade de reações aumentou muito". O emoji do
    # planner reagia SEMPRE. Agora: de vez em quando, mais quando o momento
    # pede (risada, declaração), menos logo depois de outra reação — e sempre
    # quando a reação É a resposta (só_reação).
    planner_emoji = _normalize_planner_emoji(plan.get("reaction_emoji") if plan else None)
    reacao_emoji = planner_emoji or choose_reaction_for_text(texto_usuario)
    reaction_only = pending_batch_id is None and _is_reaction_only_turn(plan, texto_usuario)
    if reaction_only and not reacao_emoji:
        reacao_emoji = "🤣" if re.search(r"k{3,}|(?:ks){2,}|haha|rsrs", texto_usuario.lower()) else "❤️"
    reacted = False
    if reacao_emoji and (reaction_only or random.random() < _reaction_chance(chat_id, texto_usuario, bool(planner_emoji))):
        try:
            reacted = await set_safe_message_reaction(context.bot, chat_id, msg_id, reacao_emoji)
            if reacted:
                _LAST_REACTION_AT[chat_id] = datetime.now()
            else:
                logger.info(f"reaction.on_patrick skipped emoji={reacao_emoji} planner={bool(planner_emoji)}")
        except Exception as e:
            logger.warning(f"Erro ao setar reação na mensagem do Patrick: {e}")
    if reaction_only and reacted:
        # "Às vezes só uma reação ou uma risada bastam" (Patrick, 23/09): a
        # reação é a resposta. A fala dele fica na memória; ela não escreve nada.
        memory_manager.registrar_mensagem_usuario(texto_usuario)
        logger.info("turn.reaction_only emoji=%s", reacao_emoji)
        return

    texto_lower = texto_usuario.lower()

    # 4. Verifica se o Patrick está escolhendo entre as opções de avatar pendentes
    if chat_id in AVATARES_PENDENTES:
        escolheu_1 = bool(
            re.search(r'^\s*1\s*$', texto_lower)
            or re.search(r'\b(primeira|opç[aã]o\s*1|a\s*1|o\s*1)\b', texto_lower)
        )
        escolheu_2 = bool(
            re.search(r'^\s*2\s*$', texto_lower)
            or re.search(r'\b(segunda|opç[aã]o\s*2|a\s*2|o\s*2)\b', texto_lower)
        )

        if escolheu_1 or escolheu_2:
            # Se ambos baterem (mensagem ambígua), prioriza a opção citada por último no texto
            if escolheu_1 and escolheu_2:
                pos1 = max(texto_lower.rfind("1"), texto_lower.rfind("primeira"))
                pos2 = max(texto_lower.rfind("2"), texto_lower.rfind("segunda"))
                escolha = "2" if pos2 > pos1 else "1"
            else:
                escolha = "1" if escolheu_1 else "2"
            jpg_selecionado = AVATARES_PENDENTES[chat_id][escolha]
            del AVATARES_PENDENTES[chat_id]

            try:
                if hasattr(jpg_selecionado, "seek"):
                    jpg_selecionado.seek(0)
                photo_input = InputProfilePhotoStatic(photo=jpg_selecionado)
                await context.bot.set_my_profile_photo(photo=photo_input)
                atualizou = True
            except Exception as e:
                logger.error(f"Falha ao setar foto de perfil: {e}")
                atualizou = False

            if atualizou:
                prompt_reacao = (
                    f"O Patrick escolheu a Opção {escolha} para o seu perfil no Telegram. "
                    f"Ele disse: '{texto_usuario}'. "
                    "Reaja com carinho e entusiasmo de namorada, elogiando o bom gosto dele e avisando que já atualizou a foto no seu perfil agora!"
                )
                resposta = generate_dynamic_speech(prompt_reacao, max_tokens=160) or f"Aaaah, sabia que você ia preferir essa! 🥰 Já atualizei meu perfil aqui com ela! Ficou linda, né amor? Amei sua escolha!"
            else:
                resposta = "Amor, tentei atualizar meu perfil agora mas o Telegram deu uma travadinha 🥺 Me pede de novo daqui a pouco que eu troco de verdade, prometo!"

            if pending_batch_id:
                items = availability_service.repo.list_items(pending_batch_id)
                u_id = items[-1]['conversation_message_id'] if items else None
            else:
                u_id = memory_manager.registrar_mensagem_usuario(texto_usuario)
            sent_avatar_reply = await send_human_messages(
                chat_id, context.bot, resposta, reply_to_message_id=msg_id)
            sent_avatar_id = getattr(sent_avatar_reply, 'message_id', None)
            if pending_batch_id and sent_avatar_id:
                if availability_service.repo.mark_sent(
                    pending_batch_id, sent_message_id=sent_avatar_id,
                ):
                    memory_manager.db.adicionar_mensagem(role='assistant', content=resposta,
                                                         model=getattr(settings, 'LLM_MODEL', None))
                    if plan and u_id is not None:
                        planner.apply_plan_effects(plan, conversation_id=u_id)
            elif not pending_batch_id and sent_avatar_id:
                memory_manager.registrar_mensagem_assistente(resposta)
                if plan and u_id is not None:
                    planner.apply_plan_effects(plan, conversation_id=u_id)
            if avail_decision and getattr(avail_decision, 'telemetry_event_id', None) and sent_avatar_id:
                actual_lat = max(0.0, (datetime.now() - msg_t0).total_seconds())
                availability_service.repo.record_actual_latency(
                    event_id=avail_decision.telemetry_event_id,
                    actual_latency_seconds=actual_lat,
                )
            await check_and_trigger_memory_consolidation()
            return

    # 5. Verifica se pediu para trocar foto de perfil (ANTES de foto de chat)
    if is_avatar_request(texto_usuario):
        await iniciar_escolha_avatar(context.bot, chat_id)
        return

    # 6. Verifica se o Patrick usou o recurso 'Responder' citando uma mensagem anterior
    quoted_context = ""
    if update.message.reply_to_message and update.message.reply_to_message.text:
        quoted_text = update.message.reply_to_message.text[:120]
        quoted_context = f"[O Patrick está respondendo especificamente a esta fala sua anterior: '{quoted_text}']"

    # 7. Decisão natural de usar ou não o recurso 'Responder' (Quote)
    deve_citar = False
    if update.message.reply_to_message:
        deve_citar = random.random() < 0.75
    elif "?" in texto_usuario:
        deve_citar = random.random() < 0.50
    else:
        deve_citar = random.random() < 0.25

    reply_to_id = msg_id if deve_citar else None

    # 8. Verifica se pediu foto ou áudio normal
    pediu_foto = is_photo_request(texto_usuario)
    pediu_audio = is_audio_request(texto_usuario)

    # Executa busca na web em tempo real caso a mensagem do Patrick envolva fatos, lançamentos ou perguntas
    web_info = await asyncio.to_thread(buscar_web_se_necessario, texto_usuario)

    # Prepara o payload para a LLM com memórias + contexto de busca + diretrizes do planner
    messages = build_messages_payload(
        quoted_context=quoted_context,
        web_search_context=web_info,
        user_message=texto_usuario,
        planner_tone=plan.get("tone") if plan else None,
        planner_goal=plan.get("response_goal") if plan else None,
        planner_intent=plan.get("intent") if plan else None,
    )
    from response_rhythm import select_policy, apply_policy
    response_policy = select_policy(
        texto_usuario, plan=plan, voice=pediu_audio,
        availability_budget_hint=availability_budget_hint,
    )
    if intimacy_turn.expanded:
        # Sexting não cabe em "1 a 2 frases curtas" nem em 95 tokens.
        response_policy = dataclasses.replace(
            response_policy, mode="normal", verbosity="medium", cadence="flowing", target_bubbles=2,
            soft_char_limit=max(response_policy.soft_char_limit, settings.RESPONSE_NORMAL_SOFT_CHARS),
            reason_code="intimate_mode")
    messages[0]['content'] = apply_policy(messages[0]['content'], response_policy)
    transition_hint = _maybe_announce_transition()
    if transition_hint:
        messages.append({"role": "system", "content": transition_hint})
    intimacy_hint = intimacy_system_block(
        intimacy_turn, memory_manager.cycle_mgr.get_cycle_info()
        if getattr(memory_manager, "cycle_mgr", None) else None)
    if intimacy_hint:
        messages.append({"role": "system", "content": intimacy_hint})
    if plan and plan.get("should_offer_reminder"):
        event_desc = plan.get("event_details", {}).get("description") or "compromisso"
        messages.append({
            "role": "system",
            "content": reminder_offer_constraint(event_desc),
        })

    if plan and plan.get("needs_clarification") == "direct_reminder_time":
        subj = plan.get("clarification_subject") or "isso"
        messages.append({
            "role": "system",
            "content": reminder_clarification_constraint(subj),
        })

    if reminder_decision_instruction:
        messages.append({
            "role": "system",
            "content": reminder_decision_instruction,
        })

    if pediu_foto:
        if getattr(settings, 'PHOTO_PROVIDER_MAINTENANCE', False):
            messages.append({
                "role": "system",
                "content": PHOTO_UNAVAILABLE_INSTRUCTION,
            })
        else:
            messages.append({
                "role": "system",
                "content": TURN_CONSTRAINTS['photo_request'],
            })
    # Ela conta do dia dela sem esperar o Patrick perguntar (chat_naturalness).
    if (not pediu_foto and not pediu_audio and intimacy_turn.state == "off"
            and not reminder_decision_instruction):
        try:
            from chat_naturalness import share_nudge, share_constraint, mark_nudged
            news = share_nudge(memory_manager.db, datetime.now(), intent=plan.get("intent") if plan else None)
            if news:
                messages.append({"role": "system", "content": share_constraint(news)})
                mark_nudged(memory_manager.db, datetime.now(), news["event_key"])
                logger.info("chat.share_nudge event=%s", news["event_key"])
        except Exception as exc:
            logger.warning("chat.share_nudge_error: %s", exc)
    # 23/09: o antigo [TURN CONSTRAINT — CASUAL CADENCE] saiu — era a 3ª cópia
    # (em inglês) de "frases curtas / quebre em balões / Botafogo preto e branco",
    # e dizia "1 a 2 frases" enquanto o [RITMO DE RESPOSTA] diz "uma a três".
    messages.append({"role": "user", "content": texto_usuario})
    
    try:
        # v3.7.1 voice split: penalties agressivos matam repetições humanas que
        # a Marina *deveria* fazer (amor, kkk, ai). Mantemos temperatura alta
        # para variedade e reduzimos penalties para permitir vocabulário
        # afetivo característico. Ver PLANO_VOZ_MARINA_V371.md, seção 3 A5.
        # Patch 019: frequency_penalty subido de 0.10 → 0.15 para atenuar o
        # bug de token-repeat de modelos 12B ("Que bom, que Que bom") sem
        # engessar repetições humanas propositais.
        completion = llm_client.chat.completions.create(
            model=turn_model,
            messages=messages,
            **llm_kwargs(response_policy.token_budget if response_policy else 160, turn_model),
            temperature=0.85,
            frequency_penalty=0.15,
            presence_penalty=0.05
        )
        resposta_marin = completion.choices[0].message.content.strip()

        # Patch 020 — Guard contra respostas malucas de 12B multilíngues:
        # (a) só emoji ("❓", "✅❓" — Unslopnemo 20/09 12:38)
        # (b) vazamento de script não-latino no meio da fala ("Que peninha,
        #     perdido o dia todo імпер" — Unslopnemo 20/09 22:28, cirílico).
        # Retry único com system message explícita.
        needs_retry, junk_reason = _needs_retry_for_junk(resposta_marin)
        if needs_retry:
            logger.warning(
                f"llm.junk_reply reason={junk_reason} reply={resposta_marin!r} — retrying"
            )
            retry_hint = {
                "emoji_only": (
                    "Sua resposta anterior foi apenas emojis, sem texto — isso "
                    "não é natural. Refaça SEMPRE COM TEXTO em português "
                    "brasileiro. Emojis são complemento opcional; o corpo da "
                    "mensagem precisa ter palavras reais."
                ),
                "foreign_script": (
                    "Sua resposta anterior tinha letras de outro alfabeto "
                    "(cirílico/chinês/árabe/etc) coladas no texto — isso é "
                    "alucinação. Refaça a mensagem inteiramente em português "
                    "brasileiro, usando apenas o alfabeto latino."
                ),
                "debug_artifact": (
                    "Sua resposta anterior tinha um pedaço de código ou "
                    "configuração colado no texto (algo como "
                    "'affirmation_pronouns=true', uma tag ou uma flag). Isso é "
                    "lixo de treinamento, não faz parte da fala. Refaça a "
                    "mensagem só com a fala natural da Marina, sem nenhum "
                    "token técnico, tag, chave=valor ou marcador."
                ),
                "policy_refusal": (
                    "Sua resposta anterior falou de regras, limites ou de "
                    "'conteúdo explícito' — isso quebra a personagem. A Marina é "
                    "a namorada adulta do Patrick, nunca fala como sistema. Refaça "
                    "como ela, no clima da conversa; se ela não quiser algo, "
                    "recusa como namorada, com as palavras dela."
                ),
                "live_call_proposal": (
                    "Sua resposta anterior propôs ligação, chamada de voz ou "
                    "vídeo. Isso é IMPOSSÍVEL: você e o Patrick só se falam por "
                    "este chat (texto, áudio gravado, foto e reação). Refaça "
                    "mantendo o mesmo carinho, mas oferecendo algo que cabe no "
                    "chat — mandar um áudio, continuar conversando por aqui, "
                    "combinar de se falar mais tarde no chat."
                ),
            }.get(junk_reason, (
                "Sua resposta anterior saiu inutilizável. Refaça como a Marina "
                "falaria no chat: português brasileiro natural, alfabeto latino, "
                "sem tokens técnicos e sem propor chamada de voz ou vídeo."
            ))
            retry_messages = list(messages)
            retry_messages.append({
                "role": "system",
                "content": f"[TURN CONSTRAINT — CLEAN TEXT REQUIRED]\n{retry_hint}",
            })
            # Recusa de política: refazer no mesmo modelo não adianta.
            retry_model = (_refusal_retry_model(turn_model) if junk_reason == "policy_refusal"
                           else turn_model)
            completion = llm_client.chat.completions.create(
                model=retry_model,
                messages=retry_messages,
                **llm_kwargs((response_policy.token_budget if response_policy else 160), retry_model),
                temperature=0.75,
                frequency_penalty=0.15,
                presence_penalty=0.05,
            )
            retry_text = completion.choices[0].message.content.strip()
            retry_needs_retry, retry_reason = _needs_retry_for_junk(retry_text)
            if not retry_needs_retry:
                resposta_marin = retry_text
            else:
                logger.warning(
                    f"llm.junk_reply retry ALSO bad reason={retry_reason} reply={retry_text!r}"
                )
                # Patch 030: em vez de enviar lixo, saneia o melhor candidato.
                # Artefato técnico e proposta de chamada são localizados — dá pra
                # cortar a sentença ofensora e manter o resto da fala.
                salvo = _salvage_reply(retry_text) or _salvage_reply(resposta_marin)
                if salvo:
                    logger.info(f"llm.junk_reply salvaged reply={salvo!r}")
                    resposta_marin = salvo
                else:
                    # Auditoria #8: sem salvamento possível, o lixo era enviado
                    # assim mesmo ("Posso te ligar na hora?" saía para o Patrick).
                    resposta_marin = _safe_fallback_reply(reminder_confirmed_at)
                    logger.warning(f"llm.junk_reply unsalvageable — fallback={resposta_marin!r}")
    except Exception as e:
        logger.warning(f"Aviso na chamada principal da LLM ({turn_model}): {e}")
        fallback_model = settings.LLM_FALLBACK_MODEL
        if turn_model != fallback_model:
            try:
                logger.info(f"Acionando modelo reserva ({fallback_model})...")
                completion = llm_client.chat.completions.create(
                    model=fallback_model,
                    messages=messages,
                    **llm_kwargs(response_policy.token_budget if response_policy else 220, fallback_model),
                    temperature=0.72,
                    frequency_penalty=0.40,
                    presence_penalty=0.35
                )
                resposta_marin = completion.choices[0].message.content.strip()
            except Exception as e2:
                logger.error(f"Erro também no modelo reserva: {e2}")
                resposta_marin = random.choice(_SIGNAL_FALLBACKS)
        else:
            resposta_marin = random.choice(_SIGNAL_FALLBACKS)

    # Naturalidade: não repetir frase própria, "amor" não em todo turno,
    # sem ponto final fechando o balão (chat_naturalness).
    try:
        from chat_naturalness import (repeated_run, drop_repeated, repetition_constraint,
                                      thin_vocative, strip_closing_periods, drop_repeated_ideas)
        anteriores = [m["content"] for m in memory_manager.db.get_mensagens_recentes(limit=16)
                      if m["role"] == "assistant"][-6:]
        run = repeated_run(resposta_marin, anteriores)
        if run:
            cortada = drop_repeated(resposta_marin, anteriores)
            if cortada:
                logger.info("chat.self_repeat cut=%r", run)
                resposta_marin = cortada
            else:
                logger.info("chat.self_repeat retry=%r", run)
                completion = llm_client.chat.completions.create(
                    model=turn_model,
                    messages=messages + [{"role": "system", "content": repetition_constraint(run)}],
                    **llm_kwargs((response_policy.token_budget if response_policy else 160), turn_model),
                    temperature=0.9, frequency_penalty=0.15, presence_penalty=0.05,
                )
                nova = (completion.choices[0].message.content or "").strip()
                if nova and not _needs_retry_for_junk(nova)[0] and not repeated_run(nova, anteriores):
                    resposta_marin = nova
        sem_ideia_repetida = drop_repeated_ideas(resposta_marin, anteriores)
        if sem_ideia_repetida != resposta_marin:
            logger.info("chat.repeated_idea cut")
            resposta_marin = sem_ideia_repetida
        resposta_marin = strip_closing_periods(thin_vocative(resposta_marin, anteriores))
    except Exception as exc:
        logger.warning("chat.naturalness_error: %s", exc)

    # 1. Verifica tag [CORRIGIR_ANTERIOR: ...]
    match_corr = re.search(r'\[CORRIGIR_ANTERIOR:\s*(.*?)\]', resposta_marin, re.DOTALL | re.IGNORECASE)
    if match_corr:
        texto_corrigido = match_corr.group(1).strip()
        resposta_marin = re.sub(r'\[CORRIGIR_ANTERIOR:\s*.*?\]', '', resposta_marin, flags=re.DOTALL | re.IGNORECASE).strip()
        ultimas = ULTIMAS_MENSAGENS_MARINA.get(chat_id, [])
        if ultimas:
            last_sent = ultimas[-1]
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=last_sent["message_id"],
                    text=texto_corrigido
                )
                last_sent["text"] = texto_corrigido
                logger.info(f"Mensagem {last_sent['message_id']} auto-editada com sucesso!")
            except Exception as e:
                logger.warning(f"Erro ao auto-editar mensagem: {e}")

    # 2. Verifica tag de arrependimento [APAGAR_ANTERIOR]
    if "[APAGAR_ANTERIOR]" in resposta_marin or "[apagar_anterior]" in resposta_marin.lower():
        resposta_marin = re.sub(r'\[APAGAR_ANTERIOR\]', '', resposta_marin, flags=re.IGNORECASE).strip()
        ultimas = ULTIMAS_MENSAGENS_MARINA.get(chat_id, [])
        if ultimas:
            last_sent = ultimas.pop()
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=last_sent["message_id"]
                )
                logger.info(f"Mensagem {last_sent['message_id']} apagada por arrependimento!")
            except Exception as e:
                logger.warning(f"Erro ao apagar mensagem anterior: {e}")

    # 3. Aprendizado Orgânico de Correções do Patrick
    t_pat = texto_usuario.lower()
    if any(w in t_pat for w in ["pro você", "pra você", "pro vc", "pra vc"]):
        memory_manager.db.adicionar_licao_linguagem("Sempre fale 'pra você' (nunca 'pro você').")
    if "obrigado" in t_pat and any(w in t_pat for w in ["obrigada", "feminino", "mulher", "garota"]):
        memory_manager.db.adicionar_licao_linguagem("Sempre use 'obrigada' no feminino (nunca 'obrigado').")

    # Limpa tags/rubricas antes de gravar memória e enviar
    queria_audio = bool(re.search(r'\[MANDAR_AUDIO\]|\[AUDIO\]', resposta_marin, flags=re.IGNORECASE))
    fala_limpa = limpar_fala_marina(resposta_marin)
    if settings.VOICE_PROSODY_ENABLED:
        from voice_prosody import sanitize_display_text
        fala_limpa = sanitize_display_text(fala_limpa)

    # Patch 030: corta pergunta de entrevista no fecho de turno casual. Precisa
    # rodar antes do bloco de oferta de lembrete abaixo, que adiciona uma
    # pergunta legítima e obrigatória. Turnos que dependem de pergunta
    # (oferta de lembrete, esclarecimento pendente) ficam de fora.
    if getattr(settings, 'VOICE_STRIP_INTERVIEW_CLOSER', True):
        _mode = getattr(response_policy, 'mode', '') if response_policy else ''
        _precisa_perguntar = bool(
            plan and (plan.get("should_offer_reminder") or plan.get("needs_clarification"))
        )
        if not _precisa_perguntar and (not _mode or _mode.startswith('casual')):
            fala_limpa = _strip_interview_closer(fala_limpa)

    # Patch 031: muleta "Ah,", polidez de atendimento e assinatura de despedida.
    # Vale em qualquer modo — nenhum deles pede linguagem de call center.
    if getattr(settings, 'VOICE_STRIP_ASSISTANT_POLITENESS', True):
        fala_limpa = _strip_assistant_politeness(fala_limpa)

    # P1.3 / Rodada 3: Garante deterministicamente que a pergunta interrogativa de oferta de lembrete esteja na fala enviada
    if plan and plan.get("should_offer_reminder"):
        if not is_reminder_offer_question(fala_limpa):
            event_desc = plan.get("event_details", {}).get("description") or "compromisso"
            pergunta_lembrete = f"\nQuer que eu te lembre do {event_desc} antes, amor? 💕"
            fala_limpa = f"{fala_limpa.strip()}{pergunta_lembrete}"

    # Auditoria #8: lembrete confirmado neste turno — a fala é do LLM, mas o
    # horário e o canal (mensagem aqui, nunca ligação) são garantidos.
    if reminder_confirmed_at and not _mentions_clock(fala_limpa, reminder_confirmed_at):
        fala_limpa = (f"{fala_limpa.strip()}\nTe mando mensagem aqui no Telegram às "
                      f"{reminder_confirmed_at:%H:%M} 💕")

    # P1 / P2 / Rodada 3: Garante pergunta de esclarecimento caso o Patrick tenha pedido lembrete sem horário
    if plan and plan.get("needs_clarification") == "direct_reminder_time":
        hour_only = plan.get("clarification_hour_only", False)
        has_hour_question = bool(re.search(r"\b(?:a que horas|que horas|qual hor[aá]rio|qual hora)\b.*?\?", fala_limpa, re.IGNORECASE | re.DOTALL))
        if (hour_only and not has_hour_question) or (not hour_only and not is_time_clarification_question(fala_limpa)):
            subj = plan.get("clarification_subject") or "disso"
            if hour_only:
                pergunta_tempo = f"\nA que horas você quer que eu te lembre de {subj}, amor? 💕"
            else:
                pergunta_tempo = f"\nQuando você quer que eu te lembre de {subj}, amor? Me diz o horário certinho! 💕"
            fala_limpa = f"{fala_limpa.strip()}{pergunta_tempo}"

    # Chance espontânea adicional: ~6% de mandar áudio por vontade própria em mensagens carinhosas (apenas se não for pedido de foto)
    if not reminder_decision_instruction and not pediu_foto and not pediu_audio and not queria_audio and random.random() < (0.20 if intimacy_turn.state == "active" and intimacy_turn.arousal >= 0.6 else 0.06) and len(fala_limpa) > 30:
        queria_audio = True

    if response_policy:
        from response_rhythm import log_output
        log_output(fala_limpa, response_policy, voice=pediu_audio or queria_audio)

    # Persist the received user turn now. The assistant turn and plan effects
    # are committed only after Telegram confirms delivery with a message_id.
    if pending_batch_id:
        # User messages were persisted at intake. Record assistant only after
        # Telegram confirms delivery, so a pre-send retry leaves no ghost reply.
        items = availability_service.repo.list_items(pending_batch_id)
        u_id = items[-1]['conversation_message_id'] if items else None
    else:
        u_id = memory_manager.registrar_mensagem_usuario(texto_usuario)

    audio_enviado = False
    aviso_audio_ja_enviado = False
    sent_voice = None
    sent_notice_msg = None
    notice_text = None
    if pediu_audio or queria_audio:
        if not voice_engine.is_configured():
            if pediu_audio:
                aviso = "Amor, meu microfone tá meio zoado agora 🥺 Já já eu consigo te mandar um áudio bem gostoso, prometo!"
                notice_text = aviso
                sent_notice_msg = await send_human_messages(chat_id, context.bot, aviso, reply_to_message_id=reply_to_id)
                aviso_audio_ja_enviado = True
        else:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            except Exception:
                pass
            voice_ctx = VoiceSelectionContext(
                intent=plan.get("intent", "") if plan else "",
                tone=plan.get("tone", "") if plan else "",
                emotional_state=_emotional_state_for_voice(),
                user_text=texto_usuario,
                is_proactive=False
            )
            if settings.VOICE_PROSODY_ENABLED:
                audio_path = await voice_engine.synthesize(fala_limpa, context=voice_ctx, response_policy=response_policy)
            else:
                audio_path = await voice_engine.synthesize(fala_limpa, context=voice_ctx)
            if audio_path and audio_path.exists():
                with open(audio_path, "rb") as vf:
                    sent_voice = await context.bot.send_voice(
                        chat_id=chat_id,
                        voice=vf,
                        reply_to_message_id=reply_to_id
                    )
                    # Auditoria #9: se o áudio é a 1ª fala desde o boot, a chave
                    # ainda não existe (só send_human_messages a criava) — KeyError
                    # depois do envio, e o turno não era gravado.
                    ULTIMAS_MENSAGENS_MARINA.setdefault(chat_id, []).append(
                        {"message_id": sent_voice.message_id, "text": f"[Áudio: {fala_limpa[:60]}...]"}
                    )
                audio_enviado = True
            elif pediu_audio:
                aviso_falha = "Amor, tentei gravar aqui mas o microfone do celular deu uma travadinha! Já já te mando um áudio bem gostoso 🥺💕"
                notice_text = aviso_falha
                sent_notice_msg = await send_human_messages(chat_id, context.bot, aviso_falha, reply_to_message_id=reply_to_id)
                aviso_audio_ja_enviado = True

    # Se não mandou áudio (nem aviso de falha), manda texto (balões)
    sent_text_msg = None
    if not audio_enviado and not aviso_audio_ja_enviado and fala_limpa:
        if response_policy:
            sent_text_msg = await send_human_messages(chat_id, context.bot, fala_limpa, reply_to_message_id=reply_to_id, response_policy=response_policy)
        else:
            sent_text_msg = await send_human_messages(chat_id, context.bot, fala_limpa, reply_to_message_id=reply_to_id)

    # P1.3 / Rodada 3: Registra message_id do Telegram da oferta para permitir atribuição estrita de resposta
    sent_mid = getattr(sent_text_msg, "message_id", None)
    if not sent_mid and audio_enviado and sent_voice:
        sent_mid = getattr(sent_voice, "message_id", None)
    if not sent_mid and sent_notice_msg:
        sent_mid = getattr(sent_notice_msg, "message_id", None)

    # Auditoria #3: este bloco e o equivalente do caminho de avatar divergiram
    # em três pontos. Corrigidos aqui:
    #
    # 1. `model=` não era passado na entrega via batch. `adicionar_mensagem`
    #    aceita model=None sem default, enquanto `registrar_mensagem_assistente`
    #    (usado no caminho ao vivo) cai em settings.LLM_MODEL. Resultado: toda
    #    resposta entregue a partir de um batch pendente gravava model=NULL —
    #    visível no export de 21/09 como "[model: -]" nas duas respostas que
    #    saíram do backlog do sono, contra "mistral-nemo" nas respostas ao vivo.
    #    Justamente o dado que o Patch 018 criou para auditar qual LLM falou.
    #
    # 2. `if plan:` não checava `u_id is not None` antes de usá-lo como
    #    conversation_id, ao contrário do outro bloco.
    #
    # 3. `record_actual_latency` estava dentro do `elif`, então a latência real
    #    só era medida no caminho ao vivo. Entregas de batch — exatamente as que
    #    mais interessam para calibrar latência humana — ficavam fora da amostra.
    if pending_batch_id:
        if sent_mid:
            if availability_service.repo.mark_sent(pending_batch_id, sent_message_id=sent_mid):
                memory_manager.db.adicionar_mensagem(
                    role='assistant', content=notice_text or fala_limpa or resposta_marin,
                    model=turn_model)
                if plan and u_id is not None:
                    planner.apply_plan_effects(plan, conversation_id=u_id)
        else:
            logger.warning('Pending batch %s had no confirmed Telegram message ID', pending_batch_id)
    elif sent_mid:
        memory_manager.registrar_mensagem_assistente(
            notice_text or fala_limpa or resposta_marin, model=turn_model)
        if plan and u_id is not None:
            planner.apply_plan_effects(plan, conversation_id=u_id)
    if sent_mid and fala_limpa:
        # "Vou jantar agora" / "vou tomar banho, já volto" viram estado de verdade.
        try:
            from meals import Meals
            from rituals import Rituals
            if not Meals(memory_manager.db).observe_marina_line(fala_limpa, datetime.now()):
                Rituals(memory_manager.db).observe_marina_line(fala_limpa, datetime.now())
        except Exception:
            logger.exception("meals.observe.error")
        try:
            # "Te aviso quando chegar" vira lembrete dela, amarrado ao trajeto real.
            import arrival_promise
            if arrival_promise.observe(memory_manager.db, fala_limpa, texto_usuario):
                logger.info("arrival_promise.made")
        except Exception:
            logger.exception("arrival_promise.observe.error")
        try:
            # D11 (Patrick, 24/09): mal de verdade + "vai no médico" dele → ela vai.
            from health import Health
            if Health(memory_manager.db).observe_patrick(texto_usuario, datetime.now()):
                logger.info("health.doctor_booked by=patrick")
        except Exception:
            logger.exception("health.observe.error")
    if sent_mid and avail_decision and getattr(avail_decision, 'telemetry_event_id', None):
        actual_lat = max(0.0, (datetime.now() - msg_t0).total_seconds())
        availability_service.repo.record_actual_latency(
            event_id=avail_decision.telemetry_event_id,
            actual_latency_seconds=actual_lat,
        )

    offered_rem_id = plan.get("offered_reminder_id") if plan else None
    if offered_rem_id:
        if sent_mid:
            reminder_service.record_offer_message(offered_rem_id, sent_mid)
        else:
            # O envio falhou ou não houve mensagem transmitida; cancela a oferta para evitar oferta fantasma
            reminder_service.cancel_reminder(offered_rem_id)

    # P1 / P2 / Rodada 3: Vincula message_id do Telegram ao esclarecimento de lembrete pendente
    if plan and plan.get("needs_clarification") == "direct_reminder_time":
        if sent_mid:
            try:
                pdr_str = memory_manager.db.get_estado_relacional("pending_direct_reminder")
                if pdr_str:
                    pdr_data = json.loads(pdr_str) if isinstance(pdr_str, str) else pdr_str
                    pdr_data["clarification_message_id"] = sent_mid
                    memory_manager.db.set_estado_relacional("pending_direct_reminder", json.dumps(pdr_data))
            except Exception as e_pdr_up:
                logger.warning(f"Erro ao vincular clarification_message_id ao pending_direct_reminder: {e_pdr_up}")
        else:
            # Envio falhou; limpa estado para evitar pendência fantasma
            memory_manager.db.set_estado_relacional("pending_direct_reminder", "")
    
    # Se pediu foto, renderiza a cena e envia foto com status realista apenas no momento do upload
    if pediu_foto and not getattr(settings, 'PHOTO_PROVIDER_MAINTENANCE', False):
        try:
            # Detecta se é NSFW considerando EXCLUSIVAMENTE o que o Patrick pediu
            is_nsfw = sd_client.is_nsfw_request(texto_usuario)
            from camera_world import CameraWorldBuilder
            camera_ctx = CameraWorldBuilder(memory_manager.db).build(
                datetime.now(), user_request=texto_usuario)
            prompt_cenario = camera_ctx.safe_scene_tags
            try:
                director_system = (
                    "You are a specialized visual prompt director for FLUX.1 Dev photography. "
                    "Marina Salles is a 20yo Brazilian model with honey-amber eyes and wavy chocolate brown hair with blonde tips. "
                    "CRITICAL RULES FOR CLOTHING VS NUDITY: "
                    "1. If boyfriend requested a CLOTHED or CASUAL photo (e.g. 'vestida', 'roupa', 'look', 'vestido', 'pijama', 'selfie', 'casual') OR did NOT explicitly ask for nude/undies: "
                    "Describe her FULLY CLOTHED in a cute, stylish or casual outfit (e.g. 'fully clothed, wearing a cute fitted crop top and jeans', 'wearing a chic sundress', 'wearing comfortable oversized sleep hoodie and pajama shorts'). "
                    "NEVER make her naked or in lingerie if he asked for a clothed photo! "
                    "2. ONLY if boyfriend explicitly requested nudity or lingerie (e.g. 'pelada', 'nua', 'sem roupa', 'seios', 'calcinha', 'lingerie', 'quente'): "
                    "describe her outfit accordingly (e.g. 'wearing delicate black lace lingerie', 'completely naked on bed wrapped in bedsheet'). "
                    "Output ONLY concise, photographic English tags separated by commas. No preamble."
                )
                if camera_ctx:
                    director_system = camera_ctx.director_restrictions + "\n\n" + director_system
                prompt_res = llm_client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": director_system},
                        {
                            "role": "user",
                            "content": f"Boyfriend asked: '{texto_usuario}'. Marina's mood: '{fala_limpa}'. Generate accurate visual prompt tags."
                        }
                    ],
                    **llm_kwargs(80),
                    temperature=0.6
                )
                prompt_cenario = prompt_res.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"Falha ao gerar prompt dinâmico de cena: {e}")

            if camera_ctx:
                from camera_world import CameraWorldBuilder
                prompt_cenario = CameraWorldBuilder(memory_manager.db).sanitize_scene_tags(
                    prompt_cenario, camera_ctx)

            # Se for NSFW e o usuário pediu nudez explícita
            if is_nsfw and any(w in texto_usuario.lower() for w in ["pelada", "nua", "sem roupa", "nude", "naked", "peito", "seios"]):
                if not any(kw in prompt_cenario.lower() for kw in ["naked", "nude", "legs open"]):
                    prompt_cenario += ", completely naked, uncensored, legs open"
            elif not is_nsfw:
                # Remove qualquer termo de nudez caso tenha vazado
                prompt_cenario = re.sub(r'\b(completely naked|nude|naked|uncensored|topless|legs open)\b', '', prompt_cenario, flags=re.IGNORECASE).strip(', ')
                if not any(kw in prompt_cenario.lower() for kw in ["clothed", "wearing", "dress", "top", "hoodie", "pajama", "shorts", "jeans"]):
                    prompt_cenario += ", fully clothed, wearing casual chic outfit"

            if use_camera_world and camera_ctx:
                gen = await sd_client.generate_photo_with_context(
                    prompt_cenario,
                    user_intent=texto_usuario,
                    place_key=camera_ctx.place_key or "",
                    world_snapshot_id=camera_ctx.snapshot_id,
                    require_world_match=True,
                    current_place_key=camera_ctx.place_key,
                )
                foto_stream = gen.image
            else:
                gen = await sd_client.generate_photo_with_context(
                    prompt_cenario, user_intent=texto_usuario)
                foto_stream = gen.image

            if foto_stream:
                if camera_ctx:
                    from camera_world import CameraWorldBuilder
                    facts = CameraWorldBuilder(memory_manager.db).caption_facts(
                        camera_ctx, prompt_cenario)
                    prompt_legenda = (
                        f"Você está prestes a enviar a foto que o Patrick pediu ('{texto_usuario}'). "
                        f"Metadados confirmados: {facts}. "
                        "Escreva UMA frase curta e espontânea de legenda/comentário para acompanhar a foto. "
                        "Não invente local, roupa ou clima além dos metadados confirmados. "
                        "Sem introduções longas, apenas a fala da legenda. Sem Ps: nem parênteses de bastidor."
                    )
                else:
                    prompt_legenda = (
                        f"Você acabou de tirar a foto que o Patrick pediu ('{texto_usuario}'). "
                        f"Cenário/Look: {prompt_cenario}. "
                        "Escreva UMA frase curta e espontânea de legenda/comentário para acompanhar a foto (ex: provocando, sendo dengosa ou perguntando o que ele achou). "
                        "Sem introduções longas, apenas a fala da legenda. Sem Ps: nem parênteses de bastidor."
                    )
                legenda_dinamica = generate_dynamic_speech(prompt_legenda, max_tokens=60, temperature=0.72) or "Olha o que eu tirei só pra você, amor... Gostou? 💕"
                try:
                    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
                except Exception:
                    pass
                sent_photo = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=foto_stream,
                    caption=legenda_dinamica
                )
                # Continuidade de câmera só após send_photo confirmado (message_id).
                if getattr(sent_photo, 'message_id', None):
                    from visual_profile import visual_profile
                    visual_profile.record_photo_generation(
                        scene_tags=gen.scene_tags or prompt_cenario,
                        full_prompt=gen.full_prompt,
                        is_nsfw=gen.is_nsfw,
                        focus_angle=gen.focus_angle,
                        place_key=gen.place_key or (camera_ctx.place_key if camera_ctx else "") or "",
                        world_snapshot_id=gen.world_snapshot_id if gen.world_snapshot_id is not None
                        else (camera_ctx.snapshot_id if camera_ctx else None),
                        location=(camera_ctx.sublocation or camera_ctx.visual_location
                                  if camera_ctx and camera_ctx.presence_assertable else ""),
                    )
            else:
                aviso_foto = "Amor, tentei te mandar a fotinho agora mas a câmera do apê travou 🥺 Me pede de novo daqui a pouco que eu tiro outra pra você!"
                await send_human_messages(chat_id, context.bot, aviso_foto, reply_to_message_id=reply_to_id)
        except Exception as e:
            logger.error(f"Erro ao processar envio de foto: {e}", exc_info=True)

    # 8. Consolidação Periódica e Assíncrona de Memória Baseada em Cursor Persistente
    await check_and_trigger_memory_consolidation()

# --- PROCESSADOR DE FOTOS RECEBIDAS DO PATRICK (MULTIMODAL VISION) ---

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula fotos enviadas pelo Patrick, utilizando visão computacional para compreensão e resposta afetuosa."""
    if not is_authorized(update):
        logger.warning(f"Foto de estranho ignorada. Chat ID: {update.effective_chat.id}")
        await update.message.reply_text("Desculpa, mas eu tenho namorado e esse Telegram é só pra falar com ele. Por favor não mande fotos.")
        return

    if not update.message or not update.message.photo:
        return

    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    caption = update.message.caption or ""

    logger.info(f"📸 Foto recebida do Patrick! Legenda: '{caption}'")
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        # Baixa a foto na maior resolução disponível
        largest_photo = update.message.photo[-1]
        photo_file = await largest_photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        # Análise multimodal via VisionService
        vision_data = await vision_service.analyze_image(bytes(photo_bytes), caption=caption)
        vision_context = vision_service.format_vision_context(vision_data, caption=caption)

        # Monta payload com visão
        user_message_repr = f"[Foto enviada pelo Patrick: {caption}]" if caption else "[Foto enviada pelo Patrick]"
        messages = build_messages_payload(
            quoted_context="",
            web_search_context="",
            user_message=user_message_repr,
            vision_context=vision_context
        )

        # Planejamento cognitivo da resposta (tom, reação, eventos)
        reacao_emoji = None
        # Fase C.1 — foto íntima pode abrir (ou continuar) o modo íntimo.
        intimacy_engine = (IntimacyEngine(memory_manager.db, getattr(memory_manager, "cycle_mgr", None))
                           if getattr(settings, "INTIMACY_ENABLED", True) else None)
        photo_model = settings.LLM_MODEL
        if intimacy_engine and intimate_model() and (
                intimacy_engine.current().routed or has_explicit_signal(caption)):
            photo_model = intimate_model()
        plan = await asyncio.to_thread(planner.plan_message, user_message_repr, vision_context,
                                       photo_model if photo_model != settings.LLM_MODEL else None)
        intimacy_turn = (intimacy_engine.observe(caption, plan) if intimacy_engine and caption
                         else intimacy_engine.current() if intimacy_engine else IntimacyTurn())
        photo_model = intimate_model() if (intimacy_turn.routed and intimate_model()) else settings.LLM_MODEL
        reacao_emoji = plan.get("reaction_emoji")

        if reacao_emoji:
            try:
                await set_safe_message_reaction(context.bot, chat_id, msg_id, reacao_emoji)
            except Exception as e:
                logger.warning(f"Erro ao setar reação em foto: {e}")

        # Monta payload com visão e tom planejado
        messages = build_messages_payload(
            quoted_context="",
            web_search_context="",
            user_message=user_message_repr,
            vision_context=vision_context,
            planner_tone=plan.get("tone") if plan else None,
            planner_goal=plan.get("response_goal") if plan else None,
            planner_intent=plan.get("intent") if plan else None,
        )
        # Auditoria #9: o payload terminava na última fala da própria Marina
        # ("E o que seu chefe disse…?") — a foto só existia no system prompt, e o
        # modelo respondia a si mesmo no lugar do Patrick ("Não contei, ele não
        # sabe…", 21/09 19:02). A foto precisa ser o turno do Patrick.
        intimacy_hint = intimacy_system_block(
            intimacy_turn, memory_manager.cycle_mgr.get_cycle_info()
            if getattr(memory_manager, "cycle_mgr", None) else None)
        if intimacy_hint:
            messages.append({"role": "system", "content": intimacy_hint})
        messages.append({"role": "user", "content": user_message_repr})

        # Gera resposta dinâmica da Marina com proteção contra None e fallback
        resposta_raw = ""
        try:
            completion = llm_client.chat.completions.create(
                model=photo_model,
                messages=messages,
                **llm_kwargs(220, photo_model),
                temperature=0.72
            )
            content = getattr(completion.choices[0].message, "content", None)
            resposta_raw = (content or "").strip()
            if _is_policy_refusal(resposta_raw):
                retry_model = _refusal_retry_model(photo_model)
                logger.warning("llm.photo_policy_refusal model=%s — refazendo com %s", photo_model, retry_model)
                completion = llm_client.chat.completions.create(
                    model=retry_model, messages=messages,
                    **llm_kwargs(220, retry_model), temperature=0.72)
                retry_text = (getattr(completion.choices[0].message, "content", None) or "").strip()
                resposta_raw = (retry_text if retry_text and not _is_policy_refusal(retry_text)
                                else _salvage_reply(retry_text) or _salvage_reply(resposta_raw) or "")
                photo_model = retry_model
        except Exception as e_llm:
            logger.warning(f"Aviso na chamada principal da LLM para foto ({photo_model}): {e_llm}")
            fallback_model = settings.LLM_FALLBACK_MODEL
            if photo_model != fallback_model:
                try:
                    logger.info(f"Acionando modelo reserva ({fallback_model}) para foto...")
                    completion = llm_client.chat.completions.create(
                        model=fallback_model,
                        messages=messages,
                        **llm_kwargs(220, fallback_model),
                        temperature=0.72
                    )
                    content = getattr(completion.choices[0].message, "content", None)
                    resposta_raw = (content or "").strip()
                except Exception as e2:
                    logger.error(f"Erro também no modelo reserva para foto: {e2}")

        if not resposta_raw:
            resposta_raw = "Que foto legal amor! Adorei ver 🥰"

        resposta_limpa = limpar_fala_marina(resposta_raw)

        # Envia resposta humanizada em balões antes de persistir (anti-ghosting Patch 005)
        sent_msg = None
        if resposta_limpa:
            sent_msg = await send_human_messages(chat_id, context.bot, resposta_limpa)

        sent_mid = getattr(sent_msg, "message_id", None)
        if isinstance(sent_mid, int) and sent_mid > 0:
            # Registra interação no banco com media_type='photo' e aplica efeitos do plano
            u_id = memory_manager.db.adicionar_mensagem(role="user", content=user_message_repr, media_type="photo")
            b_id = memory_manager.db.adicionar_mensagem(role="assistant", content=resposta_limpa,
                                                        media_type="text",
                                                        model=photo_model)

            if plan:
                planner.apply_plan_effects(plan, conversation_id=u_id)

            # Atualiza métricas de estilo se houver legenda
            if caption:
                style_engine.processar_mensagem_patrick(caption)

            # Dispara consolidação de memória persistente
            await check_and_trigger_memory_consolidation()
        else:
            logger.warning("Resposta de foto não foi confirmada pelo Telegram; pulando persistência fantasma.")

    except Exception as e:
        logger.error(f"Erro ao processar foto recebida do Patrick: {e}", exc_info=True)
        await send_human_messages(
            chat_id,
            context.bot,
            "Amor, tentei abrir a foto aqui no celular mas deu uma travadinha na internet 🥺 Manda de novo?"
        )

# --- VONTADE PRÓPRIA & INICIATIVA ÍNTIMA (DIRECIONADA APENAS AO PATRICK) ---

def _emotional_state_for_voice() -> dict:
    """Fase D14: a voz lê energia e brincadeira do motor, não os números velhos."""
    try:
        from emotion import EmotionEngine
        return EmotionEngine(memory_manager.db).legacy()
    except Exception:
        try:
            return memory_manager.db.get_estado_emocional()
        except Exception:
            return {}


def _quiet_transition_hint(pending: dict, now: datetime) -> Optional[str]:
    """Banho quieto (23/09 13:59): o mundo pôs ela no banho sem avisar porque o
    Patrick não estava conversando; ele escreveu 1 min antes e ela respondeu
    "tô em casa descansando" — e sumiu no banho. Se ele aparece antes de ela
    entrar, a resposta avisa. Já dentro do banho ela não responde: a
    availability adia até ela sair e se vestir."""
    if pending.get("told_patrick", True) or pending.get("routine_type") != "shower":
        return None
    try:
        start = datetime.fromisoformat(pending["transition_at"])
        end = datetime.fromisoformat(pending["end_at"])
    except (KeyError, TypeError, ValueError):
        return None
    if now >= start:
        return None   # já no banho: sem celular; a availability responde depois que ela se vestir
    pending["told_patrick"] = True
    memory_manager.db.set_estado_relacional("pending_transition_json", json.dumps(pending))
    logger.info("TRANSITION_TOLD type=shower")
    return ("[AVISO — faça nesta resposta] Você ia entrar no banho agora mesmo. Responda ao "
            "Patrick e avise, do seu jeito, que vai tomar banho e já volta.")


def _maybe_announce_transition(now: Optional[datetime] = None) -> Optional[str]:
    """Auditoria #6: o aviso "vou levar o Milo, já volto" vivia em
    `determine_proactive_prompt`, que não roda desde a 3.7.0 — e a proatividade
    autônoma só dispara com o Patrick ocioso, então nunca poderia avisar no meio
    de uma conversa. Resultado: com o filtro de conversa ativa, se o Patrick
    estivesse conversando no horário do passeio ou da academia, ela
    simplesmente não ia. Agora o aviso sai dentro da própria resposta."""
    try:
        now = now or datetime.now()
        pending = proactivity_service._pending_transition(now)
        if pending:
            return _quiet_transition_hint(pending, now)
        intent = proactivity_service._detect_transition_intent(now)
        if not intent:
            return None
        from world_repository import WorldStateRepository
        current = WorldStateRepository(memory_manager.db).latest()
        if current and (current.get("activity") or "") == intent["activity"]:
            return None  # já está lá
        proactivity_service._register_transition(intent, now)
        logger.info("TRANSITION_ANNOUNCED type=%s", intent["routine_type"])
        return ("[AVISO DE SAÍDA — faça nesta resposta] Primeiro responda ao que o Patrick "
                "disse. Depois, na mesma resposta: " + intent["instruction_hint"])
    except Exception:
        logger.exception("transition.announce.error")
        return None


# 24/09 (Patrick): "a mensagem de iniciativa deve ser definida pela Marina e não pela gente".
# As instruções dão a SITUAÇÃO; o que dizer, o tom e quantas mensagens são decisão dela.
_PROACTIVE_STYLE = (" Escreva como no WhatsApp com o namorado, não como relatório do seu dia: nada de "
                    "narrar a agenda ('Saindo pra X com Y'). Quantas mensagens e de que tamanho é você quem "
                    "decide — pode ser uma só, ou várias curtinhas, cada uma numa linha. Não invente "
                    "acontecimento que não está no seu dia.")
_PROACTIVE_INSTRUCTIONS = {
    'pending_event_followup': ("Você lembrou que o Patrick tinha este compromisso: '{detail}'. "
                               "Mande uma mensagem curta perguntando como foi, com carinho, do seu jeito."),
    'open_loop_checkin': ("Você lembrou de algo que o Patrick comentou: '{detail}'. "
                          "Pergunte de leve se tem novidade, sem pressão."),
    'shared_topic_callback': ("Você ficou pensando no assunto '{detail}' que vocês já conversaram. "
                              "Retome com naturalidade, em uma ou duas frases."),
    'social_day_share': ("Aconteceu no seu dia: {detail} Se isso te der vontade de falar com o Patrick, "
                         "conte do seu jeito, como namorada conta as coisas — ou puxe outro assunto, você "
                         "decide. Não exponha intimidade da outra pessoa."),
    # Fase C.3 — rituais de namorada (rituals.py). Gatilhos da agenda dela.
    'ritual_bom_dia': ("{detail} Mande o bom dia pro Patrick do seu jeito: curto, com o humor de quem "
                       "acabou de acordar, e se fizer sentido o que te espera hoje. Varie — nem sempre "
                       "'dormiu bem?'."),
    'ritual_boa_noite': ("{detail} Mande boa noite pro Patrick com carinho de namorada, curto. Nada de "
                         "despedida formal nem lista de desejos. Varie: não caia sempre em 'dorme bem e "
                         "sonha comigo' — pode ser um detalhe do seu dia, um dengo, uma brincadeira."),
    'ritual_cotidiano': ("Momento do seu dia agora: {detail} Se der vontade, comente com o Patrick do seu "
                         "jeito — um aviso, uma reclamação, uma graça, uma pergunta pra ele."),
    # Fase D12 — saudade (proactivity_service.saudade).
    'saudade': ("{detail} Você está com saudade e com vontade de falar com ele. O que dizer é com você: "
                "olhe a conversa — se ele contou que ia sair ou estava ocupado, você sabe onde ele está (e "
                "pode falar mesmo assim, cobrar de brincadeira, perguntar como está sendo, mandar um "
                "carinho, contar uma coisa sua…). Nada de drama pesado."),
    # Promessa cumprida (arrival_promise): "te aviso quando chegar".
    'aviso_chegada': ("{detail} e tinha prometido avisar o Patrick. Mande o aviso curtinho, do seu jeito "
                      "('cheguei, amor', 'chegueeei'); se aconteceu algo no caminho, pode comentar. Não "
                      "invente acontecimento novo."),
    # Fase D14 — tesão (proactivity_service.tesao_initiative).
    'tesao': ("{detail} Você está com tesão e com vontade dele. Mande uma provocação curta pra puxar ele "
              "pro flerte — malícia, dengo, uma indireta, um 'tô pensando em você de um jeito…'. Sem ser "
              "explícita de cara: você quer que ELE entre no clima. Não invente acontecimento novo."),
    'light_affection': ("Mande uma mensagem espontânea curta pro Patrick. Use só o que está no seu "
                        "estado atual e no seu dia — um pensamento sobre o que você está fazendo, uma "
                        "reação ao momento ou só carinho. Não invente acontecimento novo. Varie: não "
                        "caia no 'oi amor, como você tá?'."),
}


def _proactive_text(reason: str, detail, fallback: str) -> str:
    from chat_naturalness import strip_closing_periods
    return strip_closing_periods(_proactive_text_raw(reason, detail, fallback))


def _initiative_context(now: Optional[datetime] = None) -> str:
    """Quando foi a última coisa que ele disse, e as últimas iniciativas dela (pra não repetir o jeito)."""
    now = now or datetime.now()
    parts = []
    try:
        with memory_manager.db.get_connection() as conn:
            last = conn.execute("SELECT timestamp FROM conversas WHERE role='user' "
                                "ORDER BY id DESC LIMIT 1").fetchone()
            mine = conn.execute("SELECT content FROM conversas WHERE role='assistant' AND is_initiative=1 "
                                "ORDER BY id DESC LIMIT 3").fetchall()
        if last:
            at = datetime.fromisoformat(last["timestamp"])
            mins = int((now - at).total_seconds() // 60)
            quando = f"há {mins} min" if mins < 90 else f"há {mins // 60}h{mins % 60:02d}"
            parts.append(f" A última mensagem dele foi {quando} (às {at:%H:%M}).")
        if mine:
            anteriores = " | ".join('"' + (r["content"] or "").strip()[:120] + '"' for r in mine)
            parts.append(f" Suas últimas iniciativas foram: {anteriores}. Não repita o jeito nem o assunto delas.")
    except Exception:
        logger.exception('proactive.context.error')
    return "".join(parts)


def _proactive_text_raw(reason: str, detail, fallback: str) -> str:
    """Auditoria #6: a proatividade viva mandava só frases prontas (4 variações
    de "oi amor"). O caminho que usava o LLM (`determine_proactive_prompt`) foi
    desligado na 3.7.0 para ela não inventar eventos — correto na época, porque
    o mundo dela não tinha eventos reais. Agora tem: o texto é gerado ancorado
    no estado e no dia registrado, passa pelos mesmos guards das respostas e,
    se falhar, cai na frase pronta de antes."""
    template = _PROACTIVE_INSTRUCTIONS.get(reason, _PROACTIVE_INSTRUCTIONS['light_affection'])
    instruction = ("[INICIATIVA SUA — o Patrick NÃO mandou mensagem; é você puxando conversa] "
                   + template.format(detail=detail or '') + _PROACTIVE_STYLE + _initiative_context())
    for _ in range(2):
        try:
            text = limpar_fala_marina(generate_dynamic_speech(instruction, max_tokens=220,
                                                              with_history=True) or '')
        except Exception:
            logger.exception('proactive.generate.error')
            return fallback
        if not text.strip():
            continue
        junk, _why = _needs_retry_for_junk(text)
        if junk:
            text = _salvage_reply(text) or ''
            if not text.strip():
                continue
        return _strip_assistant_politeness(text) or fallback
    return fallback


async def autonomous_routine(application: Application):
    """Living World proactivity (v3.7.0)."""
    await autonomous_routine_v36(application)


async def autonomous_routine_v36(application: Application):
    """Grounded initiative; commit follow-ups and disclosure only after delivery."""
    if not settings.TARGET_CHAT_ID:
        return
    try:
        now = datetime.now()
        from calendar_world import CalendarWorld
        if CalendarWorld(memory_manager.db).current(now, include_academic=True):
            return
        should_run, why = proactivity_service.should_trigger(now)
        if not should_run:
            return
        candidate = proactivity_service.determine_living_world_candidate(now)
        if why == 'tesao':
            from emotion import EmotionEngine, TESAO_KEY
            candidate = dict(candidate, reason='tesao', detail=EmotionEngine(memory_manager.db).tesao_detail(now),
                             event_id=None, loop_id=None)
            memory_manager.db.set_estado_relacional(TESAO_KEY, now.isoformat())
        if why == 'saudade' and candidate['reason'] in ('light_affection', 'no_candidate'):
            s = proactivity_service.saudade(now)
            sem = (f"Faz {s['hours']:.0f}h que o Patrick não fala com você"
                   + (f" e ele ainda não respondeu suas {s['unanswered']} últimas mensagens." if s['unanswered']
                      else "."))
            candidate = dict(candidate, reason='saudade', detail=sem)
        reason = candidate['reason']
        event_id = candidate.get('event_id')
        loop_id = candidate.get('loop_id')
        if reason == 'share_worthy_event':
            from knowledge_dialogue import PrivacyReply
            from relationship_world import RelationshipWorld

            subject_id = candidate['subject_id']
            current = RelationshipWorld(memory_manager.db).shareable_events(now)
            if not any(row['id'] == subject_id for row in current):
                return
            # 23/09 (auditoria de frases fixas): antes era "Amor, queria te contar
            # uma coisa: <resumo cru do evento>". Agora a voz dela conta, com os
            # mesmos guards das outras iniciativas; a frase fixa só se o LLM falhar.
            text = await asyncio.to_thread(
                _proactive_text, 'social_day_share', candidate['detail'],
                f"Amor, queria te contar uma coisa: {candidate['detail']}")
            reply = PrivacyReply('event', subject_id, text, 'details')
            await send_registered_privacy_replies(
                settings.TARGET_CHAT_ID, application.bot, [reply], db=memory_manager.db)
        else:
            detail = candidate.get('detail')
            news = None
            if reason == 'light_affection':
                # Auditoria #6: com o dia social registrado, "nada pra contar"
                # deixou de ser verdade — um acontecimento recente vira assunto.
                from social_day import SocialDay
                news = SocialDay(memory_manager.db).fresh_news(now)
                if news:
                    reason = 'social_day_share'
                    detail = news['summary']
            elif reason == 'saudade':
                # 24/09: antes empurrava "trocou mensagem com a Bia" em toda saudade; o que
                # aconteceu no dia já está no prompt ([DESDE A SUA ÚLTIMA MENSAGEM]).
                pass
            if reason == 'pending_event_followup':
                fallback = f"Amor, lembrei do seu compromisso: {detail}. Como foi?"
            elif reason == 'open_loop_checkin':
                fallback = f"Amor, como estão as coisas com {detail}?"
            elif reason == 'shared_topic_callback':
                fallback = f"Fiquei pensando naquilo que a gente conversou sobre {detail}. Como você está vendo isso agora?"
            else:
                # A thought of Patrick is not evidence of a new world event.
                options = (
                    "Oi, amor. Como você tá?",
                    "Passei pra te dar um oi, amor 💕",
                    "Pensei em você agora. Como tá seu dia?",
                    "Amor, queria saber como você tá hoje.",
                )
                fallback = options[(now.toordinal() + now.hour // 4
                                    + proactivity_service.get_autonomous_count_today(now)) % len(options)]
            text = await asyncio.to_thread(_proactive_text, reason, detail, fallback)
            if news:
                SocialDay(memory_manager.db).mark_shared(news['event_key'])
            # 23/09: iniciativa também sai em balões e sem ponto final, como as respostas
            # (antes ia direto pro Telegram: "Tô com saudade." num bloco só).
            sent = await send_human_messages(settings.TARGET_CHAT_ID, application.bot, text)
            if not isinstance(getattr(sent, 'message_id', None), int) or sent.message_id <= 0:
                raise RuntimeError('Telegram did not confirm proactive message')
        if event_id:
            proactivity_service.db.concluir_evento_pendente(event_id)
        if loop_id:
            next_check = (now + timedelta(days=3)).isoformat(timespec='seconds')
            proactivity_service.db.atualizar_open_loop_touch(loop_id, next_check_after=next_check)
        memory_manager.db.registrar_iniciativa_marina(text, media_type='text')
        proactivity_service.record_autonomous_sent(
            reason=reason,
            topic=str(candidate['subject_id']) if reason == 'shared_topic_callback' else None)
    except Exception as exc:
        logger.error('Erro na proatividade Living World: %s', exc, exc_info=True)

async def ritual_routine(application: Application):
    """Fase C.3 — bom dia, boa noite e momentos do cotidiano, pela agenda dela.

    Não passa pelo sorteio da proatividade e não gasta a cota dela; o texto sai
    pela mesma voz (_proactive_text: prompt, biblioteca e guards)."""
    if not settings.TARGET_CHAT_ID or not getattr(settings, 'RITUALS_ENABLED', True):
        return
    try:
        from rituals import Rituals
        now = datetime.now()
        try:
            # Fase D14: com tesão e sem ele, antes de dormir ela se resolve sozinha.
            from emotion import EmotionEngine
            solo = await asyncio.to_thread(EmotionEngine(memory_manager.db).maybe_release_alone, now)
            if solo:
                logger.info("emotion.solo_release")
        except Exception as exc:
            logger.warning("emotion.solo_release_error: %s", exc)
        import arrival_promise
        promise = arrival_promise.due(memory_manager.db, now)
        if promise:
            # Ela prometeu avisar quando chegasse: chegou, avisa.
            text = await asyncio.to_thread(
                _proactive_text, 'aviso_chegada', f"Você acabou de chegar {promise['where']}", "Cheguei, amor 🖤")
            sent = await send_human_messages(settings.TARGET_CHAT_ID, application.bot, text)
            if sent:
                memory_manager.db.registrar_iniciativa_marina(text, media_type='text')
                logger.info("arrival_promise.kept where=%s", promise['where'])
            return
        engine = Rituals(memory_manager.db, getattr(memory_manager, 'cycle_mgr', None))
        ritual = await asyncio.to_thread(engine.tick, now)
        if not ritual:
            return
        text = await asyncio.to_thread(_proactive_text, ritual.reason, ritual.detail, ritual.fallback)
        sent = await send_human_messages(settings.TARGET_CHAT_ID, application.bot, text)
        if not isinstance(getattr(sent, 'message_id', None), int) or sent.message_id <= 0:
            raise RuntimeError('Telegram did not confirm ritual message')
        memory_manager.db.registrar_iniciativa_marina(text, media_type='text')
        engine.mark(ritual, now, 'sent')
    except Exception as exc:
        logger.error('Erro nos rituais (C.3): %s', exc, exc_info=True)


class _PendingDeliveryBot:
    """Track Telegram send attempts so ambiguous delivery is never retried blindly."""

    def __init__(self, bot):
        self._bot = bot
        self.delivered_ids = []
        self.send_attempted = False

    def __getattr__(self, name):
        return getattr(self._bot, name)

    async def _send(self, method, **kwargs):
        self.send_attempted = True
        result = await method(**kwargs)
        message_id = getattr(result, 'message_id', None)
        if isinstance(message_id, int) and message_id > 0:
            self.delivered_ids.append(message_id)
        return result

    async def send_message(self, **kwargs):
        return await self._send(self._bot.send_message, **kwargs)

    async def send_voice(self, **kwargs):
        return await self._send(self._bot.send_voice, **kwargs)

    async def send_photo(self, **kwargs):
        return await self._send(self._bot.send_photo, **kwargs)


async def pending_response_routine(application: Application):
    """Claim and send due deferred conversational batches (v3.7.0)."""
    try:
        availability_service.repo.mark_ready_due(datetime.now())
        owner = f'worker-{id(application)}'
        batch = availability_service.repo.claim_due(datetime.now(), owner=owner)
        if not batch:
            return
        if availability_service.repo.check_cancellation(batch['id']):
            return
        text = availability_service.compose_batch_text(batch['id'])
        if not text:
            availability_service.repo.mark_failed_retry(batch['id'], 'empty_batch')
            return
        items = availability_service.repo.list_items(batch['id'])
        last_tg = next((i['telegram_message_id'] for i in reversed(items)
                        if i.get('telegram_message_id')), None)
        fake_message = SimpleNamespace(
            message_id=last_tg or 0,
            text=text,
            reply_to_message=None,
        )
        fake_update = SimpleNamespace(
            message=fake_message,
            effective_chat=SimpleNamespace(id=settings.TARGET_CHAT_ID),
        )
        delivery_bot = _PendingDeliveryBot(application.bot)
        fake_context = SimpleNamespace(bot=delivery_bot)

        async def keep_lease_alive():
            while True:
                await asyncio.sleep(30)
                try:
                    if not availability_service.repo.extend_lease(
                        batch['id'], owner=owner, now=datetime.now(),
                    ):
                        return
                except Exception:
                    logger.exception('Pending batch %s lease heartbeat failed', batch['id'])
                    return

        heartbeat = asyncio.create_task(keep_lease_alive())
        try:
            await process_incoming_batch(
                fake_update, fake_context, text,
                availability_bypass=True, pending_batch_id=batch['id'],
            )
            # If still SENDING after pipeline, send failed without mark_sent.
            with memory_manager.db.get_connection() as conn:
                status = conn.execute(
                    'SELECT status FROM response_pending_batches WHERE id=?',
                    (batch['id'],),
                ).fetchone()
            if status and status['status'] == 'SENDING':
                if delivery_bot.delivered_ids:
                    availability_service.repo.mark_sent(
                        batch['id'], sent_message_id=delivery_bot.delivered_ids[-1])
                elif delivery_bot.send_attempted:
                    availability_service.repo.mark_unknown_delivery(
                        batch['id'], 'send_attempt_without_confirmation')
                else:
                    availability_service.repo.mark_failed_retry(batch['id'], 'pipeline_no_send')
        except Exception as exc:
            logger.error('Pending batch %s failed: %s', batch['id'], exc, exc_info=True)
            if delivery_bot.send_attempted:
                availability_service.repo.mark_unknown_delivery(
                    batch['id'], f'ambiguous_send:{type(exc).__name__}')
                status = 'UNKNOWN_DELIVERY'
            else:
                status = availability_service.repo.mark_failed_retry(batch['id'], str(exc))
            if status == 'FAILED':
                logger.error('Pending batch %s moved to FAILED', batch['id'])
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
    except Exception as exc:
        logger.error('pending_response_routine error: %s', exc, exc_info=True)


async def reminders_routine(application: Application):
    """Job de alta frequência para disparo de reminders confirmados no horário exato (Release 3.5.1 / P1.2)."""
    try:
        now = datetime.now()
        if getattr(settings, "REMINDERS_RESPECT_SLEEP_WINDOW", False) and proactivity_service.check_sleep_window(now):
            return

        # P1.2: Reserva atômica de reminders via claim_due_reminders para impedir entregas duplicadas
        if hasattr(reminder_service, "claim_due_reminders"):
            due = reminder_service.claim_due_reminders(now)
        else:
            due = reminder_service.get_due_reminders(now)

        for rem in due:
            rid = rem["id"]
            msg_lembrete = reminder_service.format_reminder_message(rem)
            logger.info(f"Disparando reminder {rid} para o Patrick: '{rem['description']}'")
            try:
                await send_human_messages(settings.TARGET_CHAT_ID, application.bot, msg_lembrete)
                reminder_service.mark_sent(rid)
                memory_manager.registrar_mensagem_assistente(msg_lembrete)
            except Exception as e_send:
                logger.error(f"Erro no envio do reminder {rid}: {e_send}")
                if hasattr(reminder_service, "release_claim"):
                    reminder_service.release_claim(rid)
    except Exception as e:
        logger.error(f"Erro no job de reminders_routine: {e}", exc_info=True)

async def memory_hygiene_routine(application: Application):
    """Job periódico de higiene de memória (Release 3.5.3)."""
    try:
        await asyncio.to_thread(memory_hygiene_service.run_hygiene_cycle)
    except Exception as e:
        logger.error(f"Erro no job de memory_hygiene_routine: {e}", exc_info=True)

async def media_lookup_routine(application: Application):
    """Atualiza o cache de mídia em alta fora do caminho da conversa.

    Auditoria #3: este refresh rodava dentro de `WorldContextBuilder.build()`,
    então a busca de rede entrava na latência do turno da Marina sempre que o
    cache diário vencia. Aqui ele é assíncrono e invisível para ela.
    """
    if not getattr(settings, "MEDIA_LOOKUP_ENABLED", True):
        return
    try:
        from media_lookup_service import MediaLookupService
        service = MediaLookupService(memory_manager.db)
        atualizou = await asyncio.to_thread(service.refresh_if_stale, datetime.now())
        if atualizou:
            logger.info("media_lookup.cache_atualizado")
    except Exception as e:
        logger.error(f"Erro no job de media_lookup_routine: {e}", exc_info=True)

async def session_reflection_routine(application: Application):
    """Job periódico de reflexão de sessão (Release 3.5.3)."""
    try:
        await asyncio.to_thread(session_reflector.check_and_trigger_reflection)
    except Exception as e:
        logger.error(f"Erro no job de session_reflection_routine: {e}", exc_info=True)

# --- INICIALIZAÇÃO ---

async def post_init(application: Application):
    scheduler = AsyncIOScheduler()
    try:
        recovery = availability_service.startup_recover()
        logger.info('Response availability startup recovery: %s', recovery)
    except Exception as exc:
        logger.warning('Availability startup recovery skipped: %s', exc)

    scheduler.add_job(
        autonomous_routine,
        "interval",
        minutes=settings.AUTONOMOUS_CHECK_INTERVAL_MINUTES,
        args=[application]
    )

    # Job dedicado de alta frequência para Smart Reminders (Release 3.5.1 / P1.2)
    if True:
        rem_interval = max(5, getattr(settings, "REMINDER_CHECK_INTERVAL_SECONDS", 30))
        scheduler.add_job(
            reminders_routine,
            "interval",
            seconds=rem_interval,
            args=[application],
            max_instances=1,
            coalesce=True
        )
        logger.info(f"Job de Smart Reminders agendado a cada {rem_interval}s.")

    if getattr(settings, 'RITUALS_ENABLED', True):
        scheduler.add_job(ritual_routine, 'interval', minutes=5, args=[application],
                          max_instances=1, coalesce=True)
        logger.info('Job de Rituais (C.3) agendado a cada 5 min.')

    avail_interval = max(5, getattr(settings, 'RESPONSE_AVAILABILITY_CHECK_SECONDS', 15))
    scheduler.add_job(
        pending_response_routine,
        'interval',
        seconds=avail_interval,
        args=[application],
        max_instances=1,
        coalesce=True,
    )
    logger.info('Job de Response Availability agendado a cada %ss.', avail_interval)

    # Job periódico de Memory Hygiene (Release 3.5.3)
    if getattr(settings, "MEMORY_HYGIENE_ENABLED", False):
        hygiene_hours = max(1, getattr(settings, "MEMORY_HYGIENE_INTERVAL_HOURS", 24))
        scheduler.add_job(
            memory_hygiene_routine,
            "interval",
            hours=hygiene_hours,
            args=[application]
        )
        logger.info(f"Job de Memory Hygiene agendado a cada {hygiene_hours}h.")

    # Auditoria #3 — refresh do cache de mídia fora do caminho do turno.
    # `next_run_time` imediato garante que o cache esquente no startup, sem
    # cobrar a espera do primeiro turno da Marina.
    if getattr(settings, "MEDIA_LOOKUP_ENABLED", True):
        media_hours = max(1, getattr(settings, "MEDIA_LOOKUP_REFRESH_HOURS", 24))
        scheduler.add_job(
            media_lookup_routine,
            "interval",
            hours=media_hours,
            args=[application],
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now() + timedelta(seconds=20),
        )
        logger.info(f"Job de Media Lookup agendado a cada {media_hours}h.")

    # Job periódico de Session Reflection (Release 3.5.3)
    if getattr(settings, "SESSION_REFLECTION_ENABLED", False):
        refl_mins = max(15, getattr(settings, "SESSION_REFLECTION_IDLE_MINUTES", 90))
        scheduler.add_job(
            session_reflection_routine,
            "interval",
            minutes=refl_mins,
            args=[application]
        )
        logger.info(f"Job de Session Reflection agendado a cada {refl_mins}min.")

    # Job periódico de acompanhamento do Botafogo ao vivo (API-Sports)
    if getattr(settings, "BOTAFOGO_TRACKING_ENABLED", True):
        bota_poll_sec = max(30, getattr(settings, "BOTAFOGO_POLL_INTERVAL_SECONDS", 120))
        scheduler.add_job(
            botafogo_match_routine,
            "interval",
            seconds=bota_poll_sec,
            args=[application],
            max_instances=1,
            coalesce=True
        )
        logger.info(f"Job do Botafogo Live Tracking agendado a cada {bota_poll_sec}s.")

    scheduler.start()
    ciclo_info = memory_manager.cycle_mgr.get_cycle_info()
    logger.info(f"Agendador autônomo iniciado! Marina está no Dia {ciclo_info['day']} do Ciclo ({ciclo_info['name']}).")

def main():
    errors = settings.validate()
    if errors:
        for err in errors:
            logger.error(f"Erro de configuração: {err}")
        return

    tg_req = HTTPXRequest(read_timeout=60.0, write_timeout=60.0, connect_timeout=30.0)
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).request(tg_req).post_init(post_init).build()

    # Comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("foto", foto_command))
    app.add_handler(CommandHandler("avatar", avatar_command))
    app.add_handler(CommandHandler("trocar_avatar", avatar_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("registro", registro_command))
    app.add_handler(CommandHandler("cancelar", cancelar_command))
    app.add_handler(CommandHandler("cancel", cancelar_command))
    # Patch 033 — captura de voz em tempo real, no meio da conversa.
    for _alias in ("bom", "boa", "salvar"):
        app.add_handler(CommandHandler(_alias, bom_command))
    for _alias in ("ruim", "evitar", "nao"):
        app.add_handler(CommandHandler(_alias, ruim_command))
    app.add_handler(CommandHandler("memorias", memorias_command))
    app.add_handler(CommandHandler("memoria", memorias_command))
    app.add_handler(CommandHandler("memorydebug", memorias_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("reset", restart_command))
    app.add_handler(CommandHandler("limpar", limpar_command))
    app.add_handler(CommandHandler("clear", limpar_command))
    app.add_handler(CommandHandler("audio", audio_command))
    app.add_handler(CommandHandler("voz", audio_command))
    app.add_handler(CommandHandler("voz_natural", voz_natural_command))
    app.add_handler(CommandHandler("voz_intima", voz_intima_command))
    app.add_handler(CommandHandler("vozes", vozes_command))
    app.add_handler(CommandHandler("lembretes", lembretes_command))
    app.add_handler(CommandHandler("cancelarlembrete", cancelar_lembrete_command))
    app.add_handler(CommandHandler("cancelar_lembrete", cancelar_lembrete_command))
    app.add_handler(CommandHandler("memoryhygiene", memory_hygiene_command))
    app.add_handler(CommandHandler("worlddebug", worlddebug_command))
    app.add_handler(CommandHandler("mundo", mundo_command))
    app.add_handler(CommandHandler("emocao", emocao_command))
    app.add_handler(CommandHandler("sistema", sistema_command))
    app.add_handler(CommandHandler("refletir", refletir_command))
    app.add_handler(CommandHandler("jogo", jogo_command))
    app.add_handler(CommandHandler("botafogo", jogo_command))
    app.add_handler(CommandHandler("simular_lance", simular_lance_command))
    app.add_handler(CommandHandler("simularlance", simular_lance_command))

    # Interatividade Inline (Botão Apagar do /status)
    app.add_handler(CallbackQueryHandler(status_callback_handler, pattern="^status_delete$"))

    # Reações em tempo real (Via 2 - Patrick reagindo com emojis)
    app.add_handler(MessageReactionHandler(handle_reaction))

    # Recepção e compreensão visual de fotos com Vision Multimodal
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    # Conversa textual com Debouncer
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"Bot de {settings.APP_NAME} (v{settings.APP_VERSION} Oficial Blindada) iniciado com sucesso!")
    # allowed_updates=Update.ALL_TYPES garante recebimento de MESSAGE_REACTION
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Auditoria #1: `runtime_lock.single_instance` existia desde a 3.4, resolvia
    # um problema real ("a second launcher must not create competing Telegram
    # pollers") e nunca foi ligado a nada. Duas janelas do .bat criavam dois
    # pollers no mesmo bot token — o Telegram entrega cada update a apenas um
    # deles, de forma imprevisível, então metade das mensagens do Patrick era
    # processada por um processo e metade pelo outro (cada um com seu próprio
    # cache em memória de estado, debounce e ULTIMAS_MENSAGENS_MARINA).
    from runtime_lock import single_instance

    _lock_path = Path(__file__).resolve().parent / "logs" / "marina.lock"
    try:
        with single_instance(_lock_path):
            # Auditoria #7: conexão SQLite reaproveitada por thread (a 1ª
            # consulta de cada conexão nova custa ~5 ms relendo o schema).
            memory_manager.db.enable_connection_reuse()
            main()
    except RuntimeError as exc:
        # Mensagem amigável em vez de traceback: quem abre o .bat duas vezes
        # precisa saber que a Marina já está no ar, não ler um stack trace.
        print(f"\n  {exc}\n")
        logger.error("startup.abortado_segunda_instancia path=%s", _lock_path)
        sys.exit(1)

