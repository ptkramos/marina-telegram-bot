import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from config import settings
from scripts.story_datasets import pipeline
from scripts.story_datasets import rebuild_official_gutenberg_pt as rebuild
from story_engine import load_local_seed_pool


class TestStoryDatasets(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        external = self.root / 'external'
        library = self.root / 'story_seeds'
        patch_external = patch.object(pipeline,'EXTERNAL',external)
        patch_library = patch.object(pipeline,'LIBRARY',library)
        patch_external.start(); patch_library.start()
        self.addCleanup(patch_external.stop)
        self.addCleanup(patch_library.stop)
        pipeline.ensure_dirs()

    def test_build_keeps_only_abstract_structure_and_manual_raw_unchanged(self):
        daily = pipeline.EXTERNAL / 'dailydialog' / 'raw' / 'tiny.zip'
        with zipfile.ZipFile(daily,'w') as archive:
            archive.writestr('data/dialogues.json',json.dumps([
                {'turns':[{'utterance':'Anya forgot a red notebook before class.'}]},
                {'turns':[{'utterance':'A friend sent an invitation.'}]},
            ]))
        roc = pipeline.EXTERNAL / 'rocstories' / 'raw' / 'manual.csv'
        with roc.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream)
            writer.writerow(['sentence1','sentence2','sentence3','sentence4','sentence5'])
            writer.writerow(['Mira forgot a blue bag.','','','',''])
        before=pipeline.sha256_file(roc)
        path=pipeline.build_library()
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(pipeline.sha256_file(roc),before)
        self.assertEqual(pipeline.validate_library(path),len(rows))
        self.assertGreaterEqual(len(rows),len(pipeline.CURATED_KEYS))
        self.assertNotIn('Anya',path.read_text(encoding='utf-8'))
        self.assertNotIn('Mira',path.read_text(encoding='utf-8'))
        self.assertIn('dailydialog',next(row for row in rows if row['seed_key']=='forgot_item')['source_families'])
        self.assertIn('rocstories',next(row for row in rows if row['seed_key']=='forgot_item')['source_families'])
        report=json.loads((pipeline.LIBRARY/'coverage_report.v1.json').read_text(encoding='utf-8'))
        self.assertEqual(report['seed_count'],len(rows))
        self.assertEqual(sum(report['by_category'].values()),len(rows))
        self.assertEqual(sum(report['by_causal_shape'].values()),len(rows))
        signatures={(row['category'],row['causal_shape'],tuple(row['actor_roles']),
                     tuple(row['preconditions']),tuple(row['possible_consequences'])) for row in rows}
        self.assertEqual(len(signatures),len(rows))

    def test_canonical_relationship_family_and_self_care_have_curated_coverage(self):
        path=pipeline.build_library()
        rows={row['seed_key']:row for row in
              (json.loads(line) for line in path.read_text(encoding='utf-8').splitlines())}
        expected={'partner_small_gesture':'romantic', 'father_check_in':'family',
                  'self_care_pause':'self_care'}
        for key,category in expected.items():
            self.assertEqual(rows[key]['category'],category)
            self.assertEqual(rows[key]['source_families'],['marina_curated'])
            self.assertEqual(len(rows[key]['preconditions']),1)
        self.assertEqual(pipeline.validate_library(path),len(rows))

    def test_cache_changes_when_raw_hash_changes(self):
        daily = pipeline.EXTERNAL / 'dailydialog' / 'raw' / 'tiny.zip'
        with zipfile.ZipFile(daily,'w') as archive:
            archive.writestr('data/dialogues.json',json.dumps([{'turns':[{'utterance':'I forgot an item.'}]}]))
        first=pipeline.ingest_source('dailydialog')
        self.assertEqual(len(first[0]),1)
        cached=pipeline.ingest_source('dailydialog')
        self.assertEqual(cached,first)
        with zipfile.ZipFile(daily,'w') as archive:
            archive.writestr('data/dialogues.json',json.dumps([{'turns':[{'utterance':'I received an invitation.'}]}]))
        second=pipeline.ingest_source('dailydialog')
        self.assertEqual(second[0][0]['candidate_tags'],['unexpected_invitation'])

    def test_offline_runtime_reads_only_local_library_when_enabled(self):
        path=pipeline.build_library()
        with patch('story_engine.LIBRARY_PATH',path),patch.object(settings,'STORY_SEED_LIBRARY_ENABLED',True):
            keys={seed.key for seed in load_local_seed_pool()}
        self.assertIn('missed_transport_connection',keys)
        self.assertIn('forgot_item',keys)
        with patch.object(settings,'STORY_SEED_LIBRARY_ENABLED',False):
            self.assertNotIn('missed_transport_connection',{seed.key for seed in load_local_seed_pool()})

    def test_validator_rejects_free_text_and_high_impact(self):
        path=pipeline.build_library()
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        rows[0]['possible_consequences']=['Anya goes to Boston']
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
        with self.assertRaises(ValueError):
            pipeline.validate_library(path)

    def test_validator_rejects_weak_derived_seed(self):
        path=pipeline.build_library()
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        derived=dict(rows[0])
        derived['seed_key']='academic_feedback'
        category,intensity,roles,preconditions,consequences=pipeline.TEMPLATES['academic_feedback']
        derived['category']=category
        derived['intensity']=intensity
        derived['causal_shape']='effort_result'
        derived['actor_roles']=list(roles)
        derived['preconditions']=list(preconditions)
        derived['possible_consequences']=list(consequences)
        derived['source_families']=['rocstories']
        path.write_text(''.join(json.dumps(row)+'\n' for row in [*rows,derived]),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Insufficient cross-source evidence'):
            pipeline.validate_library(path)

    def test_download_is_idempotent_and_never_fetches_manual_roc(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('data/dialogues.json','[]')
        with patch.object(pipeline,'urlopen',return_value=io.BytesIO(buffer.getvalue())) as fetch:
            first=pipeline.download('dailydialog')
            second=pipeline.download('dailydialog')
            self.assertEqual(fetch.call_count,1)
        self.assertEqual(first['sha256'],second['sha256'])
        with patch.object(pipeline,'urlopen') as fetch:
            self.assertEqual(pipeline.download('rocstories')['ingestion_status'],'skipped_manual_source')
            fetch.assert_not_called()

    def test_invalid_download_never_marks_source_ready(self):
        with patch.object(pipeline,'urlopen',return_value=io.BytesIO(b'not an archive')):
            with self.assertRaises(ValueError):
                pipeline.download('dailydialog')
        manifest=json.loads(pipeline.manifest_path('dailydialog').read_text(encoding='utf-8'))
        self.assertEqual(manifest['ingestion_status'],'download_failed')
        self.assertEqual(manifest['raw_files'],[])

    def test_official_mega_block_does_not_substitute_corpus(self):
        with patch.object(pipeline,'urlopen',return_value=io.BytesIO(b'[-16]')) as fetch:
            manifest=pipeline.download('gutenberg_dialogue')
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(manifest['ingestion_status'],'official_source_blocked')
        self.assertEqual(manifest['raw_files'],[])

    def test_official_gutenberg_archive_is_filtered_when_supplied_manually(self):
        archive_path=pipeline.EXTERNAL/'gutenberg_dialogue'/'raw'/'pt.zip'
        with zipfile.ZipFile(archive_path,'w') as archive:
            archive.writestr('pt/train.txt',
                'Um convite inesperado chegou.\nVossa mercê recebeu um convite.\n')
        candidates,seen=pipeline.ingest_source('gutenberg_dialogue')
        self.assertEqual(seen,2)
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['candidate_tags'],['unexpected_invitation'])

    def test_official_rebuild_provenance_survives_manifest_refresh(self):
        metadata = self.root/'source'/'code'/'utils'/'metadata.txt'
        metadata.parent.mkdir(parents=True)
        metadata.write_text('10\tpt\t1\tA\tB\n11\tpt\t0\tA\tB\n12\ten\t1\tA\tB\n',encoding='utf-8')
        self.assertEqual(rebuild.portuguese_book_ids(self.root/'source'),[10])
        raw = pipeline.EXTERNAL/'gutenberg_dialogue'/'raw'/'official_sample.txt'
        raw.write_text('10:  Um convite chegou.\n',encoding='utf-8')
        state = pipeline.refresh_manifest('gutenberg_dialogue')
        state['source_type']='official_repository_rebuild'
        state['source_version']='abc123'
        state['reconstruction']={'selected_book_ids':[10], 'exact_published_archive':False}
        pipeline.write_json(pipeline.manifest_path('gutenberg_dialogue'),state)
        refreshed = pipeline.refresh_manifest('gutenberg_dialogue',status='processed')
        self.assertEqual(refreshed['source_type'],'official_repository_rebuild')
        self.assertEqual(refreshed['reconstruction']['selected_book_ids'],[10])
        self.assertEqual(refreshed['source_version'],'abc123')


if __name__ == '__main__':
    unittest.main()
