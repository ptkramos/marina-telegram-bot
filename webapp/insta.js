"use strict";
// Instagram da Ma (27/09, Etapa 5 do PLANO_WEBAPP). Decidido com o Patrick: abre no feed (stories no topo, posts
// dela e das amigas por hora), perfil @masalles, post com comentários; ele curte, comenta, responde e reage aos
// stories (a resposta ao story vai pro chat como mensagem dele). Usa $, api, esc, ic, show, stack e toast do app.js.

if (tg && tg.colorScheme === "dark") document.body.classList.add("tg-escuro");   // o logo escrito é preto

const IG = {
  perfilDoNivel: {}, postDoNivel: {}, navPerfil: false, pai: null, post: null,
  story: { grupos: [], g: 0, i: 0, t: null },

  av(a, cls = "") {
    return a.avatar ? `<img class="ig-av ${cls}" src="${esc(a.avatar)}" alt="">`
      : `<span class="ig-av ${cls}">${esc(a.iniciais || "")}</span>`;
  },
  // @handle no texto vira link (perfil conhecido) ou só destaque
  texto(t) {
    return esc(t).replace(/@([\w.]+)/g, (m, h) => {
      const k = IG.chaves[h];
      return k ? `<button class="ig-men" data-igperfil="${k}">@${h}</button>` : `<span class="ig-men">@${h}</span>`;
    });
  },
  chaves: { "masalles": "marina", "bia.andrade": "bia_andrade", "carolmenezes": "carol_menezes",
    "juazevedo": "julia_azevedo", "theomartins": "theo_martins" },
  n(v) { return Number(v).toLocaleString("pt-BR"); },
  mil(v) { return v >= 10000 ? (v / 1000).toFixed(1).replace(".", ",").replace(",0", "") + " mil" : IG.n(v); },
  coracao(on) { return on ? ic("heart-filled", "ig-vermelho") : ic("heart"); },

  card(p) {
    const marcas = p.marcados.length ? `<button class="ig-marcas" data-igmarcas="${p.id}" aria-label="Marcados">${ic("user")}</button>
      <div class="ig-marcas-lista" id="igm-${p.id}" hidden>${p.marcados.map((m) =>
        `<button class="ig-marca" data-igperfil="${esc(m.chave)}">${esc(m.handle)}</button>`).join("")}</div>` : "";
    return `<article class="igp">
      <header class="igp-top"><button class="igp-quem" data-igperfil="${esc(p.autor.chave)}">${IG.av(p.autor, "md")}
        <span><b>${esc(p.autor.handle)}</b>${p.local ? `<span class="igp-local">${esc(p.local)}</span>` : ""}</span></button>
        ${ic("dots")}</header>
      <div class="igp-foto" data-igduplo="${p.id}"><img src="${esc(p.imagem)}" alt="" loading="lazy">${marcas}</div>
      <div class="igp-acoes"><button data-igcurtir="${p.id}" class="${p.curtiu ? "on" : ""}" aria-label="Curtir">${IG.coracao(p.curtiu)}</button>
        <button data-igpost="${p.id}" aria-label="Comentar">${ic("message-circle")}</button>
        <span class="ig-ic">${ic("send")}</span><span class="ig-flex"></span><span class="ig-ic">${ic("bookmark")}</span></div>
      <div class="igp-curtidas" id="igc-${p.id}">${p.curtido_por ? `Curtido por <b>${esc(p.curtido_por)}</b> e outras pessoas`
        : `<b>${IG.n(p.curtidas)} curtidas</b>`}</div>
      ${p.legenda ? `<div class="igp-leg"><b>${esc(p.autor.handle)}</b> ${IG.texto(p.legenda)}</div>` : ""}
      ${p.n_comentarios ? `<button class="igp-ver" data-igpost="${p.id}">Ver ${p.n_comentarios > 1 ? `todos os ${p.n_comentarios} comentários` : "1 comentário"}</button>` : ""}
      <div class="igp-quando">${esc(p.quando)}</div></article>`;
  },

  comentario(c, resposta = false) {
    return `<div class="igc${resposta ? " resp" : ""}">${c.autor.perfil ? `<button data-igperfil="${esc(c.autor.chave)}">${IG.av(c.autor, "pq")}</button>` : IG.av(c.autor, "pq")}
      <div class="igc-corpo"><div class="igc-linha"><b>${esc(c.autor.handle)}</b><span class="igc-q">${esc(c.quando)}</span></div>
        <div class="igc-txt">${IG.texto(c.texto)}</div>
        <div class="igc-acoes">${c.curtidas ? `<span>${c.curtidas} ${c.curtidas > 1 ? "curtidas" : "curtida"}</span>` : ""}
          <button data-igresponder="${c.id}" data-handle="${esc(c.autor.handle)}">Responder</button>
          ${c.dela && IG.post && IG.post.autor.chave === "marina" ? `<span class="igc-autora">${ic("heart-filled", "ig-vermelho")} pela autora</span>` : ""}</div></div>
      <button class="igc-cor" data-igccurtir="${c.id}" aria-label="Curtir comentário">${IG.coracao(c.curtiu)}</button></div>
      ${c.respostas.map((r) => IG.comentario(r, true)).join("")}`;
  },

  aneis(grupos) {
    return grupos.map((g, n) => `<button class="ig-anel-b" data-igstory="${n}">
      <span class="ig-anel${g.visto ? " visto" : ""}">${IG.av(g.autor, "gd")}</span><span class="ig-anel-n">${esc(g.autor.handle)}</span></button>`).join("");
  },

  // ------------------------------------------------------------ stories --
  abrirStory(grupos, g) {
    IG.story = { grupos, g, i: 0, t: null };
    $("igs").hidden = false;
    document.body.classList.add("sem-rolar");
    IG.mostraStory();
  },
  fecharStory() {
    clearTimeout(IG.story.t);
    $("igs").hidden = true;
    document.body.classList.remove("sem-rolar");
    const v = stack[stack.length - 1];
    if (v === "ig" || v === "igperfil") loaders[v]();
  },
  mostraStory() {
    const S = IG.story, grupo = S.grupos[S.g];
    if (!grupo) return IG.fecharStory();
    const s = grupo.itens[S.i];
    clearTimeout(S.t);
    $("igs-barras").innerHTML = grupo.itens.map((x, n) => `<span class="igs-barra"><i class="${n < S.i ? "cheia" : n === S.i ? "anda" : ""}"></i></span>`).join("");
    $("igs-quem").innerHTML = `${IG.av(grupo.autor, "pq")}<b>${esc(grupo.autor.handle)}</b><span>${esc(s.quando)}</span>`;
    const st = s.story || {};
    let meio;
    if (st.tipo === "musica") {
      meio = `${st.capa ? `<img class="igs-blur" src="${esc(st.capa)}" alt="">` : ""}<div class="igs-musica">${st.capa ? `<img src="${esc(st.capa)}" alt="">` : `<div class="igs-capa-vazia">${ic("music")}</div>`}
        <div class="igs-faixa"><b>${esc(st.nome)}</b><span>${esc(st.artista)}</span></div></div>`;
    } else if (st.tipo === "texto") {
      meio = `<div class="igs-texto" style="background:${esc(st.fundo || "#262626")}"><span>${esc(s.legenda)}</span></div>`;
    } else {
      meio = `<img class="igs-foto" src="${esc(s.imagem)}" alt="">`;
    }
    const legenda = st.tipo !== "texto" && s.legenda ? `<div class="igs-legenda">${esc(s.legenda)}</div>` : "";
    $("igs-conteudo").innerHTML = meio + legenda;
    const dela = grupo.autor.chave === "marina";
    $("igs-rodape").hidden = !dela;
    $("igs-cor").innerHTML = IG.coracao(s.curtiu);
    $("igs-cor").classList.toggle("on", !!s.curtiu);
    $("igs-msg").value = "";
    if (!s.visto) { s.visto = true; api("/api/ig/story", { id: s.id, acao: "visto" }).catch(() => {}); }
    S.t = setTimeout(() => IG.proxStory(), 6000);
  },
  proxStory() {
    const S = IG.story;
    if (S.i < S.grupos[S.g].itens.length - 1) S.i += 1;
    else { S.g += 1; S.i = 0; }
    if (S.g >= S.grupos.length) return IG.fecharStory();
    IG.mostraStory();
  },
  antStory() {
    const S = IG.story;
    if (S.i > 0) S.i -= 1;
    else if (S.g > 0) { S.g -= 1; S.i = S.grupos[S.g].itens.length - 1; }
    IG.mostraStory();
  },
};

