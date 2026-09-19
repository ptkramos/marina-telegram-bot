"""Static + behavioral audit of production prompt authority / architectural contracts (Round 3).

status=passed only when ALL contracts below are green — no false-green on token scan alone.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompt_policy import FORBIDDEN_LEGACY_TOKENS

SKIP_DIR_NAMES = {
    'tests', 'venv', '.venv', '.git', '__pycache__', 'data', 'backups',
    'scratch', 'agent-transcripts', 'mcps', 'node_modules', 'fixtures',
}
TOKEN_SCAN_EXEMPT = {
    'prompt_policy.py',
    'healthcheck.py',
    'scripts/audit_prompt_authority.py',
}

SYSTEM_PROMPT_NAMES = re.compile(r'(SYSTEM_PROMPT|_PROMPT)\s*=')
ROLE_SYSTEM = re.compile(r'["\']role["\']\s*:\s*["\']system["\']')

# Behavioral imperatives that must not appear inside data-channel formatters
WEB_VISION_IMPERATIVES = [
    'Use essas informações',
    'sem citar que',
    'INSTRUÇÃO DE RESPOSTA',
    'NUNCA diga',
    'Reaja de forma',
]

PT_CONTROL_MARKERS = [
    '[INSTRUÇÃO OBRIGATÓRIA DESTE TURNO]',
    '[INSTRUÇÃO CRÍTICA DESTE TURNO]',
]


def _iter_runtime_py() -> list[Path]:
    out = []
    for path in ROOT.rglob('*.py'):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        out.append(path)
    return out


def check_forbidden_tokens() -> list[dict]:
    hits = []
    for path in _iter_runtime_py():
        rel = path.relative_to(ROOT).as_posix()
        if rel in TOKEN_SCAN_EXEMPT:
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for token in FORBIDDEN_LEGACY_TOKENS:
            if token in text:
                hits.append({'file': rel, 'token': token})
    return hits


def check_prompts_py_not_owner() -> list[str]:
    failures = []
    prompts = (ROOT / 'prompts.py').read_text(encoding='utf-8', errors='replace')
    if 'MARIN_SYSTEM_PROMPT = None' not in prompts:
        failures.append('prompts.MARIN_SYSTEM_PROMPT is not retired (None)')
    if 'EVENTOS_COTIDIANO = ()' not in prompts and 'EVENTOS_COTIDIANO = tuple()' not in prompts:
        failures.append('prompts.EVENTOS_COTIDIANO is not empty')
    return failures


def check_safecore_gate() -> list[str]:
    failures = []
    pp = (ROOT / 'prompt_policy.py').read_text(encoding='utf-8', errors='replace')
    cb = (ROOT / 'context_builder.py').read_text(encoding='utf-8', errors='replace')
    if 'def is_canonical_runtime_ready' not in pp:
        failures.append('missing is_canonical_runtime_ready in prompt_policy')
    if 'is_canonical_runtime_ready' not in cb:
        failures.append('context_builder does not gate on is_canonical_runtime_ready')
    if 'CLEAN START GATE' not in pp and 'clean_canonical_start' not in pp:
        failures.append('SafeCore missing clean-start gate messaging')
    return failures


def check_web_vision_data_only() -> list[str]:
    failures = []
    for fname in ('bot.py', 'vision_service.py', 'prompt_policy.py'):
        text = (ROOT / fname).read_text(encoding='utf-8', errors='replace')
        for marker in WEB_VISION_IMPERATIVES:
            if marker in text and fname != 'prompt_policy.py':
                failures.append(f'{fname} contains data-channel imperative: {marker!r}')
    pp = (ROOT / 'prompt_policy.py').read_text(encoding='utf-8', errors='replace')
    if 'def format_web_evidence' not in pp:
        failures.append('missing format_web_evidence owner')
    if 'def format_vision_evidence' not in pp:
        failures.append('missing format_vision_evidence owner')
    if 'DATA_CHANNEL_POLICY_EN' not in pp:
        failures.append('missing DATA_CHANNEL_POLICY_EN')
    return failures


def check_control_language() -> list[str]:
    failures = []
    bot = (ROOT / 'bot.py').read_text(encoding='utf-8', errors='replace')
    for marker in PT_CONTROL_MARKERS:
        if marker in bot:
            failures.append(f'bot.py still has PT control marker: {marker}')
    return failures


def check_no_fake_style_seed() -> list[str]:
    failures = []
    se = (ROOT / 'style_engine.py').read_text(encoding='utf-8', errors='replace')
    if '_ensure_default_style' in se:
        failures.append('style_engine still has _ensure_default_style fake seed')
    if 'kkkk": 5' in se or "'kkkk': 5" in se:
        failures.append('style_engine still seeds fake kkkk count=5')
    if 'def has_learned_style' not in se:
        failures.append('style_engine missing has_learned_style gate')
    if 'def get_learned_style_summary' not in se:
        failures.append('style_engine missing get_learned_style_summary API')
    return failures


def check_no_legacy_proactivity_second_engine() -> list[str]:
    failures = []
    bot = (ROOT / 'bot.py').read_text(encoding='utf-8', errors='replace')
    if 'await autonomous_routine_v36(application)' not in bot:
        failures.append('bot.autonomous_routine is not routed exclusively to the canonical engine')
    if 'determine_proactive_prompt(' in bot:
        failures.append('bot.py still calls the legacy proactive prompt engine')
    if 'Chance espontânea: ~18%' in bot:
        failures.append('legacy spontaneous audio chance still present in bot.py')
    return failures


def check_no_eventos_runtime() -> list[str]:
    failures = []
    for fname in ('proactivity_service.py', 'prompts.py', 'bot.py'):
        text = (ROOT / fname).read_text(encoding='utf-8', errors='replace')
        if 'EVENTOS_COTIDIANO' in text and fname != 'prompts.py':
            if 'random.choice(EVENTOS' in text or 'choice(EVENTOS_COTIDIANO)' in text:
                failures.append(f'{fname} still chooses from EVENTOS_COTIDIANO')
    return failures


def check_style_evidence_behavioral() -> list[str]:
    """Behavioral contract: bland messages must not create fake learned style."""
    failures = []
    try:
        from db import DatabaseManager
        from style_engine import StyleEngine

        with tempfile.TemporaryDirectory() as td:
            db = DatabaseManager(db_path=Path(td) / 'audit.db')
            eng = StyleEngine(db=db)

            # Contract 1: Fresh DB + 2 bland messages → no fake style
            eng.processar_mensagem_patrick("oi tudo bem")
            eng.processar_mensagem_patrick("sim tudo certo")

            estilo = db.get_estilo()
            risada_val = estilo.get("risada", {}).get("valor", "")
            emojis_val = estilo.get("emojis_favoritos", {}).get("valor", "")
            girias_val = estilo.get("girias", {}).get("valor", "")

            # Bland messages have no kkkk/haha/rsrs, no emojis, no slang
            if risada_val:
                risada_exemplos = estilo.get("risada", {}).get("exemplos", {})
                if isinstance(risada_exemplos, dict) and sum(risada_exemplos.values()) == 0:
                    failures.append(f'bland msgs produced fake risada: {risada_val!r}')
            if emojis_val:
                failures.append(f'bland msgs produced fake emojis: {emojis_val!r}')
            if girias_val:
                failures.append(f'bland msgs produced fake girias: {girias_val!r}')

            # Contract 2: get_learned_style_summary must not mention defaults
            summary = eng.get_learned_style_summary()
            for fake in ['kkkk', '🥰', '💕', '❤️', '🥺', '🙈', 'trampo', 'codar', 'bora']:
                if fake in summary:
                    failures.append(f'learned_style_summary contains default {fake!r} without evidence')

            # Contract 3: Style prompt injection must not mention defaults
            injection = eng.get_style_prompt_injection()
            for fake in ['kkkk', '🥰', '💕', '❤️', '🥺', '🙈', 'trampo', 'codar', 'bora']:
                if fake in injection:
                    failures.append(f'style_prompt_injection contains default {fake!r} without evidence')

    except Exception as e:
        failures.append(f'style_evidence_behavioral error: {e}')
    return failures


def check_canon_ownership() -> list[str]:
    """Runtime self-modification must be absent."""
    failures = []
    if (ROOT / 'auto_patcher.py').exists():
        failures.append('auto_patcher.py still exists')
    bot = (ROOT / 'bot.py').read_text(encoding='utf-8', errors='replace')
    for handler in ('edit_command', 'rollback_command', 'patches_command'):
        if handler in bot:
            failures.append(f'{handler} still exists in Telegram runtime')
    return failures


def check_urgency_distress_coverage() -> list[str]:
    """Urgency classifier must not put distress messages in LOW."""
    failures = []
    try:
        from response_availability import classify_urgency
        distress_cases = [
            ('me ajuda', 'HIGH'),
            ('acidente', 'HIGH'),
            ('hospital', 'HIGH'),
            ('tô mal', 'HIGH'),
            ('passei mal', 'HIGH'),
            ('socorro', 'CRITICAL'),
        ]
        for msg, expected_min in distress_cases:
            result = classify_urgency(msg)
            rank = {'LOW': 0, 'NORMAL': 1, 'HIGH': 2, 'CRITICAL': 3}
            if rank.get(result, 0) < rank.get(expected_min, 0):
                failures.append(f'classify_urgency({msg!r}) = {result}, expected >= {expected_min}')
    except Exception as e:
        failures.append(f'urgency_distress error: {e}')
    return failures


def check_system_prompt_sites() -> list[dict]:
    call_sites = []
    for path in _iter_runtime_py():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding='utf-8', errors='replace')
        for m in SYSTEM_PROMPT_NAMES.finditer(text):
            call_sites.append({
                'file': rel, 'kind': 'constant',
                'snippet': text[m.start():m.start() + 48].replace('\n', ' '),
            })
        for m in ROLE_SYSTEM.finditer(text):
            call_sites.append({
                'file': rel, 'kind': 'role=system',
                'line': text[:m.start()].count('\n') + 1,
            })
    return call_sites


def main() -> int:
    contracts = {
        'forbidden_legacy_tokens': check_forbidden_tokens(),
        'deprecated_prompts_not_owner': check_prompts_py_not_owner(),
        'safecore_clean_start_gating': check_safecore_gate(),
        'web_vision_data_only': check_web_vision_data_only(),
        'control_language_en': check_control_language(),
        'no_fake_learned_style_init': check_no_fake_style_seed(),
        'no_legacy_proactivity_second_engine': check_no_legacy_proactivity_second_engine(),
        'no_runtime_eventos_owner': check_no_eventos_runtime(),
        'style_evidence_behavioral': check_style_evidence_behavioral(),
        'canon_ownership': check_canon_ownership(),
        'urgency_distress_coverage': check_urgency_distress_coverage(),
    }
    call_sites = check_system_prompt_sites()

    failed_keys = [k for k, v in contracts.items() if v]
    status = 'passed' if not failed_keys else 'failed'

    report = {
        'release': '3.7.0-round3-prompt-authority',
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'contracts': {k: ('pass' if not v else v) for k, v in contracts.items()},
        'system_prompt_sites': call_sites[:200],
        'failed_contracts': failed_keys,
        'status': status,
    }
    out = ROOT / 'data' / 'prompt_authority_validation.v370.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(out)
    print('status=', status)
    if failed_keys:
        for k in failed_keys:
            print('FAIL', k, contracts[k], file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
