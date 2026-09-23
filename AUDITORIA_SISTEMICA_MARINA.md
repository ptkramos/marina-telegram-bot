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
| 5 | Estado emocional (inclui bateria social) | 1 🔴 · 3 🟡 · 1 ⚪ | ✅ concluída |
| 6 | Mundo social — a vida dela acontece | 6 🔴 · 1 🟡 | ✅ concluída |
| 7 | Infraestrutura do banco (isolamento, conexões, migrations) | 2 🔴 · 3 🟡 | ✅ concluída |
| 8 | Planner, eventos e lembretes (+ reset do soak) | 2 🔴 · 1 🟡 | ✅ concluída |
| 9 | Arena de modelos no OpenRouter (+ bugs que ela revelou) | 3 🔴 · 3 🟡 · 1 🔵 · 1 ⚪ | ✅ concluída (Luna escolhido em 22/09) |
| 10 | Revisão do soak de 22/09 (volta do plantão) | 3 🔴 · 1 🟡 · 1 🔵 | ✅ concluída |
| 2b | Memória revisitada antes da rotina viva | 2 🔴 · 2 🟡 · 1 ⚪ | ✅ concluída |

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

---

# Auditoria #5 — Estado emocional

**Por que esta:** durante a auditoria #4 o Patrick perguntou se conversar deixava a Marina cansada. Para responder, abri o `estado_emocional` e encontrei carinho, brincadeira e intensidade romântica **todos em 1,0**, o máximo da escala. Emoção travada no teto não reage a nada do que o Patrick diz.

## Mapa

| Quem | O que faz |
|---|---|
| `planner.apply_plan_effects` | aplica `emotional_deltas` do plano (LLM ou heurística), ±0,05 por turno |
| `proactivity_service._update_state` | `aplicar_decay_emocional(0,05)`, **o único retorno ao baseline** |
| `world_context._emotional_context` | lê valor × multiplicador do ciclo e vira rótulo no prompt |
| `world_state.current_energy` | energia para a rotina (academia) |
| `proactivity._build_neutral_context` | carinho e bateria social para a mensagem espontânea |
| `bot.py` (voz) | estado emocional para a prosódia |

## Achado 5.1 🔴 — A emoção só subia

O retorno ao baseline só rodava quando a Marina mandava mensagem espontânea. Em 20–21/09 ela mandou **zero** (48 + 8 turnos do Patrick, 0 iniciativas). Os deltas de conversa carinhosa são quase sempre positivos, e as heurísticas do planner somam +0,01 a +0,04 a cada "oi amor". Sem nada puxando para baixo, bastaram uns 8 turnos para o carinho sair de 0,85 e bater em 1,0, e dali não saiu mais.

**Correção** (`db.py`):
- **Relaxamento pelo tempo**, com meia-vida de 6h, calculado na leitura a partir do `updated_at`. Não depende mais de a Marina mandar mensagem.
- **Retorno decrescente perto das bordas:** a menos de 0,30 do teto, um delta positivo rende proporcionalmente menos (o mesmo vale para negativos perto do piso). Um delta negativo perto do teto tem efeito integral, então uma briga derruba mesmo quando ela está no alto.
- `aplicar_decay_emocional` passou a partir do valor já relaxado; antes, gravar o valor bruto com `updated_at=agora` desfaria o relaxamento. A chamada na proatividade saiu.

Numa conversa carinhosa de 4h30 o carinho ainda sobe perto do máximo, o que é plausível. Depois ele volta sozinho: 0,94 em 3h e 0,88 em 12h.

## Achado 5.2 🟡 — Energia da rotina ignorava o ciclo

O prompt multiplicava a energia pela fase do ciclo (na menstrual, 0,75 × 0,45 vira "baixa"), mas a rotina da auditoria #4 usava o valor cru. Ela diria estar sem energia e iria à academia. `current_energy` agora aplica o mesmo multiplicador. Efeito: em fase de energia baixa, ela pula mais academia (na menstrual, cerca de metade dos dias da cota).

## Achado 5.3 🟡 — `playfulness` aparecia em inglês no prompt

O dicionário de rótulos não tinha `playfulness`, então o prompt recebia literalmente `- playfulness: muito alto / intenso`. Ganhou o rótulo "vontade de brincar e provocar".

## Achado 5.4 ⚪ — Nenhum registro dos deltas

Não havia como medir o viés dos `emotional_deltas`. O planner passa a logar `EMOTIONAL_DELTAS {...}` a cada turno, para uma auditoria futura saber se o Nemo só devolve números positivos.

## Achado 5.5 🟡 — A bateria social não era escrita por ninguém *(resolvido com desenho do Patrick)*

A bateria social ficava parada em 0,9 e o rótulo no prompt dizia "bateria social **para conversar**", o que abria espaço para o modelo interpretar bateria baixa como cansaço do Patrick. O Patrick definiu: é energia para sair e socializar com o círculo dela. Com ele, sobe ou desce conforme o tipo da conversa.

**Implementação** (`social_battery.py`):
- **Gasta pela agenda real**, a mesma da auditoria #4: aula −0,08/h, rolê/evento/casting −0,10/h.
- **Recarrega** em casa (+0,04/h), passeando com o Milo (+0,04/h) e dormindo (+0,09/h).
- **Integração preguiçosa** em `WorldStateManager.resolve()`: amostra a agenda em passos de 15 min desde a última conta, com clamp a cada passo. Um silêncio de 10h à noite conta como sono. A conta dá o mesmo resultado em uma consulta ou em várias. O primeiro rascunho somava tudo antes do clamp, e a noite "recarregava além de 100%" para compensar a aula do dia seguinte: 0,93 contra 0,36.
- **Com o Patrick:** o planner manda `emotional_deltas.social_battery`. Conversa leve ou carinhosa recarrega; briga, DR ou cobrança gasta. A regra no prompt do planner diz "NUNCA mexa nela pelo tamanho da conversa".
- A bateria **não relaxa pelo relógio** como as outras emoções: quem a move é o que ela faz.
- **No prompt**, o rótulo virou "pique pra gente e pra agito — não pro Patrick". Abaixo de 0,40 entra uma linha explícita: "Isso NÃO é cansaço do Patrick — com ele você fica mais caseira, dengosa e quietinha".

Terça simulada (aula 07h–15h): **1,00** ao acordar → 0,84 às 9h → 0,60 ao meio-dia → **0,36 ao chegar em casa** → 0,48 às 18h → 0,68 às 23h → cheia depois de dormir.

Falas de referência adicionadas à biblioteca (Registros 083–085, com autorização do Patrick para eu adicionar minhas sugestões de fala).

**Dívida observada na simulação:** às 15:00 em ponto ela aparece "em casa". A volta da Gávea para Botafogo (45 min) não existe como estado. Candidato para o world state: um estado de deslocamento depois de compromisso fora.

## Testes

`tests/test_emotional_state_audit5.py`, 6 testes:
- a emoção relaxa com o tempo sem proatividade;
- uma conversa longa não trava no teto;
- uma briga derruba o valor mesmo no alto;
- o decay legado não desfaz o relaxamento;
- a energia da rotina segue o ciclo;
- `playfulness` tem rótulo em português.

`tests/test_social_battery_audit5.py`, 5 testes:
- um dia inteiro na PUC esvazia a bateria e a casa recarrega;
- a conta não depende de quantas vezes foi consultada;
- conversa longa sem delta não gasta bateria;
- a bateria não relaxa pelo relógio;
- o prompt deixa claro que não é cansaço do Patrick.

`test_planner` foi atualizado: +0,03 sobre 0,85 agora rende 0,865, não 0,88.

