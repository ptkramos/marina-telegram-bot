# PLANO MESTRE — MARINA SELTIN 3.5
## Memory Intelligence, Smart Reminders, Open Loops & Adaptive Dual Voice

**Base:** Marina Seltin v3.4.3 estável  
**Objetivo da 3.5:** transformar a memória da Marina de “armazenamento e recuperação” em **continuidade inteligente de relacionamento**, com lembranças priorizadas, assuntos em aberto, compromissos acompanhados, lembretes consentidos e voz adaptada ao contexto emocional.

---

# 1. VISÃO DA RELEASE

A Marina 3.4.3 já possui uma fundação funcional:

- SQLite persistente.
- Smart Memory com consolidação automática.
- FTS5 para fatos, momentos e resumos.
- Context Builder.
- Internal Planner.
- Estado emocional e relacional.
- Eventos pendentes e follow-ups.
- APScheduler / proatividade contextual.
- Vision Service.
- Câmera com continuidade.
- Voice Engine via Novita MiniMax, ElevenLabs e Gemini.
- Auto-Patcher protegido.
- Feature flags e testes.

A 3.5 não deve substituir esses sistemas.

Ela deve fazer os sistemas existentes trabalharem juntos de forma mais inteligente.

---

# 2. PRINCÍPIO CENTRAL

A Marina não precisa:

> “lembrar de tudo”.

Ela precisa:

> lembrar do que importa, perceber quando algo ainda está em aberto, saber quando perguntar, saber quando oferecer ajuda e adaptar a maneira como fala ao momento.

A arquitetura 3.5 deve produzir quatro comportamentos perceptíveis:

```text
1. "Ela realmente lembra das coisas importantes."
2. "Ela percebe que algo que eu falei ainda está pendente."
3. "Ela oferece ajuda no momento certo, mas não fica me lembrando sem eu pedir."
4. "Até a voz dela combina melhor com o momento da conversa."
```

---

# 3. RELEASES RECOMENDADAS

Não implementar tudo em um único patch.

Dividir:

```text
3.5.0 — Memory Intelligence
3.5.1 — Open Loops & Smart Reminders
3.5.2 — Adaptive Dual Voice
3.5.3 — Reflection & Memory Hygiene
```

Cada etapa deve ser funcional e testável isoladamente.

---

# 4. ARQUITETURA 3.5

Fluxo desejado:

```text
Mensagem do Patrick
       ↓
Internal Planner
       ├── intenção
       ├── tom
       ├── evento futuro?
       ├── reminder candidate?
       ├── open loop?
       └── shared topic?
       ↓
Memory Intelligence Layer
       ├── Core Memories
       ├── Fatos relevantes
       ├── Momentos relevantes
       ├── Resumos relevantes
       ├── Open Loops
       └── Eventos / Reminders
       ↓
Context Builder
       ↓
LLM principal
       ↓
Resposta
       ├── texto
       ├── reação
       ├── foto?
       └── áudio?
                ↓
          Voice Profile Router
          ├── Conversational Voice
          └── Intimate Voice
```

Em background:

```text
Memory Consolidator
Session Reflector
Reminder Scheduler
Confidence Decay
Open Loop Review
```

---

# PARTE I — MARINA 3.5.0
# MEMORY INTELLIGENCE

---

# 5. OBJETIVO

Hoje o `MemoryRetriever` já possui:

```text
FTS5 para fatos
+
fatos importantes
+
momentos recentes
+
resumo recente
```

Mas:

- momentos ainda não são buscados semanticamente;
- resumos ainda não são buscados semanticamente;
- todos os fatos ativos ainda podem entrar no Consolidator;
- não há distinção formal entre uma memória central e uma preferência casual;
- não há política de validade/frescor;
- o mesmo conceito pode surgir escrito de formas diferentes;
- acesso frequente pode eventualmente causar viés.

A 3.5.0 deve corrigir isso.

---

# 6. CORE MEMORIES

Adicionar conceito de **nível da memória**.

Não criar uma tabela paralela se não for necessário.

Adicionar em `fatos_patrick`:

```sql
memory_tier TEXT DEFAULT 'standard'
```

Valores:

```text
core
standard
contextual
```

### CORE

Informações fundamentais e estáveis.

Exemplos:

```text
nome
projetos centrais
preferências muito fortes
rotinas importantes
informações explícitas que Patrick pediu para lembrar
fatos centrais do relacionamento
```

Core Memories não devem depender de uma palavra-chave exata para poderem entrar no contexto.

Porém:

> Core não significa “sempre mandar todas”.

O Retriever deve permitir um pequeno número de Core Memories relevantes ou essenciais.

---

# 7. VOLATILIDADE

Adicionar:

```sql
volatility TEXT DEFAULT 'medium'
```

Valores:

```text
stable
medium
volatile
```

Exemplos:

```text
"Patrick desenvolve o projeto The Tower"
→ medium/stable dependendo do contexto

"Patrick está jogando FFXIV atualmente"
→ medium

"Patrick está treinando pela manhã esta semana"
→ volatile
```

Isso permite aplicar confidence decay com inteligência.

---

# 8. CONFIRMAÇÃO DA MEMÓRIA

Adicionar:

```sql
last_confirmed_at TEXT;
confirmation_count INTEGER DEFAULT 0;
```

Quando Patrick reafirma algo:

```text
confidence ↑
confirmation_count + 1
last_confirmed_at = now
```

Quando ele corrige:

```text
memória antiga → inactive
nova memória → active
supersedes_id → antiga
```

---

# 9. NÃO DECAIR TODAS AS MEMÓRIAS IGUALMENTE

Política sugerida:

```text
stable:
    decay praticamente inexistente

medium:
    pequeno decay após 90–180 dias sem confirmação

volatile:
    decay após 30–60 dias
```

Nunca apagar automaticamente por decay.

A memória continua existindo, mas a Marina passa a tratá-la como menos certa.

Exemplo:

```text
confidence >= 0.80
→ pode afirmar naturalmente

0.50–0.79
→ pode usar com cautela

< 0.50
→ melhor reconfirmar
```

