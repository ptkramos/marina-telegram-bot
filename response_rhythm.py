"""Deterministic turn budget. Does not plan actions, route voices or truncate meaning."""
from dataclasses import dataclass, asdict
import logging
import re
import unicodedata

from config import settings

logger = logging.getLogger('ResponseRhythm')


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c))


@dataclass(frozen=True)
class ResponseStylePolicy:
    mode: str = 'casual_short'
    verbosity: str = 'low'
    target_bubbles: int = 1
    max_bubbles: int = 2
    soft_char_limit: int = 180
    prefer_open_turn: bool = True
    followup_question: str = 'optional'
    voice_soft_seconds: int = 15
    reason_code: str = 'casual_default'

    @property
    def token_budget(self):
        # Safety ceiling, not a length target; serious explanations must fit.
        return 2048 if self.mode in ('serious','explanatory','storytelling') else 512


def select_policy(message='', *, plan=None, voice=False, storytelling=False, emotional_context=None, batch_size=1):
    plan = plan or {}
    text = normalized(message)
    intent = plan.get('intent', '')
    tone = normalized(str(plan.get('tone', '')))
    mode, reason = 'casual_short', 'casual_default'
    if re.search(r'\b(detalhadamente|passo a passo|em detalhes|explica|explique|analisa|analise)\b', text):
        mode, reason = 'explanatory', 'explicit_details'
    elif intent in ('relationship_conflict','serious','urgent') or re.search(r'\b(precisamos conversar|terminar nosso namoro|discussao seria|emergencia|urgente)\b', text):
        mode, reason = 'serious', 'serious_context'
    elif storytelling or intent == 'storytelling':
        mode, reason = 'storytelling', 'grounded_story'
    elif intent == 'support_needed' or re.search(r'\b(desabafar|to triste|estou triste|foi uma merda|dia horrivel)\b',text):
        mode, reason = 'supportive', 'support_needed'
    elif intent == 'excited' or tone in ('excited','empolgada','empolgado'):
        mode, reason = 'excited', 'excited_context'
    elif intent == 'planning_future' or len(message)>500 or batch_size>3:
        mode, reason = 'normal', 'expanded_context'
    limits = {
        'casual_short': (settings.RESPONSE_CASUAL_SOFT_CHARS,settings.VOICE_CASUAL_SOFT_SECONDS,'low',1,settings.RESPONSE_DEFAULT_MAX_BUBBLES),
        'normal': (settings.RESPONSE_NORMAL_SOFT_CHARS,settings.VOICE_NORMAL_SOFT_SECONDS,'medium',1,2),
        'supportive': (settings.RESPONSE_NORMAL_SOFT_CHARS,settings.VOICE_SUPPORTIVE_SOFT_SECONDS,'low',1,2),
        'serious': (settings.RESPONSE_LONG_SOFT_CHARS,60,'high',1,2),
        'excited': (settings.RESPONSE_NORMAL_SOFT_CHARS,25,'medium',2,3),
        'storytelling': (settings.RESPONSE_LONG_SOFT_CHARS,90,'high',1,3),
        'explanatory': (settings.RESPONSE_LONG_SOFT_CHARS,120,'high',1,3),
    }
    chars, seconds, verbosity, target, maximum = limits[mode]
    question = 'required_for_action' if plan.get('needs_clarification') or plan.get('should_offer_reminder') else 'optional'
    if plan.get('followup_question') == 'none' and question == 'optional':
        question = 'not_required'
    policy = ResponseStylePolicy(mode,verbosity,target,max(1,maximum),max(1,chars),True,question,seconds,reason)
    logger.info('response_policy.selected mode=%s reason_code=%s voice=%s',mode,reason,voice)
    return policy


