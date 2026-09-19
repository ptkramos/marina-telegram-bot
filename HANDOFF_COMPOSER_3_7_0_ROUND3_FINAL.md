# HANDOFF CORRETIVO FINAL — MARINA v3.7.0 ROUND 3
## Remaining Pre-Soak Blockers

**Executor:** Composer  
**Depois:** Codex independent validation  
**Gate atual:** ❌ VOLTA PARA O COMPOSER

---

# 0. NÃO REFAZER O QUE JÁ ESTÁ CERTO

Preservar:

```text
SafeCore pre-clean gating
MARIN_SYSTEM_PROMPT = None
EVENTOS_COTIDIANO = ()
CONTROL_EN
DATA_CHANNEL_POLICY_EN
web evidence-only block
vision evidence-only block
young-adult visual DNA
dynamic canonical age
deprecated prompts.py shim
grounded v3.6 proactivity as the only official engine
clean validation archive builder
```

Esta rodada é concentrada.

---

# 1. FIX — STYLE DEFAULTS != LEARNED PATRICK STYLE

Reprodução que deve virar teste:

```text
fresh DB
message 1 = "oi tudo bem"
message 2 = "sim tudo certo"
```

Expected:

```text
NO learned kkkk
NO learned emoji
NO learned slang
```

Hoje aparecem defaults como se fossem evidência.

## Implementar

Cada dimensão deve armazenar:

```text
observed_count
actual observed value
```

e só entrar em `get_learned_style_summary()` se tiver evidência real.

Base pt-BR style fica fora do learned DB.

---

# 2. FIX — WORLDCONTEXT MUST USE EVIDENCE-AWARE STYLE API

Hoje o prompt builder lê `db.get_estilo()` diretamente.

Remover isso.

Target:

```text
StyleEngine.get_learned_style_summary()
```

ou equivalente.

Fresh DB + 1 message:

```text
has_learned_style = false
WorldContext must NOT contain [LEARNED STYLE]
```

---

# 3. FIX — PROMPT AUTHORITY AUDITOR

Atualizar:

```text
scripts/audit_prompt_authority.py
tests/test_prompt_authority_v370.py
```

Adicionar behavior contracts:

```text
2 bland messages
→ no fake learned laugh/emojis/slang

1 message
→ no learned-style block in WorldContext

learned dimension
→ must map to actual observed evidence
```

`status=passed` só depois disso.

---

# 4. FIX — URGENCY CLASSIFIER

HIGH/CRITICAL patterns MUST run before generic short-message LOW fallback.

Add explicit pt-BR cases such as:

```text
me ajuda
preciso de ajuda
acidente
hospital
machuquei
me machuquei
passei mal
estou passando mal
tô passando mal
é urgente
emergência
socorro
```

Use conservative classification.

Tests:

```text
CLASS + "me ajuda"
→ must not sit in ordinary LOW defer

CLASS + "acidente"
→ must not be LOW

SLEEPING + distress
→ classification correct independently of wake policy
```

---

# 5. FIX — EXPLICIT SLEEP WAKE POLICY

Do not silently allow CRITICAL to wake Marina.

Recommended first-soak config:

```env
CRITICAL_WAKE_POLICY_ENABLED=false
```

Document semantics.

When false:

```text
SLEEPING remains protected
```

If a future explicit wake mechanism is added:

```text
enable deliberately
```

Tests for both states if both are supported.

---

# 6. FIX — DEFERRED REPLAY MUST NOT DOUBLE-LEARN

`process_incoming_batch()` currently learns Patrick style at intake and again at deferred replay.

Ensure:

```text
one original user message
→ one learning observation
```

Possible simple guard:

```text
if pending_batch_id is not None:
    skip intake learning
```

Better if idempotent by source message ID.

Test:

```text
DEFER
→ pending replay
→ sample_count unchanged by replay
```

---

# 7. FIX — REAL SUPERSESSION/CANCELLATION

Implement before side effects.

Critical test:

```text
"manda uma foto"
→ DEFER

"deixa pra lá"
→ same pending conversation

when ready:
→ NO photo generation
→ NO FLUX call
→ stale request SUPERSEDED/suppressed
```

Also cover:

