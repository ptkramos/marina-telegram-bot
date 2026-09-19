# REVISÃO TÉCNICA INDEPENDENTE — MARINA v3.7.0v3
## Round 3 — Final Sanity / Prompt Authority / Response Availability

**Pacote auditado:** `marin-telegram-bot-3.7.0v3.zip`  
**Método:** inspeção direta do código, call graph, fallbacks, testes adversariais com SQLite temporário e execução dos testes possíveis no ambiente atual  
**Gate:** ❌ **VOLTA PARA O COMPOSER — NÃO INICIAR SOAK AINDA**

---

# 1. RESUMO EXECUTIVO

A v3 está **bem melhor** que a v2. Vários P1 da rodada anterior foram realmente corrigidos.

Mas ainda encontrei problemas reproduzíveis que afetam:

```text
- learned style / evidência do Patrick;
- urgência e Human Latency;
- deferred batch replay;
- cancelamento/supersession;
- wake policy durante sono;
- canon ownership no AutoPatcher;
- proatividade vs WorldState;
- falso verde no auditor.
```

Não encontrei evidência de P0 no caminho principal moderno.

O problema agora está muito mais concentrado: não é mais um monólito legado inteiro. São contratos específicos que ainda precisam ser fechados antes do soak.

---

# 2. CORREÇÕES DA v2 QUE AGORA ESTÃO BOAS

## 2.1 SafeCore pré-clean-start

Reproduzi novamente o ataque usado na v2:

```text
old fact:
"Patrick e Marina moram juntos no apartamento antigo"

old assistant history:
"Marina Seltin e tenho 19 anos"
```

Com:

```text
LIVING_WORLD_ENABLED=false
clean canonical marker ausente
```

Resultado na v3:

```text
stale fact não entrou no prompt
old Seltin history não entrou
style injection vazia
```

✅ **FIXED**

---

## 2.2 `prompts.py`

Agora funciona como shim deprecated:

```text
MARIN_SYSTEM_PROMPT = None
EVENTOS_COTIDIANO = ()
```

✅ **FIXED**

---

## 2.3 `prompt_policy.py`

Confirmado:

```text
CONTROL_EN centralizado
DATA_CHANNEL_POLICY_EN
SAFE_CORE_IDENTITY
neutral daypart
photo/reminder constraints
is_canonical_runtime_ready()
```

✅ **CORRETO**

---

## 2.4 Web / Vision evidence channels

A v3 migrou:

```text
web → format_web_evidence
vision → format_vision_evidence
```

e retirou as antigas instruções comportamentais embutidas nesses blocos.

✅ **FIXED**

---

## 2.5 Visual canon

Confirmado:

```text
Marina Salles
no fixed 19yo / 20yo in visual DNA
"young adult Brazilian woman"
bot visual director reuses visual DNA
```

✅ **FIXED**

---

## 2.6 AutoPatcher não usa mais `prompts.py` como owner

O deprecated shim deixou de ser target principal.

✅ **PARCIALMENTE FIXED**

Há, porém, um problema de canon ownership descrito mais abaixo.

---

## 2.7 Legacy autonomous proactivity

O segundo motor legado foi desativado quando Living World está OFF.

O caminho oficial continua sendo o v3.6 grounded.

✅ **FIXED EM RELAÇÃO À v2**

---

## 2.8 Packaging script

`scripts/build_validation_archive.py` foi testado diretamente.

Resultado:

```text
195 files
verification = PASS
no .env
no DB
no venv
no scratch
no generated private image
```

✅ **IMPLEMENTAÇÃO CORRETA**

Atenção: o ZIP manual enviado pelo usuário ainda contém arquivos privados/locais. Isso é processo de empacotamento, não falha do script. Para o Codex, usar exclusivamente o archive builder.

---

# 3. P1 — STYLE ENGINE AINDA FABRICA "APRENDIZADO DO PATRICK"

Este bug continua existindo, só que de forma mais sutil.

## Reprodução

DB limpo:

```text
patrick_sample_count = 0
style injection = ""
```

Processar apenas:

```text
"oi tudo bem"
"sim tudo certo"
```

Patrick não usou:

```text
kkkk
🥰
💕
❤️
🥺
🙈
trampo
codar
bora
suave
fechou
```

Mesmo assim, após o threshold:

```text
patrick_sample_count = 2
```

a injection passa a declarar:

```text
Risada compartilhada: kkkk
Emojis: 🥰, 💕, ❤️, 🥺, 🙈
Gírias que você pegou dele: trampo, codar, bora, suave, fechou
```

## Causa

`processar_mensagem_patrick()` persiste defaults quando não encontra observações reais.

Depois `get_style_prompt_injection()` apresenta esses defaults como evidência aprendida.

## Correção necessária

Separar definitivamente:

```text
DEFAULT_PTBR_STYLE
```

de:

```text
LEARNED_FROM_PATRICK
```

Cada dimensão aprendida precisa de evidência própria.

Exemplo:

```text
no laugh observed
→ do not store learned laugh

no emoji observed
→ do not store learned emoji

no slang observed
→ do not store learned slang
```

Base style pode continuar existindo fora do banco de evidência.

---

# 4. P1 — WORLDCONTEXT IGNORA O THRESHOLD DO STYLE ENGINE

Há um segundo problema relacionado.

## Reprodução

DB limpo.

Patrick manda apenas:

```text
"oi tudo bem"
```

Resultado:

```text
patrick_sample_count = 1
has_learned_style() = False
```

Mesmo assim o prompt Living World contém:

```text
[ESTILO APRENDIDO]
```

com cadence/style retirado diretamente da tabela.

## Causa

`world_context.py` acessa `db.get_estilo()` diretamente.

Ele não passa pela API evidence-aware do `StyleEngine`.

## Correção

WorldContext deve consumir apenas uma API como:

```text
StyleEngine.get_learned_style_summary()
```

que:

```text
- respeita threshold;
- só inclui dimensões observadas;
- retorna vazio se não existe aprendizado real.
```

Não ler tabela de estilo crua no prompt builder.

---

# 5. P1 — AUDITOR DE PROMPT AUTHORITY CONTINUA COM FALSO VERDE

Executei:

```text
scripts/audit_prompt_authority.py
```

Resultado:

```text
PASS
```

Mas os dois bugs de Style acima continuam ativos.

Logo:

```text
audit PASS != prompt authority realmente verde
```

## Correção

O auditor precisa testar comportamento, não apenas procurar strings.

Obrigatório incluir:

```text
fresh DB
+ 2 bland messages
→ no fake laugh/emojis/slang

fresh DB
+ 1 message
→ no [LEARNED STYLE] in WorldContext

each learned dimension
→ must trace to actual evidence
```

---

# 6. P1 — URGENCY CLASSIFIER SUBESTIMA MENSAGENS CURTAS IMPORTANTES

Este é um problema importante da própria 3.7.0.

## Classificação atual reproduzida

```text
"me ajuda"                → LOW
"acidente"                → LOW
"hospital"                → LOW
"tô mal"                  → LOW
"preciso de ajuda"        → NORMAL
"socorro"                 → CRITICAL
"amor preciso falar contigo" → HIGH
"aconteceu uma coisa séria"  → HIGH
```

O catch-all de mensagens curtas está vencendo casos que deveriam ser tratados conservadoramente.

## Impacto em aula

Reprodução em CLASS:

```text
"me ajuda"
→ LOW
→ DEFER ~20 min

"acidente"
→ LOW
→ DEFER vários minutos

"hospital"
→ LOW
→ DEFER

"tô mal"
→ LOW
→ DEFER
```

Isso viola o contrato:

```text
critical urgency must not get trapped by human latency
```

## Correção

Patterns HIGH/CRITICAL devem ser avaliados ANTES do fallback de mensagem curta.

Adicionar cobertura pt-BR conservadora para, por exemplo:

```text
me ajuda
preciso de ajuda
acidente
hospital
machuquei
me machuquei
passei mal
tô passando mal
estou passando mal
aconteceu um acidente
é urgente
emergência
socorro
```

Ambiguidade emocional como:

```text
"tô mal"
```

é melhor classificar para atenção maior do que LOW.

---

# 7. P1 — SLEEPING CRITICAL OVERRIDE INVENTA WAKE POLICY

Hoje:

```text
activity = SLEEPING
urgency = CRITICAL
```

pode virar resposta praticamente imediata / `REPLY_BRIEFLY`.

Mas o plano oficial dizia:

```text
grave urgency may wake/interrupt sleep
ONLY if an explicit plausible notification/wake policy exists
```

A v3.7.0 não deve criar esse mecanismo silenciosamente.

## Correção

Escolher explicitamente UMA política:

### opção A — recomendada para primeiro soak

```text
CRITICAL_WAKE_POLICY_ENABLED=false
```

