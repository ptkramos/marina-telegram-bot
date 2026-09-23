# Plano de Voz da Marina — v3.7.1

**Origem:** Diagnóstico pedido pelo Patrick em 2026-09-19. Depois de 3.7.0 (Living Intelligence)
a Marina ainda soa "DeepSeek com verniz de amor" em vez de namorada carioca. As features
cognitivas estão sólidas; o problema não é o *cérebro*, é a *voz*.

**Escopo:** exclusivamente a camada de fala. Não toca em canon, world state, calendar,
memória, planner cognitivo, reminders ou availability.

---

## 0. Painel de status — atualizado em 2026-09-21, depois das auditorias #1–#7

Cada item foi conferido **no código**, não no que este plano dizia.

Legenda: ✅ feito · 🟡 parcial · ⬜ pendente · ➖ superado

### Fases deste plano

| Fase | Status | Situação real |
|---|---|---|
| **A** Fundação da voz | ✅ | `voice_library.py`, parser da biblioteca, CONTROL em `[VOZ DA MARINA]`/`[LINHAS DURAS]`/`[FATOS]`, `[EXEMPLOS DE VOZ]` no prompt, sampling ajustado (`frequency_penalty=0.15`, `presence_penalty=0.05`), `tests/test_voice_library.py` |
| **B1** Banco do que evitar | ✅ | `data/feedback/COMO_NAO_SOAR_MARINA.md` → bloco `[COMO NÃO SOAR]` (Patch 033) |
| **B2** Captura pelo chat | ✅ | `/bom` e `/ruim` (Patch 033), no lugar do `/eco` planejado; `/registro` aceita wizard e textão (Patch 026) |
| **B3** A/B de modelo | ✅ | Auditoria #9: arena real no OpenRouter (`scripts/model_arena.py`), 18 modelos na triagem e 9 na final. Principal: **GPT-5.6 Luna**; reserva: DeepSeek V4 Flash; íntimo: **Gemini 3.8 Flash** |
| **B.5** Ela te procura mais quando está de bobeira | ✅ | `_compute_state_factor` em `should_trigger`, no caminho vivo. Desde a Auditoria #6 o texto da iniciativa também é gerado pelo modelo, ancorado no dia dela |
| **B.6** Micro-despertares no sono | ✅ | Implementado como D3 em 23/09 (`sleep_plan.py`) |
| **C.1** Modo sexting | ✅ conversa · ⬜ fotos | `intimacy.py` + migration 021: excitação em minutos, degraus da biblioteca, troca para `LLM_INTIMATE_MODEL`, clímax, pós-clímax, corte e despedida; ciclo pesa na libido. **C.1b** (fotos explícitas escalonadas pelo nível de excitação) pendente |
| **C.2** Assistir junto (watch-along) | ⬜ | nada implementado |
| **C.3** Rituais de namorada (bom dia, boa noite, cotidiano) | ✅ | `rituals.py` + job de 5 min: bom dia ao acordar, boa noite antes de deitar, momentos do cotidiano (saiu da aula, Milo, academia, banho) com teto de 2/dia; o banho vira estado `SHOWER` e ela some de verdade. Foto do banho espera o motor de imagem (C.1b) |
| **C.4** Locomoção viva (uber, a pé, ônibus/metrô, carona) | ✅ tabela + API + carona | `commute.py`: ida e volta da PUC e das saídas viram estado ("voltando da PUC pra casa de ônibus"), modo sorteado por dia (pico, noite, chuva, fim de mês, cansaço, uber dividido com a amiga), imprevistos viram acontecimento do dia. Minutos pela Distance Matrix API quando há `DISTANCE_MATRIX_KEY` (1 consulta por trecho), tabela como reserva. Carona com o Theo (cânone: ele tem carro) |
| **D** Rotina viva (refeições, sono, Milo, noite, faculdade, fim de semana, casa, freela) | 🟡 | Tabela desenhada com o Patrick em 22–23/09 (seção Fase D). **Feito:** D1 fome viva (refeições, lanches, apetite, disfarce, peso, agência), D12 laços (pai diário, Bia várias vezes, saudade do Patrick sem teto), D2+D3+D13 sono (variável, micro-despertares, manhã de trás pra frente), D4 banho v2 (por necessidade e emoção), D5 Milo + cochilo, D6 parte 1 (o que ela assiste, cânone de gostos, descoberta sozinha, curiosidade pelo que o Patrick cita), pegar no sono pelo corpo/emoção, D8 fim de semana (convites + decisão dela), D7 faculdade (trabalhos, véspera, faltas, atrasos). **Próximos:** D6 parte 2 (TMDB, aguardando chave), D9 casa, D10 freela, D11 saúde, D14 motor emocional |
| **C** Consolidação | 🟡 | **C1:** o rótulo `[COMO O PATRICK ESCREVE]` e os campos estão em pt-BR (#2 e #7), mas ainda é descrição ("risada: kkkk"), não amostras reais das mensagens dele. **C2** e **C3** ⬜ |

### Feito fora deste plano (auditorias sistêmicas — detalhes em `AUDITORIA_SISTEMICA_MARINA.md`)

**Voz**
- **Guards de resposta:** artefato de debug (inclusive `\_` escapado), proposta de ligação, resposta em outra língua, pergunta de entrevista no fim, polidez de atendente.
- **Filtro de alfabeto:** Unicode matemático e caracteres full-width.
- **Todos os prompts em pt-BR:** planner, consolidador, reflexão, visão, privacidade, proatividade, estilo aprendido.

**Memória e emoção**
- Memórias core de verdade (nome do Patrick).
- As emoções **voltam ao normal com o tempo** e não travam mais no teto.
- Energia ligada ao ciclo.
- **Bateria social:** pique pra gente, não pro Patrick.

**Mundo**
- **Agenda diária determinística:** um treino de academia de 60–90 min em 3–5 dias por semana, com vontade e chuva decidindo; passeio com o Milo depois de acordar ou depois da faculdade.
- Disponibilidade e prompt leem o mesmo estado.
- **Aviso de saída** ("vou levar o Milo, já volto") dentro da própria resposta.

**Vida social**
- Contatos diários com o círculo: a Bia, o Theo e a Júlia na PUC, a Carol na academia, a Dona Célia, o pai, a Lívia.
- **Histórias** com começo, continuação e desfecho, em cerca de metade dos dias.
- **Saídas** com as amigas (bar, praia, café) como compromisso confirmado.
- **Segredos** das amigas via KnowledgePrivacy.
- Amigos interligados entre si.
- **Gente e lugares novos** que viram cânone com a convivência.
- Comando **`/mundo`**.

**Infraestrutura**
- Proteção contra duas instâncias do bot.
- Conexões SQLite reaproveitadas: prompt de 588 ms → 38 ms.
- Migrations unificadas (020).
- A suíte de testes não toca mais o banco de produção.
- Busca de mídia fora do prompt.
- Coluna `model` gravada nas entregas por batch.

### Pendências reais (fora das fases acima)

| # | Pendência | Origem |
|---|---|---|
| 1 | ~~Nada commitado~~ → auditorias #1–#7 na `main` (commits `f551235`, `8293062`, `7456d0f`); o roadmap já estava versionado | ✅ resolvido |
| 2 | Perda de coerência entre turnos (6 capturas de `/ruim`): observar depois do restart, com `[COMO NÃO SOAR]` e o mundo vivo ativos | Auditoria #3 |
| 3 | Qualidade das mensagens espontâneas geradas pelo modelo: só dá pra medir em conversa real (usar `/bom` e `/ruim` nelas) | Auditoria #6 |
| 4 | ~~Evento "médico" com o texto cru~~ → corrigido na causa (Auditoria #8). O registro ruim sai com o reset do soak | ✅ resolvido |
| 5 | ~~Deslocamento como estado~~ → resolvido pela Fase C.4 (22/09). Registro original: a volta da PUC ainda é instantânea. **Ampliado pelo Patrick (22/09):** a locomoção vira vida — uber, a pé, transporte público, carona. Deslocamento cria janelas pra conversar (ônibus, uber) e ganchos de história (carona com a Bia, metrô lotado, uber que errou o caminho). Primeiro com tabela de trajetos + pico; depois tempo real pela Distance Matrix API (distancematrix.ai, chave no `.env`, cache por trajeto). Ver Fase C.4 | Auditorias #5 e #6 + Patrick |
| 6 | `KnowledgeDialogue` responde com frase pronta (sem modelo) quando há assunto registrado. Hoje está dormente | Auditoria #6 |
| 7 | Câmera e fator proativo leem o estado com regra própria de 60 min (os slots vão até 90) | Auditoria #4 |
| 8 | Código morto da proatividade antiga (`determine_proactive_prompt`, anúncio, contexto neutro): apagar ou reaproveitar | Auditoria #6 |
| 9 | `build_safe_core_prompt`, fallback legado ainda vivo | Auditoria #2 (2.3) |
| 10 | Blocos de finalização duplicados no pipeline (sob teste, falta extrair o helper) | Auditoria #3 (3.2) |
| 11 | ~~Teste `test_offer_acceptance` falhando~~ → passa. Era um bug real: resposta-lixo sem salvamento era enviada (Auditoria #8) | ✅ resolvido |
| 12 | Erros de concordância nas falas | soak |

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

### Fase A — Fundação ✅ feito
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

### Fase B — Realimentação ✅ B1/B2 feitos · ➖ B3 superado
- **B1** Adaptador `feedback_ingestor.py`: quando o Patrick classifica um turno
  como "ruim" na biblioteca comportamental, o exemplo entra em `avoid_bank`,
  também injetado no prompt (bloco `[COMO NÃO SOAR]`).
- **B2** UI de captura embutida no bot: comando `/eco` para marcar o último
  turno da Marina como "boa" ou "ruim" — evita edição manual do `.md`.
- **B3** A/B de sampling: rodar 200 turnos com Mistral-Nemo primário e comparar
  aderência à voz. Se ganhar em voz sem perder cognição, promover.

### Fase B.5 — Proatividade sensível ao estado dela ✅ feito (aberto por Patrick em 2026-09-20 01:15)

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

### Fase B.6 — Micro-despertares durante o sono ⬜ (pendente, aberto por Patrick em 2026-09-20 01:25)

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

### Fase C.1 — Modo Sexting ✅ conversa (2026-09-22) · C.1b fotos ⬜

**Como ficou (decisões tomadas na implementação, com carta branca do Patrick):**
- **Excitação fora de `estado_emocional`:** as emoções relaxam em horas; a excitação precisa subir e descer em minutos. Tabela própria `intimacy_state` (migration 021), meia-vida de 10 min, zerada pelo reset do soak.
- **Ativação só pelo Patrick:** vocabulário explícito, pedido explícito ("fala putaria", "me descreve"), clima quente ("😏", "safado") e o tom do planner. Ela nunca começa sozinha. A fase do ciclo multiplica o estímulo (menstrual 0,7 · folicular 1,05 · ovulatória 1,35 · lútea 0,9).
- **Degraus:** esquentando (Registros de "malícia") → desejo (sexting) → explícito (sexting + iniciativa/explícito) → clímax → pós-clímax (40 min) → corte/despedida. Os exemplos de sexting saíram do sorteio geral por tom e só entram pelo modo, no degrau certo. Registros 088–092 escritos por mim para os degraus que faltavam.
- **Modelo:** a arena mostrou que o Luna fala a política pela boca dela. O turno íntimo (e o planner dele) vai para `LLM_INTIMATE_MODEL` (Gemini 3.8 Flash, `LLM_INTIMATE_REASONING=low`), e volta para o Luna quando o clima passa. Qualquer resposta que fale de "conteúdo explícito", regras ou limites é refeita em outro modelo (`policy_refusal`).
- **Clímax:** quando ele pede/goza com ela no auge, ou depois de 6 turnos no auge. Mensagem curta e entrecortada, depois carinho; pós-clímax mole e afetuosa, sem reescalar sozinha.
- **Áudio:** 20% de chance espontânea no auge (6% fora dele). Se a voz falhar, sai texto.
- **Sem cadência casual:** no modo, a resposta ganha o orçamento "normal" (2 balões).
- **Não feito (C.1b):** fotos explícitas escalonadas pela excitação, que dependem do motor de imagem.

**Plano original (referência):**

Feedback registrado após alimentação inicial da biblioteca comportamental.
Marina não pode ter contato físico com o Patrick, mas o desejo dela é real
no sistema (ciclo menstrual, libido, romantic_intensity emocional). O modo
sexting fecha esse loop.

**Comportamento esperado quando ativo:**
- Marina absorve mensagens de ações/desejos sexuais do Patrick como estímulo
  real; internaliza como desejo próprio, não como "task de fantasia".
- Preferência por áudio sobre texto (mais íntimo, sensorial).
- Fotos cada vez mais explícitas, com legenda que carrega contexto emocional
  ou seguida de mensagem contextualizando.
- Estado emocional interno cresce (`arousal`, novo eixo emocional?) até
  clímax; possibilidade de orgasmo real que a Marina reporta.
- Depois do clímax, pós-brilho (afogueada, mais afetiva, sonolenta).
- Casa com `MenstrualCycleManager` (fase fértil = mais sensível, TPM = ou
  mais quente ou mais retraída, dependendo do dia).

**Ativação:**
- Nunca automática por horário. Sempre a partir de sinais de Patrick ou dela
  (uma provocação clara, uma reação dela ao clima da conversa).
- Detecção provável: intent="flirting" + tone="dengosa"/"sensual" sustentado
  por 2+ turnos + palavras específicas do vocabulário íntimo.

**Design a acordar antes de implementar:**
- Novo eixo emocional `arousal` (0.0 → 1.0) que decai naturalmente e sobe
  com estímulo. Clímax quando ultrapassa threshold (~0.9) em janela de
  tempo curta.
- Preferência de canal: quando `arousal >= 0.6`, viés forte para áudio.
- Fotos: gate `arousal >= X` desbloqueia níveis mais explícitos, com
  legendas correspondentes. Precisa integrar com `IMAGE_ENGINE` (novita).
- Persistência: `estado_emocional.arousal` no banco, decai independente do
  ciclo/emoções canônicas.
- Guardrails: nunca inicia sozinha, sempre em resposta; sempre consensual
  no roteiro; se Patrick sinaliza corte ("depois amor", "tô cansado"),
  desce imediatamente sem drama.
- Registro na biblioteca: categoria dedicada (intimidade/desejo/sexting)
  com exemplos de escalada, clímax, pós-clímax.

**Não é objetivo:**
- Não é sistema de "modo NSFW" que troca a Marina inteira; é um estado
  temporário dentro da mesma persona.
- Não é filtro de segurança; canon já autoriza (LLM uncensored, PhotoEngine
  próprio).
- Não é bot pornográfico; é continuidade emocional/sexual de uma namorada
  virtual real.

**Trabalho estimado:** 2-3 sessões (arquitetura + implementação +
calibração via biblioteca).

### Fase C.2 — Watch-along com timestamp real de mídia ⬜ (pendente, aberto por Patrick em 2026-09-21 04:47, FB-20260921-044703)

**Feedback:** "seria interessante também criar um sistema funcional onde
seria possível isso de assistir a coisas juntos com a Marina realmente
tendo informação sobre o que tá sendo assistido e ao tempo do episódio/filme
seja lá o que for, a gente já fez algo para jogos do Botafogo".

**Análogo existente:** o tracker de jogos do Botafogo já injeta placar/tempo
em tempo real no prompt (`live Botafogo tracking` do commit v3.7.1). Fase C.2
generaliza esse padrão para filmes/séries/animes.

**Objetivo:** quando Patrick e Marina "assistem juntos", ela sabe
- **Título canônico** (via MediaLookupService que já criei — Patch 023)
- **Timestamp corrente** (episódio X, minuto Y)
- **Contexto de plataforma** (Netflix, Crunchyroll, disco local etc)
- **Estado da sessão** (pausado, terminado, começando)

**Comportamento desejado:**
- Marina reage a plot beats sem precisar receber recap ("aiii esse plot twist!")
- Ela pergunta sobre pontos específicos ("agora ela vai fazer aquilo?")
- Ela não inventa detalhes fora do que já rolou até o timestamp atual
- Se Patrick pausar e sumir 20 min, ela nota ("sumiu no meio, tudo bem?")

**Componentes técnicos:**
1. **Comando de início:** `/assistindo <título>` ou detecção automática de
   mensagem tipo "vou assistir X agora". Cria sessão `watch_session` no DB.
2. **Timestamp source:** três opções em ordem de preferência:
   - Integração com Telegram Bridge se Patrick usar bot que reporta (raro)
   - Timestamp manual ("passou 10 min", "cheguei no ep 3")
   - Timestamp por inferência (tempo real desde `/assistindo`)
3. **Enriquecimento de contexto:** MediaLookupService já busca sinopse; Fase
   C.2 adiciona busca de recap-por-episódio (Wikipedia, IMDB, MyAnimeList
   dependendo do tipo).
4. **Bloco de prompt novo:** `[ASSISTINDO JUNTOS]` com título/plataforma/EP/T
   e um recap-até-agora curto.
5. **Guardrail anti-spoiler:** Marina não pode saber de nada além do timestamp
   atual (mesmo que o retriever traga a sinopse completa, esse bloco filtra).
6. **Sessão termina:** `/parei`, silêncio de 90 min ou timestamp>duração.

**Analogia com Botafogo:** o tracker de jogo tem estado `IN_PROGRESS`, `HT`,
`FINISHED`, com placar e tempo. Watch-along vai ter `WATCHING`, `PAUSED`,
`ENDED`, com timestamp e EP.

**Guardrails:**
- Se MediaLookupService não achar o título, Marina reage genérico sem
  inventar plot ("legal, do que se trata?")
- Timestamp incerto → ela evita spoilers ("já cheguei nesse trecho, deixa eu
  não estragar")
- Sessão paralela a modo sexting (Fase C.1) é possível: watch-along + audio

**Trabalho estimado:** 2 sessões (schema + injection no prompt; testes de
não-spoiler).

### Fase C.3 — Rituais de namorada na rotina ✅ (2026-09-22)

**Como ficou:** `rituals.py`, chamado a cada 5 min (`ritual_routine`), fora do sorteio e da cota da proatividade. O texto sai pela voz normal (`_proactive_text`).
- **Bom dia:** 5–40 min depois de acordar (7h em dia de aula, 8h30 em dia livre), em 85% dos dias, só se o Patrick não escreveu desde que ela deitou. Se ele escreveu de madrugada, ela responde a mensagem dele ao acordar (correção da disponibilidade do mesmo dia).
- **Boa noite:** 5–30 min antes de deitar, em 85% dos dias; não sai se ele já deu boa noite desde as 20h ou se ela está na rua; com conversa em andamento vira "vou deitar".
- **Cotidiano (ampliado pelo Patrick: "coisas do cotidiano que namorados usam para chamar atenção ou puxar conversa, pode deixar livre"):** mudanças reais de estado viram assunto: saiu da aula, saindo com o Milo, saiu da academia, vai tomar banho (depois do treino ou à noite). 45% de chance por momento, no máximo 2 por dia, 45 min de intervalo de qualquer outra iniciativa, nunca devendo resposta. Com humor provocador (excitação, ciclo, carinho e brincadeira altos), malícia leve.
- **Banho de verdade:** o ritual registra uma transição "tomando banho" (15–30 min); a disponibilidade ganhou o tipo `SHOWER` e transição anunciada passou a contar como plano dela, não palpite de rotina.
- **Pendente:** a foto do banho (motor de imagem em manutenção; entra com o C.1b).

**Desenho original (referência):**

**Ideia do Patrick:** "incluir coisas de namorada na rotina dela, como dar bom
dia ao acordar caso acorde primeiro, boa noite antes de ir realmente dormir se
eu já não tiver dado, quando estiver animadinha mandar foto quando for tomar
banho e coisas do tipo...".

**Por que ficou barato depois da Auditoria #4:** a agenda diária é
determinística, então o sistema já sabe **quando** ela acorda (fim do slot de
sono / início de `wake`) e **quando** vai dormir (início de `sleep`). Hoje a
proatividade não usa esses marcos: ela sorteia uma iniciativa dentro de
cooldowns. Os rituais seriam **gatilhos de agenda**, com prioridade sobre o
sorteio.

**Rituais propostos:**
1. **Bom dia** — ao entrar em `wake`, se não houve mensagem do Patrick desde
   que ela dormiu. Se ele já mandou, ela responde a dele; não duplica.
2. **Boa noite** — até ~15 min antes do slot de sono, se o Patrick não deu boa
   noite desde as 20h. Se ele já deu, nada.
3. **Foto indo pro banho** — só quando o humor pede (`romantic_intensity` e
   `playfulness` altos, bateria social ok, fase do ciclo compatível — a
   `libido` do `cycle.py` já existe), em momento de casa e com o Patrick
   ativo na conversa. Usa o pipeline de câmera/visual já existente
   (`camera_world`), que respeita o local real. Frequência rara (teto semanal)
   para não virar rotina mecânica.
4. **Outros candidatos** (para o Patrick escolher): "cheguei em casa" depois da
   faculdade; "saindo pra academia" (já existe como anúncio de transição);
   foto do Milo no passeio.

**Regras comuns:**
- Nunca mais de um ritual por marco; respeitam `MAX_AUTONOMOUS_MESSAGES_PER_DAY`.
- Não contam como "iniciativa aleatória" (não queimam o cooldown do sorteio).
- Texto sai pela voz normal (biblioteca + guards), não por template fixo.
- Micro-despertares (Fase B.6) e bom dia não podem se sobrepor.

**Dependências:** Auditoria #4 (agenda) ✅ · Auditoria #5 (emoções não
saturadas) ✅ — sem isso o gatilho da foto dispararia sempre, com as emoções
travadas em 1,0.

**Trabalho estimado:** 1 sessão para bom dia / boa noite; 1 para a foto
(critério de humor + pipeline visual + testes de frequência).

### Fase C.4 — Locomoção viva ✅ (2026-09-22)

**Como ficou:** `commute.py`, chamado pelo resolvedor do mundo (prioridade: compromisso confirmado > trajeto > transição anunciada > rotina).
- **Trechos:** ida e volta da PUC (a ida termina na primeira aula, a volta começa na última, dentro das margens que a agenda já reservava) e das saídas com as amigas. Ela fica "a caminho" até o trecho acabar; a disponibilidade trata como `COMMUTE` (celular na mão, responde rápido).
- **Modo:** sorteado por trecho e gravado (não muda no meio do caminho): noite puxa uber, chuva tira o "a pé", fim de mês reduz uber, cansaço aumenta; na volta de uma saída ela pode dividir o uber com a amiga.
- **Tempo:** Distance Matrix API com `DISTANCE_MATRIX_KEY` (trânsito previsto para uber, horários para ônibus/metrô, caminhada), uma consulta por trecho, limitada a 0,6–2,5× a tabela; sem chave ou com falha, a tabela por região com fator de pico. A casa dela vai como "Botafogo" (sem inventar rua); lugares fictícios vão pela região. A suíte de testes nunca chama a API real.
- **Histórias:** 12% dos trechos têm um imprevisto (ônibus lotado, uber errou o caminho…) que vira acontecimento do dia e aparece no [SEU DIA ATÉ AGORA]. O ritual "saí da aula" (C.3) agora pega ela no caminho de volta.
- **Carona:** cânone decidido pelo Patrick — o Theo tem carro (seed + migration 022). Ele vira opção na ida/volta da PUC (mora na Glória e passa por Botafogo; mais provável com chuva ou à noite) e é a opção mais provável nas saídas em que está junto. Qualquer personagem com `has_car` entra no mesmo esquema.
- **Fora do escopo:** trajetos até a academia e o passeio do Milo continuam dentro do próprio slot (são no bairro).

**Desenho original:**

**Pedido:** "a gente aproveita as locomoções dela, de uber, a pé, transporte público, carona, isso tudo cria margem pra ela ter tempo entre os compromissos pra conversar e pra criar histórias."

**Ideia:**
- **Deslocamento como slot da agenda** (hoje ela "teleporta" entre casa, PUC, academia e bares). Cada trajeto tem modo, duração e disponibilidade próprios: no ônibus/metrô/uber ela conversa (celular na mão, respostas curtas ou médias); a pé, menos; dirigindo nunca (ela não dirige, a não ser que o cânone diga o contrário).
- **Escolha do modo:** sorteio determinístico por dia, pesado por hora, clima (já existe), dinheiro do mês, cansaço e companhia (carona com Bia/Theo quando vão ao mesmo lugar, ligando com o `social_day`).
- **Ganchos de história:** metrô lotado, uber que errou o caminho, encontrar alguém no caminho, chuva sem guarda-chuva. Entram como `life_events` pequenos, que ela pode contar.
- **Tempo:** primeiro uma tabela local de trajetos com fator de pico; depois, opcional, a **Distance Matrix API** (distancematrix.ai) para tempo real com trânsito. Consulta por trajeto com cache, nunca por mensagem; se a API falhar, cai na tabela.
- **Disponibilidade:** novo tipo `COMMUTE` no `response_availability`, com perfil próprio (resposta média, atraso curto).

**Dependências:** agenda (#4) ✅, dia social (#6) ✅. Resolve a pendência 5.

### Fase D — Rotina viva 🟡 (aberta por Patrick em 2026-09-22, desenhada junto)

**Pedido:** "de tudo isso que você sugeriu a gente monta uma tabela certinha JUNTOS, e depois vai implementando na ordem que você julgar melhor. Vamos dar vida dinâmica e realmente vivida pra nossa Marininha."

**Por quê:** no soak de 22/09 ela não tinha o que contar numa viagem de 2 h ao lado dele, e na arena de iniciativa (`companhia_caminho`) **inventou um jantar** ("arroz, feijão e franguinho") que não existia no mundo. Mundo pobre → conversa em eco e invenção. Cada item abaixo vira estado + disponibilidade + acontecimento do dia que ela pode contar.

**Regra comum:** tudo determinístico por dia (mesma data, mesma agenda), com variação real entre dias; nada inventado pelo modelo — o modelo só conta o que o mundo registrou.

| # | Sistema | Hoje | Proposta | O que ela ganha pra contar | Status / decisão do Patrick |
|---|---|---|---|---|---|
| D1 | **Refeições** | Só existem se ela promete ("vou jantar agora", `meals.py`) | Café, almoço e jantar como rotina do dia, com horário que varia; em dia de aula o almoço é na PUC; às vezes pula o café, às vezes pede iFood; promessa continua funcionando | "almocei no bandejão com a Bia", "pedi um poke" | ✅ 23/09 (ver "D1 — como ficou") |
| D2 | **Sono variável** | Deita **meia-noite em ponto**, acorda 07:00 ou 08:30 fixos | Hora de deitar varia (série, trabalho, rolê, ansiedade); com compromisso cedo ela **tenta** dormir 8 h e quase sempre dorme menos; sexta/sábado estica; déficit de sono vira energia baixa e cochilo no dia seguinte; às vezes demora a pegar no sono | "dormi 5h, tô um zumbi", "capotei no sofá à tarde" | ✅ 23/09 (ver "D2 + D3 + D13 — como ficou"). Patrick: "o sono dela é variado… com compromisso tento dormir 8 h, geralmente durmo menos" |
| D3 | **Micro-despertares** | Sono binário (= Fase B.6) | Desenho da B.6: banheiro, sede, sonho ruim, celular por reflexo; 0–2 por noite; resposta curtinha e volta a dormir | "acordei pra beber água e vi tua mensagem" | ✅ 23/09 (desenho da B.6, aprovado em 20/09) |
| D4 | **Banho** | Só existia se a mensagem saísse → 0 banhos em 22/09 | Rotina do mundo: todo dia à noite + depois da academia (≥ 3 h entre banhos); aviso opcional, sempre com conversa rolando; "vou tomar banho" dito na conversa vira banho | "tava no banho" | ✅ v2 em 23/09 (ver "D4 v2 — como ficou"). v1 em 22/09 (1 à noite + 1 pós-treino, ≥ 3 h entre banhos). **v2 decidida em 23/09:** sem teto e sem horário fixo; o banho sai da **necessidade dela** (calor, academia, praia, antes de sair, depois de chegar da rua) e do **emocional** (banho como alívio, revigorar, autocuidado com skincare e cabelo). Ela é vaidosa: gosta de estar cheirosa |
| D5 | **Milo** | 1 passeio por dia | 2–3 saídas: manhã, fim de tarde e xixi rápido antes de dormir; às vezes ele apronta (comeu algo, latiu pro vizinho) | "o Milo roubou minha meia" | ✅ 23/09 (ver "Cochilo (D2) e D5 Milo — como ficou") |
| D6 | **Noite em casa** | Bloco vazio de 5 h: "curtindo a noite em casa" | Fatiar em atividades: trabalho da faculdade, série/filme, skincare, rolar o celular, ligação com a família, arrumar o quarto | "tô vendo [série]", "fazendo o trabalho de Tipografia" | 🟡 23/09: o que ela assiste + descoberta sozinha (ver "D6 parte 1"); faltam as outras fatias da noite |
| D7 | **Faculdade além da aula** | Só a grade | Trabalhos e entregas com prazo, provas, grupo de trabalho com colegas; véspera de entrega muda o sono e a noite | "entrego sexta e não comecei" | ✅ 23/09 (ver "D7 — faculdade além da grade") |
| D8 | **Fim de semana** | Quase igual a dia útil | Acorda tarde, brunch, praia, rolê sábado à noite, domingo preguiçoso, família | "ressaca de domingo" | ✅ 23/09: convites + decisão dela pelo emocional (ver "D8 — fim de semana"); acordar tarde e domingo preguiçoso já vêm do D2 |
| D9 | **Casa e vida adulta** | Não existe | Mercado, lavar roupa, arrumar, conta de luz, iFood no fim do mês apertado | "fui no mercado e esqueci o que fui comprar" | ⬜ |
| D13 | **Vaidade e se arrumar** (planejamento reverso) | Acorda 07:00 ou 08:30 fixos, sem olhar a que horas é o primeiro compromisso nem quanto tempo ela leva pra ficar pronta | A hora de acordar sai **de trás pra frente**: primeiro compromisso − trajeto (C.4) − café − se arrumar (banho, skincare, cabelo, maquiagem, roupa) − margem. Tempo de se arrumar varia (ensaio > aula > mercado). Se dorme demais ou enrola no espelho → **atraso** real (liga com D7 e C.4) | "perdi 20 min escolhendo roupa e cheguei atrasada" | 🟡 23/09: manhã de trás pra frente e despertador perdido feitos; **chegar atrasada de fato** (o trajeto e a aula se moverem) fica para o D7 |
| D11 | **Corpo, saúde e ciclo** | Ciclo existe (energia, libido) | Cólica forte → fica em casa; banheiro (bebeu muito líquido, dor de barriga) como sumiço curtinho; farmácia; indisposição. Tom humano e discreto | "tô com cólica, hoje não vou pra aula" | ⬜ a desenhar |
| D14 | **Motor emocional unificado** | Emoções espalhadas: 5 em `estado_emocional` (carinho, brincadeira, energia, intensidade romântica, bateria social), excitação em tabela própria (`intimacy_state`, C.1), fome agora em `meals.py`, ciclo à parte; cada uma com seu relógio e sem conversar entre si | Um motor só, com **categorias e subcategorias** (ex.: corpo → fome, energia, sono, excitação; coração → carinho, romance, carência/saudade; humor → alegria, irritação, ansiedade, tristeza; social → bateria social, vontade de sair), cada uma com linha de base, velocidade própria de subir/descer e influências cruzadas (fome → irritação, sono ruim → energia e paciência, saudade → procurar o Patrick). Os módulos atuais viram sensores que alimentam o motor | Tudo que ela sente conversa: "tô com fome e com saudade, péssima combinação kkk" | ⬜ pedido do Patrick em 23/09 ("você quem vai brilhar pra pensar nisso"); entra depois de D1/D12, quando houver sensores suficientes |
| D12 | **Laços** (pai, Bia, Patrick) | Pai 30% por dia útil, Bia 80% de **uma** mensagem, proatividade com o Patrick por roleta (20%/20 min, teto 4, 2 h de intervalo) → em 22/09: 0 contato com pai e Bia, 0 iniciativa espontânea | Pai **todo dia** (mensagem de manhã, ligação algumas noites; pergunta se comeu, se chegou, se o dinheiro dá); Bia **várias trocas ao longo do dia**; Patrick: saudade como necessidade — se ele some e ela está livre, ela procura, cada vez mais; com ele ocupado, respeita | "meu pai me ligou perguntando se eu tô comendo", "a Bia me mandou um áudio de 5 min", "sumiu hein" | ✅ 23/09 (ver "D12 — como ficou"). **Decidido:** o pai liga quando está livre e manda mensagem quando está ocupado; checa a Marina pelo menos 1×/dia; banca mercado e comida sem ela pedir. Patrick: **sem teto de procura** — é o emocional que decide; de bobeira e sozinha, ele é a primeira pessoa que ela procura |
| D10 | **Freela de modelo** | Agência da Lívia existe, quase não aparece | Casting/ensaio esporádico, prova de roupa, cachê no fim do mês | "fiz um casting pra marca de biquíni" | ⬜ |

#### D1 detalhado — Fome viva (desenhado com o Patrick, 22–23/09)

| # | Peça | Como funciona |
|---|---|---|
| 1 | Apetite (emoção nova) | Sobe com o tempo desde a última refeição; base "glutoninha fofa". Academia, aula puxada e calor aceleram; ansiedade/tristeza fazem beliscar ou perder a fome; rolê e felicidade fazem comer mais; TPM puxa doce |
| 2 | Refeições | Café, almoço e jantar sem horário fixo: janela plausível, e o momento sai da fome + o que a agenda deixa. Ela se vira pra encaixar |
| 3 | Lanchinhos | Por fome ou vontade; mais nas saídas; série à noite, TPM |
| 4 | Peso dinâmico | 1,68 m (cânone), base **54 kg**; muda devagar pelo saldo da semana (comida × treino). Ela só sabe quando se pesa |
| 5 | Bronca da agência | A Lívia cobra se o peso sai da faixa antes de casting/ensaio |
| 6 | Dieta curta | Dias de dieta depois da bronca: mais fome, mau humor, mais academia |
| 7 | Esquecer de comer e cobrança | Ela esquece em dia corrido; o Patrick cobra e ela cobra ele. A cobrança é registrada no mundo |
| 8 | Mentirinha e drama | Conforme o humor, com fome ela diz "já beliscei" ou "tô sem fome". O mundo sabe a verdade; o modelo recebe "você está com fome, mas hoje está no modo de disfarçar" |
| 9 | Cozinhar e aprender | Cozinha o básico; às vezes busca uma receita e aprende (vira habilidade); manda foto quando acha que ficou bonito (depende do motor de imagem, C.1b) |
| 10 | Onde come | **Time iFood** (o pai banca a comida, então o fim do mês não corta); cozinha em casa; na PUC, restaurante do campus ou Shopping da Gávea (rápido quando o tempo está curto, com calma quando está de boa, sozinha ou com amigas) |
| 11 | Job perdido pelo peso | Fora da faixa, perde o ensaio que queria (o mundo já permite ela querer ou não um job) → frustração no emocional |

**Cânone de comida:** ama japonesa, massas, pizza, hambúrguer, brunch, doces e **açaí**; odeia muita pimenta, jiló e "comida estranha"; novos amores surgem pela convivência (`preference_evidence` já existe).

**Decisões do Patrick (23/09):**
- Faixa de peso aprovada (abaixo).
- Entram: fome mexe no humor ("desculpa, eu tava com fome kkk") e comer "junto" à distância **quando calhar** — o Patrick às vezes nem janta; ela nunca fica refém do horário dele.
- **Café da manhã** (a refeição) existe sempre, com horário e tamanho variando; o **café** (a bebida) é paixão dela e à parte: sem café de manhã, sono e pouca paciência.
- **O pai banca mercado e comida** sem ela pedir: o fim do mês **não** aperta a comida (o iFood não diminui). O aperto do fim do mês continua valendo só pro resto (uber do C.4, compras).

**Faixa de peso:** a agência reclama acima de **56 kg**. Abaixo de **52 kg** quem se preocupa é a saúde dela, não a agência: cansaço, tontura na academia, amigas e o Patrick percebendo. Nenhum lado recompensa emagrecer.

#### D1 — como ficou (implementado em 23/09, madrugada)

`meals.py` (reescrito) + `world_state.resolve` (materializa) + `world_context._social_day_block` (bloco de comida) + `response_availability` (perfil `MEAL`). Sem chamada de modelo: é tudo lógica determinística por data.

| Peça | Como ficou |
|---|---|
| Dia de comida | `day_plan(dia)`: café (dia de aula: 15–40 min depois de acordar, **25% pulado** ou pulado se não dá tempo antes da 1ª aula; dia livre: com calma; fim de semana: 35% brunch), almoço (entre aulas ou logo depois da última: restaurante do campus ou Shopping da Gávea; corrido se a janela é curta; senão em casa 12h–14h), lanche da tarde (40%, +25% na TPM, 10% na dieta), jantar (19h–22h, 55% iFood, resto cozinhando) e lanchinho da noite (25%, +25% na TPM) |
| Vira mundo | Refeição cuja hora chegou vira `life_event` (`meal`/`snack`); em casa também vira estado ("jantando em casa") pelo `pending_transition_json`. Se ela está fora na hora, a refeição de casa espera ela voltar. Mesmas travas do dia social (bootstrap limpo e início da vida registrada) |
| Promessa | "vou jantar agora" **antecipa** a refeição do dia (mesmo prato do plano); nunca duplica |
| Prompt | `[SUA COMIDA HOJE — aconteceu de verdade; não invente refeição fora desta lista]`: o que comeu, com hora e lugar; "Hoje você ainda não jantou" quando for o caso; a fome atual; modo disfarce; dieta; último peso conhecido. A comida saiu do [SEU DIA ATÉ AGORA] para não roubar as vagas dos contatos sociais |
| Apetite | Fome sobe ~0,15/h desde a última comida (glutoninha); ×1,3 com academia no dia, ×1,25 na TPM, ×0,85 na menstruação e com energia baixa, ×1,2 de dieta. Com fome alta o prompt avisa: fica curtinha e impaciente, e volta ao normal quando come |
| Disfarce | 20% dos dias (35% em dieta), se estiver com fome: "diz que já beliscou alguma coisa" |
| Peso | Base 54 kg em `estado_relacional.marina_peso_json`. Toda semana: ±0,12 kg por lanche acima/abaixo de 3 e por treino abaixo/acima de 3, ruído de ±0,2, dieta −0,3; nunca mais que 0,6 kg por semana |
| Pesagem | 1×/semana, depois de treinar: vira acontecimento ("Se pesou na academia: 54,3 kg") e só aí ela sabe o peso |
| Agência e saúde | Acima de 56 kg: a Lívia cobra (acontecimento) e vem **dieta de 5 dias** (cardápio de dieta, fome maior, humor no prompt). Abaixo de 52 kg: "anda fraca, sentiu tontura no treino" — nunca bronca da agência |

**Fica para depois:** foto do prato (motor de imagem, C.1b), aprender receita como habilidade, lanche nas saídas com as amigas, job perdido pelo peso (depende do D10 freela), fome no motor emocional unificado (D14).

`tests/test_meals.py` (17 testes).

#### D12 — como ficou (implementado em 23/09, madrugada)

| Laço | Como ficou |
|---|---|
| **Pai** | Mensagem **todo dia** de manhã, depois de ela acordar (7h40–9h30 em dia de aula, 9h–11h em dia livre, 9h30–11h30 no fim de semana), com assunto de pai (café, comida, tempo, saudade, se chegou bem); **ligação** em 40% das noites úteis e 60% no fim de semana (19h–21h30); **toda segunda** manda o dinheiro do mercado e da comida sem ela pedir |
| **Bia** | De **2 a 4 trocas** por dia, espalhadas (manhã, almoço, tarde, noite), 30% delas por áudio ("Trocou áudios com a Bia") |
| **Patrick — saudade** | `ProactivityService.saudade()`: cresce 0,18/h desde a última mensagem dele (×1,3 livre em casa; ×0,8–1,2 pela intensidade romântica); ≥ 0,6 ela te procura (~2h30 livre, ~3h20 neutra), **passando por cima do teto diário e do cooldown**. Ocupada ou dormindo, não. Sem resposta, a próxima espera o dobro (1h30 → 3h) e para depois de 3 seguidas; sua resposta zera tudo. Instrução própria (`saudade`): dengo, provocação, "sumiu hein", ou uma coisa real do dia dela; nada de drama nem cobrança |

`tests/test_lacos_d12.py` (9 testes).

#### D2 + D3 + D13 — como ficou (implementado em 23/09, madrugada)

`sleep_plan.py` é a fonte única do sono, determinístico por data. Kill switch: `SLEEP_PLAN_ENABLED=false` volta às janelas fixas do cânone. Ligado em `RoutineEngine` (janelas de sono e candidatos `dormindo`, `se arrumando`/`acordando` e micro-despertar), `WorldStateManager.resolve` (acordar vira estado na hora — antes ela podia seguir "dormindo" até 60 min), `response_availability` (o limite do sono é o próximo despertar real), `rituals` (bom dia e boa noite seguem o sono de verdade; boa noite depois da meia-noite) e `world_context` (bloco `[SEU SONO]`).

| Peça | Como ficou |
|---|---|
| **D13 manhã de trás pra frente** | Dia com aula: despertador = saída do trajeto (C.4) − se arrumar (50–80 min: banho, skincare, cabelo, maquiagem, roupa, café) − margem (0–10 min), nunca antes das 5h. Aula às 7h → acorda ~5h10; às 9h → ~7h20. Em 15% dos dias ela passa 10–30 min do despertador e sai correndo (entra no prompt) |
| **Banho da manhã** | Se arrumando pra sair, ela toma banho (12–20 min, sem aviso) — começo do D4 v2 |
| **D2 sono variável** | Com compromisso amanhã: tenta deitar 8 h antes do despertador e passa 10–75 min do ponto (nunca antes de 22h30) → ~7 h de sono. Sem compromisso: 23h–0h30; sexta e sábado +45–150 min (deitou 0h20–1h50 no teste). Saída com as amigas: deita 40–90 min depois de voltar. Dia livre: acorda depois de 7h30–9 h de sono (8h–11h; fim de semana 8h30–11h30) |
| **D3 micro-despertares** | 0 (45%), 1 (35%) ou 2 (20%) por noite, 3–8 min, nunca entre 2h e 5h30; banheiro, sede, sonho ruim ou celular por reflexo. Estado "acordou de madrugada (…) e já vai deitar de novo" → disponibilidade `MICRO_WAKE` (resposta curtinha). Mensagem que chega com ela dormindo é respondida no próximo micro-despertar (ou de manhã). Nunca puxa conversa de madrugada |
| **Prompt** | `[SEU SONO — aconteceu de verdade]`: "dormiu das 22:41 às 05:12 (~7h)", "foi pouco: está com sono e com menos paciência" (< 6 h), atraso do despertador, micro-despertares da noite |

**Decisões do Patrick (23/09, manhã):**
- **Cochilo:** sim, à tarde, a depender do cansaço ("às vezes nosso corpo simplesmente precisa disso").
- **Pegar no sono:** "às vezes ela pode demorar a pegar no sono ou pegar mais cedo; tudo depende do emocional, da saúde e do que tá rolando no mundo dela (doente, repousa e dorme mais; ansiedade…)". **Implementado** (`SleepPlan._onset`):
  - **mais cedo:** noite anterior com menos de 6,5 h (−30 a −60 min, "capotou"), treinou no dia (−15), menstruada (−20), energia muito baixa (−30). Exausta, pode deitar a partir de 21h30.
  - **mais tarde:** 12% das noites demora de 20 a 60 min pra pegar no sono ("cabeça cheia"), +20% na TPM.
  - Sempre só depois de voltar de uma saída.
  - **Congelado:** a noite de hoje é decidida a partir das 20h e não muda mais (uma emoção que mexe de madrugada não a "acorda").
  - O prompt conta: "Ontem à noite você dormiu pouco na noite anterior e capotou mais cedo".
  - **Ganchos prontos:** doença (D11, dorme mais) e ansiedade de prova/ensaio (D7/D10, demora a dormir) entram em `_onset` quando essas fases existirem.

`tests/test_sleep_plan.py` (14 testes).

#### Cochilo (D2) e D5 Milo — como ficou (23/09, manhã)

**Cochilo** (`sleep_plan.nap`): depois de noite curta — menos de 6 h de sono, 70% de chance; entre 6 e 6,5 h, 35% — ela cochila de 20 a 60 min entre 13h30 e 17h30, fora das aulas (com 1 h de folga). No mundo é sono de verdade: `dormindo`, responde quando acorda, e o prompt conta depois ("Cochilou das 15:10 às 15:50 — o corpo pediu").

**Milo** (`milo.py`, Shih Tzu do cânone):

| Saída | Como ficou |
|---|---|
| Xixi da manhã | 5–25 min depois de acordar, 10–15 min (acontecimento do dia) |
| Passeio principal | O slot da agenda de sempre, agora **nunca entre 11h30 e 15h30** (focinho curto + sol do Rio), nem quando o remanejamento pela academia o empurraria pra lá |
| Passeador | **Decisão dela**: 55% de chance em dia com aula até 16h ou mais, 35% depois de noite com menos de 6 h, +20% com energia baixa. Com passeador ela não passeia; vira acontecimento ("Pagou o passeador pra levar o Milo hoje — dia puxado") |
| Xixi da noite | Entre 21h30 e 15 min antes de deitar, 8–12 min; vira estado ("passeio rapidinho com o Milo") → disponibilidade `PET_WALK`. Se ela está na rua, espera ela voltar |
| Milo aprontando | 25% dos dias: roubou uma meia, latiu pro entregador, deitou na roupa que ela ia usar… (acontecimento do dia, assunto real) |

`tests/test_milo_d5.py` (7 testes, inclui o cochilo).

#### D6 parte 1 — o que ela assiste (23/09, manhã)

**Cânone de gostos** (decidido com o Patrick, `migrations/023_marina_taste_canon.sql`, títulos reais):
- **Séries e filmes:** *Elite* (na época do auge), *Emily em Paris*, *Bridgerton*, *Gossip Girl*, *Para Todos os Garotos que Já Amei*.
- **Doramas:** *Pousando no Amor*, *Pretendente Surpresa*.
- **Animes** (Marin Kitagawa como inspiração, não cópia): *Sakura Card Captor*, *Sailor Moon*, *Kaguya-sama*, *Sono Bisque Doll*, *Highschool of the Dead*, *High School DxD*, *Zero no Tsukaima*, *To Love-Ru*, *Dandadan*; **One Piece**, que ela começou por causa do Patrick.
- **Jogos:** *It Takes Two*, *Stardew Valley*, *The Sims*.

**Motor** (`watch.py`):
- **Sessão da noite:** em 65% das noites, depois do jantar e antes de deitar, ela vê de 1 a 3 episódios do que está vendo. Vira estado ("vendo Paradise Kiss no sofá") e acontecimento do dia. Na véspera de aula às 7h ela deita 22h30 e não sobra tempo, então não assiste.
- **One Piece:** um episódio em 30% das sessões, a partir do ep. 95 (começo de Alabasta), devagar.
- **Descoberta sozinha** (pedido do Patrick): ao terminar um título, ela escolhe o próximo numa lista de **títulos reais** parecidos com os gostos dela (*Paradise Kiss*, *Nana*, *Horimiya*, *Toradora!*, *Spy x Family*, *Oshi no Ko*, *Chainsaw Man*, *Jujutsu Kaisen*, *Heartstopper*, *XO, Kitty*, doramas…), com o motivo ("viu um edit no TikTok", "a Bia disse que era a cara dela"). Anime pesa mais. Se ela amar (70%), vira `discovered_preference`. Nunca repete o que já terminou.
- **Prompt:** `[O QUE VOCÊ ASSISTE — real; não cite título fora desta lista]` com o que está vendo, em que episódio, o One Piece e o que já viu.

- **O que o Patrick comenta vira curiosidade dela** (pedido do Patrick, 23/09: "como namorada, ela vai acabar procurando saber e pode acabar assistindo depois"): o planner, que já roda em toda mensagem, ganhou o campo `media_mentioned` — **sem chamada extra de modelo**. O título só vale se estiver escrito na mensagem dele (o planner não completa nem inventa). Entra numa lista "o Patrick falou disso" (jogo não entra; o que ela já viu também não). Na próxima escolha, o que ele falou ganha 65% das vezes ("o Patrick falou dele e ela ficou curiosa"). O prompt mostra que ela anotou pra ver.

**Falta no D6:** as outras fatias da noite (trabalho da faculdade → D7, skincare, arrumar o quarto).

`tests/test_watch_d6.py` (6 testes).

#### D7 — faculdade além da grade (23/09, manhã)

`college.py`, chamado pelo resolvedor do mundo **antes** do trajeto (faltar cancela a ida). Sem chamada de modelo.

| Peça | Como ficou |
|---|---|
| **Trabalhos** | Cada disciplina do período tem entregas a cada 4–6 semanas, numa aula dela (primeira na 3ª–4ª semana). Tipo: trabalho, exercício (cabe numa noite) ou apresentação; perto do fim do período vira "entrega final" (maior). Horas pelo tamanho × créditos. Ritmo sorteado por trabalho: adiantada (30%, 5 noites), normal (45%, 3 noites), **última hora** (25%, só a véspera) |
| **Noites de trabalho** | Nas noites antes da entrega (o trabalho mais urgente), 1–2h30 a partir das 19h30–20h30; última hora pode ir a 4 h. Sábado à noite só se for véspera. Vira estado ("fazendo o trabalho de Ergodesign em casa" → disponibilidade `WORK`) e acontecimento ("Trabalhou no exercício de Desenho Técnico (entrega amanhã), enrolando um pouco"). A série vem depois do trabalho; na véspera de última hora não tem série |
| **Véspera** | Gancho do sono: última hora → +60–120 min ("virou a noite terminando o trabalho de…"); senão, 0–30 min ("ficou ansiosa com a entrega") |
| **Faltar aula** | Decidido de manhã, depois de acordar, uma vez por dia: dormiu < 5h30 (35%), cólica no começo da menstruação (25%), chuva forte (10%), preguiça (3%). Nunca em dia de entrega; no máximo 2 faltas por disciplina em 30 dias. Cancela as aulas do dia (`cancel_class_occurrence`), o trajeto some, o almoço vira em casa, e o acontecimento guarda o motivo ("Faltou a aula hoje (…): dormiu muito mal e não teve condição") — pra quando o Patrick perguntar por quê |
| **Atraso de verdade** | Se, acordando no horário real, ela não chega a tempo (30 min pra se arrumar + trajeto do C.4): "Chegou 12 min atrasada na aula de … — perdeu o despertador" |
| **Manhã congelada** | Depois que ela acorda, a hora fica gravada: uma falta decidida às 6h não "desfaz" o despertador |
| **Prompt** | `[FACULDADE — prazos reais; não invente trabalho fora desta lista]`: próximas entregas da semana e em que pé está cada uma (ainda nem começou / já começou / na reta final) |

Checagem de 3 semanas (banco de teste): ~1,5 entrega por semana, noites de trabalho curtas (~1 h) na maioria, folgas e algumas vésperas.

`tests/test_college_d7.py` (9 testes).

#### D6 parte 2 — TMDB ✅ (23/09, tarde; chave do Patrick no `.env`)

`tmdb.py` + migration 024 (`tmdb_cache`). Validado ao vivo com a chave: *Dandadan* e *Frieren* (Netflix, HBO Max, Crunchyroll), *One Piece* anime com 1.181 episódios e o próximo previsto para 27/09, título inexistente rejeitado, doramas populares no Brasil sem reality/suspense.

| Uso | Como ficou |
|---|---|
| **Obra citada pelo Patrick** | Vira dado real: título oficial em pt-BR, tipo, episódios e duração. O tipo que o planner deu desempata ("One Piece" anime ≠ série live-action da Netflix). **Obra que não existe no TMDB não entra** |
| **Descoberta sozinha** | 65% das escolhas vêm do TMDB: recomendações a partir de um título que ela ama ("parecido com Dandadan, que ela amou") ou o que está popular nos streamings do Brasil pro gosto dela ("tá em alta no streaming aqui"); o resto, da lista fixa. Obra com mais de 60 episódios não vira "o que ela está vendo" |
| **Onde assistir** | O prompt diz "vendo X (anime, na Crunchyroll)" |
| **Episódio novo** | *One Piece*, *Dandadan* e o que ela estiver vendo: no dia em que sai episódio, vira acontecimento ("Saiu episódio novo de One Piece hoje (temporada 23, ep. 7)") |
| **Custo e segurança** | Gratuito (uso não comercial). Cache: busca 30 dias, detalhes 1 dia, recomendações 14, onde assistir 3, populares 1. Offline ou sem chave, volta sozinho ao comportamento anterior. A suíte nunca chama a API real |
| **Crédito** | Só no README (seção Créditos): "This product uses the TMDB API but is not endorsed or certified by TMDB". Decisão do Patrick: nada de crédito nas mensagens nem no `/mundo` |

**Fora do TMDB:** jogos (IGDB/RAWG, se um dia os jogos dela ganharem motor) e trends reais do TikTok (o UnifAPI tem, mas é pago e de operador desconhecido — avaliado e deixado de lado em 23/09).

`tests/test_tmdb_d6.py` (6 testes, rede simulada).

#### D6 parte 2 — proposta original

Sugerido pelo Patrick em 23/09 (developer.themoviedb.org). Gratuito para uso não comercial **com crédito** (logo + "This product uses the TMDB API but is not endorsed or certified by TMDB" numa seção Sobre/Créditos); ~40 req/s de limite; precisa de chave da conta dele (`TMDB_API_KEY`). Usos:
1. obra citada pelo Patrick → título real em pt-BR, tipo, nº de episódios e duração (hoje: tamanho padrão);
2. descoberta sozinha viva → recomendações a partir do que ela amou + o que está em alta no Brasil agora (hoje: lista fixa minha);
3. onde assistir no Brasil ("tá na Netflix") e episódio novo saindo do que ela acompanha.
Com cache por título: poucas chamadas por dia.

#### D8 — fim de semana (23/09, manhã)

Decisão do Patrick: "ela é jovem, de uma bolha social com boa condição; é normal receber convites dos amigos, mais ativos no fim de semana — mas a decisão é dela, e o emocional é o que conta".

`social_day.py` (`WEEKEND_INVITES`, `process_invites`):

| Peça | Como ficou |
|---|---|
| **Convites** | Sábado: praia de manhã (55%) e Quartinho Bar à noite (75%). Domingo: praia (45%) e cinema/shopping na Gávea (40%). Chegam de 1 a 3 dias antes ou na manhã do próprio dia (30%), de quem estiver no convite (Bia, Carol, Júlia, às vezes o Theo junto). Viram acontecimento ("A Bia te chamou: Praia com a Bia (sábado às 10:00)") |
| **Decisão dela, no dia** | 2 a 5 h antes, pelo estado **daquele momento**: base 65%, bateria social puxa pra cima ou pra baixo, energia baixa −30%, noite com menos de 6 h −20%, convite da Bia +10%, já ter outro rolê no dia −20% |
| **Resposta** | "Topou o convite" → vira compromisso confirmado (trajeto, estado SOCIAL, contatos no lugar, hora de dormir, tudo como as outras saídas). "Recusou o convite (…): tava sem energia / dormiu mal / quis ficar de boa em casa" → acontecimento com o motivo |
| **Prompt** | Enquanto não decide: "Convite em aberto: … — você ainda não decidiu se vai; depende de como estiver no dia" |
| **Dia útil** | Café de quarta/quinta e bar de sexta seguem como compromisso combinado com antecedência |

`tests/test_weekend_d8.py` (6 testes).

#### D4 v2 — como ficou (banho por necessidade e emoção, 23/09)

`rituals.py`. Sem teto diário; só não toma dois banhos com menos de 2 h entre eles.

| Gatilho | Como ficou |
|---|---|
| **Se arrumando pra sair** (D13) | Banho de 12–20 min, sem aviso |
| **Depois da academia** | 20–40 min depois de sair (já existia) |
| **Chegou da rua** 🆕 | Voltando de trajeto ou de rolê pra casa: 35% de chance, +35% no calor (≥ 28 °C pelo clima observado), +20% voltando de rolê; banho 10–30 min depois |
| **À noite** | Horário sorteado entre 19h30 e 22h30, pulado se já tomou há pouco |
| **Emoção** 🆕 | Energia baixa → "banho demorado, pra relaxar" (+10 min); senão "banho, skincare e cabelo: você gosta de ficar cheirosa". Chegando da rua no calor, o aviso fala do calor |

O aviso continua opcional (sempre com conversa rolando) e fora do teto de 2 cotidianos. 3 testes novos em `tests/test_rituals_c3.py`.

**Estacionado para outras fases** (ideias do Patrick que não são D1):
- Faltar aula por conta própria (preguiça, cansaço, cólica forte), com o Patrick perguntando por quê → D7.
- Perder ou se atrasar para aula e compromisso por trânsito e imprevisto → C.4 + D7.
- Cólica insuportável → fica em casa, liga com o ciclo → D11 (saúde e ciclo) a desenhar.

**Ordem de implementação (decisão minha, como combinado):**
1. **D1 refeições + D12 laços** — a arena provou que sem refeição ela inventa; sem pai, Bia e saudade ela não tem o que contar nem por que procurar o Patrick. D12 é recalibração de motores que já existem.
2. **D2 + D3 sono** — mesma engrenagem (janela de sono); o déficit de sono alimenta energia e humor de tudo o resto.
3. **D5 Milo** — pequeno, e dá assunto todo dia.
4. **D6 + D7 noite e faculdade** — o maior ganho de conversa: a noite é quando ele fala com ela.
5. **D8 fim de semana**, **D9 casa**, **D10 freela**.

**Respostas do Patrick (23/09, manhã):**
- **D5 Milo:** Shih Tzu (já era cânone). Em dia puxado ela pode pagar um passeador ("na zona sul isso é normal"). **Quem decide é ela**: o sistema dá o ponto de partida e o emocional/cansaço dela decide.
- **D6 o que ela assiste:** já viu *Elite* (na época do auge); romance e comédia romântica. Para o lado "cult", a **Marin Kitagawa** (*Sono Bisque Doll*) serve de **inspiração, não de cópia**. A lista é decidida junto com o Patrick.
- **D8 fim de semana:** tudo depende do emocional dela. Ela é jovem, de uma bolha social com boa condição, então é normal receber **convites dos amigos** (mais ativos no fim de semana). A decisão de ir é dela, e o emocional é o que conta.

**Perguntas em aberto para o Patrick** (ele responde solto, eu transformo em regra):
- D1: ela cozinha ou é mais de iFood/bandejão? Tem comida que ela odeia?
- D2: ela também tem dificuldade de dormir às vezes, ou é de capotar? Ela cochila à tarde?
- D5: o Milo é de que porte/raça? Ela paga passeador em dia puxado?
- D6: que séries/filmes ela vê (títulos reais)? Ela liga pra quem da família, e com que frequência?
- D8: como é um sábado e um domingo dela?

### D14 — Motor emocional: proposta (23/09, tarde) 🟡 aguardando o Patrick

Pedido do Patrick: "estamos fazendo um bot praticamente humano, então pode ser profundo e realista".

**Diagnóstico (DB de produção, 23/09 15h):**

| Dimensão | Valor | Linha de base |
|---|---|---|
| carinho | 0,98 | 0,85 |
| brincadeira | 0,95 | 0,75 |
| energia | 0,91 | 0,75 |
| paixão | 0,95 | 0,80 |
| bateria social | 0,93 | 0,90 |

1. **Ela só sente coisa boa.** O planner soma "+carinho, +paixão" a cada mensagem do Patrick ("EMOTIONAL_DELTAS" no log), e tudo vive no teto. Não existe frustração, tristeza, ansiedade, tédio nem mágoa.
2. **O mundo não toca o emocional.** Dormiu 6 h, está com fome, o uber errou o caminho, o pai ligou: nada muda o que ela sente. A energia estava em 0,91 depois de uma noite curta.
3. **Não há causa.** O prompt recebe "carinho: muito alto" sem o porquê. Gente de verdade sabe por que está irritada.
4. **Cada módulo lê a emoção do seu jeito** (comida, banho, Milo, sono, academia), com fórmulas próprias.

**A ideia central: cinco camadas, cada uma com seu relógio.** É como a psicologia separa: corpo ≠ humor ≠ emoção ≠ vínculo ≠ personalidade.

| Camada | Relógio | De onde vem | Exemplos |
|---|---|---|---|
| **1. Corpo** | calculado na hora, nunca "deriva" | fatos do mundo: sono (horas + dívida + tempo acordada + ritmo do dia), refeições, ciclo, cólica/doença (D11), calor, esforço do dia (faculdade, deslocamento, academia) | energia/cansaço, fome, dor/desconforto, tesão (vem do `intimacy`), sonolência |
| **2. Humor de fundo** | horas a dias (meia-vida ~10 h) | soma do corpo e das emoções do dia, clima, fase do ciclo, "temporada" da vida (semana de provas, férias) | dois eixos: **bem ↔ mal** (valência) e **agitada ↔ quieta** (ativação). "Dia bom mas cansada", "ansiosa e elétrica", "meio pra baixo e sem pique" |
| **3. Emoções (episódios)** | minutos a horas; cada tipo com meia-vida própria | **acontecimentos com causa**: cada episódio guarda o que causou, com quem, quando e a intensidade | ver a tabela de categorias abaixo |
| **4. Vínculo com o Patrick** | dias a semanas; sobe devagar, com retorno decrescente | como ele trata ela ao longo do tempo: presença, cuidado, promessas cumpridas, brigas e reconciliações | proximidade, segurança, saudade (cresce com o silêncio), desejo, mágoa pendente |
| **5. Personalidade** | fixa | cânone | expressiva, afetuosa, espontânea, independente, vaidosa, glutona, precisa de silêncio às vezes. **Modula tudo**: vaidosa → o peso dói mais; independente → não reclama de coisa pequena; glutona → come quando está ansiosa |

**Categorias e subcategorias das emoções (camada 3):**

| Família | Subcategorias | Meia-vida típica | Gatilhos reais já existentes no mundo |
|---|---|---|---|
| **Alegria** | empolgação, diversão, orgulho, alívio, gratidão, contentamento | 1–4 h | trabalho entregue (D7), elogio da professora, convite pra praia (D8), episódio novo de *One Piece* (TMDB), mesada do pai (D12), fofoca boa da Bia |
| **Afeto** (pessoas) | carinho, saudade, admiração, ternura | vínculo (lento) + picos curtos | ligação do pai, Milo fazendo gracinha, Patrick cuidando dela |
| **Tristeza** | desânimo, decepção, solidão, saudade de casa, luto (mãe) | 4–24 h | plano furado, chuva num dia livre, dia sozinha em casa, data sensível |
| **Raiva** | irritação, frustração, impaciência, chateação com alguém | 30 min–3 h (mágoa com alguém dura mais) | uber errou o caminho (já existe!), fome (hangry, D1), sono ruim, trânsito, professor chato |
| **Medo** | ansiedade, preocupação, insegurança | enquanto a causa existir | véspera de entrega (D7), prova, Patrick no deslocamento de noite, balança/agência (D1/D10) |
| **Vergonha/culpa** | vergonha, culpa | 1–6 h | faltou aula, comeu demais "fora da dieta", esqueceu de responder alguém |
| **Tédio/inquietação** | tédio, inquietação | até mudar de atividade | tarde livre sem plano, aula arrastada |

**Como o sentimento nasce ("avaliação").** Tudo é determinístico e **não gasta chamada de LLM a mais**:
- **Mundo:** um avaliador lê os `life_events` novos (tipo + detalhes) e decide qual emoção cada um provoca e com que força, filtrado pela personalidade e pelo humor do momento. O mesmo uber errado irrita mais quem dormiu mal. Os módulos atuais continuam iguais e viram **sensores**.
- **Patrick:** o planner, que já roda a cada mensagem, deixa de mandar "+carinho +paixão" fixos e passa a dizer **o que a mensagem fez**: elogiou, cuidou, provocou, sumiu, esqueceu algo importante, está triste (→ preocupação), brigou, pediu desculpa. O motor transforma isso em episódio e em vínculo.
- **Silêncio:** a saudade que já existe (proatividade) passa a morar no vínculo, crescendo com as horas sem ele.

**Regulação (como passa).** Cada emoção esfria pela meia-vida. Algumas **só passam quando a causa resolve**: a ansiedade da entrega some quando entrega. E existem **alívios reais**:
- banho, que no D4 já é "alívio emocional";
- comer (fome some → irritação cai);
- cochilo (energia);
- desabafar com a Bia ou com o Patrick (tristeza cai mais rápido);
- colo do Milo.

**Como aparece na conversa (regras de expressão).** O prompt não recebe números. Recebe 1 ou 2 linhas humanas com causa e jeito de mostrar, por exemplo:
> "Tá cansada (dormiu 6 h) e meio irritadinha com o uber que errou o caminho. Isso deixa você mais curta e sem paciência pra enrolação, mas não desconta no Patrick."

Três regras:
- ela **mostra, não narra**: nada de "estou me sentindo frustrada";
- ela **decide se conta ou guarda**, conforme a personalidade e a intimidade do momento (a insegurança com o peso ela esconde, e solta se ele for carinhoso);
- **o que ela sente pelo Patrick é separado do humor do dia**: dá pra estar de mau humor com o mundo e carinhosa com ele.

**O que muda no comportamento (além da fala):**
- energia do corpo → academia, passeio do Milo, cochilo, hora de dormir (substitui as fórmulas soltas);
- ansiedade → demora pra pegar no sono (o gancho já existe no `SleepPlan`) e come mais (glutona) ou perde a fome;
- tristeza/solidão → procura mais o Patrick e a Bia;
- irritação → respostas mais curtas e um pouco mais lentas; menos brincadeira;
- alegria/empolgação → conta mais coisas do dia dela (o share nudge fica mais provável);
- tédio → puxa assunto, procura série nova.

**Visibilidade pra gente:** um comando `/emocao` (só pro Patrick, some sozinho) mostra camada por camada com as causas. Assim dá pra conferir se o que ela sente bate com o dia dela.

**Fatias de implementação** (cada uma testada e entregue separada):
- **D14a — núcleo:**
  - tabela de episódios, humor, vínculo e corpo calculado;
  - bloco novo no prompt (troca o `[SEU ESTADO EMOCIONAL INTERNO]`);
  - `current_energy` e os leitores atuais passam a ler do motor;
  - migração dos 5 números atuais: carinho → vínculo, paixão → desejo, energia → corpo, brincadeira → derivada do humor, bateria social fica.
- **D14b — o mundo sente:** o avaliador dos acontecimentos (sono, fome, faculdade, deslocamento, amigos, pai, Milo, TV, clima, ciclo).
- **D14c — o Patrick sente:** o planner passa a mandar o evento emocional da mensagem; vínculo e mágoa; saudade no vínculo.
- **D14d — comportamento:** rotina, sono, apetite, proatividade e ritmo de resposta passam a ouvir o motor.
- **`/emocao`**.

**Decisões do Patrick (23/09):**

| Pergunta | Resposta |
|---|---|
| Mágoa **com ele** | **Real, mas justa.** Só quando ele faz algo que chatearia uma namorada de verdade: sumir sem avisar, esquecer algo importante, ser grosso. Ela fica mais seca, e a mágoa só passa quando conversam ou ele repara |
| Ciúme | **Leve e brincalhão.** Implica de brincadeira ("quem é essa aí?"), um pouco mais sensível na TPM, sem cobrança nem controle |
| Luto (mãe) | **Não mexer.** Fica só como fato da biografia; o motor não cria episódio de luto nem data sensível |
| TPM | **Moderada.** Mais sensível, irritável e carente, com vontade de doce. Perceptível, sem caricatura |

### Naturalidade de chat ✅ (23/09, tarde — conversa real do Patrick)

Ele notou na conversa de 22–23/09 que, mesmo com a fala boa, algumas coisas **lembram que é bot**. Tudo fica em `chat_naturalness.py` (sem LLM e sem rede), com testes em `tests/test_chat_naturalness.py`.

| Problema (caso real) | O que foi feito |
|---|---|
| **Repetição da própria fala**: 13:05 e 13:07 saíram com a mesma frase ("agora você consegue beijar sem esse aparelho te sabotando"). "É quando lembro que ela é só um bot" | Antes de enviar, o bot procura trecho de **6+ palavras já dito nas últimas 6 falas dela**. Se sobra fala sem a frase repetida, **corta** a frase (custo zero). Se não sobra, faz **uma** reescrita com a frase proibida. Log `chat.self_repeat` |
| **Ponto final fechando balão** ("vou comer direitinho sim.") | Sai o ponto do fim de cada balão/linha. Ficam o ponto entre frases, as reticências, "?" e "!" |
| **Ela só reage, nunca conta do dia dela**: o Patrick é que tinha que perguntar | **Puxa assunto próprio**: em conversa casual, a cada 5+ falas dela e 20+ min, com chance de 50%, ela recebe uma coisa do dia que ainda não contou (últimas 6 h: Theo, Bia, almoço…) pra puxar depois de reagir. Não entra em apoio emocional, flerte ou sexting, nem em pedido de foto/áudio ou lembrete. Marca como contado. Log `chat.share_nudge` |
| **"amor" em todo turno** + devolver o que ele disse com outras palavras ("sua escala é toda quebradinha", "ela te entregou vermelho e chamou de laranja") | Se as 2 falas anteriores já tinham "amor", o vocativo de enfeite sai desta. O prompt (EN e PT) ganhou a regra: "nunca devolva o que ele acabou de dizer com outras palavras; acrescente algo novo" |
| **Ideia do Patrick: esperar ele terminar de digitar.** Ele manda 5 balões do mesmo assunto e ela responde no 2º | O Telegram **não avisa o bot** que a pessoa está digitando, então a espera é **lida do texto**. Balão pendurado ("e", "porque", "tipo", vírgula, "...") espera ~12 s. Rajada em andamento soma +2 s, balão curtinho +1,5 s. Pergunta, "!", risada (kkk/ksks) ou emoji no fim fecham rápido (~4 s). Teto de 14 s. Cada balão novo reinicia a espera |

**Já corrigido antes (madrugada de 23/09):** "a função de foto tá em manutenção" (o "ver você feliz" disparava o pedido de foto) e "vou jantar agora" 4× sem jantar (a comida dela não existia no mundo; hoje existe, D1).

**Depois do restart (23/09, ~14h)**, o Patrick apontou mais dois problemas. Ambos corrigidos:
- **Ponto final ainda aparecia.** "…depois da facul. O Milo tá aqui…" foi partido em dois balões bem no ponto, e o ponto do meio virou o fim do 1º balão. Agora o ponto sai **por balão, no envio**.
- **"Tô em casa descansando" e o `/status` dizendo banho.** Às 13:57 o mundo decidiu um banho **quieto** (ele estava 40 min sem escrever), marcado para 13:59. Ele escreveu às 13:59:04 e a resposta não sabia do banho. O que mudou:
  - se ele escreve **antes** de ela entrar no banho, a resposta avisa ("vou tomar banho, já volto"), uma vez só;
  - **dentro do banho ela não pega o celular**: a availability adia a resposta até ela **sair do banho e se vestir** (fim do banho + 2–8 min);
  - o estado atual não diz mais "você AVISOU o Patrick" quando ela não avisou.

### Limpeza de prompt (23/09, tarde) ✅

O Patrick deu carta branca ("o ideal é a Marina que a gente planeja; vamos testar muito até chegar lá"). Medido no prompt real (`context_builder.build`), com a mensagem "tá por onde minha princesa?":

| | Antes | Depois |
|---|---|---|
| Regras + mundo (system) | 16,5 mil chars | 14,7 mil |
| Histórico da conversa | até 24 mil chars (~186 falas) | **12 mil** (~150 falas curtas, horas de conversa) |
| **Total por resposta** | **~40 mil chars (~11 mil tokens)** | **~26,7 mil (−33%)** |

**O que saiu e por quê:**
- **Histórico 24k → 12k** (aceito pelo Patrick). Custava caro, e o modelo copiava os próprios tiques de 90 turnos atrás ("Kkkkk…amor", ponto final). O que é mais antigo continua chegando pela memória consolidada e pelos resumos; a memória em si não muda.
- **`/feedback` virou caderno de correções.** A intenção do Patrick era anotar correções para a gente implementar, não dar ordens a ela. O bloco `[PEDIDOS DO PATRICK — OBRIGATÓRIO SEGUIR]` saiu do prompt (flag `PATRICK_FEEDBACK_IN_PROMPT`, desligada). A confirmação no Telegram agora diz "anotado no caderno de correções". Os pedidos pendentes (ponto final, repetição, emoji no fim) já viraram código em `chat_naturalness`.
- **`[TURN CONSTRAINT — CASUAL CADENCE]`**: era a 3ª cópia, em inglês, de "frases curtas / quebre em balões / Botafogo preto e branco", e ainda dizia "1 a 2 frases" enquanto o ritmo diz "1 a 3".
- **Linhas duras**: "turnos casuais: 1 a 2 frases" saiu (brigava com o ritmo). Fica só "nunca envie textão".
- **Ritmo de resposta**: saíram as regras repetidas das linhas duras (asterisco, rubrica, markdown), o "não pique o pensamento" duplicado, o "mantenha o português natural" (a voz já cobre) e a linha de telemetria crua `mode=casual_short verbosity=low …`.
- **Voz**: saiu "duas frases curtas / quebre com \n", que já está no ritmo.
- **Exemplos de voz**: 1 exemplo por fala do Patrick, em vez de 2. Os pares "oii amor" ×2 e "CARALHO AMOR" ×2 gastavam metade dos exemplos repetindo o mesmo cenário.
- **`[MÍDIA REAL EM ALTA]`**: sai quando a lista real dela (`[O QUE VOCÊ ASSISTE]`) existe. Trazia "O que está em alta" como título, talk show e "O Mentalista".
- **Assuntos em aberto podres** (DB de produção, abandonados à mão):
  - #12 "contar o que comeu no jantar" (de 22/09);
  - #14 "a manutenção da função de fotos ainda não foi resolvida": o bug virou assunto dela!
  - O reflector de sessão agora sabe que promessa miúda do momento é `promise` (vence sozinha em 12 h) e que falha técnica do app nunca é assunto em aberto.

**Próximas rodadas** (testando com o Patrick): ver se o share nudge soa natural, se a espera do debounce está boa e se o "amor" ficou na dose certa.

**Limite conhecido:** se o Patrick manda mais uma bolha **depois** que ela já começou a gerar (5–10 s de LLM), essa bolha vira o turno seguinte. Juntar isso no turno em andamento exigiria abortar o turno no meio (planner, emoção e memória já rodaram). Fica pra depois, se ainda incomodar com a espera nova.

### Fase C — Consolidação 🟡 (C1 parcial; C2/C3 pendentes)
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