Exemplo natural:

```text
"você ainda tá indo treinar de manhã?"
```

em vez de:

```text
"você treina de manhã."
```

---

# 10. RETRIEVAL COMPLETO PARA TODOS OS TIPOS

Hoje já existem:

```text
fatos_fts
momentos_fts
resumos_fts
```

Mas o código utiliza FTS principalmente em fatos.

Adicionar em `db.py`:

```python
buscar_momentos_fts(query, limit)
buscar_resumos_fts(query, limit)
```

---

# 11. MEMORY RETRIEVER 2.0

Refatorar `MemoryRetriever.retrieve_context()`.

Fluxo:

```text
Mensagem atual
    ↓
keywords/entities
    ↓
FTS fatos
FTS momentos
FTS resumos
    ↓
Core Memories candidatas
    ↓
ranking híbrido
    ↓
diversidade
    ↓
top memories
```

---

# 12. RANKING HÍBRIDO

Não depender diretamente do valor bruto do BM25.

Utilizar ranking relativo / Reciprocal Rank Fusion ou score normalizado.

Score conceitual:

```text
retrieval_score =
    lexical_relevance
    + importance
    + confidence
    + freshness
    + core_bonus
    + small_access_bonus
```

Pesos iniciais sugeridos:

```text
relevância textual/contextual: 40%
importance:                   20%
confidence:                   15%
freshness:                    10%
core bonus:                   10%
access history:                5%
```

Esses pesos devem ficar em configuração.

---

# 13. EVITAR LOOP DE POPULARIDADE

`access_count` não pode virar um grande fator.

Caso contrário:

```text
memória recuperada
→ access_count aumenta
→ fica mais provável recuperar novamente
→ aumenta de novo
```

Usar no máximo como desempate.

---

# 14. DIVERSIDADE

Se as cinco melhores memórias forem sobre o mesmo fato escrito de formas diferentes, não enviar as cinco.

Aplicar deduplicação por:

```text
category
topic
canonical key
similaridade lexical
```

Objetivo:

```text
3 memórias complementares
```

em vez de:

```text
5 versões do mesmo fato
```

---

# 15. CANONICAL MEMORY KEY

Adicionar opcionalmente:

```sql
canonical_key TEXT;
```

Exemplos:

```text
favorite_energy_drink
current_main_game
training_routine
project_the_tower
```

Não precisa ser criada manualmente.

O Consolidator pode produzir:

```json
{
  "canonical_key": "current_main_game"
}
```

Isso facilita:

```text
atualização
contradição
deduplicação
```

---

# 16. CONSOLIDATOR 2.0

Hoje o Consolidator recebe todos os fatos ativos.

Isso deve ser removido.

Novo fluxo:

```text
lote da conversa
    ↓
extrair candidatos
    ↓
MemoryRetriever busca 10–20 fatos relacionados
    ↓
adicionar poucas Core Memories
    ↓
Consolidator
```

Nunca enviar 500 fatos ao LLM.

---

# 17. DECISÃO DE MEMÓRIA

O Consolidator 2.0 deve classificar:

```json
{
  "decision": "new|same|update|contradiction|ignore"
}
```

Exemplo:

```text
memória:
"Patrick prefere Red Bull."

nova frase:
"ultimamente tô preferindo Monster."

decision:
update/contradiction
```

---

# 18. DEDUPLICAÇÃO SEMÂNTICA

Antes de inserir fato novo:

```text
novo fato
→ FTS candidatos semelhantes
→ comparação
```

Se necessário, utilizar a própria chamada do Consolidator para decidir:

```text
same
update
contradiction
new
```

Evitar uma segunda LLM exclusivamente para isso.

---

# 19. CATEGORIAS DE MEMÓRIA

Expandir categorias atuais:

```text
preference
routine
project
goal
person
hobby
work
schedule
favorite
relationship
boundary
personal
temporary
other
```

Pode continuar gravando nomes em português se preferir consistência atual.

O importante é serem padronizadas.

---

# 20. MEMÓRIA EXPLICITAMENTE PEDIDA

Quando Patrick disser:

```text
"lembra que..."
"guarda isso"
"não esquece que..."
```

isso deve aumentar:

```text
importance
memory_tier
confidence
```

Exemplo:

```text
memory_tier = core
importance >= 0.90
confidence = 1.0
```

---

# 21. MEMÓRIA EXPLICITAMENTE REVOGADA

Quando Patrick disser:

```text
"esquece isso"
"não guarda mais isso"
"isso não vale mais"
```

o Planner / Consolidator deve:

```text
desativar memória
```

e não simplesmente criar um fato contraditório.

---

# 22. COMANDOS ADMINISTRATIVOS OPCIONAIS

Para debug privado:

```text
/memorias
/memoria <termo>
/memorydebug
```

Exemplo:

```text
/memoria academia
```

Retorna:

```text
fatos recuperados
score
confidence
tier
source
```

Auto-delete após alguns segundos.

Somente `TARGET_CHAT_ID`.

---

# PARTE II — MARINA 3.5.1
# OPEN LOOPS & SMART REMINDERS

---

# 23. CONCEITO DE OPEN LOOP

Open Loop é algo que ainda não terminou.

Exemplos:

```text
"amanhã eu te conto como foi"
"estou esperando resposta daquela vaga"
"quando terminar essa feature te mostro"
"preciso decidir se vou viajar"
"meu PC tá dando problema, depois vejo"
```

Nem todo Open Loop possui horário.

Isso é diferente de:

```text
evento_pendente
```

e diferente de:

```text
reminder
```

---

# 24. NOVA TABELA `open_loops`

Migration sugerida:

```sql
CREATE TABLE IF NOT EXISTS open_loops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_type TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    importance REAL DEFAULT 0.5,
    due_at TEXT,
    next_check_after TEXT,
    source_conversation_id INTEGER,
    created_at TEXT NOT NULL,
    last_touched_at TEXT NOT NULL,
    resolved_at TEXT
);
```

