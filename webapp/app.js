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
const TABS = ["ifood", "ifbusca", "ifpedidos"];       // abas da barra de baixo do iFood
function show(view, push = true) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "v-" + view));
  $("if-nav").hidden = !TABS.includes(view);
  document.querySelectorAll("#if-nav [data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === view));
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
function back() { if (!$("rv-fundo").hidden) { $("rv-fundo").hidden = true; return; } if (stack.length > 1) { stack.pop(); show(stack[stack.length - 1], false); } }
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
const ic = (name, cls = "") => `<i class="bi bi-${name}${cls ? " " + cls : ""}"></i>`;
const nota = (n) => String(n).replace(".", ",");
const abreAs = (h) => `Abre às ${String(h).padStart(2, "0")}:00`;

const loaders = {
  async inicio() {
    try {
      const d = await api("/api/inicio");
      const a = d.agora;
      $("inicio-sub").textContent = `${a.local} · ${new Date(a.now).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
      $("inicio-agora").textContent = cap(a.atividade);
      $("inicio-disp").textContent = a.disponivel;
      $("inicio-presente").innerHTML = pedidoCard(d.pra_voce, "Presente da Ma");
    } catch (e) { failIn($("inicio-agora"), e); }
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
        const logo = p.logo ? `<img class="loja-circ peq" src="/static/${esc(p.logo)}" alt="">` : `<span class="loja-circ peq">${ic("shop")}</span>`;
        html += `<div class="pd-card"><div class="pd-loja">${logo}
          <div><div class="t">${esc(p.restaurant)}</div><div class="d com-ic">${esc(p.status)}${p.concluido ? ic("check-circle-fill", "ok") : ""}</div></div></div>
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
      $("lj-nota").innerHTML = `<span class="com-ic">${ic("star-fill", "estrela")}<b>${nota(l.nota)}</b><span class="muted">(${IF.aval(l.avaliacoes)} avaliações)</span></span>${ic("chevron-right", "muted")}`;
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
      <div class="sc-ctl"><button data-sc="menos" data-n="${n}">${x.qtd > 1 ? ic("dash-lg") : ic("trash3")}</button><span>${x.qtd}</span><button data-sc="mais" data-n="${n}">${ic("plus-lg")}</button></div></div>`).join("");
    const ids = new Set(c.itens.map((x) => x.item.id));
    const outros = c.loja.secoes.flatMap((s) => s.itens).filter((i) => !ids.has(i.id)).slice(0, 6);
    $("sc-tambem").innerHTML = outros.map((i) => `<button class="car-item" data-prato="${esc(i.id)}"><div class="car-foto" style="background-image:url(/static/${esc(i.foto)})"><span class="car-mais">${ic("plus-lg")}</span></div>
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
  // (status_view, emocao_view, world_panel, mov_desc); aqui é só desenho.
  async bastidores() {
    try {
      const [d, g] = await Promise.all([api("/api/bastidores"), api("/api/dinheiro")]);
      const s = d.status, e = d.emocao, m = d.mundo;
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
          <span class="ag-hr">${esc(p.hora)}</span></div>`).join("")}</div>` : "";
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
          <div class="ag-sep"></div>${grade([["phone", "Celular", s.celular], s.ciclo && ["droplet", "Ciclo", s.ciclo],
            ...s.saude.map((x) => ["thermometer-half", "Saúde", x]), s.proximo && ["calendar-event", "Próximo", s.proximo],
            ...s.planos.map((x) => ["calendar3", "Plano", x])].filter(Boolean))}`;
      }
      $("ag-hoje").innerHTML = d.hoje.length ? `<ol class="linha-tempo">${d.hoje.map((h) =>
        `<li><span class="lt-hora">${esc(h.at)}</span><span class="lt-ponto"></span><span class="lt-txt">${esc(cap(h.texto.replace(/\.$/, "")))}</span></li>`).join("")}</ol>`
        : vazio(s.dormindo ? "Ela ainda não acordou." : "Nada registrado hoje ainda.");

      // Por dentro
      $("bd-corpo").innerHTML = e.body.map((b) => bar(b.label, b.value, b.word, b.label === "Tesão")).join("")
        + (e.linhas.length || e.no_clima ? `<div class="linhas sep">${e.linhas.map(([i, r, v]) => linha(i, r, v)).join("")}
          ${e.no_clima ? `<div class="linha"><span class="li-ic">${ic("fire")}</span><span class="li-rot">No clima agora</span></div>` : ""}</div>` : "");
      $("bd-humor").innerHTML = `<div class="big">${esc(e.humor)}</div>` + e.humor_barras.map((b) => bar(b.label, b.value)).join("");
      $("bd-sentindo").innerHTML = e.sentindo.length ? e.sentindo.map((f) => `<div class="feel">
        <div class="head"><span class="t">${esc(f.texto)}</span><div class="bar"><i style="width:${pct(f.valor)}%"></i></div></div>
        <div class="why">${esc(f.motivo)}</div>
        ${f.vezes > 1 || f.ate_resolver ? `<div class="pilulas">${f.vezes > 1 ? `<span class="pilula">${f.vezes} vezes</span>` : ""}${f.ate_resolver ? '<span class="pilula">até resolver</span>' : ""}</div>` : ""}</div>`).join("")
        : vazio("Nada marcante agora.");
      $("bd-voces").innerHTML = e.voces.map((b) => bar(b.label, b.value, null, b.label === "Desejo")).join("");

      // Dinheiro
      $("bn-saldo").textContent = brl(g.saldo);
      $("bn-linhas").innerHTML = [g.devendo && linha("arrow-return-left", "Deve a você", brl(g.devendo)),
        g.pedido && linha("exclamation-circle", `Precisa de ${brl(g.pedido.valor)}`, cap(g.pedido.motivo))].filter(Boolean).join("");
      $("bn-linhas").hidden = !g.devendo && !g.pedido;
      $("bn-extrato").innerHTML = g.movs.length ? g.movs.slice(0, 20).map((mv) => {
        const dt = new Date(mv.at);
        const when = dt.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + " · " +
          dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
        return `<div class="mov"><div class="mov-txt"><div>${esc(mv.desc)}</div><div class="d">${when}</div></div>
          <div class="mov-val ${mv.valor >= 0 ? "plus" : "minus"}">${mv.valor >= 0 ? "+" : "−"} ${brl(Math.abs(mv.valor))}</div></div>`;
      }).join("") : vazio("Nenhuma movimentação ainda.");

      // Mundo
      $("bm-pessoas").innerHTML = m.pessoas.map((p) => `<div class="pessoa"><span class="avatar-ini">${esc(p.iniciais)}</span>
        <div class="ps-txt"><div class="t">${esc(p.nome)}</div><div class="d">${esc(cap(p.quem))}</div></div>
        <div class="ps-dir"><div class="d">${p.falaram ? esc(p.falaram) : "Sem contato ainda"}</div>
        ${p.vezes_30d ? `<div class="d">${p.vezes_30d} ${p.vezes_30d > 1 ? "vezes" : "vez"} no mês</div>` : ""}</div></div>`).join("")
        || vazio("Ninguém ainda.");
      const bloco = (titulo, itens) => itens.length ? `<h2>${titulo}</h2><div class="card">${itens.join("")}</div>` : "";
      $("bm-resto").innerHTML =
        bloco("Rolando agora", m.rolando.map((r) => `<div class="item-m"><div>${esc(cap(r.titulo))}</div>${r.com.length ? `<div class="d">Com ${esc(r.com.join(", "))}</div>` : ""}</div>`))
        + bloco("Planos", m.planos.map((p) => `<div class="item-m dois-lados"><span>${esc(cap(p.descricao))}</span><span class="d">${esc(p.quando)}</span></div>`))
        + bloco("Lugares", m.lugares.map((l) => `<div class="item-m dois-lados"><span>${esc(l.nome)}</span><span class="d">${esc(l.quanto)}</span></div>`));
    } catch (err) { failIn($("ag-card"), err); }
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
        ? `${ic("star-fill", "estrela")}<span class="estrela">${nota(l.nota)}</span><span>(${IF.aval(l.avaliacoes)}) • ${l.eta[0]}-${l.eta[1]} min • ${IF.taxa(l.taxa)}</span>`
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
