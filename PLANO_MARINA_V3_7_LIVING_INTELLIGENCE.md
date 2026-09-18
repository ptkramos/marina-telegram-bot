# PLANO MARINA V3.7 — LIVING INTELLIGENCE
## Human Latency, Personal Pattern Recognition, Associative Recall, Causal Reasoning e Curiosidade Seletiva

**Status:** plano de implementação proposto  
**Dependência:** concluir e estabilizar Marina **v3.6 — Living World**  
**Princípio central:** a v3.6 faz Marina **existir em um mundo coerente**; a v3.7 faz esse mundo **afetar de forma humana quando, como e por que ela conversa, percebe padrões, lembra experiências e busca informação**.

---

# 0. ORDEM OFICIAL DA V3.7

```text
3.7.0 — Response Availability & Human Latency
3.7.1 — Personal Pattern Recognition / User Routine Signals
3.7.2 — Associative Life Recall
3.7.3 — Causal Everyday Reasoning
3.7.4 — Selective Real-World Curiosity & Events
```

## Regra especial

**3.7.0 é o marco de entrada em uso real contínuo.**

Ao concluir 3.7.0:

```text
v3.6 completa
+
v3.7.0 validada
        ↓
ligar as feature flags aprovadas para produção
        ↓
Marina passa a ser usada normalmente pelo Patrick
        ↓
iniciar soak test real de pelo menos 7 dias
```

Não iniciar 3.7.1 automaticamente logo em seguida.

O objetivo é obter **comportamento real de produção** antes de continuar empilhando novas camadas.

---

# 1. V3.7.0 — RESPONSE AVAILABILITY & HUMAN LATENCY

## 1.1 Objetivo

Hoje:

```text
Patrick envia mensagem
→ debounce técnico
→ processamento
→ resposta
```

Depois da 3.7.0:

```text
Patrick envia mensagem
→ Marina recebe/notifica
→ WorldState determina situação atual
→ sistema avalia disponibilidade real
→ decide:
   REPLY_NOW
   REPLY_BRIEFLY
   DEFER
→ resposta acontece em janela humana plausível
```

O objetivo NÃO é deixar Marina lenta.

O objetivo é eliminar a sensação de:

```text
"bot sempre disponível e instantâneo"
```

sem cair no extremo:

```text
"personagem artificialmente inacessível"
```

---

# 2. PRINCÍPIOS DE HUMAN LATENCY

## Regra 1

```text
BUSY DOES NOT MEAN UNREACHABLE.
```

Estar ocupada reduz disponibilidade, não necessariamente acesso ao celular.

## Regra 2

```text
AVAILABLE DOES NOT MEAN INSTANTLY RESPONSIVE.
```

Mesmo em casa, Marina não precisa responder no mesmo segundo.

## Regra 3

```text
PHONE ACCESS != ATTENTION AVAILABLE
```

Exemplo:

```text
faculdade:
phone_access = HIGH
attention = LOW

academia:
phone_access = HIGH
attention = LOW/MEDIUM

Uber:
phone_access = HIGH
attention = HIGH
```

## Regra 4

Não usar delays rígidos baseados apenas em atividade.

Errado:

```text
gym = exactly 20 minutes
class = exactly 90 minutes
```

Correto:

```text
atividade
+ atenção
+ interruptibilidade
+ urgência
+ complexidade
+ contexto
+ variação humana
→ janela plausível
```

---

# 3. MODELO DE DISPONIBILIDADE

Criar estrutura determinística/semideterminística:

```text
ResponseAvailabilityDecision
```

Campos sugeridos:

```text
decision:
  REPLY_NOW
  REPLY_BRIEFLY
  DEFER

phone_access:
  LOW
  MEDIUM
  HIGH

attention_level:
  LOW
  MEDIUM
  HIGH

interruptibility:
  LOW
  MEDIUM
  HIGH

message_urgency:
  LOW
  NORMAL
  HIGH
  CRITICAL

response_complexity:
  SHORT
  NORMAL
  LONG

reason_code:
  HOME_RELAXING
  CLASS
  GYM
  CASTING
  WORK
  COMMUTE
  SOCIAL
  SLEEPING
  OTHER

earliest_reply_at
target_reply_window_start
target_reply_window_end

context_snapshot_id
```

