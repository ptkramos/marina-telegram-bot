# Revisão técnica — Marina 3.5, rodada 3

**Data:** 17/09/2026  
**Commit auditado:** `4d805f5` (`fix(release): resolve review round 2 findings P0 to P2 for Marina 3.5`)  
**Referência:** `REVISAO_TECNICA_MARINA_V3_5_RODADA_2.md`  
**Gate:** **ainda não aprovar a 3.5 completa para operação contínua.**

## Resultado da validação

O `UnboundLocalError` foi corrigido: o ID da mensagem citada pelo usuário é obtido antes da verificação da oferta. As confirmações genéricas sem contexto explícito deixaram de ser aceitas; a reflexão recebeu claim transacional e índice único para intervalo; e o pedido direto sem horário agora registra um esclarecimento pendente. São avanços concretos.

Os testes da rodada passaram, mas dois contratos do fluxo enviado ao usuário ainda não estão garantidos. A pergunta “quando?” é acrescentada à fala **antes** de o Planner sinalizar que ela é necessária. Já a suposta garantia de que a oferta foi perguntada aceita qualquer texto com a palavra “lembrete”, mesmo sem uma pergunta. Há ainda risco de associar uma mensagem ao lembrete errado quando já existe uma oferta aberta.

## Testes executados

- `python -m unittest tests.test_audit_fixes_v3_5 -q`: **15 testes, 0 falhas** (SQLite temporário e mocks).
- `python -m unittest discover -s tests -p 'test_*.py' -q`: **144 testes, 0 falhas, 3 ignorados**. Os três ignorados dependem da LLM real, indisponível neste ambiente por `Connection error`; o ajuste da suíte passou a classificá-los como ignorados em vez de tratar a resposta vazia como resultado válido.
- Inspeção do diff `0e157ef..4d805f5` e dos caminhos completos de criação, resposta e envio. Não houve entrega real ao Telegram nem execução bem-sucedida contra a LLM/voz real.

## P1 — O pedido direto sem horário ainda pode ser respondido sem “quando?”

**Locais:** `bot.py`, bloco que prepara `messages` e a fala (`needs_clarification`, aproximadamente linhas 1342 e 1451), e chamada de `planner.apply_plan_effects()` (aproximadamente linha 1463); `planner.py`, bloco de `direct_reminder` (aproximadamente linhas 396–432).

O Planner define `plan["needs_clarification"] = "direct_reminder_time"` **dentro de `apply_plan_effects()`** ao descobrir que `remind_at` é vazio, inválido ou está no passado. O bot chama esse método somente após gerar a resposta da LLM e após os dois pontos que consultam `needs_clarification` para inserir a pergunta. Assim, no caso normal de um pedido direto vago, a primeira resposta pode ser enviada sem solicitar o horário. O estado pendente fica persistido, mas Patrick não é necessariamente avisado de que precisa completá-lo. O teste novo chama `apply_plan_effects()` isoladamente e valida o segundo turno; não verifica o conteúdo enviado no primeiro.

**Correção necessária:** decidir e sinalizar o esclarecimento antes de compor a resposta ou executar uma etapa posterior que acrescente a pergunta de forma determinística. Testar o primeiro turno inteiro com LLM que omite a pergunta e verificar o texto efetivamente transmitido.

## P1 — Oferta marcada como apresentada sem pergunta verificável

**Locais:** `bot.py`, checagem `has_offer_in_text` e associação da última oferta a `offer_message_id` (aproximadamente linhas 1440–1450 e 1505–1517); `planner.py`, criação da oferta antes do envio.

O novo fallback só acrescenta a pergunta quando a fala não contém uma das palavras `lembr`, `aviso`, `avisar` ou `lembrete` como palavra completa. Uma resposta como “Já anotei um lembrete para depois.” contém `lembrete`, passa pelo teste e é enviada sem qualquer pergunta de consentimento; ainda assim, a oferta recebe o ID da mensagem. O inverso também ocorre: “Quer que eu te lembre?” não corresponde a `lembr` como palavra completa, de modo que a pergunta pode ser duplicada. A presença de um vocábulo não comprova a oferta.

O bot também chama `get_last_offered_reminder()` depois do envio para escolher o registro. Ele não guarda o ID criado por `apply_plan_effects()` neste turno. Se a criação deste turno falhar, for ignorada por deduplicação ou não houver horário válido, uma oferta anterior ainda aberta pode receber o ID da resposta atual ou ser cancelada indevidamente. A checagem `should_offer_reminder` sozinha não distingue esses casos.

**Correção necessária:** obter do Planner o ID exato da oferta criada/reutilizada neste turno. Garantir a frase interrogativa de consentimento na saída enviada, independentemente da formulação da LLM; associar o ID da mensagem somente à oferta correspondente. Cobrir fallback, frase que apenas menciona “lembrete”, oferta anterior aberta e plano que não cria nova oferta.

## P2 — Esclarecimento pendente não expira nem é atribuído ao turno

**Local:** `bot.py`, processamento de `pending_direct_reminder` no início de `process_incoming_batch()` (aproximadamente linhas 1174–1194).

O registro persistido contém `created_at`, mas a leitura não o verifica. Qualquer mensagem futura que o parser interprete como data/hora pode agendar o lembrete, mesmo depois de uma longa mudança de assunto. O estado é global na tabela relacional, sem vínculo com a mensagem de esclarecimento enviada. Uma negativa também não o cancela. Esse risco aumenta porque a pergunta do primeiro turno não está garantida.

**Correção necessária:** estabelecer prazo e contexto de resposta, permitir recusa/cancelamento e não consumir uma data mencionada em outro assunto como confirmação de horário. Testar expiração, resposta desconexa e retomada legítima.

## Reflexão e migrations

O claim com `BEGIN IMMEDIATE` e o índice `UNIQUE(start_conversation_id, end_conversation_id)` eliminam a duplicação simples do mesmo intervalo num banco novo. O teste novo verifica claims e inserts sequenciais; ainda não executa duas instâncias reais em corrida, falha entre gravação do resumo e gravação dos demais efeitos, ou a recuperação de um banco 3.5.3 já migrado com intervalos duplicados. No banco existente, a criação tardia do índice é tentada em `db.py` e qualquer erro é silenciado; duplicatas anteriores impediriam a criação sem sinalização. Recomendável um teste de upgrade com esse estado antes do gate final.

**Decisão:** o P0 da rodada 2 foi resolvido e a suíte local está verde com três integrações reais ignoradas. Permanecem P1 nos fluxos de consentimento e esclarecimento realmente enviados. Corrigir esses caminhos, acrescentar testes ponta a ponta simulados do primeiro turno e repetir a validação antes de liberar operação contínua.
