# Painel de frentes da Marina

Uma conversa por frente. Pra começar, abra uma conversa nova e cole a frase de abertura da frente.
Ao terminar (ou quando o Claude avisar que é hora), a skill `passagem-de-bastao` atualiza este painel.
O detalhe de cada decisão está nos planos (PLANO_WEBAPP_MARINA.md, PLANO_VOZ_MARINA_V371.md) e na auditoria.

_Atualizado em 28/09/2026, 05:35 (passagem de bastão: textos do Instagram revisados no app e na produção, foto do post 6 refeita à noite; próxima conversa na frente dos apps — Bastidores aba a aba)._

---

## 1. Mundo e agenda — skill `frente-mundo`
**Abertura:** "bora na frente do mundo: agenda viva no uso real e revisão dos textos"

**Pronto (26/09):** agenda única (planejado, vontade, convite → mesma agenda com etapas); academia e passeio do
Milo decididos uma vez por dia; mercado e médico como itens (Bradesco Saúde, Samaritano/Novamed); tempo livre
concreto em casa; masturbação sem cota + convite pro sexting; fome em tempo real, saciedade, belisco e excesso no
peso; mídia real (música iTunes, leitura com compra, Botafogo pela ESPN, Last.fm dele); consumo no rolê;
**agenda reativa** (26/09, noite: conversa vira compromisso/remarca/cancela, sair mais cedo por motivo, aula largada
no meio, tesão como emergência — `agenda_reativa.py`); **unhas** (26/09, noite — `unhas.py`: cor, gel/esmalte,
desgaste; Ophicina do Cabelo na rotina/evento/mimo, R$ 180 do saldo; em casa entediada; pergunta a cor às vezes;
foto da mão depois; a cor em toda foto; seção Unhas no Por dentro); **cabelo** (26/09, noite — `cabelo.py`: lava dia sim, dia não no banho, penteado de agora, corte/luzes/hidratação, Ophicina junta o vencido e cobra do saldo, pergunta penteado e corte/cor, sugestão dele vira mudança, cabelo de agora em toda foto, seção Cabelo no Por dentro; textos revisados com ele na mesma noite).

**Pronto (27/09, tarde):** bugs abertos do mundo limpos (belisco × portaria, banho como fato no prompt, acordar sem café inventado, bloco em casa cortado por academia/banho/saída, convite visto ao acordar) e **agenda viva** (`agenda_viva.py`): o que ela sente decide — repensa rolê/academia/aula/mercado antes de sair (fura, adia, falta e corre atrás da matéria, conta pro Patrick quando o motivo é de dividir), emenda uma parada na volta, chama amiga pra sair à noite, vontade e convites pelo humor, conversa mexendo em qualquer item dos próximos 3 dias; rolê logo depois da aula vai direto (trecho emendado).

**Próximo, nesta ordem:**
1. Ver a agenda viva no uso real (primeira desistência, primeira emenda, primeira amiga chamada) e calibrar os pesos com ele se algo soar forçado.
2. Revisar com ele os textos que decidi sozinho (listas no PLANO_WEBAPP: Milo, academia, preparos, "Na calçada", aviso de saída e Pix do uber… e agora "Agenda viva").
3. Salão (Ophicina) ainda não é repensado pelo humor nem remarcado pela conversa (tem estado próprio em `unhas.py`/`cabelo.py`).
4. Pendências antigas do mundo (PLANO_VOZ 4, 5, 6, 8): virose com banheiro, pai ligando mais, job fora do Rio…
5. Bateria social: saídas sozinha (café, açaí) contam como rolê (SOCIAL) em `social_battery._kind_at` (achado 26/09).

## 2. Apps (Mini App) — skill `frente-apps`
**Abertura:** "bora na frente dos apps: Bastidores aba a aba no celular, começando pela Por dentro"

