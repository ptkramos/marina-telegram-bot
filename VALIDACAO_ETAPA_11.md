# Release 3.6.4 · etapa 11 — handoff de validação

O Gemini validou a grade canônica V2 em 18/09/2026: **274 testes, 0 falhas, 0 pulos** (`data/calendar_academic_validation.v364_grade_v2.json`). A validação anterior havia aprovado 271 testes (`data/calendar_academic_validation.v364.json`). O Codex revisou os resultados sem repetir a suíte, conforme combinado. Para reproduzir no Antigravity, na raiz do repositório:

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage11_validation.py
```

O comando executa a suíte isolada completa e salva `data/calendar_academic_validation.v364_grade_v2.json`. O Codex revisará esse resultado sem repetir os testes.
Antes da suíte, ele confere o SHA-256, os nove códigos/turmas, créditos,
horários e salas contra o CSV local em `data/external/puc_rio/2026_2/raw/`.
O CSV não é carregado no runtime e está fora do Git.

Casos novos: projeção da grade na fonte única Calendar/Events, conflito entre casting e aula, exceção por ocorrência, apresentação como evento datado, férias e dois anos de catch-up idempotente, sem avalanche de `life_events`, clima/feriado com TTL, WorldState durante aula, proteção de thread por compromisso futuro e remoção automática da proteção ao cancelar/desvincular.

Na correção da grade V2, o casting futuro do teste foi posto às 15h para não
colidir com `DSG1400` na quarta-feira. Com `ACADEMIC_LIFE_ENABLED`, a rotina
estática `university` deixa de propor presença na faculdade: somente o
CalendarWorld projeta aulas e respeita cancelamentos de ocorrências.

Ativação após validação e bootstrap canônico: `LIVING_WORLD_ENABLED=true`, `CALENDAR_CONTINUITY_ENABLED=true`, `ACADEMIC_LIFE_ENABLED=true`, `ACADEMIC_AUTO_TERM_GENERATION=true`. `REAL_CONTEXT_FETCH_ENABLED=true` é opcional e faz consultas limitadas a Open-Meteo e Nager.Date; falha de rede não cria observações fictícias. As datas de 2026.2 são oficiais da PUC-Rio; janelas futuras sem fonte institucional são simuladas e marcadas `SIMULATED_ACADEMIC`.

Depois da validação, com o bot parado, atualizar um banco já iniciado na grade anterior usando `& .\venv\Scripts\python.exe scripts\upgrade_academic_grade_v2.py`. O utilitário cria backup SQLite e recusa substituir curso alterado ou evento datado que referencie os IDs antigos.

### Ajuste de integração resolvido (idempotência de migração)
Na revisão do primeiro resultado, a recuperação de `duplicate column name` foi restringida à migration 012 e às sete colunas conhecidas de `eventos_pendentes`; outras falhas de schema continuam interrompendo a migração. O Gemini repetiu a suíte depois dessa alteração, com os 271 testes aprovados.

## Complemento Real-World Lookup + Feriados BR — pendente

O Gemini deve executar, com o mesmo ambiente local e sem expor credenciais:

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage11_lookup_validation.py
```

O resultado separado fica em `data/real_world_lookup_validation.v364.json`.
A suíte inclui contrato da Feriados API por respostas simuladas, fallback
Nager.Date, cache, escopos nacional/estadual/municipal/facultativo, prioridade
do calendário PUC e lookup pontual de horários com fontes oficiais. A chave
fica apenas em `.env`, sob `FERIADOS_API_KEY`, e as duas flags novas começam
desligadas. O runtime não precisa de MCP nem de pesquisas periódicas de lugares.
