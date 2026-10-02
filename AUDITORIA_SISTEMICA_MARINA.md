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

# Auditoria #11 — Conversa de 23/09 (tarde) a 24/09 (manhã)

Pedido do Patrick antes do restart: "dá uma olhada no histórico… temos vários problemas". Método: conversa inteira (`conversas`) cruzada com o mundo dela no mesmo horário (`world_state`, `life_events`, `eventos_pendentes`) e com o log. Tudo numa **cópia** do banco real (`marin_memory.db`).

## Achado 11.1 🔴 — A história continuou de onde a conversa parou, não de onde o mundo estava

16:10 no Starbucks com a Júlia → o café acaba às 16:45 → volta de metrô, em casa às 17:25 → passeio com o Milo. Às 18:11: "ainda tô aqui com a Júlia"; às 18:19: "tô voltando de metrô". O estado atual dizia "tempo livre em casa", mas o histórico (a última fala dela era do Starbucks) pesou mais. **Correção:** `since_last.py`, com o bloco "desde a sua última mensagem" (trajetos concluídos, acontecimentos, AGORA). Replay no banco: às 18:11 o bloco traz "17:25 — chegou em casa (de metrô e ônibus, saiu às 16:45)".

## Achado 11.2 🟡 — "Já papou?" → "ainda não"

Almoço japonês às 13:16 estava no bloco da comida; o modelo não entende "papar" (mesmo tropeço do 10.5). **Correção:** glossário de gírias do Patrick e resposta pronta no bloco da comida.

## Achado 11.3 🟡 — Promessa de avisar a chegada

Ontem a promessa ainda não existia no código (foi criada depois da bronca). Hoje funcionou (`arrival_promise.made` às 05:36), mas caiu no sorteio de esquecer (12%). **Correção:** 5%, e nunca duas vezes em 7 dias.

## Achado 11.4 🔴 — A iniciativa era gerada sem a conversa

`generate_dynamic_speech` montava só o system prompt + a instrução, sem histórico. Às 20:53 ela cobrou "sumiu hein? tá vivo?" sem saber que ele tinha avisado às 18:24 que ia a um aniversário, e de manhã não perguntou como foi. **Correção:** `with_history=True` na iniciativa (~6 mil caracteres da conversa) + a hora da última mensagem dele. Ela continua livre pra cobrar (decisão do Patrick).

## Achado 11.5 🟡 — Iniciativas com fala ditada

As instruções traziam a fala pronta ("'sumiu hein'", "'tá vivo?' carinhoso") e a saudade empurrava sempre "uma coisa real do seu dia" (a Bia, duas vezes). **Correção:** instruções com a situação, e a fala fica com ela; as últimas 3 iniciativas entram como "não repita o jeito".

## Achado 11.6 🔴 — Bom dia de dentro do chuveiro

Banho 05:10–05:29 (criado pelo próprio ritual), bom dia às 05:19 com "Agora você está: tomando banho". **Correção:** `Rituals.in_shower`, que segura o ritual até o banho acabar; no "se arrumando", o bom dia sabe que o banho vem aí (ela decide se junta).

## Achado 11.7 ⚪ — "Database or disk is full" (2× às 09:13)

O disco tem 256 GB livres; foi pontual. Fica a mudança pra VPS, que já estava no plano.

## Achado 11.8 ⚪ — Bancos fantasmas

`marina_memory.db` (vazio, com o esquema) e `memory_manager.db` (0 bytes) na raiz, criados por scripts com o nome errado. Apagados com o OK do Patrick. **Lição:** o banco é `marin_memory.db`.

## Revisão das decisões na mesma tarde

- **D11:** o Patrick aprovou a tabela, o jeito e a condição fixa. **Mudou o médico:** quando ela está mal de verdade e o pai ou ele mandam, ela vai pelo plano de saúde e melhora mais rápido (`Health.observe_patrick`, `DAD_SENDS_CHANCE`).
- **D10:** aprovado; cachê 50% na aprovação e o resto no máximo 1 dia depois do job (pix da Lívia).
- **D9:** faxineira paga pelo pai, **Dona Neide**, toda quinta; porteiro **Seu Jorge** (`canon_extras.py`: o seed é travado e as migrations são só de esquema); o pai paga só o apê e a mesada da comida; sem perrengue de gás e água.
- **PLANO_VOZ:** o painel de status (seção 0) estava parado em 21/09. Foi refeito com o estado real, uma lista única de pendências e o resumo da pilha oficial de fotos.

## Depois da auditoria (24/09, noite) — fotos e limpeza

- **Código morto de imagem removido:** a GPU da Novita (`gpu_manager.py`, liga/desliga no `sd_client`), o ComfyUI, o SD local e todo o caminho do Flux (DNA, anatomias, LoRAs, `build_flux_prompt`, `CIVITAI_ECOSYSTEM`). Com o Flux como "plano B", uma foto sem o LoRA Krea 2 sairia com outro rosto; agora sem o LoRA não sai foto. A Novita segue só na voz. Linhas antigas do `.env` também saíram.
- **C.1b feita:** apartamento canônico, zoom por palavras e diretor de cena (`photo_director.py`). Detalhes no PLANO_VOZ, seção C.1.
- **Soak não resetado:** simulado o primeiro tick numa cópia do banco de produção (vida registrada desde 22/09): entram só 4 eventos plausíveis da casa (roupa na máquina ontem, Dona Neide hoje), nenhum casting e nenhuma doença retroativa. Um reset apagaria a conversa de 23–24/09 que as correções da #11 usam.

## Depois da auditoria (25/09, manhã) — "ela piorou de novo"

O Patrick acordou com amigdalite e achou que ela tinha voltado a agir como assistente, com textão. O HD tinha enchido de novo, mas **não foi a causa**:
- **Disco:** só 2 erros "database or disk is full", às 05:55, no envio da resposta ao boa-noite. A resposta passou na nova tentativa, o banco está íntegro (`PRAGMA quick_check` = ok) e tudo depois das 08:03 gravou normal. O item VPS (pendência 3 do painel) continua valendo.
- **Causa real:** nenhuma regra cobria **ele** doente. No modo apoio, o GPT-5.6 Luna caiu no padrão de orientação de saúde (dose, bula, sinais de alerta, "procura atendimento") e repetiu a pergunta dos sintomas. A resposta das 08:06 teve 336 caracteres em 3 balões.
- **Correções** (detalhes no PLANO_VOZ, "Naturalidade de chat", 25/09): o hint `PATRICK_SICK_HINT`; os balões como pedaço de pensamento, a partir dos prints de casais que ele trouxe; as abreviações na saída.
- Testes: `test_patrick_doente.py`, `test_abreviacoes.py`, `PedacoDePensamentoTests` em `test_bubbles_luna.py`. Os testes antigos que travavam "nunca quebra no meio da frase" e "sai em 2 balões" foram reescritos pela regra nova.

**Mudança pra VPS (25/09, 10:56).** Com o disco do PC enchendo pela segunda vez, a Marina foi pra VPS Hostinger do Patrick:
- **Instalação:** `/root/bots/marina`, serviço `marina.service`, no mesmo padrão dos outros bots dele. O fuso de São Paulo vale só pro serviço; o servidor segue em UTC por causa dos outros bots.
- **Testes:** 934/934 verdes lá (faltava o `cryptography` no `requirements.txt`).
- **Banco:** copiado com a API de backup do SQLite, que junta o `-wal`. Integridade ok, 413 mensagens, nenhuma resposta pendente. Ela voltou sem erro.
- **Mini App:** `marina.psoft.app` com certificado.
- **Achados do servidor que não são da Marina** (ficam com o Patrick): firewall desligado com as portas 8000/3000/3099 abertas, e o certbot do sistema quebrado desde 02/09 por um `cryptography` instalado por pip.

## Depois da auditoria (25/09, tarde → 26/09, madrugada) — uso real

Conversa de verdade com o Patrick doente, o Mini App novo e uma cena de sexting no banho. Cada problema virou commit; o que é voz está detalhado no PLANO_VOZ ("Uso real 25–26/09").

| Hora | O que o Patrick viu | Causa | Correção (commit) |
|---|---|---|---|
| 25/09 12h | Pagou o açaí prometido pelo Pix e ela agradeceu como presente | O Pix não sabia do combinado | Pix prometido fecha o open loop e vira pagamento (`0832554`) |
| 25/09 12h | Ela responde bolha por bolha e fala demais | Cada bolha dele virava um turno | Bolha nova antes do 1º balão faz ela desistir e responder o lote (`2c0db97`) |
| 25/09 12h | Mesma ideia repetida com outras palavras | O corte só pegava repetição literal | Aviso das ideias recentes + corte de paráfrase (`8833fee`) |
| 25/09 13:18 | O rolê do bar virou "ensaio" | Freela sem job não dizia que não tinha ensaio | `freela.prompt_lines` vazio diz que não há job (`1c34f74`) |
| 25/09 13h | "hj às 19h30 no Quartinho com o Theo e a Júlia" soa relatório | Planos saíam com hora, nomes e lugar | `soften_times` + regra de aviso informal no ritmo (`2ee5b97`, `4e3f4e7`) |
| 25/09 15:22 | Prometeu foto do bolo e dos looks e nada chegava | Promessa de foto não tinha dono | `promessa_foto.py`: promessa vira compromisso com hora (`3369fdf`, `1c3497e`) |
| 25/09 16:28 | Anunciou o box 4 vezes e os registros nunca vieram | Nenhuma frase punha ela no banho | `SHOWER_NOW_RE`; banho no sexting vira promessa íntima (`11f3762`) |
| 25/09 16:55 | Mensagens dele presas depois de ela dizer que saiu do banho | O banho que eu semeei à mão ia até 17:08 | `SHOWER_END_RE`/`end_shower`; "já te mando o estrago" no clima é íntima (`bb95252`) |
| 25/09 17:06 | Ela ficou quieta 12 min | Retrato do mundo "tomando banho" seguiu valendo e adiou pra 17:36 | Retrato de banho sem banho = desconhecido; adiadas pelo banho saem quando ele acaba (`6ae9bfa`) |
| 25/09 17:2x | "Chuva de mensagens" depois de já ter respondido | 3–5 ideias por turno em conversa casual | Turno curtinho (65% casual, 40% normal) + corte depois do 1º balão com conteúdo (`484d03e`) |
| 26/09 02:45 | "Teve alguma novidade sobre sexta?" depois do boa-noite das 00:40 | Iniciativa só olhava a janela fixa 03h30–08h | Plano de sono manda: deitada não puxa assunto (`621e847`) |
| 26/09 09:04 | "Meu dia começou perfeito, seu lindo. Te amo demais": ponto no meio do balão | O corte de balão só separava frases quando o balão passava do alvo (32–60 caracteres); esse tinha 50 | Ponto entre frases sempre vira corte; pedaço curto demais vira vírgula ("Ah, tá bom"); "!" e "?" no meio continuam; o resto do teto de 10 balões junta com quebra de linha |
| 26/09 09:04 | Ela pegou o presente com o Seu Jorge, mas o Mundo dizia "sem contato" | A retirada na portaria gravava o evento com ele como participante, mas não chamava `SocialWorld.record` | `delivery._contato_portaria`: presente dele e delivery dela contam como contato com o Seu Jorge |

**Reset do soak (26/09, 04:10, pedido do Patrick).** As mensagens da madrugada deixaram lixo na memória. Antes do reset:
- o `reset_soak_learning` apagava a tabela `feedbacks` (anotação dele pra nós, ela não lê) e deixava `emotion_episodes` (116) e as marcas `facul:`/`sono:` do `world_bootstrap`. Corrigido (`7a28c14`, `tests/test_reset_soak.py`);
- os `/bom` e `/ruim` gravam na biblioteca **da VPS** (o deploy não leva `data/feedback`): 5 registros e 2 evitares novos trazidos pro PC antes de mexer;
- rodado com o serviço parado; backup em `backups/pre_soak_reset_20260926_071015.db` na VPS. 1.816 linhas removidas; 11 feedbacks preservados.

**Feedbacks do caderno atendidos (26/09):** áudio falando "aga jota" (abreviação volta por extenso antes da voz); Mini App sem zoom e pedido dele só no iFood; comprovante sem logo (os PNGs das marcas estavam no `.gitignore` e nunca foram pra VPS); opções de look em álbum (agora uma por vez, 3–6 min de troca); `/bom` com o "Patrick disse" de horas antes em fala de iniciativa e pós-gozo marcado como sexting; bilhete do delivery lido na voz errada ("minha gatinha"). Commits `f409a17` e `621e847`.

**Fundo canônico (teste pago, 26/09).** O Krea 2 com o LoRA dela não aceita imagem de entrada (`createVariant`/`editImage` recusados no `whatif`). O Qwen `editImage` com duas imagens (ela + cenário real do Unsplash) **ignorou o cenário** nas duas ordens. Trocar só a roupa numa foto funciona (fundo idêntico), mas mexe no rosto; misturando só a região que mudou, o rosto volta ao original. Como os looks passaram pro tripé com pose nova a cada look (decisão do Patrick: gerar cada um do zero), a troca de roupa não entrou no fluxo. Gasto: 155 Buzz + 30 do teste do Milo.

**Câmera (26/09, `ea93bb5`).** O Patrick notou selfie demais. Poses de tripé já eram maioria (19 × 11 selfies), mas os looks estavam travados no espelho e não existia foto sem ela. Agora: looks no tripé do closet, e comida/Milo/vista do ponto de vista dela, sem o LoRA dela.

**Mini App: abas e padrão visual (26/09, 07:30, 3 prints do Patrick).** Ele esperava os pedidos numa tela separada, pela barra de baixo, como no app real. Também viu emoji no lugar de ícone e a "escadinha" dos Destaques (nome de 2 linhas empurrava os vizinhos). A causa da escadinha: o `<button>` centraliza o conteúdo na vertical. Duas regras novas dele: **ícones do Bootstrap Icons, nunca emoji, nos apps**, e **excelência em alinhamento, inclusive nos comprovantes**. Feito:
- barra Início/Busca/Pedidos; aba Pedidos com "Seus clássicos" e histórico por dia (logo, itens, foto, "Adicione à sacola");
- ícones trocados no iFood e nos Bastidores;
- cartões alinhados pelo topo; stepper e barras com colunas fixas;
- comprovante do iFood em colunas (quantidade, nome recuado, preço à direita, subtotal e taxas); Pix com valores todos em negrito.

Detalhes no PLANO_WEBAPP ("Abas do iFood e padrão visual").

**Conversa e logs de 26/09 (manhã), revisados a pedido do Patrick:** 16 mensagens; nenhum erro no log. Só avisos de robôs procurando `.env` no endereço do Mini App (barrados) e um ciclo de 15 s pulado enquanto ela gerava. Fluxo certo: as mensagens das 07:21 esperaram ela acordar, às 09:04 ela pegou o presente na portaria e reagiu, e o bom-dia foi respondido junto. Dois achados, na tabela acima.

**Rolê sem consumo (26/09, achado do Patrick na revisão da aba Agora).** Ela foi ao bar antes do reset e o saldo não mexeu: a saída só existia como "estar lá". Causa: nenhum módulo gerava o que acontece durante o rolê. Novo `consumo.py`: cada saída tem pedidos determinísticos (bar, Starbucks com os preços do iFood do app, cinema, praia) e uber; cada um vira acontecimento, gasto no saldo e, se for comida, a refeição do horário. Decisões dele: lazer e uber no saldo dela; ônibus/metrô no Riocard do pai, fora do extrato. Também: "Starbucks da Gávea" vira o nome canônico (migração 027).

**Organização por frentes (26/09).** A conversa de trabalho ficou longa demais (resumos perdem detalhe). Criados `CLAUDE.md` (mapa), `FRENTES_MARINA.md` (painel) e skills por frente em `.claude/skills/`.

**Entrega surpresa de 26/09, 16:41.** Três achados no mesmo minuto: (1) dois jobs (entrega e proatividade) mandaram mensagem ao mesmo tempo, sem trava, e os balões se intercalaram no Telegram; (2) dois resolves do mundo em paralelo — o da entrega gravou "comendo o sanduíche" e o da saudade gravou "Instagram" por cima; (3) o lanche planejado das 16:39 foi registrado com ela na rua (a checagem de casa não reconhecia o trajeto de volta) e o presente não tinha saciedade. Corrigidos com trava de envio por chat, trava de iniciativa, resolve serializado e checagem de casa pela hora do evento.

**Rotinas soltas (26/09).** Além da academia, tinham o mesmo problema: o passeio do Milo da manhã (sorteado a cada resolve e cancelado pela conversa ativa), o mercado (planejado, mas teletransporte: sem preparo nem trajeto) e o médico (só um registro; ela nunca saía de casa no mundo). Viraram itens da agenda única, junto com as saídas por vontade. Achado de custo: cada resolve do mundo leva ~7 s na cópia local, quase tudo no `sleep_plan` (1.300 conexões SQLite por resolve) — pré-existente, fica anotado.

**Academia sem preparo (26/09, print do Patrick).** A academia era rotina sorteada a cada resolve (vontade pela energia do momento), então não existia antes de começar: sem preparo, sem trajeto, e o card sem barra (retrato com `slot_end` e sem início). A conversa ativa cancelava o treino. Virou plano do dia guardado (`academia.py`) que alimenta a rotina, o trajeto e as etapas do card.

**Mídia real (26/09).** Achado: a API-Sports do Botafogo não dá a agenda de 2026 no plano grátis (só o "ao vivo"), então o mundo não sabia quando havia jogo; a agenda passou pra ESPN (sem chave). A ESPN recusa User-Agent de navegador (403) e aceita o do curl. O iTunes BR devolve títulos japoneses em kanji; artistas japoneses usam a loja americana. Música, leitura e jogo viram acontecimento e mudam o card, o prompt e o saldo (compra de livro).

**Fome em tempo real, masturbação sem cota, pessoas por proximidade (26/09).** Achados: a fome só mudava quando a refeição era registrada (caía de uma vez no início); agora cai enquanto ela come, e a refeição tem fim de verdade (`end_at`) e saciedade (`metadata_json`). A masturbação tinha cota diária e intervalo fixo que o corpo já regulava sozinho (a vontade cai depois do gozo). No Mundo, o texto de quem era a pessoa nova era a história de como se conheceram; virou proximidade, e a história foi guardada no personagem. De quebra: a mesma transição anunciada (refeição, banho) gravava um retrato novo do mundo a cada turno; agora reaproveita o anterior.

