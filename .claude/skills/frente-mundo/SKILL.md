---
name: frente-mundo
description: Frente "mundo e agenda" da Marina — a vida dela (rotina, agenda, saídas, vontade, corpo, fome, saúde, sono, tesão, mídia, amigos, dinheiro dela). Use quando o Patrick disser "frente do mundo", "agenda", "agenda reativa", "etapa 1", "unhas", ou falar do que ela está fazendo/onde está/o que comeu.
---

# Frente: mundo e agenda

Regra de ouro do Patrick: **tudo o que ela faz acontece de verdade e vira história** (acontecimento em
`life_events`, efeito no corpo/saldo/card) — nada de atividade genérica nem teletransporte.

## Comece assim
1. Leia a seção "1. Mundo e agenda" de `FRENTES_MARINA.md` (o que falta, em ordem).
2. Leia no `PLANO_WEBAPP_MARINA.md` as seções citadas (busque por "Agenda única", "Etapa 1", "Tudo pode ser
   interrompido").
3. Confirme com o Patrick o item do dia em modo de questionamento (AskUserQuestion + mockup quando for texto de card).

## Como o mundo funciona (resumo)
- `world_state.WorldStateManager.resolve` (um por vez, trava no processo): compromisso confirmado → plano explícito
  → trajeto (`commute.leg_at`) → transição anunciada (refeição, banho) → consequência → **vontade**
  (`vontade.Vontade.talvez`, quando ela está livre) → preparo (`agenda.prep_activity`) → rotina/tempo livre.
- **Agenda única:** tudo que tem ir-e-voltar vira item em `eventos_pendentes` via `vontade.Vontade.agendar`
  (metadata: origem, tipo, decidido_em, modo, ida_min). `agenda.Agenda.etapas` monta Se arrumando → A caminho →
  Lá → Voltando; `commute._legs_agenda_viva` faz os trajetos; `consumo` o que ela consome (catálogo real).
- Planejados diários: `academia.py` (academia e passeio do Milo, decididos uma vez e guardados).
- Card da aba Agora: `agenda.card` (etapas) ou `agenda.card_casa` (em casa: blocos do `tempo_livre`).
- Disponibilidade no chat: perfis em `response_availability.py` (mapear toda atividade nova!), textos de celular
  em `webapp_server.CELULAR_POR_ATIVIDADE`, bateria social em `social_battery.py`.

## Cuidados
- Atividade nova: mapeie disponibilidade, `meals._fora` (em casa ou não), card e prompt (`world_context.py`).
- Lugares reais e canônicos (ele exige): lojas do `webapp/catalogo.json` (área "bf" = Botafogo), migrations pra lugar fixo.
- Testes do mundo mockam `academia.*.plano`, `meals.Meals.day_plan`, `sleep_plan.SleepPlan.in_bed`; bootstrap limpo
  (`clean_canonical_start_done`) e `SocialDay._floor` controlam o que pode virar acontecimento.
- Simular um dia na cópia da produção é lento (~7 s por resolve); prefira simular só o módulo novo.
- Fechar: relatórios no mesmo commit, deploy com `scripts/deploy_vps.sh`, depois `passagem-de-bastao`.
