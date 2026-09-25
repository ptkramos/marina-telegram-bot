"use strict";
// Mini App da Marina (25/09). Sem framework. A API valida o initData do Telegram.
// Termos e marcas decididos com o Patrick: Nubank (Área Pix) e iFood, sem emoji nas telas dos apps.
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.ready(); tg.expand(); }
// Telegram antigo (ou fora dele) não tem BackButton (6.1) nem showConfirm (6.2): cai no da página.
const tgAt = (v) => !!(tg && tg.isVersionAtLeast && tg.isVersionAtLeast(v));
const nativeBack = tgAt("6.1");
const insideTelegram = !!(tg && tg.initData);

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const brl = (v) => "R$ " + Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const brl0 = (v) => "R$ " + Math.round(v).toLocaleString("pt-BR");
const pct = (v) => Math.max(0, Math.min(100, Math.round((v || 0) * 100)));
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");

async function api(path, body) {
  const opts = { headers: { "X-Telegram-Init-Data": tg ? tg.initData : "" } };
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
function back() { if (stack.length > 1) { stack.pop(); show(stack[stack.length - 1], false); } }
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
      $("inicio-pedido").innerHTML = pedidoCard(d.pedido, "Seu pedido pra Ma");
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

  async ifood() {
    try {
      const d = await api("/api/delivery");
      loaders._cardapio = d.cardapio;
      $("ifood-andamento").innerHTML = d.pedido && d.pedido.status === "a_caminho"
        ? `<p class="aviso">Você tem um pedido em andamento</p>${pedidoCard(d.pedido, "Seu pedido pra Ma")}` : "";
      $("ifood-lista").innerHTML = d.cardapio.restaurantes.map((r) => {
        const precos = r.itens.map((i) => i.preco);
        return `<button class="item" data-loja="${esc(r.id)}"><div><div class="t">${esc(r.nome)}</div>
          <div class="d">${esc(r.tipo)} · ${r.eta[0]}–${r.eta[1]} min · Entrega grátis</div></div><span class="d">a partir de ${brl0(Math.min(...precos))}</span></button>`;
      }).join("");
    } catch (e) { failIn($("ifood-lista"), e); }
  },

  loja() {
    const r = (loaders._cardapio.restaurantes || []).find((x) => x.id === loaders._loja);
    if (!r) return back();
    $("loja-nome").textContent = r.nome;
    $("loja-sub").textContent = `${r.tipo} · ${r.eta[0]}–${r.eta[1]} min`;
    $("loja-resumo").hidden = true; $("loja-err").textContent = ""; $("loja-obs").value = "";
    $("loja-itens").innerHTML = r.itens.map((i) => `<button class="item" data-produto="${esc(i.id)}">
      <div><div class="t">${esc(i.curto)}</div><div class="d">${esc(cap(i.nome))}</div></div><div>${brl(i.preco)}</div></button>`).join("");
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
  const loja = e.target.closest("[data-loja]");
  if (loja) { loaders._loja = loja.dataset.loja; show("loja"); return; }
  const prod = e.target.closest("[data-produto]");
  if (prod) {
    const r = loaders._cardapio.restaurantes.find((x) => x.id === loaders._loja);
    const i = r.itens.find((x) => x.id === prod.dataset.produto);
    loaders._produto = i;
    document.querySelectorAll("[data-produto]").forEach((b) => b.classList.toggle("sel", b === prod));
    $("res-item").textContent = `1x ${i.curto}`;
    $("res-preco").textContent = brl(i.preco);
    $("res-total").textContent = brl(i.preco);
    $("loja-resumo").hidden = false;
    $("loja-resumo").scrollIntoView({ behavior: "smooth" });
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

$("loja-pedir").addEventListener("click", async () => {
  const i = loaders._produto; if (!i) return;
  $("loja-err").textContent = "";
  const btn = $("loja-pedir"); btn.disabled = true;
  try {
    await api("/api/delivery", { restaurante: loaders._loja, item: i.id, bilhete: $("loja-obs").value });
    concluido("Pedido feito");
    stack.length = 1; show("inicio", false);
  } catch (err) { $("loja-err").textContent = err.message; }
  finally { btn.disabled = false; }
});

show("inicio", false);
