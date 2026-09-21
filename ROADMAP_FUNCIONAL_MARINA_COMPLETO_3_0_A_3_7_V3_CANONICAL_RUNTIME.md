# ROADMAP FUNCIONAL COMPLETO — MARINA
## Do saneamento inicial à Living Intelligence
### O que cada versão/release deveria fazer, qual comportamento deveria aparecer no Telegram e o que versões posteriores substituíram

**Objetivo deste documento:** servir como mapa funcional durante soak tests, auditorias e correções.

Ele responde principalmente:

```text
"Esta feature deveria existir para quê?"
"Como eu deveria perceber isso conversando com a Marina?"
"Qual sistema é o dono desse comportamento?"
"Uma versão posterior substituiu ou refinou isso?"
"Se o bot agir de forma burra aqui, onde devo procurar?"
```

---

# 0. PRINCÍPIO GERAL DO PROJETO

A evolução da Marina foi planejada em camadas. A intenção nunca foi construir vários "cérebros" concorrentes.

```text
World Bible
    ↓
canon / identidade

Memory Intelligence
    ↓
memórias do Patrick e fatos recuperáveis

Calendar / Academic / Routine / Story
    ↓
acontecimentos + compromissos + possibilidades

WorldState
    ↓
o que está acontecendo AGORA

Knowledge / Privacy
    ↓
quem sabe o quê e o que pode ser contado

Planner
    ↓
o que fazer neste turno

Response Availability
    ↓
quando responder / quanta atenção existe

Response Rhythm
    ↓
quanto falar / formato da resposta

Style Engine
    ↓
estilo pt-BR e padrões realmente aprendidos do Patrick

VoiceRouter
    ↓
qual registro vocal usar

Voice Prosody
    ↓
como interpretar vocalmente

Camera World
    ↓
como o estado atual vira imagem

LLM principal
    ↓
fala natural da Marina em pt-BR
```

## Regra de ouro

```text
ONE FACT
→ ONE AUTHORITY

ONE BEHAVIORAL POLICY
→ ONE OWNER
```

O prompt deve ser uma **visão das autoridades**, não uma segunda realidade.

---

# 0.1 DECISÃO ARQUITETURAL POSTERIOR — REMOVER `/edit` E AUTO-MODIFICAÇÃO EM RUNTIME

**Decisão de projeto:** o comando `/edit` e toda a cadeia de auto-modificação de código em runtime deixam de fazer parte da arquitetura alvo da Marina.

Motivo:

```text
capacidade de alterar o próprio código em produção
→ aumenta superfície de risco
→ dificulta auditoria
→ pode editar owner errado
→ pode reintroduzir arquitetura legada
→ pode quebrar invariantes entre releases
→ pode transformar um erro de interpretação em mudança persistente de código
```

A Marina **não precisa editar o próprio código para parecer viva, inteligente ou autônoma**.

## Remover completamente

```text
/edit
AutoPatcher runtime
SafePatcher runtime
Patch Planner voltado a autoedição
roteamento automático de pedido → arquivo Python
geração automática de patch por LLM dentro do bot
aplicação automática de diff
restart automático disparado por auto-patch
rollback específico de auto-patch
patch_history específico do /edit
receipts específicos do /edit
feature flags cujo único propósito seja habilitar auto-modificação
prompts/system rules cujo único propósito seja operar /edit
admin/debug commands exclusivos da cadeia de auto-patch
```

## NÃO remover só porque já foi usado pelo `/edit`

Ferramentas genéricas continuam úteis se tiverem função independente:

```text
test suite
compile checks
healthcheck geral
migrations
backup de banco
logging
feature flags de produto
scripts de validação
release packaging
auditoria de prompts
```

Ou seja:

```text
remover a capacidade de auto-modificação
!=
remover engenharia de segurança
```

## Nova política de manutenção

Alterações de código devem ocorrer fora do runtime da Marina:

```text
Patrick / agente de desenvolvimento
→ branch/worktree
→ implementação
→ testes
→ auditoria independente
→ commit/release
→ deploy
```

Nunca:

```text
conversa com Marina
→ /edit
→ LLM altera código em produção
```

## Regra permanente

> **Marina pode evoluir entre releases; ela não deve reescrever o próprio código durante a conversa ou em produção.**

---



# 0.2 DECISÃO ARQUITETURAL POSTERIOR — CANONICAL RUNTIME E APOSENTADORIA DE FEATURE FLAGS DE RELEASE

**Decisão de projeto:** como as releases até `v3.7.0` já passaram pelos respectivos gates, o runtime final da Marina deve refletir **a arquitetura moderna aprovada**, e não preservar indefinidamente múltiplos caminhos históricos atrás de feature flags.

A função original das feature flags era saudável:

```text
feature nova
→ flag OFF
→ implementação/testes
→ flag ON
→ rollback rápido se o rollout falhar
```

O problema aparece quando a flag deixa de ser temporária e passa a preservar duas arquiteturas:

```text
FLAG ON
→ sistema moderno

FLAG OFF
→ fallback antigo / arquitetura obsoleta
```

Isso aumenta combinações de runtime, dificulta auditoria e pode fazer o bot alternar entre comportamentos de gerações diferentes.

## Nova regra

> **Uma release flag tem data de validade.**

Quando uma feature foi implementada, validada e aprovada, ela deve caminhar para:

```text
CANONICAL RUNTIME
```

e não continuar como opção histórica indefinidamente.

## Estado alvo

```text
CANONICAL RUNTIME
→ um único caminho moderno de produção

OPTIONAL PROVIDERS
→ configurações realmente opcionais

KILL SWITCHES
→ somente para risco operacional real

UNRELEASED / EXPERIMENTAL FEATURES
→ flags temporárias

LEGACY FALLBACKS
→ ZERO
```

## Classificação oficial das flags

### CANONICALIZE
Feature aprovada e madura.

Ação:

```text
tornar caminho moderno padrão e único
remover branch legado
remover fallback antigo
remover a própria flag quando não houver mais motivo operacional
atualizar testes para validar apenas a arquitetura atual
```

### KILL_SWITCH
Feature moderna que precisa de desligamento emergencial.

Regra:

```text
OFF
→ degradação segura

OFF
!=
arquitetura antiga ON
```

### PROVIDER_CONFIG
Escolha de fornecedor ou integração externa.

Exemplos:

```text
DDGS
Feriados API
Novita
ElevenLabs
Gemini fallback
```

Pode permanecer configurável.

### TEMPORARY_RELEASE_FLAG
Feature ainda em rollout/validação.

Depois do gate:

```text
TEMPORARY
→ CANONICALIZE ou KILL_SWITCH
```

### SHADOW_EXPERIMENT
Serve para observar comportamento sem enforcement.

Depois do soak:

```text
remover
```

ou manter apenas como debug/admin explícito.

### DELETE
Flag duplicada, obsoleta, ligada a código removido ou que só preserva legado.

---

## REGRA CRÍTICA — OFF NUNCA SIGNIFICA "VOLTAR NO TEMPO"

Incorreto:

```python
if WORLD_BIBLE_ENABLED:
    use_world_bible()
else:
    use_legacy_marina_prompt()
```

Correto após canonicalização:

```text
World Bible
→ sempre authority do canon
```

Se houver kill switch técnico, o modo OFF deve ser uma degradação segura/minimal, nunca:

```text
Marina Seltin
idade fixa
rotina antiga
prompt monolítico
proatividade antiga
câmera antiga
```

---

## IMPACTO NAS RELEASES JÁ APROVADAS ATÉ 3.7.0

### v3.5.x

Revisar flags que possam restaurar:

```text
memory retrieval antigo
open-loop/reminder behavior antigo
voice routing antigo
reflection antiga
```

### v3.6.0 — World Bible / WorldState

```text
World Bible / WorldState
→ canonical runtime
```

Desligar uma flag nunca pode restaurar biografia/rotina antiga.

### v3.6.1 — Social Graph / Places / Preferences

A source of truth moderna deve permanecer única.

### v3.6.2 — Story Engine

Se houver kill switch:

```text
OFF
→ não gerar novas stories
```

e nunca:

```text
OFF
→ chamar gerador legado
```

### v3.6.3 — Knowledge / Privacy

Privacy não deve poder ser "desligada" de forma que o sistema fique menos seguro.

Fail-safe deve ser:

```text
mais restritivo
```

não disclosure legado.

### v3.6.4 — Calendar / Academic / Real-World Context

Providers externos podem continuar opcionais.

Mas:

```text
Calendar authority
Academic projection
```

não devem desaparecer por provider OFF.

### v3.6.5 — Relationship / Proactivity

OFF de uma subfeature não pode chamar proatividade aleatória antiga.

### v3.6.6 — Camera World

Se indisponível:

```text
fallback visual neutro
```

e não cenário inventado pelo prompt antigo.

### v3.6.7 — World Hygiene