**Pronto:** iFood com abas (Início/Busca/Pedidos), ícones Tabler (outline, trocados em 26/09), recibos alinhados; linha do tempo Hoje (dia inteiro, saídas com o que rolou, previsto em cinza); Bastidores em abas; aba
Agora decidida linha a linha (card layout D); tela inicial só com os apps; **Instagram** no ar (27/09) com acervo refeito
(folhas das quatro amigas, fotos e textos sem fórmula) e textos revisados por ele no app e na produção (28/09); foto de
fora à noite com luz de noite; post 6 refeito.

**Próximo:**
1. Bastidores **aba a aba** com ele: **Por dentro ✅ (28/09)** — ordem nova, Ciclo no Corpo, Hoje por dentro, Na
   cabeça (agenda viva à vista), motivos num padrão só em voz de painel, barras deslizando a cada 30 s. Faltam
   **Dinheiro** e **Mundo**, no celular, palavra por palavra (PLANO_VOZ 14).
2. Instagram no uso real: o próximo post de rolê da noite (luz e cabelo) e os textos ao vivo (tipo por pessoa, sem molde).
3. iFood da Ma e o banco dela nos Bastidores; `pedido_dela` no catálogo novo; pedidos dela de farmácia/mercado.
4. Fotos provisórias de marca e logos marcados "conferir"; o X dela (Etapa 5, depois do Instagram).

## 3. Voz e chat — skill `frente-voz`
**Abertura:** "bora na frente da voz"

**Pronto (26/09):** balões inteiros e uma iniciativa por vez (fim das mensagens fora de ordem); ponto final
dividindo balão; vocabulário da masturbação; música que ele manda por link.

**Próximo:**
1. Regras das fotos por promessa (PLANO_VOZ 15: quando ela cumpre) e auditoria do prompt do chat (PLANO_VOZ 16).
2. Observar coerência entre turnos e qualidade das iniciativas no uso real (PLANO_VOZ 12, com /bom e /ruim).
3. Técnicas antigas (PLANO_VOZ 13).

## 4. Infra — skill `frente-infra`
**Abertura:** "bora na frente de infra: desempenho do resolve"

**Próximo:**
1. **Desempenho:** cada resolve do mundo leva ~7 s na cópia local, quase tudo no `sleep_plan` (~1.300 conexões
   SQLite por resolve). Cache por dia / conexão reaproveitada.
2. Do Patrick (ele faz): trocar a chave do Civitai (vazou em 24/09); firewall/porta 8000/certbot da VPS.
3. Last.fm dele configurado, mas o perfil ainda tinha 0 scrobbles (Apple Music no iPhone precisa de app de scrobble).

## 5. Bugs — skill `frente-bugs`
**Abertura:** "bora na frente de bugs: varre as últimas 24 horas (mundo × aba Agora × chat)"

Bug do uso real: capturar primeiro (banco, mundo e log da produção), depois diagnosticar por camada (mundo → prompt → fala).

**Corrigidos:**
1. ✅ **Volta do Quartinho Bar (26→27/09)** — corrigido em 27/09 (prompt com a chegada como fato, promessa de avisar amarrada à volta, uber combinado muda o trajeto; `tests/test_bug_volta_quartinho.py`). Registro: Evidências salvas na conversa de 26/09 (conversas 42–69, world_state 104–194, evento 1).
   - **Ida a pé apesar do combinado.** Às 20:19–20:20 ele pediu "vai e volta de uber" e ela prometeu. A ida saiu a pé (20:48–21:00, `commute:outing:…:c1:ida`). A promessa não chega no modo do trajeto: a agenda reativa trata horário e cancelamento, mas não "vou de uber". Camada: mundo.
   - **Chat dizendo que ainda estava no bar, com ela em casa.** O mundo estava certo: a volta foi `uber_dividido` com a Bia, 23:59–00:05, e às 00:07 ela já estava em casa (`post_event_recovery`). Às 00:18 ela disse "acabei de terminar o drink, vou pedir o Uber"; às 00:20 disse "no quarto" e depois "me confundi, ainda tô na rua"; às 00:29 veio "Cheguei", mas pelo ritual `banho_rua`. Camada: prompt.
     - `post_event_recovery` não é `binding` em `world_context.py`, e o texto ("acabou de terminar o compromisso anterior, ainda em casa relaxando") não diz de onde ela voltou nem como.
     - O histórico ("te aviso quando chegar em casa") venceu o fato.
     - Ela também não avisou que chegou quando chegou (00:05): a promessa das 21:39 não foi gravada, porque a volta começava fora da janela de 90 min do `arrival_promise`. Camada: mundo.

