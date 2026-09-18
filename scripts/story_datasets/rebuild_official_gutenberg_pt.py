"""Bounded Portuguese reconstruction using the approved Gutenberg Dialogue code.

Only the official repository metadata/extractor and Project Gutenberg book text
are inputs. All book and dialogue text stays in ignored offline directories.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from urllib.request import Request, urlopen

try:
    from .pipeline import EXTERNAL, ROOT, iso_now, manifest_path, refresh_manifest, sha256_file, write_json
except ImportError:  # direct script invocation
    from pipeline import EXTERNAL, ROOT, iso_now, manifest_path, refresh_manifest, sha256_file, write_json


SOURCE = ROOT / '.runtime' / 'story_datasets' / 'gutenberg_source'
WORK = EXTERNAL / 'gutenberg_dialogue' / 'work' / 'official_rebuild'
RAW = EXTERNAL / 'gutenberg_dialogue' / 'raw'
EXPECTED_REMOTE = 'https://github.com/ricsinaruto/gutenberg-dialog'
MAX_BOOK_BYTES = 8 * 1024 * 1024
START = re.compile(r'^\*\*\* START OF (?:THE|THIS) PROJECT GUTENBERG', re.I | re.M)
END = re.compile(r'^\*\*\* END OF (?:THE|THIS) PROJECT GUTENBERG', re.I | re.M)


def official_source_revision(source: Path) -> str:
    remote = subprocess.check_output(['git', '-C', str(source), 'remote', 'get-url', 'origin'], text=True).strip()
    if remote.removesuffix('.git').rstrip('/') != EXPECTED_REMOTE:
        raise ValueError(f'Unexpected Gutenberg Dialogue repository: {remote}')
    return subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()


def portuguese_book_ids(source: Path) -> list[int]:
    metadata = source / 'code' / 'utils' / 'metadata.txt'
    ids = []
    for line in metadata.read_text(encoding='utf-8').splitlines():
        book_id, language, available, *_ = line.split('\t', 4)
        if language == 'pt' and available == '1':
            ids.append(int(book_id))
    return ids


def fetch_book(book_id: int, destination: Path) -> str:
    """Fetch one official PG plain-text book, with a strict size bound."""
    if destination.exists():
        return destination.read_text(encoding='utf-8')
    url = f'https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt'
    request = Request(url, headers={'User-Agent': 'MarinaStorySeedResearch/1.0'})
    with urlopen(request, timeout=30) as response:
        if response.url.split('/')[2] != 'www.gutenberg.org':
            raise ValueError(f'Unexpected Project Gutenberg redirect: {response.url}')
        data = response.read(MAX_BOOK_BYTES + 1)
    if len(data) > MAX_BOOK_BYTES:
        raise ValueError(f'Book {book_id} exceeds size bound')
    text = data.decode('utf-8-sig')
    start, end = START.search(text), END.search(text)
    if not start or not end or end.start() <= start.end():
        raise ValueError(f'Book {book_id} lacks Project Gutenberg boundaries')
    text = text[start.end():end.start()].strip()
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding='utf-8')
    return text


def extract_dialogues(source: Path, books: list[tuple[int, str]]) -> tuple[list[list[str]], dict]:
    """Use the official Portuguese language extractor with its default thresholds."""
    sys.path.insert(0, str(source / 'code'))
    try:
        from languages.pt import Pt
        config = SimpleNamespace(dialog_gap=150, min_double_delim=40)
        extractor = Pt(config)
        dialogues = []
        counts = {}
        for book_id, text in books:
            paragraphs = ['']
            for line in text.splitlines(keepends=True):
                if not line.strip():
                    paragraphs.append('')
                else:
                    paragraphs[-1] += line.rstrip('\r\n') + ' '
            words = sum(len(p.split()) for p in paragraphs)
            delimiters = sum(line.count('--') * 2 for line in text.splitlines())
            if not words or delimiters / words * 10000 <= 150:
                counts[str(book_id)] = 0
                continue
            extractor.process_file(paragraphs, '--')
            new = extractor.dialogs
            accepted = [dialog for dialog in new if len(dialog) > 1
                        and all(len(turn.split()) <= 100 for turn in dialog)]
            if len(accepted) / words * 10000 < 15:
                accepted = []
            counts[str(book_id)] = len(accepted)
            dialogues.extend([[f'{book_id}:  {turn}' for turn in dialog] for dialog in accepted])
            extractor.dialogs = []
        return dialogues, counts
    finally:
        sys.path.pop(0)


def rebuild(max_books: int, source: Path = SOURCE) -> dict:
    if not 1 <= max_books <= 100:
        raise ValueError('max_books must be between 1 and 100')
    revision = official_source_revision(source)
    ids = portuguese_book_ids(source)[:max_books]
    books, failed = [], {}
    for book_id in ids:
        try:
            books.append((book_id, fetch_book(book_id, WORK / 'books' / f'{book_id}.txt')))
        except (OSError, UnicodeError, ValueError) as exc:
            failed[str(book_id)] = type(exc).__name__
    dialogues, counts = extract_dialogues(source, books)
    if not dialogues:
        raise RuntimeError('Official reconstruction yielded no Portuguese dialogues')
    # This is a bounded reconstruction, not the published preprocessed archive.
    artifact = RAW / f'official_pt_rebuild_{revision[:12]}_{max_books}.txt'
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(''.join('\n'.join(dialog) + '\n\n' for dialog in dialogues), encoding='utf-8')
    state = refresh_manifest('gutenberg_dialogue', status='raw_available')
    state['downloaded_at'] = iso_now()
    state['source_type'] = 'official_repository_rebuild'
    state['source_version'] = revision
    state['reconstruction'] = {
        'method': 'approved repository metadata and Portuguese extractor; bounded official Project Gutenberg books',
        'official_repository_revision': revision,
        'book_url_template': 'https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt',
        'selected_book_ids': ids,
        'downloaded_book_ids': [book_id for book_id, _ in books],
        'book_sha256': {str(book_id): sha256_file(WORK / 'books' / f'{book_id}.txt') for book_id, _ in books},
        'failed_book_ids': failed,
        'dialogues_per_book': counts,
        'dialogue_count': len(dialogues),
        'exact_published_archive': False,
    }
    write_json(manifest_path('gutenberg_dialogue'), state)
    return {'selected_books': len(ids), 'downloaded_books': len(books),
            'dialogues': len(dialogues), 'failed': len(failed), 'artifact': artifact.name}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-books', type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(rebuild(args.max_books), ensure_ascii=False))
