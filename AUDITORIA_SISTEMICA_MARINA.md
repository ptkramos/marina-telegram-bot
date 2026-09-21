# Auditoria Sistêmica — Marina 3.7.1

**Início:** 2026-09-21
**Pedido do Patrick:** *"Como esse bot foi desenvolvido basicamente por IA, por várias no caso, pode estar uma bagunça, e com meu pouco conhecimento, não sei realmente o que está funcionando, o que está conversando com o que, o que deveria conversar com o que."*

**Mandato:** liderar a auditoria, um sistema de cada vez, com liberdade para corrigir o que estiver errado.

---

## Como ler este documento

Cada auditoria cobre **um sistema** e responde quatro perguntas:

1. **Existe?** O código está no repositório.
2. **Está ligado?** Alguém no caminho de execução realmente chama.
3. **Está ativo?** A flag/config permite rodar em produção.
4. **Está coberto?** Existe teste que falha se quebrar.

Severidade dos achados:

| marca | significado |
|---|---|
| 🔴 **CRÍTICO** | causa comportamento errado visível para o Patrick |
| 🟡 **RELEVANTE** | risco real, ainda sem sintoma observado |
| 🔵 **HIGIENE** | não afeta comportamento; custa clareza e manutenção |
| ⚪ **POR DESIGN** | parece errado, mas está certo — registrado para não ser "consertado" por engano |

Critérios herdados do `ROADMAP_FUNCIONAL_MARINA_COMPLETO_3_0_A_3_7_V3_CANONICAL_RUNTIME.md` (seção 0.2): o runtime é **canônico**, com um único caminho moderno. `LEGACY FALLBACKS → ZERO`. Uma flag OFF significa degradação segura, nunca "voltar à arquitetura antiga".

---

## Placar das auditorias

| # | Sistema | Achados | Estado |
|---|---|---|---|
| 1 | Inventário estrutural e alcançabilidade | 2 🔴 · 2 🔵 · 9 ⚪ | ✅ concluída |
| 2 | Sistema de memória (3.1 / 3.5.0 / 3.5.3) | 1 🔴 · 1 🟡 · 1 🔵 | ✅ concluída |
| 3 | Pipeline de resposta (`process_incoming_batch`) | 4 🔴 · 1 🟡 · 1 ⚪ | ✅ concluída |
| 4 | Estado do mundo — fonte única (3.6.x Living World) | 4 🔴 · 3 🟡 | ✅ concluída |

**Ação aberta que depende do Patrick:** versionar o roadmap funcional (achado 1.2).

---

# Auditoria #1 — Inventário estrutural e alcançabilidade

**Data:** 2026-09-21
**Pergunta:** quais módulos existem, quais estão de fato no caminho de execução, e há código escrito que nunca roda?

## Método

Construí o grafo de dependências por AST (não por grep, para não confundir menção em comentário com import real), partindo de `bot.py` e percorrendo transitivamente todos os imports de módulos locais.

```
módulos na raiz:        60  (20.904 linhas)
alcançáveis de bot.py:  46
órfãos:                 14
arquivos de teste:      51
migrations:             19
```

## Achado 1.1 🔴 — Proteção contra dupla instância existia e nunca foi ligada

`runtime_lock.py` implementa `single_instance()`: um lock de arquivo mantido pelo sistema operacional, com `msvcrt.locking` no Windows e `fcntl.flock` fora dele. O docstring declara a intenção sem ambiguidade:

> *"OS-held lock: a second launcher must not create competing Telegram pollers."*

O módulo está correto, é robusto (o SO libera o lock mesmo se o processo morrer sem limpar) — e **nenhum arquivo do projeto o importava**. O entrypoint era:

```python
if __name__ == "__main__":
    main()
```

### Por que isso é crítico

Abrir o `.bat` duas vezes criava dois pollers no mesmo bot token. O Telegram entrega cada update a **apenas um** dos pollers, de forma imprevisível. O resultado não é "mensagem duplicada" — é pior: metade das mensagens do Patrick ia para um processo e metade para o outro, e **cada processo tem seu próprio estado em memória**:

- `ULTIMAS_MENSAGENS_MARINA` — o `/bom` e `/ruim` (Patch 033) resolveriam a fala errada
- `REGISTRO_WIZARDS` — o wizard responderia "não tem registro ativo" no meio do fluxo
- `MessageDebouncer` e seus locks (Patch 030) — a serialização de turnos vale por processo, então dois turnos rodariam em paralelo de novo
- `_reaction_capabilities`, `_invalid_reactions` — caches de reação divergentes

Vale registrar que isso pode explicar sintomas que atribuímos a outras causas durante o soak. O caso das quatro "Boa noite meu amor!" idênticas foi diagnosticado como teste poluindo o banco de produção (Patch 018), e aquele diagnóstico está correto — havia evidência direta no teste. Mas comportamento errático de estado em memória, que apareceu mais de uma vez, tem aqui uma explicação alternativa que não estava na mesa.

### Correção aplicada

```python
if __name__ == "__main__":
    from runtime_lock import single_instance
    _lock_path = Path(__file__).resolve().parent / "logs" / "marina.lock"
    try:
        with single_instance(_lock_path):
            main()
    except RuntimeError as exc:
        print(f"\n  {exc}\n")
        logger.error("startup.abortado_segunda_instancia path=%s", _lock_path)
        sys.exit(1)
```

A segunda janela agora encerra com mensagem legível ("A Marina já está aberta em outra janela. Use a janela existente.") em vez de traceback. Validado: primeira instância adquire, segunda é bloqueada, e após liberar o lock é readquirível.

## Achado 1.2 🔴 — O roadmap consolidado está fora do controle de versão

Durante a inspeção do working tree, encontrei 27 arquivos `.md` marcados como deletados (handoffs, planos complementares e validações de etapa, um por release) e o `ROADMAP_FUNCIONAL_MARINA_COMPLETO_3_0_A_3_7_V3_CANONICAL_RUNTIME.md` como **untracked**.

A consolidação em si é correta: 27 documentos fragmentados foram substituídos por um único roadmap, e o conteúdo antigo permanece recuperável no histórico do git. O problema é o estado resultante:

