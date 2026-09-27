---
name: frente-auditoria
description: Frente "auditoria de funcionamento" da Marina — conferir se o que foi entregue (num dia ou numa leva de conversas) funciona de verdade na produção e amarrado com o resto, e se falta deploy de alguma conversa. Use quando o Patrick disser "auditoria de funcionamento", "tá cheio de bug", "ficou coisa desamarrada", "confere o que fizemos ontem" ou "faltou deploy?".
---

# Frente: auditoria de funcionamento

Não é pra criar nada: é provar, com dado da produção, que cada entrega funciona e conversa com as outras.
O roteiro do momento está na seção 7 do `FRENTES_MARINA.md`.

## 1. Antes de tudo: o que está no ar
- `git status` (ignore `data/feedback/*`), `git worktree list`, `git stash list`: trabalho de outra conversa sem commit?
- `git log --since=… --oneline` × `ssh … "cat /root/bots/marina/.deployed"`: commit sem deploy? Se for de outra
  conversa, pergunte ao Patrick se ela terminou antes de subir (`bash scripts/deploy_vps.sh`, sem `--now`).
- Push pro GitHub só com OK dele.

## 2. Uma entrega por vez
Para cada item do roteiro:
1. **O que devia acontecer:** leia o commit e a decisão no plano (PLANO_WEBAPP / PLANO_VOZ / AUDITORIA).
2. **O que aconteceu:** consultas na produção (`root@82.29.60.214`, chave `~/.ssh/marina_vps`, banco
   `/root/bots/marina/marin_memory.db`, `TZ=America/Sao_Paulo` no Python; journal em UTC, local = UTC−3):
   `life_events`, `world_state` (`source_json.reason`), `eventos_pendentes`, `estado_relacional`, `conversas`, log.
   Consultas pontuais: não copie o banco inteiro pro PC.
3. **Amarração:** o módulo novo é visto pelos outros? (mundo ↔ card Agora ↔ Hoje ↔ prompt do chat ↔ fotos ↔ dinheiro.)
   Procure dois lugares contando a mesma coisa de jeitos diferentes.
4. **Veredito** numa linha: funciona / quebrou / não foi exercitada (e como exercitar).

Mostre ao Patrick um quadro visual (show_widget) com os vereditos, não lista longa.

## 3. Achou bug
Registre na seção 5 do `FRENTES_MARINA.md` e siga o método da `frente-bugs` (capturar → camada → teste com o caso
real → correção). Correção grande de outra frente: registre lá em vez de fazer aqui.
Todo commit leva AUDITORIA, PLANO_VOZ e PLANO_WEBAPP no mesmo lote; suíte inteira antes do deploy.
