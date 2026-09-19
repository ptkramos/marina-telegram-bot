# Canonical runtime — Marina 3.7.0

As releases aprovadas até 3.7.0 formam um único pipeline de produção. World Bible, WorldState, Memory Intelligence, Planner, Open Loops, Smart Reminders, Knowledge/Privacy, Calendar/Academic, Relationship World, Camera World, Response Rhythm e Response Availability não são selecionados pelo `.env`.

## Kill switches operacionais

- `PROACTIVITY_ENABLED`: pausa novas iniciativas autônomas.
- `STORY_SEED_LIBRARY_ENABLED`: limita a geração de novas stories ao núcleo curado.
- `MEMORY_CONSOLIDATION_ENABLED`: pausa o job de consolidação.
- `SESSION_REFLECTION_ENABLED`: pausa o job de reflexão.
- `MEMORY_HYGIENE_ENABLED`: pausa o job de higiene de memória.
- `WORLD_HYGIENE_ENABLED`: pausa mutações de higiene do mundo.
- `CRITICAL_WAKE_POLICY_ENABLED`: controla se urgência crítica pode acordar Marina.

Nenhum deles ativa um motor antigo quando desligado.

## Providers e capacidades externas

Permanecem configuráveis: imagem/manutenção, voz e prosódia, visão, LoRAs, contexto real, feriados e consulta de lugares. Uma indisponibilidade deve produzir degradação segura, sem mudar identidade, memória, mundo ou política conversacional.

## Diagnóstico

`REAL_USAGE_TELEMETRY_ENABLED` e `RESPONSE_AVAILABILITY_DEBUG` controlam observabilidade. Não alteram a autoridade funcional do runtime.

## Recursos removidos

`/edit`, `/rollback`, `/patches`, `SAFE_PATCHER_ENABLED` e `auto_patcher.py` não fazem parte do runtime. A migration e a tabela histórica de patches permanecem inertes para não arriscar bancos existentes.
