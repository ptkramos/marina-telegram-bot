"use strict";
// Lovense da Ma (05/10, passo 2 do PLANO_WEBAPP, "Lovense pelo Mini App — plano"). Decidido com o Patrick (04/10):
// igual ao Lovense Remote — Clássico (barra vertical 0–20, uma por brinquedo), Toque (arrasta o dedo; soltou, para)
// e Padrões; o Parar embaixo. O estado vem do servidor a cada 3 s; o comando sai ao soltar e no máximo 1 por
// segundo arrastando. Usa $, api, esc, ic, stack, tg, tgAt e toast do app.js.

const LV = {
  d: null, modo: "classico", alvos: null, forca: 12,
  local: {},            // nível que ele está mexendo agora, por brinquedo (o servidor não volta atrás disso)
  mexendo: 0,           // última mexida (ms): enquanto mexe, a recarga não redesenha por cima
  fila: new Map(), ultimo: 0, timer: null, poll: null,
  NIVEL_MAX: 20,

  tile(lv) {
    const on = !!(lv && lv.conectada);
    $("lv-tile").classList.toggle("apagado", !on);
    $("lv-tile-sub").textContent = on ? "Marina conectada" : "Marina desconectada";
  },

  bateria(p) {
    const n = p > 75 ? 4 : p > 50 ? 3 : p > 25 ? 2 : p > 5 ? 1 : 0;
    return `<span class="lv-bat${p <= 15 ? " fraca" : ""}">${ic(n ? "battery-" + n : "battery")}${p}%</span>`;
  },

  nivel(b) { return b.id in LV.local ? LV.local[b.id] : b.nivel; },
  alvosAtivos() {
    const ids = (LV.d ? LV.d.brinquedos : []).map((b) => b.id);
    if (!LV.alvos) LV.alvos = new Set(ids);
    const ok = ids.filter((i) => LV.alvos.has(i));
    return ok.length ? ok : ids;
  },

  // ------------------------------------------------------------------ desenho --
  desenha() {
    if (!LV.d) return;
    if (LV.desenhaTopo()) LV[LV.modo]();
  },
  // o topo (status, aviso, brinquedos com a bateria); devolve se há painel pra desenhar
  desenhaTopo() {
    const d = LV.d;
    $("lv-status").innerHTML = d.conectada
      ? `<span class="lv-ponto"></span>Conectada${d.desde ? ` desde ${esc(d.desde)}` : ""}` : "Desconectada";
    const on = d.conectada && d.brinquedos.length;
    // a faixa é só da palavra; o corte aparece no meio, no lugar do "desconectada" (Patrick, 05/10)
    $("lv-aviso").hidden = !(on && d.aviso);
    $("lv-aviso").innerHTML = on && d.aviso ? `${ic("hand-stop")}<span>${esc(d.aviso)}</span>` : "";
    $("lv-rodape").hidden = !on;
    $("lv-nav").hidden = !on || stack[stack.length - 1] !== "lovense";
    document.querySelectorAll("[data-lvmodo]").forEach((b) => b.classList.toggle("on", b.dataset.lvmodo === LV.modo));
    if (!on) {
      $("lv-brinqs").innerHTML = "";
      const cortou = d.aviso_tipo === "cortou";
      $("lv-painel").innerHTML = `<div class="lv-vazio${cortou ? " cortou" : ""}">${ic(cortou ? "plug-connected-x" : "wave-sine")}
        <div class="t">${esc(cortou ? d.aviso : d.titulo)}</div></div>`;
      return false;
    }
    const escolhe = LV.modo !== "classico" && d.brinquedos.length > 1;
    const alvos = LV.alvosAtivos();
    $("lv-brinqs").innerHTML = d.brinquedos.map((b) => `<button class="lv-brinq${escolhe && alvos.includes(b.id) ? " on" : ""}"
        data-lvbrinq="${esc(b.id)}"${escolhe ? "" : " disabled"}>
      <span class="lv-bn">${escolhe ? ic(alvos.includes(b.id) ? "circle-check-filled" : "circle") : ""}${esc(b.nome)}</span>
      ${LV.bateria(b.bateria)}</button>`).join("");
    return true;
  },

  classico() {
    const bs = LV.d.brinquedos;
    $("lv-painel").innerHTML = `<div class="lv-barras${bs.length > 1 ? " duas" : ""}">${bs.map((b) => {
      const n = LV.nivel(b);
      return `<div class="lv-col"><div class="lv-num" data-lvnum="${esc(b.id)}">${n}</div>
        <div class="lv-trilho" data-lvtrilho="${esc(b.id)}"><i style="height:${n / LV.NIVEL_MAX * 100}%"></i></div>
        ${bs.length > 1 ? `<div class="lv-nome">${esc(b.nome)}</div>` : ""}</div>`;
    }).join("")}</div>`;
    $("lv-painel").querySelectorAll("[data-lvtrilho]").forEach((el) => LV.arrasta(el, (y, r) => {
      const id = el.dataset.lvtrilho;
      const n = Math.round(Math.max(0, Math.min(1, (r.bottom - y) / r.height)) * LV.NIVEL_MAX);
      el.firstElementChild.style.height = (n / LV.NIVEL_MAX * 100) + "%";
      $("lv-painel").querySelector(`[data-lvnum="${id}"]`).textContent = n;
      LV.muda(id, n, { brinquedos: [id], nivel: n, modo: "classico" });
    }, () => LV.solta()));
  },

  toque() {
    const n = Math.max(0, ...LV.alvosAtivos().map((id) => LV.nivel(LV.d.brinquedos.find((b) => b.id === id))));
    $("lv-painel").innerHTML = `<div class="lv-num toque" id="lv-toque-num">${n}</div>
      <div class="lv-pad" id="lv-pad"><span class="lv-dedo" id="lv-dedo" hidden></span></div>`;
    const pad = $("lv-pad"), dedo = $("lv-dedo");
    LV.arrasta(pad, (y, r, x) => {
      const n = Math.round(Math.max(0, Math.min(1, (r.bottom - y) / r.height)) * LV.NIVEL_MAX);
      dedo.hidden = false;
      dedo.style.left = Math.max(0, Math.min(r.width, x - r.left)) + "px";
      dedo.style.top = Math.max(0, Math.min(r.height, y - r.top)) + "px";
      $("lv-toque-num").textContent = n;
      LV.alvosAtivos().forEach((id) => LV.muda(id, n, null));
      LV.manda("toque", { brinquedos: LV.alvosAtivos(), nivel: n, modo: "toque" });
    }, () => {
      // soltou, para (como no app real)
      dedo.hidden = true;
      $("lv-toque-num").textContent = 0;
      LV.alvosAtivos().forEach((id) => (LV.local[id] = 0));
      LV.manda("toque", { brinquedos: LV.alvosAtivos(), nivel: 0, modo: "toque" });
      LV.solta();
    });
  },

  ONDAS: {   // desenho de cada padrão (100 × 30)
    pulso: "M0 25 H10 V5 H20 V25 H35 V5 H45 V25 H60 V5 H70 V25 H85 V5 H95 V25 H100",
    onda: "M0 15 C8 0 17 0 25 15 S42 30 50 15 S67 0 75 15 S92 30 100 15",
    fogos: "M0 25 L8 22 L12 4 L16 24 L30 20 L34 10 L38 25 L52 23 L56 2 L60 25 L74 21 L78 8 L82 25 L100 24",
    terremoto: "M0 15 L4 3 L8 27 L12 5 L16 25 L20 2 L24 28 L28 6 L32 24 L36 3 L40 27 L44 5 L48 25 L52 2 L56 28 L60 6 L64 24 L68 3 L72 27 L76 5 L80 25 L84 2 L88 28 L92 6 L96 24 L100 15",
  },
  tocando() {
    const b = LV.d.brinquedos.find((x) => LV.alvosAtivos().includes(x.id) && x.modo === "padrao" && LV.nivel(x) > 0);
    return b ? b.padrao : null;
  },
  padrao() {
    const ativo = LV.tocando();
    $("lv-painel").innerHTML = `<div class="lv-padroes">${LV.d.padroes.map((p) => `<button class="lv-pd${p.id === ativo ? " on" : ""}" data-lvpadrao="${esc(p.id)}">
        <svg viewBox="0 0 100 30" preserveAspectRatio="none"><path d="${LV.ONDAS[p.id]}"/></svg><span>${esc(p.nome)}</span></button>`).join("")}</div>
      <div class="lv-forca"><span class="d">Intensidade</span><input type="range" min="1" max="${LV.NIVEL_MAX}" value="${LV.forca}" id="lv-forca"><b id="lv-forca-n">${LV.forca}</b></div>`;
    const r = $("lv-forca");
    r.addEventListener("input", () => {
      LV.forca = Number(r.value);
      $("lv-forca-n").textContent = LV.forca;
      LV.mexendo = Date.now();
      const p = LV.tocando();
      if (p) LV.manda("padrao", { brinquedos: LV.alvosAtivos(), nivel: LV.forca, modo: "padrao", padrao: p });
    });
    r.addEventListener("change", () => LV.solta());
  },

  // ------------------------------------------------------------------ gestos --
  arrasta(el, mexe, solta) {
    let ativo = false;
    el.addEventListener("pointerdown", (e) => {
      ativo = true; el.setPointerCapture(e.pointerId); e.preventDefault();
      mexe(e.clientY, el.getBoundingClientRect(), e.clientX);
    });
    el.addEventListener("pointermove", (e) => { if (ativo) mexe(e.clientY, el.getBoundingClientRect(), e.clientX); });
    const fim = () => { if (ativo) { ativo = false; solta(); } };
    el.addEventListener("pointerup", fim);
    el.addEventListener("pointercancel", fim);
  },

  muda(id, n, cmd) {
    if (LV.local[id] !== n && tgAt("6.1")) tg.HapticFeedback.selectionChanged();
    LV.local[id] = n;
    LV.mexendo = Date.now();
    if (cmd) LV.manda(id, cmd);
  },

  // ------------------------------------------------------------------ envio --
  // no máximo 1 comando por segundo enquanto arrasta; ao soltar, o último sai na hora
  manda(chave, cmd) {
    LV.fila.set(chave, cmd);
    const falta = 1000 - (Date.now() - LV.ultimo);
    if (falta <= 0) LV.esvazia();
    else if (!LV.timer) LV.timer = setTimeout(LV.esvazia, falta);
  },
  solta() { LV.esvazia(); },
  async esvazia() {
    clearTimeout(LV.timer); LV.timer = null;
    if (!LV.fila.size) return;
    const cmds = [...LV.fila.values()];
    LV.fila.clear();
    LV.ultimo = Date.now();
    for (const cmd of cmds) await LV.envia(cmd);
  },
  async envia(cmd) {
    try {
      const d = await api("/api/lovense/comando", cmd);
      LV.recebe(d);
    } catch (err) {
      toast(err.message);
      LV.local = {};
      LV.carrega();
    }
  },

  // o que ele está mexendo vale até parar de mexer: enquanto isso só o topo (aviso, bateria) se atualiza,
  // sem refazer o painel debaixo do dedo
  recebe(d) {
    const tinha = LV.d && LV.d.conectada && LV.d.brinquedos.map((b) => b.id).join();
    LV.d = d;
    const mudou = tinha !== (d.conectada && d.brinquedos.map((b) => b.id).join());
    if (!mudou && Date.now() - LV.mexendo < 1500) { LV.desenhaTopo(); return; }
    LV.local = {};
    LV.desenha();
  },

  async carrega() {
    try { LV.recebe(await api("/api/lovense")); } catch (err) { failIn($("lv-painel"), err); }
  },
};