Suíte: **538/539**. A única falha é a dívida conhecida.

---

# Auditoria #6 — Mundo social: a vida dela acontece?

**Por que esta:** o Patrick perguntou se a Marina fala com a Bia durante o dia. A resposta era não. As migrations foram adiadas para a #7.

## O que existia

| Peça | Estado encontrado |
|---|---|
| Círculo social canônico (9 relações, personalidade, bairro, temas de cada pessoa) | ✅ cadastrado, bem desenhado |
| `SocialWorld.record` (evidência de interação → proximidade, frequência, último contato) | ❌ nunca chamado; `social_evidence` com 0 linhas |
| `StoryEngine` (26 sementes, cadência, orçamento narrativo, eventos graves bloqueados) | ❌ nunca chamado; o próprio docstring dizia *"never run from current bot"* |
| `life_events`, `story_threads` | ❌ 0 linhas |
| Uso no prompt | só uma linha "Bia: best_friend; região" quando o Patrick citava o nome |

## Achado 6.1 🔴 — O mundo social era cadastro, não vida

"Falou com a Bia hoje?" era improviso do modelo, sem registro. Amanhã ela poderia contradizer. É a mesma perda de coerência das capturas de `/ruim`, agora no mundo social.

## Achado 6.2 🔴 — O StoryEngine, mesmo ligado, quase nunca dispararia

20 das 26 sementes exigem uma precondição observada (`friend_needs_support`, `academic_feedback_observed`...), e **nenhum** componente do sistema fornecia nenhuma delas. Além disso, as histórias sociais nasciam só com `participants=('marina',)`: "um contato conhecido pediu ajuda", sem saber quem.

## Achado 6.3 🔴 — Passeio do Milo marcado dentro do sono *(bug meu, da auditoria #4)*

Em dia sem aula ela dorme até 08:29, mas o slot do passeio podia cair às 07:05. O sono vence no `pick()`, então o passeio simplesmente não acontecia nesses dias. A tabela da semana que mostrei ao Patrick na #4 tinha "Sex: Milo 07:05", o que estava errado. Correção: `_placement` desconta a janela de sono do dia (`_sleep_windows`). Agora é sexta 08:30, sábado 09:45, domingo 09:40.

## Correção — `social_day.py`

O dia social é derivado da data e da agenda, do mesmo jeito que a #4 fez com academia e passeio.

**Encontros presenciais** dependem de onde ela **está**:
- Theo (75%) e Júlia (60%) na PUC, dentro de um bloco de aula;
- a professora Helena (50%) nas matérias de Projeto;
- a Carol na Bodytech, se ela foi mesmo treinar;
- a Dona Célia no prédio na hora do passeio com o Milo.

"Se foi mesmo" usa a regra do resolvedor: um snapshot de slot cobrindo o horário ou, sem ele, a agenda daquele momento com o filtro de conversa ativa. Se o Patrick estava conversando, ela não saiu, e o encontro não acontece.

**À distância**, depende de quem a pessoa é:
- a Bia em ~80% dos dias (almoço ou noite);
- o pai ~2×/semana (ligação ou mensagem, à noite);
- a Lívia ~1×/semana (dia útil, castings).

Resultado em 8 semanas, por semana: Bia 6,0 · Theo 2,6 · Júlia 2,5 · pai 2,2 · Dona Célia 2,0 · Carol 1,9 · Lívia 1,0 · Helena 0,8.

**Registro:** cada contato vira `life_event` (`social_contact`) + `SocialWorld.record` quando o horário passa. A materialização é preguiçosa em `WorldStateManager.resolve`, idempotente e cobre ontem e hoje. O assunto sai dos temas canônicos da pessoa (a Bia: relacionamentos, festas, fofocas; o Theo: faculdade, moda, crushes...).

**Sem passado inventado:** `social_day_start` é gravado no primeiro startup e nada anterior é materializado. Sem isso, o bot registraria de uma vez encontros de ontem e de hoje cedo que podem contradizer o que a Marina já contou ao Patrick nesses dias.

**Histórias:**
- Em ~35% dos dias um contato traz um **gancho** (a Bia desabafou, a Helena deu retorno, a Lívia mencionou um job). Ele fornece exatamente a precondição que o StoryEngine exigia e restringe a semente àquela pessoa. O StoryEngine ainda aplica a própria cadência (60% dos dias são banais) e o orçamento. Resultado: dias banais predominam, como o roadmap 3.6.2 pede.
- A história **nasce com a pessoa como participante**: `StoryEngine._start` ganhou `extra_participants`.
- De 1 a 4 dias depois, um novo contato com a mesma pessoa **continua ou resolve** o assunto via `continue_thread`, que já existia e nunca era usado.

**No prompt:**
- `[SEU DIA ATÉ AGORA — aconteceu de verdade]` lista os contatos de hoje e as histórias em andamento, com a instrução de usar só quando vier ao caso, não despejar a agenda e não contradizer nem inventar outro encontro.
- Quando o Patrick cita alguém, a linha da relação ganha "Último contato: hoje às 21:05 — Trocou mensagens com a Bia; assunto: relacionamentos." ou "Sem contato registrado recentemente."

Biblioteca: Registro 086 ("falou com a Bia hoje?" sem despejar agenda).

## Testes

`tests/test_social_day_audit6.py`, 7 testes:
1. Duas semanas de vida social coerente com a agenda (Bia em ≥8 dias; todo encontro na PUC cai dentro de um bloco de aula).
2. O primeiro startup não inventa passado.
3. A materialização é idempotente e só grava o que já passou.
4. O encontro na academia só acontece se ela foi (Patrick conversando → não foi → sem Carol).
5. O passeio do Milo nunca cai dentro do sono.
6. A história nasce com a pessoa e continua dias depois.
7. O prompt mostra o dia e o último contato de quem foi citado.

## Custo e desempenho

Uma resolução de estado leva ~165 ms. Na versão anterior às auditorias, medida num worktree do `HEAD`, eram **161 ms**: o acréscimo das auditorias #4–#6 é de 10–20 ms. O primeiro rascunho custava 249 ms e ganhou cache:
- plano social por (banco, dia, histórias abertas);
- linhas de rotina, grade e horários por instância do `RoutineEngine`;
- uma consulta só para os contatos já processados.

O custo alto real é antigo: **cada consulta abre e fecha uma conexão SQLite** (`db.get_connection`), cerca de 34 conexões por resolução. Fica registrado como candidato a auditoria de infraestrutura, junto com as migrations.

`test_world_context` teve o teto de tamanho do prompt ajustado de 11k para 12k: o bloco do dia é limitado a 5 contatos + 2 histórias (~700 chars).

Suíte: **545/546**. A única falha é a dívida conhecida.

## Pendente, próximo passo natural

- ~~Saídas presenciais com as amigas~~ → feito na parte 2.
- **Deslocamento como estado** (achado 5.5): a volta da PUC ainda é instantânea.

## Parte 2 — Fechando o mundo (pedido do Patrick: "ela tem 20 anos, garota popular, tem mais é que viver")

### Achado 6.4 🔴 — A proatividade viva mandava frases prontas, e parte do que eu corrigi era código morto *(erro meu nas auditorias #4 e #5)*

`autonomous_routine_v36`, o único caminho proativo em produção, escolhe um motivo via `RelationshipWorld.ranked_candidate` e manda **texto fixo**: quatro variações de "oi amor, como você tá?". O caminho que gerava a fala pelo LLM com contexto (`determine_proactive_prompt`) foi desligado na 3.7.0, e o `scripts/audit_prompt_authority.py` proíbe chamá-lo. A decisão foi correta na época, porque o mundo não tinha eventos reais e o LLM inventaria.

