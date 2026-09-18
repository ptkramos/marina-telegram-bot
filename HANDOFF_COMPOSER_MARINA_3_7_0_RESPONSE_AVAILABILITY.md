# HANDOFF DE IMPLEMENTAÇÃO — MARINA v3.7.0
## Response Availability & Human Latency
### Release crítica de entrada em produção / soak real

**Executor primário:** Composer  
**Validador independente previsto:** Codex  
**Base:** Marina v3.6 Living World concluída e validada  
**Princípio:** a v3.6 ensinou Marina a existir em um mundo coerente; a v3.7.0 faz esse mundo influenciar **quando** e **com quanta atenção** ela responde.

---

# 0. IMPORTÂNCIA DESTA RELEASE

A v3.7.0 é uma release de infraestrutura conversacional crítica.

Ela ficará entre:

```text
mensagem recebida de Patrick
        ↓
decisão de disponibilidade
        ↓
Planner / LLM / mídia
        ↓
Telegram send
```

Portanto, bugs aqui podem causar:

```text
- mensagem perdida;
- resposta duplicada;
- resposta horas atrasada;
- fila presa;
- scheduler starvation;
- resposta fora de contexto;
- Marina mentindo sobre o que estava fazendo;
- reprocessamento após restart;
- comportamento artificialmente indisponível.
```

**Não otimizar naturalidade sacrificando confiabilidade.**

Prioridade de engenharia:

```text
1. NEVER LOSE A USER MESSAGE
2. NEVER DUPLICATE A NORMAL REPLY
3. NEVER INVENT ACTIVITY TO JUSTIFY LATENCY
4. ROLLBACK MUST BE IMMEDIATE
5. ONLY THEN: HUMAN-LIKE TIMING
```

---

# 1. GATE DE ENTRADA

A v3.6 está aprovada.

Baseline independente:

```text
317 testes
0 failures
0 errors
0 skipped

30d / 90d / 365d simulations
→ PASS

canon drift
→ 0

event looping
→ 0

P0 / P1 / P2
→ 0 / 0 / 0
```

**Não reabrir nem redesenhar v3.6 nesta implementação.**

A v3.7.0 deve consumir as autoridades existentes.

---

# 2. ESCOPO EXATO DA v3.7.0

Implementar:

```text
Response Availability
Human Reply Latency
Pending Conversational Batching
Urgency override
Brief-reply mode
Persistent deferred replies
Restart recovery
Rollback seguro
Telemetry de timing
Production flag audit/preparation
Soak-test tooling
```

Não implementar ainda:

```text
3.7.1 User Routine Signals
3.7.2 Associative Life Recall
3.7.3 Causal Everyday Reasoning
3.7.4 Events / Curiosity
```

Não misturar essas etapas.

---

# 3. PRINCÍPIOS NÃO NEGOCIÁVEIS

```text
BUSY DOES NOT MEAN UNREACHABLE.

AVAILABLE DOES NOT MEAN INSTANTLY RESPONSIVE.

PHONE ACCESS != ATTENTION AVAILABLE.

DELAY != EXCUSE.

NO WORLDSTATE EVIDENCE
!=
PERMISSION TO CLAIM AN ACTIVITY.
```

O objetivo não é deixar Marina lenta.

O objetivo é evitar:

```text
bot always-online / always-instant
```

sem criar:

```text
girlfriend mysteriously offline for hours
```

---

# 4. ARQUITETURA — REUTILIZAR AUTORIDADES EXISTENTES

Antes de editar código, mapear os nomes reais no repositório de:

```text
Telegram update handler
existing short debounce/buffer
Planner
response_rhythm / ResponseStylePolicy
WorldState
Calendar/Events
Academic schedule
Routine Engine
Relationship context
scheduler / autonomous tick
message persistence
Telegram send wrapper
Open Loops / Reminders
feature flag/config system
```

### Regra

**Não criar segundo scheduler, segundo Planner, segundo WorldState ou segundo message store.**

A nova camada deve ser algo conceitualmente equivalente a:

```text
ResponseAvailabilityService
PendingResponseRepository
ResponseAvailabilityPolicy
```

Os nomes podem ser adaptados ao padrão real do projeto.

---

# 5. PIPELINE ALVO

Pipeline recomendado:

```text
Telegram update
        ↓
persist incoming message using existing path
        ↓
existing short debounce / burst aggregation
        ↓
admin/system-command bypass?
        ↓
ResponseAvailabilityService.evaluate(...)
        ↓
┌──────────────────────────────────────────────┐
│ REPLY_NOW                                    │
│ → existing Planner/LLM/send pipeline         │
│                                              │
│ REPLY_BRIEFLY                                │
│ → current pipeline with BRIEF budget hint    │
│ → optional follow-up candidate only if needed│
│                                              │
│ DEFER                                        │
│ → persist pending batch                      │
│ → DO NOT generate full response yet          │
│ → existing scheduler wakes it later          │
└──────────────────────────────────────────────┘
```

Do not use:

```python
await asyncio.sleep(minutes)
```

inside Telegram handlers.

Long latency must be **persisted + scheduled**, not held in memory.

---

# 6. EXISTING DEBOUNCE VS NEW PENDING BATCH

