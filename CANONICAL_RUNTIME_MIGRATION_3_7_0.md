# Migração para Canonical Runtime — Marina 3.7.0

**Início:** 19/09/2026  
**Status:** CONCLUÍDO — PRONTO PARA O SOAK  
**Regra:** preservar todos os patches já validados no soak.

Este arquivo é o checkpoint operacional da remoção do runtime legado. Atualizar após cada etapa antes de avançar.

## Objetivo

- Remover `/edit`, rollback e histórico de patches do runtime do Telegram.
- Impedir que flags antigas restaurem caminhos anteriores às releases aprovadas.
- Tornar World Bible, WorldState, Planner, Memory Intelligence, Knowledge/Privacy, Calendar/Academic, Relationship, Camera World, Response Rhythm e Response Availability o único caminho de produção.
- Manter somente configurações de providers, tuning, telemetria e kill switches cuja desativação apenas pause uma capacidade.

## Classificação inicial

### Canonicalizar

`SMART_MEMORY_ENABLED`, `MEMORY_INTELLIGENCE_ENABLED`, `PLANNER_ENABLED`, `EMOTIONAL_STATE_ENABLED`, `PENDING_EVENTS_ENABLED`, `OPEN_LOOPS_ENABLED`, `SMART_REMINDERS_ENABLED`, `LIVING_WORLD_ENABLED`, `RESPONSE_RHYTHM_ENABLED`, `KNOWLEDGE_PRIVACY_ENABLED`, `RELATIONSHIP_WORLD_ENABLED`, `CAMERA_WORLD_CONTINUITY_ENABLED`, `RESPONSE_AVAILABILITY_ENABLED`, `HUMAN_REPLY_LATENCY_ENABLED`, `PENDING_CONVERSATION_BATCHING_ENABLED`, `CALENDAR_CONTINUITY_ENABLED`, `ACADEMIC_LIFE_ENABLED`, `ACADEMIC_AUTO_TERM_GENERATION`, `STYLE_ENGINE_V2_ENABLED`, `RESPONSE_VERBOSITY_RETRY_ENABLED`.

### Manter como kill switch operacional

`PROACTIVITY_ENABLED`, `STORY_SEED_LIBRARY_ENABLED`, `MEMORY_CONSOLIDATION_ENABLED`, `SESSION_REFLECTION_ENABLED`, `MEMORY_HYGIENE_ENABLED`, `WORLD_HYGIENE_ENABLED`, `CRITICAL_WAKE_POLICY_ENABLED`.

O caminho OFF destes switches deve apenas pausar geração/job ou proteger o sono; nunca chamar arquitetura antiga.

### Manter como provider/capacidade externa

`PHOTO_PROVIDER_MAINTENANCE`, `DUAL_VOICE_ENABLED`, `VOICE_PROSODY_ENABLED` e capacidades de prosódia, `REAL_CONTEXT_FETCH_ENABLED`, `FERIADOS_API_ENABLED`, `REAL_WORLD_PLACE_LOOKUP_ENABLED`, `VISION_ENABLED`, `IPHONE_LORAS_ENABLED`.

### Manter como diagnóstico

`REAL_USAGE_TELEMETRY_ENABLED`, `RESPONSE_AVAILABILITY_DEBUG`.

### Excluir

`SAFE_PATCHER_ENABLED` e toda a cadeia `/edit`, `/rollback`, `/patches`, AutoPatcher e healthcheck associado.

## Progresso

- [x] Roadmap lido e comparado com o runtime.
- [x] Inventário inicial: 40 flags booleanas em `config.py`.
- [x] Fallbacks prioritários encontrados em `bot.py`, `context_builder.py`, `pending_response.py`, `world_context.py`, `world_state.py` e serviços auxiliares.
- [x] Remover handlers, import, flag e healthcheck do AutoPatcher no runtime.
- [x] Impedir que 20 flags centrais sejam lidas do `.env`; os valores agora são invariantes canônicas.
- [x] Remover o fallback de prompt biográfico/SafeCore do caminho de construção de prompt.
- [x] Remover o fallback do Memory Retriever antigo.
- [x] Tornar Planner e Response Rhythm caminhos obrigatórios no chat e nas fotos recebidas.
- [x] Tornar Camera World obrigatória quando o provider de fotos estiver disponível.
- [x] Tornar Response Availability + latência + batching um único pipeline, sem shadow/rollback para resposta imediata.
- [x] Substituir todas as leituras das 20 flags canônicas no código de produção por invariantes; mudanças no `.env` ou em marcadores de compatibilidade não alteram mais o runtime.
- [x] Remover todos os blocos `if not True` que continham fallback ou desligavam capacidades; wrappers `if True` puramente estruturais restantes são inertes e não selecionam comportamento.
- [x] Limpar `.env`, `.env.example`, preflight e documentação.
- [x] Excluir `auto_patcher.py` e `tests/test_auto_patcher.py`; adaptar auditorias para exigir ausência de self-edit.
- [x] Atualizar testes de Response Rhythm e Response Availability, removendo contratos de flag OFF, shadow e rollback.
- [x] Rodar a primeira regressão completa: 401 testes, 8 falhas, 43 erros e 3 ignorados.
- [x] Corrigir validação fail-closed do payload de memória e preservar emoção, open loops e reconfirmação no World Context canônico.
- [x] Atualizar fixtures de World Bible/vida acadêmica e contratos que ainda esperavam flags OFF; baterias focadas aprovadas.
- [x] Adaptar contratos históricos à base canônica e corrigir regressões reais.
- [x] Regressão final: 401 testes aprovados, 3 ignorados por desenho.
- [x] Compilação, auditoria de Prompt Authority e preflight aprovados.
- [x] Live gate: Telegram read-only, LLM, vozes e desculpa dinâmica de foto aprovados; GPU aceita em manutenção.
- [x] Startup gate: 26 PASS, 0 WARN, 0 FAIL; cinco jobs registrados sem envio ao Telegram.
- [x] Startup real confirmado no Telegram às 12:44:47; encerramento controlado às 12:45:16 para deixar o BAT pronto para uso.

## Próximo ponto exato

Abrir `run_local.bat` e iniciar o novo soak. O processo da Marina está intencionalmente parado; somente os dois processos Python 3.13 alheios ao projeto permanecem ativos. Durante o soak, registrar novos achados no `RELATORIO_SOAK_MARINA_3_7_0.md` sem reativar flags ou fallbacks de release.