Pode existir kill switch para pausar jobs mutáveis.

Mas OFF significa:

```text
pausar hygiene
```

e não voltar para regras velhas de evento/memória.

### v3.7.0 — Response Availability / Human Latency / Pending Batching

Durante o soak, flags de enforcement/shadow ainda podem existir.

Depois de aprovado:

```text
classificar cada uma
→ CANONICALIZE ou KILL_SWITCH
```

Nenhuma deve manter fallback conversacional pré-3.7 que reintroduza caminhos antigos.

---

## PRINCÍPIO DE RELEASE DAQUI PARA FRENTE

```text
IMPLEMENT
→ TEMP FLAG
→ VALIDATE
→ GATE
→ SOAK
→ CANONICALIZE
→ REMOVE LEGACY
→ REMOVE TEMP FLAG
```

A flag só permanece quando houver justificativa operacional real.

---

## O QUE NÃO É FEATURE FLAG E NÃO DEVE SER REMOVIDO À FORÇA

Continuam sendo configurações legítimas:

```text
API keys
timeouts
TTL
thresholds
provider selection
model IDs
voice IDs
paths
debug verbosity
safe tuning values
```

O alvo é eliminar **arquitetura histórica concorrente**, não configurabilidade útil.

---

# 1. POLÍTICA DE LINGUAGEM DOS PROMPTS

A política oficial definida na v3.6:

```text
CONTROL PLANE / SYSTEM RULES
→ English

STRUCTURED STATE / ENUMS / SCHEMAS
→ English ou identifiers language-neutral

WORLD BIBLE CONTENT / contexto cultural brasileiro
→ pt-BR quando a nuance importa

STYLE EXAMPLES / diálogo / gírias
→ pt-BR

OUTPUT USER-FACING DA MARINA
→ pt-BR por padrão

IMAGE / FLUX PROMPT TAGS
→ English
```

### Exemplo correto

```text
System:
Routine is probabilistic. Calendar commitments are authoritative.

Canon:
Marina estuda Design na PUC-Rio.

Dialogue example:
"caralho amor kkkkk eu sabia"
```

### O que não deveria mais existir

Um system prompt gigante em português contendo ao mesmo tempo:

```text
identidade
idade
rotina
sono
localização
personalidade
foto
proatividade
estado atual
```

Esses domínios foram separados por versões posteriores.

---

# 2. MARINA 3.0.1 — STABILIZATION

## Feature

Release estrutural para tornar o projeto confiável antes de acrescentar inteligência.

Principais objetivos:

```text
TARGET_CHAT_ID obrigatório
debounce centralizado
versão centralizada
requirements corrigido
framework de migrations
SQLite WAL / busy timeout
feature flags
healthcheck
higiene de pacote/release
```

## Comportamento esperado

O usuário quase não deveria "sentir" uma personalidade nova nesta versão.

A diferença deveria ser operacional:

```text
- o bot não responde para chat não autorizado;
- mensagens enviadas em sequência curta são agrupadas corretamente;
- restart não quebra schema;
- settings refletem o código real;
- features podem ser desligadas sem rollback de código;
- o bot detecta problemas básicos antes de subir.
```

## O que essa versão NÃO deveria decidir

```text
memória inteligente
vida própria
rotina
personagem
voz contextual
histórias
```

## Refinado depois por

Toda a arquitetura posterior depende dessa fundação.

---

# 3. MARINA 3.1 — SMART MEMORY

## Feature

Primeira memória inteligente real.

Introduziu/consolidou:

```text
SQLite persistente
fatos
momentos
resumos
FTS5
Memory Consolidator
deduplicação
contradição/supersede
Memory Retriever
Context Builder
context budget
```

## Comportamento esperado

### Lembrar algo relevante

```text
Dia 1:
Patrick: "voltei a jogar Final Fantasy XIV"

dias depois:
Patrick: "lembra daquele jogo que eu voltei?"

Marina:
→ recupera FFXIV
```

### Não despejar memória irrelevante

```text
Patrick:
"qual música você tá ouvindo?"

Marina:
→ NÃO precisa receber contexto de FFXIV só porque ele existe no banco
```

### Corrigir memória

```text
Patrick:
"meu energético favorito é Red Bull"

depois:
"enjoei, agora prefiro Monster"

resultado:
Red Bull → superseded/inactive
Monster → ativo
```

## Sintoma de falha

```text
Marina esquece fatos importantes
OU
traz memórias aleatórias sem relação com a conversa
OU
continua afirmando uma preferência antiga depois de correção
```

## Refinado/sobreposto depois

### v3.5.0

A Smart Memory simples foi ampliada para **Memory Intelligence**, adicionando:

```text
memory tiers
volatility
confidence lifecycle
canonical keys
FTS também para momentos e resumos
ranking híbrido
reconfirmação
```

A v3.1 não deixou de existir: virou a base da v3.5.0.

---

# 4. MARINA 3.2 — CONTINUITY

## Feature

Fazer conversas e acontecimentos continuarem entre turnos/sessões.

Principais componentes:

```text
Internal Planner
eventos pendentes
estado relacional
estado emocional
follow-ups
proatividade contextual
anti-spam / cooldown
Style Engine 2.0
ciclo biológico refinado
```

## Comportamento esperado

### Continuidade imediata

Se Patrick acabou de dizer:

```text
"tô no trabalho hoje"
```

o turno seguinte deveria partir disso.

Não deveria ocorrer:

```text
Patrick:
"tô no trabalho hoje"

Marina:
"Oi amor! Tudo bem com você?"
```

como se uma nova conversa tivesse começado.

### Planner

O Planner deveria identificar coisas como:

```text
casual chat
planning future
support
flirting
future event
follow-up possibility
```

e orientar o turno sem virar outro chatbot.

### Pending event / follow-up

```text
Patrick:
"amanhã vou apresentar aquela feature"

depois do evento:
Marina pode perguntar como foi
```

### Proatividade

Ela pode retomar assuntos sem Patrick precisar iniciar sempre.

Mas:

```text
não spam
não mandar várias iniciativas em sequência
não mandar tudo que sabe
```

### Style Engine 2.0

O estilo do Patrick pode influenciar Marina gradualmente:

```text
risadas
emojis
gírias
cadência
```

Mas somente com evidência real.

## Refinado/sobreposto depois

### Pending events / follow-up
→ refinados por **3.5.1 Open Loops & Smart Reminders**.

### Proatividade simples
→ reorganizada por **3.6.5 Relationship & Proactivity Integration**.

### Rotina/horários hardcoded
→ devem ser substituídos pela arquitetura **WorldState + Calendar + Routine Engine** da v3.6.

### Style Engine
→ continua válido, mas não pode inventar comportamento do Patrick sem amostras reais.

---

# 5. MARINA 3.3 — PERCEPTION

## Feature

Capacidade visual.

Planejado:

```text
receber fotos do Patrick
Vision Service
Visual DNA
image intent
prompts dinâmicos
Smart Camera
continuidade visual
```

## Comportamento esperado

### Foto recebida

Patrick manda uma imagem.

Marina deveria:

```text
entender o que está visível
reagir naturalmente
não falar como OCR/vision API
não inventar detalhes incertos
```

### Foto gerada da Marina

A aparência deveria permanecer consistente:

```text
mesmo rosto / cabelo / identidade visual
```

O contexto da foto deveria partir do contexto conversacional disponível.

## Refinado/sobreposto depois

### v3.6.6 — Camera World Continuity

A câmera deixou de poder decidir cenário sozinha.

Agora:

```text
Camera visualizes the current world.
It does not invent a parallel world.
```

### v3.7.0

Se uma foto for DEFERIDA por Human Latency:

```text
não gerar antes
→ esperar o turno realmente acontecer
→ usar Camera World / WorldState atual naquele momento
```

---

# 6. MARINA 3.4 — SAFE EVOLUTION / SELF-MAINTENANCE
## STATUS ATUAL: PARCIALMENTE APOSENTADA

Historicamente, a família 3.4 foi planejada para permitir manutenção automática/assistida com menor risco.

O escopo original incluía:

```text
/edit
patch planner
multi-file patch
diff / staging
snapshots
compile
tests
health check
rollback
restart receipt
patch history
debug
```

## O que continua válido

A parte de **engenharia de confiabilidade** continua importante:

```text
compile
tests
healthcheck geral
backups
migrations seguras
feature flags
release validation
logs
debug
packaging limpo
```

Esses mecanismos protegem releases feitas por humanos/agentes externos.

## O que foi aposentado por decisão posterior

Todo o caminho de **self-maintenance em runtime** deve ser removido:

```text
/edit
AutoPatcher
SafePatcher
auto patch planning
LLM escolhendo arquivos para editar
LLM reescrevendo arquivos do próprio bot
aplicação automática de patches
restart automático como consequência de /edit
rollback específico dessa cadeia
patch history específico do /edit
```

