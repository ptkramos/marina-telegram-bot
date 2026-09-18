"""Offline, bounded extraction of reusable situation labels from external corpora.

No raw dialogue/story text is written outside the ignored raw archive, and only
reviewed source families may contribute to the versioned abstract library.
"""
from __future__ import annotations

import csv
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import zipfile

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = ROOT / 'data' / 'external' / 'story_datasets'
LIBRARY = ROOT / 'data' / 'story_seeds'
VERSION = 1
PIPELINE_VERSION = 2
MAX_DOWNLOAD = 120 * 1024 * 1024

SOURCES = {
    'dailydialog': {
        'display_name': 'DailyDialog (ConvLab transformation)',
        'origin': 'https://huggingface.co/datasets/ConvLab/dailydialog',
        'download': 'https://huggingface.co/datasets/ConvLab/dailydialog/resolve/main/data.zip',
        'filename': 'convlab_dailydialog_data.zip',
        'license': 'CC-BY-NC-SA-4.0',
        'license_url': 'https://huggingface.co/datasets/ConvLab/dailydialog',
        'license_status': 'reviewed_metadata',
    },
    'empathetic_dialogues': {
        'display_name': 'EmpatheticDialogues',
        'origin': 'https://github.com/facebookresearch/EmpatheticDialogues',
        'download': 'https://dl.fbaipublicfiles.com/parlai/empatheticdialogues/empatheticdialogues.tar.gz',
        'filename': 'empatheticdialogues.tar.gz',
        'license': 'CC-BY-NC-4.0',
        'license_url': 'https://github.com/facebookresearch/EmpatheticDialogues/blob/main/LICENSE',
        'license_status': 'reviewed_official',
    },
    'rocstories': {
        'display_name': 'ROCStories',
        'origin': 'https://cs.rochester.edu/nlp/rocstories/',
        'download': None,
        'filename': None,
        'license': 'User-provided official access notice requires citation; no raw redistribution permission stated',
        'license_url': 'https://cs.rochester.edu/nlp/rocstories/',
        'license_status': 'user_provided_access_terms',
        'citation': 'https://aclanthology.org/N16-1098/',
    },
    'gutenberg_dialogue': {
        'display_name': 'Gutenberg Dialogue Dataset',
        'origin': 'https://github.com/ricsinaruto/gutenberg-dialog',
        'download': 'https://mega.nz/file/eMkgmRIC#7zdi0VGhCZSG2ULqFi6MU0NXndwlhgTEJCaXcvki8sA',
        'filename': None,
        'license': 'MIT repository; user approved offline abstract preprocessing without raw redistribution',
        'license_url': 'https://github.com/ricsinaruto/gutenberg-dialog/blob/master/LICENSE',
        'license_status': 'user_approved_official_source',
        'citation': 'https://aclanthology.org/2021.eacl-main.11/',
    },
}
SOURCE_FLAGS = {
    'dailydialog': 'STORY_DATASET_DAILYDIALOG_ENABLED',
    'empathetic_dialogues': 'STORY_DATASET_EMPATHETIC_DIALOGUES_ENABLED',
    'rocstories': 'STORY_DATASET_ROCSTORIES_ENABLED',
    'gutenberg_dialogue': 'STORY_DATASET_GUTENBERG_ENABLED',
}


def source_enabled(key):
    return (os.getenv('STORY_DATASET_INGESTION_ENABLED', 'true').lower() in ('true', '1', 'yes')
            and os.getenv(SOURCE_FLAGS[key], 'true').lower() in ('true', '1', 'yes'))