Preserve the current short debounce.

They solve different problems:

```text
SHORT DEBOUNCE
→ Patrick sends 2–4 messages within seconds
→ existing burst handling

PENDING BATCH
→ Marina cannot properly respond for minutes
→ messages arriving during that period merge coherently
```

Recommended order:

```text
raw messages
→ existing short debounce
→ conversational input unit
→ availability decision
→ pending batch if DEFER
```

Do not replace the existing debounce with the v3.7.0 feature.

---

# 7. RESPONSE AVAILABILITY DECISION

Create a structured result equivalent to:

```text
ResponseAvailabilityDecision
```

Recommended fields:

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

activity_type:
  HOME_RELAXING
  CLASS
  GYM
  CASTING
  WORK
  COMMUTE
  SOCIAL
  SLEEPING
  UNKNOWN
  OTHER

activity_source:
  CONFIRMED_COMMITMENT
  WORLD_STATE
  ROUTINE_PROBABILITY
  UNKNOWN

reason_code:
  small enum only

earliest_reply_at
target_window_start
target_window_end
selected_target_at

context_snapshot_id
world_state_freshness
decision_seed
decision_version
```

No chain-of-thought.

Do not let the LLM choose the delay.

---

# 8. CONTEXT CERTAINTY MATTERS

Not every WorldState fact has equal authority.

Use something equivalent to:

```text
confirmed Calendar/Event
> fresh explicit WorldState
> strong derived context
> probabilistic routine
> unknown
```

Example:

```text
confirmed PUC class 09:00–11:00
→ strong signal

RoutineEngine thinks gym is plausible
→ soft signal only
```

### Critical rule

A probabilistic routine may influence timing softly.

It **must not** justify a factual sentence like:

```text
"tava treinando"
```

unless the current state genuinely supports that as known/current.

---

# 9. STALE / UNKNOWN CONTEXT

If activity/location context is stale or unavailable:

```text
DO NOT manufacture busyness.
```

Fallback:

```text
UNKNOWN
→ mild/generic human latency at most
→ never long DEFER based on invented activity
```

Failing to resolve WorldState must not leave Patrick waiting indefinitely.

---

# 10. ACTIVITY PROFILES — INITIAL CALIBRATION

These are **soft starting values**, not canon.

Centralize them in config/settings.

Do not scatter magic numbers.

## HOME_RELAXING

```text
phone_access = HIGH
attention = HIGH
interruptibility = HIGH

typical:
REPLY_NOW

soft latency:
seconds → few minutes
```

## COMMUTE / UBER / WAITING

```text
phone_access = HIGH
attention = HIGH
interruptibility = HIGH

typical:
REPLY_NOW / REPLY_BRIEFLY
```

## GYM

```text
phone_access = HIGH
attention = LOW/MEDIUM
interruptibility = MEDIUM

valid:
REPLY_NOW
REPLY_BRIEFLY
DEFER
```

Do not map:

```text
gym = unavailable for entire workout
```

She can reply between sets.

Recommended normal soft delay:

```text
~1–15 min
guardrail: usually <= 25 min
```

unless another confirmed context explains otherwise.

## CLASS

```text
phone_access = HIGH
attention = LOW
interruptibility = LOW/MEDIUM
```

Casual:

```text
often DEFER
```

Simple/short:

```text
REPLY_BRIEFLY possible
```

Urgent:

```text
REPLY_BRIEFLY / REPLY_NOW
```

Do not automatically wait the entire class.

Recommended normal soft delay:

```text
~2–30 min
guardrail: usually <= 45 min
```

or earlier natural breakpoint if known.

## CASTING / MODELING JOB / PROFESSIONAL ACTIVITY

```text
phone_access = MEDIUM/HIGH
attention = LOW
interruptibility = LOW
```

Delay may be larger, but avoid multi-hour blocks by default.

Recommended guardrail:

```text
usually <= 45–60 min
```

unless sleep/explicit noninterruptible event provides stronger evidence.

## SOCIAL

```text
phone_access = HIGH
attention = MEDIUM
interruptibility = MEDIUM
```

Possible delay:

```text
few minutes → ~20/30 min
```

## SLEEPING

Normally:

```text
DEFER
```

Do not invent a wake-up mechanism.

`CRITICAL` may override only if the project has an explicit, plausible notification/wake policy.

Do not add that policy silently in this release.

---

# 11. GLOBAL LATENCY GUARDRAILS

For the first real-production week, prefer conservative humanization.

Recommended guardrails:

```text
non-sleep NORMAL message:
→ avoid > 45 min by default

HIGH urgency:
→ strongly reduce latency
→ target within a few minutes when technically possible

CRITICAL:
→ prioritize immediate/brief response
→ except explicit sleep policy limitations

UNKNOWN context:
→ no long defer
```

The soak test exists to calibrate later.

Do not start with aggressive delays.

---

# 12. MESSAGE URGENCY — NO EXTRA LLM

Use deterministic heuristics and existing intent metadata if already available.

Default:

```text
NORMAL
```

Use `LOW` only when clearly low-stakes.

Examples:

```text
LOW
- obvious meme/sticker/light reaction

