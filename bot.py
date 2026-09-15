"""
Bot Telegram de Marina Seltin (v1.4.0 Oficial Blindada).
Jovem de 19 anos, modelo em início de carreira, namorada EXCLUSIVA de Patrick Ramos.
Totalmente desinibida, carinhosa, com ciclo menstrual real, pausas humanas de digitação,
envio REAL de balões separados sucessivos (multi-bubble), comandos /feedback e /edit com Auto-Patcher autônomo,
espelhamento dinâmico de estilo linguístico (style_engine), CHAT 100% LIMPO (auto-limpeza imediata de comandos),
BUFFER INTELIGENTE DE DIGITAÇÃO (Debounce anti-atropelo) e REAÇÕES DE MENSAGEM EM VIA DE MÃO DUPLA.
"""
import logging
import random
import asyncio
import re
import sys
from datetime import datetime

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
    if not settings.TARGET_CHAT_ID:
        return True
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

def build_messages_payload(quoted_context: str = "", web_search_context: str = "") -> list[dict]:
    contexto_momento = f"\n[MOMENTO ATUAL DO DIA: {get_temporal_greeting()}]"
    contexto_quote = f"\n{quoted_context}" if quoted_context else ""
    contexto_web = f"\n{web_search_context}" if web_search_context else ""
    system_content = f"{MARIN_SYSTEM_PROMPT}\n{memory_manager.get_contexto_emocional()}{contexto_momento}{contexto_quote}{contexto_web}"
    messages = [{"role": "system", "content": system_content}]
    
    for item in memory_manager.data.get("historico_recente", []):
        messages.append({"role": item["role"], "content": item["content"]})
        
    return messages

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
    if settings.TARGET_CHAT_ID and (chat_id != settings.TARGET_CHAT_ID and user_id != settings.TARGET_CHAT_ID):
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

debouncer = MessageDebouncer(delay_seconds=3.8)

# --- ROTINA DE ESCOLHA DE AVATAR ---