# Project-authored abstraction only. External text can support these labels but
# can never create a sentence, character, place, or event in the final library.
TEMPLATES = {
    'forgot_item': ('daily_practical', 'BANAL', ('protagonist',), ('daily_routine',), ('search_later', 'replace_item')),
    'pet_minor_mischief': ('pet', 'BANAL', ('protagonist', 'pet'), ('pet_at_home',), ('tidy_up', 'laugh_it_off')),
    'small_misunderstanding': ('misunderstanding', 'LOW', ('protagonist', 'acquaintance'), ('existing_contact',), ('clarify', 'let_it_pass')),
    'unexpected_invitation': ('invitation', 'LOW', ('protagonist', 'acquaintance'), ('free_time',), ('accept', 'decline', 'reschedule')),
    'project_deadline_change': ('academic', 'LOW', ('protagonist', 'academic_contact'), ('active_project',), ('adjust_plan', 'ask_for_clarification')),
    'unexpected_work_opportunity': ('professional', 'LOW', ('protagonist', 'professional_contact'), ('work_available',), ('consider', 'decline')),
    'schedule_conflict': ('schedule_conflict', 'LOW', ('protagonist', 'acquaintance'), ('existing_plan',), ('reschedule', 'choose_priority')),
    'missed_transport_connection': ('mobility', 'BANAL', ('protagonist',), ('travel_planned',), ('take_alternative', 'arrive_later')),
    'minor_purchase_problem': ('shopping', 'BANAL', ('protagonist',), ('purchase_planned',), ('exchange', 'choose_alternative')),
    'small_success': ('minor_success', 'BANAL', ('protagonist',), ('ordinary_task',), ('share_good_news', 'continue_routine')),
    'friend_plan_cancelled': ('social_light', 'LOW', ('protagonist', 'existing_contact'), ('plan_cancelled_observed',), ('reschedule', 'choose_alternative')),
    'small_favor_requested': ('friendship', 'LOW', ('protagonist', 'existing_contact'), ('favor_request_observed',), ('help_if_possible', 'defer')),
    'support_for_friend': ('friendship', 'LOW', ('protagonist', 'existing_contact'), ('friend_needs_support',), ('listen', 'offer_practical_help')),
    'minor_embarrassment': ('embarrassment', 'BANAL', ('protagonist',), ('embarrassment_observed',), ('laugh_it_off', 'clarify')),
    'positive_feedback': ('minor_success', 'BANAL', ('protagonist', 'existing_contact'), ('feedback_observed',), ('acknowledge', 'continue_routine')),
    'home_task_disrupted': ('home', 'BANAL', ('protagonist',), ('home_issue_observed',), ('fix_small_issue', 'postpone_task')),
    'leisure_plan_changed': ('leisure', 'BANAL', ('protagonist',), ('leisure_change_observed',), ('choose_alternative', 'reschedule')),
    'weather_changes_plan': ('small_inconvenience', 'BANAL', ('protagonist',), ('weather_disruption_observed',), ('choose_indoor_option', 'reschedule')),
    'academic_feedback': ('academic', 'LOW', ('protagonist', 'academic_contact'), ('academic_feedback_observed',), ('revise_work', 'ask_for_clarification')),
    'professional_feedback': ('professional', 'LOW', ('protagonist', 'professional_contact'), ('professional_feedback_observed',), ('adjust_work', 'ask_for_clarification')),
    'unexpected_message': ('friendship', 'BANAL', ('protagonist', 'existing_contact'), ('existing_contact',), ('reply_later', 'clarify_intent')),
    'small_disagreement': ('misunderstanding', 'LOW', ('protagonist', 'existing_contact'), ('disagreement_observed',), ('discuss_calmly', 'let_it_pass')),
    'minor_help_received': ('friendship', 'BANAL', ('protagonist', 'existing_contact'), ('help_received_observed',), ('thank', 'reciprocate_later')),
    'forgotten_commitment': ('schedule_conflict', 'LOW', ('protagonist',), ('forgotten_commitment_observed',), ('apologize', 'reschedule')),
    'partner_small_gesture': ('romantic', 'BANAL', ('protagonist', 'romantic_partner'), ('partner_gesture_observed',), ('acknowledge', 'reciprocate_later')),
    'father_check_in': ('family', 'BANAL', ('protagonist', 'father'), ('father_contact_observed',), ('reply_when_available', 'arrange_call')),
    'self_care_pause': ('self_care', 'BANAL', ('protagonist',), ('rest_need_observed',), ('take_break', 'adjust_activity')),
}
CURATED_KEYS = frozenset(('forgot_item', 'pet_minor_mischief', 'small_misunderstanding',
    'unexpected_invitation', 'project_deadline_change', 'unexpected_work_opportunity',
    'schedule_conflict', 'missed_transport_connection', 'minor_purchase_problem', 'small_success',
    'partner_small_gesture', 'father_check_in', 'self_care_pause'))