Não permitir ao LLM escolher sozinho o delay.

---

# 4. INPUTS PARA A DECISÃO

A decisão deve usar apenas contexto disponível:

```text
WorldState
Calendar/Events
Academic Schedule
Routine Engine
current place
current activity
weather/context quando relevante
relationship context
message urgency
message complexity
pending message count
recent conversation state
```

Não criar novo WorldState.

Não criar segundo scheduler.

---

# 5. EXEMPLOS DE COMPORTAMENTO

## Em casa / relaxando

```text
phone_access = HIGH
attention = HIGH
interruptibility = HIGH
```

Resultado típico:

```text
REPLY_NOW
```

Delay: segundos ou poucos minutos.

## Academia

```text
phone_access = HIGH
attention = LOW/MEDIUM
interruptibility = MEDIUM
```

Possível:

```text
REPLY_NOW
REPLY_BRIEFLY
DEFER
```

A resposta pode acontecer entre séries, alguns minutos depois, ao fim de um bloco ou depois do treino.

Não bloquear por 60–90 minutos automaticamente.

## Aula

```text
phone_access = HIGH
attention = LOW
interruptibility = LOW/MEDIUM
```

Mensagem casual:

```text
DEFER
```

Mensagem simples:

```text
REPLY_BRIEFLY
```

Mensagem urgente:

```text
REPLY_BRIEFLY
ou
REPLY_NOW
```

Nunca assumir que estudante em aula não toca no celular.

## Casting / ensaio / job

```text
phone_access = MEDIUM/HIGH
attention = LOW
interruptibility = LOW
```

Atrasos maiores são plausíveis.

## Transporte / Uber

```text
phone_access = HIGH
attention = HIGH
interruptibility = HIGH
```

Boa janela para resposta rápida.

## Com amigos

```text
phone_access = HIGH
attention = MEDIUM
interruptibility = MEDIUM
```

Pode responder, mas não deve parecer que ignora completamente o grupo para ficar no Telegram.

## Dormindo

```text
phone_access = IRRELEVANT
interruptibility = VERY_LOW
```

Normalmente:

```text
DEFER
```

Urgência grave pode permitir exceção apenas se o sistema tiver mecanismo plausível de notificação/acordar.

---

# 6. URGÊNCIA DA MENSAGEM

Criar classificador simples.

Exemplos:

```text
LOW:
"olha esse meme kkkkk"

NORMAL:
"como foi sua aula?"

HIGH:
"amor, aconteceu uma coisa séria"

CRITICAL:
situação que claramente requer atenção imediata
```

A urgência deve influenciar:

```text
probabilidade de notar
probabilidade de interromper atividade
tempo de resposta
tamanho inicial da resposta
```

Não usar um LLM extra se uma classificação simples/determinística puder resolver.

---

# 7. COMPLEXIDADE DA RESPOSTA

Separar:

```text
WHEN_TO_REPLY
```

de:

```text
HOW_MUCH_TO_REPLY
```

Exemplo em aula:

```text
Patrick:
"como foi aquela apresentação?"

Marina:
"depois te conto direito kkkkk tô em aula agora"
```

Mais tarde:

```text
"agora saí, enfim..."
```

O sistema deve poder responder brevemente e manter um follow-up aberto.

---

# 8. PENDING CONVERSATIONAL BATCH

## Problema

Patrick envia:

```text
09:20 "oi amor"
09:24 "já chegou na puc?"
09:40 "olha isso kkkkk"
```

Marina estava ocupada.

Errado:

```text
11:01 responde mensagem 1
11:02 responde mensagem 2
11:03 responde mensagem 3
```

Correto:

```text
as mensagens pendentes formam um lote conversacional
→ contexto é consolidado
→ Marina responde ao que importa
```

Exemplo:

```text
"oii kkkkk tava em aula. cheguei sim, e QUE PORRA É ESSA que tu mandou 😂"
```

---

# 9. BATCHING NÃO É COMPLETENESS

Reutilizar o princípio do plano de naturalidade:

```text
OPTIMIZE FOR THE NEXT TURN, NOT COMPLETENESS.
```

Ao voltar depois de um defer:

- não responder item por item;
- não resumir a conversa;
- não explicar todos os delays;
- não pedir desculpa automaticamente;
- não usar sempre "tava ocupada".

A atividade pode ser mencionada apenas quando natural.

---

# 10. NÃO INVENTAR DESCULPA

Regra crítica:

```text
a resposta atrasou
!=
Marina precisa explicar o atraso
```

Ela só pode dizer:

```text
"tava em aula"
"tava treinando"
"tava no casting"
```

se isso for suportado pelo WorldState.

Nunca fabricar uma atividade apenas para justificar delay.

---

# 11. DEFER REAL

Quando `DEFER`:

```text
pending_reply
```

deve ser persistido.

Campos sugeridos:

```text
pending_reply_id
conversation_id
created_at
defer_reason
eligible_after
expires_at
message_batch_ids
context_snapshot_id
status
```

Status:

```text
PENDING
READY
SENT
CANCELLED
SUPERSEDED
```

---

# 12. NOVA MENSAGEM DURANTE DEFER

Se Patrick mandar outra mensagem enquanto há reply pendente:

```text
nova mensagem
→ não criar reply independente cegamente
→ atualizar/consolidar pending batch
→ recalcular urgência e disponibilidade
```

Exemplo:

```text
meme
→ DEFER

5 min depois:
"amor preciso falar contigo"

→ recalcular
→ HIGH urgency
→ reply pode antecipar
```

---

# 13. NÃO DUPLICAR O PLANNER

O sistema de Human Latency decide:

```text
quando responder
```

O Planner continua decidindo:

```text
o que fazer/responder
```

Não criar segundo cérebro.

---

# 14. NÃO DUPLICAR O SCHEDULER

Usar scheduler/infra existente para acordar replies deferidos.

Não criar daemon paralelo se já existe mecanismo de scheduling.

---

# 15. FEATURE FLAGS DA 3.7.0

Adicionar:

```env
RESPONSE_AVAILABILITY_ENABLED=false
HUMAN_REPLY_LATENCY_ENABLED=false
PENDING_CONVERSATION_BATCHING_ENABLED=false
```

Opcional:

```env
RESPONSE_AVAILABILITY_DEBUG=false
REAL_USAGE_TELEMETRY_ENABLED=false
```

---

# 16. MARCO DE PRODUÇÃO — PONTO OBRIGATÓRIO

Ao concluir e validar 3.7.0, entrar em:

```text
PRODUCTION_SOAK_PHASE
```

A partir deste ponto, o Codex deve **auditar e ligar as flags necessárias da v3.6 para o uso real da Marina**, não apenas as da 3.7.0.

O Codex deve:

1. listar TODAS as feature flags introduzidas na v3.6;
2. localizar os nomes reais no código/settings/.env.example;
3. classificar cada uma como:
   - `SAFE_TO_ENABLE`;
   - `REQUIRES_SECRET`;
   - `REQUIRES_EXTERNAL_PROVIDER`;
   - `EXPERIMENTAL`;
   - `KEEP_DISABLED`;
4. ligar apenas as aprovadas e realmente implementadas;
5. documentar o estado final;
6. realizar smoke check pós-ativação;
7. garantir rollback sem migration reversa destrutiva.

Categorias esperadas para revisão:

```text
World Bible / Core State
Social Graph / Places / Preferences
Story Engine
Knowledge / Privacy
Real World Context
Academic Life
Calendar / Events / Open Loops / Reminders
Relationship / Proactivity
Camera Continuity
Conversational Naturalness
Voice Prosody
Real-World Place Lookup
Holiday provider
```

