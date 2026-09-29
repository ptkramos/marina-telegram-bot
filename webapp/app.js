"use strict";
// Mini App da Marina (25/09). Sem framework. A API valida o initData do Telegram.
// Termos e marcas decididos com o Patrick: Nubank (Área Pix) e iFood, sem emoji nas telas dos apps.
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.ready(); tg.expand(); }
// Telegram antigo (ou fora dele) não tem BackButton (6.1) nem showConfirm (6.2): cai no da página.
const tgAt = (v) => !!(tg && tg.isVersionAtLeast && tg.isVersionAtLeast(v));
// 26/09 (Patrick): sem zoom por pinça (o WebKit do iOS ignora user-scalable=no)
["gesturestart", "gesturechange"].forEach((ev) => document.addEventListener(ev, (e) => e.preventDefault(), { passive: false }));
const nativeBack = tgAt("6.1");
const insideTelegram = !!(tg && tg.initData);

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const brl = (v) => "R$ " + Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const brl0 = (v) => "R$ " + Math.round(v).toLocaleString("pt-BR");
const pct = (v) => Math.max(0, Math.min(100, Math.round((v || 0) * 100)));
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");

async function api(path, body) {
  const opts = { headers: { "X-Telegram-Init-Data": (tg && tg.initData) || window.__DEV_INIT || "" } };
  if (body) { opts.method = "POST"; opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.erro || (r.status === 403 ? "Abra pelo botão do chat da Marina." : "Não deu certo agora. Tente de novo."));
  return data;
}

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 2600);
}

// Depois de transferir ou pedir: o comprovante aparece no chat como mensagem sua e o app fecha.
function concluido(msgForaDoTelegram) {
  if (tgAt("6.1")) tg.HapticFeedback.notificationOccurred("success");
  if (insideTelegram) { setTimeout(() => tg.close(), 250); return; }
  toast(msgForaDoTelegram);
}

// ------------------------------------------------------------------ navegação --
const stack = ["inicio"];
const IF_TABS = ["ifood", "ifbusca", "ifpedidos"];    // abas da barra de baixo do iFood
const IG_TABS = ["ig", "igativ", "igperfil"];          // 27/09: e do Instagram
const TABS = [...IF_TABS, ...IG_TABS];
function show(view, push = true) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "v-" + view));
  $("if-nav").hidden = !IF_TABS.includes(view);
  $("ig-nav").hidden = !IG_TABS.includes(view);
  document.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === view));
  if (push) stack.push(view);
  if (nativeBack) (stack.length > 1 ? tg.BackButton.show() : tg.BackButton.hide());
  else $("voltar").hidden = stack.length <= 1;
  window.scrollTo(0, 0);
  (loaders[view] || (() => {}))();
}
// trocar de aba não empilha: o voltar sai do iFood, como no app de verdade
function tab(view) {
  if (TABS.includes(stack[stack.length - 1])) stack.pop();
  show(view);
}
function back() {
  if (!$("rv-fundo").hidden) { $("rv-fundo").hidden = true; return; }
  if (!$("igs").hidden) { IG.fecharStory(); return; }
  if (stack.length > 1) { stack.pop(); show(stack[stack.length - 1], false); }
}
if (nativeBack) tg.BackButton.onClick(back);
$("voltar").addEventListener("click", back);

// ------------------------------------------------------ etapas do pedido (iFood) --
function etapas(p) {
  return `<ol class="etapas">${p.steps.map((s) => `<li class="${s.done ? "done" : ""} ${s.current ? "current" : ""}">
    <span class="dot"></span><span class="lbl">${esc(s.label)}</span><span class="hora">${esc(s.at || "")}</span></li>`).join("")}</ol>`;
}

function pedidoCard(p, titulo) {
  if (!p) return "";
  return `<div class="pedido"><div class="pedido-top"><img src="/static/marcas/ifood.svg" alt="" class="mini">
    <span class="small muted">${esc(titulo)}</span></div>
    <div class="t">${esc(cap(p.what))}</div><div class="small muted">${esc(p.restaurant)}</div>
    <div class="headline">${esc(p.headline)}</div>${etapas(p)}
    ${p.note ? `<div class="small muted">Observações: ${esc(p.note)}</div>` : ""}</div>`;
}

function failIn(el, err) { el.innerHTML = `<p class="err">${esc(err.message)}</p>`; }

// --------------------------------------------------------------------- telas --
// 26/09 (Patrick): ícones do Tabler (outline), no lugar do Bootstrap Icons
// ícones que o Tabler não tem: chuveiro desenhado no traço dele (app.css) e o hand-love-you de cabeça pra baixo
const IC_PROPRIO = { masturbacao: "hand-love-you ic-inv", chuveiro: "chuveiro" };
const ic = (name, cls = "") => `<i class="ti ti-${IC_PROPRIO[name] || name}${cls ? " " + cls : ""}"></i>`;
const nota = (n) => String(n).replace(".", ",");
const abreAs = (h) => `Abre às ${String(h).padStart(2, "0")}:00`;

const HOJE_ABERTOS = new Set();   // períodos passados que ele abriu no Hoje (sobrevivem à recarga de 30 s)
let DIARIO_ABERTO = false;        // "Ver o dia todo" no Hoje por dentro (idem)
const EXTRATO_ABERTOS = new Set(); // saídas abertas no extrato da aba Dinheiro (idem)
let BAST_CARREGANDO = false;      // uma carga dos Bastidores por vez

// 28/09 (Patrick): na recarga dos Bastidores a barra desliza do valor antigo pro novo, em vez de pular.
// A chave é o cartão (id) + a posição da barra dentro dele.
const BARRAS = "#v-bastidores .bar > i, #v-bastidores .ag-bar > i";
function chaveBarra(el) {
  const dono = el.closest("[id]");
  return dono.id + ":" + [...dono.querySelectorAll(".bar > i, .ag-bar > i")].indexOf(el);
}
function largurasBarras() {
  return new Map([...document.querySelectorAll(BARRAS)].map((el) => [chaveBarra(el), el.style.width]));
}
function deslizaBarras(antes) {
  document.querySelectorAll(BARRAS).forEach((el) => {
    const velho = antes.get(chaveBarra(el)), alvo = el.style.width;
    if (!velho || velho === alvo) return;
    el.style.transition = "none"; el.style.width = velho;
    void el.offsetWidth;                          // aplica o valor antigo antes de animar
    el.style.transition = ""; el.style.width = alvo;
  });
}

