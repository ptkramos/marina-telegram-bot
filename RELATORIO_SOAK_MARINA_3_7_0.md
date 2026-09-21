# Relatório Vivo do Soak — Marina 3.7.0

**Status:** EM ANDAMENTO  
**Início limpo:** 19/09/2026 às 03:28 (America/Sao_Paulo)  
**Objetivo:** registrar cada comportamento observado, correção aplicada, evidência de validação e resultado percebido durante o soak real.

Este é o arquivo acumulativo oficial do soak. Novas correções devem ser acrescentadas em ordem cronológica; entradas antigas não devem ser apagadas. Conversas pessoais devem ser descritas apenas o suficiente para reproduzir o defeito, sem copiar conteúdo íntimo desnecessário.

## Baseline do novo soak

- Banco reiniciado pelo `/limpar` com backup automático em `backups/pre_soak_reset_20260919_032828_296878.db`.
- Conversas: 0.
- Fatos aprendidos: somente `Nome: Patrick Ramos`.
- Momentos, resumos, estilo, feedbacks, loops e respostas pendentes: 0.
- Identidade, calendário, ciclo e mundo canônicos preservados.
- WorldState inicial: `dormindo`, rotina `light_day_sleep`.
- Fotos em manutenção; pedidos recebem explicação dinâmica da LLM.

## Como registrar uma ocorrência

Para cada problema ou melhoria, adicionar:

1. data e horário;
2. contexto mínimo e comportamento observado;
3. comportamento esperado;
4. causa encontrada;
5. patch aplicado e arquivos alterados;
6. testes executados;
7. resultado no Telegram após reinício;
8. status: aberto, monitorando ou resolvido.

## Patch 001 — Continuidade na madrugada e memória contaminada

**Horário:** 19/09/2026, 02:46–03:11  
**Status:** MONITORANDO

### Observado

- Marina foi classificada como disponível durante a madrugada.
- Perdeu a continuidade imediata, inventou uma ida ao mercado e voltou a cumprimentar no meio da conversa.
- Uma referência sem sujeito identificado foi promovida a fato, momento, resumo e tópico compartilhado.

### Correção

- Sono determinístico em dias de aula até 07:00 e dias leves até 08:30.
- Estado acordado cacheado é invalidado quando começa a janela de sono.
- Mensagens durante o sono não são liberadas antes do fim da janela.
- Reparos de contradição usam contexto imediato, temperatura menor e não aplicam efeitos persistentes do Planner.
- Memórias com referente ambíguo são recusadas antes da persistência.
- Registros contaminados foram removidos do banco real.

### Validação

- Estado do mundo: 9 testes aprovados.
- Autoridade de prompt: 19 testes aprovados.
- Disponibilidade: 21 testes aprovados.
- Memória local: aprovada; verificações opcionais externas ficaram sem rede.

## Patch 002 — Reset real do soak e orçamento de naturalidade

**Horário:** 19/09/2026, 03:18–03:24  
**Status:** MONITORANDO

### Observado

- O `/limpar` antigo apagava apenas a tabela de conversa e mantinha aprendizado anterior.
- As 20 respostas anteriores tinham média de 109,5 caracteres, mediana de 103 e máximo de 189; o tamanho casual estava adequado, mas a forma semântica continuava artificial.
- O teto técnico casual era 512 tokens, incompatível com o soft limit de aproximadamente 180 caracteres.
- O modo empolgado raramente era alcançado e dependia de quebra de linha produzida pelo modelo para usar dois balões.

### Correção

- `/limpar` agora cria backup e zera conversa, fatos aprendidos, resumos, momentos, estilo, feedbacks, tópicos, loops e estado operacional dinâmico.
- Identidade e mundo canônicos continuam intactos.
- Orçamentos ajustados para 122 tokens no casual, 242 no normal/supportive/excited e 482 nos modos longos.
- Uma única reescrita concisa é permitida quando a saída supera o dobro do soft limit; frases nunca são cortadas cegamente.
- Empolgação explícita pode separar duas frases completas em dois balões.

### Validação

- Response Rhythm: 8 testes aprovados.
- Reset de memória: 5 testes aprovados.
- Preflight: 37 recursos ativos.

## Patch 003 — Limpeza do histórico visível no Telegram

**Horário:** 19/09/2026, 03:28–03:31  
**Status:** VALIDADO NO TELEGRAM

### Observado

- O banco foi zerado corretamente, mas três lotes de exclusão do Telegram falharam com `Message can't be deleted for everyone`.
- Cada lote misturava mensagens recentes com IDs antigos ou inapagáveis; uma falha impedia a remoção das mensagens válidas do mesmo lote.

### Correção

- A limpeza começa pelas mensagens mais recentes.
- Se o lote falhar, cada mensagem recebe uma tentativa individual.
- A busca para após atingir uma sequência de mensagens inapagáveis, respeitando o limite imposto pelo Telegram.
- O resultado registra quantas mensagens foram tentadas e apagadas.

### Validação

- Testes offline cobrem fallback individual e parada ao alcançar histórico inapagável.
- Reteste real confirmado pelo usuário: o `/limpar` removeu corretamente o histórico visível permitido pelo Telegram.
- Este ponto passa a ser o marco inicial limpo do novo soak test da versão 3.7.0.

## Próximas observações

Biblioteca complementar preenchida durante as conversas: [`data/feedback/BIBLIOTECA_COMPORTAMENTAL_MARINA.md`](data/feedback/BIBLIOTECA_COMPORTAMENTAL_MARINA.md).

- Naturalidade da primeira saudação após o início limpo.
- Continuidade em correções e provocações curtas.
- Frequência real de um, dois e três balões por modo.
- Distribuição de caracteres por modo, não apenas média global.
- Perguntas finais: necessárias, opcionais ou mecânicas.
- Ausência de biografia, tarefas e deslocamentos inventados.
- Qualidade das explicações dinâmicas enquanto a GPU de fotos estiver em manutenção.

## Patch 004 — Runtime canônico 3.7.0 e remoção do self-edit

**Horário:** 19/09/2026, 12:20–12:43  
**Status:** VALIDADO — PRONTO PARA O SOAK

### Observado

- Vinte flags de release ainda podiam selecionar caminhos antigos ou fallbacks parciais.
- O Telegram ainda expunha `/edit`, `/rollback` e `/patches`, mantendo o AutoPatcher no processo principal.
- Testes históricos criavam bancos sem World Bible ou vida acadêmica e validavam modos OFF que já não representam a release 3.7.0.
- Um JSON malformado do consolidator podia virar um lote vazio antes da validação.

### Correção

- World Bible, World State, Planner, memória inteligente, privacidade, calendário acadêmico, relacionamento, Camera World, Response Rhythm e Response Availability agora são caminhos únicos de produção.
- As vinte flags centrais deixaram de ser lidas do `.env`; marcadores de compatibilidade não alteram o runtime.
- AutoPatcher e comandos `/edit`, `/rollback` e `/patches` foram removidos. A migration/tabela histórica permanece apenas para compatibilidade do SQLite.
- Emoção, assuntos em aberto e oportunidades de reconfirmação foram incorporados ao World Context canônico.
- Payload inválido de consolidação agora falha antes de qualquer escrita.
- Permanecem apenas controles operacionais, providers, telemetria e kill switches que pausam capacidades sem restaurar arquitetura anterior.

### Validação

- Regressão completa: 401 testes aprovados; 3 ignorados por desenho.
- Compilação Python: aprovada.
- Auditoria de Prompt Authority: aprovada.
- Preflight: runtime canônico, 18 switches operacionais ativos, banco íntegro e voz pronta.
- Live gate sem mensagens: Telegram read-only, LLM, voz conversacional, voz íntima e desculpa dinâmica de foto aprovados; FLUX aceito indisponível durante manutenção da GPU.
- Startup gate: 26 PASS, 0 WARN, 0 FAIL e cinco jobs de produção registrados.
- Startup real: `Application started` às 12:44:47, jobs ativos e primeiro ciclo de pending responses concluído sem erro.
- Encerramento controlado às 12:45:16; nenhum processo Python 3.10 da Marina ficou ativo. Próximo passo operacional: abrir `run_local.bat`.

## Patch 005 — Mensagem fantasma contaminando o contexto imediato

**Horário observado:** 19/09/2026, 12:58–13:01  
**Status:** VALIDADO — BOT REINICIADO

### Sequência observada

1. Patrick disse: “Tô no trabalho esperando meu ifood chegar”.
2. Marina respondeu que também estava com fome e “torcendo pra meu delivery chegar logo”, criando um pedido próprio sem base no estado do mundo ou na conversa.
3. Depois que Patrick informou o almoço dele, o SQLite registrou uma resposta de Marina dizendo estar comendo “salada de salsichas, ketchup e batata frita”. O print do Telegram comprova que essa resposta nunca foi entregue.
4. Patrick perguntou diretamente “E você pediu o que?”.
5. O turno seguinte recebeu a resposta fantasma como histórico e Marina respondeu como se Patrick a tivesse visto: “Hahaha, parece que você não tem muita fé na minha opção, né? Mas fique tranquilinho, Knowing Me, Knowing You também é uma escolha.yum”.

### Classificação

- **Invenção autobiográfica momentânea:** criou um delivery e uma refeição sem evidência canônica.
- **Mensagem fantasma:** uma fala cancelada durante a simulação de digitação foi persistida antes da confirmação do Telegram.
- **Divergência de contexto:** o modelo recebeu uma fala da Marina que Patrick nunca recebeu, fazendo “minha opção” parecer coerente apenas no histórico interno.
- **Corrupção linguística:** inseriu título/frase em inglês e o sufixo desconexo `.yum` numa conversa em português.

### Evidência técnica

- Modelo ativo no incidente: `mistralai/mistral-nemo` via OpenRouter.
- Todas as chamadas relevantes retornaram HTTP 200; não houve erro de provider.
- O turno passou pelo runtime canônico e pelo modo `casual_short`; nenhum fallback legado foi acionado.
- O histórico imediato estava persistido no SQLite e continha as afirmações conflitantes.
- O Planner chegou a registrar os tópicos `Lunch` e `Lunch order`, mas isso não impediu a quebra de continuidade.
- A resposta não entregue é a conversa SQLite ID 10, criada às 13:01:17. O print mostra a mensagem de Patrick às 13:00 seguida diretamente por “E você pediu o que?” às 13:01.
- O caminho `REPLY_NOW` gravava usuário e assistente antes de `send_human_messages`. A chegada do turno seguinte cancelou a tarefa durante o atraso de digitação, mas a linha do assistente já estava no banco.

### Correção

- A entrada do usuário passa a ser persistida separadamente assim que o turno é processado.
- A fala da Marina e os efeitos do Planner só são gravados depois que o Telegram devolve um `message_id` válido.
- Cancelamento durante digitação preserva a mensagem real do usuário, mas não cria fala, tópico ou efeito fantasma da Marina.
- A mesma regra foi aplicada às respostas de cancelamento, escolha de avatar, introdução/legenda de avatar e `/start`.
- O registro fantasma ID 10 foi removido do banco real após backup em `backups/soak/pre_patch005_20260919_1315.sqlite`.
- Regressão específica e bateria de lembretes/conversação: 37 testes aprovados.

### Validação operacional

- Compilação dos arquivos alterados: aprovada.
- Regressão focada: 37/37 testes aprovados, incluindo cancelamento durante o atraso de digitação.
- Banco real: a conversa fantasma ID 10 não existe mais.
- Instância antiga encerrada de forma direcionada; os processos Python 3.13 externos ao bot não foram alterados.
- Nova instância 3.7.0 iniciada às 13:19:20; Telegram `Application started` às 13:19:28 e primeiro ciclo de respostas pendentes concluído sem erro.

### Conclusão sobre o modelo

Este caso não serve como evidência de que DeepSeek perdeu contexto. A principal quebra veio do pipeline, que entregou ao modelo um histórico diferente do Telegram. A invenção inicial do delivery e a corrupção `.yum` continuam sendo sinais úteis para uma futura comparação Mistral Nemo versus DeepSeek, mas devem ser avaliadas separadamente da mensagem fantasma.

## Patch 006 — Retorno ao DeepSeek após correção do pipeline

**Horário:** 19/09/2026, 13:25–13:27  
**Status:** VALIDADO — BOT REINICIADO

### Decisão

- O modelo configurado voltou de `mistralai/mistral-nemo` para `deepseek/deepseek-chat` via OpenRouter.
- A comparação passa a ocorrer sobre o runtime canônico 3.7.0, sem os fallbacks de release e sem persistência de respostas não entregues.
- O período anterior com Mistral permanece como evidência de ocorrências em inglês, corrupção `.yum` e invenção autobiográfica; os próximos turnos servirão como amostra comparável do DeepSeek.

### Validação

- Configuração carregada localmente como `deepseek/deepseek-chat`.
- Chamada sintética ao modelo: aprovada, sem enviar histórico pessoal ou mensagem ao Telegram.
- Nova instância iniciada às 13:26:48; Telegram `Application started` às 13:26:54.
- Recuperação de disponibilidade limpa: nenhum lote pronto, desconhecido ou pendente.
- Primeiros ciclos de respostas pendentes e lembretes concluídos sem erro.

## Patch 007 — Correção da Visão Multimodal, Balões Múltiplos e Moderação de Tom

**Horário observado:** 19/09/2026, 14:34–14:41  
**Status:** MONITORANDO NO TELEGRAM  

### Sequência observada

1. Patrick enviou fotos no chat (uma foto assistindo Konosuba no trabalho e outra logo em seguida). Ambas as fotos foram recebidas pelo bot, porém não obtiveram resposta alguma de Marina no Telegram.
2. Nas mensagens de texto, Marina respondeu 100% das vezes com apenas um único balão, sem nunca alternar para dois balões mesmo quando havia duas ideias distintas ou resposta acompanhada de pergunta.
3. Marina entrou em um viés de dependência e carência dramática excessiva (“sou toda intensa mesmo”, “não consigo passar muito tempo sem saber de você”, promessas com “fofuras” e emojis em todas as frases).

### Classificação e Causa Raiz

- **Visão Multimodal com Modelo Descontinuado (HTTP 404):** `settings.VISION_MODEL` apontava por padrão para `google/gemini-2.0-flash-001`, que foi descontinuado e removido dos endpoints da OpenRouter (`Error code: 404 - No endpoints found`). O modelo multimodal ativo e homologado no catálogo é `google/gemini-2.5-flash`.
- **Crash no Processamento de Fotos (`AttributeError: 'NoneType'`):** Quando a LLM retornou conteúdo vazio/nulo, `completion.choices[0].message.content.strip()` estourou exceção não tratada em `handle_photo_message`. Além disso, a persistência ocorria antes da confirmação de envio do Telegram (vulnerabilidade a mensagens fantasmas).
- **Bloqueio Estrutural de Múltiplos Balões:** Em `response_rhythm.py`, `segment()` continha `if policy.target_bubbles > 1:`. Como `target_bubbles` era fixado em 1 para todos os modos cotidianos (`casual_short`, `normal`, `supportive`, etc.), o teto `max_bubbles = 2` era sumariamente ignorado e mensagens com quebras ou duas ideias nunca eram divididas.
- **Loop de Intensidade e Saturação Emocional:** A LLM gerou falas autojustificando apego com o rótulo de “intensa”; o consolidador de memória absorveu isso e gravou no SQLite (`Marina Salles prometeu... demonstrando sua intensidade`), reinjetando esse viés em loop no system prompt, enquanto as variáveis internas de carinho e paixão atingiram o teto de saturação (1.0).

### Correção Aplicada

1. **Visão Multimodal:**
   - Atualizado `VISION_MODEL` em `config.py` para `google/gemini-2.5-flash`.
   - Testada e validada a extração visual estruturada end-to-end com sucesso.