// ---------------------------------------------------------------- telas --
Object.assign(loaders, {
  async ig() {
    try {
      const d = await api("/api/ig");
      IG.feed = d;
      $("ig-stories").innerHTML = IG.aneis(d.stories);
      $("ig-stories").hidden = !d.stories.length;
      $("ig-feed").innerHTML = d.posts.map((p) => IG.card(p)).join("")
        || `<div class="vazio">${ic("camera")}<div class="t">Nada postado ainda</div><div class="d">Os posts da Ma e das amigas aparecem aqui.</div></div>`;
      $("ig-ativ-bolinha").hidden = !d.atividade_nova;
      $("ig-bolinha").hidden = true;
      IG.navAvatar();
    } catch (e) { failIn($("ig-feed"), e); }
  },

  async igperfil() {
    const nivel = stack.length - 1;
    if (IG.navPerfil) { IG.perfilDoNivel[nivel] = "marina"; IG.navPerfil = false; }
    const autor = IG.perfilDoNivel[nivel] || "marina";
    const carga = (IG.cargaPerfil = (IG.cargaPerfil || 0) + 1);
    try {
      const d = await api("/api/ig/perfil/" + encodeURIComponent(autor));
      if (carga !== IG.cargaPerfil) return;          // outra carga começou depois: vale a última
      IG.perfil = d;
      const a = d.autor;
      const temStory = d.stories.length > 0;
      const grade = (ps) => ps.length ? `<div class="igpf-grade">${ps.map((p) =>
        `<button class="igpf-tile" data-igpost="${p.id}" style="background-image:url('${esc(p.imagem)}')"></button>`).join("")}</div>`
        : `<div class="vazio">${ic("camera")}<div class="t">Nenhuma publicação ainda</div></div>`;
      $("ig-perfil").innerHTML = `<header class="ig-top igpf-handle"><b>${esc(a.handle)}</b></header>
        <div class="igpf-cab">${temStory ? `<button class="ig-anel${d.stories[0].visto ? " visto" : ""}" data-igstoryperfil="1">${IG.av(a, "xl")}</button>` : IG.av(a, "xl")}
          <div class="igpf-nums"><div><b>${IG.n(d.n_posts)}</b><span>posts</span></div>
            <div><b>${IG.mil(d.seguidores)}</b><span>seguidores</span></div><div><b>${IG.mil(d.seguindo)}</b><span>seguindo</span></div></div></div>
        <div class="igpf-bio"><b>${esc(a.nome)}</b>${d.bio.map((l) => `<div>${IG.texto(l)}</div>`).join("")}</div>
        <div class="igpf-botoes"><button class="ig-btn">Seguindo ${ic("chevron-down")}</button>
          ${a.chave === "marina" ? `<button class="ig-btn" id="igpf-msg">Mensagem</button>` : ""}</div>
        <div class="igpf-abas"><button class="on" data-igaba="posts" aria-label="Publicações">${ic("grid-dots")}</button>
          <button data-igaba="marcadas" aria-label="Marcações">${ic("user-square")}</button></div>
        <div id="igpf-posts">${grade(d.posts)}</div><div id="igpf-marcadas" hidden>${grade(d.marcadas)}</div>`;
      const msg = $("igpf-msg");
      if (msg) msg.addEventListener("click", () => (insideTelegram ? tg.close() : toast("A conversa com ela é o chat")));
      IG.navAvatar();
    } catch (e) { failIn($("ig-perfil"), e); }
  },

  async igpost() {
    const id = IG.postDoNivel[stack.length - 1];
    const carga = (IG.cargaPost = (IG.cargaPost || 0) + 1);
    try {
      const d = await api("/api/ig/post/" + id);
      if (carga !== IG.cargaPost) return;
      IG.post = d;
      $("ig-post").innerHTML = IG.card(d).replace(/<button class="igp-ver"[^>]*>.*?<\/button>/, "")
        + `<div class="igc-lista">${d.comentarios.map((c) => IG.comentario(c)).join("")
        || `<p class="muted igc-vazio">Ainda não há comentários.</p>`}</div>`;
      $("ig-coment").placeholder = `Adicione um comentário para ${d.autor.handle}…`;
      IG.responder(null);
    } catch (e) { failIn($("ig-post"), e); }
  },

  async igativ() {
    try {
      const d = await api("/api/ig/atividade");
      $("ig-ativ").innerHTML = d.itens.map((x) => `<button class="iga${x.nova ? " nova" : ""}" data-igpost="${x.post}">${IG.av(x.autor, "md")}
        <span class="iga-txt"><b>${esc(x.autor.handle)}</b> ${IG.texto(x.texto)} <span class="iga-q">${esc(x.quando)}</span></span></button>`).join("")
        || `<div class="vazio">${ic("heart")}<div class="t">Atividade nos seus comentários</div><div class="d">Quando responderem ou curtirem o que você comentou, aparece aqui.</div></div>`;
      $("ig-ativ-bolinha").hidden = true;
    } catch (e) { failIn($("ig-ativ"), e); }
  },
});

