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
