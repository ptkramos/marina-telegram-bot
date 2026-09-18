# HANDOFF — MARINA v3.6.7
## Tuning, Reflection & Hygiene

**Objetivo:** implementar a última release da v3.6 sem reescrever as autoridades já validadas nas etapas 3.6.0–3.6.6.

**Regra de trabalho:** implementação/arquitetura no Codex/Composer; preparar validação determinística e scripts. A suíte completa, simulações longas e soak sintético devem ser deixados para o Gemini, conforme o fluxo atual do projeto, salvo smoke/compile/unit checks pequenos que forem estritamente necessários durante a implementação.

---

# 1. ESCOPO OFICIAL OBRIGATÓRIO

A v3.6.7 deve implementar/refinar:

```text
- decay de current interests;
- dormancy de threads;
- revisão de NPC/place promotion;
- event dedup;
- compactação de event history;
- dashboards/debug;
- testes longos de simulação.
```

Esta etapa é **tuning/hygiene**, não uma nova camada de autoridade.

Não criar:
- segundo Memory System;
- segundo Story Engine;
- segundo Planner;
- segundo Calendar;
- segundo WorldState;
- segundo Routine Engine;
- segundo Session Reflector;
- nova narrativa paralela.

---

# 2. BASELINE QUE NÃO DEVE SER REGREDIDO

Preservar as decisões já validadas:

```text
World Bible = autoridade canônica inicial
WorldState = autoridade de estado atual
Calendar/Events = autoridade de compromissos datados
Academic schedule = padrão recorrente, não segundo calendário
Story Engine = eventos/threads, não calendário
Knowledge/Privacy = known_by + permission + source chain
Camera = consumidora do mesmo WorldState
Planner = único planner
Routine = probabilística
CycleManager = único ciclo
```

Preservar também:

```text
STORY_EVENT_CADENCE_THRESHOLD = 0.60
~89% dias banais no long-run calibrado

STORY_THREAD_DORMANT_DAYS = 7
```

E a política atual de abandono seletivo:

```text
open → dormant após período configurado

dormant → abandoned após janela longa
SOMENTE quando não estiver protegido
```

Proteções existentes devem continuar valendo para:
- academic;
- professional;
- `has_future_commitment`;
- `protected`;
- `auto_abandonable = false` ou mecanismo equivalente.

Não alterar thresholds narrativos apenas “porque parece melhor”.
Qualquer mudança de tuning exige evidência da simulação.

---

# 3. CURRENT INTEREST DECAY

## Objetivo

Evitar que interesses temporários permaneçam ativos para sempre.

Separar claramente:

```text
CORE / STABLE PREFERENCE
≠
CURRENT INTEREST
```

Exemplos de current interest:

```text
série que está assistindo
tema que está pesquisando nesta semana
projeto acadêmico atual
tendência de moda que chamou atenção
atividade temporariamente recorrente
```

Exemplos que NÃO devem sofrer decay como interesse temporário:

```text
características canônicas
preferências estáveis confirmadas
relacionamentos canônicos
curso/foco acadêmico
dados biográficos
```

## Requisitos

Um current interest deve possuir, ou derivar de metadata equivalente:

```text
first_observed_at
last_reinforced_at
reinforcement_count
strength/confidence
status
source
```

Estados sugeridos:

```text
ACTIVE
FADING
DORMANT
```

Não apagar imediatamente quando fica velho.

Preferir:

```text
ACTIVE
→ perde força gradualmente
→ FADING
→ DORMANT
```

Reforço explícito deve:
- atualizar `last_reinforced_at`;
- aumentar/estabilizar força;
- poder reativar interesse dormant.

## Regra

**Decay de interesse não é esquecimento de autobiografia.**

O fato histórico pode continuar existindo.
Apenas deixa de competir como interesse atual.

---

# 4. THREAD HYGIENE / DORMANCY

## Objetivo

Revisar a política já implementada, não substituí-la.

Garantir:

```text
OPEN
→ DORMANT
→ OPEN novamente se surgir evidência
→ RESOLVED / ABANDONED quando aplicável
```

### Regras obrigatórias