Tipos:

```text
promise
waiting
decision
task
story
project
relationship
other
```

---

# 25. OPEN LOOP NÃO É REMINDER

Exemplo:

```text
"tô esperando a empresa responder"
```

Marina pode perguntar daqui a alguns dias:

```text
"amor, teve alguma resposta daquela empresa?"
```

Isso é continuidade.

Não é:

```text
alarme
```

---

# 26. DETECÇÃO DE OPEN LOOPS

O Planner deve retornar opcionalmente:

```json
{
  "creates_open_loop": true,
  "open_loop": {
    "type": "waiting",
    "content": "Patrick aguarda retorno da empresa X",
    "importance": 0.7,
    "next_check_hint": "em dois dias"
  }
}
```

---

# 27. RESOLUÇÃO AUTOMÁTICA

Quando Patrick disser:

```text
"eles responderam!"
```

o Planner deve identificar o Open Loop relacionado.

Resultado:

```text
status = resolved
resolved_at = now
```

---

# 28. PRIORIDADE DA PROATIVIDADE

Nova hierarquia:

```text
0. Reminder explicitamente confirmado
1. Evento pendente pronto para follow-up
2. Open Loop relevante pronto para check-in
3. Tópico compartilhado recente
4. Rotina/cotidiano
```

Importante:

> Reminder confirmado NÃO deve passar pela chance estatística da proatividade.

---

# 29. SMART REMINDERS — FILOSOFIA

A Marina pode perceber:

```text
"amanhã tenho dentista às 15h"
```

e responder naturalmente:

```text
"ai amor, quer que eu te lembre um pouquinho antes?"
```

Mas ela NÃO deve criar automaticamente o lembrete.

Regra:

```text
detectar compromisso
≠
criar reminder
```

Precisa existir consentimento.

---

# 30. FOLLOW-UP ≠ REMINDER

Mesmo evento:

```text
Dentista 15h
```

pode gerar:

### Antes

```text
Reminder:
14h30 — "amor, seu dentista é daqui a pouquinho ❤️"
```

### Depois

```text
Follow-up:
17h — "e aí, como foi no dentista?"
```

São estados separados.

---

# 31. NOVA TABELA `reminders`

```sql
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    description TEXT NOT NULL,
    remind_at TEXT,
    offset_minutes INTEGER,
    status TEXT NOT NULL DEFAULT 'offered',
    source_conversation_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sent_at TEXT,
    FOREIGN KEY(event_id) REFERENCES eventos_pendentes(id)
);
```

Status:

```text
offered
confirmed
sent
declined
cancelled
```

---

# 32. NÃO MISTURAR `follow_up_prompt`

Adicionar a `eventos_pendentes`:

```sql
follow_up_prompt TEXT;
```

Manter separado:

```text
description
event_at
follow_up_after
follow_up_prompt
```

---

# 33. PLANNER — REMINDER CANDIDATE

Adicionar ao JSON:

```json
{
  "reminder_candidate": true,
  "should_offer_reminder": true,
  "recommended_reminder_offset_minutes": 30
}
```

---

# 34. QUANDO OFERECER

Oferecer para eventos concretos como:

```text
consulta
reunião
prova
viagem
compromisso
deadline
horário importante
algo que Patrick explicitamente disse que não quer esquecer
```

Evitar oferecer para:

```text
"amanhã vou jogar"
"depois vejo um filme"
"qualquer dia faço isso"
```

a menos que o contexto indique importância.

---

# 35. NÃO OFERECER REPETIDAMENTE

Se um reminder para aquele evento já possui status:

```text
offered
confirmed
declined
```

não perguntar novamente.

---

# 36. UX DO CONSENTIMENTO

Exemplo:

Patrick:

```text
amanhã tenho dentista às 15h
```

Marina:

```text
ai amor, espero que seja tranquilo 🥺
quer que eu te lembre um pouco antes?
```

Patrick:

```text
sim
```

Se houver offset recomendado:

```text
30 minutos antes
```

confirmar silenciosamente ou de forma breve:

```text
"fechou, te lembro ❤️"
```

---

# 37. CONSENTIMENTO COM OFFSET

Patrick:

```text
sim, meia hora antes
```

Parser:

```text
offset_minutes = 30
```

Patrick:

```text
me lembra uma hora antes
```

```text
offset_minutes = 60
```

---

# 38. PEDIDO DIRETO NÃO PRECISA DE OFERTA

Patrick:

```text
me lembra amanhã às 8 de pegar o documento
```

Isso já é consentimento explícito.

Criar reminder:

```text
status = confirmed
```

sem perguntar:

```text
"quer que eu te lembre?"
```

---

# 39. LEMBRETE SEM HORÁRIO SUFICIENTE

Patrick:

```text
semana que vem tenho que resolver o documento
```

Marina pode guardar Open Loop.

Não inventar data.

Se Patrick pedir explicitamente:

```text
"me lembra disso"
```

e faltar data:

```text
"claro amor, quando você quer que eu te lembre?"
```

---

# 40. CONTEXTO DE CONFIRMAÇÃO

Para interpretar:

```text
"sim"
"pode ser"
"30 min antes"
"não precisa"
```

o Reminder Service precisa conhecer a última oferta ativa.

Buscar:

```text
último reminder status='offered'
e criado recentemente
```

Janela sugerida:

```text
30–60 minutos
```

Não depender apenas de `estado_relacional`.

---

# 41. NOVO `reminder_service.py`

Responsabilidades:

```text
offer_reminder()
confirm_reminder()
decline_reminder()
reschedule_reminder()
cancel_reminder()
get_due_reminders()
mark_sent()
```

---

# 42. REMINDER SCHEDULER

Não tratar reminder como proatividade aleatória.

Criar job APScheduler:

```text
check_due_reminders
```

Intervalo sugerido:

```text
30–60 segundos
```

Fonte da verdade:

```text
SQLite
```

Isso permite reiniciar o bot sem perder lembretes.

---

