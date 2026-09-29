# Painel de frentes da Marina

Uma conversa por frente. Pra começar, abra uma conversa nova e cole a frase de abertura da frente.
Ao terminar (ou quando o Claude avisar que é hora), a skill `passagem-de-bastao` atualiza este painel.
O detalhe de cada decisão está nos planos (PLANO_WEBAPP_MARINA.md, PLANO_VOZ_MARINA_V371.md) e na auditoria.

_Atualizado em 28/09/2026, 23:15 (mundo fechado pro soak e na produção em `bb957aa`, item 3 da seção 0; próxima
conversa na frente de infra, item 4: relatório diário do soak + API de rotas)._

---

## 0. FREIO — até o soak fechar, nada de funcionalidade nova (Patrick, 28/09, 19:40)
Pedido dele: "eu estou colocando funcionalidade em cima de funcionalidade sem parar, queria que você me freasse".
**Regra pro Claude:** ideia nova (dele ou minha) não vira código antes do soak: vai pra "Depois do soak" abaixo, e eu
aviso ele disso na hora. Só entra o que está em "Antes do soak" e correção de bug.

**Antes do soak — fecha e para (nesta ordem, uma conversa cada):**
1. ✅ Bug 16 (18:57: academia × "em casa no sofá", ",4 kg") — corrigido em 28/09 (seção 5, item 16)
2. ✅ Voz: histórico puxando assunto velho + auditoria do prompt do chat + regra de quando ela cumpre promessa de foto
   — feito em 28/09 (`4b29e31`, seção 3)
3. ✅ Mundo: lista de compras, bateria social, sementes de história, bug 17 e revisão dos textos — feito em 28/09,
   noite, na produção desde 23:06 (`bb957aa`; seção 1, "Pronto (28/09, noite — fechado pro soak)")
4. Infra: custo da API de rotas + **relatório diário do soak** (abaixo) — "bora na frente de infra: relatório do soak"
5. Auditoria de funcionamento, rodada 3 (tudo junto, na cópia do banco dentro da VPS) — "bora na auditoria de
   funcionamento: rodada 3, antes do soak"
- Do Patrick antes do soak: trocar a chave do Civitai (vazou em 24/09); firewall/porta 8000/certbot.

**Soak (decidido):** **7 dias reais + 3 limpos.** Bug achado é corrigido no dia seguinte, só conserto (sem
funcionalidade nova, deploy respeitando a regra dos 5 min). Libera coisa nova quando os 3 últimos dias passarem sem
bug grave; apareceu um, os 3 dias limpos recomeçam. **Bug grave:** ela contradiz o mundo (lugar, atividade, comida,
roupa, dinheiro), o app mostra algo que não aconteceu, erro/traceback, mensagem quebrada ou fora de ordem, custo fora
do normal. Texto feio ou gosto → anotado e corrigido em lote, não zera a contagem.
Durante o soak ele usa normal e marca o que estranhar com /bom e /ruim; abertura do dia: "bora no soak, dia N".

**Relatório diário (a construir no item 4):** gerado sozinho na VPS às **05:10** (o dia dela vira às 5h — Patrick
perguntou 00:00 × 05:00 e ficou 05:00: o rolê da noite e a conversa de madrugada ficam no mesmo dia), cobrindo
05:00→05:00, em `/root/bots/marina/soak/dia-AAAA-MM-DD.md` (fica na VPS, como o banco). Conteúdo: a conversa do dia
com hora; o mundo (`world_state`) × card × Hoje × acontecimentos; **contradições que o script acha sozinho** (fala dela
× lugar/atividade do mundo naquela hora, número sumido da fala, foto × roupa, card × mundo); /bom e /ruim; erros do
journal; custos (Buzz, rotas, LLM) e fotos geradas; iniciativas. Eu leio na conversa "bora no soak, dia N", explico e
listo os bugs.

