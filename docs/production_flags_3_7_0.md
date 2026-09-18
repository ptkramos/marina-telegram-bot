# Production flags matrix — Marina v3.7.0

Audited by Codex after the 337/337 test gate on 18/09/2026. The bot process was
not running at audit time. The real `.env` now contains the approved v3.6 flags
set to `true`, plus all four 3.7.0 flags: availability, telemetry, latency and
batching. The user elected to test the complete release; an enforcement smoke
passed on a disposable copy of the real canonical DB. No live smoke or
seven-day soak has started. Provider keys needed by Novita and Feriados are present. Secrets are
never listed. The table's Default column describes code defaults, not the
current `.env` state.

The real `.env` also pins both Novita voice profile IDs, dual-voice routing,
cross-profile fallback policy, and each profile's speed/pitch. Previously
these were absent and supplied by matching code defaults. A configuration
check confirmed two distinct profiles and the intended normal/intimate routes.
The real `.env` now explicitly enables the older behavior flags that had
previously depended on code defaults. It also enables
`MEMORY_HYGIENE_ENABLED=true` and `SESSION_REFLECTION_ENABLED=true`, with
24-hour hygiene and a 90-minute reflection idle threshold. The Memory Hygiene
job is required for periodic World Hygiene; the World Hygiene flag alone does
not schedule it. `SAFE_PATCHER_ENABLED` remains off because it controls remote
code editing through admin commands, not Marina's conversation or world model.

| Flag | Default | Category | Validated stage | Dependency | Secret/provider | Proposed production | Rollback | Notes |
|------|---------|----------|-----------------|------------|-----------------|---------------------|----------|-------|
| LIVING_WORLD_ENABLED | false | World Bible / Core | 3.6.x | bootstrap | — | ON (if already soak-approved) | set false | Authority for WorldState |
| STORY_SEED_LIBRARY_ENABLED | false | Story Engine | 3.6.2 | LIVING_WORLD | — | keep prior | set false | |
| KNOWLEDGE_PRIVACY_ENABLED | false | Knowledge / Privacy | 3.6.3 | LIVING_WORLD | — | keep prior | set false | |
| RELATIONSHIP_WORLD_ENABLED | false | Relationship / Proactivity | 3.6.5 | LIVING_WORLD + PRIVACY | — | keep prior | set false | |
| CAMERA_WORLD_CONTINUITY_ENABLED | false | Camera | 3.6.6 | LIVING_WORLD | Novita image | keep prior | set false | |
| WORLD_HYGIENE_ENABLED | false | World Hygiene | 3.6.7 | LIVING_WORLD | — | keep prior | set false | |
| RESPONSE_RHYTHM_ENABLED | false | Conversational Naturalness | 3.6.7 | — | — | keep prior | set false | Brief hint works when policy selected |
| VOICE_PROSODY_ENABLED | false | Voice Prosody | 3.6.x | voice provider | Novita | keep prior | set false | |
| VOICE_PROSODY_EMOTION_ENABLED | false | Voice Prosody | 3.6.x | VOICE_PROSODY | Novita | keep prior | set false | Emotion rendering |
| VOICE_PROSODY_PAUSES_ENABLED | false | Voice Prosody | 3.6.x | VOICE_PROSODY | Novita | keep prior | set false | Pause rendering |
| VOICE_PROSODY_SOUND_TAGS_ENABLED | false | Voice Prosody | 3.6.x | VOICE_PROSODY | Novita | keep prior | set false | Sound tags |
| VOICE_PROSODY_FILLERS_ENABLED | false | Voice Prosody | 3.6.x | VOICE_PROSODY | Novita | keep prior | set false | Fillers |
| VOICE_PROSODY_CONTINUOUS_SOUND_ENABLED | false | Voice Prosody | 3.6.x | VOICE_PROSODY | Novita | keep prior | set false | Continuous sound |
| CALENDAR_CONTINUITY_ENABLED | false | Calendar / Events | 3.6.4 | LIVING_WORLD | — | keep prior | set false | Preferred activity authority |
| ACADEMIC_LIFE_ENABLED | false | Academic | 3.6.4 | calendar | — | keep prior | set false | |
| ACADEMIC_AUTO_TERM_GENERATION | false | Academic | 3.6.4 | ACADEMIC_LIFE + calendar | — | keep prior | set false | Future term projection |
| REAL_CONTEXT_FETCH_ENABLED | false | Real World Context | 3.6.4 | calendar | network | keep prior | set false | |
| FERIADOS_API_ENABLED | false | Holiday provider | 3.6.4 | REAL_CONTEXT | FERIADOS_API_KEY | keep prior | set false | |
| REAL_WORLD_PLACE_LOOKUP_ENABLED | false | Real-World Lookup | 3.6.4 | — | network | keep prior | set false | |
| RESPONSE_AVAILABILITY_ENABLED | false | Response Availability | 3.7.0 | — | — | ON | set false | Computes decisions |
| HUMAN_REPLY_LATENCY_ENABLED | false | Human Latency | 3.7.0 | RESPONSE_AVAILABILITY | — | ON | set false | Enables DEFER path |
| PENDING_CONVERSATION_BATCHING_ENABLED | false | Pending Batching | 3.7.0 | HUMAN_REPLY_LATENCY | — | ON | set false | Persist/merge batches |
| REAL_USAGE_TELEMETRY_ENABLED | false | Telemetry | 3.7.0 | — | — | true during soak | set false | Operational table only |
| RESPONSE_AVAILABILITY_DEBUG | false | Telemetry | 3.7.0 | — | — | optional | set false | Extra logs |
| RESPONSE_AVAILABILITY_CHECK_SECONDS | 15 | Response Availability | 3.7.0 | >=5 | — | 15 | n/a | Scheduler interval |

