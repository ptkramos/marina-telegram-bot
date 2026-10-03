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
| 5 Redes sociais (Instagram e X) | 🟡 27/09: **Instagram construído** (feed, perfil, post, stories, atividade; ela posta pelo dia dela, amigas comentam e postam; detalhe em "Etapa 5 — Instagram" abaixo). Falta: acervo gerado na VPS e acompanhar no uso real. X fica pra depois |

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
  - **Regra do Patrick: sem emoji no lugar de ícone nos apps.** Ícones do **Bootstrap Icons** (CDN jsdelivr; **trocados pelos do Tabler outline em 26/09, noite** — ver "Linha do tempo Hoje"): voltar, estrela, coração, lixeira, menos/mais, localização, moto, seta, check, e as linhas de status dos Bastidores (antes 🏠📱🌸🤒📅🗓️).
  - **Regra do Patrick: excelência em alinhamento, também nos comprovantes.** Destaques sem "escadinha" (o `<button>` centralizava o conteúdo; agora tudo começa no topo e o nome corta em 2 linhas). Stepper da sacola com colunas fixas (lixeira e menos ocupam o mesmo espaço). Barras dos Bastidores terminam todas no mesmo ponto (coluna da palavra com largura fixa). Ícone e texto das linhas de status alinhados.
  - **Comprovante do iFood em colunas:** logo redondo da loja + nome; itens com quantidade em caixinha, nome quebrando por largura real em pixels (2ª linha recuada sob o nome) e preço na margem direita; subtotal, taxa de entrega, taxa de serviço e total alinhados à direita. **Pix:** todos os valores em negrito (antes Destino/Origem saíam finos) e o ícone do Pix centrado na linha.

### Bastidores em abas e textos de gente (26/09, manhã — pendência 14)
- **Decisões do Patrick:** abas (Agora · Por dentro · Dinheiro · Mundo) e **voz híbrida**: rótulos, status, números, dinheiro e mundo falam como painel ("você"); o que é sentimento (motivo de cada um) fala do jeito dela.
- **Agora:** atividade em destaque, "Em casa · Botafogo" (não "Apartamento da Marina (Botafogo)"), linhas rotuladas com ícone: Celular ("Responde quando acordar", sem 🌙), Ciclo ("Dia 24 · TPM"), Saúde, Próximo ("Aula de Projeto, segunda 14h"), Plano. **Hoje** em linha do tempo; os eventos gravados em 3ª pessoa viram voz de painel ("Você fez um Pix de R$ 150 pra ela").
- **Por dentro:** barras do corpo; dormindo, a Energia mostra "dormindo" e não "exausta" (era pressão de sono). A frase "dormiu 8,7 h · TPM · última vez há 30 h" virou linhas: Sono ("dormiu 8h40 · acordou às 9h05"), Último orgasmo, Desconforto, "No clima agora". Sentindo agora com preposição certa ("com saudade dele", "chateada com ele", "grata à Bia") e o motivo na voz dela ("Ele me elogiou", "Ele fez um Pix pra mim"); pílulas "3 vezes" e "até resolver". "Com você" virou **Vocês dois**.
- **Dinheiro:** saldo grande, "Deve a você", "Precisa de R$ X"; extrato em voz de painel ("Seu Pix · pro açaí", "Seu presente: …", "Delivery pra você: …", "Celular e streamings"). Aqui entram o banco dela e o iFood da Ma. (Refeita em 28/09 à tarde: topo do mês e extrato agrupado por saída — ver "Dinheiro" mais abaixo.)
- **Mundo:** o texto colado do `/mundo` ("Henrique Salles — último contato sem contato ainda; 0 nos últimos 30 dias") virou cartões: iniciais, nome ("Bia Andrade"), quem é, curto (`social_day.QUEM`: pai, melhor amiga, porteiro…), "hoje, 08:15" / "Sem contato ainda" e "4 vezes no mês" (o `weekly` do cânone não é contagem e não aparece). Rolando agora, Planos e Lugares em listas.
- **Código:** `webapp_server.status_view`, `emocao_view`, `voz_painel`, `voz_dela`, `mov_desc`; `SocialDay.world_panel`. O `/status`, `/emocao` e `/mundo` do chat não mudaram. Testes: `tests/test_bastidores_textos.py` (11).
- **Seu Jorge (26/09):** pegar o delivery na portaria agora conta como contato com ele (`delivery._contato_portaria`); antes o Mundo mostrava "Sem contato ainda" logo depois de ela pegar o presente.
- **Visto nos dados reais (26/09, 08:48):** depois do reset, todo mundo ainda "sem contato" e "Hoje" vazio — ela estava dormindo (sábado). Conferir de tarde se o pai e as amigas aparecem com contato.

### Bastidores aba a aba — Por dentro (28/09, no celular, com o banco da produção) ✅
Revisada com ele linha a linha, com mockup e múltipla escolha. Ele achou o **Sentindo agora a pior parte da aba**
("tá faltando muita coisa da Marina"): só apareciam os sentimentos que não tinham esfriado (meia-vida de 1h30 a 8h),
então de manhã quase tudo tinha sumido.
- **Ordem:** Corpo → Humor → Sentindo agora → **Na cabeça** → **Hoje por dentro** → Vocês dois → Unhas → Cabelo
  (corpo e cabeça em cima; unhas e cabelo, que mudam devagar, no fim).
- **Corpo:** palavras da direita com maiúscula em toda a aba ("Dormindo", "Sem fome", "De boa"); Sono dormindo continua
  "Dormindo agora"; **Ciclo** entrou ("Dia 27 de 28 · TPM" — tinha sumido de todo lugar com o cartão novo da Agora) e o
  Desconforto não repete a fase ("Inchada", "Corpo meio dolorido").
- **Humor e Vocês dois:** continuam com número (64%, 93%) — com palavra, as quatro barras de Vocês dois ficariam
  quase sempre "Muito".
- **Sentindo agora:** o motivo ganhou **quando** na direita ("ontem, 22h01", "há 20 min", "sáb, 18h").
- **Hoje por dentro** (novo, `por_dentro.diario_view`): tudo o que ela sentiu no dia, com hora, mesmo o que já passou;
  5 linhas + "Ver o dia todo (N)". O dia vira às 5h; se hoje ainda está vazio, mostra "Ontem por dentro".