2. **Robustez e Anti-Ghosting em Fotos:**
   - Em `bot.py:handle_photo_message`, adicionada leitura segura de `content` (`getattr` / `or ""`), tratamento com bloco `try/except` e fallback para `mistralai/mistral-nemo` se a chamada primária falhar.
   - Persistência no SQLite (`user`, `assistant` e efeitos do `planner`) migrada para ocorrer estritamente após a confirmação de entrega do Telegram com `message_id` válido, consistente com o Patch 005.
3. **Segmentação Orgânica de Balões:**
   - Em `response_rhythm.py`, `segment()` agora avalia `if policy.max_bubbles > 1:`, permitindo divisão em até `max_bubbles` quando o modelo utilizar quebras de linha (`\n`) entre pensamentos com mais de uma palavra, ou quando `target_bubbles > 1`.
   - Atualizado `apply_policy` no Response Rhythm orientando o modelo a utilizar quebra de linha quando desejar enviar dois balões naturais.
4. **Moderação de Tom e Higiene de Memória:**
   - Adicionadas diretrizes explícitas nas regras de controle (`CONTROL_EN` e `CONTROL_PT` em `prompt_policy.py`) proibindo melodrama, carência excessiva, juras dramáticas desproporcionais, a desculpa clichê de “sou intensa mesmo” e a obrigatoriedade de emojis em toda frase, reforçando o perfil autêntico de uma garota carioca de 20 anos (afetuosa, bem-humorada, independente e descomplicada).
   - Realizado backup do banco em `backups/soak/pre_patch007_20260919_145248.db`.
   - Higienizado o registro em `momentos_marcantes` (ID 5) e normalizadas as dimensões de `estado_emocional` para os valores de baseline.

### Validação

- **Visão Computacional:** teste sintético com imagem azul via `vision_service.analyze_image` retornou descrição precisa (`scene: a solid blue image`) via `google/gemini-2.5-flash` sem erros.
- **Segmentação de Balões:** teste unitário de 2 parágrafos confirmou divisão limpa em 2 balões; teste com 1 parágrafo preservou 1 balão.
- **Regressão:** bateria de 29 testes cobrindo `test_vision_service`, `test_response_rhythm` e `test_prompt_authority_v370` executada com 100% de aprovação (29/29 OK em 29.6s).
- Compilação: todos os módulos alterados compilados com sucesso.
- Instância Operacional: processo anterior (PID 9672) encerrado; reinicialização automática pelo `run_local.bat` com nova instância (PID 1856) iniciada às 14:54:38; Telegram `Application started` às 14:54:44; jobs autônomos e de availability ativos sem erros.

## Patch 008 — Estabilização de Rotina contra Jitter Climático e Limpeza de Comandos

**Horário observado:** 19/09/2026, 16:03–16:25  
**Status:** VALIDADO — BOT REINICIADO  

### Sequência observada

1. No console do `run_local.bat`, foram registrados logs de disponibilidade: `AVAILABILITY_DECISION decision=REPLY_BRIEFLY activity=GYM source=ROUTINE_PROBABILITY`.
2. Ao executar `/status` no Telegram às 16:11, o retorno informou que Marina estava com atividade `tempo livre em casa` no `Apartamento da Marina (Botafogo)`.
3. Além disso, comandos administrativos acionados no chat deixavam mensagens de comando visíveis no histórico do Telegram.

### Classificação e Causa Técnica

- **Diferença entre Disponibilidade e Afirmação Factual:** A atividade `GYM` gerada pelo `response_availability` com `source=ROUTINE_PROBABILITY` é uma inferência probabilística para calibrar tempo de resposta humano (delay de ~90-140s e mensagens breves), respeitando a regra canônica de que rotinas não geram claims factuais nem certezas inventadas.
- **Invalidação Prematura por Jitter de Clima (`weather_changed`):** Em `world_state.py`, o cache do estado comparava o dicionário bruto de clima (`weather_context_json`). Às 16:03:26, o estado foi gerado sem temperatura (`None`); às 16:11:07, a API climática forneceu `20.2°C`. A diferença fez `weather_changed = True`, invalidando precocemente o estado com apenas 7 minutos de existência e forçando um novo sorteio probabilístico (`self.routine.choose`), que caiu no fallback `tempo livre em casa`.
- **Comandos Administrativos no Chat:** `/gravar_boa_noite`, `/gravar_voz_normal`, `/gravar_voz_intima`, `/lembretes`, `/cancelarlembrete`, `/hygiene` e `/refletir` não apagavam a mensagem original do usuário após o disparo.

### Correção Aplicada

1. **Estabilização de Cache no `world_state.py`:** A verificação de `weather_changed` agora monitora exclusivamente alterações no indicador de chuva forte (`heavy_rain`), que é o único fator climático que altera a rotina da Marina (deslocando a academia externa para a academia do prédio). Oscilações normais de temperatura ou preenchimento de cache não resetam mais a atividade em andamento antes do prazo canônico (`stale_minutes = 60`).
2. **Auto-exclusão de Comandos:** Adicionado `await context.bot.delete_message` nos handlers dos comandos administrativos em `bot.py` para manter o chat limpo.

### Validação

- **Regressão de Estado:** `tests.test_world_state` executado com 100% de aprovação (9/9 OK em 3.5s), incluindo testes de transição por chuva forte e expiração de compromissos.
- **Compilação:** `bot.py` e `world_state.py` compilados sem erros.
- **Instância Operacional:** bot reiniciado com nova instância (PID `36772`) às 16:28:11, scheduler ativo e pronto para continuidade do soak.

---

## 2026-09-19 — Patch 009: Humanização de Lembretes, Descrições em PT-BR e Integração de Atividades Compartilhadas no WorldState

### Sintomas Observados

1. **Descrição em Inglês em Contexto 100% Brasileiro:** Durante proposta de assistir ao jogo de futebol juntos, o `InternalPlanner` gerou o compromisso e o lembrete com descrição em inglês (`Watch Botafogo game together`), que foi exibida na mensagem para o usuário.
2. **Oferta Inadequada de Lembrete Prévio para Evento Iminente:** O sistema ofereceu agendar lembrete com antecedência para uma atividade combinada para menos de 15 minutos no futuro, calculando um horário que já estava no passado no momento da confirmação.
3. **Sobrescrita Robótica da Resposta (`reminder_decision_text`):** Ao confirmar o lembrete, a resposta natural gerada pela LLM foi descartada e substituída por uma string de template estática e impessoal (`Combinado, amor! Lembrete confirmado para...`), descaracterizando a persona e ignorando o conteúdo falado pelo usuário.
4. **Disparo Imediato e Não Registrado:** O lembrete vencido foi disparado em background 13 segundos após ser confirmado e não foi registrado na tabela de conversas.
5. **Lacuna no WorldState para Atividades Compartilhadas:** O motor de mundo continuava indicando `tempo livre em casa (inferência de rotina)` mesmo após um plano explícito de assistir ao jogo juntos ter sido acordado.

### Classificação e Causa Técnica

- **Língua do Prompt do Planner:** O `PLANNER_SYSTEM_PROMPT` definia o esquema JSON em inglês sem regra estrita de que os campos de conteúdo textual (`description`, `follow_up_prompt`, `shared_topic`) fossem obrigatoriamente gerados em português brasileiro natural.
- **Sobrescrita Legada da v3.5:** Em `bot.py`, `reminder_decision_text` sobrescrevia `fala_limpa` diretamente após a geração da LLM, impedindo que a Marina confirmasse com sua própria voz e empatia.
- **Ausência de Registro em `reminders_routine`:** O envio do lembrete via scheduler chamava o Telegram mas não persistia na tabela `conversas`.
- **Filtro Estrito de Propriedade no Calendário:** `CalendarWorld._dated()` consultava apenas `owner_character_key='marina'`, ignorando compromissos mútuos ou planos compartilhados com o Patrick.

### Correção Aplicada

1. **Prompt Authority em PT-BR no `planner.py`:**
   - Adicionadas regras rígidas no `PLANNER_SYSTEM_PROMPT` exigindo que todas as descrições e ganchos de acompanhamento sejam em Português do Brasil (PT-BR).
   - Inclusão da regra explícita de bom senso temporal para não ofertar lembretes para eventos com menos de 45 minutos de antecedência.
   - Atribuição automática de compromissos compartilhados (`owner_character_key='marina'`, `confirmed=1`, `end_at` calculado e `location_key='marina_apartment'`).
2. **Eliminação da Sobrescrita Robótica em `bot.py`:**
   - Removida a substituição direta de `fala_limpa = reminder_decision_text`.
   - Adicionada injeção de diretriz de turno no prompt da LLM (`reminder_decision_instruction`), permitindo que a Marina confirme o lembrete usando suas próprias palavras, tom e respondendo ao conteúdo do usuário.
   - Persistência garantida na tabela `conversas` (`memory_manager.registrar_mensagem_assistente`) ao disparar notificações de lembrete pelo scheduler.
3. **Integração de Compromissos Sociais e Compartilhados no `calendar_world.py` e `world_context.py`:**
   - `CalendarWorld._dated()` agora suporta `owner_character_key IN ('marina', 'shared')`.
   - `CalendarWorld.current()` projeta a descrição real da atividade para compromissos sociais/encontros no apartamento, refletindo a atividade no `WorldState` (`Assistindo ao jogo do Botafogo na TV em casa com o Patrick pelo Telegram (compromisso/plano explícito)`).
   - `world_context.py` mantém a localização clara como `Apartamento da Marina` em eventos caseiros em vez de ocultar como `local reservado`.
4. **Saneamento e Correção de Mensagens no Telegram e DB:**
   - Mensagens 837 e 839 editadas diretamente no Telegram e atualizadas no SQLite para falas naturais e carinhosas da Marina.
   - Mensagem de lembrete duplicada/vencida (ID 840) apagada do Telegram.
   - Snapshot atual do `world_state` sincronizado para a atividade do jogo em andamento (17h–19h).

### Validação

- **Bateria de Testes Abrangente:** 66/66 testes aprovados (100% OK):
  - `tests.test_planner`: 9/9 OK
  - `tests.test_reminder_service`: 8/8 OK
  - `tests.test_world_state` & `tests.test_calendar_academic_v364`: 23/23 OK
  - `tests.test_prompt_authority_v370`: 18/18 OK
  - `tests.test_response_rhythm`: 8/8 OK
- **Instância Reiniciada:** Bot reinicializado com nova instância operacional limpa via `run_local.bat`, scheduler ativo e ouvindo no Telegram.

## Patch 010 — Integração Botafogo Live Tracking (API-Sports) & Reações Espontâneas de Torcedora

**Horário:** 19/09/2026, 17:42–17:53  
**Status:** VALIDADO — BOT REINICIADO E MONITORANDO SEGUNDO TEMPO AO VIVO

### Contexto e Motivação

- Durante o teste de soak, o usuário solicitou integrar o acompanhamento em tempo real das partidas do Botafogo via API-Football / API-Sports.
- A intenção é transformar Marina em uma companheira torcedora autêntica, permitindo que ela assista aos jogos e comente os lances capitais (gols do Botafogo, gols sofridos, intervalo, cartões vermelhos e apito final) com o Patrick no Telegram, com emoção e espontaneidade de uma jovem carioca de 20 anos.
- Durante a validação, coincidiu de o Botafogo estar jogando ao vivo contra o Mirassol pelo Brasileirão Série A.

### Solução Técnica Implementada

1. **Credenciais e Configuração Segura:**
   - Adicionada chave da API-Sports oficial (`APISPORTS_KEY`) no `.env` e carregada via `config.py`.
   - Adicionadas flags `BOTAFOGO_TRACKING_ENABLED`, `BOTAFOGO_POLL_INTERVAL_SECONDS` (120s) e `BOTAFOGO_TEAM_ID` (120).
2. **Módulo `botafogo_service.py`:**
   - Consulta ao endpoint oficial `https://v3.football.api-sports.io/fixtures?live=all&team=120`.
   - **Gestão Inteligente de Cota Diária (100 req/dia):**
     - Trava estrita de segurança em 90 requisições diárias (evita estouro de cota do plano gratuito).
     - Cadência adaptativa (`should_poll`): durante partidas ao vivo, polling a cada 2 minutos (120s), consumindo ~50 requisições em 105 minutos de jogo; quando não há jogo ativo, reduz frequência para 15 minutos (tarde/noite) ou 60 minutos (madrugada/manhã).
   - **Detecção e Deduplicação Estrita de Eventos:**
     - Assinatura única para cada lance (`fixture_id:elapsed:type:detail:team_id:player_name`), impedindo reações duplicadas ao mesmo gol ou cartão.
     - Detecção de transições de status da partida: 1H -> HT (Intervalo), HT -> 2H (Início do 2º tempo), 2H -> FT (Fim de jogo).
   - **Suporte a Simulação Sintética (`simulate_event`):**
     - Permite simular qualquer evento (`gol_pro`, `gol_contra`, `intervalo`, `inicio_2t`, `fim`, `vermelho`) para testes imediatos sem necessidade de aguardar partida real.
3. **Integração no `bot.py` e Geração Humanizada:**
   - Criada a rotina `botafogo_match_routine`, agendada a cada 120s no `AsyncIOScheduler`.
   - Criado o handler `handle_botafogo_reaction`, que formata a instrução de contexto esportivo, chama `generate_dynamic_speech` (com persona, prosódia e controle de balões) e despacha via `send_human_messages` com persistência na memória.
   - Novos comandos no Telegram:
     - `/jogo` ou `/botafogo`: exibe o placar e tempo ao vivo, adversário e cota da API utilizada.
     - `/simular_lance <tipo>` ou `/simularlance`: comando administrativo de soak para acionar uma reação simulada.
4. **Isolamento e Hermeticidade dos Testes:**
   - Criado `tests/test_botafogo_service.py` cobrindo parsing, controle de cota, deduplicação de eventos, transições de status e simulações sintéticas.
   - Patch no teste `test_world_context.py` isolando `CalendarWorld.current` para impedir falso-negativo causado por compromissos reais ativos no banco local.

### Validação

- **Testes Automatizados:** Bateria completa aprovada sem regressões:
  - `tests.test_botafogo_service`: 5/5 OK
  - `tests.test_planner`: 9/9 OK
  - `tests.test_reminder_service`: 8/8 OK
  - `tests.test_response_rhythm`: 8/8 OK
  - `tests.test_proactivity_service`: 6/6 OK
  - `tests.test_prompt_authority_v370`: 18/18 OK
  - `tests.test_calendar_academic_v364`: 22/22 OK
  - `tests.test_world_context`: OK
- **Runtime Operacional:** Bot reiniciado com sucesso via `run_local.bat`, ouvindo no Telegram com `botafogo_match_routine` ativo e pronto para o segundo tempo de Mirassol x Botafogo.

## Patch 004 — Cadência WhatsApp, Multi-Balão e Sincronização Inicial do Botafogo

- **Data e Horário:** 19/09/2026 às 18:15.
- **Contexto Observado:** Durante o intervalo do jogo Mirassol x Botafogo, foram identificados 3 comportamentos anômalos no soak real:
  1. Ao iniciar o monitoramento, a Marina disparou mensagens retroativas dos 2 gols anteriores do Mirassol acumuladas de uma só vez (IDs 54 e 55).
  2. A Marina continuou enviando mensagens longas em bloco único ("testamentos"), sem quebrar em múltiplos balões curtos como esperado para uma jovem no WhatsApp.
  3. No prompt do Botafogo, a Marina usou emojis inadequados como coração amarelo (`💛`), apesar de o Botafogo ser estritamente preto e branco.