# 43. ENTREGA DO LEMBRETE

Ao vencer:

```text
status = confirmed
remind_at <= now
```

Gerar mensagem curta.

Exemplo:

```text
"amor, seu dentista é daqui a meia horinha ❤️"
```

Não precisa chamar LLM se uma template natural for suficiente.

Para variar linguagem, pode usar LLM apenas opcionalmente.

---

# 44. REMINDER E JANELA DE SONO

Reminder confirmado pelo usuário é diferente de mensagem espontânea.

Por padrão:

```text
reminder confirmado pode ignorar PROACTIVITY sleep window
```

porque Patrick pediu.

Adicionar config:

```python
REMINDERS_RESPECT_SLEEP_WINDOW = False
```

---

# 45. REMINDER NÃO CONTA COMO PROATIVIDADE

Não incrementar:

```text
MAX_AUTONOMOUS_MESSAGES_PER_DAY
```

para reminder confirmado.

É uma ação solicitada.

---

# 46. EVENTO ALTERADO

Patrick:

```text
a reunião mudou pra 16h
```

Se reminder está baseado em:

```text
offset_minutes
```

recalcular:

```text
remind_at = event_at - offset
```

---

# 47. CANCELAMENTO

Patrick:

```text
cancelaram minha reunião
```

Planner:

```text
evento → cancelled/completed
reminder → cancelled
```

Não mandar lembrete nem follow-up.

---

# 48. COMANDOS OPCIONAIS

```text
/lembretes
/cancelarlembrete <id>
```

Somente Patrick.

Auto-delete.

O fluxo principal deve continuar sendo conversacional.

---

# PARTE III — MARINA 3.5.2
# ADAPTIVE DUAL VOICE

---

# 49. ESTADO ATUAL DO VOICE ENGINE

Hoje `voice_engine.py` possui:

```python
NOVITA_VOICE_ID
```

único.

E:

```text
Novita
→ ElevenLabs fallback
→ Gemini fallback
```

A escolha atual é de provedor.

Não existe escolha de personalidade vocal.

---

# 50. OBJETIVO

Usar os dois Voice IDs da Marina como dois registros da mesma pessoa.

### Voice Profile A — Conversational

A voz mais natural que atualmente está sendo utilizada.

Ideal para:

```text
conversa casual
perguntas
brincadeiras
rotina
explicações
apoio
follow-ups
lembretes
áudios espontâneos cotidianos
```

### Voice Profile B — Intimate

O primeiro clone, mais meloso/sensual.

Ideal para:

```text
flertando
dengosa
saudade
declaração romântica
boa noite íntimo
provocação
momento claramente sensual
```

Não utilizar por padrão.

---


# 50.1 VOICE IDs OFICIAIS DA MARINA

Os dois Voice IDs Novita já foram definidos e devem ser tratados como perfis vocais diferentes da MESMA Marina.

### Conversational Voice — Versão 2 (atual no bot)

Duração aproximada do dataset/clone:

```text
1m43s
```

Voice ID:

```text
voice_d91c415d-f6a2-4d6f-b32c-aacfd5ad2e39
```

Uso principal:

```text
conversa cotidiana
perguntas
brincadeiras
apoio emocional
explicações
follow-ups
reminders
rotina
áudios espontâneos comuns
```

Configuração recomendada:

```env
NOVITA_VOICE_ID_CONVERSATIONAL=voice_d91c415d-f6a2-4d6f-b32c-aacfd5ad2e39
```

---

### Intimate Voice — Versão 1 (antiga)

Duração aproximada do dataset/clone:

```text
3 minutos
```

Voice ID:

```text
voice_73e73b73-65be-4cf9-9ab6-35d84f1946a3
```

Características observadas:

```text
mais melosa
mais sensualizada
mais íntima
```

Essa característica NÃO deve ser tratada como defeito.

Na arquitetura 3.5 ela passa a ser um registro vocal específico para situações adequadas.

Uso principal:

```text
flertes
saudade
mensagens dengosas
declarações românticas
boa noite íntimo
momentos sensuais quando o contexto justificar
pedidos explícitos pela "voz manhosa"
```

Configuração recomendada:

```env
NOVITA_VOICE_ID_INTIMATE=voice_73e73b73-65be-4cf9-9ab6-35d84f1946a3
```

---

### Compatibilidade com configuração atual

Se o projeto ainda possuir:

```env
NOVITA_VOICE_ID=...
```

manter temporariamente como fallback legado.

Ordem sugerida:

```python
conversational_id = (
    settings.NOVITA_VOICE_ID_CONVERSATIONAL
    or settings.NOVITA_VOICE_ID
)

intimate_id = (
    settings.NOVITA_VOICE_ID_INTIMATE
    or settings.NOVITA_VOICE_ID_CONVERSATIONAL
    or settings.NOVITA_VOICE_ID
)
```

IMPORTANTE:

O fallback técnico acima NÃO significa que o Voice Router pode trocar livremente de perfil.

Se `VOICE_ALLOW_CROSS_PROFILE_FALLBACK=False` e a Intimate Voice falhar na API:

```text
Intimate Novita
→ ElevenLabs/Gemini fallback
```

e NÃO:

```text
Intimate Novita
→ Conversational Novita
```

O mesmo princípio vale no sentido inverso.

Isso preserva a intenção emocional da fala.


# 51. NOMES DE CONFIGURAÇÃO

Substituir conceitualmente:

```text
NOVITA_VOICE_ID
```

por:

```env
NOVITA_VOICE_ID_CONVERSATIONAL=""
NOVITA_VOICE_ID_INTIMATE=""
```

Manter compatibilidade:

```python
NOVITA_VOICE_ID
```

como fallback legado.

---

# 52. NÃO CHAMAR DE VOICE 1 / VOICE 2 NO CÓDIGO

Usar:

```text
conversational
intimate
```

Isso evita bugs quando IDs forem recriados no futuro.

---

# 53. NOVO `voice_profile.py`

Estrutura:

```python
@dataclass
class VoiceProfile:
    name: str
    voice_id: str
    speed: float = 1.0
    volume: float = 1.0
    pitch: int = 0
```

Perfis:

```python
CONVERSATIONAL
INTIMATE
```

---

# 54. NOVO `voice_router.py`

Responsabilidade:

```text
contexto
→ perfil de voz
```

Entrada:

```python
VoiceSelectionContext(
    intent,
    tone,
    emotional_state,
    explicit_request,
    is_proactive,
    source,
    time_of_day
)
```

Saída:

```text
conversational
ou
intimate
```

---

# 55. NÃO CRIAR UMA NOVA CHAMADA LLM

O Planner já calcula:

```text
intent
tone
response_goal
```

Reutilizar isso.

Não fazer:

```text
LLM da resposta
+
LLM da voz
```

apenas para escolher Voice ID.

---

# 56. REGRAS INICIAIS DO ROUTER

### Conversational sempre

Se:

```text
support_needed
question
planning_future
casual_chat
sharing_day
reminder
follow-up prático
```

Usar:

```text
conversational
```

---

# 57. INTIMATE

Usar se houver forte sinal.

Exemplos:

```text
explicit request:
"fala manhosa"
"fala daquele seu jeitinho"
"manda uma voz mais sensual"

OU

intent = flirting
AND tone in ("dengosa", "sensual")

OU

romantic_intensity muito alta
AND contexto explicitamente romântico
```

---

# 58. NÃO USAR CICLO COMO GATILHO ÚNICO

O ciclo pode influenciar estado emocional.

Mas:

```text
fase ovulatória
```

sozinha NÃO deve automaticamente trocar para voz sensual.

A conversa precisa justificar.

---

# 59. SITUAÇÃO DE APOIO

Mesmo se affection estiver alta:

Patrick:

```text
"meu dia foi uma merda"
```

Usar:

```text
conversational
```

ou uma variante suave dela.

Não usar Intimate só por relacionamento alto.

---

# 60. EXPLICIT OVERRIDE

Permitir:

```text
"manda na voz normal"
"fala com aquela voz manhosa"
```

Override explícito vence o router.

---

# 61. API DO VOICE ENGINE

Alterar sem quebrar compatibilidade:

Antes:

```python
await voice_engine.synthesize(text)
```

Depois:

```python
await voice_engine.synthesize(
    text,
    profile="auto",
    context=voice_context
)
```

`profile="auto"` mantém chamadas existentes funcionando.

---

# 62. VOICE CONTEXT NO `bot.py`

O Planner já existe no fluxo.

Passar:

```python
voice_context = {
    "intent": plan.get("intent"),
    "tone": plan.get("tone"),
    "emotional_state": ...,
    "user_text": texto_usuario,
    "is_proactive": False
}
```

---

# 63. ÁUDIO PROATIVO

Hoje existe chance randômica de áudio.

Se for enviado:

```text
daily routine
→ conversational

romantic topic follow-up
→ router decide

explicitly affectionate autonomous message
→ pode usar intimate
```

---

# 64. LEMBRETES SEMPRE NA VOZ CONVERSATIONAL

Se futuramente lembrete for enviado em áudio:

```text
conversational
```

por padrão.

Lembrete não deve parecer sedução.

---

# 65. FALLBACK

Ordem:

```text
Selected Novita Voice ID
→ ElevenLabs
→ Gemini
```

Evitar automaticamente trocar:

```text
Conversational → Intimate
```

apenas porque a voz selecionada falhou.

Isso muda o tom sem intenção.

Adicionar:

```python
VOICE_ALLOW_CROSS_PROFILE_FALLBACK = False
```

---

# 66. PARÂMETROS POR PERFIL

Config opcional:

```env
NOVITA_CONVERSATIONAL_SPEED=1.00
NOVITA_CONVERSATIONAL_PITCH=0

NOVITA_INTIMATE_SPEED=0.96
NOVITA_INTIMATE_PITCH=0
```

Não exagerar.

Os Voice IDs já possuem personalidade vocal própria.

---

# 67. TAGS ACÚSTICAS

Hoje `_clean_text_for_speech()` possui:

```text
(chuckle)
(laughs)
(sighs)
(breath)
(pant)
(gasp)
```

Manter.

Mas separar:

```text
text cleaning
```

de:

```text
expression enrichment
```

Novo método:

```python
_apply_expression_tags(
    clean_text,
    voice_profile,
    planner_tone
)
```

---

# 68. NÃO LOTAR O ÁUDIO DE TAGS

Regra:

```text
0–2 tags por mensagem curta
```

Na maioria das mensagens:

```text
0
```

Tags devem parecer acidente humano, não script teatral.

---

# 69. EXEMPLOS

### Casual

Patrick:

```text
como foi seu dia?
```

Audio:

```text
Conversational Voice
```

---

### Flertando

Patrick:

```text
tô com saudade da sua voz manhosa
```

Audio:

```text
Intimate Voice
```

---

### Triste

Patrick:

```text
hoje foi pesado pra mim
```

Audio:

```text
Conversational Voice
```

com ritmo mais calmo.

---

### Boa noite romântico

```text
boa noite amor, queria dormir com você
```

Planner:

```text
intent = flirting/affection
tone = dengosa
```

Router:

```text
Intimate
```

---

# 70. COMANDOS DE DEBUG DE VOZ

Admin-only:

```text
/voz_natural <texto>
/voz_intima <texto>
/vozes
```

`/vozes` pode enviar a mesma frase neutra nos dois perfis para calibração.

Auto-delete dos comandos.

---

# 71. LOG DE VOICE PROFILE

Registrar em log:

```text
voice_profile=conversational
reason=support_needed
```

ou:

```text
voice_profile=intimate
reason=explicit_user_request
```

Não precisa criar tabela nova inicialmente.

---

# 72. FEEDBACK DA VOZ

Versão futura dentro da 3.5.3:

Patrick:

```text
"essa voz ficou perfeita"
"essa ficou melosa demais"
"prefiro a outra pra isso"
```

