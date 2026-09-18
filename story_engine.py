"""Offline v3.6.2 story continuity; no Telegram, no LLM and no disclosure."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import random
import re

from config import settings
from db import DatabaseManager
from world_repository import WorldBibleRepository


@dataclass(frozen=True)
class StorySeed:
    key: str
    title: str
    summary: str
    thread_type: str
    autonomy_level: int
    importance: float
    participants: tuple[str, ...]
    place_key: str | None = None


SEEDS = (
    StorySeed('forgot_item','Objeto esquecido','Marina percebeu que esqueceu um objeto pequeno. O objeto e o desfecho ainda não estão definidos.','ordinary',1,.15,('marina',)),
    StorySeed('pet_minor_mischief','Travessura de Milo','Milo aprontou uma travessura pequena em casa. O que ele fez ainda não está definido.','ordinary',1,.15,('marina',),'marina_apartment'),
    StorySeed('small_misunderstanding','Mal-entendido leve','Marina percebeu um mal-entendido pequeno; conteúdo e reação permanecem indefinidos.','social',1,.25,('marina',)),
    StorySeed('unexpected_invitation','Convite possível','Surgiu um convite social, ainda sem detalhes ou decisão de Marina.','social',1,.25,('marina',)),
    StorySeed('project_deadline_change','Prazo de projeto','Um prazo acadêmico pode precisar de revisão. Nenhuma mudança de calendário foi confirmada.','academic',2,.35,('marina',)),
    StorySeed('unexpected_work_opportunity','Possível oportunidade','Lívia mencionou uma possibilidade profissional; nada foi aceito nem agendado.','professional',2,.45,('marina','livia_vasconcelos')),
    StorySeed('schedule_conflict','Possível conflito de agenda','Um compromisso informado pode coincidir com outro; datas e solução ainda não estão definidos.','social',1,.2,('marina',)),
    StorySeed('missed_transport_connection','Transporte perdido','Em deslocamento informado, Marina pode ter perdido uma conexão; trajeto e solução não estão definidos.','ordinary',1,.15,('marina',)),
    StorySeed('minor_purchase_problem','Pequeno problema em compra','Uma compra informada pode ter apresentado um problema pequeno; item e solução não estão definidos.','ordinary',1,.15,('marina',)),
    StorySeed('small_success','Pequena conquista','Marina concluiu uma tarefa cotidiana informada; os detalhes ainda não estão definidos.','ordinary',1,.15,('marina',)),
    StorySeed('friend_plan_cancelled','Plano social alterado','Um plano com contato já conhecido foi desmarcado; a alternativa ainda não foi definida.','social',1,.2,('marina',)),
    StorySeed('small_favor_requested','Pedido de ajuda pequeno','Um contato conhecido pediu uma ajuda pequena; Marina ainda não decidiu como responder.','social',1,.2,('marina',)),
    StorySeed('support_for_friend','Apoio a contato próximo','Um contato conhecido sinalizou que precisa de apoio; o gesto de Marina ainda não foi definido.','social',1,.2,('marina',)),
    StorySeed('minor_embarrassment','Constrangimento leve','Marina viveu um momento social levemente constrangedor; a reação ainda não foi definida.','social',1,.15,('marina',)),
    StorySeed('positive_feedback','Comentário positivo','Marina recebeu um comentário positivo sobre tarefa conhecida; a reação ainda não foi definida.','ordinary',1,.15,('marina',)),
    StorySeed('home_task_disrupted','Tarefa doméstica interrompida','Uma pequena questão doméstica interrompeu uma tarefa informada; a solução não foi definida.','ordinary',1,.15,('marina',)),
    StorySeed('leisure_plan_changed','Lazer remarcado','Um plano de lazer informado mudou; a nova escolha ainda não foi definida.','ordinary',1,.15,('marina',)),
    StorySeed('weather_changes_plan','Plano afetado pelo tempo','Um plano externo informado foi afetado pelo tempo; a alternativa ainda não foi definida.','ordinary',1,.15,('marina',)),
    StorySeed('academic_feedback','Retorno acadêmico','Marina recebeu retorno sobre projeto acadêmico ativo; ajustes ainda não foram definidos.','academic',2,.3,('marina',)),
    StorySeed('professional_feedback','Retorno profissional','Marina recebeu retorno sobre trabalho informado; a resposta ainda não foi definida.','professional',2,.3,('marina',)),
    StorySeed('small_disagreement','Divergência leve','Uma divergência pequena com contato conhecido foi informada; a conversa ainda não foi resolvida.','social',1,.2,('marina',)),
    StorySeed('minor_help_received','Ajuda recebida','Um contato conhecido ofereceu uma ajuda pequena; a reação de Marina ainda não foi definida.','social',1,.15,('marina',)),
    StorySeed('forgotten_commitment','Compromisso esquecido','Marina percebeu que esqueceu um compromisso informado; a reparação ainda não foi definida.','social',1,.2,('marina',)),
    StorySeed('partner_small_gesture','Pequeno gesto de carinho','Um gesto pequeno de Patrick foi informado; a reação de Marina ainda não está definida.','romantic',1,.15,('marina','patrick_ramos')),
    StorySeed('father_check_in','Contato de Henrique','Um contato de Henrique foi informado; quando e como Marina responderá ainda não está definido.','family',1,.15,('marina','henrique_salles')),
    StorySeed('self_care_pause','Pausa de autocuidado','Marina percebeu necessidade de descanso em um dia informado; atividade e duração não estão definidas.','ordinary',1,.15,('marina',)),
)
CURATED_SEED_KEYS = frozenset(seed.key for seed in SEEDS[:6])
LIBRARY_PATH = Path(__file__).resolve().parent / 'data' / 'story_seeds' / 'story_seed_library.v1.jsonl'
HARD_GATED = re.compile(r'\b(?:morreu|morte|gravidez|gravid[ao]|casamento|separação definitiva|terminou com patrick|doença grave|crime grave)\b',re.I)


def load_local_seed_pool():
    """Runtime reads only the small project-authored abstract library."""
    if not settings.STORY_SEED_LIBRARY_ENABLED:
        return tuple(seed for seed in SEEDS if seed.key in CURATED_SEED_KEYS)
    if not LIBRARY_PATH.is_file():
        raise FileNotFoundError(f'Biblioteca local de seeds ausente: {LIBRARY_PATH}')
    allowed = set()
    for line in LIBRARY_PATH.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('hard_gated') or row.get('intensity') not in ('BANAL','LOW'):
            continue
        allowed.add(row['seed_key'])
    return tuple(seed for seed in SEEDS if seed.key in CURATED_SEED_KEYS or seed.key in allowed)


class StoryCoherenceValidator:
    """Check facts the offline story engine can establish without guessing details."""

    def __init__(self, bible):
        self.bible = bible

    def validate_seed(self, seed):
        if seed.autonomy_level >= 3 or not 0 <= seed.importance <= .5:
            raise ValueError('Evento de alto impacto exige decisão explícita')
        if HARD_GATED.search(seed.title + ' ' + seed.summary):
            raise ValueError('Evento hard-gated exige decisão explícita')
        if not seed.key or not seed.title.strip() or not seed.summary.strip():
            raise ValueError('Seed incompleta')
        if 'marina' not in seed.participants or len(set(seed.participants)) != len(seed.participants):
            raise ValueError('Seed exige Marina e participantes únicos')
        if any(not self.bible.get_character(key) for key in seed.participants):
            raise ValueError('Participante desconhecido no mundo canônico')
        if seed.place_key and not self.bible.get_place(seed.place_key):
            raise ValueError('Lugar desconhecido no mundo canônico')

    def validate_consequence(self, thread, *, occurred, summary, participants):
        if not summary.strip() or HARD_GATED.search(summary):
            raise ValueError('Consequência vazia ou hard-gated')
        if not participants or len(set(participants)) != len(participants):
            raise ValueError('Consequência exige participantes únicos')
        if any(not self.bible.get_character(key) for key in participants):
            raise ValueError('Participante desconhecido no mundo canônico')
        if occurred.isoformat() <= thread['last_event_at']:
            raise ValueError('Consequência deve suceder o evento anterior')


class StoryEngine:
    def __init__(self, db: DatabaseManager):
        self.db=db
        self.bible=WorldBibleRepository(db)
        self.validator=StoryCoherenceValidator(self.bible)
        self.seed_pool=load_local_seed_pool()

    def _rng(self, key):
        return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big'))

    def narrative_budget(self, now):
        with self.db.get_connection() as c:
            seven=(now-timedelta(days=7)).isoformat()
            thirty=(now-timedelta(days=30)).isoformat()
            intensity=c.execute("SELECT COALESCE(SUM(importance),0) FROM life_events WHERE source_type='simulated' AND event_at>=? AND event_at<?",(seven,now.isoformat())).fetchone()[0]
            major=c.execute("SELECT COUNT(*) FROM life_events WHERE source_type='simulated' AND importance>=.7 AND event_at>=? AND event_at<?",(thirty,now.isoformat())).fetchone()[0]
            threads=c.execute("SELECT COUNT(*) FROM story_threads WHERE status='open' AND thread_type='social'").fetchone()[0]
        return {'seven_day_intensity':float(intensity),'thirty_day_major_events':major,'active_social_threads':threads}

    def _eligible(self, seed, now, context):
        if context.get('allowed_seed_keys') is not None and seed.key not in context['allowed_seed_keys']:
            return False
        if seed.place_key and not self.bible.get_place(seed.place_key):
            return False
        if seed.place_key and context.get('location_place_key') and seed.place_key != context['location_place_key']:
            return False
        if any(not self.bible.get_character(key) for key in seed.participants):
            return False
        if context.get('calendar_busy') and seed.key in ('unexpected_invitation','unexpected_work_opportunity'):
            return False
        required_context = {
            'schedule_conflict': 'existing_plan',
            'missed_transport_connection': 'travel_planned',
            'minor_purchase_problem': 'purchase_planned',
            'small_success': 'ordinary_task',
            'friend_plan_cancelled': 'plan_cancelled_observed',
            'small_favor_requested': 'favor_request_observed',
            'support_for_friend': 'friend_needs_support',
            'minor_embarrassment': 'embarrassment_observed',
            'positive_feedback': 'feedback_observed',
            'home_task_disrupted': 'home_issue_observed',
            'leisure_plan_changed': 'leisure_change_observed',
            'weather_changes_plan': 'weather_disruption_observed',
            'academic_feedback': 'academic_feedback_observed',
            'professional_feedback': 'professional_feedback_observed',
            'small_disagreement': 'disagreement_observed',
            'minor_help_received': 'help_received_observed',
            'forgotten_commitment': 'forgotten_commitment_observed',
            'partner_small_gesture': 'partner_gesture_observed',
            'father_check_in': 'father_contact_observed',
            'self_care_pause': 'rest_need_observed',
        }
        if seed.key in required_context and not context.get(required_context[seed.key]):
            return False
        if seed.key == 'partner_small_gesture' and not context.get('relationship_committed'):
            return False
        if context.get('relationship_tension',0) >= .7 and seed.key == 'small_misunderstanding':
            return False
        if seed.thread_type=='academic' and not context.get('academic_available'):
            return False
        if seed.thread_type=='professional' and not context.get('work_available'):
            return False
        if context.get('heavy_rain') and seed.key=='unexpected_invitation':
            return False
        if seed.thread_type in ('academic','professional') and context.get('energy',.7)<.4:
            return False
        return True

    def select_seed(self, now, *, context=None):
        """None represents an ordinary day; no detailed event is invented."""
        context=context or {}
        budget=self.narrative_budget(now)
        if budget['thirty_day_major_events'] or budget['seven_day_intensity']>=2 or budget['active_social_threads']>=2:
            return None
        with self.db.get_connection() as c:
            if c.execute("SELECT 1 FROM story_threads WHERE status='open' LIMIT 1").fetchone():
                return None  # Consequences require an observed continuation, not a lottery.
        rng=self._rng(f'{now.date().isoformat()}:story-v1')
        cadence_threshold = getattr(settings, 'STORY_EVENT_CADENCE_THRESHOLD', 0.60)
        if rng.random() < cadence_threshold:
            return None
        eligible=[s for s in self.seed_pool if self._eligible(s,now,context)]
        if not eligible:
            return None
        # Repetition guard; recent seeds do not recur as a new story.
        with self.db.get_connection() as c:
            recent={r[0] for r in c.execute("SELECT json_extract(metadata_json,'$.seed_key') FROM story_threads WHERE started_at>=?",((now-timedelta(days=30)).isoformat(),))}
        eligible=[s for s in eligible if s.key not in recent]
        return rng.choice(eligible) if eligible else None

    def daily_tick(self, now, *, context=None):
        """Explicit scheduler entry point; never run on import or from current bot."""
        day=now.date().isoformat()
        key=f'story_day:{day}'
        with self.db.transaction():
            with self.db.get_connection() as c:
                existing=c.execute('SELECT value FROM world_bootstrap WHERE key=?',(key,)).fetchone()
                if existing:
                    return json.loads(existing[0])
            self.quiet_old_threads(now)
            seed=self.select_seed(now,context=context)
            result={'date':day,'seed_key':seed.key if seed else None,'event_key':None}
            if seed:
                result['event_key']=self._start(seed,now)
            with self.db.get_connection() as c:
                c.execute('INSERT INTO world_bootstrap VALUES (?,?,?)',(key,json.dumps(result),now.isoformat()))
            return result

    def _start(self,seed,now):
        self.validator.validate_seed(seed)
        thread_key=f'{seed.key}:{now.date().isoformat()}'
        event_key=f'{thread_key}:start'
        place=self.bible.get_place(seed.place_key) if seed.place_key else None
        with self.db.get_connection() as c:
            thread_id=c.execute('''INSERT INTO story_threads(thread_key,thread_type,title,summary,status,importance,
                started_at,last_event_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?)''',
                (thread_key,seed.thread_type,seed.title,seed.summary,'open',seed.importance,
                 now.isoformat(),now.isoformat(),json.dumps({'seed_key':seed.key}))).lastrowid
            c.execute('''INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                autonomy_level,importance,location_place_id,participants_json,thread_id,share_worthy,created_at)
                VALUES (?,?,?,?,?,'simulated',?,?,?,?,?,0,?)''',
                (event_key,now.isoformat(),seed.key,seed.title,seed.summary,seed.autonomy_level,
                 seed.importance,place['id'] if place else None,json.dumps(seed.participants),thread_id,now.isoformat()))
        return event_key

    def continue_thread(self, thread_key, *, evidence_key, occurred_at, summary, participants=(), resolved=False):
        """Only an explicit new observation may establish a consequence."""
        if not evidence_key or not summary.strip() or not participants:
            raise ValueError('Continuação exige evidência, resumo e participantes explícitos')
        occurred=datetime.fromisoformat(occurred_at)
        with self.db.transaction():
            with self.db.get_connection() as c:
                thread=c.execute('SELECT * FROM story_threads WHERE thread_key=?',(thread_key,)).fetchone()
                if not thread or thread['status'] in ('resolved','abandoned'):
                    existing=c.execute('SELECT * FROM life_events WHERE event_key=?',(evidence_key,)).fetchone()
                    if existing and thread and self._same_evidence(existing, thread, occurred, summary, participants, resolved):
                        return existing['id']
                    raise ValueError('Thread inexistente ou encerrada')
                existing=c.execute('SELECT * FROM life_events WHERE event_key=?',(evidence_key,)).fetchone()
                if existing:
                    if not self._same_evidence(existing, thread, occurred, summary, participants, resolved):
                        raise ValueError('Evidência conflitante')
                    return existing['id']
                self.validator.validate_consequence(thread,occurred=occurred,summary=summary,participants=participants)
                previous=c.execute('SELECT id FROM life_events WHERE thread_id=? ORDER BY event_at DESC,id DESC LIMIT 1',(thread['id'],)).fetchone()
                if not previous:
                    raise ValueError('Thread sem evento anterior')
                event_id=c.execute('''INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                    autonomy_level,importance,participants_json,thread_id,consequence_of_event_id,share_worthy,resolved,created_at)
                    VALUES (?,?,?, ?,?,'user_shared',1,?,?,?, ?,0,?,?)''',
                    (evidence_key,occurred.isoformat(),'thread_consequence',thread['title'],summary,
                     thread['importance'],json.dumps(participants),thread['id'],previous['id'],int(resolved),datetime.now().isoformat())).lastrowid
                c.execute('UPDATE story_threads SET summary=?,status=?,last_event_at=?,resolution_json=? WHERE id=?',
                    (summary,'resolved' if resolved else 'open',occurred.isoformat(),
                     json.dumps({'event_id':event_id}) if resolved else None,thread['id']))
                return event_id

    @staticmethod
    def _same_evidence(event, thread, occurred, summary, participants, resolved):
        return (event['event_type']=='thread_consequence' and event['source_type']=='user_shared'
                and event['thread_id']==thread['id'] and event['event_at']==occurred.isoformat()
                and event['summary']==summary and json.loads(event['participants_json'])==list(participants)
                and bool(event['resolved'])==bool(resolved))

    def quiet_old_threads(self, now):
        from calendar_world import local_time

        now = local_time(now)
        dormant_days = getattr(settings, 'STORY_THREAD_DORMANT_DAYS', 7)
        with self.db.get_connection() as c:
            c.execute("UPDATE story_threads SET status='dormant' WHERE status='open' AND last_event_at<?",((now-timedelta(days=dormant_days)).isoformat(),))
            c.execute("""UPDATE story_threads SET status='abandoned'
                         WHERE status='dormant' AND last_event_at<?
                           AND thread_type NOT IN ('academic', 'professional')
                           AND COALESCE(json_extract(metadata_json, '$.auto_abandonable'), 1) = 1
                           AND COALESCE(json_extract(metadata_json, '$.has_future_commitment'), 0) = 0
                           AND COALESCE(json_extract(metadata_json, '$.protected'), 0) = 0
                           AND NOT EXISTS (
                               SELECT 1 FROM eventos_pendentes e
                               WHERE e.story_thread_id=story_threads.id
                                 AND e.owner_character_key='marina'
                                 AND e.confirmed=1 AND e.status='pending'
                                 AND e.event_at>?
                           )""",
                      ((now-timedelta(days=30)).isoformat(), now.isoformat()))