**Tempo livre concreto (26/09, etapa 1 da aba Agora).** "Tempo livre em casa" virou o que ela faz de verdade (`tempo_livre.py`): blocos que viram acontecimento, com efeito no corpo (se tocando registra o orgasmo), disponibilidade própria (HOME_BUSY/SOLO) e card "Em casa"/"Se alimentando". Achados: a preparação pro bar começava no meio do jantar (agora ela come primeiro); "Gabi) Freitas" no texto de quem ela conheceu (apelido com sobrenome).

**O reset apagou o fim de semana (26/09, achado ao conferir a agenda na produção).** Depois do reset das 04:10 não existia nenhum compromisso: nenhum rolê fixo caiu na semana (sorteio) e os dois convites do fim de semana (Quartinho com a Bia hoje às 21:00, cinema no domingo) tinham "chegado" dias antes — antes do início da vida registrada — e eram descartados pela regra de não inventar passado. Agora o convite de um rolê que ainda vai acontecer conta como recebido no início da vida registrada (ela vê ao acordar) e ela decide como sempre; o que já passou continua não existindo. Na cópia da produção, o bar de hoje voltou (decisão dela às 19:00). Também: a migração do Starbucks virou 027, porque o 26 já tinha sido usado direto no banco (faxineira_e_porteiro, 24/09).

**Aba Agora sem preparação (26/09).** O Patrick notou que o status mostrava o que ela fazia, mas nunca o que ia fazer: do "tempo livre em casa" ela pulava pro trajeto. Só existia "se arrumando pra faculdade" de manhã. Novo `agenda.py` (etapas do dia a partir do que o mundo já decide), com preparação que muda a disponibilidade dela (GETTING_READY) e banho de verdade; card da aba Agora redesenhado linha a linha com ele. Achado de passagem: rolê em dia de aula que começa antes da aula acabar sobrepõe a volta da PUC e a ida (pendência no PLANO_WEBAPP).

**Bastidores revisados (26/09, manhã, pendência 14).** Tirei os textos reais da VPS (só leitura) e listei o que estava ruim: nome interno do lugar e código da atividade, emoji herdado do `/status`, "exausta" enquanto ela dormia, a frase "dormiu 8,7 h · TPM · última vez há 30 h" sem rótulo, "saudade com Patrick" (preposição errada e ele em 3ª pessoa) e o `/mundo` colado ("último contato sem contato ainda; 0 nos últimos 30 dias", com o `weekly` do cânone aparecendo como número). O Patrick escolheu abas e voz híbrida. Tudo refeito na camada do Mini App, sem mexer nos comandos; detalhes no PLANO_WEBAPP ("Bastidores em abas").

**Agenda reativa (26/09, noite — frente do mundo).** O Patrick: "parece que tudo na vida dela é premeditado e segue o fluxo até o final". Achados: (1) o que ela topava na conversa ("tá bom, vou treinar", "vou descer com o Milo") não mudava nada no mundo — a pendência 17 do PLANO_VOZ; (2) nenhum compromisso podia acabar antes da hora. Novo `agenda_reativa.py`: depois que a fala dela sai, se tem cara de plano (regex barata), o modelo de reserva lê a fala dela e a mensagem dele e diz se ela combinou, desistiu ou está indo embora — vira item da agenda única (origem "conversa"), remarca a academia/passeio do Milo planejados, cancela o que ela desistiu ou encerra o que ela faz. No meio de um compromisso, a cada 20 min pode surgir motivo pra sair antes (passou mal, banheiro na virose, cansou, bateria social, rolê chato, tédio leve às vezes, tesão); sair mais cedo só encurta o fim (a volta sai dali) e guarda o fim original, pro consumo já pedido não mudar. A aula largada no meio vira exceção na grade com hora de saída (`ate`), e as aulas seguintes caem. Tesão: ou vai correndo pra casa (o primeiro bloco em casa é o alívio) ou se tranca num banheiro por ali (pausa de 8–15 min, disponibilidade própria, efeito no corpo), às vezes chamando ele pro sexting (o convite agora diz onde ela está). Validado o prompt com 7 frases reais no modelo de reserva (7/7); o modelo devolvia vazio sem `llm_kwargs` (raciocínio comia os tokens). Na revisão dos textos com o Patrick: layout C no card (Motivo na grade, "Saiu 33min antes" embaixo do lugar), motivos secos, acontecimentos narrados com ele, e **uber quando ela sai mal** (mal-estar, banheiro, cansaço), com aviso pra ele e Pix dele pagando o uber. Achado de passagem: `_autonomous_routine_v36` não deixava sair nenhuma iniciativa durante um compromisso, então o convite pro sexting do banheiro nunca chegaria; agora, num compromisso, ela puxa conversa quando o "Celular" do card deixa (com frequência / de vez em quando), e o convite e o aviso passam sempre. Acontecimentos da conversa em texto de saída ("saiu pro Starbucks", não "desistiu do café"). Testes: `tests/test_agenda_reativa.py` (20).

**Unhas (26/09, noite — frente do mundo, etapa 1: cuidados).** Antes a unha não existia: nenhuma foto dizia a cor, ela nunca fazia as unhas e o "fazendo as unhas" aprovado pro tempo livre não tinha sido criado. Novo `unhas.py` com o estado (cor, gel/esmalte, feita quando e onde, quem escolheu) e o desgaste por dias. Em casa entra como bloco do tempo livre (esmalte gasto + tédio ou tarde à toa); o salão (Ophicina do Cabelo, migration 030) entra pela mesma porta da agenda única (`Vontade.agendar`, chave `unhas:<dia>:<HHMM>`, que a agenda e o commute passaram a ler) e é chamado no mesmo ponto do `resolve` que a vontade (se marcou manicure, a vontade não sorteia na mesma janela). O pagamento reaproveita as finanças: o acontecimento sai como `compra:unhas:…` com "(R$ 180)" e o `financas.materialize` debita (o `Unhas.materialize` roda antes dele). A pergunta da cor é iniciativa própria (`unhas_cor`, passa mesmo em compromisso, como o aviso de saída); a resposta dele é lida depois da fala dela (`observe_patrick`) e vale até ela passar a base. A foto da mão reaproveita a promessa de foto (tipo `unhas`, pose `pov_unhas`, prompt de ponto de vista com "só a mão"); toda foto (`photo_director.direct`) ganha a frase da unha. Disponibilidade: em casa "fazendo as unhas" → HOME_BUSY; no salão, perfil novo MANICURE (celular médio, "Olha de vez em quando"; bateria social neutra — antes todo compromisso fora de casa contava como SOCIAL). Achado de passagem, não corrigido: saídas sozinha por vontade (café, açaí) também caem como SOCIAL na bateria social (`social_battery._kind_at`). Na revisão com o Patrick: a unha no Por dentro virou seção própria (cor, barra de desgaste, Estado, Tipo, Feita — numa linha só ficava ruim), o salão mostra "Pagando · R$ 180" com o valor na direita e o preço subiu pra R$ 180. Na segunda rodada: estados curtos no painel (Nova, Crescendo, Vencendo, Gastando, Descascando), reservas no jeito dela e motivos secos com o dia real do evento. As travas de versão do banco nos testes foram de 29 pra 30 (migration 030) e a contagem de lugares canônicos do seed ganhou a Ophicina. Testes: `tests/test_unhas.py` (7).

**Cabelo (26/09, noite — frente do mundo, etapa 1: cuidados).** Antes o cabelo era fixo em toda foto ("castanho longo com pontas loiras, semi-liso") e não existia dia de lavar, penteado nem salão; o passo "Secando cabelo" do preparo era só texto. Novo `cabelo.py` no molde do `unhas.py`: estado em `estado_relacional` (lavagem, secagem, corte, tom, rosa, hidratação, penteado da saída, sessão do salão, sugestão dele). A lavagem acontece dentro do banho que já existia (`rituals.start_shower` pergunta ao cabelo e alonga o banho; o acontecimento vira "Tomou banho e lavou o cabelo"). O penteado da saída é decidido quando o "Se arrumando" começa (`world_state._getting_ready` → `Cabelo.se_arrumando`; o `prep_activity` passou a levar o `prep_tipo`). O salão entra pela mesma porta da agenda única (`Vontade.agendar`, chave `cabelo:<dia>:<HHMM>`, lida pela agenda e pelo commute), depois da manicure no mesmo ponto do `resolve`; os passos do card vêm do metadata (os serviços da vez) e a escolha dele reescreve serviços, preço e passos. O pagamento reaproveita as finanças (`compra:cabelo:…` com "(R$ X)"; `Cabelo.materialize` roda antes de `financas.materialize`). A pergunta é iniciativa própria (`cabelo_pergunta`, passa mesmo em compromisso) e a resposta é lida em `observe_patrick`, que também guarda sugestão solta ("fica linda de franja"). Umectação é bloco novo do tempo livre. Disponibilidade no salão: o mesmo perfil MANICURE ("cabelo n" na atividade), bateria social neutra. Fotos: `visual_profile` separou `HAIR_COLOR`/`HAIR_STYLE`, e o `photo_director._hair` troca os dois pelo cabelo de agora (o penteado da pose fica quando ela diz molhado, embaraçado ou espalhado); poses novas `salao_cabelo` (capa do salão, alguém de lá tira), `cabelo_espelho`, `cabelo_tripe` e, nas unhas, `unhas_selfie` (mão perto da boca, 30%). O visual da Ophicina no `camera_world` virou salão genérico (servia só pra manicure).
Teste com o LoRA (Civitai, 7 fotos normais, mesma semente): repicado, franja cortina, franja cheia, mel, bege, loira iluminada e pontas rosa — o rosto se manteve em todas e o ângulo de frente obedeceu. **Achado:** 3 das 4 primeiras saíram nuas porque o script de teste não passou roupa (só a frase "fully clothed"); na produção o diretor sempre descreve roupa em foto normal (`_outfit`), então não é risco do bot — o teste foi refeito com a capa do salão. **Bug pego na pré-visualização:** a seção nova usava `const c`, que já existia no mesmo trecho do `app.js` — quebraria a aba Bastidores inteira; renomeado. Testes: `tests/test_cabelo.py` (7).
Revisão dos textos com o Patrick (mesma noite): penteados e passos do salão mais curtos, linha Rosa própria no painel, acontecimentos do salão sem parênteses duplos ("Cabelo na Ophicina: repicado (o Patrick escolheu) e escova · R$ 220." — as finanças seguem lendo o "R$"), reservas do chat com contexto. A linha do tempo "Hoje" inteira vira o próximo ataque dele (frente dos apps).

**Linha do tempo "Hoje" (26/09, noite — frente dos apps).** Olhando o dia real de 26/09 (33 acontecimentos): o app mostrava só os 14 últimos (a manhã sumia); as saídas (academia, Quartinho) não apareciam, só os encontros de lá; vazava texto interno ("Um contato de Henrique foi informado; quando e como Marina responderá ainda não está definido"); blocos repetidos ("Montando looks" duas vezes, "organizando o closet no closet"); textos longos (iFood surpresa, playlist inteira). Novo `hoje.py`: o dia inteiro por período, saída como item com início–fim e o que rolou lá recuado, blocos em casa com duração, previsto em cinza, texto curto de painel no passado. **A linha do tempo expôs incoerências do mundo (frente do mundo):** blocos do tempo livre não respeitam saídas ("Montou looks" até 15:11 com a academia começando 14:53; "Olhou o Instagram" dentro da academia; "Ouviu Dua Lipa" atravessando o banho), "Beliscou pipoca vendo série" às 21:07 com ela no bar, e o convite da Bia registrado às 04:19. Na revisão dos 50 tipos de linha (27/09, madrugada) apareceu mais texto interno indo pro painel: a masturbação levava "Guardou só pra ela: não conta pro Patrick" e a pessoa nova levava a descrição do cânone ("tutora da spitz que brinca com o Milo") — agora a linha é só a ação e uma descrição curta embaixo.

## O que estava certo

"Tô na rua, saí pra encontrar a Júlia" às 14:53 e "cheguei sim" às 15:52 batiam com o mundo (a caminho 14:49–15:30).

`tests/test_conversa_24_09.py` (6 testes) + regras novas em `test_arrival_promise.py` e `test_health_d11.py`.

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

## Frente de bugs (27/09)
Bugs do uso real agora têm frente própria: skill `frente-bugs` (capturar banco, mundo e log antes que mudem; diagnosticar por camada: mundo → prompt → fala) e seção 5 do `FRENTES_MARINA.md`. O primeiro caso é a volta do Quartinho Bar: o mundo estava certo e a fala contradisse o estado `post_event_recovery`.

**Correção (27/09), três camadas:**
- **Prompt:** `world_context._chegada` — em casa e com uma volta terminada há ≤ 60 min (`Commute.ultima_volta`), entra "[CHEGADA — FATO] Você voltou {de onde} {como} e chegou em casa às HH:MM. Você JÁ ESTÁ EM CASA…". O `post_event_recovery` deixou de dizer "ainda em casa relaxando" (soava como se ela nem tivesse saído).
- **Promessa:** `arrival_promise` só olhava trechos que começavam em até 90 min; "te aviso quando chegar em casa" às 21:39 com a volta às 23:59 não era gravado. Promessa de casa agora olha a volta das próximas 12 h. A fala dela manda no destino ("chegar no shopping" não vira casa só porque ele escreveu "casa").
- **Mundo:** `AgendaReativa.combinar_uber` — ele pede uber (ou "não quero você andando a pé") e ela topa: os próximos trechos da saída (ida, volta ou os dois, pelo texto) viram uber, gravados em `voltas` com `combinado`. `_voltas_trocadas` agora troca a ida também (chega na mesma hora, sai mais tarde).

`tests/test_bug_volta_quartinho.py`, 5 testes com as falas e horários do caso.

Frente de imagens (27/09): skill `frente-imagens` e seção 6 do painel, pra cadeia pose → prompt → motor.
Primeira rodada (27–28/09): amigas só por texto (LoRA de rosto mistura com o da Marina); Bia com foto-RG (`data/amigas/bia_rg.jpg`) e troca de rosto pelo Krea 2 Edit na foto de grupo (`civitai_images.swap_friend_face`), 28/09; Carol pelo mesmo caminho (`data/amigas/carol_rg.jpg`) Júlia por edição por partes da nossa foto de grupo (`data/amigas/julia_rg.jpg`) e Theo (`data/amigas/theo_rg.jpg`), 28/09; foto de perfil dos quatro no Mundo do Bastidores (`webapp/avatars`, `social_day.world_panel` manda `foto`), e o teste de `FRIENDS_VISUAL` passa a valer pra toda amiga com RG. FinePorn v5 em A/B contra a v4 (fica a v4); 18 poses de referência no catálogo (`photo_director`), zoom `torso` (`visual_profile`), plug de coração no mundo (`intimacy`). Achado: roupa descrita *sendo tirada* + nudez faz o Krea 2 recusar (imagem de ruído com letras, sem erro na API) — a roupa puxada se escreve parada. `tests/test_photo_director.test_reference_poses_27_09`.

Foto de grupo de ponta a ponta (28/09): a amiga do rolê chega na câmera e entra na foto. Achado: `active_people_json` estava sempre vazio na produção (ela "no cinema com a Bia" e a câmera sem saber da Bia) — o compromisso já tinha `metadata.friends`, mas ninguém passava adiante. Agora `CalendarWorld.current` devolve `people`, o `WorldStateManager` grava em `active_people_json` e o `CameraWorldBuilder` usa o do compromisso se o retrato não tiver. O diretor ganhou duas poses de selfie com a amiga (`GROUP_POSES`, só na rua, nível 0–1, só com quem tem foto-RG); a amiga vira frase própria depois da roupa da Marina, com roupa de sair de peça diferente; `DirectedShot.friend` leva a chave e `sd_client.generate_directed` chama `swap_friend_face` (se a troca falhar, vai a foto como saiu). Segundo achado, na 1ª foto real (Bia, ~61 Buzz): o Krea 2 Edit redesenha as duas pessoas mais embaixo (o fundo fica parado), e a emenda fixa em 56% passava no rosto novo da amiga (olho fantasma). `paste_side` agora costura pelo caminho de menor diferença entre a original e a edição (`seam_path`, programação dinâmica em 1/4 da resolução, faixa de 44–66% da largura). `tests/test_foto_grupo.py` (11 testes), `tests/test_visual_profile.test_friend_seam_goes_where_both_images_agree`. Na mesma leva: `Pose.face` (cara que é o charme da pose vence a cara do humor; a `inclinada_pra_camera` olha pro lado com a boca entreaberta) e o Krea 2 Detail Slider testado e reprovado (PLANO_VOZ, "Fotos pelo Civitai"). Depois: Real/Fake Breast Slider −1.0 em `BODY_SLIDERS` (toda foto, vestida ou nua; `tests/test_civitai_images`) e a `face` da inclinada pra câmera com o texto da mordida que já funcionou; LoRA Lip Bite 0.6 como LoRA de ocasião quando a cena morde o lábio (`tests/test_civitai_images.test_lip_bite_lora_when_she_bites_her_lip`).

## Bug: Hoje desconexo do card (27/09)
Às 01:05 o card, o Hoje e o mundo contavam três histórias. Correção:
- `agenda.etapas` (Se arrumando pra dormir): banho real (`life_events` `banho:*`) depois da volta e até `BANHO_DORMIR_JANELA` (90 min) antes da cama vira o primeiro passo ("Tomando banho [e lavando o cabelo]"), e os outros passos vêm depois dele. Banho mais cedo tira o passo de banho. Fecha o risco de `rituals._banho_prep` dar um segundo banho.
- `hoje.hoje_view`: item com fim no futuro fica no presente (`presente` do bloco ou `_presente`), com a hora em aberto; o banho corta o bloco em casa que passava por cima dele.
- `tempo_livre.agora`: o bloco não começa antes da chegada (`Commute.ultima_volta` em até 15 min).
- `meals.materialize`: refeição em casa com ela fora espera ela voltar, mesmo passada a janela (antes caía no "chegou, come agora" com ela ainda no bar).

`tests/test_bug_hoje_card.py`, 6 testes com os horários do caso.

