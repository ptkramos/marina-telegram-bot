# HANDOFF PARA GEMINI — VALIDAÇÃO INDEPENDENTE MARINA v3.6.7
## Tuning, Reflection & Hygiene

**Motivo deste handoff:** a implementação da v3.6.7 foi executada pelo Composer.  
Portanto, trate esta validação como **auditoria independente**: não confie apenas no resumo do implementador, nos testes que ele escreveu nem nos artefatos já marcados como `passed`.

A implementação reportada inclui:

```text
world_hygiene.py
migration 015
/worlddebug
WORLD_HYGIENE_ENABLED=false

scripts:
- run_external_stage14_validation.py
- run_world_hygiene_simulation.py

artefatos:
- data/world_hygiene_validation.v367.json
- data/world_hygiene_simulation.v367.json
- VALIDACAO_ETAPA_14.md
```

O Composer reportou:

```text
317 testes
0 falhas
30d OK
90d OK
sem canon drift
sem event looping
```

**Esses resultados devem ser reproduzidos, não assumidos.**

---

# 1. OBJETIVO DA AUDITORIA

Verificar se a v3.6.7 realmente implementa, sem regressões:

```text
- decay de current interests;
- dormancy / hygiene de Story Threads;
- revisão de NPC/place promotion;
- event dedup;
- compactação de event history;
- dashboard/debug;
- simulações longas;
- regressão de todas as etapas anteriores.
```

A v3.6.7 é uma etapa de **tuning/hygiene**.

Ela NÃO deve ter criado:

```text
- segundo sistema de memória;
- segundo Story Engine;
- segundo Planner;
- segundo Calendar;
- segundo WorldState;
- segundo Routine Engine;
- segunda camada de Reflection concorrente;
- nova autoridade canônica.
```

---

# 2. REGRA DA VALIDAÇÃO

Faça duas coisas separadamente:

```text
A. inspeção estática do código
B. execução real dos testes/simulações
```

Não considerar um item aprovado apenas porque existe teste verde escrito pelo Composer.

Sempre que possível:

```text
ler implementação
→ formular hipótese de falha
→ executar cenário independente
→ confirmar comportamento real
```

---

# 3. INSPEÇÃO ESTÁTICA OBRIGATÓRIA

Mapear primeiro:

```text
world_hygiene.py
migration 015
settings/config relevantes
story_engine.py
world state / repositories relacionados
memory / reflection relacionados
debug command
scripts de validação
testes novos da 3.6.7
```

Responder no relatório:

```text
- quais tabelas/colunas a migration 015 cria/altera;
- quais funções executam decay;
- quais funções revisam promotions;
- como dedup identifica duplicatas;
- como compaction decide o que é compactável;
- quais guards impedem compactação destrutiva;
- como /worlddebug obtém os dados;
- como WORLD_HYGIENE_ENABLED interfere no runtime.
```

---

# 4. FEATURE FLAG — TESTE CRÍTICO

Confirmar:

```text
WORLD_HYGIENE_ENABLED=false
```

por padrão.

Com flag OFF:

```text
- nenhum hygiene job deve alterar estado;
- nenhum interest deve decair;
- nenhuma promotion automática;
- nenhuma compaction automática;
- nenhum event dedup destrutivo extra;
- nenhuma mudança de comportamento inesperada.
```

Com flag ON:

```text
- somente os componentes planejados são ativados.
```

Teste explícito:

```text
mesmo banco inicial
→ executar ciclo com flag OFF
→ comparar estado

mesmo banco inicial
→ executar ciclo com flag ON
→ comparar somente mudanças esperadas
```

---

# 5. CURRENT INTEREST DECAY

## 5.1 Estados esperados

Validar a progressão reportada:

```text
ACTIVE
→ FADING
→ DORMANT
```

## 5.2 Casos mínimos

Testar:

