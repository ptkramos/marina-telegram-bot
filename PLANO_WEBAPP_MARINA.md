# Plano — Mini App da Marina (Telegram WebApp)

Criado em 25/09/2026, a partir da ideia do Patrick: são ~40 comandos (`/status`, `/emocao`, `/mundo`, `/memorias`, `/pix`, `/lembretes`, `/vozes`, `/worlddebug`…), e a vida dela cresceu (casa, dinheiro, delivery, saúde, freela). Um Mini App do Telegram junta tudo numa tela que abre dentro do chat.

## 1. Princípio: duas partes com papéis opostos

| Parte | O que é | Regra |
|---|---|---|
| **A vida dela** (banco, delivery, depois presentes e datas) | Coisas que um namorado de verdade faz pelo celular | Cada tela parece um app real. Nada de número interno. O que ele faz aqui vira **acontecimento no mundo dela**, e ela reage na conversa sem saber que existiu um "app" |
| **Bastidores** (emoção, status, memórias, mundo, vozes, feedback, restart) | O painel de controle do bot | Fica numa aba separada, pra o chat voltar a ser só a conversa. Aqui pode ter número à vontade |

**O que o app não pode virar:** um Tamagotchi. Nada de "afeto 87%" na parte da vida, nem de botão de "fazer carinho". Carinho continua sendo na conversa.

## 2. Arquitetura

- **Servidor dentro do próprio bot.** Um `aiohttp.web` sobe no `post_init` do `Application` (python-telegram-bot 22.8 + aiohttp 3.14, os dois já instalados). Fica no mesmo processo e no mesmo banco SQLite, sem segundo processo disputando o banco. Arquivo novo: `webapp_server.py`.
- **Frontend:** HTML, CSS e JS puro, em `webapp/`, sem framework e sem build. Usa `telegram-web-app.js` (tema claro/escuro do próprio Telegram, botão principal, vibração).
- **Endereço HTTPS: pronto (25/09).** A Marina foi pra VPS, e `https://marina.psoft.app` já tem certificado e aponta, pelo nginx, pra `127.0.0.1:8787`, onde o servidor do app vai escutar. Até o app existir, responde 502.
  - O certbot do sistema está quebrado desde 02/09 (um `cryptography` 50 instalado por pip no Python do sistema). O certificado da Marina saiu por um certbot isolado (`/opt/certbot-marina`) e renova sozinho pelo `/etc/cron.d/certbot-marina`, sem depender do sistema.
- **Como abre:** botão de menu do chat (`MenuButtonWebApp`) e um `/app` de reserva.
- **Segurança:**
  - Toda chamada à API manda o `initData` do Telegram, e o servidor valida o HMAC com o token do bot.
  - Aceita **só o ID do Patrick** (o mesmo `chat_id` que o bot já usa).
  - `initData` com mais de 24 h é recusado.
  - Nenhum segredo vai pro frontend, e o endereço do túnel não é segredo.
  - Nada de `localStorage` para estado: tudo vem do banco.

## 3. Etapas

### Etapa 1 — Esqueleto e bastidores só de leitura
- `webapp_server.py`: rotas `/app/*` (estáticos) e `/api/*` (JSON), validação do `initData` e início junto com o bot.
- `/api/status`: o que ela está fazendo agora, a agenda do dia e o próximo evento. Mesma fonte do `/status`, sem duplicar lógica: as funções que o `/status` usa passam a devolver dados, e o comando só formata texto.
- `/api/emocao`: sentindo agora (episódios agrupados, como no `/emocao` depois de 25/09), vínculo, tesão, energia. **Com as barrinhas do `/emocao`** (pedido do Patrick, 25/09): nos bastidores, número e barra são bem-vindos.
- `/api/memorias` e `/api/mundo`: listas com busca.
- Tela de início: "agora" + atalhos. Tela de bastidores.
- **Aceite:** abre pelo botão do chat; outro usuário recebe 403; os números batem com os comandos; o bot segue respondendo normal com o servidor no ar.

### Etapa 2 — Banco
- `/api/financas`: saldo, movimentos (`MOVS_KEEP = 30`), empréstimo em aberto e pedido de ajuda em aberto. Tudo sai do `financas_json` que já existe.
- `POST /api/pix`: valor + recado, pela mesma `financas.receive_pix`. Depois de receber, ela reage na conversa do mesmo jeito que no `/pix`.
- O `/pix` de texto continua funcionando.
- **Aceite:** um pix pelo app e um pelo `/pix` dão o mesmo resultado no saldo, no evento do dia e na reação dela.

### Etapa 3 — Delivery pra ela (a parte nova)
Hoje o `delivery.py` só abre pedido quando **ela** diz que vai pedir. O que entra:
- **Cardápio fixo de lugares em Botafogo**, curto e com preços coerentes com o `DELIVERY_PRICE` do `financas.py`. Fica num arquivo de dados (`webapp/cardapio.json`) que o Patrick pode editar.
- **`POST /api/delivery`:** abre um pedido **pago por ele** (não sai do saldo dela), com um recado opcional. O tempo de entrega segue o `ETA_MIN` do delivery.
- **O mundo decide o que acontece quando o pedido chega:**
  - ela em casa → recebe e come (transição de refeição, como hoje);
  - fora de casa → fica na portaria, e ela pega ao voltar;
  - dormindo → o porteiro guarda, e ela descobre de manhã;
  - no banho → o pedido espera ela sair.
- **Ela reage na conversa quando o pedido chega**, com uma mensagem espontânea (iniciativa) que traz o recado dele. Não fica sabendo antes: é surpresa.
- **Limite de bom senso:** um pedido em aberto por vez. Se ela acabou de comer, ela pode comentar isso ("amor eu tinha acabado de jantar kkkk") em vez de fingir fome.
- **Aceite:** pedidos simulados em cada estado (em casa, fora, dormindo, no banho) geram o evento certo no dia, a refeição certa e uma mensagem dela coerente.

### Etapa 4 — Depois (só com o Patrick aprovando cada uma)
- **Presentes:** flores e coisas pequenas pela mesma mecânica de entrega. Os presentes viram objetos dela, que podem aparecer em foto ("o ursinho que você mandou").
- **Datas:** aniversário de namoro e datas dela, com lembretes.
- **Aposentar comandos** só quando o app de fato substituir o comando. Até lá, os dois convivem.

## 4. Custos e riscos

| Item | Situação |
|---|---|
| API / Buzz | Zero. Nada no app chama LLM, com uma exceção: a reação dela ao pedido, que é uma fala normal |
| Hospedagem | Túnel grátis agora; na VPS, junto com o resto |
| Banco travado | Mitigado: o servidor fica no mesmo processo e usa as mesmas funções de acesso |
| App fora do ar com o PC desligado | Igual à Marina hoje; resolve na VPS |
| Imersão | A regra da seção 1, mais uma revisão do Patrick em cada tela antes de ir ao ar |

## 5. Decisões do Patrick