```
 D  HANDOFF_*.md, PLANO_*.md, VALIDACAO_*.md      (27 arquivos, deleção não commitada)
??  ROADMAP_..._V3_CANONICAL_RUNTIME.md            (4.076 linhas, nunca versionado)
```

A fonte da verdade funcional do projeto — a única descrição do que cada release de 3.0.1 a 3.7.0 deveria fazer — existe em **uma única cópia local, não rastreada**. Um `git clean -fd` a apaga sem aviso e sem recuperação. É, hoje, o documento mais valioso e mais frágil do repositório.

**Ação:** não commito por iniciativa própria (commits são decisão do Patrick), mas recomendo com urgência versionar o roadmap. Registrado aqui porque a perda seria irreversível.

## Achado 1.3 🔵 — Arquivos mal posicionados na raiz *(corrigido)*

Quatro arquivos na raiz não eram módulos de produção:

| antes | depois | por quê |
|---|---|---|
| `test_comfyui_generate.py` | `scripts/smoke/smoke_comfyui_generate.py` | o prefixo `test_` sugeria suíte automatizada |
| `test_render_v2.py` | `scripts/smoke/smoke_render_v2.py` | idem — faz chamada de GPU real |
| `voice_prosody_smoke_test.py` | `scripts/smoke/smoke_voice_prosody.py` | idem — faz chamada à Novita |
| `apply_patch_013.py` | `scripts/apply_patch_013.py` | one-shot já aplicado, sem função em runtime |

Os três smoke tests importavam módulos da raiz, então mover quebraria o path. Adicionei `sys.path.insert` nos dois que precisavam e um docstring explicando a origem. Sintaxe validada nos quatro.

## Achado 1.4 🔵 — Limpeza de artefatos *(executada)*

Autorização do Patrick: *"pode limpar tudo que você julgar como LIXO"*. Investiguei cada diretório antes de remover; todos já estavam no `.gitignore`, ou seja, nunca foram considerados parte do projeto.

| removido | volume | natureza |
|---|---|---|
| `scratch/` | 631 arquivos, 8.9 MB | 279 scripts one-shot de IAs anteriores, 279 `.pyc`, 8 bancos de ambientes de gate (3.5.0–3.6.0) |
| `logs/marina.log.1`, `.5` | 20 MB | logs rotacionados; o log ativo foi mantido |
| `temp_audio/voice_*.ogg` | ~3 MB | áudios de turnos já entregues |
| `dist/marina-validation-clean.zip` | 660 KB | artifact de build |

**Total: ~32 MB.**

Antes de remover `scratch/`, arquivei os 316 arquivos de código e SQL em `backups/scratch_codigo_20260921_095042.zip` (971 KB) — descartei apenas `.pyc`, `.log` e os bancos de teste, que são regeneráveis ou irrelevantes. A remoção é reversível.

Em `temp_audio/` preservei dois arquivos deliberadamente: `novo_voice_id.txt` (identificador da voz clonada da Marina) e `marina_clone_demo.mp3` (referência de clonagem). Nenhum dos dois é temporário de fato, apesar do diretório.

Também adicionei `scratchpad/` ao `.gitignore` — é onde ficam os exports de conversa e arquivos de trabalho, e estava fora da lista.

## Achado 1.4 ⚪ — Nove órfãos legítimos

Registrados aqui para que não sejam tratados como código morto em auditorias futuras:

| módulo | natureza |
|---|---|
| `gpu_manager.py` | CLI de operação da GPU Novita (`status`/`start`/`stop`/`list-loras`/`sync-loras`) |
| `healthcheck.py` | diagnóstico pré-execução, chamado à mão |
| `memory_cli.py` | inspeção de memória por linha de comando |
| `bootstrap_v36.py` | bootstrap de schema, usado por testes e por upgrade manual |
| `seed_world_bible_v36.py` | seed canônico, chamado por `bootstrap_v36` e pelos testes |
| `seed_academic_v36.py` | idem |
| `seed_knowledge_v363.py` | idem |
| `upgrade_social_v361.py` | upgrade pontual, exercitado pelos testes de social world |
| `benchmark_response_rhythm.py` | benchmark de ritmo, execução manual |

Todos são entrypoints próprios ou utilitários de suporte. Órfãos do ponto de vista de `bot.py` é o comportamento esperado.

## Conclusão da Auditoria #1

O inventário está mais saudável do que o pedido do Patrick sugeria: 46 dos 60 módulos estão genuinamente no caminho de execução, e 9 dos 14 órfãos são órfãos por design. Não encontrei duplicação de arquitetura nem caminhos concorrentes nesta camada.

O achado 1.1 é o tipo de defeito que justifica a auditoria: nada no comportamento do bot apontava para ele, nenhum teste falhava, e o código da solução já estava escrito no repositório desde a 3.4 — só não estava conectado a nada.

O achado 1.2 é de outra natureza, e por isso vale separar: não é um defeito de código, é um risco de perda de conhecimento. O bot continua funcionando perfeitamente sem o roadmap — mas nós dois perdemos a capacidade de auditar o que ele deveria fazer.

**Pendência aberta:** 1.2 depende de decisão do Patrick (commit).

## Estado do repositório após a auditoria

```
módulos na raiz:  60 → 56   (4 movidos para scripts/)
espaço liberado:  ~32 MB
arquivado:        backups/scratch_codigo_20260921_095042.zip
```

Nenhuma alteração de comportamento do runtime, exceto o lock de instância única — que só age quando alguém tenta abrir a Marina duas vezes.

---

# Auditoria #2 — Sistema de memória

**Data:** 2026-09-21
**Escopo:** releases 3.1 (Smart Memory), 3.5.0 (Memory Intelligence) e 3.5.3 (Session Reflection & Hygiene).
**Componentes:** `memory.py`, `memory_retriever.py`, `memory_consolidator.py`, `memory_hygiene.py`, `session_reflector.py`, `db.py`, `context_builder.py`, `world_context.py`.

## Método

Comparei o contrato descrito no roadmap com o schema real, o wiring efetivo e o comportamento observado. Onde o roadmap descreve um comportamento verificável, executei contra o banco de produção em modo somente-leitura.

## O que está certo

Vale começar por aqui, porque a expectativa do Patrick era encontrar bagunça — e a fundação da memória está sólida.