Consequência para mim: o achado 4.5 (aviso de saída), o 4.4 e o 4.6 (contexto e instruções da mensagem espontânea) e o `_build_neutral_context` da #5 corrigiram código que **não roda**. Eu corrigi sem verificar se estava no caminho de execução. As correções continuam válidas se o caminho voltar, mas não mudaram nada em produção.

**Correção:** `_proactive_text()` em `bot.py`. O motivo continua vindo do `ranked_candidate`, com as mesmas garantias de entrega. O texto passa a ser gerado pelo LLM:
- ancorado no estado e no dia registrado, com a instrução marcada "[INICIATIVA SUA — o Patrick NÃO mandou mensagem]";
- passando pelos mesmos guards das respostas (`_needs_retry_for_junk`, `_salvage_reply`, `_strip_assistant_politeness`);
- com fallback para a frase pronta antiga se falhar.

Há um motivo novo, `social_day_share`: um acontecimento das últimas 3h que ela ainda não contou (histórias primeiro) vira assunto. `mark_shared` impede que ela conte a mesma coisa duas vezes.

### Achado 6.5 🔴 — Com o Patrick conversando, ela nunca saía

O filtro de conversa ativa (Patch 013) bloqueia saídas enquanto o Patrick fala, contando com o aviso "vou levar o Milo, já volto". O aviso vivia no caminho morto. Além disso, a proatividade autônoma só dispara com o Patrick **ocioso**, então jamais poderia avisar no meio de uma conversa. Resultado: se o Patrick conversasse no horário da academia ou do passeio, ela simplesmente não ia.

**Correção:** `_maybe_announce_transition()` roda no pipeline de resposta. Quando um slot da agenda começa durante a conversa, a transição é registrada e a própria resposta recebe a instrução "[AVISO DE SAÍDA — faça nesta resposta]". Uma vez só. Depois, o `announced_transition` do WorldState a coloca lá até o fim do slot.

### Achado 6.6 🟡 — Privacidade: instruções em inglês e resposta pronta

- `KnowledgePrivacy.prompt_constraint` ia para o prompt em inglês ("[VERIFIED KNOWLEDGE POLICY] Do not reveal..."). Traduzido.
- `KnowledgeDialogue.prepare_replies`, quando o Patrick cita um assunto registrado, **pula o LLM** e manda frase pronta ("Sobre X: prefiro não falar sobre isso."). Esse caminho está dormente (nenhum assunto registrado) e continua assim: os segredos do dia social não registram aliases e usam o bloco do dia com a instrução "contado EM SEGREDO". **Dívida:** se um dia houver assuntos registrados, esse caminho precisa passar pelo LLM.

### Mais vida (decisão do Patrick)

- `STORY_EVENT_CADENCE_THRESHOLD`: 0,60 → 0,25. `HOOK_CHANCE`: 0,35 → 0,70.
- Até **2 histórias abertas** ao mesmo tempo (antes: 1, que travava tudo), nunca 2 com a mesma pessoa. Orçamento de intensidade semanal de 2 → 3.
- Continua valendo: no máximo 1 história nova por dia, e eventos graves bloqueados.
- A continuação passou a contar da **última** vez que o assunto apareceu. Antes, uma continuação que não resolvia deixava a história morrer (ia para `dormant`).
- Em duas semanas simuladas: **4–5 histórias**, todas com continuação e desfecho (antes: 1).

### Saídas com as amigas

Viram **compromissos confirmados** no `CalendarWorld`, criados até 6 dias antes, nunca com menos de 2h de antecedência e nunca retroativos:

| Dia | Chance | Saída |
|---|---|---|
| Sábado | 65% | Quartinho Bar, 21:00–23:59 (a Bia; às vezes o Theo) |
| Domingo | 40% | praia, 10:00–13:00 (a Bia ou a Carol) |
| Sexta | 35% | Quartinho Bar, 19:30–22:30 (o Theo; às vezes a Júlia) |
| Quarta e quinta | 25% | Starbucks da Gávea depois da aula (a Júlia/o Theo) |

O que já existia reage sozinho:
- o WorldState a coloca lá (`confirmed_commitment`);
- a disponibilidade fica `SOCIAL`, com praia e café adicionados ao mapeamento;
- a bateria social gasta (−0,10/h);
- os encontros presenciais são registrados.

O `CalendarWorld` recusa conflito com aula ou com outro compromisso. O prompt mostra "Plano combinado: Saindo com o Theo no Quartinho Bar (sexta, 19:30)", então ela sabe dos próprios planos. O lugar não é mais trocado por "local reservado" quando é uma saída do dia social.

### Segredos e amigos entre si

- **Segredos:** assuntos de relacionamento, crush, fofoca e conflito leve são contados em segredo em 35% das vezes. A proveniência vai para o `KnowledgePrivacy`: a pessoa observa → autoriza a Marina → share confirmado. A Marina fica com `CONFIDENTIAL`, e `decision(marina → patrick) = WITHHOLD`. O prompt marca "contado EM SEGREDO: você sabe, mas não conta os detalhes pro Patrick — no máximo diz que prometeu guardar". Biblioteca: Registro 087.
- **Amigos entre si:** às vezes a conversa com um amigo gira em torno de outro ("…e falaram da Júlia"). Quando o Patrick cita alguém, a linha da relação mostra "Conhece: …".
  - Theo ↔ Júlia: colegas de turma (sustentado pelo cânone, os dois ligados à PUC).
  - **Bia ↔ Theo: proposta de cânone minha** ("se conheceram nas festas por causa da Marina"). **O Patrick pode vetar.**

### Proteção do bootstrap

A inicialização limpa (`bootstrap_v36`) resolve o estado e depois exige zero memória. Com o dia social, esse resolve criava saídas na agenda e o bootstrap falhava ("Memória antiga remanescente: eventos_pendentes"). A materialização agora só roda depois de `clean_canonical_start_done`.

### Testes

`tests/test_social_day_audit6.py` subiu para 15 testes. Os novos cobrem:
- proatividade ancorada: guards, fallback e a instrução marcada como iniciativa dela;
- a novidade é contada uma vez só;
- o aviso de saída ao vivo;
- saídas viram compromisso e ela está lá (`SOCIAL`);
- saída nunca é criada em cima da hora;
- o segredo da amiga fica com a Marina (`WITHHOLD` para o Patrick, cadeia pessoa → Marina);
- os amigos falam uns dos outros só dentro dos vínculos declarados.

Atualizados porque codificavam a decisão antiga:
- `test_story_engine` (faixa de dias sem história: 55–75% → 15–45%);
- `test_knowledge_privacy` (textos em pt-BR);
- `test_relationship_world_v365` (patch de `_proactive_text`).

Suíte: **553/554**. A única falha é a dívida conhecida.

## Parte 3 — O círculo vivo: gente e lugares novos que podem virar cânone

O Patrick lembrou que o sistema, em teoria, fazia a Marina e os NPCs canônicos conhecerem gente não canônica, e que essas pessoas (e lugares) tinham chance de entrar no cânone.

### Achado 6.7 🔴 — O ciclo de descoberta e promoção existia inteiro e nunca rodava

- `SocialWorld.discover_person` e `discover_place` nunca são chamados.
- A promoção **existia**, dentro de `SocialWorld.record`: pessoa `ephemeral` → `secondary` depois de 3 dias com encontro bom → `recurring` depois de 6. Lugar `discovered` → `known` → `habitual` → `favorite`. Mas como `record` nunca era chamado, nada subia.
- `WorldHygiene.review_promotions` marca candidatos `PROMOTABLE` para revisão manual, e não existe comando para o Patrick aprovar.
- A passagem de `recurring` para cânone não existia.