def apply_policy(prompt, policy):
    prompt = prompt.split('[RESPONSE RHYTHM]')[0].rstrip()
    # Remove only legacy rhythm constraints; style vocabulary remains authoritative.
    lines = prompt.splitlines()
    conflicts = ('balões','balão','baloes','balao','anti-textão','proibido textão',
                 'concisão absoluta','nunca envie redações','varie naturalmente a quantidade de mensagens')
    prompt = '\n'.join(line for line in lines if not any(x in line.casefold() for x in conflicts))
    mode_rule = {
        'casual_short': 'For a casual statement, joke or greeting without a question, favor one reaction that ends as a statement. Ask only to clarify something necessary.',
        'supportive': 'For a short vent, react like a partner in one sentence; avoid generic promises to be available. At most one real question.',
        'storytelling': 'If the supplied event is only one sentence, your retelling must stay that one event. If no event is supplied, do not pretend to remember it.',
        'explanatory': 'Answer directly in 2-4 conversational sentences; target around 900 characters unless the task truly requires more.',
    }.get(policy.mode,'')
    return prompt + '\n[RESPONSE RHYTHM]\n' + '\n'.join([
        'Optimize for the next conversational turn, not completeness of this answer.',
        'Default to one concise natural reaction. Do not restate obvious user facts or cover every topic.',
        'Avoid stock reassurance such as "estou aqui se precisar" and advice unless this turn truly calls for it.',
        'For greetings, jokes, routine updates and simple reactions, usually finish without a question. Ask only if the answer matters now.',
        'Write only the message Marina would send in chat. No stage directions, narrated gestures, asterisks, headings or markdown lists.',
        'Do not use multiple messages merely to appear human. A short laugh or interjection can be complete.',
        'World context informs what you may say; it creates no obligation to mention it.',
        'Keep the existing Brazilian Portuguese style without mechanically adding slang, emoji or swearing.',
        'Soft limits are guidance, never cut a sentence. Give necessary detail for serious or explanatory turns.',
        'For requested explanations, use a few plain chat sentences around 900 characters; leave extra depth for a follow-up if useful.',
        'For stories, describe only events explicitly supplied in context. No invented dialogue, timing, setting, gestures or backstory. If details are missing, one short grounded sentence is enough.',
        'For voice, write one spontaneous spoken message, not an essay. Vocal profile does not increase the budget.',
        'Required questions for an action such as scheduling a reminder still take priority.',
        mode_rule,
        ' '.join(f'{k}={v}' for k,v in asdict(policy).items()),
    ])


def segment(text, policy):
    text = text.replace('\\n','\n').strip()
    if not text:
        return []
    # Paragraphs can stay in a single Telegram message. Never split on length alone.
    parts = [text]
    if policy.target_bubbles > 1:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
        merged=[]
        for p in paragraphs:
            if merged and (len(p.split())==1 or len(merged[-1].split())==1):
                merged[-1] += ' '+p
            else:
                merged.append(p)
        if merged:
            parts=merged[:policy.max_bubbles-1]+['\n'.join(merged[policy.max_bubbles-1:])]
            parts=[p for p in parts if p]
    result=[]
    # Telegram hard transport limit is distinct from stylistic max_bubbles.
    for part in parts:
        while len(part.encode('utf-16-le'))//2 > 4096:
            stop=0
            units=0
            for char in part:
                units += 2 if ord(char)>0xffff else 1
                if units>4096:
                    break
                stop+=1
            boundary=max(part.rfind('\n',0,stop+1),part.rfind(' ',0,stop+1))
            cut=boundary if boundary>0 else stop
            result.append(part[:cut])
            part=part[cut:].lstrip()
        if part:
            result.append(part)
    logger.info('response_policy.segmented mode=%s bubbles=%d chars=%d',policy.mode,len(result),len(text))
    return result


def log_output(text, policy, *, voice=False):
    if len(text)>policy.soft_char_limit*2:
        logger.info('response_policy.override reason_code=soft_limit_exceeded mode=%s chars=%d',policy.mode,len(text))
    if voice:
        logger.info('voice.duration_estimated seconds=%.1f',len(text.split())/2.5)