1. **Túnel agora ou esperar a VPS?** Decidido em 25/09: **ir pra VPS primeiro** e subir o app já nela.
2. **Delivery é surpresa** (ela só descobre quando chega) **ou ele avisa na conversa?** Recomendação: surpresa por padrão. Se ele contar na conversa, ela fica esperando.
3. **Cardápio com nomes de lugares reais de Botafogo ou inventados?** Recomendação: inventados com cara de reais ("Açaí da Praia"), pra não ter que manter preço e horário de verdade.
4. **Visual das telas:** esboço mostrado no chat em 25/09. Aprovar ou ajustar antes da Etapa 1.

## 5b. Termos e realismo (decididos com o Patrick em 25/09, tarde)

- **Marcas reais** (uso pessoal): o banco dele é o **Nubank**, o dela o **Itaú Personnalité** ("ela é rica"). O delivery é o **iFood**, com o símbolo do **Pix**. Logos do Wikimedia Commons, em domínio público, guardados em `webapp/marcas/`.
- **Sem emoji** no que imita os apps (o iFood não usa); atalhos com os logos.
- **Nubank:** tile e título "Nubank", subtítulo "Área Pix".
  - Campo "Quanto você quer transferir para Marina Salles?", botão "Transferir".
  - "Adicionar mensagem (opcional)".
  - Tela de revisão ("Revise a transferência", com valor, para quem, banco, mensagem e "Confirmar").
  - O dinheiro dela (saldo, movimentações, o que ela deve) sai daqui e vai pros **bastidores**.
- **iFood:**
  - Entrega em "Casa da Ma", sem bairro.
  - Botão "Fazer pedido", com o resumo e o total acima dele.
  - "Observações do pedido".
  - Sem aviso explicativo de sistema.
- **Status do pedido no estilo iFood completo:** Pedido confirmado → Em preparo → Saiu para entrega → Entregue, com a etapa atual destacada.
  - Na portaria: "Entregue na portaria · 13:40", sem motivo.
  - Recebido: "Pedido entregue · 13:40".
- **Pedido dela pra ele:** "Presente da Ma", com cara de iFood.
- **Em andamento:** "Você tem um pedido em andamento" + o card do pedido.
- **Depois de confirmar:** o app fecha, e no chat aparece o **comprovante B**, uma imagem com cara de comprovante do Nubank ou de pedido do iFood.
  - Vai como **mensagem do Patrick** ("via @bot", pelo `answerWebAppQuery`).
  - A Marina ignora essa mensagem: ela reage ao que o sistema contou, e o recibo não entra no histórico dela, o que preserva a surpresa do delivery.

## 6. Status

| Etapa | Status |
|---|---|
| 1 Esqueleto + bastidores | ✅ 25/09 |
| 2 Banco | ✅ 25/09 |
| 3 Delivery pra ela | ✅ 25/09 |
| 4 Presentes, datas, aposentar comandos | ⬜ |
| iFood realista (layout do app real + cardápio com lojas reais) | 🟡 26/09: **64 lojas reais, todas com logo real** (43 Botafogo, 21 Campo Grande). Restaurantes de bairro voltaram com logo pelo Google Imagens; 3 saíram (Galeteria Botafogo, Ben Ali, Tacos & Wraps: o Google só trazia outras lojas) e 3 ficam marcadas pra conferir (Cake & Co., Mr. Wong, Rei da Picanha: nome repetido em outras cidades). Logos do Wikimedia, dos sites, recortados dos prints dele e, pros mercados e farmácias dela (Zona Sul, Hortifruti, Pão de Açúcar, Mundial, Droga Raia), do Google Imagens. **Cardápios feitos** (`scripts/ifood_cardapios.py`: 212 pratos + 27 produtos de mercado + 14 de farmácia; `scripts/ifood_build.py` → `webapp/catalogo.json`, 567 itens com tempo/taxa pela distância real). **Fotos: 227 de 227** — 28 do Google (produtos oficiais das redes) e o resto do Pexels (API oficial, chave do Patrick, busca em inglês; `scripts/ifood_fotos.py`, créditos em `webapp/fotos/creditos.json`). Itens de marca com foto genérica ficam marcados `provisoria` pra trocar pela oficial devagar pelo Google. **Layout feito (26/09):** lista com filtros e busca, página da loja (capa, nota, aberta/fechada, Destaques, seções), prato (observação 0/140, quantidade), sacola de vários itens (mínimo, Peça também), entrega, pagamento (iFood Pago · Pix, taxa de serviço R$ 0,99) e "Revise o seu pedido"; a observação dos pratos vira o bilhete dela. Conferido em `scripts/webapp_preview.py` (pré-visualização local). **Abas Início/Busca/Pedidos e histórico como o app real (26/09, 07:30).** Faltam: iFood da Ma nos Bastidores, pedidos dela no catálogo novo, farmácia/mercado dela |
| 5 Redes sociais (Instagram e X) | 💡 ideia 26/09 |

### Como ficou (25/09)
- **Arquivos:**
  - `webapp_server.py` (aiohttp, validação do `initData`, rotas);
  - `webapp/` (`index.html`, `app.js`, `app.css`, `cardapio.json`);
  - ligação no `bot.py`: `_start_webapp`, `_webapp_pix`, `delivery_gift_routine` (a cada 60 s) e `/app`.
- **Abrir:** botão de menu "Marina" no chat (`set_chat_menu_button`) ou `/app`.
- **Mesma fonte dos comandos:** `/status` e `/emocao` passaram a sair de `_status_snapshot` e `EmotionEngine.panel`. O texto dos comandos ficou idêntico (conferido em 3 horários).
- **Pix pelo app:** mesmo registro do `/pix`, e ela reage pelo fluxo normal de conversa (turno sem mensagem real, `message_id` 0: sem citação e sem reação por emoji).
- **Delivery surpresa** (`delivery.gift` / `gift_tick`):
  - Em casa e acordada: recebe na hora, come e vira a refeição do horário (`meal:…:presente`, que as finanças não cobram).
  - Fora, dormindo ou no banho: fica na portaria com o Seu Jorge e ela pega quando pode.
  - Se comeu há pouco: guarda pra depois (evento `gift`).
  - Até receber, o prompt dela não sabe de nada.
  - Quando recebe, ela manda uma iniciativa (`presente_delivery`) com o bilhete, e o avaliador de emoções registra carinho por ele.
- **Cache:** o `index.html` sai com a versão dos arquivos no link, pra o webview do Telegram não segurar o `app.js` antigo depois de um deploy.
- **Testes:** `tests/test_webapp.py` (15), e telas conferidas num navegador em tamanho de celular.

