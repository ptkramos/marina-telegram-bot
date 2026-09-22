import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from seed_academic_v36 import seed_academic
from social_world import SocialWorld, seed_social


class TestSocialWorld(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name)/'social.db')
        seed_world_bible(self.db)
        seed_academic(self.db)
        seed_social(self.db)
        self.social = SocialWorld(self.db)

    def test_canonical_graph_regions_and_seed_idempotence(self):
        before = self.social.graph()
        seed_social(self.db)
        self.assertEqual(before,self.social.graph())
        people = {p['character_key']:p for p in before}
        for key, region in [('carol_menezes','Botafogo'),('bia_andrade','Laranjeiras'),('theo_martins','Glória'),('julia_azevedo','Jardim Botânico')]:
            self.assertIn(region,people[key]['home_region'])
        self.assertEqual(people['patrick_ramos']['relationship_type'],'romantic_primary')
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("SELECT place_key FROM social_place_links WHERE character_key='carol_menezes'").fetchone()[0], 'bodytech_sao_clemente')

    def test_repeated_evidence_and_npc_promotion_do_not_create_close_friend(self):
        self.social.discover_person('new','Pessoa nova','Botafogo')
        for day in range(1,8):
            args = dict(character_key='new',occurred_at=f'2026-09-{day:02d}T10:00:00',meaningful=True,valence=1)
            self.assertTrue(self.social.record(f'e{day}',**args))
            self.assertFalse(self.social.record(f'e{day}',**args))
        self.assertEqual(self.social.bible.get_character('new')['character_type'],'recurring')
        self.assertEqual(next(p for p in self.social.graph() if p['character_key']=='new')['relationship_type'],'acquaintance')
        with self.assertRaises(ValueError):
            self.social.record('e1',character_key='new',occurred_at='2026-09-01T10:00:00',valence=-1)

    def test_favorite_requires_multiple_days_and_preference(self):
        self.social.discover_place('cafe','Café interno','Botafogo',observed_at='2026-09-01')
        for i in range(8):
            self.social.record(f'same{i}',place_key='cafe',occurred_at='2026-09-01T10:00:00',valence=1)
        self.assertEqual(self.social.place('cafe')['effective_familiarity'],'discovered')
        for day in range(2,8):
            stamp=f'2026-09-{day:02d}T10:00:00'
            self.social.record(f'visit{day}',place_key='cafe',occurred_at=stamp,valence=1)
        self.assertEqual(self.social.place('cafe')['effective_familiarity'],'habitual')
        for day in range(1,5):
            self.social.reinforce_preference(f'pref{day}','place','cafe',occurred_at=f'2026-09-{day:02d}')
        self.assertEqual(self.social.place('cafe',now=datetime(2026,9,8))['effective_familiarity'],'favorite')
        self.assertEqual(self.social.bible.get_place('cafe')['familiarity'],'discovered')

    def test_canonical_place_and_npc_cannot_be_replaced(self):
        self.social.discover_person('bia_andrade','Intrusa','Outra cidade')
        self.social.discover_place('puc_rio','Outro local','Outra região',observed_at='2026-09-01')
        self.assertIn('Beatriz',self.social.bible.get_character('bia_andrade')['display_name'])
        self.assertEqual(self.social.bible.get_place('puc_rio')['name'],'PUC-Rio')

    def test_preference_dedup_and_core_protection(self):
        args=dict(occurred_at='2026-09-01')
        self.social.reinforce_preference('p','music','jazz',**args)
        self.social.reinforce_preference('p','music','jazz',**args)
        with self.assertRaises(ValueError):
            self.social.reinforce_preference('x','music','pop',preference_type='core_like',**args)
        with self.db.get_connection() as c:
            row=c.execute("SELECT strength,times_reinforced FROM character_preferences WHERE value='jazz'").fetchone()
            self.assertEqual(tuple(row),(.4,1))
            self.assertTrue(c.execute("SELECT canon_locked FROM character_preferences WHERE value='pop'").fetchone()[0])

    def test_upgrade_preserves_existing_conversation_and_dynamic_state(self):
        from upgrade_social_v361 import upgrade
        self.db.adicionar_fato_patrick('Registro novo preservado')
        self.social.record('carol1',character_key='carol_menezes',occurred_at='2026-09-17',valence=1,meaningful=True)
        before=self.social.graph()
        upgrade(self.db.db_path)
        self.assertEqual(self.social.graph(),before)
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM fatos_patrick WHERE fato='Registro novo preservado'").fetchone()[0],1)

    def test_context_only_includes_relevant_canonical_relationship(self):
        from world_context import WorldContextBuilder
        with self.db.get_connection() as c:
            c.execute("INSERT INTO world_bootstrap VALUES ('clean_canonical_start_done','1','2026-09-17')")
        prompt=WorldContextBuilder(self.db).build(user_message='Como está a Carol?',now=datetime(2026,9,17,16))
        self.assertIn('Carolina (Carol) Menezes: close_friend',prompt)
        self.assertNotIn('Beatriz (Bia) Andrade:',prompt)

    def test_upgrade_from_nine_and_habitual_decay(self):
        from upgrade_social_v361 import upgrade
        with self.db.get_connection() as c:
            for table in ('preference_evidence','social_evidence','social_place_state','social_place_links','social_relationships'):
                c.execute(f'DROP TABLE {table}')
            c.execute('DELETE FROM schema_version WHERE version>=10')
        upgrade(self.db.db_path)
        self.assertEqual(self.db.get_schema_version(), 21)
        self.assertEqual(len(self.social.graph()),9)
        for day in range(1,5):
            self.social.record(f'v{day}',place_key='bodytech_sao_clemente',occurred_at=f'2026-01-{day:02d}',valence=1)
        self.assertEqual(self.social.place('bodytech_sao_clemente',now=datetime(2026,9,17))['effective_familiarity'],'occasional')
        self.assertEqual(self.social.bible.get_place('bodytech_sao_clemente')['familiarity'],'habitual')
