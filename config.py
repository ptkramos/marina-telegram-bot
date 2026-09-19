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


    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    
    # Configurações do Provedor de LLM (OpenRouter / OpenAI / Outros)
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").strip()
    LLM_MODEL: str = os.getenv("LLM_MODEL", "mistralai/mistral-nemo").strip()
    
    # URL da API do Stable Diffusion na RX 570 (legado/local)
    _raw_sd_url = os.getenv("SD_API_URL", "http://127.0.0.1:7860/").strip()
    SD_API_URL: str = _raw_sd_url if _raw_sd_url.endswith("/") else f"{_raw_sd_url}/"
    
    # Chat ID alvo do namorado (exclusividade total)
    TARGET_CHAT_ID: int = int(os.getenv("TARGET_CHAT_ID", "0"))

    # Buffer Inteligente de Digitação (Debounce)
    MESSAGE_DEBOUNCE_SECONDS: float = float(os.getenv("MESSAGE_DEBOUNCE_SECONDS", "3.8"))
    
    # Consolidação Periódica de Memória
    MEMORY_CONSOLIDATION_BATCH_SIZE: int = int(os.getenv("MEMORY_CONSOLIDATION_BATCH_SIZE", "8"))

    # Motor de Geração de Imagem (novita ou local)
    IMAGE_ENGINE: str = os.getenv("IMAGE_ENGINE", "novita").strip().lower()
    # Temporary provider outage accepted for the 3.7.0 soak; not a feature rollback.
    PHOTO_PROVIDER_MAINTENANCE: bool = os.getenv("PHOTO_PROVIDER_MAINTENANCE", "false").lower() in ("true", "1", "yes")
    NOVITA_API_KEY: str = os.getenv("NOVITA_API_KEY", "").strip()

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
    # Living World v3.6.2: Cadência de novos Story Events calibrada para ~89% de dias banais (longo prazo).
    # Com STORY_THREAD_DORMANT_DAYS=7 e STORY_EVENT_CADENCE_THRESHOLD=0.60, a simulação de 1.095 dias
    # produz ~11% de novos eventos e ~89% de dias banais, preservando cooldowns e limites.
    STORY_EVENT_CADENCE_THRESHOLD: float = float(os.getenv("STORY_EVENT_CADENCE_THRESHOLD", "0.60"))
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
    PROMPT_CONTROL_LANGUAGE: str = os.getenv("PROMPT_CONTROL_LANGUAGE", "en").strip()
    MARINA_OUTPUT_LANGUAGE: str = os.getenv("MARINA_OUTPUT_LANGUAGE", "pt-BR").strip()
    VISION_MODEL: str = os.getenv("VISION_MODEL", "google/gemini-2.0-flash-001").strip()
    VISION_ENABLED: bool = os.getenv("VISION_ENABLED", "true").lower() in ("true", "1", "yes")
    
    # LoRAs de Estética iPhone e Mirror Selfie (FLUX.1 Dev)
    IPHONE_LORAS_ENABLED: bool = os.getenv("IPHONE_LORAS_ENABLED", "false").lower() in ("true", "1", "yes")
    IPHONE_PHOTO_LORA_NAME: str = os.getenv("IPHONE_PHOTO_LORA_NAME", "iphone_photo_flux.safetensors").strip()
    MIRROR_SELFIE_LORA_NAME: str = os.getenv("MIRROR_SELFIE_LORA_NAME", "mirror_selfie_flux.safetensors").strip()
    IPHONE_DEVICE_LORA_NAME: str = os.getenv("IPHONE_DEVICE_LORA_NAME", "iphone16pro_flux.safetensors").strip()


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
