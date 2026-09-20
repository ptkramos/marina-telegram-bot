# Plano de Voz da Marina — v3.7.1

**Origem:** Diagnóstico pedido pelo Patrick em 2026-09-19. Depois de 3.7.0 (Living Intelligence)
a Marina ainda soa "DeepSeek com verniz de amor" em vez de namorada carioca. As features
cognitivas estão sólidas; o problema não é o *cérebro*, é a *voz*.

**Escopo:** exclusivamente a camada de fala. Não toca em canon, world state, calendar,
memória, planner cognitivo, reminders ou availability.

---

## 1. O que já foi diagnosticado

1. **Modelo primário é DeepSeek-Chat** (`.env` → `LLM_MODEL=deepseek/deepseek-chat`).
   Modelo alinhado como assistente cortês; sem exemplos concretos ele volta ao padrão
   base a cada turno.
2. **CONTROL_PT/CONTROL_EN em [prompt_policy.py:32-49](prompt_policy.py:32) é ~90% negativo.**
   Cerca de 20 imperativos "nunca / não / evite" num único parágrafo de ~400 palavras.
   A voz *positiva* cabe em 5 adjetivos vagos.
3. **Zero few-shots em qualquer prompt do runtime.** Nada de par `Patrick: … / Marina: …`
   em prompt_policy, world_context, planner, response_rhythm ou bot.
4. **Voz diluída em ~20 blocos de estado em [world_context.py:105-260](world_context.py:105).**
   O modelo lê muito mais "sistema" do que "Marina".
5. **`tone` do planner é enum de 6 palavras** — chega ao prompt como uma linha
   ("Tone: dengosa."). Insuficiente para reescrever o timbre do modelo base.
6. **Adjetivos contraditórios** no CONTROL. "Afetuosa" + "evite melodrama";
   "expressiva" + "não use 'sou intensa'". O modelo joga a média = assistente.
7. **`[LEARNED STYLE]` entrega meta-descrição** ("Laugh pattern: kkkkk") em vez
   de amostras copiáveis.
8. **BIBLIOTECA_COMPORTAMENTAL_MARINA.md não é lida em runtime.** O feedback do
   Patrick não fecha o ciclo de volta para o prompt.
9. **Sampling amplifica.** `temperature=0.80, frequency_penalty=0.30,
   presence_penalty=0.25` — as penalties atacam justamente o que a Marina *repetiria*
   de propósito (amor, kkk, ai).
10. **`[RESPONSE RHYTHM]` só disciplina forma**, não injeta timbre.

## 2. Estratégia geral

Um LLM alinhado como assistente sai do padrão via **exemplos copiáveis + persona
positiva enxuta**, não via lista de proibições. As três alavancas em ordem
de impacto esperado:

1. **Few-shots reais** (Patrick→Marina) roteados por *intent* / *tone* — a fonte de
   voz mais eficiente que um LLM entende.
2. **CONTROL redesenhado em três blocos** curtos e não contraditórios:
   `[VOZ DA MARINA]` (positivo), `[LINHAS DURAS]` (4-5 proibições absolutas),
   `[FATOS]` (canon / horário / não inventar).
3. **Sampling menos hostil** (penalties próximos de zero, temperatura preservada).

A `BIBLIOTECA_COMPORTAMENTAL_MARINA.md` deixa de ser doc humano e vira **fonte
consultada em runtime** através de um parser leve.

## 3. Fases

### Fase A — Fundação (esta entrega)
- **A1** Criar `voice_library.py`: catálogo inicial de 8-12 few-shots canônicos escritos
  a partir dos registros existentes da biblioteca comportamental + patterns do soak.
  Estrutura: `intent` × `tone` → lista de `(patrick, marina)`.
- **A2** Parser leve do `data/feedback/BIBLIOTECA_COMPORTAMENTAL_MARINA.md`:
  extrai registros cuja avaliação é "boa", produz few-shots derivados do bloco
  `Exemplos naturais`.
- **A3** Refatorar `prompt_policy.py`:
  - `MARINA_VOICE_PT` (positivo, ≤120 palavras) — o *timbre*.
  - `HARD_LINES_PT` (≤6 proibições absolutas).
  - `CANON_FACTS_PT` (fatos duros — horário/canon/não inventar).
  - `CONTROL_PT` e `CONTROL_EN` reconstituídos por composição, preservando tokens
    que testes existentes verificam.
