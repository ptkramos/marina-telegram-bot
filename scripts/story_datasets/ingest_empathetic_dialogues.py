from pipeline import ingest_source

if __name__ == '__main__':
    result = ingest_source('empathetic_dialogues')
    print(f'empathetic_dialogues: {len(result[0]) if result else 0} abstract candidates')
