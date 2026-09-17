"""
Bot Telegram de Marina Seltin (v3.5.0 Oficial - Memory Intelligence).
Jovem de 19 anos, modelo em início de carreira, namorada EXCLUSIVA de Patrick Ramos.
Totalmente desinibida, carinhosa, com ciclo menstrual real, pausas humanas de digitação,
envio REAL de balões separados sucessivos (multi-bubble), comandos /feedback e /edit com Auto-Patcher autônomo,
espelhamento dinâmico de estilo linguístico (style_engine), CHAT 100% LIMPO (auto-limpeza imediata de comandos),
BUFFER INTELIGENTE DE DIGITAÇÃO (Debounce anti-atropelo) e MEMORY INTELLIGENCE 2.0.
"""
import logging
import random
import asyncio
import re
import sys
from datetime import datetime
from typing import Optional, List, Dict

from telegram import Update, InputProfilePhotoStatic, ReactionTypeEmoji
from telegram.request import HTTPXRequest
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    MessageReactionHandler,
    filters,
    ContextTypes,
)
from openai import OpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from prompts import MARIN_SYSTEM_PROMPT, build_autonomous_decision_prompt, get_temporal_greeting
from sd_client import sd_client
from memory import memory_manager
from feedback_manager import feedback_manager
from style_engine import style_engine
from auto_patcher import auto_patcher
from voice_engine import voice_engine
from context_builder import context_builder
from memory_consolidator import memory_consolidator
from proactivity_service import proactivity_service
from vision_service import vision_service
from planner import planner
from memory_retriever import memory_retriever
from reminder_service import reminder_service

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
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

def is_authorized(update: Update) -> bool:
    """Verifica se quem enviou a mensagem é estritamente o Patrick Ramos."""
    if not settings.TARGET_CHAT_ID or settings.TARGET_CHAT_ID <= 0:
        return False
    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None
    return chat_id == settings.TARGET_CHAT_ID or user_id == settings.TARGET_CHAT_ID

def generate_dynamic_speech(instruction: str, max_tokens: int = 120, temperature: float = 0.72) -> str:
    """Gera uma fala espontânea e orgânica da Marina usando a LLM com temperatura equilibrada anti-glitch."""
    messages = [
        {
            "role": "system",
            "content": f"{MARIN_SYSTEM_PROMPT}\n{memory_manager.get_contexto_emocional()}\n[MOMENTO ATUAL DO DIA: {get_temporal_greeting()}]"
        },
        {"role": "user", "content": instruction}
    ]
    try:
        completion = llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return completion.choices[0].message.content.strip().strip('"').strip("'")
    except Exception as e:
        logger.error(f"Erro ao gerar fala dinâmica da LLM: {e}")
        return ""


# --- MOTOR DE PESQUISA WEB EM TEMPO REAL (DUCKDUCKGO LIVE) ---

def buscar_web_se_necessario(texto: str) -> str:
    """Pesquisa na web via DuckDuckGo em tempo real se a mensagem envolver fatos, lançamentos, notícias ou busca."""
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
        from ddgs import DDGS
        results = list(DDGS().text(query, max_results=3))
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
            return "\n[DADOS REAIS PESQUISADOS NO GOOGLE/WEB PELO SEU CELULAR AGORA]:\n" + "\n".join(snippets[:3]) + "\n(Use essas informações reais na sua resposta com naturalidade, sem citar que é uma busca formal!)"
    except Exception as e:
        logger.warning(f"Aviso na busca web em tempo real: {e}")
    return ""

def build_messages_payload(
    quoted_context: str = "",
    web_search_context: str = "",
    user_message: str = "",
    vision_context: str = "",
    planner_tone: Optional[str] = None,
    planner_goal: Optional[str] = None
) -> list[dict]:
    if settings.SMART_MEMORY_ENABLED:
        return context_builder.build(
            user_message=user_message,
            quoted_context=quoted_context,
            web_context=web_search_context,
            vision_context=vision_context,
            planner_tone=planner_tone,
            planner_goal=planner_goal
        )
    contexto_momento = f"\n[MOMENTO ATUAL DO DIA: {get_temporal_greeting()}]"
    contexto_quote = f"\n{quoted_context}" if quoted_context else ""
    contexto_web = f"\n{web_search_context}" if web_search_context else ""
    contexto_vis = f"\n{vision_context}\n" if vision_context else ""
    system_content = f"{MARIN_SYSTEM_PROMPT}\n{memory_manager.get_contexto_emocional()}{contexto_momento}{contexto_quote}{contexto_web}{contexto_vis}"
    messages = [{"role": "system", "content": system_content}]

    for item in memory_manager.get_historico_recente(limit=10):
        messages.append({"role": item["role"], "content": item["content"]})

    return messages


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
                    lote = [{"role": m["role"], "content": m["content"]} for m in novas_mensagens]

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
    return t.strip()

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