2. ✅ **Hoje desconexo do card (27/09, 01:05)** — corrigido em 27/09 (`tests/test_bug_hoje_card.py`).
   - **Dois banhos.** O card "Se arrumando" (pra dormir) marcava banho às 01:00, com o banho de chegada (ritual `banho_rua`) rolando 00:31–01:12. Às 01:14 o passo ainda ativo podia disparar um segundo banho de verdade. Agora o banho de chegada até 90 min antes da cama vira o banho do card (decisão do Patrick: "um card só"); banho mais cedo só tira o passo. Camada: mundo.
   - **Passado no que ainda acontece.** O Hoje mostrava "Tomou banho e lavou o cabelo 00:31–01:12" às 01:05. O que ainda não acabou fica no presente, com a hora em aberto ("Tomando banho e lavando o cabelo 00:31–"). Camada: app.
   - **Instagram fora de hora.** O bloco em casa recuava 5 min e começou às 00:02, com ela no uber até 00:05, e ia até 00:38 passando por cima do banho. O bloco não começa antes da chegada, e o Hoje corta o bloco quando o banho começa. Camada: mundo e app.
   - **Pipoca no bar.** O lanchinho planejado das 21:07 ("pipoca vendo série") foi registrado com ela no Quartinho: passada a janela, a refeição em casa não conferia se ela tinha voltado. Agora espera ela estar em casa. Camada: mundo.

3. ✅ **Pix pago duas vezes (achado na auditoria, 27/09)** — corrigido em 27/09 (`tests/test_bug_auditoria_2609.py`).
   O pix de R$ 300 das 20:17 ("pra curtir") pagou os dois gins e o uber do Quartinho (consumo), e às 10:17 de 27/09 o presente ainda "comprou uma saída com as meninas" (R$ 236): saldo 629 em vez de 865. Agora pix de presente com saída marcada no dia é pro rolê (o prompt diz "pra curtir o rolê de hoje…"), sem segunda compra. Camada: mundo (`financas.py`).
4. ✅ **Milo desce duas vezes de manhã (auditoria, 27/09)** — corrigido. Xixi rapidinho 09:28 e passeio planejado saindo 09:41 (26/09: 09:15 e 09:36); o Hoje mostrava "Foi pra calçada" e "Foi pra Enseada" colados. Passeio até 90 min depois do xixi substitui o xixi. Camada: mundo (`milo.py`).
5. ✅ **Almoço engolia o Se arrumando (auditoria, 27/09)** — corrigido antes de acontecer. Almoço em casa planejado 13:50–14:29 e saída pro cinema às 14:20: a agenda deixa ela comer antes de se arrumar, então o Se arrumando sumia do card, e o almoço atravessava o trajeto. Agora refeição em casa acaba antes do preparo de uma saída do dia (75 min antes, 110 à noite); se não cabe, come quando voltar (saída curta) ou por lá. Camada: mundo (`meals.py`).

6. ✅ **Belisco com o sanduíche na portaria (26/09, 16:40)** — corrigido em 27/09 na frente do mundo: presente na portaria ou pedido dela chegando seguram o belisco (`meals._comida_chegando`).
7. ✅ **"Banhou já?" → "Ainda não" (27/09, 01:57)** — corrigido: "[BANHO — FATO]" no prompt (`world_context._banho`).
8. ✅ **Acordou "tomando café" com o café 1h30 depois (27/09)** — corrigido: sem café agora, "acabou de acordar, ainda de pijama… (o café fica pra umas 10:37)".
9. ✅ **Linha do tempo (26/09):** "Montou looks" × academia e música × banho (o bloco em casa é cortado quando outra coisa começa) e convite às 04:19 (visto ao acordar). `tests/test_bug_mundo_2709.py`.

