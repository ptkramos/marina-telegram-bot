# Relatório de Validação Independente: Marina v3.6.7 (Stage 14)
**Data:** 18 de Setembro de 2026  
**Auditor Independente:** Gemini Agentic Assistant  
**Alvo:** Marina Release 3.6.7 — Tuning, Reflection & Hygiene (Stage 14)  
**Status do Gate:** ✅ **PODE AVANÇAR**

---

## 1. Ambiente e Baseline Auditado

- **Commit Base:** `96da77b` (`feat(camera): implement camera world continuity and validate release 3.6.6 stage 13`)
- **Working Tree:** Modificações da v3.6.7 aplicadas localmente em arquivos de configuração, schema, modelo e testes.
- **Python:** 3.10.11 (`c:\Arquivos\GitHub\marin-telegram-bot\venv\Scripts\python.exe`)
- **Sistema Operacional / Shell:** Windows 11 / PowerShell
- **Database:** SQLite 3 via `DatabaseManager` (`migrations/015_world_hygiene.sql`, schema version 15)

---

## 2. Comandos Executados na Auditoria

1. **Suíte Completa de Testes Isolados:**
   ```powershell
   .\venv\Scripts\python.exe tests/run_isolated.py
   ```
   *Resultado:* `Ran 317 tests in 222.828s — OK` (0 falhas, 0 erros, 0 skipped).

2. **Simulações de Durabilidade / Soak de Higiene:**
   ```powershell
   .\venv\Scripts\python.exe scripts/run_world_hygiene_simulation.py 30 90 365
   ```
   *Resultado:* Execução bem-sucedida gerando `data/world_hygiene_simulation.v367.json`.

3. **Validação Externa Automatizada (Stage 14):**
   ```powershell
   .\venv\Scripts\python.exe scripts/run_external_stage14_validation.py
   ```
   *Resultado:* Execução oficial com saída `data/world_hygiene_validation.v367.json`, exit code 0.

4. **Verificação Direta de Módulos Críticos:**
   ```powershell
   .\venv\Scripts\python.exe -m unittest tests.test_world_hygiene_v367
   .\venv\Scripts\python.exe -m unittest tests.test_camera_world_v366 tests.test_calendar_academic_v364 tests.test_relationship_world_v365 tests.test_knowledge_privacy tests.test_response_rhythm
   ```
   *Resultado:* 8/8 novos testes da v3.6.7 aprovados; 54/54 testes de subsistemas adjacentes aprovados com 0 erros.

5. **Verificação de Rollback / Comportamento com Feature Flag Desligada:**
   *Resultado:* Com `WORLD_HYGIENE_ENABLED=False`, `WorldHygiene.run_cycle()` retorna imediatamente `{'status': 'disabled', 'success': False}` sem mutações no banco.

---

## 3. Resultados dos Testes da Suíte Completa

- **Total de testes executados:** 317 (incremento de 8 testes frente aos 309 da v3.6.6)
- **Falhas:** 0
- **Erros:** 0
- **Skipped:** 0
- **Status:** **PASS**

---

## 4. Resultados da Simulação de Durabilidade (Soak Test)

| Métrica | 30 Dias | 90 Dias | 365 Dias |
| :--- | :--- | :--- | :--- |
| **Total de Eventos Ativos** | 3 | 10 | 40 |
| **Eventos Arquivados** | 0 | 0 | 0 |
| **Open Threads** | 1 | 1 | 1 |
| **Duplicates Marcados** | 0 | 0 | 0 |
| **Canon Locked Characters (Início)** | 10 | 10 | 10 |
| **Canon Locked Characters (Fim)** | 10 | 10 | 10 |
| **Canon Drift Detectado** | **NÃO (false)** | **NÃO (false)** | **NÃO (false)** |
| **Event Looping Detectado** | **NÃO (false)** | **NÃO (false)** | **NÃO (false)** |
| **Status Geral** | **PASS** | **PASS** | **PASS** |

---

## 5. Auditoria Detalhada dos Contratos de Higiene

### 5.1 Proteção Canônica e Imunidade de Preferências Core
- **Inspeção:** O método `decay_current_interests()` filtra explicitamente `WHERE preference_type='current_interest' AND canon_locked=0`. O método auxiliar `interest_status()` retorna `None` caso `preference_type != 'current_interest'` ou `canon_locked=1`.
- **Validação:** No teste `test_interest_lifecycle_and_core_never_decays`, uma preferência canônica (`core_like`, `canon_locked=1`, pop) com 200 dias de inatividade permaneceu com `strength=1.0` e `active=1`.
- **Drift de Cânone:** Inalterado (10/10 personagens canônicos preservados em 30d, 90d e 365d).

### 5.2 Ciclo de Vida e Decaimento de Interesses Efêmeros
- **Inspeção:** Interesses temporários passam pelo ciclo `ACTIVE` (< 14 dias) -> `FADING` (14 a 45 dias) -> `DORMANT` (>= 45 dias).
- **Preservação Autobiográfica:** Interesses dormentes recebem `active=0` e `strength=0.15`, mas **nunca são deletados** da tabela `character_preferences`. Isso preserva o registro autobiográfico de que Marina um dia teve aquele interesse.
- **Proteção de Prompt Context:** O arquivo `world_context.py` foi atualizado para conter a restrição `AND NOT (p.preference_type='current_interest' AND p.strength < 0.35)`, garantindo que interesses enfraquecidos ou dormentes não poluam o prompt do LLM.
- **Reativação Explícita:** Se um interesse dormente for citado/reforçado via `SocialWorld.reinforce_preference()`, o campo `active=1` é restaurado com recálculo de força.

