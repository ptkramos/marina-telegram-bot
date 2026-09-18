# Handoff de implementação — etapa 13 · release 3.6.6

Este arquivo é um roteiro para outro agente implementar **Camera World
Continuity**. A etapa 12 · release 3.6.5 foi validada pelo Gemini com 291
testes; a 3.6.6 ainda não foi implementada. O usuário prefere que o agente
implemente o código e entregue a suíte ao Gemini/Antigravity para execução.
Não rodar a suíte no Codex. Preservar as decisões já validadas nas releases
3.6.0–3.6.5, especialmente Calendar/Events como fonte de compromissos,
KnowledgePrivacy para divulgação e o WorldState como fonte do estado atual.

## Resultado esperado

Uma foto solicitada agora deve refletir o local, a atividade e o horário
**observados** da Marina. Clima só entra quando há observação válida e efeito
visual pertinente. Roupa e cômodo entram quando há evidência atual. Um pedido
de “mais uma” pode repetir o look da foto anterior dentro da sessão, desde que
o estado do mundo ainda seja compatível. Gerar ou enviar foto jamais muda
silenciosamente o `world_state` nem cria compromisso ou transição de lugar.

## Pontos reais de integração

- [world_state.py](world_state.py): `WorldStateManager.resolve()` pode criar um
  novo snapshot. **Não chamá-lo da câmera** para obter contexto; a câmera deve
  ser uma projeção somente de leitura. Usar `WorldStateRepository.latest()` em
  [world_repository.py](world_repository.py), com verificação de data/frescor.
- [calendar_world.py](calendar_world.py): `CalendarWorld.current()` fornece o
  compromisso confirmado atual, incluindo aula quando o Academic Life está
  habilitado. Ele tem precedência sobre rotina inferida; usar
  `local_time()` para o fuso de São Paulo.
- [visual_profile.py](visual_profile.py): `CameraState` e a janela de 45 minutos
  já preservam look e ambiente da foto anterior. Isso é **memória da câmera**,
  não autoridade sobre o local atual. Hoje `build_scene_prompt()` pode reutilizar
  `prev.location` apenas pelo texto “outra foto” e pelo relógio; condicionar
  essa reutilização à compatibilidade com o WorldState atual. A persistência
  `camera_last_state` em `estado_relacional` pode continuar, sem nova tabela.
- [sd_client.py](sd_client.py): `generate_photo()` hoje chama
  `visual_profile.record_photo_generation()` assim que a imagem é gerada. Isso
  registra também imagens nunca enviadas e avatares. Mover a gravação para o
  fluxo **após** `send_photo` confirmado; geração pura não deve alterar memória
  da câmera. Há chamadas em `bot.py`, no gerador de avatar do próprio
  `sd_client.py` e em `test_render_v2.py`: manter compatibilidade para esses
  chamadores.
- [bot.py](bot.py): o pedido de foto está em `process_incoming_batch`, perto
  de `pediu_foto` e da chamada `sd_client.generate_photo(prompt_cenario,
  user_intent=texto_usuario)`. A rotina autônoma legada tem outra chamada,
  mas está desativada no Living World; não permitir que um caminho futuro a
  reative sem o mesmo contexto. A legenda e a resposta em texto não devem
  afirmar que a foto já foi tirada/enviada antes da confirmação do Telegram.

## Implementação proposta

1. Criar um módulo pequeno `camera_world.py` com `CameraWorldContext` imutável e
   um `CameraWorldBuilder(db).build(now, user_request)` **somente de leitura**.
   Retornar: identificador de snapshot, `place_key` conhecido ou `None`, local
   visual seguro, sublocal apenas se explícito, atividade e fonte
   (`confirmed_commitment`, plano explícito, rotina inferida), hora local,
   clima observado e válido, pessoas presentes se confirmadas, e restrições
   negativas para cena. Usar snapshot recente do mesmo dia; se estiver velho,
   não transformar residência canônica em afirmação de presença atual. O
   calendário confirmado pode suprir contexto atual sem criar `world_state`.
   Ausência de local rende enquadramento neutro, sem cenário geográfico novo.

