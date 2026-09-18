# Release 3.6.4 · etapa 11 — handoff de validação

Esta implementação não foi testada pelo Codex, conforme combinado. Para o Gemini no Antigravity, na raiz do repositório:

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage11_validation.py
```

O comando executa a suíte isolada completa e salva `data/calendar_academic_validation.v364.json`. O Codex revisará esse resultado sem repetir os testes.

Casos novos: projeção da grade na fonte única Calendar/Events, conflito entre casting e aula, exceção por ocorrência, apresentação como evento datado, férias e dois anos de catch-up idempotente, sem avalanche de `life_events`, clima/feriado com TTL, WorldState durante aula, proteção de thread por compromisso futuro e remoção automática da proteção ao cancelar/desvincular.

Ativação após validação e bootstrap canônico: `LIVING_WORLD_ENABLED=true`, `CALENDAR_CONTINUITY_ENABLED=true`, `ACADEMIC_LIFE_ENABLED=true`, `ACADEMIC_AUTO_TERM_GENERATION=true`. `REAL_CONTEXT_FETCH_ENABLED=true` é opcional e faz consultas limitadas a Open-Meteo e Nager.Date; falha de rede não cria observações fictícias. As janelas de semestre são convenções do projeto, não calendário oficial da PUC-Rio. O currículo futuro é híbrido e autoral.
