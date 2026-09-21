"""Living World knowledge provenance and disclosure decisions (v3.6.3).

This module stores who knows an opaque subject, never the subject's prose. A
share is recorded only after an explicit, confirmed disclosure. The LLM cannot
grant permissions or create knowledge by merely proposing a response.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Mapping

from db import DatabaseManager
from world_repository import WorldBibleRepository


PRIVACY_LEVELS = frozenset({
    'PRIVATE_SELF', 'PRIVATE_COUPLE', 'CONFIDENTIAL', 'CLOSE_CIRCLE', 'PUBLIC_SOCIAL',
})
SUBJECT_TYPES = frozenset({'event', 'fact', 'thread', 'relationship'})
SAFE_VALUES = {
    'severity': frozenset({'none', 'low', 'moderate', 'high', 'unknown'}),
    'physical_safety': frozenset({'okay', 'concern', 'unknown'}),
    'category': frozenset({'family', 'friendship', 'health', 'relationship', 'work', 'safety', 'other'}),
}
DETAIL_RANK = {'safe_metadata': 1, 'details': 2}
EVIDENCE_KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _timestamp(value: str) -> str:
    try:
        datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Expected an ISO timestamp') from exc
    return value


def _permissions(detail='details') -> dict:
    return {'knowledge_detail': detail, 'details_to': [], 'safe_metadata_to': [],
            'spontaneous_to': []}


def _safe_metadata(value: Mapping | None) -> dict:
    value = dict(value or {})
    if any(key not in SAFE_VALUES or not isinstance(item, str)
           or item not in SAFE_VALUES[key] for key, item in value.items()):
        raise ValueError('Safe metadata must use reviewed enum fields and values')
    return value


@dataclass(frozen=True)
class DisclosureDecision:
    level: str  # UNKNOWN, WITHHOLD, SAFE_METADATA, DETAILS
    recipient_already_knows: bool
    safe_metadata: dict
    can_spontaneously_share: bool


class KnowledgePrivacy:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.bible = WorldBibleRepository(db)

    def _character(self, key: str) -> None:
        if not key or not self.bible.get_character(key):
            raise ValueError(f'Unknown canonical character: {key}')

    @staticmethod
    def _subject(subject_type: str, subject_id: int) -> None:
        if subject_type not in SUBJECT_TYPES or isinstance(subject_id, bool) or not isinstance(subject_id, int) or subject_id <= 0:
            raise ValueError('Expected a valid opaque subject type and positive id')

    def _item(self, subject_type: str, subject_id: int, holder: str):
        with self.db.get_connection() as conn:
            row = conn.execute('''SELECT * FROM knowledge_items
                WHERE subject_type=? AND subject_id=? AND holder_character_key=? AND revoked_at IS NULL''',
                (subject_type, subject_id, holder)).fetchone()
            return dict(row) if row else None

    def observe(self, subject_type: str, subject_id: int, holder: str, *,
                privacy_level: str, safe_metadata: Mapping | None = None,
                learned_at: str | None = None) -> dict:
        """Record an explicit direct observation; no NPC knowledge is inferred."""
        self._subject(subject_type, subject_id)
        self._character(holder)
        if privacy_level not in PRIVACY_LEVELS:
            raise ValueError('Unknown privacy level')
        safe = _safe_metadata(safe_metadata)
        learned_at = _timestamp(learned_at or _now())
        existing = self._item(subject_type, subject_id, holder)
        if existing:
            if (existing['privacy_level'] == privacy_level
                    and json.loads(existing['source_chain_json']) == [holder]
                    and json.loads(existing['safe_metadata_json'] or '{}') == safe):
                return existing
            raise ValueError('Knowledge already exists with different provenance or policy')
        with self.db.get_connection() as conn:
            revoked = conn.execute('''SELECT id FROM knowledge_items WHERE subject_type=?
                AND subject_id=? AND holder_character_key=? AND revoked_at IS NOT NULL''',
                (subject_type, subject_id, holder)).fetchone()
            if revoked:
                conn.execute('''UPDATE knowledge_items SET source_character_key=NULL,
                    source_chain_json=?,privacy_level=?,permission_json=?,safe_metadata_json=?,
                    learned_at=?,revoked_at=NULL WHERE id=?''',
                    (_json([holder]), privacy_level, _json(_permissions()), _json(safe),
                     learned_at, revoked['id']))
            else:
                conn.execute('''INSERT INTO knowledge_items
                    (subject_type,subject_id,holder_character_key,source_character_key,
                     source_chain_json,privacy_level,permission_json,safe_metadata_json,learned_at)
                    VALUES (?,?,?,?,?,?,?,?,?)''',
                    (subject_type, subject_id, holder, None, _json([holder]), privacy_level,
                     _json(_permissions()), _json(safe), learned_at))
        return self._item(subject_type, subject_id, holder)

    def known_by(self, subject_type: str, subject_id: int, holder: str) -> bool:
        self._subject(subject_type, subject_id)
        self._character(holder)
        return self._item(subject_type, subject_id, holder) is not None

    def source_chain(self, subject_type: str, subject_id: int, holder: str) -> tuple[str, ...]:
        self._subject(subject_type, subject_id)
        self._character(holder)
        item = self._item(subject_type, subject_id, holder)
        return tuple(json.loads(item['source_chain_json'])) if item else ()

    def grant(self, subject_type: str, subject_id: int, holder: str, recipient: str,
              *, authorized_by: str, detail_level: str = 'details',
              spontaneous: bool = False) -> dict:
        """Only the chain's original observer can authorize onward disclosure."""
        self._subject(subject_type, subject_id)
        self._character(holder)
        self._character(recipient)
        self._character(authorized_by)
        if holder == recipient or detail_level not in DETAIL_RANK:
            raise ValueError('Invalid recipient or detail level')
        item = self._item(subject_type, subject_id, holder)
        if not item:
            raise ValueError('Holder does not know this subject')
        chain = json.loads(item['source_chain_json'])
        if authorized_by != chain[0]:
            raise PermissionError('Only the original source may grant disclosure')
        if item['privacy_level'] == 'PRIVATE_SELF':
            raise PermissionError('PRIVATE_SELF must be reclassified before sharing')
        if item['privacy_level'] == 'PRIVATE_COUPLE' and recipient not in ('marina', 'patrick_ramos'):
            raise PermissionError('PRIVATE_COUPLE cannot be shared outside the couple')
        permissions = json.loads(item['permission_json'])
        if detail_level == 'details' and permissions['knowledge_detail'] != 'details':
            raise PermissionError('Holder only received safe metadata')
        if detail_level == 'safe_metadata' and not json.loads(item['safe_metadata_json'] or '{}'):
            raise ValueError('No reviewed safe metadata exists')
        field = 'details_to' if detail_level == 'details' else 'safe_metadata_to'
        permissions[field] = sorted(set(permissions[field]) | {recipient})
        if spontaneous:
            permissions['spontaneous_to'] = sorted(set(permissions['spontaneous_to']) | {recipient})
        with self.db.get_connection() as conn:
            conn.execute('UPDATE knowledge_items SET permission_json=? WHERE id=?',
                         (_json(permissions), item['id']))
        return self._item(subject_type, subject_id, holder)

    def set_privacy_level(self, subject_type: str, subject_id: int, holder: str,
                          *, privacy_level: str, authorized_by: str) -> dict:
        """An explicit source decision can relax or tighten future sharing."""
        self._subject(subject_type, subject_id)
        self._character(holder)
        self._character(authorized_by)
        if privacy_level not in PRIVACY_LEVELS:
            raise ValueError('Unknown privacy level')
        item = self._item(subject_type, subject_id, holder)
        if not item or authorized_by != json.loads(item['source_chain_json'])[0]:
            raise PermissionError('Only the original source may change privacy')
        with self.db.get_connection() as conn:
            rows = conn.execute('''SELECT id,permission_json FROM knowledge_items
                WHERE subject_type=? AND subject_id=?
                AND json_extract(source_chain_json,'$[0]')=?''',
                (subject_type, subject_id, authorized_by)).fetchall()
            for row in rows:
                detail = json.loads(row['permission_json'])['knowledge_detail']
                conn.execute('''UPDATE knowledge_items SET privacy_level=?,permission_json=?
                    WHERE id=?''', (privacy_level, _json(_permissions(detail)), row['id']))
        return self._item(subject_type, subject_id, holder)

    def revoke_grant(self, subject_type: str, subject_id: int, holder: str,
                     recipient: str, *, authorized_by: str) -> dict:
        """Stop future disclosure; previously transmitted knowledge remains recorded."""
        self._subject(subject_type, subject_id)
        self._character(holder)
        self._character(recipient)
        self._character(authorized_by)
        item = self._item(subject_type, subject_id, holder)
        if not item or authorized_by != json.loads(item['source_chain_json'])[0]:
            raise PermissionError('Only the original source may revoke disclosure')
        permissions = json.loads(item['permission_json'])
        for field in ('details_to', 'safe_metadata_to', 'spontaneous_to'):
            permissions[field] = [value for value in permissions[field] if value != recipient]
        with self.db.get_connection() as conn:
            conn.execute('UPDATE knowledge_items SET permission_json=? WHERE id=?',
                         (_json(permissions), item['id']))
        return self._item(subject_type, subject_id, holder)

    def decision(self, subject_type: str, subject_id: int, holder: str,
                 recipient: str) -> DisclosureDecision:
        self._subject(subject_type, subject_id)
        self._character(holder)
        self._character(recipient)
        item = self._item(subject_type, subject_id, holder)
        recipient_item = self._item(subject_type, subject_id, recipient)
        recipient_detail = (json.loads(recipient_item['permission_json'])['knowledge_detail']
                            if recipient_item else None)
        already_knows = recipient_item is not None
        if not item:
            return DisclosureDecision('UNKNOWN', already_knows, {}, False)
        permissions = json.loads(item['permission_json'])
        safe = json.loads(item['safe_metadata_json'] or '{}')
        if item['privacy_level'] == 'PRIVATE_SELF':
            return DisclosureDecision('WITHHOLD', already_knows, {}, False)
        if item['privacy_level'] == 'PRIVATE_COUPLE' and recipient not in ('marina', 'patrick_ramos'):
            return DisclosureDecision('WITHHOLD', already_knows, {}, False)
        details_allowed = (permissions['knowledge_detail'] == 'details'
                           and (item['privacy_level'] == 'PUBLIC_SOCIAL'
                                or recipient in permissions['details_to']))
        if details_allowed:
            return DisclosureDecision('DETAILS', recipient_detail == 'details', {},
                                      item['privacy_level'] == 'PUBLIC_SOCIAL'
                                      or recipient in permissions['spontaneous_to'])
        if safe and recipient in permissions['safe_metadata_to']:
            return DisclosureDecision('SAFE_METADATA', already_knows, safe,
                                      recipient in permissions['spontaneous_to'])
        return DisclosureDecision('WITHHOLD', already_knows, {}, False)

    def record_confirmed_share(self, subject_type: str, subject_id: int, holder: str,
                               recipient: str, *, detail_level: str,
                               evidence_key: str, shared_at: str | None = None) -> dict:
        """Persist a real disclosure, never a candidate LLM reply."""
        if not isinstance(evidence_key, str) or not EVIDENCE_KEY.fullmatch(evidence_key) or detail_level not in DETAIL_RANK:
            raise ValueError('A confirmed evidence key and detail level are required')
        self._subject(subject_type, subject_id)
        self._character(holder)
        self._character(recipient)
        with self.db.transaction():
            with self.db.get_connection() as conn:
                replay = conn.execute('''SELECT * FROM knowledge_shares
                    WHERE json_extract(metadata_json,'$.evidence_key')=? LIMIT 1''',
                    (evidence_key,)).fetchone()
            if replay:
                if (replay['subject_type'], replay['subject_id'], replay['from_character_key'],
                    replay['to_character_key'], replay['detail_level']) != (
                        subject_type, subject_id, holder, recipient, detail_level):
                    raise ValueError('Conflicting knowledge share replay')
                return dict(replay)
            decision = self.decision(subject_type, subject_id, holder, recipient)
            if detail_level == 'details' and decision.level != 'DETAILS':
                raise PermissionError('Disclosure of details is not permitted')
            if detail_level == 'safe_metadata' and decision.level not in ('SAFE_METADATA', 'DETAILS'):
                raise PermissionError('Safe metadata disclosure is not permitted')
            sender = self._item(subject_type, subject_id, holder)
            if detail_level == 'safe_metadata' and not json.loads(sender['safe_metadata_json'] or '{}'):
                raise ValueError('No reviewed safe metadata exists to share')
            existing = self._item(subject_type, subject_id, recipient)
            chain = json.loads(sender['source_chain_json'])
            if recipient in chain:
                raise ValueError('Source chain cannot loop back to a prior holder')
            shared_at = _timestamp(shared_at or _now())
            with self.db.get_connection() as conn:
                if not existing:
                    revoked = conn.execute('''SELECT id FROM knowledge_items WHERE subject_type=?
                        AND subject_id=? AND holder_character_key=? AND revoked_at IS NOT NULL''',
                        (subject_type, subject_id, recipient)).fetchone()
                    if revoked:
                        conn.execute('''UPDATE knowledge_items SET source_character_key=?,
                            source_chain_json=?,privacy_level=?,permission_json=?,safe_metadata_json=?,
                            learned_at=?,revoked_at=NULL WHERE id=?''',
                            (holder, _json([*chain, recipient]), sender['privacy_level'],
                             _json(_permissions(detail_level)), sender['safe_metadata_json'],
                             shared_at, revoked['id']))
                    else:
                        conn.execute('''INSERT INTO knowledge_items
                            (subject_type,subject_id,holder_character_key,source_character_key,
                             source_chain_json,privacy_level,permission_json,safe_metadata_json,learned_at)
                            VALUES (?,?,?,?,?,?,?,?,?)''',
                            (subject_type, subject_id, recipient, holder, _json([*chain, recipient]),
                             sender['privacy_level'], _json(_permissions(detail_level)),
                             sender['safe_metadata_json'], shared_at))
                else:
                    current = json.loads(existing['permission_json'])
                    if DETAIL_RANK[detail_level] > DETAIL_RANK[current['knowledge_detail']]:
                        current['knowledge_detail'] = detail_level
                        conn.execute('''UPDATE knowledge_items SET permission_json=?,
                            source_character_key=?,source_chain_json=? WHERE id=?''',
                            (_json(current), holder, _json([*chain, recipient]), existing['id']))
                cursor = conn.execute('''INSERT INTO knowledge_shares
                    (subject_type,subject_id,from_character_key,to_character_key,
                     shared_at,detail_level,explicit_permission,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (subject_type, subject_id, holder, recipient, shared_at, detail_level,
                     int(sender['privacy_level'] != 'PUBLIC_SOCIAL'),
                     _json({'evidence_key': evidence_key})))
                return dict(conn.execute('SELECT * FROM knowledge_shares WHERE id=?',
                                         (cursor.lastrowid,)).fetchone())

    def revoke(self, subject_type: str, subject_id: int, holder: str,
               *, revoked_at: str | None = None) -> None:
        self._subject(subject_type, subject_id)
        self._character(holder)
        item = self._item(subject_type, subject_id, holder)
        if item:
            with self.db.get_connection() as conn:
                conn.execute('UPDATE knowledge_items SET revoked_at=? WHERE id=?',
                             (_timestamp(revoked_at or _now()), item['id']))

    def prompt_constraint(self, subject_type: str, subject_id: int,
                          *, recipient: str = 'patrick_ramos') -> str:
        """Return policy only; never include source wording, identity chain or secret text."""
        # Auditoria #6: resto da Auditoria #2 — ia em inglês para o prompt.
        decision = self.decision(subject_type, subject_id, 'marina', recipient)
        prefix = '[POLÍTICA DE CONHECIMENTO VERIFICADO] '
        if decision.level == 'UNKNOWN':
            return prefix + 'Você não tem conhecimento verificado sobre este assunto. Não invente resposta.'
        if decision.level == 'WITHHOLD':
            return prefix + ('Não revele, não confirme e não negue detalhes privados que ele esteja '
                             'supondo. Não revele quem te contou nem dê a entender que existe um segredo.')
        if decision.level == 'SAFE_METADATA':
            fields = ', '.join(f'{key}={value}' for key, value in sorted(decision.safe_metadata.items()))
            return prefix + (f'Só estes campos genéricos podem ser mencionados: {fields}. Não confirme '
                             'nem negue detalhes supostos e não revele quem te contou.')
        known = 'ele já sabe' if decision.recipient_already_knows else 'ele ainda não sabe'
        return prefix + f'Os detalhes podem ser conversados se vierem ao caso; {known}. Não apresente como novidade o que ele já sabe.'
