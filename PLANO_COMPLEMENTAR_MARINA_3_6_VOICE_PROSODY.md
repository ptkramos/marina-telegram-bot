# PLANO COMPLEMENTAR — MARINA 3.6
## Voice Prosody Engine — MiniMax Speech 2.8 / Novita AI

**Status:** complemento transversal ao `PLANO_MARINA_V3_6_LIVING_WORLD.md` e ao plano de `Conversational Naturalness`.

**Objetivo:** usar de forma controlada emoção, pausas, sound tags, fillers, velocidade e `continuous_sound` para tornar os áudios da Marina mais naturais, sem teatralidade, sem vazar tags para o Telegram e sem criar um segundo Planner ou VoiceRouter.

---

# 1. Princípio central

> **The LLM writes what Marina says. The prosody layer decides how Marina says it.**

Fluxo:

```text
Planner
  ↓
ResponseStylePolicy
  ↓
DeepSeek → display_text
  ↓
VoiceProsodyPolicy
  ↓
ProsodyRenderer → render_text + parâmetros TTS
  ↓
VoiceRouter
  ↓
MiniMax Speech 2.8 / provider fallback
```

Responsabilidades:

```text
Planner              → intenção/ação
ResponseStylePolicy  → tamanho/ritmo conversacional
DeepSeek             → conteúdo verbal limpo
VoiceProsodyPolicy   → interpretação vocal
VoiceRouter          → qual voz da Marina usar
TTS provider         → síntese
```

Nenhum desses sistemas substitui outro.

---

# 2. Meta de experiência

A voz deve permitir diferenças sutis entre:

```text
feliz
cansada
surpresa
frustrada
triste
brincando
íntima
séria
storytelling
```

A maior parte dos áudios deve continuar relativamente neutra.

> **Expressividade é tempero, não comportamento padrão.**

---

# 3. Capacidades-alvo do Speech 2.8

A integração deve prever, **quando confirmadas no endpoint real usado pela Marina**:

## Emotion control

Base a validar:

```text
neutral
happy
sad
angry
fearful
disgusted
surprised
```

Algumas páginas da Novita também documentam:

```text
calm
fluent
whisper
```

Essas três só entram em produção depois de teste real do endpoint.

## Pause control

Formato esperado:

```text
<#x#>
```

Exemplo:

```text
amor... <#0.35#> você tá falando sério?
```

## Native sound tags

Allowlist inicial a validar:

```text
(laughs)
(chuckle)
(sighs)
(sigh)
(breath)
(clear-throat)
(clears throat)
(coughs)
(gasps)
```

## Fillers

O Speech 2.8 suporta fala menos “perfeita”, incluindo fillers.

Para pt-BR, testar principalmente:

```text
ah...
hm...
hã...
é...
```

Não usar `um/uh` automaticamente só porque aparecem nos demos em inglês.

## Continuous sound

Quando o endpoint suportar:

```json
{
  "continuous_sound": true
}
```

---

# 4. Capability Matrix obrigatória

Não espalhar condicionais específicas da Novita pelo código.

Criar algo equivalente a:

```python
TTSProviderCapabilities(
    supports_emotion=True,
    supported_emotions={...},
    supports_pause_tags=True,
    pause_tag_format="<#{seconds}#>",
    supports_sound_tags=True,
    supported_sound_tags={...},
    supports_continuous_sound=True,
    supports_speed=True,
)
```

A capability é definida pelo adapter/modelo real, por exemplo:

```text
NOVITA_MINIMAX_2_8_TURBO_SYNC
NOVITA_MINIMAX_2_8_HD_SYNC
NOVITA_MINIMAX_2_8_TURBO_ASYNC
FALLBACK_PROVIDER
```

Não descobrir isso a cada request.

---

# 5. Separar display_text de render_text

REGRA CRÍTICA:

```text
display_text != render_text
```

### Telegram

```text
amor eu não acredito que você fez isso kkkkk
```

