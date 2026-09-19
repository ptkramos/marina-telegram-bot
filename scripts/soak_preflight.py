"""Read-only local startup gate for the agreed full 3.7.0 soak configuration."""
from contextlib import closing
import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REQUIRED_SWITCHES = (
    'PROACTIVITY_ENABLED', 'DUAL_VOICE_ENABLED',
    'MEMORY_CONSOLIDATION_ENABLED', 'SESSION_REFLECTION_ENABLED',
    'MEMORY_HYGIENE_ENABLED', 'STORY_SEED_LIBRARY_ENABLED',
    'WORLD_HYGIENE_ENABLED', 'REAL_USAGE_TELEMETRY_ENABLED', 'VOICE_PROSODY_ENABLED',
    'VOICE_PROSODY_EMOTION_ENABLED', 'VOICE_PROSODY_PAUSES_ENABLED',
    'VOICE_PROSODY_SOUND_TAGS_ENABLED', 'VOICE_PROSODY_FILLERS_ENABLED',
    'VOICE_PROSODY_CONTINUOUS_SOUND_ENABLED', 'REAL_CONTEXT_FETCH_ENABLED',
    'FERIADOS_API_ENABLED', 'REAL_WORLD_PLACE_LOOKUP_ENABLED', 'VISION_ENABLED',
)


def main():
    from config import settings
    errors = list(settings.validate())
    for flag in REQUIRED_SWITCHES:
        if not getattr(settings, flag, False):
            errors.append(f'Recurso do soak desativado: {flag}')
    for name in ('telegram', 'openai', 'apscheduler', 'aiohttp', 'PIL', 'requests', 'ddgs'):
        if importlib.util.find_spec(name) is None:
            errors.append(f'Dependencia ausente: {name}')
    for tool in ('ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            errors.append(f'Conversao de voz indisponivel: {tool}')
    for key in ('NOVITA_API_KEY', 'FERIADOS_API_KEY'):
        if not getattr(settings, key, None):
            errors.append(f'Credencial ausente: {key}')
    if settings.NOVITA_VOICE_ID_CONVERSATIONAL == settings.NOVITA_VOICE_ID_INTIMATE:
        errors.append('Os dois perfis de voz precisam ser distintos.')
    if settings.PROMPT_CONTROL_LANGUAGE != 'en':
        errors.append('PROMPT_CONTROL_LANGUAGE precisa ser en; a saída para o usuário continua pt-BR.')
    if settings.MARINA_OUTPUT_LANGUAGE != 'pt-BR':
        errors.append('MARINA_OUTPUT_LANGUAGE precisa ser pt-BR para a conversa da Marina.')
    source = Path(os.environ.get('MARINA_DB_PATH') or ROOT / 'marin_memory.db').resolve()
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                errors.append('Integridade do banco de memoria invalida.')
            if not conn.execute('SELECT COUNT(*) FROM world_characters WHERE canon_locked=1').fetchone()[0]:
                errors.append('Mundo canonico ausente.')
            if not conn.execute("SELECT COUNT(*) FROM academic_profile WHERE character_key='marina'").fetchone()[0]:
                errors.append('Perfil academico ausente.')
    except sqlite3.Error as exc:
        errors.append(f'Banco indisponivel: {type(exc).__name__}')
    if errors:
        for error in errors:
            print('[ERRO]', error)
        return 1
    print(f'[OK] Marina {settings.APP_VERSION}: runtime canonico + {len(REQUIRED_SWITCHES)} switches operacionais ativos, memoria integra e voz pronta.')
    if settings.PHOTO_PROVIDER_MAINTENANCE:
        print('[INFO] Fotos em manutencao: Marina respondera naturalmente quando voce pedir uma foto.')
    print('[OK] Preparacao local concluida. O bot vai conectar ao Telegram.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