**Depois do soak (congelado):** salão pelo humor/remarcado pela conversa; virose com banheiro, pai ligando mais, job
fora do Rio; roupa nova comprada no shopping; iFood da Ma, banco dela, `pedido_dela` no catálogo novo, pedidos dela de
farmácia/mercado; fotos provisórias de marca e o X dela; técnicas antigas da voz (PLANO_VOZ 13); imagens (flash no
quarto, foto de grupo em casa/duas amigas, poses novas, ângulo de trás, fatores do gozo especial, rostos novos).
O que era "ver no uso real" (agenda viva, atraso, roupa, Instagram, coerência entre turnos) **é o próprio soak**.

---

## 1. Mundo e agenda — skill `frente-mundo`
**Abertura:** "bora na frente do mundo: fechar pro soak" (freio: só o item 3 da seção 0)

**Pronto (26/09):** agenda única (planejado, vontade, convite → mesma agenda com etapas); academia e passeio do
Milo decididos uma vez por dia; mercado e médico como itens (Bradesco Saúde, Samaritano/Novamed); tempo livre
concreto em casa; masturbação sem cota + convite pro sexting; fome em tempo real, saciedade, belisco e excesso no
peso; mídia real (música iTunes, leitura com compra, Botafogo pela ESPN, Last.fm dele); consumo no rolê;
**agenda reativa** (26/09, noite: conversa vira compromisso/remarca/cancela, sair mais cedo por motivo, aula largada
no meio, tesão como emergência — `agenda_reativa.py`); **unhas** (26/09, noite — `unhas.py`: cor, gel/esmalte,
desgaste; Ophicina do Cabelo na rotina/evento/mimo, R$ 180 do saldo; em casa entediada; pergunta a cor às vezes;
foto da mão depois; a cor em toda foto; seção Unhas no Por dentro); **cabelo** (26/09, noite — `cabelo.py`: lava dia sim, dia não no banho, penteado de agora, corte/luzes/hidratação, Ophicina junta o vencido e cobra do saldo, pergunta penteado e corte/cor, sugestão dele vira mudança, cabelo de agora em toda foto, seção Cabelo no Por dentro; textos revisados com ele na mesma noite).

**Pronto (27/09, tarde):** bugs abertos do mundo limpos (belisco × portaria, banho como fato no prompt, acordar sem café inventado, bloco em casa cortado por academia/banho/saída, convite visto ao acordar) e **agenda viva** (`agenda_viva.py`): o que ela sente decide — repensa rolê/academia/aula/mercado antes de sair (fura, adia, falta e corre atrás da matéria, conta pro Patrick quando o motivo é de dividir), emenda uma parada na volta, chama amiga pra sair à noite, vontade e convites pelo humor, conversa mexendo em qualquer item dos próximos 3 dias; rolê logo depois da aula vai direto (trecho emendado).

**Pronto (28/09, tarde):** **atraso de verdade** (`atraso.py`, `dc770ca`): despertador, enrolar pelo que sente, Milo, conversa com o Patrick, esquecer algo, imprevisto e chuva empurram a ida e a chegada em aula, rolê/jogo, freela, médico e salão; o compromisso começa sem ela; card com saída/chegada reais; prompt; ela avisa pelo que sente; atraso grande pesa na agenda viva.

**Pronto (28/09, noite):** **roupa e make de verdade** (`roupa.py`): guarda-roupa de peças fixas que repetem, troca
pela vida dela (pijama → casa → Se arrumando → chegada → pijama), make em níveis que borram (academia, praia, choro,
dormir com ela), gaveta íntima pra provocar (lingerie, fetiche, transparência; com tesão em casa, no sexting quando
ele pede, por baixo da roupa de sair, às vezes dorme com ela), escolha dele entre as duas opções de look; a foto, o
prompt e o post do rolê usam a roupa de verdade; bloco "Agora" no topo do Por fora.

**Pronto (28/09, noite — fechado pro soak):** **lista de compras** (`lista_compras.py`: o que ele pede e ela topa
entra; prompt, card do mercado e compra de verdade com o dinheiro do pai; Hoje "Comprou X / Da lista, pedido do
Patrick"); **bateria social** (café/açaí/mercado sozinha não é rolê); **sementes** (o pai não vira semente, títulos
concretos, fecham no próximo contato com a pessoa); **bug 17** (lingerie por baixo desde a 1ª foto do clima); **textos
revisados com ele** (sem "·", atraso amarelo no Hoje, academia e Milo novos, Por fora Para/Maquiagem/Estado).