NORMAL
- ordinary conversation
- normal question

HIGH
- "preciso falar contigo"
- "aconteceu uma coisa séria"
- explicit time-sensitive request

CRITICAL
- explicit emergency / danger / immediate help language
```

### Requirements

- Portuguese must be first-class.
- Conservative classification is better than underestimating urgency.
- Do not add one extra LLM call merely to classify urgency.
- Store only the category in telemetry, not unnecessary message text.

---

# 13. RESPONSE COMPLEXITY

Estimate enough to choose between:

```text
SHORT
NORMAL
LONG
```

Possible signals:

```text
message length
number of questions
multi-topic burst size
explicit "me explica"
existing Planner intent if already available cheaply
```

Do not run Planner solely to decide delay.

The purpose is:

```text
WHEN_TO_REPLY
+
HOW_MUCH_TO_REPLY
```

remain separate.

---

# 14. REPLY_NOW

Use the existing response pipeline.

Do not fork Planner or Response Rhythm.

Availability may pass only compact hints such as:

```text
availability_mode=normal
response_budget_hint=normal
```

No extra persona system.

---

# 15. REPLY_BRIEFLY

Purpose:

```text
Marina can acknowledge/reply while partially occupied
without writing a long answer.
```

Integrate with existing `response_rhythm.py` / ResponseStylePolicy.

Pass a hint such as:

```text
response_budget_hint=brief_due_to_availability
```

Do not force the phrase:

```text
"tô ocupada"
```

The response may simply be shorter.

### Truthfulness

If Marina mentions why she is brief:

```text
activity explanation
```

must be supported by current WorldState.

---

# 16. BRIEF REPLY + POSSIBLE FOLLOW-UP

Do not automatically create a second message for every brief reply.

Only create a deferred continuation candidate when:

```text
message complexity = NORMAL/LONG
AND
the current brief answer intentionally leaves material unresolved
AND
conversation state still makes a follow-up useful
```

Recommended state:

```text
FOLLOWUP_CANDIDATE
```

Before sending later:

```text
- has Patrick sent something new?
- was the topic superseded?
- is follow-up still relevant?
```

If not relevant:

```text
SUPERSEDED
```

Do not send stale:

```text
"agora te conto..."
```

40 minutes after the conversation changed topic.

---

# 17. DEFER — CRITICAL IMPLEMENTATION RULE

When decision is `DEFER`:

```text
DO NOT generate the full LLM response immediately.
```

Persist the pending batch and generate at send time.

Why:

```text
WorldState may change
new messages may arrive
urgency may increase
topic may change
the old response may become stale
```

At due time:

```text
reload latest relevant context
re-evaluate batch
run Planner
run LLM
send
```

---

# 18. PENDING BATCH PERSISTENCE

Use SQLite / existing DB.

Do not keep the authoritative pending queue only in RAM.

Recommended conceptual table:

```text
response_pending_batches
```

Fields:

```text
id
conversation_key
active_key
status
created_at
updated_at

decision
reason_code
activity_type
activity_source
urgency_max
response_complexity

eligible_after
target_window_start
target_window_end
selected_target_at
expires_at

context_snapshot_id
decision_seed
decision_version

retry_count
last_error
lease_owner
lease_until

followup_candidate
created_by_version
```

Recommended statuses:

```text
PENDING
READY
SENDING
SENT
SUPERSEDED
CANCELLED
UNKNOWN_DELIVERY
```

Adapt to existing migration conventions.

---

# 19. DO NOT DUPLICATE USER TEXT

If incoming messages are already stored in the conversation table, do not copy full raw text into another queue table.

Use references.

Recommended:

```text
response_pending_batch_items

batch_id
conversation_message_id
telegram_message_id
received_at
ordinal
```

Add uniqueness on source message identity where practical.

This reduces:
- privacy duplication;
- storage;
- divergence.

---

# 20. ONE ACTIVE DEFERRED BATCH PER CONVERSATION

Prefer one active pending conversational batch for Patrick/Marina at a time.

When another message arrives:

```text
existing active batch?
→ append
→ increment decision_version
→ recalculate max urgency
→ recalculate timing
```

Do not create a queue of independent Marina replies for each Telegram message.

---

# 21. NEW MESSAGE DURING DEFER

Example:

```text
09:20 meme
→ DEFER to 09:35

09:25 "amor preciso falar contigo"
```

Expected:

```text
same pending conversational batch
urgency LOW → HIGH
availability recalculated
target brought forward
```

Do not leave the urgent message behind the meme delay.

---

# 22. BATCHING BEHAVIOR

When batch becomes ready:

```text
messages are context
not a checklist
```

The existing conversational-naturalness principle remains:

```text
OPTIMIZE FOR THE NEXT TURN, NOT COMPLETENESS.
```

Do not generate:

```text
Resposta 1:
Resposta 2:
Resposta 3:
```

Do not force acknowledgement of every pending item.

---

# 23. SCHEDULER INTEGRATION

**Reuse the existing scheduler/autonomous tick.**

Do not create a permanent second daemon if current infrastructure can service due replies.

Needed behavior:

```text
periodically:
  find due pending batches
  atomically claim one
  process
  send
  mark SENT
