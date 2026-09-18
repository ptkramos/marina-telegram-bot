"""Social continuity from explicit evidence; no event generation or disclosure of secrets."""
import logging
import math
from datetime import datetime, timedelta

from world_repository import WorldBibleRepository, CanonConflictError

logger = logging.getLogger(__name__)


RELATIONS = {
    'bia_andrade': 'best_friend', 'carol_menezes': 'close_friend',
    'theo_martins': 'close_friend', 'julia_azevedo': 'close_friend',
    'henrique_salles': 'family_primary', 'patrick_ramos': 'romantic_primary',
    'livia_vasconcelos': 'professional_trusted', 'helena_prado': 'academic_professor',
    'celia_ribeiro': 'friendly_neighbor',
}
LINKS = [('carol_menezes','bodytech_sao_clemente','academia'),
         ('theo_martins','puc_rio','faculdade'), ('julia_azevedo','puc_rio','faculdade'),
         ('helena_prado','puc_rio','professora'), ('livia_vasconcelos','boutique_agency','trabalho')]


def seed_social(db):
    with db.transaction():
        with db.get_connection() as c:
            for key, kind in RELATIONS.items():
                old = c.execute('SELECT relationship_type FROM social_relationships WHERE character_key=?', (key,)).fetchone()
                if old and old[0] != kind:
                    raise CanonConflictError(f'Relação canônica conflitante: {key}')
                c.execute('INSERT OR IGNORE INTO social_relationships(character_key,relationship_type,canon_locked,closeness,trust) VALUES (?,?,1,.75,.75)', (key,kind))
            c.executemany('INSERT OR IGNORE INTO social_place_links VALUES (?,?,?)', LINKS)