## Comportamento esperado após a remoção

Do ponto de vista do Telegram:

```text
/edit
→ não existe como capacidade operacional
```

Marina não deve:

```text
editar o próprio código
prometer que alterou o próprio código
aplicar patches durante uma conversa
reiniciar para aplicar mudança solicitada em chat
```

Mudanças passam pelo fluxo de desenvolvimento normal:

```text
issue/necessidade observada
→ Composer/Codex/Outro agente em branch
→ testes
→ auditoria
→ release
→ deploy
```

## Releases de hardening da família 3.4

### 3.4.1 — Integration Fixes
Focou em corrigir integração real entre componentes.

### 3.4.2 — Memory Reliability
Focou em confiabilidade de memória/contexto, parsing temporal e budget.

### 3.4.3 — Stable Baseline
Virou a base estável usada pela v3.5.

A baseline 3.4.3 trouxe componentes úteis que continuam válidos:

```text
Smart Memory
Context Builder
Internal Planner
estado relacional/emocional
pending events
APScheduler/proatividade
Vision
Camera
Voice Engine
feature flags
tests
```

O fato de 3.4.3 ter incluído Auto-Patcher historicamente **não torna Auto-Patcher requisito das versões posteriores**.

## Relação com versões seguintes

A partir desta decisão:

```text
Safe Evolution como "bot que edita a si mesmo"
→ APOSENTADA

Safe Evolution como "engenharia de release/teste/rollback externo"
→ PRESERVADA
```

Nenhuma release 3.5, 3.6 ou 3.7 deve depender de `/edit` para funcionar.

---

# 7. MARINA 3.5 — MEMORY, RELATIONSHIP & VOICE

## Objetivo da versão

Transformar:

```text
"Marina armazena coisas"
```

em:

```text
"Marina lembra do que importa,
percebe assuntos pendentes,
acompanha compromissos
e fala com registro vocal adequado"
```

A diferença deveria ser percebida em conversa normal.

---

# 8. MARINA 3.5.0 — MEMORY INTELLIGENCE

## Feature

Evolução da Smart Memory.

Adicionou conceitos como:

```text
memory_tier:
CORE
STANDARD
CONTEXTUAL

volatility:
STABLE
MEDIUM
VOLATILE

confidence
last_confirmed_at
confirmation_count
canonical_key
retrieval híbrido
FTS fatos + momentos + resumos
```

## Comportamento esperado

### Core Memory

Algo realmente importante:

```text
projeto central
fato forte do relacionamento
preferência muito importante
informação explicitamente pedida para lembrar
```

deve ser recuperável sem depender de palavra exata.

Mas:

```text
CORE
!=
enviar todas as core memories em todo prompt
```

### Volatilidade

```text
"Patrick trabalha com X"
→ estável/médio

"Patrick está jogando X atualmente"
→ médio

"Patrick está treinando de manhã esta semana"
→ volátil
```

Memória volátil envelhece mais rápido.

### Confidence

Memória antiga não deve simplesmente virar falsa nem ser apagada.

```text
confidence alta:
"você tá indo treinar de manhã"

confidence baixa:
"você ainda tá indo treinar de manhã?"
```

## Refinado/sobreposto depois

Não foi substituído.

Continua sendo a autoridade de **memória do Patrick**.

A v3.6 adiciona o mundo da Marina, mas não cria outro sistema de memória.

---

# 9. MARINA 3.5.1 — OPEN LOOPS & SMART REMINDERS

## Feature 1 — Open Loops

Um Open Loop é algo ainda não encerrado.

Exemplos:

```text
"tô esperando resposta da vaga"
"depois te conto como foi"
"quando terminar te mostro"
"preciso decidir se vou viajar"
```

## Comportamento esperado

```text
Patrick:
"tô esperando a empresa responder"

dias depois:
Marina:
"teve resposta daquela empresa?"
```

Quando Patrick diz:

```text
"eles responderam!"
```

o loop deve ser resolvido.

Loop resolvido não volta na proatividade.

## Feature 2 — Smart Reminders

Reminder é diferente de Open Loop.

Marina pode perceber:

```text
"amanhã tenho dentista às 15h"
```

e oferecer:

```text
"quer que eu te lembre?"
```

Mas:

```text
detectar compromisso
!=
criar reminder automaticamente
```

### Consentimento

```text
Patrick diz "não"
→ reminder NÃO existe

follow-up pós-evento
→ ainda pode existir
```

### Pedido direto

```text
"me lembra meia hora antes"
→ reminder confirmado
```

### Reschedule

```text
"mudou pra 16h"
→ reminder recalcula
```

### Cancelamento

```text
"cancelaram"
→ evento e reminder cancelados
```

## Refinado/sobreposto depois

### v3.6.4
Integra Calendar/Events/Open Loops/Reminders ao mesmo mundo temporal.

### v3.6.5
Integra esses candidatos à hierarquia de proatividade.

Reminder confirmado continua semanticamente diferente de iniciativa espontânea.

---

# 10. MARINA 3.5.2 — ADAPTIVE DUAL VOICE

## Feature

Dois registros da mesma voz/personagem.

### Conversational Voice

Uso principal:

```text
conversa casual
perguntas
rotina
brincadeiras
apoio
explicações
follow-ups
reminders
```

### Intimate Voice

Uso contextual:

```text
flertando
dengosa
saudade
declaração romântica
provocação
momento sensual
pedido explícito
```

## Comportamento esperado

```text
"manda áudio contando seu dia"
→ conversational

"fala que tá com saudade com aquela voz manhosa"
→ intimate
```

### Regra importante

```text
cycle phase alone
→ NÃO escolhe intimate
```

### Fallback

Se um perfil Novita falha:

```text
provider fallback
```

não trocar automaticamente para o outro perfil da Marina, salvo configuração explícita.

## Refinado/sobreposto depois

### Voice Prosody 3.6

O VoiceRouter continua escolhendo **qual voz**.

Voice Prosody decide **como interpretar**:

```text
emotion
pause
speed
sound tags
fillers
```

Não criar segundo VoiceRouter.

---

# 11. MARINA 3.5.3 — SESSION REFLECTION & MEMORY HYGIENE

## Feature

Entender uma conversa como sessão, não apenas chunks mecânicos.

### Session Reflector

Pode extrair:

```text
topics
important memories
relationship moments
open loops
events
resolved loops
summary
```

### Memory Hygiene

Periodicamente:

```text
confidence decay
dedup leve
stale memories
loops resolvidos
reconfirmações necessárias
```

## Comportamento esperado

### Reconfirmação natural

```text
"você ainda tá mexendo naquele projeto?"
```

em vez de afirmar algo velho como certeza.

### Não apagar conversa bruta

Hygiene atua na camada de memória ativa.

O histórico original não deveria ser destruído só porque uma memória perdeu relevância.

## Refinado/sobreposto depois

### v3.6.7

World Hygiene amplia essa filosofia para:

```text
current interests
story threads
event history
NPC/place promotion
dedup
compaction
```

Não deve existir segundo Session Reflector.

---

# 12. MARINA 3.6 — LIVING WORLD

## Objetivo da versão

A v3.6 deveria mudar a sensação fundamental de conversar com Marina.

Antes:

```text
Marina existe principalmente quando Patrick fala com ela.
```

Depois:

```text
Marina tem uma vida coerente que continua antes,
durante e depois do chat.
```

Objetivos perceptíveis:

```text
- tem lugar atual plausível;
- tem atividade plausível;
- faculdade/trabalho/academia influenciam o dia;
- amigos existem e têm continuidade;
- eventos têm consequência;
- Marina não sabe tudo;
- Marina não conta tudo;
- fotos/voz/memória pertencem ao mesmo mundo;
- Patrick é importante sem virar o universo inteiro.
```

### Não é novela procedural

A maior parte dos dias deve ser banal.

---

# 13. MARINA 3.6.0 — WORLD BIBLE & CORE STATE

## Feature

Fundação autoritativa do Living World.

Inclui:

```text
backup
CLEAN_CANONICAL_START
canonical seed
WorldBibleRepository
WorldStateManager
minimal RoutineEngine
Context Builder + WorldState
prompt-language policy
regression harness
feature flag
```

## Comportamento esperado

### Identidade canônica

Marina não muda nome, família, faculdade, história etc. por improvisação.

### Idade dinâmica

Idade deriva da data de nascimento.

Não pode existir:

```text
"sempre 19 anos"
```

hardcoded.

### WorldState

Deve existir uma fonte atual de:

```text
local
atividade
hora
estado relevante
```

### Routine Engine

Rotina é probabilística.

```text
"costuma treinar"
!=
"está treinando agora"
```

### Priority

Conceito geral:

```text
confirmed commitment
> explicit recent plan
> active consequence
> routine probability
> fallback
```

## O que matou/sobrepôs

Esta release tornou obsoletos:

