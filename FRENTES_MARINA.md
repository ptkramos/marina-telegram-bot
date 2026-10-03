# Painel de frentes da Marina

Uma conversa por frente. Pra começar, abra uma conversa nova e cole a frase de abertura da frente.
Ao terminar (ou quando o Claude avisar que é hora), a skill `passagem-de-bastao` atualiza este painel.
O detalhe de cada decisão está nos planos (PLANO_WEBAPP_MARINA.md, PLANO_VOZ_MARINA_V371.md) e na auditoria.

_Atualizado em 03/10/2026, manhã (/feedback de 02/10 lidos e corrigidos — seção 5, item 25: não responde mais no
banho, foto e Pix esperam como mensagem, toalha depois do banho, troca de look de verdade, mensagem cruzada, Pix com o
combinado, "Kkkkk" no começo). **Próxima conversa: frente da voz — a voz do áudio variando (ouvir junto) e o lote dos
/ruim de 02/10** (item 25, "Aberto"). **Soak: dia 1 = terça 29/09**; depois: "bora no soak, dia 5" no domingo de manhã
(relatório `soak/dia-2026-10-03.md`, com `chat.enviado` e `photo_director.cena` a partir do deploy; sábado tem Quartinho de
novo com a Júlia e o convite da Bia). Aberto pra frente do mundo: o preparo pra dormir que volta de passo._

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
4. ✅ Infra: custo da API de rotas + **relatório diário do soak** — feito em 28/09, noite (seção 4; timer na VPS às
   05:10, `scripts/relatorio_soak.py`)
5. ✅ Auditoria de funcionamento, rodada 3 (tudo junto, na cópia do banco dentro da VPS) — feita em 28/09, 23:40
   (seção 7; bug 18 na seção 5)
- Do Patrick (não segura o soak, mas não esquecer): firewall/porta 8000/certbot. (Chave do Civitai: ele decidiu não trocar
  em 02/10 — não houve vazamento real.)

**Soak (decidido):** **7 dias reais + 3 limpos.** Bug achado é corrigido no dia seguinte, só conserto (sem
funcionalidade nova, deploy respeitando a regra dos 5 min). Libera coisa nova quando os 3 últimos dias passarem sem
bug grave; apareceu um, os 3 dias limpos recomeçam. **Bug grave:** ela contradiz o mundo (lugar, atividade, comida,
roupa, dinheiro), o app mostra algo que não aconteceu, erro/traceback, mensagem quebrada ou fora de ordem, custo fora
do normal. Texto feio ou gosto → anotado e corrigido em lote, não zera a contagem.
Durante o soak ele usa normal e marca o que estranhar com /bom e /ruim; abertura do dia: "bora no soak, dia N".
**Meta (Patrick, 02/10, noite):** "pegar todos os problemas e destruir eles, em todas as frentes" — depois do soak
a Marina fica lisa e pronta pras funcionalidades novas. **Leitura do soak, melhorada antes do dia 4** (no 02/10 ele
achou três coisas que eu deixei passar: as fotos com desculpa fixa, a comida que não matou a fome, o fundo de rua no
Rei do Mate): (1) relatório com conferências novas — comida × fome (comeu e a fome não caiu; compra de comida sem
refeição), foto pedida/prometida × foto que chegou e o que foi no lugar, mensagem enviada fora do histórico, fundo
da foto × lugar; (2) seção "o Patrick estranhou" (fala dele com "?!", "como assim", "n entendi", correção) com o
mundo daquela hora; (3) meu roteiro de leitura: além das suspeitas, a conversa inteira com o mundo do lado, e todo
erro do log seguido até o que ele recebeu. É conserto da ferramenta do soak (infra), não funcionalidade nova.
**Feito em 03/10** (`scripts/relatorio_soak.py`): roteiro de leitura no topo do relatório; conferências comida ×
fome (comeu e não caiu, voltou alta em 2 h, comprou e não virou refeição) + fome de hora em hora; foto pedida/
prometida/começada × foto que chegou, com o que ela mandou no lugar e o erro do log; enviado pro Telegram ×
histórico e fundo da foto × lugar (o bot passou a registrar `chat.enviado` e `photo_director.cena` no log — valem
dos relatórios de 04/10 em diante); "O Patrick estranhou" com a fala dela antes, o mundo e a resposta; cada erro de
verdade com o que veio depois; exceção de handler não cai mais em "rede" (o BadRequest do /ruim 055 caía); e o que
a leitura de 03/10 achou à mão: compra num lugar com ela em casa, "se divertindo" em casa, "banho tomado" sem
banho desde a volta. Rodado no 02/10: pega as duas fotos que falharam, 3 dos 6 graves da noite e a caipirinha.
Ainda em 03/10 (o Patrick: "não lê nenhum sentimento pra saber por que a Marina toma as decisões que toma"): seções
**/feedback do Patrick**, **Por dentro, de hora em hora** (energia, humor, fome, tesão, sono, desconforto, ciclo e os
sentimentos com a causa — o mesmo `EmotionEngine.feeling` que decide a agenda, refeito pra cada hora) e **Decisões
dela e o que pesou** (vontade × peso de cada saída/compromisso, a favor e contra pelo `Disposicao.avaliar` daquela
hora, mais vontades, remarcações, convites e atrasos com o motivo). A bateria social não tem histórico no banco
(só o valor de agora) — lacuna anotada. Pistas já no 02/10: "carinhosa 0,88" às 00:30 porque ele perguntou do banho;
a dor de cabeça das 18:30 não aparece entre os pesos da saída.
**Placar:** dia 1 (ter 29/09) — 5 graves (lugar dela errado depois da aula e a fala seguindo, plantão "de amanhã",
"boa noite" de manhã no banho), 2 médios, 4 textos feios; corrigidos em 30/09 (seção 5, item 19). Dia 2 (qua 30/09), manhã, antes daquele
deploy — "alucinada": [ELE ESTÁ DOENTE] com a pergunta dele, "dia livre" com ela faltando, check-in do peso dela,
plantas 5x; corrigidos em 30/09 (item 20). Dia 2, resto do dia (relatório lido em 01/10) — 1 grave (varal no meio
do banho), 1 médio (foto da conversa fora do histórico), 7 textos feios (4 de pontuação, já no filtro); corrigidos
em 01/10 (item 21). Dia 3 (qui 01/10, os castings) — 3 graves ("hoje é dia livre" tendo faltado, "a canja chegou"
no dia seguinte, Hoje com o 2º casting feito que ela largou no meio), 3 médios (foto dele sem leitura, agência duas
vezes no Hoje, bom dia antes da resposta da madrugada), 4 textos feios; corrigidos em 02/10 (item 22). Dia 4 (sex
02/10), olhado até 15:41 — 3 graves ("GATE_CHANNEL" na fala, "aqui tá sequinho" com chuvisco, "a câmera do apê travou" no lugar de duas fotos), 2 médios (foto dele
sem leitura de novo, confirmação do /ruim que não chegou); corrigidos na hora (item 23). Dia 4, da tarde em diante
(lido em 03/10) — 6 graves (Uber combinado e foi a pé, caipirinha com ela em casa, "se divertindo ainda" em casa,
"apaguei no sofá", "banho tomado" sem banho, "vele"), 7 médios (avisos de saída/chegada, convite em cima do da Bia,
boa noite no banho, TV num item só, jantar "pulado" no bar, preparo pra dormir que volta de passo), 6 textos feios;
corrigidos em 03/10 menos o preparo pra dormir (item 24). Dias limpos: 0.

