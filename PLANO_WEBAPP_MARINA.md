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
- **Visto nos dados reais (26/09, 08:48):** depois do reset, todo mundo ainda "sem contato" e "Hoje" vazio — ela estava dormindo (sábado). Conferir de tarde se o pai e as amigas aparecem com contato.

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