### Ajustes de 25–26/09
- **Ela manda delivery pra ele** (`pedido_dela.py`): aparece na tela inicial como "Presente da Ma", **no fim da página e só até ser entregue**. Ela compartilha o link "🛵 Acompanhar entrega" na própria fala (chat é chat, app é app).
- **Pedido dele sai da tela inicial** (feedback 26/09): fica no iFood, em andamento e na lista "Pedidos" (histórico `ifood_pedidos_json`, 30 últimos).
- **Sem zoom:** viewport, `touch-action`, bloqueio de `gesturestart` e campos com 16 px (o iOS amplia campo menor).
- **Comprovante:** os PNGs das marcas estavam no `.gitignore` (`*.png`) e nunca tinham ido pra VPS — o do iFood saía sem logo e a revisão do Pix sem o ícone. Agora `!webapp/marcas/*.png`. Item com o nome inteiro (igual ao app) e observação toda em negrito.
- **Reset do soak (26/09)** zerou finanças, pedidos e histórico do iFood.
- **Abas do iFood e padrão visual (26/09, 07:30, 3 prints novos do Patrick):**
  - **Barra fixa embaixo** com Início, Busca e Pedidos (como no app real). Trocar de aba não empilha: o voltar sai do iFood. O Início tem um botão de busca que abre a aba Busca.
  - **Aba Pedidos:** pedido em andamento no topo, "Seus clássicos" (lojas onde ele já pediu, em cartões) e **Histórico** agrupado por dia ("Sáb, 26/09/2026"). Cada cartão tem logo, loja, "Pedido concluído" com check verde, itens com a quantidade numa caixinha, foto do prato e "Ver loja" / "Adicione à sacola" (refaz a mesma sacola se a loja estiver aberta). O histórico agora guarda `loja_id`, `logo` e `itens` (id, nome, qtd, foto).
  - **Regra do Patrick: sem emoji no lugar de ícone nos apps.** Ícones do **Bootstrap Icons** (CDN jsdelivr): voltar, estrela, coração, lixeira, menos/mais, localização, moto, seta, check, e as linhas de status dos Bastidores (antes 🏠📱🌸🤒📅🗓️).
  - **Regra do Patrick: excelência em alinhamento, também nos comprovantes.** Destaques sem "escadinha" (o `<button>` centralizava o conteúdo; agora tudo começa no topo e o nome corta em 2 linhas). Stepper da sacola com colunas fixas (lixeira e menos ocupam o mesmo espaço). Barras dos Bastidores terminam todas no mesmo ponto (coluna da palavra com largura fixa). Ícone e texto das linhas de status alinhados.
  - **Comprovante do iFood em colunas:** logo redondo da loja + nome; itens com quantidade em caixinha, nome quebrando por largura real em pixels (2ª linha recuada sob o nome) e preço na margem direita; subtotal, taxa de entrega, taxa de serviço e total alinhados à direita. **Pix:** todos os valores em negrito (antes Destino/Origem saíam finos) e o ícone do Pix centrado na linha.

### Bastidores em abas e textos de gente (26/09, manhã — pendência 14)
- **Decisões do Patrick:** abas (Agora · Por dentro · Dinheiro · Mundo) e **voz híbrida**: rótulos, status, números, dinheiro e mundo falam como painel ("você"); o que é sentimento (motivo de cada um) fala do jeito dela.
- **Agora:** atividade em destaque, "Em casa · Botafogo" (não "Apartamento da Marina (Botafogo)"), linhas rotuladas com ícone: Celular ("Responde quando acordar", sem 🌙), Ciclo ("Dia 24 · TPM"), Saúde, Próximo ("Aula de Projeto, segunda 14h"), Plano. **Hoje** em linha do tempo; os eventos gravados em 3ª pessoa viram voz de painel ("Você fez um Pix de R$ 150 pra ela").
- **Por dentro:** barras do corpo; dormindo, a Energia mostra "dormindo" e não "exausta" (era pressão de sono). A frase "dormiu 8,7 h · TPM · última vez há 30 h" virou linhas: Sono ("dormiu 8h40 · acordou às 9h05"), Último orgasmo, Desconforto, "No clima agora". Sentindo agora com preposição certa ("com saudade dele", "chateada com ele", "grata à Bia") e o motivo na voz dela ("Ele me elogiou", "Ele fez um Pix pra mim"); pílulas "3 vezes" e "até resolver". "Com você" virou **Vocês dois**.
- **Dinheiro:** saldo grande, "Deve a você", "Precisa de R$ X"; extrato em voz de painel ("Seu Pix · pro açaí", "Seu presente: …", "Delivery pra você: …", "Celular e streamings"). Aqui entram o banco dela e o iFood da Ma.
- **Mundo:** o texto colado do `/mundo` ("Henrique Salles — último contato sem contato ainda; 0 nos últimos 30 dias") virou cartões: iniciais, nome ("Bia Andrade"), quem é, curto (`social_day.QUEM`: pai, melhor amiga, porteiro…), "hoje, 08:15" / "Sem contato ainda" e "4 vezes no mês" (o `weekly` do cânone não é contagem e não aparece). Rolando agora, Planos e Lugares em listas.
- **Código:** `webapp_server.status_view`, `emocao_view`, `voz_painel`, `voz_dela`, `mov_desc`; `SocialDay.world_panel`. O `/status`, `/emocao` e `/mundo` do chat não mudaram. Testes: `tests/test_bastidores_textos.py` (11).
- **Seu Jorge (26/09):** pegar o delivery na portaria agora conta como contato com ele (`delivery._contato_portaria`); antes o Mundo mostrava "Sem contato ainda" logo depois de ela pegar o presente.
- **Visto nos dados reais (26/09, 08:48):** depois do reset, todo mundo ainda "sem contato" e "Hoje" vazio — ela estava dormindo (sábado). Conferir de tarde se o pai e as amigas aparecem com contato.

### Aba Agora — decisões com o Patrick, linha a linha (26/09; saída de casa implementada, atividades em casa a decidir)
**Por quê:** o status só mostrava onde ela está e o que faz; não existia preparação nem "indo fazer" (fora a faculdade de manhã) — do "tempo livre em casa" ela pulava pro trajeto.

**Mundo (comportamento):**
- Todo compromisso fora de casa vira sequência: **Se arrumando → A caminho → Lá → Voltando → Chegou**.
- Tudo que ela faz pode virar gancho pra avisar ele, mas avisar ou não é escolha dela; se ele pediu pra avisar e ela lembra, ela avisa (já existe).
- Se arrumando ela não larga tudo pelo celular: dá olhadinhas, responde com atraso, às vezes pede opinião.

**Card (base: layout D):**
1. **Título curto** ("Se arrumando", "A caminho"). Nome de lugar curto só no título e no chat; nos detalhes, nome oficial.
2. **Linha 2** diz o que vem, com hora aproximada: "Vai sair pro Quartinho Bar às ~20:00", "Chega na PUC-Rio às ~13:40".
3. **Barra de progresso** do início até o fim da etapa: "13:05 · há 16min · faltam ~19min · ~13:40". Duração no formato **"1h 10min"**. Sem hora de fim conhecida: hora de início e duração à direita do título.
4. **Grade** (rótulo de uma palavra, coluna do tamanho do maior rótulo, nada quebra linha): Com (Theo e Júlia), Como (Ônibus / Carona com o Theo), Celular.
5. **Linha do tempo única:** o dia inteiro (etapas feitas com hora, atual em destaque, próximas com hora aproximada) e os **passos da etapa atual recuados dentro dela**. Vale pra todas as fases.
6. **Imprevisto** vira passo amarelo na linha do tempo, com hora ("Ônibus veio lotado 13:15").
- **Horas:** formato 00:00. Aproximadas (~) na chegada prevista, fim de rolê, saída de casa e fim de aula.

**Textos do Celular** (sempre "Olha…"): livre em casa **Olha com frequência** · se arrumando, comendo, no rolê, de carona **Olha de vez em quando** · transporte público e uber **Olha com frequência** · aula, treino, trabalho **Olha nos intervalos** · banho **Olha depois do banho** · dormindo **Olha quando acordar**.