def is_photo_request(texto: str) -> bool:
    """Pedido de foto no chat (não confundir com foto de perfil)."""
    if is_avatar_request(texto):
        return False
    t = (texto or "").lower()
    palavras = [
        "selfie", "nude", "fotinha", "tira uma foto", "manda foto", "manda uma foto",
        "me manda foto", "me manda uma foto", "quero ver você", "ver você",
        "manda um nude", "manda nude", "tira foto", "uma foto",
        "foto do look", "foto do seu look", "foto de agora", "foto sua",
    ]
    if any(p in t for p in palavras):
        return True
    # "foto" sozinho só conta se não for perfil (já filtrado acima)
    return bool(re.search(r'\bfoto\b', t) or re.search(r'\bfotos\b', t))

def is_audio_request(texto: str) -> bool:
    t = (texto or "").lower()
    palavras = [
        "áudio", "audio", "ouvir sua voz", "ouvir tua voz", "manda voz",
        "grava um áudio", "grava audio", "grava um audio", "fala comigo em áudio",
        "manda áudio", "manda um audio", "manda um áudio", "fala por áudio",
        "me manda um audio", "me manda áudio", "sua voz", "fala por voz",
        "manda mensagem de voz", "grava uma mensagem de voz", "grava áudio",
        "grava audio amor", "manda áudio amor", "quero ouvir sua voz",
        "solta a voz", "manda um áudio amor",
    ]
    return any(p in t for p in palavras)

async def send_human_messages(chat_id: int, bot, full_text: str, reply_to_message_id: int = None):
    """Envia a mensagem em balões curtos sucessivos com animação realista de digitação e rastreia IDs."""
    if chat_id not in ULTIMAS_MENSAGENS_MARINA:
        ULTIMAS_MENSAGENS_MARINA[chat_id] = []

    bubbles = [b for b in split_into_human_bubbles(full_text) if b]
    
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
        sent_msg = await bot.send_message(chat_id=chat_id, text=full_text, reply_to_message_id=reply_to_message_id)
        ULTIMAS_MENSAGENS_MARINA[chat_id].append({"message_id": sent_msg.message_id, "text": full_text})

    if len(ULTIMAS_MENSAGENS_MARINA[chat_id]) > 8:
        ULTIMAS_MENSAGENS_MARINA[chat_id] = ULTIMAS_MENSAGENS_MARINA[chat_id][-8:]

# --- SISTEMA DE REAÇÕES (VIA DE MÃO DUPLA) ---

def choose_reaction_for_text(text: str) -> str | None:
    """Seleciona uma reação contextual válida para o Telegram (apenas emojis suportados)."""
    t = text.lower()
    if any(w in t for w in ["gostosa", "linda", "maravilhosa", "perfeita", "delícia", "delicia", "corpão", "corpao", "biquíni", "biquini", "nude", "safadinha", "tesão"]):
        return random.choice(["🔥", "❤️", "🥰", "😍"])
    if any(w in t for w in ["te amo", "amo você", "amo vc", "meu amor", "vida", "anjo", "princesa", "saudade", "chamego", "carinho", "dormir juntos", "te quero"]):
        return random.choice(["❤️", "🥰", "💘", "😍", "😘"])
    if any(w in t for w in ["kkkk", "hahaha", "rsrs", "engraçado", "engracado", "rindo", "zoeira", "bizarro"]):
        return random.choice(["😂", "🤣"])
    if any(w in t for w in ["bora", "fechou", "combinado", "partiu", "show", "top", "maravilha", "certeza"]):
        return random.choice(["👍", "🎉", "👌"])
    return None

