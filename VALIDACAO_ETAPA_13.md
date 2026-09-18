# Release 3.6.6 · etapa 13 — implementação pronta para validação externa

Camera World Continuity (3.6.6) foi implementada conforme
[HANDOFF_ETAPA_13_CAMERA_WORLD_3_6_6.md](HANDOFF_ETAPA_13_CAMERA_WORLD_3_6_6.md).
A suíte isolada **não** deve ser executada pelo Codex; o Gemini/Antigravity
roda a validação e grava o artefato. Para reproduzir na raiz do repositório:

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage13_validation.py
```

O relatório é escrito em `data/camera_world_validation.v366.json`.

## O que entrou

- `camera_world.py`: projeção somente leitura (`CameraWorldBuilder.build`) a
  partir de `WorldStateRepository.latest()` e/ou `CalendarWorld.current()`,
  sem chamar `WorldStateManager.resolve()`.
- Flag `CAMERA_WORLD_CONTINUITY_ENABLED=false` (exige `LIVING_WORLD_ENABLED`).
- Diretor visual recebe restrições estruturadas; tags conflitantes (praia,
  estúdio, sol diurno à noite etc.) são rejeitadas em favor de um prompt seguro.
- `sd_client.generate_photo_with_context()` devolve metadados por chamada;
  `generate_photo()` legado não grava mais `camera_last_state`.
- `bot.py` só chama `record_photo_generation` após `send_photo` com
  `message_id`; avatar e falhas não alteram continuidade conversacional.
- `CameraState` ganhou `place_key` / `world_snapshot_id` com `from_dict`
  compatível com estados antigos; “mais uma” exige mesmo local.

## Critérios a validar no artefato

- apartamento atual + pedido de praia não produz praia nem move `world_state`;
- aula atual prevalece sobre rotina;
- snapshot velho não afirma localização atual;
- noite não vira sol diurno; clima ausente/vencido não é inventado;
- “mais uma” preserva look só na mesma sessão/local;
- falha de geração ou `send_photo` não atualiza `camera_last_state`;
- avatar não altera continuidade; envio ok registra só a foto transmitida.

Ativação futura: `CAMERA_WORLD_CONTINUITY_ENABLED=true` exige
`LIVING_WORLD_ENABLED=true`. A flag permanece desligada por padrão até o
aceite externo.