default false.

Enquanto false:

```text
sleep remains protected
```

com comportamento documentado.

### opção B

Definir formalmente a política de notificação/acordar e testá-la.

Não deixar implícito.

---

# 8. P1 — DEFERRED BATCH DUPLICA LEARNING DO PATRICK

Fluxo atual:

```text
incoming batch
→ processar_mensagem_patrick()
→ availability decides DEFER
→ persist pending
```

Mais tarde:

```text
pending_response_routine()
→ process_incoming_batch(... availability_bypass=True ...)
→ processar_mensagem_patrick() AGAIN
```

A mesma mensagem é aprendida duas vezes.

## Impacto

Uma única mensagem deferida pode artificialmente aproximar/atingir o threshold de estilo.

## Correção

Learning deve acontecer apenas no intake original.

Exemplo:

```text
if pending_batch_id is not None:
    do not learn Patrick style again
```

Ideal:

```text
idempotent learning keyed by Telegram/conversation message id
```

## Teste

```text
1 deferred message
→ replay
→ sample count increments exactly once
```

---

# 9. P1 — `SUPERSEDED` EXISTE, MAS CANCELAMENTO REAL NÃO ESTÁ IMPLEMENTADO

O repository possui:

```text
supersede()
```

mas o runtime não está usando isso para invalidar ações deferidas que ficaram obsoletas.

## Caso concreto

Patrick:

```text
"manda uma foto"
```

Marina:

```text
DEFER
```

Patrick depois:

```text
"deixa pra lá"
```

O batch consolidado ainda contém:

```text
"manda uma foto"
```

e o detector de photo request pode disparar.

Resultado possível:

```text
Marina envia foto
MESMO DEPOIS DO CANCELAMENTO
```

## Correção

Antes de qualquer side effect deferido:

```text
photo
voice
avatar
reminder/action
```

fazer stale/cancellation check.

No mínimo entender:

```text
deixa pra lá
esquece
não precisa
pode deixar
cancela
não manda mais
```

Quando aplicável:

```text
SUPERSEDED
```

ou suprimir aquela ação dentro do batch.

Teste obrigatório:

```text
photo request
→ DEFER
→ user cancels
→ ZERO image generation
→ ZERO FLUX call
→ no stale photo sent
```

---

# 10. P1 — AUTOPATCHER AINDA ERRA O OWNER DE CANON

O `prompts.py` saiu do caminho, o que foi bom.

Mas conceitos como:

```text
"canon"
"personalidade"
```

ainda podem ser roteados para:

```text
prompt_policy.py
world_context.py
```

Isso é conceitualmente incorreto para canon.

Canon pertence a:

```text
World Bible / canonical repository / canonical seed
```

## Risco

Um `/edit` de canon pode modificar uma VIEW/POLICY em vez da source of truth.

## Correção

Para:

```text
alterar canon
```

ou:

```text
alterar identidade biográfica
```

fazer uma destas duas coisas:

```text
A. route explicitamente para World Bible owner
```

ou, mais seguro agora:

```text
B. refuse automatic patch and require explicit canonical target/migration
```

Não deixar prompt policy virar canon por acidente.

---

# 11. P1 — PROACTIVITY AINDA TEM SLEEP WINDOW RÍGIDA PRÉ-WORLDSTATE

`ProactivityService.check_sleep_window()` ainda usa:

```text
03:30 <= time < 08:00
```

como bloqueio fixo.

O caminho Living World chama `should_trigger()`, portanto essa regra pode vencer WorldState/Calendar.

## Exemplo

WorldState confirmado:

```text
05:00
Marina awake / commute / unusual explicit plan
```

Mesmo assim:

```text
hardcoded clock
→ proactivity blocked
```

Isso viola:

```text
Routine is probabilistic.
Calendar/current state are authoritative.
```

## Correção

No Living World:

```text
sleep/current availability
→ WorldState / Calendar / Routine authority
```

Não hardcoded clock como source of truth.

Teste:

```text
explicit awake state at 05:00
→ not blocked merely by clock
```

---

# 12. P2 — INTERNAL CONTROL INSTRUCTIONS AINDA EM PORTUGUÊS

Ainda existem instruções internas de workflow, especialmente relacionadas a avatar/speech, passadas como app-generated user messages em pt-BR.

Isto não é canon corruption.

Mas para cumprir completamente a política:

```text
control instructions → English
user-facing examples/output → pt-BR
```

devem ser migradas/centralizadas.