- thread dormant pode receber nova evidência;
- evidência válida pode reabrir thread;
- thread resolvida não reabre silenciosamente;
- thread abandoned não reabre sem decisão explícita;
- consequência continua apontando para evento anterior;
- proteção por compromisso futuro continua consultando Calendar/Events;
- cancelamento/conclusão do compromisso atualiza a proteção sem duplicar estado.

### Não fazer

```text
idade da thread sozinha
→ destruir thread acadêmica/profissional relevante
```

Não mudar a cadência de Story Events nesta etapa sem relatório comparativo.

---

# 5. NPC / PLACE PROMOTION REVIEW

## Objetivo

Impedir crescimento descontrolado do World Bible/Social Graph.

A promoção deve continuar sendo rara e baseada em evidência.

Usar os thresholds configuráveis existentes ou equivalentes, incluindo:

```text
WORLD_DISCOVERY_PROMOTION_THRESHOLD
WORLD_PREFERENCE_PROMOTION_THRESHOLD
```

Os números são tuning, não canon.

## Candidate lifecycle

Sugestão compatível:

```text
DISCOVERED
→ REINFORCED
→ PROMOTABLE
→ PROMOTED
```

Não promover automaticamente por:
- uma única menção;
- um único resultado DDGS;
- uma participação incidental em Story Seed;
- aparecer em evento público;
- existir no mundo real.

### Places

Um lugar novo pesquisado por DDGS:

```text
candidate place
!=
canonical place
```

Promoção só após uso/visita/relevância repetida ou evidência equivalente.

### NPCs

Pessoa mencionada:

```text
mentioned person
!=
Social Graph NPC
```

Não transformar docente real, funcionário, pessoa pública ou terceiro real em NPC ficcional automaticamente.

## Review job

Criar um job/review determinístico que:
- liste candidatos;
- conte reinforcement;
- marque `PROMOTABLE`;
- não precise promover automaticamente se a evidência for ambígua.

Registrar:

```text
NPC_PROMOTION
PLACE_PROMOTION
```

sem chain-of-thought.

---

# 6. EVENT DEDUPLICATION

## Objetivo

O mesmo acontecimento pode chegar por múltiplas camadas:

```text
Calendar
Story Engine
Real World Context
Academic Life
Open Loop / Reminder
Conversation extraction
```

Evitar que isso vire múltiplos eventos autobiográficos.

## Dedup deve preferir

1. identificador externo/canônico explícito;
2. `source_type + source_id`;
3. chave de idempotência;
4. janela temporal + entidade + tipo;
5. fallback conservador.

### Regra

```text
mesmo fato por duas fontes
→ uma realidade
```

Mas:

```text
dois eventos parecidos
!=
mesmo evento automaticamente
```

Não usar dedup semântico agressivo que possa fundir:
- dois castings diferentes;
- duas aulas diferentes;
- dois treinos diferentes;
- dois encontros distintos.

## Idempotência

Reprocessar:
- bootstrap;
- lazy catch-up;
- scheduler;
- provider retry;
- restart;

não deve duplicar evento já materializado.

---

# 7. EVENT HISTORY COMPACTION

## Objetivo

Impedir que ContextBuilder, debug e queries degradam conforme histórico cresce.

Compactação não pode destruir:
- provenance;
- source chain;
- privacy;
- relações entre thread/event;
- auditoria;
- hard-gated decisions;
- eventos ainda ativos/relevantes.

## Preferência arquitetural

Separar:

```text
raw/authoritative event record
```

de:

```text
compact historical representation
```

Se o schema atual permitir, preferir arquivar/resumir para retrieval/context em vez de apagar sem rastreabilidade.

### Candidatos à compactação

- eventos antigos;
- resolvidos;
- baixa importância;
- sem thread ativa;
- sem compromisso futuro;
- sem unresolved open loop;
- não usados como source de privacy/knowledge atual.

### Nunca compactar de modo destrutivo

- thread OPEN/DORMANT protegida;
- evento apontado por consequência ativa;
- compromisso futuro;
- item relevante à Knowledge/Privacy;
- relacionamento/canon;
- evento hard-gated;
- fato ainda necessário para shared history.