```

If the existing tick resolution is too coarse for minute-level latency, adjust the shared scheduling mechanism carefully.

Do not implement handler sleeps.

---

# 24. ATOMIC CLAIM / DUPLICATE PROTECTION

Two scheduler wakes must not send the same reply.

Use transactional claim semantics equivalent to:

```text
READY
→ atomic UPDATE / claim
→ SENDING
```

Only one worker may claim.

Use:

```text
lease_owner
lease_until
```

or the project's equivalent.

Test concurrent claims.

---

# 25. TELEGRAM SEND CONFIRMATION

A reply is only `SENT` after Telegram returns a valid `message_id`.

Same philosophy as the privacy sharing ledger.

Flow:

```text
claim batch
→ generate reply
→ Telegram send
→ valid message_id
→ persist outgoing message
→ mark batch SENT
```

Send failure:

```text
do not mark SENT
```

Apply bounded retry/backoff.

---

# 26. HARD-CRASH DELIVERY WINDOW

Telegram Bot API does not provide a true application idempotency key for `sendMessage`.

Therefore:

```text
network send succeeds
+
process dies before DB commit
```

can create an unavoidable delivery-uncertainty window.

Do not pretend strict exactly-once is mathematically guaranteed.

Handle explicitly:

```text
SENDING after restart
→ do NOT blindly resend immediately
→ move to UNKNOWN_DELIVERY after grace/recovery rule
→ log prominently
```

Prefer an observable rare uncertainty over guaranteed duplicates.

Document this transport limitation for Codex.

---

# 27. RESTART RECOVERY

At startup:

```text
load active pending batches
```

For each:

```text
PENDING with future target
→ re-register / leave for scheduler

PENDING/READY already overdue
→ make eligible safely

SENDING with expired lease
→ recovery policy
→ UNKNOWN_DELIVERY or safe retry only when delivery is known not to have occurred
```

Never discard because `expires_at` passed.

Here:

```text
expires_at
```

means:

```text
must be resolved/re-evaluated
```

not:

```text
drop Patrick's message
```

---

# 28. STARTUP DRAIN

After a long downtime:

```text
do not emit a burst of many stale replies.
```

Because there should be one active conversational batch, consolidate/re-evaluate before sending.

If old batch is no longer relevant:

```text
SUPERSEDED
```

If still relevant:

```text
generate one current response
```

---

# 29. ROLLBACK

Required flags:

```env
RESPONSE_AVAILABILITY_ENABLED=false
HUMAN_REPLY_LATENCY_ENABLED=false
PENDING_CONVERSATION_BATCHING_ENABLED=false
```

Optional:

```env
RESPONSE_AVAILABILITY_DEBUG=false
REAL_USAGE_TELEMETRY_ENABLED=false
```

All new flags default **OFF**.

### Flag semantics

Recommended:

```text
RESPONSE_AVAILABILITY_ENABLED=false
→ legacy/current reactive behavior

RESPONSE_AVAILABILITY_ENABLED=true
HUMAN_REPLY_LATENCY_ENABLED=false
→ SHADOW MODE
→ compute decisions + telemetry
→ do NOT actually delay

LATENCY=true
BATCHING=true
→ enforce v3.7.0 behavior
```

This provides a safe validation path.

---

# 30. ROLLBACK WITH PENDING REPLIES

If flags are disabled while replies are pending:

```text
PENDING / READY
→ re-evaluate
→ make immediately processable on next safe cycle

SUPERSEDED
→ remain terminal

SENT
→ never resend
```

No migration reversal required.

Rollback must be configuration-only.

---

# 31. FAIL-OPEN POLICY

If ResponseAvailability crashes or cannot resolve:

```text
fail open
→ use previous reactive response behavior
```

Never fail closed into silence.

Telemetry may record:

```text
AVAILABILITY_POLICY_ERROR
```

but Patrick still receives a reply.

---

# 32. ADMIN / SYSTEM COMMAND BYPASS

Do not human-delay operational commands.

Bypass availability for:

```text
admin/debug commands
health checks
maintenance callbacks
internal scheduler commands
```

Use actual project command routing.

Do not accidentally defer `/worlddebug` for 25 minutes because Marina is "in class".

---

# 33. CONVERSATIONAL MEDIA REQUESTS

Ordinary user requests for:

```text
photo
voice
normal text
```

may pass through availability.

If DEFER:

```text
do not pre-generate expensive/stale media
```

Generate when the reply actually becomes ready.

For camera:

```text
reload current Camera World Context at send time
```

Do not reuse a stale visual snapshot merely because the request arrived earlier.

---

# 34. PROACTIVITY IS OUTSIDE THIS QUEUE

v3.7.0 primarily governs **replies to Patrick**.

Existing 3.6.5 proactive-message scheduling remains authoritative for Marina-initiated messages.

Do not route all proactive messages through pending reply batching unless current architecture already unifies them safely.

No second proactivity engine.

---

# 35. NO FAKE "SEEN"

Telegram bot receipt is not the same as human read receipt.

Do not expose claims such as:

```text
"vi tua mensagem há meia hora"
```

unless the system has a real basis for that wording.

Internal concepts like:

```text
noticed_probability
```

may influence timing, but they are not externally observable truth.

---

# 36. ACTIVITY EXPLANATION POLICY

Latency itself does not require explanation.

Do not make Marina say:

```text
"desculpa a demora"
"tava ocupada"
```

every time.

Only mention activity if:

```text
- it is relevant to the reply;
- the WorldState supports it;
- the phrase is conversationally natural.
```

---

# 37. INTEGRATION WITH RESPONSE RHYTHM

Do not duplicate `response_rhythm.py`.

Availability provides hints.

Response Rhythm remains authority for conversational size/shape.

Examples:

```text
REPLY_BRIEFLY
→ target short / 1 bubble