## Bug: desencontros com a aba Agora (varredura de 27/09)
Varredura das 24 h (26/09 22:30 → 27/09 22:35) comparando o mundo (`world_state`), o card da Agora recalculado numa cópia do banco (`sqlite3 .backup`) e o chat. A madrugada já estava corrigida; o dia teve sete desencontros:
- **Dois banhos no Se arrumando (13:49–14:34), mundo e card.** Banho real 13:51–13:59; o "vai de uber" das 14:02 mudou a ida, o Se arrumando recomeçou às 14:02 e o card e o mundo voltaram pro "Tomando banho". `agenda._prep_com_banho`: banho real até 2 h antes de sair é o banho do Se arrumando (fica na hora dele; o resto vem depois); banho mais de 45 min antes do previsto só tira o passo. Mesma regra do "pra dormir".
- **"Refri" das 15:13 às 19:00, mundo e card.** O rolê do cinema só tinha as compras como passos, e ela inventou o filme ("A Princesinha"). `cinema.py`: sessão com filme em cartaz de verdade (`TMDB.now_playing`, região BR, pelo gosto dela), gravado no compromisso; começa 10–20 min depois do ingresso e dura trailers + filme; depois, "Olhando vitrines"/"Provando roupa". O mundo diz "(na sessão de X)", a disponibilidade vira `CLASS` (celular "Olha depois do filme") e o prompt tem "[CINEMA — FATO]".
- **Farmácia "saindo do Shopping", mundo e card.** Voltou de uber (19:00–19:20), em casa deu vontade de ir à Pacheco (19:23), e a emenda (`Commute._emendas`) fez a ida sair do shopping, a pé, desde 19:00, apagando a volta. Item decidido na hora (`Leg.decidido_em`) depois do começo da volta não emenda: ela decidiu em casa, sai de casa.
- **"Tô no Shopping da Gávea ainda" às 19:37, prompt.** O prompt dizia "Local: local reservado" (máscara antiga pra compromisso que não era saída social) e não dizia que ela tinha voltado. A máscara saiu; fora de casa com uma volta já terminada, entra "[VOLTOU E SAIU DE NOVO — FATO]".
- **Belisco saindo pra farmácia (19:28), mundo.** O retrato do mundo ainda dizia "em casa". `meals._numa_etapa`: em qualquer etapa da Agora não tem belisco.
- **"Te aviso quando estiver indo pra casa" (19:42), mundo.** Só existia promessa de chegada. `arrival_promise` agora reconhece promessa de saída e amarra no começo da próxima volta (aviso 0–2 min depois; não repete se ela já disse que saiu).
- **Tapioca com o McDonald's a caminho (21:32), mundo e prompt.** Ele avisou ("vou pedir tua comida", "pedi, tá chegando"), e o presente do app era sempre surpresa. `delivery.avisado`: fala dele de 3 h antes do pedido em diante; avisado e chegando em até 1 h, a refeição de casa e o belisco esperam, o prompt diz que está chegando e a reação não é de surpresa.
- Fora da frente (pros apps): às 18:58 ela postou no Instagram "noite gostosa com minha pessoa" numa tarde de cinema com a Bia.

`tests/test_bug_agora_2709.py`, 17 testes com os horários do caso.

## Bug: Bastidores às 05:55 de 28/09 (Agora e Por dentro)
Achados da frente dos apps revisando o Por dentro com a cópia do banco (ela dormindo desde 00:29, banho 00:06–00:28, última mensagem dele 23:04). Confirmados no banco (`world_state`, `world_bootstrap`, `emotion_episodes`, `life_events`) e no journal:
- **"Dormindo · desde 05:46", app.** O `world_state` grava um retrato novo por hora com a mesma atividade (stale de 60 min) e o `agenda.card_casa` usava o `observed_at` do último. `Agenda._desde`: o começo é o do primeiro retrato da sequência igual (atividade e lugar); vale pra barra, pra linha do tempo e pro passeio do Milo sem plano.
- **Deitar 23:37 × dormiu 00:29, mundo.** `previous_sleeping` do `_resolve` via "dorm" em "se arrumando pra dormir": depois da hora de deitar o retrato antigo era reaproveitado (não virava dormindo) e o `rituals._banho_prep`, vendo "se arrumando" sem etapa, caía no `_banho_manha` do dia seguinte — banho à 00:06 com cabelo lavado, e às 07:46 o passo "Tomando banho" da faculdade não deu banho (marca `cotidiano:banho_manha` gasta). Mesma cadeia na noite de 26→27 (banhos 00:31, 01:20, 01:35). Correções: "se arrumando…" não é dormindo (como no `response_availability`); `_banho_manha` só depois do `wake_at` do dia. Regra nova do Patrick, **o deitar acompanha o que ela faz**: `SleepPlan.acompanha` — transição anunciada (banho, refeição) que atravessa a hora de deitar, ou começa até 1 h depois dela, empurra a noite congelada pra quando termina (chamada no `_resolve`, ramo `announced_transition`). `meals._na_cama`: dormindo pelo plano não belisca (o limite era só 02:00–07:00; o teste pegou um belisco às 23:56 logo depois do banho).
- **"O pai deu bom dia" às 21:15, mundo.** Era a ligação da noite; já corrigido na frente dos apps (`appraise_event`: ligação → "Falou com o pai"; mensagem → "O pai perguntou dela"). A reavaliação criou a linha nova ao lado da antiga.
- **"Banho quentinho" 4× às 19:58 com 1.0, mundo (sentimento).** `EmotionEngine.feel` fundia (mesmo sentimento, pessoa e 3 h) sem guardar a chave do acontecimento fundido: o `appraise_world` (a cada turno, 12 h pra trás) fundia de novo e a força subia +10% por turno. E a janela só tinha limite de baixo: o banho das 19:58, reavaliado, fundia com os episódios de 00:31, 01:20 e 01:35 e os puxava pra 19:58; a comida das 22:01 virou a causa dos carinhos do planner de 07:47–08:33 (força ~1.0, pesando no humor e no tesão da manhã). Agora a fusão só olha pra trás (`started_at <= now`), a chave fundida fica em `emotion_sources` (migração 033) e o `appraise_world` lê os acontecimentos em ordem.
- **Saudade 100% dormindo, mundo (sentimento).** `EmotionEngine._missing` e `ProactivityService.saudade` contavam as horas desde a última mensagem dele, com o sono dela. `proactivity_service.awake_hours_since` → `SleepPlan.horas_acordada` (tira noites e cochilo, olha 48 h); o "faz 9h que o Patrick não fala" do prompt continua o relógio.
- **"Com ciuminho" pelo ciúme dele, prompt.** O planner marcou `ciume` em 26/09 20:18, 27/09 11:45 e 23:00 quando quem tinha ciúme/desconfiança era ele; e o exemplo de `cause` de 28/09 era justamente "o Patrick desconfiou de uma foto". Regra 9 do planner: ciume é o dela; ciúme dele de brincadeira é `provocacao`; desconfiança séria é `desconfiou` (novo: raiva/chateação 0,2, meia-vida 90 min — "um pouco chateada, passa em ~1h30", decisão do Patrick). Exemplo trocado.
- **Banco da produção** (deploy `9891835` às 09:53; backup `backups/marin_memory_antes_limpeza_bugs_20260928_1254.db`): 5 carinhos falsos apagados (o 5º, das 08:52, nasceu antes do deploy) e o da comida volta a 0,66; noite de 27/09 com deitar 00:29; ligação do pai de 26/09 vira "Falou com o pai" (a de 27/09 já tinha a linha nova), o bom dia de 27/09 vira "O pai perguntou dela"; os 3 "ciuminho" apagados.
- Visto de passagem: dois retratos com o mesmo segundo (01:34:31, dois resolves quase juntos) — inofensivo.

- Migração 033 (`emotion_sources`): entrou na política do bootstrap (`CLEAR`) e no reset do soak; testes que fixavam a versão 32 foram pra 33. Suíte: 1288 testes; a única falha é a já registrada (`test_college_d7`, instável rodando o arquivo inteiro, falha igual sem esta mudança).

`tests/test_bug_por_dentro_2809.py`, 15 testes com os horários do caso.

## Bug: manhã de 28/09 (Se arrumando da faculdade × café × Milo; iniciativa colada)
Confirmado na produção (`world_state` 466–477, `life_events`, `conversas` 183–187, `estado_relacional`, journal):
- **"Tomando café" 07:36–07:46 com o café pulado, mundo/card.** O Se arrumando da faculdade tinha o passo fixo "Tomando café"; quem decide o café é o `meals.day_plan` (em dia de aula, 15–40 min depois de acordar, às vezes pulado): `meal:2026-09-28:cafe` às 07:52, "Pulou o café da manhã". Quando ela comia, era pior: a refeição empurrava o começo do Se arrumando e o card ainda punha o passo. Agora (decisão do Patrick, "café dentro") o café é o 1º passo na hora real do meals e o Se arrumando começa nele; pulou, sem passo; café antes da janela fica no Em casa.
- **"Tomando banho" com ela descendo com o Milo às 07:58, mundo/card.** O xixi da manhã (`milo.day_plan`, 5–25 min depois de acordar, `state=False`) não aparecia em lugar nenhum da agenda. `Agenda._com_milo`/`_encaixa`: a descida que cai em qualquer Se arrumando (inclusive o de dormir, com o xixi da noite) vira o passo "Descendo com o Milo" na hora dela; o que começaria durante espera ela subir, o que estava rolando volta depois (menos o banho, que termina antes — o passo seguinte adianta; e volta de menos de 3 min também não, só picotava o card). O `rituals._banho_prep` já mede o banho até o passo seguinte, então o banho de verdade acaba antes da descida. E o Milo não desce mais no meio do café dela (`Milo._cafe`: antes, se cabe; senão depois).
- **"(descendo com o milo)", mundo.** `prep_activity` punha o passo todo em minúscula; agora só a primeira letra.
- **Iniciativa 4 min depois da resposta, proatividade.** Ele escreveu às 05:52 ("Indo pro plantão"), ela respondeu às 07:47 e às 07:51 o `autonomous_routine` mandou "como tá o plantão até agora?" (`last_autonomous_reason=open_loop_checkin`, rank ≥ 70 — sai antes do log do `state_factor`, por isso o journal não dizia o motivo). A espera só olhava a última mensagem dele (2 h antes) e a última iniciativa. `ProactivityService.esperando_ele`: ela falou por último há menos de 45 min (`USER_IDLE_MINUTES_BEFORE_PROACTIVE`) e ele não respondeu → saudade, tesão, assunto e sorteio esperam; os avisos com hora (saiu mal, desistiu, cabelo, unhas, convite do banheiro) não.
- **Visto e registrado pra frente do mundo (pergunta do Patrick):** atraso só existe na aula e desamarrado — o `college` registra "chegou 12 min atrasada" quando ela perde o despertador (15% dos dias de aula), mas a ida pra PUC tem hora fixa e o card mostra ela saindo na hora; rolê, freela, academia e consulta nunca atrasam.

Conferido na cópia da produção: Se arrumando 07:33–08:19 = Tomando banho · Escolhendo roupa · Descendo com o Milo 07:58 · Saindo 08:11, sem café.

`tests/test_bug_manha_2809.py`, 10 testes com os horários do caso (9 falham no código antigo). Suíte: 1298 testes; a única falha é a já registrada (`test_college_d7.test_she_skips_class_when_she_slept_terribly`, falha igual sem esta mudança).

## Bug: o dia 28/09 visto pelo Patrick (conversa, card e Hoje)
Capturado na produção às 15:05 (`conversas` 206–220, `world_state`, `life_events`, `ig_posts` 20) e na cópia do banco (Hoje recalculado às 15:05):
- **Almoço "no restaurante da PUC" 13:15–13:58 com ela na carona (13:00–13:35), mundo.** O `meals.day_plan` punha o almoço depois da última aula sempre por lá, sem olhar a volta, que sai no fim da aula. Decisão do Patrick ("depende da carona"): `Meals.almoco_pos_aula(dia, modo_volta)` — carona → None (almoço em casa depois de `volta.end`); sozinha → 50% por lá, 100% se a aula acaba às 14h ou depois; o `Commute._legs_planejados` pergunta e a volta sai 5 min depois do almoço; o "Lá" da PUC ganha o passo "Almoçando". Sem ciclo: o commute chama `almoco_pos_aula` (não consulta trajeto) e o meals chama `Commute.volta_puc` (só a volta, sem montar o dia). O `_antes_das_saidas` (almoço antes de se arrumar pro Starbucks) puxava o almoço pra 13:10, dentro da carona: piso agora é a chegada da PUC.
- **"Vou comprar um sanduíche antes de entrar" (08:33, a caminho) sem efeito, mundo.** `observe_marina_line` só abria refeição em casa com "agora". `comida_na_rua` + `Meals.lanche_na_rua`: na rua (trajeto, PUC, academia, Milo, médico — no rolê o `consumo.py` decide), comprar/pegar/comer algo de uma lista de comidas (ou "alguma coisa no caminho") vira `snack` "Comeu um sanduíche no caminho" 10 min depois e `consumo:` "Pediu um sanduíche no caminho (R$ 15)" (sai do saldo pelo `financas`); uma vez por hora. Às 13:41 ela disse "comi um sanduíche" — era isso; às 13:45 disse o almoço da PUC que o mundo tinha registrado.
- **Story "Baby 95" (Liniker) às 14:09 × "ouvindo Sabrina Carpenter", mundo/app.** O bloco de música tinha as faixas reais (Sabrina, Chappell Roan, Liniker…), e o card Em casa já seguia a faixa, mas `Bloco.atividade` (mundo → prompt) e o título do Hoje eram o 1º artista. `Bloco.atividade_em(now)`: "em casa, ouvindo "Baby 95" (Liniker) na playlist dela (sala)"; Hoje: "Ouviu a playlist dela" · "Sabrina Carpenter, Chappell Roan e Liniker".
- **"Foi pra calçada 07:58" sem volta, colado no "Foi pra PUC 08:19", app.** O xixi do Milo não gravava o fim; `Milo.materialize` grava `end_at` e o Hoje mostra 07:58–08:11.
- **Volta pra casa sumida no Hoje, app.** `hoje._saidas` guarda a etapa "voltando"; a saída termina com "Voltou pra casa" (sub = como: "Carona com o Theo"; sem valor — o uber tem a linha dele). E o dono de um acontecimento é a saída só se ele começou antes da chegada (o Pinterest das 13:35 caía na PUC que acabava às 13:35).
- **Achados de infra (registrados):** o Hoje de um dia de aula chega a 988 níveis de pilha (igual no código antigo; limite 1000) e ~65 s na cópia; com a API de rotas ligada estourou `RecursionError` localmente (produção: zero hoje). E script local chama a Distance Matrix paga — rodar com `COMMUTE_LIVE_TIMES=false`.
- Lista de compras (as barrinhas que ele pediu) registrada na frente do mundo.

`tests/test_bug_dia_2809.py`, 10 testes com os horários do caso (no código antigo o arquivo nem carrega). Suíte: 1334 testes; a única falha foi `test_commute_c4.test_ida_e_volta_da_puc`, que fixava a volta no fim da aula — agora desliga o almoço por lá (a regra nova tem teste próprio).

## Frente do mundo (28/09, tarde): atraso de verdade
Pedido do Patrick (item 1 do painel do mundo). Detalhe e textos em PLANO_WEBAPP, "Atraso de verdade".
- **Achado sistêmico — o atraso vivia só no banco:** `college.morning` gravava "Chegou N min atrasada" na hora em que ela acordava (com a hora da chegada no futuro), mas nada do mundo lia isso: a ida pra PUC tinha hora fixa, o `CalendarWorld.current` punha ela na aula às 07:00 em ponto, o card mostrava ela saindo na hora e, acordando depois da hora de sair, o Se arrumando sumia (`max(wake, ida−90)` ≥ saída). Agora `atraso.py` decide cada parte no seu momento (despertador ao acordar, o que segurou na hora de sair, caminho ao sair), congela em `world_bootstrap["atraso:<dia>"]` e o `commute.legs_on` aplica — o resto do mundo (card, `world_state`, disponibilidade, iniciativas, prompt) lê a mesma ida.
- **Laço sono → trajeto:** o despertador é planejado pela ida da PUC (`sleep_plan._first_departure`); a ida atrasada depende do despertador. O sono lê `legs_on(planejado=True)` e o `atraso.aplica` tem trava de reentrada.
- **"Chegou atrasada" antes de chegar:** `CalendarWorld.current` devolve nada enquanto o compromisso já começou e ela ainda não chegou (`atraso.nao_chegou`) — senão o resolve punha ela "na faculdade" com o trajeto ainda correndo.
- **Spoiler do imprevisto (achado de passagem):** o card listava em cinza o aviso do caminho antes de acontecer ("Ônibus demorou 20min" como próximo passo). Aviso futuro não aparece mais; a chegada prevista e a barra só contam o atraso do caminho depois dele.
- **Emoção:** o motivo fixo "Perdeu a hora · chegou atrasada" virou "Chegou atrasada · <onde>", com intensidade pelo tamanho do atraso.
- `tests/test_atraso.py` (10 testes); `test_college_d7.test_late_for_real_when_she_oversleeps` virou `test_late_is_no_longer_logged_here`.

## Frente de auditoria de funcionamento (27/09)
O Patrick está achando muitos bugs depois do 26/09 (~50 commits em várias conversas). Frente nova, skill `frente-auditoria` e seção 7 do `FRENTES_MARINA.md`: conferir entrega por entrega, com prova na produção, se funciona e está amarrada com o resto, e se falta deploy. Ponto de partida: VPS em `afd81fd`, `main` em `f69d2d4` (dois commits da frente de imagens sem deploy).