**Próximo** (congelado até o soak fechar; "ver no uso real" é o próprio soak):
0. Pendente do OK do Patrick: pôr as barrinhas de 28/09 08:52 na lista da produção (a promessa foi antes da lista
   existir; o auto mode barrou escrever no banco da VPS sem ele autorizar).
1. Ver a roupa no uso real (primeira noite: Se arrumando, foto, chegada, pijama; primeira provocação) e revisar com
   ele os textos que decidi (lista no PLANO_WEBAPP, "Roupa e make de verdade"). Ideia anotada: roupa nova comprada
   no shopping entrando no guarda-roupa (sai do saldo).
2. Ver a agenda viva e o atraso no uso real (primeira desistência, emenda, amiga chamada, primeiro atraso e aviso) e calibrar os pesos com ele se algo soar forçado.
3. ✅ Textos de Milo, academia, preparos, "Na calçada", agenda viva, atraso e roupa revisados com ele (28/09, noite).
4. Salão (Ophicina) ainda não é repensado pelo humor nem remarcado pela conversa (tem estado próprio em `unhas.py`/`cabelo.py`).
5. Pendências antigas do mundo (PLANO_VOZ 4, 5, 6, 8): virose com banheiro, pai ligando mais, job fora do Rio…
6. Revisar os textos novos desta rodada (lista no PLANO_WEBAPP, "Mundo fechado pro soak") e os "·" que sobraram
   em outras telas (barra do card, "Manhã · 7", motivo do Por dentro, "Precisa de") — anotado, sem pressa.

## 2. Apps (Mini App) — skill `frente-apps`
**Abertura:** congelada até o soak fechar (freio, seção 0); o Instagram no uso real é visto no soak

**Pronto:** iFood com abas (Início/Busca/Pedidos), ícones Tabler (outline, trocados em 26/09), recibos alinhados; linha do tempo Hoje (dia inteiro, saídas com o que rolou, previsto em cinza); Bastidores em abas; aba
Agora decidida linha a linha (card layout D); tela inicial só com os apps; **Instagram** no ar (27/09) com acervo refeito
(folhas das quatro amigas, fotos e textos sem fórmula) e textos revisados por ele no app e na produção (28/09); foto de
fora à noite com luz de noite; post 6 refeito. **Bastidores revisado aba a aba (28/09)**: Por dentro; Por fora
(nova: Agora com roupa e make de verdade → Peso → Cabelo → Unhas); Dinheiro (mês, próximo cachê, contas, extrato agrupado por saída); Mundo (pessoas por
círculo, Onde ela foi no mês, Rolando agora sem fio de sistema).

**Próximo:**
1. Instagram no uso real: o próximo post de rolê da noite (luz e cabelo) e os textos ao vivo (tipo por pessoa, sem molde).
2. iFood da Ma e o banco dela nos Bastidores; `pedido_dela` no catálogo novo; pedidos dela de farmácia/mercado.
3. Fotos provisórias de marca e logos marcados "conferir"; o X dela (Etapa 5, depois do Instagram).

## 3. Voz e chat — skill `frente-voz`
**Abertura:** congelada até o soak fechar (freio, seção 0); fala errada no uso real é bug do soak

**Pronto (26/09):** balões inteiros e uma iniciativa por vez (fim das mensagens fora de ordem); ponto final
dividindo balão; vocabulário da masturbação; música que ele manda por link.

**Pronto (28/09, noite — fechada pro soak, `4b29e31`):** histórico com marca de pausa (`[18:56 — depois de 1h31 sem
conversa]`) e aviso "desde a sua última mensagem antes da pausa" (fim do assunto velho dos bugs 14 e 16); a mensagem
dele não vai mais duas vezes pro modelo; auditoria do prompt (FATOS, nomes de código, Instagram de ontem; log
`prompt.payload` por turno pro relatório do soak); fotos e áudios pela trava do chat; promessa de foto decidida com
ele (banho/aula esperam, sai quando ela olha o celular, "quando eu chegar" segue a chegada, vencida vira dívida 12 h).