async def iniciar_escolha_avatar(bot, chat_id: int):
    prompt_intro = (
        "O Patrick pediu para você trocar a sua foto de perfil (ou você decidiu atualizar). "
        "Mande uma mensagem curtinha, fofa e espontânea de namorada dizendo que vai tirar uma foto linda e elegante agora pro perfil e já coloca!"
    )
    msg_espera_texto = generate_dynamic_speech(prompt_intro, max_tokens=100) or "Ai amor, ótima ideia! Vou tirar uma selfie bem linda agora pro perfil, espera só um segundinho... 🥰📸"

    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    msg_espera = await bot.send_message(chat_id=chat_id, text=msg_espera_texto)

    # Gera 1 avatar único com visual casual elegante (100% SFW e vestida)
    style = random.choice(["fofa", "estilosa"])
    jpg, raw = await sd_client.generate_avatar(look_style=style)

    try:
        await msg_espera.delete()
    except Exception:
        pass

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

        prompt_legenda = (
            "Você acabou de atualizar a sua foto de perfil do Telegram e mandou a foto completa pro Patrick. "
            "Escreva UMA frase curta e fofa mostrando a foto nova, perguntando se ele achou linda e dizendo que se ele quiser que mude de novo é só pedir."
        )
        legenda = generate_dynamic_speech(prompt_legenda, max_tokens=90) or "Prontinho amor! Acabei de atualizar meu perfil com essa aqui! Ficou linda? Se quiser outra depois é só me pedir 💕✨"

        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
        except Exception:
            pass
        await bot.send_photo(
            chat_id=chat_id,
            photo=raw,
            caption=legenda
        )
    else:
        prompt_falha = "Sua câmera travou na hora de tirar a foto pro perfil. Diga algo fofo e dengoso pedindo pro Patrick tentar de novo daqui a pouco."
        msg_falha = generate_dynamic_speech(prompt_falha, max_tokens=70) or "Amor, minha câmera deu uma travadinha aqui no apê! Me pede de novo daqui a pouco que eu troco de verdade? 🥺"
        await bot.send_message(chat_id=chat_id, text=msg_falha)

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
        "🌹 **Status de Marina Seltin (v1.4.0 Oficial - SQLite & Reações):**\n\n"
        f"• **Namorado Exclusivo**: Patrick Ramos (Chat ID: `{settings.TARGET_CHAT_ID}`) 💕\n"
        f"• **Fase Biológica**: Dia {ciclo_info['day']} de 28 ({ciclo_info['name']}) 🌸\n"
        f"• **Cérebro (LLM)**: `{settings.LLM_MODEL}` (Temp: 0.72 - Anti-Glitch) ✅\n"
        f"• **Sincronia de Estilo**: Risada `{risada}` | Emojis & Gírias em espelhamento 💬\n"
        f"• **Buffer de Digitação**: 2.8s (captura mensagens consecutivas completas) ⏱️\n"
        f"• **Reações Mão Dupla**: Ativas (Telegram Bot API 7.0+) 💖\n"
        f"• **Câmera**: {'Novita AI Serverless (FLUX.1 Dev 4090)' if settings.IMAGE_ENGINE == 'novita' else 'SD Local'} "
        f"({'Online 📸' if camera_online else 'Verificando ⚠️'})\n"
        f"• **Banco de Dados**: `marin_memory.db` (SQLite Relacional Exclusivo) 🗄️\n"
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
    Comando /edit para Patrick solicitar melhorias e correções autônomas no código diretamente pelo Telegram.
    Usa a LLM para gerar a alteração, valida via py_compile e reinicia o bot com segurança.
    """
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
            text=(
                "🛠️ **Auto-Patcher da Marina (v1.4.0)**\n\n"
                "Peça melhorias diretas no código sem precisar ligar o PC!\n"
                "📌 **Exemplo:**\n"
                "`/edit adicione uma regra no prompt para você me chamar de meu bem com mais frequência`\n"
                "`/edit no style_engine inclua a gíria fechou no rastreador`"
            ),
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, ajuda.message_id, delay=8.0))
        return

    instrucao = " ".join(args)
    msg_espera = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔧 **Auto-Patcher em Ação**: Analisando sua solicitação e aplicando melhoria via Gemini Pro... Aguarde amor! ⏳",
        parse_mode="Markdown"
    )

    sucesso, resultado = await asyncio.to_thread(auto_patcher.apply_patch, instrucao, "Patrick Ramos")

    try:
        await msg_espera.delete()
    except Exception:
        pass

    if sucesso:
        msg_ok = await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ {resultado}\n\n🔄 **Reiniciando o bot da Marina em 3 segundos** para carregar as novas instruções...",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, msg_ok.message_id, delay=4.0))
        await asyncio.sleep(3.0)
        sys.exit(0)
    else:
        msg_fail = await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ **Não foi possível aplicar com segurança:**\n{resultado}",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after_delay(context.bot, chat_id, msg_fail.message_id, delay=12.0))

async def memorias_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe o que a Marina guarda na memória sobre o Patrick direto pelo Telegram (auto-limpeza em 15s)."""
    if not is_authorized(update):
        return

    chat_id = update.effective_chat.id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

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

    # 2. Reação espontânea da Marina no balão de mensagem do Patrick (Via 1)
    reacao_emoji = choose_reaction_for_text(texto_usuario)
    if reacao_emoji and random.random() < 0.50:
        try:
            await context.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=msg_id,
                reaction=[ReactionTypeEmoji(emoji=reacao_emoji)]
            )
        except Exception as e:
            logger.warning(f"Erro ao setar reação na mensagem do Patrick: {e}")

    texto_lower = texto_usuario.lower()
    
    # 3. Verifica se o Patrick está escolhendo entre as opções de avatar pendentes
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
            
            memory_manager.registrar_interacao(texto_usuario, resposta)
            await send_human_messages(chat_id, context.bot, resposta, reply_to_message_id=msg_id)
            return

    # 4. Verifica se pediu para trocar foto de perfil (ANTES de foto de chat)
    if is_avatar_request(texto_usuario):
        await iniciar_escolha_avatar(context.bot, chat_id)
        return

    # 5. Verifica se o Patrick usou o recurso 'Responder' citando uma mensagem anterior
    quoted_context = ""
    if update.message.reply_to_message and update.message.reply_to_message.text:
        quoted_text = update.message.reply_to_message.text[:120]
        quoted_context = f"[O Patrick está respondendo especificamente a esta fala sua anterior: '{quoted_text}']"

    # 6. Decisão natural de usar ou não o recurso 'Responder' (Quote)
    deve_citar = False
    if update.message.reply_to_message:
        deve_citar = random.random() < 0.75
    elif "?" in texto_usuario:
        deve_citar = random.random() < 0.50
    else:
        deve_citar = random.random() < 0.25

    reply_to_id = msg_id if deve_citar else None

    # 7. Verifica se pediu foto ou áudio normal
    pediu_foto = is_photo_request(texto_usuario)
    pediu_audio = is_audio_request(texto_usuario)
    
    # Executa busca na web em tempo real caso a mensagem do Patrick envolva fatos, lançamentos ou perguntas
    web_info = await asyncio.to_thread(buscar_web_se_necessario, texto_usuario)

    # Prepara o payload para a LLM com memórias + contexto de busca
    messages = build_messages_payload(quoted_context=quoted_context, web_search_context=web_info)
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

    # Chance espontânea adicional: ~6% de mandar áudio por vontade própria em mensagens carinhosas
    if not pediu_audio and not queria_audio and random.random() < 0.06 and len(fala_limpa) > 30:
        queria_audio = True

    # Registra na memória a fala já limpa (sem tags/rubricas)
    memory_manager.registrar_interacao(texto_usuario, fala_limpa if fala_limpa else resposta_marin)

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

            foto_stream = await sd_client.generate_photo(prompt_cenario)
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

