"""
Módulo de Síntese de Voz e Clonagem da Marina Seltin (v3.0.0 Estrita).
Gera mensagens de voz nativas do Telegram (.ogg Opus com waveform):
1. Modo Clone (ElevenLabs): Ativado automaticamente quando ELEVENLABS_VOICE_ID contiver a voz da amiga clonada.
2. Modo Google Gemini TTS (Leda): Voz oficial da Marina (jovem, doce, expressiva e natural) via chave Gemini Pro.
SEM FALLBACK EXTERNO: Não utiliza vozes robóticas ou de terceiros (sem Microsoft Thalita).
"""
import os
import re
import uuid
import logging
import asyncio
import base64
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("VoiceEngine")

BASE_DIR = Path(__file__).resolve().parent
TEMP_AUDIO_DIR = BASE_DIR / "temp_audio"
TEMP_AUDIO_DIR.mkdir(exist_ok=True)

class VoiceEngine:
    def __init__(self):
        self.eleven_api_key = os.getenv("ELEVENLABS_API_KEY", "")
        self.eleven_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_voice_name = os.getenv("GEMINI_VOICE_NAME", "Leda")
        
        # Modelos TTS oficiais do Gemini (3.1)
        self.gemini_models = [
            "gemini-3.1-flash-tts-preview",
            "gemini-2.5-flash-preview-tts"
        ]

    def is_configured(self) -> bool:
        """Verifica se há algum motor ativo (ElevenLabs clone ou Google Gemini TTS)."""
        has_clone = bool(self.eleven_api_key and self.eleven_voice_id and self.eleven_voice_id != "cgSgspJ2msm6clMCkdW9")
        has_gemini = bool(self.gemini_api_key)
        return has_clone or has_gemini

    def _clean_text_for_speech(self, text: str) -> str:
        """Limpa o texto para garantir máxima naturalidade e dicção impecável sem sotaques caricatos."""
        # Remove tags de controle (com ou sem asteriscos ao redor)
        clean = re.sub(r'\*?\s*\[MANDAR_AUDIO\]\s*\*?', '', text, flags=re.IGNORECASE)
        clean = re.sub(r'\*?\s*\[AUDIO\]\s*\*?', '', clean, flags=re.IGNORECASE)
        clean = clean.replace("[VOZ]", "")
        clean = re.sub(r'\[APAGAR_ANTERIOR\]', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\[CORRIGIR_ANTERIOR:[^\]]+\]', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\[Ps:[^\]]*\]', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\(Ps:[^)]*\)', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\(\s*(No áudio|Na voz|Com voz|voz manhosa)[^)]*\)', '', clean, flags=re.IGNORECASE)
        
        # Remove ações físicas entre asteriscos (*sorri*, *olha nos seus olhos*)
        clean = re.sub(r'\*[^*]+\*', '', clean)
        
        # Suaviza pontuações repetidas que forçam entonação histriônica
        clean = re.sub(r'!{2,}', '!', clean)
        clean = re.sub(r'\?{2,}', '?', clean)
        clean = re.sub(r'\.{3,}', '...', clean)
        
        # Remove emojis para evitar leitura estranha por extenso
        clean = re.sub(r'[\U00010000-\U0010ffff]', '', clean)
        
        return clean.strip()

    async def _synthesize_elevenlabs(self, clean_text: str, out_ogg: Path) -> bool:
        """Sintetiza via ElevenLabs se a voz clonada da amiga estiver ativa."""
        if not self.eleven_api_key or not self.eleven_voice_id or self.eleven_voice_id == "cgSgspJ2msm6clMCkdW9":
            return False
            
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.eleven_voice_id}"
        headers = {
            "xi-api-key": self.eleven_api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": clean_text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.85,
                "style": 0.35,
                "use_speaker_boost": True
            }
        }
        
        loop = asyncio.get_running_loop()
        temp_mp3 = out_ogg.with_suffix(".mp3")
        try:
            logger.info("Sintetizando áudio com voz clonada da amiga (ElevenLabs)...")
            res = await loop.run_in_executor(
                None,
                lambda: requests.post(url, json=payload, headers=headers, timeout=25)
            )
            if res.status_code == 200:
                temp_mp3.write_bytes(res.content)
                cmd = [
                    "ffmpeg", "-y", "-i", str(temp_mp3),
                    "-c:a", "libopus", "-b:a", "64k", str(out_ogg)
                ]
                await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                )
                if temp_mp3.exists():
                    temp_mp3.unlink()
                logger.info("Áudio ElevenLabs gerado com sucesso!")
                return True
            else:
                logger.warning(f"ElevenLabs retornou status {res.status_code}: {res.text[:100]}")
        except Exception as e:
            logger.warning(f"Exceção ao chamar ElevenLabs: {e}")
        return False

    async def _synthesize_gemini(self, clean_text: str, out_ogg: Path) -> bool:
        """Sintetiza via Google Gemini TTS exclusivamente com a voz Leda."""
        if not self.gemini_api_key:
            return False
            
        loop = asyncio.get_running_loop()
        
        for model in self.gemini_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"
            payload = {
                "contents": [{"parts": [{"text": clean_text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": self.gemini_voice_name
                            }
                        }
                    }
                }
            }
            
            try:
                logger.info(f"Sintetizando voz Leda pelo Google Gemini TTS ({model})...")
                res = await loop.run_in_executor(
                    None,
                    lambda u=url, p=payload: requests.post(u, json=p, timeout=45)
                )
                
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for p in parts:
                            if "inlineData" in p:
                                b64_audio = p["inlineData"].get("data")
                                mime = p["inlineData"].get("mimeType", "")
                                raw_bytes = base64.b64decode(b64_audio)
                                
                                temp_raw = out_ogg.with_suffix(".raw")
                                temp_raw.write_bytes(raw_bytes)
                                
                                if "l16" in mime or "pcm" in mime or not mime:
                                    cmd = [
                                        "ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                                        "-i", str(temp_raw), "-c:a", "libopus", "-b:a", "64k", str(out_ogg)
                                    ]
                                else:
                                    cmd = [
                                        "ffmpeg", "-y", "-i", str(temp_raw),
                                        "-c:a", "libopus", "-b:a", "64k", str(out_ogg)
                                    ]
                                    
                                await loop.run_in_executor(
                                    None,
                                    lambda: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                                )
                                
                                if temp_raw.exists():
                                    temp_raw.unlink()
                                logger.info(f"Áudio da Marina (Leda do Google) gerado com sucesso!")
                                return True
                else:
                    logger.warning(f"Google Gemini {model} retornou status {res.status_code} ({res.text[:100]})")
            except Exception as e:
                logger.warning(f"Exceção no Gemini {model}: {e}")
                
        return False

    async def synthesize(self, text: str) -> Path | None:
        """
        Sintetiza texto em áudio nativo do Telegram (.ogg Opus com waveform).
        Ordem estrita:
        1. ElevenLabs (quando Patrick desbloquear o cartão e ativar o clone da amiga)
        2. Google Gemini TTS (Voz Leda)
        SEM FALLBACK ROBÓTICO. Se falhar, retorna None.
        """
        clean_text = self._clean_text_for_speech(text)
        if not clean_text:
            return None

        uid = uuid.uuid4().hex[:8]
        out_ogg = TEMP_AUDIO_DIR / f"voice_{uid}.ogg"

        # 1. ElevenLabs (Clone da Amiga)
        if await self._synthesize_elevenlabs(clean_text, out_ogg):
            return out_ogg

        # 2. Google Gemini TTS (Leda Oficial)
        if await self._synthesize_gemini(clean_text, out_ogg):
            return out_ogg

        # Sem fallback para Thalita/Microsoft: se ambos falharem, loga e encerra
        logger.error("Falha na síntese de voz (nem ElevenLabs nem Gemini Leda responderam).")
        return None

voice_engine = VoiceEngine()
