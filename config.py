"""
Módulo de configurações e variáveis de ambiente do Bot de Marina Salles (v3.7.0).
Compatível com OpenAI, OpenRouter e outros provedores sem censura.
"""
import os
import math
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

class Settings:
    APP_NAME: str = "Marina Salles"
    APP_VERSION: str = "3.7.0"
    VERSION: str = APP_VERSION
    VERSION_NAME: str = f"{APP_NAME} (v{APP_VERSION} Oficial - Living Intelligence)"

    # Deprecated compatibility markers for historical tests and tooling only.
    # Production code never reads these names; changing them cannot select an
    # older runtime path. Remove after the legacy test fixtures are retired.
    SMART_MEMORY_ENABLED = True
    MEMORY_INTELLIGENCE_ENABLED = True
    PLANNER_ENABLED = True
    EMOTIONAL_STATE_ENABLED = True
    PENDING_EVENTS_ENABLED = True
    OPEN_LOOPS_ENABLED = True
    SMART_REMINDERS_ENABLED = True
    LIVING_WORLD_ENABLED = True
    RESPONSE_RHYTHM_ENABLED = True
    KNOWLEDGE_PRIVACY_ENABLED = True
    RELATIONSHIP_WORLD_ENABLED = True
    CAMERA_WORLD_CONTINUITY_ENABLED = True
    RESPONSE_AVAILABILITY_ENABLED = True
    HUMAN_REPLY_LATENCY_ENABLED = True
    PENDING_CONVERSATION_BATCHING_ENABLED = True
    RESPONSE_VERBOSITY_RETRY_ENABLED = True
    ACADEMIC_LIFE_ENABLED = True
    ACADEMIC_AUTO_TERM_GENERATION = True
    CALENDAR_CONTINUITY_ENABLED = True
    STYLE_ENGINE_V2_ENABLED = True
    VOICE_LIBRARY_ENABLED = True
    VOICE_LIBRARY_MAX_EXAMPLES = int(os.getenv("VOICE_LIBRARY_MAX_EXAMPLES", "6"))

    # v3.7.1 — Verbal replies when Patrick reacts to Marina's messages. Humans
    # usually absorb a reaction silently; keep chances low, add a cooldown so a
    # burst of reactions never produces a burst of "ai amor..." messages.
    REACT_TO_HEART_REACTION_CHANCE: float = float(os.getenv("REACT_TO_HEART_REACTION_CHANCE", "0.10"))
    REACT_TO_FIRE_REACTION_CHANCE: float = float(os.getenv("REACT_TO_FIRE_REACTION_CHANCE", "0.15"))
    REACT_TO_LAUGH_REACTION_CHANCE: float = float(os.getenv("REACT_TO_LAUGH_REACTION_CHANCE", "0.05"))
    REACTION_VERBAL_REPLY_COOLDOWN_MINUTES: int = int(os.getenv("REACTION_VERBAL_REPLY_COOLDOWN_MINUTES", "15"))

    # v3.7.1 Fase B.5 — Proatividade sensível ao WorldState.
    # Multiplicadores aplicados sobre AUTONOMOUS_TRIGGER_CHANCE conforme o
    # activity atual da Marina. Redistribui as ocasiões sem aumentar volume
    # nem tocar em cooldown/teto diário.
    PROACTIVITY_STATE_FACTOR_FREE_TIME: float = float(os.getenv("PROACTIVITY_STATE_FACTOR_FREE_TIME", "1.6"))
    PROACTIVITY_STATE_FACTOR_POST_EVENT: float = float(os.getenv("PROACTIVITY_STATE_FACTOR_POST_EVENT", "1.3"))
    PROACTIVITY_STATE_FACTOR_BUSY: float = float(os.getenv("PROACTIVITY_STATE_FACTOR_BUSY", "0.4"))
    PROACTIVITY_STATE_FACTOR_UNKNOWN: float = float(os.getenv("PROACTIVITY_STATE_FACTOR_UNKNOWN", "1.0"))

    # v3.7.1 Patch 023 — Retriever antecipado de filmes/séries para Marina
    # citar título real em vez de "Filme de Romance" placeholder. Cache diário.
    MEDIA_LOOKUP_ENABLED: bool = os.getenv("MEDIA_LOOKUP_ENABLED", "true").lower() in ("true", "1", "yes")
    MEDIA_LOOKUP_REFRESH_HOURS: int = int(os.getenv("MEDIA_LOOKUP_REFRESH_HOURS", "24"))


    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    
    # Configurações do Provedor de LLM (OpenRouter / OpenAI / Outros)
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").strip()
    LLM_MODEL: str = os.getenv("LLM_MODEL", "mistralai/mistral-nemo").strip()
    # Auditoria #9 — ver llm_options.py. off | minimal | low | medium
    LLM_REASONING: str = os.getenv("LLM_REASONING", "off").strip().lower()
    # Reserva quando o modelo principal falha (antes fixo no código como mistral-nemo).
    LLM_FALLBACK_MODEL: str = os.getenv("LLM_FALLBACK_MODEL", "mistralai/mistral-nemo").strip()
    # Fase C.1 — modelo do modo íntimo (vazio = sem troca). Ver intimacy.py.
    LLM_INTIMATE_MODEL: str = os.getenv("LLM_INTIMATE_MODEL", "").strip()
    LLM_INTIMATE_REASONING: str = os.getenv("LLM_INTIMATE_REASONING", "off").strip().lower()
    INTIMACY_ENABLED: bool = os.getenv("INTIMACY_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    # Fase C.3 — rituais (bom dia, boa noite, cotidiano). Ver rituals.py.
    RITUALS_ENABLED: bool = os.getenv("RITUALS_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    # Fases D2/D3/D13 — sono variável, micro-despertares e manhã de trás pra frente (sleep_plan.py).
    # false = volta às janelas fixas do cânone (00:00–06:59 / 00:00–08:29).
    SLEEP_PLAN_ENABLED: bool = os.getenv("SLEEP_PLAN_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    # Fase D6 parte 2 — TMDB (títulos reais, episódios, recomendações, onde assistir no Brasil).
    # Uso não comercial com crédito ao TMDB. Sem chave, vale a lista fixa do watch.py.
    TMDB_API_KEY: str = os.getenv("TMDB_API_KEY", "").strip()
    TMDB_API_TOKEN: str = os.getenv("TMDB_API_TOKEN", "").strip()
    TMDB_ENABLED: bool = os.getenv("TMDB_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    # Fase C.4 — tempo real dos trajetos (distancematrix.ai). Sem chave, vale a tabela do commute.py.
    DISTANCE_MATRIX_KEY: str = os.getenv("DISTANCE_MATRIX_KEY", "").strip()
    COMMUTE_LIVE_TIMES: bool = os.getenv("COMMUTE_LIVE_TIMES", "true").strip().lower() in ("1", "true", "yes", "on")

    # URL da API do Stable Diffusion na RX 570 (legado/local)
    _raw_sd_url = os.getenv("SD_API_URL", "http://127.0.0.1:7860/").strip()
    SD_API_URL: str = _raw_sd_url if _raw_sd_url.endswith("/") else f"{_raw_sd_url}/"
    
    # Chat ID alvo do namorado (exclusividade total)
    TARGET_CHAT_ID: int = int(os.getenv("TARGET_CHAT_ID", "0"))

    # Buffer Inteligente de Digitação (Debounce)
    MESSAGE_DEBOUNCE_SECONDS: float = float(os.getenv("MESSAGE_DEBOUNCE_SECONDS", "3.8"))
    # Patch 030 — remove pergunta de entrevista no fecho de turno casual
    # ("E você, tem alguma coisa planejada?"). Kill switch caso o corte fique
    # agressivo em algum modo.
    VOICE_STRIP_INTERVIEW_CLOSER: bool = os.getenv(
        "VOICE_STRIP_INTERVIEW_CLOSER", "true").lower() == "true"
    # Patch 031 — remove muleta "Ah," de abertura, polidez de atendimento
    # ("obrigada por perguntar", "se precisar é só chamar") e assinatura de
    # despedida ("Beijos 😘").
    VOICE_STRIP_ASSISTANT_POLITENESS: bool = os.getenv(
        "VOICE_STRIP_ASSISTANT_POLITENESS", "true").lower() == "true"
    # Patch 033 — bloco [COMO NÃO SOAR] com exemplos negativos capturados pelo
    # Patrick via /ruim. Fecha a Fase B1 do PLANO_VOZ_MARINA_V371.
    VOICE_AVOID_BLOCK_ENABLED: bool = os.getenv(
        "VOICE_AVOID_BLOCK_ENABLED", "true").lower() == "true"
    # Teto de emoji por fala (feedback do Patrick, 22/09: nem toda mensagem
    # precisa terminar com emoji). Kill switch se a poda ficar seca demais.
    VOICE_EMOJI_BUDGET: bool = os.getenv(
        "VOICE_EMOJI_BUDGET", "true").lower() == "true"
    VOICE_AVOID_MAX_EXAMPLES: int = int(os.getenv("VOICE_AVOID_MAX_EXAMPLES", "4"))
    
    # Consolidação Periódica de Memória
    MEMORY_CONSOLIDATION_BATCH_SIZE: int = int(os.getenv("MEMORY_CONSOLIDATION_BATCH_SIZE", "8"))

    # Motor de Geração de Imagem (novita ou local)
    IMAGE_ENGINE: str = os.getenv("IMAGE_ENGINE", "novita").strip().lower()
    # Temporary provider outage accepted for the 3.7.0 soak; not a feature rollback.
    # 23/09: /feedback é caderno de correções, não vai pro prompt (ver world_context).
    PATRICK_FEEDBACK_IN_PROMPT: bool = os.getenv("PATRICK_FEEDBACK_IN_PROMPT", "false").lower() in ("true", "1", "yes")
    PHOTO_PROVIDER_MAINTENANCE: bool = os.getenv("PHOTO_PROVIDER_MAINTENANCE", "false").lower() in ("true", "1", "yes")
    NOVITA_API_KEY: str = os.getenv("NOVITA_API_KEY", "").strip()
    # 24/09: fotos pelo Civitai (Orchestration API) — IMAGE_ENGINE=civitai.
    CIVITAI_API_KEY: str = os.getenv("CIVITAI_API_KEY", "").strip().strip('"')
    CIVITAI_BASE_MODEL: str = os.getenv("CIVITAI_BASE_MODEL", "").strip()   # vazio = Flux.1 Dev
    CIVITAI_ECOSYSTEM: str = os.getenv("CIVITAI_ECOSYSTEM", "flux1").strip().lower()   # flux1 | krea2
    CIVITAI_LORA_MARINA_KREA2: str = os.getenv("CIVITAI_LORA_MARINA_KREA2", "").strip()   # AIR do LoRA Krea 2 dela
    CIVITAI_BREAST_SLIDER: float = float(os.getenv("CIVITAI_BREAST_SLIDER", "1.0") or 0)   # padrão da Marina (a calibrar)

    # Ciclo de vontade própria e iniciativa autônoma
    AUTONOMOUS_CHECK_INTERVAL_MINUTES: int = int(os.getenv("AUTONOMOUS_CHECK_INTERVAL_MINUTES", "30"))
    AUTONOMOUS_TRIGGER_CHANCE: float = float(os.getenv("AUTONOMOUS_TRIGGER_CHANCE", "0.30"))
    MAX_AUTONOMOUS_MESSAGES_PER_DAY: int = int(os.getenv("MAX_AUTONOMOUS_MESSAGES_PER_DAY", "4"))
    AUTONOMOUS_COOLDOWN_MINUTES: int = int(os.getenv("AUTONOMOUS_COOLDOWN_MINUTES", "120"))
    USER_IDLE_MINUTES_BEFORE_PROACTIVE: int = int(os.getenv("USER_IDLE_MINUTES_BEFORE_PROACTIVE", "45"))
    PROACTIVITY_ENABLED: bool = os.getenv("PROACTIVITY_ENABLED", "true").lower() in ("true", "1", "yes")

    # Síntese de Voz (ElevenLabs, Google Gemini TTS e Novita Voice)
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "").strip()
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_VOICE_NAME: str = os.getenv("GEMINI_VOICE_NAME", "Leda").strip()
    NOVITA_VOICE_ID: str = os.getenv("NOVITA_VOICE_ID", "voice_d91c415d-f6a2-4d6f-b32c-aacfd5ad2e39").strip()
    NOVITA_VOICE_MODEL: str = os.getenv("NOVITA_VOICE_MODEL", "speech-2.8-hd").strip()

    # Adaptive Dual Voice (Release 3.5.2)
    DUAL_VOICE_ENABLED: bool = os.getenv("DUAL_VOICE_ENABLED", "true").lower() in ("true", "1", "yes")
    NOVITA_VOICE_ID_CONVERSATIONAL: str = os.getenv("NOVITA_VOICE_ID_CONVERSATIONAL", "voice_d91c415d-f6a2-4d6f-b32c-aacfd5ad2e39").strip()
    NOVITA_VOICE_ID_INTIMATE: str = os.getenv("NOVITA_VOICE_ID_INTIMATE", "voice_73e73b73-65be-4cf9-9ab6-35d84f1946a3").strip()
    VOICE_ALLOW_CROSS_PROFILE_FALLBACK: bool = os.getenv("VOICE_ALLOW_CROSS_PROFILE_FALLBACK", "false").lower() in ("true", "1", "yes")
    NOVITA_CONVERSATIONAL_SPEED: float = float(os.getenv("NOVITA_CONVERSATIONAL_SPEED", "1.00"))
    NOVITA_CONVERSATIONAL_PITCH: int = int(os.getenv("NOVITA_CONVERSATIONAL_PITCH", "0"))
    NOVITA_INTIMATE_SPEED: float = float(os.getenv("NOVITA_INTIMATE_SPEED", "0.96"))
    NOVITA_INTIMATE_PITCH: int = int(os.getenv("NOVITA_INTIMATE_PITCH", "0"))

    MEMORY_CONSOLIDATION_ENABLED: bool = os.getenv("MEMORY_CONSOLIDATION_ENABLED", "true").lower() in ("true", "1", "yes")
    MEMORY_MAX_FACTS: int = int(os.getenv("MEMORY_MAX_FACTS", "5"))
    MEMORY_MAX_MOMENTS: int = int(os.getenv("MEMORY_MAX_MOMENTS", "3"))
    MEMORY_MAX_SUMMARIES: int = int(os.getenv("MEMORY_MAX_SUMMARIES", "2"))
    MEMORY_CANDIDATE_POOL_SIZE: int = int(os.getenv("MEMORY_CANDIDATE_POOL_SIZE", "20"))
    
    # Pesos do Ranking Híbrido da Memory Intelligence (3.5.0)
    MEMORY_WEIGHT_LEXICAL: float = float(os.getenv("MEMORY_WEIGHT_LEXICAL", "0.40"))
    MEMORY_WEIGHT_IMPORTANCE: float = float(os.getenv("MEMORY_WEIGHT_IMPORTANCE", "0.20"))
    MEMORY_WEIGHT_CONFIDENCE: float = float(os.getenv("MEMORY_WEIGHT_CONFIDENCE", "0.15"))
    MEMORY_WEIGHT_FRESHNESS: float = float(os.getenv("MEMORY_WEIGHT_FRESHNESS", "0.10"))
    MEMORY_WEIGHT_CORE: float = float(os.getenv("MEMORY_WEIGHT_CORE", "0.10"))
    MEMORY_WEIGHT_ACCESS: float = float(os.getenv("MEMORY_WEIGHT_ACCESS", "0.05"))

    # Open Loops & Smart Reminders (Release 3.5.1)
    REMINDER_CHECK_INTERVAL_SECONDS: int = int(os.getenv("REMINDER_CHECK_INTERVAL_SECONDS", "30"))
    REMINDERS_RESPECT_SLEEP_WINDOW: bool = os.getenv("REMINDERS_RESPECT_SLEEP_WINDOW", "false").lower() in ("true", "1", "yes")
    MAX_ACTIVE_OPEN_LOOPS_CONTEXT: int = int(os.getenv("MAX_ACTIVE_OPEN_LOOPS_CONTEXT", "2"))

    # Session Reflection & Memory Hygiene (Release 3.5.3)
    SESSION_REFLECTION_ENABLED: bool = os.getenv("SESSION_REFLECTION_ENABLED", "false").lower() in ("true", "1", "yes")
    MEMORY_HYGIENE_ENABLED: bool = os.getenv("MEMORY_HYGIENE_ENABLED", "false").lower() in ("true", "1", "yes")
    MEMORY_HYGIENE_INTERVAL_HOURS: int = int(os.getenv("MEMORY_HYGIENE_INTERVAL_HOURS", "24"))
    SESSION_REFLECTION_IDLE_MINUTES: int = int(os.getenv("SESSION_REFLECTION_IDLE_MINUTES", "90"))

    STORY_SEED_LIBRARY_ENABLED: bool = os.getenv("STORY_SEED_LIBRARY_ENABLED", "false").lower() in ("true", "1", "yes")
    WORLD_HYGIENE_ENABLED: bool = os.getenv("WORLD_HYGIENE_ENABLED", "false").lower() in ("true", "1", "yes")
    WORLD_DISCOVERY_PROMOTION_THRESHOLD: int = int(os.getenv("WORLD_DISCOVERY_PROMOTION_THRESHOLD", "3"))
    WORLD_PREFERENCE_PROMOTION_THRESHOLD: int = int(os.getenv("WORLD_PREFERENCE_PROMOTION_THRESHOLD", "4"))
    INTEREST_FADING_DAYS: int = int(os.getenv("INTEREST_FADING_DAYS", "14"))
    INTEREST_DORMANT_DAYS: int = int(os.getenv("INTEREST_DORMANT_DAYS", "45"))
    INTEREST_FADING_STRENGTH_STEP: float = float(os.getenv("INTEREST_FADING_STRENGTH_STEP", "0.08"))
    INTEREST_DORMANT_STRENGTH: float = float(os.getenv("INTEREST_DORMANT_STRENGTH", "0.15"))
    EVENT_COMPACTION_DAYS: int = int(os.getenv("EVENT_COMPACTION_DAYS", "90"))
    EVENT_COMPACTION_MAX_IMPORTANCE: float = float(os.getenv("EVENT_COMPACTION_MAX_IMPORTANCE", "0.35"))
    RESPONSE_AVAILABILITY_DEBUG: bool = os.getenv("RESPONSE_AVAILABILITY_DEBUG", "false").lower() in ("true", "1", "yes")
    REAL_USAGE_TELEMETRY_ENABLED: bool = os.getenv("REAL_USAGE_TELEMETRY_ENABLED", "false").lower() in ("true", "1", "yes")
    RESPONSE_AVAILABILITY_CHECK_SECONDS: int = int(os.getenv("RESPONSE_AVAILABILITY_CHECK_SECONDS", "15"))
    RESPONSE_AVAILABILITY_PROFILES = None  # optional override; defaults live in response_availability.py
    # v3.7.0 — CRITICAL urgency during SLEEPING requires explicit wake policy.
    # When false (default for first soak), sleep remains protected even for CRITICAL messages.
    CRITICAL_WAKE_POLICY_ENABLED: bool = os.getenv("CRITICAL_WAKE_POLICY_ENABLED", "false").lower() in ("true", "1", "yes")
    # Living World v3.6.2 calibrou ~89% de dias banais. Auditoria #6 (decisão do
    # Patrick, 21/09): "ela tem 20 anos, garota popular, tem mais é que viver" —
    # 0,25 aqui + gancho em 70% dos dias (social_day.HOOK_CHANCE) dá história
    # nova em cerca de metade dos dias. Limite de 1 história nova por dia e
    # eventos graves bloqueados continuam valendo.
    STORY_EVENT_CADENCE_THRESHOLD: float = float(os.getenv("STORY_EVENT_CADENCE_THRESHOLD", "0.25"))
    STORY_THREAD_DORMANT_DAYS: int = int(os.getenv("STORY_THREAD_DORMANT_DAYS", "7"))
    VOICE_PROSODY_ENABLED: bool = os.getenv("VOICE_PROSODY_ENABLED", "false").lower() in ("true", "1", "yes")
    VOICE_PROSODY_EMOTION_ENABLED: bool = os.getenv("VOICE_PROSODY_EMOTION_ENABLED", "false").lower() in ("true", "1", "yes")
    VOICE_PROSODY_PAUSES_ENABLED: bool = os.getenv("VOICE_PROSODY_PAUSES_ENABLED", "false").lower() in ("true", "1", "yes")
    VOICE_PROSODY_SOUND_TAGS_ENABLED: bool = os.getenv("VOICE_PROSODY_SOUND_TAGS_ENABLED", "false").lower() in ("true", "1", "yes")
    VOICE_PROSODY_FILLERS_ENABLED: bool = os.getenv("VOICE_PROSODY_FILLERS_ENABLED", "false").lower() in ("true", "1", "yes")
    VOICE_PROSODY_CONTINUOUS_SOUND_ENABLED: bool = os.getenv("VOICE_PROSODY_CONTINUOUS_SOUND_ENABLED", "false").lower() in ("true", "1", "yes")
    VOICE_PROSODY_MAX_SOUND_TAGS: int = int(os.getenv("VOICE_PROSODY_MAX_SOUND_TAGS", "2"))
    RESPONSE_DEFAULT_MAX_BUBBLES: int = int(os.getenv("RESPONSE_DEFAULT_MAX_BUBBLES", "2"))
    RESPONSE_CASUAL_SOFT_CHARS: int = int(os.getenv("RESPONSE_CASUAL_SOFT_CHARS", "180"))
    RESPONSE_NORMAL_SOFT_CHARS: int = int(os.getenv("RESPONSE_NORMAL_SOFT_CHARS", "420"))
    RESPONSE_LONG_SOFT_CHARS: int = int(os.getenv("RESPONSE_LONG_SOFT_CHARS", "900"))
    VOICE_CASUAL_SOFT_SECONDS: int = int(os.getenv("VOICE_CASUAL_SOFT_SECONDS", "15"))
    VOICE_NORMAL_SOFT_SECONDS: int = int(os.getenv("VOICE_NORMAL_SOFT_SECONDS", "30"))
    VOICE_SUPPORTIVE_SOFT_SECONDS: int = int(os.getenv("VOICE_SUPPORTIVE_SOFT_SECONDS", "45"))
    REAL_CONTEXT_FETCH_ENABLED: bool = os.getenv("REAL_CONTEXT_FETCH_ENABLED", "false").lower() in ("true", "1", "yes")
    FERIADOS_API_ENABLED: bool = os.getenv("FERIADOS_API_ENABLED", "false").lower() in ("true", "1", "yes")
    FERIADOS_API_KEY: str = os.getenv("FERIADOS_API_KEY", "").strip()
    REAL_WORLD_PLACE_LOOKUP_ENABLED: bool = os.getenv("REAL_WORLD_PLACE_LOOKUP_ENABLED", "false").lower() in ("true", "1", "yes")
    WORLD_STATE_DEFAULT_STALE_MINUTES: int = int(os.getenv("WORLD_STATE_DEFAULT_STALE_MINUTES", "60"))
    # Patch 032: default passou de "en" para "pt-BR". O Patch 021 mostrou que
    # instrução de controle em inglês degrada a voz da Marina (modelo lê regra
    # em EN, responde em PT e mistura os dois registros). O .env do Patrick já
    # marcava pt-BR, mas o default em "en" era uma armadilha para qualquer
    # ambiente sem a variável setada.
    PROMPT_CONTROL_LANGUAGE: str = os.getenv("PROMPT_CONTROL_LANGUAGE", "pt-BR").strip()
    MARINA_OUTPUT_LANGUAGE: str = os.getenv("MARINA_OUTPUT_LANGUAGE", "pt-BR").strip()
    VISION_MODEL: str = os.getenv("VISION_MODEL", "google/gemini-2.5-flash").strip()
    VISION_ENABLED: bool = os.getenv("VISION_ENABLED", "true").lower() in ("true", "1", "yes")
    
    # LoRAs de Estética iPhone e Mirror Selfie (FLUX.1 Dev)
    IPHONE_LORAS_ENABLED: bool = os.getenv("IPHONE_LORAS_ENABLED", "false").lower() in ("true", "1", "yes")
    IPHONE_PHOTO_LORA_NAME: str = os.getenv("IPHONE_PHOTO_LORA_NAME", "iphone_photo_flux.safetensors").strip()
    MIRROR_SELFIE_LORA_NAME: str = os.getenv("MIRROR_SELFIE_LORA_NAME", "mirror_selfie_flux.safetensors").strip()
    IPHONE_DEVICE_LORA_NAME: str = os.getenv("IPHONE_DEVICE_LORA_NAME", "iphone16pro_flux.safetensors").strip()
    # API-Sports / API-Football (Botafogo Live Tracking)
    APISPORTS_KEY: str = os.getenv("APISPORTS_KEY", "").strip()
    BOTAFOGO_TRACKING_ENABLED: bool = os.getenv("BOTAFOGO_TRACKING_ENABLED", "true").lower() in ("true", "1", "yes")
    BOTAFOGO_POLL_INTERVAL_SECONDS: int = int(os.getenv("BOTAFOGO_POLL_INTERVAL_SECONDS", "120"))
    BOTAFOGO_TEAM_ID: int = int(os.getenv("BOTAFOGO_TEAM_ID", "120"))


    def memory_weights(self) -> dict[str, float]:
        names = ("LEXICAL", "IMPORTANCE", "CONFIDENCE", "FRESHNESS", "CORE", "ACCESS")
        weights = {name: getattr(self, "MEMORY_WEIGHT_" + name) for name in names}
        if any(not math.isfinite(value) or value < 0 for value in weights.values()):
            raise ValueError("Pesos de memória devem ser finitos e não negativos")
        total = sum(weights.values())
        if not math.isfinite(total) or total <= 0:
            raise ValueError("Soma dos pesos de memória deve ser finita e positiva")
        return {name: value / total for name, value in weights.items()}

    @classmethod
    def validate(cls) -> list[str]:
        errors = []
        if cls.RESPONSE_AVAILABILITY_CHECK_SECONDS < 5:
            errors.append('RESPONSE_AVAILABILITY_CHECK_SECONDS deve ser >= 5')
        if cls.WORLD_DISCOVERY_PROMOTION_THRESHOLD < 2:
            errors.append('WORLD_DISCOVERY_PROMOTION_THRESHOLD deve ser >= 2')
        if cls.WORLD_PREFERENCE_PROMOTION_THRESHOLD < 2:
            errors.append('WORLD_PREFERENCE_PROMOTION_THRESHOLD deve ser >= 2')
        if cls.INTEREST_FADING_DAYS <= 0 or cls.INTEREST_DORMANT_DAYS <= cls.INTEREST_FADING_DAYS:
            errors.append('INTEREST_DORMANT_DAYS deve ser maior que INTEREST_FADING_DAYS')
        try:
            cls().memory_weights()
        except ValueError as exc:
            errors.append(str(exc))
        if not cls.TELEGRAM_BOT_TOKEN or cls.TELEGRAM_BOT_TOKEN == "SEU_TOKEN_TELEGRAM_AQUI":
            errors.append("TELEGRAM_BOT_TOKEN não configurado no .env")
        if not cls.LLM_API_KEY or cls.LLM_API_KEY.startswith("sk-..."):
            errors.append("LLM_API_KEY não configurada no .env")
        if not cls.TARGET_CHAT_ID or cls.TARGET_CHAT_ID <= 0:
            errors.append("TARGET_CHAT_ID não configurado ou inválido no .env (deve ser > 0)")
        return errors

settings = Settings()