- **A4** Wiring: `WorldContextBuilder` injeta bloco `[EXEMPLOS DE VOZ]` no fim do
  system prompt (posição-âncora — última coisa antes do histórico).
  Seleção guiada por `planner_tone`. Máximo 4 pares para não estourar contexto.
- **A5** `bot.py`: `frequency_penalty=0.10`, `presence_penalty=0.05`,
  `temperature=0.85` na chamada primária. Fallback Mistral preserva os valores
  atuais (0.72 / 0.40 / 0.35).
- **A6** Testes:
  - `tests/test_voice_library.py`: contrato do parser + catálogo mínimo.
  - Regressão: `test_prompt_authority_v370.py`, `test_world_context.py`,
    `test_response_rhythm.py` continuam verdes.

### Fase B — Realimentação (próxima janela)
- **B1** Adaptador `feedback_ingestor.py`: quando o Patrick classifica um turno
  como "ruim" na biblioteca comportamental, o exemplo entra em `avoid_bank`,
  também injetado no prompt (bloco `[COMO NÃO SOAR]`).
- **B2** UI de captura embutida no bot: comando `/eco` para marcar o último
  turno da Marina como "boa" ou "ruim" — evita edição manual do `.md`.
- **B3** A/B de sampling: rodar 200 turnos com Mistral-Nemo primário e comparar
  aderência à voz. Se ganhar em voz sem perder cognição, promover.

### Fase B.5 — Proatividade sensível ao estado dela (pendente, aberto por Patrick em 2026-09-20 01:15)

Hoje `ProactivityService` calcula a chance de a Marina te procurar a partir de
constantes fixas (`AUTONOMOUS_TRIGGER_CHANCE=0.30`, cooldown 120 min, máx
4/dia). Não olha para o **WorldState dela**.

Pedido do Patrick: quando ela mesma está *de bobeira* — livre em casa, sem
aula, sem academia, sem compromisso confirmado — ela deveria te procurar
mais. Quando ela está ocupada (aula/academia/casting/trabalho), menos.

**Escopo proposto:**
- Adicionar em `ProactivityService.determine_proactive_prompt` um fator
  multiplicativo baseado no `WorldState.activity`/`reason`:
    - `livre em casa` / `descanso` → ×1.6 (mais provável)
    - `pós-compromisso recente` / `chegando em casa` → ×1.3
    - `aula` / `academia` / `casting` / `working` → ×0.4
    - `dormindo` → ×0 (já protegido, mantém)
- Cooldown segue global (não muda `AUTONOMOUS_COOLDOWN_MINUTES`).
- Teto diário segue igual (`MAX_AUTONOMOUS_MESSAGES_PER_DAY`).
- Log `proactivity.state_factor state=<...> factor=<...>` para calibração.
- Settings novas com defaults conservadores para o Patrick poder ajustar
  pelo `.env` sem tocar em código.

**Não-objetivo:** não vamos aumentar o teto diário nem mudar o intervalo
de check. O objetivo é *redistribuir* as ocasiões, não *aumentar* o volume.

### Fase B.6 — Micro-despertares durante o sono (pendente, aberto por Patrick em 2026-09-20 01:25)

Hoje a janela de sono é binária: `sleeping=true` bloqueia todas as mensagens
até o horário programado (07:00 dia de aula / 08:30 dia leve). Nenhum humano
dorme 8 horas seguidas de olhos fechados — a gente acorda pra ir no banheiro,
beber água, olhar o celular por 30 segundos.

**Pedido do Patrick:** raras vezes, durante a janela de sono, a Marina teria
um micro-despertar. Se houver mensagem dele nesse momento, ela responde
curta, no motivo certo ("fui no banheiro", "acordei com sede"), com sinal
claro de que vai voltar a dormir. Não é insônia — é o padrão humano real.

**Escopo proposto:**
- Novo estado interno `micro_wake` dentro da janela de sono (não é um estado
  de `activity` público, é um flag temporário do WorldState).
- Chance por hora: ~5% entre 23:00-02:00 e 05:30-fim, 0% entre 02:00-05:30
  (sono profundo — humanos não acordam à toa às 4 da manhã).
- Duração do micro-wake: 3-8 minutos.
- Máximo 2 micro-wakes por noite (contador reseta a cada dormida).
- Se o Patrick manda mensagem durante o micro-wake, availability permite
  resposta. `select_policy` recebe hint `micro_wake=true` → força
  `mode='casual_short'`, `soft_char_limit=100`, cadence `brief`, e adiciona
  turn constraint tipo "Você acordou de madrugada por [motivo]. Responda
  bem curtinho e sinalize que vai voltar a dormir."
