# Revisão técnica — Marina Seltin 3.5.0 a 3.5.3

**Data:** 17/09/2026  
**Estado auditado:** `0071be1` (`feat(release): Marina Seltin v3.5.3 - Session Reflection & Memory Hygiene`)  
**Plano de referência:** `PLANO_MARINA_3_5_MEMORY_RELATIONSHIP_VOICE.md`  
**Gate:** **não aprovar a 3.5 completa para operação contínua ainda.**

## Resumo

As quatro etapas foram implementadas em módulos, migrations e testes separados. A arquitetura de memória 3.5.0 mantém o hardening já validado; as migrations 006 e 007 são aplicadas; o roteamento de voz é determinístico; lembretes confirmados têm um job separado da chance estatística de proatividade.

A revisão encontrou falhas reproduzíveis nas etapas novas. Uma memória pode ganhar confiança ao envelhecer; a reflexão periódica reprocessa a mesma sessão; e dois jobs simultâneos podem enviar o mesmo lembrete. O fluxo de ofertas também não comprova que o usuário viu a pergunta antes de uma resposta genérica ser interpretada como consentimento. Esses pontos atingem diretamente a definição de pronto do plano.

Esta revisão é **diagnóstico e plano de correção**. Nenhum código, banco real, credencial, job ou serviço foi alterado. As exclusões locais já existentes dos três relatórios anteriores foram preservadas.

## Validação executada

Os fontes, migrations e testes foram copiados para `scratch/review_353`, sem `.env` nem `marin_memory.db`. O Python do `venv` existente rodou com configuração fictícia, bloqueio de conexão externa e SQLite descartável.

- `compileall`: passou.
- `unittest discover`: **129 testes descobertos; 126 passaram, 3 foram ignorados (integração LLM real), 0 falhas, 0 erros**, em 15,378 s.
- `healthcheck.py`, na cópia isolada: **28 PASS, 0 WARN, 0 FAIL**.
- Reproduções independentes com SQLite real descartável: `scratch/review_353/repros.py`, `repros_more.py` e respectivos logs.
- Não foram executados nesta rodada envio real ao Telegram, síntese de áudio pelos provedores ou testes novos com LLM real. Os três testes LLM ignorados já haviam sido executados com sucesso na validação anterior da 3.5.0; isso não valida as funcionalidades 3.5.1–3.5.3.

## P0.1 — Higiene aumenta a confiança de uma memória incerta

**Local:** `db.py`, `aplicar_confidence_decay()`, cálculo de `novo_conf` (aprox. linhas 1330–1351).  
**Plano:** §§ 9, 77, 79 e definição de pronto da 3.5.3.

O cálculo usa `1.0 - ciclos * 0.10/0.05` como base, sem respeitar a confiança já persistida. Fatos `stable` ou `core` ainda recebem pisos absolutos de 0,85. Assim, um ciclo de manutenção pode transformar uma memória já incerta em aparente certeza.

**Reprodução:** fato `volatile`, criado há 25 dias, `confidence=0.20`, `last_confirmed_at=NULL`. Depois de `MemoryHygieneService.run_hygiene_cycle()`, o banco registrou **`confidence=0.90`**; `needs_reconfirmation` permaneceu 0. O log isolado contém `DECAY_LOW_CONFIDENCE 0.2 0.9`.

**Correção:** usar apenas uma redução monotônica a partir do valor atual, limitada por um piso que nunca o ultrapasse; `stable/core` devem sofrer pouca ou nenhuma redução, sem aumento automático. A confirmação explícita deve continuar sendo o único caminho para elevar confiança. Testar `confidence_after <= confidence_before` para todos os tiers/volatilidades, inclusive valores iniciais abaixo do piso.

## P1.1 — A mesma sessão é refletida repetidamente

**Local:** `session_reflector.py`, `check_and_trigger_reflection()` (aprox. linhas 205–232); `db.py`, `get_mensagens_sessao()` (aprox. linha 1467).  
**Plano:** §§ 73–77, 98 e definição de pronto da 3.5.3.

O job verifica a idade da última mensagem, mas não registra um cursor ou intervalo de sessão já processado. Após uma hora de inatividade, a consulta continua devolvendo as mesmas últimas 30 mensagens a cada execução. Cada rodada chama a LLM e pode criar novamente resumo, open loops e momentos.