## Audit classification

- `SAFE_TO_ENABLE`: `LIVING_WORLD_ENABLED`, `STORY_SEED_LIBRARY_ENABLED`,
  `KNOWLEDGE_PRIVACY_ENABLED`, `RELATIONSHIP_WORLD_ENABLED`,
  `WORLD_HYGIENE_ENABLED`, `RESPONSE_RHYTHM_ENABLED`,
  `CALENDAR_CONTINUITY_ENABLED`, `ACADEMIC_LIFE_ENABLED`,
  `ACADEMIC_AUTO_TERM_GENERATION`.
- `REQUIRES_EXTERNAL_PROVIDER`: `CAMERA_WORLD_CONTINUITY_ENABLED`,
  `VOICE_PROSODY_ENABLED` and its five effect flags,
  `REAL_CONTEXT_FETCH_ENABLED`, `REAL_WORLD_PLACE_LOOKUP_ENABLED`.
- `REQUIRES_SECRET`: `FERIADOS_API_ENABLED` (key present). Camera and voice
  also require a provider key (present); key presence does not certify uptime.
- `HUMAN_REPLY_LATENCY_ENABLED` and `PENDING_CONVERSATION_BATCHING_ENABLED`
  were enabled together after the offline shadow smoke and the user's request
  to test all implementations. Both can be disabled together for immediate
  rollback; the pending-response job still drains queued messages.

The three legacy LLM integration tests passed on the authorized run with
network access. After the final flag change, the configuration gate confirmed
37 behavior flags enabled, the enforcement smoke passed against a disposable
copy of the real database, and the two focused hygiene suites passed. The
legacy Reflection/Hygiene test suite requires the pre-3.6 Living World and
Knowledge Privacy flags off within that test process; the production `.env`
was not changed for this compatibility test.

## Recommended activation sequence (post-Codex only)

1. **Prepared:** the real `.env` enables the audited v3.6 flags and the
   provider flags with available Novita and Feriados credentials. The five
   voice effects were approved from the user's audio comparison.
2. **Prepared:** all 3.7.0 flags are `true`. Offline shadow and enforcement
   smokes against disposable copies of the real DB passed. Enforcement deferred
   during a confirmed class, merged an urgent follow-up and closed the batch
   after a simulated send.
3. **Pending live activation:** start the bot and smoke: ordinary exchange, short burst, admin-command
   bypass, privacy response, voice/photo request, provider failure fallback.
   Confirm the bot is reachable, telemetry records decisions, and deferred
   replies are delivered after their computed delay.
4. During live smoke, check deferred batch, urgent follow-up, restart recovery,
   multi-message output and rollback if any delivery issue occurs.
5. Begin the real seven-day soak. Do not start 3.7.1 before review of its
   actual delivery and latency report.

## Immediate rollback

```text
RESPONSE_AVAILABILITY_ENABLED=false
HUMAN_REPLY_LATENCY_ENABLED=false
PENDING_CONVERSATION_BATCHING_ENABLED=false
```

The pending-response scheduler remains registered even with enforcement flags off. On
its next tick it force-READYs outstanding batches and drains them through the
existing reply pipeline. No schema downgrade is required. Do not infer that
turning flags off deletes or silently discards queued user messages.