### Correção

**Gente que ela pode conhecer**, onde a rotina já a leva (`NPC_POOLS` em `social_day.py`), com pesos 3/2/1 para que uma pessoa por lugar tenda a virar "a da turma":

| Onde | Quem | Ligado a |
|---|---|---|
| PUC (35% dos dias de aula) | Rafa (colega de Projeto), Duda (fotografia), Lara (Moda) | Rafa → Theo; Duda → Júlia |
| Bodytech (25% dos treinos) | Bruno (personal), Nanda (funcional) | Bruno → Carol |
| Passeio (20%) | Gabi (tutora da spitz), Seu Ademir (golden) | Seu Ademir → Dona Célia |
| Saídas (45%) | Caio (amigo da Bia), Luana (amiga do Theo) | Caio → Bia; Luana → Theo |

- **Primeiro encontro:** `discover_person` cria o NPC como `ephemeral`, e o registro diz "Conheceu a Gabi, tutora da spitz que brinca com o Milo". Os encontros seguintes dizem "Encontrou".
- **Laços com o círculo canônico:** entram em `FRIEND_TIES`, então a conversa com a Júlia pode girar em torno da Duda. O Patrick pediu o círculo "de alguma forma interligado quando fizer sentido".
- **Promoção a cânone:** quando o NPC chega a `recurring`, `_maybe_canonize` o trava no cânone (`canon_locked=1`, com o "quem é" como tipo de relação) e registra `canonized:<chave>` em `world_bootstrap`. O caminho automático para `close_npc` continua não existindo, por decisão do código original.
- **Lugares novos:** 30% das saídas de sexta vão para um lugar em descoberta (hamburgueria na Voluntários, barzinho no Humaitá, açaí na Praia de Botafogo). São ficção interna, sem endereço real. Cada visita alimenta a familiaridade via `SocialWorld.record`.
- **No prompt:** quando o Patrick cita um conhecido novo, a linha de relação aparece com "(conhecido(a) recente)".

### `/mundo`

Um comando novo mostra o mundo dela de fora:
- o círculo, com último contato e frequência em 30 dias;
- os conhecidos novos e o nível de cada um;
- os lugares em descoberta e a familiaridade;
- as histórias rolando e os próximos planos.

**Não mostra o assunto das conversas**, porque pode ser segredo de amiga.

Seis semanas simuladas: a Bia com 33 contatos no mês, o Theo com 18, a Júlia com 17. **A Gabi, do passeio, entrou no cânone.** Rafa, Bruno, Luana e Seu Ademir já são conhecidos; Duda, Caio e Lara acabaram de aparecer. Um lugar novo foi descoberto.

### Decisões do Patrick nesta parte

- Aceitou o vínculo Bia ↔ Theo proposto na parte 2 ("o ideal é que o círculo dela seja de alguma forma interligado quando fizer sentido").
- Os NPCs e os lugares da tabela acima são **propostas minhas de cânone suave**: só viram cânone de fato se a Marina conviver com eles.

### Testes

`LivingCircleTests`, com 4 testes:
1. O primeiro encontro cria o NPC e diz "Conheceu".
2. Seis dias de encontro fazem o NPC entrar no cânone (`secondary` no 3º dia).
3. O `/mundo` não expõe o assunto das conversas.
4. A saída de sexta pode descobrir um lugar novo, não canônico.

Suíte depois da parte 3: **557/558**. A única falha é a dívida conhecida. O teto de tamanho do `test_world_context` mede só a estrutura fixa: o bloco do dia social, que varia com a data, é isolado no teste.

---

# Auditoria #7 — Infraestrutura do banco: isolamento, conexões e migrations

**Por que esta:** o Patrick autorizou unificar as migrations. Na #6 medi que cada resolução de estado custava ~165 ms, quase tudo em abertura de conexão SQLite. Com o mundo vivo rodando a cada mensagem, isso pesa.

## Achado 7.1 🔴 — A suíte de testes gravava no banco de produção *(eu rodei assim a sessão inteira)*

`db.py` cria um `db_manager` global na importação, apontando para `marin_memory.db`. O projeto tem um runner isolado (`tests/run_isolated.py`, que aponta `MARINA_DB_PATH` para um banco descartável), mas nada impedia o caminho direto. Eu rodei todas as suítes desta sessão com `python -m unittest discover -s tests`. Os testes que usam os singletons do bot gravaram na produção.

Levantamento feito antes da limpeza, com backup em `backups/pre_test_pollution_cleanup_20260921_165631.db`:
- **Intacto:** conversas (a última é real, 13:29), memórias, schema 19, emoções exceto a bateria.
- **Poluído pelos testes da #6:**
  - 2 saídas agendadas (café com a Júlia, bar com a Bia);
  - o marco `social_day_start`, gravado às 15:54, quando deveria nascer no startup do bot;
  - a bateria social (0,90 → 0,97) e o marco de contagem dela;
  - 55 snapshots de `world_state` da tarde, com o bot desligado.

Tudo foi removido ou restaurado.

A auditoria #3 já tinha achado a mesma causa para o log (achado 3.6). Aquela correção isolou só o arquivo de log.

**Correção:** `db._resolve_db_file()`. Sob teste (`python -m unittest` ou pytest) e sem `MARINA_DB_PATH` explícito, o banco global é um arquivo descartável na pasta temporária. `test_suite_nunca_usa_o_banco_de_producao` trava isso. A suíte seguinte foi verificada com hash MD5 do `marin_memory.db` antes e depois.

**Descoberto no caminho:** importar `db.py` roda as migrations na produção. É assim por desenho (o bot migra no startup), mas qualquer script que importa `db` sem `MARINA_DB_PATH` também migra. Aconteceu nesta auditoria: um teste manual da migration 020 importou `db` e tentou aplicá-la na produção. Falhou antes de gravar (ver 7.4), e a verificação posterior confirmou schema 19, a coluna presente e a integridade ok.

## Achado 7.2 🔴 — Uma conexão nova por consulta: meio segundo por mensagem

`get_connection()` abria uma conexão por consulta e fechava no fim. Medição por etapa:

| Etapa | Custo |
|---|---|
| abrir | 0,6 ms |
| PRAGMAs | 0,05 ms |
| **1ª consulta** | **4–5 ms** (o SQLite relê o schema inteiro: dezenas de tabelas, índices, FTS) |
| fechar | 1,7–2,6 ms |
| consulta numa conexão reaproveitada | **0,04 ms** |

**Correção:** `_ReusedConnection`, uma conexão por thread mantida aberta, com commit/rollback no `__exit__` (mesma semântica do `with`), sem fechar.
- Ligada no startup do bot (`memory_manager.db.enable_connection_reuse()`) e desligada por padrão: os testes criam bancos em pastas temporárias, e conexão aberta trava arquivo no Windows.
- `close()` fecha todas.
- Uma conexão reaproveitada que aparecer com transação pendurada leva rollback e warning: nunca deveria acontecer, porque todo uso no código é `with`, o que foi verificado.

| Medida | Antes | Depois |
|---|---|---|
| Resolução de estado | 173 ms | **4 ms** |
| Montagem do prompt (banco de produção copiado) | 588 ms | **38 ms** |

## Achado 7.3 🟡 — Schema fora das migrations, rodando a cada startup

Três remendos em `_run_migrations`, todos com `except: pass`:

| Remendo | Situação |
|---|---|
| `ALTER TABLE fatos_patrick ADD COLUMN last_decay_at` | redundante: já está na migration 007 |
| `DELETE` de resumos duplicados + `CREATE UNIQUE INDEX idx_resumos_intervalo` | redundante: está na 007. O `DELETE` varria a tabela a cada startup |
| `ALTER TABLE reminders ADD COLUMN offer_message_id` | **não estava em migration nenhuma**: a coluna existia só por causa desse remendo |

**Correção:** a migration `020_reminder_offer_message.sql` cria a coluna, e os três remendos saíram. O replay de ADD COLUMN duplicada ganhou a versão 20, porque bancos antigos já têm a coluna. O schema agora tem uma fonte só (`migrations/*.sql`), travada por `test_schema_tem_uma_fonte_so`.

## Achado 7.4 🟡 — O replay de migration quebrava com `;` dentro de comentário *(bug meu, do Patch 032)*

O replay divide o SQL em `;` e só depois remove comentários. Um `;` no meio de uma frase de comentário partia o texto, e o resto do comentário virava "statement" (`near "o": syntax error`). Apareceu na primeira versão da 020. Correção: os comentários saem **antes** da divisão.

## Pendente registrado

- `eventos_pendentes` id 2, "medico", tem como descrição a própria mensagem do Patrick ("A gente é né amor ksksksk…"). É uma extração ruim do planner, de uma conversa real às 12:37. Candidato para uma auditoria do planner e dos eventos.

## Testes

`tests/test_infra_audit7.py`, com 8 testes:
- a suíte não usa o banco de produção;
- a mesma thread reaproveita a conexão e faz commit;
- uma exceção faz rollback;
- threads diferentes têm conexões diferentes;
- a transação em lote continua atômica;
- o schema tem uma fonte só;
- um banco novo tem a coluna da 020;
- um banco antigo com a coluna avulsa migra sem erro.

Atualizados de 19 para 20: `test_bootstrap_v36`, `test_social_world`, `test_world_repository`.

### Testes que só passavam por causa do banco de produção