REPLY_NOW
→ current normal policy

DEFER
→ no generation until due
```

Preserve:

```text
1 bubble as default in casual chat
no mandatory question
no completeness obsession
```

---

# 38. CONFIG / CALIBRATION

All activity weights/windows belong in one configuration area.

Possible structure:

```text
RESPONSE_AVAILABILITY_PROFILES = {
  HOME_RELAXING: ...
  GYM: ...
  CLASS: ...
  WORK: ...
  CASTING: ...
  COMMUTE: ...
  SOCIAL: ...
  SLEEPING: ...
  UNKNOWN: ...
}
```

Config should expose:

```text
base decision weights
soft delay range
max guardrail
brief likelihood
interruptibility
```

No dozens of hardcoded literals across services.

---

# 39. HUMAN VARIATION AND REPRODUCIBILITY

Decision should contain a stored:

```text
decision_seed
selected_target_at
```

Once chosen, restart must not roll a new random delay.

New incoming message may:

```text
increment decision_version
→ legitimately recalculate
```

Testing can use fixed seeds.

Production gets variation from message/batch identity and time context.

Avoid repeated patterns:

```text
gym always 8 minutes
class always 23 minutes
```

---

# 40. TIME HANDLING

Use timezone-aware datetimes.

Project context:

```text
America/Sao_Paulo
```

Do not mix naive and aware datetime objects.

Persist timestamps using the project's established convention.

Test:

```text
restart
midnight crossing
day change
long defer
```

---

# 41. TELEMETRY

Create compact technical telemetry, conceptually:

```text
response_availability_events
```

Recommended fields:

```text
id
batch_id
timestamp

decision
reason_code
activity_type
activity_source
context_freshness

urgency
response_complexity

target_latency_seconds
actual_latency_seconds

pending_message_count
batch_merged
urgent_override

cache/provider/error flags if relevant

decision_version
release_version
```

Do not store full raw conversation text again.

---

# 42. TELEMETRY IS NOT MEMORY

Telemetry must not be retrieved as Marina's autobiographical memory.

Keep it out of:
- Memory Intelligence retrieval;
- World Bible;
- Relationship history;
- Story Engine.

It is operational data only.

---

# 43. DEBUG / OBSERVABILITY

Prefer extending existing admin/debug infrastructure.

Useful view:

```text
availability feature flags
active pending batch count
next due batch
last decisions
REPLY_NOW / BRIEF / DEFER counts
current activity profile
scheduler health
oldest pending age
UNKNOWN_DELIVERY count
```

Do not expose:
- chain-of-thought;
- secret values;
- full private message text unnecessarily.

---

# 44. SOAK REPORT TOOLING

Implement a small report script, e.g.:

```text
scripts/report_response_availability_soak.py
```

It should produce:

```text
period
total user message batches
median latency
P90 latency
P95 latency

REPLY_NOW %
REPLY_BRIEFLY %
DEFER %

batch merge count
urgent override count
retry count
UNKNOWN_DELIVERY count
scheduler errors
availability policy errors

latency by activity
latency by urgency
```

No quality verdict based solely on lower latency.

---

# 45. MANUAL FEEDBACK FILE

Prepare:

```text
data/feedback/real_usage_3_7_0.md
```

Suggested template:

```text
[DATA/HORA]
Situação:
WorldState esperado:
Eu mandei:
Comportamento:
Esperado:
Observação:
```

Patrick only needs to record:
- weird cases;
- very good cases;
- frustrating cases;
- obviously artificial cases.

---

# 46. MIGRATION

If new tables are needed, create the next migration following the actual repository numbering after migration 015.

Do not assume `016` without checking.

Migration requirements:

```text
idempotent under migration framework
no destructive schema change
safe with feature flags OFF
existing production DB upgrades cleanly
fresh DB reaches same final schema
```

No pending message state may depend on reversible destructive migration.

---

# 47. UNIT TESTS — DECISION POLICY

Add deterministic tests for at least:

```text
home + normal
→ high availability

commute + normal
→ high availability

gym + normal
→ mixed/medium

class + casual
→ lower availability

class + HIGH urgency
→ delay strongly reduced / brief allowed

sleeping + normal
→ DEFER

UNKNOWN context
→ no long defer
```

Tests should assert ranges/constraints, not one magic exact number unless seed-fixed.

---

# 48. UNIT TESTS — CONTEXT TRUTH

Required:

```text
probabilistic gym routine
→ may influence timing softly
→ cannot justify factual "tava treinando" metadata

confirmed class
→ may drive CLASS profile