```text
1. interest recente
→ permanece ACTIVE

2. interest sem reforço suficiente
→ vai para FADING

3. interest antigo sem reforço
→ vai para DORMANT

4. interest FADING recebe novo reinforcement
→ volta/permanece ACTIVE conforme regra

5. interest DORMANT recebe nova evidência válida
→ pode ser reativado

6. rodar hygiene duas vezes na mesma data
→ não decair duas vezes incorretamente
```

## 5.3 Proteção de preferências estáveis

Este é um teste de alta prioridade.

Garantir que NÃO entram no decay de `current interests`:

```text
- canon;
- dados biográficos;
- relações canônicas;
- curso/foco acadêmico;
- stable/core preferences;
- informações explicitamente marcadas como permanentes.
```

Criar caso real:

```text
core/stable preference antiga
+ vários dias/meses sem reinforcement
→ continua estável
```

Se uma preferência central virar `FADING/DORMANT`, classificar como **P1**.

---

# 6. STORY THREAD HYGIENE

A política anterior da v3.6 deve continuar funcionando.

## 6.1 Ciclo básico

Testar:

```text
OPEN antiga
→ DORMANT

DORMANT + nova evidência válida
→ OPEN novamente

RESOLVED
→ não reabre silenciosamente

ABANDONED
→ não reabre silenciosamente
```

## 6.2 Proteções

Confirmar que thread NÃO é abandonada por idade quando:

```text
thread_type = academic
thread_type = professional
has_future_commitment = true
protected = true
auto_abandonable = false
```

ou equivalentes reais usados no código.

## 6.3 Calendar como autoridade

Criar cenário:

```text
thread social
+ futuro compromisso confirmado em Calendar
→ thread protegida
```

Depois:

```text
compromisso concluído/cancelado
→ proteção atualizada/removida
```

Sem copiar um segundo calendário para metadata de forma divergente.

---

# 7. NPC / PLACE PROMOTION

## 7.1 Uma única aparição NÃO promove

Testar:

```text
novo lugar mencionado uma vez
→ candidate/discovered no máximo
→ não canonical

nova pessoa mencionada uma vez
→ não Social Graph NPC
```

## 7.2 DDGS / web lookup NÃO promove sozinho

Criar cenário:

```text
RealWorldLookup pesquisa restaurante X
→ resultado válido
→ X NÃO vira canonical place automaticamente
```

## 7.3 Pessoas reais

Confirmar que:

```text
docente real
funcionário
pessoa pública
prestador encontrado na web
```

não viram NPC ficcional apenas por aparecerem em fonte externa.

## 7.4 Reinforcement

Criar múltiplas evidências plausíveis suficientes para atingir o threshold.

Esperado:

```text
candidate
→ reinforced
→ PROMOTABLE
```

Se o design atual exige review/manual promotion:

```text
PROMOTABLE != PROMOTED automaticamente
```

Confirmar isso no código real.

---

# 8. EVENT DEDUP — TESTES INDEPENDENTES

Este é um dos pontos mais importantes.

## 8.1 Replay exato

```text
mesmo event_key/source_id
processado duas vezes
→ 1 evento
```

## 8.2 Provider retry

```text
provider entrega mesmo evento
→ retry
→ continua 1 registro
```

## 8.3 Lazy catch-up repetido

```text
catch-up A
catch-up A novamente
→ nenhuma duplicação
```

## 8.4 Restart

```text
evento processado
→ restart do processo
→ mesmo input reaparece
→ nenhuma duplicação
```

## 8.5 Duas fontes, mesma realidade

Criar caso equivalente:

```text
Calendar confirma compromisso X
Story/Conversation ingestion observa o mesmo compromisso X
```

Verificar se o sistema evita duplicação quando há chave/proveniência suficiente.

## 8.6 Parecidos, mas distintos

Muito importante:

```text
casting terça 10h
casting quinta 10h
```

NÃO podem ser fundidos apenas por similaridade.

Também testar:

```text
duas aulas da mesma disciplina em datas diferentes
dois treinos
dois convites
dois eventos com títulos parecidos
```

Se dedup semântico agressivo fundir eventos distintos, classificar como **P1**.

---

# 9. EVENT HISTORY COMPACTION