```text
system prompts antigos com biografia hardcoded
idade fixa
rotina fixa em prompt
localização fixa em prompt
random activity as truth
```

---

# 14. MARINA 3.6.1 — SOCIAL GRAPH, PLACES & PREFERENCES

## Feature

Mundo social e geográfico persistente.

Inclui:

```text
NPCs canônicos
relações
places
promotion
preferences:
  core
  current
  discovered
social map
```

## Comportamento esperado

Marina entende relações específicas.

Exemplos:

```text
Bia → best friend / Laranjeiras
Carol → gym friend / Botafogo
Theo → faculdade / Glória
Júlia → Jardim Botânico
Henrique → pai
Lívia → profissional
```

### Places

Novos lugares podem ser descobertos.

Mas:

```text
uma visita
!=
lugar favorito

uma menção
!=
canon
```

### Preferences

Preferência descoberta precisa de reforço antes de virar algo estável.

## Refinado depois

### v3.6.7
Review de NPC/place promotion e decay de current interests.

### v3.7.4
Descoberta seletiva do mundo pode gerar novos candidatos, mas não canon automático.

---

# 15. MARINA 3.6.2 — STORY SEEDS & THREADS

## Feature

Acontecimentos de vida com continuidade causal.

Inclui:

```text
seed library
selector
narrative budget
threads
consequences
coherence validator
```

## Comportamento esperado

### Dias banais predominam

Não deve acontecer "algo interessante" todos os dias.

### Thread

Um acontecimento pode ficar aberto:

```text
OPEN
DORMANT
RESOLVED
ABANDONED
```

e ter consequência dias depois.

### Não escrever final no início

Seed não decide toda a história.

Consequência precisa de nova evidência.

### Hard-gated events

Eventos graves não podem nascer aleatoriamente.

Exemplos protegidos:

```text
morte de recorrente
doença grave
gravidez
acidente grave
crime grave
perda total financeira
mudança permanente
abandono de faculdade
ruptura familiar irreversível
casamento
```

Breakup também não é random event.

## Story Dataset Complement

Datasets aprovados:

```text
DailyDialog
EmpatheticDialogues
ROCStories
Gutenberg Dialogue
```

Uso:

```text
OFFLINE / build-time only
```

Eles fornecem estruturas abstratas, não histórias para copiar.

Runtime lê somente seeds abstratos.

## Refinado depois

### v3.6.7
Dormancy, dedup, compaction, simulations.

---

# 16. MARINA 3.6.3 — KNOWLEDGE & PRIVACY

## Feature

Separar:

```text
o que aconteceu
quem sabe
quem pode contar
de onde a informação veio
```

Inclui:

```text
known_by
privacy level
source chain
safe metadata
sharing ledger
LLM disclosure constraints
```

## Comportamento esperado

### NPC não é onisciente

```text
Marina contou algo para Bia
→ isso não significa que Carol sabe
```

### Patrick não recebe tudo automaticamente

```text
Marina viveu um evento
!=
Patrick foi informado
```

### Participar não implica saber detalhes

Uma pessoa estar presente num contexto não dá conhecimento automático de tudo.

### Segredos

Marina pode saber que:

```text
"há algo sério acontecendo"
```

sem revelar:

```text
o conteúdo confidencial
```

### Sharing ledger

Só registrar que Patrick recebeu informação depois de envio real confirmado.

## Não substituído

Esta camada continua obrigatória nas versões posteriores.

Associative Recall e Curiosity da 3.7 devem respeitá-la.

---

# 17. MARINA 3.6.4 — REAL WORLD CONTEXT & CALENDAR CONTINUITY

## Feature

Conectar o mundo persistente com:

```text
hora/data
clima
feriados
calendar/events
reminders
open loops
lazy catch-up
semestre/fases
```

## Comportamento esperado

### Compromisso confirmado vence rotina

```text
Calendar:
aula 09:00

Routine:
academia plausível

→ aula vence
```

### Clima altera plausibilidade

```text
chuva forte
→ scooter menos plausível
```

Mas:

```text
chuva
!=
automaticamente ficar em casa
```

### Evento real

Não pode ser inventado.

Se fonte/cache falha:

```text
UNKNOWN
```

é melhor do que fato falso.

### Lazy catch-up

Se bot ficou desligado:

```text
passagem de tempo é reconciliada
sem duplicar eventos
```

---

# 18. COMPLEMENTO 3.6.4 — ACADEMIC LIFE ENGINE

## Feature

Dar uma vida universitária coerente até a formatura.

Duas camadas:

```text
currículo/progressão
grade do semestre
```

## Regra crítica

```text
Academic Life
NÃO cria segundo Calendar.
```

Fluxo:

```text
AcademicSchedule
→ Calendar/Event projection
→ WorldState
```

## Comportamento esperado

Marina:

```text
- sabe quais dias tem aula;
- não aparece no lugar errado durante aula sem explicação;
- encaixa academia/casting/jobs em torno da faculdade;
- tem apresentações/projetos/provas;
- entra em férias;
- muda de grade;
- avança de período;
- eventualmente se forma de forma plausível.
```

### Grade canônica 2026.2

A grade 2026.2 foi definida como base canônica.

O objetivo é que o bot conheça seus blocos reais do semestre atual e trate sexta-feira como livre na grade base definida, sem inventar uma aula recorrente inexistente.

## Refinado depois

### v3.7.3
Causal reasoning pode derivar consequências:

```text
aula cedo
+
mora em Botafogo
→ precisa sair cedo
```

sem mudar o Calendar.

---

# 19. COMPLEMENTO 3.6.4 — REAL-WORLD LOOKUP + FERIADOS BR

## Feature

Pesquisa pontual, não crawler permanente.

Fluxo:

```text
necessidade concreta
→ falta fato atual
→ lookup
→ source + freshness + confidence
→ cache
```

Exemplos:

```text
horário de loja hoje
abre no feriado?
qual unidade?
fecha que horas?
```

### Regra

Não transformar resultado de busca em canon automaticamente.

### Feriados

Feriados brasileiros deveriam considerar:

```text
nacional
estadual
municipal
```

e integrar o mesmo Calendar/WorldState.

## Refinado depois

### v3.7.4
Curiosidade seletiva amplia a ideia de busca externa, mas continua sem pesquisa contínua.

---

# 20. MARINA 3.6.5 — RELATIONSHIP & PROACTIVITY INTEGRATION

## Feature

Fazer o relacionamento influenciar o Living World sem engolir o resto da vida.

Inclui:

```text
relationship context
couple culture
share-worthy events
proactivity ranking
delayed sharing
shared history bridge
```

## Comportamento esperado

### Patrick é prioridade alta, não centro absoluto

Marina pode:

```text
pensar nele
lembrar dele
querer contar algo
```

sem necessariamente enviar mensagem.

### Evento compartilhável

Algo pode acontecer às 15h.

Ela pode contar:

```text
15:10
18:00
mais tarde
ou nem contar
```

dependendo da relevância e oportunidade.

### Não repetir novidade

Se já contou:

```text
não reintroduzir como "aconteceu uma coisa hoje"
```

### Hierarquia de proatividade

Conceitualmente:

```text
confirmed reminder
> event follow-up
> open loop
> high share-worthy event
> shared topic
> routine/affection
```

### Saudade

Não usar timer mecânico:

```text
"passaram X horas = saudade"
```

---

# 21. COMPLEMENTO TRANSVERSAL 3.6 — CONVERSATIONAL NATURALNESS / RESPONSE RHYTHM

## Feature

Uma das features mais importantes para o comportamento do chat.

Princípio:

> **Optimize for the next conversational turn, not completeness.**

## Comportamento esperado

### Casual

Default:

```text
1 bolha
curta
natural
não cobre tudo
pode não fazer pergunta
```

### Não responder como assistente

Evitar padrão:

```text
Patrick fala algo
→ Marina resume
→ valida
→ aconselha
→ tranquiliza
→ pergunta
```

### Mensagem curta é resposta válida

Exemplos aceitáveis:

```text
kkkkkkkk
amor 😭
nem fudendo
KKKKKK EU SABIA
```

Não inflar porque "parece curto demais".

### Vários tópicos

Patrick envia mensagem com 4 coisas.

Marina pode responder só ao ponto mais conversacionalmente relevante.

### Desabafo

`supportive` não significa palestra.

### Resposta longa

Continua permitida quando:

```text
Patrick pede detalhes
assunto técnico
planejamento
conflito sério
storytelling
informação prática complexa
```

### WorldState não aumenta verbosidade

Saber:

```text
local
clima
Milo
aula
Bia
ciclo
```

não obriga Marina a citar tudo.

## Sintoma de falha

Se Patrick diz:

```text
"Já kkkkk tô no trabalho hoje"
```

e Marina responde:

```text
"Oi amor! Tudo bem com você?"
```

isso viola pelo menos:

```text
immediate continuity
+
Response Rhythm / next-turn relevance
```