CAUSAL_SHAPES = {
    'forgot_item': 'routine_disruption', 'pet_minor_mischief': 'routine_disruption',
    'small_misunderstanding': 'social_repair', 'unexpected_invitation': 'offer_decision',
    'project_deadline_change': 'plan_revision', 'unexpected_work_opportunity': 'offer_decision',
    'schedule_conflict': 'plan_revision', 'missed_transport_connection': 'routine_disruption',
    'minor_purchase_problem': 'routine_disruption', 'small_success': 'effort_result',
    'friend_plan_cancelled': 'plan_revision', 'small_favor_requested': 'offer_decision',
    'support_for_friend': 'social_support', 'minor_embarrassment': 'social_repair',
    'positive_feedback': 'effort_result', 'home_task_disrupted': 'routine_disruption',
    'leisure_plan_changed': 'plan_revision', 'weather_changes_plan': 'plan_revision',
    'academic_feedback': 'effort_result', 'professional_feedback': 'effort_result',
    'unexpected_message': 'offer_decision', 'small_disagreement': 'social_repair',
    'minor_help_received': 'social_support', 'forgotten_commitment': 'social_repair',
    'partner_small_gesture': 'social_support', 'father_check_in': 'social_support',
    'self_care_pause': 'effort_recovery',
}

