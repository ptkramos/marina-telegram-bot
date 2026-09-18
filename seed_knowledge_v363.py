"""Idempotent, reviewed knowledge topics from the locked v3.6 canon."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db import DatabaseManager


def seed_knowledge(db: DatabaseManager) -> dict[str, int]:
    from knowledge_dialogue import KnowledgeDialogue

    dialogue = KnowledgeDialogue(db)
    if not dialogue.privacy.bible.get_character('marina'):
        raise RuntimeError('Seed the locked World Bible first')

    milo = dialogue.register_subject(
        'fact', 'o Milo', ['o Milo', 'meu cachorro'],
        approved_detail='O Milo é meu Shih Tzu.')
    dialogue.privacy.observe('fact', milo, 'marina', privacy_level='PUBLIC_SOCIAL')

    relationship = dialogue.register_subject(
        'relationship', 'o nosso namoro', ['nosso namoro', 'meu namoro com você'],
        approved_detail='Você é meu primeiro namorado oficial; nosso relacionamento é comprometido.')
    dialogue.privacy.observe('relationship', relationship, 'marina',
                             privacy_level='PRIVATE_COUPLE')
    dialogue.privacy.grant('relationship', relationship, 'marina', 'patrick_ramos',
                           authorized_by='marina')
    return {'milo': milo, 'relationship': relationship}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()
    os.environ['MARINA_DB_PATH'] = str(args.db.resolve())
    from db import DatabaseManager

    print(seed_knowledge(DatabaseManager(args.db)))
