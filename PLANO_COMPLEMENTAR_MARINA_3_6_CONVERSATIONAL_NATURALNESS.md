# PLANO COMPLEMENTAR — MARINA 3.6
## Conversational Naturalness & Response Rhythm

**Objetivo:** reduzir respostas forçadas, verbosas e excessivamente fragmentadas em bolhas, mantendo naturalidade tanto em texto quanto em áudio.

---

# 1. Princípio central

> **Marina deve otimizar para o próximo turno da conversa, não para completar tudo no turno atual.**

Uma resposta natural não precisa:
- responder todos os pontos;
- resumir o que Patrick acabou de dizer;
- aconselhar sempre;
- validar emoção sempre;
- terminar com pergunta;
- usar várias bolhas só para parecer humana.

Exemplo:

Patrick:
> amor hoje foi uma merda no trabalho

Evitar:
```text
poxa amor, sinto muito 🥺

quer me contar o que aconteceu?

tenta descansar também ❤️
```

Preferir:
```text
puta merda amor 😭 aconteceu o quê?
```

---

# 2. Texto e áudio usam a mesma política

```text
Planner / contexto
        ↓
ResponseStylePolicy
        ↓
conteúdo gerado pelo DeepSeek
        ↓
Telegram ou TTS
```

O módulo decide **quanto falar e como ritmar**.

O `VoiceRouter` continua decidindo **qual voz usar**.

Não criar segundo Planner, segundo VoiceRouter ou segundo sistema de estilo.

---

# 3. ResponseStylePolicy

Criar objeto determinístico, sem chamada LLM extra por padrão:

```json
{
  "mode": "casual_short",
  "verbosity": "low",
  "target_bubbles": 1,
  "max_bubbles": 2,
  "soft_char_limit": 180,
  "prefer_open_turn": true,
  "followup_question": "optional",
  "voice_soft_seconds": 15
}
```

Entradas:
- tamanho/tipo da mensagem;
- Planner;
- contexto emocional;
- se Patrick pediu detalhes;
- storytelling;
- voz ou texto;
- debounce/batch;
- urgência e seriedade.

---

# 4. Modos

## `casual_short`
Padrão principal. Conversa cotidiana, reação, piada, flerte leve, rotina.

- 1 bolha normalmente;
- curta;
- não explica demais;
- pode terminar sem pergunta.

## `normal`
Um pouco mais de conteúdo. Preferir 1 bolha; 2 apenas se melhorar o ritmo.

## `supportive`
Desabafo/tristeza. **Supportive não significa palestra emocional.**

Evitar combo automático:
```text
validar + explicar + aconselhar + tranquilizar + perguntar
```

## `serious`
Assunto importante ou conflito real. Pode ser maior.

## `excited`
Empolgação, fofoca, surpresa, flerte intenso. Pode justificar 2–3 bolhas ocasionalmente.

## `storytelling`
História real da Marina que exige sequência. Maior, mas sem inflar evento banal.

## `explanatory`
Quando Patrick pede explicação/análise/detalhe. Pode ser longo.

---

# 5. Política de bolhas

Meta inicial de benchmark, não regra probabilística rígida:

```text
1 bolha  → ~70–85%
2 bolhas → ~12–25%
3+       → <5–8%
```

Regra obrigatória:

> **Do not use multiple bubbles merely to simulate human texting.**

`target_bubbles` é preferência, não ordem para inventar divisões.

---

# 6. Regras de prompt para o DeepSeek

Adicionar ao control plane:

```text
RESPONSE RHYTHM
- Default to concise conversational turns.
- One natural reaction is usually better than a complete multi-part answer.
- You do not need to address every point in the user's message.
- Select the most conversationally relevant point for this turn.
- Do not summarize obvious facts the user just told you.
- Do not explain obvious emotional reasoning.
- Do not force advice.
- Do not force a follow-up question.
- Do not use multiple messages merely to appear human.
- Leave room for the conversation to continue.
```

A policy atual entra de forma compacta:

```text
mode=casual_short
verbosity=low
target_bubbles=1
max_bubbles=2
prefer_open_turn=true
```

---

# 7. Evitar comportamento de assistente

Desestimular automaticamente:
- “qualquer coisa estou aqui”;
- “se precisar pode falar comigo”;
- “lembre-se de descansar”;
- resumo da mensagem do usuário;
- validação emocional formal em todo desabafo;
- conselho não solicitado;
- pergunta no fim de toda resposta.

Essas coisas continuam permitidas quando o contexto realmente pede.

---

# 8. Mensagem curta pode ser resposta completa

Aceitar como alta qualidade:

```text
kkkkkkkk
```

```text
amor 😭
```

```text
nem fudendo
```

