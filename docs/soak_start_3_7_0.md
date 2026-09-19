# Iniciar o soak da Marina 3.7.0

Abra `run_local.bat` e mantenha a janela aberta. Converse normalmente no Telegram.
O inicializador confere os 37 recursos combinados, o banco e as dependências.
Uma segunda abertura não inicia outro bot concorrente. Não é necessário reinstalar nada.

Os recursos de conversa, personalidade, mundo, calendário, vida acadêmica, memória,
privacidade, iniciativa, lembretes, ritmo, disponibilidade, visão e dois perfis de voz
estão ativados. A política de sono foi preservada (`CRITICAL_WAKE_POLICY_ENABLED=false`).
O editor remoto de código continua desativado, conforme a configuração anterior.

## Exceção aceita para este soak

O usuário adiou expressamente a recuperação da GPU da Novita em 18/09/2026.
`PHOTO_PROVIDER_MAINTENANCE=true` impede tentativas de ligar a GPU defeituosa.
Pedidos de foto recebem uma resposta contextual da LLM explicando que não foi
possível enviar a imagem; avatar também usa a desculpa dinâmica. Se a LLM falhar,
existe uma resposta de reserva. Nenhuma foto inexistente é registrada como enviada.
Receber e compreender fotos do usuário continua ativado.

Depois de recuperar e validar a GPU, definir `PHOTO_PROVIDER_MAINTENANCE=false`
restaura o fluxo de geração existente. Nenhum modelo ou perfil visual foi trocado.

## Evidências da preparação

- `validation_soak_full_final.log`: suíte final isolada.
- `validation_soak_regressions.log`: 17 regressões independentes aprovadas.
- `validation_soak_startup.log`: saúde local e cinco rotinas registradas.
- `validation_soak_production.log`: disponibilidade, fila e telemetria com configuração real em cópia do banco.
- `data/soak_live_gate.v370.json`: Telegram somente leitura, conversa, duas vozes e desculpa dinâmica aprovados; GPU como indisponibilidade aceita.
- `data/prompt_authority_validation.v370.json`: auditoria de autoridade dos prompts.
- `dist/marina-validation-clean.zip`: pacote sem credenciais, banco, logs ou mídia privada.

Foi criado backup local do banco e da configuração em
`backups/pre_soak_370_20260918_175840/` antes das alterações de configuração.
Testes de conversa e inicialização usaram bancos descartáveis; nenhum teste enviou
mensagens ao Telegram. O soak real começa com a abertura do bot e o uso normal;
esta preparação não equivale a sete dias de soak concluídos.

## Se precisar interromper

Feche a janela do inicializador. Para retirar apenas a latência humana,
desative conjuntamente `RESPONSE_AVAILABILITY_ENABLED`,
`HUMAN_REPLY_LATENCY_ENABLED` e `PENDING_CONVERSATION_BATCHING_ENABLED` no `.env`.
A rotina de fila continua escoando mensagens pendentes quando o bot estiver aberto.