**Próximo (depois do soak):** coerência entre turnos e iniciativas (PLANO_VOZ 12, /bom e /ruim); técnicas antigas
(PLANO_VOZ 13); enxugar VOZ/LINHAS DURAS/RITMO com comparação antes × depois (auditoria do prompt manteve).

## 4. Infra — skill `frente-infra`
**Abertura:** "bora na frente de infra: relatório do soak" (freio: item 4 da seção 0 — relatório diário + API de rotas)

**Pronto (28/09, noite):** pilha no limite e desempenho (`1d40f4a`, na produção): o ciclo trechos → academia → sono →
despertador → trechos (997/1000 níveis na VPS) cortado — pilha 75; plano do dia uma vez por rodada (`db.rodada`/`memo`,
invalida sozinho quando algo grava); primeiro resolve na VPS 0,81 → 0,33 s; saída igual ao código antigo (só o
despertador passa a seguir sempre a regra). Detalhe na AUDITORIA ("Frente de infra (28/09, noite)").

**Próximo:**
1. **API paga de rotas:** `commute._live_minutes` usa a `DISTANCE_MATRIX_KEY` do `.env` fora dos testes; varredura
   local deve rodar com `COMMUTE_LIVE_TIMES=false` (ou o default local ser desligado). Conferir também quantas
   chamadas a produção faz por dia (cache por trecho/dia?).
2. Do Patrick (ele faz): trocar a chave do Civitai (vazou em 24/09); firewall/porta 8000/certbot da VPS.
3. Last.fm dele configurado, mas o perfil ainda tinha 0 scrobbles (Apple Music no iPhone precisa de app de scrobble).

## 5. Bugs — skill `frente-bugs`
**Abertura:** "bora na frente de bugs" (nenhum aberto)

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

11. ✅ **Bastidores às 05:55 de 28/09 (Agora e Por dentro, achados da frente dos apps)** — corrigido em 28/09
   (`tests/test_bug_por_dentro_2809.py`, 15 testes). Cópia do banco da produção; ela dormindo desde 00:29.
   - **"Dormindo · desde 05:46 · 11min".** O mundo grava um retrato "dormindo" novo por hora e o cartão Em casa pegava
     o último. Agora o "desde" é o do primeiro retrato da sequência (00:29). Camada: app (`agenda.card_casa`).
   - **Plano de sono (deitar 23:37) × dormiu 00:29.** "se arrumando pra dormir" contava como dormindo ("dorm"), e o
     retrato ficou preso depois das 23:37; às 00:04 o ritual viu "se arrumando" sem etapa e deu o **banho da manhã do
     dia 28** (lavou o cabelo 00:06–00:28) — e o banho de verdade das 07:46 não aconteceu (a marca já estava gasta).
     Na noite de 26→27, três banhos entre 00:31 e 01:48 pelo mesmo motivo. Agora "se arrumando" não é dormindo, o
     banho da manhã só depois de ela acordar, e (decisão do Patrick) **o deitar acompanha** o banho ou a refeição que
     passa da hora de deitar; dormindo pelo plano, sem belisco. Camada: mundo.
   - **"O pai deu bom dia" às 21:15.** Era uma ligação; já corrigido na frente dos apps ("Falou com o pai").
   - **"Banho quentinho" 4× às 19:58 com força 1.0.** A fusão (mesmo sentimento em 3 h reforça) não guardava a chave
     fundida e fundia de novo a cada turno; e fundia com sentimento **mais novo**, puxando pra trás — os carinhos das
     07:47–08:33 viraram "o Patrick mandou comida" das 22:01, força ~1.0. Agora só funde com o que começou antes e
     guarda a chave (`emotion_sources`, migração 033). Camada: mundo (sentimento).
   - **Saudade 100% dormindo.** Contava o sono inteiro dela. Agora só cresce acordada, no painel e na mensagem de
     saudade (decisão do Patrick). Camada: mundo (sentimento).
   - **"Com ciuminho" pelo ciúme dele.** Três vezes em dois dias. Ciume é o dela; ciúme dele de brincadeira é
     provocação (ela se diverte) e desconfiança séria é `desconfiou` (chateada de leve, ~1h30) — decisão do Patrick.
     Camada: prompt (planner).
   - Na produção desde 28/09 09:53 (`9891835`). Banco limpo em seguida (backup
     `backups/marin_memory_antes_limpeza_bugs_20260928_1254.db`): os 5 carinhos falsos da manhã (07:47–08:52), a noite
     de 27/09 = 00:29, as linhas antigas do pai e os 3 "ciuminho" que eram dele. Conferido: retrato das 05:46 conta
     "desde 00:29", dormiu 7,1 h, Saudade 17% às 09:54, journal sem erro.