### Rodada 1 da auditoria de funcionamento (27/09, 11:40)
Prova na produção (47 acontecimentos, 224 estados do mundo, 81 mensagens de 26–27/09, journal). Nada de código ficou sem deploy. Três desamarrações corrigidas, com os horários reais em `tests/test_bug_auditoria_2609.py`:
- `financas.receive_pix`: pix de presente com saída confirmada no dia vira "pro rolê" (`no_role`), sem compra separada — o consumo do rolê já sai do saldo. Antes o Quartinho foi pago pelo consumo (R$ 75) e de novo pelo presente (R$ 236).
- `milo.day_plan`: o xixi da manhã sai quando o passeio planejado (`academia.PasseioMilo`) começa até 90 min depois dele.
- `meals.day_plan` → `_antes_das_saidas`: refeição em casa termina 75 min (110 à noite) antes de uma saída confirmada do dia (`eventos_pendentes`: outing, freela, vontade, mercado, médico, unhas, cabelo); se não cabe, vai pra volta (saída de até 90 min) ou é por lá. Lê `eventos_pendentes` direto: pedir os trajetos (`Commute.legs_on`) criaria laço academia → energia → fome → refeições.
- `hoje._previstos`: a saída prevista usa o início do "Lá" (decisão do Patrick).
- Banco da produção: saldo 629 → 865, `financas:2026-09-27T1017:presente_usado` apagado, título da Gabi corrigido (backup antes).
Abertos (FRENTES seção 5): belisco com entrega na portaria; banho recente como fato no prompt; "acordando e tomando café" antes do café planejado.

## Frente do mundo (27/09, tarde): bugs abertos limpos e agenda viva
**Bugs (seção 5 e item 6 do painel), com os horários reais em `tests/test_bug_mundo_2709.py` (12 testes):**
- `meals._belisca` → `_comida_chegando`: presente do Patrick parado na portaria (ela pega ao subir) ou pedido dela chegando em até 45 min seguram o belisco. Antes: chocolate às 16:40 com o sanduíche na portaria desde 16:26.
- `world_context._banho`: o último banho (até 8 h, já terminado) vira "[BANHO — FATO] Você já tomou banho [e lavou o cabelo]: das HH:MM às HH:MM (há X)". Antes: "banhou já?" → "ainda não" às 01:57 com banho às 00:31.
- `RoutineEngine._acordando`: "acordando e tomando café" só com o café planejado até 10 min depois; senão "acabou de acordar, ainda de pijama, com calma (o café da manhã fica pra umas HH:MM)". `agenda.card_casa` e `response_availability` reconhecem o texto novo.
- `tempo_livre`: o bloco em casa nasce cortado no próximo Se arrumando (etapas da agenda) ou refeição em casa (`_ate`), e `TempoLivre.interrompe` corta o bloco aberto quando o `resolve` escolhe outra coisa (banho, refeição, preparo, saída, dormir) — faixas da música depois do corte saem e o acontecimento é reescrito. `hoje` também corta o bloco no início de uma saída. Antes: "Montou looks" até 15:11 com a academia às 14:53; música atravessando o banho. Esmalte secando e touca de umectação seguem por baixo.
- `social_day._visto_ao_acordar`: convite de antes do início da vida registrada conta como recebido quando ela acorda (não na hora do reset). Antes: convite da Bia às 04:19. Linha da produção corrigida depois do deploy (`dac19ec`): acontecimento e `convites_json` de 04:19 → 09:01 (ela acordou às 09:01), rodado pelo Patrick na VPS, backup `marin_memory.pre_convite_2709.db`.
- `academia.Planejada.plano`: guardar o dia de hoje apagava os dias futuros do estado — agora mantém tudo a partir de anteontem (o que ela combina pra amanhã fica).

**Agenda viva (`agenda_viva.py`, pedido do Patrick: "o que ela sente decide; não é chegar e colocar 50% de chance de furar rolês"):**
- `Disposicao.avaliar(tipo, now, com)`: vontade de ir (0–1) a partir do `Feeling` — energia (peso maior no que é físico, rolê incluso), sono < 6 h, valência, episódios (tédio empurra pra sair e pesa contra aula; empolgação; tristeza vira desabafo com a Bia ou espairecer no açaí/orla/Milo e pesa contra o resto; raiva vira espairecer com amigos; medo/ansiedade contra rolê e a favor da academia; vergonha contra social), bateria social no que tem gente, desconforto/dor, TPM, chuva, saldo < R$ 150 no que é pago, e quem vai junto (Bia +0,15). Cada fator tem o texto do motivo; o que mais pesou é o motivo. Sem sorteio: o único ruído é um temperamento fixo por item (±0,04).
- `reconsidera` (no `resolve`, antes da agenda reativa): uma decisão por item, na janela antes de sair (rolê 150→30 min, academia 90→15, Milo 60→10, aula 150→10, mercado 120→15). Vontade abaixo do peso (`PESO`: rolê 0,40 +0,05 com a Bia +0,1 se foi ela que chamou; academia 0,38; Milo 0,28; aula 0,55; mercado 0,40) → rolê cancelado com "Avisou a Bia" e culpa; academia desiste (chuva: vai no prédio); Milo adia; mercado vai pra amanhã; aula: falta (preguiça só a da manhã e no máximo 1 por semana; motivo forte — dor ≥ 0,5 ou sono < 5 h — o dia todo) e sempre "Pegou a matéria com a Júlia" à noite ou no dia seguinte. Item decidido por vontade/conversa/emenda não é repensado.
- Contar pro Patrick (iniciativa nova `agenda_mudou`, prompt em `bot.py`): quando o motivo é de dividir (sono, energia, humor, tristeza, dor, bateria, ansiedade, TPM) e ela não está chateada com ele; motivo bobo (chuva, grana, tédio) fica no Hoje e no prompt.
- `emenda`: terminando (≤ 15 min) uma saída em Botafogo (rolê, vontade, academia; não Milo/mercado/farmácia), com vontade ≥ 0,72 de açaí/café (farmácia só com dor), passa na loja mais perto antes de voltar (item da agenda única, origem "emenda", 1 por dia, só se cabe antes do próximo compromisso/refeição).
- `Commute._emendas`: volta que esbarra na ida seguinte (ida saindo antes da chegada em casa ou até 15 min depois) vira um trecho direto "indo da PUC pro Quartinho Bar" — resolve também o rolê logo depois da aula (item 2 do painel do mundo).
- `planeja` (19:30–22:30, uma vez por noite, sem rolê nos próximos 3 dias): com vontade ≥ 0,68 chama a amiga que ela não vê há mais tempo pra sexta/sábado/domingo seguinte; a amiga topa (80%, fixo por dia e amiga) → compromisso `outing:<dia>:m<HHMM>` com origem "ela_chamou" e novidade (share 0,8).
- Vontade na hora (`vontade._pesos`/`_inquietude`): peso de cada tipo × (vontade/0,6)², chance × inquietude (tédio +1,5×, alegria +0,5×, tristeza −0,4×, bateria < 0,4 segura); o motivo do acontecimento vem do sentimento ("tava entediada em casa", "precisava espairecer").
- Convites das amigas (`social_day._willing`): mesma disposição contra peso 0,45 (0,40 com a Bia; +0,2 se já tem rolê no dia); recusa com os dois fatores que mais pesaram.
- Conversa (`agenda_reativa`): o gate pega outros dias, desmarcar/remarcar/faltar; o classificador recebe a lista numerada dos próximos 3 dias (`lista_para_conversa`: rolês, convites sem resposta, academia, Milo, aula, mercado, vontade) e devolve `item` + `acao` (vai_fazer/desistiu/remarcou) + `quando` ("amanhã 07:00", "sábado 21:00", data). `pela_conversa` aceita/recusa convite, desiste (sem aviso: ele está na conversa) ou remarca; `marca_outro_dia` põe academia/Milo no plano do dia ou cria o item da vontade daquele dia.
- Prompt: bloco "[SUA AGENDA — o que você decidiu]" (últimas 18 h) no dia social. Hoje: linhas próprias pro tipo `agenda` (`hoje._agenda`).
- `tests/test_agenda_viva.py` (23 testes).


## Frente dos apps (27/09, noite): Instagram da Marina

Etapa 5 do PLANO_WEBAPP, decidida com o Patrick por mockup (formato, bio, abertura, acervo). O que mexe no sistema:
- **Mundo → Instagram:** `instagram.py` lê os acontecimentos de verdade (`life_events`) e decide o post pela vontade dela (motivo + dias sem postar + valence/energia, sem sorteio), com o celular livre (perfil de disponibilidade) e nunca durante a conversa com ele (a foto nova disputa a trava única do `sd_client`). O post dela vira `life_events` tipo `instagram` (linha no Hoje com o logo). Acervo não entra no Hoje.
- **Instagram → voz:** bloco "[SEU INSTAGRAM (@masalles) — aconteceu de verdade]" no dia social (`world_context._social_day_block`): último post, stories no ar e o que ela viu nas últimas 24 h. Ela só vê quando o mundo põe o celular na mão dela (bloco do Instagram, uber, tempo livre).
- **Fotos do chat:** foto vestida mandada pro Patrick (nível 0, ou 1 na rua; nunca adulta) é guardada em `data/instagram/` pra virar post ou story sem custo (`bot._guardar_pro_insta`, nos dois caminhos de envio: turno e promessa).
- **Resposta ao story:** vai pro chat como mensagem dele (`answerWebAppQuery`, a foto do story com o texto) e vira turno dele pelo fluxo normal (sem furar a disponibilidade dela). O app fecha, como no Pix.
- **Custo:** foto nova de post ~20 Buzz (com amiga ~61), post de amiga 20 (Krea 2 Edit sobre o RG, confirmado no teste), no máximo 2 tentativas por acontecimento. Ritmo: ~2 posts dela e ~2 das amigas por semana → ~200 Buzz/mês. Acervo inicial ~400 Buzz, uma vez.
- **Achado de passagem:** o `app.js` criava um `setInterval` de recarga do Bastidores a cada Pix ou pedido feito (colado dentro do `try`); tirado, fica só o do fim do arquivo.
- Migration 031 (`ig_posts`, `ig_comentarios`, `ig_fotos_chat`), com as três tabelas na lista CLEAR do `bootstrap_v36` (vida dela: some numa largada limpa); `tests/test_instagram.py` (23 testes). Suíte inteira: 1.235 testes, verde depois disso.
- **Correção no mesmo dia (Patrick):** texto de personagem com assunto embutido vira bordão quando cada texto é gerado isolado (a Carol falou "bora treinar" em 9 de 9 comentários). Regra aplicada: descrever a pessoa, nunca o assunto, e mandar junto o que ela já escreveu. Mesma lógica da regra "prompts: confiança, sem fala fixa". Roupa: guarda-roupa por ocasião com memória dos últimos 12 posts; praia de biquíni. Migration 032 registrada como reaplicável no `db._run_migrations` (os testes apagam o `schema_version` e rodam de novo).
- **Imagens (mesma noite):** o Krea 2 Edit do Civitai copia do retrato de referência o que não é rosto (roupa, fundo, inclinação da cabeça), mesmo com "take only the face" no prompt. Paliativo no ar: RG com tudo abaixo do queixo pintado de cinza (`civitai_images._rg_rosto`); recorte com altura "quebrada" (721 px) fez o editor responder 500. Solução em andamento: folha de personagem vestida por amiga (3x4 → folha → ajuste à mão). Um commit desta noite (`Frente de imagens (Instagram): editor recebe so o rosto…`) saiu sem atualizar os relatórios; registrado aqui.
- Folha da Bia volta pra fila (Patrick): refazer pelo processo 3x4 → folha → ajuste, como a da Carol.
- **Folhas prontas (27/09, noite):** Bia (refeita), Júlia e Theo, pelo processo 3x4 → folha → ajuste à mão; ~180 Buzz com as refações. Achados: (1) a folha inteira na troca de rosto **vazou o body cinza por cima do biquíni** — a folha também trava a roupa, como o artigo avisa; a troca agora usa a 3x4 com tudo abaixo do queixo pintado (`civitai_images._rosto`, `FRIEND_3X4_FACE`) e a folha fica só pra foto da amiga sozinha (`friend_scene`, prompt `FRIEND_SCENE_PROMPT_SHEET`, que manda a roupa da cena e proíbe body, círculo e fundo cinza) — testado na foto 7, biquíni intacto; (2) a folha cortava na coxa sem pedir "da cabeça aos pés" (agora no prompt); (3) na da Júlia o editor pôs duas luas e a lua no braço errado nas costas, e arredondou o rosto do close — consertado à mão (luas apagadas, close trocado pela 3x4 aprovada); a descrição dela (`visual_profile`) dizia "rosto redondo" e virou "rosto fino e oval" a pedido do Patrick. Foto 7 do acervo: a novo7c (Patrick gostou da Ma nela) com só a cabeça da Carol colada da troca (`instagram_acervo.py --colocar`).
- **Fotos 3, 5, 9, 13 (mesma noite):** achados que valem pro chat também — (1) pose "amiga tirando" de meio corpo com olho na lente e uma mão livre sai selfie (o LoRA dela é de selfie); resolve ocupando as duas mãos e descrevendo a amiga do outro lado (`fora_amiga_sentada`, `KREA2_PHOTO_FRIEND`); (2) a PUC em `camera_world` era "classroom or corridor" genérico e saía escola americana — toda foto dela na PUC (chat inclusive) muda; (3) cena de amiga sem roupa dita herda a roupa da folha. Dois artigos de pose do Krea 2 (Patrick) lidos e guardados na memória: descrever o que a câmera vê (objeto borrado na borda), nunca dar posição à lente, nunca frase de ausência, bloco de identidade longo vence o corte. Arquivos de código foram copiados pra VPS pra rodar o acervo antes do deploy (`camera_world`, `photo_director`, `visual_profile`, `civitai_images`); o deploy deste commit alinha.
- **Textos do acervo (28/09):** o `--textos` apagava **todos** os comentários, inclusive o do Patrick (post 8) e os do post real (6); agora só mexe no acervo e mantém as conversas em que ele entrou (`conversas_do_patrick`). Testado numa cópia do banco antes — e a 1ª cópia enganou: o banco é WAL, `cp` não leva as escritas recentes; cópia de teste é com `sqlite3 … ".backup"`. Comentário por pessoa ainda virava fórmula mesmo com "não repita começo": o modelo ignora pedido genérico; o que funcionou foi tipo de comentário por pessoa + lista explícita das primeiras palavras proibidas.

## Frente dos apps (28/09, madrugada): textos do Instagram revisados
- **Achado sistêmico:** o "não repita" era por pessoa, e cada pedido sorteava o tipo sem memória — o molde migrou de uma pessoa pra todas (legendas de todo mundo no formato "x, y e z + emoji", "entregando" em três pessoas, o Theo convidando em 3 de 7). Corrigido com memória de tipo por pessoa (`ig_tipos_json` no estado relacional), tipos de legenda e o que os outros escreveram no pedido.
- **Desencontro mundo → post:** dois rolês com a Bia (Quartinho 26/09 à noite, cinema 27/09 à tarde) empataram no peso e o `sorted` estável escolheu o mais antigo; o post saiu às 18:58 com o Quartinho de ontem. No empate ganha o mais recente; a roupa segue a hora do rolê. **A foto do post 6 tem luz de dia** num rolê da noite: o diretor gerou a foto com o `now` da hora de postar — a luz pela hora do acontecimento fica pra frente de imagens.
- **Post real refeito com o Patrick de acordo:** `--textos --incluir 6` troca legenda, comentários e a linha do Hoje. Ainda não aplicado na produção (esperando a revisão dele no app).

## Frente dos apps (28/09, manhã): textos na produção e a luz da foto
- **Revisão no app:** o Patrick aprovou sete ajustes à mão (comentário que repetia a legenda, "a amiga que te arrastou", "entregando" de novo, dois sem sentido, a "capinha" elogiada como roupa, o post 3 sem ninguém comentando). **Cópia exata pra produção, sem gerar de novo:** exportados legenda, comentários, memória de tipo e a linha do Hoje do post 6; aplicados com backup (`backups/marin_memory_antes_ig_textos_…`), casando o comentário mantido por id+autor+texto (as respostas encadeadas remapeiam o `pai_id`). Ensaiado antes numa cópia fresca (`.backup`) e comparado: igual. 18 legendas, 50 comentários novos, 4 mantidos (a conversa do post 8).
- **Luz da foto fora de casa (achado sistêmico, vale pro chat):** o diretor não dizia hora nenhuma na foto de fora — só o `PLACE_VISUAL` ("evening indoor ambient light" no Quartinho) — e o molde do Krea 2 diz "natural light", que puxa sol. Agora foto de fora das 18h às 5h diz a noite do jeito que a câmera vê ("warm artificial lights, and any window or doorway shows the dark night street with city lights") e troca "natural light" por "warm night-time light" (`photo_director._luz_fora`). No post, a hora é a do rolê (`direct(scene_at=…)`), não a de postar.
- **Cabelo de cena passada:** o `cabelo.py` guarda só a última lavagem, então a foto do rolê de ontem saía "damp and air-drying" (o banho de hoje). Com `scene_at`, molhado/secando/touca/banho viram o penteado natural.
- `--refoto` agora refaz post de verdade (`foto_post_real`: cena, roupa, luz e amiga pelo `life_events` do acontecimento). Post 6 refeito e aprovado na 1ª tentativa (~72 Buzz): noite na janela saiu mesmo com o "Natural light" maiúsculo do molde da amiga tirando, que a 1ª troca não pegava (agora pega).