- **Causa Raiz:**
  1. Em `botafogo_service.py`, `check_live_updates()` não diferenciava o polling inicial (`is_initial_sync`) dos ciclos seguintes; como `seen_events` começava vazio, eventos passados da partida eram classificados como novos.
  2. Em `response_rhythm.py`, `apply_policy()` continha uma tupla agressiva de limpeza (`conflicts = ('balões', 'balão', 'anti-textão', ...)`) que apagava silenciosamente qualquer linha de prompt mencionando "balões" ou "anti-textão".
  3. O orçamento de tokens para `casual_short` era de ~122 tokens (teto de 180 caracteres), permitindo que a LLM gerasse 4 a 5 frases densas.
  4. O algoritmo `segment()` dependia estritamente de quebras de linha (`\n`) para segmentar em múltiplos balões Telegram quando `target_bubbles == 1`. Como a instrução havia sido limpa pelo filtro e o histórico de 50 mensagens anteriores só continha blocos únicos, a LLM espelhava as mensagens longas sem quebras.
- **Solução Técnica Aplicada:**
  1. **Sincronização Inicial Silenciosa (`botafogo_service.py`):** Adicionada flag `is_initial_sync` na rotina de polling para preencher `seen_events` silenciosamente no primeiro ciclo de checagem.
  2. **Preservação de Diretrizes de Ritmo (`response_rhythm.py`):** Ajustado o filtro de conflitos para restringir apenas as chaves legadas exatas (`'ritmo: múltiplos balões'`), impedindo o expurgo indevido de regras de concisão.
  3. **Canonicidade do Idioma de Controle:** A regra de modo `casual_short` em `response_rhythm.py` e a diretriz `[TURN CONSTRAINT — CASUAL CADENCE]` em `bot.py` foram padronizadas em inglês seguindo a arquitetura `PROMPT_CONTROL_LANGUAGE = 'en'`, instruindo explicitamente a LLM a manter no máximo 1-2 frases curtas com quebra `\n` entre reações.
  4. **Orçamento de Tokens Reduzido:** Em `ResponseStylePolicy`, o orçamento para `casual_short` foi reduzido para 75–85 tokens, limitando fisicamente a prolixidade.
  5. **Restrição Estrita de Emojis do Fogão:** Proibição explícita do emoji amarelo `💛` e limitação a `🖤, 🤍, ⭐️, 🔥`.
- **Testes e Validação:**
  - `tests.test_response_rhythm`: 8/8 OK.
  - `tests.test_botafogo_service`: 5/5 OK.
  - `tests.test_soak_readiness_v370`: 19/19 OK.
  - Verificação de runtime: o bot foi reiniciado via `run_local.bat` com as novas regras ativas.
- **Status:** Resolvido e monitorando em tempo real durante o 2º tempo.




## Patch 012 — Cadência Livre de Balões (Marina Decide, Não o Código)

**Horário:** 19/09/2026, 22:00–22:20  
**Status:** VALIDADO EM TESTE UNITÁRIO — AGUARDANDO REINÍCIO

### Observado

- Mesmo após os Patches 007 e 011, o soak continuava mostrando Marina despejando prosa densa num único balão quando o natural pediria dois (reação + pergunta, interjeição + substância, notícia + comentário).
- A causa persistia mesmo depois de o filtro de conflitos ter sido corrigido e do orçamento de tokens ter sido reduzido para 75–85 no `casual_short`.
- Além disso, o teto artificial de `max_bubbles = 2` (herdado de decisões de IAs anteriores) contradiz a diretiva de que quem decide o ritmo deve ser a "própria" Marina — não uma constante hardcoded no código.

### Classificação e Causa Raiz

- **Delegação frágil ao LLM:** o `apply_policy` embutia uma diretiva `\n entre balões` no meio de 14 outras regras. O `segment()` só quebrava se a Marina lembrasse de emitir `\n`. DeepSeek e similares, treinados majoritariamente em prosa contínua, ignoravam a instrução silenciosamente, especialmente com histórico recente reforçando o padrão de bloco único.
- **`target_bubbles` sempre em 1 nos modos cotidianos** (`casual_short`, `normal`, `supportive`): o fallback semântico do `segment()` só disparava por castigo (texto > `soft_char_limit`), nunca por ritmo natural. Uma reação de 150 chars com uma pergunta no fim nunca virava dois balões.
- **Teto de 2 balões (`max_bubbles = 2`)** truncava agressivamente qualquer intenção de burst genuíno em modos `excited` ou `storytelling`, contradizendo a autonomia expressiva da persona.
- **Split semântico ingênuo:** o algoritmo antigo usava `mid = len(sentences) // 2`, dividindo por contagem cega sem considerar pivôs conversacionais reais (reação → pergunta, interjeição → substância, mudança de tópico).

### Correção Aplicada

1. **Remoção do teto de balões (`response_rhythm.py`):**
   - `max_bubbles` deixou de ser um cap obrigatório em `segment()`; permanece como campo advisory (default `0` = irrestrito) para compatibilidade com callers existentes.
   - Introduzido um `_SANITY_CEILING = 6` puramente anti-runaway (para o caso improvável de o LLM gerar uma explosão de balões).
   - Preservado o limite hard de transporte do Telegram (4096 code units UTF-16 por mensagem).

2. **Segmentação semântica determinística por pivôs naturais:**
   - `_semantic_split` avalia o draft e detecta, em ordem de precedência:
     - Interjeição de abertura ("kkkk", "nossa", "sério?", "caraca"…) → bolha própria; se houver pergunta de fechamento depois, promove a 3 balões.
     - Statement seguido de pergunta de fechamento → 2 balões.
     - Ponto de interrogação no meio da resposta → split ali.
     - Modo `excited` ou `storytelling` com 2+ frases → cadência de burst mesmo sem pivô forte; `storytelling` com 3+ beats vira 3 balões sequenciais.
     - Pivô conjuntivo no início da próxima frase ("mas", "aí", "e você", "agora", "aliás"…) → split.
     - Overflow de comprimento (>1× soft) → 2 balões; (>2× soft com 4+ frases) → 3 balões.
     - Nenhum pivô + comprimento confortável → 1 balão coerente.
   - `_coalesce_paragraphs` funde single-word fragments em vizinhos para evitar "confetti", **exceto** quando o primeiro parágrafo é uma interjeição intencional (preserva "kkkk\nnossa amor…" como 2 balões).

3. **Prompt do `[RESPONSE RHYTHM]` reescrito:**
   - Removidas as 14 regras conflitantes que competiam por atenção.
   - Nova diretiva única e curta focada em **onde** quebrar (pivôs naturais), sem mencionar contagem de balões (respeita a autonomia da Marina).
   - Filtro de conflitos ampliado para varrer também "máximo de 2 balões" / "maximum of 2 bubbles" caso apareçam em prompts herdados.

4. **Novo campo `cadence` na `ResponseStylePolicy`** (`brief`/`flowing`/`burst`/`expansive`) como hint informacional de energia por modo, sem valor de teto.

5. **Log com motivo do split:** cada segmentação agora emite `reason=` no log (`interjection_lead`, `interjection_then_question`, `question_pivot_tail`, `question_pivot_mid`, `excited_burst`, `storytelling_beats`, `conjunctive_pivot`, `length_balance`, `length_balance_3`, `coherent_single`, `llm_newlines`, `llm_newlines_coalesced`, `too_short`, `single_sentence`), permitindo calibração baseada em evidência durante o soak em vez de tuning por achismo.

### Validação

- **Testes unitários:** 25/25 asserts do `tests/test_response_rhythm.py` executados isoladamente, todos aprovados. Incluem regressão de:
  - modos e voz independentes de intimacy;
  - preservação de conteúdo em long text (30 frases → 2 balões balanceados);
  - `'amor\nkkkk'` permanece como um único balão renderizado (vocativo não é interjeição);
  - excited 4-linhas com "Sério" solto → coalescido em 3 balões sem singletons;
  - excited 2-sentenças plain text → 2 balões via burst;
  - `'😀'*5000` respeita o limite de transporte UTF-16 e preserva conteúdo;
  - budget de tokens `casual_short` ≤ 128;
  - `apply_policy` mantém `Identidade canônica.`, remove `múltiplos balões`, preserva a diretriz "no invented dialogue" e "usually finish without a question", conta 1 header `[RESPONSE RHYTHM]` mesmo após re-aplicação.

- **Simulação de 15 turnos reais** representando padrões do soak — todos com decisão de balão coerente:
  - `"foi bom mas cansativo, tive prova de cálculo e depois academia. e o seu?"` → 2 balões (`question_pivot_tail`).
  - `"meu deus não acredito!! parabéns amor, você merece demais isso!"` (excited) → 2 balões (`excited_burst`).
  - `"o Milo pegou uma meia. correu até o sofá. e devolveu quando ofereci o brinquedinho dele."` (storytelling) → 3 balões (`storytelling_beats`).
  - `"nossa amor que jogo foi esse. vitória suada mas a gente ganhou! como foi aí no estádio?"` → 2 balões (`question_pivot_tail`).
  - `"boa noite meu amor, dorme com Deus. amanhã a gente se fala, te amo"` → 1 balão (`coherent_single`).
  - `"kkkk\nvocê é bobo\nsério\ntô rindo aqui\nque coisa mais engraçada de imaginar"` (5 linhas do LLM) → 4 balões (`llm_newlines`, "sério" coalescido com vizinho, interjeição de abertura preservada).

- **Compatibilidade retroativa:** todos os campos existentes da dataclass foram preservados (`target_bubbles`, `max_bubbles`, `soft_char_limit`, etc.), então nenhum caller precisou ser tocado. `bot.py:send_human_messages` e `bot.py:generate_dynamic_speech` continuam funcionando sem alteração.

- **Próximo passo operacional:** reiniciar via `run_local.bat` e observar `response_policy.segmented reason=…` nos logs durante o soak para calibrar heurísticas em cima de evidência real (não achismo).

### Arquivos alterados

- `response_rhythm.py` (reescrito integralmente; ~330 linhas, mesma API pública).

## Patch 013 — Data migration: opening_hours do Bodytech São Clemente

**Horário:** 19/09/2026 (sessão `cse_01RhmTyBLksLR4FZgubG3isb`); aplicação: 20/09/2026, 01:05
**Status:** APLICADO (idempotente)

### Observado

- WorldState sorteava `local=Bodytech São Clemente` mesmo em horários em que a academia está fechada (madrugada, domingo à tarde), o que produzia respostas do tipo "tô na academia" às 03h30.

### Correção

- Script `apply_patch_013.py` grava horário oficial em `usage_rules_json` do lugar canônico Bodytech São Clemente: `mon-fri 06:00-22:00, sat 08:00-18:00, sun 09:00-14:00`. RoutineEngine passa a filtrar sorteios fora da janela.
- Idempotente: reexecuções detectam o estado atual e não sobrescrevem.

### Validação

- Execução dentro do ambiente do soak retornou "OK" sem exceção; conferido via consulta ao SQLite de que `usage_rules_json` contém as chaves esperadas.

### Arquivos

- `apply_patch_013.py` (executado; permanece no repositório para reexecução idempotente).

## Patch 014 — Voice Library (v3.7.1) e Correção do Sistema de Reações

**Horário:** 19/09/2026, 22:45 → 20/09/2026, 01:00
**Status:** VALIDADO EM TESTE UNITÁRIO — AGUARDANDO SOAK REAL

### Observado

- Depois de 3.7.0 (Living Intelligence) a Marina continuava soando "DeepSeek com verniz de amor" em vez de namorada carioca: reagia com empolgação vazia, não puxava detalhes concretos ("qual jogo?", "que horas?", "contra quem?"), abria com "Ah,", fechava com "e você, como tá?" e usava frases de call-center — apesar do CONTROL_PT proibir tudo isso explicitamente.
- A Marina simplesmente **parou de reagir com emoji** às mensagens do Patrick.
- Quando **o Patrick reagia** com ❤️/🔥/😂 numa mensagem dela, ela respondia com uma frase tosca a cada 2 reações ("Ai amor, vi seu coraçãozinho aqui... me derrete toda 🥰💕"). Humanos absorvem reações em silêncio; o comportamento parecia bot.

### Classificação e Causa Raiz

- **CONTROL_PT era 90% negativo.** Um único parágrafo de ~400 palavras com ~20 imperativos "nunca / não / evite" e apenas 5 adjetivos vagos como voz positiva ("afetuosa, bem-humorada, independente, parceira, descomplicada"). LLM alinhado como assistente (DeepSeek-Chat) não descola do padrão base por lista de proibições — precisa ver exemplos concretos de como Marina fala.
- **Zero few-shots em qualquer camada do prompt** (prompt_policy, world_context, response_rhythm, planner). O modelo tinha que inferir "carioca de 20 anos" a partir de adjetivos abstratos, misturados a ~20 blocos técnicos de estado.
- **Adjetivos contraditórios no CONTROL:** "afetuosa" vs. "evite melodrama"; "expressiva" vs. "não use 'sou intensa'". Modelo joga a média — que é "assistente cortês".
- **Sampling agressivo:** `frequency_penalty=0.30 / presence_penalty=0.25` penalizavam justamente as repetições humanas ("amor", "kkk", "ai") que caracterizam a Marina.
- **Reações Marina→Patrick paradas:** `planner_emoji` recebia string literal `"null"` quando o LLM planner devolvia esse valor no JSON. Truthy no Python; passava adiante e falhava mudo em `set_safe_message_reaction` (sem log de skip). Além disso, `_invalid_reactions` era um `set()` permanente — qualquer rejeição pontual do Telegram banha o emoji para sempre.
- **Reações Patrick→Marina toscas:** `handle_reaction` disparava resposta verbal em 45 % / 60 % / 40 % dos casos (coração / fogo / risada), sem cooldown, com fallbacks constrangedores ("Sabia que você ia rir disso kkkk te amo amor!").

### Correção Aplicada

1. **Novo módulo `voice_library.py`** — few-shots roteados por `tone × intent` com dois pools:
   - **Catálogo canônico** (11 pares escritos à mão baseados no CONTROL e no Registro 001 da biblioteca comportamental): cobre `carinhosa`, `brincalhona`, `dengosa`, `acolhedora`, `tranquila` e intents `casual_chat`, `flirting`, `support_needed`, `planning_future`, `sharing_day`, `question`.
   - **Parser da `BIBLIOTECA_COMPORTAMENTAL_MARINA.md`**: extrai os "Exemplos naturais" escritos pelo Patrick como padrão desejado. **Semântica combinada com Patrick em 2026-09-20**: os exemplos são sempre o padrão desejado independentemente da Avaliação (que só reflete o comportamento observado). Registros aceitos: qualquer um com `Exemplos naturais` não-placeholder e `Patrick disse` real. Descartados: Registro 000 (gabarito) e registros só com placeholders.
   - Ranking privilegia (tone-match, intent-match), com biblioteca antes de canônico dentro de cada bucket.
   - Bloco serializado como `[EXEMPLOS DE VOZ — inspiração, não são turnos reais desta conversa]` com delimitadores `---` entre pares.
   - Fail-open em todo o pipeline: arquivo inexistente, encoding torto ou registro mal-formatado não derrubam turno.
   - Contra a `BIBLIOTECA_COMPORTAMENTAL_MARINA.md` populada (registros 1-15 revisados manualmente pelo Patrick, 16-50 vindos de outra IA), o parser produz **97 few-shots** roteáveis.

2. **`prompt_policy.py` refatorado em três subblocos** compostos:
   - `MARINA_VOICE_PT/EN` (persona positiva, ≤150 palavras): como ela fala, curiosidade concreta, callbacks, cores do Botafogo.
   - `HARD_LINES_PT/EN` (5 proibições absolutas): não IA/call center, não "Ah,", não "e você?", não textão, não melodrama.
   - `CANON_FACTS_PT/EN` (fatos duros): canon, horário, não inventar, continuity repair.
   - `CONTROL_EN` / `CONTROL_PT` reconstituídos por composição preservando os headers `[CONTROL RULES]` / `[REGRAS DE CONTROLE]` que os testes verificam.

3. **Wiring do bloco de voz em `world_context.py`** — injetado como última posição-âncora antes do histórico, gated por `settings.VOICE_LIBRARY_ENABLED` (default `True`). Roteado por `planner_tone` + `planner_intent`, ambos propagados de `bot.py` → `context_builder.py` → `WorldContextBuilder`.