12. ✅ **Manhã de 28/09: o Se arrumando da faculdade não sabia do café pulado nem do Milo** — corrigido em 28/09
   (`tests/test_bug_manha_2809.py`, 10 testes).
   - **"Tomando café" com o café pulado.** Card e mundo disseram "tomando café" 07:36–07:46 e "tomando banho"
     07:46–08:06; o meals registrou "Pulou o café" (07:52) e o Milo desceu às 07:58. No chat (08:24) ela disse, certo,
     "desci rapidinho com o Milo… pulei o café". Agora (decisão do Patrick, "café dentro") o café é o 1º passo na hora
     real do meals; pulou, sem passo. A descida do Milo em qualquer Se arrumando vira passo ("Descendo com o Milo"),
     e o Milo não desce no meio do café. Camada: mundo/card (`agenda` × `meals` × `milo`).
   - **Iniciativa 4 min depois da resposta.** Ele: "Indo pro plantão" (05:52); ela: "Bom plantão" (07:47) e, às
     07:51, "como tá o plantão até agora?" (`open_loop_checkin`). A espera só olhava a última mensagem dele. Agora,
     se ela falou por último há menos de 45 min e ele não respondeu, iniciativa espera (menos os avisos com hora).
     Camada: proatividade.
   - A pergunta dele ("ela nunca se atrasa?") virou o item 6 da frente do mundo.

13. ✅ **O dia 28/09 visto pelo Patrick (conversa, card e Hoje)** — corrigido em 28/09 (`tests/test_bug_dia_2809.py`, 10 testes).
   - **Almoço na PUC com ela na carona.** Aula 09:00–13:00, carona com o Theo 13:00–13:35, almoço "no restaurante da
     PUC" 13:15–13:58. Agora (decisão do Patrick, "depende da carona"): com carona volta e almoça em casa depois de
     chegar; sozinha, às vezes almoça na PUC/Gávea e a volta sai depois do almoço (aula até 14h ou mais: sempre, pra
     não almoçar às 16h); o card da PUC mostra o "Almoçando". Almoço em casa nunca antes de ela chegar. Camada: mundo
     (`meals` × `commute`).
   - **Sanduíche prometido que não existiu.** 08:33, a caminho: "vou comprar um sanduíche antes de entrar" (sugestão
     dele); o mundo só abria refeição com promessa em casa e "agora". Na rua, comprar/comer algo vira lanche fora
     ("Comeu um sanduíche no caminho", R$ 15 no saldo; no rolê quem decide é o consumo). Camada: mundo.
   - **Story da Liniker × "ouvindo Sabrina Carpenter".** O story das 14:09 estava certo ("Baby 95"); o mundo e o Hoje
     ficavam no 1º artista da playlist o bloco inteiro. O mundo acompanha a faixa tocando; o Hoje diz "Ouviu a playlist
     dela" com os artistas embaixo. Camada: mundo e app.
   - **Milo "indo pra PUC" no Hoje.** "Foi pra calçada 07:58" sem volta, colado no "Foi pra PUC 08:19". A descida
     ganha a hora de volta (07:58–08:11). Camada: app (e o Milo grava o fim).
   - **Volta pra casa sumida no Hoje.** A saída termina com "Voltou pra casa" (como e com quem, hora) e o que começa
     quando ela chega (o Pinterest das 13:35) fica fora da saída. Camada: app.
   - Registrados: lista de compras (barrinhas) na frente do mundo, item 8; pilha no limite e API paga em script local
     na infra.