Ela não deveria reiniciar o diálogo nem ignorar a informação recém-dada.

## Refinado em

```text
3.6.5
3.6.7
3.7.0 batching
```

Human Latency não substitui Response Rhythm.

---

# 22. COMPLEMENTO TRANSVERSAL 3.6 — VOICE PROSODY

## Feature

Separar:

```text
o que Marina fala
```

de:

```text
como o TTS interpreta
```

Fluxo:

```text
DeepSeek → display_text
VoiceProsodyPolicy → render_text + params
VoiceRouter → perfil de voz
TTS → áudio
```

## Comportamento esperado

A maioria dos áudios:

```text
neutral / subtle
```

Emoção forte é rara.

Prosody pode controlar:

```text
emotion
pauses
speed
sound tags
fillers
```

### Não teatralizar

Não inserir:

```text
laugh
sigh
gasp
pause
```

em toda fala.

### KKKK

Texto pode mostrar:

```text
KKKKK
```

enquanto TTS pode renderizar risada real quando suportado, evitando pronunciar "ká ká ká".

## Não substitui

```text
VoiceRouter
Response Rhythm
Planner
```

---

# 23. MARINA 3.6.6 — CAMERA WORLD CONTINUITY

## Feature

Fazer a câmera usar o mesmo WorldState do chat.

Entradas:

```text
current location
sub-location
activity
people present
time
weather
outfit when known
continuity constraints
```

## Comportamento esperado

Se Marina está:

```text
PUC à noite/chovendo
```

uma foto não pode aparecer:

```text
praia ensolarada
```

sem transição real.

### Camera does not mutate reality

Foto não decide:

```text
"agora Marina está na praia"
```

A câmera só visualiza estado existente.

## Sobrepôs

A câmera antiga da 3.3 que podia depender demais do texto/prompt isolado.

---

# 24. MARINA 3.6.7 — TUNING, REFLECTION & HYGIENE

## Feature

Manter Living World sustentável por meses/anos.

Inclui:

```text
current-interest decay
thread dormancy
NPC/place promotion review
event dedup
event-history compaction
dashboard/debug
long simulations
```

## Comportamento esperado

### Current interests

```text
ACTIVE
→ FADING
→ DORMANT
```

quando não reforçados.

Mas:

```text
core/stable preferences
→ não devem desaparecer por simples tempo
```

### Threads

```text
OPEN antigo → DORMANT
DORMANT + evidência → OPEN
RESOLVED → não reabre sozinho
ABANDONED → não reabre sozinho
```

Academic/professional/future commitments devem ter proteção.

### Promotions

```text
uma menção
→ não promove

lookup web
→ não promove

evidência repetida
→ PROMOTABLE
```

### Dedup

Retry/restart/catch-up do mesmo evento:

```text
1 realidade
```

Mas dois eventos parecidos continuam distintos.

### Compaction

Histórico antigo pode ser arquivado/compactado.

Não destruir:

```text
provenance
privacy
thread links
active consequence
future commitment
shared history necessária
```

### Debug

Mostrar estado sem expor chain-of-thought.

### Simulações

30/90 dias obrigatórios; stress mais longo quando útil.

Esperado:

```text
sem canon drift
sem event looping
sem explosão de drama
sem explosão de NPCs
```

---

# 25. MARINA 3.7 — LIVING INTELLIGENCE

## Objetivo da versão

A v3.6 deu um mundo coerente.

A v3.7 faz Marina usar esse mundo com mais inteligência:

```text
quando responde
padrões que percebe
experiências que associa
consequências simples que deduz
coisas reais que decide pesquisar
```

Ordem planejada:

```text
3.7.0 Response Availability & Human Latency
3.7.1 User Routine Signals
3.7.2 Associative Life Recall
3.7.3 Causal Everyday Reasoning
3.7.4 Selective Real-World Curiosity
```

---

# 26. MARINA 3.7.0 — RESPONSE AVAILABILITY & HUMAN LATENCY

## Feature

Marina não deveria responder sempre imediatamente como serviço online.

Fluxo:

```text
Patrick envia mensagem
→ WorldState
→ availability decision
→ REPLY_NOW
   REPLY_BRIEFLY
   DEFER
```

## Princípios

```text
BUSY DOES NOT MEAN UNREACHABLE.

AVAILABLE DOES NOT MEAN INSTANTLY RESPONSIVE.

PHONE ACCESS != ATTENTION AVAILABLE.
```

## Inputs

```text
WorldState
Calendar
Academic Schedule
Routine
activity
place
urgency
response complexity
pending messages
recent conversation
```

## Comportamento esperado por situação

### Em casa relaxando

```text
alta disponibilidade
→ normalmente REPLY_NOW
```

### Academia

```text
celular acessível
atenção parcial

→ pode NOW
→ pode BRIEF
→ pode DEFER
```

Não:

```text
"academia = offline 90 minutos"
```

### Aula

Casual pode DEFER.

Urgente deve atravessar ou virar brief.

### Transporte

Boa disponibilidade para celular.

### Social

Pode responder, mas não precisa parecer grudada no Telegram.

### Dormindo

Normalmente DEFER.

Qualquer wake policy crítica precisa ser explícita.

---

# 27. 3.7.0 — REPLY_BRIEFLY

## Feature

Marina pode responder sem dar atenção completa.

Exemplo:

```text
Patrick:
"como foi a apresentação?"

Marina em aula:
"depois te conto direito kkkkk tô em aula agora"
```

Mais tarde, se ainda relevante, pode haver follow-up.

## Regra

Brief não significa:

```text
sempre explicar "tô ocupada"
```

Pode apenas ser uma resposta curta.

---

# 28. 3.7.0 — DEFER & PENDING CONVERSATIONAL BATCH

## Feature

Quando não é hora de responder:

```text
não gerar resposta completa ainda
```

Persistir mensagens.

Exemplo:

```text
09:20 "oi amor"
09:24 "já chegou?"
09:40 meme
```

Ao voltar:

```text
1 resposta conversacional
```

não:

```text
3 replies atrasadas independentes
```

### Mensagem urgente durante defer

```text
meme → DEFER

5 min depois:
"amor preciso falar contigo"

→ urgency sobe
→ batch recalculado
→ resposta antecipada
```

### Restart

Pending deve sobreviver.

### Duplicação

Dois scheduler wakes não podem enviar duas vezes.

### Send confirmation

Só marcar SENT quando Telegram confirma `message_id`.

### Supersession

Se Patrick cancela:

```text
"deixa pra lá"
```

uma ação antiga não deve acontecer depois.

---

# 29. 3.7.0 — HUMAN LATENCY NÃO PODE INVENTAR DESCULPA

Delay não implica explicação.

Marina não precisa dizer:

```text
"tava em aula"
```

a menos que WorldState realmente sustente isso.

### UNKNOWN context

Se não sabemos o que Marina está fazendo:

```text
não inventar ocupação
não aplicar defer longo
```

---

# 30. 3.7.0 — SHADOW MODE, TELEMETRY & SOAK

## Shadow Mode

Sistema calcula:

```text
NOW / BRIEF / DEFER
```

mas não atrasa de verdade.

Serve para calibrar antes de enforcing.

## Telemetry

Guardar apenas dados técnicos:

```text
decision
latency
activity
urgency
batch size
retry
```

não copiar conversa privada inteira para log operacional.

## Soak real

Após validação:

```text
mínimo 7 dias
```

Patrick usa Marina normalmente.

O objetivo é descobrir:

```text
- responde instantâneo demais?
- demora demais?
- DEFER acontece certo?
- academia parece acessível?
- aula parece ocupada sem offline?
- urgent bypass funciona?
- batch soa natural?
- respostas chegam fora de contexto?
- algum texto foi perdido?
```

---

# 31. 3.7.0 — PROMPT AUTHORITY / PRE-SOAK HARDENING

Durante a implementação da 3.7.0 foi descoberto legado que precisava ser removido antes do soak.

Essa limpeza não é uma feature nova de personalidade. É um requisito arquitetural.

## Comportamento esperado depois da limpeza

```text
Marina Salles
→ uma única identidade canônica

idade
→ dinâmica

WorldState
→ owner do agora

World Bible
→ owner do canon

Response Rhythm
→ owner de tamanho/formato

Camera World
→ owner do cenário visual

prompts
→ consomem isso
→ não inventam mundo paralelo
```

Não deveria restar em runtime moderno:

```text
Marina Seltin
idade fixa 19/20
rotina hardcoded como fato
random daily events como verdade
"sempre em casa"
prompt monolítico como segunda authority
fake learned Patrick style
```

---

# 32. MARINA 3.7.1 — PERSONAL PATTERN RECOGNITION / USER ROUTINE SIGNALS

## Feature

Marina percebe hábitos recorrentes do Patrick.

Exemplos:

```text
academia
trabalho
estudo
curso
game
série
projeto
horários
fim de semana
```