**Relatório diário (pronto, 28/09):** gerado sozinho na VPS às **05:10** (o dia dela vira às 5h — Patrick
perguntou 00:00 × 05:00 e ficou 05:00: o rolê da noite e a conversa de madrugada ficam no mesmo dia), cobrindo
05:00→05:00, em `/root/bots/marina/soak/dia-AAAA-MM-DD.md` (fica na VPS, como o banco). Conteúdo: a conversa do dia
com hora; o mundo (`world_state`) × card × Hoje × acontecimentos; **contradições que o script acha sozinho** (fala dela
× lugar/atividade do mundo naquela hora, número sumido da fala, foto × roupa, card × mundo); /bom e /ruim; erros do
journal; custos (Buzz, rotas, LLM) e fotos geradas; iniciativas. Eu leio na conversa "bora no soak, dia N", explico e
listo os bugs.

**Depois do soak (congelado):** o Patrick rabisca as ideias pelo celular em https://claude.ai/artifact/64rLbsTa3m5CmdhdtnJgEQ
("Ideias pós-soak", respostas no banco da página, coleção `ideias`: ler com ArtifactData quando o soak fechar).
**Preenchida por ele em 02/10, noite** (6 ideias: banheiro, em_casa, lovense, provocar_saida, roupa_nova, selfies); cópia
em `data/feedback/ideias_pos_soak/ideias/*.json` (não vai pro git).
 **Hoje com bloco "Em casa"** (Patrick, 30/09: o que ela faz em casa, aninhado, como as
saídas — 1º da frente de apps); salão pelo humor/remarcado pela conversa; virose com banheiro, pai ligando mais, job
fora do Rio; roupa nova comprada no shopping; iFood da Ma, banco dela, `pedido_dela` no catálogo novo, pedidos dela de
farmácia/mercado; fotos provisórias de marca e o X dela; técnicas antigas da voz (PLANO_VOZ 13); imagens (flash no
quarto, foto de grupo em casa/duas amigas, poses novas, ângulo de trás, fatores do gozo especial, rostos novos);
**selfie sozinha fora de casa** (Patrick, 02/10: só existem duas, "selfie na rua" e a da mão na boca — fotos fora
vão repetir); **ir ao banheiro do lugar pra mandar foto mais ousada** (Patrick, 02/10: lingerie na rua não, a não ser
que ela vá ao banheiro do local); roupa de provocar + saída (02/10: ela disse "baby-doll por baixo", pro mundo ele
saiu quando ela se vestiu pro açaí); **brinquedo Lovense pelo Mini App** (Patrick, 02/10, noite: um controle no
app pra brincar à distância quando ela quiser — decidir com ele quem controla o quê, o brinquedo de verdade é dele ou
é o dela na história, e como a fala e as fotos dela acompanham); **bebidas nos pedidos e vinho no mercado, Marina
bêbada** (/feedback de 30/09); **esquecer o aviso pelo sentimento** (03/10: o
sorteio de 5% saiu e ela sempre cumpre; esquecer de verdade — empolgada com a amiga, bateria lá embaixo — é
comportamento novo).
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
concretos, fecham no próximo contato com a pessoa); as barrinhas de 08:52 já estão na lista da produção (OK do
Patrick, 23:20; próxima compra sábado ~10:58); **bug 17** (lingerie por baixo desde a 1ª foto do clima); **textos
revisados com ele** (sem "·", atraso amarelo no Hoje, academia e Milo novos, Por fora Para/Maquiagem/Estado).