4. **Sampling calibrado em `bot.py`** (chamada primária ao LLM):
   - `temperature`: 0.80 → **0.85**
   - `frequency_penalty`: 0.30 → **0.10**
   - `presence_penalty`: 0.25 → **0.05**
   - Fallback Mistral-Nemo preserva valores atuais (0.72 / 0.40 / 0.35).

5. **Correções do sistema de reações** (`bot.py`):
   - `_normalize_planner_emoji`: rejeita `"null"`, `"none"`, `""`, tipos não-string e emojis fora dos 5 safe. Retorna `None` explícito.
   - `_invalid_reactions`: virou `dict[(chat, emoji) → expiry_ts]` com TTL de 24 h. Rejeição transiente não bana emoji permanentemente.
   - `set_safe_message_reaction` agora loga o motivo do skip (`not_safe`, `recently_invalid`, `chat_disallowed`) — visibilidade para calibração.
   - `handle_reaction` reescrito. Probabilidades: **10 % coração / 15 % fogo / 5 % risada** (era 45 / 60 / 40). Cooldown de **15 min** entre respostas verbais por chat. Prompts do `generate_dynamic_speech` proíbem os clichês antigos ("ai amor", "me derrete toda", "gostou do que viu"). Fallbacks curtos e naturais: `"vi seu coração aí 🥺"`, `"kkkk safado"`, `"kkkk né amor"`.
   - Novas settings em `config.py`: `REACT_TO_HEART_REACTION_CHANCE`, `REACT_TO_FIRE_REACTION_CHANCE`, `REACT_TO_LAUGH_REACTION_CHANCE`, `REACTION_VERBAL_REPLY_COOLDOWN_MINUTES`.

6. **Rollback gated:** `VOICE_LIBRARY_ENABLED=false` no `.env` restaura comportamento anterior de voz sem tocar em código. Cada probabilidade de reação também é configurável.

### Validação

- **`tests/test_voice_library.py`** (novo) — 15 asserts: cobertura de tones/intents, ranking com aliases, parser aceitando registros com Avaliação em branco/ruim (exemplos válidos), fail-open em arquivo ausente/malformado, orçamento do bloco ≤ 2000 chars, `VoiceExample` imutável.
- **Regressão prompt-adjacent**: `test_prompt_authority_v370` (19), `test_response_rhythm` (25), `test_world_context` (7), `test_voice_library` (15), `test_context_builder`, `test_wiring_auditoria` — todos verdes.
- **Suíte inteira**: 424/426 passando. As 2 falhas restantes (`test_offer_acceptance_does_not_leave_second_direct_reminder_pending`, `test_incoming_flow_routes_registered_subjects_before_llm`) são **pré-existentes** ao Patch 013 — reproduzidas via `git stash` antes das mudanças, envolvem fluxo de reminder + privacy + `process_incoming_batch`.
- **3 falhas triviais consertadas alinhando testes ao refactor do Patch 012**: `test_world_context::test_flag_on_uses_canon_dynamic_age...` (header `[SEU ESTADO ATUAL` em vez do inexistente `[WORLD STATE — agora]`; teto de tamanho subido para 10 k), `test_world_hygiene_v367::test_optimize_for_next_turn...` (removidas 2 strings do RESPONSE RHYTHM antigo), `test_response_availability_v370::test_brief_hint_caps_bubbles` (`target_bubbles==1` em vez de `max_bubbles==1`, que agora é advisory-only).
- **Smoke test do parser contra `BIBLIOTECA_COMPORTAMENTAL_MARINA.md` populada**: 50 registros lidos, 97 exemplos extraídos, 0 exceções. Registro 001 (jogo do glorioso) já produz os few-shots que o Patrick escreveu manualmente ("Aaaahhh! é que horas?", "amor, eu já até comecei o aquecimento emocional pro jogo!").

### Próximo passo operacional

- **Soak de 2-3 dias** com Fase A completa; após isso, avaliar se a mudança de voz é perceptível antes de partir para a Fase B (comando `/eco boa`/`/eco ruim` para fechar o loop de feedback sem edição manual do `.md`).
- Monitorar logs `voice_library.injected examples=... tone=... intent=... sources=...` e `reaction.skip reason=...` durante o soak para diagnóstico.

### Arquivos alterados/criados

- `voice_library.py` (novo — ~240 linhas).
- `tests/test_voice_library.py` (novo — 15 tests).
- `PLANO_VOZ_MARINA_V371.md` (novo — plano documentado das fases A/B/C).
- `prompt_policy.py` (refatorado em subblocos; API pública preservada).
- `world_context.py` (wiring do voice block; novo parâmetro `planner_intent`).
- `context_builder.py` (propagação de `planner_intent`).
- `bot.py` (sampling calibrado, `_normalize_planner_emoji`, TTL em `_invalid_reactions`, `handle_reaction` reescrito, cooldown de reação verbal, propagação de `planner_intent`).
- `config.py` (`VOICE_LIBRARY_ENABLED`, `VOICE_LIBRARY_MAX_EXAMPLES`, 4 settings de reação).
- `tests/test_world_context.py`, `tests/test_world_hygiene_v367.py`, `tests/test_response_availability_v370.py` (alinhamento ao refactor do Patch 012).

## Patch 015 — Fallback invertido do sono: SLEEPING preservado em stale

**Horário:** 20/09/2026, 10:15–10:45
**Status:** VALIDADO EM TESTE UNITÁRIO — AGUARDANDO REINÍCIO

### Observado

- Patrick escreveu à 01:06 do domingo 20/09; availability retornou `DEFER reason=sleeping activity=SLEEPING` (correto).
- Às 01:27 do mesmo dia (21 min depois, ainda na janela de sono `light_day_sleep` até 08:30), availability retornou `REPLY_NOW reason=unknown_available activity=UNKNOWN`.
- Marina respondeu "Hahaha, já tá com saudade? Mas calma, amor, que logo a gente se encontra de novo." às 01:28, quebrando a proteção de sono e o realismo humano.
- Confirmado via `scripts/export_conversation_history.py`: o último snapshot fresco de world_state foi 00:08:31 (dizendo `dormindo`); às 01:27 esse snapshot já tinha 79 min → considerado stale (`WORLD_STATE_DEFAULT_STALE_MINUTES=60`).

### Classificação e Causa Raiz

- Fallback invertido em `response_availability.py::_resolve_activity` (linha 248, pré-Patch): quando o snapshot mais recente era stale, o método retornava `('UNKNOWN', 'UNKNOWN', ..., 'stale', False)` sem verificar o *conteúdo* do snapshot stale.
- A cadeia downstream (`sleep_protected = activity_type == 'SLEEPING'` na linha 168) nunca ativava porque o activity_type já tinha sido reduzido a UNKNOWN.
- Consequência: qualquer intervalo stale > 60 min DENTRO da janela de sono conhecida da rotina liberava respostas como se Marina estivesse "provavelmente acordada". Um snapshot antigo dizendo "dormindo" era descartado silenciosamente.
- Design correto: sono é *determinístico o suficiente* para que um snapshot stale dizendo dormindo, ainda dentro da janela `routine_patterns.window_end`, seja preservado como SLEEPING.

### Correção Aplicada

Em `response_availability.py::_resolve_activity`, antes do fallback UNKNOWN:

1. Se o snapshot stale mapeia para `SLEEPING` (via `_map_place_activity`);
2. E `_routine_sleep_until(snapshot_id, now)` retorna um horário futuro (ainda dentro da janela de sono);
3. Então retornar `('SLEEPING', 'ROUTINE_PROBABILITY', snapshot_id, 'fresh', False)`.

Fora dessas condições (snapshot stale de qualquer outra atividade OU snapshot SLEEPING mas fora da janela de sono), o fallback UNKNOWN original permanece — comportamento preservado para atividades não-determinísticas.

### Validação

- Teste novo `test_patch_015_stale_sleeping_snapshot_still_protects_sleep`: reproduz literalmente o cenário 20/09 01:27 (snapshot 79 min stale dizendo dormindo, `now` dentro do `light_day_sleep`) e verifica `activity_type=SLEEPING`, `decision=DEFER`, `selected_target_at >= 08:30`.
- Teste-guarda `test_patch_015_stale_non_sleeping_still_falls_back_to_unknown`: snapshot stale de "tempo livre em casa" continua caindo para UNKNOWN (comportamento preservado, sem falsos positivos de sono).
- Suíte completa de availability: 20/20 aprovada.
- Regressão prompt-adjacente: `test_prompt_authority_v370` + `test_response_rhythm` + `test_world_context` + `test_voice_library` → 69/69 verdes.

### Próximo passo operacional

- Reiniciar `run_local.bat` para o Patch 015 subir em runtime.
- Nova ferramenta `scripts/export_conversation_history.py` + wrapper `export_history.bat`: exporta conversa + últimas resoluções de WorldState + últimos 20 eventos de Response Availability para `scratchpad/conversation_export_<timestamp>.txt`. Patrick pode rodar e me passar quando precisar triagem sem depender de print.

### Arquivos alterados/criados

- `response_availability.py` (linhas 244-263; `_resolve_activity` estende cheque stale com preservação de SLEEPING).
- `tests/test_response_availability_v370.py` (2 novos testes de contrato).
- `scripts/export_conversation_history.py` (novo — export CLI).
- `export_history.bat` (novo — wrapper Windows).

## Patch 016 — Incidente: modelo `neversleep/llama-3.1-lumimaid-8b` inexistente no OpenRouter

**Horário:** 20/09/2026, 10:45–11:00
**Status:** DIAGNOSTICADO — instruções de substituição entregues ao Patrick

### Observado

- Patrick alterou `LLM_MODEL=neversleep/llama-3.1-lumimaid-8b` no `.env` após discussão sobre trocar o modelo primário.
- Toda chamada da LLM principal retornou HTTP 404: `{"error": {"message": "No endpoints found for neversleep/llama-3.1-lumimaid-8b."}}`.
- Cascata: `InternalPlanner` também caiu em plano de contingência (mesmo modelo), `MemoryConsolidator` falhou repetidamente, respostas caíram no fallback `mistralai/mistral-nemo` sem planner cognitivo.
- Sintomas observados: voz ainda robótica (Mistral-Nemo puro), consolidação de memória parada (`cursor NÃO avançado`), `tone=- intent=-` nos logs de `voice_library.injected` (planner heurístico sem enum de tone).

### Classificação e Causa Raiz

- Recomendação da assistente feita sem verificação de disponibilidade contra o catálogo real do OpenRouter. `neversleep/llama-3.1-lumimaid-8b` existe no Hugging Face mas **não** é servido pelo OpenRouter atualmente. A `Lumimaid-70B` foi retirada da lista.
- Cadeia de fallback do bot suportou a falha graciosamente (Mistral-Nemo pegou), mas o planner cognitivo ficou sem LLM real, degradando a experiência conversacional.

### Correção Aplicada

- Verificação direta contra `https://openrouter.ai/api/v1/models` para confirmar quais modelos companion/roleplay estão vivos hoje.
- Lista de 7 candidatos válidos entregue ao Patrick, com preço real ($/M tokens) e classificação de moderação:

| Modelo | Input $/M | Output $/M | Contexto | Moderação |
| --- | --- | --- | --- | --- |
| `sao10k/l3-lunaris-8b` | 0.04 | 0.05 | 8k | unmoderated |
| `gryphe/mythomax-l2-13b` | 0.08 | 0.11 | 8k | unmoderated |
| `thedrummer/cydonia-24b-v4.1` | 0.30 | 0.50 | 131k | unmoderated |
| `thedrummer/skyfall-36b-v2` | 0.55 | 0.80 | 32k | unmoderated |
| `sao10k/l3.3-euryale-70b` | 0.65 | 0.75 | 131k | unmoderated |
| `nousresearch/hermes-3-llama-3.1-70b` | 0.70 | 0.70 | 131k | unmoderated |
| `anthracite-org/magnum-v4-72b` | 2.50 | 5.00 | 32k | unmoderated |

- Patrick trocou para `sao10k/l3-lunaris-8b` — Llama-3 8B roleplay-tune, uncensored, $0.04/$0.05 por M.
- Próximos passos sugeridos: se persona pegar no Lunaris, subir para Euryale-70B (mais solto) ou Hermes-3-70B (mais aderente a system prompt) para qualidade.

### Validação

- 404 verificado em `logs/marina.log` (dezenas de warnings `Error code: 404` do `InternalPlanner` e `MarinaBot`).
- Cascata de fallback confirmada: `Aviso na chamada principal da LLM (neversleep/llama-3.1-lumimaid-8b)` seguido de `Acionando modelo reserva (mistralai/mistral-nemo)` no código de recovery.

### Arquivos alterados

- Nenhum código de produção alterado; apenas `.env` do Patrick (fora do repositório).
- Documentação: este patch e a tabela de modelos vivos.

## Patch 017 — Fase B.5: Proatividade sensível ao WorldState da Marina

**Horário:** 20/09/2026, 11:00–11:30
**Status:** VALIDADO EM TESTE UNITÁRIO — AGUARDANDO REINÍCIO

### Observado

- Patrick pediu no fechamento de sessão de 19-20/09: "quando ela mesma está de bobeira, ela deveria te procurar mais; quando ocupada, menos".
- Hoje `ProactivityService.should_trigger` usa `AUTONOMOUS_TRIGGER_CHANCE=0.30` fixo, sem olhar para o `WorldState` da própria Marina. Livre em casa ou em aula, mesma chance.

### Classificação e Causa Raiz

- Arquitetura pré-Fase-B.5 tratava a decisão de iniciativa como função só do tempo desde a última troca (`USER_IDLE_MINUTES_BEFORE_PROACTIVE`) e do cooldown autônomo (`AUTONOMOUS_COOLDOWN_MINUTES`), sem input do estado atual dela.
- Sem modulação por atividade, ela poderia interromper a si mesma na academia ou ignorar horas de tempo livre no apartamento — comportamento não-humano.

### Correção Aplicada

1. Novo método `ProactivityService._compute_state_factor(now) -> (float, str)`:
   - Consulta `WorldStateRepository.latest()` e verifica frescor (≤ 90 min); stale/absent devolve `PROACTIVITY_STATE_FACTOR_UNKNOWN=1.0` (comportamento anterior preservado).
   - `activity` contendo `dorm/sleep/sono` → fator `0.0` (defense-in-depth; `sleep_window` já bloqueia antes).
   - Atividades ocupadas (`aula/class/faculdade/academia/gym/treinando/trabalh/working/casting/reuniao`) → fator `PROACTIVITY_STATE_FACTOR_BUSY=0.4`.
   - `reason=post_event_recovery` → fator `PROACTIVITY_STATE_FACTOR_POST_EVENT=1.3`.
   - `reason=free_time` ou activity com `livre/descans/relax/em casa` → fator `PROACTIVITY_STATE_FACTOR_FREE_TIME=1.6`.
   - Devolve tupla `(factor, label)` para log.

2. `should_trigger` aplica o fator sobre a chance estocástica em duas rotas:
   - Living World (linha ~172): `probability = base_relationship_prob * state_factor`.
   - Fallback estocástico (linha ~187): `probability = AUTONOMOUS_TRIGGER_CHANCE * state_factor`.
   - Log `proactivity.state_factor state=<label> factor=<X.XX> base=<Y.YYY> prob=<Z.ZZZ> route=<...>` para calibração.

3. `cooldown` e `MAX_AUTONOMOUS_MESSAGES_PER_DAY` preservados intactos — o fator apenas *redistribui* as ocasiões dentro dos limites já configurados.

4. Novas settings no `config.py` (defaults conservadores, ajustáveis via `.env`):
   - `PROACTIVITY_STATE_FACTOR_FREE_TIME=1.6`
   - `PROACTIVITY_STATE_FACTOR_POST_EVENT=1.3`
   - `PROACTIVITY_STATE_FACTOR_BUSY=0.4`
   - `PROACTIVITY_STATE_FACTOR_UNKNOWN=1.0`