10. ✅ **Desencontros com a aba Agora (varredura de 27/09, a pedido do Patrick em 28/09)** — corrigido em 28/09 (`tests/test_bug_agora_2709.py`). Varredura das 24 h: mundo × card recalculado numa cópia do banco × chat.
   - **Dois banhos no Se arrumando (13:49–14:34).** Banho real 13:51–13:59; o "vai de uber" das 14:02 mudou a ida e o card e o mundo voltaram pro "Tomando banho" até 14:16. O banho que aconteceu fica como o banho do card. Camada: mundo e card.
   - **"Refri" das 15:13 às 19:00.** O cinema só tinha as compras; ela inventou o filme. Agora tem sessão com filme em cartaz de verdade (TMDB), passeio depois, e o prompt sabe o filme. Camada: mundo e card.
   - **Farmácia "saindo do Shopping" (19:23).** Voltou de uber às 19:20 e, em casa, decidiu ir à Pacheco; a ida saiu do shopping, a pé, desde 19:00. Decidiu em casa, sai de casa. Camada: mundo.
   - **"Tô no Shopping ainda" na farmácia (19:37).** O prompt dizia "local reservado" e não dizia que ela voltou. A máscara saiu e entrou "[VOLTOU E SAIU DE NOVO — FATO]". Camada: prompt.
   - **Belisco saindo de casa (19:28).** Sem belisco em etapa da Agora. Camada: mundo.
   - **Não avisou que estava indo pra casa (19:44).** Promessa de saída agora é cumprida no começo da volta. Camada: mundo.
   - **Tapioca com o McDonald's a caminho (21:32).** Ele avisou que pediu; o jantar agora espera e ela não reage como surpresa. Camada: mundo e prompt.
   - Pros apps: post das 18:58 "noite gostosa com minha pessoa" numa tarde de cinema com a Bia.

**Abertos:** nenhum. Deploy das correções de 28/09 feito junto (ver seção 7 se faltar).

## 6. Imagens (poses, prompts, motor) — skill `frente-imagens`
**Abertura:** "bora na frente de imagens: quarto apagado com flash e foto de grupo das outras amigas"

Cadeia única: pose de referência → prompt no jeito da casa (`photo_director.Pose`) → motor (Civitai Krea 2, LoRA `marinaX`).
O *quando* ela manda foto continua na frente da voz.

**Pronto:** pilha oficial decidida foto a foto (24/09); catálogo por cômodo com faixa de nível (70 poses, com as 18 referências do Patrick em 27/09); sessão com seed; foto sem ela (comida, Milo, vista); unha e cabelo de agora em toda foto; FinePorn v5 em A/B, **mantida a v4** (27/09); plug de coração como 3º brinquedo da gaveta; **Bia com rosto fixo** (28/09): foto-RG `data/amigas/bia_rg.jpg` + `visual_profile.FRIENDS_VISUAL` (quem ela é + estilo) + foto de grupo pela troca de rosto (`civitai_images.swap_friend_face`: Krea 2 Edit, 41 Buzz, cola só o lado dela; Marina intacta); **Carol com rosto fixo** (28/09): foto-RG `data/amigas/carol_rg.jpg`, loira de mel com braço fechado de tatuagem, pele branca rosada; **Júlia com rosto fixo** (28/09): `data/amigas/julia_rg.jpg`, nipo-brasileira de franja, olho verde (a menina da foto de grupo do teste da Bia, editada por partes); **Theo com rosto fixo** (28/09): `data/amigas/theo_rg.jpg`, pardo de cachos (a troca de rosto diz "the man" pra ele, `FRIENDS_VISUAL[...]["noun"]`); **foto de perfil dos quatro no Mundo do Bastidores** (28/09): Krea 2 Edit sobre o RG (cenário e roupa novos, 41 Buzz cada), recorte no rosto em `webapp/avatars/<chave>.jpg`; quem não tem foto fica nas iniciais. **Foto de grupo de ponta a ponta** (28/09): agenda → câmera (`active_people_json`, estava sempre vazio) → diretor (`GROUP_POSES`, selfie com a amiga, só na rua e com RG) → `sd_client` troca o rosto; costura pelo caminho onde original e edição concordam (`seam_path`). 1ª foto real com a Bia conferida por mim (Marina intacta, rosto do RG, sem emenda); cabeças um pouco separadas nas poses de grupo (Patrick). `Pose.face` (a inclinada pra câmera olha pro lado, boca entreaberta); Detail Slider reprovado (1.0 e 3.0); Sick Ollie visto e deixado de lado; **Real/Fake Breast Slider −1.0 em toda foto** (Patrick, contra o bojo); **mordida no lábio** pelo LoRA Lip Bite 0.6 sempre que a cena morde (só texto não mordia).