**Não assumir nomes de flags. Usar os nomes reais existentes no projeto.**

---

# 17. MATRIZ DE ATIVAÇÃO DE PRODUÇÃO

Criar:

```text
docs/production_flags_3_7_0.md
```

Formato mínimo:

| Flag | Estado | Categoria | Motivo | Dependência | Rollback |
|---|---|---|---|---|---|
| `...` | ON/OFF | ... | ... | ... | ... |

Objetivo:

```text
um único lugar
→ mostra exatamente o que está ativo na Marina de produção
```

Também incluir:

```text
activation_timestamp
app_version/commit
DB schema version
provider readiness
secret readiness
```

---

# 18. PRINCÍPIO DE ATIVAÇÃO

Ao entrar no soak test:

```text
ligar funcionalidades que já passaram pelos testes e gates
```

mas:

```text
não ligar feature incompleta só porque pertence à 3.6
```

Se um provider depende de segredo ausente:

```text
feature permanece OFF
```

Se o provider falhar:

```text
fallback / UNKNOWN
```

não crash.

---

# 19. PRODUÇÃO = USO REAL DO PATRICK

O ambiente de produção deste projeto é:

```text
Patrick usando Marina normalmente no Telegram
```

Não criar comportamento especial de `test_user` que altere a personalidade.

A Marina deve rodar como rodaria depois do lançamento.

O único acréscimo é observabilidade técnica.

---

# 20. SOAK TEST REAL — MÍNIMO 7 DIAS

Após 3.7.0:

```text
D0:
- ativar flags aprovadas
- subir Marina
- confirmar providers
- executar smoke check
- confirmar rollback disponível

D1–D7:
- uso normal e contínuo
- não tentar provocar artificialmente todos os casos
- registrar problemas reais encontrados
```

Usar Marina normalmente em diferentes contextos:

```text
manhã
trabalho
faculdade/rotina da Marina
academia
fim da tarde
noite
fim de semana
mensagens únicas
mensagens acumuladas
mensagens urgentes ocasionais
```

O objetivo não é transformar Patrick em QA manual em tempo integral.

---

# 21. MÉTRICAS DO SOAK TEST

Coletar apenas métricas técnicas úteis.

## Response latency

```text
message_received_at
decision_at
reply_sent_at
latency_seconds
decision_type
reason_code
```

## Availability

```text
REPLY_NOW count
REPLY_BRIEFLY count
DEFER count
```

## Context

```text
activity_type
phone_access
attention
interruptibility
urgency
```

## Batch

```text
pending_message_count
batch_merged
batch_age
```

## External

```text
provider failures
cache hits
UNKNOWN fallback
```

---

# 22. NÃO LOGAR CONTEÚDO PRIVADO DESNECESSÁRIO

Para telemetry, preferir:

```text
message_id
hash/id
length
urgency class
activity
timing
decision
```

Evitar copiar texto inteiro de conversa para logs técnicos.

Se conteúdo precisar ser preservado para debugging:

- usar mecanismo já existente;
- limitar retenção;
- evitar duplicação desnecessária.

---

# 23. HUMAN LATENCY QUALITY CHECK

Depois de 7 dias, responder:

```text
1. Marina ainda responde instantaneamente demais?
2. Marina está demorando demais?
3. DEFER acontece nos momentos corretos?
4. academia parece acessível sem ser instantânea?
5. aula parece ocupada sem virar "offline"?
6. mensagens urgentes conseguem furar delays?
7. batches são respondidos naturalmente?
8. ela inventou desculpas?
9. delays pareceram repetitivos?
10. respostas curtas durante ocupação pareceram naturais?
```

---

# 24. EVENT LOG PARA REVIEW

Criar log compacto de decisões, por exemplo:

```text
response_availability_events
```

Campos:

```text
id
timestamp
activity
decision
urgency
latency_target
latency_actual
pending_batch_size
context_snapshot_id
reason
```

