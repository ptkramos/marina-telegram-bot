"use strict";
// Mini App da Marina (25/09). Sem framework: 5 telas, a API valida o initData do Telegram.
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.ready(); tg.expand(); }
// Telegram antigo (ou fora dele) não tem BackButton (6.1) nem showConfirm (6.2): cai no da página.
const tgAt = (v) => !!(tg && tg.isVersionAtLeast && tg.isVersionAtLeast(v));
const nativeBack = tgAt("6.1");

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const brl = (v) => "R$ " + Math.round(v).toLocaleString("pt-BR");
const pct = (v) => Math.max(0, Math.min(100, Math.round((v || 0) * 100)));
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");

async function api(path, body) {
  const opts = { headers: { "X-Telegram-Init-Data": tg ? tg.initData : "" } };
  if (body) { opts.method = "POST"; opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.erro || (r.status === 403 ? "Abra pelo botão do chat da Marina." : "Não deu certo agora."));
  return data;
}

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 2600);
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
document.addEventListener("click", (e) => {
  const go = e.target.closest("[data-go]");
  if (go) show(go.dataset.go);
});

function pedidoCard(p) {
  if (!p) return "";
  return `<div class="pedido"><div class="t">${esc(cap(p.what))}</div>
    <div class="small">${esc(p.restaurant)} · ${brl(p.price)}</div>
    <div class="small">${esc(p.detalhe)}</div>${p.note ? `<div class="small muted">Bilhete: "${esc(p.note)}"</div>` : ""}</div>`;
}

function failIn(el, err) { el.innerHTML = `<p class="err">${esc(err.message)}</p>`; }