**Passos do Se arrumando** (gerúndio, sem artigo; feitos e atual com hora):
- Rolê à noite: Tomando banho · Secando cabelo · Fazendo maquiagem · Escolhendo roupa
- Faculdade: Tomando café · Tomando banho · (Secando cabelo, às vezes) · Escolhendo roupa
- Café/almoço com amiga: Tomando banho · Fazendo maquiagem · Escolhendo roupa
- Freela: sem maquiagem (a make é feita lá)
- Academia e praia: dois passos (ex.: roupa de treino + garrafinha; biquíni + protetor — textos a fechar)
- Último passo antes de sair, pelo transporte: **Esperando carona** / **Chamando uber** / saindo
- Skincare faz parte do banho (higiene), não é passo.

**A caminho** (título "A caminho"; linha 2 "Chega na PUC-Rio às ~13:40"):
- Ônibus: Andando até o ponto · No ônibus · Saltando na Gávea · Andando até a PUC
- Metrô (e metrô + ônibus): Andando até a estação · No metrô · Trocando pro ônibus · No ônibus · Saltando · Andando até o lugar
- Carona: No carro com o Theo · Chegando no {lugar curto}
- Uber: Esperando uber · No uber (valor do uber aparece na linha)

**Lá:**
- **Título = nome curto do lugar** ("No Quartinho", "No Starbucks", "Na PUC"); **Onde = sempre só o bairro** (Botafogo, Gávea), igual pra toda atividade.
- Linha 2: o que vem ("Volta pra casa às ~00:00"). Barra no padrão "há X" (na aula também; a matéria fica nos passos).
- Passos recuados: faculdade = as aulas e o intervalo; rolê/café = **o que ela consumiu, em uma linha**: nome curto à esquerda, **valor e hora em colunas à direita** ("Gin tônica · R$ 34 · 20:40"). Pedido repetido aparece de novo com o mesmo nome (sem "(2)").
- **Isso é cânone:** cada consumo é acontecimento real do mundo — sai do saldo, entra no extrato, vira lembrança, ela pode comentar. Antes do reset ela foi ao bar e o banco não mexeu. **✅ Feito em 26/09 (`consumo.py`)** — ver "Consumo no rolê" abaixo.
- Etapa concluída mostra o total gasto nela ("No Quartinho · R$ 86").

**Voltando** (aprovado): "Voltando pra casa" · "Chega em casa às ~00:25" · passos do transporte (uber com valor).

**Em casa:** chegou é **"Em casa"**, não uma fase "Chegou". O que ela faz pra dormir é outro **Se arrumando** ("Vai dormir às ~01:00"; Tirando maquiagem · Tomando banho · Colocando pijama).

**Cânone:** "Starbucks do Shopping da Gávea" vira **"Starbucks da Gávea"** (vale pro mundo todo, inclusive chat).

**Falta decidir:** as atividades em casa (tempo livre, comendo, banho, vendo série, Milo, dormindo) e os textos de academia/praia.

**Ordem combinada com o Patrick:** (1) consumo canônico ✅ → (2) implementar a sequência no mundo + o card novo ✅ → (3) atividades em casa.

### Sequência da saída e card da aba Agora (26/09, `agenda.py`) ✅
- **`agenda.py`** organiza o dia em etapas a partir do que o mundo já decide (saídas, freelas, aulas, trajetos com modo/carona/imprevisto, consumo, plano de sono): Se arrumando → A caminho → Lá → Voltando; depois de rolê com make, Se arrumando pra dormir. Não inventa nada.
- **No mundo:** o `WorldStateManager` põe ela "se arrumando pra sair pro Quartinho Bar (fazendo maquiagem)" durante a preparação (antes: "tempo livre em casa" até o trajeto). Disponibilidade nova **GETTING_READY** ("olha de vez em quando": responde entre um passo e outro, 45 s a 10 min); "se arrumando pra dormir" não é lido como dormindo. O **banho do passo "Tomando banho" acontece de verdade** (qualquer preparação, com a duração do passo; o da faculdade continua marcando o bom dia).
- **Durações:** rolê à noite 60–90 min, encontro de dia 30–45, freela 40–55, praia 15–20, faculdade do acordar até sair (máx. 90), pra dormir 30–45. O último passo segue o transporte (Esperando carona / Chamando uber / Saindo). Faculdade tem "Secando cabelo" em 40% dos dias.
- **Card (layout D):** título, linha 2 com hora aproximada, barra (início · "há 1h 10min · faltam ~15min" · fim; no Lá só "há"), grade (Onde/Como/Com/Celular), linha do tempo do compromisso inteiro + a próxima etapa, com os passos da etapa atual recuados; consumo só aparece depois de pedido, com valor e hora em colunas; etapa concluída mostra o total; imprevisto em amarelo, com texto curto ("Motorista errou o caminho", "Pararam pra um açaí").
- **Celular** em todo o app no padrão "Olha …" (também fora das etapas, pelo tipo de atividade).
- **Conferido** na pré-visualização com o backup de antes do reset (`scripts/webapp_preview.py --db … --agora …`, rota `/dev/agora` só local): se arrumando pro bar, a caminho de carona, no bar com os pedidos, dia de aula com o imprevisto do açaí, se arrumando pra dormir.
- Testes: `tests/test_agenda.py` (7).
- **Convite de antes do reset (26/09):** o reset tinha apagado o fim de semana (convites "chegados" antes da vida registrada eram descartados). Agora rolê futuro conta o convite como recebido no reset; o bar de sábado com a Bia voltou na produção (convite gravado 12:17, decisão dela às 19h).
- **Pendências:** (a) conflito antigo do mundo — café às 15:30 em dia de aula até 15:00: a volta da PUC e a ida pro Starbucks se sobrepõem (o trajeto precisa decidir "direto da PUC"); (b) academia não tem preparação (é rotina sorteada, não compromisso com trajeto); (c) fora de uma etapa o card ainda é o antigo — é a etapa 3 (atividades em casa).

### Consumo no rolê (26/09, `consumo.py`) ✅
- **Quem paga (decisão do Patrick):** lazer e uber saem do **saldo dela**; ônibus e metrô são do Riocard que o pai carrega (fora do saldo e fora do extrato). O que o pai paga não aparece no extrato.
- **O que ela pede** é função do rolê (data, lugar, amigos): o mesmo rolê sempre tem os mesmos pedidos, então card e extrato batem.
  - Quartinho Bar: 2 a 4 drinks (Gin tônica R$ 34, Chopp R$ 16, Caipirinha R$ 28, Drink de maracujá R$ 32; às vezes troca), porção dividida em 70% dos rolês (Fritas R$ 36, Bolinho de bacalhau R$ 44, Pastel de queijo R$ 38), às vezes uma água.
  - Starbucks da Gávea: **os mesmos itens e preços do iFood do app** (catálogo `starbucks-bf`): uma bebida e, em 60%, uma comida.
  - Cinema no Shopping da Gávea: ingresso R$ 42, pipoca dividida R$ 34, às vezes refri.
  - Praia: cadeira e guarda-sol dividido (60%), água de coco, e 1–2 de mate, biscoito Globo, queijo coalho.
  - Uber: R$ 6 + R$ 1,30/min (dividido = metade).