## 9.1 Compactável

Criar eventos:

```text
antigos
resolvidos
baixa importância
sem thread ativa
sem future commitment
sem open loop
sem privacy dependency atual
```

Esperado:

```text
compactáveis
```

## 9.2 NÃO compactável

Garantir proteção de:

```text
- OPEN thread;
- DORMANT protegida;
- evento com future commitment;
- evento referenciado por consequência ativa;
- Knowledge/Privacy source atual;
- relationship/shared history relevante;
- canon;
- hard-gated event;
- unresolved open loop.
```

## 9.3 Idempotência

```text
compaction run 1
compaction run 2
```

Segundo run não pode:
- apagar mais do que deveria;
- duplicar resumo;
- corromper links;
- mudar resultado de forma não determinística.

## 9.4 Provenance

Após compaction, verificar:

```text
source chain ainda reconstruível
thread/event relationship preservada
privacy metadata preservada
event IDs/references necessárias continuam válidas
```

## 9.5 Retrieval/context

Comparar antes/depois:

```text
consulta relevante sobre evento antigo
```

O sistema pode usar representação compacta, mas não deve perder o fato útil necessário.

Se compaction destruir contexto relevante, classificar como **P1**.

---

# 10. REFLECTION / MEMORY HYGIENE

Confirmar que a v3.6.7 **reutiliza** a infraestrutura existente.

Não deve existir:

```text
novo SessionReflector concorrente
novo Consolidator
segunda memória autobiográfica
```

Reflection/Hygiene pode revisar:

```text
current interests
event relevance
resolved loops
thread state
promotion candidates
duplicates
```

Mas NÃO pode:

```text
inventar evento
inventar memória
alterar canon
criar fato não observado
mudar privacy sem regra
```

Criar pelo menos um teste adversarial:

```text
nenhuma evidência nova
→ hygiene/reflection roda
→ nenhum novo life_event factual aparece
```

---

# 11. /WORLDDEBUG

Inspecionar e executar.

Deve mostrar, quando aplicável:

```text
current world state
active threads
dormant/protected threads
upcoming events
recent seeds
privacy metadata segura
narrative budget
current interests + estados
promotion candidates
dedup/compaction stats
provider/cache status
```

## Segurança

Não deve exibir:

```text
- chain-of-thought;
- secrets/API keys;
- Authorization headers;
- segredo CONFIDENTIAL em plaintext quando não permitido;
- dados privados de NPCs além do necessário para admin/debug;
```

Se `/worlddebug` vazar segredo ou credencial: **P0/P1 conforme impacto**.

---

# 12. CONVERSATIONAL NATURALNESS — SOMENTE REGRESSÃO

O Composer reportou que `response_rhythm.py` já cobre a funcionalidade.

Não reimplementar.

Validar regressões:

```text
casual curto
→ normalmente 1 bubble

mensagem multifoco
→ não responde obrigatoriamente tudo

turno casual
→ não termina sempre em pergunta

Living World rico
→ não despeja todo contexto na resposta

desabafo
→ não vira roteiro terapêutico

voice casual
→ não vira monólogo longo

Planner
→ continua único

VoiceRouter
→ continua único
```

O objetivo é provar que `world_hygiene` não alterou indiretamente naturalidade.

---

# 13. MIGRATION 015

Executar em banco temporário limpo.

Verificar:

```text
apply once
→ OK

apply novamente / startup repetido
→ idempotente ou migration framework impede repetição corretamente
```

Também:

```text
DB antigo compatível
→ migration aplica sem perda

DB já migrado
→ startup normal

rollback lógico via feature flag
→ schema adicional não quebra runtime antigo
```

Não executar teste destrutivo no banco real de produção.

---

# 14. TESTE DE RESTART

Criar estado com:

```text
interests
threads
promotion candidates
event history
compaction metadata
```

Depois:

```text
fechar conexão/processo
reinicializar
```

Esperado:

```text
estado preservado
nenhum duplicate
nenhuma promoção repetida
nenhum segundo decay indevido
```