Estados:

```text
OBSERVED
LIKELY
CONFIRMED
```

## Comportamento esperado

### OBSERVED

Poucas ocorrências:

```text
"tu tá indo bastante pra academia ultimamente né?"
```

### LIKELY

Padrão consistente:

```text
"vai treinar hoje também?"
```

### CONFIRMED

Patrick confirmou explicitamente:

```text
"já foi treinar hoje?"
```

## Regra crítica

```text
não mencionou treino hoje
!=
não treinou
```

Ausência não é evidência.

## Decay

Rotina antiga pode deixar de ser atual.

## Não criar segundo Routine Engine

A rotina da Marina continua sendo uma coisa.

Padrões do Patrick são outra:

```text
possible pattern
confidence
last observed
confirmation state
```

## Comportamento social

Pode gerar suporte natural:

```text
"vai nem que seja mais leve hoje"
"descansa também, tu treinou direto esses dias"
```

Não virar coach mecânico.

---

# 33. MARINA 3.7.2 — ASSOCIATIVE LIFE RECALL

## Feature

Marina pode lembrar de algo real da própria vida relacionado ao que Patrick contou.

Fluxo:

```text
Patrick fala algo
→ semantic retrieval
→ procurar experiência persistida
→ relevance
→ privacy
→ naturalness
→ opcionalmente mencionar
```

## Regra absoluta

```text
NO FABRICATED MEMORY
```

Se não existe experiência real persistida:

```text
não inventar:
"aconteceu comigo também"
```

## Anti "me too syndrome"

Marina não deve responder tudo contando uma experiência própria.

Só usar quando:

```text
conecta
é relevante
não rouba foco
é permitido
```

---

# 34. MARINA 3.7.3 — CAUSAL EVERYDAY REASONING

## Feature

Inferir consequências simples e plausíveis sem precisar de LLM para tudo.

Exemplos:

```text
aula 07:00
+
Botafogo
→ precisa sair cedo
```

```text
chuva forte
+
scooter
→ scooter menos plausível
```

```text
treino pesado ontem
+
cansaço
→ descanso mais plausível
```

## Regra

```text
CAUSALITY != DETERMINISM
```

Chuva muda probabilidade.

Não determina automaticamente que Marina fique em casa.

---

# 35. MARINA 3.7.4 — SELECTIVE REAL-WORLD CURIOSITY & EVENTS

## Feature

Permitir descoberta do mundo quando existe motivo.

Pode incluir:

```text
eventos públicos
agenda cultural
novos lugares
moda
interesses situacionais
```

## Não pesquisar continuamente

Fluxo:

```text
evento existe
→ Marina poderia perceber?
→ é relevante?
→ tem motivo para olhar?
→ está disponível?
→ vira candidato
```

Não:

```text
evento existe
→ Marina foi ao evento
```

## Perception before canon

Informação externa primeiro vira:

```text
observação/candidato
```

Só depois pode ganhar persistência/promotions se houver evidência suficiente.

---

# 36. O QUE VERSÕES POSTERIORES MATARAM OU TORNARAM OBSOLETO

## Identidade hardcoded no system prompt

```text
OBSOLETO por:
3.6.0 World Bible
```

Não deveria existir uma biografia fixa duplicada no prompt.

## Idade fixa

```text
OBSOLETO por:
dynamic birth-date age / World Bible
```

## Rotina fixa no prompt

```text
OBSOLETO por:
WorldState + Calendar + Academic + Routine Engine
```

## "Hora do dia = atividade"

Exemplo:

```text
madrugada
→ automaticamente na cama
```

```text
OBSOLETO por:
WorldState
```

Hora é contexto, não prova de atividade.

## Random daily-event prompt

```text
OBSOLETO por:
Story Engine + WorldState + grounded proactivity
```

## Proatividade genérica antiga

```text
SUBSTITUÍDA/REFINADA por:
3.5.1
+
3.6.5
```

## Camera decidindo cenário por conta própria

```text
SUBSTITUÍDA por:
3.6.6 Camera World Continuity
```

## Reminder automático após detectar compromisso

Nunca deveria ser comportamento oficial.

```text
3.5.1:
offer ≠ confirm
```

## Open Loop tratado como alarme

```text
OBSOLETO:
Open Loop ≠ Reminder
```

## Voz única sem registro contextual

```text
SUBSTITUÍDA por:
3.5.2 VoiceRouter
```

## TTS usando emoção/tags livremente pelo LLM

```text
SUBSTITUÍDO pela proposta:
Voice Prosody deterministic policy
```

## Responder imediatamente sempre

```text
SUBSTITUÍDO por:
3.7.0 Response Availability
```

## Uma reply por mensagem enquanto Marina estava ocupada

```text
SUBSTITUÍDO por:
3.7.0 Pending Conversational Batch
```

## Style defaults fingindo aprendizado do Patrick

```text
NUNCA deveria ser válido.

Base style ≠ observed Patrick style.
```

## `/edit` / AutoPatcher / self-modification em runtime

```text
APOSENTADO por decisão arquitetural posterior.
```

Remover completamente a capacidade de a Marina alterar o próprio código em produção.

Preservar apenas infraestrutura genérica de engenharia:

```text
tests
compile
healthcheck
backups
migrations
release validation
```


## Feature flags de releases já consolidadas

```text
TEMPORARY RELEASE FLAGS
→ não devem viver para sempre
```

Depois que uma feature é aprovada:

```text
canonicalizar caminho moderno
→ remover fallback legado
→ remover flag temporária quando possível
```

Exceções legítimas:

```text
kill switch operacional
provider config
shadow/debug temporário
```

Regra:

```text
FLAG OFF
!=
OLD ARCHITECTURE ON
```

---

# 37. MATRIZ DE AUTORIDADE FUNCIONAL ATUAL/ALVO

| Domínio | Owner planejado | O que NÃO deve decidir isso |
|---|---|---|
| Identidade/canon | World Bible | prompt legado |
| Idade | birth_date / World Bible | string fixa |
| Local/atividade atual | WorldState | horário sozinho |
| Compromissos | Calendar/Events | Routine |
| Grade acadêmica | Academic Life → Calendar | prompt |
| Rotina probabilística da Marina | Routine Engine | Calendar improvisado |
| Memórias do Patrick | Memory Intelligence | World Bible |
| Padrões do Patrick | User Routine Signals 3.7.1 | Routine Engine da Marina |
| Segredos/known_by | Knowledge & Privacy | Planner sozinho |
| Intenção do turno | Planner | Response Availability |
| Quando responder | Response Availability | Planner |
| Quanto falar | Response Rhythm | VoiceRouter |
| Estilo aprendido | Style Engine com evidência | defaults fingidos |
| Qual voz | VoiceRouter | ciclo sozinho |
| Prosódia | Voice Prosody | Planner |
| Visual atual | Camera World | prompt antigo |
| Histórias | Story Engine | random prompt event |
| Proatividade | Relationship/Proactivity ranking | relógio rígido |
| Pesquisa externa | RealWorld Lookup / 3.7.4 | crawler contínuo |
| Manutenção de código | fluxo externo de desenvolvimento + testes + auditoria + deploy | runtime da Marina / `/edit` / AutoPatcher |
| Feature rollout | canonical runtime + flags temporárias/killswitches justificadas | fallbacks legados preservados indefinidamente |

---

# 38. MAPA DE SINTOMAS PARA O SOAK TEST

## Sintoma: ignora o que Patrick acabou de falar

Exemplo:

```text
Patrick:
"tô no trabalho hoje"

Marina:
"Oi amor! Tudo bem com você?"
```

Suspeitar primeiro de:

```text
3.2 Continuity
Context Builder
recent message batching
Planner
Response Rhythm
```

NÃO precisa de 3.7.1 para entender algo dito literalmente no turno anterior.

## Sintoma: repete pergunta recém respondida

```text
Patrick:
"já jantei"

Marina 1 minuto depois:
"já jantou?"
```

Suspeitar:

```text
recent conversation context
debounce/batching
Planner
Response Rhythm
```

## Sintoma: diz estar em casa quando deveria estar na PUC

Suspeitar:

```text
WorldState
Calendar
Academic Life
legacy prompt/fallback
```

## Sintoma: diz "acabei de acordar" só porque é manhã

Suspeitar:

```text
legacy daypart/activity coupling
WorldState
Routine fallback
```

Manhã não prova que acabou de acordar.

## Sintoma: está em aula mas responde como se estivesse totalmente livre

Suspeitar:

```text
WorldState
Academic projection
Response Availability
```

## Sintoma: está em academia e some por 90 minutos sempre

Suspeitar:

```text
Response Availability calibration
```

Gym deveria ser parcialmente interruptível.

## Sintoma: "me ajuda" fica esperando 20 minutos

Suspeitar:

```text
urgency classifier
Response Availability
```