2. Definir mapeamento revisado de `world_places.canonical_key` para descrições
   fotográficas genéricas (apartamento, campus PUC, academia etc.). Nunca
   repassar `location_region` ou descrição privada de compromisso para um
   provedor de imagem sem necessidade. `room/sub-location` só é conhecido se
   dado explícito confiável o trouxer; “apartamento” não implica quarto,
   banheiro ou varanda. Hora noturna não pode gerar sol de meio-dia; chuva
   observada só restringe céu/janela/cena externa quando visualmente relevante.

3. Introduzir uma flag `CAMERA_WORLD_CONTINUITY_ENABLED=false` em `config.py` e
   `.env.example`, exigindo `LIVING_WORLD_ENABLED=true`. Sob essa flag, o
   diretor visual recebe as restrições estruturadas **antes** de produzir as
   tags FLUX. Se a LLM sugerir praia, sol, estúdio, quarto ou roupa em conflito
   com um estado mais autoritativo, rejeitar essas tags e usar um prompt seguro
   derivado do contexto; não apenas acrescentar “apartment” ao fim de uma
   descrição contraditória. Um pedido explícito de Patrick por outro lugar
   não autoriza deslocamento instantâneo. Pedir esclarecimento sobre foto
   antiga/imaginada ou oferecer a foto no local atual, sem alterar o mundo.

4. Preservar o contrato de `sd_client.generate_photo()` para chamadas legadas,
   mas fornecer ao caminho novo resultado com imagem e metadados da geração
   (`full_prompt`, `scene_tags`, `is_nsfw`, `focus_angle`, `place_key` e
   `world_snapshot_id`). Evitar um singleton `last_generation` compartilhado:
   duas gerações concorrentes poderiam trocar metadados. Uma dataclass de
   resultado ou um método novo `generate_photo_with_context()` é adequada.
   Avatares e tentativas falhas não persistem `camera_last_state`.

5. No `bot.py`, confirmar `send_photo` e seu `message_id` antes de chamar o
   registro de continuidade. Gravar no `CameraState` a referência ao snapshot
   ou ao `place_key` e manter `from_dict()` compatível com estados antigos.
   “Outra foto” dentro de 45 minutos reaproveita roupa/sublocal somente se
   local e contexto atuais ainda coincidirem; caso contrário começa sessão
   nova. Roupa não observada permanece indefinida, e look da foto anterior
   não se torna automaticamente roupa da Marina no mundo. Se o upload falhar,
   nenhuma nova continuidade de câmera é persistida.

6. O texto ao Patrick deve corresponder ao resultado real: evite a instrução
   atual que obriga “já tirei” antes de gerar/enviar. A legenda é produzida
   para a foto efetivamente gerada e não deve inventar local, roupa ou clima
   além dos metadados confirmados.

## Critérios de aceitação e testes para o Gemini

Escrever testes offline em SQLite descartável, com LLM, Telegram e gerador de
imagem simulados. Os casos essenciais são: apartamento atual + pedido de praia
não produz praia nem move `world_state`; aula atual prevalece sobre rotina;
snapshot velho não afirma localização atual; noite não vira sol diurno; chuva
ausente ou cache vencido não é inventada; “mais uma” preserva look apenas na
mesma sessão/local; mudança de compromisso invalida câmera anterior; falha de
geração ou de `send_photo` não atualiza `camera_last_state`; geração de avatar
não altera continuidade conversacional; envio bem-sucedido registra apenas a
foto realmente transmitida. Comparar contagem e IDs de `world_state` antes e
depois da geração para demonstrar ausência de mutação silenciosa.

Criar `scripts/run_external_stage13_validation.py`, seguindo o formato de
`scripts/run_external_stage12_validation.py`, para executar a suíte isolada e
salvar `data/camera_world_validation.v366.json`. O Gemini roda; o Codex só
revisa o artefato e as mudanças. Manter a flag desligada até esse aceite.