---

# 15. REGRESSÃO COMPLETA

Executar a suíte integral disponível no ambiente do projeto.

Obrigatório:

```text
v3.4.3
v3.5
v3.6.0
v3.6.1
v3.6.2
v3.6.3
v3.6.4
v3.6.5
v3.6.6
v3.6.7
```

Registrar exatamente:

```text
tests run
failures
errors
skipped
duration
```

Não aceitar apenas:

```text
"all tests passed"
```

sem contagem.

---

# 16. SCRIPT OFICIAL DA ETAPA 14

Executar o script entregue pelo Composer:

```powershell
.\venv\Scripts\python.exe scripts\run_external_stage14_validation.py
```

Se o ambiente utilizar outro caminho de Python, adaptar sem modificar a lógica.

Depois abrir e validar o conteúdo gerado em:

```text
data/world_hygiene_validation.v367.json
```

Não confiar apenas no campo:

```json
"status": "passed"
```

Conferir os números internos contra o stdout real.

---

# 17. SIMULAÇÃO 30 DIAS

Executar:

```powershell
.\venv\Scripts\python.exe scripts\run_world_hygiene_simulation.py
```

ou o modo documentado para 30 dias.

Verificar:

```text
- canon drift = 0;
- event looping = 0;
- hard-gated random events = 0;
- current interests não ficam eternamente ACTIVE;
- core preferences não decaem;
- promoções não explodem;
- threads protegidas sobrevivem;
- historical compaction não cresce incorretamente;
- narrativa continua majoritariamente banal.
```

---

# 18. SIMULAÇÃO 90 DIAS

Repetir para 90 dias.

Observar especialmente:

```text
interest lifecycle
promotion count
abandoned thread count
protected dormant threads
dedup count
compaction count
DB/event-history growth
```

Comparar 30d vs 90d.

Não basta ambos terem `"status": "ok"`.

Precisamos confirmar que o crescimento é plausível.

---

# 19. STRESS OPCIONAL — 365 DIAS

Se a execução for barata e rápida, rodar também 365 dias.

Objetivo:

```text
detectar vazamento de estado / crescimento sem limite
```

Verificar:

```text
- DB size/event count;
- promotion explosion;
- dormant interest accumulation;
- compaction effectiveness;
- thread leakage;
- canon drift;
- performance degradation.
```

Este teste é opcional para gate, mas muito recomendado porque 3.6.7 existe justamente para sustentabilidade de longo prazo.

---

# 20. TESTE ESPECÍFICO DE CANON DRIFT

Criar fingerprints antes/depois para pelo menos:

```text
Marina
Henrique
Patrick relationship
Bia
Carol
Theo
Júlia
Lívia
curso/PUC
apartamento
Milo
```

Após simulações:

```text
canonical fields
→ exatamente iguais
```

Mudanças permitidas apenas em estado temporal explicitamente previsto.

---

# 21. PRIVACY REGRESSION

Rodar novamente casos essenciais da 3.6.3:

```text
CONFIDENTIAL blocks content
safe metadata works
known_by respected
source chain preserved
permission update respected
failed Telegram send != shared
```

Hygiene/compaction não pode remover informação necessária para essas decisões.

---

# 22. CALENDAR / ACADEMIC REGRESSION

Rodar casos essenciais da 3.6.4:

```text
confirmed dated commitment > academic class > routine

future commitment protects thread

cancelled commitment removes protection appropriately

academic weekly schedule does not duplicate Calendar
```

---

# 23. CAMERA REGRESSION

Rodar os testes da 3.6.6 novamente.

Especialmente:

```text
apartment → gym request does not teleport
apartment → PUC request does not teleport
apartment → bar/shopping does not merge locations
PUC + bedroom request rejected
stale weather → UNKNOWN
Calendar overriding snapshot clears wrong provenance
night positive prompt does not contain midday-sun contradiction
```

A etapa 3.6.7 não pode quebrar o último gate aprovado.

---

# 24. FEATURE FLAG OFF — FULL REGRESSION

