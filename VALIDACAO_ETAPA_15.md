# Release 3.7.0 · etapa 15 — Response Availability & Human Latency

Implementação conforme [PLANO_MARINA_V3_7_LIVING_INTELLIGENCE.md](PLANO_MARINA_V3_7_LIVING_INTELLIGENCE.md)
e [HANDOFF_COMPOSER_MARINA_3_7_0_RESPONSE_AVAILABILITY.md](HANDOFF_COMPOSER_MARINA_3_7_0_RESPONSE_AVAILABILITY.md).

**Não reabre v3.6.** Flags de enforcement permanecem **OFF** por padrão. O gate
local da etapa 15 passou; o soak real de sete dias ainda não começou.

## O que entrou

- `migrations/016_response_availability.sql` — batches / items / telemetry
- `response_availability.py` — policy determinística (REPLY_NOW / REPLY_BRIEFLY / DEFER)
- `pending_response.py` — repositório + claim/lease + recovery + service gate
- `bot.py` — gate pós-debounce, job `pending_response_routine`, startup recover
- `response_rhythm.py` — hint `brief_due_to_availability`
- Flags em `config.py` / `.env.example` (defaults false)
- Matriz: `docs/production_flags_3_7_0.md`
- Soak helper: `scripts/build_soak_report_3_7_0.py`

## Validação executada pelo Codex

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage15_validation.py
```

Artefatos esperados:
- `data/response_availability_validation.v370.json`
- `data/response_availability_simulation.v370.json` (24h / 72h / 7d)

Resultado de 18/09/2026: **337 testes, 0 falhas, 0 erros, 0 pulos**. A primeira
execução no sandbox teve três pulos em testes legados de LLM por erro de conexão;
a repetição autorizada com rede liberada passou sem pulos. O runner isolado fixa
as flags de regressão no baseline desligado, independentemente do `.env` real;
o perfil shadow e depois o enforcement foram verificados separadamente com
`scripts/run_production_shadow_smoke_3_7_0.py` em cópias do banco canônico:
cânon e perfil acadêmico presentes; shadow com dois replies imediatos e nenhum
lote; enforcement com defer em aula confirmada, merge urgente e envio simulado.
Nas simulações de
24h / 72h / 7d houve **0 perdas, 0 duplicações e 0 filas presas**, com
**1 / 3 / 7 overrides urgentes**. Maior espera simulada: 3h30 (abaixo do
guardrail de 11h do validador).

## Contratos cobertos nos testes unitários

- policy por atividade / stale → UNKNOWN fail-open
- critical override
- intake atômico (mensagem + batch + item), replay idempotente e lote SENDING congelado
- claim serializado + SENT libera slot; heartbeat mantém lease durante geração/envio
- lease expirado → UNKNOWN_DELIVERY (sem reenvio cego)
- startup recover + rollback force-ready com scheduler ainda ativo
- merge + urgent override → READY
- shadow mode não defere
- brief hint no rhythm

## Próxima fase

O `.env` está preparado com todas as flags 3.6/3.7.0 aprovadas e o bot segue
parado. Fazer smoke com o bot em execução e iniciar o soak real de sete dias. A validação
sintética não substitui essa observação em produção.
