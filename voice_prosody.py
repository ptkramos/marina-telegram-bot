"""Conservative provider-specific prosody. Display text is never the TTS payload."""
from dataclasses import dataclass, field
import logging
import re

from config import settings

logger = logging.getLogger('VoiceProsody')

TAG_PATTERN = re.compile(r'\((?:laughs|chuckle|sighs|sigh|breath|clear-throat|clears throat|coughs|gasps|gasp|pant|humming)\)', re.I)
PAUSE_PATTERN = re.compile(r'<#[0-9]+(?:\.[0-9]+)?#>')
LAUGH_PATTERN = re.compile(r'\b(?:k{2,}|ha(?:ha)+|rs(?:rs)+)\b', re.I)
SUPPORTED_EMOTIONS = frozenset({'neutral', 'happy', 'sad', 'angry', 'fearful', 'disgusted', 'surprised'})
SUPPORTED_SOUNDS = frozenset({'(chuckle)', '(laughs)', '(sighs)', '(gasps)'})


@dataclass(frozen=True)
class TTSProviderCapabilities:
    provider: str
    supports_emotion: bool = False
    supported_emotions: frozenset[str] = field(default_factory=frozenset)
    supports_pause_tags: bool = False
    supports_sound_tags: bool = False
    supported_sound_tags: frozenset[str] = field(default_factory=frozenset)
    supports_continuous_sound: bool = False
    supports_speed: bool = False


def capabilities_for(provider, model=None):
    if provider == 'novita' and model == 'speech-2.8-hd':
        return TTSProviderCapabilities('NOVITA_MINIMAX_2_8_HD_SYNC',
            supports_emotion=settings.VOICE_PROSODY_EMOTION_ENABLED,
            supported_emotions=SUPPORTED_EMOTIONS,
            supports_pause_tags=settings.VOICE_PROSODY_PAUSES_ENABLED,
            supports_sound_tags=settings.VOICE_PROSODY_SOUND_TAGS_ENABLED,
            supported_sound_tags=SUPPORTED_SOUNDS,
            supports_continuous_sound=settings.VOICE_PROSODY_CONTINUOUS_SOUND_ENABLED,
            supports_speed=True)
    return TTSProviderCapabilities('FALLBACK_PROVIDER')


@dataclass(frozen=True)
class VoiceProsodyPolicy:
    emotion: str | None = None
    intensity: str = 'NONE'
    speed: float = 1.0
    pause_profile: str = 'none'
    sound_tag_budget: int = 0
    filler_budget: int = 0
    continuous_sound: bool = False
    reason_code: str = 'neutral_default'


@dataclass(frozen=True)
class VoiceRenderPlan:
    display_text: str
    render_text: str
    emotion: str | None
    speed: float
    continuous_sound: bool
    provider_options: dict


def sanitize_display_text(text):
    # LLM content is treated as words, not permission to inject provider syntax.
    clean = PAUSE_PATTERN.sub(' ', TAG_PATTERN.sub(' ', text or ''))
    return '\n'.join(line for raw in clean.splitlines()
                     if (line := re.sub(r'[ \t]+',' ',raw).strip()))


def select_voice_prosody(display_text, response_policy=None, *, last_sound_tag=None):
    from response_rhythm import select_policy
    rhythm = response_policy or select_policy(display_text, voice=True)
    content = sanitize_display_text(display_text)
    lower = content.casefold()
    mode = rhythm.mode
    if len(content.split()) <= 3:
        return VoiceProsodyPolicy(reason_code='short_audio_neutral')
    if mode == 'supportive':
        return VoiceProsodyPolicy(intensity='SUBTLE',speed=.98,pause_profile='thoughtful',reason_code='supportive_neutral')
    if mode == 'serious':
        return VoiceProsodyPolicy(intensity='SUBTLE',speed=.98,reason_code='serious_neutral')
    if mode == 'storytelling':
        return VoiceProsodyPolicy(intensity='SUBTLE',pause_profile='thoughtful',
                                 continuous_sound=True,reason_code='storytelling')
    if mode == 'excited' and ('!' in content or re.search(r'\b(?:amei|consegui|incrivel)\b',lower)):
        return VoiceProsodyPolicy(emotion='happy',intensity='CLEAR',speed=1.03,
                                 sound_tag_budget=int(last_sound_tag!='(chuckle)'),
                                 reason_code='explicit_excitement')
    if ('?' in content and ('o quê' in lower or 'serio' in lower or 'sério' in lower)):
        return VoiceProsodyPolicy(emotion='surprised',intensity='CLEAR',speed=1.02,
                                 pause_profile='casual',reason_code='clear_surprise')
    if LAUGH_PATTERN.search(content) and last_sound_tag!='(chuckle)':
        return VoiceProsodyPolicy(intensity='SUBTLE',sound_tag_budget=1,reason_code='textual_laughter')
    return VoiceProsodyPolicy()


def render_voice(display_text, policy, capabilities, *, max_sound_tags=None):
    display = sanitize_display_text(display_text)
    render = display
    allowed_tags = max(0,min(2, max_sound_tags if max_sound_tags is not None else settings.VOICE_PROSODY_MAX_SOUND_TAGS))
    emotion = policy.emotion if capabilities.supports_emotion and policy.emotion in capabilities.supported_emotions else None
    if policy.emotion and emotion is None:
        logger.info('voice.prosody.unsupported_feature emotion')
    speed = min(1.06,max(.94,policy.speed)) if capabilities.supports_speed else 1.0
    if LAUGH_PATTERN.search(render):
        if capabilities.supports_sound_tags and '(chuckle)' in capabilities.supported_sound_tags and policy.sound_tag_budget and allowed_tags:
            render = LAUGH_PATTERN.sub('(chuckle)',render,count=1)
            render = LAUGH_PATTERN.sub('',render)
        else:
            render = LAUGH_PATTERN.sub('',render)
    if policy.pause_profile!='none' and capabilities.supports_pause_tags and len(render.split())>=7:
        # One pause at a natural sentence boundary, never after a fixed word.
        match = re.search(r'(?<=[.!?…])\s+',render)
        if match:
            duration = .30 if policy.pause_profile=='casual' else .35
            render = render[:match.start()] + f' <#{duration:.2f}#> ' + render[match.end():]
    if not capabilities.supports_pause_tags:
        render=PAUSE_PATTERN.sub(' ',render)
    if not capabilities.supports_sound_tags:
        render=TAG_PATTERN.sub(' ',render)
    else:
        found=TAG_PATTERN.findall(render)
        if len(found)>allowed_tags or any(t.casefold() not in capabilities.supported_sound_tags for t in found):
            render=TAG_PATTERN.sub(' ',render)
    render=re.sub(r'\s+',' ',render).strip()
    if not render:
        render='haha' if LAUGH_PATTERN.search(display) else display
    continuous=bool(policy.continuous_sound and capabilities.supports_continuous_sound)
    options={}
    if emotion:
        options['emotion']=emotion
    if continuous:
        options['continuous_sound']=True
    logger.info('voice.prosody.rendered provider=%s emotion=%s tags=%d pause=%s reason_code=%s',
                capabilities.provider,emotion,len(TAG_PATTERN.findall(render)),bool(PAUSE_PATTERN.search(render)),policy.reason_code)
    return VoiceRenderPlan(display,render,emotion,speed,continuous,options)
