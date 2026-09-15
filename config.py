"""
Módulo de configurações e variáveis de ambiente do Bot da Marin Kitagawa.
Compatível com OpenAI, OpenRouter e outros provedores sem censura.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

class Settings:
    VERSION: str = "2.5.0"
    VERSION_NAME: str = "Marina Seltin - Ultra-Humanoid & Autonomous"

    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    
    # Configurações do Provedor de LLM (OpenRouter / OpenAI / Outros)
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").strip()
    LLM_MODEL: str = os.getenv("LLM_MODEL", "mistralai/mistral-nemo").strip()
    
    # URL da API do Stable Diffusion na RX 570
    _raw_sd_url = os.getenv("SD_API_URL", "http://127.0.0.1:7860/").strip()
    SD_API_URL: str = _raw_sd_url if _raw_sd_url.endswith("/") else f"{_raw_sd_url}/"
    
    # Chat ID alvo do namorado
    TARGET_CHAT_ID: int = int(os.getenv("TARGET_CHAT_ID", "0"))
    
    # Motor de Geração de Imagem (novita ou local)
    IMAGE_ENGINE: str = os.getenv("IMAGE_ENGINE", "novita").strip().lower()
    NOVITA_API_KEY: str = os.getenv("NOVITA_API_KEY", "").strip()

    # Ciclo de vontade própria e iniciativa
    AUTONOMOUS_CHECK_INTERVAL_MINUTES: int = int(os.getenv("AUTONOMOUS_CHECK_INTERVAL_MINUTES", "30"))
    AUTONOMOUS_TRIGGER_CHANCE: float = float(os.getenv("AUTONOMOUS_TRIGGER_CHANCE", "0.30"))

    # Síntese de Voz (ElevenLabs & Google Gemini TTS)
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "").strip()
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_VOICE_NAME: str = os.getenv("GEMINI_VOICE_NAME", "Leda").strip()
    NOVITA_VOICE_ID: str = os.getenv("NOVITA_VOICE_ID", "voice_d91c415d-f6a2-4d6f-b32c-aacfd5ad2e39").strip()
    NOVITA_VOICE_MODEL: str = os.getenv("NOVITA_VOICE_MODEL", "speech-2.8-hd").strip()

    @classmethod
    def validate(cls) -> list[str]:
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN or cls.TELEGRAM_BOT_TOKEN == "SEU_TOKEN_TELEGRAM_AQUI":
            errors.append("TELEGRAM_BOT_TOKEN não configurado no .env")
        if not cls.LLM_API_KEY or cls.LLM_API_KEY.startswith("sk-..."):
            errors.append("LLM_API_KEY não configurada no .env")
        return errors

settings = Settings()
