import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from db import DatabaseManager
from memory_consolidator import MemoryConsolidator, MemoryConsolidationError
from memory_retriever import MemoryRetriever

class AuditRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(Path(self.tmp.name) / 'audit.db')
        self.llm = MagicMock()
        self.c = MemoryConsolidator(db=self.db, llm_client=self.llm)
        self.r = MemoryRetriever(db=self.db)

    def apply_llm(self, payload, candidates):
        self.llm.chat.completions.create.return_value.choices[0].message.content = json.dumps(payload)
        result = self.c.consolidate_dialogue([{'role':'user','content':'Uma conversa de teste'}], existing_facts=candidates)
        return self.c.apply_consolidation(result)

    def test_same_outside_nonempty_allowlist(self):
        allowed = self.db.adicionar_fato_patrick('Fato candidato')
        other = self.db.adicionar_fato_patrick('Fato protegido', confidence=0.5)
        self.apply_llm({'facts_to_create':[{'decision':'same','fato':'Texto sem correspondencia','existing_fact_id':other}]}, [self.db.get_fato_detalhado(allowed)])
        self.assertEqual(self.db.get_fato_detalhado(other)['confirmation_count'], 0)

    def test_empty_key_allowlist(self):
        allowed = self.db.adicionar_fato_patrick('Fato legado sem chave')
        other = self.db.adicionar_fato_patrick('Fato protegido', canonical_key='protected')
        self.apply_llm({'keys_to_deactivate':['protected']}, [self.db.get_fato_detalhado(allowed)])
        self.assertIsNotNone(self.db.get_fato_detalhado(other))

    def test_empty_id_allowlist(self):
        other = self.db.adicionar_fato_patrick('Fato protegido')
        self.apply_llm({'facts_to_deactivate':[{'existing_fact_id':other}]}, [])
        self.assertIsNotNone(self.db.get_fato_detalhado(other))

    def test_deactivate_and_update_same_target(self):
        old = self.db.adicionar_fato_patrick('Patrick joga FFXIV', canonical_key='game')
        self.apply_llm({'facts_to_deactivate':[{'existing_fact_id':old}], 'facts_to_create':[{'decision':'update','existing_fact_id':old,'fato':'Patrick joga GW2','canonical_key':'game'}]}, [self.db.get_fato_detalhado(old)])
        self.assertEqual(len(self.db.get_fatos_por_chave('game', active_only=True)), 1)

    def test_fts_preserves_migrated_fact_age(self):
        fid = self.db.adicionar_fato_patrick('Patrick joga xadrez', volatility='volatile', confidence=1.0)
        old = (datetime.now()-timedelta(days=180)).isoformat()
        with self.db.get_connection() as conn:
            conn.execute('UPDATE fatos_patrick SET created_at=?, updated_at=NULL, last_confirmed_at=NULL WHERE id=?',(old, fid))
        fallback = next(f for f in self.r.retrieve_context('', max_facts=10, record_access=False)['fatos_detalhados'] if f['id'] == fid)
        matched = next(f for f in self.r.retrieve_context('xadrez', max_facts=10, record_access=False)['fatos_detalhados'] if f['id'] == fid)
        self.assertEqual(matched['effective_confidence'], fallback['effective_confidence'])

    def test_intermediate_confidence_is_qualified(self):
        self.db.adicionar_fato_patrick('Patrick joga xadrez', confidence=0.65)
        value = self.r.retrieve_context('xadrez', record_access=False)['fatos'][0]
        self.assertNotEqual(value, 'Patrick joga xadrez')

    def test_expiration_does_not_raise_confidence(self):
        fact = {'confidence':0.1, 'volatility':'medium', 'created_at':(datetime.now()-timedelta(days=200)).isoformat()}
        self.assertLessEqual(self.r.compute_effective_confidence(fact), fact['confidence'])

    def test_malformed_fact_does_not_commit_revocation(self):
        fid = self.db.adicionar_fato_patrick('Fato protegido')
        with self.assertRaises(MemoryConsolidationError):
            self.apply_llm({'facts_to_deactivate':[{'existing_fact_id':fid}], 'facts_to_create':[{'fato':123,'decision':'new'}]}, [self.db.get_fato_detalhado(fid)])
        self.assertIsNotNone(self.db.get_fato_detalhado(fid))

    def test_unique_insert_failure_preserves_old(self):
        old = self.db.adicionar_fato_patrick('Antigo', canonical_key='game')
        self.db.adicionar_fato_patrick('Texto ja existente')
        result = self.db.substituir_fato_atomicamente(old, {'fato':'Texto ja existente'})
        self.assertIsNone(result)
        self.assertIsNotNone(self.db.get_fato_detalhado(old))

    def test_all_mutations_reject_empty_or_foreign_candidates(self):
        fid = self.db.adicionar_fato_patrick('Protected', confidence=0.4)
        for candidates in ([], [self.db.get_fato_detalhado(1)]):
            for decision in ('same', 'update', 'contradiction'):
                with self.subTest(decision=decision, candidates=bool(candidates)):
                    before = self.db.get_fatos_patrick_detalhados(active_only=False)
                    self.apply_llm({'facts_to_create':[{'decision':decision, 'existing_fact_id':fid, 'fato':'Replacement'}]}, candidates)
                    self.assertEqual(before, self.db.get_fatos_patrick_detalhados(active_only=False))

    def test_key_revocation_only_touches_presented_ids(self):
        first = self.db.adicionar_fato_patrick('Presented', canonical_key='shared')
        other = self.db.adicionar_fato_patrick('Not presented', canonical_key='shared')
        self.apply_llm({'keys_to_deactivate':['shared']}, [self.db.get_fato_detalhado(first)])
        self.assertIsNone(self.db.get_fato_detalhado(first))
        self.assertIsNotNone(self.db.get_fato_detalhado(other))

    def test_key_revocation_and_replacement_are_reconciled(self):
        for decision in ('update', 'contradiction'):
            with self.subTest(decision=decision):
                key = 'game_' + decision
                fid = self.db.adicionar_fato_patrick('Old ' + decision, canonical_key=key)
                self.apply_llm({'keys_to_deactivate':[key], 'facts_to_create':[{'decision':decision, 'existing_fact_id':fid, 'canonical_key':key, 'fato':'New ' + decision}]}, [self.db.get_fato_detalhado(fid)])
                active = self.db.get_fatos_por_chave(key)
                self.assertEqual(len(active), 1)
                self.assertEqual(active[0]['supersedes_id'], fid)

    def test_conflicting_confirmation_or_ignore_rejects_whole_batch(self):
        fid = self.db.adicionar_fato_patrick('Protected')
        for decision in ('same', 'ignore'):
            with self.subTest(decision=decision):
                before = self.db.get_fato_detalhado(fid)
                with self.assertRaises(MemoryConsolidationError):
                    self.apply_llm({'facts_to_deactivate':[{'existing_fact_id':fid}], 'facts_to_create':[{'decision':decision, 'existing_fact_id':fid, 'fato':'Protected'}]}, [before])
                self.assertEqual(self.db.get_fato_detalhado(fid), before)

    def test_late_sql_failure_rolls_back_confirmation_and_new_fact(self):
        fid = self.db.adicionar_fato_patrick('Protected', confidence=0.4)
        before = self.db.get_fatos_patrick_detalhados(active_only=False)
        with self.db.get_connection() as conn:
            conn.execute("CREATE TRIGGER fail_summary BEFORE INSERT ON resumos_conversa BEGIN SELECT RAISE(ABORT, 'audit failure'); END")
        payload = {'facts_to_create':[{'decision':'same', 'existing_fact_id':fid, 'fato':'Protected'}, {'decision':'new', 'fato':'New fact'}], 'topic_summary':'Resumo de teste que falha'}
        for attempt in range(2):
            with self.subTest(attempt=attempt), self.assertRaises(MemoryConsolidationError) as error:
                self.apply_llm(payload, [self.db.get_fato_detalhado(fid)])
            self.assertIn('audit failure', str(error.exception.__cause__))
            self.assertEqual(before, self.db.get_fatos_patrick_detalhados(active_only=False))
            self.assertEqual(self.db.buscar_fatos_fts('New'), [])

    def test_failed_replacement_rolls_back_prior_confirmation(self):
        first = self.db.adicionar_fato_patrick('First', confidence=0.4)
        old = self.db.adicionar_fato_patrick('Old')
        self.db.adicionar_fato_patrick('Collision')
        before = self.db.get_fatos_patrick_detalhados(active_only=False)
        payload = {'facts_to_create':[{'decision':'same', 'existing_fact_id':first, 'fato':'First'}, {'decision':'update', 'existing_fact_id':old, 'fato':'Collision'}]}
        with self.assertRaises(MemoryConsolidationError):
            self.apply_llm(payload, [self.db.get_fato_detalhado(i) for i in (first, old)])
        self.assertEqual(before, self.db.get_fatos_patrick_detalhados(active_only=False))

    def test_payload_types_and_nonfinite_values_rejected_before_writes(self):
        fid = self.db.adicionar_fato_patrick('Protected')
        invalid = [
            {'facts_to_create':None}, {'facts_to_create':[42]},
            {'important_moments':[{'momento':[]}]}, {'topic_summary':{}},
            *({'facts_to_create':[{'fato':'New', 'decision':d}]} for d in ('unknown', None)),
            *({'facts_to_create':[{'fato':'New', 'confidence':v}]} for v in (float('nan'), float('inf'), True)),
            *({'facts_to_create':[{'fato':'New', 'existing_fact_id':v}]} for v in (True, 1.5, '5', -1, [], {})),
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(MemoryConsolidationError):
                    self.apply_llm(dict(value, facts_to_deactivate=[{'existing_fact_id':fid}]), [self.db.get_fato_detalhado(fid)])
                self.assertIsNotNone(self.db.get_fato_detalhado(fid))

    def test_core_and_fts_return_age_and_source(self):
        fid = self.db.adicionar_fato_patrick('Chess preference', memory_tier='core', source_conversation_id=123)
        for fact in (self.db.buscar_fatos_fts('Chess')[0], self.db.get_core_memories()[0]):
            self.assertEqual(fact['id'], fid)
            self.assertIn('created_at', fact)
            self.assertIn('updated_at', fact)
            self.assertEqual(fact['source_conversation_id'], 123)

    def test_context_builder_confidence_boundaries_and_access(self):
        from context_builder import ContextBuilder
        # Only memory persistence is injected; the real prompt builder is exercised.
        manager = MagicMock(wraps=__import__('memory').memory_manager)
        manager.db = self.db
        builder = ContextBuilder(memory_mgr=manager, retriever=self.r)
        fid = self.db.adicionar_fato_patrick('Chess preference')
        for value, expected in ((0.49, 'reconfirmar naturalmente'), (0.50, 'tratar com cautela'), (0.79, 'tratar com cautela'), (0.80, None)):
            with self.subTest(value=value):
                with self.db.get_connection() as conn:
                    conn.execute('UPDATE fatos_patrick SET confidence=? WHERE id=?', (value, fid))
                prompt = builder.build_system_prompt(user_message='Chess')
                line = next(line for line in prompt.splitlines() if 'Chess preference' in line)
                if expected:
                    self.assertIn(expected, line)
                else:
                    self.assertEqual(line, '- Chess preference')
        self.assertEqual(self.db.get_fato_detalhado(fid)['access_count'], 4)

    def test_consolidator_candidate_lookup_does_not_track_access(self):
        fid = self.db.adicionar_fato_patrick('Chess preference')
        self.llm.chat.completions.create.return_value.choices[0].message.content = '{}'
        result = self.c.consolidate_dialogue([{'role':'user', 'content':'Chess'}])
        self.assertIn(fid, result['_candidate_fact_ids'])
        self.assertEqual(self.db.get_fato_detalhado(fid)['access_count'], 0)

    def test_debug_command_preserves_access_and_source(self):
        import asyncio
        import bot
        fid = self.db.adicionar_fato_patrick('Chess preference', source_conversation_id=123)
        update, context = MagicMock(), MagicMock()
        context.args = ['Chess']
        context.bot.delete_message = AsyncMock()
        context.bot.send_message = AsyncMock()
        with patch.object(bot, 'is_authorized', return_value=True), patch.object(bot, 'memory_retriever', self.r), patch.object(bot, 'delete_after_delay', new_callable=AsyncMock):
            asyncio.run(bot.memorias_command(update, context))
        self.assertEqual(self.db.get_fato_detalhado(fid)['access_count'], 0)
        self.assertIn('Src: `123`', context.bot.send_message.call_args.kwargs['text'])

    def test_weights_normalize_and_reject_invalid_values(self):
        from config import Settings
        config = Settings()
        config.MEMORY_WEIGHT_LEXICAL = 4.0
        self.assertAlmostEqual(sum(config.memory_weights().values()), 1.0)
        for value in (-1.0, float('nan'), float('inf')):
            config.MEMORY_WEIGHT_LEXICAL = value
            with self.assertRaises(ValueError):
                config.memory_weights()
        for name in ('LEXICAL','IMPORTANCE','CONFIDENCE','FRESHNESS','CORE','ACCESS'):
            setattr(config, 'MEMORY_WEIGHT_' + name, 0.0)
        with self.assertRaises(ValueError):
            config.memory_weights()

    def test_relative_lexical_rank_changes_score(self):
        first = self.db.adicionar_fato_patrick('Chess first')
        second = self.db.adicionar_fato_patrick('Chess second')
        rows = [self.db.get_fato_detalhado(i) for i in (first, second)]
        with patch.object(self.db, 'buscar_fatos_fts', return_value=rows):
            details = self.r.retrieve_context('Chess', max_facts=10, record_access=False)['fatos_detalhados']
        scores = {f['id']:f['hybrid_score'] for f in details}
        self.assertGreater(scores[first], scores[second])

    def test_concurrent_replacements_leave_one_active_version(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        fid = self.db.adicionar_fato_patrick('Old', canonical_key='game')
        ready = Barrier(2)
        def replace(text):
            ready.wait(timeout=5)
            return self.db.substituir_fato_atomicamente(fid, {'fato':text})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(replace, ('First replacement', 'Second replacement')))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(len(self.db.get_fatos_por_chave('game')), 1)

    def test_async_persistence_failure_does_not_report_success(self):
        import asyncio
        fid = self.db.adicionar_fato_patrick('Old')
        self.db.adicionar_fato_patrick('Collision')
        self.db.set_last_consolidated_conversation_id(10)
        payload = {'facts_to_create':[{'decision':'update', 'existing_fact_id':fid, 'fato':'Collision'}], '_candidate_fact_ids':{fid}, 'success':True}
        with patch.object(self.c, 'consolidate_dialogue', return_value=payload):
            with self.assertRaises(MemoryConsolidationError):
                asyncio.run(self.c.consolidate_and_apply_async([{'role':'user', 'content':'test'}], 11, 20))
        self.assertEqual(self.db.get_last_consolidated_conversation_id(), 10)
        self.assertIsNotNone(self.db.get_fato_detalhado(fid))

if __name__ == '__main__':
    unittest.main(verbosity=2)