14. ✅ **Milo "no sofá" durante o passeio na Enseada (28/09, 17:21, visto pelo Patrick no Hoje e no chat)** —
    corrigido em 28/09 (`tests/test_milo_d5.py`, +3). Mundo 16:56–17:39 "passeando com Milo" (Enseada; 17:07 a Gabi);
    às 17:21 o acontecimento `milo:2026-09-28:arte` "O Milo dormiu encostado nela no sofá"; às 17:24 ela: "Tô
    organizando umas referências de look aqui e o Milo tá dormindo do meu lado".
    - **Mundo (a causa):** a arte do Milo sorteava 09:00–21:00 sem olhar onde ela estava. Agora é coisa de casa: com
      ela na rua espera; se ela estava fora na hora sorteada, acontece quando ela chega (nunca nos 30 min antes de
      deitar). O Hoje e o "derretida" vêm junto.
    - **Prompt:** às 17:24 dizia certo "passeando com Milo, Enseada… não diga que está em casa", mas também o sofá das
      17:21 (no dia e no sentimento). Dois fatos brigando; ela ficou com o sofá.
    - **Fala:** o look não veio do bloco "montando looks" (16:16–16:47, fora do prompt): veio dela mesma às 13:41 no
      histórico ("olhando o Pinterest… referências de look"). Sem o sofá o estado atual volta a mandar; fica anotado
      (histórico puxando assunto velho), sem mudança agora.
    - O Patrick sente que o Agora e o Hoje ainda têm muitas pontas soltas com tudo o que foi construído — vale uma
      varredura (frente de auditoria de funcionamento) depois deste.