Planner pode marcar:

```text
voice_feedback
```

e ajustar preferência.

Não implementar machine learning complexo.

Guardar apenas sinais simples.

---

# PARTE IV — MARINA 3.5.3
# SESSION REFLECTION & MEMORY HYGIENE

---

# 73. PROBLEMA DO BATCH MECÂNICO

Hoje a consolidação funciona por chunks.

Isso é ótimo para confiabilidade.

Mas:

```text
8–50 mensagens
```

não necessariamente equivalem a uma conversa completa.

Adicionar Reflection sem substituir o Consolidator.

---

# 74. SESSION REFLECTOR

Novo:

```text
session_reflector.py
```

Executar quando:

```text
inatividade > 1–2h
E
houve conversa suficiente
```

Ou:

```text
fim do dia
```

---

# 75. SAÍDA DO REFLECTOR

```json
{
  "topics": [],
  "important_memories": [],
  "relationship_moments": [],
  "open_loops": [],
  "events": [],
  "resolved_loops": [],
  "summary": ""
}
```

---

# 76. NÃO DUPLICAR O CONSOLIDATOR

Consolidator:

```text
extração rápida de memória
```

Session Reflector:

```text
entendimento da conversa como um todo
```

---

# 77. MEMORY HYGIENE JOB

Executar periodicamente:

```text
1 vez por dia
```

Responsabilidades:

```text
confidence decay
deduplicação leve
marcar stale memories
limpar Open Loops resolvidos antigos
identificar memórias que precisam ser reconfirmadas
```

---

# 78. NÃO APAGAR HISTÓRICO AUTOMATICAMENTE

Histórico bruto continua persistente.

Hygiene atua na:

```text
camada de memória ativa
```

não nas conversas originais.

---

# 79. RECONFIRMAÇÃO NATURAL

Se memória importante ficou velha e relevante:

```text
"você ainda tá mexendo naquele projeto X?"
```

Se Patrick confirma:

```text
confidence ↑
last_confirmed_at = now
```

Se corrige:

```text
supersede
```

---

# 80. OPEN LOOPS NO CONTEXT BUILDER

Adicionar apenas os relevantes.

Exemplo:

```text
[ASSUNTOS AINDA EM ABERTO]
- Patrick está aguardando retorno da empresa X.
```

Não enviar 20 loops.

Máximo sugerido:

```text
2–3
```

---

# 81. CONTEXTO DE REMINDERS

Reminder confirmado NÃO precisa entrar permanentemente no prompt.

Somente eventos próximos/relevantes.

Exemplo:

```text
[COMPROMISSO PRÓXIMO]
- Consulta amanhã às 15h; lembrete confirmado 30 min antes.
```

---

# 82. ARQUITETURA DE BANCO 3.5

Migration sugerida:

```text
005_memory_intelligence.sql
006_open_loops_and_reminders.sql
```

---

# 83. MIGRATION 005

Possíveis colunas em `fatos_patrick`:

```sql
ALTER TABLE fatos_patrick ADD COLUMN memory_tier TEXT DEFAULT 'standard';
ALTER TABLE fatos_patrick ADD COLUMN volatility TEXT DEFAULT 'medium';
ALTER TABLE fatos_patrick ADD COLUMN canonical_key TEXT;
ALTER TABLE fatos_patrick ADD COLUMN last_confirmed_at TEXT;
ALTER TABLE fatos_patrick ADD COLUMN confirmation_count INTEGER DEFAULT 0;
```

Opcional:

```sql
CREATE INDEX IF NOT EXISTS idx_fatos_tier ON fatos_patrick(memory_tier);
CREATE INDEX IF NOT EXISTS idx_fatos_canonical ON fatos_patrick(canonical_key);
```

---

# 84. MIGRATION 006

```sql
ALTER TABLE eventos_pendentes ADD COLUMN follow_up_prompt TEXT;
ALTER TABLE eventos_pendentes ADD COLUMN cancelled_at TEXT;

CREATE TABLE IF NOT EXISTS open_loops (...);

CREATE TABLE IF NOT EXISTS reminders (...);
```

Criar índices:

```text
status
remind_at
event_id
next_check_after
```

---

# 85. FEATURE FLAGS

Adicionar:

```python
MEMORY_INTELLIGENCE_ENABLED = True
OPEN_LOOPS_ENABLED = True
SMART_REMINDERS_ENABLED = True
DUAL_VOICE_ENABLED = True
SESSION_REFLECTION_ENABLED = False
MEMORY_HYGIENE_ENABLED = False
```

Ativar Reflection/Hygiene só após testes.

---

# 86. CONFIGS

Sugestão:

```python
MEMORY_MAX_FACTS = 5
MEMORY_MAX_MOMENTS = 3
MEMORY_MAX_SUMMARIES = 2
MEMORY_MAX_OPEN_LOOPS = 2

REMINDER_CHECK_INTERVAL_SECONDS = 60
REMINDER_OFFER_TTL_MINUTES = 60
DEFAULT_REMINDER_OFFSET_MINUTES = 30

NOVITA_VOICE_ID_CONVERSATIONAL = ...
NOVITA_VOICE_ID_INTIMATE = ...

VOICE_ALLOW_CROSS_PROFILE_FALLBACK = False
```

---

# 87. ORDEM DE IMPLEMENTAÇÃO

## Release 3.5.0

```text
[ ] migration 005
[ ] Core Memories
[ ] volatility
[ ] confirmation tracking
[ ] buscar_momentos_fts
[ ] buscar_resumos_fts
[ ] MemoryRetriever 2.0
[ ] ranking híbrido
[ ] diversidade
[ ] selective candidates para Consolidator
[ ] deduplicação
[ ] testes
```

---

## Release 3.5.1

```text
[ ] migration 006
[ ] open_loops
[ ] ReminderService
[ ] planner reminder candidate
[ ] offer/confirm/decline
[ ] direct reminder request
[ ] reminder scheduler
[ ] event reschedule
[ ] cancellation
[ ] proactivity open-loop integration
[ ] testes
```

