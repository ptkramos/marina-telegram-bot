# Release 3.6.7 · etapa 14 — Tuning, Reflection & Hygiene

Implementação conforme [HANDOFF_MARINA_3_6_7_TUNING_REFLECTION_HYGIENE.md](HANDOFF_MARINA_3_6_7_TUNING_REFLECTION_HYGIENE.md).

## Conversational Naturalness

**Confirmado sem reimplementação:** `response_rhythm.py` já aplica
`OPTIMIZE FOR THE NEXT TURN`, orçamento de bolhas via
`RESPONSE_DEFAULT_MAX_BUBBLES`, evita cobrir todos os tópicos, não força
pergunta no casual, e trata Living World como contexto sem obrigação de
mencionar. Regressão em `tests/test_world_hygiene_v367.py`
(`ConversationalNaturalnessConfirmTests`).

## O que entrou

- `migrations/015_world_hygiene.sql` — `life_events_archive` + `world_hygiene_log`
- `world_hygiene.py` — decay ACTIVE→FADING→DORMANT de `current_interest`,
  review de dormancy (reusa `StoryEngine.quiet_old_threads`), review
  PROMOTABLE de NPC/place (sem auto-promover ambíguo), dedup exato,
  compaction idempotente, `/worlddebug`
- Flags: `WORLD_HYGIENE_ENABLED` (+ thresholds de interesse/promoção/compaction)
- Integração opcional no ciclo de `memory_hygiene` quando Living World + flag

## Validação

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage14_validation.py
```

Artefatos:
- `data/world_hygiene_validation.v367.json`
- `data/world_hygiene_simulation.v367.json` (30d/90d)

Flag permanece **desligada** por padrão até ativação explícita.
