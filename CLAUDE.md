# Marina — mapa do projeto

Bot de Telegram da Marina Salles, namorada virtual do Patrick (dono do projeto, uso pessoal). Objetivo dele: ela
ser "praticamente humana" — um mundo vivo onde tudo o que ela faz acontece de verdade e vira história.

## Como trabalhar com o Patrick
- Sempre em **português**. Ele é visual: decisões de texto/tela com mockup (show_widget) e perguntas de múltipla
  escolha (AskUserQuestion), linha a linha. Lista longa antes de uma pergunta some atrás da pergunta: mostre visual.
- Ele dá autonomia ("permissão pra tudo que for necessário"), mas **sem torrar dinheiro** (APIs pagas só com motivo).
- Texto que você decidir sozinho: liste no fim pra ele revisar.
- **Todo commit atualiza AUDITORIA_SISTEMICA_MARINA.md, PLANO_VOZ_MARINA_V371.md e PLANO_WEBAPP_MARINA.md no mesmo lote.**
- Nunca commitar `data/feedback/*` (edições dele) nem `references/` (prints com endereço dele).
- Nunca criar contas, nunca imprimir segredos (só nomes de chave), nunca mostrar imagem adulta no chat, nunca resolver CAPTCHA.
- Não mexer nos outros bots dele na VPS.

## Frentes (uma conversa por frente — ver FRENTES_MARINA.md)
| Frente | Skill | Onde mora a decisão |
|---|---|---|
| Mundo e agenda (vida dela, corpo, rotina, saídas) | `frente-mundo` | PLANO_WEBAPP (aba Agora, etapas), PLANO_VOZ |
| Apps (Mini App: iFood, Nubank, Bastidores) | `frente-apps` | PLANO_WEBAPP |
| Voz e chat (como ela fala, balões, quando manda foto, proatividade) | `frente-voz` | PLANO_VOZ, AUDITORIA |
| Infra (VPS, deploy, desempenho, testes) | `frente-infra` | AUDITORIA |
| Bugs do uso real (capturar, diagnosticar, corrigir) | `frente-bugs` | FRENTES_MARINA.md (seção 5) |
| Imagens (poses de referência, prompts de foto, motor Civitai/LoRA) | `frente-imagens` | PLANO_VOZ ("Fotos pelo Civitai") |
| Encerrar/trocar de conversa | `passagem-de-bastao` | FRENTES_MARINA.md |

**Quando sugerir conversa nova (regra pra você, Claude):** ao terminar um item grande do painel; quando o assunto
muda de frente; ou depois que a conversa já foi resumida (compactada) uma vez. Nesses momentos, diga ao Patrick em
uma linha que é uma boa hora e rode a skill `passagem-de-bastao`. Ele tende a continuar na mesma conversa — o aviso é seu.

## Mapa dos módulos
- **Mundo (estado):** `world_state.py` (resolve: compromisso → plano → trajeto → transição → preparo → rotina;
  um resolve por vez), `agenda.py` (etapas do dia e cards da aba Agora), `vontade.py` (agenda única: saídas por
  vontade, mercado, médico — porta `agendar`), `academia.py` (academia e passeio do Milo planejados),
  `tempo_livre.py` (blocos em casa, masturbação), `commute.py` (trajetos), `calendar_world.py` (compromissos em
  eventos_pendentes), `social_day.py` (amigos, convites, pessoas novas, jogos), `sleep_plan.py`, `rituals.py`.
- **Corpo e sentimentos:** `emotion.py` (sentimentos, tesão), `meals.py` (fome em tempo real, saciedade, belisco,
  peso), `health.py` (doença, médico; plano Bradesco Saúde), `cycle.py`, `social_battery.py`, `intimacy.py`.
- **Vida:** `casa.py`, `milo.py`, `college.py`, `academic_life.py`, `freela.py`, `financas.py` (saldo dela),
  `consumo.py` (o que consome fora), `delivery.py` / `pedido_dela.py`, `watch.py`, `musica.py`, `leitura.py`,
  `futebol.py` (ESPN), `lastfm.py`.
- **Chat e voz:** `bot.py` (handlers, jobs, envio em balões com trava), `proactivity_service.py`, `response_rhythm.py`,
  `response_availability.py` (perfis de disponibilidade), `chat_naturalness.py`, `voice_library.py`,
  `prompt_policy.py`, `world_context.py` (blocos do prompt), `photo_director.py`, `promessa_foto.py`, `civitai_images.py`.
- **Apps:** `webapp_server.py` (API do Mini App), `webapp/` (index.html, app.js, app.css, catalogo.json), `recibo.py`.
- **Banco:** `db.py`, `migrations/NNN_*.sql` (versão = número do arquivo; produção já usou o 26 direto no banco).

## Infra
- Produção na VPS (Hostinger): `root@82.29.60.214`, chave `~/.ssh/marina_vps`, pasta `/root/bots/marina`,
  serviço `marina.service`, banco `marin_memory.db`. Nunca rodar o bot no PC.
- Deploy: `bash scripts/deploy_vps.sh` — não reinicia se o Patrick falou com ela há < 5 min; `--now` só com OK dele.
- Journal da VPS em UTC (local = UTC−3). Python na VPS sem `TZ=America/Sao_Paulo` mostra hora errada.
- Testes: `venv/Scripts/python.exe -m unittest discover -s tests` (sem pytest; ~20 min; não edite código enquanto roda).
- Heredoc no bash estraga `\b` e aspas: para scripts de edição use Write num arquivo do scratchpad.
- Pré-visualização do Mini App: `.claude/launch.json` ("miniapp-real") e `scripts/webapp_preview.py`.