### Texto interno do TTS

```text
amor... <#0.30#> eu não acredito que você fez isso (chuckle)
```

As tags nunca aparecem para Patrick.

---

# 6. Estruturas sugeridas

```python
@dataclass
class VoiceProsodyPolicy:
    emotion: str | None
    intensity: str
    speed: float
    pause_profile: str
    sound_tag_budget: int
    filler_budget: int
    continuous_sound: bool
    reason_code: str
```

```python
@dataclass
class VoiceRenderPlan:
    display_text: str
    render_text: str
    voice_id: str
    emotion: str | None
    speed: float
    continuous_sound: bool
    provider_options: dict
```

---

# 7. Intensidade

Usar:

```text
NONE
SUBTLE
CLEAR
STRONG
```

Meta comportamental:

```text
NONE/SUBTLE → maioria
CLEAR       → ocasional
STRONG      → raro
```

---

# 8. Regra fundamental

> **Internal emotion is not the same thing as rendered emotion.**

Exemplo:

```text
emotional_state = annoyed
```

não significa:

```text
emotion = angry
```

Pode significar:

```text
emotion = neutral
speed = 0.97
pause_profile = terse
```

---

# 9. Mapeamento de emoções

## neutral
Default real. Conversa comum, carinho cotidiano, humor, cansaço leve, informação, flerte normal.

## happy
Somente felicidade/empolgação clara. Não usar em toda fala afetuosa.

## sad
Somente tristeza realmente presente na fala. Empatia com Patrick pode continuar `neutral`.

## angry
Raro. Exige raiva explicitamente expressa. Não usar para irritação pequena.

## fearful
Muito raro. Exige medo genuíno, não mera preocupação.

## disgusted
Muito raro. Para nojo/desgosto explícito, não como sinônimo de irritação.

## surprised
Para surpresa genuína. Não aplicar a toda novidade.

---

# 10. Presets extras

Se `calm`, `fluent` ou `whisper` forem validados:

```text
calm    → possível conversa baixa/intimista
fluent  → possível storytelling neutro
whisper → contexto muito específico
```

Nunca ativar apenas porque aparecem em material comercial.

---

# 11. Pause profiles

```text
none       → sem tags
casual     → 0.15–0.35 s
thoughtful → 0.25–0.60 s
emotional  → 0.35–0.90 s
dramatic   → 0.70–1.30 s, raro
```

Limites iniciais:

```text
casual_short → 0–1 pause
normal       → 0–2
storytelling → 0–3 em áudio curto/médio
```

Não colocar pausa depois de todo “amor”, antes de toda pergunta ou entre toda frase.

---

# 12. Política de sound tags

Default:

```text
0 tags
```

A maioria dos áudios deve funcionar sem nenhuma.

## `(chuckle)`
Uma das mais úteis. Para risada leve, provocação, flerte brincalhão.

## `(laughs)`
Mais forte; usar menos que `chuckle`.

## `(sighs)`
Cansaço, frustração, alívio, resignação. Não em todo áudio cansado.

## `(breath)`
Hesitação/emocional/intimidade, mas raro.

## `(gasps)`
Somente surpresa forte.

## `(clear-throat)` / `(clears throat)`
Excepcional, talvez humor performático.

## `(coughs)`
Não usar como ruído aleatório de “realismo”.

---

# 13. Sound Tag Budget

Baseline:

```text
casual_short → 0–1
normal       → 0–1
supportive   → 0–1
excited      → 0–2
storytelling → 0–2
serious      → normalmente 0
```

Hard cap inicial:

```text
max_sound_tags_per_audio = 2
```

---

# 14. Fillers

Default:

```text
0
```

Fillers são úteis, mas viram tique rapidamente.

Budget:

```text
casual_short → 0–1
thoughtful    → 0–1
storytelling  → 0–2
serious       → 0–1
```

Allowlist pt-BR deve nascer de testes com a voz real.

