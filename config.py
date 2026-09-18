"""
Módulo de configurações e variáveis de ambiente do Bot de Marina Seltin.
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
    APP_NAME: str = "Marina Seltin"
    APP_VERSION: str = "3.5.3"
    VERSION: str = APP_VERSION
    VERSION_NAME: str = f"{APP_NAME} (v{APP_VERSION} Oficial - Reflection & Memory Hygiene)"


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

    # Feature Flags para evolução arquitetural incremental (3.2.0 - 3.5.0)
    SMART_MEMORY_ENABLED: bool = os.getenv("SMART_MEMORY_ENABLED", "true").lower() in ("true", "1", "yes")
    MEMORY_CONSOLIDATION_ENABLED: bool = os.getenv("MEMORY_CONSOLIDATION_ENABLED", "true").lower() in ("true", "1", "yes")
    MEMORY_INTELLIGENCE_ENABLED: bool = os.getenv("MEMORY_INTELLIGENCE_ENABLED", "true").lower() in ("true", "1", "yes")
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

    PLANNER_ENABLED: bool = os.getenv("PLANNER_ENABLED", "true").lower() in ("true", "1", "yes")
    EMOTIONAL_STATE_ENABLED: bool = os.getenv("EMOTIONAL_STATE_ENABLED", "true").lower() in ("true", "1", "yes")
    PENDING_EVENTS_ENABLED: bool = os.getenv("PENDING_EVENTS_ENABLED", "true").lower() in ("true", "1", "yes")
    
    # Open Loops & Smart Reminders (Release 3.5.1)
    OPEN_LOOPS_ENABLED: bool = os.getenv("OPEN_LOOPS_ENABLED", "true").lower() in ("true", "1", "yes")
    SMART_REMINDERS_ENABLED: bool = os.getenv("SMART_REMINDERS_ENABLED", "true").lower() in ("true", "1", "yes")
    REMINDER_CHECK_INTERVAL_SECONDS: int = int(os.getenv("REMINDER_CHECK_INTERVAL_SECONDS", "30"))
    REMINDERS_RESPECT_SLEEP_WINDOW: bool = os.getenv("REMINDERS_RESPECT_SLEEP_WINDOW", "false").lower() in ("true", "1", "yes")
    MAX_ACTIVE_OPEN_LOOPS_CONTEXT: int = int(os.getenv("MAX_ACTIVE_OPEN_LOOPS_CONTEXT", "2"))

    # Session Reflection & Memory Hygiene (Release 3.5.3)
    SESSION_REFLECTION_ENABLED: bool = os.getenv("SESSION_REFLECTION_ENABLED", "false").lower() in ("true", "1", "yes")
    MEMORY_HYGIENE_ENABLED: bool = os.getenv("MEMORY_HYGIENE_ENABLED", "false").lower() in ("true", "1", "yes")
    MEMORY_HYGIENE_INTERVAL_HOURS: int = int(os.getenv("MEMORY_HYGIENE_INTERVAL_HOURS", "24"))
    SESSION_REFLECTION_IDLE_MINUTES: int = int(os.getenv("SESSION_REFLECTION_IDLE_MINUTES", "90"))

    # Living World v3.6: infraestrutura pronta, integração liberada por etapa.
    LIVING_WORLD_ENABLED: bool = os.getenv("LIVING_WORLD_ENABLED", "false").lower() in ("true", "1", "yes")
    RESPONSE_RHYTHM_ENABLED: bool = os.getenv("RESPONSE_RHYTHM_ENABLED", "false").lower() in ("true", "1", "yes")
    STORY_SEED_LIBRARY_ENABLED: bool = os.getenv("STORY_SEED_LIBRARY_ENABLED", "false").lower() in ("true", "1", "yes")
    KNOWLEDGE_PRIVACY_ENABLED: bool = os.getenv("KNOWLEDGE_PRIVACY_ENABLED", "false").lower() in ("true", "1", "yes")
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
    # Reserved for 3.6.4 calendar projection; storage/seed do not activate behavior.
    ACADEMIC_LIFE_ENABLED: bool = os.getenv("ACADEMIC_LIFE_ENABLED", "false").lower() in ("true", "1", "yes")
    ACADEMIC_AUTO_TERM_GENERATION: bool = os.getenv("ACADEMIC_AUTO_TERM_GENERATION", "false").lower() in ("true", "1", "yes")
    CALENDAR_CONTINUITY_ENABLED: bool = os.getenv("CALENDAR_CONTINUITY_ENABLED", "false").lower() in ("true", "1", "yes")
    REAL_CONTEXT_FETCH_ENABLED: bool = os.getenv("REAL_CONTEXT_FETCH_ENABLED", "false").lower() in ("true", "1", "yes")
    FERIADOS_API_ENABLED: bool = os.getenv("FERIADOS_API_ENABLED", "false").lower() in ("true", "1", "yes")
    FERIADOS_API_KEY: str = os.getenv("FERIADOS_API_KEY", "").strip()
    REAL_WORLD_PLACE_LOOKUP_ENABLED: bool = os.getenv("REAL_WORLD_PLACE_LOOKUP_ENABLED", "false").lower() in ("true", "1", "yes")
    WORLD_STATE_DEFAULT_STALE_MINUTES: int = int(os.getenv("WORLD_STATE_DEFAULT_STALE_MINUTES", "60"))
    PROMPT_CONTROL_LANGUAGE: str = os.getenv("PROMPT_CONTROL_LANGUAGE", "en").strip()
    MARINA_OUTPUT_LANGUAGE: str = os.getenv("MARINA_OUTPUT_LANGUAGE", "pt-BR").strip()
    VISION_MODEL: str = os.getenv("VISION_MODEL", "google/gemini-2.0-flash-001").strip()
    VISION_ENABLED: bool = os.getenv("VISION_ENABLED", "true").lower() in ("true", "1", "yes")
    STYLE_ENGINE_V2_ENABLED: bool = os.getenv("STYLE_ENGINE_V2_ENABLED", "true").lower() in ("true", "1", "yes")
    SAFE_PATCHER_ENABLED: bool = os.getenv("SAFE_PATCHER_ENABLED", "false").lower() in ("true", "1", "yes")
    
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