PATTERNS = {
    'forgot_item': r'\b(?:forgot|forget|misplac\w*|left (?:my|her|his|the)\b|esquec\w*|perdeu)\b',
    'pet_minor_mischief': r'\b(?:dog|cat|puppy|kitten|pet|cachorro|gato)\b.{0,100}\b(?:chew|steal|mess|hide|bagun|roub)\w*',
    'small_misunderstanding': r'\b(?:misunderst\w*|confus\w*|mal.entendid\w*)\b',
    'unexpected_invitation': r'\b(?:invit\w*|convite|convid\w*)\b',
    'project_deadline_change': r'\b(?:deadline|due date|prazo)\b.{0,80}\b(?:chang\w*|mov\w*|adiad\w*|mud\w*)\b',
    'unexpected_work_opportunity': r'\b(?:job offer|work opportunity|oportunidade de trabalho|proposta de trabalho)\b',
    'schedule_conflict': r'\b(?:double.book\w*|schedule conflict|same time|conflict(?:ing)? plans|horários? conflit\w*)\b',
    'missed_transport_connection': r'\b(?:missed (?:the )?(?:bus|train|subway)|perdeu (?:o )?(?:ônibus|metrô|trem))\b',
    'minor_purchase_problem': r'\b(?:wrong size|return(?:ed)? (?:the )?(?:item|shirt|dress)|trocar (?:a|o) (?:roupa|produto))\b',
    'small_success': r'\b(?:finished (?:the )?(?:task|project)|completed (?:the )?(?:task|project)|conseguiu terminar)\b',
    'friend_plan_cancelled': r'\b(?:cancel(?:led|ed)?|called off|desmarc\w*|cancel\w*)\b.{0,70}\b(?:plan|meeting|visit|dinner|lunch|plans|encontro|passeio|compromisso)\b',
    'small_favor_requested': r'\b(?:asked? (?:me|him|her|a friend) (?:for|to) (?:a favor|help)|asked? for help|pediu (?:uma )?ajuda|pediu (?:um )?favor)\b',
    'support_for_friend': r'\b(?:friend|amig\w*)\b.{0,90}\b(?:upset|sad|worried|chatead\w*|trist\w*|preocupad\w*)\b|\b(?:comforted|consol\w*)\b.{0,50}\b(?:friend|amig\w*)\b',
    'minor_embarrassment': r'\b(?:embarrass\w*|awkward moment|constrang\w*|vergonha)\b',
    'positive_feedback': r'\b(?:compliment\w*|prais\w*|elogi\w*|positive feedback|good feedback)\b',
    'home_task_disrupted': r'\b(?:broken|broke|leak\w*|quebrou|vazamento)\b.{0,65}\b(?:sink|door|appliance|faucet|chair|kitchen|pia|porta|torneira|cozinha)\b',
    'leisure_plan_changed': r'\b(?:movie|concert|show|passeio|cinema|filme)\b.{0,65}\b(?:cancel\w*|changed|adiad\w*|desmarc\w*|mudou)\b|\b(?:cancel\w*|adiad\w*|desmarc\w*)\b.{0,65}\b(?:movie|concert|show|passeio|cinema|filme)\b',
    'weather_changes_plan': r'\b(?:rain\w*|storm\w*|chuva|choveu)\b.{0,90}\b(?:plan|trip|walk|picnic|passeio|viagem)\b|\b(?:plan|trip|walk|picnic|passeio|viagem)\b.{0,90}\b(?:rain\w*|storm\w*|chuva|choveu)\b',
    'academic_feedback': r'\b(?:teacher|professor|instructor|professora)\b.{0,90}\b(?:feedback|grade|review|nota|coment\w*)\b',
    'professional_feedback': r'\b(?:boss|manager|supervisor|chefe)\b.{0,90}\b(?:feedback|review|prais\w*|comment\w*|coment\w*)\b',
    'unexpected_message': r'\b(?:unexpected|surprise|inesperad\w*|surpresa)\b.{0,40}\b(?:message|text|email|mensagem|recado)\b',
    'small_disagreement': r'\b(?:disagree\w*|argument|argued|discussão|discord\w*)\b',
    'minor_help_received': r'\b(?:helped (?:me|him|her|a friend)|ajudou (?:me|ela|ele|um amigo|uma amiga))\b',
    'forgotten_commitment': r'\b(?:forgot|forget|esqueceu|esqueci)\b.{0,70}\b(?:appointment|meeting|date|plan|compromisso|encontro|consulta)\b',
}
COMPILED = {key: re.compile(pattern, re.I) for key, pattern in PATTERNS.items()}
HARD_GATED = re.compile(r'\b(?:death|died|pregnan\w*|murder\w*|cancer|severe illness|violent crime|grave accident|morte|morreu|gravidez|assassinato|doença grave)\b', re.I)
ARCHAIC = re.compile(r'\b(?:thou|thee|thy|hast|doth|lordship|your majesty|vossa mercê|vossa senhoria)\b', re.I)


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def ensure_dirs():
    for key in SOURCES:
        (EXTERNAL / key / 'raw').mkdir(parents=True, exist_ok=True)
    (EXTERNAL / 'manifests').mkdir(parents=True, exist_ok=True)
    (EXTERNAL / 'licenses').mkdir(parents=True, exist_ok=True)
    LIBRARY.mkdir(parents=True, exist_ok=True)


def manifest_path(key):
    return EXTERNAL / 'manifests' / f'{key}.json'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')


def refresh_manifest(key, *, status=None, processed_at=None):
    ensure_dirs()
    source = SOURCES[key]
    path = manifest_path(key)
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    files = sorted(p for p in (EXTERNAL / key / 'raw').iterdir() if p.is_file() and not p.name.endswith('.part'))
    state = {
        'dataset_key': key,
        'display_name': source['display_name'],
        'source_type': old.get('source_type') or ('manual_download' if key == 'rocstories' else 'attributed_distribution' if key == 'dailydialog' else 'official_download'),
        'source_origin': source['origin'],
        'download_url': source['download'],
        'downloaded_at': old.get('downloaded_at'),
        'source_version': old.get('source_version'),
        'raw_files': [p.name for p in files],
        'sha256': {p.name: sha256_file(p) for p in files},
        'license_file': f'../licenses/{key}.json',
        'license_status': source['license_status'],
        'ingestion_status': status or old.get('ingestion_status') or ('raw_available' if files else 'missing'),
        'last_processed_at': processed_at or old.get('last_processed_at'),
        'pipeline_version': PIPELINE_VERSION,
    }
    if old.get('reconstruction'):
        state['reconstruction'] = old['reconstruction']
    write_json(path, state)
    write_json(EXTERNAL / 'licenses' / f'{key}.json', {
        'dataset_key': key, 'license': source['license'], 'license_status': source['license_status'],
        'reference': source['license_url'],
        'note': ('Review source terms before ingesting.' if source['license_status'] == 'review_required'
                 else 'Only offline abstract preprocessing; raw data is never distributed or read at runtime.'),
        'citation': source.get('citation'),
    })
    return state