IG.navAvatar = () => {
  const src = "/ig/avatar_marina.jpg";
  const el = $("ig-nav-av");
  if (!el.dataset.ok) {
    el.outerHTML = `<img class="ig-av pq" id="ig-nav-av" data-ok="1" src="${src}" alt="" onerror="this.outerHTML='<span class=&quot;ig-av pq&quot; id=&quot;ig-nav-av&quot; data-ok=&quot;1&quot;>MS</span>'">`;
  }
};

IG.responder = (c) => {
  IG.pai = c ? Number(c.id) : null;
  $("ig-respondendo").hidden = !c;
  if (c) {
    $("ig-resp-txt").textContent = `Respondendo a ${c.handle}`;
    $("ig-coment").value = `@${c.handle} `;
    $("ig-coment").focus();
  }
};

async function igCurtirPost(id, forcaOn) {
  const acha = (lista) => (lista || []).find((p) => p.id === id);
  const p = (IG.post && IG.post.id === id && IG.post) || acha(IG.feed && IG.feed.posts) || acha(IG.perfil && IG.perfil.posts) || { id, curtiu: false, curtidas: 0 };
  const on = forcaOn === undefined ? !p.curtiu : forcaOn;
  if (on === p.curtiu) return;
  p.curtiu = on; p.curtidas += on ? 1 : -1;
  document.querySelectorAll(`[data-igcurtir="${id}"]`).forEach((b) => { b.classList.toggle("on", on); b.innerHTML = IG.coracao(on); });
  document.querySelectorAll(`#igc-${id}`).forEach((el) => { if (!p.curtido_por) el.innerHTML = `<b>${IG.n(p.curtidas)} curtidas</b>`; });
  if (on && tgAt("6.1")) tg.HapticFeedback.impactOccurred("light");
  try { await api("/api/ig/curtir", { post: id, on }); } catch (e) { toast(e.message); }
}

