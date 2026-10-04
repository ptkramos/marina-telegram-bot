"""Aba Dinheiro dos Bastidores (Patrick, 28/09, no celular).

- Topo: saldo, o que entrou e saiu no mês, próximo cachê e as contas dela (celular e streamings).
- Extrato **agrupado por saída**, como o Hoje: "Foi no Shopping da Gávea" · "Cinema, pipoca, refri e uber" com o total;
  tocar abre os itens (Uber · Ida, Cinema, Pipoca · Dividiu com a Bia…). Fora de saída, uma linha por movimento no
  molde do painel: a ação no passado na linha e o detalhe curto embaixo ("Recebeu o Pix do Patrick", "Pagou as contas" ·
  "Celular e streamings"). Dias como título ("Hoje", "Ontem", "Sáb, 26/09").

O movimento guarda a chave do acontecimento desde 28/09 (`financas._mov`); os antigos acham a chave pelo título e pela
hora em `life_events`.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

DIAS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")
PREFIXOS = ("consumo:", "transporte:", "compra:", "freela:", "casa:", "meal:")


def _cap(t: str) -> str:
    return t[:1].upper() + t[1:] if t else t


def _hm(at: datetime) -> str:
    return f"{at:%H:%M}"


def _dia(d: date, hoje: date) -> str:
    gap = (hoje - d).days
    return "Hoje" if gap == 0 else "Ontem" if gap == 1 else f"{DIAS[d.weekday()]}, {d:%d/%m}"


# ------------------------------------------------------------------ chaves --
def _eventos(db, desde: str) -> dict[str, dict]:
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT event_key, event_at, title, summary FROM life_events WHERE event_at >= ? AND ("
            + " OR ".join("event_key LIKE ?" for _ in PREFIXOS) + ")",
            (desde, *(p + "%" for p in PREFIXOS))).fetchall()
    return {r["event_key"]: dict(r) for r in rows}


def _chave(mov: dict, eventos: dict[str, dict]) -> str:
    if mov.get("key"):
        return mov["key"]
    for k, ev in eventos.items():
        if str(ev["event_at"])[:16] != mov["at"][:16]:
            continue
        if ev["title"] == mov["desc"] or (mov["desc"] == "cachê do freela" and k.startswith("freela:")) \
                or (mov["desc"].startswith("contas dela") and k.endswith(":contas_dela")) \
                or (mov["desc"] == "delivery" and k.startswith("meal:")):
            return k
    return ""


def _grupo(key: str) -> str:
    """'consumo:outing:2026-09-27:c3:1' e 'transporte:commute:outing:2026-09-27:c3:ida' → 'outing:2026-09-27:c3'."""
    if key.startswith("consumo:"):
        return key[len("consumo:"):].rsplit(":", 1)[0]
    if key.startswith("transporte:commute:"):
        return key[len("transporte:commute:"):].rsplit(":", 1)[0]
    return ""


# ------------------------------------------------------------------ textos --
def _lugar_do_uber(summary: str) -> str:
    """'Pagou o uber indo pro Shopping da Gávea (R$ 35).' → 'Shopping da Gávea'; na volta, 'voltando do X pra casa'."""
    m = re.search(r"voltando (?:do|da|dos|das) (.+?) pra casa", summary or "")
    if m:
        return m.group(1)
    m = re.search(r".* (?:pro|pra|pros|pras) (.+?) \(R\$", summary or "")
    return m.group(1) if m else ""


def _nome_item(title: str) -> str:
    """'Drogarias Pacheco · Demaquilante Bioderma 250 ml' → 'Demaquilante Bioderma' (sem quantidade nem '(dividiu)')."""
    nome = title.split(" · ", 1)[-1].replace(" (dividiu)", "")
    palavras = []
    for p in nome.split():
        if any(ch.isdigit() for ch in p):
            break
        palavras.append(p)
    return " ".join(palavras) or nome


def _plural(n: int, nome: str) -> str:
    if n == 1:
        return nome
    return f"{n} {nome[:1].lower() + nome[1:]}{'s' if nome[-1:] in 'aeiou' else ''}"


def _lista(nomes: list[str]) -> str:
    nomes = [n if i == 0 else n[:1].lower() + n[1:] for i, n in enumerate(nomes)]
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _filho(mov: dict, key: str, ev: dict) -> dict:
    at = datetime.fromisoformat(mov["at"])
    summary = ev.get("summary") or ""
    if key.startswith("transporte:"):
        sub = "Ida" if key.endswith(":ida") else "Volta"
        m = re.search(r"dividido com (.+?)\)", summary)
        texto, sub = "Uber", sub + (f", dividiu com {m.group(1)}" if m else "")
    else:
        texto = _cap(mov["desc"].split(" · ", 1)[-1].replace(" (dividiu)", ""))
        m = re.search(r"^Dividiu .+? com (.+?) n[oa] ", summary)
        sub = f"Dividiu com {m.group(1)}" if m else ""
    return {"texto": texto, "sub": sub, "valor": mov["valor"], "hora": _hm(at), "at": at}


def _sozinho(mov: dict, key: str, ev: dict) -> dict:
    """Movimento fora de saída: ação no passado na linha, detalhe curto embaixo."""
    desc, summary = mov["desc"], ev.get("summary") or ""
    texto, sub = _cap(desc), ""
    if desc.startswith("pix do Patrick"):
        texto, sub = "Recebeu o Pix do Patrick", _cap(desc.partition(": ")[2])
    elif desc.startswith("presente do Patrick: "):
        texto, sub = "Usou o Pix do Patrick", _cap(desc.split(": ", 1)[1].split(" (ele disse:")[0])
    elif desc.startswith("delivery pro Patrick: "):
        texto, sub = "Mandou um delivery para o Patrick", _cap(desc.split(": ", 1)[1])
    elif desc == "devolveu o empréstimo do Patrick":
        texto = "Devolveu o empréstimo do Patrick"
    elif desc.startswith("contas dela"):
        texto, sub = "Pagou as contas", "Celular e streamings"
    elif key.startswith("freela:"):
        texto = "Recebeu metade do cachê" if key.endswith(":sinal") else "Recebeu o resto do cachê"
        m = re.search(r"\((.+?)\)", summary)
        sub = _cap(m.group(1)) if m else ""
    elif key.startswith("meal:") or desc == "delivery":
        texto = "Pediu delivery"
    elif key.startswith("compra:leitura:"):
        texto, sub = "Comprou um livro", desc
    elif desc.endswith(" · cabelo"):
        m = re.search(r": (.+?) · R\$", summary)
        texto, sub = f"Fez o cabelo na {desc.split(' · ')[0].split()[0]}", _cap(m.group(1)) if m else ""
    elif desc.endswith(" · unhas em gel"):
        m = re.search(r": (.+?)(?: — .+)? \(R\$", summary)
        texto, sub = f"Fez as unhas na {desc.split(' · ')[0].split()[0]}", "Em gel" + (f", {m.group(1)}" if m else "")
    elif " · " in desc:
        from vontade import no
        lugar, item = desc.split(" · ", 1)
        texto, sub = f"Comprou {no(lugar)}", _cap(item)
    at = datetime.fromisoformat(mov["at"])
    return {"texto": texto, "sub": sub, "valor": mov["valor"], "hora": _hm(at), "at": at, "filhos": []}


def _saida(filhos: list[tuple[dict, str, dict]]) -> dict:
    """Uma saída: 'Foi no Shopping da Gávea' · 'Cinema, pipoca, refri e uber', o total e os itens embaixo."""
    from vontade import no
    lugar = next((m["desc"].split(" · ")[0] for m, k, _ in filhos if k.startswith("consumo:") and " · " in m["desc"]),
                 "") or next((_lugar_do_uber(ev.get("summary", "")) for _, k, ev in filhos
                              if k.startswith("transporte:")), "")
    contagem: dict[str, int] = {}
    for m, k, _ in filhos:
        if k.startswith("consumo:"):
            nome = _nome_item(m["desc"])
            contagem[nome] = contagem.get(nome, 0) + 1
    nomes = [_plural(n, nome) for nome, n in contagem.items()]
    if any(k.startswith("transporte:") for _, k, _ in filhos):
        nomes.append("uber")
    itens = [_filho(m, k, ev) for m, k, ev in filhos]
    return {"texto": f"Foi {no(lugar)}" if lugar else "Saiu", "sub": _cap(_lista(nomes)) if nomes else "",
            "valor": sum(i["valor"] for i in itens), "hora": itens[0]["hora"], "at": itens[0]["at"],
            "filhos": itens if len(itens) > 1 else []}


def extrato_view(db, movs: list[dict], now: datetime) -> list[dict]:
    """[{'dia': 'Ontem', 'itens': [{texto, sub, valor, hora, filhos}]}], do mais novo pro mais velho."""
    if not movs:
        return []
    eventos = _eventos(db, min(m["at"] for m in movs)[:10])
    grupos: dict[str, list] = {}
    soltos = []
    for mov in sorted(movs, key=lambda m: m["at"]):
        key = _chave(mov, eventos)
        g = _grupo(key)
        if g:
            grupos.setdefault(g, []).append((mov, key, eventos.get(key, {})))
        else:
            soltos.append(_sozinho(mov, key, eventos.get(key, {})))
    itens = sorted(soltos + [_saida(f) for f in grupos.values()], key=lambda i: i["at"], reverse=True)
    dias: list[dict] = []
    for it in itens:
        rotulo = _dia(it["at"].date(), now.date())
        if not dias or dias[-1]["dia"] != rotulo:
            dias.append({"dia": rotulo, "itens": []})
        it.pop("at")
        for f in it["filhos"]:
            f.pop("at", None)
        dias[-1]["itens"].append(it)
    return dias


# -------------------------------------------------------------------- topo --
def _dia_das_contas(mes: date) -> int:
    from casa import _rng
    return 5 + _rng(mes.replace(day=1), "contas_dela").randint(0, 3)


def _contas(db, now: datetime) -> str:
    """'Dia 6, R$ 189'; pagas no mês, 'Pagas dia 6, R$ 189'; o dia passou sem conta (antes da vida registrada),
    a do mês que vem, 'Dia 7/10, R$ 189'. 04/10 (catálogo, leva 2): vírgula no lugar do "·"."""
    from financas import CONTAS_DELA
    dia = _dia_das_contas(now.date())
    with db.get_connection() as conn:
        paga = conn.execute("SELECT 1 FROM life_events WHERE event_key LIKE ? AND event_at <= ? LIMIT 1",
                            (f"casa:{now:%Y-%m}-%:contas_dela", now.isoformat())).fetchone()
    if paga:
        return f"Pagas dia {dia}, R$ {CONTAS_DELA}"
    if now.day <= dia:
        return f"Dia {dia}, R$ {CONTAS_DELA}"
    prox = (now.date().replace(day=28) + timedelta(days=4)).replace(day=1)
    return f"Dia {_dia_das_contas(prox)}/{prox:%m}, R$ {CONTAS_DELA}"


def _cache(db) -> str:
    from freela import Freela
    for st in Freela(db)._state().values():
        if st.get("step") == "a_receber" and st.get("pay_at"):
            return f"R$ {st.get('rest', st.get('pay'))}, até {datetime.fromisoformat(st['pay_at']):%d/%m}"
        if st.get("step") == "job_marcado" and st.get("rest") and st.get("job_at"):
            return f"R$ {st['rest']}, job dia {datetime.fromisoformat(st['job_at']):%d/%m}"
    return "Nenhum marcado"


def topo_view(db, st: dict, now: datetime) -> dict:
    mes = (st.get("meses") or {}).get(f"{now:%Y-%m}", {"entrou": 0, "saiu": 0})
    linhas = []
    for icone, rotulo, conta in (("briefcase", "Próximo cachê", _cache), ("receipt", "Contas", _contas)):
        try:
            linhas.append([icone, rotulo, conta(db) if conta is _cache else conta(db, now)])
        except Exception:
            pass
    return {"mes": MESES[now.month - 1], "entrou": mes["entrou"], "saiu": mes["saiu"], "linhas": linhas}