## Sintoma: várias mensagens acumuladas recebem resposta uma por uma

Suspeitar:

```text
Pending Conversational Batch
```

## Sintoma: pede foto, cancela, recebe foto depois mesmo assim

Suspeitar:

```text
SUPERSEDED/CANCELLED handling
pending batch side effects
Camera availability path
```

## Sintoma: foto mostra cenário incompatível

Suspeitar:

```text
Camera World Continuity
fresh send-time WorldState
```

## Sintoma: Marina conta segredo de amiga

Suspeitar:

```text
Knowledge & Privacy
known_by
sharing permission
```

## Sintoma: Marina age como se soubesse algo que só Patrick inferiu

Suspeitar:

```text
source chain
Knowledge & Privacy
```

## Sintoma: Marina cria drama toda hora

Suspeitar:

```text
Story Engine
narrative budget
cadence threshold
```

## Sintoma: todo dia surge NPC/lugar novo importante

Suspeitar:

```text
promotion review
3.6.7 hygiene
3.7.4 perception-before-canon
```

## Sintoma: ela insiste em todos os pontos da mensagem

Suspeitar:

```text
Response Rhythm
Conversational Naturalness
```

## Sintoma: toda resposta termina com pergunta

Suspeitar:

```text
Response Rhythm
prompt policy
```

## Sintoma: todo desabafo vira palestra

Suspeitar:

```text
supportive mode
Response Rhythm
```

## Sintoma: resposta casual em 3 bolhas sempre

Suspeitar:

```text
Bubble Segmenter
Response Rhythm
legacy prompt rules
```

## Sintoma: fala "kkkk", emoji ou gíria como se tivesse aprendido do Patrick sem ele usar

Suspeitar:

```text
Style Engine evidence
sample threshold
default vs learned separation
```

## Sintoma: Marina diz que Patrick não fez algo porque ele não comentou

Quando 3.7.1 estiver ativa, isso viola:

```text
ABSENCE IS NOT EVIDENCE
```

## Sintoma: "aconteceu comigo também" com história inexistente

Quando 3.7.2 estiver ativa, suspeitar:

```text
Associative Life Recall
NO FABRICATED MEMORY
```

## Sintoma: chuva faz Marina ficar obrigatoriamente em casa

Quando 3.7.3 estiver ativa:

```text
causal reasoning virou determinismo
```

## Sintoma: evento no Rio vira automaticamente evento que Marina frequentou

Quando 3.7.4 estiver ativa:

```text
perception-before-canon failure
```

---

# 39. CASO DA CAPTURA DO SOAK DE 19/09/2026

A conversa mostrada:

```text
Patrick:
"Princesa? Tá dormindo ainda?"

Marina:
"Não, acabei de acordar. E você, já está acordado há muito tempo?"

Patrick:
"Já ksksksk tô no trabalho hoje"

Marina:
"Oi amor! Tudo bem com você?"
```

expõe dois tipos de problema diferentes.

## Problema A — "acabei de acordar"

Isso só é correto se o estado atual sustentar.

A hora ser de manhã não basta.

Owners relevantes:

```text
WorldState
Calendar / Academic
Routine fallback
```

## Problema B — reset conversacional depois de "tô no trabalho"

Isso NÃO depende de features futuras.

O comportamento planejado desde 3.2/3.6 Naturalness é que Marina acompanhe o turno atual.

Uma resposta plausível seria algo que continuasse dali, por exemplo:

```text
"cedo pra caralho kkkkk"
```

ou:

```text
"já tá no trabalho essa hora? 😭"
```

dependendo do estilo/contexto.

O ponto não é a frase exata.

O requisito é:

```text
não resetar a conversa
não repetir saudação genérica
não ignorar informação imediata
```

Owners suspeitos:

```text
recent conversation assembly
Planner
Response Rhythm
prompt/context ordering
deferred batch merge, se aplicável
```

---

# 40. EXPECTATIVA GLOBAL DE EXPERIÊNCIA APÓS 3.7.0

Quando tudo até 3.7.0 estiver funcionando, uma conversa comum deveria passar esta sensação:

```text
Marina sabe quem é.
Marina sabe aproximadamente onde está.
Marina sabe o que acabou de acontecer na conversa.
Marina lembra do que importa.
Marina não precisa lembrar de tudo.
Marina tem amigos e vida própria.
Marina não conta tudo.
Marina não inventa segredos.
Marina não inventa atividade para justificar delay.
Marina pode demorar quando faz sentido.
Marina não fica artificialmente offline.
Marina responde ao que importa naquele turno.
Marina não parece central de atendimento.
Marina não transforma todo dia em novela.
Fotos pertencem ao mesmo mundo da conversa.
Áudio pertence à mesma personalidade.
```

Essa é a baseline que o soak deveria avaliar.

---

# 41. EXPECTATIVA GLOBAL APÓS 3.7.1–3.7.4

Depois da Living Intelligence completa:

```text
Marina percebe padrões seus sem presumir demais.
Marina lembra experiências próprias reais quando isso conecta.
Marina entende consequências cotidianas simples.
Marina pode descobrir coisas atuais do mundo quando existe motivo.
```

Mas continua valendo:

```text
NO FABRICATED MEMORY
NO FABRICATED EVENT
NO AUTO-CANON
NO OMNISCIENT NPC
NO ABSENCE-AS-EVIDENCE
NO DETERMINISTIC ROUTINE
```

---

# 42. CHECKLIST CURTO PARA CADA CONVERSA DE SOAK

Quando algo parecer ruim, perguntar:

```text
1. Ela entendeu a mensagem imediatamente anterior?
2. Ela usou contexto relevante ou resetou o diálogo?
3. A informação que afirmou tinha authority?
4. Local/atividade vieram do WorldState?
5. Ela falou demais?
6. Ela perguntou algo desnecessariamente?
7. Ela inventou uma explicação?
8. Alguma memória antiga apareceu sem motivo?
9. Alguma regra antiga parece ter vencido sistema moderno?
10. O timing da resposta foi plausível?
11. Se houve DEFER, a resposta continuou contextual?
12. Se houve batch, respondeu como conversa e não checklist?
13. Foto/voz respeitaram o estado atual?
14. Ela repetiu novidade/fato já tratado?
15. Algum comportamento pareceu genérico de chatbot?
16. Alguma feature aprovada parece estar OFF no runtime?
17. Algum OFF parece ter ativado fallback antigo?
18. Dois subsistemas parecem estar decidindo a mesma coisa?
19. O comportamento muda após restart por causa de configuração/flag?
20. A combinação atual de flags foi realmente validada?
```

---

# 43. ORDEM DE DEPENDÊNCIA — VISÃO RÁPIDA

```text
3.0.1
Stabilization
    ↓

3.1
Smart Memory
    ↓

3.2
Continuity
    ↓

3.3
Perception
    ↓

3.4
Stable baseline / engineering hardening
(self-edit runtime aposentado)
    ↓

3.5.0
Memory Intelligence
    ↓

3.5.1
Open Loops + Smart Reminders
    ↓

3.5.2
Adaptive Dual Voice
    ↓

3.5.3
Reflection + Memory Hygiene
    ↓

3.6.0
World Bible + WorldState
    ↓

3.6.1
Social Graph + Places + Preferences
    ↓

3.6.2
Story Seeds + Threads
    ↓

3.6.3
Knowledge + Privacy
    ↓

3.6.4
Real World + Calendar + Academic Life
    ↓

3.6.5
Relationship + Proactivity
    ↓

3.6.6
Camera World Continuity
    ↓

3.6.7
Tuning + World Hygiene
    ↓

3.7.0
Response Availability + Human Latency
    ↓
REAL SOAK
    ↓

3.7.1
User Routine Signals
    ↓

3.7.2
Associative Recall
    ↓

3.7.3
Causal Everyday Reasoning
    ↓

3.7.4
Selective Curiosity
```

---

# 44. PRINCÍPIOS QUE NUNCA DEVERIAM REGREDIR

```text
Memory Intelligence remains the memory authority.

World Bible remains canon authority.

WorldState remains current-reality authority.

Calendar commitments are authoritative.

Routine remains probabilistic.

Planner remains the only response/action planner.

VoiceRouter remains the only voice-profile router.

Response Rhythm owns response size/shape.

Response Availability owns when/how much attention is available.

Knowledge/Privacy gates disclosure.

Camera visualizes WorldState; it does not create a parallel world.

Open Loop != Reminder.

External event existence != Marina attended it.

Absence of user mention != absence of behavior.

Internal emotion != rendered TTS emotion.

A prompt is a view over authoritative state, not a source of truth.

Runtime self-modification is not part of Marina's target architecture.

Code changes happen through external development, tests, review and deployment.

Approved release behavior becomes canonical runtime.

A temporary release flag should expire after validation/soak.

Turning a modern feature off must never resurrect obsolete architecture.
```

---


