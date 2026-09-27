---
name: frente-bugs
description: Frente "bugs" da Marina — algo deu errado no uso real (ela disse onde está e não estava, fez o que não devia, mensagem estranha, estado do mundo incoerente, app mostrando errado). Use quando o Patrick disser "peguei um bug", "deu problema", "ela falou X mas estava Y", mandar print de erro, ou abrir com "bora na frente de bugs".
---

# Frente: bugs

Bug do uso real some rápido: o estado do mundo muda, o card da aba Agora troca, o log gira. **Primeiro capture,
depois pense.**

## 1. Capture (antes de qualquer coisa)
Salve no scratchpad, da produção (`root@82.29.60.214`, chave `~/.ssh/marina_vps`, `/root/bots/marina`):
- Conversa: `sqlite3 marin_memory.db "SELECT id,timestamp,role,content FROM conversas WHERE timestamp >= '…'"`
  (timestamp em hora local).
- Mundo: `SELECT id,observed_at,location_place_id,activity,current_plan_json,source_json FROM world_state
  WHERE observed_at BETWEEN '…' AND '…'` — `source_json.reason` diz de onde veio o estado.
- Agenda: `SELECT * FROM eventos_pendentes ORDER BY id DESC LIMIT 10`.
- Log: `journalctl -u marina --since "… UTC" --until "…" --no-pager | grep -v "apscheduler\|getUpdates"`
  (**journal em UTC**, local = UTC−3). Linhas úteis: `AVAILABILITY_DECISION`, `ritual.`, `turn.yielded`.
- Recalcular o mundo numa hora: `TZ=America/Sao_Paulo venv/bin/python -c "…"` com `db.DatabaseManager()`
  (ex.: `commute.Commute(db).leg_at(datetime(...))`).

## 2. Diagnostique em três camadas
1. **Mundo:** o estado (world_state / agenda / trajeto) estava certo naquela hora?
2. **Prompt:** o que o `world_context.py` disse pra ela? (`certainty_map`, linhas "FATO CANÔNICO"; `binding` só vale
   pra compromisso/plano/transição anunciada.)
3. **Fala:** o modelo ignorou o fato? Histórico da conversa puxando pro contrário?
Diga ao Patrick em 2–3 linhas qual camada falhou, com a hora e a prova (a linha do banco/log).

## 3. Corrija
- Teste que reproduz o caso real primeiro (dados do caso, hora fixa), depois a correção.
- Suíte inteira em segundo plano (~20 min, não edite enquanto roda), relatórios no mesmo commit, deploy
  (`bash scripts/deploy_vps.sh`, sem `--now` se ele estiver falando com ela).
- Se a correção for grande e da alçada de outra frente, registre lá no `FRENTES_MARINA.md` em vez de fazer aqui.

## Onde fica o registro
Seção "5. Bugs" do `FRENTES_MARINA.md`: um item por bug, com hora, o que ele viu, a camada e o estado.
