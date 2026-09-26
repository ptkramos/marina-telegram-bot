---
name: frente-infra
description: Frente "infra" da Marina — VPS, deploy, reinício, logs, banco de produção, migrations, testes, desempenho e chaves de API. Use quando o Patrick falar de servidor, deploy, erro, lentidão, teste, banco ou chave.
---

# Frente: infra

## Regras
- Produção: `root@82.29.60.214` (chave `~/.ssh/marina_vps`), `/root/bots/marina`, `marina.service`,
  banco `marin_memory.db`. **Nunca subir o bot no PC.** Não mexer nos outros bots dele na mesma VPS.
- Deploy: `bash scripts/deploy_vps.sh` — pula o reinício se ele falou com ela há < 5 min; `--now` só com OK dele.
- Segredos: só conferir nomes/tamanhos de chave (`grep -o '^NOME' .env`), nunca imprimir valor.
- Journal em UTC (local = UTC−3). Scripts Python na VPS precisam de `TZ=America/Sao_Paulo`.
- Migrations: `migrations/NNN_nome.sql`, versão = número; a produção já tem a 26 aplicada direto no banco
  (por isso existe 027+). Ao criar uma, atualize os testes que conferem a versão do schema.

## Testes
- `venv/Scripts/python.exe -m unittest discover -s tests` (~20 min). Rode em segundo plano e **não edite código
  enquanto roda** (inspect.getsource e migrations leem arquivos no meio da execução).
- Heredoc no bash estraga `\b`/aspas: use Write com script no scratchpad para edições grandes.

## Comece assim
Leia "4. Infra" em `FRENTES_MARINA.md`. Pendência principal: desempenho do `WorldStateManager.resolve`
(~7 s por resolve na cópia local; perfil com cProfile mostra `sleep_plan` e ~1.300 conexões SQLite por resolve).
