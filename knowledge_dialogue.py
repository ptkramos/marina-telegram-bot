"""Reviewed subject aliases and deterministic disclosure replies.

The LLM never chooses a subject ID or decides whether a protected detail was
disclosed. Only registered aliases can route a turn, and the sent text comes
from reviewed fields or fixed privacy-safe templates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import unicodedata
from typing import Iterable

from db import DatabaseManager
from knowledge_privacy import KnowledgePrivacy, SUBJECT_TYPES


def _normalize(value: str) -> str:
    plain = unicodedata.normalize('NFKD', value.casefold())
    plain = ''.join(ch for ch in plain if not unicodedata.combining(ch))
    return ' '.join(re.findall(r'[a-z0-9]+', plain))


@dataclass(frozen=True)
class ResolvedTopic:
    subject_type: str
    subject_id: int
    matched_alias: str
    topic_label: str
    approved_detail: str


@dataclass(frozen=True)
class PrivacyReply:
    subject_type: str
    subject_id: int
    text: str
    disclosed_level: str | None


class KnowledgeDialogue:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.privacy = KnowledgePrivacy(db)

    def register_subject(self, subject_type: str, topic_label: str,
                         aliases: Iterable[str], *, approved_detail: str = '',
                         source_event_id: int | None = None,
                         source_thread_id: int | None = None) -> int:
        """Trusted ingestion only; never call with an LLM-proposed binding."""
        if subject_type not in SUBJECT_TYPES:
            raise ValueError('Unknown subject type')
        if not isinstance(topic_label, str) or not topic_label.strip():
            raise ValueError('A reviewed topic label is required')
        if not isinstance(approved_detail, str):
            raise ValueError('Approved detail must be text')
        if subject_type == 'event' and (not source_event_id or source_thread_id):
            raise ValueError('An event subject requires one source event')
        if subject_type == 'thread' and (not source_thread_id or source_event_id):
            raise ValueError('A thread subject requires one source thread')
        if subject_type in ('fact', 'relationship') and (source_event_id or source_thread_id):
            raise ValueError('This subject type has no event/thread source')
        normalized = {_normalize(alias) for alias in aliases}
        if not normalized or any(len(alias.split()) < 2 for alias in normalized):
            raise ValueError('Reviewed aliases must contain at least two words')
        with self.db.transaction():
            with self.db.get_connection() as conn:
                existing = conn.execute('''SELECT * FROM knowledge_subjects
                    WHERE subject_type=? AND topic_label=?''',
                    (subject_type, topic_label.strip())).fetchone()
                if existing:
                    prior_aliases = {row['normalized_alias'] for row in conn.execute('''
                        SELECT normalized_alias FROM knowledge_subject_aliases WHERE subject_id=?''',
                        (existing['id'],)).fetchall()}
                    if (existing['approved_detail'] != approved_detail.strip()
                            or existing['source_event_id'] != source_event_id
                            or existing['source_thread_id'] != source_thread_id
                            or prior_aliases != normalized):
                        raise ValueError('Registered subject differs from reviewed definition')
                    return (source_event_id if subject_type == 'event' else
                            source_thread_id if subject_type == 'thread' else existing['id'])
                if source_event_id and not conn.execute('SELECT 1 FROM life_events WHERE id=?',
                                                        (source_event_id,)).fetchone():
                    raise ValueError('Source event does not exist')
                if source_thread_id and not conn.execute('SELECT 1 FROM story_threads WHERE id=?',
                                                         (source_thread_id,)).fetchone():
                    raise ValueError('Source thread does not exist')
                subject_id = conn.execute('''INSERT INTO knowledge_subjects
                    (subject_type,topic_label,approved_detail,source_event_id,source_thread_id,created_at)
                    VALUES (?,?,?,?,?,?)''',
                    (subject_type, topic_label.strip(), approved_detail.strip(), source_event_id,
                     source_thread_id, datetime.now(timezone.utc).isoformat())).lastrowid
                conn.executemany('''INSERT INTO knowledge_subject_aliases
                    (subject_id,normalized_alias) VALUES (?,?)''',
                    [(subject_id, alias) for alias in sorted(normalized)])
        if subject_type == 'event':
            return source_event_id
        if subject_type == 'thread':
            return source_thread_id
        return subject_id

    def resolve(self, user_message: str) -> list[ResolvedTopic]:
        """Exact normalized phrase matches; ambiguous aliases resolve to nothing."""
        normalized = _normalize(user_message)
        if not normalized:
            return []
        with self.db.get_connection() as conn:
            rows = conn.execute('''SELECT s.id,s.subject_type,s.topic_label,s.approved_detail,
                s.source_event_id,s.source_thread_id,
                a.normalized_alias FROM knowledge_subject_aliases a
                JOIN knowledge_subjects s ON s.id=a.subject_id WHERE s.active=1''').fetchall()
        matches = []
        for row in rows:
            pattern = rf'(?<![a-z0-9]){re.escape(row["normalized_alias"])}(?![a-z0-9])'
            for match in re.finditer(pattern, normalized):
                matches.append((match.start(), match.end(), row))
        # If one phrase names multiple subjects, do not guess which ID it means.
        ambiguous = {(start, end) for start, end, _ in matches if
                     len({r['id'] for a, b, r in matches if a == start and b == end}) > 1}
        selected = []
        spans = []
        for start, end, row in sorted(matches, key=lambda item: (-(item[1]-item[0]), item[0])):
            if (start, end) in ambiguous or any(start < b and end > a for a, b in spans):
                continue
            if any(topic.subject_id == row['id'] for topic in selected):
                continue
            spans.append((start, end))
            actual_id = (row['source_event_id'] if row['subject_type'] == 'event' else
                         row['source_thread_id'] if row['subject_type'] == 'thread' else row['id'])
            selected.append(ResolvedTopic(row['subject_type'], actual_id, row['normalized_alias'],
                                          row['topic_label'], row['approved_detail']))
        return selected

    def prepare_replies(self, topics: Iterable[ResolvedTopic], *,
                        recipient: str = 'patrick_ramos') -> list[PrivacyReply]:
        replies = []
        for topic in topics:
            decision = self.privacy.decision(topic.subject_type, topic.subject_id,
                                             'marina', recipient)
            prefix = f'Sobre {topic.topic_label}: '
            if decision.level == 'DETAILS' and topic.approved_detail:
                replies.append(PrivacyReply(topic.subject_type, topic.subject_id,
                                            prefix + topic.approved_detail, 'details'))
            elif decision.level == 'SAFE_METADATA' and decision.safe_metadata:
                parts = []
                safe = decision.safe_metadata
                if safe.get('physical_safety') == 'okay':
                    parts.append('a pessoa está fisicamente bem')
                elif safe.get('physical_safety') == 'concern':
                    parts.append('há uma preocupação com a segurança física')
                if safe.get('severity') in ('low', 'moderate', 'high'):
                    names = {'low': 'baixa', 'moderate': 'moderada', 'high': 'alta'}
                    parts.append(f'a gravidade geral é {names[safe["severity"]]}')
                if safe.get('category'):
                    names = {'family': 'família', 'friendship': 'amizade', 'health': 'saúde',
                             'relationship': 'relacionamento', 'work': 'trabalho',
                             'safety': 'segurança', 'other': 'outro assunto'}
                    parts.append(f'é um assunto de {names[safe["category"]]}')
                if parts:
                    replies.append(PrivacyReply(topic.subject_type, topic.subject_id,
                                                prefix + '; '.join(parts) + '.', 'safe_metadata'))
                else:
                    replies.append(PrivacyReply(topic.subject_type, topic.subject_id,
                                                prefix + 'prefiro não entrar em detalhes.', None))
            else:
                replies.append(PrivacyReply(topic.subject_type, topic.subject_id,
                                            prefix + 'prefiro não falar sobre isso.', None))
        return replies