```text
voice
avatar
other side-effectful delayed action
```

Cancellation examples:

```text
deixa pra lá
esquece
não precisa
cancela
não manda mais
```

Do not create a heavy LLM cancellation classifier.

Deterministic + context-aware is enough for v3.7.0.

---

# 8. FIX — AUTOPATCHER CANON OWNER

Remove mapping:

```text
canon
→ prompt_policy.py / world_context.py
```

Canon is not prompt policy.

For this release prefer:

```text
canon edit
→ refuse automatic patch
→ require explicit World Bible target / canonical migration
```

unless a safe canonical patch owner already exists.

Test:

```text
"alterar canon da Marina"
→ does NOT patch prompt_policy.py
→ does NOT patch world_context.py as source of truth
```

---

# 9. FIX — PROACTIVITY SLEEP WINDOW

In Living World path:

```text
03:30–08:00 hardcoded clock
```

must not override explicit current state/calendar.

Target:

```text
WorldState / Calendar
> probabilistic routine
> time-of-day fallback
```

Test:

```text
05:00
explicit awake current state
→ not blocked solely by wall-clock sleep window
```

Legacy fallback clock may exist only if Living World/current state unavailable and documented as fallback, not authority.

---

# 10. P2 CLEANUP WHILE HERE

## Internal control language

Migrate remaining app-generated control prompts in avatar/speech workflows to English.

User-facing responses/examples remain pt-BR.

## Internal labels

If low-risk, normalize:

```text
[PLANNER ...]
Tone:
Goal:
[STRATEGIC INTENT...]
```

to English/language-neutral.

## memory_cli

`export_dump()` must derive age from birth_date or omit it.

## deprecated import

Remove unused:

```text
from prompts import build_autonomous_decision_prompt
```

and healthcheck dependency on deprecated prompts if unnecessary.

## activity mapper

Prefer explicit activity over place heuristic.

Examples that should behave sensibly:

```text
PUC + "tomando café no intervalo"
→ not automatically CLASS if explicit fresh activity says otherwise

apartment + "trabalhando num freela"
→ WORK, not HOME_RELAXING
```

---

# 11. TESTS TO ADD

Minimum:

```text
test_bland_messages_do_not_create_learned_style
test_world_context_respects_learned_style_threshold
test_deferred_replay_does_not_double_learn
test_short_distress_messages_not_low
test_sleeping_critical_requires_explicit_wake_policy
test_deferred_photo_cancellation_supersedes
test_deferred_voice_cancellation_supersedes
test_autopatcher_does_not_treat_prompt_policy_as_canon
test_explicit_awake_state_overrides_clock_sleep_fallback
```

---

# 12. VALIDATION

Run on Windows project venv:

```powershell
.\venv\Scripts\python.exe tests/run_isolated.py

.\venv\Scripts\python.exe -m unittest tests.test_prompt_authority_v370
.\venv\Scripts\python.exe -m unittest tests.test_response_availability_v370
```

Plus relevant:

```text
world context
camera
knowledge/privacy
calendar/academic
relationship/proactivity
response rhythm
planner
memory consolidator
session reflector
vision
```

---

# 13. BUILD CLEAN CODEX PACKAGE

Do NOT manually zip repository.

Use:

```powershell
.\venv\Scripts\python.exe scripts\build_validation_archive.py
```

or its documented arguments.

Verify archive contains no:

```text
.env
DB
.git
venv
scratch
private images
logs
```

---

# 14. HANDOFF TO CODEX

Only after all above are green.

Composer report must say:

```text
implementation complete
awaiting independent Codex validation
```

not:

```text
release approved
```

Codex must independently reproduce at least:

```text
bland style attack
WorldContext threshold
urgency distress cases
sleep wake policy
deferred learning idempotency
photo cancellation
canon AutoPatcher routing
05:00 explicit awake proactivity
clean package inspection
```

---

# 15. FINAL GATE FOR COMPOSER

Ready for Codex only when:

```text
P1 from this handoff = 0
full suite = green
new adversarial tests = green
clean validation archive = green
```

Then:

```text
✅ LIBERADO PARA CODEX
```

Not yet:

```text
✅ LIBERADO PARA SOAK
```

Codex owns the independent gate before real activation.