# --- VONTADE PRÓPRIA & INICIATIVA ÍNTIMA (DIRECIONADA APENAS AO PATRICK) ---

async def autonomous_routine(application: Application):
    if not settings.TARGET_CHAT_ID:
        return

    # Madrugada alta (entre 3h30 e 8h00): dormindo no apê
    hora_atual = datetime.now().hour
    if 3 < hora_atual < 8:
        logger.info("Marina Seltin está dormindo no apê (rotina de sono noturna).")
        return

    # Sorteio de iniciativa
    if random.random() > settings.AUTONOMOUS_TRIGGER_CHANCE:
        return

    logger.info("Marina Seltin decidiu puxar assunto por vontade própria!")
    
    # 6% de chance de ela ficar com vontade de trocar a foto de perfil e pedir ajuda ao Patrick!
    if random.random() < 0.06:
        logger.info("Marina Seltin decidiu pedir ajuda para escolher um novo avatar!")
        await iniciar_escolha_avatar(application.bot, settings.TARGET_CHAT_ID)
        return

    try:
        decision_prompt = build_autonomous_decision_prompt()
        resposta = llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": f"{MARIN_SYSTEM_PROMPT}\n{memory_manager.get_contexto_emocional()}"},
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
                memory_manager.registrar_interacao("[Iniciativa da Marina em Áudio]", texto_limpo)
            else:
                memory_manager.registrar_interacao("[Iniciativa da Marina]", texto_limpo)
                if texto_limpo:
                    await send_human_messages(settings.TARGET_CHAT_ID, application.bot, texto_limpo)
        elif texto_limpo:
            memory_manager.registrar_interacao("[Iniciativa da Marina]", texto_limpo)
            await send_human_messages(settings.TARGET_CHAT_ID, application.bot, texto_limpo)

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

# --- INICIALIZAÇÃO ---

async def post_init(application: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        autonomous_routine,
        "interval",
        minutes=settings.AUTONOMOUS_CHECK_INTERVAL_MINUTES,
        args=[application]
    )
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
    app.add_handler(CommandHandler("memorias", memorias_command))
    app.add_handler(CommandHandler("memoria", memorias_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("reset", restart_command))
    app.add_handler(CommandHandler("limpar", limpar_command))
    app.add_handler(CommandHandler("clear", limpar_command))
    app.add_handler(CommandHandler("audio", audio_command))
    app.add_handler(CommandHandler("voz", audio_command))

    # Reações em tempo real (Via 2 - Patrick reagindo com emojis)
    app.add_handler(MessageReactionHandler(handle_reaction))

    # Conversa textual com Debouncer
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot de Marina Seltin (v1.4.0 Oficial Blindada) iniciado com sucesso!")
    # allowed_updates=Update.ALL_TYPES garante recebimento de MESSAGE_REACTION
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