**Schema completo.** Todos os campos que a 3.5.0 promete existem em `fatos_patrick`: `memory_tier`, `volatility`, `confidence`, `last_confirmed_at`, `confirmation_count`, `canonical_key`. O supersede da 3.1 é feito por `active` + `supersedes_id`, e a 3.5.3 acrescentou `needs_reconfirmation` e `last_decay_at`. As três tabelas FTS5 do contrato (`fatos_fts`, `momentos_fts`, `resumos_fts`) estão presentes.

**O bug histórico crítico está corrigido.** O `implementation_plan.md` documenta que o retriever ficou 100% desligado em produção por uma condição invertida:

```python
if self.retriever and not getattr(settings, 'KNOWLEDGE_PRIVACY_ENABLED', False):
```

Com a flag em `true`, nenhum fato consolidado chegava ao prompt. Hoje a condição é `if self.retriever and not privacy_subjects` — depende de haver sujeito confidencial na consulta, não de uma flag global. Verifiquei o caminho de produção de ponta a ponta: `context_builder` (o singleton que o `bot.py` usa) tem retriever wireado, e uma pergunta sobre "a prova da quinta" traz o fato correto para o bloco `[MEMÓRIA]`.

**Jobs ativos.** `memory_hygiene_routine` e `session_reflection_routine` estão registrados no scheduler, e as seis flags relevantes estão `True`. Os fatos sem `last_decay_at` que encontrei foram todos criados hoje — o ciclo de higiene roda a cada 24h, então não há defeito aqui.

## Achado 2.1 🟡 — Nenhuma memória era classificada como core

O `MemoryRetriever` tem um passo explícito que carrega core memories em **todo turno**, independentemente de casamento lexical:

```python
# 2. Carrega Core Memories
core_memories = self.db.get_core_memories(limit=5)
```

Isso implementa com precisão o contrato da 3.5.0: *"CORE deve ser recuperável sem depender de palavra exata"*. O mecanismo está correto.

Só que o banco tinha **zero** fatos com `memory_tier='core'`. Todos os seis eram `standard`. O passo existia, rodava a cada turno e devolvia lista vazia sempre.

### Por que nenhum era core

Duas causas independentes.

**A primeira, no prompt do consolidator.** O contrato define quatro casos de core:

> *projeto central, fato forte do relacionamento, preferência muito importante, informação explicitamente pedida para lembrar*

O prompt implementava só o último:

```
6. If Patrick explicitly asks to remember ("remember that..."): set memory_tier='core'
```

Nenhuma regra dizia quando escolher `core`, `standard` ou `contextual` nos outros casos. Na dúvida, o modelo usava o default do schema — `standard`.

**A segunda, no seed.** O fato mais fundamental do banco nascia sem tier:

```python
"INSERT OR IGNORE INTO fatos_patrick (fato, created_at) VALUES (?, ?)",
("Nome: Patrick Ramos", now_iso),
```

A identidade do Patrick é o exemplo mais óbvio de core memory que existe — e caía em `standard` por omissão. Pior: o seed se repete em `reset_soak_learning()`, então cada `/limpar` devolvia o banco ao estado sem nenhuma core memory.

### Por que nenhum teste pegou

Os testes existentes cobrem `memory_tier='core'`, mas injetando o tier à mão:

```python
fid = self.db.adicionar_fato_patrick('Chess preference', memory_tier='core', ...)
```

Validam o **mecanismo** (dado um core, ele é recuperado) e nunca a **alimentação** (algo produz cores?). A lacuna estava exatamente entre os dois.

### Correção

Ampliei o prompt do consolidator com uma seção `COMO ESCOLHER memory_tier`, cobrindo os quatro casos do contrato e incluindo um freio explícito — *"Seja criterioso com 'core': se tudo for core, nada é"* — porque sem isso o modelo tende ao oposto e marca tudo. O seed passou a criar a identidade como `core`/`stable`/`importance=1.0` com `canonical_key='nome_patrick'`, nos dois pontos onde ele aparece.

No banco de produção, promovi o fato existente (backup em `backups/pre_core_tier_fix_20260921_100246.db`). Validado: a pergunta *"qual música você tá ouvindo?"*, que não tem palavra em comum com o fato, agora traz `Nome: Patrick Ramos` — a garantia do contrato passou a ser exercida.

## Achado 2.2 🔴 — O Patch 021 traduziu metade dos prompts

Investigando o consolidator, notei que o prompt dele estava em inglês. Levantei todos os prompts do projeto por AST, comparando densidade de marcadores de instrução em inglês e em português, e encontrei o padrão: **o Patch 021 traduziu o prompt de fala e deixou todos os prompts de processamento em inglês.**

| prompt | função | estado |
|---|---|---|
| `planner.PLANNER_SYSTEM_PROMPT` | decide intent, tone, emoji, eventos | inglês |
| `memory_consolidator.CONSOLIDATOR_SYSTEM_PROMPT` | extrai fatos duráveis | inglês |
| `session_reflector.SESSION_REFLECTOR_SYSTEM_PROMPT` | resume sessão, open loops | inglês |
| `vision_service.VISION_PROMPT` | descreve fotos do Patrick | inglês |

Todos leem conversa em português e gravam saída em português, raciocinando sob instrução em inglês — exatamente a configuração que o Patch 021 identificou como causa da voz degradada.

### O vazamento concreto: `response_goal`

Entre esses, um caso é pior que os demais. O schema do planner pede português explicitamente em vários campos:

```
"description": "...in Brazilian Portuguese"
"follow_up_prompt": "...in Brazilian Portuguese"
"content": "Concise pending topic in Brazilian Portuguese"
```

Mas não em `response_goal`:

```
"response_goal": "One short planning sentence for Marina's reply"
```

E esse campo não fica no planner — o `world_context` injeta o valor **cru** no prompt da Marina:

```python
blocks.append("[PLANNER 3.5 — TURN INTENT]")
blocks.append(f"Goal: {planner_goal}.")
```

Ou seja: a cada turno, uma frase gerada em inglês entrava no prompt de uma Marina que deveria pensar e falar só em português. O Patch 021 traduziu tudo em volta e este passou intacto, porque o texto não está no código — é gerado em runtime.