stale WorldState
→ cannot drive long defer

UNKNOWN
→ fallback safe
```

---

# 49. UNIT TESTS — PENDING BATCH

Required:

```text
3 incoming messages while deferred
→ one active batch
→ 3 item refs

same Telegram message replayed
→ not duplicated

new LOW message
→ merge

new HIGH message
→ urgency upgrades
→ target moved earlier

SENT batch
→ cannot send again

SUPERSEDED
→ never sends
```

---

# 50. UNIT TESTS — CONCURRENCY

Critical.

Simulate:

```text
two scheduler workers
→ same READY batch
→ only one claims

two new messages arriving concurrently
→ no two active batches

scheduler claim races with new urgent message
→ no lost message
→ no duplicate reply
→ deterministic terminal state
```

---

# 51. UNIT TESTS — RESTART

Required:

```text
PENDING future
→ survives restart

READY overdue
→ recovered

SENT
→ never resent

expired lease
→ recovery path

SENDING after crash
→ does not blindly duplicate
→ UNKNOWN_DELIVERY/recovery rule
```

---

# 52. UNIT TESTS — SEND FAILURE

Required:

```text
Telegram exception
→ batch not SENT

invalid/no message_id
→ batch not SENT

temporary failure
→ bounded retry

successful retry
→ SENT once

permanent failure
→ observable error state
→ no infinite loop
```

---

# 53. UNIT TESTS — ROLLBACK

Required:

```text
all flags OFF
→ legacy behavior

availability ON + latency OFF
→ shadow mode
→ no actual defer

flags turned OFF with PENDING batch
→ message not lost

restart after rollback
→ no orphan batch
```

---

# 54. UNIT TESTS — BRIEF FOLLOW-UP

Required:

```text
brief simple answer
→ no mandatory follow-up

brief complex answer
→ followup candidate possible

Patrick sends new message before followup
→ candidate superseded/merged

followup still relevant
→ can send later

topic changed
→ no stale continuation
```

---

# 55. MEDIA REGRESSION

Test:

```text
deferred photo request
→ photo generated at execution time
→ Camera uses fresh WorldState

deferred voice request
→ TTS generated only when ready

admin/debug command
→ no latency
```

---

# 56. FULL REGRESSION EXPECTATION

Composer should prepare tests, but **must not self-certify this release**.

Small compile/unit checks during implementation are acceptable.

The independent Codex validation should later execute:

```text
full existing suite
v3.6.7 regression
camera regression
privacy regression
calendar/academic regression
relationship/proactivity regression
response rhythm regression
new v3.7.0 suite
```

Baseline before v3.7.0:

```text
317/317
```

Any regression must be explained.

---

# 57. SYNTHETIC SIMULATIONS

Prepare a script, conceptually:

```text
scripts/run_response_availability_simulation.py
```

Scenarios:

```text
24h
72h
7d
```

Test:
- ordinary mixed messages;
- class;
- gym;
- commute;
- social;
- sleep;
- urgent upgrades;
- message bursts;
- restart;
- scheduler duplicate wake;
- temporary send failure.

Measure:

```text
lost messages
duplicate replies
pending starvation
max pending age
latency distribution
decision distribution
urgent bypass
batch merges
```

---

# 58. PRE-PRODUCTION SUCCESS CRITERIA

Before real soak:

```text
lost messages = 0
normal duplicate replies = 0
stuck pending = 0
scheduler starvation = 0
restart loss = 0

urgent override works
activity changes timing
UNKNOWN does not over-defer
batching works
rollback works
telemetry works
```

---

# 59. P0 / P1 / P2

## P0 — DO NOT ACTIVATE

```text
message loss
duplicate reply under normal execution
pending batch permanently stuck
DB corruption
migration corruption
critical urgency trapped
scheduler deadlock
privacy/secrets regression
reply sent to wrong conversation
```

## P1 — DO NOT START REAL SOAK

```text
Marina nearly always DEFER
Marina never DEFER
class means effectively offline
gym means effectively offline
stale WorldState causes fake busyness
frequent false activity explanations
batch replies robotic
deferred replies frequently out of context
restart causes timing reset/storm
send retry loop
production rollback unsafe
```

## P2 — TUNING

```text
soft-delay distributions
weights
brief frequency
debug ergonomics
minor telemetry/reporting issues
```

---

# 60. PRODUCTION FLAGS AUDIT — PREPARE, DO NOT ACTIVATE YET

Because Codex will independently validate this critical release:

**Composer must not silently turn the production flags ON as the final implementation step.**

Composer must create a proposed matrix:

```text
docs/production_flags_3_7_0.md
```

Scan the actual code/config and list every relevant v3.6/v3.7 flag.

Columns:

```text
Flag
Current default
Current runtime value if knowable
Category
Validated release/stage
Dependency
Secret/provider requirement
Proposed production state
Rollback action
Notes
```

Categories include:

```text
World Bible / Core
Social Graph / Places
Story Engine
Knowledge / Privacy
Real World Context
Academic
Calendar / Events
Relationship / Proactivity
Camera
Conversational Naturalness
Voice Prosody
Real-World Lookup
Holiday provider
World Hygiene
Response Availability
Human Latency
Pending Batching
Telemetry
```

Never include secret values.

---

# 61. PRODUCTION ACTIVATION OWNERSHIP

Recommended sequence:

```text
Composer
→ implements
→ leaves new enforcement flags OFF
→ prepares flag matrix
→ prepares tests/scripts/artifacts

