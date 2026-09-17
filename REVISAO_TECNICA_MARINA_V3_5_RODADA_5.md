# Revisão técnica — Marina 3.5, rodada 5

**Data:** 17/09/2026  
**Commit auditado:** `e767e42` (`fix(release): resolve review round 4 findings P0 and P1 for Marina 3.5`)  
**Referência:** `REVISAO_TECNICA_MARINA_V3_5_RODADA_4.md`  
**Gate:** **ainda não aprovar a 3.5 para operação contínua.**

## Resultado

O P0 da rodada 4 foi corrigido: a heurística rejeita “não me lembra...” e perguntas de recordação, e a saída da LLM é validada antes de criar lembretes diretos. O filtro do esclarecimento também rejeita o exemplo “Amanhã vou viajar”. A suíte local passou.

O filtro de resposta de horário ainda aceita frases curtas que introduzem outro assunto, como “Amanhã viajo” e “Amanhã tenho festa”. Se vierem imediatamente após a pergunta de esclarecimento, podem agendar o lembrete anterior para um horário que Patrick não escolheu. Portanto, o P1 de associação de horário permanece parcialmente aberto.

## Validação executada

- `python -m unittest tests.test_audit_fixes_v3_5 -q`: **28 testes, 0 falhas**.
- `python -m unittest discover -s tests -p 'test_*.py' -q`: **157 testes, 0 falhas, 3 ignorados** (integração com LLM real indisponível nesta execução).
- Reexecução direta, sem alterar banco real: `detect_direct_reminder_intent("Nao me lembra da reuniao amanha as 10h")` retornou `False`; a pergunta “Voce lembra de quando eu fui ao medico?” também retornou `False`; o pedido positivo “me lembra de pagar a conta amanha as 10h” retornou `True`.
- Reexecução do filtro temporal com pendência “pagar a conta”: `is_pure_time_specification("Amanha vou viajar", ...)` retornou `False`, mas `is_pure_time_specification("Amanha viajo", ...)` e `is_pure_time_specification("Amanha tenho festa", ...)` retornaram `True`. O parser de data converte ambas para `2026-09-18T14:00:00` nesta execução.
- Não houve envio real ao Telegram nem validação real dos provedores de LLM/voz.

## P1 — Mudança de assunto curta ainda pode confirmar horário de outro lembrete

**Locais:** `planner.py`, `is_pure_time_specification()` (aproximadamente linhas 216–275); `bot.py`, consumo de `pending_direct_reminder` (aproximadamente linhas 1265–1290).

O filtro tenta reconhecer atividades por uma lista de verbos e compromissos. “Vou viajar” é rejeitado, mas “viajo” e “tenho festa” não estão nessa lista. Após retirar os marcadores temporais, a função aceita até duas palavras remanescentes, tratando a frase como resposta de horário. Se a última fala da Marina foi a pergunta de esclarecimento, o bot considera o turno contextual, passa a frase ao parser e cria um lembrete `confirmed` com a descrição pendente. Assim, depois de perguntar quando lembrar de “pagar a conta”, “Amanhã viajo” pode agendar “pagar a conta” para amanhã às 14h.

**Correção necessária:** tratar como confirmação apenas uma expressão temporal isolada ou uma frase que vincule explicitamente o horário ao lembrete pendente. Quando restar uma nova proposição/atividade, pedir confirmação em vez de agendar. Incluir no teste integrado o turno imediatamente seguinte com “Amanhã viajo”, “Amanhã tenho festa” e outras formulações que não estejam em uma lista fixa de verbos.

## P2 — Guarda defensiva de `apply_plan_effects()` usa variável não inicializada

**Local:** `planner.py`, bloco de `direct_reminder` em `apply_plan_effects()` (aproximadamente linhas 599–615).

Quando `neg_check` ou `mem_check` rejeita um plano direto, o código define `plan["direct_reminder"] = None`, mas segue para `if rem_time_iso:`. Nesse ramo, `rem_time_iso` não foi definido; ocorre `UnboundLocalError`, capturado pelo `except` genérico do próprio método e registrado apenas como aviso. O caminho comum pelo `plan_message()` já filtra essas frases, então não reproduz o P0 anterior; contudo, essa segunda guarda não termina de modo limpo e pode ocultar uma falha de chamada alternativa.

**Correção necessária:** interromper o processamento desse lembrete ao rejeitá-lo ou deixar o agendamento inteiramente no ramo `else`. Testar chamada direta de `apply_plan_effects()` com plano negado e verificar ausência de erro, estado pendente e lembrete.

**Decisão:** manter o gate fechado pelo P1 de agendamento sem consentimento de horário. O P0 de negação foi resolvido e a suíte local está verde, mas o caso de mudança de assunto continua reproduzível com frases naturais que os novos testes não cobrem.