**Próximo** (congelado até o soak fechar; "ver no uso real" é o próprio soak):
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
**Abertura:** congelada até o soak fechar (freio, seção 0); o Instagram no uso real é visto no soak. Exceção
liberada: **"bora na frente de apps: catálogo de textos, leva 2 (Bastidores)"** — o lote 1 já está no ar (01/10).
**Exceção liberada durante o soak (Patrick, 30/09): "bora na frente de apps: catálogo de textos"** — página com todos
os textos visíveis por categoria (Hoje, card do Agora, Bastidores, iFood, Nubank, Instagram), cada um com exemplo
real, onde/quando aparece e a marca **só tela / ela lê / os dois**; ele preenche no ritmo dele e eu aplico em lotes.
**Prévia ao vivo (Patrick, 30/09):** cada texto dentro de uma cópia fiel do componente (CSS do `webapp/app.css`: linha do
Hoje, card do Agora, extrato…), antes × depois lado a lado, largura de celular (ver quebra de linha), e texto com
variável mostrando exemplos reais do banco, inclusive o mais longo; muda enquanto ele digita.
Só tela entra no lote durante o soak (não zera); "ela lê" com cuidado (lote claro, ou depois do soak). Já na fila do
catálogo: "Faltou a aula" gigante, belisco no Hoje, nome do bloco "Em casa".
**Leva 1 no ar (30/09, noite):** Hoje + card do Agora, 205 textos, página no claude.ai com banco próprio (coleção
`textos`: linha/embaixo/decisao/nota por ficha). Código em `scripts/catalogo_textos/` (`varre_textos.py` roda na VPS
numa cópia do banco em /tmp/catalogo, com o código copiado pra /tmp/catalogo/code; `gera_catalogo.py` casa os textos;
`monta.py` gera o HTML). Dados reais em `data/feedback/catalogo_textos/` (nunca commitar). **Troca de conta (01/10):** o
Patrick segue o catálogo em outra conta do claude.ai (mesmo PC). A página antiga é privada da conta velha; as 59
decisões dele foram salvas em `data/feedback/catalogo_textos/decisoes/textos/*.json`. Na conta nova: rodar `monta.py`,
publicar `data/feedback/catalogo_textos/catalogo_textos.html` como artefato novo com `capabilities: {db: {}}`, semear a
coleção `textos` com os JSON das decisões (ArtifactData batch, sem `version`) e mandar o link. **Feito (01/10):** conta nova em https://claude.ai/artifact/7B9uEC9tqYNai5zC8TPokU com as 59 decisões semeadas (26 mudar, 25 conversar, 8 manter). **Leva 1 decidida inteira (01/10):** 205 fichas, 118 mudar e 87 manter (as 45 "conversar" fechadas no chat, com 6 regras gerais em `data/feedback/catalogo_textos/regras_gerais.md`: "~" vira "por volta das", durações por extenso, gerúndio enquanto acontece, Indo/Está/Foi nas saídas, detalhe aninhado um por linha, "o Patrick" em tudo). Cópia das decisões em `decisoes/textos/`. **Lote 1 aplicado (01/10, noite) ✅:** os 118 "mudar" e as seis regras no Hoje e no card, só na tela (o mundo grava
igual; detalhe e o que eu decidi sozinho na Auditoria, "Catálogo de textos, lote 1 aplicado"). Ficam pra depois do
soak os assuntos que vêm como frase e a foto do provador (frente de voz).
**Leva 2 no ar (02/10, noite):** Bastidores (moldura, Por dentro, Por fora, Dinheiro, Mundo), iFood, Nubank (com os
comprovantes) e Instagram, 253 fichas, no **mesmo link** da leva 1 (a página agora mostra só a leva 2; as decisões da
leva 1 seguem no banco). Cada ficha mostra o HTML real da tela (o mesmo do `webapp/app.js`/`insta.js`) com o
`webapp/app.css` escopado, celular com 375 px. Ficha nova "lista": palavras do mesmo campo separadas por " / " (ex.:
"Exausta / Cansada / Ok / Cheia de energia"). Código em `scripts/catalogo_textos/`: `varre_leva2.py` (roda na VPS
sobre a cópia do banco em /tmp/catalogo2, com o código copiado pra /tmp/catalogo2/code; só o JSON volta, em
`data/feedback/catalogo_textos/varredura_leva2.json`), `gera_leva2.py` (fichas) e `monta_leva2.py` (página). Notas já apontam as regras da leva 1 que esbarram aqui: regra 6
("você" → "o Patrick": 12 fichas), "·" (14), durações abreviadas (4), "~" (1); 61 fichas são cópia do app de verdade
(iFood/Nubank/Instagram). 29 fichas das regras 1, 2, 6 e "sem ·" já semeadas como "mudar" (OK dele, 02/10; cópia em `decisoes/leva2_preenchidas_pelo_claude.json`). **Próximo:** ele decide pelo celular; eu leio a coleção `textos` (ids `b.`, `d.`, `f.`, `n.`,
`m.`, `if.`, `nu.`, `ig.`, `i.`, `e.`) e aplico em lote (só tela no soak; "os dois" com cuidado).

**Pronto:** iFood com abas (Início/Busca/Pedidos), ícones Tabler (outline, trocados em 26/09), recibos alinhados; linha do tempo Hoje (dia inteiro, saídas com o que rolou, previsto em cinza); Bastidores em abas; aba
Agora decidida linha a linha (card layout D); tela inicial só com os apps; **Instagram** no ar (27/09) com acervo refeito
(folhas das quatro amigas, fotos e textos sem fórmula) e textos revisados por ele no app e na produção (28/09); foto de
fora à noite com luz de noite; post 6 refeito. **Bastidores revisado aba a aba (28/09)**: Por dentro; Por fora
(nova: Agora com roupa e make de verdade → Peso → Cabelo → Unhas); Dinheiro (mês, próximo cachê, contas, extrato agrupado por saída); Mundo (pessoas por
círculo, Onde ela foi no mês, Rolando agora sem fio de sistema).

**Próximo:**
0. **Depois do soak, o primeiro:** Hoje com bloco "Em casa" — o que ela faz em casa (celular, belisco, mensagens,
   closet…) aninhado num bloco com hora e cômodo, como as saídas já são (esboço de 30/09, com TikTok, chocolate,
   manicure marcada e Bia dentro). A decidir linha a linha: **o nome do bloco** (não é "Ficou em casa", Patrick
   30/09 — só rascunho do esboço) e os textos; onde o bloco começa e termina; se banho, Milo na calçada, refeições,
   sessão de trabalho e o íntimo entram dentro ou ficam fora.
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

