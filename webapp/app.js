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
function show(view, push = true) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "v-" + view));
  if (push) stack.push(view);
  if (nativeBack) (stack.length > 1 ? tg.BackButton.show() : tg.BackButton.hide());
  else $("voltar").hidden = stack.length <= 1;
  window.scrollTo(0, 0);
  (loaders[view] || (() => {}))();
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
      const d = await api("/api/ifood");
      IF.lojas = d.lojas;
      $("if-andamento").innerHTML = d.pedido && d.pedido.status === "a_caminho"
        ? `<div class="if-andamento"><div class="small muted">Pedido em andamento</div>${pedidoCard(d.pedido, "Seu pedido pra Ma")}</div>` : "";
      IF.chips();
      IF.lista();
      $("if-pedidos").innerHTML = d.pedidos.length ? `<h3 class="if-h">Pedidos</h3>${d.pedidos.map((p) =>
        `<div class="ped-row"><div><div class="t">${esc(p.restaurant)}</div><div class="d">${esc(cap(p.what))}</div>
          <div class="d">${esc(p.when)} · ${brl(p.price)}</div></div><span class="d">${esc(p.status)}</span></div>`).join("")}` : "";
    } catch (e) { failIn($("if-lojas"), e); }
  },

  async loja() {
    try {
      const l = await api("/api/ifood/loja/" + encodeURIComponent(IF.lojaId));
      IF.loja = l;
      $("lj-capa").style.backgroundImage = l.capa ? `url(/static/${l.capa})` : "";
      $("lj-logo").src = "/static/" + l.logo;
      $("lj-nome").textContent = l.nome;
      $("lj-info").textContent = `Entrega rastreável • ${String(l.km).replace(".", ",")} km • Min ${brl(l.minimo)}`;
      $("lj-nota").innerHTML = `<span>★ <b>${String(l.nota).replace(".", ",")}</b> <span class="muted">(${IF.aval(l.avaliacoes)} avaliações)</span></span><span class="muted">›</span>`;
      $("lj-entrega").innerHTML = l.aberta
        ? `<span><b>Padrão</b> • ${l.eta[0]}-${l.eta[1]} min • ${IF.taxa(l.taxa)}</span>`
        : `<span class="fechada">Loja fechada • Abre às ${String(l.abre).padStart(2, "0")}:00</span>`;
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
      <div class="sc-ctl"><button data-sc="menos" data-n="${n}">${x.qtd > 1 ? "−" : '<span class="lixo"></span>'}</button><span>${x.qtd}</span><button data-sc="mais" data-n="${n}">+</button></div></div>`).join("");
    const ids = new Set(c.itens.map((x) => x.item.id));
    const outros = c.loja.secoes.flatMap((s) => s.itens).filter((i) => !ids.has(i.id)).slice(0, 6);
    $("sc-tambem").innerHTML = outros.map((i) => `<button class="car-item" data-prato="${esc(i.id)}"><div class="car-foto" style="background-image:url(/static/${esc(i.foto)})"><span class="car-mais">+</span></div>
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

  async bastidores() {
    try {
      const [d, g] = await Promise.all([api("/api/bastidores"), api("/api/dinheiro")]);
      const s = d.status, e = d.emocao;
      const linhas = [`🏠 ${s.local} · ${s.atividade}`, `📱 ${s.disponivel}`, `🌸 Dia ${s.ciclo_dia} do ciclo (${s.ciclo_fase})`];
      (s.saude || []).forEach(([l, r]) => linhas.push(`🤒 ${l} · ${r}`));
      if (s.proximo) linhas.push(`📅 Próximo: ${s.proximo[0]} ${s.proximo[1]}`);
      (s.planos || []).forEach(([p, w]) => linhas.push(`🗓️ ${p} · ${w}`));
      $("bast-status").innerHTML = linhas.map((l) => `<div>${esc(l)}</div>`).join("");

      const bar = (label, v, word, warm) => `<div class="bar-row"><span>${esc(label)}</span>
        <div class="bar${warm ? " warm" : ""}"><i style="width:${pct(v)}%"></i></div><span class="w">${esc(word || pct(v) + "%")}</span></div>`;
      let corpo = e.body.map((b) => bar(b.label, b.value, b.word, b.label === "Tesão")).join("");
      const extra = [];
      if (e.in_the_mood) extra.push("no clima agora");
      if (e.hours_since_release != null) extra.push(`última vez há ${Math.round(e.hours_since_release)} h`);
      if (e.hours_slept != null) extra.push(`dormiu ${e.hours_slept.toFixed(1).replace(".", ",")} h`);
      if (e.phase) extra.push(e.phase);
      if (e.discomfort_why) extra.push(e.discomfort_why);
      if (extra.length) corpo += `<div class="small muted">${esc(extra.join(" · "))}</div>`;
      $("bast-corpo").innerHTML = corpo;
      $("bast-humor").innerHTML = `<div class="big">${esc(cap(e.mood))}</div>` + e.mood_bars.map((b) => bar(b.label, b.value)).join("");
      $("bast-sentindo").innerHTML = e.feelings.length ? e.feelings.map((f) => `<div class="feel">
        <div class="head"><span>${esc(f.word)}${f.target ? " com " + esc(f.target) : ""}${f.count > 1 ? ` <span class="muted small">· ${f.count} momentos</span>` : ""}</span>
        <div class="bar"><i style="width:${pct(f.value)}%"></i></div></div>
        <div class="why">${esc(f.cause)}${f.until_resolved ? " (até resolver)" : ""}</div></div>`).join("")
        : `<p class="muted">Nada marcante agora.</p>`;
      $("bast-vinculo").innerHTML = e.bond.map((b) => bar(b.label, b.value, null, b.label === "Desejo")).join("");

      let din = `<div class="muted small">Saldo</div><div class="big">${brl(g.saldo)}</div>`;
      if (g.devendo) din += `<div class="small">Te deve ${brl(g.devendo)}</div>`;
      if (g.pedido) din += `<div class="small">Precisando de ${brl(g.pedido.valor)}: ${esc(g.pedido.motivo)}</div>`;
      $("bast-dinheiro").innerHTML = din;
      $("bast-movs").innerHTML = g.movs.slice(0, 12).map((m) => {
        const dt = new Date(m.at);
        const when = dt.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + " " +
          dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
        return `<div class="item"><div><div class="t">${esc(cap(m.desc))}</div><div class="d">${when}</div></div>
          <div class="${m.valor >= 0 ? "plus" : "minus"}">${m.valor >= 0 ? "+" : "−"}${brl(Math.abs(m.valor))}</div></div>`;
      }).join("");

      $("bast-hoje").innerHTML = d.hoje.length ? d.hoje.map((h) => `<div class="item"><span class="d">${esc(h.at)}</span>
        <span style="flex:1">${esc(h.texto)}</span></div>`).join("") : `<p class="muted">Nada registrado hoje ainda.</p>`;
      $("bast-mundo").textContent = d.mundo || "";
    } catch (err) { failIn($("bast-status"), err); }
  },
};

// ------------------------------------------------------------------- ações --
document.addEventListener("click", (e) => {
  const go = e.target.closest("[data-go]");
  if (go) { show(go.dataset.go); return; }
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
  chips() {
    const cats = [...new Set(this.lojas.filter((l) => l.tipo === "restaurante").map((l) => l.categoria))].sort();
    const all = ["Tudo", "Restaurantes", "Mercados", "Farmácias", ...cats];
    $("if-chips").innerHTML = all.map((c) => `<button class="chip${c === this.filtro ? " on" : ""}" data-chip="${esc(c)}">${esc(c)}</button>`).join("");
  },
  lista() {
    const q = ($("if-busca").value || "").trim().toLowerCase();
    const f = this.filtro;
    let ls = this.lojas.filter((l) => f === "Tudo" || (f === "Restaurantes" && l.tipo === "restaurante") ||
      (f === "Mercados" && l.tipo === "mercado") || (f === "Farmácias" && l.tipo === "farmacia") || l.categoria === f);
    if (q) ls = ls.filter((l) => (l.nome + " " + l.categoria).toLowerCase().includes(q));
    const ordem = { restaurante: 0, mercado: 1, farmacia: 2 };
    ls.sort((a, b) => (b.aberta - a.aberta) || (ordem[a.tipo] - ordem[b.tipo]) || (b.mais_pedido - a.mais_pedido) || a.km - b.km);
    $("if-titulo").textContent = f === "Tudo" ? "Lojas" : f === "Mercados" || f === "Farmácias" ? "Mais pedidos" : f;
    $("if-lojas").innerHTML = ls.map((l) => `<button class="loja-row${l.aberta ? "" : " off"}" data-loja="${esc(l.id)}">
      <img class="loja-circ" src="/static/${esc(l.logo)}" alt=""><div class="lr-txt">
      ${l.mais_pedido && l.aberta ? '<span class="selo-mp">Mais Pedido</span>' : ""}
      <div class="lr-nome">${esc(l.nome)}</div>
      <div class="d">${l.aberta ? `<span class="estrela">★ ${String(l.nota).replace(".", ",")}</span> (${IF.aval(l.avaliacoes)}) • ${l.eta[0]}-${l.eta[1]} min • ${IF.taxa(l.taxa)}`
        : `Fechada • Abre às ${String(l.abre).padStart(2, "0")}:00`}</div>
      ${l.aberta && !l.taxa ? '<span class="tag-gratis">Grátis</span>' : ""}</div><span class="coracao">♡</span></button>`).join("")
      || `<p class="muted">Nada encontrado.</p>`;
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
  if (chip) { IF.filtro = chip.dataset.chip; IF.chips(); IF.lista(); return; }
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

$("if-busca").addEventListener("input", () => IF.lista());
$("pr-obs").addEventListener("input", () => ($("pr-cont").textContent = `${$("pr-obs").value.length}/140`));
$("pr-menos").addEventListener("click", () => { if (IF.qtd > 1) { IF.qtd -= 1; IF.stepper(); } });
$("pr-mais").addEventListener("click", () => { if (IF.qtd < 20) { IF.qtd += 1; IF.stepper(); } });
$("pr-add").addEventListener("click", async () => {
  const loja = IF.loja;
  if (!loja.aberta) { toast(`Loja fechada • Abre às ${String(loja.abre).padStart(2, "0")}:00`); return; }
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
    $("rv-fundo").hidden = true;
    concluido("Pedido feito");
    stack.length = 1; show("inicio", false);
  } catch (err) { $("rv-err").textContent = err.message; }
  finally { btn.disabled = false; }
});

show("inicio", false);
