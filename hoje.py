"""Linha do tempo "Hoje" da aba Agora (Patrick, 26/09).

O dia inteiro por período (Manhã, Tarde, Noite): os acontecimentos gravados em texto curto de painel,
as saídas da agenda como um item com início–fim e o que rolou lá dentro recuado embaixo, os blocos em casa
com a duração, e no fim o que ainda vem (previsto, em cinza, hora aproximada).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# tipos que não são acontecimento pro painel (texto interno do mundo)
FORA = {"father_check_in", "thread_consequence"}

PERIODOS = (("Manhã", 4, 12), ("Tarde", 12, 18), ("Noite", 18, 28))

# 26/09 (Patrick): ícones do Tabler (outline)
SAIDA_IC = {"faculdade": "school", "academia": "activity", "milo": "dog", "noite": "moon-stars",
            "encontro": "users", "freela": "camera", "praia": "beach", "jogo": "ball-football", "cafe": "coffee",
            "mercado": "shopping-cart", "medico": "building-hospital", "unhas": "brush", "cabelo": "scissors"}

# 26/09 (Patrick): redes com o logo próprio do Tabler; cada bloco em casa com ícone seu
MIDIA_IC = (("instagram", "brand-instagram"), ("tiktok", "brand-tiktok"), ("pinterest", "brand-pinterest"),
            ("o x", "brand-x"), ("celular", "device-mobile"), ("ouvindo", "music"), ("lendo", "book"),
            ("vendo", "device-tv"), ("série", "device-tv"), ("jogando", "device-gamepad-2"), ("look", "hanger"),
            ("closet", "hanger"), ("umect", "droplet-half"), ("unha", "brush"), ("estudando", "notebook"),
            ("trabalho", "device-laptop"), ("dormindo", "moon"), ("cochil", "moon"), ("piscina", "pool"),
            ("treinando", "activity"), ("croqui", "pencil"), ("quarto", "home-check"), ("milo", "dog"),
            ("plantas", "plant"), ("sol", "sun"), ("à toa", "sofa"))

VERBO_REFEICAO = {"café da manhã": "Tomou café", "almoço": "Almoçou", "jantar": "Jantou", "lanche": "Lanchou"}
REFEICAO_PREVISTA = {"cafe": ("Café da manhã", "coffee"), "almoco": ("Almoço", "tools-kitchen-2"),
                     "lanche": ("Lanche", "tools-kitchen-2"), "jantar": ("Jantar", "tools-kitchen-2")}


def dia_de(now: datetime) -> date:
    """O dia dela vai até as 4h (depois de meia-noite ainda é a noite de ontem)."""
    return now.date() if now.hour >= 4 else now.date() - timedelta(days=1)


def _hm(at: Optional[datetime]) -> str:
    return f"{at:%H:%M}" if at else ""


def _aprox(at: datetime) -> str:
    from agenda import aprox
    return aprox(at)


def _periodo(at: datetime, dia: date) -> str:
    h = at.hour + (24 if at.date() > dia else 0)
    for nome, ini, fim in PERIODOS:
        if ini <= h < fim:
            return nome
    return "Manhã"


def _sem_ponto(txt: str) -> str:
    return (txt or "").strip().rstrip(".").strip()


def _cap(txt: str) -> str:
    return txt[:1].upper() + txt[1:] if txt else txt


def _painel(txt: str) -> str:
    from webapp_server import voz_painel
    return voz_painel(_sem_ponto(txt))


# ------------------------------------------------------------ texto curto --
def curto(ev: dict) -> dict:
    """Um acontecimento em linha de painel: ícone, texto curto e (às vezes) linha de baixo e valor.
    26/09 (Patrick): sempre a ação na linha e a descrição curta, menor e cinza, embaixo — o que ainda vem cru
    do mundo se divide no parêntese do fim, no primeiro ':' ou no '—'."""
    out = _curto(ev)
    if not out["sub"] and out["texto"] == _painel(_sem_ponto(ev.get("summary") or ev.get("title") or "")):
        out.update(_divide(out["texto"]))
    return out


def _divide(txt: str) -> dict:
    m = re.match(r"(.+?) \(([^()]+)\)$", txt)
    if m:
        return {"texto": m.group(1), "sub": _cap(m.group(2))}
    for sep in (": ", " — ", "; "):
        if sep in txt:
            acao, resto = txt.split(sep, 1)
            return {"texto": acao, "sub": _cap(resto)}
    return {}


def _curto(ev: dict) -> dict:
    tipo, title = ev["event_type"], (ev.get("title") or "")
    s = _sem_ponto(ev.get("summary") or title)
    out = {"ic": "point", "texto": _painel(s), "sub": "", "valor": None, "aviso": False, "fim": None}

    if tipo == "agenda":
        out.update(_agenda(s))
        return out
    if tipo == "instagram":     # 27/09 (Patrick): o post dela no Hoje, a legenda embaixo
        acao, _, legenda = s.partition(": ")
        out.update(ic="brand-instagram", texto=acao, sub=legenda)
        return out
    if tipo == "tempo_livre" and s.startswith("Fez as unhas em casa"):
        return {**out, **_salao(s)}
    if tipo == "tempo_livre" and s.startswith("Ficou ouvindo a playlist dela"):
        # 28/09: "Ouviu Sabrina Carpenter" com Chappell Roan e Liniker tocando (e o story da Liniker às 14:09)
        artistas = list(dict.fromkeys(re.findall(r'"[^"]+" \(([^)]+)\)', s)))
        out.update(ic="music", texto="Ouviu a playlist dela", presente="Ouvindo a playlist dela",
                   sub=_e(artistas) if artistas else "")
        return out
    if tipo == "tempo_livre":
        out.update(ic=_ic_midia(title), texto=passado(_cap(title)) if title else _painel(s))
        return out
    if tipo == "social_contact":
        base, _, assunto = s.partition("; assunto: ")
        base = re.sub(r"\s*\([^)]*\)$", "", base)                  # "(Bodytech São Clemente)"
        base = base.split(", ")[0]                                  # "Conheceu a Gabi" (quem é fica no sistema)
        ic = ("user-plus" if base.startswith("Conheceu") else "message-dots" if base.startswith("Trocou mensagens")
              else "microphone" if base.startswith("Trocou áudios") else "phone" if base.startswith("Falou por telefone")
              else "users")
        out.update(ic=ic, texto=_painel(base), sub=f"Assunto: {_painel(assunto)[:1].lower()}{_painel(assunto)[1:]}" if assunto else "")
        return out
    if tipo == "social_invite":
        m = re.match(r"(.+?) te chamou: (.+?)(?: \(.*\))?$", s)
        if m:
            out.update(ic="calendar-plus", texto=f"{m.group(1)} chamou {_pra_onde(m.group(2))}")
        elif s.startswith("Topou o convite"):
            out.update(ic="calendar-check", texto="Topou ir " + _pra_onde(s.split(":", 1)[-1].strip()))
        else:
            out.update(ic="calendar-plus")
        return out
    if tipo == "consumo" and s.startswith(("Cabelo na ", "Fez as unhas em gel")):
        return {**out, **_salao(s)}
    if tipo == "consumo":
        m = re.match(r"(?:Pediu|Dividiu) (.+?)(?: com .+?)? no .+? \(R\$ (\d+)", s)
        if m:
            out.update(ic="receipt", texto=("Dividiu " if s.startswith("Dividiu") else "Pediu ") + m.group(1),
                       valor=int(m.group(2)))
        else:
            out.update(ic="receipt")
        return out
    if tipo == "transporte":
        m = re.search(r"R\$ (\d+)", s)
        out.update(ic="car", texto="Pegou um Uber" + (" dividido" if "dividido" in s else ""),
                   valor=int(m.group(1)) if m else None)
        return out
    if tipo == "commute":                                  # "No caminho (ida, ônibus): ônibus veio lotado"
        out.update(ic="alert-circle", aviso=True, texto=_cap(s.split("): ", 1)[-1]))
        return out
    if tipo == "money":
        out.update(ic="cash", **_dinheiro(s))
        return out
    if tipo == "gift":
        out.update(ic="shopping-bag-heart")
        m = re.match(r"Mandou (.+?) do (.+?) pr[oa] Patrick pelo app(?: de surpresa)? \(R\$ (\d+)\)", s)
        if m:
            out.update(texto="Mandou um presente pra você", sub=f"{_cap(m.group(1))} do {m.group(2)}",
                       valor=int(m.group(3)))
            return out
        m = re.match(r"O Patrick mandou de surpresa .+? do (.+?) pelo app", s)
        if m:
            out["texto"] = f"Chegou o presente do {m.group(1)} que você mandou"
        return out
    if tipo in ("meal", "snack"):
        return {**out, **_refeicao(ev, s)}
    if tipo == "routine":
        m = re.match(r"Tomou banho( e lavou o cabelo)? \((\d\d:\d\d)–(\d\d:\d\d)\)", s)
        if m:
            fim = datetime.fromisoformat(ev["event_at"]).replace(
                hour=int(m.group(3)[:2]), minute=int(m.group(3)[3:]))
            out.update(ic="chuveiro", texto="Tomou banho" + (" e lavou o cabelo" if m.group(1) else ""), fim=fim)
            return out
        m = re.match(r"Se pesou(?: na academia)?: (.+)", s)
        if m:
            out.update(ic="scale", texto=f"Se pesou · {m.group(1)}")
            return out
        if "masturbou" in s or "se tocou" in s:             # Patrick: hand-love-you de cabeça pra baixo
            out.update(ic="masturbacao", **_masturbacao(s))
            return out
        if s.startswith("Cuidou da bagunça dela: "):        # Patrick: "Arrumou a casa" e o que fez embaixo
            out.update(ic="home-check", texto="Arrumou a casa", sub=_cap(s.split(": ", 1)[1]))
            return out
        if s.startswith("Pagou o passeador"):
            out.update(ic="dog", texto="Pagou o passeador do Milo",
                       sub=_cap(s.split("— ", 1)[1]) if "— " in s else "")
            return out
        m = re.match(r"O Milo (.+)$", s)
        if m:
            out.update(ic="dog", texto="Arte do Milo", sub=_cap(m.group(1)))
            return out
        if "Milo" in s and "xixi" in s:                  # Patrick: "Foi pra calçada" e o xixi recuado
            out.update(ic="dog", texto="Foi pra calçada", filhos=[{"texto": "Xixi do Milo"}])
            if ev.get("end_at"):                         # 28/09: sem a volta, parecia que o Milo foi com ela pra PUC
                out["fim"] = datetime.fromisoformat(ev["end_at"])
        elif "Milo" in s or title == "Milo":
            out.update(ic="dog")
        elif title == "casa":
            out.update(ic="home-check")
        elif title == "faculdade":
            out.update(ic="school")
            m = re.match(r"(Trabalhou n[oa] .+?) \(entrega ([^)]+)\)(?:, (.+))?$", s)
            if m:
                out.update(texto=m.group(1), sub=f"Entrega {m.group(2)}" + (f" · {m.group(3)}" if m.group(3) else ""))
        elif title in ("vontade", "agenda reativa"):
            out.update(ic="bolt", **_decisao(s))
        elif title == "tv":
            out.update(ic="device-tv")
        elif title == "médico":
            out.update(ic="building-hospital")
        return out
    if tipo == "midia":
        out.update(ic="music" if "música" in s or "Ouviu" in s else "book")
        m = re.match(r'Ouviu "(.+?)" \((.+?)\), que o Patrick mandou: (.+)$', s)
        if m:
            out.update(texto="Ouviu a música que você mandou",
                       sub=f'"{m.group(1)}", {m.group(2)} · ' + ("curtiu" if m.group(3).startswith("curtiu") else "não curtiu muito"))
        m = re.match(r'Descobriu que saiu música nova de (.+?): "(.+?)"', s)
        if m:
            out.update(texto=f"Saiu música nova de {m.group(1)}", sub=f'"{m.group(2)}"')
        return out
    if tipo == "work":
        out.update(ic="camera")
        return out
    if tipo in ("manicure", "unhas"):
        out.update(ic="brush")
    return out


def _masturbacao(s: str) -> dict:
    """26/09 (Patrick): "Se masturbou no quarto" / "Pensando em você"; fora de casa, "Tesão muito alto".
    O resto do texto do mundo (se conta pra ele ou guarda) é do sistema, não do painel."""
    m = re.search(r"se (?:masturbou|trancou) ((?:n[oa]s?|em) [^,.—]+?)(?= pensando| e | —|[,.]|$)", s)
    onde = f" {m.group(1)}" if m else (" antes de dormir" if s.startswith("Antes de dormir") else "")
    chamou = "chamou" in s
    if s.startswith("Bateu um tesão"):
        return {"texto": f"Se masturbou{onde}", "sub": "Tesão muito alto" + (" · chamou você" if chamou else "")}
    return {"texto": f"Se masturbou{onde}", "sub": "Chamou você pra entrar no clima" if chamou else "Pensando em você"}


def _dinheiro(s: str) -> dict:
    """26/09 (Patrick): a ação na linha, o valor na coluna, o detalhe curto embaixo."""
    m = re.match(r"O Patrick (?:fez|mandou) (?:um|o) pix de R\$ (\d+)(.*)$", s)
    if m:
        resto = m.group(2)
        nota = re.search(r"\('(.+?)'\)", resto)
        sub = ("O que tinha prometido" if "prometido" in resto else "Pro uber" if "uber" in resto
               else "De presente" if "presente" in resto else "")
        if nota:
            sub = (sub + " · " if sub else "") + f'"{nota.group(1)}"'
        return {"texto": "Você fez um Pix pra ela", "valor": int(m.group(1)), "sub": sub}
    m = re.match(r"Usou o pix do Patrick: comprou (.+?) \(R\$ (\d+)\)", s)
    if m:
        return {"texto": "Usou o seu Pix", "sub": _cap(m.group(1)), "valor": int(m.group(2))}
    m = re.match(r"Caiu o cachê e ela fez o pix de volta pro Patrick: R\$ (\d+)", s)
    if m:
        return {"texto": "Devolveu o seu Pix", "sub": "Caiu o cachê", "valor": int(m.group(1))}
    m = re.match(r"Aperto: (.+?) \(R\$ (\d+)\)", s)
    if m:
        return {"texto": "Ficou no aperto", "sub": _cap(m.group(1)) + " · vai pedir ajuda pra você",
                "valor": int(m.group(2))}
    if s.startswith("O dinheiro dela acabou"):
        return {"texto": "Ficou no aperto", "sub": "O dinheiro acabou antes do cachê · vai pedir ajuda pra você"}
    return {}


def _salao(s: str) -> dict:
    """Cabelo e unhas: "Fez o cabelo" / "Repicado e escova" e o valor na coluna."""
    escolheu = " · você escolheu" if "Patrick escolheu" in s else ""
    m = re.match(r"Cabelo na .+?: (.+) · R\$ (\d+)$", s)
    if m:
        feito = m.group(1).replace(" (o Patrick escolheu)", "")
        return {"ic": "scissors", "texto": "Fez o cabelo", "sub": _cap(feito) + escolheu, "valor": int(m.group(2))}
    m = re.match(r"Fez as unhas em gel .+?: (.+?)(?: — .+)? \(R\$ (\d+)\)", s)
    if m:
        return {"ic": "brush", "texto": "Fez as unhas", "sub": f"Gel · {m.group(1)}{escolheu}", "valor": int(m.group(2))}
    m = re.match(r"Fez as unhas em casa, esmalte (.+?)(?: — .+)?$", s)
    if m:
        return {"ic": "brush", "texto": "Fez as unhas", "sub": f"Esmalte {m.group(1)}{escolheu}"}
    return {}


def _agenda(s: str) -> dict:
    """27/09 (agenda viva): o que ela decidiu pelo que sentia — ação na linha, motivo embaixo."""
    m = re.match(r"Saindo de lá, resolveu passar .+? antes de voltar \((.+)\)$", s)
    if m:
        return {"ic": "bolt", "motivo": f"Emendou na volta · {m.group(1)}"}
    m = re.match(r"Desistiu de ir: (.+?) \((.+?)\)(?:\. Avisou (.+?)(?: e combinaram outro dia)?)?$", s)
    if m:
        sub = _cap(m.group(2)) + (f" · avisou {m.group(3)}" if m.group(3) else "")
        return {"ic": "calendar-x", "texto": f"Desistiu de ir {_pra_onde(m.group(1))}", "sub": sub}
    m = re.match(r"Faltou a aula de hoje \((.+?)\): (.+?)\. Vai pegar", s)
    if m:
        return {"ic": "school-off", "texto": "Faltou a aula", "sub": f"{m.group(1)} · {m.group(2)}"}
    m = re.match(r"Pegou a matéria da aula que faltou \((.+?)\) com (.+?) e", s)
    if m:
        return {"ic": "notebook", "texto": f"Pegou a matéria com {m.group(2)}", "sub": _cap(m.group(1))}
    m = re.match(r"Chamou (.+?) pra sair (\S+)(?: às (\d\d:\d\d) \(.+\); .+ topou|, mas .+ não podia)$", s)
    if m:
        topou = "topou" in s
        quando = _cap(m.group(2)) + (f" {m.group(3)}" if m.group(3) else "")
        return {"ic": "calendar-plus", "texto": f"Chamou {m.group(1)} pra sair",
                "sub": f"{quando} · " + ("topou" if topou else "não podia")}
    m = re.match(r"Remarcou pra (.+?) às (\d\d:\d\d): (.+?) \((.+)\)$", s)
    if m:
        return {"ic": "calendar-time", "texto": "Remarcou", "sub": f"{_cap(m.group(3))} · pra {m.group(1)} {m.group(2)}"}
    m = re.match(r"Combinou com o Patrick: (.+?) (amanhã|segunda|terça|quarta|quinta|sexta|sábado|domingo) às (\d\d:\d\d)", s)
    if m:
        return {"ic": "calendar", "texto": "Combinou com você", "sub": f"{_cap(m.group(1))} · {m.group(2)} {m.group(3)}"}
    for padrao, texto in ((r"Desistiu de treinar hoje \((.+)\)$", "Desistiu de treinar"),
                          (r"Trocou a Bodytech pela academia do prédio \((.+)\)$", "Treinou no prédio"),
                          (r"Deixou o passeio do Milo pra depois \((.+)\)$", "Adiou o passeio do Milo"),
                          (r"Deixou o mercado da semana pra amanhã \((.+)\)$", "Adiou o mercado"),
                          (r"Desistiu do mercado da semana hoje \((.+)\)$", "Desistiu do mercado"),
                          (r"Desistiu: .+? \((.+)\)$", None)):
        m = re.match(padrao, s)
        if m:
            if texto is None:
                return {"ic": "calendar-x", **_divide(s)}
            return {"ic": "calendar-x" if "Desistiu" in texto else "calendar-time", "texto": texto,
                    "sub": _cap(m.group(1))}
    return {"ic": "calendar"}


def _decisao(s: str) -> dict:
    """Por que saiu (vira a linha cinza da saída) ou desistência (linha própria)."""
    m = re.match(r"Deu vontade e foi: .+? \((.+)\)$", s)
    if m:
        return {"motivo": f"Resolveu sair · {m.group(1)}"}
    if s.startswith("O Patrick convenceu"):
        return {"motivo": "Você convenceu"}
    m = re.match(r"Combinou com o Patrick[^:]*(?:: (.+))?$", s)
    if m:
        return {"motivo": "Combinou com você" + (f" · {m.group(1)}" if m.group(1) else "")}
    m = re.match(r"Desistiu de (.+?)(?: hoje)?(?:: (.+))?$", s)
    if m:
        return {"texto": f"Desistiu de {m.group(1)}", "sub": _cap(m.group(2) or "")}
    return {}


def _pra_onde(plano: str) -> str:
    """'Saindo com a Bia no Quartinho Bar' → 'pro Quartinho Bar'."""
    m = re.search(r" (no|na|nos|nas) (.+)$", plano)
    if not m:
        return "pra sair"
    return {"no": "pro", "na": "pra", "nos": "pros", "nas": "pras"}[m.group(1)] + " " + m.group(2)


def _min(txt: str) -> str:
    return txt[:1].lower() + txt[1:] if txt else txt


def _refeicao(ev: dict, s: str) -> dict:
    """26/09 (Patrick): a refeição na linha 1 e o prato embaixo; presente seu: a loja em cima, os itens embaixo."""
    fim = datetime.fromisoformat(ev["end_at"]) if ev.get("end_at") else None
    estufada = " · comeu além da conta" if "estufada" in s else ""
    if ev["event_type"] == "snack" or s.startswith("Beliscou"):
        return {"ic": "cookie", "texto": _painel(s.split(";")[0]), "fim": None}
    m = re.match(r"O Patrick mandou de surpresa (.+?) do (.+?) pelo app", s)
    if m:
        return {"ic": "shopping-bag-heart", "texto": f"Comeu o {m.group(2)} que você mandou", "fim": fim,
                "sub": _cap(m.group(1)) + estufada}
    m = re.match(r"O (.+?) do delivery chegou", s)
    if m:
        return {"ic": "shopping-bag", "texto": "Comeu o delivery", "fim": fim, "sub": _cap(m.group(1))}
    m = re.match(r"(Café da manhã|Almoço|Jantar|Lanche) ([^:]+): ([^;]+)", s)
    if m:
        verbo = VERBO_REFEICAO[m.group(1).lower()]
        onde = "" if m.group(2) == "em casa" else " " + m.group(2)
        prato = re.sub(r"^(um|uma|uns|umas) ", "", m.group(3).strip())
        prato = re.sub(r" pedido no iFood$", " do iFood", prato)
        return {"ic": "coffee" if verbo == "Tomou café" else "tools-kitchen-2", "texto": verbo + onde,
                "fim": fim, "sub": _cap(prato) + estufada}
    m = re.match(r"Comeu (.+?) no (.+)", s)
    if m:
        return {"ic": "tools-kitchen-2", "texto": "Comeu", "sub": _cap(m.group(1)), "fim": fim}
    return {"ic": "tools-kitchen-2", "texto": _painel(s.split(";")[0]), "fim": fim}


IRREGULAR = {"vendo": "Viu", "lendo": "Leu", "fazendo": "Fez", "pondo": "Pôs", "tendo": "Teve", "trazendo": "Trouxe"}


FORA_DO_PADRAO = {"deitada à toa": "Ficou à toa"}


def passado(texto: str) -> str:
    """26/09 (Patrick): tudo no passado — 'Olhando o Instagram' → 'Olhou o Instagram', 'Vendo X' → 'Viu X'."""
    if texto.lower() in FORA_DO_PADRAO:
        return FORA_DO_PADRAO[texto.lower()]
    pre, _, corpo = texto.partition(" ") if texto.lower().startswith("se ") else ("", "", texto)
    palavra, _, resto = corpo.partition(" ")
    p = palavra.lower()
    if p in IRREGULAR:
        novo = IRREGULAR[p].lower()
    elif p[-4:] in ("ando", "endo", "indo"):
        novo = p[:-4] + {"ando": "ou", "endo": "eu", "indo": "iu"}[p[-4:]]
    else:
        return texto
    frase = (f"{pre} {novo}" if pre else novo) + (f" {resto}" if resto else "")
    return _cap(frase)


def _ic_midia(texto: str) -> str:
    t = texto.lower()
    for chave, ic in MIDIA_IC:
        if chave in t:
            return ic
    return "home"


# ------------------------------------------------------------------ dia --
def _eventos(db, ini: datetime, fim: datetime) -> list[dict]:
    with db.get_connection() as conn:
        rows = conn.execute(
            """SELECT event_key, event_at, end_at, event_type, title, summary FROM life_events
               WHERE event_at>=? AND event_at<=? ORDER BY event_at, id""",
            (ini.isoformat(), fim.isoformat())).fetchall()
    return [dict(r) for r in rows if r["event_type"] not in FORA]


def _saidas(db, dia: date, now: datetime) -> list[dict]:
    """Cada compromisso do dia: do pé na rua até chegar em casa, com o título do 'Lá'."""
    from agenda import Agenda
    from social_day import short_name
    try:
        ag = Agenda(db)
        etapas = ag.etapas(dia, now)
        amigos = {c["key"]: [short_name(f) for f in c["friends"]] for c in ag._compromissos(dia)}
    except Exception:
        logger.exception("hoje.saidas")
        return []
    por: dict[str, list] = {}
    for e in etapas:
        if e.compromisso and e.tipo != "arrumando":
            por.setdefault(e.compromisso, []).append(e)
    out = []
    for key, es in por.items():
        la = next((e for e in es if e.tipo == "la"), es[0])
        tipo = _tipo_saida(key, la)
        com = amigos.get(key) or la.com                      # "com a Bia" (o card usa sem artigo)
        titulo = _foi(la.titulo) + (f" com {_e(com)}" if com else "")
        out.append({"key": key, "ini": es[0].inicio, "fim": es[-1].fim, "titulo": titulo,
                    "previsto": la.titulo + (f" com {_e(com)}" if com else ""),
                    "ic": SAIDA_IC.get(tipo, "map-pin"), "la": la,
                    "volta": next((e for e in es if e.tipo == "voltando"), None)})
    return sorted(out, key=lambda s: s["ini"])


def _foi(titulo: str) -> str:
    """Título do 'Lá' no passado: 'No Quartinho' → 'Foi pro Quartinho', 'Na academia' → 'Foi pra academia'."""
    m = re.match(r"(No|Na|Nos|Nas) (.+)$", titulo)
    if not m:
        return titulo
    return "Foi " + {"No": "pro", "Na": "pra", "Nos": "pros", "Nas": "pras"}[m.group(1)] + " " + m.group(2)


def _e(nomes: list) -> str:
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _tipo_saida(key: str, la) -> str:
    if key.startswith("puc:"):
        return "faculdade"
    if key.startswith("gym:"):
        return "academia"
    if key.startswith("milo:"):
        return "milo"
    if key.startswith("freela:"):
        return "freela"
    for t in ("mercado", "medico", "unhas", "cabelo"):
        if key.startswith(t + ":"):
            return t
    if key.startswith("vontade:"):
        return "cafe"
    if la.lugar_key.endswith("_beach"):
        return "praia"
    if la.lugar_key == "estadio_nilton_santos":
        return "jogo"
    return "noite" if la.inicio.hour >= 18 else "encontro"


def _blocos(db, now: datetime) -> dict[str, datetime]:
    """Fim de cada bloco em casa (pela chave do acontecimento)."""
    try:
        from tempo_livre import TempoLivre
        return {b.chave: b.fim for b in TempoLivre(db).do_dia(now)}
    except Exception:
        logger.exception("hoje.blocos")
        return {}


def _previstos(db, dia: date, now: datetime, saidas: list[dict]) -> list[dict]:
    out = []
    comidas = set()
    try:
        from meals import Meals
        meals = Meals(db)
        comidas = {e["event_key"] for e in meals.eaten_today(now)}
        for s in meals.day_plan(dia):
            if s.skipped or s.key in comidas or s.at <= now:
                continue
            if any(x["ini"] <= s.at < x["fim"] for x in saidas):
                continue                                 # come fora: já está na saída
            nome, ic = REFEICAO_PREVISTA.get(s.kind, ("Refeição", "tools-kitchen-2"))
            out.append({"at": s.at, "ic": ic, "texto": nome})
    except Exception:
        logger.exception("hoje.previsto.refeicoes")
    for s in saidas:
        if s["ini"] > now:                      # 27/09 (Patrick): "~15:00 No Shopping da Gávea" — a hora em que chega lá
            out.append({"at": s["la"].inicio, "ic": s["ic"], "texto": s["previsto"]})
    try:
        from watch import Watching
        plano = Watching(db).night_plan(dia)
        if plano and plano["start"] > now and not any(x["ini"] <= plano["start"] < x["fim"] for x in saidas):
            out.append({"at": plano["start"], "ic": "device-tv", "texto": "Série"})
    except Exception:
        logger.exception("hoje.previsto.serie")
    try:
        from sleep_plan import SleepPlan
        bed = SleepPlan(db).bed(dia)
        if bed > now:
            out.append({"at": bed, "ic": "moon", "texto": "Dormir"})
    except Exception:
        logger.exception("hoje.previsto.dormir")
    return sorted(out, key=lambda p: p["at"])


def hoje_view(db, now: datetime) -> dict:
    dia = dia_de(now)
    ini = datetime.combine(dia, datetime.min.time()) + timedelta(hours=4)
    saidas = _saidas(db, dia, now)
    fins = _blocos(db, now)
    itens: list[dict] = []

    try:
        from sleep_plan import SleepPlan
        wake = SleepPlan(db).wake(dia)
        if wake and ini <= wake <= now:
            itens.append({"at": wake, "ic": "sunrise", "texto": "Acordou", "sub": "", "valor": None,
                          "aviso": False, "fim": None})
    except Exception:
        logger.exception("hoje.acordou")

    for ev in _eventos(db, ini, now):
        at = datetime.fromisoformat(ev["event_at"])
        it = {"at": at, "key": ev["event_key"], **curto(ev)}
        if ev["event_type"] == "tempo_livre" and ev["event_key"] in fins:
            it["fim"] = fins[ev["event_key"]]
            if ev.get("title") and not it.get("presente"):
                it["presente"] = _cap(ev["title"])
        itens.append(it)

    # 27/09: o banho interrompe o que ela fazia em casa (o Instagram 00:02–00:38 com banho às 00:31)
    # e a saída também (27/09: "Montou looks" até 15:11 com a academia às 14:53)
    banhos = [it["at"] for it in itens if it["ic"] == "chuveiro"] + [s["ini"] for s in saidas]
    for it in itens:
        corte = next((b for b in banhos if it["ic"] != "chuveiro" and it.get("fim") and it["at"] < b < it["fim"]), None)
        if corte:
            it["fim"] = corte
    # 27/09: o que ainda está acontecendo fica no presente ("Tomando banho 00:31–"), não "Tomou banho 00:31–01:12"
    for it in itens:
        if it.get("fim") and it["fim"] > now:
            it["texto"] = it.get("presente") or _presente(it["texto"])
            it["fim"], it["agora"] = None, True

    # blocos iguais em seguida viram um só ("Montando looks no closet" 13:59 e 14:38)
    juntos: list[dict] = []
    for it in sorted(itens, key=lambda x: x["at"]):
        ant = juntos[-1] if juntos else None
        if ant and ant["texto"] == it["texto"] and ant["ic"] == it["ic"] and not it["valor"]:
            ant["fim"] = max(filter(None, (ant["fim"], it["fim"], it["at"])))
            continue
        juntos.append(it)

    # saídas já começadas: viram item, e o que aconteceu no período entra recuado
    raiz: list[dict] = []
    abertas = [s for s in saidas if s["ini"] <= now]
    for s in abertas:
        raiz.append({"at": s["ini"], "key": s["key"], "fim": s["fim"] if s["fim"] <= now else None, "ic": s["ic"],
                     "texto": s["titulo"], "sub": "", "valor": None, "aviso": False, "filhos": [], "saida": True})
    for it in list(juntos):                           # por que saiu: vira a linha cinza da saída
        if it.get("motivo"):
            chave = (it.get("key") or "").removesuffix(":decidiu")
            alvo = next((r for r in raiz if r.get("key") == chave), None) or next(
                (r for r in raiz if r.get("saida") and it["at"] <= r["at"] + timedelta(minutes=5)
                 and r["at"] - it["at"] <= timedelta(hours=3)), None)
            if alvo:
                alvo["sub"] = it["motivo"]
                juntos.remove(it)
            else:
                it["sub"] = it["motivo"]
    for it in juntos:
        # 28/09: "Olhou o Pinterest 13:35" (já em casa) caía dentro da PUC, que acabava às 13:35
        dono = next((r for r in raiz if r.get("saida") and r["at"] <= it["at"]
                     and (it["at"] < r["fim"] if r["fim"] else it["at"] <= now)), None)
        if dono:
            dono["filhos"].append(it)
        else:
            raiz.append({**it, "filhos": [{"at": it["at"], "fim": None, **f} for f in it.get("filhos") or []]})
    # 28/09 (Patrick): a volta pra casa não aparecia — "Foi pra PUC 08:19–13:35" engolia a carona com o Theo
    for s in abertas:
        v, dono = s.get("volta"), next((r for r in raiz if r.get("key") == s["key"] and r.get("saida")), None)
        if v and dono and v.inicio <= now:
            chegou = v.fim <= now
            dono["filhos"].append({"at": v.inicio, "fim": v.fim if chegou else None, "ic": "home",
                                   "texto": "Voltou pra casa" if chegou else "Voltando pra casa", "sub": v.como,
                                   "valor": None, "aviso": False})       # o uber já tem a linha dele, com valor
    for r in raiz:
        if r.get("filhos"):
            r["filhos"].sort(key=lambda f: f["at"])
    raiz.sort(key=lambda x: x["at"])

    previstos = _previstos(db, dia, now, saidas)
    periodos: dict[str, list] = {}
    for it in raiz:
        periodos.setdefault(_periodo(it["at"], dia), []).append(_linha(it))
    for p in previstos:
        periodos.setdefault(_periodo(p["at"], dia), []).append(
            {"ic": p["ic"], "texto": p["texto"], "sub": "", "hora": _aprox(p["at"]), "valor": None,
             "aviso": False, "filhos": [], "previsto": True})
    ordem = [n for n, *_ in PERIODOS if n in periodos]
    return {"periodos": [{"nome": n, "itens": periodos[n]} for n in ordem]}


PRESENTE = (("Tomou banho e lavou o cabelo", "Tomando banho e lavando o cabelo"), ("Tomou banho", "Tomando banho"),
            ("Tomou café", "Tomando café"), ("Almoçou", "Almoçando"), ("Jantou", "Jantando"), ("Lanchou", "Lanchando"),
            ("Comeu", "Comendo"))


def _presente(texto: str) -> str:
    for antes, agora in PRESENTE:
        if texto.startswith(antes):
            return agora + texto[len(antes):]
    return texto


def _linha(it: dict) -> dict:
    fim = it.get("fim")
    em_curso = (it.get("saida") or it.get("agora")) and not fim
    hora = _hm(it["at"]) + ("–" + _hm(fim) if fim and _hm(fim) != _hm(it["at"]) else "–" if em_curso else "")
    return {"ic": it["ic"], "texto": it["texto"], "sub": it.get("sub") or "", "hora": hora,
            "valor": it.get("valor"), "aviso": it.get("aviso", False), "previsto": False,
            "filhos": [{"texto": f["texto"], "sub": f.get("sub") or "", "valor": f.get("valor"),
                        "aviso": f.get("aviso", False),
                        "hora": _hm(f["at"]) + ("–" + _hm(f["fim"]) if f.get("fim") and _hm(f["fim"]) != _hm(f["at"]) else "")}
                       for f in it.get("filhos", [])]}