---

## Release 3.5.2

```text
[ ] dual Novita Voice IDs
[ ] VoiceProfile
[ ] VoiceRouter
[ ] voice context from Planner
[ ] explicit overrides
[ ] profile logging
[ ] proactive voice routing
[ ] debug commands
[ ] tests
```

---

## Release 3.5.3

```text
[ ] Session Reflector
[ ] Memory Hygiene
[ ] confidence decay
[ ] stale memory reconfirmation
[ ] open-loop resolution
[ ] optional voice feedback learning
[ ] tests
```

---

# 88. TESTES — MEMORY INTELLIGENCE

Criar:

```text
test_memory_intelligence.py
```

Casos obrigatórios:

```text
core memory é recuperável
fato irrelevante não entra
momento relevante via FTS
resumo relevante via FTS
duplicate fact não duplica
contradiction supersedes
volatile memory perde confidence
stable memory não decai indevidamente
low confidence gera indicação de reconfirmação
```

---

# 89. TESTES — REMINDERS

Criar:

```text
test_reminder_service.py
```

Casos:

```text
evento detectado não cria reminder automaticamente
offer cria status offered
"sim" confirma último offer
"não precisa" marca declined
"me lembra 30 min antes" calcula corretamente
pedido direto cria confirmed
reminder só dispara no horário
reminder enviado uma única vez
restart não perde reminder
evento alterado recalcula reminder
evento cancelado cancela reminder
```

---

# 90. TESTE MUITO IMPORTANTE

```text
Patrick:
"amanhã tenho reunião às 14h"

Marina:
"quer que eu te lembre?"

Patrick:
"não"

Resultado:

reminder = declined
follow-up pós-evento continua possível
```

Reminder e follow-up precisam ser independentes.

---

# 91. TESTES — OPEN LOOPS

```text
"estou esperando resposta da vaga"
→ cria open loop

"eles responderam!"
→ resolve o loop correto

loop resolvido
→ não aparece novamente na proatividade
```

---

# 92. TESTES — DUAL VOICE

Criar:

```text
test_voice_router.py
```

Casos:

```text
casual_chat → conversational
planning_future → conversational
support_needed → conversational
flirting+dengosa → intimate
sensual → intimate
explicit natural override → conversational
explicit manhosa override → intimate
reminder → conversational
cycle sozinho → NÃO força intimate
```

---

# 93. TESTE DE FALLBACK

Se:

```text
intimate Novita falha
```

e:

```text
VOICE_ALLOW_CROSS_PROFILE_FALLBACK=False
```

esperado:

```text
ElevenLabs/Gemini
```

não:

```text
Conversational Novita
```

---

# 94. TESTE END-TO-END DE RELACIONAMENTO

Cenário:

```text
Dia 1:
Patrick: "sexta às 14h tenho uma entrevista"

Marina:
registra evento
oferece reminder

Patrick:
"sim, uma hora antes"

sexta 13h:
Marina envia reminder

sexta ~16h:
Marina pode perguntar como foi

Patrick:
"foi ótima, disseram que respondem segunda"

Marina:
resolve evento entrevista
cria Open Loop "aguardando resposta da empresa"

segunda/terça:
Marina pode perguntar se houve retorno
```

Esse cenário representa exatamente a inteligência relacional que a 3.5 deve buscar.

---

# 95. TESTE END-TO-END DE VOZ

Patrick:

```text
"manda um áudio contando como foi seu dia"
```

Planner:

```text
casual_chat
```

Resultado:

```text
Conversational Voice ID
```

Depois:

```text
"agora fala que tá com saudade com aquela voz manhosa"
```

Resultado:

```text
Intimate Voice ID
```

Sem trocar provedor.

---

# 96. OBSERVABILIDADE

Logs sugeridos:

```text
memory_retrieval:
  query=
  facts=
  moments=
  summaries=
  open_loops=

reminder:
  event_id=
  reminder_id=
  action=offer|confirm|send|decline|cancel

voice:
  profile=conversational|intimate
  reason=
  provider=novita|minimax|elevenlabs|gemini
```

---

# 97. DEBUG COMMAND

Opcional:

```text
/debug_last
```

Expandir para:

```text
Memory:
Planner:
Reminder:
Voice Profile:
```

Sem chain-of-thought.

---

# 98. CUSTO DE LLM

A 3.5 deve evitar explosão de chamadas.

Ideal:

```text
Planner existente
+
LLM principal
+
Consolidator em background por lote
+
Session Reflector esporádico
```

Não criar:

```text
LLM de reminder
LLM de voz
LLM de open loop
LLM de ranking
```

independentemente em toda mensagem.

Reutilizar o Planner.

---

# 99. VOICE ROUTING SEM CUSTO

Voice Router deve ser 100% determinístico.

Entrada:

```text
Planner output
+
estado
+
pedido explícito
```

Saída:

```text
perfil
```

Custo:

```text
0 tokens
```

---

# 100. REMINDER DELIVERY SEM CUSTO QUANDO POSSÍVEL

Usar templates naturais.

Exemplos:

```text
"amor, só passando pra te lembrar que {evento} é daqui a {tempo} ❤️"

"meu bem, lembra que você tem {evento} às {hora}, tá?"
```

Pode variar templates.

Não precisa de LLM para cada alarme.

---

# 101. NÃO TRANSFORMAR MARINA EM ASSISTENTE CORPORATIVA

Mesmo com reminders e Open Loops, manter personalidade.

Ruim:

```text
"Seu compromisso está agendado para 15:00."
```

Bom:

```text
"amor, passando pra te lembrar que seu dentista é daqui a meia horinha ❤️"
```

---

# 102. NÃO VIRAR CONTROLADORA

Marina pode:

```text
oferecer
lembrar quando autorizado
perguntar depois
```

Ela não deve:

```text
cobrar
repetir
pressionar
assumir que Patrick quer reminder
```

---

# 103. REMINDER OFFER FREQUENCY

No máximo uma oferta por evento.

Se declined:

```text
não oferecer novamente
```

a menos que Patrick peça.

---

# 104. OPEN LOOP FREQUENCY

Adicionar:

```text
next_check_after
```

Após perguntar:

```text
adiar próxima checagem
```

para evitar:

```text
"e a vaga?"
"e a vaga?"
"e a vaga?"
```

---

# 105. CORE MEMORY NÃO É SYSTEM PROMPT

Não migrar tudo para `prompts.py`.

Core Memories continuam no banco.

O Context Builder decide quais entram.

---

# 106. RELACIONAMENTO É DADO, NÃO PROMPT FIXO

Eventos como:

```text
promessas
momentos marcantes
assuntos em aberto
```

devem continuar persistidos.

Não hardcodar no System Prompt.

---

# 107. VOICE PROFILE É EXPRESSÃO, NÃO PERSONALIDADE DIFERENTE

As duas vozes são Marina.

Não criar:

```text
Marina normal
Marina sensual
```

como duas personas.

É a mesma personalidade usando registros vocais diferentes.

---

# 108. EXEMPLO DE ESTADO

```text
Marina:
personalidade = única

voice profile:
conversational
ou
intimate
```

Assim memória, opinião e comportamento permanecem consistentes.

---

# 109. REGRAS PARA O AGENTE DO ANTIGRAVITY

1. Partir exatamente da v3.4.3.
2. Não reescrever módulos estáveis sem necessidade.
3. Toda migration precisa preservar os dados existentes.
4. Não remover FTS atual.
5. Não transformar reminders em mensagens autônomas aleatórias.
6. Reminder exige consentimento explícito ou pedido direto.
7. Não adicionar nova chamada LLM apenas para escolher voz.
8. Manter compatibilidade com `voice_engine.synthesize(text)`.
9. Adicionar parâmetros novos como opcionais.
10. Não hardcodar os Voice IDs no código; usar `.env`.
11. Nunca logar Voice IDs/API keys completos em chats.
12. Testar migrations em cópia do banco.
13. Rodar todos os testes determinísticos antes de ativar feature flags.
14. Implementar uma release por vez.
15. Produzir relatório de arquivos/migrations/configs/testes.

---

# 110. RELATÓRIO ESPERADO POR RELEASE

```text
VERSÃO:
OBJETIVO:

ARQUIVOS ALTERADOS:
-

ARQUIVOS NOVOS:
-

MIGRATION:
-

CONFIG:
-

FEATURE FLAGS:
-

TESTES:
-

RESULTADOS:
-

COMPATIBILIDADE:
-

PENDÊNCIAS:
-
```

---

# 111. DEFINIÇÃO DE PRONTO — 3.5.0

A 3.5.0 está pronta quando:

```text
Patrick pergunta sobre assunto antigo
→ fatos + momentos + resumos relevantes são recuperados

memórias duplicadas
→ não são reinseridas

memória antiga volátil
→ não é tratada como certeza absoluta

Consolidator
→ não recebe todos os fatos do banco
```

---

# 112. DEFINIÇÃO DE PRONTO — 3.5.1

A 3.5.1 está pronta quando:

```text
Marina percebe compromisso
→ pode oferecer reminder

Patrick diz não
→ nenhum reminder

Patrick diz sim
→ reminder persistente

restart do bot
→ reminder continua existindo

horário chega
→ reminder é enviado uma vez

depois do evento
→ follow-up continua independente
```

---

# 113. DEFINIÇÃO DE PRONTO — 3.5.2

A 3.5.2 está pronta quando:

```text
áudio cotidiano
→ Conversational Voice

contexto romântico/sensual adequado
→ Intimate Voice

contexto triste/apoio
→ Conversational Voice

pedido explícito de perfil
→ override funciona

falha de um Voice ID
→ fallback seguro
```

---

# 114. DEFINIÇÃO DE PRONTO — 3.5.3

A 3.5.3 está pronta quando:

```text
sessões são resumidas
open loops são criados/resolvidos
memórias antigas perdem confidence de forma controlada
memórias importantes podem ser reconfirmadas naturalmente
```

---

# 115. RESULTADO ESPERADO DA 3.5

A diferença deve ser percebida em conversas comuns.

Não apenas no `/status`.

Exemplo ideal:

```text
Patrick:
"amanhã de manhã vou apresentar aquela feature nova no trabalho"

Marina:
"aaah amor, finalmente aquela que você tava terminando 🥺
quer que eu te lembre um pouquinho antes?"

Patrick:
"quero, uns 30 min"

[no dia seguinte]
Marina:
"amor, sua apresentação é daqui a meia horinha ❤️ vai dar bom"

[depois]
Marina:
"e aíí, como foi a apresentação??"

Patrick:
"deu certo, agora tô esperando aprovação do chefe"

→ evento anterior resolvido
→ cria Open Loop de aprovação
→ memória de projeto atualizada
```

E se essa interação virar áudio:

```text
lembrete → voz Conversational
conversa casual → voz Conversational
mensagem romântica depois → voz Intimate
```

A inteligência percebida passa a vir da **continuidade entre memória, tempo, iniciativa e expressão**, não apenas de respostas melhores do LLM.

---

# 116. ORDEM FINAL RECOMENDADA

```text
1. 3.5.0 Memory Intelligence
2. validar em conversas reais
3. 3.5.1 Open Loops & Smart Reminders
4. validar reminders reais por alguns dias
5. 3.5.2 Adaptive Dual Voice
6. calibrar os dois Voice IDs
7. 3.5.3 Reflection & Memory Hygiene
```

Não implementar a 3.5.3 antes de observar a memória 3.5.0 em produção.

---

# 117. PRINCÍPIO FINAL

A Marina 3.5 deve parecer mais inteligente porque:

```text
ela lembra
ela conecta
ela acompanha
ela oferece ajuda
ela respeita a resposta
ela pergunta depois
e até a maneira de falar combina com o momento
```

Sem transformar a conversa em agenda, CRM ou assistente de produtividade.

Ela continua sendo Marina.