// --------------------------------------------------------------------- telas --
const loaders = {
  async inicio() {
    try {
      const d = await api("/api/inicio");
      const a = d.agora;
      $("inicio-sub").textContent = `${a.local} · ${new Date(a.now).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
      $("inicio-agora").textContent = a.atividade.charAt(0).toUpperCase() + a.atividade.slice(1);
      $("inicio-disp").textContent = a.disponivel;
      $("inicio-pedido").innerHTML = pedidoCard(d.pedido);
      const pv = d.pra_voce;
      $("inicio-pra-voce").innerHTML = pv ? `<div class="pedido dela">
        <div class="small muted">${pv.surprise ? "Surpresa da Marina 🤍" : "A Marina te mandou"}</div>
        <div class="t">${esc(cap(pv.what))}</div><div class="small">${esc(pv.restaurant)}</div>
        <div class="small">${pv.status === "entregue" ? "✅ " : "🛵 "}${esc(pv.detalhe)}</div>
        ${pv.note ? `<div class="small muted">"${esc(pv.note)}"</div>` : ""}</div>` : "";
    } catch (e) { failIn($("inicio-agora"), e); }
  },

  async banco() {
    try {
      const d = await api("/api/banco");
      $("banco-saldo").textContent = brl(d.saldo);
      let tags = "";
      if (d.devendo) tags += `<span class="tag">Ela te deve ${brl(d.devendo)}</span>`;
      if (d.pedido) tags += `<span class="tag">Precisando de ${brl(d.pedido.valor)}: ${esc(d.pedido.motivo)}</span>`;
      $("banco-tags").innerHTML = tags;
      $("banco-movs").innerHTML = d.movs.length ? d.movs.map((m) => {
        const dt = new Date(m.at);
        const when = dt.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + " " +
          dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
        const cls = m.valor >= 0 ? "plus" : "minus";
        return `<div class="item"><div><div class="t">${esc(cap(m.desc))}</div><div class="d">${when}</div></div>
          <div class="${cls}">${m.valor >= 0 ? "+" : "−"}${Math.abs(m.valor)}</div></div>`;
      }).join("") : `<p class="muted">Sem movimentos ainda.</p>`;
    } catch (e) { failIn($("banco-movs"), e); }
  },

  async delivery() {
    try {
      const d = await api("/api/delivery");
      loaders._cardapio = d.cardapio;
      $("delivery-pedido").innerHTML = pedidoCard(d.pedido);
      $("delivery-lista").innerHTML = d.cardapio.restaurantes.map((r) => {
        const precos = r.itens.map((i) => i.preco);
        return `<button class="item" data-rest="${esc(r.id)}"><div><div class="t">${esc(r.nome)}</div>
          <div class="d">${esc(r.tipo)} · ${r.eta[0]}–${r.eta[1]} min · a partir de ${brl(Math.min(...precos))}</div></div><span class="muted">›</span></button>`;
      }).join("");
    } catch (e) { failIn($("delivery-lista"), e); }
  },

  item() {
    const r = (loaders._cardapio.restaurantes || []).find((x) => x.id === loaders._rest);
    if (!r) return back();
    $("item-rest").textContent = r.nome;
    $("item-sub").textContent = `${r.tipo} · ${r.eta[0]}–${r.eta[1]} min`;
    $("item-form").hidden = true; $("item-err").textContent = ""; $("item-bilhete").value = "";
    $("item-lista").innerHTML = r.itens.map((i) => `<button class="item" data-item="${esc(i.id)}">
      <div><div class="t">${esc(i.curto)}</div><div class="d">${esc(i.nome)}</div></div><div>${brl(i.preco)}</div></button>`).join("");
  },

  async bastidores() {
    try {
      const d = await api("/api/bastidores");
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
      $("bast-humor").innerHTML = `<div class="big">${esc(e.mood.charAt(0).toUpperCase() + e.mood.slice(1))}</div>` +
        e.mood_bars.map((b) => bar(b.label, b.value)).join("");
      $("bast-sentindo").innerHTML = e.feelings.length ? e.feelings.map((f) => `<div class="feel">
        <div class="head"><span>${esc(f.word)}${f.target ? " com " + esc(f.target) : ""}${f.count > 1 ? ` <span class="muted small">· ${f.count} momentos</span>` : ""}</span>
        <div class="bar"><i style="width:${pct(f.value)}%"></i></div></div>
        <div class="why">${esc(f.cause)}${f.until_resolved ? " (até resolver)" : ""}</div></div>`).join("")
        : `<p class="muted">Nada marcante agora.</p>`;
      $("bast-vinculo").innerHTML = e.bond.map((b) => bar(b.label, b.value, null, b.label === "Desejo")).join("");
      $("bast-hoje").innerHTML = d.hoje.length ? d.hoje.map((h) => `<div class="item"><span class="d">${esc(h.at)}</span>
        <span style="flex:1">${esc(h.texto)}</span></div>`).join("") : `<p class="muted">Nada registrado hoje ainda.</p>`;
      $("bast-mundo").textContent = d.mundo || "";
    } catch (err) { failIn($("bast-status"), err); }
  },
};

// ------------------------------------------------------------------- ações --
document.addEventListener("click", (e) => {
  const rest = e.target.closest("[data-rest]");
  if (rest) { loaders._rest = rest.dataset.rest; show("item"); return; }
  const it = e.target.closest("[data-item]");
  if (it) {
    const r = loaders._cardapio.restaurantes.find((x) => x.id === loaders._rest);
    const i = r.itens.find((x) => x.id === it.dataset.item);
    loaders._item = i;
    $("item-escolhido").textContent = `${i.curto} · ${brl(i.preco)}`;
    $("item-form").hidden = false;
    $("item-form").scrollIntoView({ behavior: "smooth" });
  }
});

function confirmar(msg) {
  return new Promise((ok) => (tgAt("6.2") ? tg.showConfirm(msg, ok) : ok(window.confirm(msg))));
}

$("item-pedir").addEventListener("click", async () => {
  const i = loaders._item; if (!i) return;
  $("item-err").textContent = "";
  if (!(await confirmar(`Pedir ${i.curto} (${brl(i.preco)}) pra Marina?`))) return;
  const btn = $("item-pedir"); btn.disabled = true;
  try {
    await api("/api/delivery", { restaurante: loaders._rest, item: i.id, bilhete: $("item-bilhete").value });
    if (tgAt("6.1")) tg.HapticFeedback.notificationOccurred("success");
    toast("Pedido feito. Ela não sabe de nada 🤫");
    stack.pop(); show("delivery", false);
  } catch (err) { $("item-err").textContent = err.message; }
  finally { btn.disabled = false; }
});

$("pix-valor").addEventListener("input", () => ($("pix-err").textContent = ""));
$("pix-enviar").addEventListener("click", async () => {
  const valor = Math.round(Number($("pix-valor").value));
  if (!valor || valor < 1 || valor > 5000) { $("pix-err").textContent = "Coloque um valor entre R$ 1 e R$ 5.000"; return; }
  if (!(await confirmar(`Mandar ${brl(valor)} de pix pra Marina?`))) return;
  const btn = $("pix-enviar"); btn.disabled = true;
  try {
    await api("/api/pix", { valor, recado: $("pix-recado").value });
    if (tgAt("6.1")) tg.HapticFeedback.notificationOccurred("success");
    $("pix-valor").value = ""; $("pix-recado").value = "";
    toast("Pix enviado. Ela vai ver no chat");
    loaders.banco();
  } catch (err) { $("pix-err").textContent = err.message; }
  finally { btn.disabled = false; }
});

show("inicio", false);
