---
name: frente-apps
description: Frente "apps" da Marina — o Mini App do Telegram (iFood, Nubank/Pix, Bastidores com as abas Agora, Por dentro, Dinheiro, Mundo), comprovantes e catálogo de lojas. Use quando o Patrick falar de app, tela, Bastidores, iFood, Pix, comprovante, card, layout ou alinhamento.
---

# Frente: apps (Mini App)

## Regras do Patrick
- **Chat é chat, app é app:** nada de notificação de sistema no chat; o app mostra, ela só "compartilha" com botão.
- **Ícones: Bootstrap Icons, nunca emoji.** **Alinhamento impecável** (inclusive nos comprovantes em imagem).
- Ele decide texto e layout **linha a linha**: mostre mockup (show_widget) com 2–4 opções e pergunte
  (AskUserQuestion). Ele é visual.
- Marcas reais podem (uso pessoal). Nunca raspar a API interna do iFood.

## Comece assim
1. Leia "2. Apps" em `FRENTES_MARINA.md` e as seções do `PLANO_WEBAPP_MARINA.md` sobre a tela em questão.
2. Suba a pré-visualização com dados reais: `.claude/launch.json` → "miniapp-real" (cópia do banco da produção no
   scratchpad; baixe uma cópia nova com scp se precisar) ou `scripts/webapp_preview.py --db copy --agora ISO`
   (rota local `/dev/agora?t=…&mundo=1` resolve o mundo numa hora simulada).
3. Confira no tamanho de celular (resize_window mobile) antes de mostrar a ele.

## Onde fica
- Servidor: `webapp_server.py` (rotas `/api/*` com initData; textos do painel: `TELEFONE`, `CELULAR_POR_ATIVIDADE`,
  `status_view`, `emocao_view`, `mov_desc`).
- Front: `webapp/index.html`, `webapp/app.js` (loaders por tela, `ic()` pra ícone), `webapp/app.css`.
- Card da aba Agora vem pronto do `agenda.py` (`card`/`card_casa`) — mudar dado de card é na frente do mundo.
- Catálogo: `webapp/catalogo.json` (lojas reais de Botafogo e cardápios; scripts `scripts/ifood_*.py`).
- Comprovantes: `recibo.py` (PIL, âncoras e largura em pixel).
- Deploy de front sem reiniciar deixa o servidor velho: se mudou rota/JSON, precisa reiniciar (pedir OK se ele
  estiver conversando com ela).
