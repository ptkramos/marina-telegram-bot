"""Build a clean validation archive (allowlist of tracked source + docs).

Excludes .env, DBs, venv, scratch, logs, generated images, backups, private cache.
.env.example is allowed.
"""
from __future__ import annotations

import argparse
import fnmatch
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Allowlist globs relative to repo root (tracked-style sources)
ALLOW_GLOBS = [
    '*.py',
    'migrations/*.sql',
    'docs/**/*',
    'scripts/**/*',
    'tests/**/*',
    '.env.example',
    'requirements*.txt',
    'pyproject.toml',
    'README*',
    'VALIDACAO*.md',
    'HANDOFF*.md',
    'PLANO*.md',
    'REVISAO*.md',
    '*.md',
    'run_local.bat',
    'run_local.sh',
]

DENY_NAMES = {
    '.env',
    '.git',
    'venv',
    '.venv',
    '__pycache__',
    'scratch',
    'backups',
    'node_modules',
    '.runtime',
}

DENY_SUFFIXES = {
    '.db',
    '.sqlite',
    '.sqlite3',
    '.pyc',
    '.pyo',
    '.log',
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
    '.gif',
    '.mp3',
    '.ogg',
    '.wav',
    '.zip',
}

DENY_GLOBS = [
    'logs/**',
    'data/**/*.db',
    'data/**/*.sqlite*',
    '**/scratch/**',
    '**/.env',
    '**/venv/**',
    '**/.venv/**',
    '**/__pycache__/**',
    '**/*.db',
]


def _denied(rel: str) -> bool:
    parts = Path(rel).parts
    if any(p in DENY_NAMES for p in parts):
        return True
    name = Path(rel).name
    if name == '.env':
        return True
    if name == '.env.example':
        return False
    suffix = Path(rel).suffix.lower()
    if suffix in DENY_SUFFIXES:
        return True
    for pat in DENY_GLOBS:
        if fnmatch.fnmatch(rel.replace('\\', '/'), pat):
            return True
    return False


def _allowed(rel: str) -> bool:
    if _denied(rel):
        return False
    norm = rel.replace('\\', '/')
    for pat in ALLOW_GLOBS:
        if fnmatch.fnmatch(norm, pat) or fnmatch.fnmatch(Path(norm).name, pat):
            return True
    return False


def collect_files() -> list[Path]:
    files = []
    for path in ROOT.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if _allowed(rel):
            files.append(path)
    return sorted(files)


def build_archive(out_path: Path) -> list[str]:
    members = collect_files()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for path in members:
            rel = path.relative_to(ROOT).as_posix()
            zf.write(path, arcname=rel)
    return [p.relative_to(ROOT).as_posix() for p in members]


def verify_archive(archive: Path) -> list[str]:
    """Return list of violations found inside the zip."""
    violations = []
    with zipfile.ZipFile(archive, 'r') as zf:
        for name in zf.namelist():
            norm = name.replace('\\', '/')
            base = Path(norm).name
            if base == '.env' or norm.endswith('/.env'):
                violations.append(f'contains .env: {norm}')
            if Path(norm).suffix.lower() in {'.db', '.sqlite', '.sqlite3'}:
                violations.append(f'contains DB: {norm}')
            if '/venv/' in f'/{norm}/' or norm.startswith('venv/'):
                violations.append(f'contains venv: {norm}')
            if '/scratch/' in f'/{norm}/' or norm.startswith('scratch/'):
                violations.append(f'contains scratch: {norm}')
            if Path(norm).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'} and 'tests/' not in norm:
                violations.append(f'contains private/generated image: {norm}')
            if _denied(norm) and base != '.env.example':
                violations.append(f'denied path slipped in: {norm}')
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description='Build clean Marina validation archive')
    parser.add_argument(
        '-o', '--output',
        default=str(ROOT / 'dist' / 'marina-validation-clean.zip'),
        help='Output zip path',
    )
    parser.add_argument('--verify-only', action='store_true', help='Only verify an existing archive')
    args = parser.parse_args()
    out = Path(args.output)

    if not args.verify_only:
        members = build_archive(out)
        print(f'Wrote {out} with {len(members)} files')

    violations = verify_archive(out)
    if violations:
        print('VERIFY FAIL')
        for v in violations:
            print(' ', v)
        return 1
    print('VERIFY OK — no .env / DB / venv / scratch / private images')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