**Pronto (28/09, noite — fechado pro soak):** **relatório diário do soak** (`scripts/relatorio_soak.py`, timer
`marina-soak.timer` às 05:10 de São Paulo; `soak/dia-AAAA-MM-DD.md` na VPS; cópia do banco em /tmp, sem API paga):
conversa com o mundo, Hoje, acontecimentos, /bom e /ruim, erros, custos e suspeitas automáticas (fala × lugar e
atividade, fala × o que ela fez, card × mundo, fala quebrada, foto × roupa, ordem). Calibrado em 26–28/09: achou
sozinho os bugs 14 e 16 e o sanduíche. **Dia N** conta de `soak/inicio.txt` — criar com a data do dia 1 quando o soak
começar (`echo AAAA-MM-DD > /root/bots/marina/soak/inicio.txt`). Ler um dia sem esperar: `ssh … "cat
/root/bots/marina/soak/dia-AAAA-MM-DD.md"`; gerar de novo: `venv/bin/python scripts/relatorio_soak.py --dia AAAA-MM-DD`.
**API de rotas:** a produção faz 2–10 chamadas por dia (um trecho, uma chamada, guardada); agora só o bot rodando paga
(`commute.BOT_VIVO`), script e varredura usam a tabela. Detalhe na AUDITORIA.

**Próximo:**
1. Soak: ler o relatório de cada dia na conversa "bora no soak, dia N" e ajustar as regras de suspeita se acusarem
   à toa (falso positivo) ou deixarem passar um bug que o Patrick viu.
2. Do Patrick (ele faz): firewall/porta 8000/certbot da VPS. (Chave do Civitai: não troca, decisão dele em 02/10.)
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

18. ✅ **A noite de 28/09 depois da academia (auditoria de funcionamento, rodada 3)** — corrigido em 28/09
    (`tests/test_auditoria3_2809.py`, 15; `test_rituals_c3` atualizado). Mundo: treino 18:50–20:09, casa 20:21.
    - **Milo no meio do jantar.** Xixi da noite 21:30–21:38, jantar 21:07–21:41, mundo em "jantando". O acontecimento
      saía na hora sorteada. Agora espera ela terminar (comendo, banho, estudo) e desce em seguida. Camada: mundo
      (`milo.py`).
    - **"Trabalhou no trabalho de Práticas Experimentais VI" às 19:59, na academia.** Gravado às 20:29 com a hora
      planejada; o Hoje pôs o trabalho dentro do treino. Agora começa quando ela está livre em casa; sobrando menos de
      20 min, não senta. Camada: mundo (`college.py`).
    - **Sem banho depois do treino.** Estudo e jantar pegaram a vez; banho só 21:52. Decisão do Patrick: **banho logo
      ao chegar** — marcado pra chegada quando ela sai da academia; o resto espera. Camada: mundo (`rituals.py`).
    - **"Vou deitar agora" (21:45) e banho 21:52–22:17.** Decisão do Patrick: **banho antes do boa noite** — o banho
      da noite começa até 65 min antes de deitar; sem banho na hora do boa noite, toma primeiro; ocupada, o boa noite
      espera e o deitar vai 15 min pra depois. Camada: mundo (`rituals.py`).
    - De passagem: bloco em casa começando antes do fim do Milo (21:50 × 21:53). Camada: mundo (`tempo_livre.py`).

19. ✅ **Soak, dia 1 (terça 29/09)** — relatório de 30/09 05:10 com 0 suspeitas; lido na conversa "bora no soak, dia
    1" e corrigido em 30/09 (`tests/test_soak_dia1.py`). O Patrick: "a maioria é inconsistência de onde ela está".
    - **15:01 "Cheguei em casa" com a aula até 15:00** (ele pegou na hora). Almoçou na PUC às 15:18 e a volta saiu
      16:06, mas entre 15:00 e 16:06 o mundo não tinha estado "na PUC" e caiu na rotina de casa. Agora, entre o fim
      da última aula e a volta, ela está por lá ("saindo da aula, indo almoçar", "almoçando no restaurante da PUC").
      Camada: mundo (`world_state._depois_da_aula`).
    - **16:06 "indo da PUC pra Enseada a pé".** O passeio do Milo foi marcado 16:25 contando a chegada sem o almoço, e
      o trajeto emendou a volta da PUC com a ida pro passeio. A volta da PUC conta o almoço por lá; a faculdade ocupa
      até ela chegar; passeio do Milo nunca emenda (sai de casa e volta pra casa). Camada: mundo (`commute.py`,
      `world_state.RoutineEngine._class_busy`).
    - **16:13–18:13 "terminando o trabalho" passeando e fazendo as unhas.** Às 16:13 o mundo dizia o absurdo acima e
      ela inventou; às 17:57 o prompt dizia "fazendo as unhas na Ophicina" e ela seguiu a história. Com o mundo certo
      a origem some; o bloco "desde a sua última mensagem" agora diz que o que ela disse que estava fazendo também
      ficou velho. Camada: voz (`since_last.py`).
    - **19:01 "o plantão de amanhã" e 19:37 "seu plantão"** (ele de folga, próximo é quinta). O assunto em aberto
      "Patrick terá um plantão amanhã" era de 27/09 e seguia "amanhã". Data relativa vira o dia de quando foi anotado
      ("na segunda (28/09)"), no que entra e no que é lido. Camada: memória (`db.ancorar_datas`).
    - **05:36 "Boa noite, te amo demais tb" de manhã, no chuveiro.** Resposta adiada da madrugada. No banho nada sai
      da fila; a resposta atrasada sabe quando ele escreveu e que é agora. Camada: voz (`bot.py`).
    - **Milo 05:39 no meio do banho (05:23–05:47).** O xixi da manhã espera o banho/café (até 1 h). Camada: mundo
      (`milo.py`).
    - **"Morrendo de fome" 11:47, nada até 15:18** (quatro aulas seguidas). Decisão do Patrick: **conserto agora** —
      com fome, ela belisca na cantina na troca de aula. Camada: mundo (`meals._belisca_na_puc`).
    - **15:37 "o Seu Jorge contou uma fofoca quando ela passou pela portaria"** (achado na simulação, com ela na PUC).
      Coisa de casa (portaria, lâmpada, máquina de roupa, varal) espera ela estar em casa. Camada: mundo (`casa.py`).
    - **Relatório com 0 suspeitas.** Ganhou "mundo × mundo" (teleporte, trajeto saindo do lugar errado, refeição ×
      lugar, coisa no meio do banho), "trabalho" dito na rua e saudação fora de hora. No dia 29 acusa todos os de cima;
      em 27 e 28, só casos reais daqueles dias. Camada: infra (`scripts/relatorio_soak.py`).
    - Ruído: agenda reativa com resposta vazia do modelo vira aviso, não traceback.
    - Texto feio (lote da voz, não zera): os 4 /ruim do dia — "Deu tudo tranquilo mesmo" (concordância), "Se achou,
      aguenta" (fora de contexto), "seu convencido" (repetido, sem motivo), "trabalho se achando importante" (sem
      sentido).