### Dois rótulos fixos também ficaram

As linhas do `world_context` que emitem `[LEARNED STYLE]`, `[PLANNER 3.5 — TURN INTENT]`, `Tone:` e `Goal:` não tinham ramo condicional de idioma. Saíam em inglês mesmo com `control_language='pt-BR'`, ao contrário de todos os blocos vizinhos.

### Correção

Traduzi os quatro prompts de processamento. No planner, `response_goal` agora exige explicitamente português, e a regra 6 das REGRAS DURAS lista todos os campos de texto que precisam estar em pt-BR. No `world_context`, os rótulos passaram a respeitar `control_language`:

| antes (sempre) | agora (pt-BR) |
|---|---|
| `[LEARNED STYLE]` | `[COMO O PATRICK ESCREVE]` |
| `[PLANNER 3.5 — TURN INTENT]` | `[INTENÇÃO DESTE TURNO — planner interno]` |
| `Tone:` / `Goal:` | `Tom:` / `Objetivo:` |

O rótulo novo do estilo aprendido, aliás, é o que a Fase C1 do plano de voz já pedia: `[LEARNED STYLE]` → `[COMO O PATRICK ESCREVE]`.

Verificado no prompt real de produção: zero resíduos em inglês, quatro equivalentes em português presentes.

## Achado 2.3 🔵 — `build_safe_core_prompt` é um legacy fallback vivo

`prompt_policy.build_safe_core_prompt` monta um prompt com `DATA_CHANNEL_POLICY_EN` e `SAFE_CORE_IDENTITY` — este último sem par em português, diferente de `MARINA_VOICE`, `HARD_LINES` e `CANON_FACTS`, que têm versão `_PT`.

Não está no caminho de conversa: `bot.py`, `context_builder.py` e `world_context.py` não o chamam. Só `healthcheck.py` e um re-export em `prompts.py`. Então não afeta a Marina hoje.

O problema é conceitual. A docstring diz *"Production-safe fallback when Living World dynamic context is OFF"* — mas o Living World é canônico desde a 3.7.0 e não pode ser desligado. É precisamente o que a seção 0.2 do roadmap manda eliminar:

```
LEGACY FALLBACKS
→ ZERO
```

**Ação:** não removi agora porque `healthcheck.py` depende dele e o escopo desta auditoria é memória. Fica para uma auditoria de prompts e fallbacks.

## Testes adicionados

`tests/test_memory_core_tier_audit2.py` — 8 testes. Cobrem a lacuna que os testes antigos deixavam: banco novo nasce com core memory, a identidade é core/stable, o `reset_soak_learning` recria como core (senão cada `/limpar` reintroduzia o defeito), core entra sem casamento lexical, contextual não ganha a mesma garantia, e o prompt do consolidator ensina os três tiers com freio no core.

`tests/test_prompt_language_audit2.py` — 6 testes. Travam o idioma dos quatro prompts de processamento e dos rótulos do prompt montado. Existem para que a próxima tradução parcial falhe no CI, em vez de passar semanas despercebida como esta.

## Conclusão

A arquitetura de memória está correta e bem construída — o schema cumpre o contrato, o ranking híbrido funciona, o bug crítico de 2026-09-19 está resolvido. Os dois achados não são de arquitetura, são de **alimentação**: um mecanismo certo que ninguém abastecia (core memories) e uma tradução que parou no meio do caminho (prompts de processamento).

O achado 2.2 é o mais relevante desta rodada. Ele significa que o Patch 021, que tratamos como a correção mais impactante do soak, foi aplicado a **metade** do sistema. O planner — que escolhe o tom de cada resposta e roteia os few-shots da voice_library — continuou raciocinando em inglês por mais dois dias depois daquele patch.

**Arquivos alterados:** `memory_consolidator.py`, `session_reflector.py`, `planner.py`, `vision_service.py`, `world_context.py`, `db.py`, `tests/test_memory_core_tier_audit2.py` (novo), `tests/test_prompt_language_audit2.py` (novo).

**Pendência aberta:** 2.3 (remover o legacy fallback).

---

# Auditoria #3 — Pipeline de resposta

**Data:** 2026-09-21
**Escopo:** `process_incoming_batch` — 878 linhas, o ponto onde todos os sistemas se encontram.
**Por que primeiro:** três bugs já tinham aparecido ali por acidente nesta sessão (debouncer abortando turno, availability mapeando rotina errada, disclaimer sabotando estado). Taxa alta de defeito é sinal de área nunca auditada. E 100% das conversas passam por essa função — defeito aqui não é localizado.

## Método

Extraí a estrutura por AST em vez de leitura linear: pontos de saída, chamadas de efeito e a função que contém cada registro de job. Para cada saída antecipada, verifiquei quais efeitos essenciais ficam de fora.

```
process_incoming_batch:   linhas 2530–3408 (878)
pontos de saída:          6
marcos numerados:         8
```

## Achado 3.1 ⚪ — Saída por DEFER não perde a fala do Patrick *(verificado, está correto)*

Comecei por uma suspeita que se mostrou infundada, e registro porque o raciocínio importa para quem auditar depois.

O `return` do ramo `action == 'deferred'` (L2596) acontece **antes** de qualquer `registrar_mensagem_usuario`. A leitura ingênua é alarmante: quando a Marina está dormindo, a mensagem do Patrick nunca chegaria em `conversas`, e se o batch morresse (`FAILED` após 3 retries, `SUPERSEDED`, `UNKNOWN_DELIVERY`) a fala dele desapareceria do histórico para sempre.

Não é o que acontece. Os itens do batch carregam `conversation_message_id`, ou seja, a mensagem **já foi persistida** antes de o batch existir; o item apenas referencia. Verifiquei a integridade no banco real:

```
items apontando para conversa inexistente: 0
batch 1 → conversas 19..23, todas role='user', conteúdo intacto
```

Um batch que morre leva só a *entrega*, nunca o registro. Está correto.

## Achado 3.2 🔴 — Dois blocos de finalização duplicados, divergentes em três pontos

O pipeline termina em dois lugares que fazem o mesmo trabalho: um no caminho de escolha de avatar (L2855-2882) e outro no caminho principal (L3245-3264). Ambos persistem a fala da Marina, aplicam efeitos do plano, marcam o batch como enviado e registram latência.