- **Cada pedido vira:** acontecimento do dia (`life_events` tipo `consumo`/`transporte`, "Pediu um gin tônica no Quartinho Bar (R$ 34)."), gasto no saldo (extrato "Quartinho Bar · Gin tônica"), e — se for comida no horário de uma refeição — **a refeição do horário** (`meal:{dia}:{tipo}:fora`), pra ela não jantar de novo em casa. Ela fica sabendo pelo `since_last` (o que aconteceu desde a última fala dela).
- **Só o que já aconteceu** e só em rolê confirmado e não cancelado; idempotente. Roda no `WorldStateManager.resolve`, depois do trajeto e antes das refeições.
- **Cânone:** "Starbucks do Shopping da Gávea" → **"Starbucks da Gávea"** (seed + migração `027_starbucks_da_gavea.sql` (o 26 já estava usado direto no banco da produção), que também corrige os eventos já marcados).
- Testes: `tests/test_consumo.py` (10).
- **Ainda não:** pedido limitado pelo saldo (hoje ela pede igual com pouco dinheiro; o aperto cai no pedido de ajuda pra você, que já existe) e consumo em outros lugares (PUC, academia, shopping sem cinema).

### Etapa 1 — Em casa: decisões do Patrick (26/09, tarde; **base construída** — mídia real, cuidados e música sugerida a seguir)
**Regra de ouro:** tudo o que ela faz acontece de verdade no mundo e vira história (acontecimento do dia, efeito no corpo/dinheiro/estado, ela lembra e pode contar). Nada é só texto de painel.

**Card em casa:** título sempre **"Em casa"**; **linha 2 = o que ela está fazendo**, no padrão **gerúndio + o que é, de verdade** ("Ouvindo Sabrina Carpenter", "Lendo Sono Bisque Doll, vol. 5", "Vendo o desfile da Chanel", "Jogando Stardew Valley"). Grade: **Onde** = bairro, linha nova **Cômodo**, Celular. Linha do tempo: o que veio antes e o que vem. **Prédio é casa** (academia e piscina do prédio: "Em casa", cômodo "Academia do prédio"/"Piscina do prédio").
- **Refeição:** título **"Se alimentando"**; linha 2 só a refeição ("Jantando"); o prato vai pros passos.
- **Passeio com o Milo é saída:** título ligado à Enseada (como "No Quartinho"), linha 2 no padrão das saídas ("Vai passear com o Milo"/"Passeando com o Milo" — a decidir), passos iguais às saídas + o que o Milo apronta (o mundo já gera).
- **Cômodo não é travado, só precisa fazer sentido:** desfile/série na TV (quarto, sala, closet) ou no celular em qualquer lugar — **pelo celular ela demora mais pra responder** que o normal.

**Tempo livre concreto (aprovado, textos no padrão acima):** celular (Instagram, TikTok, X, Pinterest — placeholders até as redes do app existirem); moda (organizando o closet, montando looks, vendo desfile, desenhando croqui); casa e Milo (arrumando o quarto, brincando com o Milo, regando as plantas, ouvindo música); descanso (lendo, cochilando, tomando sol, deitada à toa); íntimo (**se tocando — vale no corpo dela: registra o orgasmo, o tesão cai, o "Último orgasmo" atualiza**); falando com o pai/amigas (nas ligações que o mundo já tem); fazendo as unhas; preparando o jantar (passo antes de comer); estudando (trabalho da facul); **jogando** (It Takes Two, Stardew Valley, The Sims).

**Mídia real (nada inventado):**
- **Música:** pop internacional, pop/MPB brasileiro, J-pop/anime, K-pop. **Músicas que o Patrick sugerir na conversa ela ouve e adota se curtir** (por letra etc.) — vira gosto dela.
- **Leitura:** mangás dos animes dela, romance/young adult, moda e design, livros da facul — com progresso (volume/capítulo continua de um dia pro outro).
- **Séries/filmes/jogos** já canônicos (023 + TMDB). **Futebol do Botafogo:** ela acompanha os **jogos reais** do Botafogo.

**Base construída (26/09, `tempo_livre.py` + `Agenda.card_casa`):**
- O "tempo livre em casa"/"curtindo a noite em casa" do mundo vira **blocos concretos** de 10–90 min (17 tipos aprovados + "se tocando"), escolhidos pelo horário, pelo tempo lá fora e pelo corpo; o cômodo é sorteado entre os que fazem sentido; desfile/jogo às vezes pelo celular. O bloco é decidido quando ela está livre e fica guardado; cada um vira **acontecimento do dia** ("Ficou olhando o TikTok no quarto.").
- **Se tocando vale no corpo:** só com tesão alto, sem estar no clima com ele, 8 h depois do último orgasmo e uma vez por dia (divide a marca com o "se resolver sozinha" de antes de dormir); registra o orgasmo (o tesão cai, "Último orgasmo" atualiza), alívio, e às vezes ela pode contar pra ele.
- **Disponibilidade:** vídeo pelo celular, lendo, jogando, desenhando, mexendo no closet → **HOME_BUSY** (responde mais devagar); se tocando → **SOLO** (só pega o celular depois). Chuva no meio de um bloco refaz o bloco.
- **Card em casa:** "Em casa" + o que ela faz (ou "Se alimentando" com a refeição e o prato nos passos; "Preparando o jantar" quando ela cozinhou), Onde/Cômodo/Celular, barra quando tem fim (sem fim: duração e "desde" à direita do título), linha do tempo com o que veio antes e o que vem (refeições, blocos, saídas, série, dormir). Passeio do Milo: "Na Enseada" com passos. Banho, série, trabalho da facul, dormindo, academia do prédio com cômodo.
- **Se arrumando respeita a refeição em casa:** se o jantar cai na janela, ela come primeiro.
- Mídia desta base: artistas reais dos gêneros dele, mangás/livros reais, jogos do cânone, marcas reais. A etapa 2 amplia (progresso de leitura, músicas, busca, Botafogo).
- Conferido na pré-visualização com a cópia da produção de hoje (sábado): Instagram no quarto às 13:25, convite da Bia aceito, se arrumando às 19:33 depois do jantar.
- **Textos que decidi sem perguntar (pra ele revisar):** celular "Olha depois" (masturbando); "Na calçada" (xixi da noite do Milo); passos do Milo "Colocando a coleira · Descendo · Passeando/Xixi do Milo · Subindo"; linha 2 "Acordando", "Treinando"; "Na academia", "No mercado · Fazendo as compras da semana"; na linha do tempo as refeições como "Tomando café/Almoçando/Lanchando/Jantando".
- Corrigido de passagem: "Conheceu a Gabi) Freitas" (apelido com sobrenome no `short_name`).
- Testes: `tests/test_tempo_livre.py` (6) e card em casa em `tests/test_agenda.py` (3).