**Reprodução:** quatro mensagens antigas, resposta do Reflector controlada. Duas chamadas sucessivas a `check_and_trigger_reflection()` retornaram resultado e deixaram **2 resumos e 2 open loops idênticos**. Log: `REFLECTION_REPLAY True True 2 2`.

**Correção:** persistir o último ID refletido, selecionar apenas sessões novas e avançar o cursor após aplicação bem-sucedida. Usar uma chave de sessão/intervalo para impedir duplicatas em retry, reinício e jobs concorrentes. Em falha da LLM, não gravar um resumo genérico nem avançar o cursor como se a sessão tivesse sido refletida. Testar execução repetida, reinício e falha/retry.

## P1.2 — Lembrete pode ser enviado duas vezes

**Local:** `bot.py`, `reminders_routine()` (aprox. linhas 1712–1729); `db.py`, `get_due_reminders()` e `marcar_reminder_enviado()` (aprox. linhas 1235–1262).  
**Plano:** §§ 42–45, 89, 112.

O job lê todos os lembretes `confirmed`, envia e só depois muda o estado para `sent`. Duas execuções que leem antes da primeira atualização enviam o mesmo ID. A consulta e a marcação não formam uma reserva atômica. Reinício/crash entre envio e marcação também pode causar reenvio; exatamente uma entrega externa exige uma política explícita de idempotência ou reconciliação.

**Reprodução:** duas chamadas simultâneas da rotina, com transporte Telegram simulado e SQLite real: **2 envios do mesmo ID**, estado final `sent`. Log: `REMINDER_CONCURRENT_SENDS 1 2 sent`.

**Correção:** reservar/claimar cada lembrete atomicamente antes do envio, com estado intermediário e trava/lease de recuperação. Restringir concorrência do job no scheduler e definir o comportamento após falha de envio ou crash. Não marcar `sent` quando o envio falhar. Testar duas instâncias/jobs concorrentes e reinício durante a entrega.

## P1.3 — Oferta não é comprovadamente mostrada; “sim” pode confirmar outro assunto

**Locais:** `planner.py`, `apply_plan_effects()` (aprox. linhas 356–374); `bot.py`, `process_incoming_batch()` (aprox. linhas 1177–1188) e geração da resposta (aprox. linhas 1280–1320); `db.py`, `get_ultimo_reminder_ofertado()`.
**Plano:** §§ 29, 35–40, 89–90, 103 e definição de pronto da 3.5.1.

O Planner grava `status='offered'` após gerar a resposta, independentemente de o texto enviado conter a oferta. O sinal `should_offer_reminder` não é usado para inserir uma pergunta obrigatória no payload da resposta nem para verificar o texto entregue. Na próxima mensagem, qualquer “sim” dentro de 60 minutos confirma o último registro `offered`, sem associação à mensagem de oferta ou ao turno respondido. Além disso, aplicar o mesmo plano duas vezes cria duas ofertas: o banco não verifica se o evento já tem uma em `offered/confirmed/declined`.

**Evidência:** duas aplicações do mesmo plano criaram **2 ofertas** (`REPEATED_OFFER_COUNT 2`). Para uma oferta pendente, `parse_confirmation_response('sim')` retorna `confirm` mesmo sem contexto de resposta (`UNRELATED_YES_ACTION 3 confirm`). A análise do fluxo mostra que a resposta pode ser enviada sem a pergunta, embora o banco registre uma oferta.

**Correção:** entregar uma oferta explícita ao usuário e registrar o ID da mensagem Telegram/turno somente após envio bem-sucedido. Confirmar ou recusar apenas uma resposta atribuível a essa oferta; em caso ambíguo, pedir esclarecimento. Impedir nova oferta para o mesmo evento quando há `offered`, `confirmed` ou `declined` (exceto novo pedido direto). Testar mensagem efetivamente enviada, “sim” em outro assunto, oferta repetida e recusa seguida de nova interação.

## P1.4 — Reflexão pode resolver um loop que não foi apresentado à LLM

**Local:** `session_reflector.py`, `apply_reflection()` (aprox. linhas 172–185).  
**Plano:** § 27 e § 75.

`reflect_session()` mostra no máximo cinco loops ativos, mas `apply_reflection()` aceita diretamente qualquer `loop_id` retornado, consultando apenas se o ID existe e está aberto. Uma resposta alucinada ou malformada pode resolver outro assunto pendente.