Eles divergiram.

### Divergência A — a coluna `model` não era gravada na entrega via batch

O caminho ao vivo usa `registrar_mensagem_assistente()`, que tem default inteligente:

```python
if model is None:
    model = getattr(settings, "LLM_MODEL", None)
```

O caminho de batch chamava `db.adicionar_mensagem()` direto, e esse método aceita `model=None` sem default. Resultado: **toda resposta entregue a partir de um batch pendente gravava `model=NULL`** — exatamente o dado que o Patch 018 criou para auditar qual LLM produziu cada fala.

A evidência estava no export que o Patrick me mandou hoje, e eu tinha lido sem perceber:

```
[07:57:54] MARINA:  [model: -]        ← backlog do sono, via batch
[07:58:39] MARINA:  [model: -]        ← backlog do sono, via batch
[08:00:47] MARINA:  [model: mistralai/mistral-nemo]   ← ao vivo
...
#4  07:57:39 → 08:05:36  (19 msgs)  models: mistralai/mistral-nemo×7, -×2
```

Consulta ao banco confirma, e o recorte é exato:

```
mistralai/mistral-nemo   16
(NULL)                    2
  2026-09-21T07:57  Bom dia, amor! Como você acordou tão cedo?...
  2026-09-21T07:58  Sim,amor, já acordei. Tudo certo com você?...
```

As duas sem modelo são as mesmas duas que saíram fora de ordem no Patch 030 — as que vieram do batch. Duas evidências independentes apontando para o mesmo caminho de código.

Não preenchi retroativamente: não há como saber qual modelo gerou aquelas falas, e inventar o dado seria pior que deixá-lo nulo.

### Divergência B — `apply_plan_effects` sem guarda de `u_id`

O bloco do avatar checava `if plan and u_id is not None`. O principal checava só `if plan:` e passava `conversation_id=u_id` em seguida, aceitando `None`.

### Divergência C — latência medida só no caminho ao vivo

`record_actual_latency` estava **dentro** do `elif sent_mid:`, então entregas via batch nunca eram medidas. São justamente as mais interessantes para calibrar latência humana — foram adiadas de propósito pela política de availability. A amostra de telemetria estava enviesada para os turnos rápidos.

### Correção

As três divergências corrigidas no bloco principal: `model=` passado explicitamente, guarda de `u_id` adicionada, e `record_actual_latency` movido para fora do `if/elif` (agora condicionado só a `sent_mid`, cobrindo os dois caminhos).

Mantive os dois blocos em vez de extrair um helper. A causa raiz é a duplicação, mas refatorar duas finalizações de um pipeline crítico exige cobertura de integração que hoje não existe — o risco de introduzir um defeito novo supera o ganho. Em vez disso, travei as invariantes com testes estruturais que leem a AST e falham se **qualquer** caminho futuro esquecer o mesmo detalhe.

## Achado 3.3 🔴 — Busca de rede dentro da montagem do prompt *(bug meu, do Patch 023)*

Investigando por que a suíte levava ~15 minutos, encontrei nos logs:

```
primp - INFO - response: https://pt.wikipedia.org/w/api.php?...search=filmes%20em%20cartaz...
primp - INFO - response: https://grokipedia.com/api/typeahead?query=filmes+em+cartaz...
ddgs - INFO - Error in engine duckduckgo: TimeoutException(...operation timed out)
primp - INFO - response: https://search.brave.com/search?q=animes+populares... 429
```

As queries são do `MediaLookupService`, que **eu** criei no Patch 023 para acabar com o "Filme de Romance". E eu chamei o refresh no lugar errado:

```python
media = MediaLookupService(self.db)
media.refresh_if_stale(now)     # ← dentro de WorldContextBuilder.build()
media_block = media.get_prompt_block(now)
```

Duas consequências, e a segunda é pior que a primeira.

**Na suíte:** todo teste que monta um prompt dispara as três buscas, porque banco temporário nasce com cache vazio. Daí os ~15 minutos e a dependência de rate limit alheio — o `429` do Brave apareceu numa execução normal, o que torna a suíte não determinística.

**Na conversa real:** o refresh é síncrono. Sempre que o cache diário vence, o **próximo turno da Marina paga a busca inteira** antes de ela conseguir responder. Os logs mostram timeouts de 5 a 10 segundos por provedor, somados. O Patch 013 teve o cuidado de honrar soft-delays para simular ocupação humana; este bug adicionava atraso real e aleatório sobre isso.

### Correção

`build()` agora só **lê** o cache. O refresh virou `media_lookup_routine`, registrado no scheduler de `post_init` junto dos outros jobs, com `asyncio.to_thread` e `next_run_time` 20s após o startup — o cache esquenta sozinho, sem cobrar a espera do primeiro turno.

Medição depois da mudança, com cache vazio:

```
1º build: 0.53s      (zero chamadas de rede)
2º build: 0.39s
```

Um detalhe do processo vale registro: o teste que escrevi para verificar o registro do job falhou na primeira execução, porque eu o apontei para `main()`. Os jobs vivem em `post_init` — `main()` só monta handlers. Eu havia registrado no lugar certo, mas se tivesse errado, o job nunca rodaria e o bloco de mídia ficaria vazio para sempre, silenciosamente. O teste pegou a única coisa que ele podia pegar, e por isso ficou.

## Testes adicionados

`tests/test_pipeline_invariants_audit3.py` — 5 testes estruturais (AST). Nenhum teste de comportamento pegaria as divergências do achado 3.2: a resposta chega ao Patrick normalmente, só o dado de auditoria fica errado. Então estes leem o código: toda `adicionar_mensagem(role='assistant')` passa `model=`, todo `apply_plan_effects` está sob checagem de `u_id`, nenhum `record_actual_latency` fica preso sob `elif sent_mid`, e o item de batch referencia a conversa.

`tests/test_no_network_in_prompt_audit3.py` — 7 testes. `build()` não chama `refresh_if_stale`, mas continua lendo o bloco de cache; falha no cache não derruba o turno; e o job existe, está em `post_init` ao lado dos outros, e respeita o kill switch.

## Achado 3.4 🔴 — O bloco de mídia injetava lixo como "título real" *(bug meu, do Patch 023)*