20. ✅ **Soak, dia 2 (quarta 30/09, manhã) — "ela tá completamente alucinada"** (Patrick, ~09:00; tudo antes do
    deploy do item 19, às 08:55). Olhado na hora em vez de esperar o relatório; corrigido em 30/09
    (`tests/test_soak_dia2.py`).
    - **08:38 "Kkkkk vc que tá dodói".** Ele perguntou "Tá dodói? O que houve?" (ela com cólica) e o
      `[ELE ESTÁ DOENTE]` entrou por várias mensagens. Pergunta (frase com "?") ou fala com "vc/tu/tá dodói" é sobre
      ela, não conta. Camada: voz (`health.patrick_sick_hint`).
    - **"Hoje é dia livre" / "ainda bem que hoje não tem aula"** — ela faltou por cólica (05:22). Faltar cancela as
      aulas e o prompt dizia "Hoje NÃO tem aula (dia livre)". Agora: "Hoje TINHA aula e você faltou — …", e o bom dia
      também. Camada: voz (`world_context`, `rituals._bom_dia`, `College.falta`).
    - **08:36 "Lembrei daquele papo do meu peso, tem alguma novidade ou continua tudo igual por aí?"** — o assunto
      em aberto era "Esclarecer se o peso mencionado por Marina aumentou ou diminuiu". Assunto só dela (sem Patrick/
      ele) não vira pergunta de check-in a ele. Camada: memória (`db.get_open_loops_para_checkin`).
    - **"Regando as plantas" 07:01, 07:26, 07:39, 07:49 e 08:49**, a das 07:26 no fim do banho (07:03–07:30). Antes
      das 8 só existia esse tipo; cada pedaço sorteava de novo. Agora não repete o que acabou de fazer, regar é uma
      vez de manhã e uma à tarde (sem outra opção: celular ou o Milo), e o bloco não volta pra dentro do banho.
      Camada: mundo (`tempo_livre.py`).
    - **Manhã, depois do deploy — a escova que não aconteceu** (Patrick: "problemas sérios de rota de novo"). 11:03,
      com cólica forte (desconforto 0,8), na hora das aulas que faltou e com ele escolhendo a comida dela, a vontade
      marcou escova na Ophicina 11:22 ("job amanhã"). A saída atrasou de propósito (ida 11:45–11:55); às 11:36 a
      canja chegou e ela comeu em casa, e o "passando mal" da agenda reativa tratou como "saiu mais cedo da
      Ophicina": volta de uber de onde ela nunca esteve, R$ 70 de escova e R$ 12 de uber cobrados, "saí mais cedo do
      salão" no chat, e às 11:48 ela "indo pro Ophicina a pé" de novo. Consertos: só está "lá" quem chegou
      (`AgendaReativa._atual` conta a ida); saída por vontade (salão, unhas, café) não acontece passando mal
      (desconforto ≥ 0,5), na hora da aula que faltou nem com comida a caminho (`Vontade._sem_condicao`). Camada: mundo.
      Decisão do Patrick: **desfazer tudo** — escova cancelada, R$ 82 de volta ao saldo, fora do Hoje, cabelo como
      estava, as duas falas do salão corrigidas no histórico (originais em `soak/originais-2026-09-30-salao.json`).
    - **Tarde (12:16–18:11) — "tô fechando o trabalho" sem trabalho no mundo.** Entrega amanhã; a sessão do dia só
      às 20:21; ela prometeu "vou pegar firme", disse "tô fechando agora" (13:45) e "ainda tô no trabalho" (15:11)
      lendo mangá, vendo desfile e jogando Stardew. Decisão do Patrick: **a fala vira mundo** — livre em casa,
      "vou fazer/tô fazendo o trabalho agora" adianta a sessão do dia pra agora (`College.observe_marina_line`).
      Camada: mundo. 19:56 "voltei pro arquivo, juro" (no Instagram, antes do reconhecimento pegar "voltei pro") —
      a frase entrou no reconhecimento e a sessão da noite foi marcada como começada às 19:56 na produção.
    - **17:56 "e a entrega de Práticas Experimentais VI, saiu alguma coisa?"** — de novo o assunto dela perguntado a
      ele (o lembrete não tinha nome nenhum). A instrução do check-in dizia "algo que o Patrick comentou, pergunte se
      tem novidade"; agora: coisa dele, pergunta; coisa dela, conta como está. Camada: voz (`proactivity_service`,
      `bot._PROACTIVE_INSTRUCTIONS`).
    - **13:06 "já tem cabelo novo"** — o "assunto do momento" do planner ainda era "ida ao salão e cuidados com o
      cabelo" (não foi limpo no desfazer do salão, falha minha). Lembrete falso "Contar como ficou o cabelo" fechado.
    - **15:14 "vai###"** — resto de formatação do modelo; `limpar_fala_marina` tira `##`+. Camada: voz.
    - Texto feio (lote, não zera; print do Patrick 30/09): no Hoje, "Faltou a aula hoje (Acessórios de Moda e
      Extensões do Corpo e Conteúdos Estruturantes: Projetar para a Sociedade e Projeto: Projetar em Sociedade): cólica
      forte, ficou em casa" em 5 linhas. `hoje.curto` só reconhece o texto da agenda viva ("Faltou a aula **de** hoje
      … Vai pegar a matéria"); o do `college.morning` ("Faltou a aula hoje (…): motivo") cai na frase interna inteira.
      E mesmo o curto põe a lista de matérias no cinza. Vai pro catálogo de textos (o Patrick decide linha e cinza).
    - **"Beliscou pipoca vendo série" (10:03 no closet, 18:41 no TikTok)** — a segunda vez que o Patrick via. O
      cardápio de lanche trazia a cena pronta ("pipoca vendo série"): o Hoje afirmava uma série que não existiu (app
      mostrando o que não aconteceu). Agora o lanche é só "pipoca" (`meals.MENU["lanche"]` e o lanchinho da noite).
      Os dois de 30/09 corrigidos na produção ("Beliscou pipoca."). Decisão (Patrick + Claude, 30/09): o mundo
      continua sabendo o que ela beliscou (a conversa e a conferência de comida do relatório dependem disso); como o
      belisco aparece no Hoje (ex.: "Beliscou" na linha, o item em cinza) vai pro catálogo de textos.
    - **Amanhã (01/10), visto antes de acontecer** (Patrick: "acho que a Marina vai se complicar amanhã"): aula
      07–15h, casting 15:30–17:00 e outro 17:00–18:30 na mesma agência. O planejado: almoço no Shopping da Gávea 15:18
      (com casting 15:30), volta da PUC 15:50 emendando no 2º casting, "voltando pra casa" do 1º às 17:00 e "a caminho"
      do 2º desde 15:50, passeio do Milo 17:48–18:38 no meio do 2º, almoço em casa 17:40 no meio do 2º. Consertos:
      saída até 2 h depois da aula → não almoça por lá (`Meals.almoco_pos_aula`); dois compromissos seguidos no mesmo
      lugar → ela fica (`Commute._emendas`, também com fim = início); o card mostra o 2º "Na agência" e a volta
      (`Agenda.etapas`); passeio do Milo e academia não caem em saída marcada (`RoutineEngine._placement`); saídas
      emendadas contam como uma pras refeições (`Meals._saidas`); refeição pulada por compromisso diz isso (não
      "acordou em cima da hora"). Simulado: PUC → agência 15:00–15:30 → castings → casa 18:55 → jantar 19:33.