Object.assign(loaders, {
  lovense() {
    LV.carrega();
    clearInterval(LV.poll);
    LV.poll = setInterval(() => {
      if (stack[stack.length - 1] !== "lovense") { clearInterval(LV.poll); LV.poll = null; return; }
      if (!document.hidden) LV.carrega();
    }, 3000);
  },
});

document.addEventListener("click", (e) => {
  const m = e.target.closest("[data-lvmodo]");
  if (m) { LV.modo = m.dataset.lvmodo; LV.local = {}; LV.desenha(); window.scrollTo(0, 0); return; }
  const b = e.target.closest("[data-lvbrinq]");
  if (b && !b.disabled) {
    const id = b.dataset.lvbrinq, s = LV.alvos || new Set();
    // pelo menos um sempre marcado
    if (s.has(id) && LV.alvosAtivos().length > 1) s.delete(id); else s.add(id);
    LV.alvos = s; LV.desenha(); return;
  }
  const p = e.target.closest("[data-lvpadrao]");
  if (p) {
    const igual = LV.tocando() === p.dataset.lvpadrao;
    LV.alvosAtivos().forEach((id) => (LV.local[id] = igual ? 0 : LV.forca));
    LV.mexendo = 0;
    LV.envia(igual ? { brinquedos: LV.alvosAtivos(), nivel: 0, modo: "classico" }
      : { brinquedos: LV.alvosAtivos(), nivel: LV.forca, modo: "padrao", padrao: p.dataset.lvpadrao });
    return;
  }
});

$("lv-parar").addEventListener("click", () => {
  if (tgAt("6.1")) tg.HapticFeedback.impactOccurred("medium");
  LV.fila.clear(); clearTimeout(LV.timer); LV.timer = null;
  LV.local = {}; LV.mexendo = 0;
  LV.envia({ acao: "parar" });
});