// ---------------------------------------------------------------- ações --
document.addEventListener("click", async (e) => {
  const perfil = e.target.closest("[data-igperfil]");
  if (perfil) {
    if (!$("igs").hidden) IG.fecharStory();
    IG.perfilDoNivel[stack.length] = perfil.dataset.igperfil;
    show("igperfil");
    return;
  }
  const post = e.target.closest("[data-igpost]");
  if (post) { IG.postDoNivel[stack.length] = Number(post.dataset.igpost); show("igpost"); return; }
  const cur = e.target.closest("[data-igcurtir]");
  if (cur) { igCurtirPost(Number(cur.dataset.igcurtir)); return; }
  const marcas = e.target.closest("[data-igmarcas]");
  if (marcas) { const l = $("igm-" + marcas.dataset.igmarcas); l.hidden = !l.hidden; return; }
  const cc = e.target.closest("[data-igccurtir]");
  if (cc) {
    const on = !cc.querySelector(".ig-vermelho");
    cc.innerHTML = IG.coracao(on);
    try { await api("/api/ig/curtir", { comentario: Number(cc.dataset.igccurtir), on }); } catch (err) { toast(err.message); }
    return;
  }
  const resp = e.target.closest("[data-igresponder]");
  if (resp) { IG.responder({ id: resp.dataset.igresponder, handle: resp.dataset.handle }); return; }
  const st = e.target.closest("[data-igstory]");
  if (st) { IG.abrirStory(IG.feed.stories, Number(st.dataset.igstory)); return; }
  if (e.target.closest("[data-igstoryperfil]")) { IG.abrirStory(IG.perfil.stories, 0); return; }
  const aba = e.target.closest("[data-igaba]");
  if (aba) {
    document.querySelectorAll("[data-igaba]").forEach((b) => b.classList.toggle("on", b === aba));
    $("igpf-posts").hidden = aba.dataset.igaba !== "posts";
    $("igpf-marcadas").hidden = aba.dataset.igaba !== "marcadas";
  }
});