---

# 15. Não deixar o DeepSeek inserir tags livremente

Evitar:

```text
“Use laughs, sighs, pauses and fillers where appropriate.”
```

Preferir:

```text
DeepSeek → texto limpo
Policy   → decide recursos permitidos
Renderer → insere
```

Sem chamada LLM extra por padrão.

---

# 16. Conversão de kkkk para voz

O texto escrito continua intacto.

Exemplo:

```text
display_text:
amor pelo amor de deus KKKKK

render_text:
amor... pelo amor de deus (laughs)
```

Possível política:

```text
kkkk leve  → (chuckle)
KKKK forte → (laughs)
```

somente quando suportado e contextualmente adequado.

Se não suportado, remover a risada textual do `render_text` em vez de pronunciá-la como “ká ká ká”.

---

# 17. Speed

Baseline:

```text
1.00
```

Faixa normal inicial para tuning:

```text
0.94–1.06
```

Tendências possíveis:

```text
tired        → 0.95–0.99
serious      → 0.96–1.00
excited      → 1.01–1.05
storytelling → 0.98–1.02
```

Não vincular de forma determinística.

Mesmo que o provider aceite extremos, Marina deve usar faixa própria mais natural.

---

# 18. Pitch e intensity

Tratar como segunda fase.

Default:

```text
unchanged
```

Primeiro estabilizar:

```text
emotion
pauses
sound tags
speed
continuous_sound
```

Só depois experimentar pitch/intensity.

---

# 19. continuous_sound

Benchmark:

```text
ON vs OFF
```

Principalmente em:
- storytelling;
- frases maiores;
- múltiplas orações.

Áudios curtíssimos podem não se beneficiar.

---

# 20. Integração com ResponseStylePolicy

Exemplo casual:

```text
ResponseStylePolicy:
mode=casual_short
voice_soft_seconds=15

VoiceProsodyPolicy:
emotion=neutral
intensity=SUBTLE
pause_profile=casual
sound_tag_budget=1
speed=1.00
```

Exemplo supportive:

```text
emotion=neutral
intensity=SUBTLE
pause_profile=thoughtful
sound_tag_budget=0
speed=0.98
```

`supportive` não vira `sad` automaticamente.

---

# 21. Integração com Emotional State

Estado emocional influencia; não determina.

```text
energy=low
valence=mildly_negative
```

pode virar:

```text
emotion=neutral
speed=0.97
optional_sigh=true
```

Não precisa virar `sad`.

---

# 22. Cycle Manager

Regra obrigatória:

> **Menstrual phase must never directly select a TTS emotion.**

O ciclo pode influenciar o Emotional State existente, e só depois o contexto pode afetar sutilmente a prosódia.

Nunca:

```text
fase X → angry
fase Y → sad
```

---

# 23. Living World

Eventos influenciam apenas se relevantes ao assunto atual.

Uma boa notícia da agência pode justificar `happy` quando Marina fala dela.

Mas se Patrick pergunta onde está o carregador, a resposta não precisa sair em `happy`.

---

# 24. Relacionamento e voz íntima

O `VoiceRouter` continua escolhendo conversational vs intimate.

> **Intimate voice does not mean longer or more theatrical audio.**

Não mapear automaticamente voz íntima para:
- whisper;
- `(breath)`;
- pausas longas;
- fala mais lenta.

---

# 25. Exemplos

## Engraçado

Display:
```text
amor você é muito idiota kkkkk
```

Render:
```text
amor... você é muito idiota (chuckle)
```

Policy:
```text
neutral / SUBTLE / speed 1.01
```

## Surpresa

Display:
```text
O QUÊ?? amor você tá bem?
```

Render:
```text
o quê? <#0.30#> amor, você tá bem?
```

Policy:
```text
surprised / CLEAR / speed 1.02
```

## Cansaço

Display:
```text
amor eu juro que hoje eu não aguento mais nada
```