const loaders = {
  async inicio() {
    try {
      const d = await api("/api/inicio");
      $("inicio-presente").innerHTML = pedidoCard(d.pra_voce, "Presente da Ma");
      $("ig-bolinha").hidden = !d.insta_novo;
    } catch (e) { failIn($("inicio-presente"), e); }
  },

  nubank() {
    $("pix-err").textContent = "";
    setTimeout(() => $("pix-valor").focus(), 150);
  },

  revisao() {
    const v = loaders._pix;
    $("rev-valor").textContent = brl(v.valor);
    $("rev-msg").textContent = v.recado;
    $("rev-msg-row").hidden = !v.recado;
    $("rev-err").textContent = "";
  },

  // ------------------------------------------------ iFood (26/09, lojas reais) --
  async ifood() {
    try {
      const d = await IF.carregar();
      $("if-andamento").innerHTML = IF.andamento(d.pedido);
      IF.chips("if-chips");
      IF.lista();
    } catch (e) { failIn($("if-lojas"), e); }
  },

  async ifbusca() {
    try {
      await IF.carregar();
      IF.chips("bs-chips");
      IF.busca();
      setTimeout(() => $("if-busca").focus(), 150);
    } catch (e) { failIn($("bs-lojas"), e); }
  },

  // aba Pedidos (print real 26/09): em andamento, "Seus clássicos" e o histórico por dia
  async ifpedidos() {
    try {
      const d = await IF.carregar(true);
      $("pd-andamento").innerHTML = IF.andamento(d.pedido);
      const lojas = new Map(d.lojas.map((l) => [l.id, l]));
      const vistos = new Set(), classicos = [];
      d.pedidos.forEach((p) => {
        if (p.loja_id && lojas.has(p.loja_id) && !vistos.has(p.loja_id)) { vistos.add(p.loja_id); classicos.push(lojas.get(p.loja_id)); }
      });
      $("pd-classicos").innerHTML = classicos.length ? `<h3 class="if-h">Seus clássicos</h3><div class="carrossel">${classicos.map((l) =>
        `<button class="classico" data-loja="${esc(l.id)}"><img class="loja-circ" src="/static/${esc(l.logo)}" alt="">
          <div class="cl-nome">${esc(l.nome)}</div>
          <div class="d">${l.aberta ? `${l.eta[0]}-${l.eta[1]} min • ${IF.taxa(l.taxa)}` : abreAs(l.abre)}</div></button>`).join("")}</div>` : "";
      if (!d.pedidos.length) {
        $("pd-historico").innerHTML = `<div class="vazio">${ic("receipt")}<div class="t">Nenhum pedido ainda</div>
          <div class="d">Os pedidos que você mandar pra Ma aparecem aqui.</div></div>`;
        return;
      }
      let html = `<h3 class="if-h">Histórico</h3>`, dia = null;
      d.pedidos.forEach((p, n) => {
        if (p.dia !== dia) { dia = p.dia; html += `<div class="pd-dia">${esc(dia)}</div>`; }
        const foto = p.itens.find((i) => i.foto);
        const logo = p.logo ? `<img class="loja-circ peq" src="/static/${esc(p.logo)}" alt="">` : `<span class="loja-circ peq">${ic("building-store")}</span>`;
        html += `<div class="pd-card"><div class="pd-loja">${logo}
          <div><div class="t">${esc(p.restaurant)}</div><div class="d com-ic">${esc(p.status)}${p.concluido ? ic("circle-check-filled", "ok") : ""}</div></div></div>
          <div class="pd-itens"><div class="pd-lista">${p.itens.map((i) =>
            `<div class="pd-item"><span class="qtd">${i.qtd}</span><span class="nome">${esc(i.nome)}</span></div>`).join("")}</div>
          ${foto ? `<div class="pd-foto" style="background-image:url(/static/${esc(foto.foto)})"></div>` : ""}</div>
          ${p.loja_id && lojas.has(p.loja_id) ? `<div class="pd-acoes"><button class="link-vermelho" data-loja="${esc(p.loja_id)}">Ver loja</button>
          <button class="link-vermelho" data-repetir="${n}">Adicione à sacola</button></div>` : ""}</div>`;
      });
      $("pd-historico").innerHTML = html;
    } catch (e) { failIn($("pd-historico"), e); }
  },

  async loja() {
    try {
      const l = await api("/api/ifood/loja/" + encodeURIComponent(IF.lojaId));
      IF.loja = l;
      $("lj-capa").style.backgroundImage = l.capa ? `url(/static/${l.capa})` : "";
      $("lj-logo").src = "/static/" + l.logo;
      $("lj-nome").textContent = l.nome;
      $("lj-info").textContent = `Entrega rastreável • ${String(l.km).replace(".", ",")} km • Min ${brl(l.minimo)}`;
      $("lj-nota").innerHTML = `<span class="com-ic">${ic("star-filled", "estrela")}<b>${nota(l.nota)}</b><span class="muted">(${IF.aval(l.avaliacoes)} avaliações)</span></span>${ic("chevron-right", "muted")}`;
      $("lj-entrega").innerHTML = l.aberta
        ? `<span><b>Padrão</b> • ${l.eta[0]}-${l.eta[1]} min • ${IF.taxa(l.taxa)}</span>`
        : `<span class="fechada">Loja fechada • ${abreAs(l.abre)}</span>`;
      const secoes = l.secoes;
      const dest = secoes[0].nome === "Destaques" ? secoes[0].itens : secoes[0].itens.slice(0, 3);
      $("lj-destaques").innerHTML = `<h3 class="if-h">Destaques</h3><div class="dest-grid">${dest.slice(0, 3).map((i, n) =>
        `<button class="dest" data-prato="${esc(i.id)}"><div class="dest-foto" style="background-image:url(/static/${esc(i.foto)})">${n === 0 ? '<span class="selo">Mais pedido</span>' : ""}</div>
        <div class="dest-preco">${brl(i.preco)}</div><div class="dest-nome">${esc(i.nome)}</div></button>`).join("")}</div>`;
      const resto = secoes[0].nome === "Destaques" ? secoes.slice(1) : secoes;
      $("lj-tabs").innerHTML = resto.map((s, n) => `<button data-secao="${n}">${esc(s.nome)}</button>`).join("");
      $("lj-secoes").innerHTML = resto.map((s, n) => `<h3 class="if-h" id="sec-${n}">${esc(s.nome)}</h3>${s.itens.map((i) =>
        `<button class="prato-row" data-prato="${esc(i.id)}"><div class="pr-txt"><div class="t">${esc(i.nome)}</div>
          <div class="d dois">${esc(i.desc)}</div><div class="pr-preco">${brl(i.preco)}</div></div>
          <div class="pr-img" style="background-image:url(/static/${esc(i.foto)})"></div></button>`).join("")}`).join("");
      IF.barra();
    } catch (e) { failIn($("lj-secoes"), e); }
  },

  prato() {
    const i = IF.item;
    $("pr-foto").style.backgroundImage = `url(/static/${i.foto})`;
    $("pr-nome").textContent = i.nome;
    $("pr-desc").textContent = i.desc;
    $("pr-serve").textContent = i.serve || "";
    $("pr-preco").textContent = brl(i.preco);
    $("pr-obs").value = ""; $("pr-cont").textContent = "0/140";
    IF.qtd = 1; IF.stepper();
  },

  sacola() {
    const c = IF.cart;
    if (!c.itens.length) return back();
    $("sc-logo").src = "/static/" + c.loja.logo;
    $("sc-nome").textContent = c.loja.nome;
    const sub = IF.subtotal();
    $("sc-min").hidden = sub >= c.loja.minimo;
    $("sc-min").innerHTML = `O pedido mínimo dessa loja é <b>${brl(c.loja.minimo)}</b> sem contar com a taxa de entrega.`;
    $("sc-itens").innerHTML = c.itens.map((x, n) => `<div class="sc-item"><div class="sc-img" style="background-image:url(/static/${esc(x.item.foto)})"></div>
      <div class="sc-txt"><div class="t">${esc(x.item.nome)}</div><div class="d dois">${esc(x.obs || x.item.desc)}</div><div class="t">${brl(x.item.preco * x.qtd)}</div></div>
      <div class="sc-ctl"><button data-sc="menos" data-n="${n}">${x.qtd > 1 ? ic("minus") : ic("trash")}</button><span>${x.qtd}</span><button data-sc="mais" data-n="${n}">${ic("plus")}</button></div></div>`).join("");
    const ids = new Set(c.itens.map((x) => x.item.id));
    const outros = c.loja.secoes.flatMap((s) => s.itens).filter((i) => !ids.has(i.id)).slice(0, 6);
    $("sc-tambem").innerHTML = outros.map((i) => `<button class="car-item" data-prato="${esc(i.id)}"><div class="car-foto" style="background-image:url(/static/${esc(i.foto)})"><span class="car-mais">${ic("plus")}</span></div>
      <div class="t">${brl(i.preco)}</div><div class="small">${esc(i.nome)}</div></button>`).join("");
    $("sc-total").textContent = brl(IF.total());
  },

  entrega() {
    const l = IF.cart.loja;
    $("en-eta").textContent = `Hoje, ${l.eta[0]} - ${l.eta[1]} min`;
    $("en-taxa").innerHTML = IF.taxa(l.taxa);
    $("en-total").textContent = brl(IF.total());
  },

  pagamento() {
    const l = IF.cart.loja, sub = IF.subtotal();
    $("pg-resumo").innerHTML = [["Subtotal", brl(sub)], ["Taxa de entrega", l.taxa ? brl(l.taxa) : '<span class="gratis">Grátis</span>'],
      ["Taxa de serviço", brl(TAXA_SERVICO)]].map(([a, b]) => `<div class="rs-linha"><span class="muted">${a}</span><span>${b}</span></div>`).join("")
      + `<div class="rs-linha total"><span>Total</span><span>${brl(IF.total())}</span></div>`;
    $("pg-revisar").textContent = `Revisar pedido • ${brl(IF.total())}`;
    $("pg-err").textContent = "";
  },

  // 26/09 (Patrick): abas Agora · Por dentro · Dinheiro · Mundo. O servidor já manda o texto pronto
  // (status_view, emocao_view, world_panel, extrato); aqui é só desenho.
  async bastidores() {
    if (BAST_CARREGANDO) return;              // 28/09: abrir a tela e a recarga de 30 s não pedem duas vezes
    BAST_CARREGANDO = true;
    try {
      const [d, g] = await Promise.all([api("/api/bastidores"), api("/api/dinheiro")]);
      const s = d.status, e = d.emocao, m = d.mundo;
      const antes = largurasBarras();
      const linha = (icone, rotulo, valor) => `<div class="linha"><span class="li-ic">${ic(icone)}</span>
        <span class="li-rot">${esc(rotulo)}</span><span class="li-val">${esc(valor)}</span></div>`;
      const vazio = (txt) => `<p class="muted vazio-txt">${esc(txt)}</p>`;
      const bar = (label, v, word, warm) => `<div class="bar-row"><span>${esc(label)}</span>
        <div class="bar${warm ? " warm" : ""}"><i style="width:${pct(v)}%"></i></div><span class="w">${esc(word || pct(v) + "%")}</span></div>`;

      // Agora — 26/09: layout D aprovado com o Patrick linha a linha (agenda.card no servidor)
      const grade = (rows) => `<div class="ag-grade">${rows.map(([i, r, v]) =>
        `<span class="li-ic">${ic(i)}</span><span class="ag-rot">${esc(r)}</span><span class="ag-val">${esc(v)}</span>`).join("")}</div>`;
      const c = s.card;
      if (c) {
        const passos = (ps) => ps.length ? `<div class="ag-sub">${ps.map((p) => `<div class="ag-st ${p.estado}">
          <span class="ag-dot"></span><span class="ag-tx">${esc(p.texto)}</span><span class="ag-vl">${p.valor ? brl0(p.valor) : ""}</span>
          <span class="ag-hr">${esc(p.hora)}</span>${p.nota ? `<span class="ag-nota">${esc(p.nota)}</span>` : ""}</div>`).join("")}</div>` : "";
        const b = c.barra;
        // sem hora de fim: duração e "desde" à direita do título (decisão do Patrick)
        const topo = b.pct == null
          ? `<div class="ag-topo"><div class="ag-t">${esc(c.titulo)}</div><div class="ag-dur"><b>${esc(b.duracao)}</b><span>desde ${esc(b.desde)}</span></div></div>`
          : `<div class="ag-t">${esc(c.titulo)}</div>`;
        $("ag-card").innerHTML = `${topo}${c.linha2 ? `<div class="ag-s">${esc(c.linha2)}</div>` : ""}
          ${b.pct == null ? "" : `<div class="ag-bar"><i style="width:${b.pct}%"></i></div>
          <div class="ag-bar-l"><span>${esc(b.inicio)}</span><span>${esc(b.meio)}</span><span>${esc(b.fim)}</span></div>`}
          <div class="ag-sep"></div>${grade(c.grade)}<div class="ag-sep"></div>
          <div class="ag-linha">${c.linha.map((e) => `<div class="ag-st ${e.estado}"><span class="ag-dot"></span>
            <span class="ag-tx">${esc(e.texto)}</span><span class="ag-vl">${e.valor ? brl0(e.valor) : ""}</span>
            <span class="ag-hr">${esc(e.hora)}</span></div>${passos(e.passos)}`).join("")}</div>`;
      } else {
        // fora de uma etapa (em casa, dormindo…): a revisar com o Patrick (atividades em casa)
        $("ag-card").innerHTML = `<div class="ag-t">${esc(s.atividade)}</div><div class="ag-s">${esc(s.local)}</div>
          <div class="ag-sep"></div>${grade([["device-mobile", "Celular", s.celular], s.ciclo && ["droplet", "Ciclo", s.ciclo],
            ...s.saude.map((x) => ["temperature", "Saúde", x]), s.proximo && ["calendar-event", "Próximo", s.proximo],
            ...s.planos.map((x) => ["calendar", "Plano", x])].filter(Boolean))}`;
      }
      // 26/09 (Patrick): Hoje por período, saída com o que rolou dentro, previsto em cinza.
      // Períodos que já passaram ficam fechados ("Manhã · 7") e abrem ao tocar; o de agora fica aberto.
      const hj = d.hoje.periodos || [];
      const hjHora = (x) => `<span class="lt-hora">${esc(x.hora)}</span>`;
      const hjVal = (x) => `<span class="lt-val">${x.valor ? brl0(x.valor) : ""}</span>`;   // coluna sempre existe: hora alinhada
      const hjTx = (x) => `<span class="lt-txt">${esc(x.texto)}${x.sub ? `<span class="lt-sub">${esc(x.sub)}</span>` : ""}</span>`;
      const atual = hj.reduce((k, p, n) => (p.itens.some((x) => !x.previsto) ? n : k), 0);
      const desenhaHoje = () => {
      $("ag-hoje").innerHTML = hj.length ? hj.map((p, n) => {
        const fechado = n < atual && !HOJE_ABERTOS.has(p.nome);
        const feitos = p.itens.filter((x) => !x.previsto).length;
        return `<button class="hj-per${n < atual ? " passado" : ""}" data-per="${esc(p.nome)}"${n < atual ? "" : " disabled"}>
            <span>${esc(p.nome)}${fechado ? ` · ${feitos}` : ""}</span>${n < atual ? ic(fechado ? "chevron-down" : "chevron-up") : ""}</button>
          ${fechado ? "" : `<ol class="linha-tempo">${p.itens.map((x) => `<li class="${x.previsto ? "previsto" : ""}${x.aviso ? " aviso" : ""}">
            <span class="lt-ic">${ic(x.ic)}</span>${hjTx(x)}${hjVal(x)}${hjHora(x)}</li>
            ${x.filhos.length ? `<li class="lt-filhos"><ol>${x.filhos.map((f) => `<li class="${f.aviso ? "aviso" : ""}">
              ${hjTx(f)}${hjVal(f)}${hjHora(f)}</li>`).join("")}</ol></li>` : ""}`).join("")}</ol>`}`;
      }).join("") : vazio(s.dormindo ? "Ela ainda não acordou." : "Nada registrado hoje ainda.");
      $("ag-hoje").querySelectorAll(".hj-per.passado").forEach((b) => b.addEventListener("click", () => {
        const nome = b.dataset.per;
        HOJE_ABERTOS.has(nome) ? HOJE_ABERTOS.delete(nome) : HOJE_ABERTOS.add(nome);
        desenhaHoje();
      }));
      };
      desenhaHoje();

      // Por dentro — 28/09 (Patrick, no celular): Corpo, Humor, Sentindo agora, Na cabeça, Hoje por dentro,
      // Vocês dois. Unhas e Cabelo foram pra aba Por fora (28/09).
      $("bd-corpo").innerHTML = e.body.map((b) => bar(b.label, b.value, b.word, b.label === "Tesão")).join("")
        + (e.linhas.length || e.no_clima ? `<div class="linhas sep">${e.linhas.map(([i, r, v]) => linha(i, r, v)).join("")}
          ${e.no_clima ? `<div class="linha"><span class="li-ic">${ic("flame")}</span><span class="li-rot">No clima agora</span></div>` : ""}</div>` : "");
      // Por fora — 28/09 (Patrick): Agora (roupa e make de verdade), Peso (barra de folga até a agência, amarela
      // quando passa), Cabelo, Unhas. Agora: a roupa em destaque, a barra da make quando tem, e as linhas.
      const rp = d.roupa;
      $("bf-agora-t").hidden = $("bf-agora").hidden = !rp;
      if (rp) {
        $("bf-agora").innerHTML = `<div class="big">${esc(rp.look)}</div>
          ${rp.make ? `<div class="ca-barras"><div class="bar-row"><span>Estado</span><div class="bar${rp.make.alerta ? " alerta" : ""}"><i style="width:${pct(rp.make.valor)}%"></i></div>
            <span class="w">${esc(rp.make.palavra)}</span></div></div>` : ""}
          <div class="linhas sep">${rp.linhas.map(([i, r, v]) => linha(i, r, v)).join("")}</div>`;
      }
      const ps = d.peso;
      $("bf-peso-t").hidden = $("bf-peso").hidden = !ps;
      if (ps) {
        $("bf-peso").innerHTML = `<div class="big">${esc(ps.kg)}</div>
          <div class="ca-barras"><div class="bar-row"><span>Agência</span><div class="bar${ps.alerta ? " alerta" : ""}"><i style="width:${pct(ps.barra)}%"></i></div>
            <span class="w">${esc(ps.palavra)}</span></div></div>
          <div class="linhas sep">${ps.linhas.map(([i, r, v]) => linha(i, r, v)).join("")}</div>`;
      }
      // 26/09 (Patrick): unhas em seção própria. 28/09: a barra ganha rótulo, igual ao Cabelo (Desgaste · estado)
      const u = d.unhas;
      $("bd-unhas-t").hidden = $("bd-unhas").hidden = !u;
      if (u) {
        $("bd-unhas").innerHTML = `<div class="big un-cor">${u.hex ? `<span class="un-dot" style="background:${esc(u.hex)}"></span>` : ""}${esc(u.cor)}</div>
          <div class="ca-barras"><div class="bar-row"><span>Desgaste</span><div class="bar${u.gasta ? " alerta" : ""}"><i style="width:${pct(u.desgaste)}%"></i></div>
            <span class="w">${esc(u.estado)}</span></div></div>
          <div class="linhas sep">${linha("droplet-half", "Tipo", u.tipo)}${linha("calendar-check", "Feita", u.feita)}</div>`;
      }
      // 26/09 (Patrick): cabelo em seção própria — penteado, quatro barras (amarela quando vence) e as linhas
      const cab = d.cabelo;
      $("bd-cabelo-t").hidden = $("bd-cabelo").hidden = !cab;
      if (cab) {
        $("bd-cabelo").innerHTML = `<div class="big un-cor">${cab.hex ? `<span class="un-dot" style="background:${esc(cab.hex)}"></span>` : ""}${esc(cab.penteado)}</div>
          <div class="ca-barras">${cab.barras.map((b) => `<div class="bar-row"><span>${esc(b.label)}</span>
            <div class="bar${b.alerta ? " alerta" : ""}"><i style="width:${pct(b.valor)}%"></i></div><span class="w">${esc(b.palavra)}</span></div>`).join("")}</div>
          <div class="linhas sep">${cab.linhas.map(([i, r, v]) => linha(i, r, v)).join("")}</div>`;
      }
      $("bd-humor").innerHTML = `<div class="big">${esc(e.humor)}</div>` + e.humor_barras.map((b) => bar(b.label, b.value)).join("");
      // 28/09 (Patrick): o motivo ganha quando começou, na direita
      $("bd-sentindo").innerHTML = e.sentindo.length ? e.sentindo.map((f) => `<div class="feel">
        <div class="head"><span class="t">${esc(f.texto)}</span><div class="bar"><i style="width:${pct(f.valor)}%"></i></div></div>
        <div class="why"><span>${esc(f.motivo)}${f.detalhe ? `<span class="dt"> · ${esc(f.detalhe)}</span>` : ""}</span>${f.quando ? `<span class="qd">${esc(f.quando)}</span>` : ""}</div>
        ${f.vezes > 1 || f.ate_resolver ? `<div class="pilulas">${f.vezes > 1 ? `<span class="pilula">${f.vezes} vezes</span>` : ""}${f.ate_resolver ? '<span class="pilula">até resolver</span>' : ""}</div>` : ""}</div>`).join("")
        : vazio("Nada marcante agora.");
      // 28/09 (Patrick): Na cabeça — o que vem pela frente e a vontade dela de ir (agenda viva).
      // O mais curto possível: título | quando; embaixo estado | barra | motivo (coluna da direita, como no Corpo)
      const cb = d.cabeca || [];
      $("bd-cabeca-t").hidden = $("bd-cabeca").hidden = !cb.length;
      $("bd-cabeca").innerHTML = cb.map((x) => `<div class="nc"><div class="nc-t"><span>${esc(x.titulo)}</span><span class="qd">${esc(x.quando)}</span></div>
        ${x.estado || x.vontade != null || x.detalhe ? `<div class="nc-s"><span class="nc-e">${esc(x.estado)}</span>${x.vontade != null
          ? `<div class="bar"><i style="width:${pct(x.vontade)}%"></i></div>` : "<span></span>"}<span class="w">${esc(x.detalhe)}</span></div>` : ""}</div>`).join("");
      // 28/09 (Patrick): Hoje por dentro — tudo o que ela sentiu no dia, mesmo o que já passou (5 + ver o dia todo)
      const di = d.diario || { itens: [] };
      $("bd-diario-t").hidden = $("bd-diario").hidden = !di.itens.length;
      $("bd-diario-t").textContent = di.titulo || "Hoje por dentro";
      const desenhaDiario = () => {
        const todos = DIARIO_ABERTO || di.itens.length <= 6;
        $("bd-diario").innerHTML = (todos ? di.itens : di.itens.slice(0, 5)).map((x) => `<div class="dr">
          <span class="dr-h">${esc(x.hora)}</span><div><div>${esc(x.texto)}</div><div class="dr-m"><span>${esc(x.motivo)}</span>
          ${x.detalhe ? `<span class="dr-d">${esc(x.detalhe)}</span>` : ""}</div></div></div>`).join("")
          + (di.itens.length > 6 ? `<button class="dr-mais">${DIARIO_ABERTO ? "Mostrar menos" : `Ver o dia todo (${di.itens.length})`}</button>` : "");
        const b = $("bd-diario").querySelector(".dr-mais");
        if (b) b.addEventListener("click", () => { DIARIO_ABERTO = !DIARIO_ABERTO; desenhaDiario(); });
      };
      desenhaDiario();
      $("bd-voces").innerHTML = e.voces.map((b) => bar(b.label, b.value, null, b.label === "Desejo")).join("")
        + ((e.voces_linhas || []).length ? `<div class="linhas sep">${e.voces_linhas.map(([i, r, v]) => linha(i, r, v)).join("")}</div>` : "");

      // Dinheiro — 28/09 (Patrick, no celular): saldo, entrou/saiu no mês, próximo cachê e contas;
      // extrato por dia, saída agrupada com o total (toca e abre os itens, como no Hoje)
      $("bn-saldo").textContent = brl(g.saldo);
      const tp = g.topo;
      $("bn-mes").innerHTML = `<div><span class="d">Entrou em ${esc(tp.mes)}</span><b class="plus">+ ${brl0(tp.entrou)}</b></div>
        <div><span class="d">Saiu em ${esc(tp.mes)}</span><b>− ${brl0(tp.saiu)}</b></div>`;
      $("bn-linhas").innerHTML = [...tp.linhas.map(([i, r, v]) => linha(i, r, v)),
        g.devendo && linha("arrow-back-up", "Deve a você", brl0(g.devendo)),
        g.pedido && linha("alert-circle", "Precisa de", `${brl0(g.pedido.valor)} · ${g.pedido.motivo}`)].filter(Boolean).join("");
      const valor = (v) => `${v >= 0 ? "+" : "−"} ${brl0(Math.abs(v))}`;
      const mov = (x, extra = "") => `<span class="mov-txt">${esc(x.texto)}${extra}${x.sub ? `<span class="mov-sub">${esc(x.sub)}</span>` : ""}</span>
        <span class="mov-val${x.valor >= 0 ? " plus" : ""}">${valor(x.valor)}<span class="mov-sub">${esc(x.hora)}</span></span>`;
      const desenhaExtrato = () => {
        $("bn-extrato").innerHTML = g.extrato.length ? g.extrato.map((d) => `<h2>${esc(d.dia)}</h2><div class="card">${d.itens.map((x) => {
          if (!x.filhos.length) return `<div class="mov">${mov(x)}</div>`;
          const id = `${d.dia}|${x.hora}|${x.texto}`, aberto = EXTRATO_ABERTOS.has(id);
          return `<button class="mov${aberto ? " aberto" : ""}" data-ext="${esc(id)}">${mov(x, ic(aberto ? "chevron-up" : "chevron-down"))}</button>
            ${aberto ? `<div class="mov-filhos">${x.filhos.map((f) => `<div class="mov">${mov(f)}</div>`).join("")}</div>` : ""}`;
        }).join("")}</div>`).join("") : `<h2>Extrato</h2><div class="card">${vazio("Nenhuma movimentação ainda.")}</div>`;
        $("bn-extrato").querySelectorAll("[data-ext]").forEach((b) => b.addEventListener("click", () => {
          const id = b.dataset.ext;
          EXTRATO_ABERTOS.has(id) ? EXTRATO_ABERTOS.delete(id) : EXTRATO_ABERTOS.add(id);
          desenhaExtrato();
        }));
      };
      desenhaExtrato();

      // Mundo — 28/09 (Patrick, no celular): pessoas por círculo (quando e vezes no mês na direita, se houve contato);
      // Rolando agora sem os fios de sistema; Planos; Onde ela foi no mês (com quem, quando, vezes)
      const vezes = (n) => n ? `<div class="d">${n} ${n > 1 ? "vezes" : "vez"} no mês</div>` : "";
      const bloco = (titulo, itens) => itens.length ? `<h2>${titulo}</h2><div class="card">${itens.join("")}</div>` : "";
      const pessoa = (p) => `<div class="pessoa">${p.foto
        ? `<img class="avatar-ini avatar-foto" src="/static/${esc(p.foto)}" alt="">`
        : `<span class="avatar-ini">${esc(p.iniciais)}</span>`}
        <div class="ps-txt"><div class="t">${esc(p.titulo)}</div>${p.sub ? `<div class="d">${esc(p.sub)}</div>` : ""}</div>
        <div class="ps-dir"><div class="d">${p.falaram ? esc(p.falaram) : "Sem contato ainda"}</div>${p.falaram ? vezes(p.vezes_30d) : ""}</div></div>`;
      $("bm-pessoas").innerHTML = m.circulos.map((c) => bloco(c, m.pessoas.filter((p) => p.circulo === c).map(pessoa))).join("")
        || `<h2>Pessoas</h2><div class="card">${vazio("Ninguém ainda.")}</div>`;
      $("bm-resto").innerHTML =
        bloco("Rolando agora", m.rolando.map((r) => `<div class="item-m"><div>${esc(cap(r.titulo))}</div>${r.com.length ? `<div class="d">Com ${esc(r.com.join(", "))}</div>` : ""}</div>`))
        + bloco("Planos", m.planos.map((p) => `<div class="item-m dois-lados"><span>${esc(cap(p.descricao))}</span><span class="d">${esc(p.quando)}</span></div>`))
        + bloco("Onde ela foi", m.lugares.map((l) => `<div class="item-m lugar"><div><div>${esc(l.nome)}</div><div class="d">${esc(l.com)}</div></div>
          <div class="ps-dir"><div class="d">${esc(l.quando)}</div>${vezes(l.vezes)}</div></div>`));
      deslizaBarras(antes);
    } catch (err) { failIn($("ag-card"), err); }
    finally { BAST_CARREGANDO = false; }
  },
};

