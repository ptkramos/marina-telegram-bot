# HANDOFF Codex — Marina 3.7.0 Response Availability

**De:** Composer (implementação)  
**Para:** Codex (validação independente / gate)  
**Base:** v3.6 Living World fechada; **não reabrir 3.6 nem implementar 3.7.1+**.

## O que foi entregue

| Área | Arquivos |
|------|----------|
| Schema 16 | `migrations/016_response_availability.sql` |
| Policy | `response_availability.py` |
| Persistência / claim / recover | `pending_response.py` |
| Integração | `bot.py` (gate, `pending_response_routine`, `post_init` recover+job) |
| Rhythm brief | `response_rhythm.select_policy(..., availability_budget_hint=)` |
| Config | `config.py`, `.env.example` — defaults **OFF** |
| Testes | `tests/test_response_availability_v370.py` |
| Stage 15 | `scripts/run_external_stage15_validation.py`, `run_response_availability_simulation.py` |
| Flags matrix | `docs/production_flags_3_7_0.md` |
| Artefatos | `VALIDACAO_ETAPA_15.md`, `data/feedback/real_usage_3_7_0.md`, soak builder |

## Contratos críticos a auditar

1. **Nunca perder mensagem do usuário** — DEFER persiste `conversas` + batch + item na mesma transação.
2. **Nunca duplicar reply normal** — claim atômico; SENDING+lease expirado → `UNKNOWN_DELIVERY` (sem reenvio cego).
3. **Fail-open** — erro de policy → legacy imediato.
4. **Shadow** — `RESPONSE_AVAILABILITY_ENABLED` sem latency: telemetria, sem DEFER.
5. **Enforce** — precisa dos três: availability + latency + batching.
6. **UNKNOWN / stale WorldState** — não inventa atividade; delays curtos.
7. **ROUTINE_PROBABILITY** — sem claim factual; delay capped.
8. **Um batch aberto para intake** — SENDING congela seus itens e libera o `active_key`; chegada concorrente cria sucessor.
9. **Rollback** — flags OFF → job permanece ativo, `force_ready_on_rollback` e drain no próximo tick.
10. **v3.6 intocada** em autoridades (Calendar > WorldState > routine).

## Como validar

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage15_validation.py
```

Baseline pré-3.7.0: 317 testes. Qualquer regressão deve ser explicada.

## Gate

O primeiro relatório de simulação do Composer aceitava esperas excessivas e não
serviu como gate. Após esta revisão, o validador exige os três cenários,
sem perda/duplicação, com prazo de espera, urgência e sucessor em voo verificados.
O usuário pediu que Codex executasse a validação: **337 testes, 0 falhas,
0 erros, 0 pulos** na execução com rede liberada; simulações 24h / 72h / 7d
PASS. Próximo passo: shadow → enforce → soak real de 7 dias. O soak não foi
iniciado pela validação sintética.