def download(key):
    source = SOURCES[key]
    manifest = refresh_manifest(key)
    if not source_enabled(key):
        return refresh_manifest(key, status='disabled')
    if manifest['raw_files']:
        return refresh_manifest(key, status='raw_available')
    if not source['download']:
        return refresh_manifest(key, status='skipped_manual_source')
    if key == 'gutenberg_dialogue':
        return _download_mega_public(key)
    destination = EXTERNAL / key / 'raw' / source['filename']
    partial = destination.with_name(destination.name + '.part')
    request = Request(source['download'], headers={'User-Agent': 'MarinaStoryDatasetBuild/1.0'})
    try:
        with urlopen(request, timeout=90) as response, partial.open('wb') as output:
            size = 0
            for block in iter(lambda: response.read(1024 * 1024), b''):
                size += len(block)
                if size > MAX_DOWNLOAD:
                    raise ValueError(f'{key}: download exceeds 120 MiB bound')
                output.write(block)
        if not (zipfile.is_zipfile(partial) or tarfile.is_tarfile(partial)):
            raise ValueError(f'{key}: downloaded file is not a valid archive')
        partial.replace(destination)
        manifest = refresh_manifest(key, status='raw_available')
        manifest['downloaded_at'] = iso_now()
        write_json(manifest_path(key), manifest)
        return manifest
    except Exception:
        partial.unlink(missing_ok=True)
        refresh_manifest(key, status='download_failed')
        raise