### Validação

- 7 testes novos em `tests/test_proactivity_service.py::TestProactivityStateFactor`: cobertura de free_time, busy (activity + confirmed), aula, post_event_recovery, sleeping (zero-out), WorldState ausente, WorldState stale (fallback para 1.0).
- Suíte proactivity: 13/13 aprovada.
- Regressão prompt/availability/voice: 66/66 aprovada.

### Próximo passo operacional

- Reiniciar `run_local.bat` após confirmar substituição do modelo (Patch 016).
- Durante o soak, procurar linhas `proactivity.state_factor` no log para calibrar defaults se necessário.
- Aberto na fila: Fase B.6 (micro-despertares durante o sono) — próximo item planejado.

### Arquivos alterados/criados

- `proactivity_service.py` (`_compute_state_factor` novo; `should_trigger` estende as duas rotas estocásticas com o fator).
- `config.py` (4 settings novas).
- `tests/test_proactivity_service.py` (nova classe `TestProactivityStateFactor` com 7 testes).

## Patch 018 — Isolamento de DB nos testes, coluna `model` em `conversas`, export por sessão + regra dura de idioma

**Horário:** 20/09/2026, 11:35–12:00
**Status:** VALIDADO EM TESTE UNITÁRIO — AGUARDANDO REINÍCIO

### Observado

Três achados relacionados no mesmo bloco de trabalho:

1. **Fixtures de teste vazando no banco de produção.** Investigação das 4 "Boa noite meu amor!" idênticas do soak de 19-20/09 revelou que **6 pares** de `Boa noite vida` / `Boa noite meu amor!` estavam persistidos em `conversas` com timestamps ~15 ms de diff entre pergunta e resposta — impossível para chamadas de LLM real. Origem confirmada: `tests/test_context_builder.py::test_context_builder_preserves_recent_history_under_knowledge_privacy` usava o singleton `memory_manager` global (banco de produção) para inserir fixtures via `db.adicionar_mensagem(...)`, sem tempfile isolado. Cada execução da suíte fora do CI durante o soak dobrou a poluição.

2. **Sem rastreabilidade de qual modelo produziu cada resposta.** No teste de trocar entre DeepSeek → Lumimaid (404) → Cydonia → Euryale → Nemo → Unslopnemo, ficou impossível auditar retroativamente qual turno saiu de qual modelo. Toda análise de voz dependia de correlacionar timestamps com a hora que o Patrick trocou o `.env`.

3. **Export dumpava sempre 48h**, misturando várias trocas de modelo, várias sessões distintas e pouca separação visual.

Adicionalmente, análise dos testes com **Cydonia-24B**, **Euryale-70B** e **Lunaris-8B** mostrou padrão comum de degradação:
- Lunaris-8B: "cuterinho" (palavra inexistente), "Carta Vermelha" (referência inventada), "Estou sempre na pra aumentar a Chance" (frase truncada).
- Cydonia-24B / Euryale-70B: "Oito um pouco" (alucinação de token), spam de emoji no fim das mensagens.
- Padrão comum: **mistura de línguas / palavras em inglês** em contextos onde a Marina deveria estar em pt-BR puro.

### Classificação e Causa Raiz

- **Design ruim do teste (achado 1):** o singleton `memory_manager` importado no topo dos testes aponta para `marin_memory.db`. Sem `setUp`/`tearDown` que aponte para tempfile, qualquer `db.adicionar_*` altera o banco real. O sqlite não separa "test" de "prod" por si só.
- **Falta de coluna `model` em `conversas` (achado 2):** o schema original não previa multi-modelo, então nunca se persistiu qual LLM gerou cada texto.
- **Script sem noção de sessão (achado 3):** dumpar linear todo o histórico funciona para diagnóstico único mas não para triagem iterativa.
- **Regra de idioma dispersa (achado extra):** o `MARINA_VOICE_PT/EN` do Patch 014 tinha só uma linha final "Responda como Marina em português brasileiro natural". Modelos que oscilam entre línguas (Nemo, Lunaris, Euryale, Cydonia) precisam de regra dura no topo com exemplos concretos.

### Correção Aplicada

1. **Isolamento de DB em `tests/test_context_builder.py`:**
   - Novo `setUp` cria `TemporaryDirectory` + `DatabaseManager` isolado, substitui `memory_manager.db` e `memory_retriever.db` temporariamente, seed World Bible + academic.
   - `tearDown` restaura os singletons e limpa o tempfile.
   - Todos os 6 testes da suíte agora rodam contra tempfile — zero vazamento para o banco de produção.

2. **Migration `018_conversation_model.sql`:**
   - Adiciona coluna `model TEXT` em `conversas` (NULL para linhas anteriores; auto-populada em novas respostas).
   - Índice `idx_conversas_model` para filtros por modelo.

3. **`db.adicionar_mensagem` estendido:**
   - Novo parâmetro `model: Optional[str] = None`.
   - Só grava `model` quando `role == 'assistant'` (defense-in-depth contra populamento incorreto em mensagens do usuário).

4. **`memory.registrar_mensagem_assistente` puxa `settings.LLM_MODEL` como default:**
   - Callers antigos continuam funcionando; automaticamente registram o modelo primário sem alteração.
   - Callers modernos (`bot.py:1930` e `bot.py:2481`) explicitamente passam `settings.LLM_MODEL` para as duas rotas que ainda usam `adicionar_mensagem` direto.

5. **Script `export_conversation_history.py` reescrito:**
   - Novo default: exporta **apenas a sessão mais recente** (menos ruído para triagem iterativa).
   - `--all-sessions` para o histórico completo, `--hours N` / `--last N` para os modos antigos.
   - `--session-gap-minutes N` (default 45) define o corte entre sessões.
   - Header do export lista **modelos LLM usados por sessão** com contagem de mensagens por modelo.
   - Cada balão da Marina imprime `[model: <id>]` inline.

6. **Regra de idioma dura em `prompt_policy.py`:**
   - Novo bloco `LANGUAGE RULE — ABSOLUTE:` / `REGRA DE IDIOMA — ABSOLUTA:` no topo do `MARINA_VOICE_PT/EN`.
   - Lista palavras em inglês que a Marina costuma soltar por estética ("crush", "vibe", "cute") e a equivalente em pt-BR ("paixãozinha", "clima", "fofo/a").
   - Exceção explícita para nomes próprios (Konosuba, Botafogo, iFood).
   - Objetivo: reduzir mistura de línguas em modelos Nemo/Llama-3 tuned que oscilam.

7. **Script `cleanup_test_poluted_conversations.py`:**
   - Deleta as 12 linhas de fixture (`ids 38-84`) mediante `--apply`.
   - Backup automático em `backups/pre_patch018_cleanup_<timestamp>.db`.
   - Idempotente e dry-run por default.

### Validação

- **Suíte `test_context_builder`:** 6/6 aprovada com isolamento tempfile. Verificação manual: consultar `marin_memory.db` após rodar a suíte no ambiente do Patrick não deve mais mostrar fixtures inseridas.
- **Regressão prompt/availability/proactivity/voice:** 72/72 aprovada.
- **Migration:** aplicada localmente no banco de teste sem erros.
- **Script novo:** smoke test com sessão atual (6 msgs, 1 sessão) — imprime resumo de modelos e ligação inline.
- **Regra de idioma:** ativa em ambos `MARINA_VOICE_PT` e `MARINA_VOICE_EN`; testes existentes de prompt authority passam sem regressão.

### Próximo passo operacional

- Reiniciar `run_local.bat` para migration 018 subir; novas respostas passam a ser gravadas com `model` populado.
- Rodar `python scripts/cleanup_test_poluted_conversations.py --apply` quando conveniente (idempotente; se banco já foi resetado, no-op).
- Aguardando teste do Patrick com `LLM_MODEL=thedrummer/unslopnemo-12b` para avaliar se a base Nemo com "unslop" tune + regra de idioma dura resolve simultaneamente voz-assistente e mistura de línguas.
- Aberto na fila: Fase B.6 (micro-despertares durante o sono).

### Arquivos alterados/criados

- `migrations/018_conversation_model.sql` (nova).
- `db.py` (`adicionar_mensagem` aceita `model`).
- `memory.py` (`registrar_mensagem_assistente` puxa `settings.LLM_MODEL` como default).
- `bot.py` (duas chamadas `adicionar_mensagem(role='assistant', …)` passam `model=settings.LLM_MODEL`).
- `scripts/export_conversation_history.py` (reescrito: sessões, modelo por resposta, summary por sessão).
- `scripts/cleanup_test_poluted_conversations.py` (novo).
- `tests/test_context_builder.py` (`setUp`/`tearDown` com tempfile DB isolado).
- `prompt_policy.py` (bloco `REGRA DE IDIOMA — ABSOLUTA` em `MARINA_VOICE_PT/EN`).

## Patch 019 — Sampling ajustado + regra de idioma realista

**Horário:** 20/09/2026, 11:30–12:00
**Status:** VALIDADO

- `frequency_penalty` subido de 0.10 → 0.15 para atenuar token-repeat de 12B ("Que bom, que Que bom"). `temperature=0.85` e `presence_penalty=0.05` mantidos.
- Regra de idioma reescrita: **aceita** anglicismos casuais do jovem carioca ("crush", "vibe", "sorry", "chill", "cringe", "hype", "top", "cool", "please"); **bane** só mistura sintática ("legalTogether"), frases em inglês, gramática inglesa em pt-BR e palavras inventadas.

## Patch 020 — Guard emoji-only + guard script não-latino

**Horário:** 20/09/2026, 12:40–22:35
**Status:** VALIDADO

- Detector `_is_essentially_emoji_only(text)`: threshold <2 letras → retry único com system message dura.
- Detector `_has_foreign_script_leak(text)`: 2+ caracteres cirílico/chinês/japonês/coreano/árabe/hebraico/devanagari/tâmil/tailandês → retry.
- Prompt CONTROL ganhou linhas duras: "resposta SEMPRE precisa ter texto real em português" + "use apenas o alfabeto latino".
- Origem: Unslopnemo 12B produziu "❓✅" (12:38) e "Que peninha, perdido o dia todo імпер" (22:28).

## Patch 021 — Prompt inteiro traduzido para pt-BR (auto-sabotagem descoberta)

**Horário:** 20/09/2026, 23:00–23:30
**Status:** VALIDADO EM TESTE UNITÁRIO — SOAK CONFIRMOU MELHORIA VISÍVEL

### Observado

- Patrick levantou a hipótese: "o prompt CONTROL em inglês pode estar atrapalhando".
- Auditoria do prompt real que Marina recebe: **9935 chars, ~55% em inglês**. Os dois maiores blocos (VOZ DA MARINA no topo, RESPONSE RHYTHM no fim — juntos 4044 chars) estavam em EN, junto com FACTS (1414 chars), DATA CHANNEL POLICY (259 chars) e KNOWLEDGE POLICY (197 chars).
- Modelos multilíngues 12B (Nemo, Unslopnemo), quando pisam num prompt majoritariamente EN, "pensam" em EN e traduzem mal — daí vazamento de cirílico/Mathematical Bold, anglicismos forçados, e ativação da persona-assistente base do modelo.

### Classificação e Causa Raiz

- Herança de decisão antiga: `PROMPT_CONTROL_LANGUAGE=en` era default no config.py, exigido pelo `soak_preflight.py`.
- CONTROL_EN e CONTROL_PT existiam paralelamente, mas 3 blocos globais só existiam em EN: `DATA_CHANNEL_POLICY_EN`, `[KNOWLEDGE POLICY]` inline em world_context.py, `[RESPONSE RHYTHM]` inline em response_rhythm.py.
- Sem cobertura PT desses 3 blocos, mesmo trocar `PROMPT_CONTROL_LANGUAGE=pt-BR` deixaria ~2400 chars em EN no prompt.

### Correção Aplicada

1. `prompt_policy.py`: novo `DATA_CHANNEL_POLICY_PT` traduzindo o EN.
2. `world_context.py`: escolha condicional de `DATA_CHANNEL_POLICY_PT`/`_EN` por `control_language`; bloco `[POLÍTICA DE CONHECIMENTO]` PT injetado quando `control_language == 'pt-BR'`.
3. `response_rhythm.py`: `_MODE_RULE` e `apply_policy` inteiramente traduzidos; header vira `[RITMO DE RESPOSTA]`; sanitizer aceita tanto o header antigo quanto o novo para transição.
4. `scripts/soak_preflight.py`: remove exigência de "en"; aceita "en" ou "pt-BR".
5. Linhas duras adicionais em `HARD_LINES_PT/EN`:
   - Bots do Telegram não conseguem chamada de voz/vídeo/Zoom/FaceTime — Marina só pode se comunicar por chat (texto, áudio, foto, reação).
   - Nunca inventar títulos genéricos de filme/série/música/livro/anime ("Filme de Romance"). Se não souber, perguntar ou falar sem nome.
6. Testes atualizados para checar tanto o header EN (com `PROMPT_CONTROL_LANGUAGE="en"` patchado) quanto o PT novo. Teto de tamanho do prompt subido para 11k para absorver expansão das novas regras.

### Métrica antes/depois

| | Antes | Depois |
|---|---|---|
| Tamanho | 9935 chars | ~10460 chars |
| % em EN | ~55% | 0% |
| Coerência de idioma | Mistura EN/PT | 100% pt-BR |

### Validação

- Regressão prompt/world/voice/context/rhythm/proactivity/hygiene: 76/76 verdes.
- Soak imediato pós-Patch 021 (22:53-23:00, mistral-nemo como primário): voz visivelmente mais coerente. Marina reagiu naturalmente ("Haha, beleza então"), tomou iniciativa concreta (sugestão de filme), aceitou redireção do Patrick sem drama. Bugs residuais: ainda usou "Estou vendo" formal em vez de "tô vendo" (resíduo assistente), inventou nome genérico "Filme de Romance" (bug de mídia), sugeriu Zoom (bug de canal — bots não podem chamada).
- Bugs residuais atacados pelo mesmo Patch via novas linhas duras (chamadas + títulos).

### Próximo passo operacional

- Patrick: `PROMPT_CONTROL_LANGUAGE=pt-BR` no `.env` (feito).
- Continuar soak com `mistralai/mistral-nemo` como primário (surpreendeu positivamente pós-tradução; $0.019/M input vs $0.40 do Unslopnemo).
- Fase B.6 (micro-despertares) e retriever antecipado de mídia (Patch 023 em potencial) ficam na fila.

### Arquivos alterados

- `prompt_policy.py` (DATA_CHANNEL_POLICY_PT novo; linhas duras: alfabeto latino, sem chamada, sem título genérico).
- `world_context.py` (wiring PT dos blocos DATA_CHANNEL e KNOWLEDGE POLICY).
- `response_rhythm.py` (_MODE_RULE + apply_policy inteiros traduzidos; header `[RITMO DE RESPOSTA]`).
- `scripts/soak_preflight.py` (aceita 'en' ou 'pt-BR').
- `tests/test_response_rhythm.py`, `tests/test_world_context.py`, `tests/test_world_hygiene_v367.py` (assertions atualizadas + patches explícitos de `PROMPT_CONTROL_LANGUAGE`).

## Patch 022 — Auditoria do `.env` do Patrick

**Horário:** 21/09/2026, 00:15
**Status:** RECOMENDAÇÕES ENTREGUES (Patrick decide se aplica)

### Achados