Ao inspecionar um prompt gerado durante esta auditoria, o bloco `[MÍDIA REAL EM ALTA — se for citar filme/série/anime hoje, use um destes]` trazia:

```
- Top 10 Netflix: s
- Veja as 10 s
- Netflix atualiza lista das s
```

O cache de produção confirmou: os **quatro** títulos armazenados eram fragmentos de manchete (`"Top 10 Netflix: s"`, `"Veja as 10 s"`, `"Top 10 Melhores S"`, `"Para Você Ver"`). Nenhum era uma obra. E o bloco instrui a Marina a usar *um destes* — o Patch 023 foi criado para acabar com o "Filme de Romance" e, na prática, oferecia um placeholder pior.

**Causa:** o lookahead do extrator era `(?=\s*(?:é|estreou|...))`. `\s*` aceita zero espaços e não havia fronteira de palavra, então o "é" de dentro de "s**é**ries" casava como o verbo "é" e cortava a manchete no meio da palavra.

**Correção:** o gatilho exige `\s+` antes e `` depois; manchetes de agregador ("Top ", "Veja ", "Lista ", "Netflix atualiza"…) são descartadas; fragmento terminado em letra solta é rejeitado — mas não em dígito, para preservar "Round 6" e "Duna 2", que o primeiro rascunho do filtro derrubou.

O cache corrompido foi apagado do banco de produção; `media_lookup_routine` refaz no startup com o extrator corrigido. Testes de regressão em `tests/test_media_lookup.py` usam as manchetes reais que produziram o lixo.

## Achado 3.5 🔴 — O guard de artefatos do Patch 030 estava cego para o caso real *(bug meu)*

Esta auditoria encontrou uma prova de campo que nenhum teste teria produzido: o Patrick passou a usar `/ruim` às 10:35 e, até 13:12, marcou nove respostas. O `marina.lock` criado às 10:32 confirma que o bot rodava **com** os Patches 030–033 carregados. Mesmo assim, três respostas vazaram artefato de dataset:

```
Evitar 002:  ...A gente não é namorada ainda. otechnically\_single=true
Evitar 003:  ...Vou colocar um lembrete... dysfunction\_manage=none irdp=
Evitar 007:  htar\_reason=query htar\_negative=0
```

O Nemo emite o underscore **escapado** (`\_`) — reflexo de modelo treinado em markdown. O regex esperava `_` cru. Os testes do Patch 030 usavam apenas a forma crua e ficaram verdes; o guard estava cego justamente para a forma que aparece em produção.

A Evitar 001 mostrou um segundo buraco: a resposta inteira foi `Unternehmensprufung` (alemão). Alfabeto latino, então o detector de script estrangeiro não dispara.

**Correção:** `_unescape_markdown()` normaliza `\_`, `\*` e afins antes de qualquer checagem, inclusive no `_salvage_reply`; o regex passou a pegar `chave=` sem valor (`irdp=`) e `=query`; e um detector novo, `_is_non_portuguese_reply`, pega turnos curtos sem nenhuma palavra funcional do português e com morfologia claramente estrangeira (`-ung`, `-keit`, `-schaft`, `ß`…), sem disparar em "Wandinha", "Konosuba kkk" ou "tranquilidade".

A Evitar 004 ("Foi tranquilo sim, Como foi o seu dia? Tem alguma novidade?" — motivo: *"a todo momento perguntando como foi o meu dia"*) também passou com o guard ativo, por três razões somadas: o corte removia só a última pergunta; "tem alguma novidade" e "como foi o seu dia" não estavam no padrão; e o modelo usa vírgula + maiúscula como fim de frase, o que o split não reconhecia. As três foram corrigidas, e o corte agora opera em laço sobre o texto original, preservando a pontuação entre passadas.

**Todos os testes novos usam as falas literais da antibiblioteca.** A lição é a mesma do achado 2.2 e do teste invertido da Auditoria #2: um teste escrito a partir do que eu *imagino* que o modelo faz fica verde e não protege nada. Os casos agora vêm do que ele *fez*.

## Achado 3.6 🟡 — A suíte de testes escrevia no log de produção

O `RotatingFileHandler` era anexado no import do `bot.py`, e todo teste importa `bot`. Em 21/09 o `marina.log` rotacionou 10 MB em cerca de três horas; a sessão real do Patrick (10:32–13:12) foi empurrada para o `.1` por spam de teste. Com `backupCount=5`, algumas corridas da suíte bastam para expulsar da rotação os logs que servem para diagnosticar o soak — e os logs dos meus próprios testes apareceram misturados às linhas reais durante esta investigação, quase me levando a uma conclusão errada sobre quais guards tinham disparado em produção.

**Correção:** o handler de arquivo só é anexado fora de `unittest`/`pytest`, com override explícito por `MARINA_LOG_TO_FILE`. Validado: zero bytes gravados no log durante a suíte; execução normal continua anexando o arquivo.

## As outras seis capturas

Não são corrigíveis por guard — são alucinação de conteúdo e perda de coerência:

| # | fala | problema |
|---|---|---|
| 001 | "chego aí em 15 minutos" | presume que os dois estudam no mesmo lugar |
| 005 | "então você não quer me contar nada de novo?" | resposta sem relação com "vai pra academia hoje?" |
| 006 | "fiquei em casa... só saí pra comprar suplementos" | reaproveita fala antiga do Patrick como se fosse dela; contradiz que acabou de voltar da faculdade |
| 008 | "já me parece uma gracinha pra ir sozinha" | ininteligível |
| 009 | "quer que eu convide ela pra ir junto?" | contradiz o turno anterior |

O padrão comum é **perda de coerência entre turnos consecutivos** — e é exatamente o sintoma que o bloco `[COMO NÃO SOAR]` passa a atacar a partir do próximo startup, porque essas nove falas agora entram no prompt como contraste. Vale observar se a taxa cai antes de concluir que é limite do modelo 12B.

## Efeito colateral medido do achado 3.3

```
suíte completa antes:  498 testes em 880s
suíte completa depois: 510 testes em 207s   (−76%)
```

## Três testes que validavam o comportamento antigo