// ------------------------------------------------------------------- ações --
document.addEventListener("click", (e) => {
  const go = e.target.closest("[data-go]");
  if (go) { show(go.dataset.go); return; }
  const aba = e.target.closest("[data-bast]");
  if (aba) {
    document.querySelectorAll("[data-bast]").forEach((b) => b.classList.toggle("on", b === aba));
    document.querySelectorAll(".bast-aba").forEach((v) => (v.hidden = v.id !== "ba-" + aba.dataset.bast));
    window.scrollTo(0, 0);
  }
});

$("pix-valor").addEventListener("input", () => ($("pix-err").textContent = ""));
$("pix-continuar").addEventListener("click", () => {
  const valor = Math.round(Number(String($("pix-valor").value).replace(",", ".")));
  if (!valor || valor < 1 || valor > 5000) { $("pix-err").textContent = "Digite um valor entre R$ 1 e R$ 5.000"; return; }
  loaders._pix = { valor, recado: $("pix-recado").value.trim() };
  show("revisao");
});

$("pix-confirmar").addEventListener("click", async () => {
  const btn = $("pix-confirmar"); btn.disabled = true;
  try {
    await api("/api/pix", loaders._pix);
    $("pix-valor").value = ""; $("pix-recado").value = "";
    concluido("Transferência feita");
    stack.length = 1; show("inicio", false);
  } catch (err) { $("rev-err").textContent = err.message; }
  finally { btn.disabled = false; }
});