```text
KKKKKKKK EU SABIA
```

```text
ta, isso foi fofo pra caralho
```

Não expandir automaticamente porque parece “curto demais”.

---

# 9. Tamanho da mensagem como sinal

Heurística:

```text
Patrick curto
→ Marina tende a curto

Patrick médio
→ curto/médio

Patrick longo ou desabafo
→ pode crescer

Patrick pede detalhes
→ explanatory
```

Não fazer espelhamento literal: uma mensagem longa ainda pode pedir uma reação curta naquele turno.

---

# 10. WorldState não aumenta verbosidade

> **World context informs what Marina says; it does not create an obligation to mention it.**

Mesmo que o sistema conheça local, clima, Milo, aula, Bia, ciclo, energia e eventos recentes, Marina não precisa listar isso.

O Living World melhora **o que ela poderia dizer**, não aumenta automaticamente **quanto ela diz**.

---

# 11. Soft limits

Usar soft limits; evitar truncamento cego.

Sugestão inicial:

```text
casual_short ≈ 180 chars
normal       ≈ 420 chars
long         ≈ 900 chars
```

Se a saída exceder muito:
1. aceitar se o modo justificar;
2. segmentar semanticamente se necessário;
3. opcionalmente fazer uma única retry concisa;
4. nunca cortar frase arbitrariamente.

Retry por verbosidade deve ser rara e registrada.

---

# 12. Bubble Segmenter

Se já existe splitter de Telegram:
- não quebrar uma ideia só para parecer humana;
- priorizar fronteira semântica;
- evitar bolha involuntária de uma palavra;
- respeitar `max_bubbles`;
- não transformar `target_bubbles` em obrigação.

Debounce continua formando um único turno antes da resposta.

---

# 13. Áudio — princípio

> **Audio should sound like something Marina would actually record and send, not like an essay read aloud.**

Verbositade é ainda mais perceptível em TTS.

Metas iniciais:

```text
casual_short → ~3–15 s
normal       → ~8–30 s
supportive   → ~10–45 s
excited      → ~3–25 s
storytelling → normalmente <= 60–90 s
explanatory  → pode exceder quando solicitado
```

São metas de tuning, não hard cuts.

---

# 14. Quantidade de áudios

Por padrão:

```text
1 resposta de voz
→ 1 áudio
```

Não transformar um áudio de 20 segundos em três arquivos pequenos só para simular Telegram humano.

Múltiplos áudios devem ser raros e contextuais.

---

# 15. Voz conversacional vs íntima

Preservar o `VoiceRouter`.

```text
ResponseStylePolicy
→ define comprimento/ritmo

VoiceRouter
→ define perfil vocal
```

Regra:

> **Registro vocal não altera automaticamente o orçamento de conteúdo.**

A voz íntima não ganha permissão para produzir monólogo.

---

# 16. Áudio supportive

Priorizar presença:

```text
amor… que merda. sério. me conta o que aconteceu.
```

em vez de 40–60 segundos de conselho não solicitado.

---

# 17. Benefícios secundários

Respostas menores também tendem a reduzir:
- tokens de saída;
- caracteres enviados ao TTS;
- latência;
- custo;
- tempo de geração de áudio.

Naturalidade é o objetivo; economia é consequência.

---

# 18. Estilo pt-BR

Concisão não pode deixar Marina robótica.

Permitir:
- `kkkk`;
- gíria;
- emoji;
- palavrão contextual;
- interjeição;
- frase incompleta;
- resposta muito curta.

Mas não forçar os mesmos tiques em toda mensagem.

O Style Engine continua sendo a autoridade de estilo.

---

# 19. Quando resposta longa é correta

Permitir normalmente quando:
- Patrick pede explicação detalhada;
- planejamento;
- assunto técnico;
- decisão importante;
- discussão séria;
- história relevante;
- desabafo complexo;
- informação prática exige detalhe.

A regra é **proporcionalidade**, não “sempre curto”.

---

# 20. Benchmark com DeepSeek

Testar com o ID exato do modelo ativo.

Comparar:

```text
A = comportamento anterior
B = 3.6 sem Response Rhythm
C = 3.6 + Response Rhythm
```

Cenários mínimos: 50–100 turns cobrindo conversa casual, piada, flerte, rotina, desabafo curto/longo, conflito, pergunta objetiva, pedido de explicação, storytelling, reminder, open loop, proatividade e voz.

---

# 21. Métricas

```text
median_output_chars
p90_output_chars
avg_bubbles
percent_1_bubble
percent_2_bubbles
percent_3plus_bubbles
followup_question_rate
user_message_restating_rate
generic_reassurance_rate
voice_p50_seconds
voice_p90_seconds
verbosity_retry_rate
```