A primeira suíte após a Auditoria #2 falhou em três testes, todos codificando o estado que as correções mudaram de propósito. Um deles merece registro:

`test_prompt_authority_v370.test_control_prompts_english_markers` **exigia** inglês nos quatro prompts de processamento e proibia explicitamente a string `'Você é'`. Ele é a razão pela qual esses prompts sobreviveram ao Patch 021: quem tentasse traduzir veria o teste falhar e concluiria, com razão, que o inglês era deliberado. A política estava documentada no topo de `prompt_policy.py` como `CONTROL PLANE → English`.

O teste institucionalizou o defeito. Foi invertido, e a política de idioma reescrita no docstring de `prompt_policy` com o histórico da decisão.

Os outros dois eram ajustes mecânicos: `test_core_and_fts_return_age_and_source` assumia que a única core memory do banco era a do teste (agora o seed cria a identidade como core), e `test_context_builder_accepts_planner_tone_and_goal` procurava o rótulo em inglês.

## Conclusão

O pipeline não está bagunçado no sentido que o Patrick temia — a ordem das etapas faz sentido, os efeitos essenciais rodam, e a saída por DEFER que parecia perigosa está correta. O problema é outro: **878 linhas com duas finalizações duplicadas**, e duplicação sem teste que compare os ramos deriva sozinha.

Os dois achados críticos têm a mesma assinatura: não produzem erro, não quebram teste, não incomodam o Patrick na conversa. Um corrompe silenciosamente o dado de auditoria; o outro adiciona segundos de latência de forma intermitente. São defeitos que só aparecem quando alguém vai olhar — e é por isso que a auditoria existe.

Também vale dizer: o achado 3.3 é meu, de dois dias atrás. Colocar o refresh no `build()` pareceu natural na hora (o dado é para o prompt, então buscar ali é conveniente) e passou pela minha própria revisão do Patch 023.

**Arquivos alterados:** `bot.py` (três divergências + `media_lookup_routine` + registro no scheduler), `world_context.py` (refresh removido do build), `tests/test_pipeline_invariants_audit3.py` (novo), `tests/test_no_network_in_prompt_audit3.py` (novo).

**Dívida registrada:** a duplicação dos blocos de finalização segue lá, agora sob teste. Extrair o helper pede cobertura de integração do pipeline — candidato natural a uma auditoria futura.

---

# Auditoria #4 — Estado do mundo: quem decide o que a Marina está fazendo

**Por que esta:** o bug do "passeando com o Milo" × "tô em casa" (Patch 030) e seis das nove capturas de `/ruim` são o mesmo sintoma, perda de coerência sobre onde ela está e o que está fazendo. O Patch 030 corrigiu o texto do prompt. Esta auditoria olhou para a fonte do dado.

## Método

1. Mapear todo leitor de estado: quem chama `WorldStateManager.resolve()` e quem lê `world_state` direto via `latest()`.
2. Simular dias inteiros em cópia do banco de produção (sábado e terça, conversa a cada 10 min e mensagens esparsas a cada 75 min). Em cada turno, registrar o que a **disponibilidade** vê antes e o que o **prompt** resolve depois.

Mapa encontrado: **um resolvedor e cinco leitores diretos.**

| Quem | Como obtinha o estado | Checava idade? |
|---|---|---|
| Prompt (`world_context`) | `resolve()` | sim (é o resolvedor) |
| `/status` | `resolve()` | sim |
| Disponibilidade | `latest()` | sim → UNKNOWN se velho |
| Câmera | `latest()` | sim → degrada |
| Proatividade (janela de sono, fator de estado) | `latest()` | sim |
| Proatividade (contexto da mensagem espontânea) | `latest()` | **não** |
| Anúncio de saída | sorteio próprio no `RoutineEngine` | n/a |

## Achado 4.1 🔴 — A rotina era um sorteio do instante, refeito a cada hora

`RoutineEngine.choose()` sorteava entre as rotinas cuja janela contém o **agora**, com peso pela probabilidade. O snapshot vale 60 min, então a cada hora o sorteio era refeito do zero. Duas consequências medidas:

- **Academia de cinco horas.** Janela 15:00–21:00, probabilidade 0,55 × energia contra 0,20 do "tempo livre". Na simulação de terça: `16:00 → 17:15 → 18:30 → 19:45 → 21:00`, todas "treinando na academia".
- **Todo dia.** `_day_applies()` aceitava `3_to_5_days_per_week` como `daily`. A cota semanal nunca existiu no código.

O passeio com o Milo tinha a mesma forma (janela de 07:00 a 10:30, reamostrada a cada hora).

**Correção — agenda diária determinística** (`world_state.py`):
- Cada rotina com deslocamento (`pet_walk`, `gym`, `gym_indoor`) recebe **um slot concreto por dia**, com início e duração derivados só da data: passeio de 30–50 min, academia de 60–90 min.
- A cota semanal escolhe de 3 a 5 dias por semana ISO, também pela data.
- `pick()` substitui o sorteio no `resolve()`, com ordem fixa: sono > slot ativo > rotina de janela > tempo livre.

Resultado: /status, disponibilidade, prompt, câmera e anúncio veem o mesmo slot, e ele sobrevive a um restart. `choose()` continua existindo para os testes antigos, mas saiu do caminho de produção.

## Achado 4.2 🔴 — Teletransporte para casa no meio do passeio

O filtro "conversa ativa" (Patch 013) tira as rotinas externas do sorteio quando o Patrick falou nos últimos 15 min, e a proatividade anuncia a saída antes. Com o sorteio refeito a cada hora, ele também agia **no meio** de uma atividade. Se ela estava na academia e o Patrick puxava conversa, o próximo re-sorteio só tinha rotinas de casa, e ela voltava sem transição.

**Correção:** o snapshot de slot grava `slot_end` e fica válido até o fim do slot, mesmo com conversa e mesmo depois dos 60 min. Na direção contrária, um snapshot de casa ainda "fresco" é descartado se um slot começou e nada o bloqueia (`_slot_began`). Antes ela podia ficar até 60 min atrasada para a própria rotina.

## Achado 4.3 🔴 — A disponibilidade decidia com um estado diferente do prompt

