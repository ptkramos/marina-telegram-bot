"""Redesenho dos Bastidores, passo 4 (06/10): a sub-aba Sentimentos do Por dentro.

PLANO_WEBAPP, "Redesenho dos Bastidores — plano". Três seções, cada informação vira desenho:

* **Humor:** grade 3×3 pelos eixos que já existem (`valence` = mal↔bem nas colunas, `arousal` = calma↔agitada nas
  linhas), uma palavra e uma carinha por casa. A casa de agora pintada com o "desde", as do dia clarinhas com a hora e
  o caminho em setinhas nos vãos (só os últimos 4 passos). O caminho sai do `bastidores_hist` (chave `humor`: o
  relógio de 10 min grava a casa quando ela muda). Embaixo, Brincadeira e Bateria social.
* **Sentindo agora:** por pessoa (Patrick, Bia, …, Dela), cada sentimento com 5 bolinhas e a força, o motivo, o
  "Desde 14:10" e a tendência (Crescendo / Estável / Passando) ou "Até resolver".
* **Já passou hoje:** o que ela sentiu hoje e já esfriou, cinza, sem repetir o de cima.

Só tela: a grade não muda o prompt (ela segue com as frases do `EmotionEngine.mood_words`), e um erro numa seção
some com a seção.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# linhas de cima pra baixo (agitada → calma), colunas da esquerda pra direita (mal → bem)
GRADE = ((("Irritada", "mood-angry"), ("Inquieta", "mood-nervous"), ("Animada", "mood-crazy-happy")),
         (("Chateada", "mood-sad"), ("Normal", "mood-neutral"), ("Feliz", "mood-happy")),
         (("Desanimada", "mood-empty"), ("Preguiçosa", "zzz"), ("Relaxada", "mood-smile-beam")))
BEM, MAL = 0.62, 0.45                # cortes do bem-estar (os mesmos do mood_words)
AGITADA, CALMA = 0.62, 0.40          # cortes da agitação
PASSOS_MAX = 4                       # setinhas do caminho
FORCA = ((0.2, "Leve"), (0.4, "Moderada"), (0.6, "Forte"), (0.8, "Muito forte"), (9, "Intensa"))
BRINCADEIRA = ((0.3, "Séria"), (0.5, "Na dela"), (0.7, "Brincalhona"), (9, "Zoeira"))
BATERIA = ((0.25, "Esgotada"), (0.5, "Na reserva"), (0.75, "De boa"), (9, "Carregada"))
TENDENCIA_JANELA = timedelta(hours=1)
SUBINDO, ESTAVEL = 0.02, 0.9         # cresceu mais que isso / ainda tem 90% do que tinha há 1 h
PESSOAS_SENTIMENTOS_MAX = 8
# 06/10 (Patrick, nos prints): motivo e detalhe têm uma linha cada, sem cortar (o detalhe quebra se precisar)
MOTIVO_MAX, DETALHE_MAX = 90, 60
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _palavra(v: float, escada) -> str:
    return next(w for lim, w in escada if v < lim)


# ------------------------------------------------------------------- humor --
def casa(valence: float, arousal: float) -> tuple[int, int]:
    """(linha, coluna) da grade: linha 0 agitada … 2 calma; coluna 0 mal … 2 bem."""
    linha = 0 if arousal >= AGITADA else 1 if arousal >= CALMA else 2
    coluna = 2 if valence >= BEM else 1 if valence >= MAL else 0
    return linha, coluna


def _passos(caminho: list[tuple[int, int]]) -> list[dict]:
    """Setinhas entre casas vizinhas. Salto de várias casas vira uma seta por casa (anda na diagonal enquanto dá,
    depois reto). Cada seta: a casa de onde sai e a direção (dl, dc), cada um em -1, 0, 1; só os últimos 4 passos."""
    setas = []
    for (l0, c0), (l1, c1) in zip(caminho, caminho[1:]):
        l, c = l0, c0
        while (l, c) != (l1, c1):
            dl = (l1 > l) - (l1 < l)
            dc = (c1 > c) - (c1 < c)
            setas.append({"l": l, "c": c, "dl": dl, "dc": dc})
            l, c = l + dl, c + dc
    # foi e voltou pelo mesmo vão (Feliz → Animada → Feliz): uma seta de ida e volta no lugar das duas
    out: list[dict] = []
    for s in setas[-PASSOS_MAX:]:
        volta = next((o for o in out if (o["l"] + o["dl"], o["c"] + o["dc"], -o["dl"], -o["dc"])
                      == (s["l"], s["c"], s["dl"], s["dc"])), None)
        if volta:
            out.remove(volta)
            s = {**s, "ida_volta": True}
        out.append(s)
    return out


def humor(db, now: datetime, valence: float, arousal: float, dia_ini: datetime,
          dormiu: Optional[datetime] = None) -> dict:
    """Dormindo (Patrick, 06/10): o motor não olha o sono (de madrugada ela aparecia "Inquieta"); fica pintada a
    casa em que ela pegou no sono, "até 23:30", e o caminho para até ela acordar."""
    import bastidores_hist
    l, c = casa(valence, arousal)
    sem_historia = bastidores_hist.ultimo(db, "humor", now) is None   # 1ª vez: o "desde" seria a hora que abriu
    if dormiu:
        antes = bastidores_hist.ultimo(db, "humor", dormiu)
        if antes:
            l, c = antes["l"], antes["c"]
        now = dormiu                                    # o dia dela parou aí
    else:
        bastidores_hist.humor(db, now, l, c)           # grava se mudou (o relógio de 10 min também grava)
    regs = bastidores_hist.lista(db, "humor", dia_ini, now)
    antes = bastidores_hist.ultimo(db, "humor", dia_ini)   # de onde ela veio da noite
    if antes:
        regs.insert(0, {**antes, "em": dia_ini})
    visitas: list[dict] = []                            # trechos seguidos na mesma casa
    for r in regs:
        if visitas and (visitas[-1]["l"], visitas[-1]["c"]) == (r["l"], r["c"]):
            continue
        visitas.append({"l": r["l"], "c": r["c"], "em": r["em"]})
    if not visitas or (visitas[-1]["l"], visitas[-1]["c"]) != (l, c):
        visitas.append({"l": l, "c": c, "em": now})
    horas: dict = {}
    for v in visitas[:-1]:                              # volta a uma casa: vale a hora mais nova
        horas[(v["l"], v["c"])] = v["em"]
    desde = visitas[-1]["em"]
    grade = []
    for li, linha in enumerate(GRADE):
        for ci, (palavra, icone) in enumerate(linha):
            agora = (li, ci) == (l, c)
            em = desde if agora else horas.get((li, ci))
            grade.append({"palavra": palavra, "icone": icone, "agora": agora,
                          "hora": f"{em:%H:%M}" if em and em > dia_ini and not (agora and sem_historia) else ""})
    if dormiu:
        return {"grade": grade, "palavra": GRADE[l][c][0], "desde": f"até {dormiu:%H:%M}" if not sem_historia else "",
                "dormindo": f"Dormindo desde {dormiu:%H:%M}", "setas": _passos([(v["l"], v["c"]) for v in visitas])}
    return {"grade": grade, "palavra": GRADE[l][c][0], "dormindo": "",
            "desde": f"desde {desde:%H:%M}" if desde > dia_ini and not sem_historia else "",
            "setas": _passos([(v["l"], v["c"]) for v in visitas])}


def barras(panel: dict) -> list[dict]:
    brinc, social = (b["value"] for b in panel["mood_bars"])
    return [{"label": "Brincadeira", "icone": "mood-tongue", "value": brinc, "word": _palavra(brinc, BRINCADEIRA)},
            {"label": "Bateria social", "icone": "battery-3", "value": social, "word": _palavra(social, BATERIA)}]


# ---------------------------------------------------------- sentindo agora --
def _grupos(eps) -> dict:
    """Mesmo sentimento pela mesma pessoa vira um (como o `EmotionEngine.panel`): o mais forte + 0,02 por repetição.
    O que fica "até resolver" (entrega, casting) é um por causa: a ansiedade da entrega não vira a do casting."""
    out: dict = {}
    for e in eps:
        out.setdefault((e.kind, e.target, e.id if e.sticky else 0), []).append(e)
    return {k: min(1.0, max(e.intensity for e in v) + 0.02 * (len(v) - 1)) for k, v in out.items()}, out


def _desde(at: datetime, now: datetime) -> str:
    dias = (now.date() - at.date()).days
    if dias <= 0:
        return f"Desde {at:%H:%M}"
    if dias == 1:
        return f"Desde ontem, {at:%H:%M}"
    return f"Desde {DIAS[at.weekday()]}, {at:%H:%M}"


def _tendencia(valor: float, antes: float) -> str:
    if valor > antes + SUBINDO:
        return "crescendo"
    return "estavel" if valor >= antes * ESTAVEL else "passando"


def _pessoas(db) -> dict:
    """Primeiro nome em minúsculas → nome, iniciais e foto, como na aba Mundo."""
    from social_day import AVATARS_DIR
    out = {"patrick": {"nome": "Patrick", "iniciais": "P", "foto": None}}
    try:
        with db.get_connection() as conn:
            rows = conn.execute("SELECT canonical_key, display_name FROM world_characters WHERE active=1 "
                                "AND canonical_key NOT IN ('marina','patrick_ramos')").fetchall()
    except Exception:
        logger.exception("bastidores_sentimentos.pessoas")
        rows = []
    for r in rows:
        nome = r["display_name"]
        if " (" in nome:                                # "Beatriz (Bia) Andrade" → "Bia Andrade"
            apelido = nome.split(" (")[1].split(")")[0]
            nome = " ".join([apelido] + nome.split(") ")[1].split()) if ") " in nome else apelido
        limpo = nome.replace("Dona ", "").replace("Seu ", "")
        info = {"nome": nome.split()[0] if not nome.startswith(("Dona ", "Seu ")) else " ".join(nome.split()[:2]),
                "iniciais": "".join(w[0] for w in limpo.split()[:2]).upper(),
                "foto": f"avatars/{r['canonical_key']}.jpg" if (AVATARS_DIR / f"{r['canonical_key']}.jpg").is_file()
                else None}
        if r["canonical_key"] == "henrique_salles":
            out["pai"] = {**info, "nome": "Pai"}
        out.setdefault(limpo.split()[0].lower(), info)
    return out


def _quem(target: Optional[str], pessoas: dict) -> dict:
    if not target:
        return {"chave": "", "nome": "Dela", "iniciais": "", "foto": None, "icone": "user"}
    nome = target.split(" ", 1)[1] if target.split(" ", 1)[0] in ("o", "a") and " " in target else target
    info = pessoas.get(nome.split()[0].lower()) or {"nome": nome[:1].upper() + nome[1:],
                                                   "iniciais": nome[:1].upper(), "foto": None}
    return {"chave": target, **info}


def sentindo(db, now: datetime) -> list[dict]:
    from emotion import FAMILIES, EmotionEngine
    from webapp_server import SENTIMENTO_TELA, cap, motivo_tela
    eng = EmotionEngine(db)
    valores, grupos = _grupos(eng.episodes(now))
    antes, _ = _grupos(eng.episodes(now - TENDENCIA_JANELA))
    pessoas = _pessoas(db)
    blocos: dict = {}
    for chave, valor in sorted(valores.items(), key=lambda kv: -kv[1])[:PESSOAS_SENTIMENTOS_MAX]:
        target, eps = chave[1], grupos[chave]
        ultimo = max(eps, key=lambda e: e.started_at)
        forte = max(eps, key=lambda e: e.intensity)
        ate_resolver = forte.sticky and forte.intensity >= forte.peak * 0.99
        n = next(i for i, (lim, _) in enumerate(FORCA) if valor < lim)
        blocos.setdefault(target or "", []).append({
            "nome": cap(SENTIMENTO_TELA.get(ultimo.word, ultimo.word)),
            "bolinhas": n + 1, "forca": FORCA[n][1],
            **motivo_tela(ultimo.cause, target or "", MOTIVO_MAX, DETALHE_MAX),
            "desde": _desde(min(e.started_at for e in eps), now),
            "tendencia": "ate_resolver" if ate_resolver else _tendencia(valor, antes.get(chave, 0.0)),
            "bom": FAMILIES[ultimo.family]["valence"] > 0})
    ordem = sorted(blocos, key=lambda t: (t != "o Patrick", t == "", -max(s["bolinhas"] for s in blocos[t])))
    return [{**_quem(t or None, pessoas), "sentimentos": blocos[t]} for t in ordem]


# ---------------------------------------------------------- já passou hoje --
def ja_passou(db, now: datetime, dia_ini: datetime) -> list[dict]:
    from emotion import EmotionEngine
    from webapp_server import motivo_tela, sentimento_tela
    eng = EmotionEngine(db)
    ativos = {(e.word, e.target or "") for e in eng.episodes(now)}
    out, vistos = [], set()
    for x in eng.day_log(dia_ini, now):
        chave = (x["word"], x["target"] or "")
        if chave in ativos or (chave, x["cause"]) in vistos:
            continue
        vistos.add((chave, x["cause"]))
        out.append({"hora": f"{x['at']:%H:%M}", "texto": sentimento_tela(x["word"], x["target"]),
                    **motivo_tela(x["cause"], x["target"] or "", MOTIVO_MAX, DETALHE_MAX)})
    return out


# --------------------------------------------------------------------- tela --
def sentimentos_view(db, now: datetime, panel: dict, dormiu: Optional[datetime] = None) -> dict:
    """Chave `sentimentos` do /api/bastidores?tela=dentro. Uma seção com erro some sozinha."""
    from por_dentro import VIRA_O_DIA, dia_logico
    dia_ini = datetime.combine(dia_logico(now), time(VIRA_O_DIA))
    out: dict = {}
    for chave, fn in (("humor", lambda: humor(db, now, panel["valence"], panel["arousal"], dia_ini, dormiu)),
                      ("barras", lambda: barras(panel)),
                      ("sentindo", lambda: sentindo(db, now)),
                      ("passou", lambda: ja_passou(db, now, dia_ini))):
        try:
            out[chave] = fn()
        except Exception:
            logger.exception("bastidores_sentimentos.%s", chave)
            out[chave] = None
    return out
