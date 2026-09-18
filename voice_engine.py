"""
Módulo de Síntese de Voz e Clonagem da Marina Seltin (v3.0.0 Oficial - Novita MiniMax).
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

from config import settings
from voice_profile import (
    VoiceProfile,
    get_voice_profile,
    PROFILE_CONVERSATIONAL,
    PROFILE_INTIMATE,
)
from voice_router import VoiceRouter, VoiceSelectionContext, voice_router

load_dotenv()
logger = logging.getLogger("VoiceEngine")

BASE_DIR = Path(__file__).resolve().parent
TEMP_AUDIO_DIR = BASE_DIR / "temp_audio"
TEMP_AUDIO_DIR.mkdir(exist_ok=True)


class VoiceEngine:
    def __init__(self):
        self.novita_api_key = os.getenv("NOVITA_API_KEY", "").strip()
        self.novita_voice_id = os.getenv("NOVITA_VOICE_ID", "voice_d91c415d-f6a2-4d6f-b32c-aacfd5ad2e39").strip()
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
        """Verifica se há algum motor ativo (Novita, ElevenLabs ou Gemini)."""
        conv_id = getattr(settings, "NOVITA_VOICE_ID_CONVERSATIONAL", "") or self.novita_voice_id
        has_novita = bool(self.novita_api_key and conv_id)
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

        # Expande gírias e abreviações da internet para fonética falada natural antes do TTS
        abreviacoes = {
            r'\bmds\b': 'meu Deus',
            r'\bvc\b': 'você',
            r'\bvcs\b': 'vocês',
            r'\btbm?\b': 'também',
            r'\bpq\b': 'porque',
            r'\bobg\b': 'obrigada',
            r'\bpvf?\b': 'por favor',
            r'\bblz\b': 'beleza',
            r'\bqto\b': 'quanto',
            r'\bmsg\b': 'mensagem',
            r'\bcmg\b': 'comigo',
            r'\bctg\b': 'contigo',
            r'\bpprt\b': 'papo reto',
            r'\bn\b': 'não',
        }
        for padrao, extensao in abreviacoes.items():
            clean = re.sub(padrao, extensao, clean, flags=re.IGNORECASE)

        # Substitui kkkk/hahaha solto no texto por risada fonética e tag acústica
        clean = re.sub(r'\b(?:k{2,}|ha(?:ha)+|rs(?:rs)+|ks(?:ks)+)\b', ' (chuckle) haha ', clean, flags=re.IGNORECASE)

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

    def _apply_expression_tags(self, clean_text: str, voice_profile: VoiceProfile, planner_tone: str = "") -> str:
        """
        Aplica tags acústicas nativas do MiniMax 2.8 de forma sutil e natural.
        Regra da Seção 68: 0 a 2 tags por mensagem curta (na maioria 0).
        Tags válidas: (chuckle), (laughs), (sighs), (breath), (pant), (gasp), (humming).
        """
        tags_validas = ["(chuckle)", "(laughs)", "(sighs)", "(breath)", "(pant)", "(gasp)", "(humming)"]
        existing_count = sum(clean_text.count(t) for t in tags_validas)

        # Se já possui 2 ou mais tags acústicas geradas pelo clean_text, não adiciona mais
        if existing_count >= 2:
            return clean_text

        # Para perfil íntimo com tom dengoso ou contexto de saudade, insere no máximo 1 tag suave
        if voice_profile.name == PROFILE_INTIMATE and existing_count == 0:
            tone_lower = (planner_tone or "").lower()
            text_lower = clean_text.lower()
            if "saudade" in text_lower:
                if not clean_text.startswith("("):
                    clean_text = f"(sighs) {clean_text}"
            elif tone_lower in ("dengosa", "sensual"):
                if not clean_text.startswith("("):
                    clean_text = f"(breath) {clean_text}"

        return clean_text

    async def _synthesize_novita_minimax(self, clean_text: str, out_ogg: Path, profile: VoiceProfile | None = None, voice_plan=None) -> bool:
        """
        Sintetiza via Novita MiniMax Speech 2.8 HD com o perfil vocal da Marina.
        Retorno de áudio binário direto via HEX com streaming instantâneo e sem delay de S3.
        """
        if not self.novita_api_key:
            return False

        active_profile = profile or get_voice_profile(PROFILE_CONVERSATIONAL)
        voice_id = active_profile.voice_id or self.novita_voice_id
        if not voice_id:
            return False

        url = f"https://api.novita.ai/v3/minimax-{self.novita_voice_model}"
        headers = {
            "Authorization": f"Bearer {self.novita_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "text": clean_text,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": active_profile.speed,
                "vol": active_profile.volume,
                "pitch": active_profile.pitch
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
        if voice_plan is not None:
            payload['voice_setting']['speed'] = max(.94, min(1.06, active_profile.speed * voice_plan.speed))
            payload['voice_setting'].update({k:v for k,v in voice_plan.provider_options.items() if k=='emotion'})
            payload['continuous_sound'] = voice_plan.continuous_sound

        loop = asyncio.get_running_loop()
        temp_mp3 = out_ogg.with_suffix(".mp3")

        try:
            logger.info(f"🎙️ Sintetizando áudio da Marina ({active_profile.name}) via Novita MiniMax ({self.novita_voice_model})...")
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
                logger.warning(f"Novita MiniMax retornou status {res.status_code}.")
        except Exception as e:
            logger.warning(f"Exceção ao chamar Novita MiniMax: {type(e).__name__}")

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
            logger.warning(f"Exceção ao chamar ElevenLabs: {type(e).__name__}")
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
                logger.warning(f"Exceção no Gemini {model}: {type(e).__name__}")

        return False

    async def synthesize(
        self,
        text: str,
        profile: str | VoiceProfile = "auto",
        context: VoiceSelectionContext | dict | None = None,
        response_policy=None
    ) -> Path | None:
        """
        Sintetiza texto em áudio nativo do Telegram (.ogg Opus com waveform).

        Ordem de Prioridade:
        1. Seleção de perfil vocal (Conversational vs Intimate) via VoiceRouter ou parâmetro explícito.
        2. Novita MiniMax Voice Cloning (speech-2.8-hd) com as configurações do perfil selecionado.
        3. Fallback de Provedor (ElevenLabs -> Google Gemini TTS Leda).
           - Se VOICE_ALLOW_CROSS_PROFILE_FALLBACK=False, NÃO troca de perfil Novita na falha!
        """
        if settings.VOICE_PROSODY_ENABLED:
            from voice_prosody import sanitize_display_text
            clean_text = sanitize_display_text(text)
        else:
            clean_text = self._clean_text_for_speech(text)
        if not clean_text:
            return None

        # 1. Determina o perfil vocal da Marina
        selected_profile: VoiceProfile
        reason: str = ""
        if profile == "auto":
            selected_profile, reason = voice_router.route(context)
        elif isinstance(profile, str):
            selected_profile = get_voice_profile(profile)
            reason = f"explicit_profile_{profile}"
        elif isinstance(profile, VoiceProfile):
            selected_profile = profile
            reason = "custom_profile_instance"
        else:
            selected_profile = get_voice_profile(PROFILE_CONVERSATIONAL)
            reason = "default_conversational"

        planner_tone = getattr(context, "tone", "") if context else ""
        if isinstance(context, dict):
            planner_tone = context.get("tone", "")
        voice_plan = None
        if settings.VOICE_PROSODY_ENABLED:
            from voice_prosody import select_voice_prosody, render_voice, capabilities_for
            if not hasattr(self, '_last_prosody_tag'):
                self._last_prosody_tag = None
            prosody = select_voice_prosody(clean_text,response_policy,last_sound_tag=self._last_prosody_tag)
            voice_plan = render_voice(clean_text,prosody,capabilities_for('novita',self.novita_voice_model))
            clean_text = voice_plan.render_text
            self._last_prosody_tag = '(chuckle)' if '(chuckle)' in clean_text else None
            logger.info('voice.prosody.selected reason_code=%s profile=%s',prosody.reason_code,selected_profile.name)
        else:
            clean_text = self._apply_expression_tags(clean_text, selected_profile, planner_tone=planner_tone)

        logger.info(f"🎙️ Voice Profile selecionado: {selected_profile.name} (motivo: {reason})")

        uid = uuid.uuid4().hex[:8]
        out_ogg = TEMP_AUDIO_DIR / f"voice_{uid}.ogg"

        # 2. Novita MiniMax Voice Cloning com o perfil selecionado (PRIORIDADE OFICIAL)
        if await self._synthesize_novita_minimax(clean_text, out_ogg, profile=selected_profile, voice_plan=voice_plan):
            if voice_plan is not None:
                self._log_actual_duration(out_ogg)
            return out_ogg

        # Se Novita falhou e cross-profile fallback estiver expressamente permitido:
        if getattr(settings, "VOICE_ALLOW_CROSS_PROFILE_FALLBACK", False):
            alt_profile_name = PROFILE_INTIMATE if selected_profile.name == PROFILE_CONVERSATIONAL else PROFILE_CONVERSATIONAL
            alt_profile = get_voice_profile(alt_profile_name)
            if alt_profile.voice_id != selected_profile.voice_id:
                logger.info(f"Tentando perfil Novita cruzado ({alt_profile.name}) por fallback configurado...")
                if await self._synthesize_novita_minimax(clean_text, out_ogg, profile=alt_profile, voice_plan=voice_plan):
                    if voice_plan is not None:
                        self._log_actual_duration(out_ogg)
                    return out_ogg

        # 3. ElevenLabs (Fallback de Provedor)
        fallback_text = clean_text
        if voice_plan is not None:
            from voice_prosody import render_voice, capabilities_for
            fallback_text = render_voice(voice_plan.display_text,prosody,capabilities_for('fallback')).render_text
            logger.info('voice.prosody.fallback provider=elevenlabs')
        if await self._synthesize_elevenlabs(fallback_text, out_ogg):
            if voice_plan is not None:
                self._log_actual_duration(out_ogg)
            return out_ogg

        # 4. Google Gemini TTS Leda (Fallback de Provedor)
        if await self._synthesize_gemini(fallback_text, out_ogg):
            if voice_plan is not None:
                self._log_actual_duration(out_ogg)
            return out_ogg

        logger.error("Falha em todos os motores de voz (MiniMax, ElevenLabs, Gemini).")
        return None

    @staticmethod
    def _log_actual_duration(audio_path: Path) -> None:
        if not audio_path.exists():
            return
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info('voice.duration_actual seconds=%.2f', float(result.stdout.strip()))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            logger.debug('voice.duration_actual unavailable')


voice_engine = VoiceEngine()