1. `AUTONOMOUS_TRIGGER_CHANCE=0.35` — acima do default (0.30). Com o multiplicador da Fase B.5 (×1.6 para `free_time`), fica 0.56 por check de 30 min. Muito agressivo para o soak inicial. **Sugestão:** baixar para 0.20-0.25.
2. `AUTONOMOUS_CHECK_INTERVAL_MINUTES=30` — checks a cada 30 min. Se a intenção é sensação humana (~2-3 iniciativas por dia), 60 min faz mais sentido.
3. `PHOTO_PROVIDER_MAINTENANCE=true` — Marina responde "câmera em manutenção" a pedido de foto. Confirmar se ainda é intencional.
4. Cinco features de aprendizado ativas simultaneamente (`SESSION_REFLECTION_ENABLED`, `MEMORY_HYGIENE_ENABLED`, `WORLD_HYGIENE_ENABLED`, `STORY_SEED_LIBRARY_ENABLED`, `MEMORY_CONSOLIDATION_ENABLED`). Cada uma faz LLM calls periódicas, gasta créditos e pode gerar warnings no log. **Sugestão** para o início do soak: manter só `MEMORY_CONSOLIDATION_ENABLED=true` e ligar os outros depois de 3-4 dias.

### Não é bug, é ajuste

Nenhuma dessas configurações está errada — todas são intencionais em algum momento. Auditoria só sinaliza que, para um soak curto pós-mudanças de arquitetura, elas somam ruído desnecessário.

## Patch 023 — Retriever antecipado de mídia real (fim do "Filme de Romance")

**Horário:** 21/09/2026, 00:20–00:45
**Status:** VALIDADO EM TESTE UNITÁRIO — AGUARDANDO REINÍCIO

### Observado

- Marina 20/09 22:57 disse *"Estou assistindo 'Filme de Romance'"* — placeholder óbvio.
- Sistema de busca web (`buscar_web_se_necessario`) existia mas só reagia à mensagem do Patrick. Nunca alimentava a Marina proativamente com títulos reais que ela pudesse citar espontaneamente.

### Correção Aplicada

1. **Novo `media_lookup_service.py`** — `MediaLookupService.refresh_if_stale(now)` roda 1x por dia via DuckDuckGo em pt-BR ("filmes em cartaz cinema brasil hoje", "séries mais assistidas netflix brasil", "animes populares crunchyroll 2026"), extrai candidatos de título com regex conservador + blocklist, dedupe, guarda top-8 no `real_context_cache` com TTL `MEDIA_LOOKUP_REFRESH_HOURS` (24h).
2. **Migration `019_media_context_cache.sql`** — atualiza CHECK constraint do `real_context_cache` para aceitar `kind='media'` (mesma técnica de swap-tabela usada na migration 013).
3. **Validador em `calendar_world.py::RealContextCache.put`** aceita novo kind e valida payload (`{titles: List[str]}`, cada título 1-80 chars).
4. **Wiring em `world_context.py`** — antes do bloco de memória, chama `MediaLookupService`, refresca se stale, injeta bloco `[MÍDIA REAL EM ALTA — se for citar filme/série/anime hoje, use um destes]` com os 8 títulos.
5. **Settings novas em `config.py`**: `MEDIA_LOOKUP_ENABLED=true` (default), `MEDIA_LOOKUP_REFRESH_HOURS=24`.
6. **Fail-open em todos os pontos**: busca falha, cache vazio, network offline — o turno segue normal, apenas sem enrichment de mídia.

### Como funciona combinado com HARD LINE de "não inventar títulos" (Patch 021)

- Patrick pergunta "que filme você tá vendo?" → Marina lê o bloco `[MÍDIA REAL EM ALTA]` no prompt → cita título real (ex.: "tô vendo Wicked aqui em casa").
- Marina proativamente quer sugerir filme → mesma coisa, escolhe da lista.
- Marina não sabe nem tem na lista → HARD LINE do Patch 021 força ou perguntar ao Patrick ou falar sem nome ("um romance que peguei aqui"). Fim do "Filme de Romance".

### Validação

- 6 testes novos em `tests/test_media_lookup.py`: filtro de título (aceita reais, rejeita blocklist/curto/longo/all-caps), disabled → vazio, cache absent → vazio, cache populado → bloco correto, cache expirado → vazio, refresh fail-open.
- Regressão prompt/world/voice/context/rhythm: 64/64 verdes.

### Próximo passo operacional

- Reiniciar `run_local.bat` (migration 019 sobe sozinha; primeiro turno depois disso dispara refresh de mídia).
- Log a acompanhar: `media_lookup.refreshed n=X ttl_h=24`.

### Arquivos alterados/criados

- `media_lookup_service.py` (novo).
- `migrations/019_media_context_cache.sql` (novo).
- `tests/test_media_lookup.py` (novo — 6 testes).
- `calendar_world.py` (RealContextCache aceita `kind='media'` com validação de payload).
- `config.py` (`MEDIA_LOOKUP_ENABLED`, `MEDIA_LOOKUP_REFRESH_HOURS`).
- `world_context.py` (wiring que injeta bloco `[MÍDIA REAL EM ALTA]` antes do bloco de memória).

## Patch 024 — Comando `/registro` no Telegram + diversidade nos few-shots

**Horário:** 21/09/2026, 00:50–01:10
**Status:** VALIDADO EM TESTE UNITÁRIO — AGUARDANDO REINÍCIO

### Observado

- Alimentar a `BIBLIOTECA_COMPORTAMENTAL_MARINA.md` exigia editar arquivo no computador, quebrando o fluxo do Patrick (que quer registrar cenários enquanto deita).
- Voice library injetava só 4 exemplos por turno; papers de in-context learning sugerem 6-10 pra transferência efetiva de estilo em modelos 12B.
- Ranking sem diversidade: 5 registros de "boa noite" com mesmo tone/intent → todos os 4 slots poderiam sair sobre boa noite.

### Correção Aplicada

1. **Comando `/registro` no bot** (`bot.py::registro_command`):
   - Sem args → mostra template curto em Markdown.
   - Com corpo estruturado → parseia campos (`Título`, `Categoria`, `Patrick`, `Marina`, `Tom`, `Exemplos`, `Evitar`, etc.), calcula próximo `## Registro NNN`, appenda ao `.md` no formato canônico.
   - Aceita campos em qualquer ordem, `Exemplos:` inicia bloco de bullets até o próximo campo.
   - Só `Patrick:` e `Exemplos:` são obrigatórios; outros são opcionais.
   - Auto-limpa mensagens após 8-90s pra não poluir o chat.
2. **Voice library `limit`**: 4 → **6** exemplos por turno (default no `config.py::VOICE_LIBRARY_MAX_EXAMPLES` e em `select_examples`/`build_voice_block`).
3. **Diversidade forçada**: novo parâmetro `max_per_patrick=2` — no máximo 2 exemplos com a mesma fala do Patrick, para evitar bloco monotemático.

### Validação

- Parser do `/registro` testado com bloco realista (título, categoria, contexto, Patrick, tom, 2 exemplos, evitar) — todos os campos extraídos corretamente.
- Regressão prompt/world/voice/media/context: 64+/64+ verdes com ajuste em `limit=0` para não pular o guard `max_per_patrick`.

### Como usar do celular

No Telegram, com o bot ligado:

```
/registro
Título: Ciúme leve
Categoria: intimidade / ciúme
Contexto: eu comento que passei tempo com a Bia
Patrick: terminei de conversar com a Bia, foi bom
Tom: brincalhona
Exemplos:
- haha ok, ainda te amo mais que ela
- kkk pode ir, só me liga depois
Evitar: fingir indiferença, drama
```

Bot confirma com `✅ Registro 051 adicionado: _Ciúme leve_`.

### Arquivos alterados/criados

- `bot.py` (`registro_command`, `_parse_registro_body`, `_append_registro_to_biblioteca`, handler registrado).
- `voice_library.py` (`select_examples` com `limit=6` default + `max_per_patrick=2`; `build_voice_block` com `limit=6`).
- `config.py` (`VOICE_LIBRARY_MAX_EXAMPLES=6`).

## Patch 025 — Wizard interativo do /registro + poda dos 16-50 + Fase C.1 planejada

**Horário:** 21/09/2026, 02:30–03:30
**Status:** VALIDADO EM TESTE UNITÁRIO — AGUARDANDO REINÍCIO

### Observado

- Patrick relatou que o `/registro` de bloco único era pouco amigável no celular; queria wizard interativo que perguntasse cada campo com exemplo.
- Registros 16-50 da biblioteca comportamental foram gerados por outra IA como bootstrap — Patrick avaliou baixa qualidade e autorizou remoção.
- Feedback novo em 21/09 02:22: sistema de "modo sexting" para a Marina (Fase C.1) precisa ser desenhado.

### Correção Aplicada

1. **Wizard interativo** em `bot.py::registro_command`:
   - Estado in-memory por `chat_id` em `REGISTRO_WIZARDS`.
   - 7 etapas: título, categoria, contexto, patrick, tom, exemplos (múltiplos), evitar.
   - Cada etapa mostra exemplo concreto de uma das 6 categorias faltantes (rotativo aleatório): *intimidade/assistir junto*, *planos futuros*, *paulista virando carioca*, *piada interna do casal*, *reação a foto do Patrick*, *conflito e reconciliação*.
   - Comandos durante wizard: `/pular` (opcional), `/cancelar` (aborta), `/pronto` (finaliza exemplos).
   - Interceptação em `process_incoming_batch`: se `chat_id in REGISTRO_WIZARDS`, mensagem alimenta wizard sem passar pela Marina.
   - Auto-limpeza das mensagens do wizard após 3 min pra não poluir o chat.
2. **Script `scripts/prune_biblioteca_ia.py`** — backup automático em `data/feedback/backups/`, remove registros 16-50, renumera 51+ sequencialmente. Idempotente.
3. **Executado**: 35 registros de IA removidos, biblioteca ficou com 39 registros (001-039) — 76 exemplos extraídos vs 141 anteriores. Sinal muito mais concentrado no padrão real do Patrick.
4. **Fase C.1 (Modo Sexting)** catalogada no `PLANO_VOZ_MARINA_V371.md` como pendente: arousal como novo eixo emocional, preferência de canal (áudio > texto quando ativo), integração com ciclo/libido, guardrails, escalada de fotos. 2-3 sessões estimadas.

### Validação

- Sanity import do bot: OK; wizard dict criado, 6 categorias-exemplo carregadas.
- Regressão prompt/world/voice/media: 50/50 verdes.
- Dry-run e apply do prune verificados; backup salvo em `biblioteca_pre_prune_20260921_032356.md`.

### Como usar (Patrick, do celular)

1. `/registro` — bot pergunta cada campo com exemplo da categoria em falta escolhida aleatoriamente.
2. Responde cada pergunta com uma mensagem.
3. Em `Exemplos`, manda vários (um por mensagem) e diz `/pronto` para avançar.
4. Ao final: `✅ Registro 040 salvo` (numeração continua onde a biblioteca parou).
5. `/cancelar` a qualquer momento aborta; `/pular` deixa campo opcional em branco.

### Arquivos alterados/criados

- `bot.py` (`registro_command` reescrito como wizard, `cancelar_command`, `_advance_wizard`, `_wizard_send`, `_wizard_reset`, `REGISTRO_WIZARDS`, `_WIZARD_CATEGORY_EXAMPLES`; interceptação em `process_incoming_batch`; handlers `/cancelar` e `/cancel` registrados).
- `scripts/prune_biblioteca_ia.py` (novo — script idempotente).
- `data/feedback/BIBLIOTECA_COMPORTAMENTAL_MARINA.md` (podado e renumerado).
- `data/feedback/backups/biblioteca_pre_prune_20260921_032356.md` (backup).
- `PLANO_VOZ_MARINA_V371.md` (Fase C.1 modo sexting adicionada como pendente).

---

## Patch 026 — `/registro` dual mode (wizard OU textão pronto)

**Data:** 2026-09-21 03:35
**Origem:** feedback do Patrick logo após reiniciar o `.bat` do Patch 025: ele mandou entrada pronta em formato `Título:/Categoria:/Patrick:/Exemplos:/…` e o comando entrou no wizard mesmo assim, desperdiçando o corpo. Ideal: aceitar os dois modos.

### Sintoma

Depois do restart do bot:
1. Patrick mandou `/registro\nTítulo: ...\nCategoria: ...\n...`
2. O handler ignorava o corpo, iniciava wizard na Etapa 1, e a Etapa 1 gravava o *título inteiro concatenado* como se fosse resposta ao "Título curto".
3. A entrada pronta se perdia.

### Causa raiz

O `registro_command` do Patch 025 tratava qualquer invocação como "abrir wizard", sem inspecionar se havia corpo após `/registro`. `_parse_registro_body` (do modo antigo) ficou órfão.

### Correção

`registro_command` agora:
1. Extrai o corpo com `re.sub(r"^/registro(?:@\w+)?\s*", "", raw_text, count=1)`.
2. Se corpo **vazio** → inicia wizard interativo (fluxo do Patch 025 intacto).
3. Se corpo **presente** → chama `_parse_registro_body` + `_append_registro_to_biblioteca` direto e confirma `✅ Registro NNN salvo`.
4. Validação mínima: exige `Patrick:` e `Exemplos:` preenchidos (o resto é opcional).

Assim o Patrick tem os dois caminhos:
- Do celular: `/registro` → wizard guia campo a campo com exemplos rotativos.
- Do desktop / cópia colada: `/registro\n<textão pronto>` → grava direto sem entrar em wizard.

### Entrada perdida recuperada manualmente

Como o wizard já tinha interceptado a entrada de ciúme que Patrick mandou (03:35), appendei manualmente como **Registro 041 — Ciúme porque ele teve tempo pra tudo menos pra ela** direto no `.md`. Biblioteca passou de 40 → 41 registros, 76 → 80 exemplos (voice_library confirmou parse).

### Arquivos alterados

- `bot.py` — `registro_command` reescrito com bifurcação corpo-vazio/corpo-cheio.
- `data/feedback/BIBLIOTECA_COMPORTAMENTAL_MARINA.md` — Registro 041 appendado manualmente (não passou pelo comando).


---

## Patch 027 — Estabilização de testes contra janela de sono + prompts traduzidos

**Data:** 2026-09-21 05:00
**Origem:** vistoria completa da suite pedida por Patrick após restart do Patch 026. Rodou 444 testes: 15 failures + 2 errors. Diagnóstico revelou 3 causas independentes.

### Causa raiz das 17 falhas

**A. Schema version desatualizado (3 testes)**
As migrations 018 (conversation_model) e 019 (media_context_cache) subiram schema para 19. Testes ainda esperavam 17:
- `tests/test_world_repository.py:39`
- `tests/test_bootstrap_v36.py:66`
- `tests/test_social_world.py:100`

Fix: `assertEqual(...schema_version(), 19)` nos três.

**B. Prompt traduzido para pt-BR (2 testes)**
Patch 021 traduziu `[KNOWLEDGE POLICY]` → `[POLÍTICA DE CONHECIMENTO]`. Testes procuravam o marker antigo:
- `tests/test_knowledge_privacy.py:138` — asserção de bloco no prompt
- `tests/test_knowledge_privacy.py:177` — asserção de bloco em legacy_bot_context

Fix: atualizar strings esperadas para versão em pt-BR.

**C. AVAILABILITY_DEFER bloqueando process_incoming_batch de madrugada (11+1 testes)**
Esta foi a descoberta mais interessante. Confirmado via `git stash`: as falhas **já existiam no HEAD limpo `a02961e`**, não são regressão da sessão.

Motivo: quando `process_incoming_batch` roda dentro da janela de sono da Marina (00-08h), `availability_service.evaluate_and_maybe_defer` retorna `('deferred', ...)` e o fluxo aborta com `return`. O reminder/knowledge-dispatch nunca chega ao código de confirmação. **Os testes não foram atualizados quando Response Availability (Stage 15, release 3.7.0) foi introduzido.** Só 1 dos 18 testes de `test_audit_fixes_v3_5` passava `availability_bypass=True`.

Fix: patch de classe no `setUp` de `TestAuditFixesV35` e `TestKnowledgeDialogue`:
```python
self._availability_patcher = patch.object(
    bot.availability_service, "evaluate_and_maybe_defer",
    return_value=("proceed", None, None),
)
self._availability_patcher.start()
self.addCleanup(self._availability_patcher.stop)
```