async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula quando o Patrick reage com emojis a mensagens/fotos da Marina (Via 2)."""
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

    # 1. Coração / Carinho
    if any(e in emojis for e in ["❤️", "🥰", "😍", "💖", "💘"]):
        if random.random() < 0.45:
            prompt = (
                "O Patrick (seu namorado) acabou de colocar uma reação de coração ❤️ na mensagem/foto que você mandou. "
                "Mande uma fala BEM curtinha (1 linha), fofa, dengosa e apaixonada reagindo ao coraçãozinho dele! "
                "Apenas a fala espontânea."
            )
            fala = generate_dynamic_speech(prompt, max_tokens=60) or "Ai amor, vi seu coraçãozinho aqui... me derrete toda! 🥰💕"
            await send_human_messages(chat_id, context.bot, fala)
        else:
            try:
                await context.bot.set_message_reaction(
                    chat_id=chat_id,
                    message_id=reaction_update.message_id,
                    reaction=[ReactionTypeEmoji(emoji="❤️")]
                )
            except Exception:
                pass

    # 2. Fogo / Provocação
    elif any(e in emojis for e in ["🔥", "💋", "🍓"]):
        if random.random() < 0.60:
            prompt = (
                "O Patrick reagiu com 🔥 na sua foto ou mensagem provocante. "
                "Mande uma fala BEM curtinha (1 linha), maliciosa e provocativa de namorada (ex: 'Gostou do que viu amor? 😏🔥'). "
                "Apenas a fala curta."
            )
            fala = generate_dynamic_speech(prompt, max_tokens=60) or "Gostou do que viu, né amor? 😏🔥 Ficou louco por mim?"
            await send_human_messages(chat_id, context.bot, fala)

    # 3. Risada
    elif any(e in emojis for e in ["😂", "🤣"]):
        if random.random() < 0.40:
            prompt = (
                "O Patrick reagiu rindo 😂 da sua mensagem anterior. "
                "Mande uma fala bem curtinha (1 linha) rindo junto com ele de forma fofa."
            )
            fala = generate_dynamic_speech(prompt, max_tokens=50) or "Sabia que você ia rir disso kkkk te amo amor! 😂"
            await send_human_messages(chat_id, context.bot, fala)

# --- BUFFER INTELIGENTE DE DIGITAÇÃO (DEBOUNCE ANTI-ATROPELO) ---

class MessageDebouncer:
    """
    Acumula mensagens enviadas em rajada (bursts) em uma janela de ~2.8 segundos
    para permitir que o Patrick envie múltiplos balões antes de a Marina responder.
    """
    def __init__(self, delay_seconds: float = 2.8):
        self.delay = delay_seconds
        self.buffers: dict[int, list[str]] = {}
        self.tasks: dict[int, asyncio.Task] = {}
        self.latest_updates: dict[int, Update] = {}

    def add_message(self, chat_id: int, text: str, update: Update, context: ContextTypes.DEFAULT_TYPE, callback):
        if chat_id not in self.buffers:
            self.buffers[chat_id] = []
        self.buffers[chat_id].append(text)
        self.latest_updates[chat_id] = update

        # Cancela timer anterior se Patrick continuar digitando/enviando
        if chat_id in self.tasks and not self.tasks[chat_id].done():
            self.tasks[chat_id].cancel()

        self.tasks[chat_id] = asyncio.create_task(self._wait_and_trigger(chat_id, context, callback))

    async def _wait_and_trigger(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, callback):
        try:
            await asyncio.sleep(self.delay)
            mensagens = self.buffers.pop(chat_id, [])
            update = self.latest_updates.pop(chat_id, None)
            if mensagens and update:
                texto_acumulado = "\n".join(mensagens).strip()
                await callback(update, context, texto_acumulado)
        except asyncio.CancelledError:
            pass

debouncer = MessageDebouncer(delay_seconds=settings.MESSAGE_DEBOUNCE_SECONDS)

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
            max_tokens=120,
            temperature=0.78
        )
        msg_espera_texto = completion.choices[0].message.content.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Aviso ao gerar intro dinâmica de avatar: {e}")
        msg_espera_texto = "Ai amor, com certeza! Vou escolher e tirar uma selfie bem linda agora pro perfil, espera só um segundinho... 🥰📸"

    fala_intro_limpa = limpar_fala_marina(msg_espera_texto)
    await send_human_messages(chat_id, bot, fala_intro_limpa)
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
                max_tokens=100,
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
        await bot.send_photo(
            chat_id=chat_id,
            photo=raw,
            caption=legenda_limpa
        )
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

    memory_manager.registrar_interacao("[Iniciou a conversa /start]", boas_vindas)
    await send_human_messages(chat_id, context.bot, boas_vindas)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    camera_online = await sd_client.is_online()
    ciclo_info = memory_manager.cycle_mgr.get_cycle_info()
    estilo = memory_manager.db.get_estilo()
    risada = estilo.get("risada", {}).get("valor", "kkkk")
    
    status_msg = (
        f"🌹 **Status de {settings.APP_NAME} (v{settings.APP_VERSION} Oficial - SQLite & Reações):**\n\n"
        f"• **Namorado Exclusivo**: Patrick Ramos (Chat ID: `{settings.TARGET_CHAT_ID}`) 💕\n"
        f"• **Fase Biológica**: Dia {ciclo_info['day']} de {ciclo_info.get('cycle_length', 28)} ({ciclo_info['name']}) 🌸\n"
        f"• **Cérebro (LLM)**: `{settings.LLM_MODEL}` (Temp: 0.72 - Anti-Glitch) ✅\n"
        f"• **Sincronia de Estilo**: Risada `{risada}` | Emojis & Gírias em espelhamento 💬\n"
        f"• **Buffer de Digitação**: {settings.MESSAGE_DEBOUNCE_SECONDS}s (captura mensagens consecutivas completas) ⏱️\n"
        f"• **Reações Mão Dupla**: Ativas (Telegram Bot API 7.0+) 💖\n"
        f"• **Câmera**: {'Novita AI Serverless (FLUX.1 Dev 4090)' if settings.IMAGE_ENGINE == 'novita' else 'SD Local'} "
        f"({'Online 📸' if camera_online else 'Verificando ⚠️'})\n"
        f"• **Banco de Dados**: `marin_memory.db` (SQLite Relacional Exclusivo) 🗄️\n"
        f"• **Memória Inteligente**: {'Ativa (FTS5 Seletivo & Consolidator)' if settings.SMART_MEMORY_ENABLED else 'Modo Legado'} 🧠\n"
        f"• **Auto-Patcher Remoto**: Ativo via `/edit` 🛠️\n"
        f"• **Chat 100% Limpo**: Comandos e recibos são auto-deletados 🧹\n\n"
        f"💬 **Histórico Permanente**: {memory_manager.db.get_total_conversas()} mensagens salvas\n"
        f"🧠 **Lembranças sobre você**: {len(memory_manager.db.get_fatos_patrick())} fatos guardados\n\n"
        "*(Esta mensagem sumirá em 15s para manter a conversa limpa!)*"
    )
    msg = await context.bot.send_message(chat_id=chat_id, text=status_msg, parse_mode="Markdown")
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=15.0))

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
        text=f"✨ **Anotado com muito carinho, amor!**\nSua observação foi guardada no banco de dados para eu sempre melhorar por você! 💕",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_after_delay(context.bot, chat_id, confirmacao.message_id, delay=5.0))

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /edit para Patrick solicitar melhorias e correções no código diretamente pelo Telegram.
    Executa em staging isolado (.runtime/patch_staging/), valida sintaxe e compilação via subprocesso
    e reinicia o bot de forma transacional e segura.
    """
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    if not getattr(settings, "SAFE_PATCHER_ENABLED", False):
        aviso = await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ **Auto-Patcher Seguro**: O recurso de auto-edição remota está desativado no momento (`SAFE_PATCHER_ENABLED=False` no `.env`).",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, aviso.message_id, delay=8.0))
        return

    args = context.args
    if not args:
        ajuda = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🛠️ **Auto-Patcher Seguro da Marina (v3.4.0)**\n\n"
                "Peça melhorias diretas no código com proteção de staging e rollback!\n\n"
                "📌 **Exemplos de uso:**\n"
                "`/edit adicione no prompts.py mais apelidos carinhosos`\n"
                "`/edit no visual_profile ajuste o ângulo de câmera`\n"
                "`/edit no style_engine inclua a gíria fechou`\n\n"
                "⏪ Para desfazer um patch: `/rollback`\n"
                "📜 Para ver o histórico: `/patches`"
            ),
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, ajuda.message_id, delay=12.0))
        return

    instrucao = " ".join(args)
    msg_espera = await context.bot.send_message(
        chat_id=chat_id,
        text="🔧 **Auto-Patcher Transacional (v3.4.0)**: Preparando staging isolado, gerando código e validando compilação... Aguarde amor! ⏳",
        parse_mode="Markdown"
    )

    sucesso, resultado, diff = await asyncio.to_thread(auto_patcher.apply_patch, instrucao, "Patrick Ramos")

    try:
        await msg_espera.delete()
    except Exception:
        pass

    if sucesso:
        diff_snippet = ""
        if diff and len(diff) <= 1200:
            diff_snippet = f"\n\n```diff\n{diff}\n```"
        msg_ok = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{resultado}{diff_snippet}\n\n🔄 **Reiniciando o bot da Marina em 3 segundos** para carregar as novas instruções...",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, msg_ok.message_id, delay=6.0))
        await asyncio.sleep(3.0)
        sys.exit(0)
    else:
        msg_fail = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{resultado}",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, msg_fail.message_id, delay=15.0))