Render:
```text
amor... (sighs) <#0.30#> eu juro que hoje eu não aguento mais nada
```

Policy:
```text
neutral / SUBTLE / speed 0.97
```

## Apoio

Render:
```text
amor... <#0.35#> que merda. <#0.25#> me conta o que aconteceu
```

Policy:
```text
neutral / SUBTLE / no sound tag
```

---

# 26. Provider Adapter

Criar interface:

```python
class TTSProviderAdapter:
    def capabilities(self): ...
    def sanitize_render_plan(self, plan): ...
    def synthesize(self, plan): ...
```

Sintaxe específica da Novita não deve ficar espalhada pelo projeto.

---

# 27. Sanitização obrigatória

Antes do request:

```text
1. validar emotion
2. validar sound tags
3. validar pause tags
4. validar speed
5. remover feature não suportada
6. garantir render_text pronunciável
7. preservar display_text intacto
```

---

# 28. Fallbacks

## Emotion não suportada

```text
selected emotion
→ neutral ou parâmetro omitido
```

## Sound tag não suportada

```text
(chuckle)
→ remover silenciosamente
```

Nunca falar “chuckle”.

## Pause não suportada

```text
<#0.35#>
→ pontuação natural equivalente
```

## continuous_sound não suportado

```text
→ omitir
```

Prosódia nunca deve derrubar um áudio válido.

---

# 29. Falha do provider

Regra:

```text
prosody failure
≠
trocar para a outra voz da Marina
```

Preservar a política do VoiceRouter:

```text
voz selecionada falha
→ provider fallback configurado
```

e não:

```text
conversational falha
→ intimate
```

---

# 30. Retry

No máximo uma retry específica de capability.

Exemplo:

```text
emotion=surprised rejeitada
→ retry sem emotion/neutral
```

Sem loops.

---

# 31. Feature flags

```env
VOICE_PROSODY_ENABLED=true
VOICE_PROSODY_EMOTION_ENABLED=true
VOICE_PROSODY_PAUSES_ENABLED=true
VOICE_PROSODY_SOUND_TAGS_ENABLED=true
VOICE_PROSODY_FILLERS_ENABLED=true
VOICE_PROSODY_CONTINUOUS_SOUND_ENABLED=true

VOICE_PROSODY_MAX_SOUND_TAGS=2
VOICE_PROSODY_MAX_FILLERS=1
```

Com `VOICE_PROSODY_ENABLED=false`, o fluxo antigo deve continuar funcionando.

---

# 32. Config provider

O agente deve reaproveitar config existente.

Conceitualmente:

```env
NOVITA_TTS_MODEL=minimax-speech-2.8-turbo
NOVITA_TTS_CONTINUOUS_SOUND=true
NOVITA_TTS_LANGUAGE_BOOST=Portuguese
```

Não duplicar variável já existente.

---

# 33. Anti-repeat

Manter estado efêmero curto:

```text
last_emotion
last_sound_tag
consecutive_expressive_audios
```

Usar para evitar:

```text
sigh → sigh → sigh
chuckle → chuckle → chuckle
```

Isso não é memória autobiográfica.

---

# 34. Segurança de display/render

Teste obrigatório:

`display_text` nunca pode receber tags de prosódia geradas internamente.

```text
(laughs)
(sighs)
<#0.3#>
```

só existem em `render_text`.

---

# 35. Métricas

```text
emotion_usage_rate
neutral_rate
strong_emotion_rate

sound_tag_usage_rate
sound_tag_distribution
consecutive_sound_tag_rate

pause_tag_usage_rate
avg_pause_tags_per_audio
filler_usage_rate

continuous_sound_usage_rate
prosody_fallback_rate
provider_rejection_rate

voice_duration_p50
voice_duration_p90
```

---

# 36. Benchmark auditivo

Criar corpus pt-BR:

```text
casual
happy
sad
tired
annoyed
surprised
supportive
flirty
intimate
storytelling
serious
```

