# Validação — Prompt Authority Cleanup Round 2 (pre-soak 3.7.0)

Conforme [HANDOFF_COMPOSER_3_7_0_PROMPT_AUTHORITY_CLEANUP_ROUND2.md](HANDOFF_COMPOSER_3_7_0_PROMPT_AUTHORITY_CLEANUP_ROUND2.md)
e [REVISAO_TECNICA_MARINA_3_7_0V2_PROMPT_AUTHORITY.md](REVISAO_TECNICA_MARINA_3_7_0V2_PROMPT_AUTHORITY.md).

**Não iniciar soak real até Codex validar este Round 2.**

## Mudanças Round 2

- SafeCore gated by `is_canonical_runtime_ready` (no stale memory/history/style pre-clean)
- Web/vision data-only via `format_web_evidence` / `format_vision_evidence` + `DATA_CHANNEL_POLICY_EN`
- Reminder turn constraints EN in `prompt_policy`
- AutoPatcher: `prompts.py` removed from catalog; refuse unknown/deprecated targets
- StyleEngine: no fake learned seed; injection only after real samples
- LW OFF: autonomous legacy second engine disabled
- `scripts/audit_prompt_authority.py` — multi-contract, no false-green
- `scripts/build_validation_archive.py` — clean allowlist zip
- memory_cli age from birth_date; admin voice defaults neutral

## Como validar

```powershell
& .\venv\Scripts\python.exe scripts\audit_prompt_authority.py
& .\venv\Scripts\python.exe scripts\build_validation_archive.py
& .\venv\Scripts\python.exe -m unittest tests.test_prompt_authority_v370 tests.test_style_engine tests.test_auto_patcher -v
& .\venv\Scripts\python.exe tests\run_isolated.py
```

Composer: **implementation complete / awaiting independent Codex validation.**