async def rollback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /rollback para reverter com segurança o último patch aplicado."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    if not getattr(settings, "SAFE_PATCHER_ENABLED", False):
        aviso = await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ **Auto-Patcher Seguro**: O recurso de auto-edição remota está desativado no momento (`SAFE_PATCHER_ENABLED=False` no `.env`).",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, aviso.message_id, delay=8.0))
        return

    patch_id_arg = context.args[0] if context.args else None
    msg_espera = await context.bot.send_message(
        chat_id=chat_id,
        text="⏪ **Iniciando Rollback**: Restaurando arquivos originais a partir do backup seguro...",
        parse_mode="Markdown"
    )

    sucesso, resultado = await asyncio.to_thread(auto_patcher.rollback_patch, patch_id_arg)

    try:
        await msg_espera.delete()
    except Exception:
        pass

    if sucesso:
        msg_ok = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{resultado}\n\n🔄 **Reiniciando o bot em 3 segundos** para restabelecer a versão anterior...",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, msg_ok.message_id, delay=6.0))
        await asyncio.sleep(3.0)
        sys.exit(0)
    else:
        msg_fail = await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {resultado}",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, msg_fail.message_id, delay=12.0))

async def patches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /patches para listar os patches recentes e seu status de auditoria."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    if not getattr(settings, "SAFE_PATCHER_ENABLED", False):
        aviso = await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ **Auto-Patcher Seguro**: O recurso de auto-edição remota está desativado no momento (`SAFE_PATCHER_ENABLED=False` no `.env`).",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, aviso.message_id, delay=8.0))
        return

    from db import db_manager
    history = db_manager.get_patch_history(limit=5)
    if not history:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="📜 **Histórico de Patches**: Nenhum patch registrado até o momento.",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, msg.message_id, delay=10.0))
        return

    linhas = ["📜 **Histórico Recente de Patches (SQLite Audit):**\n"]
    for p in history:
        status_icon = "✅" if p["status"] == "applied" else ("⏪" if p["status"] == "rolled_back" else "⚠️")
        arquivos = ", ".join(p["target_files"]) if p["target_files"] else "N/A"
        inst_curta = p["instruction"][:60] + "..." if len(p["instruction"]) > 60 else p["instruction"]
        linhas.append(
            f"{status_icon} **`{p['patch_id']}`** ({p['status']})\n"
            f"   📁 Arquivos: `{arquivos}`\n"
            f"   📝 \"{inst_curta}\"\n"
            f"   🕒 {p['created_at']}\n"
        )

    linhas.append("*(Esta mensagem sumirá em 25s)*")
    msg_history = await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(linhas),
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_after_delay(context.bot, chat_id, msg_history.message_id, delay=25.0))


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
        "🌹 **Diário de Memórias de Marina Seltin (SQLite):**\n\n"
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

