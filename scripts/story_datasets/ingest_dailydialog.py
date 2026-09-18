from pipeline import ingest_source

if __name__ == '__main__':
    result = ingest_source('dailydialog')
    print(f'dailydialog: {len(result[0]) if result else 0} abstract candidates')