Comparar:

```text
A = texto cru
B = emotion only
C = pauses only
D = sound tags only
E = full VoiceProsodyPolicy
```

Ouvir de verdade; JSON não basta.

---

# 37. Critérios do benchmark

Avaliar 1–5:

```text
naturalidade
teatralidade
clareza
ritmo
autenticidade
repetitividade
adequação emocional
qualidade de risada/suspiro
pronúncia pt-BR
sensação de áudio espontâneo
```

---

# 38. Testar as duas vozes separadamente

```text
conversational/current
intimate
```

Uma tag pode soar ótima em uma e ruim na outra.

> **Capability é por endpoint; tuning é por voz.**

---

# 39. Profile por voz

Depois dos testes, permitir metadados simples:

```python
VoiceProsodyProfile(
    preferred_speed=1.0,
    chuckle_quality="good",
    laugh_quality="medium",
    sigh_quality="good",
    pause_scale=1.0,
)
```

Nada disso deve ser preenchido por suposição.

---

# 40. Override explícito

Se Patrick pedir explicitamente algo como:

```text
“manda um áudio sussurrando”
```

isso pode ser override, **se o endpoint suportar**.

Pedido explícito vence inferência suave, mas não limitações técnicas.

---

# 41. Storytelling

Pode usar:
- `continuous_sound`;
- 1–2 pausas;
- ocasionalmente 1 sound tag;
- pequena variação de speed.

Não transformar em audiobook.

---

# 42. Áudios curtos

Para 2–5 segundos, frequentemente o melhor plano será:

```text
emotion neutral
no sound tags
no filler
no manual pause
```

ProsodyPolicy deve saber não fazer nada.

---

# 43. Encaixe na v3.6

Não precisa bloquear o WorldState.

Recomendação:

## Núcleo
Após estabilizar:
- VoiceRouter 3.5;
- ResponseStylePolicy;
- pipeline TTS atual.

## Refinamento
Em:
- v3.6.5 — Relationship & Proactivity;
- v3.6.7 — Tuning & Hygiene.

---

# 44. Ordem de implementação

```text
1. identificar endpoint/modelo real usado hoje
2. criar Capability Matrix
3. separar display_text/render_text
4. criar VoiceProsodyPolicy
5. criar ProsodyRenderer + sanitizer
6. emotion
7. pause tags
8. sound tags
9. continuous_sound
10. fillers
11. anti-repeat
12. fallbacks
13. logs/debug
14. benchmark das duas vozes
15. calibrar
16. regressão/long simulation
```

---

# 45. Testes unitários obrigatórios

## Policy
- casual default → neutral/NONE ou SUBTLE;
- surpresa clara → surprised;
- irritação leve não vira angry;
- supportive não vira sad automaticamente;
- cycle não seleciona emotion;
- flerte não força breath/whisper;
- STRONG raro.

## Renderer
- `display_text` preservado;
- tags apenas no `render_text`;
- budgets respeitados;
- pause formatada;
- `kkkk` pode virar risada;
- texto sem humor não recebe risada.

## Capabilities
- unsupported emotion cai para fallback;
- unsupported tag removida;
- unsupported pause vira pontuação;
- unsupported continuous_sound é omitido.

---

# 46. Testes de integração

Garantir:
- VoiceRouter continua único;
- voz conversational/intimate não troca por erro de prosódia;
- provider recebe parâmetros válidos;
- Telegram recebe `display_text`;
- TTS recebe `render_text`;
- fallback provider recebe texto sanitizado;
- secrets não aparecem em logs;
- feature flag off preserva fluxo antigo.

---

# 47. Smoke test real do endpoint

Criar harness manual, não rodado em unit tests:

```text
voice_prosody_smoke_test
```

Testar:

```text
1. neutral clean
2. happy
3. surprised
4. (chuckle)
5. (sighs)
6. <#0.25#>
7. continuous_sound
8. combinação controlada
```