async def lembretes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /lembretes para exibir os lembretes ativos e confirmados da Marina."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
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

async def process_incoming_batch(update: Update, context: ContextTypes.DEFAULT_TYPE, texto_usuario: str):
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id

    # 1. Aprendizado dinâmico do estilo linguístico do Patrick (risadas, emojis, gírias, cadência)
    style_engine.processar_mensagem_patrick(texto_usuario)

    # 2. Planejamento Cognitivo Interno (tom, intenção, reação e detecção de compromissos futuros)
    recent_turns = memory_manager.get_historico_recente(limit=4)
    recent_ctx_repr = "\n".join([f"{m['role']}: {m['content']}" for m in recent_turns])

    plan = None
    if getattr(settings, "PLANNER_ENABLED", False):
        plan = await asyncio.to_thread(planner.plan_message, texto_usuario, recent_ctx_repr)
    else:
        plan = planner.plan_heuristics(texto_usuario) or {}

    # 2.1 Verificação de consentimento para oferta recente de lembrete (Smart Reminders Release 3.5.1)
    if getattr(settings, "SMART_REMINDERS_ENABLED", True):
        last_offered = reminder_service.get_last_offered_reminder(max_age_minutes=60)
        if last_offered:
            confirmation = reminder_service.parse_confirmation_response(texto_usuario)
            if confirmation["action"] == "confirm":
                reminder_service.confirm_reminder(last_offered["id"], custom_offset_minutes=confirmation.get("offset_minutes"))
                logger.info(f"Oferta de lembrete {last_offered['id']} confirmada pelo Patrick com offset {confirmation.get('offset_minutes')}m.")
            elif confirmation["action"] == "decline":
                reminder_service.decline_reminder(last_offered["id"])
                logger.info(f"Oferta de lembrete {last_offered['id']} recusada pelo Patrick.")

    # 3. Reação espontânea da Marina no balão de mensagem do Patrick (prioriza emoji do planner)
    planner_emoji = plan.get("reaction_emoji") if plan else None
    reacao_emoji = planner_emoji or choose_reaction_for_text(texto_usuario)
    if reacao_emoji and (planner_emoji or random.random() < 0.50):
        try:
            await context.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=msg_id,
                reaction=[ReactionTypeEmoji(emoji=reacao_emoji)]
            )
        except Exception as e:
            logger.warning(f"Erro ao setar reação na mensagem do Patrick: {e}")

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

            u_id, b_id = memory_manager.registrar_interacao(texto_usuario, resposta)
            if plan:
                planner.apply_plan_effects(plan, conversation_id=u_id)
            await send_human_messages(chat_id, context.bot, resposta, reply_to_message_id=msg_id)
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
        planner_goal=plan.get("response_goal") if plan else None
    )
    if pediu_foto:
        messages.append({
            "role": "system",
            "content": (
                "[INSTRUÇÃO CRÍTICA DESTE TURNO]: O Patrick acabou de pedir uma foto/selfie/look! "
                "Você AMA se mostrar pra ele e VAI ENVIAR A FOTO AGORA MESMO. "
                "NUNCA adie, NUNCA diga 'mais tarde te mando' ou 'tô na cama depois eu mostro'. "
                "Responda empolgada avisando que tirou ou que está mostrando pra ele agora mesmo!"
            )
        })
    messages.append({"role": "user", "content": texto_usuario})
    
    try:
        completion = llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            max_tokens=160,
            temperature=0.80,
            frequency_penalty=0.30,
            presence_penalty=0.25
        )
        resposta_marin = completion.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Aviso na chamada principal da LLM ({settings.LLM_MODEL}): {e}")
        fallback_model = "mistralai/mistral-nemo"
        if settings.LLM_MODEL != fallback_model:
            try:
                logger.info(f"Acionando modelo reserva ({fallback_model})...")
                completion = llm_client.chat.completions.create(
                    model=fallback_model,
                    messages=messages,
                    max_tokens=220,
                    temperature=0.72,
                    frequency_penalty=0.40,
                    presence_penalty=0.35
                )
                resposta_marin = completion.choices[0].message.content.strip()
            except Exception as e2:
                logger.error(f"Erro também no modelo reserva: {e2}")
                resposta_marin = "Amor, deu uma osciladinha aqui no sinal do apê! Me manda de novo? 🥺"
        else:
            resposta_marin = "Amor, deu uma osciladinha aqui no sinal do apê! Me manda de novo? 🥺"

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

    # Chance espontânea adicional: ~6% de mandar áudio por vontade própria em mensagens carinhosas (apenas se não for pedido de foto)
    if not pediu_foto and not pediu_audio and not queria_audio and random.random() < 0.06 and len(fala_limpa) > 30:
        queria_audio = True

    # Registra na memória a fala já limpa (sem tags/rubricas) e aplica efeitos do plano
    u_id, b_id = memory_manager.registrar_interacao(texto_usuario, fala_limpa if fala_limpa else resposta_marin)
    if plan:
        planner.apply_plan_effects(plan, conversation_id=u_id)

    audio_enviado = False
    aviso_audio_ja_enviado = False
    if pediu_audio or queria_audio:
        if not voice_engine.is_configured():
            if pediu_audio:
                aviso = "Amor, meu microfone tá meio zoado agora 🥺 Já já eu consigo te mandar um áudio bem gostoso, prometo!"
                await send_human_messages(chat_id, context.bot, aviso, reply_to_message_id=reply_to_id)
                aviso_audio_ja_enviado = True
        else:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            audio_path = await voice_engine.synthesize(fala_limpa)
            if audio_path and audio_path.exists():
                with open(audio_path, "rb") as vf:
                    sent_voice = await context.bot.send_voice(
                        chat_id=chat_id,
                        voice=vf,
                        reply_to_message_id=reply_to_id
                    )
                    ULTIMAS_MENSAGENS_MARINA[chat_id].append(
                        {"message_id": sent_voice.message_id, "text": f"[Áudio: {fala_limpa[:60]}...]"}
                    )
                audio_enviado = True
            elif pediu_audio:
                aviso_falha = "Amor, tentei gravar aqui mas o microfone do celular deu uma travadinha! Já já te mando um áudio bem gostoso 🥺💕"
                await send_human_messages(chat_id, context.bot, aviso_falha, reply_to_message_id=reply_to_id)
                aviso_audio_ja_enviado = True

    # Se não mandou áudio (nem aviso de falha), manda texto (balões)
    if not audio_enviado and not aviso_audio_ja_enviado and fala_limpa:
        await send_human_messages(chat_id, context.bot, fala_limpa, reply_to_message_id=reply_to_id)
    
    # Se pediu foto, renderiza a cena e envia foto com status realista apenas no momento do upload
    if pediu_foto:
        try:
            # Detecta se é NSFW considerando EXCLUSIVAMENTE o que o Patrick pediu
            is_nsfw = sd_client.is_nsfw_request(texto_usuario)
            
            prompt_cenario = "casual smartphone selfie in apartment, smiling warmly at camera"
            try:
                prompt_res = llm_client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a specialized visual prompt director for FLUX.1 Dev photography. "
                                "Marina Seltin is a 19yo Brazilian model with honey-amber eyes and wavy chocolate brown hair with blonde tips. "
                                "CRITICAL RULES FOR CLOTHING VS NUDITY: "
                                "1. If boyfriend requested a CLOTHED or CASUAL photo (e.g. 'vestida', 'roupa', 'look', 'vestido', 'pijama', 'selfie', 'casual') OR did NOT explicitly ask for nude/undies: "
                                "Describe her FULLY CLOTHED in a cute, stylish or casual outfit (e.g. 'fully clothed, wearing a cute fitted crop top and jeans', 'wearing a chic sundress', 'wearing comfortable oversized sleep hoodie and pajama shorts'). "
                                "NEVER make her naked or in lingerie if he asked for a clothed photo! "
                                "2. ONLY if boyfriend explicitly requested nudity or lingerie (e.g. 'pelada', 'nua', 'sem roupa', 'seios', 'calcinha', 'lingerie', 'quente'): "
                                "describe her outfit accordingly (e.g. 'wearing delicate black lace lingerie', 'completely naked on bed wrapped in bedsheet'). "
                                "Output ONLY concise, photographic English tags separated by commas. No preamble."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Boyfriend asked: '{texto_usuario}'. Marina's mood: '{fala_limpa}'. Generate accurate visual prompt tags."
                        }
                    ],
                    max_tokens=80,
                    temperature=0.6
                )
                prompt_cenario = prompt_res.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"Falha ao gerar prompt dinâmico de cena: {e}")

            # Se for NSFW e o usuário pediu nudez explícita
            if is_nsfw and any(w in texto_usuario.lower() for w in ["pelada", "nua", "sem roupa", "nude", "naked", "peito", "seios"]):
                if not any(kw in prompt_cenario.lower() for kw in ["naked", "nude", "legs open"]):
                    prompt_cenario += ", completely naked, uncensored, legs open"
            elif not is_nsfw:
                # Remove qualquer termo de nudez caso tenha vazado
                prompt_cenario = re.sub(r'\b(completely naked|nude|naked|uncensored|topless|legs open)\b', '', prompt_cenario, flags=re.IGNORECASE).strip(', ')
                if not any(kw in prompt_cenario.lower() for kw in ["clothed", "wearing", "dress", "top", "hoodie", "pajama", "shorts", "jeans"]):
                    prompt_cenario += ", fully clothed, wearing casual chic outfit"

            foto_stream = await sd_client.generate_photo(prompt_cenario, user_intent=texto_usuario)
            if foto_stream:
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
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=foto_stream,
                    caption=legenda_dinamica
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
        plan = None
        if getattr(settings, "PLANNER_ENABLED", False):
            plan = await asyncio.to_thread(planner.plan_message, user_message_repr, vision_context)
            reacao_emoji = plan.get("reaction_emoji")

        if reacao_emoji:
            try:
                await context.bot.set_message_reaction(
                    chat_id=chat_id,
                    message_id=msg_id,
                    reaction=[ReactionTypeEmoji(emoji=reacao_emoji)]
                )
            except Exception as e:
                logger.warning(f"Erro ao setar reação em foto: {e}")

        # Monta payload com visão e tom planejado
        messages = build_messages_payload(
            quoted_context="",
            web_search_context="",
            user_message=user_message_repr,
            vision_context=vision_context,
            planner_tone=plan.get("tone") if plan else None,
            planner_goal=plan.get("response_goal") if plan else None
        )

        # Gera resposta dinâmica da Marina
        completion = llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            max_tokens=220,
            temperature=0.72
        )
        resposta_raw = completion.choices[0].message.content.strip()
        resposta_limpa = limpar_fala_marina(resposta_raw)

        # Registra interação no banco com media_type='photo' e aplica efeitos do plano
        u_id = memory_manager.db.adicionar_mensagem(role="user", content=user_message_repr, media_type="photo")
        b_id = memory_manager.db.adicionar_mensagem(role="assistant", content=resposta_limpa, media_type="text")

        if plan:
            planner.apply_plan_effects(plan, conversation_id=u_id)

        # Atualiza métricas de estilo se houver legenda
        if caption:
            style_engine.processar_mensagem_patrick(caption)

        # Dispara consolidação de memória persistente
        await check_and_trigger_memory_consolidation()

        # Envia resposta humanizada em balões
        if resposta_limpa:
            await send_human_messages(chat_id, context.bot, resposta_limpa)

    except Exception as e:
        logger.error(f"Erro ao processar foto recebida do Patrick: {e}", exc_info=True)
        await send_human_messages(
            chat_id,
            context.bot,
            "Amor, tentei abrir a foto aqui no celular mas deu uma travadinha na internet 🥺 Manda de novo?"
        )

