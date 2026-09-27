# Painel de frentes da Marina

Uma conversa por frente. Pra começar, abra uma conversa nova e cole a frase de abertura da frente.
Ao terminar (ou quando o Claude avisar que é hora), a skill `passagem-de-bastao` atualiza este painel.
O detalhe de cada decisão está nos planos (PLANO_WEBAPP_MARINA.md, PLANO_VOZ_MARINA_V371.md) e na auditoria.

_Atualizado em 26/09/2026, noite._

---

## 1. Mundo e agenda — skill `frente-mundo`
**Abertura:** "bora na frente do mundo: conflito do rolê em dia de aula"

**Pronto (26/09):** agenda única (planejado, vontade, convite → mesma agenda com etapas); academia e passeio do
Milo decididos uma vez por dia; mercado e médico como itens (Bradesco Saúde, Samaritano/Novamed); tempo livre
concreto em casa; masturbação sem cota + convite pro sexting; fome em tempo real, saciedade, belisco e excesso no
peso; mídia real (música iTunes, leitura com compra, Botafogo pela ESPN, Last.fm dele); consumo no rolê;
**agenda reativa** (26/09, noite: conversa vira compromisso/remarca/cancela, sair mais cedo por motivo, aula largada
no meio, tesão como emergência — `agenda_reativa.py`); **unhas** (26/09, noite — `unhas.py`: cor, gel/esmalte,
desgaste; Ophicina do Cabelo na rotina/evento/mimo, R$ 180 do saldo; em casa entediada; pergunta a cor às vezes;
foto da mão depois; a cor em toda foto; seção Unhas no Por dentro); **cabelo** (26/09, noite — `cabelo.py`: lava dia sim, dia não no banho, penteado de agora, corte/luzes/hidratação, Ophicina junta o vencido e cobra do saldo, pergunta penteado e corte/cor, sugestão dele vira mudança, cabelo de agora em toda foto, seção Cabelo no Por dentro; textos revisados com ele na mesma noite).

**Próximo, nesta ordem:**
1. Conflito: rolê em dia de aula que começa antes da aula acabar sobrepõe volta e ida.
2. Revisar com ele os textos que decidi sozinho (listas no PLANO_WEBAPP: Milo, academia, preparos, "Na calçada", aviso de saída e Pix do uber…).
3. Pendências antigas do mundo (PLANO_VOZ 4, 5, 6, 8): virose com banheiro, pai ligando mais, job fora do Rio…
4. Bateria social: saídas sozinha (café, açaí) contam como rolê (SOCIAL) em `social_battery._kind_at` (achado 26/09).
5. Incoerências que a linha do tempo Hoje mostrou (26/09, noite): blocos do tempo livre não respeitam saídas nem o banho ("Montou looks" até 15:11 com a academia às 14:53; Instagram dentro da academia; música atravessando o banho); "Beliscou pipoca vendo série" com ela no bar; convite da Bia registrado às 04:19.

## 2. Apps (Mini App) — skill `frente-apps`
**Abertura:** "bora na frente dos apps: Bastidores aba a aba"

**Pronto:** iFood com abas (Início/Busca/Pedidos), ícones Tabler (outline, trocados em 26/09), recibos alinhados; linha do tempo Hoje (dia inteiro, saídas com o que rolou, previsto em cinza); Bastidores em abas; aba
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
**Abertura:** "bora na frente de bugs: volta do Quartinho (27/09)"

Bug do uso real: capturar primeiro (banco, mundo e log da produção), depois diagnosticar por camada (mundo → prompt → fala).

**Abertos:**
1. **Volta do Quartinho Bar (26→27/09).** Evidências salvas na conversa de 26/09 (conversas 42–69, world_state 104–194, evento 1).
   - **Ida a pé apesar do combinado.** Às 20:19–20:20 ele pediu "vai e volta de uber" e ela prometeu. A ida saiu a pé (20:48–21:00, `commute:outing:…:c1:ida`). A promessa não chega no modo do trajeto: a agenda reativa trata horário e cancelamento, mas não "vou de uber". Camada: mundo.
   - **Chat dizendo que ainda estava no bar, com ela em casa.** O mundo estava certo: a volta foi `uber_dividido` com a Bia, 23:59–00:05, e às 00:07 ela já estava em casa (`post_event_recovery`). Às 00:18 ela disse "acabei de terminar o drink, vou pedir o Uber"; às 00:20 disse "no quarto" e depois "me confundi, ainda tô na rua"; às 00:29 veio "Cheguei", mas pelo ritual `banho_rua`. Camada: prompt.
     - `post_event_recovery` não é `binding` em `world_context.py`, e o texto ("acabou de terminar o compromisso anterior, ainda em casa relaxando") não diz de onde ela voltou nem como.
     - O histórico ("te aviso quando chegar em casa") venceu o fato.
     - Ela também não avisou que chegou quando chegou (00:05): a promessa não virou gatilho.

## 6. Imagens (poses, prompts, motor) — skill `frente-imagens`
**Abertura:** "bora na frente de imagens: tenho poses pra mandar"

Cadeia única: pose de referência → prompt no jeito da casa (`photo_director.Pose`) → motor (Civitai Krea 2, LoRA `marinaX`).
O *quando* ela manda foto continua na frente da voz.

**Pronto:** pilha oficial decidida foto a foto (24/09); catálogo de 28 poses por cômodo com faixa de nível; sessão com seed; foto sem ela (comida, Milo, vista); unha e cabelo de agora em toda foto.

**Próximo:**
1. Poses que o Patrick mandar: resgatar o prompt (metadado do arquivo → texto do site → descrição) e virar pose do catálogo (PLANO_VOZ 1).
2. Ângulo dela sem rosto (de trás, por cima do ombro): sempre sai selfie de frente; quem puxa é o prompt (PLANO_VOZ 1d).
3. Fatores do gozo especial (PLANO_VOZ 1e); FinePorn v5 quando voltar ao Civitai (1g); acompanhar o slider de peso (9).
4. Do Patrick: trocar a chave do Civitai (vazou em 24/09).