// ------------------------------------------------------------ iFood: estado --
const TAXA_SERVICO = 0.99;
const IF = {
  lojas: [], filtro: "Tudo", lojaId: null, loja: null, item: null, qtd: 1,
  cart: { loja: null, itens: [] },
  aval: (n) => (n >= 1000 ? (n / 1000).toFixed(1).replace(".", ",").replace(",0", "") + " mil" : String(n)),
  taxa: (t) => (t ? brl(t) : '<span class="gratis">Grátis</span>'),
  subtotal() { return this.cart.itens.reduce((s, x) => s + x.item.preco * x.qtd, 0); },
  total() { return this.cart.loja ? this.subtotal() + this.cart.loja.taxa + TAXA_SERVICO : 0; },
  // a lista (e o pedido em andamento) vem uma vez; a aba Pedidos recarrega pra ver o histórico novo
  async carregar(fresco = false) {
    if (fresco || !this._d) { this._d = await api("/api/ifood"); this.lojas = this._d.lojas; }
    return this._d;
  },
  andamento(p) {
    return p && p.status === "a_caminho"
      ? `<div class="if-andamento"><div class="small muted">Pedido em andamento</div>${pedidoCard(p, "Seu pedido pra Ma")}</div>` : "";
  },
  chips(alvo) {
    const cats = [...new Set(this.lojas.filter((l) => l.tipo === "restaurante").map((l) => l.categoria))].sort();
    const all = ["Tudo", "Restaurantes", "Mercados", "Farmácias", ...cats];
    $(alvo).innerHTML = all.map((c) => `<button class="chip${c === this.filtro ? " on" : ""}" data-chip="${esc(c)}">${esc(c)}</button>`).join("");
  },
  filtrar(q) {
    const f = this.filtro;
    let ls = this.lojas.filter((l) => f === "Tudo" || (f === "Restaurantes" && l.tipo === "restaurante") ||
      (f === "Mercados" && l.tipo === "mercado") || (f === "Farmácias" && l.tipo === "farmacia") || l.categoria === f);
    if (q) ls = ls.filter((l) => (l.nome + " " + l.categoria).toLowerCase().includes(q));
    const ordem = { restaurante: 0, mercado: 1, farmacia: 2 };
    return ls.sort((a, b) => (b.aberta - a.aberta) || (ordem[a.tipo] - ordem[b.tipo]) || (b.mais_pedido - a.mais_pedido) || a.km - b.km);
  },
  linhas(ls) {
    return ls.map((l) => `<button class="loja-row${l.aberta ? "" : " off"}" data-loja="${esc(l.id)}">
      <img class="loja-circ" src="/static/${esc(l.logo)}" alt=""><div class="lr-txt">
      ${l.mais_pedido && l.aberta ? '<span class="selo-mp">Mais Pedido</span>' : ""}
      <div class="lr-nome">${esc(l.nome)}</div>
      <div class="d com-ic">${l.aberta
        ? `${ic("star-filled", "estrela")}<span class="estrela">${nota(l.nota)}</span><span>(${IF.aval(l.avaliacoes)}) • ${l.eta[0]}-${l.eta[1]} min • ${IF.taxa(l.taxa)}</span>`
        : `<span>Fechada • ${abreAs(l.abre)}</span>`}</div>
      ${l.aberta && !l.taxa ? '<span class="tag-gratis">Grátis</span>' : ""}</div>${ic("heart", "coracao")}</button>`).join("")
      || `<p class="muted">Nada encontrado.</p>`;
  },
  lista() {
    const f = this.filtro;
    $("if-titulo").textContent = f === "Tudo" ? "Lojas" : f === "Mercados" || f === "Farmácias" ? "Mais pedidos" : f;
    $("if-lojas").innerHTML = this.linhas(this.filtrar(""));
  },
  busca() {
    $("bs-lojas").innerHTML = this.linhas(this.filtrar(($("if-busca").value || "").trim().toLowerCase()));
  },
  // "Adicione à sacola" do histórico: a mesma sacola de novo (se a loja estiver aberta)
  async repetir(p) {
    const loja = await api("/api/ifood/loja/" + encodeURIComponent(p.loja_id));
    if (!loja.aberta) { toast(`Loja fechada • ${abreAs(loja.abre)}`); return; }
    const por = new Map(loja.secoes.flatMap((s) => s.itens).map((i) => [i.id, i]));
    const itens = p.itens.filter((i) => por.has(i.id)).map((i) => ({ item: por.get(i.id), qtd: i.qtd, obs: "" }));
    if (!itens.length) { toast("Esses itens não estão mais no cardápio"); return; }
    if (this.cart.loja && this.cart.loja.id !== loja.id && this.cart.itens.length &&
        !(await this.confirmar(`Sua sacola tem itens de ${this.cart.loja.nome}. Limpar a sacola e adicionar estes itens?`))) return;
    this.cart = { loja, itens };
    this.loja = loja;
    show("sacola");
  },
  stepper() {
    $("pr-qtd").textContent = this.qtd;
    $("pr-menos").disabled = this.qtd <= 1;
    $("pr-total").textContent = brl(this.item.preco * this.qtd);
  },
  barra() {
    const b = $("lj-barra");
    const on = this.cart.loja && this.loja && this.cart.loja.id === this.loja.id && this.cart.itens.length;
    b.hidden = !on;
    if (on) {
      const n = this.cart.itens.reduce((s, x) => s + x.qtd, 0);
      b.innerHTML = `<button class="btn-vermelho largo" data-go="sacola"><span>Ver sacola</span><span>${brl(this.subtotal())} / ${n} ${n > 1 ? "itens" : "item"}</span></button>`;
    }
  },
  async confirmar(msg) {
    if (tgAt("6.2")) return new Promise((r) => tg.showConfirm(msg, r));
    return window.confirm(msg);
  },
};