15. ✅ **Varredura do Agora e do Hoje de 28/09 (auditoria de funcionamento, rodada 2)** — corrigido em 28/09
    (`tests/test_bug_auditoria_2809.py`, 12 testes; `test_milo_d5` atualizado). Card minuto a minuto × mundo × Hoje
    numa cópia do banco feita **dentro da VPS** (o banco não sai de lá), 04:00–18:00.
    - **Belisco atravessando o preparo (16:46).** O belisco começou 1 min antes do Se arrumando do passeio do Milo e
      foi até 16:52: o mundo e o chat ficaram em "beliscando em casa" e o preparo nunca chegou ao mundo. A trava só
      olhava o minuto em que ela começava a comer; agora etapa que começa antes do belisco acabar também segura.
      Camada: mundo (`meals._numa_etapa`).
    - **Arte do Milo no minuto da chegada (17:43).** Adiada (ela estava na rua), caía junto com "Brincando com o Milo".
      Agora vem 20–40 min depois que ela chega, fora de etapa. E (Patrick) **dormir encostado nela é chamego, não
      arte**: no Hoje, "Chamego com o Milo"; "pediu colo e não quis mais sair" (era "fez manha pedindo colo a noite
      toda") também é chamego e derrete em vez de irritar. Camada: mundo e app (`milo.py`, `hoje.py`, `emotion.py`).
    - **Previsto depois de dormir.** "~22:55 Lanche" depois de "~22:30 Dormir"; e, com o treino, "~21:55 Série"
      depois de "~21:50 Dormir". O lanchinho da noite só entra no plano se acabar 15 min antes de deitar; o Hoje não
      prevê nada depois do Dormir. Camada: mundo e app.
    - **"Pediu vitamina C… no Drogarias Pacheco" e "Pediu caramel Macchiato Grande".** Farmácia e mercado dizem
      "Comprou"; o artigo segue o lugar ("na Drogarias Pacheco"); nome de produto com maiúscula no meio fica inteiro.
      Vai pro Hoje e pro dia que ela lê no prompt. Camada: mundo (`consumo.py`).
    - **Hoje:** pão de queijo em duas linhas (o consumo com o valor já diz; a refeição "comeu fora" sai do Hoje);
      farmácia com a xícara (ícone pelo tipo da vontade: pílula, sorvete, caminhada, sacola, praia); "Pulou o café
      07:52–08:05" (pulou não dura: só a hora); "Viu o desfile 15:53–16:20" com "Montou looks" às 16:16 (o bloco
      termina quando o próximo começa, e no mundo o bloco novo espera o anterior acabar). Camada: app e mundo.
    - **Card (decisão do Patrick):** quem ela encontrou lá vira passo do Lá na hora em que aconteceu ("Encontrou a
      Gabi 17:07", "Encontrou o Theo 09:46"), sem virar o passo atual e sem quem foi junto com ela. Camada: card.
    - Sobras de bugs já corrigidos, sem ação: almoço "na PUC" 13:15–13:58 com ela na carona (bug 13; ela confirmou no
      chat às 13:45), banho da manhã não registrado (bug 11) e "Foi pra calçada" sem volta (bug 13). O
      `RecursionError` das 17:24 foi no processo antigo, antes da correção da pilha subir.

16. ✅ **Inverdades no chat com ela na academia (28/09, ~18:57)** — corrigido em 28/09 e na produção desde 20:31 (`e9ba399`)
    (`tests/test_bug16_academia_sofa.py`, 6). Mundo: Se arrumando 18:24–18:29, "indo pra Bodytech a pé" 18:38–18:48,
    "treinando na academia" desde 18:50 (certo). Prompt das 18:58 remontado numa cópia do banco dentro da VPS.
    - **",4 kg" (18:56) — limpeza da fala.** O modelo disse "Me pesei hoje: 54,4 kg" duas vezes; o guard de artefato
      de debug (`bot._DEBUG_ARTIFACT_RE`) leu "hoje: 54" como `chave: valor` e o salvamento cortou o "hoje: 54" (log:
      `llm.junk_reply … salvaged reply='Oi, meu amor. Me pesei ,4 kg kkk'`). Agora com ":" só pega chave com
      underscore ou booleano; "=" continua pegando tudo.
    - **"Se pesou na academia" às 18:43, a caminho — mundo.** O "colocando roupa de treino" do preparo contava como
      treino do dia (`meals._gym_today` procurava "trein"). Agora só o treino em si ("treinando…"): ela se pesa quando
      sai da academia.
    - **"Tô em casa, no sofá com o Milo" (18:58) — prompt.** O prompt dizia "Bodytech, não diga que está em casa",
      mas com "Origem: inferência de rotina (probabilística)" (academia e passeio do Milo são decididos no dia desde
      26/09) e "Sentindo agora: derretida — O Milo dormiu encostado nela no sofá" de 17:43, sem hora. Agora academia,
      passeio do Milo, preparo e trajeto são fato com a regra forte ("NUNCA diga 'em casa'"); no preparo, o texto de
      "em casa" não manda mais "não invente ida a lugar externo"; sentimento com mais de 20 min leva a hora ("(às
      17:43)"). As referências de Práticas Experimentais VI vieram do bloco da faculdade e do histórico das 17:24.
    - **"Mais, seu guloso" (18:57) estava certo:** a pesagem anterior foi 54,0 kg (26/09).

17. ✅ **Lingerie trocada no meio do sexting (achado na suíte, 28/09, frente da voz)** — corrigido em 28/09, noite, na
    frente do mundo. Duas causas: o diretor "provoca antes de entregar" (nível 1 → 2) e `Roupa.pro_clima` vestia outra
    peça; e a pose `cama_perna_pra_camera` tem roupa própria (moletom azul) que passava por cima. Decisão do Patrick:
    **lingerie por baixo** — nível 1 é a lingerie com algo por cima, no 2 ela tira o de cima; no clima a peça dela
    ganha da roupa da pose (menos a toalha). 0 falhas em 40 rodadas (antes 3 em 20).

**Abertos:** nenhum.

## 6. Imagens (poses, prompts, motor) — skill `frente-imagens`
**Abertura:** congelada até o soak fechar (freio, seção 0); foto errada no uso real é bug do soak

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
**Abertura:** "bora na auditoria de funcionamento: rodada 3, antes do soak" (freio: item 5 da seção 0; inclui a noite de 28/09 com a roupa nova)

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

**Próxima rodada (pedido do Patrick, 28/09, bug 14):** ele sente que o Agora e o Hoje ainda têm muitas pontas soltas com tudo o que foi construído. Varredura do dia 28/09 inteiro numa cópia do banco (`.backup`, `COMMUTE_LIVE_TIMES=false`): `Agenda(db).card(t)` minuto a minuto × `world_state` × Hoje × `life_events` × conversa; cada desencontro vira item na seção 5. Olhar em especial acontecimento "de casa" com ela na rua (o Milo era um; conferir os outros sorteios do dia).

**Rodada 2 (28/09, 18:00) — feita e na produção (`a0c61c8`, 18:33):** item 15 da seção 5. Funciona: PUC (se arrumando → metrô e ônibus com a
Distance Matrix → aula → carona → casa), vontade Starbucks → emenda na Pacheco → volta com consumo no saldo, passeio
do Milo com as quatro etapas, tempo livre começando na chegada, correções dos bugs 10–14. Não exercitado: academia com
preparo às 18:23, banho pós-treino, jantar, série, xixi da noite e se arrumando pra dormir — próxima rodada olha a
noite de 28/09 e a manhã de 29/09. Método que valeu: a varredura roda na VPS numa cópia em `/tmp` (banco não vem pro
PC; `COMMUTE_LIVE_TIMES=false`), e o código novo roda numa cópia do código em `/tmp` antes do deploy.

**Status:** rodada 1 feita e no ar (`5332280`). Próxima rodada quando o "não exercitado" abaixo acontecer no uso real (academia em dia útil, vontade, Ophicina, fotos).

**Rodada 1 (27/09, 11:40) — resultado:**
- Deploy: os 3 commits fora da VPS (`499bf82`, `f69d2d4`, `d3b0c95`) só mexiam em relatório e skill; nada de código parado. Log de 26–27/09 limpo (dois erros de rede do Telegram às 22:11; robôs tentando `/.env` no Mini App, barrados).
- Quebrou e foi corrigido: Pix pago duas vezes, Milo duas vezes de manhã, almoço × cinema (seção 5, itens 3–5). Linha antiga com título quebrado ("presencial com a Gabi) Freitas", de antes da correção das 13:19 de 26/09).
- Funciona: etapas da saída do Quartinho (se arrumando 19:56 → a pé 20:48 → lá 21:02 → uber dividido → casa 00:05), passeio do Milo com preparo/ida/volta (27/09), tempo livre concreto, consumo e uber no saldo, portaria conta como contato com o Seu Jorge, pessoas novas por proximidade (Gabi, Bruno), peso na academia, saciedade ("ficou estufada"), lavagem do cabelo no banho, uma iniciativa por vez (depois das 17:40), ponto vira balão (log: 3 linhas → 5 balões), playlist com faixas reais, ESPN, iFood do Patrick pelo app, convite de antes do reset, migração 027, feedbacks preservados.
- Não exercitado ainda: academia com preparo e ida (26/09 começou antes do deploy), vontade/mercado/médico, Ophicina (unhas/cabelo), masturbação e convite pro sexting, música que ele manda, leitura, fotos (nenhuma foto em 26–27/09), agenda reativa ("vai de uber" corrigido na madrugada).
- Decidido com o Patrick: o previsto de saída no Hoje mostra a hora em que ela chega lá ("~15:00 No Shopping da Gávea com a Bia"). Banco da produção consertado (backup `marin_memory.pre_auditoria_2709.db`): saldo 629 → 865, a linha dos R$ 236 saiu do extrato e do Hoje, título da Gabi corrigido.