def _b64url(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _download_mega_public(key):
    """Download the project's official Portuguese MEGA file, without an account."""
    source = SOURCES[key]
    parsed = urlsplit(source['download'])
    if parsed.netloc != 'mega.nz' or not parsed.path.startswith('/file/'):
        raise ValueError('Only the approved official MEGA file link is allowed')
    handle = parsed.path.removeprefix('/file/')
    key_material = _b64url(parsed.fragment)
    if len(key_material) != 32:
        raise ValueError('Invalid MEGA public file key')
    aes_key = bytes(left ^ right for left, right in zip(key_material[:16], key_material[16:]))
    iv = key_material[16:24] + b'\x00' * 8
    request = Request('https://g.api.mega.co.nz/cs',
                      data=json.dumps([{'a':'g','g':1,'p':handle,'ssl':2}]).encode(),
                      headers={'Content-Type':'application/json','User-Agent':'MarinaStoryDatasetBuild/1.0'})
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if not isinstance(payload,list) or not payload or not isinstance(payload[0],dict):
        code = payload[0] if isinstance(payload,list) and payload and isinstance(payload[0],int) else 'unexpected_response'
        if code == -16:
            return refresh_manifest(key,status='official_source_blocked')
        raise ValueError(f'MEGA did not return file metadata ({code})')
    info = payload[0]
    size = info.get('s')
    if not isinstance(size,int) or not 0 < size <= MAX_DOWNLOAD or not isinstance(info.get('g'),str):
        raise ValueError('MEGA file unavailable or outside size bound')
    attributes = _b64url(info['at'])
    decoded = Cipher(algorithms.AES(aes_key),modes.CBC(b'\x00' * 16)).decryptor().update(attributes)
    if not decoded.startswith(b'MEGA'):
        raise ValueError('MEGA metadata failed decryption')
    filename = json.loads(decoded[4:].rstrip(b'\x00'))['n']
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.lower().endswith(('.zip','.tar.gz','.tgz','.csv','.json','.txt','.tsv')):
        raise ValueError('Unexpected official Gutenberg filename')
    destination = EXTERNAL / key / 'raw' / safe_name
    if destination.exists():
        return refresh_manifest(key, status='raw_available')
    partial = destination.with_name(destination.name + '.part')
    decryptor = Cipher(algorithms.AES(aes_key),modes.CTR(iv)).decryptor()
    try:
        with urlopen(Request(info['g'],headers={'User-Agent':'MarinaStoryDatasetBuild/1.0'}),timeout=90) as response, partial.open('wb') as output:
            written = 0
            for block in iter(lambda: response.read(1024 * 1024),b''):
                written += len(block)
                if written > size:
                    raise ValueError('MEGA download exceeded declared size')
                output.write(decryptor.update(block))
            output.write(decryptor.finalize())
        if written != size or (safe_name.lower().endswith(('.zip','.tar.gz','.tgz')) and not
                               (zipfile.is_zipfile(partial) or tarfile.is_tarfile(partial))):
            raise ValueError('Incomplete or invalid official Gutenberg download')
        partial.replace(destination)
        manifest = refresh_manifest(key,status='raw_available')
        manifest['downloaded_at'] = iso_now()
        manifest['source_version'] = 'official-portuguese-preprocessed'
        write_json(manifest_path(key),manifest)
        return manifest
    except Exception:
        partial.unlink(missing_ok=True)
        refresh_manifest(key,status='download_failed')
        raise


def _safe_members(path):
    """Yield archive member bytes without extracting to disk or following paths."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or member.file_size > 80 * 1024 * 1024:
                    continue
                name = Path(member.filename).name
                if name and not name.startswith('.'):
                    yield member.filename, archive.read(member)
    elif tarfile.is_tarfile(path):
        with tarfile.open(path, 'r:*') as archive:
            for member in archive:
                if not member.isfile() or member.size > 80 * 1024 * 1024:
                    continue
                name = Path(member.name).name
                if name and not name.startswith('.'):
                    stream = archive.extractfile(member)
                    if stream:
                        yield member.name, stream.read()
    else:
        yield path.name, path.read_bytes()


def _decode(data):
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError('Unsupported encoding in story source')


def _records_from_member(key, name, data):
    lower = name.lower()
    if lower.endswith('.csv'):
        for row in csv.DictReader(io.StringIO(_decode(data))):
            if key == 'rocstories':
                yield ' '.join(row.get(f'sentence{i}', '') for i in range(1, 6))
            elif key == 'empathetic_dialogues':
                yield row.get('prompt', '') or row.get('context', '')
            else:
                yield ' '.join(str(value) for value in row.values() if value)
    elif lower.endswith('.json'):
        payload = json.loads(_decode(data))
        if isinstance(payload, dict):
            payload = payload.get('train') or payload.get('data') or payload.get('dialogues') or []
        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict):
                    turns = row.get('turns', [])
                    yield ' '.join(str(turn.get('utterance', '')) for turn in turns if isinstance(turn, dict))
    elif lower.endswith(('.txt', '.tsv')):
        for line in _decode(data).splitlines():
            if line.strip():
                yield line.replace('__eou__', ' ')


def extract_candidates(key):
    """Return only hashes and enum labels; source wording is never persisted."""
    if key not in SOURCES:
        raise ValueError(key)
    manifest = refresh_manifest(key)
    if manifest['license_status'] == 'review_required':
        refresh_manifest(key, status='license_review_required')
        return []
    candidates = []
    seen_hashes = set()
    records_seen = 0
    for filename in manifest['raw_files']:
        path = EXTERNAL / key / 'raw' / filename
        for member_name, data in _safe_members(path):
            for record in _records_from_member(key, member_name, data):
                records_seen += 1
                if HARD_GATED.search(record) or (key == 'gutenberg_dialogue' and ARCHAIC.search(record)):
                    continue
                labels = sorted(template_key for template_key, pattern in COMPILED.items() if pattern.search(record))
                if labels:
                    record_hash = hashlib.sha256(record.encode('utf-8')).hexdigest()
                    if record_hash in seen_hashes:
                        continue
                    seen_hashes.add(record_hash)
                    candidates.append({'source_dataset': key,
                                       'source_record_hash': record_hash,
                                       'candidate_tags': labels,
                                       'causal_shape': sorted({CAUSAL_SHAPES[label] for label in labels}),
                                       'intensity_estimate': 'low'})
    refresh_manifest(key, status='processed', processed_at=iso_now())
    return candidates, records_seen


def ingest_source(key):
    manifest = refresh_manifest(key)
    if not source_enabled(key):
        refresh_manifest(key, status='disabled')
        return None
    if not manifest['raw_files']:
        return None
    if manifest['license_status'] == 'review_required':
        refresh_manifest(key, status='license_review_required')
        return None
    fingerprint = hashlib.sha256(json.dumps({
        'files': manifest['sha256'], 'version': PIPELINE_VERSION,
    }, sort_keys=True).encode()).hexdigest()
    folder = EXTERNAL / key / 'normalized'
    cache = folder / 'cache.json'
    candidates_path = folder / 'candidates.v1.jsonl'
    if cache.exists() and candidates_path.exists():
        state = json.loads(cache.read_text(encoding='utf-8'))
        if state.get('fingerprint') == fingerprint:
            return ([json.loads(line) for line in candidates_path.read_text(encoding='utf-8').splitlines() if line],
                    state['records_seen'])
    candidates, seen = extract_candidates(key)
    folder.mkdir(parents=True, exist_ok=True)
    candidates_path.write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in candidates), encoding='utf-8')
    write_json(cache, {'fingerprint': fingerprint, 'records_seen': seen, 'pipeline_version': PIPELINE_VERSION})
    return candidates, seen


def build_library():
    """Build a deterministic local library; source counts never become weights."""
    ensure_dirs()
    evidence = {key: set() for key in TEMPLATES}
    candidate_support = {key: Counter() for key in TEMPLATES}
    summary = {}
    for source in SOURCES:
        outcome = ingest_source(source)
        if outcome is not None:
            candidates, seen = outcome
            for unit in candidates:
                for key in unit['candidate_tags']:
                    evidence[key].add(source)
                    candidate_support[key][source] += 1
            summary[source] = {'enabled': True, 'records_seen': seen,
                               'candidate_units': len(candidates), 'license_status': SOURCES[source]['license_status']}
        else:
            current = refresh_manifest(source)
            summary[source] = {'enabled': False, 'records_seen': 0,
                               'reason': 'disabled' if not source_enabled(source) else
                                         'license_review_required' if SOURCES[source]['license_status'] == 'review_required' else
                                         current['ingestion_status'] if not current['raw_files'] else 'source_missing',
                               'license_status': SOURCES[source]['license_status']}
    rows = []
    selected = {key for key in TEMPLATES if key in CURATED_KEYS or len(evidence[key]) >= 2}
    structural_signatures = {}
    deduplicated = {}
    for key in sorted(TEMPLATES, key=lambda item: (item not in CURATED_KEYS, item)):
        if key not in selected:
            continue
        category, intensity, roles, preconditions, consequences = TEMPLATES[key]
        signature = (category, CAUSAL_SHAPES[key], roles, preconditions, consequences)
        if signature in structural_signatures:
            deduplicated[key] = structural_signatures[signature]
            continue
        structural_signatures[signature] = key
        rows.append({'seed_key': key, 'category': category, 'intensity': intensity,
                     'actor_roles': list(roles), 'preconditions': list(preconditions),
                     'possible_complications': [], 'possible_consequences': list(consequences),
                     'causal_shape': CAUSAL_SHAPES[key],
                     'allowed_horizons': ['TODAY', 'NEAR_FUTURE'], 'hard_gated': False,
                     'source_families': (["marina_curated"] if key in CURATED_KEYS else []) + sorted(evidence[key])})
    rows.sort(key=lambda row: row['seed_key'])
    path = LIBRARY / 'story_seed_library.v1.jsonl'
    path.write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows), encoding='utf-8')
    write_json(LIBRARY / 'story_seed_taxonomy.v1.json', {
        'library_version': VERSION, 'categories': sorted({row['category'] for row in rows}),
        'intensities': ['BANAL', 'LOW', 'MEDIUM', 'HIGH', 'SIGNIFICANT'],
    })
    write_json(LIBRARY / 'provenance_summary.v1.json', {
        'library_version': VERSION, 'pipeline_version': PIPELINE_VERSION,
        'sources': summary, 'final_seed_count': len(rows),
        'excluded_for_weak_support': sorted(set(TEMPLATES) - selected),
        'deduplicated_to': deduplicated,
        'derivation': 'project-authored abstract templates with source-family evidence; no original text',
    })
    by_category = Counter(row['category'] for row in rows)
    by_family = Counter(family for row in rows for family in row['source_families'])
    by_shape = Counter(row['causal_shape'] for row in rows)
    write_json(LIBRARY / 'coverage_report.v1.json', {
        'library_version': VERSION,
        'seed_count': len(rows),
        'by_category': dict(sorted(by_category.items())),
        'by_source_family': dict(sorted(by_family.items())),
        'by_causal_shape': dict(sorted(by_shape.items())),
        'seed_support': {row['seed_key']: dict(sorted(candidate_support[row['seed_key']].items())) for row in rows},
        'selection_rule': 'curated seeds retained; additional shapes need at least two approved source families; identical structures collapse to curated-first canonical key',
        'excluded_for_weak_support': sorted(set(TEMPLATES) - selected),
        'deduplicated_to': deduplicated,
    })
    validate_library(path)
    return path


def validate_library(path=None):
    path = path or LIBRARY / 'story_seed_library.v1.jsonl'
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
    keys = set()
    signatures = set()
    for row in rows:
        key = row['seed_key']
        expected_fields = {'seed_key','category','intensity','actor_roles','preconditions',
                           'possible_complications','possible_consequences','allowed_horizons',
                           'hard_gated','source_families','causal_shape'}
        if set(row) != expected_fields:
            raise ValueError(f'Unexpected story seed fields: {key}')
        if key in keys or key not in TEMPLATES or row['category'] not in {item[0] for item in TEMPLATES.values()}:
            raise ValueError(f'Invalid or duplicated story seed: {key}')
        if row['intensity'] not in ('BANAL', 'LOW') or row['hard_gated']:
            raise ValueError(f'Unsafe automatic story seed: {key}')
        if row['causal_shape'] != CAUSAL_SHAPES[key]:
            raise ValueError(f'Unexpected causal shape: {key}')
        if any(not re.fullmatch(r'[a-z][a-z0-9_]*', value) for field in ('actor_roles','preconditions','possible_complications','possible_consequences') for value in row[field]):
            raise ValueError(f'Free text survived in story seed: {key}')
        if not row['preconditions'] or not row['possible_consequences']:
            raise ValueError(f'Incomplete story seed: {key}')
        expected = TEMPLATES[key]
        if (row['category'],row['intensity'],tuple(row['actor_roles']),tuple(row['preconditions']),
            tuple(row['possible_consequences'])) != expected:
            raise ValueError(f'Unreviewed structure in story seed: {key}')
        if row['possible_complications'] or row['allowed_horizons'] != ['TODAY','NEAR_FUTURE']:
            raise ValueError(f'Unreviewed sequence in story seed: {key}')
        if not set(row['source_families']) <= {'marina_curated',*SOURCES}:
            raise ValueError(f'Unknown provenance in story seed: {key}')
        if key not in CURATED_KEYS and len(set(row['source_families'])) < 2:
            raise ValueError(f'Insufficient cross-source evidence: {key}')
        signature = (row['category'], row['causal_shape'], tuple(row['actor_roles']),
                     tuple(row['preconditions']), tuple(row['possible_consequences']))
        if signature in signatures:
            raise ValueError(f'Duplicate structural seed: {key}')
        signatures.add(signature)
        keys.add(key)
    return len(rows)