document.addEventListener("click", async (e) => {
  const chip = e.target.closest("[data-chip]");
  if (chip) {
    IF.filtro = chip.dataset.chip;
    if (stack[stack.length - 1] === "ifbusca") { IF.chips("bs-chips"); IF.busca(); } else { IF.chips("if-chips"); IF.lista(); }
    return;
  }
  const aba = e.target.closest("[data-tab]");
  if (aba) { tab(aba.dataset.tab); return; }
  const rep = e.target.closest("[data-repetir]");
  if (rep) { try { await IF.repetir(IF._d.pedidos[Number(rep.dataset.repetir)]); } catch (err) { toast(err.message); } return; }
  const loja = e.target.closest("[data-loja]");
  if (loja) { IF.lojaId = loja.dataset.loja; show("loja"); return; }
  const sec = e.target.closest("[data-secao]");
  if (sec) { const h = $("sec-" + sec.dataset.secao); if (h) window.scrollTo({ top: h.offsetTop - 56, behavior: "smooth" }); return; }
  const prato = e.target.closest("[data-prato]");
  if (prato) {
    const lojaAtual = IF.loja || IF.cart.loja;
    IF.item = lojaAtual.secoes.flatMap((s) => s.itens).find((i) => i.id === prato.dataset.prato);
    if (IF.item) show("prato");
    return;
  }
  const sc = e.target.closest("[data-sc]");
  if (sc) {
    const x = IF.cart.itens[Number(sc.dataset.n)];
    if (sc.dataset.sc === "mais") x.qtd = Math.min(20, x.qtd + 1);
    else if (x.qtd > 1) x.qtd -= 1;
    else IF.cart.itens.splice(Number(sc.dataset.n), 1);
    if (IF.cart.itens.length) loaders.sacola(); else back();
    return;
  }
  if (e.target.closest("[data-go-back]")) back();
});