21. ✅ **Soak, dia 2 (quarta 30/09) — o relatório inteiro** (`soak/dia-2026-09-30.md`, lido em 01/10; o que já estava
    no item 20 ficou de fora). Corrigido em 01/10 (`tests/test_soak_dia2.py`, +6).
    - **21:57 "Tirou a roupa da máquina e estendeu no varal" no meio do banho (21:34–22:01).** Coisa de casa só
      esperava ela estar em casa. Agora espera banho, refeição e Milo; se a hora caiu dentro disso, acontece quando
      ela termina; o varal sai pelo menos 1 h depois da máquina. Camada: mundo (`casa.py`).
    - **11:37 e 13:06: duas fotos mandadas na conversa, nenhuma no histórico** (relatório: "0 fotos"; ele perguntou
      "aquela roupa da foto que mandou"). Só a foto prometida entrava. Agora a da conversa também. Camada: voz (`bot.py`).
    - **Pontuação** (/ruim 039, 042, 043, 044): travessão, ponto e vírgula e dois pontos entre palavras viram vírgula
      no filtro da fala. Decisão do Patrick: "agora, no filtro". Camada: voz (`limpar_fala_marina`).
    - Ruído: 13:08 traceback da agenda reativa com JSON cortado vira aviso. Alarmes falsos do relatório: "acabou de
      acordar, de pijama" é em casa (05:21, 06:16); "tô treinando com você" não é academia (15:14).
    - Conferido e ok: a sessão de trabalho aconteceu (19:56–20:56); banho antes do boa noite; pai e Bia batem com o que
      ela contou; as 2 respostas com letra estrangeira foram refeitas antes de sair; US$ 0,47 de LLM, 62 Buzz.
    - Texto feio (lote da voz, não zera): "convencido" de novo, "derretida/arrepiada" demais, "seu bobo atrevido"
      depois de só uma risada dele, "abusado demais" fora de contexto.