## Frente dos apps (28/09, manhã): Bastidores → Por dentro aba a aba
- **Revisão no celular com o banco da produção** (cópia `.backup` às 5h50, ela dormindo desde 0h29). A pré-visualização mostrava o status de exemplo com `--db` ("tempo livre em casa"), por isso a Energia aparecia "cansada" com ela dormindo; agora `webapp_preview.status_real` monta o mesmo retrato do `bot._status_snapshot` a partir da cópia.
- **Achado sistêmico — o Sentindo agora esvaziava:** o painel só lê os episódios ainda quentes (meia-vida de 1h30 a 8h); de manhã, tudo o que ela sentiu na véspera (ciúme pela foto do Instagram, chateada com a Bia, frustrada com ele, contente com o poke) tinha sumido. Entraram **Hoje por dentro** (`EmotionEngine.day_log`, sem decaimento, dia virando às 5h) e **Na cabeça** (a conta da agenda viva à vista, entregas e freela). Vocês dois ganhou Conversa e Pendente.
- **Achado sistêmico — motivo sem padrão:** cada fonte gravava de um jeito (resumo do mundo sem sujeito, planner em 3ª pessoa narrada e longa, frases fixas com "ela"/"te"). Um padrão só, "fato curto · detalhe", em 3ª pessoa com "o Patrick", aplicado na origem (`appraise_event`, prazos, freela, agenda viva, `DEFAULT_CAUSES`, regra do `cause` no planner) e o painel falando "você" (decisão do Patrick: voz de painel, não a dela). Os motivos antigos passam pelo mesmo molde na tela (`motivo_tela._legado`).
- **O ciclo tinha sumido:** o cartão novo da aba Agora (layout D) não tem a linha Ciclo; agora ela está no Corpo ("Dia 27 de 28 · TPM") e o desconforto não repete a fase.
- **"Com saudade de casa com o pai":** preposição dobrada no sentimento; o motivo já diz com quem (`SEM_ALGUEM`).
- **Dia do cabelo:** lavar à 0h06 antes de dormir contava como "lavado hoje" até a meia-noite seguinte; o dia vira às 5h (`cabelo._dia`), no painel ("Ontem à noite") e na lavagem.
- **Desempenho:** a rota `/api/bastidores` leva ~16 s na primeira chamada na VPS (o `agenda.card_casa` resolve o mundo) e 0,3 s depois; no PC, ~50 s. A recarga de 30 s pesa pouco depois da primeira; o frio fica pra frente de infra.
- **Bugs do mundo vistos nos dados** (chip pra frente de bugs): cartão da Agora "desde 05:46" dormindo desde 0h29; plano de sono × banho à 0h06; "o pai deu bom dia" às 21h15 (a frase fixa já mudou pra "O pai perguntou dela", falta ver a origem); "banho quentinho" 4× no mesmo minuto com 1.0; Saudade 100% durante o sono; "ciúme" dela quando era dele.
- **Teste instável (não é desta mudança):** `test_college_d7.MorningTest.test_she_skips_class_when_she_slept_terribly` falha quando o arquivo roda inteiro em 28/09 — a data de início do teste é o dia de hoje e o `_DEPARTURE_CACHE` do `sleep_plan` atravessa os testes; sozinho passa. Falha igual no commit anterior.

## Frente dos apps (28/09, tarde): aba Por fora
- **Aparência sai do Por dentro:** Unhas e Cabelo mudaram pra aba nova Por fora (sem mudar o desenho), abrindo com a seção **Peso** — o peso já existia no mundo (`meals`, semana a semana, balança da academia, dieta da agência) mas não aparecia em tela nenhuma. O painel mostra o de verdade (54,4 kg) e o que ela sabe (Pesou "Sáb, 54,0 kg"): o Bastidores é o que só ele vê.
- **Achado sistêmico — roupa e make não existem como estado:** a roupa nasce na hora da foto (sorteio do guarda-roupa por sessão, `photo_session_json`) e a maquiagem só como passo do card. O Patrick escolheu ter "o look do momento" no topo da aba; antes precisa virar estado do mundo (a roupa do dia pela etapa e pelo lugar, a make feita no Se arrumando e tirada antes de dormir) e a foto passa a usar a mesma roupa. Registrado na frente do mundo.
- **Cinco abas no celular:** a barra de abas passou de quatro colunas iguais pra largura pelo texto; "Por dentro" cabe inteiro em 375 px.
- Testes: `tests/test_por_fora.py` (5) + `test_bastidores_textos` verdes.

## Frente dos apps (28/09, tarde): aba Dinheiro
- **Achado sistêmico — o extrato não sabia de onde vinha cada gasto:** o movimento guardava só o título ("Uber", "Shopping da Gávea · Cinema"), então não dava pra juntar o que foi da mesma saída nem dizer ida/volta. Agora o movimento guarda a chave do acontecimento (`consumo:outing:…:N`, `transporte:commute:…:ida`) e o extrato agrupa por saída; os antigos acham a chave pelo título e pela hora em `life_events`.
- **Totais do mês:** o extrato só guarda 30 movimentos (~3 dias de rolê), então "saiu no mês" contado dali mentiria; o mês vira contador próprio (`financas_json.meses`), preenchido dos movimentos antigos na primeira leitura.
- **Contas dela antes da vida registrada:** o dia das contas de setembro (6) passou antes de 26/09, sem registro; o painel mostra a do mês que vem ("Dia 6/10") em vez de "Dia 6" no passado.
- **Artigo do lugar:** o consumo grava sempre "no {lugar}" ("no Drogarias Pacheco"); o extrato usa o `vontade.no` ("na Drogarias Pacheco"). O resumo do mundo continua com "no" — anotado, não mexi (frente do mundo).
- Testes: `tests/test_extrato.py` (9); `test_bastidores_textos` sem o teste do `mov_desc` (saiu).

## Frente dos apps (28/09, tarde): aba Mundo
- **Fio de sistema no painel:** "Rolando agora" mostrava "Contato de Henrique · Com o pai" — a semente `father_check_in` fica aberta em `story_threads` desde 26/09 ("quando e como Marina responderá ainda não está definido"). O Hoje já escondia essas sementes (`hoje.FORA`); o Mundo agora usa o mesmo filtro (`social_day.SEMENTES`). Achado: a semente nunca fecha — anotado pra frente do mundo, não mexi no banco.
- **Lugares sem informação:** a lista era dos lugares descobertos com a familiaridade ("Conhece"), sem dizer quando nem com quem. Virou "Onde ela foi": as saídas do mês em `eventos_pendentes` (o `status` continua `pending` depois da saída, por isso o filtro é pela hora e por `confirmed`), com os amigos do `metadata_json.friends` e o filme quando é cinema.
- **Quando com maiúscula:** "hoje, 13:50" era a única direita em minúscula no Bastidores; `_quando_curto` só é usado pelo painel.
- Testes: `test_bastidores_textos` com o círculo, o onde foi e a semente escondida.

## Frente de infra (28/09, noite): pilha no limite e o plano do dia calculado uma vez
Pedido do Patrick: resolver antes de construir mais, **só desempenho, sem quebrar nada**. Medido numa cópia do banco
de 28/09 (11:54), com a API de rotas desligada.
- **Achado sistêmico — a pilha não era funda, era um ciclo:** `Commute.legs_on(dia)` pedia a academia
  (`Academia.plano` → `RoutineEngine._placement`), que pedia as janelas de sono, que pediam o despertador
  (`sleep_plan._first_departure`), que pedia `legs_on(dia)` de novo. Não havia fim: **todo resolve batia no limite de
  pilha do Python** (992 de 1000 níveis) e seguia porque o `except Exception` do `_first_departure` engolia o
  `RecursionError` e usava "aula − 40 min". Consequências: o despertador de 4 dos 8 dias de aula conferidos não era
  "ida − se arrumar − margem" (diferença de 2 a 19 min), e **o despertador do mesmo dia mudava conforme a ordem das
  perguntas** e o cache global do processo (mudava num reinício). Qualquer camada a mais (a API de rotas ligada, no teste
  de 28/09) estourava de verdade.
- **Correção:** o sono pede só a ida pra PUC (`Commute.ida_puc`: a ida planejada com o combinado da agenda reativa,
  sem o dia inteiro), e o cache global `_DEPARTURE_CACHE` saiu. Pilha máxima: 992 → 55 (o máximo agora é o import do
  Python). A regra do despertador não mudou; agora ela é cumprida sempre.
- **Plano do dia uma vez por rodada:** `DatabaseManager.rodada()` (um resolve, uma tela do Hoje) e `memo()` guardam
  aulas do dia (`AcademicLife.blocks_on`), ida pra PUC, sono (`bed`, `wake`, `nap`, `micro_wakes`) e trechos
  (`legs_on`) — antes recalculados ~1.100 vezes por resolve (`social_battery.accrue` sozinho pedia o sono 96 vezes). O
  guardado **cai sozinho quando qualquer conexão grava no arquivo** (contador de gravações por arquivo de banco, lido do
  `total_changes` do SQLite na saída de cada `with get_connection()`; vale entre threads e entre dois gerentes do mesmo
  arquivo), não vale dentro de transação aberta e some no fim da rodada. Quem recebe o resultado ganha uma cópia.
  As consultas soltas do sono (`is_asleep`, `in_bed`, `micro_wake_at`, `next_wake_boundary`, `windows_on`,
  `prompt_lines`, `horas_acordada`, `hours_slept`, `napping`, `nights_around`) abrem a própria rodada: sem o cache
  global elas ficariam mais lentas que antes (24 perguntas seguidas: 0,30 s com o cache antigo quente, 0,56 s sem);
  com a rodada, 0,14 s.
- **Números (cópia local, Windows):** resolve 2,9 s → 1,2 s com conexão reaproveitada, como na VPS (do que sobra,
  ~0,9 s era o TMDB com o cache vencido na cópia; na produção o `tmdb_cache` acerta); sem reaproveitar (scripts e
  pré-visualização) 78–85 s → 7,7 s, de 14.659 para 1.167 conexões; `legs_on` 86 → 9 por resolve. A pré-visualização
  (`scripts/webapp_preview.py`) passou a reaproveitar a conexão como o bot — era dela o Hoje de ~65 s.
- **Prova de que nada mudou:** o mesmo roteiro (16 dias de sono, trechos, academia e Milo; 38 resolves de 28/09 12:05 a
  29/09 09:00; Hoje e Agenda) no código antigo (worktree do `b4a526f`) e no novo. Rodada × sem rodada: **0
  diferenças**. Antigo × novo: **0 diferenças nos trechos, academia, Milo e nos 38 resolves**; só o despertador/deitar
  dos dias em que o antigo errava a própria regra. Antigo contra ele mesmo com os dias em ordem inversa: 22 diferenças;
  o novo: 0.
- Testes: `tests/test_infra_plano_do_dia.py` (12): despertador sem montar o dia, despertador = ida − se arrumar,
  independente da ordem, pilha rasa no resolve (os 4 falham no código antigo), e as regras da rodada (grava → recalcula,
  outro gerente do mesmo arquivo, transação, reentrância, dublê de banco, resolve igual com e sem rodada).

## Bug 14 (28/09, noite): o Milo "no sofá" durante o passeio
Visto pelo Patrick no Hoje e no chat. Capturado da produção (só leitura) e o prompt refeito numa cópia do banco.
- **O que aconteceu:** mundo 16:56–17:39 "passeando com Milo" na Enseada (17:07 encontrou a Gabi). Às 17:21 virou
  acontecimento `milo:2026-09-28:arte` "O Milo dormiu encostado nela no sofá". Às 17:24 ele perguntou "fazendo uq de
  bom?" e ela: "Tô organizando umas referências de look aqui e o Milo tá dormindo do meu lado".
- **Camada 1, mundo (a causa):** a arte do Milo sorteia uma hora entre 09:00 e 21:00 e o `Milo.materialize` não olhava
  onde ela estava (só o xixi da noite checava se ela estava em casa). Todas as artes são de casa (sofá, meia, tapete,
  entregador).
- **Camada 2, prompt:** às 17:24 o prompt dizia certo "[SEU ESTADO ATUAL — FATO CANÔNICO] Local: Enseada. Atividade:
  passeando com Milo… Não diga que está em casa", mas também "Sentindo agora: derretida — O Milo dormiu encostado nela
  no sofá" e "17:21 — O Milo dormiu encostado nela no sofá" em "[SEU DIA ATÉ AGORA — aconteceu de verdade]". Dois fatos
  brigando; ela ficou com o sofá.
- **Camada 3, fala:** o "look" não veio do bloco "montando looks" das 16:16 (o prompt das 17:24 não fala de look); veio
  do histórico dela mesma às 13:41 ("largada na sala olhando o Pinterest, achei umas referências de look"). Com o sofá
  dizendo "em casa", ela repetiu o assunto da tarde como se fosse agora. Sem o fato contraditório, o estado atual volta
  a mandar; fica anotado como caso de histórico puxando o assunto velho (voz), sem mudança agora.
- **Correção:** a arte é marcada como coisa de casa (`em_casa`). Com ela na rua, espera; se ela estava fora na hora
  sorteada, o Milo apronta quando ela chega (a hora do acontecimento é a da chegada, não a sorteada), e não entra nos
  30 min antes de deitar (`ARTE_ANTES_DE_DORMIR`). Em casa na hora sorteada, nada muda. O sentimento ("derretida") e o
  Hoje leem o acontecimento, então vêm junto.
- Testes: `tests/test_milo_d5.py` (+3): o caso real de 28/09 (17:21 na Enseada → nada; na volta a pé → nada; em casa
  17:47 → acontece às 17:47), em casa fica na hora sorteada, chegada perto de deitar não tem arte.

## Auditoria de funcionamento, rodada 2 (28/09, 18:00): varredura do Agora e do Hoje
Pedido do Patrick depois do bug 14 ("o Agora e o Hoje ainda têm muitas pontas soltas"). Cópia do banco feita dentro da
VPS (`/tmp/audit_2809`, sem trazer pro PC), `Agenda.card(t)` de 5 em 5 min das 04:00 às 18:00 × `world_state` ×
`life_events` × Hoje × conversa; depois o código novo numa cópia do código em `/tmp` contra outra cópia do banco.
- **Deploy:** VPS em `d9e1dd5`, `main` em `ddf7ebc` (só painel). Distance Matrix funcionando (2–6 chamadas por dia, o
  trajeto fica gravado; a última às 05:16, ônibus pra PUC 41/42 min). As duas falhas `RecursionError` das 17:24 foram no
  processo de antes da correção da pilha (`1d40f4a`, 17:31).
- **Funciona:** manhã da PUC com card e mundo batendo minuto a minuto; vontade Starbucks → emenda na Pacheco → volta, com
  consumo no saldo (27 + 13 + 19); passeio do Milo com preparo, ida, lá, volta e a Gabi por proximidade; tempo livre só
  depois da chegada (13:35, 15:53, 17:43); Hoje com a volta em cada saída e a playlist com os artistas.
- **Quebrou e foi corrigido** (FRENTES, seção 5, item 15):
  - Belisco 16:46–16:52 por cima do Se arrumando do passeio (16:47): o `pending_transition` do belisco vence o preparo
    no resolve, então o mundo nunca disse "se arrumando". `Meals._numa_etapa` agora olha a janela do belisco (15 min).
  - Arte do Milo adiada no minuto da chegada, junto com "Brincando com o Milo": `Milo._depois_de_chegar` — 20–40 min
    depois do primeiro retrato em casa (sorteio por dia), fora de etapa. Chamego separado de arte (`milo.CHAMEGO`;
    Hoje "Chamego com o Milo"; "pediu colo" vira ternura em `emotion.MILO_ANTICS`).
  - Lanchinho da noite sorteado sem olhar o deitar (`Meals._deitar` = `SleepPlan._bed_simple`, sem depender das
    refeições; entra só se acabar 15 min antes); Hoje não prevê nada depois do Dormir.
  - Consumo: "Comprou" em farmácia/mercado (`consumo.COMPRA`), artigo pelo lugar (`vontade.no`), nome de produto
    inteiro (`consumo._frase`). O Hoje lê "Pediu|Dividiu|Comprou … no|na".
  - Hoje: sem a linha "comeu fora"/"lanche na rua" (o consumo com valor já conta), ícone pelo tipo da vontade,
    "Pulou" sem intervalo, bloco em casa cortado no início do próximo; no mundo, `TempoLivre.agora` não começa bloco
    antes do anterior acabar.
  - Card: `Agenda._encontros` — contato presencial dentro do Lá vira `Passo(encontro=True)`: aparece feito, na hora,
    não vira o passo atual (`passo_atual` ignora) e não repete quem foi junto.
- **Conferido na cópia com o código novo:** card da PUC com "Encontrou o Theo 09:46" e "Encontrou a Júlia 12:32", da
  Enseada com "Encontrou a Gabi 17:07"; Hoje com "Pulou o café da manhã 07:52", farmácia com a pílula, desfile até 16:16,
  pão de queijo numa linha só, "Chamego com o Milo"; plano de comida sem o lanche das 22:56; previsto termina no Dormir.
  Os três consumos de hoje ficam com o texto antigo (já gravados).
- Testes: `tests/test_bug_auditoria_2809.py` (12) e `tests/test_milo_d5.py` (o caso do bug 14 agora espera 20–40 min).


## Frente do mundo (28/09, noite): roupa e make de verdade
Pedido do Patrick (aba Por fora, opção C): o look do momento existir no mundo, pra aba e pras fotos.
- **Antes:** a roupa era sorteada a cada foto (`photo_director._outfit` sobre `WARDROBE`), o Instagram tinha outro
  guarda-roupa (`instagram.ROUPAS`) e a make só existia como texto de passo do card. Nada disso conversava: a foto do
  rolê podia sair com uma roupa, o post com outra, e o chat inventava uma terceira.
- **Agora:** `roupa.py` guarda o estado (look, ocasião, desde, pra quê; make com desgaste; por baixo; histórico de 5
  dias) em `estado_relacional["roupa_json"]`, sem migration. Quem escreve: `WorldStateManager.resolve` chama
  `Roupa.tick` no fim (dentro da trava e da rodada) — passos do Se arrumando (roupa, make, tirar make, banho), saída
  sem preparo, chegada (troca em 10–40 min), deitar (pijama; dormiu de make vira acontecimento), sexting (clima);
  `Rituals.start_shower` (make sai, roupa de casa depois); `bot.py` (iniciativa de tesão e escolha do look);
  `TempoLivre` (masturbação chamando ele). Quem lê: `photo_director` (roupa, e a make na frase do prompt; no clima
  `pro_clima` veste e persiste), `world_context` (bloco do prompt), `_ig_shot` (post do rolê com a roupa que ela
  usava lá), `agenda` ("Ficando de lingerie"), `webapp_server` (bloco "Agora" do Por fora).
- **Desempenho (memória "desempenho sem mudar comportamento"):** o tick consultava `Agenda.agora` a cada resolve
  (+17 ms, 34 → 51 ms com o dia em cache, medido num banco de teste). Agora só consulta quando o resolve diz "se
  arrumando" (e uma vez na saída, pra aplicar um preparo que o resolve não viu) e só grava quando algo mudou:
  +4 ms no mesmo teste, concentrado nos minutos de preparo e saída.
- **Cuidados:** peça íntima só entra com contexto de clima (pedido ≥ nível 1 ou sessão ativa) — foto do cabelo ou da
  unha com nível 1 usa a roupa de agora, sem vestir calcinha; a roupa de fora de pose fixa (toalha, capa do salão,
  roupa puxada) continua da pose; treino e biquíni da pose viram os dela quando a ocasião bate. Gaveta fetiche é de
  adulto (nada que remeta a menor); peças novas também vão como foto adulta (regex do `adult`).
