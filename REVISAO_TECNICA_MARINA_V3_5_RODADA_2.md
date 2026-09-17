# Revisão técnica — Marina 3.5, rodada 2

**Data:** 17/09/2026  
**Commit auditado:** `0e157ef` (`fix(release): resolve technical review findings P0.1 to P2.2 for Marina 3.5`)  
**Referência:** `REVISAO_TECNICA_MARINA_V3_5_COMPLETA.md`  
**Gate:** **ainda não aprovar a 3.5 completa para operação contínua.**

## Resultado

A correção eliminou o aumento automático da confiança, passou a reservar lembretes antes do envio, impediu o replay sequencial da reflexão, restringiu os loops que a reflexão pode resolver, removeu o horário padrão de uma hora para lembretes diretos, adiou o primeiro check-in de open loops e desligou Reflection/Hygiene por padrão. Os 11 testes novos passaram.

Ainda há um bloqueio direto no recebimento de mensagens após uma oferta de lembrete e lacunas nos fluxos de oferta e reflexão concorrente. Portanto, os testes novos não fecham o gate anterior.

## Validação executada

- `python -m unittest tests.test_audit_fixes_v3_5 -v`: **11 testes, 0 falhas**. Os testes usam SQLite temporário e mocks.
- `python -m unittest discover -s tests -p 'test_*.py' -q`: **140 testes, 2 falhas**, ambas na classe de integração com LLM real (`test_real_fact_extraction`, `test_contradiction_detection`). O log registra `Connection error` nas chamadas ao provedor. Essas falhas não demonstram regressão funcional do commit, mas impedem declarar a suíte completa verde nesta execução. O teste de conversa casual também recebeu erro de conexão e passou porque o retorno vazio satisfez a asserção; ele não valida a LLM nesta rodada.
- Revisão estática do diff `0071be1..0e157ef` e dos caminhos integrados em `bot.py`, `planner.py`, `reminder_service.py`, `session_reflector.py`, `db.py` e migrations. Não foram feitos envios reais ao Telegram, síntese real de voz ou chamadas LLM bem-sucedidas.

## P0 — Uma oferta pendente interrompe o processamento da próxima mensagem

**Local:** `bot.py:1183` e `bot.py:1286`.

`process_incoming_batch()` usa `reply_to_id` na verificação de atribuição da oferta antes da primeira atribuição da variável local, que só ocorre aproximadamente 100 linhas depois. Quando `get_last_offered_reminder()` devolve uma oferta, a expressão avalia `reply_to_id` e lança `UnboundLocalError`. Assim, a própria mensagem em que Patrick tentaria aceitar ou recusar o lembrete não chega ao restante do processamento. Os 11 testes novos exercitam o parser separadamente, mas não chamam esse caminho integrado do bot.

**Correção necessária:** obter o ID da mensagem citada logo no início do processamento, por exemplo a partir de `update.message.reply_to_message.message_id`, e usar esse ID para comparar com `offer_message_id`. `reply_to_id` como está definido mais adiante decide, aleatoriamente, se a *resposta da Marina* citará a mensagem do usuário; mesmo antecipar essa atribuição não resolveria a associação ao aceite. Criar teste integrado para uma oferta pendente com resposta direta, resposta no turno seguinte e mensagem sem relação.

## P1 — P1.3 continua parcial: oferta registrada sem prova de que a pergunta foi entregue

**Locais:** `planner.py:368`, `bot.py:1303` e `bot.py:1451`.

O Planner ainda persiste a oferta antes do envio. O bot adiciona uma instrução ao prompt pedindo que a LLM formule a pergunta, mas não verifica a resposta final nem insere uma pergunta determinística quando a LLM omite a oferta ou falha. Depois, associa o ID da mensagem enviada à última oferta em aberto, mesmo que esse texto seja apenas a resposta de fallback. O registro `offered` e `offer_message_id` podem, portanto, afirmar que uma oferta foi apresentada quando Patrick não a viu. O teste novo verifica deduplicação e o parser, mas não o conteúdo realmente enviado nem a associação entre o lembrete criado neste turno e a mensagem entregue.

