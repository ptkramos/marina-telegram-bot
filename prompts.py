"""Deprecated compatibility shim — NOT a biographical authority (v3.7.0).

Production identity/canon lives in World Bible + WorldContextBuilder / SafeCore.
This module only keeps thin wrappers so old imports do not resurrect pre-v3.6 canon.
"""
from __future__ import annotations

import warnings

from prompt_policy import get_daypart, get_temporal_greeting, build_safe_core_prompt
from visual_profile import visual_profile, MARINA_VISUAL_DNA_BASE, build_flux_prompt

# Explicitly retired — kept as empty/raising so silent reintroduction fails loudly in tests.
EVENTOS_COTIDIANO = ()  # retired: no random invented daily events

# Soft marker so audits can detect accidental reintroduction of the monolith.
MARIN_SYSTEM_PROMPT = None  # retired; use context_builder / build_safe_core_prompt


def build_autonomous_decision_prompt(custom_situation: str = '') -> str:
    """Grounded autonomous instruction only — never invents random events."""
    warnings.warn(
        'build_autonomous_decision_prompt is deprecated; Living World proactivity is authoritative.',
        DeprecationWarning,
        stacklevel=2,
    )
    daypart = get_daypart()
    situacao = custom_situation.strip() or (
        f'Daypart is {daypart}. Send a short affectionate check-in to Patrick. '
        'Do not invent a specific location, outfit, or fabricated daily event.'
    )
    return (
        f'{situacao}\n\n'
        'Respond as Marina in natural Brazilian Portuguese, 1–3 short bubbles.\n'
        'Format:\n'
        'ACAO: [Telegram text; use newlines between bubbles] | FOTO_PROMPT: '
        '[English FLUX tags only if sending a photo of yourself, else empty]'
    )


SD_BASE_PROMPT_PREFIX = f'{MARINA_VISUAL_DNA_BASE}, '

__all__ = [
    'MARIN_SYSTEM_PROMPT',
    'EVENTOS_COTIDIANO',
    'get_daypart',
    'get_temporal_greeting',
    'build_autonomous_decision_prompt',
    'build_flux_prompt',
    'build_safe_core_prompt',
    'SD_BASE_PROMPT_PREFIX',
    'MARINA_VISUAL_DNA_BASE',
]