Isso força availability a "proceed" em todos os testes da classe, sem tocar em bot.py nem obrigar cada teste a passar `availability_bypass=True`.

### Resultado

- **10/11 testes de `test_audit_fixes_v3_5` recuperados** com o patch de setUp.
- **7/7 testes de `test_knowledge_dialogue` recuperados**.
- **5 falhas de schema/prompt corrigidas**.

### Sobra: 1 falha estrutural (não regressão)

`test_offer_acceptance_does_not_leave_second_direct_reminder_pending` ainda falha em:
```
AssertionError: '09:30' not found in 'Posso te ligar na hora?'
```

Análise: o teste mocka `bot.llm_client.chat.completions.create` para retornar `"Posso te ligar na hora?"` e depois espera que `captured[0]` (mensagem enviada ao Patrick) contenha `"09:30"` (horário do reminder confirmado) e NÃO contenha `"ligar"`. Não existe nenhum branch em `bot.py` que reescreva a resposta do LLM baseado em `reminder_decision_instruction` — a instrução é injetada como `role=system` para o LLM interpretar. Com LLM real seguindo Hard Line "sem chamada de voz" (Patch 022), esse teste passaria; com mock hard-coded, nunca passa.

Isso é dívida do teste (assume comportamento agentico do LLM real), não regressão de código. Marcado como "test-quality issue" no relatório para revisão manual. Não bloqueia soak.

### Arquivos alterados

- `tests/test_world_repository.py` — schema 17→19
- `tests/test_bootstrap_v36.py` — schema 17→19
- `tests/test_social_world.py` — schema 17→19
- `tests/test_knowledge_privacy.py` — `[KNOWLEDGE POLICY]` → `[POLÍTICA DE CONHECIMENTO]`
- `tests/test_audit_fixes_v3_5.py` — availability_patcher em setUp + test_reaction_is_permissive_... renomeado/invertido (era `test_reaction_is_skipped_...` — Patch 019 mudou intencionalmente para permissive-by-default)
- `tests/test_knowledge_dialogue.py` — availability_patcher em setUp
- `PLANO_VOZ_MARINA_V371.md` — Fase C.2 (watch-along) adicionada (FB-20260921-044703)

### Placar

- Antes: 429/444 passando (15 F + 2 E)
- Depois: **443/444 passando** (1 test-quality issue conhecido)

---

## Patch 028 — Guard estendido para Unicode "estilizado"

**Data:** 2026-09-21 05:15
**Origem:** débito técnico do Patch 020 — o guard `_has_foreign_script_leak` cobria cirílico/CJK/árabe mas não pegava faixas Unicode que o LLM usa como decoração pseudo-fancy. Bug observado no soak de 20/09 com "𝟣/𝟤" (Mathematical Bold), documentado como pendente.

### Adições no `_FOREIGN_SCRIPT_RE`