class SocialWorld:
    def __init__(self, db):
        self.db = db
        self.bible = WorldBibleRepository(db)

    def discover_person(self, key, name, region):
        if self.bible.get_character(key):
            return self.bible.get_character(key)
        return self.bible.upsert_character(key, dict(display_name=name, home_region=region,
                                                    character_type='ephemeral', canon_locked=0))

    def discover_place(self, key, name, region, *, source_url=None, observed_at):
        stamp = datetime.fromisoformat(observed_at).isoformat()
        if self.bible.get_place(key):
            return self.bible.get_place(key)
        return self.bible.upsert_place(key, dict(name=name, region=region, place_type='other',
            truth_type='real_world' if source_url else 'simulated', familiarity='discovered',
            usage_rules_json={'source_url': source_url, 'observed_at': stamp,
                              'internal_fiction': source_url is None}, canon_locked=0))

    def graph(self):
        with self.db.get_connection() as c:
            return [dict(r) for r in c.execute('''SELECT r.*, w.display_name, w.home_region
                FROM social_relationships r JOIN world_characters w ON w.canonical_key=r.character_key
                WHERE w.active=1 ORDER BY r.character_key''')]

    def record(self, evidence_key, *, occurred_at, character_key=None, place_key=None,
               valence=0.0, meaningful=False):
        """Caller supplies an actual occurrence id; retries never count twice."""
        if not evidence_key or not math.isfinite(valence) or not -1 <= valence <= 1:
            raise ValueError('Evidência e valência válidas são obrigatórias')
        stamp = datetime.fromisoformat(occurred_at).isoformat()
        payload = (character_key, place_key, stamp, valence, int(meaningful))
        with self.db.transaction():
            with self.db.get_connection() as c:
                old = c.execute('SELECT character_key,place_key,occurred_at,valence,meaningful FROM social_evidence WHERE evidence_key=?', (evidence_key,)).fetchone()
                if old:
                    if tuple(old) != payload:
                        raise ValueError('Evidência reutilizada com conteúdo diferente')
                    return False
                c.execute('INSERT INTO social_evidence VALUES (?,?,?,?,?,?)', (evidence_key,*payload))
                if character_key:
                    c.execute("INSERT OR IGNORE INTO social_relationships(character_key,relationship_type) VALUES (?,'acquaintance')", (character_key,))
                    rows = c.execute('SELECT * FROM social_evidence WHERE character_key=? ORDER BY occurred_at', (character_key,)).fetchall()
                    last = datetime.fromisoformat(rows[-1]['occurred_at'])
                    recent = [r for r in rows if datetime.fromisoformat(r['occurred_at']) >= last-timedelta(days=30)]
                    positive = sum(r['valence'] > 0 and r['meaningful'] for r in recent)
                    positive_days = len({r['occurred_at'][:10] for r in recent if r['valence'] > 0 and r['meaningful']})
                    locked = c.execute('SELECT canon_locked FROM social_relationships WHERE character_key=?', (character_key,)).fetchone()[0]
                    base = .75 if locked else 0
                    c.execute('''UPDATE social_relationships SET contact_frequency=?,
                        recent_positive_interactions=?,recent_tension=?,last_interaction_at=?,
                        closeness=?,trust=? WHERE character_key=?''',
                        (len(recent),positive,min(1,sum(max(0,-r['valence']) for r in recent)/10),
                         last.isoformat(),min(1,base+positive_days*.02),min(1,base+positive_days*.02),character_key))
                    person = self.bible.get_character(character_key)
                    days = {r['occurred_at'][:10] for r in rows if r['meaningful'] and r['valence'] > 0}
                    # No automatic route to close_npc; identity and relationship type remain intact.
                    if not person['canon_locked']:
                        level = person['character_type']
                        target = 'recurring' if len(days) >= 6 else 'secondary' if len(days) >= 3 else level
                        if level == 'ephemeral' and target in ('secondary','recurring') or level == 'secondary' and target == 'recurring':
                            c.execute('UPDATE world_characters SET character_type=? WHERE canonical_key=?', (target,character_key))
                if place_key:
                    self._refresh_place(c, place_key, datetime.fromisoformat(stamp))
        return True

    def _refresh_place(self, c, key, now):
        place = self.bible.get_place(key)
        rows = c.execute('SELECT occurred_at,valence FROM social_evidence WHERE place_key=? ORDER BY occurred_at', (key,)).fetchall()
        days = {r['occurred_at'][:10] for r in rows}
        positive_days = {r['occurred_at'][:10] for r in rows if r['valence'] > 0}
        preferred = c.execute("SELECT 1 FROM character_preferences WHERE character_key='marina' AND category='place' AND value=? AND active=1 AND strength>=0.6", (key,)).fetchone()
        level = place['familiarity']
        if len(days) >= 2 and level == 'discovered':
            level = 'known'
        if len(days) >= 4 and len(positive_days) >= 3:
            level = 'habitual'
        if len(positive_days) >= 6 and preferred:
            level = 'favorite'
        if rows and now - datetime.fromisoformat(rows[-1]['occurred_at']) > timedelta(days=90) and level == 'habitual':
            level = 'occasional'
        c.execute('INSERT INTO social_place_state VALUES (?,?) ON CONFLICT(place_key) DO UPDATE SET familiarity=excluded.familiarity', (key,level))

    def place(self, key, *, now=None):
        result = self.bible.get_place(key)
        if result is None:
            return None
        with self.db.get_connection() as c:
            if now is not None:
                self._refresh_place(c,key,now)
            state = c.execute('SELECT familiarity FROM social_place_state WHERE place_key=?', (key,)).fetchone()
            result['effective_familiarity'] = state[0] if state else result['familiarity']
        return result

    def reinforce_preference(self, evidence_key, category, value, *, occurred_at,
                             preference_type='discovered_preference'):
        if preference_type not in ('current_interest','discovered_preference') or not evidence_key:
            raise ValueError('Somente preferências dinâmicas podem ser aprendidas')
        stamp = datetime.fromisoformat(occurred_at).isoformat()
        with self.db.transaction():
            pref = self.bible.upsert_preference('marina',category,value,preference_type,
                                              strength=.4,confidence=.5,canon_locked=False)
            with self.db.get_connection() as c:
                old = c.execute('SELECT preference_id,occurred_at FROM preference_evidence WHERE evidence_key=?', (evidence_key,)).fetchone()
                if old:
                    if tuple(old) != (pref['id'],stamp):
                        raise ValueError('Evidência reutilizada com conteúdo diferente')
                    return
                c.execute('INSERT INTO preference_evidence VALUES (?,?,?)', (evidence_key,pref['id'],stamp))
                days = c.execute('SELECT COUNT(DISTINCT substr(occurred_at,1,10)),MIN(occurred_at),MAX(occurred_at) FROM preference_evidence WHERE preference_id=?', (pref['id'],)).fetchone()
                c.execute('''UPDATE character_preferences SET strength=?,confidence=?,times_reinforced=?,
                    first_seen_at=?,last_seen_at=?,active=1 WHERE id=? AND canon_locked=0''',
                    (min(.9,.3+days[0]*.1),min(.95,.4+days[0]*.1),days[0],days[1],days[2],pref['id']))
                if preference_type == 'current_interest':
                    logger.info('PREFERENCE_REINFORCED preference_id=%s value=%s', pref['id'], value)