**Próximo:**
0. **Quarto apagado com flash** (o Patrick gostou no teste da pose inclinada, 27/09): "her dark bedroom with the lights off… the only light is the bright direct flash of the camera" ficou igual à referência dele. Decidir se vira opção de luz à noite no quarto (`apartamento.setting/backdrop`, e o fim "natural light" → "direct camera flash") e quando entra (tarde da noite, clima de sexting?).
1. Foto de grupo: acompanhar a 1ª no uso real (log `foto de grupo sem a troca de rosto` = falhou a troca). Pendências: Carol/Júlia/Theo ainda não rodaram em grupo (a Carol é o maior contraste); foto de grupo em casa (amiga visitando) e com duas amigas (a troca hoje é de uma só, lado direito); ligar no Instagram.
2. Poses que o Patrick mandar (PLANO_VOZ 1). **Aplicar os artigos de pose do Krea 2 (memória `krea2-poses-e-camera`):** a pose de grupo "alguém tirando" ainda sai selfie — testar o objeto borrado na borda (ombro de quem tira); revisar as frases de ausência dos prompts ("not a selfie", "no white circles"…) quando algo proibido aparecer. Lição: roupa *sendo tirada* + nudez = recusa do Krea 2 (ruído de letras); escrever a roupa parada.
3. Ângulo de trás sem espelho (PLANO_VOZ 1d); fatores do gozo especial (1e); acompanhar o slider de peso (9).
4. **Rostos de gente nova** (se o Patrick quiser, ex.: Gabi, Bruno): mesmo caminho — referência → 4 rostos por texto (~80 Buzz) → RG → `FRIENDS_VISUAL` + `FRIEND_RG` → foto de perfil (41) em `webapp/avatars`. Lições: LoRA de rosto da amiga mistura com o da Marina; só texto sai com as feições da Marina; contraste de estrutura com a Marina; o Krea 2 põe sardas sozinho (pele "clear smooth even-toned" e cor concreta tiram quase tudo); a seed de uma candidata puxa o rosto dela numa nova geração com o texto ajustado; **edição por partes** (Júlia): o Krea 2 Edit muda um traço de cada vez (olho, cor da íris, nariz) e só aquela região volta colada na original, com a cor igualada pela pele do rosto — assim a pele, as sardas e a textura não "crocam"; nariz pede frase forte ("noticeably smaller and flatter… low, flat bridge"), a frase fraca não mexe.
5. Do Patrick: trocar a chave do Civitai (vazou em 24/09).

## 7. Auditoria de funcionamento — skill `frente-auditoria`
**Abertura:** "bora na auditoria de funcionamento: tudo o que fizemos em 26/09"

O Patrick está achando muitos bugs no uso real: o dia 26/09 teve ~50 commits em várias conversas, e muita coisa pode ter ficado desamarrada (um módulo novo que o outro não conhece). Não é criar nada novo: é conferir se cada entrega **funciona de verdade na produção**, junto com as outras.