### 5.3 Proteção de Story Threads e Dormência
- **Inspeção:** `review_thread_dormancy()` aciona `StoryEngine.quiet_old_threads()`, mantendo o teto de dias (`STORY_THREAD_DORMANT_DAYS=7`).
- **Imunidade de Threads Especiais:** Threads dos tipos `academic` ou `professional`, ou com flag `metadata_json.protected=1`, são explicitamente ignoradas por processos destrutivos e jamais são compactadas ou abandonadas inadvertidamente.

### 5.4 Revisão de Promoções (NPCs e Lugares)
- **Inspeção:** `review_promotions()` busca menções com dias distintos (`COUNT(DISTINCT substr(occurred_at,1,10)) >= threshold`).
- **Garantia Anti-Alucinação:** O módulo **apenas marca** como `PROMOTABLE` (registrando log e atualizando `usage_rules_json['promotion_status'] = 'PROMOTABLE'`). Ele **não auto-promove** de forma ambígua nem inventa novos personagens/locais. Cânones nunca são re-promovidos.

### 5.5 Deduplicação de Eventos
- **Inspeção:** `dedup_life_events()` agrupa estritamente por `(source_type, event_type, title, event_at) HAVING n > 1`.
- **Soft-Mark:** Eventos duplicados não são removidos do banco imediatamente; recebem `resolved=1`, `share_worthy=0` e `metadata_json.duplicate_of = keep_id`, preservando a rastreabilidade e prevenindo merges incorretos de eventos similares mas não idênticos.

### 5.6 Compactação de Histórico de Vida e Proveniência
- **Inspeção:** `compact_event_history()` move eventos com mais de 90 dias (`EVENT_COMPACTION_DAYS`), `resolved=1` e `importance <= 0.35` para a tabela `life_events_archive`.
- **Proteções Estritas:** Não compacta eventos:
  - Canônicos ou com `importance >= 0.7`.
  - Vinculados a threads abertas ou dormentes.
  - Com desdobramentos causais (`consequence_of_event_id`).
  - Vinculados a itens de conhecimento (`knowledge_items`) ou compartilhamentos (`knowledge_shares`).
  - Vinculados a compromissos pendentes futuros.
- **Idempotência:** A compactação é 100% idempotente; execuções repetidas não duplicam registros no arquivo.

### 5.7 Comando Operacional `/worlddebug` e Segurança
- **Inspeção de `bot.py` e `world_hygiene.py`:**
  - Exige autenticação (`is_authorized`).
  - Apaga imediatamente o comando digitado pelo usuário.
  - Retorna contagens agregadas (número de threads por tipo, estados, total de itens de privacidade por nível, contadores de higiene).
  - **Zero vazamento:** Não expõe tokens, prompts, chains-of-thought, thinking blocks, nem o corpo confidencial de memórias/segredos.
  - A mensagem gerada é auto-deletada após 20 segundos.

### 5.8 Ritmo Conversacional e Naturalidade (Response Rhythm)
- **Inspeção:** Validação cruzada confirmando que o sistema de respostas não possui arquitetura fragmentada ou múltiplos planejadores conflitantes.
- O prompt injeta orientações explícitas: *"Optimize for the next conversational turn"*, *"Do not restate obvious user facts or cover every topic"*, e *"World context informs what you may say; it creates no obligation"*.

---

## 6. Verificação de Regressão em Subsistemas Anteriores

- **Knowledge Privacy (Stage 10):** APROVADO — Isolamento por nível de privacidade e subject registry mantidos intactos.
- **Calendar & Academic Life (Stage 11):** APROVADO — Integração de grade horária acadêmica, continuidade de datas e cálculo local respeitados.
- **Relationship Culture (Stage 12):** APROVADO — Dinâmica relacional e evidências sociais funcionando sem conflitos.
- **Camera World Continuity (Stage 13):** APROVADO — Contexto visual e fotográfico preservado sem degradação.

---

## 7. Classificação de Bugs e Problemas

- **P0 (Bloqueador Crítico):** 0
- **P1 (Severo / Regressão Grave):** 0
- **P2 (Melhoria Menor / Aviso Cosmético):** 0

---

## 8. Decisão do Gate

```text
P0 = 0
P1 = 0
full regression = green (317/317)
30d = green
90d = green
365d = green
canon drift = 0
event looping = 0
core preferences protegidas = sim
protected threads preservadas = sim
dedup não funde eventos distintos = sim
compaction não perde provenance/privacy/retrieval = sim
flag OFF preserva comportamento anterior = sim
```

**Conclusão:** O Release 3.6.7 atende integralmente a todos os critérios de aceitação, testes de contrato, robustez matemática de higienização e segurança de rollback. A iniciativa **Living World v3.6** está consolidada e concluída com êxito.

**GATE:** **✅ PODE AVANÇAR** para `v3.7.0 — Response Availability & Human Latency`.
