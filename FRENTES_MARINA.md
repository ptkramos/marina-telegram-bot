# Painel de frentes da Marina

Uma conversa por frente. Pra começar, abra uma conversa nova e cole a frase de abertura da frente.
Ao terminar (ou quando o Claude avisar que é hora), a skill `passagem-de-bastao` atualiza este painel.
O detalhe de cada decisão está nos planos (PLANO_WEBAPP_MARINA.md, PLANO_VOZ_MARINA_V371.md) e na auditoria.

_Atualizado em 26/09/2026, fim da tarde._

---

## 1. Mundo e agenda — skill `frente-mundo`
**Abertura:** "bora na frente do mundo: cabelo" (ou o item 2 abaixo)

**Pronto (26/09):** agenda única (planejado, vontade, convite → mesma agenda com etapas); academia e passeio do
Milo decididos uma vez por dia; mercado e médico como itens (Bradesco Saúde, Samaritano/Novamed); tempo livre
concreto em casa; masturbação sem cota + convite pro sexting; fome em tempo real, saciedade, belisco e excesso no
peso; mídia real (música iTunes, leitura com compra, Botafogo pela ESPN, Last.fm dele); consumo no rolê;
**agenda reativa** (26/09, noite: conversa vira compromisso/remarca/cancela, sair mais cedo por motivo, aula largada
no meio, tesão como emergência — `agenda_reativa.py`).

**Próximo, nesta ordem:**
1. **Etapa 1 — cuidados:** ✅ **unhas** (26/09, noite — `unhas.py`: cor, gel/esmalte, gastando; salão Ophicina
   do Cabelo na rotina/evento/mimo, pago do saldo; em casa entediada; pergunta a cor às vezes; foto da mão depois;
   a cor em toda foto). Revisar com ele os textos da lista no PLANO_WEBAPP ("Unhas — como ficou"). Próximo: cabelo.
2. Conflito: rolê em dia de aula que começa antes da aula acabar sobrepõe volta e ida.
3. Revisar com ele os textos que decidi sozinho (listas no PLANO_WEBAPP: Milo, academia, preparos, "Na calçada", aviso de saída e Pix do uber…).
4. Pendências antigas do mundo (PLANO_VOZ 4, 5, 6, 8): virose com banheiro, pai ligando mais, job fora do Rio…

## 2. Apps (Mini App) — skill `frente-apps`
**Abertura:** "bora na frente dos apps: Bastidores aba a aba"

**Pronto:** iFood com abas (Início/Busca/Pedidos), Bootstrap Icons, recibos alinhados; Bastidores em abas; aba
Agora decidida linha a linha (card layout D); tela inicial só com os apps.

**Próximo:**
1. Bastidores **aba a aba** com ele (Por dentro, Dinheiro, Mundo), como foi a Agora — ele quer ver no celular e
   ajustar palavra por palavra (PLANO_VOZ 14).
2. iFood da Ma e o banco dela nos Bastidores; `pedido_dela` no catálogo novo; pedidos dela de farmácia/mercado.
3. Fotos provisórias de marca e logos marcados "conferir"; redes sociais dela (Etapa 5).

## 3. Voz e chat — skill `frente-voz`
**Abertura:** "bora na frente da voz"

**Pronto (26/09):** balões inteiros e uma iniciativa por vez (fim das mensagens fora de ordem); ponto final
dividindo balão; vocabulário da masturbação; música que ele manda por link.

**Próximo:**
1. Regras das fotos por promessa (PLANO_VOZ 15) e auditoria do prompt (PLANO_VOZ 16).
2. Observar coerência entre turnos e qualidade das iniciativas no uso real (PLANO_VOZ 12, com /bom e /ruim).
3. Técnicas antigas (PLANO_VOZ 13).

## 4. Infra — skill `frente-infra`
**Abertura:** "bora na frente de infra: desempenho do resolve"

**Próximo:**
1. **Desempenho:** cada resolve do mundo leva ~7 s na cópia local, quase tudo no `sleep_plan` (~1.300 conexões
   SQLite por resolve). Cache por dia / conexão reaproveitada.
2. Do Patrick (ele faz): trocar a chave do Civitai (vazou em 24/09); firewall/porta 8000/certbot da VPS.
3. Last.fm dele configurado, mas o perfil ainda tinha 0 scrobbles (Apple Music no iPhone precisa de app de scrobble).
