"""Evidence-backed couple context and v3.6.5 proactive candidate ranking.

This service never invents relationship history. The sharing ledger in
knowledge_shares remains the authority for whether Patrick has heard an event.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import re
import unicodedata

from db import DatabaseManager
from knowledge_privacy import KnowledgePrivacy


CULTURE_KINDS = frozenset({'nickname_for_patrick', 'ritual', 'inside_joke', 'shared_preference'})
EXPLICIT_CULTURE = (
    ('nickname_for_patrick', re.compile(r'\b(?:me chama de|pode me chamar de)\s+["“]([^"”]{2,40})["”]', re.I)),
    ('ritual', re.compile(r'\b(?:nosso ritual|nossa tradição)\s+(?:é|vai ser)\s+["“]([^"”]{2,80})["”]', re.I)),
    ('inside_joke', re.compile(r'\bnossa piada interna\s+(?:é|vai ser)\s+["“]([^"”]{2,80})["”]', re.I)),
    ('shared_preference', re.compile(r'\b(?:nossa música|nosso lugar)\s+é\s+["“]([^"”]{2,80})["”]', re.I)),
)


def _normalized(value: str) -> str:
    plain = unicodedata.normalize('NFKC', value).casefold()
    return ' '.join(plain.split())


class RelationshipWorld:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.privacy = KnowledgePrivacy(db)

    def observe_explicit_user_culture(self, text: str, *, conversation_id: int) -> list[dict]:
        """Capture only explicitly quoted conventions from a received message.

        Negated requests and questions are not evidence of an adopted custom.
        A convention reaches the prompt only after a second distinct message.
        """
        if not text or '?' in text:
            return []
        with self.db.get_connection() as conn:
            message = conn.execute('SELECT role,content FROM conversas WHERE id=?',
                                   (conversation_id,)).fetchone()
        if not message or message['role'] != 'user' or message['content'] != text:
            raise ValueError('Expected the exact received Patrick message')
        observed = []
        for kind, pattern in EXPLICIT_CULTURE:
            for match in pattern.finditer(text):
                preface = text[max(0, match.start() - 12):match.start()].casefold()
                if re.search(r'\b(?:não|nunca|jamais)\s*$', preface):
                    continue
                observed.append(self.observe_culture(kind, match.group(1),
                                                     conversation_id=conversation_id))
        return observed

    def observe_culture(self, kind: str, phrase: str, *, conversation_id: int) -> dict:
        """Accept only a literal span in a received Patrick message.

        A proposed convention cannot be inserted merely because an LLM emitted
        it. Assistant text may be recorded before Telegram delivery. Replaying
        the same conversation does not reinforce it twice.
        """
        phrase = ' '.join(phrase.strip().split())
        normalized = _normalized(phrase)
        if (kind not in CULTURE_KINDS or not 2 <= len(phrase) <= 80
                or len(phrase.split()) > 12 or not isinstance(conversation_id, int)
                or conversation_id <= 0):
            raise ValueError('Invalid relationship culture evidence')
        with self.db.transaction():
            with self.db.get_connection() as conn:
                message = conn.execute(
                    "SELECT id,role,content,timestamp FROM conversas WHERE id=?",
                    (conversation_id,),
                ).fetchone()
                if (not message or message['role'] != 'user'
                        or normalized not in _normalized(message['content'])):
                    raise ValueError('Culture phrase is absent from recorded conversation')
                row = conn.execute('''SELECT id FROM relationship_culture
                    WHERE kind=? AND normalized_phrase=?''', (kind, normalized)).fetchone()
                if row:
                    culture_id = row['id']
                else:
                    culture_id = conn.execute('''INSERT INTO relationship_culture
                        (kind,phrase,normalized_phrase,first_seen_at,last_seen_at)
                        VALUES (?,?,?,?,?)''',
                        (kind, phrase, normalized, message['timestamp'], message['timestamp'])
                    ).lastrowid
                evidence = conn.execute('''INSERT OR IGNORE INTO relationship_culture_evidence
                    (culture_id,conversation_id) VALUES (?,?)''',
                    (culture_id, conversation_id))
                if row and evidence.rowcount:
                    conn.execute('''UPDATE relationship_culture SET
                        times_reinforced=times_reinforced+1,last_seen_at=?,active=1
                        WHERE id=?''', (message['timestamp'], culture_id))
                return dict(conn.execute('SELECT * FROM relationship_culture WHERE id=?',
                                         (culture_id,)).fetchone())

    def culture_context(self, *, limit: int = 3, now: datetime | None = None) -> list[str]:
        """Only reinforced, recent conventions reach the prompt."""
        cutoff = ((now or datetime.now()) - timedelta(days=180)).isoformat()
        with self.db.get_connection() as conn:
            rows = conn.execute('''SELECT kind,phrase FROM relationship_culture
                WHERE active=1 AND times_reinforced>=2 AND last_seen_at>=?
                ORDER BY last_seen_at DESC,id DESC LIMIT ?''', (cutoff, limit)).fetchall()
        labels = {'nickname_for_patrick': 'Patrick pediu para ser chamado de',
                  'ritual': 'ritual do casal', 'inside_joke': 'piada interna',
                  'shared_preference': 'preferência compartilhada'}
        return [f"{labels[row['kind']]}: {row['phrase']}" for row in rows]

    def shareable_events(self, now: datetime, *, limit: int = 5) -> list[dict]:
        """Only known, permissioned, unsent, substantiated events qualify."""
        since = (now - timedelta(days=21)).isoformat()
        with self.db.get_connection() as conn:
            rows = conn.execute('''SELECT e.* FROM life_events e
                JOIN knowledge_items k ON k.subject_type='event' AND k.subject_id=e.id
                    AND k.holder_character_key='marina' AND k.revoked_at IS NULL
                WHERE e.share_worthy>=0.65 AND e.event_at>=? AND e.event_at<=?
                    AND e.source_type IN ('canonical','real_world','user_shared')
                    AND NOT EXISTS (SELECT 1 FROM knowledge_shares s
                        WHERE s.subject_type='event' AND s.subject_id=e.id
                          AND s.to_character_key='patrick_ramos'
                          AND s.detail_level='details')
                ORDER BY e.share_worthy DESC,e.event_at DESC,e.id DESC LIMIT 20''',
                (since, now.isoformat())).fetchall()
        eligible = []
        for row in rows:
            decision = self.privacy.decision('event', row['id'], 'marina', 'patrick_ramos')
            if (decision.level == 'DETAILS' and decision.can_spontaneously_share
                    and not decision.recipient_already_knows
                    and 1 <= len(row['summary'].strip()) <= 320):
                eligible.append(dict(row))
        return eligible[:limit]

    def shared_history(self, *, limit: int = 3) -> list[dict]:
        """Project actual disclosures; no second shared-event store."""
        with self.db.get_connection() as conn:
            rows = conn.execute('''SELECT s.subject_id,MAX(s.shared_at) AS shared_at,e.title
                FROM knowledge_shares s JOIN life_events e
                  ON s.subject_type='event' AND s.subject_id=e.id
                WHERE s.from_character_key='marina' AND s.to_character_key='patrick_ramos'
                  AND s.detail_level='details'
                GROUP BY s.subject_id
                ORDER BY shared_at DESC,s.subject_id DESC LIMIT ?''', (limit,)).fetchall()
        return [dict(row) for row in rows]

    def ranked_candidate(self, now: datetime) -> dict | None:
        """Rank concrete reasons before a low-pressure relationship check-in."""
        with self.db.get_connection() as conn:
            event = conn.execute('''SELECT id,description FROM eventos_pendentes
                WHERE owner_character_key='patrick_ramos' AND status='pending'
                  AND ((follow_up_after IS NOT NULL AND follow_up_after<=?)
                    OR (follow_up_after IS NULL AND event_at IS NOT NULL AND event_at<=?))
                ORDER BY importance DESC,id ASC LIMIT 1''',
                (now.isoformat(), now.isoformat())).fetchone()
        if event:
            return {'reason': 'pending_event_followup', 'rank': 90,
                    'event_id': event['id'], 'detail': event['description']}
        from config import settings
        if True:
            loops = self.db.get_open_loops_para_checkin(now.isoformat())
            if loops:
                loop = loops[0]
                return {'reason': 'open_loop_checkin', 'rank': 80,
                        'loop_id': loop['id'], 'detail': loop['content']}
        events = self.shareable_events(now, limit=1)
        if events:
            event = events[0]
            return {'reason': 'share_worthy_event', 'rank': 70,
                    'subject_type': 'event', 'subject_id': event['id'],
                    'detail': event['summary'], 'event_at': event['event_at']}
        history = self.shared_history(limit=1)
        if history and history[0]['shared_at'] >= (now - timedelta(days=45)).isoformat():
            state = self.db.get_estado_relacional()
            last_callback = state.get('last_autonomous_message_at') or ''
            recently_called_back = (
                state.get('last_autonomous_reason') == 'shared_topic_callback'
                and state.get('last_autonomous_topic') == str(history[0]['subject_id'])
                and last_callback >= (now - timedelta(days=30)).isoformat()
            )
            if not recently_called_back:
                return {'reason': 'shared_topic_callback', 'rank': 40,
                        'subject_id': history[0]['subject_id'],
                        'detail': history[0]['title'], 'shared_at': history[0]['shared_at']}
        return {'reason': 'light_affection', 'rank': 20, 'detail': None}