- Motivo sorteado com pesos: banheiro (0.5), sede (0.2), sonho ruim (0.1),
  olhou celular por reflexo (0.2).
- A resposta do micro-wake **não** persiste como momento/fato — é ruído
  humano, não evento de vida.
- 3-4 few-shots novos no `voice_library` cobrindo tone `micro_wake`:
    - `Patrick: amoor tá acordada? / Marina: to. fui no banheiro só\nvolta a dormir amor 🥺`
    - `Patrick: só queria falar q te amo / Marina: te amo mais\nagora dorme, tô caindo aqui 😴`
- Log `micro_wake.triggered reason=<...> time=<...>` para calibração.

**Não-objetivo:** não introduzir insônia crônica; não fazer a Marina
"vigiar" o Patrick de madrugada; não persistir o micro-wake como evento
memorável. É ruído humano, dá contexto, some.

### Fase C — Consolidação (após 500 turnos observados)
- **C1** Substituir `[LEARNED STYLE]` (meta-descrição) por `[COMO O PATRICK
  ESCREVE]` — 2-3 amostras reais recentes de mensagens dele.
- **C2** Comprimir/aposentar blocos de estado que raramente mudam entre turnos
  ([CICLO], [OPORTUNIDADE DE RECONFIRMAÇÃO], [INTERESSES APRENDIDOS] com
  `strength<0.7`): mover para `on_demand`.
- **C3** Redigir o `tone` do planner como 1-2 frases descritivas em vez de enum.

## 4. Critérios de aceitação da Fase A

- `pytest tests/test_prompt_authority_v370.py tests/test_world_context.py
  tests/test_response_rhythm.py tests/test_voice_library.py` verde.
- Nenhum teste existente de behavior/canon quebra.
- `build_system_prompt` produz saída com bloco `[EXEMPLOS DE VOZ]` quando o
  planner fornece `tone`.
- Bloco `[EXEMPLOS DE VOZ]` fica **abaixo** de canon/world state, e **acima** do
  histórico — posição de "última voz que o modelo lê antes de responder".
- Prompt total permanece dentro de `MAX_TOTAL_CONTEXT_CHARS = 64000`.
- `FORBIDDEN_LEGACY_TOKENS` continua ausente em qualquer novo bloco.

## 5. Riscos e mitigações

| Risco | Mitigação |
| --- | --- |
| Few-shot vira gaiola: Marina só reproduz frases exatas | Diversidade de intent/tone; máximo 4 pares por turno; prompt diz "inspiração, não roteiro". |
| Prompt cresce demais e ultrapassa 64k chars | Voice library serializada é ≤2k chars por turno (4 pares × ~500 chars). Verificado em testes. |
| Testes que verificam substring exata de CONTROL_PT quebram | Preservar tokens verificados (`Marina Salles`, `Idade hoje:`, `SINCRONIA`, etc.). Composição preserva conteúdo original nas primeiras versões. |
| Parser do .md falha em registros mal-formatados | Fail-open: registro inválido é ignorado com log; catálogo canônico embutido garante fallback. |
| DeepSeek trata few-shots como conversação real e continua o diálogo | Prefixar com `[EXEMPLOS — não são turnos reais desta conversa]` e delimitar com `---`. |

## 6. Não-objetivos

- Não trocar modelo automaticamente. A/B de Mistral fica em Fase B.
- Não alterar canon, calendário, memória ou availability.
- Não introduzir novos sinais no planner. Consumimos `tone` que já existe.
- Não escrever documentação para o LLM sobre "seja mais humana". O plano
  parte da hipótese de que instruções abstratas não funcionam.

## 7. Observabilidade

- Log `voice_library.injected examples=N tone=<tone> intent=<intent>`
  em cada chamada.
- Log `voice_library.source=<canonical|biblioteca_comportamental|combined>` para
  distinguir origem.
- Contador do parser da biblioteca: `registros_lidos / registros_boa /
  registros_rejeitados`.

## 8. Rollback

Toda a Fase A é gated por `settings.VOICE_LIBRARY_ENABLED` (default `True`).
`VOICE_LIBRARY_ENABLED=false` no `.env` restaura comportamento atual sem
alteração de código.

---

**Owner:** Patrick + assistant (Claude Opus 4.7)
**Última revisão:** 2026-09-19