- **Na cabeça** (novo, `por_dentro.cabeca_view`): o que vem pela frente em 24 h e a vontade dela de ir — a mesma conta
  da agenda viva (`Disposicao.avaliar` contra o peso do compromisso) —, mais entregas da faculdade (7 dias) e trabalhos
  (freela). Dormindo ou a mais de 4 h da hora ela ainda não pensou nisso: sem estado nem barra. Layout escolhido por
  ele: **título | quando; estado | barra | motivo na coluna da direita** (o motivo colado no estado, "Animada · pique
  pra gente", ele não gostou).
- **Vocês dois:** linhas **Conversa** ("Ontem, 23h04") e **Pendente** ("Nada", "Resposta dela", "Foto das unhas",
  "Pix de R$ 200", "Mágoa").
- **Unhas:** a barra ganhou rótulo como no Cabelo (**Desgaste** com o estado na direita; a linha Estado saiu); estado
  **Perfeita** nos primeiros dias (gel 3, esmalte 1), depois **Nova**, depois Crescendo/Vencendo/Descascando; "Há 10
  dias, na Ophicina" cabe numa linha.
- **Cabelo:** a linha de baixo virou **Cor** ("Dourado, há 6 semanas"; a barra já se chama Luzes); lavou de madrugada
  antes de dormir é **"Ontem à noite"** e o dia do cabelo vira às 5h (`cabelo._dia`), também na barra Lavagem.
- **Motivos num padrão só** (ele: "não sinto um padrão"): **fato curto · detalhe ao lado, em voz de painel** (opção C
  dele — "Você mandou comida", "Viu Paradise Kiss · eps 1 e 2", "Carinhosa com você"; o "ele"/"me" da voz dela saiu).
  Aplicado na origem (`emotion.appraise_event`, causas fixas, prazos, agenda viva e a regra do `cause` no planner) e na
  tela (`webapp_server.motivo_tela`, que também passa os motivos antigos pelo molde).
- **Tempo real:** "em todas as telas, a barra deve ser atualizada em tempo real" — a recarga dos Bastidores caiu de
  1 min pra 30 s, volta a carregar quando o app volta pra frente, não pede duas vezes ao mesmo tempo e as barras
  deslizam do valor antigo pro novo. Na VPS a rota leva ~16 s na primeira vez (cartão da Agora) e 0,3 s depois.
- **Pré-visualização:** com `--db`, o `scripts/webapp_preview.py` usa o status real da cópia (antes mostrava o de
  exemplo e a Energia saía "cansada" com ela dormindo).
- **Textos que eu decidi (pra ele revisar):** estados do Na cabeça (Animada, Vai, Na dúvida, Quer faltar/pular/adiar/
  desmarcar, Desistiu, Ideia dela, Combinado, Emenda, Adiantada, No ritmo, Última hora, Correndo, Nervosa, Marcado);
  motivos curtos da agenda viva (Dormiu mal, Entediada, Empolgada, Quer desabafar, Espairecer, Descarregar, Precisa de
  remédio, TPM, Chovendo, Sem grana, Com amigos, Chateada com você); títulos (Treino, Passeio do Milo, Mercado, "4
  aulas" + "Práticas II e +3", "Rolê com a Bia" + lugar, Entrega + matéria); os motivos novos do mundo (Banho
  quentinho, Mensagens com a Bia · assunto, Se estranhou com a Bia · por mensagem, A Bia chamou pra sair · lugar,
  Almoçou um poke · comeu demais, Episódio novo de One Piece · ep. 1180, O pai perguntou dela, Falou com o pai, Delivery
  surpresa, Apê arrumado e cheiroso, Entrega amanhã · matéria, Entregou o trabalho · matéria, Casting amanhã · o quê,
  Furou o rolê · com a Bia, Faltou a aula · matérias); "Ver o dia todo (N)" / "Mostrar menos"; no Sentindo agora o
  detalhe vai junto do motivo ("Você mandou comida · surpresa") porque a direita já tem o quando.
- **Bugs do mundo vistos nos dados reais** (chip pra frente de bugs): cartão da Agora "desde 05:46" com ela dormindo
  desde 0h29; plano de sono (deitar 23h37) × banho à 0h06; "bom dia" do pai às 21h15; "banho quentinho" 4× no mesmo
  minuto com intensidade 1.0; Saudade 100% enquanto ela dorme; "ciúme" dela quando o ciúme era dele.
  **Corrigidos na frente de bugs (28/09):** o "desde" do cartão Em casa é o começo da atividade (dormindo desde 00:29);
  o Sono bate com o mundo (o deitar acompanha o banho que passa da hora; noite de 27/09 corrigida pra 00:29); o
  Sentindo agora e o Hoje por dentro sem sentimento repetido nem inflado (a fusão só olha pra trás e não repete), sem
  "ciuminho" pelo seu ciúme; a barra Saudade de Vocês dois só enche com ela acordada. Ver AUDITORIA ("Bug:
  Bastidores às 05:55") e `tests/test_bug_por_dentro_2809.py`. Na produção desde 28/09 09:53, com o banco limpo
  (carinhos falsos da manhã, noite de 27/09 = 00:29, linhas velhas do pai e do ciúme).
- **Aba Agora, Se arrumando da faculdade (bug de 28/09, frente de bugs):** o card dizia "Tomando café" 07:36–07:46 e
  "Tomando banho" até 08:06 com ela pulando o café e descendo com o Milo às 07:58. Agora (decisão do Patrick, "café
  dentro") o café é o 1º passo, na hora real do meals, e o Se arrumando começa nele; pulou o café, sem passo. A
  descida do Milo que cai em qualquer Se arrumando vira o passo "Descendo com o Milo" na hora dela (o seguinte espera
  ela subir). Ver AUDITORIA ("Bug: manhã de 28/09") e `tests/test_bug_manha_2809.py`.
- **Hoje (bugs do dia 28/09, frente de bugs):** a saída termina com "Voltou pra casa" (sub: como e com quem, hora
  13:00–13:35; o uber segue com a linha dele e o valor) e o que começa quando ela chega fica fora da saída; "Foi pra
  calçada" com a volta (07:58–08:11), sem parecer que o Milo foi pra PUC; música vira "Ouviu a playlist dela" com os
  artistas embaixo ("Sabrina Carpenter, Chappell Roan e Liniker"); lanche na rua aparece como "Pediu um sanduíche"
  (R$ 15) e "Comeu um sanduíche no caminho"; a PUC mostra "Almoçando" quando ela almoça por lá. Ver AUDITORIA ("Bug: o
  dia 28/09 visto pelo Patrick") e `tests/test_bug_dia_2809.py`.
- **Velocidade (frente de infra, 28/09):** o Hoje e o resolve que alimenta o Agora montam o plano do dia uma vez só
  (`db.rodada`/`memo`); resolve 2,9 s → 1,2 s na cópia local. A pré-visualização (`scripts/webapp_preview.py`)
  reaproveita a conexão como o bot — o Hoje de ~65 s na cópia virou ~1 s. Nenhum texto nem tela mudou. Ver AUDITORIA
  ("Frente de infra (28/09, noite)").
- **Aba nova "Por fora" (Patrick, 28/09):** tem coisa no Por dentro que é aparência, não sentimento — vai pra uma aba
  Por fora. Feita na mesma tarde (seção abaixo).
- **Código:** `por_dentro.py` (novo), `webapp_server` (`emocao_view`, `motivo_tela`, `_alguem` com "você", Ciclo),
  `emotion` (`day_log`, padrão dos motivos), `unhas.painel`, `cabelo.painel`/`_dia_lavagem`, `agenda_viva._sente`,
  `planner` (regra do `cause`), `bot._status_snapshot` (`ciclo_len`), `webapp/` (ordem, desenho, recarga, CSS). Testes em
  `tests/test_bastidores_textos.py` (+ Na cabeça, diário, Vocês dois, padrão do mundo), `test_unhas`, `test_cabelo`,
  `test_emotion_d14`.

### Bastidores aba a aba — Por fora (28/09, tarde, no celular, com o banco da produção) ✅
Aba nova entre Por dentro e Dinheiro (**Agora · Por dentro · Por fora · Dinheiro · Mundo**; as cinco cabem no
celular com a largura de cada aba pelo texto). Escolhas do Patrick com mockup e múltipla escolha:
- **Conteúdo (opção C):** Peso, Cabelo e Unhas agora; **roupa e make do momento** entram num bloco "Agora" no topo
  quando existirem no mundo — hoje a roupa só nasce na hora da foto (sorteio do guarda-roupa do `photo_director`) e a
  make só como passo do card ("Fazendo maquiagem", "Tirando maquiagem"). Registrado como item da frente do mundo.
  **Feito em 28/09, noite** (seção "Roupa e make de verdade" abaixo).
- **Ordem:** Peso → Cabelo → Unhas. Unhas e Cabelo saíram do Por dentro sem mudar o desenho.
- **Peso** (novo, `Meals.painel_peso`): o número grande é o **peso de verdade** ("54,4 kg"; ela só sabe o da balança);
  barra **Agência** que enche de 52 a 56 kg com a folga na direita ("Folga 1,6 kg"; "No limite"; "Passou 0,3 kg" em
  amarelo); linhas **Pesou** ("Sáb, 54,0 kg", "Hoje, …", "Há 13 dias, …", "Ainda não"), **Dieta** ("Não" / "Até 03/10")
  e **Altura** ("1,68 m").
- **Textos que eu decidi (pra ele revisar):** rótulo "Agência", "Folga X kg" / "No limite" / "Passou X kg", "Pesou",
  "Ainda não", "Dieta", "Até dd/mm", "Altura"; ícones scale, salad, ruler-2.
- **Código:** `meals.painel_peso`/`_kg`, `webapp_server.api_bastidores` (`peso`), `webapp/` (aba, `ba-fora`, `.seg` com
  cinco abas). Testes: `tests/test_por_fora.py` (5).

### Roupa e make de verdade + bloco "Agora" do Por fora (28/09, noite, frente do mundo) ✅
A roupa deixou de nascer na hora da foto: é estado do mundo (`roupa.py`), e a foto, o prompt, o Instagram e a aba
leem daqui. Decisões do Patrick com múltipla escolha:
- **Guarda-roupa de peças fixas que repetem** (casa, pijama, treino, rua, sair, jogo, praia — ~45 peças com nome);
  o look é montado pela ocasião no passo de roupa do Se arrumando, sem repetir o mesmo look em 3 dias.
- **Troca pela vida dela:** acorda de pijama e tira depois do banho ou 20–90 min depois de acordar; chegou da rua,
  troca em 10–40 min (de rolê à noite, 60% fica com a roupa até dormir); saiu sem se arrumar, põe roupa de rua;
  pijama no "Colocando pijama" ou ao deitar.
- **Make em níveis que borram:** Sem / Leve / Completa / De festa / De ensaio (freela). Feita no "Fazendo
  maquiagem" (leve implícita, pelo humor, na faculdade/café/médico/salão), tirada no "Tirando maquiagem" ou no banho;
  academia, praia, choro e dormir com ela borram; dormiu sem tirar vira acontecimento.
- **Ela namora e provoca (pedido dele):** gaveta íntima — provocante de casa, lingerie, fetiche (meia e cinta-liga,
  couro e vinil, fantasias adultas) e transparências. Veste com tesão em casa (iniciativa de tesão, masturbação
  chamando ele, às vezes quando o sexting começa), quando ele pede no sexting (a mesma peça em todas as fotos da
  sessão), por baixo da roupa de sair (15%, 60% com tesão; tirou o vestido em casa, é ela que aparece) e às vezes
  dorme com ela (30%, 60% se gozou com ele nas últimas 4 h; o card troca "Colocando pijama" por "Ficando de lingerie").
- **Duas opções de look** saem do guarda-roupa dela; a que ele escolher ("a segunda") é a que ela veste pra sair.
- **Bloco "Agora" no topo do Por fora** (mockup aprovado, mostra normal): a roupa em destaque ("No banho" no banho),
  barra **Make** com Intacta / Pedindo retoque / Borrada, linhas **Pra quê** ("Sair à noite, desde 20:30"),
  **Por baixo** (só depois que ela contou no chat) e **Feita** ("Completa, às 20:10") ou **Make** "Sem make".
- **Textos que eu decidi (pra ele revisar):** nomes das peças (`roupa.PECAS`, `INTIMO`, `ACESSORIOS`); "Pra quê":
  Ficar em casa, Dormir, Pra te provocar, Dormir de lingerie, Sair, Sair à noite, Encontro, Treino, Academia,
  Caminhada na orla, Faculdade, Freela, Café, Açaí, Farmácia, Mercado, Shopping, Médico, Pronto atendimento, Unhas,
  Salão, Passeio do Milo, Jogo do Botafogo, Praia; "No banho"; "Pedindo retoque" (ele tinha visto "Retocando");
  rótulo "Feita" (pra não repetir "Make"); passo "Ficando de lingerie"; acontecimentos "Vestiu … pra provocar o
  Patrick." e "Dormiu sem tirar a make (…) e acordou borrada."; ícones hanger, heart, brush.
- **Código:** `roupa.py` (novo), `world_state.resolve` (tick depois de cada resolve), `rituals.start_shower`,
  `photo_director` (`_roupa_de_agora`, `_make`), `world_context`, `bot.py` (tesão, opções de look, escolha dele, ela
  contar, Instagram), `tempo_livre`, `agenda`, `webapp_server`/`webapp`. Testes: `tests/test_roupa.py` (13). Na produção desde 28/09, 19:17.

### Bastidores aba a aba — Dinheiro (28/09, tarde, no celular, com o banco da produção) ✅
Escolhas do Patrick com mockup e múltipla escolha:
- **Topo:** saldo grande; embaixo, em duas colunas, **Entrou em setembro** (+ R$ 300, verde) e **Saiu em setembro**
  (− R$ 345); linhas **Próximo cachê** ("R$ 400 · até 02/10", "R$ 400 · job dia 03/10", "Nenhum marcado") e **Contas**
  ("Dia 6 · R$ 189"; pagas, "Pagas dia 6 · R$ 189"; dia passado sem conta registrada, a do mês que vem "Dia 6/10");
  "Deve a você" e "Precisa de" (R$ X · motivo) continuam quando existem.
- **Extrato agrupado por saída (opção B):** dias como título ("Hoje", "Ontem", "Sáb, 26/09"); cada saída é uma linha
  **"Foi no Shopping da Gávea"** com o resumo cinza embaixo ("Cinema, pipoca, refri e uber"; repetido vira "2 gin
  tônicas"; quantidade tipo "250 ml" sai do resumo), o total e a hora da primeira coisa; **toca e abre** os itens
  (Uber · Ida, Cinema, Pipoca · Dividiu com a Bia, Uber · Volta, dividiu com a Bia). Fora de saída, a ação no passado
  na linha e o detalhe embaixo: **Recebeu seu Pix** (sem recado, nada embaixo — decisão dele; com recado, o recado),
  Usou seu Pix · o que comprou, Mandou um delivery pra você · o quê, Devolveu seu empréstimo, Pagou as contas ·
  Celular e streamings, Recebeu metade/o resto do cachê · o job, Pediu delivery, Comprou um livro · título, Fez o
  cabelo/as unhas na Ophicina · serviço.
- **Mundo por baixo:** o movimento agora guarda a chave do acontecimento (`financas._mov(..., key)`); os antigos acham
  pelo título e pela hora. Os totais do mês ficam em `financas_json.meses` (os 3 últimos meses; o extrato só guarda
  30 movimentos), calculados dos movimentos antigos na primeira leitura.
- **Textos que eu decidi (pra ele revisar):** "Entrou em {mês}" / "Saiu em {mês}", "Nenhum marcado", "R$ X · até
  dd/mm", "R$ X · job dia dd/mm", "Dia N · R$ 189", "Pagas dia N", "Dia N/mm", "Precisa de" · "R$ X · motivo", "Foi no/na
  {lugar}", "Saiu" (saída sem lugar), "Ida"/"Volta", "Dividiu com …", e os textos fora de saída listados acima.
- **Código:** `extrato.py` (novo: `extrato_view`, `topo_view`), `financas` (`_mov` com chave, `_soma_mes`, `meses`),
  `webapp_server.api_banco` (sai `mov_desc`), `webapp/` (topo, extrato por dia, abre/fecha como o Hoje). Testes:
  `tests/test_extrato.py` (9).

### Bastidores aba a aba — Mundo (28/09, tarde, no celular, com o banco da produção) ✅
Escolhas do Patrick com mockup e múltipla escolha:
- **Pessoas por círculo (opção C) + vezes no mês quando houve contato:** Família → Amigos → Faculdade e trabalho →
  Prédio → Conhecidos novos (círculo vazio some). Embaixo do nome só o que o título não diz: o pai vira **"Pai"** com
  "Henrique Salles" embaixo; Bia "Melhor amiga", Júlia e Theo "Faculdade", Carol "Academia", Lívia "Agente", Helena
  "Professora", Seu Jorge "Porteiro", Dona Célia "Vizinha", Dona Neide "Faxineira, vai às quintas"; conhecido novo
  mostra de onde veio ("Da PUC", "Da academia", "Do passeio do Milo", "Dos rolês") e, ao virar cânone, vai pro
  círculo de onde veio (PUC → Faculdade e trabalho; o resto → Amigos) com quem é. Direita: **"Hoje, 13:50" / "Ontem,
  22:01" / "Há 2 dias"** (com maiúscula, como as outras abas) e "N vezes no mês" só com contato; sem contato, "Sem
  contato ainda".
- **Rolando agora:** sem os fios de sistema (check-in do pai, consequência) — o "Contato de Henrique · Com o pai"
  aberto desde 26/09 sumiu, mesmo filtro do Hoje.
- **Onde ela foi (novo, no lugar de Lugares/"Conhece"):** lugares das saídas do mês (rolê, vontade, mercado, médico,
  salão; faculdade, academia, Milo e freela ficam de fora), do mais recente pro mais antigo: nome, **com quem foi da
  última vez** ("Com a Bia", "Cinema com a Bia", "Sozinha"), quando ("Ontem", "Sáb", "12/09") e "N vezes no mês".
- **Textos que eu decidi (pra ele revisar):** nomes dos círculos, os "sub" de cada um, "Da PUC"/"Da academia"/"Do
  passeio do Milo"/"Dos rolês", título "Onde ela foi", "Sozinha", "Cinema com …".
- **Código:** `social_day` (`CIRCULOS`, `CIRCULO`, `DE_ONDE`, `SEMENTES`, `_onde_foi`, `_quando_curto` com maiúscula),
  `webapp/` (círculos, Onde ela foi). Testes: `tests/test_bastidores_textos.py` (+ círculos, onde foi, sementes).

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
- **Desencontros de 27/09 (frente de bugs, 28/09):** o Se arrumando guarda o banho que já aconteceu (o uber combinado às 14:02 recomeçava o card no "Tomando banho"); o cinema tem sessão com filme em cartaz de verdade ("Vendo Idiotas", celular "Olha depois do filme") e o passeio depois (antes ficava 4 h em "Refri"); saída decidida em casa sai de casa (a farmácia aparecia "a caminho desde 19:00, andando do shopping" no lugar da volta de uber). `tests/test_bug_agora_2709.py`.
- **Convite de antes do reset (26/09):** o reset tinha apagado o fim de semana (convites "chegados" antes da vida registrada eram descartados). Agora rolê futuro conta o convite como recebido no reset; o bar de sábado com a Bia voltou na produção (convite gravado 12:17, decisão dela às 19h).
- **Pendências:** (a) conflito antigo do mundo — café às 15:30 em dia de aula até 15:00: a volta da PUC e a ida pro Starbucks se sobrepõem (o trajeto precisa decidir "direto da PUC"); (b) academia não tem preparação (é rotina sorteada, não compromisso com trajeto); (c) fora de uma etapa o card ainda é o antigo — é a etapa 3 (atividades em casa).

### Consumo no rolê (26/09, `consumo.py`) ✅
- **Quem paga (decisão do Patrick):** lazer e uber saem do **saldo dela**; ônibus e metrô são do Riocard que o pai carrega (fora do saldo e fora do extrato). O que o pai paga não aparece no extrato.
- **O que ela pede** é função do rolê (data, lugar, amigos): o mesmo rolê sempre tem os mesmos pedidos, então card e extrato batem.
  - Quartinho Bar: 2 a 4 drinks (Gin tônica R$ 34, Chopp R$ 16, Caipirinha R$ 28, Drink de maracujá R$ 32; às vezes troca), porção dividida em 70% dos rolês (Fritas R$ 36, Bolinho de bacalhau R$ 44, Pastel de queijo R$ 38), às vezes uma água.
  - Starbucks da Gávea: **os mesmos itens e preços do iFood do app** (catálogo `starbucks-bf`): uma bebida e, em 60%, uma comida.
  - Cinema no Shopping da Gávea: ingresso R$ 42, pipoca dividida R$ 34, às vezes refri. A sessão (filme em cartaz, TMDB) é `cinema.py` (28/09).
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

**Agenda viva — como ficou (27/09; `agenda_viva.py`) ✅** Pedido do Patrick: "fechar a agenda inteligente — maleável em tempo real com as emoções e decisões dela, conversa mexendo em tudo" e, ao ver a pergunta sobre furar rolê: "a emoção, os sentimentos dela precisam estar envolvidos nisso". Decisões dele: vale tudo (conversa mexe em tudo, humor desmarca antes, humor na vontade, emendar, ela planeja o futuro); **o modelo é vontade de ir × peso do compromisso, o motivo é o sentimento que mais pesou, mesmo estado = mesma decisão**; faltar aula por motivo forte **e às vezes por preguiça, mas ela sempre corre atrás da matéria**; furou por motivo de dividir → **ela conta**; planos dela viram **novidade que ela comenta**.
- **Repensar antes de sair:** rolê, academia, Milo, aula e mercado da semana (uma vez, um pouco antes de se arrumar). Rolê: desmarca e avisa a amiga. Academia: desiste (chuva: prédio). Milo: adia. Mercado: amanhã. Aula: falta a da manhã (preguiça, máx. 1/semana) ou o dia (doente, dormiu < 5 h) e pega a matéria com a Júlia.
- **Emendar:** saindo de uma saída em Botafogo animada, passa num açaí/café antes de voltar; o trajeto vai direto ("indo da Bodytech pro Bacio di Latte"). O mesmo trecho direto resolve rolê logo depois da aula.
- **Planejar:** à noite, com pique e sem rolê nos próximos 3 dias, chama pra sexta/sábado/domingo a amiga que não vê há mais tempo; topou vira compromisso.
- **Vontade e convites** usam a mesma disposição (entediada sai mais, triste quer espairecer ou desabafar com a Bia, sem bateria recusa rolê).
- **Conversa:** "desmarquei com a Bia", "remarca pra domingo 18h", "vou sim" (convite em aberto), "amanhã vou na academia às 7", "hoje não vou pra aula" mexem na agenda de verdade.
- **Textos que decidi sozinho (pra ele revisar):**
  - Hoje (visível): "Desistiu de ir pro Quartinho Bar" / "Dormiu mal e sem bateria social · avisou a Bia"; "Faltou a aula" / "Moda e Corpo · dormiu mal"; "Pegou a matéria com a Júlia" / "Moda e Corpo"; "Chamou a Bia pra sair" / "Sábado 21:00 · topou" (ou "não podia"); "Remarcou" / "Saindo com a Bia no Quartinho Bar · pra domingo 18:00"; "Combinou com você" / "Treino na Bodytech · amanhã 07:00"; "Desistiu de treinar", "Treinou no prédio", "Adiou o passeio do Milo", "Adiou o mercado", "Desistiu do mercado" (com o motivo embaixo); na saída emendada, a linha cinza "Emendou na volta · empolgada".
  - Motivos (visíveis embaixo, vindos dos sentimentos): "sem energia", "dormiu mal", "desanimada", "entediada em casa", "empolgada", "precisando desabafar com alguém", "precisando espairecer", "querendo espairecer", "querendo descarregar a ansiedade", "sem bateria social", "com pique pra gente", "de TPM", "chovendo", "sem grana", "é com a Bia".
  - Chat: reserva da iniciativa "amor desisti… não tô no clima hoje" (só se a geração falhar); instrução interna "Conte pro Patrick… como quem desabafa com o namorado".
  - Prompt (interno): "[SUA AGENDA — o que você decidiu]" e "A agenda é sua: se na conversa você mudar de ideia de novo (ir, desistir, remarcar), vale de verdade."; "[BANHO — FATO]"; "acabou de acordar, ainda de pijama, com calma (o café da manhã fica pra umas HH:MM)".
  - Acontecimentos (internos, o prompt lê): "Desistiu de ir: … (motivo). Avisou a Bia e combinaram outro dia.", "Faltou a aula de hoje (…): …. Vai pegar a matéria com a Júlia depois.", "Saindo de lá, resolveu passar no … antes de voltar (…)", "Chamou a Bia pra sair sábado às 21:00 (…); Bia topou."
- Testes: `tests/test_agenda_viva.py` (23) e os bugs do dia em `tests/test_bug_mundo_2709.py` (12).

**Atraso de verdade — como ficou (28/09, tarde; `atraso.py`) ✅** Pergunta do Patrick na frente de bugs: "ela se atrasar pra aula e pros outros compromissos, e o mundo, o card e o chat saberem". Antes só a aula atrasava, e desamarrado (o `college` gravava "chegou 12 min atrasada" mas a ida tinha hora fixa e o card mostrava ela saindo na hora). Decisões dele (28/09): **todas as causas** (e as que eu trouxesse de real); **aula, rolê/jogo, freela, médico e salão** atrasam (academia, Milo e saída sozinha sem hora só saem mais tarde); **atraso grande pesa pelo que ela sente**; **ela conta pelo que sente**.
- **Despertador** (dia de aula, na hora em que ela acorda): se arruma correndo (30 min, mais o café se tomou); se nem assim dá, sai atrasada — e já sabe disso ao acordar.
- **Na hora de sair** (decidido nesse momento, pelo que aconteceu no Se arrumando): **enrolou pelo que sente** (sono < 6 h, sem pique, insegura/TPM num rolê = troca de roupa, empolgada = troca de look; rolê tem um tico a mais — carioca; freela ela se esforça), **o Milo aprontou** (deitou na roupa, roubou a meia, xixi no tapete — a arte do dia caindo na última hora), **ficou no celular com o Patrick** (5+ mensagens dele na última hora; freela não), **voltou pra pegar algo** (4%, 10% correndo ou com sono). Atrasinho < 4 min ela compensa.
- **No caminho** (quando sai): o imprevisto custa minutos (`commute.INCIDENT_DELAY`: ônibus demorou +15, integração +10, uber errou +8, uber cancelou +7, trânsito +10, açaí +6, metrô parou +5; lotado e garoa, 0) e chuva forte +25% no uber/ônibus/carona.
- **Mundo:** a ida sai e chega mais tarde (`commute.legs_on`; o sono planeja pela saída planejada, `planejado=True`); o compromisso começa sem ela (`CalendarWorld.current` não a põe lá antes de chegar — disponibilidade, iniciativas e mundo leem isso); na chegada vira acontecimento ("Chegou 15 min atrasada na aula de … — perdeu o despertador e o ônibus demorou") e frustração proporcional ao atraso.
- **Card:** Se arrumando desde que acordou, com "· atrasada" na linha 2, os avisos (Perdeu o despertador, Trocou de roupa três vezes…) e os passos de antes da hora de sair onde estavam (só a saída vai pro fim de verdade); A caminho "Chega na PUC às ~07:15 · 15min atrasada" — o que o caminho atrasa só aparece depois de acontecer (a barra também); Lá começa na chegada, entrando no meio da aula, com "Chegou 15min atrasada". De quebra: aviso futuro não aparece mais em cinza antes da hora (era spoiler do imprevisto).
- **Chat:** bloco "[ATRASO — aconteceu de verdade]" (atrasada agora, por quê, que horas chega, se já avisou; depois, até 90 min, que chegou atrasada). Iniciativa `atraso`: aula, freela, médico, atraso ≥ 25 min, despertador perdido ou de mau humor → avisa na hora; atrasinho de rolê de bom humor, não; chateada com ele, não; ele escrevendo agora, fala no chat.
- **Atraso grande (≥ 40 min):** pesa na agenda viva (vontade − o atraso contra o peso do compromisso). Aula: desiste só das aulas que perderia (a ida passa pra próxima, se houver) e vai pegar a matéria; rolê: fura e avisa a amiga; dia de entrega e quem já matou aula na semana vão assim mesmo. Freela, médico e salão: vai atrasada.
- **Textos que decidi sozinho (pra ele revisar):**
  - Card (visível): "· atrasada" (Se arrumando); "Chega na PUC às ~07:15 · 15min atrasada"; avisos "Perdeu o despertador", "Lerda de sono", "Sem pique pra se arrumar", "Trocou de roupa três vezes", "Trocou de look", "Enrolou se arrumando", "Milo deitou na roupa", "Milo roubou uma meia", "Milo fez xixi no tapete", "No celular com o Patrick", "Voltou pra pegar a chave" (carteirinha da PUC, carregador, fone, batom, cartão, book), "Trânsito da chuva"; na chegada "Chegou 15min atrasada".
  - Hoje (visível, pelo acontecimento): "Chegou 15 min atrasada na aula de Ergodesign" / "perdeu o despertador e o ônibus demorou".
  - Chat: reserva da iniciativa "amor tô atrasada… depois te conto" (só se a geração falhar); instrução interna "Avise o Patrick agora, do seu jeito e curto, no meio da correria…".
  - Prompt e acontecimentos (internos): "Você está ATRASADA na aula de … (começa 07:00): …. Chega ~07:15, uns 15 min depois — o compromisso começa sem você."; motivo do sentimento "Chegou atrasada · aula de Ergodesign"; desistência "Faltou a aula de hoje (…): ia chegar 45 min atrasada e …".
- Testes: `tests/test_atraso.py` (10).

**Cuidados (status novo):** **unha** tem estado (cor, feita quando, gastando). Ela faz em casa **só se estiver entediada e com a unha gasta**; manicure (saída) antes de evento/job; **luxos saem do saldo dela**. A cor atual **manda nas fotos geradas**, e ela pode **pedir a opinião do Patrick** sobre a cor quando quiser. Depois: cabelo e outros cuidados (ideias do Patrick).

**Unhas — como ficou (26/09, noite; `unhas.py`) ✅** Decisões do Patrick: esmalte comum em casa gasta em 5–7 dias, gel no salão dura 2–3 semanas; **salão = Ophicina do Cabelo** (Rua Voluntários da Pátria, 185 — migration 030; serve pro cabelo depois); vai na **rotina (gel a cada ~3 semanas), antes de evento/job e às vezes por mimo**; em casa **só retoque**; todas as paletas (clássicas, escuras, candy, da estação — o peso muda com a estação); **pergunta a cor às vezes (metade das vezes), antes de fazer**; **a foto é sempre depois** — sempre se ele participou da escolha, às vezes por vontade dela.
- **Estado:** cor, gel/esmalte, feita quando e onde, quem escolheu. Condição: gel perfeita (< 12 dias) → crescendo → pedindo manutenção (18) → descascando (24); esmalte perfeita (< 3) → começando a gastar → gastando (5) → descascando (7). Partida: nude rosado em gel, feita há 9 dias.
- **Em casa:** bloco "Fazendo as unhas" do tempo livre (40–60 min) quando o esmalte está gasto (ou o gel passou de 24 dias sem salão marcado) e ela está entediada (episódio de tédio: 60% por bloco) ou à toa (tarde/noite sem nada nas próximas 2 h: 15%). A cor entra no card quando é decidida ("Fazendo as unhas · Lilás"); celular: "Olha de vez em quando" (esmalte secando).
- **Salão:** livre em casa, seg–sáb, 9h–18h: evento nas próximas 48 h (job, casting, encontro, festa/aniversário) com a unha não tão nova (35% por janela de 20 min); rotina, gel com 18+ dias ou esmalte com 7+ (15%); mimo com saldo ≥ R$ 600 (2%). Só se o saldo cobre R$ 180 + R$ 100 de reserva e se cabe antes do próximo compromisso e das 20h. Vira item da agenda única (preparo, 10 min a pé, 90 min lá: "Tirando o esmalte antigo", "Fazendo a mão em gel", "Fazendo o pé", "Pagando · R$ 180" com o valor na direita, como o consumo do rolê; volta). Pago do saldo ao terminar (R$ 180: mão em gel R$ 110 + pé R$ 70 — valor do Patrick).
- **Pergunta:** a iniciativa `unhas_cor` manda "X ou Y?" (duas cores sorteadas, nunca a de agora); ele tem até 15 min depois de ela começar em casa, ou até ela sentar na cadeira no salão. Vale qualquer cor que ele disser, "a primeira/a segunda", e "tanto faz / você escolhe" (aí ela decide). Sem resposta, ela vai de uma das duas e o prompt sabe disso.
- **Foto:** 2–6 min depois de pronta, foto da mão do ponto de vista dela (pose `pov_unhas`, sem o LoRA dela); **toda foto** leva a frase da unha de verdade (cor, e gasta/descascando quando for o caso).
- **Onde aparece:** "Por dentro" ganha a **seção Unhas** (layout do Patrick, revisado 26/09 — "numa linha única fica péssimo"): a cor com a bolinha na linha 2, a barra de desgaste (enche até descascar; amarela quando gasta) e embaixo **Estado** ("Gastando"), **Tipo** ("Gel"/"Esmalte") e **Feita** ("Há 6 dias, em casa" / "Há 9 dias, na Ophicina do Cabelo"); fazendo: "Fazendo agora" e "Agora, em casa". O Patrick vai arrumar as outras abas dos Bastidores depois de fechar a primeira; o prompt tem o bloco [SUAS UNHAS]; acontecimento do dia ao terminar ("Fez as unhas em gel (mão e pé) na Ophicina do Cabelo: lilás — a cor que o Patrick escolheu (R$ 180)").
- **Textos revisados com o Patrick (26/09, noite):** Estado curto no painel — **Nova · Crescendo · Vencendo · Gastando · Descascando · Fazendo agora · Escolhendo a cor** (o prompt segue por extenso); nomes das 17 cores ok; reservas no jeito dela — **"vou fazer a unha agr, X ou Y? vc decide"** e legenda **"olha como ficou"**; motivos secos — **"manutenção do gel", "job amanhã", "encontro hoje", "festa depois de amanhã", "mimo"** (o dia sai da data real do evento). Antes da revisão: card em casa "Fazendo as unhas · <cor>"; passos do salão ("Tirando o esmalte antigo", "Fazendo a mão em gel", "Fazendo o pé", "Pagando"; preparo "Trocando de roupa", "Pegando a bolsa"; título "Na Ophicina" — ok do Patrick); nomes das cores (Vermelho, Vinho, Nude rosado, Branco leitoso, Francesinha, Preto, Marsala, Azul-marinho, Verde-musgo, Rosa bebê, Lilás, Azul clarinho, Rosa chiclete, Coral, Laranja, Amarelo, Glitter — só em festa); instrução da pergunta e mensagem reserva "amor vou fazer a unha… X ou Y? escolhe vc"; legenda reserva da foto "ficou bom? 💅"; motivos do acontecimento "o gel já tava pedindo manutenção / tem job chegando / tem encontro chegando / tem festa chegando / quis se dar um mimo". Horário da Ophicina (seg–sáb 9h–20h) é estimativa minha.

**Cabelo — como ficou (26/09, noite; `cabelo.py`) ✅** Mesmo molde das unhas. Decisões do Patrick: tudo como status — **dia de lavar, como está agora, corte e pontas, luzes**; salão (Ophicina do Cabelo) com **escova R$ 70, hidratação R$ 120, corte R$ 150, tonalização R$ 250**, juntando o que venceu numa ida só; em casa **lavagem no banho, umectação e penteado pra sair**; opinião dele **nos dois** (penteado antes de sair e corte/cor no salão); **lava dia sim, dia não**. Teste de fotos com o LoRA (7 imagens, mesma semente): o rosto se manteve em todas, e cor, corte e ângulo obedecem o texto. Aprovados: cortes **reto, repicado, franja cortina e franja cheia**; luzes **dourado (padrão), bege claro, pontas rosa** (tonalizante que desbota) e **loira iluminada** (mudança rara). Ela decide mudar às vezes pedindo a opinião dele; se ele sugerir no chat, ela pode aderir na próxima ida.
- **Lavagem:** acontece dentro do banho de verdade (`rituals.start_shower` → `Cabelo.banho`, +8–12 min, acontecimento "Tomou banho e lavou o cabelo"). Lavado hoje não lava; 2º dia lava se foi à academia/praia ou vai sair (80%), senão 15%; 3º dia sempre; a escova do salão é protegida até o 3º dia. Secagem: secador se vai sair, à noite 60%, de dia 40%; natural fica úmido 100–150 min.
- **Penteado de agora** (painel e foto): no banho → molhado; secando; umectando (touca); o penteado da saída; academia → rabo de cavalo; dormindo → coque frouxo; escova do salão até o 3º dia; 3º dia oleoso → preso (coque ou rabo baixo); senão solto natural (ou escovado, se secou no secador).
- **Penteado pra sair:** quando o "Se arrumando" começa, ela escolhe pelo tipo (noite: babyliss, escova, rabo alto, meio preso, coque; encontro; jogo; praia; dia a dia), sem solto no dia oleoso. Noite/encontro com ≥ 30 min de preparo: 40% pergunta "X ou Y?" (iniciativa `cabelo_pergunta`); ele tem até a metade do preparo. Se ele escolheu, sempre manda a foto pronta (espelho 60% / tripé); sem ele, 25% em noite/encontro.
- **Corte, luzes, hidratação:** pontas Boas < 45 dias, Crescendo, Pedindo corte (70), Ressecadas (90); luzes Nova < 14, Boa, Desbotando (¾ do prazo), Amarelada/Raiz aparecendo (prazo 56 dias; loira 49); rosa viva < 12 dias, desbotando até 25, depois volta o tom de base; hidratação Macio < 10, Normal, Ressecado (18). A franja cheia vira cortina em 6 semanas e some nas camadas em 10.
- **Umectação em casa:** bloco "Umectando o cabelo" (60–90 min, celular na mão) com o cabelo sem hidratar há 12+ dias — entediada 35%, senão 4%; lava no próximo banho.
- **Salão:** seg–sáb 9h–17h (termina até 20h), item da agenda única (`cabelo:<dia>:<HHMM>`), 10 min a pé. Motivos: sugestão dele (3% por janela de 20 min, vale 21 dias), evento em 30 h sem escova (30%), pontas ou luzes vencidas (12%; nessas, 15% de chance de ela querer mudar), ressecado 24+ dias (6%), mimo com saldo ≥ R$ 800 (1,5%). Serviços: o vencido + escova sempre depois de corte/cor; sem dinheiro, tira hidratação e escova. Pergunta no salão em 50% quando tem corte ou mudança ("só as pontas ou repicar?"); ele tem até ela sentar na cadeira; a resposta muda serviços, preço e passos do card. Luzes no cabelo todo R$ 650 (~3h40), retoque da loira R$ 450, pontas rosa R$ 220.
- **Foto do salão:** perto do fim, alguém de lá tira (ela de capa preta na cadeira, pose `salao_cabelo`); sempre se ele escolheu ou se houve mudança, 25% sem. **Toda foto** troca a cor/corte e o penteado fixos do perfil pelos de agora (menos quando a pose já diz que o cabelo está molhado, embaraçado ou espalhado).
- **Onde aparece:** "Por dentro" ganha a **seção Cabelo** (mockup aprovado): o penteado com a bolinha do tom, quatro barras (Lavagem, Pontas, Luzes, Hidratação — amarela quando vence) e as linhas **Lavou** ("Ontem, secou natural"), **Corte** ("Reto, há 5 semanas"), **Luzes** ("Dourado, há 6 semanas"). No salão, o card "Lá" mostra os serviços da vez e "Pagando · R$ X" na direita. Prompt com o bloco [SEU CABELO]. Unhas: agora POV em 70% e **selfie com a mão perto da boca** em 30% (Patrick).
- **Textos revisados com o Patrick (26/09, noite):** penteados mais curtos — **Solto natural · Escovado · Umectando · Secando natural · No secador · No banho · No salão** (os outros ficaram); palavras das barras ok; linha **Lavou** sem o nome do salão ("Hoje, escova no salão"); pontas rosa ganham **linha própria Rosa** ("Há 3 dias, desbota em ~3 semanas" / "Há 2 semanas, desbotando") e a linha Luzes fica com a base; card do salão com o título **"Na Ophicina"** (igual unhas) e passos curtos em substantivo — **Luzes · Retoque das luzes · Tonalização · Pontas bege · Pontas rosa · Hidratação · Corte das pontas · Repicado · Franja cortina · Franja · Corte reto · Escova · Pagando**; preparo igual à manicure; acontecimentos limpos — **"Marcou o cabelo na Ophicina: pontas e luzes vencidas."** e **"Cabelo na Ophicina: repicado (o Patrick escolheu), tonalização e escova · R$ 470."**; reservas com contexto — **"vou sair, X ou Y? escolhe vc"** e **"tô indo no salão, X ou Y? vc decide"**. Banho com lavagem e umectação na linha do tempo ficam pro ataque geral do "Hoje" (próximo da frente dos apps).
- **Textos que decidi sozinho (versão anterior à revisão):** nomes dos penteados (Solto, ondulado natural · Solto com babyliss · Escova lisa · Escovado com secador · Rabo alto · Rabo baixo · Coque despojado · Meio preso · Trança lateral · Preso com piranha · Preso num coque · Coque frouxo · Rabo de cavalo · Preso com touca, umectando · Molhado, secando natural · Secando com secador · Molhado, no banho); palavras das barras (Lavado hoje · 2º dia · 3º dia · Oleoso; Boas · Crescendo · Pedindo corte · Ressecadas; Nova · Boa · Desbotando · Amarelada · Raiz aparecendo · Rosa · Rosa desbotando; Macio · Normal · Ressecado); passos do salão (Fazendo as luzes · Retocando as luzes · Lavando e tonalizando as pontas · Tonalizando as pontas de bege · Pintando as pontas de rosa · Fazendo hidratação · Cortando as pontas · Repicando o cabelo · Cortando a franja cortina · Cortando a franja · Cortando reto · Fazendo escova · Pagando); como ela fala as opções (só as pontas · repicar · franja cortina · franja · tirar as camadas e deixar reto · manter o dourado · pontas bege · pontas rosa · ficar loira); motivos (pontas e luzes vencidas · cabelo ressecado · o Patrick sugeriu · job/encontro/festa + dia · mimo); reserva da pergunta "X ou Y? escolhe vc"; legenda reserva "olha como ficou"; bloco do tempo livre "Umectando o cabelo"; título na agenda "Arrumando o cabelo na Ophicina do Cabelo"; preços da loira, do retoque e do rosa (estimativa minha).

**Linha do tempo "Hoje" — como ficou (26/09, noite; `hoje.py`, frente dos apps) ✅** Decisões do Patrick, olhando o dia real de 26/09 no celular:
- **Formato B, períodos fechados:** o dia inteiro por período (**Manhã 4h–12h · Tarde 12h–18h · Noite 18h–4h**). Primeiro foi uma caixa com rolagem; o Patrick mudou de ideia: **os períodos que já passaram ficam fechados ("Manhã · 7") e abrem ao tocar**; o de agora fica aberto (o que ele abriu continua aberto na recarga de 1 min).
- **Saída** vira um item com **início–fim** (do pé na rua até chegar em casa; em curso fica "20:48–") e o que aconteceu no período **recuado embaixo** (encontros, consumo com valor, Uber, peso, imprevisto em amarelo).
- **Dia inteiro**, **blocos em casa** (com duração; iguais em seguida viram um) e **conversas por mensagem** entram; o que vem depois aparece **em cinza** no fim, com hora aproximada (refeições do plano, saídas marcadas, série, **Dormir**).
- **Tudo no passado** (o previsto fica em substantivo): "Olhou o Instagram", "Montou looks", "Ouviu Dua Lipa", "Tomou banho e lavou o cabelo", "Foi pra academia", "Foi pro Quartinho com a Bia", "A Bia chamou pro Quartinho Bar", "Topou ir pro Quartinho Bar", "Pediu um gin tônica  R$ 34", "Pegou um Uber".
- **Refeição** na linha 1 e **prato embaixo** ("Almoçou" / "Poke do iFood"; "· comeu além da conta" quando estufou). **Presente seu:** a loja em cima ("Comeu o Rei do Mate que você mandou"), os itens embaixo.
- **Conversas:** "Trocou mensagens com o pai" e embaixo **"Assunto: saudade dela"**; pessoa nova só **"Conheceu a Gabi"** (quem ela é fica pro sistema/cânone).
- **Xixi do Milo:** "Foi pra calçada" com **"Xixi do Milo"** recuado, igual ao passeio.
- Texto interno (`father_check_in`, consequência de thread) **não aparece**.
- **Ícones:** o Patrick preferiu os do **Tabler (outline)** aos do Bootstrap — trocados **no Mini App inteiro** (iFood, Nubank, Bastidores; nomes nas grades do `agenda.py`, `cabelo.py`, `webapp_server.py`). Milo com ícone de cachorro.
- **Revisão de textos e ícones com o Patrick (27/09, madrugada) — regra geral: a ação na linha, a descrição curta menor e cinza embaixo, valor na coluna.** Catálogo inteiro (50 tipos de linha) revisado:
  - Ícones próprios: **chuveiro desenhado no traço do Tabler** (o Tabler não tem) pro banho; masturbação com o **hand-love-you de cabeça pra baixo** (`ic("masturbacao")`).
  - Masturbação em casa: **"Se masturbou no quarto" / "Pensando em você"** (ou "Chamou você pra entrar no clima"); fora: **"Se masturbou no banheiro" / "Tesão muito alto"**. O "guardou só pra ela / pode contar" é do sistema e não aparece.
  - Casa: **"Arrumou a casa" / "Trocou a roupa de cama"**; Milo: **"Arte do Milo" / "Fez xixi no tapete do banheiro"**, **"Pagou o passeador do Milo" / "Dia puxado"**.
  - Blocos em casa: redes com **logo próprio** (Instagram, TikTok, Pinterest, X); croqui lápis; quarto casa com check; Milo cachorro; plantas planta; sol sol; **"Deitada à toa" → "Ficou à toa"** (sofá).
  - Comida: refeições com **talheres**, belisco **biscoito**, presente guardado **sacola com coração**, delivery **sacola**; convite e "Topou" com **calendário**.
  - Dinheiro: **"Você fez um Pix pra ela" · R$ 300 / "De presente"** (ou "Pro uber", "O que tinha prometido", o recado); "Usou o seu Pix", "Devolveu o seu Pix", "Ficou no aperto". Presente dela: **"Mandou um presente pra você" · R$ 18 / "Cappuccino do Rei do Mate"**.
  - Mídia: "Ouviu a música que você mandou" / "\"Espresso\", Sabrina Carpenter · curtiu"; "Saiu música nova de …". Salão: **"Fez o cabelo" / "Repicado e escova · você escolheu"** e **"Fez as unhas" / "Gel · vermelho"** com valor. Faculdade: "Trabalhou no seminário de … / Entrega 02/10 · rendendo bem". Imprevisto: só o fato, em amarelo ("Ônibus veio lotado").
  - Por que saiu vira a linha cinza da saída: **"Resolveu sair · motivo"** ("deu vontade" não existe no jeito dele), **"Você convenceu"**, "Combinou com você"; desistência é linha própria ("Desistiu de sair pro Starbucks" / "Começou a chover").
  - O que ainda vem cru do mundo se divide sozinho no parêntese do fim, no primeiro ":" ou no "—".
- **Textos que decidi sozinho (pra ele revisar):** "Acordou"; "Comeu o delivery" (prato embaixo); "Chegou o presente do {loja} que você mandou" (quando ela guarda); "Se pesou · 54,0 kg"; "Pegou um Uber (dividido)"; previsto "Café da manhã · Almoço · Lanche · Jantar · Série · Dormir"; limites dos períodos; ícones de cada tipo.

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

**Auditoria, rodada 2 (28/09, 18:00): Agora e Hoje de 28/09.** Card: quem ela encontrou lá vira passo do Lá na hora em que aconteceu ("Encontrou a Gabi 17:07"; decisão do Patrick), sem virar o passo atual e sem repetir quem foi junto. Hoje: o que ela pediu fora aparece uma vez só ("Pediu pão de queijo", com o valor; a linha "Comeu pão de queijo no Starbucks" saiu); saída por vontade com ícone do tipo (farmácia pílula, açaí sorvete, orla caminhada, shopping sacola, praia); "Pulou o café da manhã 07:52" sem intervalo; bloco em casa acaba quando o próximo começa; farmácia e mercado dizem "Comprou"; "Chamego com o Milo" (dormiu encostado, pediu colo) separado de "Arte do Milo" (decisão do Patrick), 20–40 min depois de ela chegar; nada previsto depois do Dormir (o lanche das 22:55 e a série das 21:55). FRENTES_MARINA.md, seção 5, item 15.

**Bug corrigido (28/09, Hoje, bug 14):** o Hoje mostrou "O Milo dormiu encostado nela no sofá" às 17:21 no meio do passeio na Enseada. A arte do Milo agora só acontece com ela em casa; se ela estava fora, aparece no Hoje na hora em que ela chegou (FRENTES_MARINA.md, seção 5, item 14).

**Bug corrigido (28/09, Hoje e Por fora, bug 16):** "Se pesou · 54,4 kg" aparecia às 18:43, com ela ainda a caminho da Bodytech (o preparo contava como treino). Agora a pesagem entra no Hoje e na linha Pesou quando ela sai do treino (FRENTES_MARINA.md, seção 5, item 16).

**Bug corrigido (27/09, Hoje x card):** às 01:05 o card dizia "Se arrumando" com banho às 01:00 e o Hoje dizia "Tomou banho 00:31–01:12". Agora é um card só (o banho de chegada é o banho do Se arrumando), o Hoje põe no presente o que ainda está acontecendo ("Tomando banho 00:31–"), corta o bloco em casa quando o banho começa e não mostra mais bloco antes da chegada nem lanche em casa com ela no bar (FRENTES_MARINA.md, seção 5, item 2).

**Bug corrigido (27/09):** a aba Agora mostrou certo, em casa às 00:07 depois da volta de uber às 00:05, enquanto no chat ela dizia que estava no bar. O bug era da fala, não do app (FRENTES_MARINA.md, seção 5). Efeito no app: quando ele combina "vai e volta de uber" e ela topa, os trechos da saída na aba Agora passam a mostrar uber (e o tempo de uber).

**Organização (27/09):** frentes novas de bugs (seção 5) e imagens (seção 6) no `FRENTES_MARINA.md`.

**Frente de imagens (27/09):** nada mudou no Mini App. As fotos dela ganharam 18 poses novas e o plug de coração entrou na gaveta (PLANO_VOZ, "Poses de referência").

**Amigas (27/09, frente de imagens):** pensando no Instagram, a Bia ganhou um LoRA de rosto (teste: sozinha funciona, junto da Marina os rostos se misturam; em grupo, a amiga vai só por prompt). Nada no Mini App ainda.

**Auditoria de funcionamento (27/09):** o Mini App entra no roteiro da frente nova (FRENTES_MARINA.md, seção 7): card Agora × Hoje × mundo, iFood (sacola, checkout, pedidos), Bastidores e comprovantes, com prova na produção.

**Auditoria, rodada 1 (27/09, 11:40):** Hoje e card batem com o mundo nas saídas; o Hoje deixa de mostrar "Foi pra calçada" colado no "Foi pra Enseada" (xixi do Milo some quando o passeio vem logo depois) e o card volta a ter o Se arrumando antes de uma saída de tarde (o almoço sai antes do preparo). Dinheiro: o pix de presente com rolê no dia não vira mais "Usou o pix do Patrick: comprou…" no Hoje. Decidido com o Patrick: o previsto de saída mostra a hora em que ela chega lá ("~15:00 No Shopping da Gávea com a Bia"), não a de sair de casa. O saldo dela foi consertado na produção (R$ 865) e a compra fantasma de R$ 236 saiu do Hoje.

**Bia (28/09, frente de imagens):** aparência canônica decidida (morena carioca, só texto). Nada no Mini App ainda; entra quando houver Instagram.

**Bia (28/09):** rosto fixo por foto-RG e troca de rosto nas fotos de grupo (frente de imagens). Nada no Mini App ainda.

**Carol (28/09):** rosto fixo por foto-RG, como a Bia (frente de imagens). Nada no Mini App ainda.

**Júlia (28/09):** rosto fixo por foto-RG, como a Bia e a Carol (frente de imagens). Nada no Mini App ainda.

**Fotos de perfil no Mundo (28/09):** Bia, Carol, Júlia e Theo aparecem com foto (círculo de 38px no lugar das iniciais) na lista de Pessoas do Bastidores. `social_day.world_panel` manda `foto: "avatars/<chave>.jpg"` quando o arquivo existe em `webapp/avatars/`; sem arquivo, continua nas iniciais. A foto é o recorte no rosto de uma foto de perfil gerada sobre o RG de cada um (frente de imagens).

**Foto de grupo (28/09):** quando ela está num rolê com uma amiga de RG, a foto pode sair com as duas (selfie juntas, rosto da amiga trocado pelo do RG). Chega pelo chat como qualquer foto; nada no Mini App ainda — é a matéria-prima do Instagram (Etapa 5). Na foto de grupo as cabeças ficam um pouco separadas (lado a lado ou abraçadas). O peito dela sai mais natural em toda foto (slider real/fake −1.0), o que vale também pro feed do Instagram; e a mordidinha no lábio sai de verdade quando a foto pede (LoRA Lip Bite em 0.6).


### Etapa 5 — Instagram (27/09, frente dos apps) 🟡

**Decidido com o Patrick (mockups e perguntas, 27/09):**
- Só Instagram agora; o X fica pra uma etapa própria depois.
- **Foto do post, mista:** as fotos vestidas que ela manda no chat ficam guardadas e podem virar post ou story (custo zero). Foto nova só em momento de post (rolê, look, vista, Milo…), ~20 Buzz; com amiga, ~61.
- **Feed pelo dia dela, ~2 por semana**, no máximo 1 por dia. **Stories sem foto nova:** música que está tocando (capa do iTunes), foto do chat e texto sobre fundo; somem em 24 h.
- **Ela só fica sabendo quando abre o Insta** (bloco "Olhando o Instagram", uber, tempo livre com o celular): responde lá e às vezes puxa no chat. Nada de aviso do sistema.
- **Amigas comentam, aparecem marcadas e postam** (~2 posts por semana somando as quatro).
- **Ele:** curte e comenta os posts, responde e curte comentários, reage aos stories. A resposta ao story vira mensagem dele no chat (a foto do story com o texto, "via @bot") e ela responde lá.
- **Namoro discreto, mas na bio:** ela não posta foto dele (não existe foto dele no mundo); a bio tem ♡ @ptkramos.
- **Perfil:** @masalles, "Ma Salles / moda, croqui e café gelado / mãe do @milooshi / ♡ @ptkramos", ~4 mil seguidores.
- **Abre no feed** (stories no topo, posts dela e das amigas por hora); o perfil dela fica na barra de baixo.
- Quando ela posta: linha no Hoje ("Postou uma foto no Instagram", a legenda embaixo), vai pro prompt dela, e bolinha vermelha no ícone do Instagram na tela inicial.
- **Acervo inicial:** 9 posts dela dos últimos 2 meses e 2 de cada amiga, gerados uma vez (~400 Buzz).

**Como ficou (código):**
- `instagram.py` — as regras. Motivos de post vêm do que aconteceu de verdade (`life_events`): encontro com amiga numa saída (`social_contact …:saida`, com a amiga de RG vira foto de grupo), praia, salão, unhas, looks, academia, passeio do Milo, foto do chat; sem nada, a selfie em casa. **Vontade de postar** = peso do motivo + 0,1 por dia sem postar (até 6) + (valence − 0,6) + (energia − 0,5) × 0,3; posta com ≥ 1,0, 36 h depois do último post, 20–120 min depois do acontecimento, com o celular livre (em casa à toa, uber, sozinha na rua, bloco do Instagram), das 9:30 à 0:40 e fora da conversa com ele (a trava do Civitai é uma só). Triste (valence < 0,45) não posta story.
- **Quando ela abre o app:** no bloco do Instagram a cada 20 min; com o celular livre a cada 75 min (30 min nas 3 h depois de postar, vendo as curtidas); ocupada-mas-dá (refeição, rolê, se arrumando) a cada 150 min. Ela curte e responde todo comentário dele (e curte a curtida); das amigas, curte todos e responde até 2; de fora, curte metade. Post de amiga: curte e comenta metade das vezes. O que viu nas últimas 24 h vai pro prompt como fato ("[SEU INSTAGRAM (@masalles) — aconteceu de verdade]").
- **Curtidas:** seguidores × alcance (5–11%) × (1 − e^(−horas/4)), mais a dele.
- **Comentários das amigas:** gerados todos de uma vez (um JSON) quando o post sai, e chegam espalhados: a marcada em 4–40 min, o resto em até 8 h (de madrugada, não). Quem comenta: a marcada sempre, Bia 85%, Theo 60%, Júlia 50%, Carol 45%, e 1–2 seguidores de fora. Quando ele comenta, 35% de chance de uma amiga (a marcada ou a Bia) responder ele em 15 min–3 h.
- **Post das amigas:** um sorteio por dia (2/7), hora entre 11h e 21h; se a Marina postou foto de grupo com ela nas últimas 30 h, a amiga reposta a mesma foto (sem custo); senão, foto nova pelo Krea 2 Edit sobre o RG (`civitai_images.friend_scene`, 20 Buzz — teste da Bia na praia e do Theo no carro aprovado pelo rosto). No máximo 2 tentativas de foto por acontecimento.
- `bot.py`: `instagram_routine` a cada 5 min (ela olha, story, post, amiga), `_guardar_pro_insta` nas fotos do chat (vestida: nível 0, ou nível 1 na rua), `_ig_shot` (pose do motivo, nível 0, roupa de sair em rolê/look), `_ig_responder_story`.
- `webapp_server.py`: `/api/ig`, `/api/ig/perfil/{autor}`, `/api/ig/post/{id}`, `/api/ig/atividade`, `/api/ig/curtir`, `/api/ig/comentar`, `/api/ig/story`, `/ig/{arquivo}` (fotos em `data/instagram/`, nome impossível de adivinhar, fora do git); `insta_novo` na `/api/inicio`.
- Front: `webapp/insta.js` (feed, perfil com abas publicações/marcações, post com comentários encadeados e "pela autora", atividade, visualizador de story com barras, toque duplo curte), estilos no fim do `app.css`, logos do Instagram do Wikimedia (`webapp/marcas/instagram*.svg`).
- Banco: `migrations/031_instagram.sql` (`ig_posts`, `ig_comentarios`, `ig_fotos_chat`).
- Acervo: `scripts/instagram_acervo.py` (roda na VPS; sem `--gerar` só mostra o plano e o custo).
- `tests/test_instagram.py` (23 testes). Conferido na pré-visualização (`miniapp-insta`) em tamanho de celular: feed, comentários, perfil, marcações, stories de música e de texto.

**Textos que decidi sozinho (revisar com o Patrick):**
- Perfis das amigas: **@bia.andrade** "Laranjeiras · RJ / sexta é sagrada" (2.387 seguidores); **@carolmenezes** "nutri em formação / treino e comida de verdade" (1.652); **@juazevedo** "design · PUC-Rio / fotografo tudo em 35 mm" (934); **@theomartins** "moda · PUC-Rio / Glória" (1.428). Seguidores de fora que comentam: lu.mendes, nanda.rocha, pedroh.lima, carolinabastos, rafa.nogueira, duda.lins.
- O que cada amiga posta: Bia (festa na Lapa, praia de Ipanema no pôr do sol, espelho de roupa preta), Carol (espelho da academia, bowl num café de Botafogo, corrida no Aterro), Júlia (exposição de fotografia, câmera analógica no Jardim Botânico, café com caderno), Theo (espelho de look, rooftop à noite, encostado no carro na Glória).
- Telas: "Nada postado ainda / Os posts da Ma e das amigas aparecem aqui", "Nenhuma publicação ainda", "Atividade nos seus comentários / Quando responderem ou curtirem o que você comentou, aparece aqui", "Adicione um comentário para masalles…", "Respondendo a …", "pela autora", "Enviar mensagem", "Mensagem enviada", atividade "respondeu: …", "curtiu seu comentário: …", "marcou a masalles numa publicação". Botão "Mensagem" no perfil dela fecha o app (a conversa com ela é o chat).
- Na tela inicial ficaram 5 quadrados (Nubank, iFood, Instagram, Presentes e Datas "em breve"): o último sobra sozinho numa linha.

**Correção depois do acervo (27/09, noite — Patrick):** "legendas e comentários ruins, amigas absurdamente repetitivas; roupa repetida; praia sem biquíni (biquíni não é NSFW)". No acervo: Bia com "amiga… absurdo 🔥😂" em quase todo post e a legenda dela escrita como comentário, Carol "bora treinar" em todo comentário, Júlia sempre "a luz", Theo com "look" na praia, a Ma de regata preta em 4 de 9 fotos, a praia com a Carol de blusa. Causa: a descrição de cada amiga tinha assunto e bordão embutidos e nenhum pedido sabia o que a pessoa já tinha escrito; guarda-roupa pequeno sem memória. Corrigido:
- Amigas descritas como pessoa (idade, bairro, temperamento, como escrevem), sem assunto fixo; todo pedido de legenda, comentário ou resposta leva as últimas 10 coisas que aquela pessoa escreveu, com a regra de não repetir palavra marcante, emoji, começo nem estrutura; o pedido diz a roupa e o que a foto mostra. Menos gente comenta (Bia 70%, Theo 45%, Júlia e Carol 35%, 0–2 de fora) e a Ma responde menos (35%, até 2).
- Guarda-roupa do Instagram (`instagram.ROUPAS`: 12 de dia, 12 de noite, 8 biquínis), sem repetir roupa dos últimos 12 posts; **praia é sempre de biquíni** (a amiga também, outro biquíni).
- **Poses:** fora de casa ela quase sempre está com gente — 5 poses novas no catálogo (`photo_director`): rindo olhando pro lado, sentada à mesa, encostada na parede, indo embora olhando por cima do ombro, e as duas amigas com alguém tirando a foto (grupo, com troca de rosto). Não repete a pose dos últimos 3 posts.
- Acervo: `scripts/instagram_acervo.py --refoto ID` (foto nova, uma por vez, aprovada pelo Patrick antes da próxima) e `--textos` (refaz legendas e comentários de todos os posts em ordem de data). Refazer: 3 (look), 5 (PUC), 7 (praia com a Carol), 9 (Starbucks) e 13 (Theo no carro), ~160 Buzz.
- Migration 032 (`roupa` e `pose` no post).

**Refazendo o acervo e folhas de personagem das amigas (27/09, noite):**
- Foto 7 (praia com a Carol) em 4 tentativas: a troca de rosto copiava a **regata branca do RG** da Carol por cima do biquíni, depois o **fundo do RG** (parede de apartamento atrás dela na praia); a pose das duas "alguém tirando" continua saindo com cara de selfie (braço da Ma esticado). Hoje está no ar a 4ª (rosto certo, fundo errado) — **a refazer com a folha**.
- Aprendizado de dois artigos do Civitai (memória `referencia-folha-de-personagem`): referência em **folha de personagem** (4 vistas, fundo cinza, círculo branco no rosto das vistas de corpo, close 3x4) e prompt de edição "o que se quer primeiro, trava de identidade depois". Decidido com o Patrick: **só a folha vestida** (body cinza justo; a pelada obrigaria toda foto delas a ir pela fila adulta).
- Como sai uma folha boa: **1) 3x4 de documento** a partir do RG (`civitai_images.friend_id_photo`; o editor copiava a cabeça inclinada da selfie do RG) → **2) folha a partir da 3x4** (`friend_sheet`) → **3) ajuste à mão, grátis:** círculo branco pintado no rosto da vista de lado (o editor nunca cobre) e espelhar o quadro que puser a tatuagem no braço errado. `scripts/folha_amigas.py <amiga> 3x4|folha` (salva com `_teste`; renomeia quando o Patrick aprova).
- Prontas: **Carol** (`data/amigas/carol_3x4.jpg`, `carol_folha.jpg`, aprovada) e **Bia** (`bia_folha.jpg`, 1ª versão provisória, com 5 vistas e rosto nas de lado — **o Patrick quer refazer** pelo processo da 3x4). Faltam **Júlia e Theo**.
- Ainda **não ligado:** a troca de rosto e a foto da amiga sozinha usam o RG com o corpo pintado de cinza (`_rg_rosto`; recortar a imagem fez o editor responder 500). `_referencia()` já escolhe a folha quando existe, mas `swap_friend_face`/`friend_scene` ainda não chamam — ligar com o prompt do artigo ("as shown in the second image as a turnaround sheet") e testar.
- Pedido da amiga sozinha reescrito pelo guia (cena e roupa primeiro, depois "strictly preserve…", "clean dry skin").
- **Folhas prontas (27/09, noite, aprovadas pelo Patrick uma a uma):** Bia refeita, Júlia e Theo (`data/amigas/<nome>_3x4.jpg` e `_folha.jpg`). A folha agora pede corpo inteiro "da cabeça aos pés" (as primeiras cortavam na coxa). Júlia: 3 tentativas da 3x4 ("rosto muito largo"; a 3x4 leva `FRIEND_ID_EXTRA` pedindo rosto fino e oval) e a folha ajustada à mão (uma lua só, no antebraço direito; close trocado pela 3x4 aprovada).
- **Ligado:** foto da amiga sozinha (`friend_scene`) parte da folha ("as shown in the image as a turnaround sheet", roupa da cena, sem body/círculo/fundo cinza). A troca de rosto **não** usa a folha: no teste o body cinza vazou por cima do biquíni; usa a 3x4 só com a cabeça (`_rosto`) — testada na 7, biquíni intacto.
- **Foto 7 pronta:** a novo7c (o Patrick gostou da Ma nela) com só a cabeça da Carol colada da troca, no ar (`--colocar 7 --base arquivo`).
- **Fotos 3, 5, 9 e 13 refeitas e aprovadas uma a uma (27/09, noite):** 3 vestido de laise no closet (1ª); 5 rindo olhando pro lado, camisa listrada (a 1ª, encostada na parede, saiu com a perna esquisita e corredor de escola americana — a PUC agora é descrita como o campus de verdade, pilotis de concreto no meio do verde, `camera_world.PLACE_VISUAL`); 9 no Starbucks com o café gelado e a amiga de costas desfocada na borda (4 tentativas: 2 selfies — olho na lente + uma mão livre = braço esticado; a pose `fora_amiga_sentada` agora ocupa as duas mãos e é "seen from across the table"; a 3ª tinha marca d'água fraca na parede); 13 Theo de camisa de linho (a 1ª vazou a camiseta e a bermuda cinza da folha: o pedido da amiga sozinha agora diz a roupa no estilo da pessoa, `FRIENDS_VISUAL[...]["style"]`). "Amiga tirando" de meio corpo ganhou texto próprio (`visual_profile.KREA2_PHOTO_FRIEND`; o de corpo inteiro dizia "her whole body in the frame").
- **Corte do feed (Patrick: "tá cortando a testa dela"):** as fotos dela saem 2:3 e o feed é 4:5 com corte centrado; agora corta mais embaixo (`object-position: 50% 20%`, e o mesmo na grade do perfil).
- **Textos refeitos (28/09, madrugada).** `--textos` agora só mexe no acervo (post de verdade fica) e mantém inteira a conversa em que o Patrick comentou (post 8: o comentário da Bia, a resposta da Ma e o dele); quem já tem comentário mantido não comenta de novo. A 1ª rodada ainda deu fórmula por pessoa (Bia 6 de 8 começando "essa/esse … em você", Theo sempre aforismo com ponto final, Carol formal, a Ma respondendo a Bia com 😮‍💨 e flerte). Corrigido: **cada comentário recebe um tipo** (`instagram.TIPOS_COMENTARIO`: pergunta, lembrança/piada interna, reação curtíssima, **só emojis — liberado pelo Patrick**, detalhe da foto, zoeira, convite, o lugar/momento), um tipo por post; **seguidor de fora** só reação, emoji, detalhe ou lugar (`TIPOS_DE_FORA`); **as primeiras palavras dos últimos 6 textos da pessoa viram lista proibida** (`_comecos`); caixa baixa sem ponto final; "entre as amigas o carinho é de amiga, sem flerte"; Theo e Carol descritos sem o molde ("humor seco, escreve bem" e "pontuação certinha" saíram). Vale também pra rotina ao vivo.
- **Falta:** o Patrick revisar os textos no app. Deslizes vistos: no post 11 (da Bia) a Carol fala com a Marina; o Theo convida pra algo em 3 de 7 comentários.
- **Revisão dos textos (28/09, madrugada, com o Patrick):** lidos no banco da produção, seis padrões: (1) as 17 legendas no mesmo molde, lista ou antítese com um emoji no fim ("unhas novas, humor novo ✨", "sol, sal e pele terracota 🌞"); (2) no post da amiga falavam com a Marina; (3) no post da Ma falavam dela em 3ª pessoa ("o olho da Marina"); (4) a mesma palavra entre pessoas diferentes ("entregando" ×3); (5) o Theo sempre convidando; (6) comentário sem sentido. **O post real de 27/09 (id 6)** era do Quartinho da **noite de 26/09**, postado no dia seguinte (os dois rolês com a Bia empataram no peso e o mais antigo ganhou); "noite" estava certo, o que soava date era "minha pessoa". Decidido (Patrick): corrigir o gerador e refazer antes de ele olhar; refazer também o post 6; no empate, o rolê mais recente.
  - **Legenda com tipo** (`TIPOS_LEGENDA`: só emoji, uma ou duas palavras, só o lugar, o que passou pela cabeça, autozoeira, reação ao momento, frase simples) e proibido lista de três / "x novo, y novo" / frase de efeito; foto com amiga nunca soa como encontro. A legenda sabe a hora da foto quando ela é de mais de 3 h antes ("a foto é de ontem à noite", `quando_foi`, `momento_do_post`).
  - **Memória de tipo por pessoa** (`_escolher_tipo`, `ig_tipos_json`): não repete os últimos 3 tipos dela, na legenda e no comentário.
  - **Com quem falam:** todos falam com quem postou, na 2ª pessoa; no post da amiga a Ma é só mais uma. **A marcada estava lá** e tem tipos próprios (`TIPOS_DA_MARCADA`: lembrança do que rolou ali, reação, emoji, zoeira) — ela perguntava "vocês ficaram até que horas?".
  - **O que os outros escreveram** vai no pedido (`_dos_outros`); detalhe só do que está na foto; resposta da Ma em caixa baixa, sem ponto nem exclamação.
  - **Rolê mais recente ganha o empate** (`motivos`); a roupa do post segue a hora do rolê, não a hora de postar (`bot._ig_shot`).
  - `--textos --incluir 6` refaz também o post de verdade e troca a linha do Hoje. Três rodadas numa cópia local do banco (~120 chamadas de texto, sem foto); a versão revisável está em `C:\Users\conta\AppData\Local\Temp\claude\C--Arquivos-GitHub-marin-telegram-bot\74d4f8ca-239b-46bd-b480-5a881cd34d81\scratchpad\ig_copy.db` (pré-visualização `miniapp-insta`). Deslizes que sobraram: no post 14 a Ma quase repete a legenda do Theo; no 9 a Bia fala de "a amiga que te arrastou"; o "entregando" voltou uma vez; numa rodada uma legenda saiu com lixo no fim ("tarde-cuntegn").
  - **Falta:** o Patrick revisar no app e, aprovado, **copiar esses textos exatos** pra produção (não gerar de novo); **refazer a foto do post 6** (Quartinho à noite, a foto saiu com luz de dia na janela). `scripts/instagram_acervo.py --refoto ID`, `--trocar ID [--base arquivo]` (só a troca de rosto), `--colocar ID --base arquivo`, `--textos`.
- **Revisão no app e produção (28/09, manhã, com o Patrick):** ele leu o feed na pré-visualização em tamanho de celular e aprovou sete ajustes (textos meus, lista abaixo). Os textos exatos da cópia foram pra produção sem gerar de novo (acervo + post 6 + a linha do Hoje; a conversa do post 8 ficou). **Foto do post 6:** a luz de fora agora segue a hora do rolê (noite das 18h às 5h) e o cabelo de cena passada não sai molhado; `--refoto` passou a refazer post de verdade. Foto nova do post 6 **aprovada** na 1ª (pose `fora_amigas_alguem_tirando`, pra não repetir o abraço do post 2 no mesmo bar; a rua escura com as luzes da cidade na janela; ~72 Buzz). A troca de "natural light" também pega o "Natural light" com maiúscula do molde da amiga tirando.
  - Textos que decidi (aprovados por ele): post 14, Ma pro Theo "essa jaqueta é nova? 👀"; post 9, Bia "da próxima vez me chama que eu quero um desse"; post 4, Bia "o milo posando melhor que a gente kkkkk"; post 10, Bia "que cor é essa? preciso"; post 12, Júlia "vocês foram pra onde depois?"; post 3, Júlia "de onde é esse vestido?" (era o único post da Ma sem comentário); post 15, Ma pra Carol "acordou cedo mesmo, orgulho kkkk".

## Freio e soak (28/09, 19:40 — decisão do Patrick)
Nada de funcionalidade nova até o soak fechar. Antes do soak: bug 16, voz (histórico velho, auditoria do prompt, promessa de foto), mundo (lista de compras, bateria social, sementes, revisão de textos), infra (relatório diário do soak + API de rotas) e auditoria de funcionamento rodada 3. Soak: 7 dias reais + 3 limpos; relatório gerado na VPS às 05:10 cobrindo 05:00→05:00. Detalhe e lista "Depois do soak" na seção 0 do `FRENTES_MARINA.md`.

**28/09, noite (frente da voz, sem mudança de tela):** a promessa de foto pendente no Por dentro agora pode ficar
mais tempo na lista (espera ela sair do banho/aula e olhar o celular; "quando eu chegar" espera a chegada); quando
vence, some da lista como antes (a dívida fica só no prompt dela). No prompt, o Instagram de ontem passou a dizer
"ontem, HH:MM" e "no post da Bia". Detalhe na Auditoria ("Frente da voz (28/09, noite)").

**28/09, noite (auditoria de funcionamento, rodada 3, sem mudança de tela):** o Hoje da noite de treino fica na ordem em que aconteceu: "Tomou banho" logo depois de "Voltou pra casa" da academia, "Foi pra calçada" (Milo) depois do "Jantou" e não dentro dele, o trabalho da faculdade na hora em que ela sentou em casa (não às 19:59 dentro de "Foi pra academia") e o bloco em casa começando depois do Milo voltar. Detalhe na Auditoria ("Auditoria de funcionamento, rodada 3").

**28/09, noite (frente de infra, sem mudança de tela):** o relatório diário do soak (VPS, 05:10) confere o app
sozinho: o **card do Agora** de hora em hora e em cada fala dela contra o mundo, e a **aba Hoje** como ficou no fim do
dia vai inteira no relatório, lado a lado com os acontecimentos. App mostrando o que não aconteceu é bug grave do
soak. Detalhe na Auditoria ("Frente de infra (28/09, noite): relatório diário do soak").

**30/09 — soak, dia 1 (29/09), sem mudança de tela:** o Hoje e o Agora de 29/09 mostravam "Foi pra PUC 06:22–15:00"
sem volta, "Brincou com o Milo" às 14:58 e "Almoçou no restaurante da PUC" com ela tomando sol no prédio, e o passeio
do Milo "da PUC pra Enseada". Com o mundo corrigido, dia de almoço na PUC tem a volta depois do almoço (16:06–16:51)
e o passeio sai de casa; "Foi pra calçada" (xixi da manhã) não cai mais dentro do banho; beliscos na cantina da PUC
aparecem no Hoje ("Beliscou um pão de queijo na cantina da PUC"); fofoca do porteiro, lâmpada, máquina de roupa e
varal só com ela em casa. O relatório diário ganhou "Mundo × mundo" (confere o Hoje contra o mundo). Detalhe na
Auditoria ("Soak, dia 1").

**30/09, manhã — soak, dia 2, sem mudança de tela:** o Hoje e o Agora mostravam "Regando as plantas" cinco vezes na
manhã (uma no fim do banho). Agora regar é uma vez de manhã e uma à tarde, o bloco em casa não repete o anterior e não
volta pra dentro do banho. Detalhe na Auditoria ("Soak, dia 2").

**30/09, 11:41 — Nubank e Hoje com uma escova que não aconteceu:** "Ophicina do Cabelo · cabelo −R$ 70", "Uber −R$ 12",
"Marcou o cabelo", "Saiu mais cedo na Ophicina". Desfeito a pedido do Patrick (saldo de volta a R$ 356). Causa e
conserto na Auditoria ("a escova que não aconteceu").

**30/09, tarde — o card do Agora com dois compromissos seguidos no mesmo lugar:** o 2º casting (17:00–18:30, mesma
agência) sumia do card — agora aparece "Na agência" e a volta. Hoje de 01/10: almoço pulado aparece como "não deu
tempo entre os compromissos". Detalhe na Auditoria ("30/09, tarde").

**30/09, noite:** o Hoje dizia "Beliscou pipoca vendo série" com ela no closet ou no TikTok — o lanche agora é
só "Beliscou pipoca". Detalhe na Auditoria ("pipoca vendo série").

**01/10, sem mudança de tela:** o Hoje mostrava "Tirou a roupa da máquina e estendeu no varal" às 21:57, no meio do
banho (21:34–22:01). Máquina, varal e as coisas do apê agora esperam o banho, a refeição e o Milo, e o varal sai
pelo menos 1 h depois da máquina. Detalhe na Auditoria ("01/10, manhã").

**01/10, catálogo de textos, leva 1 decidida (sem mudança de tela ainda):** as 205 fichas do Hoje e do card do Agora
fechadas com o Patrick (118 mudar, 87 manter), com seis regras gerais pra tela inteira: "~" vira "por volta das" na
frase e some dos números soltos; durações por extenso ("1 hora e 20 minutos"); gerúndio enquanto acontece e passado
depois ("Fazendo as unhas" → "Fez as unhas"); saída "Indo para o…" → "Está no…" → "Foi para o…"; detalhe aninhado,
um por linha (aulas perdidas em amarelo, itens do iFood, artistas enquanto ouve); "o Patrick" em tudo, nunca "você".
Regras e decisões em `data/feedback/catalogo_textos/` (não vai pro git). Aplicar: 106 só tela entram no soak; 12
"os dois" (ela lê) em lote separado.

**01/10, noite — lote 1 aplicado (Hoje + card do Agora, só tela) ✅:** os 118 "mudar" e as seis regras entraram em
`hoje.py` (texto curto), `agenda.py` (card) e `webapp/app.js`. Os 12 "os dois" também, mas como regra de tela: o mundo
grava o mesmo texto e o que ela lê não mudou (fora "chamando o Uber" no "se arrumando pra sair"). Hoje: "o Patrick"
no lugar de "você" (o Hoje não passa mais pelo `voz_painel`); saída "Indo para o…" → "Está no…" → "Foi para o…";
previsto "Vai para o Shopping da Gávea com a Bia" na hora em que ela sai de casa; gerúndio enquanto acontece (trabalho
da facul, masturbação, série, descida do Milo, treino no prédio); aninhados um por linha (aulas perdidas em amarelo,
itens do iFood, "Lavou o cabelo", artistas enquanto ouve, atraso com a aula e cada motivo); ícone da desistência
pelo motivo; período fechado "Manhã, 7 acontecimentos"; vazio "Ainda não acordou" / "Nenhum acontecimento". Card:
"por volta das" na frase e sem "~" nos números, durações por extenso ("há 1 hora e 20 minutos, faltam 58 minutos"),
"Indo dormir" / "Deita por volta das…", passos novos do caminho e de lá, celular "Na mão / No bolso / Pega nos
intervalos…" (`agenda.CELULAR_TELA`, só na tela: o bot ainda compara os textos internos "Olha …"), "Com" com artigo,
"A pé" com o bonequinho andando, em casa o que vem no futuro ("Vai ver série") e "desde as". Conferido na VPS numa
cópia do banco, código antigo × novo nos últimos 7 dias (Hoje 7 vezes por dia, card a cada 10 min): 0 erros.
Detalhe e o que eu decidi sozinho na Auditoria ("Catálogo de textos, lote 1 aplicado").

**02/10 — soak, dia 3 (01/10, o dia dos dois castings):** o Hoje dizia "Fez o casting na agência… agora é esperar a
resposta" às 18:30 do 2º casting, que ela largou no meio passando mal às 17:30 — agora é "Não terminou o casting
(…): saiu no meio, não tava se sentindo bem." e não tem resposta da Lívia. E os dois castings emendados na mesma
agência apareciam como duas saídas ("Foi para a agência" 14:58–17:00 e 17:00–17:53); agora é uma só, 14:58–17:53,
com os dois dentro. Hoje de 01/10 corrigido na produção (OK do Patrick). Detalhe na Auditoria ("Soak, dia 3").

**02/10, tarde — soak, dia 4, sem mudança de tela:** o tempo do mundo agora é o de Botafogo (o ponto era o Corcovado,
3 °C mais frio) e sabe de chuvisco; o que a tela e as fotos mostram de chuva passa a ser o tempo real. Detalhe na
Auditoria ("Soak, dia 4"). Foto que falha (recusa do Civitai) não muda nada no app; no chat, ela mesma explica e fica
devendo outra (Auditoria, "as duas fotos que não vieram"). Foto em loja ou café mostra o lugar por dentro, e a do
Instagram vem dessas fotos (Auditoria, "lógica da foto").

**02/10, noite — a barra de fome acompanha a comida fora em tempo real:** antes, depois do açaí e do Rei do Mate a
barra seguia subindo (só o mate contava, como beliscão); agora cai enquanto ela come cada coisa e sobe no ritmo
normal. O Hoje continua com o "Pediu…" de cada item (o "Comeu…" não repete). Detalhe na Auditoria.
Sem mudança de tela: as caras novas das fotos valem só pro clima, e nenhuma pose tem cara fixa (vem do sentimento).

**03/10, manhã — soak, dia 4, o Hoje mostra só o que aconteceu:** o que ela pede no rolê e o encontro com a amiga
contam da chegada de verdade (a caipirinha das 20:06 aparecia com ela ainda em casa, 22 min atrasada); One Piece e a
série da noite são dois itens, cada um na sua hora; num rolê com comida não aparece mais "Pulou o jantar: não deu
tempo" (a comida de lá é o jantar). Sem tela nova. Detalhe na Auditoria ("Soak, dia 4 da tarde em diante").
Pendentes do app vindos do /feedback (FRENTES, item 25): no Bastidores, "olhar redes sociais" com "celular no bolso";
secando o cabelo com a roupa da academia (ali é toalha); atraso "por trocar de look" e o Por fora com a mesma roupa.
O relatório do soak mostra o por dentro de hora em hora (o mesmo que a aba Por dentro deveria mostrar) — serve pra
conferir as barras do app contra o que ela sentia. Sem mudança de tela.

**03/10 — /feedback de 02/10, o que muda no Bastidores (sem tela nova):** no passo do banho do Se arrumando (e do
Indo dormir) o Celular é "Pega após o banho", não "No bolso"; do banho até o passo da roupa o Por fora mostra
"Enrolada na toalha" (sem a linha "Para"); quando o atraso é "Trocou de look", a roupa do Por fora troca de verdade
naquela hora; "olhando o X" é celular "Na mão". Detalhe na Auditoria ("/feedback do soak de 02/10").
/feedback antigo de 27/09 01:58 (card do "colocando pijama"): conferido em 03/10, já corrigido em 27/09 ("um card
só") — o pijama ficava preso depois do fim do card; hoje o "Indo dormir" vai até ela deitar (noite de 02→03/10 bateu).
Nada muda no Mini App (Auditoria, "Os dois /feedback antigos do item 25").
**03/10 — frente da voz (item 25):** nada muda no Mini App. A voz dos áudios virou uma só (o clone original; no
provocar e no sexting a mesma voz, um pouco mais devagar). Detalhe na Auditoria ("Voz do áudio e o lote dos /ruim").

**03/10, tarde — "Eu nem mandei áudio!" (frente de bugs):** nada muda no Mini App. O áudio dela passa a ser gravado
como áudio na conversa (ela lembra que mandou; o relatório do soak conta os áudios).
Às 14:16, a fala em laço dentro da mesma resposta passa a ser cortada; nada muda no Mini App.

### Mundo fechado pro soak (28/09, noite, frente do mundo) ✅
Item 3 da lista "antes do soak". Decisões do Patrick (28/09, múltipla escolha, todas na recomendada):
- **Lista de compras** (`lista_compras.py`): "vou colocar barrinhas na lista da semana" (08:52) passa a existir. O que
  ele pede e ela topa, ou o que ela diz que vai comprar no mercado, entra na lista (modelo barato, só quando o trecho
  fala de lista/mercado/compra da semana; também tira o que ela desistiu). **Pago com o dinheiro do pai** (compras da
  semana, fora do saldo e do extrato — D9). **No card do mercado**: embaixo de "Fazendo a lista" (Se arrumando) e de
  "Enchendo o carrinho" (Lá), em cinza, os itens ("barrinhas de proteína, granola") — conferido na pré-visualização em
  tamanho de celular (`miniapp-lista`). Na compra, o que foi anotado até ela encher o carrinho é comprado: no **Hoje**,
  dentro da saída, "Comprou barrinhas de proteína" / "Da lista, pedido do Patrick" (ícone `list-check`, sem valor).
  Não foi ao mercado: a lista espera; anotado depois do carrinho: fica pra próxima.
- **Bateria social:** café, açaí, farmácia, mercado, shopping, praia e médico sozinha não gastam mais como rolê
  (quase neutro); orla sozinha recarrega; Milo é passeio; academia, academia. Com amiga continua rolê.
- **Sementes de história:** o pai não vira mais semente; as outras ganham título com quem ("A Bia precisando de
  apoio", "Convite da Bia", "Retorno da Helena sobre o projeto") e fecham no próximo contato de verdade com a pessoa
  (sem contato, ela procura em 1–4 dias); sem ninguém, fecham em 2 dias. Na aba Mundo, "Rolando agora" mostra o
  título novo. O "Contato de Henrique" aberto desde 26/09 fecha na próxima mensagem do pai.
- **Bug 17 (roupa no sexting):** foto provocante (nível 1) já é a lingerie com algo por cima (moletom cinza aberto,
  camisetão branco ou robe de cetim rosa); no nível 2 ela tira o de cima; não volta a pôr. No Por fora: "Conjunto de
  renda preta com moletom cinza largo aberto por cima". Pose com roupa própria (moletom azul na cama) não troca mais a
  peça dela no clima.
- **Textos revisados com o Patrick (28/09, noite):**
  - Academia (card, Lá): **Cardio na esteira · Superiores ou Inferiores · Abdominais · Alongando** (era Aquecendo na
    esteira · Musculação/Funcional).
  - Milo: **Necessidades do Milo** no lugar de "Xixi do Milo" (card e Hoje).
  - **Sem ponto separador "·"** (regra dele): atraso no card "Vai sair pra PUC às ~06:45 (atrasada)", "Chega na PUC às
    ~07:15 (15min atrasada)"; no Hoje tudo com vírgula ("Moda e Corpo, dormiu mal", "Sábado 21:00, topou",
    "Emendou na volta, empolgada", "Se pesou" / "54,4 kg" embaixo, "Gel, vermelho").
  - **Atraso no Hoje em amarelo** na linha principal ("Chegou 15 min atrasada"), embaixo o porquê enxuto
    ("Ergodesign, perdeu o despertador, o ônibus demorou"). "Remarcou" / "Quartinho Bar, pra domingo 18:00".
  - Por fora: **"Pra quê" → "Para"** ("Te provocar" no lugar de "Pra te provocar"), **"Feita" → "Maquiagem"** ("Sem
    maquiagem"), a barra da make se chama **"Estado"**.
  - Aprovados como estavam: avisos do atraso, passos do Milo e do "Na calçada", Hoje da agenda viva, nomes das peças.
- **Textos que decidi sozinho nesta rodada (pra ele revisar):** "Comprou X" / "Da lista, pedido do Patrick" (ou "Da
  lista, ela tinha anotado"); títulos das sementes (lista acima, mais "{Nome} desmarcou um plano", "Desentendimento
  pequeno com {nome}", "{Nome} pediu uma ajuda", "Mico na frente {da pessoa}", "{Nome} ofereceu uma ajuda", "Elogio
  {da pessoa}", "Retorno {da pessoa} sobre um trabalho", "{Nome} falou de uma possível oportunidade de job"); peças
  de cima "moletom cinza largo aberto", "camisetão branco", "robe de cetim rosa"; "Sem maquiagem"; convite recusado
  em cima da hora ganhou motivo ("viu o convite em cima da hora" — antes "Recusou o convite (…): .").
- Ainda com "·", aprovados antes ou fora desta revisão (perguntar antes de mexer): barra do card "há 4min · faltam
  ~6min", "Manhã · 7", motivo do sentimento no Por dentro ("Viu Paradise Kiss · eps 1 e 2"), "Precisa de R$ X · motivo".
- Testes: `tests/test_lista_compras.py` (8), `test_social_battery_audit5` (+1), `test_social_day_audit6` (+1 e o
  fechamento), `test_roupa` (bug 17, 0 falhas em 40 rodadas), `test_hoje` (+1).