- **Mathematical Alphanumeric Symbols** (`U+1D400-U+1D7FF`) — cobre `𝐀`, `𝟣`, `𝔸`, `𝕒` e todas as variantes bold/italic/fraktur/script/double-struck/monospace/sans-serif de letras e dígitos.
- **Letterlike Symbols** (`U+2100-U+214F`) — cobre `ℝ`, `ℂ`, `ℕ`, `ℤ`, `ℚ`, `℘`, `℗`, `℮`.
- **Fullwidth Forms** (`U+FF00-U+FFEF`, faixa `！-～`) — cobre `Ａ`, `Ｂ`, `！`, `？` (usados por LLMs asiáticos como "estilo".

Threshold segue `>=2` — 1 caractere é tolerado (ex: usuário citar "ℝ" numa piada matemática). Sequência de 2+ dispara retry endurecido.

### Sanity

7/7 casos manuais:
- pt-br normal → false
- 1 dígito math bold → false (tolerado)
- 2 dígitos math bold → true
- 2 letterlike → true
- 3 fullwidth → true
- cirílico → true
- "Konosuba e Netflix" → false (nomes próprios ok)

### Arquivos alterados

- `bot.py` — `_FOREIGN_SCRIPT_RE` estendido.

---

## Patch 029 — Ajustes de biblioteca (3 opiniões aplicadas)

**Data:** 2026-09-21 05:35
**Origem:** Patrick pediu opinião sobre a biblioteca após popular 41 registros novos. Três ajustes propostos e aprovados.

### #3 — Template enxuto para novos registros

Removidos do template gerado por `_append_registro_to_biblioteca` os 6 campos que nunca eram preenchidos em soak real: "Princípio comportamental", "Marina respondeu", "O que ela deveria perceber", "Reação esperada", "Avaliação", "Observações". Ficam só 8 campos que o parser realmente usa: Origem, Categoria, Data, Contexto, Patrick disse, Tom, Exemplos, Evitar. Registros antigos permanecem intactos — o parser tolera os campos extras.

### #1 — Recategorização do cluster de vulnerabilidade

Os 8 registros 029-036 tinham categoria muito parecida (`vulnerabilidade / intimidade emocional` em todos), fazendo o retriever `select_examples(max_per_patrick=2)` amostrar 2 desse mesmo cluster e sufocar outros tons. Recategorizados com tags específicas:

| # | Categoria antiga | Categoria nova |
|---|------------------|----------------|
| 029 | vulnerabilidade / insegurança | vulnerabilidade_academica_profissional / sobrecarga |
| 030 | vulnerabilidade / medo | vulnerabilidade_antecipatoria / nervosismo_pre_evento |
| 031 | vulnerabilidade / relacionamento | vulnerabilidade_relacional / medo_decepcionar |
| 032 | vulnerabilidade / solidão | vulnerabilidade_afetiva / solidao |
| 033 | vulnerabilidade / acolhimento | vulnerabilidade_afetiva / pedido_acolhimento |
| 034 | vulnerabilidade / independência | vulnerabilidade_relacional / aceitar_apoio |
| 035 | vulnerabilidade / mágoa | vulnerabilidade_relacional / magoa |
| 036 | vulnerabilidade / intimidade / confiança | vulnerabilidade_afetiva / exaustao_emocional |

O retriever agora consegue escolher o subgênero de vulnerabilidade certo pra situação.

### #2 — Guard anti-invenção de lore nas piadas internas

Registros 069-076 catalogam piadas internas usando expressões placeholder ("zika reversa", "'ela' trabalhar", apelidos). Se o retriever puxa esses few-shots sem contexto real, o LLM começa a inventar lore compartilhado que nunca aconteceu ("finalmente a Marina fala da zika reversa que nunca combinamos").

**Fix em `voice_library.py`:**

1. `VoiceExample` ganhou campo `categoria: str = ""` populado pelo parser.
2. Constante `_SHARED_LORE_CATEGORIES` lista palavras-chave que marcam registro como "lore compartilhado" (piada interna, apelido, código interno, linguagem do casal).
3. Nova função `_exemplo_amarrado_ao_contexto(ex, recent_context)`: extrai palavras 4+ letras do `ex.marina` (ignorando stopwords "amor", "meu", "kkkk" etc.) e testa se alguma aparece no `recent_context`.
4. `select_examples` filtra: se o exemplo é lore-compartilhado E não tem match com o contexto recente, cai fora. Sem contexto passado → todos os lore são bloqueados por padrão (segurança).
5. `build_voice_block` aceita e propaga `recent_context`.
6. `world_context.py` puxa 8 últimas mensagens da sessão via `get_mensagens_sessao(limit=8)` e passa como contexto.

**Comportamento resultante:**
- Primeira vez que a Marina pega "zika reversa" via few-shot: só rola se você tiver usado essa expressão nos últimos 8 turnos.
- Do jeito que era antes, o LLM poderia começar do nada com "aquela nossa zika reversa" sem histórico nenhum.

### Validação

- `python -m unittest tests.test_voice_library`: 15/15 verdes.
- Sanity manual: `_exemplo_amarrado_ao_contexto(reg_069_zika_reversa, "vc lembra da zika reversa amor")` → `True`. Sem contexto → `False`.
- Import de `bot.py`, `world_context.py`, `voice_library.py` limpo.

### Arquivos alterados

- `bot.py` — `_append_registro_to_biblioteca` com template enxuto.
- `voice_library.py` — `VoiceExample.categoria`, `_SHARED_LORE_CATEGORIES`, `_exemplo_amarrado_ao_contexto`, `select_examples` e `build_voice_block` com `recent_context`.
- `world_context.py` — passa histórico curto pra `build_voice_block`.
- `data/feedback/BIBLIOTECA_COMPORTAMENTAL_MARINA.md` — registros 029-036 recategorizados.

---

## Patch 030 — Seis defeitos do soak de 21/09 manhã

**Data:** 2026-09-21 08:30
**Origem:** export `conversation_export_20260921_081341.txt`, conversa de 07:57-08:05. Patrick: "problemas e problemas". Seis defeitos independentes, um deles (o mais grave) apontado por ele.

### Defeito 1 (CRÍTICO) — Marina mentiu sobre onde estava

**Observado:** Patrick viu no `/status` que ela estava passeando com o Milo e perguntou "tá fazendo o que agora?". Ela respondeu *"Estou aqui no meu quarto, lendo um pouco antes de começar o dia"*.

**Investigação:** dois bugs em camadas diferentes.

**1a. `_map_place_activity` não conhecia metade das rotinas canônicas.** Testando as 7 atividades que a `RoutineEngine` gera:

| rotina | activity | mapeado ANTES | depois |
|---|---|---|---|
| pet_walk | "passeando com Milo" | **UNKNOWN** | PET_WALK |
| wake | "acordando e tomando café" | **SOCIAL** | WAKING |
| university | "na faculdade" | CLASS | CLASS |
| gym | "treinando na academia" | GYM | GYM |
| home_evening | "curtindo a noite em casa" | HOME_RELAXING | HOME_RELAXING |
| sleep | "dormindo" | SLEEPING | SLEEPING |
| free_time | "tempo livre em casa" | HOME_RELAXING | HOME_RELAXING |

O `wake` era o pior: "acordando e tomando café" batia na heurística `'tomando café' → SOCIAL`, então durante toda a janela de 07:00-08:30 a Marina era tratada como se estivesse num bar com amigos. Exatamente o horário do "Bom dia amor da minha vida!".

Criados `PET_WALK` e `WAKING` em `DEFAULT_PROFILES`, com `'acordando'` testado ANTES de `'tomando café'` e `place_key == 'enseada_botafogo'` como fallback. Ambos incluídos na lista de soft-delay do `bot.py`.

**1b. O disclaimer do prompt sabotava o estado canônico.** O bloco `[SEU ESTADO ATUAL]` dizia corretamente "Atividade: passeando com Milo", mas logo abaixo vinha:

> "Se você esteve em conversa com o Patrick nos últimos minutos, é MAIS provável que ainda esteja em casa do que tenha saído sem avisar."

Esse texto era aplicado a **qualquer** estado não-binding, inclusive quando a rotina canônica colocava a Marina legitimamente fora de casa. **Ela obedeceu o prompt.** O disclaimer foi escrito para impedir que inventasse uma saída; na prática mandava negar as saídas reais.

Agora o texto depende de onde a rotina colocou ela: se o local é o apartamento, mantém o aviso anterior; se é externo, instrui a não dizer que está em casa e a mencionar a saída com naturalidade ("saí pra X agorinha").

### Defeito 2 (CRÍTICO) — Token de dataset vazou na fala

```
MARINA: Sim, tenho aula hoje às 10h. E você, tem alguma coisa planejada para hoje? affirmation_pronouns=true
```

`affirmation_pronouns=true` não existe em nenhum arquivo do repo — é artefato de dataset instrucional que o Nemo colou no fim do turno. Os guards do Patch 020/028 não pegavam: é ASCII latino puro, não é emoji-only nem script estrangeiro.

Novo `_has_debug_artifact_leak` cobre `chave=valor` técnico (booleano/número), tags `<...>`, flags `--xxx`, `ns::func`, `[INST]`, `<|im_start|>`.

### Defeito 3 (CRÍTICO) — Hard Line contra chamada violada

```
MARINA: Se precisar de alguma coisa ou quiser fazer alguma coisa juntos mais tarde, é só me ligar, viu?
```

A `[LINHAS DURAS]` proíbe propor chamada desde o Patch 022. O modelo ignorou. **Conclusão estrutural: regra negativa em prompt não é garantia em modelo 12B — precisa de guard pós-resposta.**

Novo `_proposes_live_call` pega "me liga", "te ligo", "videochamada", "chamada de voz/vídeo", "chama no vídeo", Zoom/FaceTime/Meet/Discord. Testado contra falsos positivos: "ligar o computador", "liguei pra pizzaria", "religar o modem", "me liguei que esqueci a chave" — todos passam.

Ambos entram no `_needs_retry_for_junk` com hint de retry próprio. Novo `_salvage_reply` como último recurso: se o retry também sai ruim, corta a sentença ofensora e preserva o resto da fala, em vez de enviar o lixo.

### Defeito 4 (IMPORTANTE) — Respostas fora de ordem + turno abortado no meio

```
07:57:39 PATRICK: Bom dia amor da minha vida!
07:57:47 PATRICK: Tá acordada já?              (8s depois — fora da janela de 3.8s)
07:57:54 MARINA:  Bom dia, amor! Como você acordou tão cedo?
07:58:39 MARINA:  Sim, amor, já acordei.        (responde a pergunta ANTERIOR à primeira resposta)
```

O debounce cancelava o timer enquanto o Patrick digitava, mas depois que a janela expirava o turno entrava no pipeline e levava ~10-15s no LLM. Mensagem que chegasse nesse intervalo abria um ciclo **paralelo**.

Pior: `add_message` chamava `.cancel()` em qualquer task não-concluída — inclusive a que já estava **executando o callback**, com o `await callback(...)` dentro do `try/except CancelledError`. Ou seja, uma mensagem nova abortava silenciosamente o turno em geração. Isso explica os `pending=17` órfãos no log de availability.

Corrigido com dois mecanismos no `MessageDebouncer`:
- `_waiting` separa as tasks ainda na janela (canceláveis) das que entraram no pipeline (intocáveis).
- Lock por chat serializa os turnos; ao assumir o lock, o buffer é drenado de novo, então mensagens que chegaram durante o turno anterior entram no mesmo turno seguinte.

Testes em `tests/test_debouncer_serialization.py` cobrem os quatro cenários (ordem preservada, coalescência durante turno lento, burst dentro da janela, isolamento entre chats).

### Defeito 5 (IMPORTANTE) — Perguntas de entrevista no fecho

Quatro ocorrências na mesma conversa: "E você, tem alguma coisa planejada para hoje?", "E mais tarde, vai fazer alguma outra coisa?", "E aí, o que você vai fazer hoje?", "Tudo certo com você?".

Em vez de gastar uma chamada de LLM em retry, o corte é cirúrgico: `_strip_interview_closer` remove a sentença final quando ela é pergunta **genérica** e sobra substância antes. O critério é generalidade, não interrogação — "vai comer o quê?", "é que horas?", "conseguiu resolver aquilo?" puxam detalhe concreto e passam intactas. Se a resposta inteira for a pergunta, mantém (melhor protocolar que vazio).

Roda só em modo casual, e nunca quando o turno depende de pergunta (`should_offer_reminder`, `needs_clarification`). Kill switch: `VOICE_STRIP_INTERVIEW_CLOSER`.

### Defeito 6 (pendente de janela) — "Filme de Romance" persistido no banco

O Patch 023 impede criar novos placeholders, mas o antigo continua gravado:
- `eventos_pendentes.id=1` — `status='pending'`, venceu 21/09 01:00 e nunca fechou
- `world_state.id=2,3,4,5` — activity com a concatenação suja "descrição | Follow-up: pergunta"
- `conversas.id=6` — a fala original da Marina, que o retriever pode trazer de volta

Criado `scripts/purge_placeholder_media.py` (backup automático + dry-run). **Não executado**: o bot estava rodando (PID 28448) e escrever no banco de produção com o processo ativo arrisca lock e sobrescrita por cache em memória. Rodar com o `.bat` fechado:

```
python scripts/purge_placeholder_media.py --apply
```

### Defeitos observados e NÃO corrigidos nesta rodada

- **"Ah, entendi."** — abertura proibida pela `[LINHAS DURAS]`, violada. Mesmo caso estrutural do defeito 3: vai precisar de guard pós-resposta.
- **"eu sempre chego na hora certo"** — erro de concordância ("hora certa").
- **"obrigada por perguntar!" / "Beijos 😘"** — polidez formal de assistente.
- **Voz geral ainda protocolar** — os few-shots não estão sobrepondo o padrão base do Nemo.

### Leitura estrutural

Três das seis falhas (2, 3 e o "Ah, entendi") são **regras de prompt ignoradas pelo modelo**. Com 5+ proibições simultâneas num 12B, a chance de pelo menos uma vazar por turno é alta. A estratégia precisa migrar de "listar proibições" para "interceptar e corrigir pós-resposta" — os guards deste patch são o primeiro passo nessa direção.

### Arquivos alterados

- `response_availability.py` — profiles `PET_WALK`/`WAKING`, precedência de `acordando`, `enseada_botafogo`.
- `world_context.py` — disclaimer de rotina condicionado a estar em casa ou fora.
- `bot.py` — `_DEBUG_ARTIFACT_RE`, `_CALL_PROPOSAL_RE`, `_INTERVIEW_CLOSER_RE`, `_has_debug_artifact_leak`, `_proposes_live_call`, `_strip_interview_closer`, `_salvage_reply`, hints de retry novos, `MessageDebouncer` com `_waiting` + lock por chat, `PET_WALK`/`WAKING` no soft-delay.
- `config.py` — `VOICE_STRIP_INTERVIEW_CLOSER`.
- `scripts/purge_placeholder_media.py` — novo (pendente de execução).
- `tests/test_debouncer_serialization.py` — novo, 4 testes.
- `tests/test_reply_guards_v030.py` — novo, 13 testes.

---

## Patch 031 — Polidez de assistente removida da fala

**Data:** 2026-09-21 08:55
**Origem:** defeitos que sobraram do Patch 030, mesma conversa de 21/09 07:57-08:05.

### O que foi cortado

Três padrões de linguagem de atendimento que o Nemo insiste em produzir, todos já proibidos na `[LINHAS DURAS]` e todos ignorados pelo modelo:

**1. Muleta "Ah," de abertura** — "Ah, entendi.", "Ah, legal!"

O corte precisa ser cirúrgico, porque interjeição com "ah" é voz legítima da Marina e está aprovada na biblioteca:

| texto | veredito |
|---|---|
| "Ah, entendi. Tudo bem amor" | cortado → "Entendi. Tudo bem amor" |
| "AH NÃO KKKKKKK isso já tá virando tradição" | intacto (registro 070) |
| "ah então tempo vc teve né… só esqueceu de mim mesmo…" | intacto (registro 041) |
| "ihhh já começou a zika reversa? kkkkk" | intacto (registro 069) |
| "Aaaahhh! é que horas?" | intacto (canônico) |

O critério é "ah" curto + vírgula + palavra de concordância neutra (`entendi|legal|sei|tá|ok|certo|sim|claro|bacana|verdade|beleza`). Interjeição real vem alongada, em caixa alta ou com carga emocional, e não casa. A primeira letra do que sobra é recapitalizada.

**2. Polidez de atendimento** — "obrigada por perguntar", "fico à disposição", "se precisar de alguma coisa é só me chamar", "qualquer dúvida estou aqui"

"obrigada amor, vc é o melhor" e "obrigada por hoje, foi tão bom" passam — o gatilho é a fórmula de serviço, não o agradecimento.

**3. Assinatura de despedida** — "Beijos 😘" / "Beijinhos!" isolados no fim do turno

Pega quando abre a sentença (início de linha ou após pontuação) e termina o texto. "te enchendo de beijos agora", "manda beijo pro Milo" e "quero mil beijos seus" passam.

### Garantia anti-vazio

`_strip_assistant_politeness` nunca devolve string vazia. Se a resposta inteira for polidez ("Fico à disposição!"), o original é preservado — turno protocolar é ruim, turno vazio é pior. Roda em todos os modos, com kill switch `VOICE_STRIP_ASSISTANT_POLITENESS`.

### Descoberta lateral: o sistema de lições de linguagem está vazio

`db.get_licoes_linguagem()` devolve `[]`. O mecanismo funciona e é injetado no prompt (`memory.py:102-103`), mas os únicos gatilhos que o alimentam são o Patrick escrever "pro você" ou "obrigado" em contexto feminino (`bot.py:2938-2941`). Nada mais nunca cadastrou uma lição, então o prompt recebe "Nenhuma correção necessária apontada ainda" desde o início do soak.

Isso é um canal de correção pronto e sem uso. Sugestão para o Patrick decidir: um comando `/licao <regra>` que grava direto, ou ampliar os gatilhos automáticos.

### Não corrigido: concordância ("eu sempre chego na hora certo")

Erro de gênero em expressão comum. Não tem solução por regex sem falso positivo — "certo" é adjetivo válido em dezenas de construções, e a correção depende do substantivo que ele qualifica. As opções reais são uma lição de linguagem no prompt (que reduz, não elimina) ou trocar de modelo. Fica em aberto.

### Validação

- `tests/test_voice_politeness_v031.py`: 10 testes, incluindo proteção explícita dos exemplos da biblioteca contra regressão.
- Teste integrado cobre o turno real das 08:04, que tinha muleta + polidez + proposta de chamada ao mesmo tempo: guard de chamada manda pra retry, salvage corta a sentença, polidez sai no fim.

### Arquivos alterados

- `bot.py` — `_AH_CRUTCH_RE`, `_SERVICE_POLITENESS_RE`, `_SIGNOFF_RE`, `_strip_assistant_politeness`, chamada no pipeline após `_strip_interview_closer`.
- `config.py` — `VOICE_STRIP_ASSISTANT_POLITENESS`.
- `tests/test_voice_politeness_v031.py` — novo.

### Execução do purge do Patch 030

`scripts/purge_placeholder_media.py --apply` rodou às 08:53, com o banco livre:
- `eventos_pendentes.id=1` → `cancelled`, description "assistir ao filme juntos"
- `world_state.id=2,3,4,5` → activity saneada
- `conversas.id=6` → "Estou assistindo um filme que peguei aqui..."
- Backup: `backups/pre_placeholder_purge_20260921_085338.db`
- Segunda execução confirma idempotência ("Nada a fazer").

Correção de rumo: eu havia afirmado que o bot estava rodando (PID 28448). Era o `cams-auto-publisher`, outra aplicação do Patrick. Nenhuma instância da Marina estava ativa.

---

## Patch 032 — Default de idioma do prompt e migration 018 não idempotente

**Data:** 2026-09-21 09:05
**Origem:** suite completa pós-Patch 031 (471 testes, 2 failures + 2 errors). Duas das quatro falhas expuseram defeitos estruturais, não dívida de teste.

### Defeito 1 — Default do prompt era inglês

`test_prompt_integration_excludes_unclassified_memory_when_flag_enabled` falhou procurando `[POLÍTICA DE CONHECIMENTO]`. O prompt gerado tinha saído **inteiro em inglês**: `[CONTROL RULES]`, `[MARINA VOICE]`, `[HARD LINES]`, `[FACTS]`, `[DATA CHANNEL POLICY]`, `[KNOWLEDGE POLICY]`.

Causa: três defaults apontando para `"en"`.

| local | antes | depois |
|---|---|---|
| `world_context.py:33` — parâmetro `control_language` | `"en"` | `None` → resolve do setting |
| `config.py:197` — `PROMPT_CONTROL_LANGUAGE` | `os.getenv(..., "en")` | `os.getenv(..., "pt-BR")` |
| `context_builder.py:64` — fallback do `getattr` | `"en"` | `"pt-BR"` |

**Em produção o Patch 021 estava ativo**: o `.env` do Patrick tem `PROMPT_CONTROL_LANGUAGE="pt-BR"` e o valor é lido corretamente (aspas removidas pelo dotenv). Confirmado por inspeção antes de qualquer alteração.

Mas o default era uma armadilha real: qualquer caminho que instancie `WorldContextBuilder` e chame `build()` sem passar o parâmetro — um teste, um script, uma feature nova, um ambiente sem a variável setada — montava o prompt inteiro em inglês **sem nenhum aviso**. É precisamente o defeito que o Patch 021 identificou como a causa mais impactante da voz degradada, deixado ao alcance de um esquecimento.

Agora o parâmetro nasce `None` e resolve `settings.PROMPT_CONTROL_LANGUAGE`, com `pt-BR` como último recurso. Validado: `build()` sem argumento produz 5/5 marcadores PT e 0/5 EN.

### Defeito 2 — Migration 018 quebrava em replay

`test_upgrade_from_schema_eight_backed_up_before_migration` e `test_upgrade_from_nine_and_habitual_decay` falharam com:

```
sqlite3.OperationalError: duplicate column name: model
```

Os dois testes simulam downgrade: dropam tabelas de social/academic e apagam `schema_version >= 9`, depois reexecutam as migrations. A tabela `conversas` fica intacta, então a coluna `model` sobrevive — mas o registro da migration 18 desaparece, e o replay tenta `ALTER TABLE conversas ADD COLUMN model` de novo.

A migration 018 (Patch 018) foi escrita sem considerar replay. SQLite não tem `ADD COLUMN IF NOT EXISTS`, e o `db.py` já tinha um mecanismo de recovery — deliberadamente escopado à migration 012 (commit `5092283`, "scope duplicate column recovery to migration 012"), justamente para não mascarar erro de schema real.

Respeitando essa decisão, o recovery passou de um `if version_num != 12` hardcoded para um mapa explícito:

```python
replayable = {
    12: ('eventos_pendentes', {...colunas de calendário...}),
    18: ('conversas', {'model'}),
}
```

Continua escopado — migration fora do mapa, ou erro que não seja `duplicate column name`, sobe como antes. A verificação final de que as colunas existem agora nomeia a tabela e a versão na mensagem de erro.

### Falhas restantes da suite

Das 4 originais, 3 são estas duas correções. A quarta é `test_offer_acceptance_does_not_leave_second_direct_reminder_pending`, a dívida de teste já documentada no Patch 027: o teste mocka o LLM com uma string fixa e depois exige que a resposta contenha `"09:30"` e não contenha `"ligar"`. Não há código que reescreva a saída do modelo — a instrução vai como `role=system` para o LLM interpretar. Com mock, nunca passa.

Vale registrar que esse teste ficou ainda mais estranho depois do Patch 030: o `"ligar"` que ele proíbe é hoje capturado pelo guard `_proposes_live_call`, mas o guard atua sobre a resposta real do modelo, não sobre um mock hardcoded.

### Arquivos alterados

- `world_context.py` — `control_language` default `None` com resolução via settings.
- `config.py` — `PROMPT_CONTROL_LANGUAGE` default `pt-BR`.
- `context_builder.py` — fallback do `getattr` para `pt-BR`.
- `db.py` — recovery de replay generalizado para um mapa escopado `{versão: (tabela, colunas)}`.

---

## Patch 033 — Captura de voz em tempo real (`/bom` e `/ruim`)

**Data:** 2026-09-21 09:30
**Origem:** pedido do Patrick — "sabe o wizard da biblioteca? Se tivesse uma opção pra adicionar em tempo real, tipo eu conversando com ela aí ela dá uma resposta interessante e boa, eu conseguir salvar, e o contrário também seria um adianto pra gente".

### O problema com o wizard

O `/registro` do Patch 025/026 serve bem para sessão dedicada, mas o momento em que dá para julgar uma resposta é imediatamente depois dela chegar. Abrir wizard de 7 etapas no meio de uma conversa tira o Patrick do fluxo — e a resposta boa já passou.

### Comandos

| comando | aliases | destino |
|---|---|---|
| `/bom` | `/boa`, `/salvar` | biblioteca comportamental (few-shot positivo) |
| `/ruim` | `/evitar`, `/nao` | antibiblioteca (bloco `[COMO NÃO SOAR]`) |

Ambos resolvem o alvo de duas formas:
- **com reply** numa mensagem específica da Marina → usa aquela
- **sem reply** → usa a última coisa que ela falou

Reply em foto/áudio sem legenda ainda funciona: cai no histórico de `ULTIMAS_MENSAGENS_MARINA` por `message_id`.

Um comentário depois do comando vira anotação:

```
/ruim soou como atendente de SAC
/bom essa reação foi perfeita
```

O contexto (`Patrick disse`) é recuperado automaticamente da última fala dele em `get_mensagens_sessao`, ignorando linhas que começam com `/`.

### Fase B1 do plano de voz, finalmente fechada

O `PLANO_VOZ_MARINA_V371.md` previa desde o início:

> **B1** Adaptador: quando o Patrick classifica um turno como "ruim", o exemplo entra em `avoid_bank`, também injetado no prompt (bloco `[COMO NÃO SOAR]`).

Isso nunca tinha sido implementado — o `/feedback` gravava observações, mas nenhum exemplo negativo voltava ao prompt. Agora o ciclo fecha:

1. `/ruim` grava em `data/feedback/COMO_NAO_SOAR_MARINA.md`
2. `voice_library.parse_avoid_examples()` lê os registros
3. `voice_library.build_avoid_block()` monta o bloco com os N mais recentes
4. `world_context` injeta **depois** dos few-shots positivos — o modelo lê o padrão desejado primeiro e o contraste em seguida

O bloco identifica explicitamente a fala como errada:

```
[COMO NÃO SOAR — falas suas que o Patrick marcou como erradas]
Estes são turnos REAIS seus que soaram mal. Não repita a forma deles.
---
Patrick: q bom princesa, tá fazendo o que agora?
Marina (RUIM): Estou aqui no meu quarto, lendo um pouco antes de começar o dia.
Problema: disse que estava em casa quando estava passeando com o Milo
---
```

Os mais recentes entram primeiro porque refletem o que o Patrick está corrigindo agora. Sem capturas, o bloco não aparece no prompt.

### Por que isso importa mais que os guards

Os Patches 030-031 corrigem sintomas conhecidos por regex. Este comando deixa o Patrick corrigir sintomas que eu não previ, sem precisar de uma sessão de código para cada um. É o canal que transforma observação em correção de prompt.

Vale contrastar com o sistema de lições de linguagem (`db.get_licoes_linguagem`), que está vazio desde o início do soak: o Patrick avaliou que poderia "colocar algo errado" numa regra abstrata. Capturar um exemplo concreto tem menos risco — é a fala real, não uma generalização.

### Configuração

- `VOICE_AVOID_BLOCK_ENABLED` (default `true`) — kill switch do bloco
- `VOICE_AVOID_MAX_EXAMPLES` (default `4`) — quantos exemplos entram por turno

### Validação

`tests/test_voice_capture_v033.py` — 13 testes: resolução de alvo (reply, última fala, foto sem legenda, histórico vazio, entradas em branco), criação/numeração/roundtrip da antibiblioteca, e o bloco de prompt (vazio sem capturas, traz os mais recentes, rotula como RUIM).

### Arquivos alterados

- `bot.py` — `ANTIBIBLIOTECA_PATH`, `_resolve_marina_target`, `_last_patrick_line`, `_append_avoid_example`, `bom_command`, `ruim_command`, handlers dos 6 aliases.
- `voice_library.py` — `AvoidExample`, `parse_avoid_examples`, `build_avoid_block`.
- `world_context.py` — injeção do bloco `[COMO NÃO SOAR]`.
- `config.py` — `VOICE_AVOID_BLOCK_ENABLED`, `VOICE_AVOID_MAX_EXAMPLES`.
- `tests/test_voice_capture_v033.py` — novo.