$("if-busca").addEventListener("input", () => IF.busca());
$("pr-obs").addEventListener("input", () => ($("pr-cont").textContent = `${$("pr-obs").value.length}/140`));
$("pr-menos").addEventListener("click", () => { if (IF.qtd > 1) { IF.qtd -= 1; IF.stepper(); } });
$("pr-mais").addEventListener("click", () => { if (IF.qtd < 20) { IF.qtd += 1; IF.stepper(); } });
$("pr-add").addEventListener("click", async () => {
  const loja = IF.loja;
  if (!loja.aberta) { toast(`Loja fechada • ${abreAs(loja.abre)}`); return; }
  if (IF.cart.loja && IF.cart.loja.id !== loja.id && IF.cart.itens.length) {
    if (!(await IF.confirmar(`Sua sacola tem itens de ${IF.cart.loja.nome}. Limpar a sacola e adicionar este item?`))) return;
    IF.cart.itens = [];
  }
  IF.cart.loja = loja;
  IF.cart.itens.push({ item: IF.item, qtd: IF.qtd, obs: $("pr-obs").value.trim() });
  back();
  toast("Item adicionado à sacola");
});
$("sc-limpar").addEventListener("click", async () => {
  if (await IF.confirmar("Limpar a sacola?")) { IF.cart.itens = []; back(); }
});
$("sc-continuar").addEventListener("click", () => {
  if (IF.subtotal() < IF.cart.loja.minimo) { toast(`O pedido mínimo dessa loja é ${brl(IF.cart.loja.minimo)}`); return; }
  show("entrega");
});
$("pg-revisar").addEventListener("click", () => {
  $("rv-eta").textContent = `Hoje, ${IF.cart.loja.eta[0]} - ${IF.cart.loja.eta[1]} min`;
  $("rv-total").textContent = brl(IF.total());
  $("rv-err").textContent = "";
  $("rv-fundo").hidden = false;
});
$("rv-alterar").addEventListener("click", () => ($("rv-fundo").hidden = true));
$("rv-fundo").addEventListener("click", (e) => { if (e.target.id === "rv-fundo") $("rv-fundo").hidden = true; });
$("rv-fazer").addEventListener("click", async () => {
  const btn = $("rv-fazer"); btn.disabled = true;
  try {
    await api("/api/delivery", { loja: IF.cart.loja.id, itens: IF.cart.itens.map((x) => ({ id: x.item.id, qtd: x.qtd, obs: x.obs })) });
    IF.cart = { loja: null, itens: [] };
    IF._d = null;
    $("rv-fundo").hidden = true;
    concluido("Pedido feito");
    stack.length = 1; show("inicio", false);
  } catch (err) { $("rv-err").textContent = err.message; }
  finally { btn.disabled = false; }
});

show("inicio", false);
// 26/09 (Patrick): o que ela sente atualiza em tempo real — Bastidores aberto se recarrega sozinho.
// 28/09: "em todas as telas, a barra deve ser atualizada em tempo real" — a cada 30 s (antes 1 min), sem
// duas recargas ao mesmo tempo, na volta pro app e com a barra deslizando até o valor novo (app.css)
function recarregaBastidores() {
  if (stack[stack.length - 1] === "bastidores" && !document.hidden) loaders.bastidores();
}
setInterval(recarregaBastidores, 30000);
document.addEventListener("visibilitychange", recarregaBastidores);