# --- VONTADE PRÓPRIA & INICIATIVA ÍNTIMA (DIRECIONADA APENAS AO PATRICK) ---

async def autonomous_routine(application: Application):
    if not settings.TARGET_CHAT_ID:
        return

    # Avaliação inteligente de gatilho (janela de sono, limite diário, cooldowns e eventos pendentes)
    should_run, trigger_reason = proactivity_service.should_trigger()
    if not should_run:
        logger.debug(f"Rotina autônoma de Marina: gatilho não disparado ({trigger_reason}).")
        return

    logger.info(f"Marina Seltin decidiu puxar assunto por iniciativa própria! Motivo: {trigger_reason}")
    
    # 6% de chance de ela ficar com vontade de trocar a foto de perfil e pedir ajuda ao Patrick!
    if random.random() < 0.06:
        logger.info("Marina Seltin decidiu pedir ajuda para escolher um novo avatar!")
        await iniciar_escolha_avatar(application.bot, settings.TARGET_CHAT_ID)
        proactivity_service.record_autonomous_sent(reason="avatar_pick")
        return

    try:
        proactive_info = proactivity_service.determine_proactive_prompt()
        decision_prompt = build_autonomous_decision_prompt(custom_situation=proactive_info.get("instruction", ""))
        
        if settings.SMART_MEMORY_ENABLED:
            system_prompt = context_builder.build_system_prompt()
        else:
            system_prompt = f"{MARIN_SYSTEM_PROMPT}\n{memory_manager.get_contexto_emocional()}"

        resposta = llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": decision_prompt}
            ],
            max_tokens=220,
            temperature=0.72
        ).choices[0].message.content.strip()

        partes = re.split(r'\|\s*FOTO_PROMPT\s*:', resposta, maxsplit=1, flags=re.IGNORECASE)
        acao_texto = partes[0].replace("ACAO:", "").strip()
        prompt_foto = partes[1].strip() if len(partes) > 1 else ""

        # Verifica se Marina decidiu mandar por áudio por vontade própria
        deve_mandar_audio = bool(re.search(r'\[MANDAR_AUDIO\]|\[AUDIO\]', acao_texto, flags=re.IGNORECASE))
        # Chance espontânea: ~18% das iniciativas autônomas sem foto viram áudio carinhoso
        if not deve_mandar_audio and random.random() < 0.18 and not prompt_foto:
            deve_mandar_audio = True

        texto_limpo = limpar_fala_marina(acao_texto)

        if deve_mandar_audio and voice_engine.is_configured():
            logger.info("Marina decidiu gravar uma mensagem de voz autônoma por vontade própria!")
            await application.bot.send_chat_action(chat_id=settings.TARGET_CHAT_ID, action=ChatAction.RECORD_VOICE)
            audio_path = await voice_engine.synthesize(texto_limpo)
            if audio_path and audio_path.exists():
                with open(audio_path, "rb") as vf:
                    await application.bot.send_voice(chat_id=settings.TARGET_CHAT_ID, voice=vf)
                memory_manager.db.registrar_iniciativa_marina(texto_limpo, media_type="voice")
            else:
                memory_manager.db.registrar_iniciativa_marina(texto_limpo, media_type="text")
                if texto_limpo:
                    await send_human_messages(settings.TARGET_CHAT_ID, application.bot, texto_limpo)
        elif texto_limpo:
            memory_manager.db.registrar_iniciativa_marina(texto_limpo, media_type="text")
            await send_human_messages(settings.TARGET_CHAT_ID, application.bot, texto_limpo)

        proactivity_service.record_autonomous_sent(reason=proactive_info.get("reason", "autonomous"))

        # Conclui evento pendente apenas após confirmação de entrega da mensagem no Telegram
        event_id = proactive_info.get("event_id")
        if event_id:
            try:
                proactivity_service.db.concluir_evento_pendente(event_id)
                logger.info(f"Evento pendente {event_id} concluído com sucesso após entrega no Telegram.")
            except Exception as e_ev:
                logger.warning(f"Erro ao concluir evento pendente {event_id}: {e_ev}")

        if prompt_foto:
            await asyncio.sleep(1.5)
            foto_stream = await sd_client.generate_photo(prompt_foto)
            if foto_stream:
                prompt_legenda_auto = (
                    f"Você acabou de mandar uma foto espontânea sua para o Patrick ('{prompt_foto}'). "
                    "Escreva UMA frase curta e espontânea de legenda para acompanhar a foto. "
                    "Apenas a fala curta. Sem Ps: nem parênteses de bastidor."
                )
                legenda_auto = generate_dynamic_speech(prompt_legenda_auto, max_tokens=50) or "Tirei essa agora pensando em você... 💕"
                await application.bot.send_photo(
                    chat_id=settings.TARGET_CHAT_ID,
                    photo=foto_stream,
                    caption=legenda_auto
                )
            else:
                await send_human_messages(
                    settings.TARGET_CHAT_ID,
                    application.bot,
                    "Amor, tentei te mandar uma fotinho agora mas a câmera travou 🥺 Depois eu mando outra!"
                )
    except Exception as e:
        logger.error(f"Erro na rotina autônoma de Marina: {e}", exc_info=True)