---

# 13. P2 — PLANNER / WORLDCONTEXT LABELS INTERNOS

Ainda há labels como:

```text
[PLANNER ...]
Tom:
Objetivo:
[INTENÇÃO ESTRATÉGICA DESTE TURNO]
```

em português.

Funcionam, mas structured internal state deveria ser English/language-neutral.

Baixa prioridade depois dos P1.

---

# 14. P2 — MEMORY CLI EXPORT

`show_stats()` usa idade dinâmica.

Mas `export_dump()` ainda lê:

```text
perfil.get("idade")
```

em vez de derivar por `birth_date`.

Não afeta runtime conversational principal, mas completar a limpeza.

---

# 15. P2 — IMPORT DEPRECATED AINDA EXISTE

`bot.py` ainda importa:

```text
build_autonomous_decision_prompt
```

do shim deprecated, mesmo sem uso runtime real.

Remover.

`healthcheck.py` também ainda referencia/importa `prompts`.

Retirar dependência deprecated se não necessária.

---

# 16. P2 — ACTIVITY MAPPER PODE SUPERCLASSIFICAR PELO LOCAL

Reproduções:

```text
place = puc_rio
activity = "tomando café com Theo no intervalo"
→ CLASS
```

e:

```text
place = marina_apartment
activity = "trabalhando num freela"
→ HOME_RELAXING
```

Pode distorcer Human Latency.

Melhor priorizar atividade explícita/fresh sobre place heuristic.

Provável tuning P2, mas vale corrigir antes do soak para não contaminar telemetria.

---

# 17. TESTES EXECUTADOS NESTA AUDITORIA

## Prompt Authority

Com stub apenas para dependência externa `openai`:

```text
tests.test_prompt_authority_v370
18/18 PASS
```

Importante:

```text
esses 18 testes ainda NÃO cobrem os bugs adversariais desta revisão
```

---

## Response Availability

Testes carregáveis:

```text
18 PASS
```

Dois casos adicionais não rodaram porque o ambiente Linux atual não possui o pacote Telegram usado pelo projeto Windows.

Isso é:

```text
environment limitation
!=
project failure
```

---

## Python compile

```text
top-level project Python
→ PASS
```

---

## Prompt Authority Audit Script

```text
PASS
```

Mas o próprio resultado é insuficiente, porque os bugs de Style reproduzidos escapam do auditor.

---

# 18. FULL SUITE — LIMITAÇÃO DE AMBIENTE

Não consegui executar o `tests/run_isolated.py` completo neste ambiente porque:

```text
repository venv = Windows
current executor = Linux
system environment lacks some project deps
Windows compiled site-packages cannot be reused safely
```

Portanto NÃO vou afirmar:

```text
full suite green
```

Isso precisa ser executado no Windows do projeto depois das correções e novamente pelo Codex.

---

# 19. PACKAGING

O ZIP manual v3 continua contendo coisas que não devem ir para um validador:

```text
.env
.git
venv
scratch
local/private artifacts
```

Não usar este ZIP como handoff final para Codex.

Use:

```text
scripts/build_validation_archive.py
```

O script foi testado e gera pacote limpo.

---

# 20. GATE FINAL DA v3

## P0 encontrados

```text
0
```

## P1 ainda abertos

```text
1. StyleEngine defaults masquerade as learned Patrick evidence
2. WorldContext bypasses style evidence threshold
3. Prompt-authority auditor false-green
4. Urgency classifier underestimates short urgent/distress messages
5. Sleeping CRITICAL override lacks explicit wake policy
6. Deferred replay double-counts Patrick style learning
7. Pending cancellation/supersession is not functionally enforced
8. AutoPatcher canon ownership is wrong
9. Living World proactivity still has hardcoded sleep authority
```

## P2

```text
internal Portuguese control directives
internal Portuguese labels
memory_cli export age
deprecated prompt import
activity mapper overclassification
```

---

# 21. DECISÃO

```text
❌ VOLTA PARA O COMPOSER

❌ NÃO MANDAR PARA CODEX AINDA

❌ NÃO INICIAR SOAK

❌ NÃO ATIVAR 3.7.1
```

Mas a diferença em relação à v2 é importante:

```text
v2
→ prompt/canon legacy architecture still leaking broadly

v3
→ most broad legacy leaks fixed
→ remaining blockers are concentrated, reproducible contracts
```

Depois de corrigir estes P1, a próxima auditoria pode ser focada e curta.

