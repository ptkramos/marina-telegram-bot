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

## 6. Status

| Etapa | Status |
|---|---|
| 1 Esqueleto + bastidores | ✅ 25/09 |
| 2 Banco | ✅ 25/09 |
| 3 Delivery pra ela | ✅ 25/09 |
| 4 Presentes, datas, aposentar comandos | ⬜ |

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