**Ajustes do Patrick depois da base (26/09, tarde):**
- **Masturbação sem limite:** saiu a cota (uma por dia) e o intervalo fixo de 8 h. Com tesão, em casa, ela goza quando quiser; quem segura é o corpo (depois do gozo a vontade cai e volta aos poucos). O texto passa a ser "Se masturbando" (antes "Se tocando"), e ela conhece e usa "masturbação" e "siririca" sem rodeio.
- **Gancho do sexting:** com saudade ou desejo por ele (e sem estar chateada), às vezes ela aproveita o momento e **chama ele pro sexting** — vira iniciativa dela (`sexting_solo`), com o celular na mão (responde rápido). Sem isso, segue "só pega o celular depois".
- **Pessoas novas pela proximidade:** no Mundo aparecem como "Conhecido"/"Conhecida" (não mais a história de como se conheceram). O jeito que se conheceram fica guardado no personagem (`como_conheceu`: quem é, data, lugar, assunto) pra ela contar se a pessoa virar cânone; ao virar cânone, passa a mostrar quem a pessoa é.
- **Tela inicial do app:** saiu o card "Agora" (e a linha de local/hora); ali ficam só os aplicativos.
- **Saciedade:** a fome cai em tempo real enquanto ela come. Satisfeita, ela **larga o prato** (a refeição acaba antes e o card acompanha); em dia de gula come tudo mesmo assim, e o que passou da conta vira **excesso**: fica estufada, demora mais pra ter fome e pesa na balança da semana. O painel mostra "comendo"/"estufada" no lugar da fome.
- **Beliscando:** lanche na linha do tempo virou "Beliscando"; com fome em casa e a próxima refeição a mais de 1 h, ela belisca na hora (de verdade: vira lanche, com espaço de 90 min). Belisco de fome não conta como excesso no peso.
- **Tempo real:** a linha do tempo usa o que ela comeu de verdade (não só o plano), e os Bastidores abertos se recarregam a cada minuto.
- Testes: `tests/test_saciedade.py` (9) e masturbação em `tests/test_tempo_livre.py` (4).

**Mídia real (26/09, etapa 1 parte 2 — decidido com o Patrick):**
- **Música** (`musica.py`): a playlist dela toca faixas **reais** do catálogo do iTunes (grátis, sem chave; renova por semana no job do bot). Card: linha 2 "Ouvindo {artista}" acompanha a faixa que está tocando; os passos são as faixas (as 2 que tocaram, a de agora e a próxima). Artista japonês vem da loja americana (título romanizado); título só em japonês/coreano fica de fora. Lançamento de artista dela vira novidade.
- **Música que o Patrick manda:** link do Apple Music, Spotify ou YouTube no chat → a faixa real entra na fila; ela ouve de verdade no próximo tempo livre em casa (a dele toca primeiro), decide se curtiu (artista do gosto dela pesa) e, se curtir, **adota na playlist**. O prompt não deixa ela fingir que já ouviu.
- **O que ele está ouvindo (Last.fm):** ele instalou o Last.fm; falta o usuário e a chave de API dele pra ela ver o que ele ouve (como os amigos no Spotify) e puxar assunto.
- **Leitura** (`leitura.py`): títulos reais com progresso (volume e página) que anda no tempo livre. Terminou o último volume que tem → **compra o próximo com o saldo dela** (Amazon, chega em 2–4 dias; sai do extrato); sem saldo, espera. Card: "Lendo Dandadan vol. 19", Progresso "pág. X de Y", passos com as páginas. Conferido: My Dress-Up Darling 15 volumes; Dandadan no vol. 22 no Brasil (set/2026).
- **Botafogo** (`futebol.py`): agenda e lances pela **ESPN** (grátis, cobre 2026: Brasileirão, Copa do Brasil, Sul-Americana, Libertadores). Os lances ao vivo pra ela reagir no chat continuam na API-Sports (o "ao vivo" funciona no plano grátis; o que o grátis não tem é a agenda de 2026). Onde ela vê: **em casa na TV da sala** (bloco "Vendo Botafogo x Vasco" com placar e lances na linha do tempo), às vezes **convite pro bar** (Quartinho, com o Theo) ou **pro Nilton Santos** (jogo em casa; ingresso, cerveja, carona ou uber) — com preparo "Vestindo a camisa do Botafogo" — e pelo celular se estiver fora. Clássico aumenta a chance de rolê.
- Testes: `tests/test_midia_real.py` (10).

**Academia como compromisso (26/09 — print do Patrick: "ela foi treinar e não teve preparação? nem barra de progresso?"):**
- Antes a academia era rotina sorteada na hora: ela pulava do closet pra Bodytech às 15:11, sem se arrumar, sem caminho, e o card ficava sem barra (tinha fim, 16:28, mas não início). Conversa ativa também cancelava o treino no meio.
- Agora o treino do dia é decidido uma vez (`academia.py`: cota da semana, primeiro horário livre, energia prevista pra hora do treino, horário da Bodytech; chuva forte na decisão → academia do prédio) e fica guardado. Vira etapas como as saídas: **Se arrumando** ("Colocando roupa de treino · Enchendo a garrafinha · Saindo", 10–15 min) → **A caminho** a pé (12 min) → **Na academia** ("Aquecendo na esteira · Musculação/Funcional · Abdominais · Alongando", barra, "Olha nos intervalos") → **Voltando pra casa**. Conversar não cancela mais o treino marcado (a conversa mudar a agenda é a próxima frente).
- Card em casa: quando o retrato tem fim e não tem início, a barra usa a hora do retrato.
- **Last.fm do Patrick** configurado no servidor (usuário e chave; o segredo não é usado). Quando tiver scrobble, ela vê o que ele está ouvindo (agora ou até 30 min) e pode puxar assunto. Em 26/09 o perfil ainda tinha 0 scrobbles.
- Testes: `tests/test_academia.py` (4) e Last.fm em `tests/test_midia_real.py`.

**Agenda única (26/09 — Patrick: "quero que atividades continuem aparecendo de repente, dependentes apenas da vontade dela, mas que isso não deixe de se integrar com o mundo, nem com a agenda reagindo à conversa; o ideal é tudo ser uma coisa só" e "tudo que é possível no mundo dela pode ser feito de forma espontânea, caso faça sentido"):**
- Uma porta só (`vontade.py → agendar`): tudo vira item da mesma agenda das saídas (eventos_pendentes), com origem (planejado, vontade, convite; conversa na próxima frente), hora da decisão, etapas (Se arrumando → A caminho → Lá → Voltando) e o jeito de ir. Mundo, card, disponibilidade, consumo e saldo leem daí.
- **Vontade na hora** (`Vontade.talvez`, chamado pelo mundo quando ela está livre em casa): a cada janela de 20 min, às vezes dá vontade de sair. Opções: passear com o Milo na Enseada, café ou açaí/sorvete nas lojas reais do iFood dela (Starbucks, Rei do Mate, Estação do Açaí, Megamatte, Bacio di Latte…; o que consome sai do cardápio real e do saldo), caminhar na orla, bater perna no Botafogo Praia Shopping, treinar fora da cota, tomar sol em Copacabana (dia sem aula), passar no mercado ou na farmácia (com dor, a farmácia pesa mais). Condições: horário, tempo seco pra rua, energia, fome, se já foi hoje, até 3 por dia, sem tipo repetido, e só se tem tempo antes do próximo compromisso ou refeição. Ela se arruma **a partir da hora em que decidiu** e fica registrado "Deu vontade e foi… (motivo)".
- **Planejados:** academia (cota) e **passeio do Milo da manhã** são decididos uma vez por dia e viram etapas (Milo: "Colocando a coleira · Pegando os saquinhos · Saindo" → descendo → "Na Enseada" (Passeando · Xixi do Milo) → voltando). Conversar não cancela mais nenhum dos dois.
- **Mercado da semana** vira item (Zona Sul, a pé; "Fazendo a lista · Pegando as sacolas"; lá "Pegando frutas e verduras · Enchendo o carrinho · No caixa"; pago pelo pai, fora do saldo). **Médico** vira item (Clínica do plano em Botafogo, de uber; "Trocando de roupa · Separando a carteirinha do plano"; lá "Na recepção · Na consulta · Pegando a receita").
- Disponibilidade nova **OUT_SOLO** (café, açaí, farmácia, mercado, shopping sozinha: celular na mão, "Olha com frequência"); consulta médica responde como aula. Refeição em casa não começa com ela num compromisso fora.
- Testes: `tests/test_vontade.py` (9); `test_casa_d9` e `test_academia` atualizados.