Não é memória autobiográfica da Marina.

É observabilidade do sistema.

---

# 25. FEEDBACK MANUAL DO PATRICK

Criar um arquivo simples:

```text
data/feedback/real_usage_3_7_0.md
```

ou equivalente fora do Git.

Modelo:

```text
[DATA/HORA]
Situação:
Ela estava:
Eu mandei:
Comportamento:
Esperado:
Observação:
```

Não precisa preencher sempre.

Registrar apenas casos:
- estranhos;
- muito bons;
- frustrantes;
- claramente artificiais.

---

# 26. CRITÉRIO PARA NÃO AVANÇAR À 3.7.1

Bloquear avanço se houver:

## P0

```text
- replies perdidos;
- reply duplicado;
- pending batch nunca enviado;
- urgência crítica presa;
- crash/scheduler failure;
- restart perde pending replies.
```

## P1

```text
- delays absurdos recorrentes;
- Marina quase sempre DEFER;
- Marina nunca DEFER;
- mentira recorrente sobre atividade;
- batches robóticos;
- respostas deferidas chegam fora de contexto com frequência.
```

P2 pode ser calibrado durante/ao fim do soak.

---

# 27. ROLLBACK DE PRODUÇÃO

Deve ser possível desligar 3.7.0 sem reverter código:

```env
RESPONSE_AVAILABILITY_ENABLED=false
HUMAN_REPLY_LATENCY_ENABLED=false
PENDING_CONVERSATION_BATCHING_ENABLED=false
```

Ao desligar:

```text
Marina volta ao comportamento reativo anterior
```

Sem:
- perder mensagens;
- corromper estado;
- deixar pending replies presos.

---

# 28. PENDING REPLIES NO ROLLBACK

Se flags forem desligadas com replies pendentes:

política recomendada:

```text
pending reply
→ marcar READY
→ processar imediatamente / próximo ciclo seguro
```

ou cancelar explicitamente se já foi `SUPERSEDED`.

Nunca deixar mensagem esquecida.

---

# 29. TESTES AUTOMÁTICOS DA 3.7.0

Antes do soak:

## Availability

```text
- home -> high availability
- class -> lower availability
- gym -> medium availability
- sleeping -> defer
- commute -> high availability
```

## Urgency

```text
- HIGH urgency reduces latency
- HIGH may override gym
- HIGH may produce brief reply during class
```

## Batch

```text
- 3 pending messages -> 1 conversational batch
- new urgent message upgrades existing batch
- sent batch cannot resend
- duplicate scheduler wakeup is idempotent
```

## Truthfulness

```text
- no activity reason without WorldState evidence
```

## Persistence

```text
- restart does not lose pending batch
```

## Rollback

```text
- disabling feature does not lose pending replies
```

---

# 30. SIMULAÇÕES ANTES DO USO REAL

Executar cenários sintéticos:

```text
24h
72h
7d
```

Não para definir qualidade humana por número, mas para detectar:
- starvation;
- filas infinitas;
- delays extremos;
- duplicação;
- bugs de scheduler.

Gemini pode executar simulações/testes longos.

Codex foca:
- arquitetura;
- implementação;
- revisão de relatórios;
- correções.

---

# 31. CRITÉRIO DE SUCESSO DA 3.7.0

A 3.7.0 está pronta para soak quando:

```text
no lost messages
no duplicate replies
pending survives restart
urgent messages can bypass defer
activity affects latency
availability is probabilistic
busy != unreachable
available != instant
batching works
rollback works
flags documented
production activation plan complete
```

---

# 32. 3.7.1 — PERSONAL PATTERN RECOGNITION / USER ROUTINE SIGNALS

## Objetivo

Perceber hábitos recorrentes do Patrick sem exigir declaração formal.

Exemplos:

```text
academia
trabalho
estudo
curso
game
série
projeto pessoal
horários recorrentes
fim de semana
```

Estados:

```text
OBSERVED
LIKELY
CONFIRMED
```