Há ainda confirmações genéricas sem contexto aceitas pelo parser: `pode ser`, `por favor`, `quero sim`, `fechou` e `manda bala` retornam `confirm` mesmo com `has_context=False` (`reminder_service.py`, bloco `aceite_explicito`/`aceite_generico`). Isso mantém a possibilidade de confirmar um lembrete por resposta a outro assunto.

**Correção necessária:** criar uma oferta vinculada ao ID retornado pelo Planner e garantir a pergunta no texto/áudio que será enviado; só marcar a oferta como apresentada após envio bem-sucedido. Para respostas genéricas, exigir vínculo com a mensagem da oferta ou pedir esclarecimento. Testar fallback da LLM, resposta sem pergunta, envio dividido em balões e mudança de assunto.

## P1 — P1.1 continua parcial: reflexão concorrente pode duplicar efeitos

**Locais:** `session_reflector.py:139–166` e `session_reflector.py:250–270`; schema de `resumos_conversa` em `migrations/002_smart_memory.sql`.

O cursor impede que uma segunda execução **sequencial** processe a mesma sessão. Contudo, duas execuções podem ler o mesmo cursor e as mesmas mensagens antes de uma delas avançá-lo. A verificação de existência do intervalo e a gravação do resumo/loops ocorrem em transações separadas. O schema não possui restrição `UNIQUE(start_conversation_id, end_conversation_id)`. Assim, duas execuções simultâneas podem passar pela verificação e aplicar os mesmos efeitos. O teste novo cobre apenas chamadas sequenciais.

**Correção necessária:** reservar o intervalo de reflexão de modo atômico e impor uma chave única persistente antes de aplicar os demais efeitos, com tratamento de retry após falha. Testar dois reflectors/instâncias concorrentes sobre o mesmo SQLite e verificar um único resumo e conjunto de loops.

## P2 — Pedido direto sem horário não solicita esclarecimento

**Local:** `planner.py:396–419`.

O agendamento implícito de `+1h` foi removido corretamente. Quando a data é vaga ou inválida, porém, o código apenas registra uma linha de log. Não persiste uma proposta pendente nem assegura que a resposta da Marina pergunte “quando?”, como exigia o plano. O teste novo confirma somente que não há lembrete `confirmed`.

**Correção necessária:** encaminhar uma instrução explícita de esclarecimento à resposta e, se o fluxo precisar sobreviver ao próximo turno, persistir o estado pendente. Testar a resposta enviada e a conclusão após Patrick fornecer a hora.

## Observações sobre as correções aprováveis

- **P0.1:** o decaimento parte da confiança atual e não a eleva. Há marcador `last_decay_at` e teste com confiança inicial baixa.
- **P1.2:** a reserva `BEGIN IMMEDIATE` e o estado `sending` eliminam a duplicação por duas leituras simultâneas enquanto o lease está válido. Falha de envio libera a reserva. Continua existindo a janela inevitável entre sucesso no Telegram e marcação local como `sent`: após crash, o lease pode reenviar. Essa política de entrega ao menos uma vez precisa ser assumida explicitamente ou reconciliada; o código atual não garante entrega exatamente uma vez.
- **P1.4:** a allowlist de IDs apresentados à LLM passou a ser aplicada antes de resolver open loops.
- **P1.5:** pedidos diretos com data não reconhecida ou no passado deixam de criar lembrete confirmado.
- **P2.1/P2.2:** check-in sem data começa após 24 horas, e Reflection/Hygiene estão `false` por padrão no código e no `.env.example`. Uma instalação que já tenha `true` no `.env` ainda precisa ser verificada antes da ativação.

**Decisão:** corrigir primeiro o `UnboundLocalError` e concluir o vínculo verificável entre oferta, mensagem enviada e aceite. Depois, tornar a reflexão segura sob concorrência, cobrir os fluxos integrados e repetir a suíte. O commit representa progresso substancial, mas ainda não fecha a revisão.