// toque duplo na foto curte (como no app)
document.addEventListener("dblclick", (e) => {
  const f = e.target.closest("[data-igduplo]");
  if (!f) return;
  igCurtirPost(Number(f.dataset.igduplo), true);
  const h = document.createElement("span");
  h.className = "ig-pop"; h.innerHTML = ic("heart-filled");
  f.appendChild(h); setTimeout(() => h.remove(), 800);
});

// o perfil da barra de baixo é sempre o dela
document.querySelector('#ig-nav [data-tab="igperfil"]').addEventListener("click", () => { IG.navPerfil = true; });

$("ig-resp-x").addEventListener("click", () => { IG.responder(null); $("ig-coment").value = ""; });
$("ig-publicar").addEventListener("click", async () => {
  const texto = $("ig-coment").value.trim();
  if (!texto || !IG.post) return;
  const btn = $("ig-publicar"); btn.disabled = true;
  try {
    await api("/api/ig/comentar", { post: IG.post.id, texto, pai: IG.pai });
    $("ig-coment").value = "";
    await loaders.igpost();
  } catch (err) { toast(err.message); }
  finally { btn.disabled = false; }
});
$("ig-coment").addEventListener("keydown", (e) => { if (e.key === "Enter") $("ig-publicar").click(); });

$("igs-fechar").addEventListener("click", () => IG.fecharStory());
$("igs-prox").addEventListener("click", () => IG.proxStory());
$("igs-ant").addEventListener("click", () => IG.antStory());
$("igs-msg").addEventListener("focus", () => clearTimeout(IG.story.t));
$("igs-msg").addEventListener("blur", () => { if (!$("igs").hidden && !$("igs-msg").value) IG.story.t = setTimeout(() => IG.proxStory(), 4000); });
$("igs-cor").addEventListener("click", async () => {
  const s = IG.story.grupos[IG.story.g].itens[IG.story.i];
  s.curtiu = !s.curtiu;
  $("igs-cor").innerHTML = IG.coracao(s.curtiu);
  if (s.curtiu && tgAt("6.1")) tg.HapticFeedback.impactOccurred("light");
  try { await api("/api/ig/story", { id: s.id, acao: "coracao", on: s.curtiu }); } catch (err) { toast(err.message); }
});
async function igEnviarStory() {
  const texto = $("igs-msg").value.trim();
  if (!texto) return;
  const s = IG.story.grupos[IG.story.g].itens[IG.story.i];
  try {
    const r = await api("/api/ig/story", { id: s.id, acao: "responder", texto });
    $("igs-msg").value = "";
    // como no Insta: a resposta vai pra conversa (aqui, o chat com ela)
    if (r.chat) concluido("Mensagem enviada");
    else { toast("Mensagem enviada"); IG.proxStory(); }
  } catch (err) { toast(err.message); }
}
$("igs-enviar").addEventListener("click", igEnviarStory);
$("igs-msg").addEventListener("keydown", (e) => { if (e.key === "Enter") igEnviarStory(); });
