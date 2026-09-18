"""Normalize all reviewed sources to ignored hash/enum candidate caches."""
from pipeline import SOURCES, ingest_source

if __name__ == '__main__':
    for key in SOURCES:
        result = ingest_source(key)
        print(f'{key}: {len(result[0]) if result else 0} abstract candidates')