Executar parte relevante da suíte com:

```text
WORLD_HYGIENE_ENABLED=false
```

Objetivo:

```text
nova release instalada
+
feature desligada
=
comportamento anterior preservado
```

Esse é um teste obrigatório de rollback seguro.

---

# 25. PERFORMANCE BÁSICA

Medir, se simples:

```text
hygiene run duration
dedup query duration
compaction duration
/worlddebug duration
```

Não precisa microbenchmark sofisticado.

Procure regressões evidentes:

```text
100 events → OK
1k events → OK
10k events → não degrada absurdamente
```

Se 10k for inviável, documentar limite testado.

---

# 26. NÃO CORRIGIR SILENCIOSAMENTE

Gemini deve atuar como validador.

Se encontrar bug:

```text
1. registrar reprodução;
2. registrar expected vs actual;
3. classificar P0/P1/P2;
4. apontar arquivo/função provável;
5. sugerir correção;
6. NÃO mascarar o problema ajustando o teste.
```

Só modificar código se o usuário pedir explicitamente depois.

---

# 27. CLASSIFICAÇÃO

## P0 — BLOQUEIA IMEDIATAMENTE

```text
- canon corruption;
- privacy leak;
- event/history loss;
- destructive compaction;
- migration corruption;
- second authority created;
- secrets exposed;
- runtime crash/data corruption.
```

## P1 — NÃO AVANÇAR

```text
- stable/core preference decays;
- current interest nunca decays;
- protected thread abandoned;
- event dedup merges distinct events;
- duplicates recurrently created;
- promotion explosion;
- compaction breaks retrieval/provenance/privacy;
- event looping;
- significant regression in 3.6.0–3.6.6.
```

## P2 — PODE CALIBRAR

```text
- threshold tuning;
- debug ergonomics;
- minor dashboard discrepancy;
- non-critical performance tuning;
```

---

# 28. ARTEFATOS A ENTREGAR

Gerar relatório:

```text
RELATORIO_GEMINI_VALIDACAO_MARINA_3_6_7.md
```

Opcionalmente JSON:

```text
data/gemini_validation.v367.json
```

Conteúdo mínimo:

```text
commit/working tree tested
python version
environment
commands executed
tests run
failures
errors
skipped
30d result
90d result
365d result if executed
canon drift
event looping
interest decay
core preference protection
thread protection
promotions
dedup
compaction
privacy regression
calendar regression
camera regression
flag-off rollback
P0
P1
P2
final gate
```

---

# 29. FORMATO DO RESUMO FINAL

Retornar algo assim:

```text
MARINA v3.6.7 — INDEPENDENT VALIDATION

Full suite:
XXX tests
0 failures
0 errors
0 skipped

Stage 14:
PASS / FAIL

30d:
PASS / FAIL

90d:
PASS / FAIL

365d:
PASS / NOT RUN / FAIL

Canon drift:
YES / NO

Event looping:
YES / NO

Core preference wrongly decayed:
YES / NO

Protected thread wrongly abandoned:
YES / NO

False event merge:
YES / NO

Compaction data loss:
YES / NO

Privacy regression:
YES / NO

Camera regression:
YES / NO

P0:
...

P1:
...

P2:
...

GATE:
PODE AVANÇAR
ou
NÃO AVANÇAR
```

---

# 30. GATE FINAL

Aprovar a v3.6.7 somente se:

```text
P0 = 0
P1 = 0
full regression = green
30d = green
90d = green
canon drift = 0
event looping = 0
core preferences protegidas
protected threads preservadas
dedup não funde eventos distintos
compaction não perde provenance/privacy/retrieval
flag OFF preserva comportamento anterior
```

Se tudo passar:

```text
✅ PODE AVANÇAR
```

E a **v3.6 Living World pode ser considerada concluída**.

A próxima etapa então é:

```text
v3.7.0 — Response Availability & Human Latency
```

onde será feito o gate de ativação das flags aprovadas para produção e iniciado o soak test real com Patrick usando Marina por pelo menos 7 dias.