Com a suíte isolada, 3 testes de `test_prompt_language_audit2` (meus, da Auditoria #2) quebraram: eles montavam o prompt pelo `context_builder` global, ou seja, com a World Bible e o estilo aprendido do banco real. Agora montam num banco temporário com o cânone semeado. O rótulo `[COMO O PATRICK ESCREVE]` saiu da lista de obrigatórios, porque só existe com estilo aprendido. A ausência da versão em inglês continua travada.

Prova de isolamento: o MD5 do `marin_memory.db` é idêntico antes e depois da suíte completa (`f6684b66…`).

## Achado 7.5 🟡 — O conteúdo de `[COMO O PATRICK ESCREVE]` seguia em inglês *(resto da Auditoria #2)*

Na #2 traduzi o rótulo do bloco, mas não os campos gerados por `StyleEngine.get_learned_style_summary`: "Laugh pattern:", "Frequent emojis:", "Shared slang:", "Writing rhythm:". Achei isso ao conferir, no código, o item C1 do plano de voz. Os campos foram traduzidos (risada, emojis que ele mais usa, gírias em comum, ritmo de escrita) e travados por `LearnedStyleContentLanguageTests`.

O `PLANO_VOZ_MARINA_V371.md` ganhou um painel de status (seção 0): cada fase foi conferida no código, com a lista do que foi entregue fora do plano e as pendências reais.

Suíte final da #7: **565/566**, com o hash do banco de produção idêntico antes e depois.

---

# Auditoria #8 — Planner, eventos e lembretes

**Por que esta:** era a pendência mais concreta do painel. Havia um evento "médico" com o texto cru da mensagem do Patrick como descrição. Lembrete é confiabilidade pura: uma namorada que lembra da coisa errada quebra a ilusão rápido.

## Preparação — o reset do soak não conhecia o mundo vivo

O `reset_soak_learning` foi escrito antes da #6. Ele apagava as tabelas de vida, mas preservava (corretamente, porque ali mora o cânone) as tabelas onde o mundo vivo também grava. Depois de um soak, o reset deixaria:
- a Gabi canonizada **sem nenhuma lembrança de como a Marina a conheceu**;
- os lugares de ficção descobertos;
- as marcas do dia social;
- a convivência da Bia com 33 contatos que nunca aconteceram.

**Correção:**
- O reset remove NPCs (`npc_*`) e as relações deles, lugares de ficção interna, marcas em `world_bootstrap` (`social_day_start`, `skip:`, `story_day:`, `canonized:`) e preferências aprendidas (`canon_locked=0`).
- A convivência com o círculo canônico volta ao ponto de partida (0,75).
- O modo de teste do `reset_soak.py` passou a mostrar essas linhas.
- A lista de "preservados" mostrava `calendar_events` e `avatar_atual` como "(ausente)", tabelas que não existem neste schema, o que sugeria perda de dados. Foi corrigida: o avatar e o DNA visual moram no código (`visual_profile.py`).

Teste: `SoakResetTests` (2 semanas de mundo vivo com NPC canonizado → reset → cânone intacto, resto zerado).

## Achado 8.1 🔴 — O dentista do Patrick virou compromisso da Marina

O caso real, de 21/09 às 12:34: o debouncer juntou duas mensagens num lote só.

> A gente é né amor ksksksk tô falando exatamente isso, que qualquer coisa você me lembra
> Em falar em me lembrar, quarta-feira eu tenho dentista, 10h

`detect_explicit_scheduled_event` foi escrito para uma frase por vez:
- O corte "até a palavra *tenho*" usava `^.*?` sem DOTALL, e o `tenho` estava na 2ª linha. **Nada foi cortado.**
- A remoção do horário exigia "às 10h", e o "10h" solto ficou.
- A descrição virou o **lote inteiro**.
- A regra de "compromisso do casal" procura "a gente" na descrição, e o lote começava com "A gente é…". O evento ficou com **dono Marina, confirmado, no apartamento dela**.

Consequências se o bot estivesse ligado:
- Na quarta, das 10h às 12h, o `CalendarWorld` colocaria a Marina "em um compromisso" em casa (o dentista **dele**). A disponibilidade a deixaria ocupada.
- O lembrete das 9h mandaria o texto cru ("amor, passando pra te lembrar: A gente é né amor ksksksk…").

**Correção:**
- O detector olha **só o trecho do lote** que tem o gatilho e o tipo de evento (a negação também é avaliada no trecho).
- A descrição sai limpa, sem dia e sem hora: "dentista", "prova", "consulta no cardiologista".
- O resultado leva `owner: patrick_ramos` explícito ("eu tenho" é dele).
- Em `apply_plan_effects`, o dono explícito vence a heurística de palavras.
- Programa do casal ("assistir ao filme juntos") continua sendo do casal.

O registro ruim da produção (evento id 2 e o lembrete dele) sai com o reset do soak.

## Achado 8.2 🔴 — Resposta-lixo sem salvamento era enviada assim mesmo

Depois de uma resposta ruim (artefato de debug, proposta de ligação, outra língua), o pipeline tenta de novo. Se a segunda tentativa também é ruim, tenta salvar cortando a frase problemática. Se **nada** sobra (a resposta inteira era "Posso te ligar na hora?"), o código seguia com a resposta ruim e **enviava**.

**Correção:** `_safe_fallback_reply()`. Se o turno era de confirmar lembrete, a fala segura é a própria confirmação ("Combinado, amor! Te mando mensagem aqui no Telegram às 09:30 💕"). Senão, "Amor, deu uma bugadinha aqui kkk me manda de novo?".

## Achado 8.3 🟡 — Confirmação de lembrete sem garantia do horário

Quando o Patrick aceita um lembrete oferecido ("pode me lembrar uma hora antes"), o lembrete era registrado certo no banco (09:30), mas a confirmação ficava inteira com o LLM, sem garantia de citar o horário nem o canal.

**Correção:** a fala continua sendo do LLM, e se ela não citar o horário (`_mentions_clock` aceita 09:30, 9:30, 9h30 e, na hora cheia, 9h), é acrescentado "Te mando mensagem aqui no Telegram às HH:MM 💕". É o mesmo padrão que já garantia a pergunta de oferta e a de esclarecimento.

**Dívida quitada:** `test_offer_acceptance_does_not_leave_second_direct_reminder_pending`, que falhava desde **antes** das auditorias, passa. Ele exigia exatamente isso: "09:30", "mensagem aqui no Telegram" e nada de "ligar".

## Testes

`tests/test_planner_events_audit8.py`, com 7 testes:
- o lote real vira "dentista" do Patrick;
- a descrição sai sem dia nem hora;
- a negação só vale no trecho do compromisso;
- o compromisso do Patrick não ocupa a Marina (`CalendarWorld.current` = None na quarta às 10:30);
- o programa do casal continua sendo do casal;
- o fallback seguro nunca propõe ligação;
- o horário é reconhecido em vários formatos.

Suíte: **575/575**, a primeira totalmente verde desde o início das auditorias. O hash do banco de produção ficou idêntico antes e depois da rodada.

---

# Auditoria #9 — Arena de modelos no OpenRouter

**Por que esta (pedido do Patrick):** depois das auditorias #1–#8, o mundo, o prompt e o pipeline estão certos, mas a Marina seguia conversando mal. A sessão de 21/09 (mistral-nemo) inventou "cara de mistério", perguntou "como vai passar a tarde" às 18h51, perguntou do chefe no dia de folga, respondeu a foto como se fosse o Patrick e disse "desculpa não ter contado… acabei de terminar agora" estando na academia. Faltava escolher o modelo com teste real, não com achismo.

## A arena

`scripts/model_arena.py` roda a Marina **de verdade**: `process_incoming_batch` / `handle_photo_message`, planner, guards, segmentação em balões. A conversa segue um roteiro fixo, e só o modelo muda.
- **Cópia do banco:** cada corrida é um subprocesso com a sua própria cópia (backup SQLite read-only da produção). A conversa e o estado transitório são zerados, e o mundo, o cânone e as memórias ficam intactos.
- **Relógio congelado:** `scripts/scripts_clock.py` troca `datetime` antes dos imports do bot. Todo módulo vê o horário do cenário.
- **Nada sai do simulador:** nada vai para o Telegram nem para o `marina.log`. Visão, foto e voz são stubs; a voz entra como "[áudio] fala" na transcrição.
- **Registro por chamada:** cada chamada ao LLM registra quem chamou, a latência, os tokens, o custo em US$ e o provedor.
- **Relatório:** `scripts/model_arena_report.py <run> --transcripts` mostra as transcrições lado a lado e as métricas.

Cenários (`scripts/model_arena_scenarios.py`):

| Cenário | O que mede |
|---|---|
| `noite_domingo` | replay fiel da sessão real de 21/09 |
| `dia_dela` | uso do mundo vivo (dia, Bia, Theo, saudade) |
| `desabafo` | empatia sem virar terapeuta |
| `memoria_curta` | lembrar chefe, promoção, coordenador e sexta 30 min depois |
| `lembrete` | oferta, confirmação às 9h e pergunta depois |
| `brincadeira` | ciúme do Theo, Botafogo, filme favorito, Paris |
| `manha_de_aula` | coerência com a agenda (matéria, local) |

**Rodada 1 (triagem):** 18 modelos × 3 cenários. **Rodada 2 (final):** 9 modelos × 7 cenários × 2 repetições = 126 corridas. As duas somaram menos de US$ 5.

## Achado 9.1 🔴 — Foto: a Marina respondia a si mesma

O payload da foto não tinha o turno do Patrick. A foto só existia no system prompt, e a última mensagem era a pergunta da própria Marina ("E o que seu chefe disse…?"). O modelo continuava o texto como se fosse o Patrick: "Não contei, ele não sabe, eu só trabalho meio período mesmo" (21/09 19:02).

**Correção:** a foto entra como mensagem `user` no fim do payload. Na arena, com o próprio Nemo, a resposta passou a comentar Harry Potter.

## Achado 9.2 🔴 — Plano malformado derrubava o turno inteiro

O Gemma 4 devolveu `{"intent": -1, "event_details": -1, …}`. `event_details.get` explodiu e o Patrick ficou **sem resposta**.

**Correção:** `planner._sanitize_plan`. Tipo errado vira o padrão (texto → None, flag → False, objeto → None, deltas não numéricos descartados). Plano é conselho, não pode matar a conversa.

## Achado 9.3 🔴 — Áudio espontâneo como primeira fala depois do boot: KeyError

Há 6% de chance de a resposta sair em áudio. `ULTIMAS_MENSAGENS_MARINA[chat_id]` só era criado por `send_human_messages`. Se a primeira fala depois de ligar o bot fosse áudio, dava KeyError **depois** do envio, e o turno não era gravado (o GPT-5.6 Luna caiu nesse caso na arena).

**Correção:** `setdefault`.

## Achado 9.4 🟡 — Filtro de alfabeto estrangeiro só conhecia algumas faixas

"Como foi a conversa com ele? ್ದೇಶ" (canarês, Luna) passou.

**Correção:** qualquer letra fora do latino conta (emoji não é letra).

## Achado 9.5 🟡 — Garantia de horário redundante

"às 09h", "às 9" e "9 da manhã" não eram reconhecidos. A confirmação ganhava um "Te mando mensagem aqui no Telegram às 09:00 💕" repetido.

**Correção:** `_mentions_clock` aceita essas formas.

## Achado 9.6 🟡 — Nenhum controle de raciocínio; modelo reserva fixo no código

- Modelos como Gemini 3.x Flash **recusam** `reasoning.enabled=false` (HTTP 400). Todas as chamadas falhavam e a Marina só dizia "deu uma osciladinha no sinal".
- Modelos híbridos podem raciocinar por padrão, gastando latência e o orçamento de 160 tokens da fala.
- O reserva era `"mistralai/mistral-nemo"` escrito em dois lugares do bot.

**Correção:** `llm_options.llm_kwargs()` em todas as 12 chamadas de LLM (bot, planner, consolidador, reflexão), mais `LLM_REASONING` (off | minimal | low | medium) e `LLM_FALLBACK_MODEL` no `.env`. O que a arena testou é exatamente o que a produção manda.

## Achado 9.7 🔵 — O cânone não tem gostos da Marina

`gostos_marina` está vazio. Perguntados sobre o filme favorito, os modelos responderam Harry Potter, Amélie Poulain, Questão de Tempo, Clube da Luta, Orgulho e Preconceito, Como Se Fosse a Primeira Vez e O Diabo Veste Prada. Nenhum errou: não existe resposta. Mas cada conversa inventa um gosto novo, e com o tempo isso vira contradição. **Decisão do Patrick:** definir os gostos-base dela (filme, série, música, comida…).

## Achado 9.8 ⚪ — O planner roda antes da resposta e soma latência

O turno mede de 7 a 18 s do início ao fim, contra 1,4 a 3 s da chamada da fala. Boa parte vem do planner, que é sequencial. Fica registrado para uma auditoria de latência.

## Resultado

### Eliminados na triagem (com o que se viu)

- **mistral-nemo:** tokens estrangeiros ("álního", "knives", "RT"), "você deve estar bem **cansada**" para o Patrick, "quer que eu vá com você para a empresa?".
- **unslopnemo-12b:** inventou "acabei de sair do cinema com a Ju", caracteres de controle, "town".
- **cydonia-24b:** "amiingh", "Tens", "o melhor fornecedor de melhora do Rio".
- **llama-4-maverick:** "kkkk calma, amor" para briga com a mãe; alucinou estar vendo Harry Potter junto.
- **deepseek-v3.2:** "esses dias de TPM com ela".
- **qwen3-235b:** repetiu a mensagem do Patrick como se fosse dela.
- **minimax-m2-her:** "(Fotos enviada por Marina)", "vc ficou chateada?", palavrão gratuito.
- **gemma-4-31b:** quebrou o planner (9.2); "Quem? Que doideira é essa" num desabafo.
- **claude-haiku-4.5:** "kkk por quê?" para "tô meio pra baixo"; 20× o custo do DeepSeek.
- **grok-4.3:** seco e caro.

### Final (7 cenários × 2 repetições)

| Modelo | Fala (s) | Turno (s) | US$/turno | ~US$/mês* | Pontos fortes | Pontos fracos |
|---|---|---|---|---|---|---|
| **openai/gpt-5.6-luna** | 1,4 | 9,0 | 0,0015 | ~7 | **o mais fiel**: lembrou promoção/coordenador/sexta nas 2 repetições, agenda exata, honesto quando não sabe ("a gente nunca definiu meu favorito"), provedor único | um pouco "certinho"; 1 vazamento de canarês (agora filtrado); a OpenAI pode recusar conteúdo íntimo explícito |
| google/gemini-3.8-flash | 2,4 | 10,8 | 0,0054 | ~24 | **mais personalidade e emoção** ("Para com isso, Patrick. Se não puder desabafar comigo vai desabafar com quem?"), flerte natural | raciocínio obrigatório; 3,5× o custo do Luna; às vezes sai do mundo (pilotis em horário de aula) |
| moonshotai/kimi-k2.5 | 3,1 | 17,6 | 0,0035 | ~16 | usa muito bem o mundo (Quartinho, Nilton Santos, Milo) | concordância ("quer que eu te mando"), lento, 5 provedores |
| deepseek/deepseek-v4-flash | 3,2 | 17,9 | 0,00036 | ~2 | a gíria mais natural, a mais barata | **inventa memórias** nas 2 repetições ("o cara que te chamou de 'jovem' no primeiro dia"); 14 provedores diferentes; lento |
| z-ai/glm-4.7 | 4,2 | 20,0 | 0,0025 | ~11 | ok | inventa ("ele é meio tenso"), o mais lento, "then" |
| google/gemini-3.1-flash-lite | 1,7 | 7,8 | 0,0019 | ~8 | o mais rápido | genérico/atendente, fugiu da pergunta de memória |
| mistralai/mistral-medium-3.1 | 1,6 | 7,2 | 0,0019 | ~9 | conciso | 4 vazamentos ("treating", "'auteur", "organized") |
| mistralai/mistral-small-2603 | — | — | — | — | — | limitado pelo provedor (429) nas duas rodadas |

\* estimativa com 150 turnos/dia; inclui planner, consolidação e reflexão.

## Testes

`tests/test_model_arena_audit9.py`, 11 testes:
- a foto é o último turno do Patrick;
- plano com tipos errados vira o padrão;
- plano bom passa intacto;
- JSON-lixo no planner não derruba;
- `llm_kwargs` com raciocínio off e obrigatório;
- canarês dispara retry;
- horário já citado não ganha frase repetida;
- o relógio congelado vale para imports feitos depois.

Suíte completa: **584/584**. A arena só lê a produção (backup read-only); todos os testes rodam em banco descartável.

## Achado 9.9 🔴 — `/feedback` gravava no banco e ninguém lia

O comando existe desde as primeiras versões: grava a observação do Patrick em `feedbacks` com status `pendente` e responde "Anotado com muito carinho". O único trecho que levava esses pedidos ao prompt era `memory.get_contexto_emocional()`, marcado como *legacy* no próprio corpo e **sem nenhum chamador em produção** desde a migração para o Living World — sobrou apenas numa fixture de teste. Todo `/feedback` do soak virou registro morto, inclusive o de 22/09 ("Não é necessário que toda mensagem termine com emojis"), que ficou dois dias no banco sem efeito.

**Correção:** os pedidos pendentes entram em `WorldContextBuilder.build()` como último bloco antes do histórico — posição de ordem direta, não de enriquecimento — e saem quando o status deixa de ser `pendente`/`em_andamento`. Limite em `PATRICK_FEEDBACK_MAX` (8).

## Achado 9.10 🟡 — Emoji em toda fala, sempre no fecho

Medido nas 15 falas do dia: **15 de 15** levavam emoji, média 1,2 por fala, 40% fechando com emoji e 😘 respondendo por 9 dos 21. A regra do prompt ("emojis com moderação, nunca um por frase") era respeitada ao pé da letra por um modelo que escreve tudo corrido: uma mensagem, um emoji, sempre.

**Correção em dois lados**, como nas bolhas:
- **prompt:** regra contável — no máximo um por turno, maioria dos turnos sem nenhum, nunca fechar todo turno com emoji, nunca repetir o mesmo emoji dois turnos seguidos;
- **entrega:** `thin_emojis()` poda o excedente e deixa o fecho seco na maioria dos turnos, com o mesmo sorteio determinístico do ritmo de balões. O emoji preservado é o **primeiro**: é ele que marca o pivô da batida em `_split_sentences`, e podar pelo começo desmancharia o segundo balão. Kill switch em `VOICE_EMOJI_BUDGET`.

Nas falas reais do dia: com emoji **100% → 73%**, média **1,2 → 0,8**.

`tests/test_emoji_budget.py`, 14 testes (teto por fala, emoji composto com ZWJ intacto, pivô ainda virando dois balões, fecho estável por fala, kill switch, feedback pendente no prompt, feedback resolvido fora dele). Suíte completa: **657/657**.


---

# Auditoria #10 — Revisão do soak de 22/09 (volta do plantão)

**Data:** 2026-09-23
**Pergunta:** o que a conversa real de 22/09 (139 mensagens, 17h–22h31, Luna) mostra de errado?
**Fonte:** `scratchpad/conversation_export_20260922_230601.txt` + banco de produção.

## Achado 10.1 🔴 — "A função tá em manutenção" apareceu sem pedido de foto

Patrick escreveu "o importante vai ser **ver você** feliz se divertindo na sua sexta". `is_photo_request` casava "ver você" solto, e a instrução de foto indisponível falava em "manutenção" — ela repetiu a palavra, falando como sistema. O áudio tinha o mesmo defeito ("adoro sua voz", "te mandei um áudio" pediam mensagem de voz).

**Correção:** pedido de mídia exige verbo de pedido perto do objeto (`_FOTO_PEDIDO_RE`/`_AUDIO_PEDIDO_RE` em `bot.py`), com intervalo que não aceita "te/eu/mandar/mostrar" (o Patrick oferecendo mídia dele não conta). A instrução de indisponibilidade pede desculpa de gente e proíbe falar em manutenção, sistema, app ou função. `tests/test_media_request_detectors.py`.

## Achado 10.2 🔴 — O jantar prometido seis vezes que nunca aconteceu

"Vou comer agora" às 21h14, 21h15, 21h18, 22h13, 22h26 e 22h31, respondendo em 6 s entre uma promessa e outra. O mundo ficou em "curtindo a noite em casa": não havia refeição na rotina, e o que ela dizia que ia fazer não mudava o estado.

**Correção:** `meals.py` — fala dela com anúncio imediato de refeição abre `pending_transition_json` ("jantando em casa", 20–35 min), a disponibilidade ganha o perfil `MEAL` (45 s–8 min) e o prato vira `life_event` do tipo `meal` no [SEU DIA ATÉ AGORA]. **Limite conhecido:** na arena (`companhia_caminho`) o Luna ainda **inventou** um jantar quando nenhum existia → a refeição precisa ser rotina, não só promessa (Fase D1).

## Achado 10.3 🔴 — Zero banhos no dia

O banho só existia se a mensagem de ritual saísse, e ela disputava o teto de 2 cotidianos (aula e Milo já tinham gastado), tinha 45% de chance e era proibida com conversa rolando — justo a janela do banho.

**Correção (v1):** banho é rotina do mundo em `rituals.py` (noite + pós-treino, ≥ 3 h entre banhos); o aviso é opcional, sai do teto e sempre acontece com conversa rolando; "vou tomar banho, já volto" dito na conversa vira banho. A v2 (sem teto, por necessidade e emoção) está na Fase D4.

## Achado 10.4 🟡 — Eco em vez de companhia

Numa viagem de 2 h ela devolveu o que ele dizia ("saga" ~10×, "me avisa quando chegar" ~8×) e, ao "diz aí", perguntou "o que você quer saber?". O prompt de voz era 100% reativo.

**Correção:** duas regras em `[VOZ DA MARINA]` (vida própria quando ele só faz companhia; cuidado pedido uma vez, sem bordão). Arena `companhia_caminho` (2 corridas, Luna): "saga" e "me avisa" sumiram, a chuva foi respondida; ainda troca o bordão ("expedição") e fecha quase tudo com pergunta. A causa de fundo é mundo pobre → Fase D (rotina viva) e D12 (laços).

## Achado 10.5 🔵 — "o que eu papou", misreading de "aí não tá chovendo?"

Deslizes do modelo; sem correção de código. Registrados para a próxima arena.

Suíte: **676/676** após o ajuste de tamanho do prompt.

---

# Auditoria #2b — Memória revisitada antes da rotina viva

**Data:** 2026-09-23
**Pedido do Patrick:** garantir que a memória não tem bug e não vai atrapalhar a Fase D.
**Por que de novo:** desde a #2 o modelo virou o Luna, o `/feedback` foi achado morto (9.9) e a rotina viva vai multiplicar os acontecimentos do dia.

## O retrato de uma noite

Em 22/09 (uma noite de conversa) a memória gravou **24 fatos, 20 "momentos marcantes", 18 resumos e 11 pendências**. O prompt só usa 3 fatos, 2 momentos e 1 resumo por turno — o volume não incha o prompt, mas **dilui**: as vagas vão para ruído.

## Achado 2b.1 🔴 — Pendências de conversa viravam check-in proativo dias depois

"Me avisa quando chegar" virava `open_loop` com check-in em **+48 h** (o planner usa 48 h quando a dica é descritiva) ou **+24 h** (o banco completa quando vem vazio). Pendência aberta nunca vencia — só as resolvidas eram arquivadas. Resultado: 9 pendências de 22/09 abertas, com check-in marcado para 24/09 19h39, e o `proactivity_service` dispara mensagem espontânea em `open_loop_ready`: ela perguntaria "chegou em casa?" dois dias depois. E o planner reabria a mesma pendência a cada turno ("Patrick avisar quando chegar em casa" ×4).

**Correção:**
- `waiting`/`promise` sem data explícita são **pendências curtas**: sem check-in, somem do prompt em 12 h e a higiene as abandona (`SHORT_LIVED_LOOP_TYPES`, `vencer_open_loops_curtos`). Projetos mantêm o contrato P2.1 (+24 h).
- Pendência aberta parecida (mesmo tipo, Jaccard ≥ 0,5) é **tocada, não duplicada**.
- `abandonar_open_loop` grava `resolved_at` — antes os abandonados nunca eram arquivados.

## Achado 2b.2 🔴 — Fatos tirados da boca da Marina, e fatos sobre ela

- "Patrick **costuma** comer macarrão com frango" e "tem teclado RGB e gosta de atmosfera gamer" saíram da **fala dela** sobre uma foto dele — uma observação, interpretada por ela, virou hábito dele.
- "Marina pretende passar a tarde em casa" foi gravado em `fatos_patrick`: a vida dela vazando na memória dele — exatamente o risco da Fase D.
- Uma noite virou "costuma avisar Marina durante o trajeto" (×2).

**Correção no prompt do consolidador (DE ONDE VEM A EVIDÊNCIA):** só o que o Patrick diz é evidência; fala da Marina é contexto; nunca fato sobre a Marina; uma ocorrência não é hábito ("costuma" só se ele disser que é recorrente); narração do momento é `ignore`; padrão de relacionamento já conhecido é `same`.

**Validação real (Luna, cópia do banco sem os fatos ruins, lotes de 22/09):** foto do jantar → **nenhum** fato; viagem → **nenhum**; escala 12x60 → guardada (com os próximos plantões calculados); aparelho → manutenção como contextual + ansiedade como fato; dentista → data absoluta correta. Detalhe revelado no teste: com os fatos ruins ainda ativos, o Luna os **reconfirmava** ("same") — por isso a limpeza do banco é parte da correção.

## Achado 2b.3 🟡 — Data relativa congelada e fato contextual eterno

"Consulta com o dentista **amanhã** às 10h30" continuaria ativo — e errado — para sempre: nada expirava `contextual`, e o texto guardava "amanhã". Além disso, a data de referência era a da consolidação, não a da conversa (um lote atrasado converteria "amanhã" para o dia errado — reproduzido no replay: virou 24/09).

**Correção:** o consolidador recebe `HOJE:` com a hora da **última mensagem do lote** (o lote de `bot.py` passou a levar `timestamp`) e deve escrever data absoluta; a higiene desativa `contextual` com mais de 3 dias (`expirar_fatos_contextuais`).

## Achado 2b.4 🟡 — Momentos marcantes do dia a dia

20 "momentos marcantes" numa noite ("Patrick saiu do trabalho e avisou que estava indo para casa"). O prompt não definia o que é marcante. **Correção:** só o que o casal lembraria daqui a meses; em geral zero por diálogo.

## Achado 2b.5 ⚪ — Resumos por lote de 8 mensagens

18 resumos na noite, `topic` = `summary`. Por design do consolidador (um resumo por lote); o prompt usa só o mais recente. Registrado, sem mudança.

## Limpeza do banco de produção

Backup: `backups/pre_audit2b_memory_20260923_012559.db`.
- **8 fatos desativados:** 17 (sobre a Marina), 37 e 38 (interpretação dela sobre a foto), 30 e 34 (uma noite virou "costuma"; duplicavam o 35), 20, 22 e 32 (narração do momento).
- **Fato 27:** "amanhã" → "23/09/2026 às 10h30".
- **8 momentos desativados** (narração da viagem: 3, 4, 5, 8, 12, 13, 14, 17).
- **9 pendências abertas abandonadas** (todas de 22/09).
- Ficaram 15 fatos, 12 momentos e 0 pendências abertas.

`tests/test_memory_audit2b.py`, 10 testes (pendência curta sem check-in, deduplicação, vencimento em 12 h, projeto mantém 24 h, abandonado arquivável, dica descritiva sem data, contextual expira em 3 dias, higiene roda as expirações, regras no prompt, `HOJE` com a data da conversa).