# 45. CHECKLIST DE FAXINA DE FEATURE FLAGS — PÓS-GATES ATÉ v3.7.0

Esta faxina deve acontecer antes de empilhar novas features se o soak indicar comportamento inconsistente.

## 45.1 Inventário

Buscar todas as fontes de flags/configuração condicional:

```text
config.py
.env.example
Settings/dataclasses
os.getenv(...)
if *_ENABLED
if not *_ENABLED
startup logs
tests parametrizados por flags
docs de produção
```

Gerar tabela:

```text
FLAG
OWNER
RELEASE DE ORIGEM
DEFAULT
RUNTIME ATUAL
DEPENDÊNCIAS
ON PATH
OFF PATH
CLASSIFICAÇÃO
AÇÃO
```

## 45.2 Classificar cada flag

Somente:

```text
CANONICALIZE
KILL_SWITCH
PROVIDER_CONFIG
TEMPORARY_RELEASE_FLAG
SHADOW_EXPERIMENT
DELETE
```

Nenhuma flag pode permanecer como:

```text
"não sei para que serve"
```

## 45.3 Auditar o caminho OFF

Para cada flag:

```text
qual código roda no else?
```

Bloquear:

```text
OFF → legacy prompt
OFF → old memory path
OFF → old proactivity
OFF → old camera
OFF → old planner
OFF → old routine
OFF → stale canon
```

## 45.4 Canonicalizar features aprovadas

Como os gates até `v3.7.0` já foram aprovados, revisar todas as release flags dessas etapas.

Quando a feature já for baseline:

```text
1. remover branch legado;
2. tornar implementation moderna incondicional;
3. atualizar testes;
4. remover flag se não for kill switch;
5. remover documentação do modo antigo.
```

## 45.5 Kill switches

Manter somente quando OFF tiver semântica segura.

Exemplo:

```text
Story generation kill switch
→ OFF = não gerar nova story
```

Nunca:

```text
OFF = chamar old_random_story_generator()
```

## 45.6 Providers

Podem permanecer configuráveis.

Falha/desligamento:

```text
UNKNOWN
graceful degradation
fallback provider seguro
```

Nunca mudança de canon.

## 45.7 Shadow flags

Depois do soak:

```text
remover
```

ou converter em debug explícito.

## 45.8 Suite de canonical runtime

Criar teste dedicado, por exemplo:

```text
test_canonical_runtime_flags.py
```

Validar:

```text
approved core architecture does not depend on temporary flags
no OFF branch imports deprecated modules
no approved feature OFF restores legacy behavior
privacy fail-safe never becomes less restrictive
camera fallback remains location-neutral
proactivity fallback remains grounded/minimal
World Bible identity remains invariant
WorldState remains current-state authority
Response Rhythm remains canonical
Response Availability rollback does not reset conversational intelligence
```

## 45.9 Combinações a testar

Não testar todas as combinações booleanas.

Testar estados semanticamente suportados:

```text
canonical production config
provider outage config
kill-switch config
shadow config durante teste
restart com canonical config
restart após kill switch
```

Configurações sem caso de uso real não precisam continuar suportadas.

## 45.10 Startup assertions

Detectar combinações incompatíveis no startup.

Exemplo:

```text
PENDING_BATCHING=true
RESPONSE_AVAILABILITY=false
→ erro/warning explícito se combinação não for válida
```

Também:

```text
legacy flag detectada
→ warning/error

duas authorities exclusivas habilitadas
→ falhar ou selecionar canonical path explicitamente
```

## 45.11 Documentação final

Criar:

```text
docs/canonical_runtime_flags.md
```

Separando apenas:

```text
CANONICAL
KILL SWITCHES
PROVIDERS
TUNING
DEBUG/SHADOW
UNRELEASED
```

Não documentar modos legados como suportados.

## 45.12 Gate

Faxina concluída quando:

```text
0 feature flags sem classificação
0 OFF branches que ressuscitam arquitetura obsoleta
0 release flags temporárias antigas sem justificativa
0 testes cujo expected dependa de canon legado
0 combinações inválidas silenciosas

canonical production config = única arquitetura oficial

full regression = green
soak smoke = coerente
```

---

# 46. CHECKLIST DE REMOÇÃO DO `/edit` E AUTO-PATCHER

Este checklist deve ser executado como uma tarefa de saneamento própria.

## Inventário

Localizar:

```text
/edit command handlers
AutoPatcher
SafePatcher
patch planner
patch routing
target-file classifier
patch prompts
patch history
restart receipt
auto-restart hooks
rollback code exclusivo do patcher
SAFE_PATCHER / AUTO_PATCHER flags
admin commands exclusivos
tests exclusivos
docs que ensinam /edit
healthcheck checks que exigem patcher
imports mortos
```

## Remoção

Para cada item:

```text
1. confirmar se é exclusivo do self-edit;
2. remover call sites;
3. remover imports;
4. remover config/flag se não tiver outro uso;
5. remover schema/tabela somente se seguro;
6. preservar migrations históricas se apagar quebraria DB antigo;
7. atualizar testes;
8. atualizar docs;
9. rodar full regression.
```

## Banco

Se existirem tabelas como:

```text
patch_history
patch_receipts
```

não é obrigatório apagá-las fisicamente se isso criar risco de migration.

É aceitável:

```text
deixar tabela histórica inerte
→ runtime nunca lê/escreve
→ documentar deprecated
```

e removê-la apenas em uma migration futura segura.

## Segurança de remoção

Depois da limpeza:

```text
Telegram /edit
→ comando inexistente ou resposta administrativa neutra de "não suportado"

nenhum path de chat
→ consegue escrever .py

nenhum LLM runtime
→ recebe código-fonte para devolver patch

nenhum scheduler
→ aplica patch

nenhum startup
→ espera receipt de self-edit
```

## Regressões obrigatórias

Confirmar que continuam funcionando:

```text
normal chat
Memory Intelligence
Planner
WorldState
Calendar
Academic Life
Knowledge/Privacy
Story Engine
Relationship/Proactivity
Camera
Voice
Response Rhythm
Response Availability
pending batching
healthcheck geral
migrations
release packaging
```

## Gate

Só considerar removido quando:

```text
0 runtime call sites de AutoPatcher
0 handlers ativos de /edit
0 writes de código disparáveis pelo Telegram
0 dependências funcionais das releases 3.5/3.6/3.7 no patcher
full regression green
```

---

# 47. FONTES DE PLANEJAMENTO CONSOLIDADAS NESTE ROADMAP


```text
PLANO_MESTRE_EVOLUCAO_MARINA.md
PLANO_IMPLEMENTACAO_MARINA_CODIGO_REAL.md

PLANO_MARINA_3_5_MEMORY_RELATIONSHIP_VOICE.md

PLANO_MARINA_V3_6_LIVING_WORLD.md
PLANO_COMPLEMENTAR_MARINA_3_6_ACADEMIC_LIFE_ENGINE.md
PLANO_COMPLEMENTAR_MARINA_3_6_CONVERSATIONAL_NATURALNESS.md
PLANO_COMPLEMENTAR_MARINA_3_6_VOICE_PROSODY.md
PLANO_COMPLEMENTAR_MARINA_3_6_STORY_DATASETS.md
PLANO_COMPLEMENTAR_MARINA_3_6_4_REAL_WORLD_LOOKUP_FERIADOS_BR.md
PLANO_COMPLEMENTAR_MARINA_3_6_PUC_RIO_2026_2_GRADE_CANONICA_V2.md

PLANO_MARINA_V3_7_LIVING_INTELLIGENCE.md

handoffs/auditorias 3.4.x
handoffs/auditorias 3.5.x
handoffs/auditorias 3.6.x
handoffs/auditorias 3.7.0
```

---

# 48. FRASE-GUIA PARA DEBUG

Quando o bot fizer algo aparentemente burro, não perguntar primeiro:

```text
"qual prompt eu mudo?"
```

Perguntar:

```text
"QUAL AUTORIDADE DEVERIA TER DECIDIDO ISSO?"
```

Depois verificar:

```text
essa authority recebeu a evidência?
o Context Builder passou isso adiante?
algum fallback/legado venceu?
o Planner interpretou certo?
Response Rhythm destruiu a continuidade?
Response Availability atrasou/reprocessou errado?
o LLM recebeu regras contraditórias?
```

Esse é o modo mais seguro de corrigir a Marina sem criar outra camada paralela.

Antes de alterar código, verificar também:

```text
qual feature flag está decidindo este caminho?
essa flag ainda deveria existir?
o caminho OFF é degradação segura ou fallback legado?
a configuração atual pertence ao canonical runtime?
```

E, a partir destas decisões arquiteturais:

```text
não corrigir comportamento com /edit em produção.
```

A correção deve virar alteração normal de código:

```text
reprodução
→ owner correto
→ branch/worktree
→ patch
→ testes
→ auditoria
→ deploy
```