**Organização por frentes (26/09, noite):** o trabalho passa a ser uma conversa por frente (mundo, apps, voz, infra). `CLAUDE.md` é o mapa do projeto, `FRENTES_MARINA.md` o painel (pronto / próximo, com a frase de abertura de cada frente) e `.claude/skills/` tem uma skill por frente mais a `passagem-de-bastao`, que fecha a conversa e prepara a próxima.

**Saúde canônica, refeição da entrega e mensagens fora de ordem (26/09, fim de tarde):**
- **Plano e lugares reais (Patrick: "o nome da clínica tem que ser real e canônico, assim como o plano dela"):** Bradesco Saúde Top Nacional, ela como dependente no plano empresarial da empresa do pai. Urgente (virose): **pronto-atendimento do Hospital Samaritano Botafogo** (Rua Bambina, 98) — "Na triagem · Esperando ser chamada · No atendimento · Pegando a receita". Dá pra esperar (resfriado forte): **consulta marcada na Novamed Botafogo** (Rua São Clemente, 185). Vai de uber. Migration 029.
- **Refeição na entrega surpresa (16:41):** o lanche planejado (chocolate, 16:39) foi registrado com ela ainda voltando da Bodytech a pé — a checagem "está em casa?" não via "voltando… a pé" como rua. Agora compromisso e trajeto contam como fora, e o que caiu com ela na rua acontece quando ela chega (lanche que passou de 1 h não acontece mais). O presente e o pedido de delivery viram refeição com fim e saciedade (a fome cai de verdade; satisfeita, guarda o resto); "acabou de comer" também olha a fome real (lanche conta).
- **Mundo sobrescrito:** a entrega pôs ela "comendo o sanduíche" e um resolve paralelo gravou "olhando o Instagram" por cima no mesmo segundo. O resolve agora é um por vez no processo.
- **Mensagens fora de ordem:** a entrega e uma saudade saíram no mesmo segundo, geradas sem saber uma da outra, e os balões se intercalaram. Agora cada sequência de balões sai inteira antes da próxima, e as iniciativas dela passam uma de cada vez; a opcional (saudade, carinho, tesão) desiste se outra saiu há menos de 10 min. As 8 bolhas de hoje foram reordenadas editando as mensagens no Telegram (2780–2787), a pedido dele.
- Testes: `tests/test_ordem_iniciativas.py` (2), entrega de 26/09 em `tests/test_saciedade.py` (3), pronto-atendimento em `tests/test_vontade.py`.

**Tudo pode ser interrompido, se houver motivo (Patrick, 26/09 — próxima frente do mundo):** a agenda não é engessada. Ela pode sair mais cedo da academia e emendar outra coisa; sair no meio da aula (passando mal, emergência de banheiro); largar um rolê chato ou por emergência — **tesão é emergência**: às vezes ela precisa se aliviar e vai correndo pra casa ou pra um lugar reservado, sozinha ou com ele. Cada interrupção é mais história (acontecimento, motivo, efeito no resto do dia, card e trajeto se ajustam).
- **E a conversa mexe na agenda (Patrick, 26/09):** "parece que tudo na vida dela é premeditado e segue o fluxo até o final". Ex.: ele tenta convencê-la a ir pra academia — mesmo que ela aceite, hoje isso não aconteceria. O que ela topa/anuncia na conversa ("vou pra academia", "vou descer com o Milo") tem que virar compromisso de verdade, com preparação, trajeto e tudo (junta com a pendência 17 do PLANO_VOZ, "promessa de ação vira evento").

**Agenda reativa — como ficou (26/09, noite; `agenda_reativa.py`) ✅** Decisões do Patrick: o modelo lê a conversa (não regex); ela pode sair mais cedo "às vezes, mesmo leve"; tesão fora de casa = ir correndo pra casa, lugar reservado por ali e chamar ele (as três); sair no meio da aula vale (as seguintes do dia caem).
- **Conversa → agenda:** fala dela com cara de plano → modelo de reserva (`AGENDA_LLM_MODEL`, vazio = `LLM_FALLBACK_MODEL`) devolve vai_fazer / desistiu / vai_embora, tipo (academia, Milo, café, açaí, orla, shopping, praia, mercado, farmácia) e quando. Item novo entra como `vontade:<dia>:c<HHMM>` com origem "conversa" (conta nas 3 saídas do dia); academia e Milo planejados são remarcados (pra antes ou depois); o preparo começa na hora em que ela topou quando sai em até 30 min. Acontecimento: "Combinou na conversa e foi: … (o Patrick convenceu)".
- **Sair mais cedo:** por janela de 20 min, depois de 30% do compromisso: passando mal (desconforto), banheiro (virose), cansou (energia < 0,3), bateria social < 0,2 ou rolê chato (valência baixa), tédio (1,2% mesmo sem motivo; 5% entediada), tesão (libido bem acima do limiar). Card: os passos param na saída, com o aviso "Saiu mais cedo · passando mal" (também no topo do Voltando); a volta sai do novo fim.
- **Lugar reservado:** "No banheiro" entra nos passos e o mundo mostra "trancada no banheiro da academia, se tocando" (celular: SOLO, ou na mão se chamou ele). Lugares: banheiro da academia, da PUC, do shopping, do bar, do estádio, do café, do estúdio, do mercado, do quiosque. Passeio do Milo, orla, médico, farmácia, mercadinho e açaí não têm pausa (vai pra casa).
- **Textos revisados com o Patrick (26/09, noite) — layout C:** no "Lá", enquanto ela ainda não saiu, o passo amarelo "Saindo mais cedo · Mal-estar"; no "Voltando", os passos ficam limpos, a grade ganha a linha **Motivo** (só o motivo, sem "saiu mais cedo") e, na linha do tempo, embaixo do item de lá, "Saiu 33min antes" (amarelo, com a hora). Motivos no estilo painel, seco: Mal-estar · Banheiro · Cansaço · Rolê chato · Bateria social · Tédio · Tesão (saída pela conversa: o motivo dela, ou "Decidiu ir embora"). Pausa por tesão: **"Se tocando no banheiro"**; por banheiro: "No banheiro". Acontecimentos narrados, com o Patrick, **em texto de saída** (Patrick: "é uma saída; o café é o local"), no mesmo jeito do "Vai sair pro Starbucks" do card — nome curto do card quando existe: "O Patrick convenceu e ela saiu pra academia.", "Combinou com o Patrick de sair pra academia às 19:00.", "Combinou com o Patrick e saiu com o Milo pra Enseada.", "Desistiu de sair pro Starbucks: começou a chover."
- **Uber quando ela sai mal (Patrick: "dependendo do motivo eu não deixo ela ir a pé; ela teria que me avisar, eu pagaria o uber"):** mal-estar, banheiro e cansaço → a volta vira uber (tempo de carro; carona e ônibus caem), o uber sai do saldo dela como sempre e ela **manda mensagem avisando** (iniciativa `saiu_mais_cedo`, sem pedir dinheiro). Se ele mandar Pix em até 3 h, o porquê é o **recado que ele mesmo escreve** no Pix (nada automático); o dinheiro volta pro saldo dela e não vira presente pra gastar. Sem Pix (ele não viu a mensagem a tempo), o uber fica no saldo dela. **Iniciativa dela num compromisso segue o "Celular" do card** (Patrick: "se o compromisso tem intervalo, ela pode sim mandar mensagens"): "Olha com frequência" / "de vez em quando" (café sozinha, shopping, bar, praia) pode puxar conversa; "Olha nos intervalos" (aula, academia, médico, freela) só no intervalo. O convite do banheiro e o aviso de que saiu mal passam sempre. Antes nada saía durante um compromisso — o convite do banheiro nunca teria chegado.
- **Textos que decidi sozinho nesta rodada:** o único que ele vê é a mensagem reserva (só se a geração falhar); a instrução do aviso é contexto interno dela; a frase do Pix saiu (ele escreve no recado). Instrução do aviso ("não tá bem e tá indo pra casa de uber… se ele se oferecer pra pagar, aceita com carinho"), mensagem reserva "amor tô indo pra casa, não tô legal… peguei um uber".