Codex
→ audits code independently
→ runs full validation
→ verifies flag matrix
→ gate decision

ONLY AFTER CODEX GATE:
→ activate approved flags
→ smoke check
→ start real 7-day soak
```

This separation is deliberate.

Implementation is not self-approval.

---

# 62. SHADOW MODE BEFORE ENFORCEMENT

Codex may choose to validate in:

```text
RESPONSE_AVAILABILITY_ENABLED=true
HUMAN_REPLY_LATENCY_ENABLED=false
REAL_USAGE_TELEMETRY_ENABLED=true
```

Expected:

```text
policy calculates what it WOULD do
but user receives legacy immediate reply
```

Use to compare decisions without risking message delay.

After confidence:

```text
HUMAN_REPLY_LATENCY_ENABLED=true
PENDING_CONVERSATION_BATCHING_ENABLED=true
```

---

# 63. POST-VALIDATION ACTIVATION

After Codex gate:

```text
D0
- apply approved .env/config states
- restart Marina
- verify DB schema
- verify scheduler
- verify providers
- verify pending queue empty/healthy
- send normal smoke message
- send burst smoke
- verify admin/debug bypass
- verify rollback flags immediately available
```

Then:

```text
PRODUCTION_SOAK_PHASE
```

---

# 64. REAL SOAK — 7 DAYS MINIMUM

Patrick uses Marina normally.

Do not artificially test every turn.

Expected contexts:

```text
morning
workday
Marina class
gym
commute
evening
weekend
single messages
bursts
occasional urgent message
photo/voice request
```

Do not start 3.7.1 during this period.

---

# 65. SOAK QUALITY QUESTIONS

After 7 days:

```text
1. Marina still replies instantly too often?
2. Marina delays too much?
3. DEFER happens at plausible moments?
4. gym feels reachable?
5. class feels busy without offline behavior?
6. urgent messages break through?
7. pending batches sound natural?
8. any fake excuses?
9. delays repetitive?
10. brief replies feel natural?
11. any reply arrived after topic changed?
12. any message felt lost?
```

---

# 66. FINAL SOAK REPORT

Prepare tooling for:

```text
RELATORIO_SOAK_MARINA_3_7_0.md
```

Include:

```text
period
total message batches

median latency
P90
P95
max non-sleep latency

REPLY_NOW %
REPLY_BRIEFLY %
DEFER %

latency by activity
latency by urgency

batch count
average batch size
urgent override count

retries
send failures
scheduler failures
UNKNOWN_DELIVERY

manual feedback highlights
P0 / P1 / P2
recommended tuning
final gate
```

---

# 67. VALIDATION ARTIFACTS FOR CODEX

Follow project naming convention.

Suggested if sequential Stage numbering continues:

```text
Stage 15
```

but verify actual project convention.

Prepare:

```text
scripts/run_external_stage15_validation.py
scripts/run_response_availability_simulation.py

data/response_availability_validation.v370.json
data/response_availability_simulation.v370.json

VALIDACAO_ETAPA_15.md
```

These files are **inputs for independent validation**, not proof by themselves.

---

# 68. VALIDATION JSON MINIMUM

Suggested fields:

```text
release: 3.7.0
stage

commit / working tree
python version

tests_run
failures
errors
skipped

availability_tests
batch_tests
restart_tests
rollback_tests
race_tests
media_tests

simulation_24h
simulation_72h
simulation_7d

lost_messages
duplicate_replies
stuck_pending
urgent_override_failures
unknown_delivery_count