**Primeiro, antes de auditar (27/09, 02:40):**
- **Deploy faltando:** a VPS está em `afd81fd`, o `main` em `f69d2d4`. Não subiram `499bf82` (aparência das amigas) e `f69d2d4` (foto em grupo por prompt), ambos da frente de imagens. Confirmar com o Patrick se aquela conversa terminou antes de subir.
- `origin/main` parado em 26/09: nada de 26–27/09 foi enviado ao GitHub (só o Patrick decide o push).
- Outras conversas abertas: sem worktree nem stash; conferir `git status` (fora `data/feedback/*`) no começo.

**Roteiro** (uma entrega por vez; para cada uma, prova na produção — banco, mundo, log de 26–27/09 — e veredito: funciona / quebrou / não foi exercitada):
1. Etapas do dia e card Agora (se arrumando → a caminho → lá → voltando) × agenda única × agenda reativa × academia/Milo.
2. Em casa: tempo livre concreto, card Em casa, Hoje × rituais (banho) × refeições (fome, belisco, entrega) × saídas.
3. Consumo no rolê e dinheiro: pedidos, uber, saldo, Pix dele, Ophicina (unhas/cabelo) cobrando do saldo.
4. Corpo: fome/saciedade/peso, masturbação sem cota e convite pro sexting, unhas e cabelo como status (e nas fotos).
5. Chat: uma iniciativa por vez, balões, ponto vira balão, portaria (Seu Jorge), mídia (música dele, leitura, ESPN, Last.fm).
6. Mini App: iFood (lojas, sacola, checkout, pedidos), Bastidores em abas, comprovantes.
7. Reset do soak (feedbacks preservados), convite futuro que sobrevive ao reset, migração 027.
8. Imagens (27/09): câmera segue a situação, catálogo de poses, unha e cabelo nas fotos.

Bug achado vira item na seção 5 (Bugs), com a correção feita aqui mesmo se for pequena.

**Status:** rodada 1 feita e no ar (`5332280`). Próxima rodada quando o "não exercitado" abaixo acontecer no uso real (academia em dia útil, vontade, Ophicina, fotos).

**Rodada 1 (27/09, 11:40) — resultado:**
- Deploy: os 3 commits fora da VPS (`499bf82`, `f69d2d4`, `d3b0c95`) só mexiam em relatório e skill; nada de código parado. Log de 26–27/09 limpo (dois erros de rede do Telegram às 22:11; robôs tentando `/.env` no Mini App, barrados).
- Quebrou e foi corrigido: Pix pago duas vezes, Milo duas vezes de manhã, almoço × cinema (seção 5, itens 3–5). Linha antiga com título quebrado ("presencial com a Gabi) Freitas", de antes da correção das 13:19 de 26/09).
- Funciona: etapas da saída do Quartinho (se arrumando 19:56 → a pé 20:48 → lá 21:02 → uber dividido → casa 00:05), passeio do Milo com preparo/ida/volta (27/09), tempo livre concreto, consumo e uber no saldo, portaria conta como contato com o Seu Jorge, pessoas novas por proximidade (Gabi, Bruno), peso na academia, saciedade ("ficou estufada"), lavagem do cabelo no banho, uma iniciativa por vez (depois das 17:40), ponto vira balão (log: 3 linhas → 5 balões), playlist com faixas reais, ESPN, iFood do Patrick pelo app, convite de antes do reset, migração 027, feedbacks preservados.
- Não exercitado ainda: academia com preparo e ida (26/09 começou antes do deploy), vontade/mercado/médico, Ophicina (unhas/cabelo), masturbação e convite pro sexting, música que ele manda, leitura, fotos (nenhuma foto em 26–27/09), agenda reativa ("vai de uber" corrigido na madrugada).
- Decidido com o Patrick: o previsto de saída no Hoje mostra a hora em que ela chega lá ("~15:00 No Shopping da Gávea com a Bia"). Banco da produção consertado (backup `marin_memory.pre_auditoria_2709.db`): saldo 629 → 865, a linha dos R$ 236 saiu do extrato e do Hoje, título da Gabi corrigido.