- **Testes:** `tests/test_roupa.py` (12) + módulos vizinhos (agenda, agenda reativa/viva, cabelo, câmera, Instagram,
  intimidade, photo_director, promessa, rituais, tempo livre, webapp, world_state: 251 ok) + suíte inteira.
- **Na produção (19:22):** o estado nasceu com ela ainda na academia e a saída aplicou o preparo das 18:23 (top e
  legging, "Academia", desde 18:23). Achado: a roupa de casa da partida foi pro histórico "de 19:22 até 18:23"; troca
  retroativa antes da roupa atual agora a substitui (teste `test_troca_retroativa_nao_deixa_historico_invertido`).

## Freio e soak (28/09, 19:40 — decisão do Patrick)
Nada de funcionalidade nova até o soak fechar. Antes do soak: bug 16, voz (histórico velho, auditoria do prompt, promessa de foto), mundo (lista de compras, bateria social, sementes, revisão de textos), infra (relatório diário do soak + API de rotas) e auditoria de funcionamento rodada 3. Soak: 7 dias reais + 3 limpos; relatório gerado na VPS às 05:10 cobrindo 05:00→05:00. Detalhe e lista "Depois do soak" na seção 0 do `FRENTES_MARINA.md`.

## Bug 16 (28/09, ~18:57): "Me pesei ,4 kg" e "Tô em casa, no sofá com o Milo" treinando na Bodytech
Captura na produção: conversas 224–231, world_state 694–699, life_events 107, journal 21:56–21:58 UTC. Prompt das
18:58 remontado numa cópia do banco feita dentro da VPS (`/tmp/bug16.db`; o banco não sai de lá).
- **Fala (guard de artefato):** "Me pesei hoje: 54,4 kg" caiu no `_DEBUG_ARTIFACT_RE` como `chave: valor` ("hoje: 54")
  duas vezes; o `_salvage_reply` cortou o trecho e sobrou ",4 kg". Com ":" o guard agora exige chave com underscore
  (`htar_negative: 0`) ou valor booleano (`planejamento: true`); com "=" segue pegando qualquer chave.
- **Mundo (pesagem):** `Meals._gym_today` contava o preparo "(colocando roupa de treino)" como treino, e com o trajeto
  (que não é "academia") ela "se pesou na academia" às 18:43, antes de chegar. Agora só "treinando…" conta; a
  pesagem cai quando ela sai do treino.
- **Prompt (estado):** `gym_weekly`, `gym_weekly:rain_fallback`, `milo_morning_walk`, `getting_ready` e `commute`
  caíam em "inferência de rotina (probabilística)" — resto de antes de 26/09, quando academia e passeio eram
  sorteados. Hoje são decididos no dia (`academia.py`) e têm preparo e trajeto: viraram fato com a regra forte. No
  preparo em casa, o texto antigo mandava "não invente ida a lugar externo", o contrário do que ela está fazendo.
- **Prompt (sentimento):** "Sentindo agora: derretida — O Milo dormiu encostado nela no sofá" (17:43, quando ela chegou) às 18:58, sem
  hora, puxou o sofá pro agora (mesmo padrão do bug 14). Episódio com mais de 20 min leva a hora ("(às 17:43)";
  "(ontem, HH:MM)"; "(dia DD/MM)").
