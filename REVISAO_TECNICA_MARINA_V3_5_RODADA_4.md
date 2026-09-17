# Revisão técnica — Marina 3.5, rodada 4

**Data:** 17/09/2026  
**Commit auditado:** `e09911b` (`fix(release): resolve review round 3 findings for Marina 3.5`)  
**Referência:** `REVISAO_TECNICA_MARINA_V3_5_RODADA_3.md`  
**Gate:** **não aprovar a 3.5 para operação contínua ainda.**

## Resultado

Os problemas específicos da rodada 3 avançaram: o Planner antecipa a necessidade de perguntar o horário, o bot acrescenta a pergunta quando a LLM a omite, guarda o ID da oferta deste turno e dá prazo de 30 minutos ao esclarecimento pendente. A migration remove intervalos de resumo duplicados antes de criar o índice único. Os 23 testes específicos e a suíte completa passaram.

A nova heurística de pedido direto, porém, introduziu um risco de consentimento: reconhece frases negadas e perguntas sobre lembranças passadas como ordens para criar lembrete. O esclarecimento pendente também continua capaz de consumir uma data de uma mudança de assunto no turno imediatamente seguinte.

## Validação executada

- `python -m unittest tests.test_audit_fixes_v3_5 -q`: **23 testes, 0 falhas**.
- `python -m unittest discover -s tests -p 'test_*.py' -q`: **152 testes, 0 falhas, 3 ignorados**. Os ignorados dependem da LLM real; não houve validação bem-sucedida do provedor nesta rodada.
- Reprodução direta da heurística, sem LLM e sem alterar banco real: `plan_heuristics("Voce lembra de quando eu fui ao medico?")` devolveu `intent=direct_reminder` e `is_direct_reminder=True`; `plan_heuristics("Nao me lembra da reuniao amanha as 10h")` devolveu `intent=direct_reminder`, `is_direct_reminder=True`, `remind_at=2026-09-18T10:00:00`. O caminho de `apply_plan_effects()` cria lembrete `confirmed` quando recebe esse plano com horário futuro.
- Reprodução do parser: `parse_iso_or_relative_datetime("Amanha vou viajar", default_offset_hours=None)` devolveu um horário futuro (`2026-09-18T14:00:00` nesta execução).
- Não houve entrega real ao Telegram nem teste real de voz/LLM.

## P0 — Frase negada pode criar lembrete confirmado

**Locais:** `planner.py`, `plan_heuristics()` (aproximadamente linhas 252–279) e `apply_plan_effects()` (bloco `direct_reminder`, aproximadamente linhas 453–487).

A expressão `re.search(r"\b(?:me\s+)?(?:lembra|avisa)...", t)` busca em qualquer posição, não exige que seja pedido afirmativo e não considera negação. Em “Não me lembra da reunião amanhã às 10h”, captura “lembra da reunião amanhã às 10h”, obtém um horário futuro e retorna `direct_reminder=True`. O caminho de aplicação interpreta pedido direto como consentimento implícito e cria lembrete `confirmed`. A mesma expressão classifica “Você lembra de quando eu fui ao médico?” como pedido de lembrete, embora seja uma pergunta sobre memória passada. A heurística roda antes da LLM, que não tem oportunidade de corrigir essa intenção.

**Correção necessária:** restringir a detecção a formas imperativas/solicitações positivas, rejeitar negações e perguntas metalinguísticas ou de memória, e validar a intenção antes de qualquer efeito persistente. Testar frases afirmativas, negativas e perguntas, incluindo “não me lembra”, “você lembra de...” e “lembra quando...”. Um horário válido não deve superar uma negação.

## P1 — Data de outro assunto pode completar lembrete pendente

**Locais:** `bot.py`, processamento de `pending_direct_reminder` (aproximadamente linhas 1242–1283); `planner.py`, `parse_iso_or_relative_datetime()`.

O bot considera a próxima mensagem como contexto do esclarecimento se a última fala da Marina tiver o ID da pergunta. Ele passa **todo o texto** ao parser e agenda o lembrete sempre que houver uma data futura, sem exigir que a mensagem responda à pergunta. Por exemplo, depois de “Quando você quer que eu te lembre de pagar a conta?”, a resposta “Amanhã vou viajar” pode agendar “pagar a conta” para amanhã às 14h. A regra de descarte por mudança de assunto só roda quando o parser não reconhece data. O teste novo para resposta desconexa usa um turno *não consecutivo*; não cobre esse caso.

**Correção necessária:** reconhecer uma resposta de horário como tal, em vez de inferir pelo simples aparecimento de marcador temporal. Quando a próxima fala menciona outra atividade, pedir confirmação ou descartar a pendência sem agendar. Testar explicitamente mudança de assunto com data/hora no turno seguinte.

## Observações de cobertura

A verificação de oferta agora exige estrutura interrogativa e corrige o caso declarativo “Já anotei um lembrete”. O ID registrado vem de `offered_reminder_id` no plano, evitando associar a resposta à última oferta global. O teste de upgrade com duplicatas também passa. Ainda não há validação ponta a ponta com Telegram e LLM reais, nem teste de corrida real entre duas instâncias de reflexão ou envio de lembretes. Essas limitações não explicam os dois achados acima, que foram observados no código e nas reproduções locais.

**Decisão:** manter o gate fechado. Corrigir primeiro o reconhecimento de pedidos diretos negados ou interrogativos; depois impedir que uma data de outro assunto complete uma pendência. Repetir a suíte e incluir esses dois casos como regressão permanente.