## Reprocessamento

Rodar compaction duas vezes deve ser idempotente.

---

# 8. REFLECTION — REUTILIZAR, NÃO DUPLICAR

Já existe a filosofia de Session Reflection / Memory Hygiene das versões anteriores.

A v3.6.7 deve integrar/refinar isso com Living World, não criar um segundo `SessionReflector`.

Reflection pode revisar:
- current interests;
- event relevance;
- resolved loops;
- thread status;
- candidates para promotion;
- duplicatas prováveis.

Não permitir que Reflection:
- invente acontecimentos;
- reescreva canon;
- altere privacy sem regra;
- crie eventos como se fossem observados;
- gere novos fatos apenas porque parecem plausíveis.

---

# 9. DASHBOARD / DEBUG

Adicionar/refinar debug/admin sem expor chain-of-thought.

O plano principal pede visibilidade de:

```text
current world state
active threads
upcoming events
recent seeds
privacy metadata
narrative budget
```

Também é útil mostrar:

```text
current interests + strength/state
dormant/protected threads
promotion candidates
dedup counters
compaction counters
provider/cache status
```

Logs/eventos esperados incluem, quando aplicável:

```text
STORY_SEED_CREATED
STORY_THREAD_ADVANCED
EVENT_REJECTED_CANON_CONFLICT
KNOWLEDGE_SHARE
PRIVACY_BLOCK
PLACE_PROMOTION
NPC_PROMOTION
PREFERENCE_REINFORCED
CAMERA_WORLD_CONTEXT
```

Adicionar reason codes curtos.
Não logar raciocínio interno.

---

# 10. CONVERSATIONAL NATURALNESS — REFINAMENTO FINAL

A v3.6.7 é o ponto de refinamento final do módulo de Conversational Naturalness.

Preservar o princípio:

```text
OPTIMIZE FOR THE NEXT TURN, NOT COMPLETENESS.
```

Revisar regressões como:
- 3 bolhas por padrão;
- responder todos os tópicos;
- terminar sempre com pergunta;
- explicar contexto demais;
- Living World tornar a resposta verborrágica;
- voz casual virar monólogo.

Não criar outro LLM call em toda resposta só para decidir tamanho.

Planner e VoiceRouter continuam únicos.

---

# 11. LONG SIMULATION — PREPARAR PARA GEMINI

O plano oficial exige simulação acelerada de:

```text
30 dias
90 dias
```

Verificar:
- distribuição de intensidade;
- número de threads simultâneas;
- taxa de dias/eventos banais;
- ausência de canon drift;
- ausência de event looping;
- promoções razoáveis;
- preferências não mudam rápido demais;
- NPCs têm vida sem dominar contexto;
- nenhum drama grave aleatório.

Como o projeto já possui simulações mais longas de Story Engine, preparar opcionalmente:

```text
365 dias
1095 dias
```

como stress/soak, sem torná-los requisito se custo/tempo for desnecessário.

**Não peça ao Codex/Composer para gastar quota executando a simulação longa.**
Preparar scripts e handoff para o Gemini.

---

# 12. CENÁRIOS DE TESTE ESSENCIAIS

## Interests

```text
interest recente → ACTIVE
sem reforço → FADING
longo tempo → DORMANT
nova evidência → ACTIVE novamente

core preference → NÃO decai como current interest
```

## Threads

```text
open antiga → dormant
dormant + evidence → open
academic dormant protegida → não abandoned por idade
future commitment → protege
commitment cancelado/completo → proteção atualizada
```

## Promotions

```text
1 menção → não promove
repeated candidate → promotable
DDGS result → não promove automaticamente
docente real → não vira NPC
```

## Dedup

```text
mesmo calendar event reprocessado → 1 evento
retry provider → 1 evento
lazy catch-up repetido → não duplica
dois eventos semelhantes distintos → continuam separados
```

## Compaction

```text
old resolved low-value → compactable
active/protected → não compacta destrutivamente
segunda execução → idempotente
retrieval mantém contexto útil
```

## Debug