A disponibilidade roda **antes** da montagem do prompt, e o prompt é quem resolvia o estado. Na primeira mensagem depois de mais de 60 min de silêncio, o snapshot estava velho, então a disponibilidade via `UNKNOWN`. Um segundo depois, o prompt resolvia um estado novo. Na simulação esparsa, **13 de 15** turnos caíram em UNKNOWN.

Esse é justamente o caso em que a latência humana importa ("tava passeando com o Milo, vi agora"): o profile `PET_WALK` do Patch 030 **praticamente nunca era usado** na primeira mensagem.

**Correção:** se o snapshot está velho, a disponibilidade chama `resolve()`. Os dois passam a ler o mesmo snapshot, e uma falha ali continua fail-open. Depois da correção: 15/15 turnos frescos e 0 divergências.

## Achado 4.4 🔴 — Mensagem espontânea com estado de horas atrás

`_build_neutral_context` dizia à Marina "Seu estado agora: X" com o `latest()` cru, **sem checar a idade**. Às 14h, com o último snapshot das 03h, a instrução era "Seu estado agora: dormindo" — para uma mensagem que ela mesma ia mandar. **Correção:** passa pelo `resolve()`.

## Achado 4.5 🟡 — O anúncio de saída escolhia sozinho o que anunciar

`_detect_transition_intent` pegava o externo de maior score **a qualquer momento da janela**. Vencida a transição (75 min fixos), a próxima rodada da proatividade durante uma conversa podia anunciar academia de novo na mesma tarde. **Correção:** só anuncia um slot da agenda que começa em até 3 min, e a transição termina junto com o slot, não em 75 min fixos.

## Achado 4.6 🟡 — Resto da Auditoria #2: instruções proativas em inglês

Os quatro prompts de processamento foram traduzidos, mas as quatro instruções da proatividade (`pending_event_followup`, `open_loop_checkin`, `topic_followup`, `neutral_affection`) continuavam em inglês ("Daypart is…", "Send a spontaneous message…"). O teste da Auditoria #2 só olhava os prompts que eu tinha traduzido. Estas instruções foram traduzidas e agora têm teste. O `build_autonomous_decision_prompt` de `prompts.py` também está em inglês, mas é deprecated e não é chamado (só importado em `bot.py`), então não foi tocado.

## Testes adicionados

`tests/test_world_agenda_audit4.py`, com 8 testes:
- o estado não depende do RNG;
- a academia ocupa no máximo um slot de até 90 min por dia;
- a cota semanal fica entre 3 e 5 dias em 8 semanas;
- o slot se mantém até o fim mesmo com conversa;
- a disponibilidade vê o slot na primeira mensagem após silêncio;
- o anúncio só sai dentro do slot e termina com ele;
- as instruções proativas estão em pt-BR;
- a mensagem espontânea não usa snapshot velho.

Suíte completa: **522/523**. A única falha é a dívida conhecida (`test_offer_acceptance`).

## Conclusão

O Living World tinha as peças certas (compromisso > plano > transição > rotina, horário de funcionamento, cooldown), mas o último degrau, a rotina, era **sem memória**. Cada leitor perguntava "o que ela está fazendo agora?" em um momento diferente, e às vezes recebia um sorteio novo. O Patch 030 ensinou o prompt a respeitar o estado. Esta auditoria faz o estado ser o mesmo para todo mundo.

**Dívida registrada:**
- Câmera e fator proativo ainda leem `latest()` com a própria regra de 60 min. Com slots de até 90 min, os últimos 30 min de uma academia longa aparecem para eles como "desconhecido". Isso degrada com segurança, sem inventar estado, mas o ideal é que todos passem pelo resolvedor.
- ~~Em dia de aula o Milo não passeava~~ → resolvido no achado 4.7.

## Achado 4.7 🟡 — A agenda nova tinha perdido a "vontade" *(regressão minha, pega pela pergunta do Patrick)*

O Patrick perguntou se tempo ruim e vontade de ir ou não à academia continuavam valendo. Tempo ruim sim: a academia de rua já virava a do prédio. A vontade **não**. Na primeira versão da agenda, energia, chuva e feriado só mexiam no score, e o score só servia de desempate. Num dia da cota ela ia à academia exausta, e o passeio na chuva, que antes acontecia 1 vez em 4, passou a acontecer sempre.

Havia ainda uma divergência antiga: só o prompt lia a energia real. A disponibilidade, o /status e o anúncio de saída supunham 0,7.

**Correção:**
- `_willing()` transforma o score (que já embute energia, chuva e feriado) em chance de ir, com uma rolagem fixa por dia. Com energia normal ela vai em todos os dias da cota. Cansada, pula.
- `current_energy(db)` passa a ser a fonte única de energia para todos os leitores.

**Passeio em dia de aula** (decisão do Patrick: "encaixa onde for mais cômodo"):
- A janela vira 07:00–19:00, menos a faculdade (1h antes da primeira aula para se arrumar e ir, 45 min depois da última para voltar).
- O passeio cai no primeiro horário livre em que cabe: segunda de manhã cedo, terça a quinta à tarde.
- Nunca se sobrepõe à academia do mesmo dia.
- A academia também passou a respeitar a volta da faculdade: antes podia começar às 15:00 em ponto, quando a aula acaba às 15:00.

Semana simulada (21–27/09):

| | Normal | Cansada (0,3) | Chuva forte |
|---|---|---|---|
| Seg (aula 9–13) | Milo 07:05 · academia 18:50 | Milo 07:05 | Milo 07:05 · academia do prédio 18:50 |
| Ter (aula 7–15) | Milo 18:10 | Milo 18:10 | — |
| Qua (aula 7–13) | Milo 17:20 | Milo 17:20 | Milo 17:20 |
| Qui (aula 7–15) | Milo 16:27 · academia 17:30 | Milo 16:27 | academia do prédio 17:30 |
| Sex | Milo 07:05 | Milo 07:05 | — |
| Sáb | Milo 09:35 · academia 15:05 | Milo 09:35 · academia 15:05 | academia do prédio 15:05 |
| Dom | Milo 09:25 | Milo 09:25 | — |

Mais 3 testes em `test_world_agenda_audit4.py`: o passeio em dia de aula fica fora da faculdade e da academia; cansada, ela vai menos à academia; com chuva forte, vai à academia do prédio.