22. ✅ **Soak, dia 3 (quinta 01/10) — o dia dos dois castings** (`soak/dia-2026-10-01.md`, lido em 02/10). O dia
    planejado no item 20 aconteceu: falta pela cólica, ônibus 15:00, castings 15:30 e 17:00, saiu mal 17:30 de uber.
    Corrigido em 02/10 (`tests/test_soak_dia3.py`, +13).
    - **05:32 "Hoje é dia livre da facul, não tenho aula pra faltar"** (e "tô fechando o trabalho"; ele: "tô
      entendendo mais nada"). A falta veio da agenda viva (`agenda:faltou:`) e o aviso do prompt só lia `falta:`.
      Camada: prompt (`College.falta`).
    - **11:29 "só sei que a canja chegou mais cedo"** — a canja era de 30/09; a promessa "avisar quando a canja
      chegar" seguia aberta. Pedido que chega fecha a promessa. Camada: memória (`delivery.fecha_promessas_do_pedido`).
    - **Hoje 18:30 "Fez o casting na agência"** — ela largou o 2º casting às 17:30, passando mal. Saiu no meio vira
      "Não terminou o casting", sem resposta da Lívia. Camada: mundo (`Freela._saiu_no_meio`). Produção corrigida
      (OK do Patrick; originais em `soak/originais-2026-10-01.json`), junto com a promessa da canja.
    - **08:04 a foto dele sem leitura** ("que lindo, começou o dia com estilo"): JSON da visão mal formado. Leitura
      tolerante e 2ª tentativa. Camada: voz (`vision_service`).
    - **Hoje: "Foi para a agência" duas vezes** (castings emendados na mesma agência). Uma saída só. Camada: app
      (`hoje._saidas`).
    - **05:22 bom dia e 05:24 "Acordei agora e vi isso"** — com mensagem dele esperando da madrugada, o bom dia vai
      junto da resposta. Camada: voz (`bot._bom_dia_na_resposta`).
    - Alarmes falsos do relatório: «tomei um Buscopan» é do mundo (cólica moderada); «jantei» foi a tigela das 19:08.
    - Leve: "a Dona Neide tá terminando a faxina" às 09:30 (foi até 13:41).
    - Texto feio (lote da voz, não zera): "O Uber tá andando", "vou papá-la toda", "guloso afetuoso", "tô aceitando,
      amor, finalmente" forçado.

23. ✅ **Soak, dia 4 (sexta 02/10) — olhado à tarde, até 15:41** (pedido do Patrick, antes do Quartinho; o relatório
    inteiro sai sábado 05:10 e a conversa "bora no soak, dia 4" lê o resto do dia). `tests/test_soak_dia4.py` (+9).
    - **13:53 "g-relacionada", 14:22 "hein GATE_CHANNEL"** — rótulo de prompt colado pelo modelo. Barrado e refeito
      como os outros artefatos. Camada: voz (`bot._DEBUG_ARTIFACT_RE`).
    - **14:23 /ruim 055 sem confirmação** — o "_" quebrou o Markdown. Manda sem formatação. Camada: voz.
    - **"Aqui tá sequinho" (13:48), "dia quente" (15:03), "tô de guarda-chuva" (15:15)** — chuvisco desde as 10h e o
      mundo só sabia de chuva forte; o ponto do tempo era o Corcovado (558 m); três módulos liam um "rain" que
      ninguém gravava; toda foto em casa tinha chuva. Agora: Botafogo, condição do tempo gravada e dita no prompt.
      Camada: mundo/prompt (`real_context_provider`, `world_context.tempo_agora`, `photo_director`).
    - **15:01 foto dele sem leitura de novo** — a visão foi cortada em 300 e 500 tokens. Mais espaço, listas curtas.
    - **14:55 e 15:41 as duas fotos dela que não vieram** (o Patrick viu; eu tinha deixado passar no relatório) — o
      moderador do Civitai recusou a selfie normal pela expressão sensual ("sultry… teasing smirk"; testado, 31
      Buzz: sem ela passa) e ela mandou o texto fixo "a câmera do apê travou" estando na rua, fora do histórico.
      Agora refaz uma vez com um sorriso; se falhar, ela explica do jeito dela, no histórico, e fica devendo outra.
      Camada: imagens/voz (`sd_client`, `photo_director.suavizar`, `bot._foto_nao_saiu`). `test_soak_dia4_fotos` (+7).
    - **Conversa sobre a lógica da foto (Patrick):** "no Rei do Mate ela está dentro, não na rua" — lugar fora da
      lista de fundos caía em "a street in Botafogo"; agora é "the inside of a small café in Botafogo"
      (`photo_director.visual_do_lugar`, pelo tipo do lugar no mundo). Cara sensual vestida: testadas 3 (62 Buzz) —
      "sultry… teasing smirk" recusada mesmo sem "young"; A ("flirty, confident look… playful half-smile") e C
      passaram, ele não viu diferença (mesma pose, mão no rosto) e não gostou de eu ter decidido sozinho; 2ª rodada numa selfie sem mão no rosto (62 Buzz): mordendo o lábio recusada; **no flerte o sorriso largo, no tesão vestida o olhar por cima do ombro** (escolha dele, `EXPRESSAO_FLERTE` / `EXPRESSAO_TESAO_VESTIDA`).
      Unha: "faz parte do corpo dela, mas não precisa ser o foco" — "mostrando as unhas" só se o assunto é unha (às
      15:41 a pose foi escolhida com a unha de 3 dias). `test_soak_dia4_fotos` (+3).
    - **"Comeu pra cacete e continuou com fome"** (o Patrick viu) — Tigela Nutella e croissant não contaram (só o
      mate, como beliscão). Toda comida fora conta, com saciedade; bebida não é comida. Produção de hoje corrigida
      (OK dele). Camada: mundo (`consumo._meal`). `test_soak_dia4_fome` (+3).
    - Ficou como vida (opinião minha; Patrick indeciso): 14:40 saiu pro açaí no meio da provocação.
    - Texto feio (lote, não zera): reações a elogio repetitivas, "gosto quando você gosta", "plano de elogio bem
      convincente", "convencido" de novo.

24. ✅ **Soak, dia 4 (sexta 02/10) — da tarde em diante (15:41 →), lido em 03/10** com o relatório já melhorado
    (seção 0). `tests/test_soak_dia4_noite.py` (+16), `test_soak_leitura` (+15), `test_arrival_promise` (ajustado).
    - **19:44 Uber combinado e ela foi a pé, na chuva** (com os R$ 200 dele) — "Quero sim, melhor ir de Uber" não
      contava como topar. Agora conta ("prefiro ir a pé" segue recusa). E (Patrick, 03/10) **chuva de verdade tira o
      "a pé"**, como o temporal; chuvisco não. Camada: mundo (`agenda_reativa.TOPOU_RE`, `commute._chuva`).
    - **20:05/20:06 "encontrou a Júlia" e caipirinha com ela em casa** — chegou 20:22 (22 min atrasada) e o bar
      seguia a hora marcada. O consumo e o encontro contam da chegada de verdade (`Commute.chegada`). Camada: mundo.
    - **23:26 "Se divertindo ainda"** em casa desde 23:06, e **23:43 "cheguei e apaguei no sofá"** (viu TikTok,
      desceu o Milo, pôs a série) — o fato da chegada estava no meio do prompt e o histórico venceu. Agora vai uma
      dica no fim: chegou às X, desde então fez só isto (`world_context.desde_que_voltou`). Camada: prompt.
    - **23:45 "Já sim, banho tomado"** — o `[BANHO — FATO]` mandava responder "sim" pelo banho das 18:31, antes do
      Quartinho. Agora sabe que ela saiu e voltou depois. Camada: prompt.
    - **"vele"** no fim da fala (20:30 no áudio, 23:39) — palavra inventada; sai da fala (`limpar_fala_marina`).
    - **Aviso (Patrick, 03/10): sem sorteio.** A chegada no Quartinho foi "esquecida" pelos 5%; "assim que eu sair
      te mando mensagem" nem virava promessa; uma promessa por vez; a hora não seguia o atraso. Agora: várias
      promessas, saída de casa também, hora pelo trajeto de agora, e **"cheguei" de bom tom** — volta de rolê à
      noite, ou qualquer chegada de rolê depois de ele cobrar o aviso no dia (`arrival_promise.implicitas`).
    - Médios: boa noite no meio do banho (00:19) — espera o passo do banho; One Piece e Paradise Kiss num item só
      do Hoje — dois acontecimentos, e o mundo diz os dois; "Pulou o jantar: não deu tempo" no bar com fritas — rolê
      com comida é o jantar (`Meals.por_la`); chamou a Júlia pra sábado com o convite da Bia (mesmo bar e hora) sem
      resposta — com convite esperando, não chama ninguém (`AgendaViva.planeja`).
    - Textos: "atrasada 22 min" → no prompt vai "uns 20 min"; os graus só se ele perguntar (/ruim 060); a desculpa
      fixa do microfone virou fala dela (mesmo defeito da câmera). /ruim 059, 061, 062, 063, 064 anotados.
    - **Aberto (médio, frente do mundo):** depois do banho de 00:26 o mundo voltou pra "tirando maquiagem" (00:39) —
      o preparo pra dormir esticou e os passos se redistribuíram. E 19:44 "ainda não sei como vou" com o jeito de
      ir já decidido (fala; anotado).

25. **/feedback do Patrick sem leitura (achado em 03/10, ele perguntou)** — o relatório não lia a tabela
    `feedbacks` e 11 /feedback de 30/09 a 02/10 ficaram pendentes. O relatório passou a trazê-los em destaque, com o
    mundo daquela hora (roteiro: cada /feedback é bug a investigar). Situação de cada um:
    - ✅ 02/10 20:09 Bastidores dizia que ia sair pro Quartinho e já mostrava ela lá com a Júlia e a caipirinha —
      corrigido no item 24 (o rolê conta da chegada de verdade).
    - ✅ **Graves (03/10, frente de bugs)** — `tests/test_soak_feedbacks_0210.py` (+15). Detalhe na Auditoria
      ("/feedback do soak de 02/10").
      - 11:36 "me respondeu durante o banho": o banho começou 11:24 e a disponibilidade confiava no retrato do
        Instagram das 10:57; o tick dos rituais não atualizava o mundo no banho; e a foto dele não passava pela
        disponibilidade. Os três corrigidos; o Pix também espera agora. Camada: mundo/disponibilidade.
      - 18:50 "telefone no bolso no banho": ela não respondeu (adiou certo); era o card — no passo do banho, "Pega
        após o banho". Camada: app.
      - 19:06 secando o cabelo com a roupa da academia: do banho até o passo da roupa, "Enrolada na toalha".
      - 19:54 atrasou "por trocar de look" com a mesma roupa: a troca acontece de verdade, na hora do aviso.
      - 23:36 "respondeu de novo": ele escreveu no meio dos 9 balões do resumo do dia; agora o turno sabe que as
        mensagens se cruzaram e o que ele ainda não tinha lido. Camada: chat.
    - ✅ **Voz:** 19:48 Pix sem contexto (= /ruim 061) — o Pix lê o que ele acabou de combinar; 14:34 "Kkkkk" no começo
      — no máximo 1 a cada 5 respostas.
    - ✅ **App (texto):** 01/10 23:14 "olhando o X" com "No bolso" — o `' x '` do jogo na TV pegava o X; agora "Na mão".
    - **Aberto (voz):** 19:52 "a voz está variando muito e perdendo a naturalidade" — ouvir junto antes de mexer (os
      perfis `conversational` e `intimate` do MiniMax se alternam por turno). E o lote dos /ruim de 02/10 (053, 054,
      056–059, o contexto da 063; 053 e 058 são crítica geral), mais os 9 balões pra quem pediu "devagar" e "De manhã
      eu acordei de manhã" (23:34).
    - **Ideia → depois do soak:** 30/09 mais bebidas nos pedidos, vinho no mercado, Marina bêbada.

**Abertos:** a voz do áudio e o lote dos /ruim (item 25, frente da voz); o preparo pra dormir que volta de passo
(item 24, frente do mundo).

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
5. ~~Trocar a chave do Civitai~~ — o Patrick decidiu não trocar (02/10: não houve vazamento real).

## 7. Auditoria de funcionamento — skill `frente-auditoria`
**Abertura:** "bora na auditoria de funcionamento" (rodada 3 feita em 28/09, 23:40; a próxima é no próprio soak, pelo relatório diário)

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

**Rodada 3 (28/09, 23:40) — antes do soak, tudo junto:** item 18 da seção 5. Funciona: academia com as quatro etapas,
jantar do iFood fora do saldo (D9), lista de compras (barrinhas, compra no sábado), semente do pai fora do prompt e
fechando no primeiro contato (29/09 08:30), marca de pausa pra resposta adiada da madrugada, relatório do soak (timer
05:10; rodado sobre 28/09, 0 erros de verdade), bug 16 sem `junk_reply` depois das 20:31. Quebrou e foi corrigido: Milo
no meio do jantar, estudo às 19:59 dentro do treino, banho pós-treino perdido, "vou deitar" antes do banho. Não
exercitado (o soak exercita): bug 17 com foto, bateria social pelo tipo da saída, card do mercado com a lista (sábado).
Método novo: além da varredura, **a noite refeita com o código novo** (banco cortado às 20:05 numa cópia em `/tmp` e
`Rituals.tick` de 5 em 5 min) — achou um efeito colateral da própria correção (boa noite perdido com o Milo) antes do
deploy.

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

