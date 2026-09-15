"""
Módulo de Síntese de Voz e Clonagem da Marina Seltin (v3.5.0 - Novita MiniMax Oficial).
Gera mensagens de voz nativas do Telegram (.ogg Opus com waveform):
1. Modo Principal: Novita MiniMax Voice Cloning (speech-2.8-hd) com a voz oficial clonada da Marina,
   suporte a Português com language_boost e reações orgânicas (laughs, chuckle, sighs, breath, pant).
2. Modo Secundário: ElevenLabs (se voice_id customizado estiver ativo).
3. Modo Terciário: Google Gemini TTS (Voz Leda).
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
        self.novita_api_key = os.getenv("NOVITA_API_KEY", "").strip()
        self.novita_voice_id = os.getenv("NOVITA_VOICE_ID", "voice_73e73b73-65be-4cf9-9ab6-35d84f1946a3").strip()
        self.novita_voice_model = os.getenv("NOVITA_VOICE_MODEL", "speech-2.8-hd").strip()

        self.eleven_api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        self.eleven_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_voice_name = os.getenv("GEMINI_VOICE_NAME", "Leda").strip()

        self.gemini_models = [
            "gemini-3.1-flash-tts-preview",
            "gemini-2.5-flash-preview-tts"
        ]

    def is_configured(self) -> bool:
        """Verifica se há algum motor ativo."""
        has_novita = bool(self.novita_api_key and self.novita_voice_id)
        has_eleven = bool(self.eleven_api_key and self.eleven_voice_id and self.eleven_voice_id != "cgSgspJ2msm6clMCkdW9")
        has_gemini = bool(self.gemini_api_key)
        return has_novita or has_eleven or has_gemini

    def _clean_text_for_speech(self, text: str) -> str:
        """Limpa o texto e converte expressões de sentimento em tags acústicas suportadas pelo MiniMax 2.8."""
        clean = re.sub(r'\*?\s*\[MANDAR_AUDIO\]\s*\*?', '', text, flags=re.IGNORECASE)
        clean = re.sub(r'\*?\s*\[AUDIO\]\s*\*?', '', clean, flags=re.IGNORECASE)
        clean = clean.replace("[VOZ]", "")
        clean = re.sub(r'\[APAGAR_ANTERIOR\]', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\[CORRIGIR_ANTERIOR:[^\]]+\]', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\[Ps:[^\]]*\]', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\(Ps:[^)]*\)', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\(\s*(No áudio|No audio|Na voz|Com voz|voz manhosa)[^)]*\)', '', clean, flags=re.IGNORECASE)

        # Mapeia ações humanas para interjeições auditivas nativas do MiniMax
        clean = re.sub(r'\*(?:risos?|risinho|risadinha|rindo|haha|kkk)\*', ' (chuckle) ', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\*(?:gargalhada|gargalha)\*', ' (laughs) ', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\*(?:suspiro|suspira)\*', ' (sighs) ', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\*(?:respira(?: fundo)?|arfa|arfar)\*', ' (breath) ', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\*(?:ofegante|arqueja)\*', ' (pant) ', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\*(?:surpresa|chocada|espanto)\*', ' (gasp) ', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\*(?:cantarola|cantarolando|hum)\*', ' (humming) ', clean, flags=re.IGNORECASE)

        # Remove outras ações teatrais genéricas entre asteriscos (*olha pra você*, etc)
        clean = re.sub(r'\*[^*]+\*', '', clean)

        # Suaviza pontuações repetidas
        clean = re.sub(r'!{2,}', '!', clean)
        clean = re.sub(r'\?{2,}', '?', clean)
        clean = re.sub(r'\.{3,}', '...', clean)

        # Remove emojis para evitar leitura estranha por extenso
        clean = re.sub(r'[\U00010000-\U0010ffff]', '', clean)

        # Normaliza espaços múltiplos
        clean = re.sub(r'\s+', ' ', clean)

        return clean.strip()

    async def _synthesize_novita_minimax(self, clean_text: str, out_ogg: Path) -> bool:
        """
        Sintetiza via Novita MiniMax Speech 2.8 HD com a voz oficial clonada da Marina.
        Retorno de áudio binário direto via HEX com streaming instantâneo e sem delay de S3.
        """
        if not self.novita_api_key or not self.novita_voice_id:
            return False

        url = f"https://api.novita.ai/v3/minimax-{self.novita_voice_model}"
        headers = {
            "Authorization": f"Bearer {self.novita_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "text": clean_text,
            "voice_setting": {
                "voice_id": self.novita_voice_id,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0
            },
            "audio_setting": {
                "format": "mp3",
                "sample_rate": 32000,
                "channel": 1
            },
            "continuous_sound": True,
            "language_boost": "Portuguese",
            "output_format": "hex"
        }

        loop = asyncio.get_running_loop()
        temp_mp3 = out_ogg.with_suffix(".mp3")

        try:
            logger.info(f"🎙️ Sintetizando áudio da Marina via Novita MiniMax ({self.novita_voice_model})...")
            res = await loop.run_in_executor(
                None,
                lambda: requests.post(url, json=payload, headers=headers, timeout=30)
            )

            if res.status_code == 200:
                data = res.json()
                hex_audio = data.get("data", {}).get("audio")
                if hex_audio:
                    mp3_bytes = bytes.fromhex(hex_audio)
                    temp_mp3.write_bytes(mp3_bytes)

                    # Converte MP3 para OGG Opus otimizado para mensagem de voz Telegram
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
                    logger.info("✅ Mensagem de voz da Marina gerada com sucesso no MiniMax!")
                    return True
                else:
                    logger.warning(f"MiniMax não retornou dados de áudio em HEX: {data}")
            else:
                logger.warning(f"Novita MiniMax retornou status {res.status_code}: {res.text[:150]}")
        except Exception as e:
            logger.warning(f"Exceção ao chamar Novita MiniMax: {e}")

        return False

    async def _synthesize_elevenlabs(self, clean_text: str, out_ogg: Path) -> bool:
        """Sintetiza via ElevenLabs como fallback."""
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
            logger.info("Sintetizando áudio de fallback via ElevenLabs...")
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
                logger.info(f"Sintetizando voz de fallback Leda pelo Google Gemini TTS ({model})...")
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
                                logger.info("Áudio da Marina (Gemini Leda) gerado com sucesso!")
                                return True
            except Exception as e:
                logger.warning(f"Exceção no Gemini {model}: {e}")

        return False

    async def synthesize(self, text: str) -> Path | None:
        """
        Sintetiza texto em áudio nativo do Telegram (.ogg Opus com waveform).
        Ordem de Prioridade:
        1. Novita MiniMax Voice Cloning (speech-2.8-hd com a voz clonada oficial)
        2. ElevenLabs (fallback)
        3. Google Gemini TTS Leda (fallback)
        """
        clean_text = self._clean_text_for_speech(text)
        if not clean_text:
            return None

        uid = uuid.uuid4().hex[:8]
        out_ogg = TEMP_AUDIO_DIR / f"voice_{uid}.ogg"

        # 1. Novita MiniMax Voice Cloning (PRIORIDADE OFICIAL)
        if await self._synthesize_novita_minimax(clean_text, out_ogg):
            return out_ogg

        # 2. ElevenLabs
        if await self._synthesize_elevenlabs(clean_text, out_ogg):
            return out_ogg

        # 3. Google Gemini TTS (Leda)
        if await self._synthesize_gemini(clean_text, out_ogg):
            return out_ogg

        logger.error("Falha em todos os motores de voz (MiniMax, ElevenLabs, Gemini).")
        return None


voice_engine = VoiceEngine()