### OBSERVED

Poucas ocorrências.

Permitido:

```text
"tu tá indo bastante pra academia ultimamente né?"
```

### LIKELY

Padrão consistente, ainda não confirmado.

Permitido:

```text
"vai treinar hoje também?"
```

### CONFIRMED

Patrick explicitamente confirmou rotina.

Permitido:

```text
"já foi treinar hoje?"
```

---

# 33. AUSÊNCIA NÃO É EVIDÊNCIA

Regra:

```text
não mencionou treino
!=
não treinou
```

Marina pode perguntar.

Não pode afirmar falta sem evidência.

---

# 34. DECAY DE ROTINAS

Padrões deixam de ser considerados atuais se:
- não aparecem por tempo suficiente;
- Patrick corrige;
- rotina muda.

Não manter hábito antigo como verdade eterna.

---

# 35. ROTINA DO PATRICK ≠ ROUTINE ENGINE DA MARINA

Não criar segundo Routine Engine.

User Routine Signals apenas produz:

```text
possible pattern
confidence
last_observed
confirmation state
```

---

# 36. MOTIVAÇÃO / SUPORTE NATURAL

A rotina compartilhada pode gerar suporte:

```text
Marina treina
+
Patrick treina
+
Patrick está sem vontade
→ incentivo natural
```

Evitar persona de coach.

Exemplos desejados:

```text
"vai nem que seja mais leve hoje"
"já foi treinar?"
"descansa também, tu treinou direto esses dias"
```

Nunca pressionar mecanicamente.

---

# 37. 3.7.2 — ASSOCIATIVE LIFE RECALL

## Objetivo

Quando Patrick conta algo, Marina pode lembrar de experiência real semelhante.

Fluxo:

```text
Patrick conta situação
→ retrieval semântico
→ procurar evento/fato real persistido
→ verificar recência/relevância
→ verificar privacy/known_by
→ avaliar naturalidade
→ opcionalmente mencionar
```

Regra absoluta:

```text
NO FABRICATED MEMORY
```

Se não existe experiência persistida:

```text
não inventar "aconteceu comigo também"
```

---

# 38. ANTI "ME TOO SYNDROME"

Não responder toda experiência com experiência própria.

Associative recall deve ser opcional.

Só usar quando:
- adiciona conexão;
- não rouba foco;
- é relevante;
- é permitido pela privacidade.

---

# 39. 3.7.3 — CAUSAL EVERYDAY REASONING

## Objetivo

Derivar consequências cotidianas simples.

Exemplos:

```text
aula 07:00
+ mora em Botafogo
→ precisa sair cedo
```

```text
chuva forte
+ scooter
→ scooter menos plausível
```

```text
treino intenso ontem
+ cansaço hoje
→ descanso mais plausível
```

Não usar LLM para reescrever leis universais a cada turno se regras simples forem suficientes.

---

# 40. CAUSALIDADE NÃO É DETERMINISMO

```text
chuva
!=
ficar em casa obrigatoriamente
```

Ela altera plausibilidade.

---

# 41. 3.7.4 — SELECTIVE REAL-WORLD CURIOSITY & EVENTS

## Objetivo

Permitir que Marina descubra coisas do mundo quando há motivo.

Inclui:

```text
eventos públicos
novos lugares
agenda cultural
informação de moda
interesses situacionais
```

Não pesquisar continuamente.

---

# 42. PERCEPTION BEFORE CANON

Evento externo:

```text
evento existe
↓
Marina pode perceber?
↓
é relevante?
↓
está livre?
↓
alguém do círculo pode compartilhar?
↓
vira candidato
```

Nunca:

```text
evento existe
→ Marina foi
```

---

# 43. APRENDIZADO SELETIVO

Fluxo:

```text
não sabia
→ teve razão para pesquisar
→ encontrou fonte
→ informação contextual
→ pode persistir se estável/relevante
```

---

# 44. PROVIDERS FUTUROS

Possíveis fontes:

```text
DDGS search
Ticketmaster / outra fonte de events
fontes oficiais
sites de lugares
fontes acadêmicas
```

Não obrigar uma API específica neste plano.

---

# 45. RELEASE GATES

## Gate 3.7.0

Só avançar após:
- testes automáticos;
- flags documentadas;
- produção ativada;
- pelo menos 7 dias de uso real;
- revisão de telemetry e feedback;
- P0/P1 zerados.

## Gate 3.7.1

Só iniciar após aprovação do soak 3.7.0.

## Gate 3.7.2+

Cada etapa deve manter rollback e não alterar autoridade das anteriores.

---

# 46. RELATÓRIO DE SOAK TEST

Após pelo menos 7 dias gerar:

```text
RELATORIO_SOAK_MARINA_3_7_0.md
```

Conteúdo:

```text
period
total messages
median latency
P90/P95 latency
REPLY_NOW %
REPLY_BRIEFLY %
DEFER %
batch count
urgent override count
provider failures
bugs
manual feedback highlights
recommended tuning
P0/P1/P2
final gate
```

Não otimizar métricas isoladamente.

Exemplo:

```text
lower latency != always better
```

O objetivo é naturalidade + confiabilidade.

---

# 47. CONFIGURAÇÃO DE CALIBRAÇÃO

Pesos/faixas devem ficar em settings/config, não hardcoded espalhado.

Exemplo conceitual:

```text
home_relaxing
gym
class
work
casting
commute
social
sleeping
```

Cada perfil pode ter:
- base availability;
- interruptibility;
- min/max soft window;
- brief-response likelihood.

Não transformar isso em dezenas de magic numbers sem documentação.

---

# 48. VARIAÇÃO HUMANA E REPRODUTIBILIDADE

Para testes e simulações:

usar RNG seedável/determinístico onde apropriado.

Produção pode usar variação suficiente para não repetir padrões.

Evitar:

```text
sempre 8 min na academia
sempre 23 min em aula
```

---

# 49. PRIVACIDADE

Response Availability pode usar:
- atividade atual;
- contexto local da Marina;
- metadados de mensagem.

Não deve:
- contornar Knowledge/Privacy;
- registrar conteúdo extra apenas para telemetry;
- transformar telemetria em memória narrativa.

---

# 50. CUSTO

3.7.0 deve ser majoritariamente determinística.

Não adicionar LLM extra apenas para decidir delay.

Objetivo:

```text
same LLM pipeline
+ deterministic availability layer
```

Quando `DEFER`, evitar gerar uma resposta completa muito cedo se o contexto provavelmente mudará até o envio.

---

# 51. FAILURE MODE

Se ResponseAvailability falhar:

```text
fail open
→ responder normalmente
```

Melhor uma resposta rápida do que perder uma mensagem.

Nunca deixar o bot silencioso por erro interno.

---

# 52. PRODUÇÃO APÓS 3.7.0

Estado esperado:

```text
Marina v3.6 completa
+
3.7.0
+
flags aprovadas ON
+
uso real contínuo
+
observabilidade
+
rollback pronto
```

A partir desse ponto, Patrick deve poder parar de pensar no sistema como “ambiente de desenvolvimento” e usar a Marina normalmente por pelo menos uma semana.

O comportamento observado durante essa semana passa a ser evidência prioritária para o tuning seguinte.

---

# 53. DEFINITION OF DONE — V3.7.0

```text
Marina sabe quando está ocupada
+
não fica artificialmente offline
+
não responde sempre imediatamente
+
urgência importa
+
mensagens acumuladas viram conversa
+
atividade influencia tamanho da resposta
+
não inventa desculpa
+
pending replies sobrevivem restart
+
rollback é seguro
+
flags da v3.6 foram auditadas
+
produção foi ligada
+
telemetry real começou
```

> **A 3.7.0 não tenta fazer Marina conversar mais. Ela tenta fazer Marina conversar no momento certo, com a quantidade certa de atenção, como alguém que também está vivendo a própria vida.**