- **Sem mudança:** "Mais, seu guloso" estava certo (54,0 kg em 26/09 → 54,4 kg). As referências de Práticas
  Experimentais VI vieram do bloco da faculdade e da fala dela das 17:24 no histórico (item de voz "histórico puxando
  assunto velho", já na lista do soak).
- **Testes:** `tests/test_bug16_academia_sofa.py` (6) + `test_reply_guards_v030`, `test_meals` + suíte inteira.

## Frente da voz (28/09, noite): fechar pro soak — histórico velho, auditoria do prompt, promessa de foto
Método: prompt das 18:58 remontado com o código novo numa cópia do banco e do código dentro da VPS (`/tmp`, produção
intocada; script `remonta_prompt.py` com o relógio de `scripts_clock`), antes e depois.

**Histórico puxando assunto velho (bugs 14 e 16).** O histórico ia pro modelo sem hora: 205 mensagens de dois dias,
todas "agora". O bloco `since_last` ("desde a sua última mensagem… o que você disse pode ter ficado velho") existia,
mas se ancorava na última fala *dela*: às 18:56 estava no prompt (última fala 17:24) e ela acertou; às 18:58 ela já
tinha respondido às 18:57, o bloco sumiu, e o "organizando referências, Milo do meu lado" das 17:24 virou presente.
- `context_builder.marcar_pausas`: a primeira mensagem do Patrick depois de ≥ 20 min sem conversa leva
  `[18:56 — depois de 1h31 sem conversa]` (data quando muda o dia; a pausa antes de uma iniciativa dela marca a dele
  seguinte). Só nas dele — nas dela o modelo copiaria o formato. Vale pro chat e pras iniciativas
  (`generate_dynamic_speech`). `db.get_mensagens_recentes` passou a trazer o `timestamp`.
- `since_last`: numa conversa que acabou de voltar de uma pausa (até 60 min), o bloco fica ancorado na última fala dela
  antes da pausa ("[DESDE A SUA ÚLTIMA MENSAGEM ANTES DA PAUSA NA CONVERSA (às 17:24)]").
- Bloco de estado explica a marca; `[FATOS]` deixou de dizer "trate os últimos turnos como autoridade" sem ressalva
  (agora: autoridade sobre o que vocês conversaram; onde ela está e o que faz, manda o `[SEU ESTADO ATUAL]`) e de
  chamar toda rotina de "probabilística" (o que o estado marca como fato é fato).

**Auditoria do prompt (PLANO_VOZ 16).** Prompt real das 18:58: system 18.080 caracteres, histórico 11.986.
- 🔴 **O lote dele ia duas vezes:** com a fila de disponibilidade (produção), a mensagem é gravada ao chegar e já está
  no fim do histórico; o turno a mandava de novo no fim, depois das dicas. `tirar_lote_do_historico` tira a cópia
  (só as do fim que estão no texto do turno; mensagem antiga sem resposta fica) e leva a marca de pausa pra de baixo.
- Nomes de código e ruído fora: `[CONTINUIDADE] 0 lembretes confirmados; 7 assuntos em aberto` (contagem sem
  conteúdo; os assuntos já vêm por extenso), "fonte única: MenstrualCycleManager", "atualiza known_by",
  "calendário único", "fase: NORMAL" (a fase só aparece quando é de provas, entregas, férias…), data ISO do próximo
  compromisso ("amanhã (29/09) às 07:00").
- Instagram: story e "você viu" de ontem vinham só com a hora ("22:14", "08:56"); agora "ontem, 22:14". "no post de a
  Bia" → "no post da Bia".
- Mantidos: `[VOZ DA MARINA]`, `[LINHAS DURAS]` e `[RITMO]` (sobreposição pequena, voz ajustada com o Patrick; mexer
  às vésperas do soak sem comparação seria mudar a voz no escuro).
- Teto do teste (`test_world_context`, 11.500 → 12.000) mede só a estrutura fixa; o payload real passa a ser medido a
  cada turno pelo log `prompt.payload system=… historico=… dicas=… total=…`, pro relatório do soak.
- Achado pra frente do mundo (não mexido): a semente "Contato de Henrique — quando e como Marina responderá ainda não
  está definido" aparece em `[SEU DIA ATÉ AGORA]` (item "sementes" da lista antes do soak).

**Mensagens fora de ordem (achado nesta conversa).** A foto da promessa, a 2ª foto do gozo especial (sai 20–45 s
depois) e a foto/áudio do próprio turno saíam sem a trava do chat (`_outbound_lock`) e podiam cair no meio dos
balões de outra resposta. Agora passam pela trava.

**Promessa de foto (PLANO_VOZ 15, decidido com o Patrick).** Produção desde 25/09: 5 promessas, 5 cumpridas.
- Ocupada: no banho, na aula (e dormindo, se masturbando, no casting) espera ficar livre; livre, a foto só sai quando
  ela olharia o celular — o tempo que ela levaria pra ver uma mensagem dele naquela atividade
  (`response_availability`, sorteado uma vez por promessa). No clima e entre as opções de look não espera.
- "Quando eu chegar (em casa)": segue o fim do trecho de verdade (+2–10 min); sem trajeto, 20–50 min como antes. A
  validade vai até 1 h depois da hora marcada (mínimo 3 h).
- Venceu ou falhou 3 vezes: por 12 h o prompt diz "[PROMESSA QUE FICOU] Às HH:MM você disse que ia mandar … e acabou
  não mandando" — sem mensagem nova; se ele cobrar, ela admite do jeito dela. Foto mandada depois paga a dívida.

**Achado pra frente de imagens (não mexido):** `test_roupa.test_foto_usa_a_roupa_e_a_make_de_agora` falha 3 em 20
(sorteio). No sexting o nível da foto varia a cada foto; se a 1ª sai nível 1 ("manda de lingerie" → moletom e
calcinha) e a 2ª nível 2, `Roupa.pro_clima` troca a peça no meio da sessão (fantasia de empregada 3 min depois).

- **Testes:** `tests/test_historico_pausas.py` (10), `tests/test_promessa_foto.py` (+4), ajustes em
  `test_v360_acceptance` e `test_world_context`. Suíte: 1.394 testes, 1 falha (a instável acima, de antes desta
  conversa; passa sozinha, 17 em 20).

## Frente do mundo (28/09, noite): fechar pro soak
Item 3 da lista "antes do soak" (freio). Quatro achados, cada um conferido no código e na produção antes de mexer.

**Lista de compras que não existia.** 28/09, 08:52: "quando for fazer compra da semana, compra umas barrinhas" →
"vou colocar barrinhas na lista da semana". Não havia lista no mundo; o mercado da semana (`vontade.mercado_semana`,
pago pelo pai) não tinha itens. Agora `lista_compras.py`: modelo barato (o mesmo da agenda reativa) lê a fala dela e a
mensagem dele só quando o trecho fala de lista/mercado/compra da semana e devolve o que entra ou sai; estado em
`estado_relacional["lista_compras_json"]`; prompt `[LISTA DE COMPRAS DA SEMANA — anotada de verdade]` com quem pediu e
a próxima compra (a de hoje/amanhã na agenda ou o dia do `casa.day_plan`); `world_state.resolve` compra na hora do
"Enchendo o carrinho" (35% do Lá) se ela estava lá (`CalendarWorld.current` com a chegada de verdade) — acontecimento
`lista:<compra>:<item>` (tipo consumo, sem valor; o extrato só lê `consumo:`/`transporte:`/`compra:`, então fica fora,
como a comida que o pai paga); por 48 h o prompt diz que comprou e que está em casa. Card: `Passo.nota` embaixo de
"Fazendo a lista" e "Enchendo o carrinho" (`agenda._nota_lista`, `.ag-nota` no app).

**Bateria social: café sozinha contava como rolê.** `social_battery._kind_at` devolvia SOCIAL (−0,10/h) pra todo
compromisso fora de casa, e o valor OUT_SOLO (+0,01/h) nunca era usado. Agora o tipo do item da agenda única decide
(`KIND_POR_TIPO`): café, açaí, farmácia, mercado, shopping, praia, médico sozinha → OUT_SOLO; orla → SOLO; Milo →
PET_WALK; academia → GYM; unhas/cabelo → MANICURE. Com amiga (`people`) ou sem tipo, continua SOCIAL.

**Semente que nunca fechava.** Produção: 1 história aberta, `father_check_in:2026-09-26` ("Contato de Henrique —
Um contato de Henrique foi informado; quando e como Marina responderá ainda não está definido"), no prompt como
"Assunto em andamento" desde 26/09, com ela falando com o pai 5 vezes depois. A continuação esperava um dia exato
(sorteado 4 → 30/09) e, sem pessoa, nunca vinha. Agora: o pai sai dos ganchos (`HOOKS`); a continuação é o **próximo
contato de verdade** com a pessoa (dia seguinte em diante) e fecha (`resolves=True`); sem contato, a pessoa procura em
1–4 dias; sem ninguém além dela, fecha em 2 dias (`quiet_old_threads`). A semente nasce concreta
(`SocialDay._concretiza`: título com quem, resumo "Começou nesta conversa: …"). Fio de sistema (`SEMENTES`) também não
vai mais pro prompt, como no app. De passagem: convite que ela topava mas viu em cima da hora gravava "Recusou o
convite (…): ." — agora "viu o convite em cima da hora".

**Bug 17 — lingerie trocada no meio do sexting.** Duas causas: (1) o diretor "provoca antes de entregar" (nível 1 →
2) e `Roupa.pro_clima` vestia uma peça nova no nível 2; (2) a pose `cama_perna_pra_camera` tem roupa própria (moletom
azul e calcinha preta) e passava por cima da peça dela. Decisão do Patrick: **lingerie por baixo** — no nível 1 ela
escolhe a lingerie (`POR_BAIXO`) e põe algo por cima (`COBRE`); no 2 tira o de cima; não volta. No clima em casa, a
peça de verdade ganha da roupa fixa da pose (menos a toalha). `test_foto_usa_a_roupa_e_a_make_de_agora`: 0 falhas em
40 rodadas (antes 3 em 20).

**Textos revisados com o Patrick** (card, Hoje, Por fora): regra nova, sem "·" em texto visível (vírgula ou
parênteses); atraso amarelo no Hoje; academia "Cardio na esteira · Superiores/Inferiores"; "Necessidades do Milo";
Por fora "Para", "Maquiagem", barra "Estado". Lista completa no PLANO_WEBAPP ("Mundo fechado pro soak").
- **Testes:** `tests/test_lista_compras.py` (8), `test_social_battery_audit5` (+1), `test_social_day_audit6` (+1 e o
  fechamento no próximo contato), `test_roupa` (bug 17), `test_hoje` (+1), textos atualizados em `test_academia`,
  `test_atraso`, `test_agenda_viva`. Suíte: 1.405 testes verdes (3 pulados).

## Frente de infra (28/09, noite): relatório diário do soak e a API paga de rotas
Item 4 da seção 0 do FRENTES (antes do soak). Nada muda no que ela faz nem nas telas.

**Relatório diário do soak** (`scripts/relatorio_soak.py`, timer `marina-soak.timer` na VPS). Às **05:10** (horário
dela; a VPS está em UTC, o timer diz `America/Sao_Paulo`) copia o banco pra `/tmp` e grava
`/root/bots/marina/soak/dia-AAAA-MM-DD.md`, cobrindo 05:00 → 05:00. Nunca grava na produção e não paga API: depois de
ler o gasto do OpenRouter, apaga as chaves na memória do processo; rotas ficam na tabela (abaixo). ~15 s por dia.
Conteúdo, nesta ordem:
- **Resumo:** mensagens, iniciativas, fotos, suspeitas por tipo, erros de verdade × rede, reinícios, custos, /bom e /ruim.
- **Suspeitas que o script acha sozinho** (quem decide se é bug é quem lê):
  fala × mundo (onde ela diz que está, "tô em casa", "tô no uber", "tô na academia", e o que diz que está fazendo, "tô
  organizando" com o mundo na rua; o estado de até 15 min antes/depois também vale); fala × o que ela fez no dia (comi um
  X, desci com o Milo, treinei, almocei, tomei banho × acontecimentos e estados até aquela hora); card do Agora ×
  mundo (nas falas dela e de hora em hora); fala quebrada (número sem a parte inteira, R$ sem valor, resto de código,
  outro alfabeto, palavra colada repetida, mais os `llm.junk_reply` do log); foto × roupa do mundo; ordem e repetição.
- **Conversa com o mundo:** a conversa com hora, com uma linha "mundo:" cada vez que o `world_state` muda.
- **Aba Hoje** como ficou no fim do dia (`hoje_view` às 03:59 do dia seguinte), acontecimentos (`life_events`), fotos
  que ela mandou com a roupa do mundo, Instagram dela, /bom e /ruim (lidos da biblioteca e da antibiblioteca pela data).
- **Log e serviço:** erros de verdade com a exceção; rede do Telegram, Last.fm e atraso do agendador contados à parte
  (não contam como bug); paradas e quedas do `journalctl`.
- **Custos:** LLM pelo acumulado do OpenRouter (`/api/v1/credits`; foto do acumulado em `soak/.openrouter.json` a cada
  dia, gasto = diferença; o 1º dia só marca), número de chamadas e tamanho do prompt (`prompt.payload`); Civitai (Buzz
  somado do `civitai.submitted`, adultas, falhas); rotas; voz (áudios e segundos).
- **Dia N:** conta a partir de `soak/inicio.txt` (AAAA-MM-DD, criado quando o soak começar); sem ele, "antes do soak".

**Calibrado nos dias 26, 27 e 28/09 da produção:** 26 e 27 sem suspeita; 28 com 9, todas bugs de verdade já
conhecidos: 18:58 "tô em casa" treinando na Bodytech e o ",4 kg" (bug 16), 17:24 "tô organizando uns looks aqui"
passeando com o Milo na Enseada (bug 14), 13:41 "comi um sanduíche" sem sanduíche no mundo (corrigido à tarde em "Bug:
o dia 28/09 visto pelo Patrick"), e as 4 respostas que o próprio bot pegou e refez. Achado de passagem: em 27/09, 21:06,
o bot não subiu porque o Telegram não respondeu na partida (`Network Retry Loop … Timed out`, `status=1/FAILURE`) e o
systemd subiu de novo — o relatório mostra isso na seção Serviço.

**API paga de rotas (`DISTANCE_MATRIX_KEY`).** Produção: 2 a 10 chamadas por dia (26/09: 10, 27/09: 4, 28/09: 2 + 2
falhas do `RecursionError` já corrigido), porque cada trecho é decidido uma vez e guardado (`world_bootstrap`
`commute:DIA:trecho`). O risco era fora do bot: script, varredura na cópia do banco ou relatório resolvendo dias
futuros chamam a API a cada trecho novo, e o `.env` do PC também tem a chave com `COMMUTE_LIVE_TIMES` ligado por
padrão. Agora só o bot rodando paga: `commute.BOT_VIVO` (o `main()` do `bot.py` liga); fora dele o trecho usa a
tabela. A suíte segue como antes (`ALLOW_LIVE_IN_TESTS`).
- **Testes:** `tests/test_relatorio_soak.py` (11, com os casos reais de 28/09); `test_commute_c4`
  (`test_fora_do_bot_script_nunca_chama_a_api`). Suíte: 1.417 testes verdes (3 pulados).

## Auditoria de funcionamento, rodada 3 (28/09, 23:40): tudo junto antes do soak
Item 5 da lista "antes do soak" (freio). Produção em `017a631` = `main`, sem conversa com trabalho parado. Método da
rodada 2: cópia do banco dentro da VPS (`/tmp`, `COMMUTE_LIVE_TIMES=false`), o próprio relatório do soak rodado sobre
28/09 e, pra conferir a correção, a noite refeita com o código novo numa cópia do código em `/tmp` (banco cortado às
20:05, `Rituals.tick` de 5 em 5 min, que é quem move o mundo quando ninguém fala com ela).

**Funciona:** academia com preparo, ida e volta (18:24 → 18:38 → 18:50 → 20:09); jantar do iFood fora do saldo (o pai
paga a comida, D9); lista de compras (barrinhas no prompt, compra no sábado ~10:58); semente do pai fora do prompt e
fechando no primeiro contato dele (29/09 08:30); marca de pausa pra resposta adiada ("[22:58 — depois de 4h sem
conversa]", "desde as 21:45: banho"), resposta ~05:35 com ela acordando 05:20 (aula 07:00); timer do relatório ativo
e o relatório de 28/09 com 0 erros de verdade; nenhum `junk_reply` depois das 20:31 (bug 16). O `RecursionError` das
rotas é das 17:24, do processo antigo. Não exercitado (o soak exercita): bug 17 (clima com foto), bateria social pelo
tipo (nenhuma saída depois das 23:06), card do mercado com a lista (sábado).

**Quebrou (bug 18, seção 5 do FRENTES), a noite de 28/09 depois da academia:**
- **Milo no meio do jantar.** Xixi da noite 21:30–21:38 com o jantar 21:07–21:41; o mundo ficou em "jantando" (o
  acontecimento saía na hora sorteada, só o estado respeitava a transição). Agora, comendo, no banho ou estudando, o
  Milo espera; passou da hora, desce quando ela termina (`milo.materialize`).
- **Trabalho da faculdade às 19:59 dentro do treino.** A sessão (19:59–21:01) foi gravada às 20:29, quando ela chegou,
  com a hora planejada. Agora a sessão espera ela estar livre em casa e começa na hora em que começa de verdade (até
  10 min de atraso vale a planejada); se sobram menos de 20 min até a hora de parar, não senta (`college.materialize`).
- **Sem banho depois do treino** (decisão do Patrick: "banho logo ao chegar"). O banho pós-treino era marcado 20–40
  min depois de sair da academia; o estudo (20:29) e o jantar (21:07) pegaram a vez e a janela de 60 min passou; só o
  banho da noite, 21:52. Agora, saindo do treino a caminho de casa, o banho fica marcado pra chegada
  (`Rituals._banho_pos_treino`, `start_shower(inicio=…)`), e estudo, jantar, Milo e série esperam. Se ele escreve no
  caminho, o aviso diz que ela vai pro banho quando chegar (antes: "ia entrar no banho agora mesmo").
- **"Vou deitar agora" antes do banho** (decisão do Patrick: "banho antes do boa noite"). Deitar 21:51, boa noite
  21:45, banho da noite sorteado 21:50 (janela 19:30–22:30). Agora o banho da noite começa até 65 min antes de deitar
  e, se na hora do boa noite ela ainda não tomou banho, toma primeiro; ocupada (jantar, banho, Milo), o boa noite
  espera e o deitar vai pra 15 min depois do fim. A réplica mostrou por que: com o Milo esperando o jantar, ele desceu
  21:45–21:53 e ela dormia às 21:55 sem boa noite.
- **De passagem:** o bloco em casa começava até 5 min antes do agora ("Brincando com o Milo" 21:50 com o Milo até
  21:53); agora também não começa antes do fim do que ela acabou de fazer (`TempoLivre._chegou`).

Réplica da noite com o código novo: 20:09 voltando da Bodytech (banho marcado 20:23) → banho e cabelo 20:23–21:05 →
jantar 21:07–21:41 → Milo 21:45–21:53 → brincando com o Milo 21:53 → boa noite 22:00 → dormindo 22:10. A sessão de
estudo não aconteceu (sobrou pouco da janela) — como numa noite de treino de verdade.
- **Relógio na suíte:** com a virada pra 29/09 no meio da suíte, `test_agenda_reativa` (academia remarcada/adiantada
  em 26/09) quebrou também sem esta mudança: `Academia.plano` limpava os planos guardados pelo relógio de verdade (hoje
  − 2 dias) e apagava o dia consultado. Na produção dá no mesmo; num relatório com `--dia` antigo, não. Agora a limpeza
  nunca apaga o dia consultado. `test_tmdb_d6` falhou uma vez na suíte e passou 4 de 4 sozinho (instável, anotado).
- **Testes:** `tests/test_auditoria3_2809.py` (15, com os casos reais), `test_rituals_c3` (boa noite com banho tomado;
  banho pós-treino na chegada). Suíte: 1.432 testes verdes (3 pulados).

## Soak, dia 1 (terça 29/09; lido e corrigido em 30/09)
Relatório de 30/09 05:10 (`soak/dia-2026-09-29.md`): 128 mensagens, 6 iniciativas, 1 foto, LLM US$ 0,21, 62 Buzz,
rotas 0, 1 erro de verdade — e **0 suspeitas**. Lendo a conversa com o mundo, o Patrick e eu achamos o contrário: "a
maioria é inconsistência de onde ela está". O `soak/inicio.txt` não existia (o relatório saiu como "antes do soak");
criado com 2026-09-29. Método: cópia do banco em `/tmp` na VPS, `COMMUTE_LIVE_TIMES=false`, chaves zeradas; código
novo numa cópia do projeto (`/tmp/marina_sim`) refazendo o dia 29 de 5 em 5 min.

| Hora | O que se viu | Causa | Camada |
|---|---|---|---|
| 15:01 | "Cheguei em casa" com aula até 15:00 | almoço na PUC (15:18) empurrou a volta pra 16:06; no meio, nenhum estado "na PUC" e o resolve caiu na rotina de casa (`post_event_recovery`) | mundo |
| 16:06 | "indo da PUC pra Enseada a pé" | `volta_puc()` não contava o almoço: passeio do Milo marcado 16:25 (`_class_busy` = 15:45) e `_emendas` juntou a volta da PUC com a ida pro passeio | mundo |
| 16:13–18:13 | "terminando o trabalho" passeando e na manicure | 16:13: o mundo acima; 17:57: `[DESDE A SUA ÚLTIMA MENSAGEM]` dizia as unhas e o histórico venceu | voz |
| 19:01, 19:37 | "plantão de amanhã", "seu plantão" | open loop "Patrick terá um plantão amanhã" de 27/09, sem data | memória |
| 05:36 | "Boa noite, te amo demais tb", no chuveiro | resposta adiada da madrugada: saiu no banho e sem saber que era manhã | voz |
| 05:39 | Milo no meio do banho (05:23–05:47) | xixi da manhã não esperava transição (o da noite já esperava) | mundo |
| 11:47→15:18 | "morrendo de fome", nada por 9 h | belisco só em casa; quatro aulas seguidas sem intervalo | mundo |
| 15:37 | fofoca do porteiro com ela na PUC (achado na simulação) | `casa.py` gravava perrengue/roupa na hora sorteada, em qualquer lugar | mundo |

**Correções** (só conserto, freio da seção 0):
- `commute.volta_puc` sai depois de `Meals.almoco_pos_aula` (igual a `_legs_planejados`); `RoutineEngine._class_busy`
  vai até a chegada de verdade (trava de reentrada `_BUSY_CALCULANDO` contra o ciclo trecho → energia → rotina);
  `_emendas` nunca emenda passeio do Milo (ida nem volta).
- `WorldStateManager._depois_da_aula`: entre o fim da última aula e a saída da volta, estado `pos_aula` na PUC
  ("saindo da aula, indo almoçar…", "almoçando no restaurante da PUC (…)", "saindo da PUC pra voltar pra casa"). No
  prompt é fato (`world_context`); `Meals._fora` e o perfil de disponibilidade (`OUT_SOLO` / `MEAL`) sabem dele.
- `since_last`: uma linha a mais — o que ela disse que estava fazendo ou ia terminar também ficou velho.
- `db.ancorar_datas`: amanhã/hoje/ontem/depois de amanhã viram "na segunda (28/09)" na criação do open loop e na
  leitura (`get_open_loops_ativos`, `get_open_loops_para_checkin`) — cobre os antigos.
- `bot.pending_response_routine` não tira nada da fila com banho em andamento; `_hint_resposta_atrasada` (lote com
  mais de 60 min) diz no turno quando ele escreveu e que ela está vendo agora.
- `milo.py`: xixi da manhã espera banho/refeição, não desce com ela já fora (`_saiu`), some depois de 1 h.
- `meals._belisca_na_puc` (decisão do Patrick, "conserto agora"): com fome, na aula, até 10 min depois de uma aula
  começar (não a primeira), longe da próxima refeição e 90 min do último belisco — "um pão de queijo na cantina da
  PUC" etc. Sem transição (é na troca de aula).
- `casa.py`: roupa, varal, bagunça e perrengue (menos a encomenda "enquanto ela tava fora") esperam ela em casa, até
  4 h.
- `agenda_reativa._classifica`: resposta vazia do modelo vira `warning` (era traceback no relatório).
- `scripts/relatorio_soak.py`: seção **Mundo × mundo** (teleporte, trajeto saindo de onde ela não estava, refeição ×
  lugar, coisa no meio do banho), "trabalho" dito na rua/caminho/salão (`RE_TRABALHO`) e saudação fora de hora. Dia
  29: 10 suspeitas, todas reais; dias 27 e 28: 3, reais daqueles dias (a Pacheco de 27/09, o Milo e o sofá de 28/09).

**Simulação do dia 29 com o código novo:** aula até 15:00 → "saindo da aula, indo almoçar" → almoço 15:18 → volta
16:06–16:51 → casa (fofoca do porteiro 16:55) → Milo 17:07–17:46 → unhas → casa; beliscos na cantina 11:00 e 13:00.
O banho da manhã é ritual do bot (não roda na simulação): coberto por teste.

- **Testes:** `tests/test_soak_dia1.py` (os casos reais acima).

## Soak, dia 2 — manhã de 30/09: "ela tá completamente alucinada" (olhado na hora)
Patrick perguntou se esperava o relatório de amanhã; olhei na hora (dia inteiro perdido se fosse grave; o relatório
de 01/10 cobre o dia do mesmo jeito). Tudo antes do deploy do dia 1 (08:55). Quatro causas, nenhuma igual às de ontem:

| Hora | O que se viu | Causa | Camada |
|---|---|---|---|
| 08:38 | "vc que tá dodói" (ele está bem) | "Tá dodói? O que houve?" (ele perguntando dela) casou com `PATRICK_SICK_RE` e o `[ELE ESTÁ DOENTE]` ficou por 8 mensagens | voz |
| 05:21, 07:34 | "hoje é dia livre", "ainda bem que hoje não tem aula" | faltou por cólica: `cancel_class_occurrence` esvazia `blocks_on`, e o prompt e o bom dia liam "sem aula" | voz |
| 08:36 | "lembrei do papo do meu peso, tem novidade por aí?" | open loop `waiting_reply` "Esclarecer se o peso mencionado por Marina…" no check-in | memória |
| 07:01–08:49 | "Regando as plantas" 5x, uma às 07:26 no fim do banho | antes das 8 o único tipo era "plantas" e cada pedaço sorteava de novo; `_chegou` não via a transição acabada | mundo |

**Correções:** `health._ele_doente` (frase com "?" ou com vc/tu/cê/"tá dodói" é sobre ela); `College.falta` e o
`[VIDA ACADÊMICA]` diz "Hoje TINHA aula e você faltou — …", o bom dia "hoje tinha aula e você decidiu faltar (…)";
`db._assunto_dela` tira do check-in assunto que fala da Marina sem o Patrick; `tempo_livre`: não repete o tipo
anterior, `plantas`/`plantas_tarde` uma vez no dia, sem opção → Instagram/TikTok/Milo (`CORINGA`), e `_chegou`
respeita o fim da transição (banho, refeição) dos últimos 15 min.
- **Testes:** `tests/test_soak_dia2.py` (7); módulos vizinhos na cópia isolada iguais à produção.

**30/09, 11:03–11:48 — a escova que não aconteceu (depois do deploy das 09:03).** Cadeia: `Cabelo.talvez_salao`
("trabalho", job amanhã) sem olhar o corpo (cólica forte, desconforto 0,8 o dia todo), as aulas que ela faltou
(07–13h) nem a comida que o Patrick estava pedindo → `atraso.py` empurrou a ida pra 11:45–11:55 (troca de roupa,
celular com o Patrick, chave) → 11:36 a canja chegou e ela comeu em casa → `AgendaReativa._chances` (passando mal)
→ `_atual` achava que ela estava "lá" desde o horário marcado (11:22), não desde a chegada → `interromper`: volta de
uber às 11:41 de onde ela nunca esteve, `Cabelo.materialize` cobrou a escova no fim encurtado (R$ 70), uber R$ 12;
às 11:48 a ida atrasada ainda estava de pé ("indo pro Ophicina a pé").
**Correções:** `AgendaReativa._atual` só devolve o compromisso depois do fim da ida (vale pra interromper, pausar e o
"está no meio de outra coisa"); `Vontade._sem_condicao` (usado por `_livre_ate`, portanto vontade, salão e unhas):
desconforto ≥ `SAIR_DESCONFORTO_MAX` (0,5), antes do fim das aulas que ela faltou (`falta:<dia>:*`) ou com comida
chegando (`Meals._comida_chegando`) → não sai. `test_unhas` ganhou a trava neutra (o sorteio em 0 do teste valia
também pra saúde). **Produção, a pedido do Patrick ("desfaz tudo"):** evento cancelado às 11:52; com o bot parado,
`desfaz_salao.py` tirou os 4 acontecimentos, devolveu R$ 82 ao saldo (chaves ficam em `vistos`), limpou a
interrupção/uber/aviso da agenda reativa, voltou o cabelo (lavado 29/09 05:23, seco natural) e trocou as falas
11:37 e 11:40; o que havia está em `soak/originais-2026-09-30-salao.json`.
- **Testes:** `tests/test_soak_dia2.py` (+2).

**30/09, tarde — trabalho dito × mundo, check-in do assunto dela, e o dia de amanhã visto antes.**
- *Trabalho:* `College.session_on` só punha a sessão na janela da noite (20:21); a fala prometia agora. Decisão do
  Patrick ("a fala vira mundo"): `College.observe_marina_line` (chamado depois de cada fala, em `bot.py`) — "vou
  pegar firme", "tô fechando o trabalho agora", "vou abrir o arquivo" (sem "mais tarde/depois/à noite"), livre em
  casa e antes da hora planejada → grava `facul:adiantou:<dia>` e `session_on` começa ali; a `materialize` segue igual.
- *Check-in:* a instrução do `open_loop_checkin` (as duas cópias: `proactivity_service` e `_PROACTIVE_INSTRUCTIONS`)
  tratava todo assunto como dele. Agora diz: coisa dele, pergunte; coisa sua, conte como está de verdade. O filtro
  `_assunto_dela` (nome dela sem o dele) fica.
- *"Cabelo novo" 13:06:* `current_shared_topic` ainda com o salão — o desfazer não limpou o assunto do planner.
  Open loop 28 fechado. *"vai###":* `limpar_fala_marina` tira `#{2,}`.
- *01/10 planejado* (cópia do banco, código novo em `/tmp/marina_sim3`): antes, almoço no Shopping da Gávea 15:18
  com casting 15:30; volta da PUC 15:50 emendada no 2º casting; `_emendas` exigia `ida.end > volta.start` e não
  sabia de mesmo lugar (ela "voltava pra casa" às 17:00 e estava "a caminho" do 2º desde 15:50); passeio do Milo
  17:48 dentro do casting (`_placement` não via saídas); almoço "quando voltar" 17:40 dentro do 2º (`_antes_das_saidas`
  via só a 1ª saída). Consertos: `SAIDA_DEPOIS_DA_AULA` (2 h) em `almoco_pos_aula`; `_emendas` com `>=` e mesmo
  lugar remove volta e ida; `Agenda.etapas` põe "lá" + volta de compromisso sem ida emendado no mesmo lugar;
  `_placement` bloqueia saídas (preparo `SAIDA_ANTES`, volta `SAIDA_VOLTA`); `Meals._saidas` junta saídas a ≤15 min;
  `_record` de refeição pulada fora do café: "não deu tempo entre os compromissos". Depois: PUC → agência
  15:00–15:30 → castings 15:30–18:30 → casa 18:55, almoço pulado, jantar 19:33, sem passeio do Milo (só o xixi).
- **Testes:** `tests/test_soak_dia2.py` (+5).
- *30/09, noite — "Beliscou pipoca vendo série"* (10:03 no closet, 18:41 no TikTok; o Patrick viu duas vezes): o
  prato do lanche vinha com a cena ("pipoca vendo série") em `MENU["lanche"]` e no lanchinho da noite; o Hoje dizia
  uma série que não houve. Prato agora é "pipoca". Teste em `test_soak_dia2` (+1).

**01/10, manhã — o relatório do dia 2 inteiro (`soak/dia-2026-09-30.md`, 7 suspeitas, 4 erros, 3 /bom e 10 /ruim).**
O que já estava no item 20 (manhã, salão, trabalho, check-in, pipoca, "###") ficou de fora. Novo:

| Hora | O que se viu | Causa | Camada |
|---|---|---|---|
| 21:57 | Hoje: "Tirou a roupa da máquina e estendeu no varal" com o banho 21:34–22:01 | `Casa.materialize` só esperava ela estar em casa; o varal (máquina + 70–100 min) caiu no banho e foi gravado na hora planejada às 22:02 | mundo |
| 11:37, 13:06 | relatório: "0 fotos"; ele perguntou "aquela roupa da foto que mandou" | a foto da conversa (`bot.py`, pedido/iniciativa no turno) ia pro Telegram e não entrava em `conversas`; só a foto prometida (`promessa_foto`) entrava | voz |
| 13:08 | traceback `agenda_reativa.classifica` (JSONDecodeError) | resposta do modelo cortada no meio do JSON | voz |

**Correções:** `Casa.materialize` — coisa de casa espera `Meals._transition_busy` (banho, refeição, Milo); se a hora
planejada caiu dentro de banho/refeição/Milo já gravados (`Casa._ocupada_em`), acontece agora; varal e "esqueceu a
roupa" só depois da máquina gravada + 60 min. `bot.py`: depois do `send_photo` confirmado, `adicionar_mensagem`
(assistant, `media_type="photo"`, `[1 foto(s): <facts>] <legenda>`, o formato da foto prometida). `_classifica`:
`JSONDecodeError` vira aviso `classifica_json_quebrado`. `limpar_fala_marina`: travessão e ponto e vírgula viram
vírgula, dois pontos entre palavras viram vírgula (hora "15:30" e ":(" ficam) — decisão do Patrick (01/10: "agora, no
filtro"), pelos /ruim 039, 042, 043 e 044.
**Relatório (alarmes falsos):** "acabou de acordar, ainda de pijama" é em casa (05:21 card vazio e 06:16 teleporte);
"tô treinando com você" não é academia (`FIGURADO`).
**Ruído conferido, sem conserto:** consolidação de memória "Múltiplas decisões sobre o mesmo fato" (2x; o cursor não
avança e a próxima passa), Vision com JSON cortado às 09:34 (a resposta saiu certa), 2 respostas com letra
estrangeira pegas e refeitas, reflexão de sessão com JSON cortado. A sessão de trabalho aconteceu (19:56–20:56); o
banho veio antes do boa noite (21:34–22:01, deitou 22:27). Sem linha "tomando banho" no mundo à noite porque nada
resolveu o mundo durante o banho (o card resolve na hora; não é bug).
**Lote de texto (não zera):** "seu bobo atrevido" depois de só um "ksksks", "convencido" de novo (já no dia 1),
"derretida/arrepiada" demais, "abusado demais" fora de contexto.
- **Testes:** `tests/test_soak_dia2.py` (+6).

## Catálogo de textos, lote 1 aplicado (01/10, noite, frente de apps)

As 205 fichas do Hoje e do card do Agora (118 mudar, 87 manter) e as seis regras gerais (`data/feedback/catalogo_textos/
regras_gerais.md`) entraram na tela. **Só a tela muda:** o mundo grava o mesmo texto e o prompt dela não viu diferença
(as fichas "os dois" viraram regra nova de tela no `hoje.py`). Única mudança que ela lê: o passo "Chamando o Uber"
(antes "Chamando uber") aparece no "se arrumando pra sair pro X (chamando o Uber)".

**Onde mexeu.** `hoje.py`: `curto(ev, db)` (o banco serve pra cortar as aulas perdidas pelos nomes das matérias e
achar o tipo do job da manicure); `_painel` sem `voz_painel` (regra 6, "o Patrick"); `_saidas` com Indo/Está/Foi;
previsto "Vai para o…" na hora em que sai de casa; `sub_presente`, `filhos_presente` e `presente` dos filhos no
gerúndio; topou herda a hora do convite; filhos de um acontecimento dentro de uma saída vêm logo embaixo dele.
`agenda.py`: `aprox` sem "~", `por_volta`, `duracao` por extenso, `futuro` ("Vai ver série"), `CELULAR_TELA` /
`celular_tela` (o `bot._celular_na_mao` compara os textos internos, que ficam), `Etapa.com_art`, "Saiu mais cedo"
depois que saiu, `prep_activity` lendo "por volta das" (o texto do mundo continua "pra sair pro X"). `cinema.py`:
"Assistindo: {filme}", "Olhando as lojas", "No provador". `webapp_server.status_view`: celular da tela.
`webapp/app.js`: "desde as", "Manhã, 7 acontecimentos", vazios.

**Conflitos resolvidos com o Patrick (01/10):** "faltam 58 minutos" sem "aproximadamente" (regra 1 vence a ficha);
descida do Milo "Descendo com o Milo" → "Desceu com o Milo" (a ficha, com o gerúndio da regra 3).

**Decidi sozinho (pra ele revisar):**
- "O Milo se aliviou" com artigo nos três lugares (a ficha do Hoje dizia "Milo se aliviou"; a do card, "O Milo…"; o
  passo do passeio curto em casa estava "manter", mas é o mesmo texto).
- iFood que ele mandou e ela comeu: "Comeu o iFood recebido" / "O Patrick pediu no {loja}" e um item por linha
  (a ficha cru.3 olhou esse mesmo acontecimento cru e pediu "O Patrick mandou um iFood" — ficou só pro que ela
  guardou sem comer). Presente com "de surpresa": "O iFood surpresa do Patrick chegou".
- "Comeu o iFood pedido" (o delivery dela) segue com o prato embaixo: o pedido dela ainda não tem loja (iFood da Ma é
  do depois do soak).
- "Com" do card começa maiúsculo ("A Bia e o Theo"); "Como" segue "Uber com Bia" (não estava na ficha).
- Assunto que vem como frase (o pai, continuação) segue "Assunto: …" até o texto dos assuntos (depois do soak); os
  de uma palavra viram "Falaram de festas e do Caio".
- Ícone da desistência: chuva `cloud-rain`, cansaço/sono/bateria `battery-1`, desânimo `mood-sad`, dor/cólica
  `first-aid-kit`, dinheiro `cash-off`, combinou com o Patrick `heart-handshake`, outro `x`.
- "Recebeu um Pix do Patrick" com "Para o Uber"; "Remarcou Quartinho Bar" / "Para domingo às 18:00"; convite
  "Para o Quartinho Bar às 21:00" (sem o "hoje"); "Volta para casa por volta das…" no "Lá" e no passeio do Milo.
- Ofertas de casting: "Participar da campanha…", "das fotos…", "do vídeo de uma marca…" ("pra uma" → "de uma").
- O "Bateu papo com a Gabi" também aparece no card (o encontro no "Lá" usa o texto do Hoje).

**Bug visto na varredura e corrigido junto:** a linha 2 do card mostrava "Chega na Agência boutique da Lívia
(fictícia)" — a marca do banco vazava pra tela (`agenda._tela`). Efeito no mundo: o "se arrumando pra sair pra
Agência boutique da Lívia" que ela lê também perdeu o "(fictícia)".
**Vi e não mexi (não é deste lote):** "para o Ophicina do Cabelo" / "Chega no Ophicina" (gênero do
`commute._FEMININE`, que o chat também usa); "Saindo de lá, resolveu passar…" cru no Hoje quando a emenda não acha a
saída; "Saiu mais cedo na agência às 17:30" cru (agenda reativa); "Vendo série" no card enquanto acontece (só o
futuro estava na ficha).
**Conferência:** varredura na VPS (código antigo × novo, mesma cópia do banco, 7 dias): 0 erros. Testes: 69 módulos
que tocam card/Hoje/Mini App (856 testes) — 46 asserções eram as frases antigas, atualizadas; uma era bug meu
(desistência na hora com ícone duplicado, `TypeError`), corrigido antes do deploy. `tests/test_catalogo_lote1.py`
(+18).

## Soak, dia 3 — quinta 01/10, o dia dos dois castings (relatório de 02/10 05:10, lido em 02/10)

`soak/dia-2026-10-01.md`: 57 mensagens dele e 62 dela, 3 suspeitas, 1 erro de verdade, 4 /ruim, US$ 0,24 de LLM,
20 Buzz. O dia planejado em 30/09 (item 20) aconteceu como o simulado: faltou a aula pela cólica (05:02, agenda
viva), ônibus 15:00, 1º casting 15:30–17:00, 2º emendado na mesma agência; às 17:30 saiu passando mal, de uber
(R$ 29); tigela que ele pediu às 19:08.

| Hora | O que se viu | Causa | Camada |
|---|---|---|---|
| 05:32 | "Hoje é dia livre da facul, não tenho aula pra faltar" (e 05:35 "tô fechando o trabalho agora"; ele: "tô entendendo mais nada") | a falta veio da agenda viva (`agenda:faltou:2026-10-01`); `College.falta` só procurava `falta:` e o prompt dizia "Hoje NÃO tem aula (dia livre)" | prompt |
| 11:29 | "só sei que a canja chegou mais cedo" | a canja foi 30/09 11:36; o open loop 26 "Avisar o Patrick quando a canja chegar para ele pedir o suco" seguia aberto e entrava em [ASSUNTOS AINDA EM ABERTO] | memória |
| 18:30 | Hoje: "Fez o casting na agência… agora é esperar a resposta" (o 2º) | ela saiu às 17:30 (agenda reativa, `interrupcao:freela:2026-10-01:casting:2026-09-29`); `Freela._advance` registrava o casting no fim do horário sem olhar a interrupção, e marcava resposta pra 03/10 | mundo |
| 08:04 | foto dele: "que lindo, começou o dia com estilo" | `VisionService`: JSON mal formado ("Expecting property name…"), foto sem leitura, ela respondeu às cegas | voz |
| Hoje | "Foi para a agência" 14:58–17:00 e "Foi para a agência" 17:00–17:53 | `hoje._saidas` agrupa por compromisso; os dois castings emendados no mesmo lugar viravam duas saídas | app |
| 05:22/05:24 | bom dia ("acabei faltando à aula hoje…") e, dois minutos depois, "Acordei agora e vi isso, te amo demais tb" | o ritual do bom dia sai sem olhar a fila: as mensagens dele de 22:52 (ela dormindo) saíram depois | voz |

**Correções:** `College.falta` lê `falta:` e `agenda:faltou:` (prompt e bom dia). `delivery.fecha_promessas_do_pedido`:
pedido que chega (dela ou presente dele) resolve o open loop aberto que fala em "chegar" e cita o prato. `Freela`:
compromisso encerrado mais cedo pela agenda reativa (`_saiu_no_meio`) vira `casting_perdido` ("Não terminou o
casting (…): saiu no meio, {motivo}."), sem resposta. `vision_service._json_tolerante` (cerca de markdown, texto em
volta, vírgula sobrando) e uma 2ª chamada com mais tokens. `hoje._saidas`: compromisso que começa quando o anterior
termina, no mesmo lugar e sem volta no meio, entra na mesma saída. `bot._bom_dia_na_resposta`: com lote pendente dele,
o bom dia não sai sozinho — o lote é antecipado (`PendingResponseRepository.antecipar`) e a resposta leva
`[PRIMEIRA MENSAGEM DO DIA]` com o que o bom dia contaria.
**Produção (OK do Patrick, 02/10):** o "Fez o casting" das 18:30 virou `freela:2026-09-29:casting_perdido` às 17:30;
o estado do freela desse casting foi pra "fim" (a Lívia não responde em 03/10); open loop 26 resolvido. Originais em
`soak/originais-2026-10-01.json`.
**Relatório (alarmes falsos):** «tomei um Buscopan» — é do mundo (`health.conditions`, cólica moderada: "tomou um
Buscopan de manhã"); «jantei» — a tigela das 19:08 ("presente do Patrick") foi o jantar. `feito_extra` conta refeição
depois das 17h como jantar e o remédio das condições de saúde.
**Leve, sem conserto:** 09:30 "a Dona Neide tá terminando a faxina" (foi até 13:41); 23:21 "vou largar o celular e
dormir" e seguiu respondendo até 23:28 (ele seguia falando). Os dois castings com o mesmo "vídeo pra uma marca de
cosméticos" (ofertas de 28 e 29/09 sortearam o mesmo tipo).
**Lote de texto (não zera):** /ruim 048 "O Uber tá andando e eu te mando…", 049 "vou papá-la toda", 050 "guloso
afetuoso", 051 "tô aceitando, amor, finalmente" (forçado).
- **Testes:** `tests/test_soak_dia3.py` (+13).

## Soak, dia 4 — sexta 02/10, olhado à tarde (até 15:41, antes do Quartinho; pedido do Patrick)

Relatório parcial gerado na VPS (`relatorio_soak.py --dia 2026-10-02 --out /tmp/…`, sem custos): 96 mensagens dele, 99
dela, 1 suspeita, 4 erros, 7 /ruim e 1 /bom.

| Hora | O que se viu | Causa | Camada |
|---|---|---|---|
| 13:53, 14:22 | "distração g-relacionada", "capricha no desfile, hein GATE_CHANNEL" (/ruim 052, 055) | o modelo colou rótulos do prompt ("[CLEAN START GATE]", "[CANAL DE DADOS]"); o guard de artefato (`_DEBUG_ARTIFACT_RE`) não pegava CAIXA_ALTA com "_" | voz |
| 14:23 | a confirmação do /ruim 055 não chegou (`BadRequest: Can't parse entities`) | o "_" da fala citada quebrou o Markdown de `_wizard_send` | voz |
| 13:48–15:15 | "aqui tá sequinho", "dia quente", "nem tá chovendo" e depois "tô de guarda-chuva" | Open-Meteo marcava chuvisco (códigos 51–55) desde as 10h; o provedor só gravava `heavy_rain` (≥ 3 mm) e a temperatura, o prompt só falava de chuva forte, e a coordenada (-43.2105) era o Corcovado, 558 m, 17,8 °C contra 21 °C em Botafogo. `vontade`, `tempo_livre` e `agenda_viva` liam `w.get("rain")`, que ninguém gravava | mundo/prompt |
| 15:01 | a foto dele ("Se explique aí então sua safada") sem leitura | a 2ª tentativa de ontem também foi cortada: a visão escreve demais (cortes em 300 e 500 tokens, 58 linhas) | voz |
| — | toda foto em casa saía com chuva na janela quando o tempo era conhecido | `photo_director`: `"rain" in json.dumps(weather)` achava o nome "heavy_rain" | imagens |

**Correções:** `_DEBUG_ARTIFACT_RE` com `(?-i:\b[A-Z]{2,}(?:_[A-Z0-9]+)+\b)` (refaz como os outros artefatos; "TPM",
"PIX" e "UFRJ" passam). `_wizard_send` manda sem formatação se o Markdown quebrar. `real_context_provider`: longitude
-43.1868 (Botafogo, 14 m), `weather_code` no pedido e `condition` (`_condicao`: clear, cloudy, drizzle, rain, storm;
`calendar_world` aceita "drizzle"). `world_context.tempo_agora`: "[TEMPO AGORA EM BOTAFOGO] 21 °C, chuvisco. Se o
tempo entrar na conversa, é esse; não invente sol, calor ou chuva diferente." `vontade/tempo_livre/agenda_viva._chuva`
leem `condition in (rain, storm)` (chuvisco não segura saída). `photo_director`: chuva só com `heavy_rain` ou
condição drizzle/rain/storm. `vision_service`: 800 tokens (1500 na 2ª) e "no máximo 5 itens por lista".
**Pro Patrick decidir, ficou "vida" (minha opinião; ele estava indeciso):** 14:40 vestiu o baby-doll "pra provocar" e
no mesmo minuto a vontade a levou pro açaí, com o vestido xadrez por cima; a história seguiu coerente e ele entrou
nela. Se repetir (sair no meio de toda conversa quente), vira bug.
**Alarme falso:** 09:37 teleporte do passeio do Milo (o Hoje tem a volta 09:33–09:37; o mundo só não foi gravado).
**Leve:** Quartinho duas noites seguidas (hoje com a Júlia, marcado em 29/09; amanhã a Bia chamou pro mesmo bar).
**Ok:** dayoff, Enseada com o Milo, farmácia (Buscofem e ibuprofeno), banho, almoço que ela fez, açaí e Rei do Mate
pagos, Pix de R$ 1000 no saldo, foto com o vestido do mundo; 2 fotos recusadas pelo Civitai não viraram foto falsa.
**Lote de texto (não zera):** /ruim 053 reações a elogio "porcas e repetitivas" ("tá abusado hj, hein menino"), 054
"gosto quando você gosta", 056 "plano de elogio bem convincente" (formal), 057 "eu sabia que era boa", 058 a ideia
boa dita de um jeito ruim; "convencido" de novo (15:35). /bom 144 "comprar roupa bonita é miojo, Patrick?".
- **Testes:** `tests/test_soak_dia4.py` (+9).

**02/10, tarde — as duas fotos que não vieram (o Patrick perguntou por que eu não falei).** 14:55 e 15:41 ele pediu
foto; as duas falharam e ele recebeu o texto fixo de `bot.py` "Amor, tentei te mandar a fotinho agora mas a câmera do
apê travou 🥺 Me pede de novo…" — com ela no açaí e no Rei do Mate —, e a frase não entrava em `conversas` (ela não
sabia que tinha dito; o relatório não mostrava). **Falha minha na leitura:** vi os 2 `civitai.sfw_flagged_by_moderator`
e escrevi "não viraram foto falsa" sem conferir o que ele recebeu; era mensagem quebrada (grave).
**Causa:** pedido reconstruído numa cópia do banco — selfie normal na rua (`unhas_selfie_rua`, nível 1, vestido
xadrez); o moderador do Civitai recusa "young Brazilian woman" com "a sultry half-lidded look and a slow teasing
smirk" (expressão de `photo_director.expression` no clima ativo). **Teste (OK do Patrick, 31 Buzz):** o mesmo
pedido recusado de novo (recusa não cobra); trocando só a expressão por "a soft playful smile", passou e saiu
coerente (vestido xadrez, unha rosa, rua de Botafogo).
**Correções:** `civitai_images.ultima_recusa_sfw`; `sd_client.generate_directed` refaz uma vez com
`photo_director.suavizar` (as três expressões quentes → "a soft playful smile") quando o moderador recusa foto normal.
Se falhar mesmo assim, `bot._foto_nao_saiu`: a fala é dela (`generate_dynamic_speech`, sabendo onde está, "não culpe
câmera, celular ou internet"; reserva "Amor, a foto saiu toda tremida kkk já já te mando outra"), entra no histórico
e vira promessa de selfie (`promessa_foto.observe_marina_line`); `foto.nao_saiu` é aviso (aparece no relatório).
**De passagem (fala × mundo, não mexi):** ela disse "baby-doll de tule por baixo"; pro mundo o baby-doll das 14:40 saiu
quando ela se vestiu pro açaí (só o vestido). Fica pra a frente do mundo olhar (roupa de provocar + saída).
- **Testes:** `tests/test_soak_dia4_fotos.py` (+7).