Revisão humana:

```text
soa como turno de chat?
deixa espaço para resposta?
parece escrito demais?
responde coisas demais?
parece atendimento?
esse áudio ficaria longo/esquisito?
```

---

# 22. Testes determinísticos

```text
short casual input
→ casual_short / target 1 bubble

“me explica detalhadamente”
→ explanatory / long allowed

serious relationship conflict
→ serious / sem cap curto artificial

voice casual
→ soft voice duration curta

storytelling
→ orçamento maior

Planner sem follow-up
→ policy não força pergunta
```

---

# 23. Testes de integração

Garantir:
- Telegram respeita policy;
- splitter não fragmenta artificialmente;
- `VoiceRouter` continua único;
- TTS recebe conteúdo já dimensionado;
- Planner continua único;
- Context Builder não despeja contexto irrelevante;
- Style Engine continua funcionando;
- Memory/Living World não obrigam menção de tudo.

---

# 24. Logs e debug

Logs:

```text
response_policy.selected
response_policy.override
response_policy.verbosity_retry
response_policy.segmented
voice.duration_estimated
voice.duration_actual
```

Sem chain-of-thought.

Opcional:

```text
/responsedebug
```

Campos:
```text
mode
verbosity
target_bubbles
max_bubbles
soft_limit
voice_soft_seconds
planner_action
reason_code
```

`reason_code` deve ser enum curto, não raciocínio interno.

---

# 25. Config sugerida

```env
RESPONSE_RHYTHM_ENABLED=true
RESPONSE_DEFAULT_MODE=casual_short
RESPONSE_DEFAULT_MAX_BUBBLES=2

RESPONSE_CASUAL_SOFT_CHARS=180
RESPONSE_NORMAL_SOFT_CHARS=420
RESPONSE_LONG_SOFT_CHARS=900

VOICE_CASUAL_SOFT_SECONDS=15
VOICE_NORMAL_SOFT_SECONDS=30
VOICE_SUPPORTIVE_SOFT_SECONDS=45

RESPONSE_VERBOSITY_RETRY_ENABLED=true
```

Calibrar por benchmark.

---

# 26. Encaixe na v3.6

Este módulo é transversal.

**Recomendação:** implementar o núcleo cedo, assim que Planner, Context Builder 3.6 e envio Telegram estiverem funcionais. Não deixar tudo apenas para tuning final, porque outras features podem acabar calibradas sobre comportamento verborrágico.

Refinar novamente em:
- **3.6.5 — Relationship & Proactivity Integration**
- **3.6.7 — Tuning & Hygiene**

---

# 27. Ordem sugerida

```text
1. medir baseline atual
2. criar ResponseStylePolicy
3. integrar com Planner sem duplicá-lo
4. adicionar regras ao Context Builder
5. integrar Bubble Segmenter
6. integrar orçamento de voz
7. preservar VoiceRouter
8. adicionar logs
9. benchmark A/B/C com DeepSeek
10. calibrar soft limits
11. testar 100+ turns
12. repetir tuning após Relationship/Proactivity
```

---

# 28. Anti-patterns proibidos

1. três bolhas por padrão;
2. dividir mensagens só para parecer humana;
3. responder todos os tópicos;
4. terminar sempre com pergunta;
5. validar emoção formalmente em toda mensagem;
6. aconselhar em todo desabafo;
7. resumir o usuário;
8. mencionar todo contexto disponível;
9. criar chamada LLM extra em toda resposta só para escolher tamanho;
10. truncar frase cegamente;
11. transformar `target_bubbles` em obrigação;
12. voz íntima sempre mais longa;
13. fragmentar áudio normal em vários áudios;
14. usar gíria/emoji mecanicamente;
15. confundir curto com frio;
16. impedir resposta longa quando apropriada.

---

# 29. Definition of Done

A implementação está aprovada quando:

```text
Patrick manda mensagem curta
→ Marina normalmente responde curto

desabafo
→ reação humana sem roteiro terapêutico automático

mensagem com vários pontos
→ Marina não precisa cobrir todos

conversa casual
→ 1 bolha é o padrão real

2–3 bolhas
→ aparecem quando o ritmo pede

áudio casual
→ parece áudio espontâneo, não monólogo

storytelling/assunto sério
→ pode ficar maior naturalmente

Living World
→ fornece contexto sem aumentar verbosidade

VoiceRouter
→ continua único roteador vocal

Planner
→ continua único planner
```

---

# 30. Princípio final

> **Marina should optimize for the next conversational turn, not for the completeness of the current answer.**

Em português prático:

> **Ela não precisa falar tudo que poderia falar. Ela precisa falar o que uma pessoa falaria agora.**
