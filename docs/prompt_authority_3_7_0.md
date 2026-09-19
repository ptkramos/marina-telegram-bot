# Prompt Authority Matrix — Marina v3.7.0 (pre-soak)

| Concern | Authority | Prompt consumer | Language | May invent? |
|---|---|---|---|---|
| Canon identity | World Bible | WorldContextBuilder / SafeCore | pt-BR content | No |
| Dynamic age | World Bible birth_date | WorldContextBuilder | structured | No |
| Current place/activity | WorldState / Calendar | WorldContextBuilder | structured/pt-BR | No |
| Calendar commitments | CalendarWorld | WorldContextBuilder | structured | No |
| Academic life | Academic projection | WorldContextBuilder | structured | No |
| Routine inference | Routine Engine | WorldContextBuilder (provisional) | structured | No detailed event |
| Knowledge / privacy | KnowledgePrivacy | WorldContext + dialogue gate | English control | No disclosure invent |
| Relationship / proactivity | RelationshipWorld | autonomous_routine_v36 | grounded | No EVENTOS_COTIDIANO |
| Response length / bubbles | ResponseRhythm | final system prompt | English | No |
| Availability / latency | ResponseAvailability | pre-generation gate | structured | No |
| Voice routing | VoiceRouter | media pipeline | structured | No |
| Photo context | CameraWorld + visual_profile | FLUX tags | English | No location invent |
| Visual DNA | MARINA_VISUAL_DNA_BASE | visual_profile / director | English | No fixed age |
| Planner | InternalPlanner | JSON plan | English control | No new facts |
| Memory consolidation | MemoryConsolidator | JSON extract | English control | No |
| Session reflection | SessionReflector | JSON reflection | English control | No new reality |
| Vision extraction | VisionService | JSON scene | English control | No |
| Style examples | style_engine | final response | pt-BR | No facts |
| Safe fallback (LW OFF) | prompt_policy.SafeCore | ContextBuilder | English control | No legacy canon |

## Retired

- `MARIN_SYSTEM_PROMPT` monolith (pre-v3.6 autobiography)
- `EVENTOS_COTIDIANO` random invented scenes
- `get_temporal_greeting()` activity invention → `get_daypart()` only
- `db._seed_default_profile` parallel Marina Seltin / age 19 autobiography

## Language policy

```text
CONTROL PLANE → English
STRUCTURED ENUMS/KEYS → keep existing (compat)
WORLD BIBLE / DIALOGUE EXAMPLES → pt-BR
USER-FACING OUTPUT → pt-BR
FLUX TAGS → English
```