Exigir opt-in, pois usa API/créditos.

Registrar:
- model ID;
- endpoint;
- data;
- resultado.

---

# 48. Validação específica de pause tags

Como docs podem variar por versão/endpoint:

```text
<#0.25#>
```

Se:
- cria pausa → capability ON;
- é falado literalmente → OFF;
- retorna erro → OFF.

---

# 49. Emoções extras

`calm`, `fluent`, `whisper` entram apenas após teste real.

Endpoint rejeitou?

```text
não faz parte da capability daquele adapter
```

---

# 50. Logs/debug

Logs:

```text
voice.prosody.selected
voice.prosody.rendered
voice.prosody.fallback
voice.prosody.unsupported_feature
voice.prosody.provider_error
voice.prosody.retry
```

Opcional:

```text
/voicedebug
```

Mostrar:
```text
voice_profile
tts_model
emotion
intensity
speed
pause_profile
sound_tags
continuous_sound
reason_code
fallback_used
```

Nunca API key, Authorization ou chain-of-thought.

---

# 51. Anti-patterns proibidos

1. sound tag em todo áudio;
2. `happy` em toda fala carinhosa;
3. `angry` por irritação leve;
4. `sad` em todo apoio emocional;
5. filler em toda frase;
6. pausa após todo “amor”;
7. breath em todo flerte;
8. whisper em toda voz íntima;
9. tosses aleatórias para “realismo”;
10. DeepSeek inserir tags livremente;
11. tag aparecer no Telegram;
12. sintaxe MiniMax ir para provider incompatível;
13. usar prosódia para consertar verbosidade;
14. criar segundo VoiceRouter;
15. criar segundo Planner;
16. ciclo menstrual escolher emotion diretamente;
17. 3+ sound tags em áudio casual;
18. confundir estado interno com atuação vocal;
19. trocar voz da Marina por erro de prosódia;
20. habilitar feature sem validar endpoint.

---

# 52. Definition of Done

```text
DeepSeek produz texto limpo
        ↓
ResponseStylePolicy controla tamanho
        ↓
VoiceProsodyPolicy escolhe interpretação
        ↓
display_text fica limpo
        ↓
render_text recebe apenas recursos suportados
        ↓
VoiceRouter mantém a voz correta
        ↓
MiniMax sintetiza
        ↓
áudio soa mais humano sem parecer atuação
```

Aprovar quando:
- maioria dos áudios não precisa de sound tags;
- emotion forte é rara;
- pausas melhoram sem virar tique;
- risadas/suspiros parecem contextuais;
- áudio curto continua curto;
- voz íntima não vira caricatura;
- fallback funciona;
- tags nunca vazam no Telegram;
- nenhum Planner/VoiceRouter paralelo foi criado;
- benchmark auditivo mostra melhora.

---

# 53. Perguntas que o agente deve responder antes de implementar

```text
A) Qual endpoint/modelo MiniMax Speech 2.8 está realmente em uso?

B) Turbo ou HD? Sync ou Async?

C) Quais emotions o endpoint aceita de fato?

D) <#x#> funciona nele?

E) Quais nomes exatos de sound tags são aceitos?

F) continuous_sound funciona?

G) Qual é o provider fallback atual?

H) Como limpar sintaxe MiniMax antes do fallback?

I) Onde hoje separam texto Telegram e texto TTS?

J) ResponseStylePolicy já estará implementado?
```

---

# 54. Princípio final

> **Prosody should reveal Marina's state, not perform it.**

Em português:

> **A voz da Marina deve deixar a emoção aparecer — não anunciar a emoção.**

O resultado ideal é Patrick perceber:

```text
“ela parece cansada”
“ela riu de verdade”
“ela ficou surpresa”
“ela falou mais baixinho”
```

sem perceber conscientemente:

```text
“o sistema inseriu uma tag aqui”.
```