```text
dashboard mostra estado correto
não expõe segredo/confidential content indevido
não expõe chain-of-thought
```

---

# 13. REGRESSION OBRIGATÓRIA

Além dos testes específicos da 3.6.7, preservar:

```text
todos os testes de v3.4.3
todos os testes de v3.5
todos os testes já existentes da v3.6
```

Especial atenção para regressão em:

```text
3.6.2 Story cadence
3.6.3 Knowledge/Privacy
3.6.4 Calendar/Academic/Real Context
3.6.5 Relationship/Proactivity
3.6.6 Camera World Continuity
```

---

# 14. NÃO ALTERAR NESTA ETAPA

Não iniciar features da 3.7.

Especialmente NÃO implementar ainda:

```text
Response Availability / Human Latency
User Routine Signals
Associative Life Recall
Causal Everyday Reasoning
Events discovery / selective curiosity
```

Essas entram após fechamento da v3.6.

Também NÃO ligar as flags de produção em massa aqui.

O marco oficial de:
- auditoria de flags;
- ativação para produção;
- soak real de 7 dias;

é a **v3.7.0**.

---

# 15. FEATURE FLAGS / CONFIG

Não inventar nomes se já existem.

Reutilizar settings reais.

Qualquer novo tuning deve:
- ter default seguro;
- ser documentado;
- ser facilmente reversível;
- não virar magic number espalhado pelo código.

Se adicionar knobs, centralizar em config.

---

# 16. VALIDATION ARTIFACT

Preparar um artefato de validação equivalente ao padrão já usado no projeto, por exemplo:

```text
data/world_hygiene_validation.v367.json
```

Se já houver convenção de nome/Stage no repositório, seguir a convenção real em vez de forçar esse nome.

Campos mínimos:

```text
release
stage
timestamp
test_command
tests_run
failures
errors
skipped
simulation_30d
simulation_90d
canon_drift_detected
event_looping_detected
promotion_anomalies
preference_decay_anomalies
status
```

---

# 17. HANDOFF PARA GEMINI

Ao terminar implementação, entregar ao Gemini:

```text
1. branch/commit ou working tree exata;
2. comandos de instalação/execução;
3. script principal de validação;
4. testes novos da 3.6.7;
5. suíte regressiva;
6. simulação 30d;
7. simulação 90d;
8. opcional 365/1095d;
9. path do JSON de resultado;
10. critérios de gate.
```

Gemini deve retornar relatório compacto:

```text
total tests
failures/errors/skips
30d result
90d result
canon drift
event loops
promotions
interest decay
thread lifecycle
regressions
gate
```

---

# 18. GATE

## P0

```text
canon corruption
privacy leak
lost/corrupted events
destructive compaction
duplicate authoritative state
crash/migration corruption
```

## P1

```text
interests não decaem
core preference decai
threads protegidas abandonadas
event dedup falha recorrentemente
promoções excessivas
event looping
context/retrieval piora após compaction
dashboard expõe informação indevida
```

## P2

```text
threshold tuning
debug ergonomics
minor dashboard inconsistencies
non-critical compaction efficiency
```

### Gate final

```text
PODE AVANÇAR
```

somente quando:
- P0 = 0;
- P1 = 0;
- regressões passam;
- 30d/90d não mostram canon drift/event looping/drama excessivo;
- promotion/interest decay ficam plausíveis.

---

# 19. DEFINITION OF DONE

A v3.6.7 está concluída quando:

```text
current interests envelhecem sem apagar história
threads entram/saem de dormancy coerentemente
future commitments continuam protegendo threads
NPC/place promotion é conservadora
eventos não duplicam em retry/catch-up
histórico antigo não polui contexto indefinidamente
compaction preserva provenance e relações
debug mostra estado sem chain-of-thought
naturalidade conversacional não regrede
30d/90d passam
regression suite passa
```

Resultado esperado:

```text
v3.6 Living World
→ coerente
→ auditável
→ sustentável no longo prazo
→ pronta para fechamento
→ pronta para iniciar v3.7.0
```

> **3.6.7 deve limpar, estabilizar e provar o Living World — não expandir o universo com novas autoridades.**