flag_matrix_path
status
```

Do not mark passed merely because script completed.

---

# 69. DOCUMENTATION

Composer should update/create:

```text
docs/production_flags_3_7_0.md
VALIDACAO_ETAPA_15.md
```

And document:

```text
feature semantics
rollback
pending recovery
known transport uncertainty
telemetry
how to run validation
how to run simulations
how to generate soak report
```

---

# 70. DO NOT CHANGE PERSONA TO FIT THE FEATURE

No new system prompt like:

```text
"You are often busy and should delay replies."
```

Timing is system behavior.

Persona should not become:
- distant;
- less affectionate;
- evasive;
- apologetic;
- performatively busy.

---

# 71. DO NOT USE DELAY AS ENGAGEMENT MANIPULATION

Never deliberately delay because:

```text
"scarcity increases attachment"
"make Patrick miss Marina"
"increase engagement"
```

Latency must come from plausible availability and human variation only.

---

# 72. DO NOT MAKE RELATIONSHIP TENSION CONTROL LATENCY PUNITIVELY

Relationship context may affect tone.

It must not turn into:

```text
Marina is annoyed
→ silently ignore Patrick for 3 hours
```

No punishment-by-latency system in v3.7.0.

---

# 73. KEEP COST LOW

Target:

```text
same existing LLM response call
+
deterministic availability layer
```

No extra LLM on every message.

`DEFER` should often reduce wasted LLM calls because response is generated only when actually due.

---

# 74. MEMORY / PRIVACY

Pending queue and telemetry are operational state.

They are not:
- autobiographical memory;
- shared history;
- relationship facts.

Do not index them into Memory Intelligence.

Knowledge/Privacy rules still apply when the delayed response is eventually generated.

---

# 75. WORLDSTATE DOES NOT CHANGE BECAUSE OF DELAY

Human latency consumes WorldState.

It does not mutate Marina's activity merely to fit a delay.

Wrong:

```text
need delay
→ set Marina gym
```

Correct:

```text
WorldState says class
→ availability reacts to class
```

---

# 76. CURRENT CONTEXT MUST BE RELOADED AT SEND TIME

For deferred batches:

```text
arrival context
```

is useful for provenance/debug.

But final response should use:

```text
fresh send-time context
```

when available.

This prevents:

```text
"tô em aula"
```

after class already ended.

---

# 77. ARRIVAL CONTEXT VS SEND CONTEXT

Store compact arrival metadata:

```text
arrival_activity
arrival_source
arrival_context_snapshot_id
```

At send time resolve again:

```text
send_activity
send_context_snapshot_id
```

Telemetry can compare them.

Do not store full prompt snapshots unnecessarily.

---

# 78. OUT-OF-CONTEXT GUARD

Before sending a deferred response, check:

```text
- batch still active?
- user sent new messages?
- another reply already satisfied topic?
- conversation topic moved?
- deferred response still useful?
```

If not:

```text
SUPERSEDED
```

If new messages exist:

```text
merge and regenerate
```

Never send a stale pre-written reply.

---

# 79. DEAD-LETTER / OBSERVABILITY

If a batch cannot be processed after bounded retries:

```text
do not loop forever
```

Move to explicit error state / dead-letter equivalent.

Admin/debug must surface it.

Fail-open strategy can then allow a normal response path on next interaction.

No silent loss.

---

# 80. CODE REVIEW QUESTIONS COMPOSER MUST SELF-CHECK

Before handing to Codex:

```text
Did I create any second scheduler?
Did I create any second Planner?
Do I store duplicate raw user text?
Can two workers send same batch?
Can restart reroll delay?
Can stale context hold a reply too long?
Can a LOW meme block later HIGH message?
Can pending survive restart?
Can flags OFF restore old behavior?
Can send failure mark SENT incorrectly?
Can delay invent "tava treinando"?
Can media be generated stale?
Can telemetry leak message content?
Can admin commands be deferred?
Can batching force completeness?
```

If any answer is uncertain, resolve it before handoff.

---

# 81. COMPOSER HANDOFF TO CODEX

At completion, Composer must return a compact implementation report containing:

```text
files changed
migration added
new services/classes
new DB tables/columns
scheduler integration point
Telegram handler integration point
flags added
default values
tests added
scripts added
docs added
known limitations
commands for validation
```

Do NOT conclude:

```text
"release approved"
```

Composer may say:

```text
"implementation complete; awaiting independent Codex validation"
```

---

# 82. CODEX VALIDATION TARGET

Codex should be able to independently determine:

```text
NO LOST MESSAGES
NO NORMAL DUPLICATES
NO STUCK QUEUE
NO FAKE ACTIVITY
NO LONG UNKNOWN-CONTEXT DELAYS
URGENT OVERRIDE WORKS
BATCH MERGE WORKS
RESTART WORKS
ROLLBACK WORKS
MEDIA FRESHNESS WORKS
317-TEST BASELINE DOES NOT REGRESS
```

---

# 83. DEFINITION OF DONE — IMPLEMENTATION

Composer implementation is complete when:

```text
ResponseAvailabilityPolicy exists
+
activity certainty handled
+
urgency handled
+
brief mode integrated with Response Rhythm
+
persistent DEFER exists
+
pending batching exists
+
scheduler reuses existing infrastructure
+
atomic claim exists
+
Telegram send confirmation exists
+
restart recovery exists
+
rollback flags exist and default OFF
+
shadow mode works
+
telemetry exists
+
production flag matrix prepared
+
Stage 15 validation tooling prepared
+
no 3.7.1+ scope creep
```

---

# 84. DEFINITION OF DONE — RELEASE

The release itself is **not** done when Composer finishes coding.

Release done requires:

```text
Composer implementation
        ↓
Codex independent validation
        ↓
P0 = 0
P1 = 0
        ↓
approved production flag activation
        ↓
real 7-day soak
        ↓
soak report
        ↓
P0/P1 = 0
```

Only then:

```text
v3.7.0 COMPLETE
```

and only then consider:

```text
v3.7.1 — Personal Pattern Recognition / User Routine Signals
```

---

# 85. FINAL PRINCIPLE

> **Marina should not reply late because a timer says so. She should reply when a person in her current situation plausibly would — without ever sacrificing reliability.**

Engineering translation:

```text
WorldState provides reality.
Availability interprets attention.
Scheduler handles time.
Planner handles intent.
Response Rhythm handles conversational size.
Telegram send confirms delivery.
Telemetry observes.
Feature flags guarantee rollback.
```

No layer should steal another layer's authority.