**Cuidados (status novo):** **unha** tem estado (cor, feita quando, gastando). Ela faz em casa **só se estiver entediada e com a unha gasta**; manicure (saída) antes de evento/job; **luxos saem do saldo dela**. A cor atual **manda nas fotos geradas**, e ela pode **pedir a opinião do Patrick** sobre a cor quando quiser. Depois: cabelo e outros cuidados (ideias do Patrick).

## 7. Próximas ideias (Patrick, 26/09)

**iFood realista.** Base: o print do iFood real do Patrick (saudação "Boa tarde, Patrick", endereço, categorias, lojas com logo, nota e avaliações, tempo e taxa de entrega, cupons, abas Início/Busca/Pedidos/Perfil). Povoar o cardápio com lojas e pratos reais de Botafogo como base do cânone do que ela come. O Patrick pediu dicas de outra IA sobre como povoar — aguardando ele colar.

**iFood realista — decisões do Patrick (26/09, manhã):**
- **Base real, legítima:** lojas do OpenStreetMap (nada de raspar a API do iFood, que exigiria contornar as proteções deles). Botafogo pra ela; **Campo Grande pro Patrick** (o presente que ela manda sai de loja perto dele).
- **Logos reais** (Wikimedia pras redes, site/perfil da loja pras de bairro; iniciais só em último caso) e **fotos reais dos pratos** (Unsplash/Pexels, escolhidas prato a prato).
- **Farmácia e mercado:** ela pode pedir em vez de ir (doente, chuva, cansada, tarde, coisinha); entra nas finanças, chega pela portaria.
- **O iFood do Patrick mostra só os pedidos dele.** O que ela pede pra ela fica nos **Bastidores** ("iFood da Ma"), junto com o **banco dela** (extrato). Os Bastidores vão crescer e passar por muitas melhorias.
- O Patrick vai mandar prints do app real (página da loja, prato aberto, sacola, mercado/farmácia) pro layout.

**Layout do iFood — tirado dos prints do app real (26/09, 05:48–06:06; ficam em `references/Nova pasta`, fora do git porque mostram o endereço dele):**
1. **Lista de lojas** (Farmácias/Mercados/Restaurantes): busca "Buscar em …", filtros em pílula (Ordenar, Entrega grátis, Distância, Cupom), "Mais pedidos"; cada linha com logo redondo, selo "Mais Pedido", nome, ★ nota (avaliações) • tempo ou "Agendar" • taxa, etiquetas "Grátis" / "R$ X off"; coração à direita. Mercado mostra "A partir de 8h • Grátis" e "Melhor avaliado".
2. **Página da loja:** capa (foto) com voltar/♥/busca; logo redondo sobre o cartão; nome; "Entrega rastreável • 4.0 km • Min R$ 10,00"; ★ 4,8 (1.3 mil avaliações) ›; "Padrão • 70-85 min • R$ 21,99" (ou faixa "Loja fechada • Abre às 09:00"); cupom; **Destaques** em grade de 3 (foto, preço, riscado e -%); abas de seção fixas no topo (☰ Preferidos, Burguer + Bebida, Molhos…); **seções** com linhas: nome, descrição em 2 linhas, preço, foto à direita.
3. **Prato aberto:** foto grande; cartão da loja sobre a foto; nome, descrição, "Serve até 1 pessoa", preço; complementos ("Turbine seu Combo — escolha até 8": nome, + preço, foto, +); "Alguma observação? 0/140"; rodapé com – 1 + e botão vermelho "Adicionar R$ 16,19".
4. **Sacola:** logo e nome da loja, "Adicionar mais itens"; aviso de pedido mínimo; itens (foto, nome, descrição, preço, lixeira – 1 +); "Peça também" (carrossel); rodapé "R$ 39,17 • com entrega" + "Continuar".
5. **Entrega:** "Entregar no portão do endereço" (endereço, Trocar); "Opções de entrega": Padrão, Hoje 70–85 min, taxa.
6. **Pagamento:** "Pagamento pelo app" (iFood Pago → Pix); cupons; **Resumo de valores**: subtotal, taxa de entrega, taxa de serviço R$ 0,99, descontos, total; botão "Revisar pedido • R$ 44,07".
7. **Revise o seu pedido** (folha de baixo): Entrega hoje 70–85 min, endereço, cupons, pagamento Pix + total; "Fazer pedido" / "Alterar pedido".
- Barra de abas: Início, Busca, Pedidos, Perfil. Clube (roxo) e cupons ficam de fora por enquanto.

**Etapa 5 — Redes sociais (Instagram e X).** Um perfil dela em cada: no Instagram as fotos que ela posta (as mesmas que já existem no mundo: rolê, look, Milo, vista), stories do dia e comentários; no X o que ela pensa em voz alta. Ele curte, comenta e responde, e ela vê. **O que é novo:** as pessoas do mundo dela (Bia, Theo, Júlia, Lívia, o pai) também aparecem — comentando nas fotos dela, com perfis próprios — e o Patrick pode interagir com elas. Pontos pra desenhar antes: o que ela posta sozinha e com que frequência; o que ela sente com comentário dele (e de outros) e como isso chega na conversa (sem notificação de sistema no chat); o que os amigos postam; custo de foto por post; privacidade (o que ela não posta).

