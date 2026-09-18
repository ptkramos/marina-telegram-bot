"""Download public approved archives and register manual/official-only sources."""
from pipeline import SOURCES, download


if __name__ == '__main__':
    failed = False
    for key in SOURCES:
        try:
            manifest = download(key)
            print(f'[story-datasets] {key}: {manifest["ingestion_status"]} ({len(manifest["raw_files"])} raw files)')
        except Exception as exc:
            failed = True
            print(f'[story-datasets] {key}: download_failed ({exc.__class__.__name__}: {exc})')
    if failed:
        raise SystemExit(1)