**Reprodução:** resposta controlada com um ID aberto que não constava da lista apresentada; `apply_reflection()` marcou o loop `resolved` (`REFLECTOR_UNPRESENTED_ID_RESOLVED 1 resolved`).

**Correção:** passar ao aplicador o allowlist de IDs efetivamente mostrados; verificar tipo inteiro positivo, estado e pertencimento antes de mutar. Resolver por texto apenas quando houver correspondência única e verificável. Testar ID inexistente, ID existente fora da lista e duas correspondências ambíguas.

## P1.5 — Pedido direto sem horário claro pode virar lembrete em uma hora

**Local:** `planner.py`, `apply_plan_effects()` (aprox. linha 382), `parse_iso_or_relative_datetime()` (aprox. linhas 139–141).  
**Plano:** §§ 38–40.

O caminho `direct_reminder` chama o parser com `default_offset_hours=1`. Uma expressão temporal não reconhecida, porém não vazia, gera um horário uma hora à frente. Isso substitui a pergunta “quando?” exigida pelo plano e pode disparar um lembrete em momento que Patrick não escolheu.

**Correção:** exigir horário suficiente e futuro para criar `confirmed`. Se não houver data/hora reconhecível, manter apenas uma proposta pendente de esclarecimento, sem agendamento. Testar expressões vagas e malformadas, além de data no passado.

## P2.1 — Open loop sem `next_check_after` fica pronto imediatamente

**Locais:** `db.py`, `get_open_loops_para_checkin()` (aprox. linhas 1037–1052); `planner.py`, criação de loop com `next_check_hint` opcional.  
**Plano:** §§ 25, 28 e 104.

A consulta usa `next_check_after IS NULL OR next_check_after <= now`. Quando o Planner não fornece hint, grava `NULL`; o loop recém-criado fica imediatamente elegível para proatividade. Reprodução: `NULL_CHECK_IMMEDIATELY_READY 1 [1]`.

**Correção:** definir uma primeira data de check-in coerente com o contexto (por exemplo, após 1–2 dias para espera sem prazo), e exigir data vencida na consulta. Evitar que `NULL` signifique “perguntar agora”.

## P2.2 — Flags de Reflection/Hygiene foram ativadas por padrão antes do gate

**Local:** `config.py` (aprox. linhas 100–101) e `.env.example` (aprox. linhas 75–76).  
**Plano:** § 85 e § 116.

O plano pede `SESSION_REFLECTION_ENABLED=False` e `MEMORY_HYGIENE_ENABLED=False` até a validação. O código e o exemplo usam `true`. Isso agenda automaticamente os dois jobs, inclusive os caminhos de confiança e duplicação reproduzidos acima.

**Correção:** deixar ambas desligadas por padrão e ativá-las somente após o gate de regressão e observação da memória 3.5.0. Para uma instalação já configurada com `true`, corrigir explicitamente a configuração antes de executar o bot.

## Cobertura e próximos testes

Os testes atuais cobrem bem contratos isolados: migrations, ciclo simples de reminder, parse de aceite/recusa, roteador de voz, fallback entre provedores, decaimento de memória partindo de confiança 1.0 e aplicação única de reflection. Não cobrem as invariantes entre jobs, mensagens efetivamente entregues e respostas atribuídas a uma oferta.

Adicionar testes permanentes para cada reprodução acima, além dos cenários integrados dos §§ 94–95 do plano. O teste de voz atual simula provedores; ainda falta verificar os dois Voice IDs configurados, áudio realmente gerado e comportamento de fallback na instalação alvo. Nenhum teste real de entrega Telegram ou de voz foi feito nesta revisão.

Ordem recomendada: (1) impedir aumento de confiança; (2) cursor/idempotência da reflexão; (3) reserva do reminder e política de retry; (4) vínculo verificável entre oferta e aceite, com deduplicação; (5) allowlist de loops resolvidos; (6) recusar horário implícito e atrasar check-ins sem data; (7) refazer a suíte e os testes integrados. Ao final, repetir healthcheck, migration 4→7 em cópia de banco antigo e uma execução supervisionada com os serviços reais.

**Decisão:** manter a 3.5.3 sem aprovação para uso contínuo até corrigir os P0/P1. A suíte verde comprova os casos nela escritos; as reproduções independentes mostram que ainda faltam condições centrais do plano.