async def reminders_routine(application: Application):
    """Job de alta frequência para disparo de reminders confirmados no horário exato (Release 3.5.1)."""
    if not getattr(settings, "SMART_REMINDERS_ENABLED", True):
        return
    try:
        now = datetime.now()
        if getattr(settings, "REMINDERS_RESPECT_SLEEP_WINDOW", False) and proactivity_service.check_sleep_window(now):
            return

        due = reminder_service.get_due_reminders(now)
        for rem in due:
            rid = rem["id"]
            msg_lembrete = reminder_service.format_reminder_message(rem)
            logger.info(f"Disparando reminder {rid} para o Patrick: '{rem['description']}'")
            await send_human_messages(settings.TARGET_CHAT_ID, application.bot, msg_lembrete)
            reminder_service.mark_sent(rid)
    except Exception as e:
        logger.error(f"Erro no job de reminders_routine: {e}", exc_info=True)

# --- INICIALIZAÇÃO ---

async def post_init(application: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        autonomous_routine,
        "interval",
        minutes=settings.AUTONOMOUS_CHECK_INTERVAL_MINUTES,
        args=[application]
    )

    # Job dedicado de alta frequência para Smart Reminders (Release 3.5.1)
    if getattr(settings, "SMART_REMINDERS_ENABLED", True):
        rem_interval = max(5, getattr(settings, "REMINDER_CHECK_INTERVAL_SECONDS", 30))
        scheduler.add_job(
            reminders_routine,
            "interval",
            seconds=rem_interval,
            args=[application]
        )
        logger.info(f"Job de Smart Reminders agendado a cada {rem_interval}s.")

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
    app.add_handler(CommandHandler("edit", edit_command))
    app.add_handler(CommandHandler("rollback", rollback_command))
    app.add_handler(CommandHandler("patches", patches_command))
    app.add_handler(CommandHandler("memorias", memorias_command))
    app.add_handler(CommandHandler("memoria", memorias_command))
    app.add_handler(CommandHandler("memorydebug", memorias_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("reset", restart_command))
    app.add_handler(CommandHandler("limpar", limpar_command))
    app.add_handler(CommandHandler("clear", limpar_command))
    app.add_handler(CommandHandler("audio", audio_command))
    app.add_handler(CommandHandler("voz", audio_command))
    app.add_handler(CommandHandler("lembretes", lembretes_command))
    app.add_handler(CommandHandler("cancelarlembrete", cancelar_lembrete_command))
    app.add_handler(CommandHandler("cancelar_lembrete", cancelar_lembrete_command))

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
    main()
