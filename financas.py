"""O dinheiro dela e o /pix do Patrick (feedback FB-20260924-190751, decisões de 24/09).

Decisões do Patrick:
- Pix sem ela pedir: ela agradece e USA em algo concreto do mundo, e conta depois.
- Aperto de dinheiro: ela recorre SEMPRE a ele primeiro (não ao pai).
- Saldo de verdade, simples: cachês do freela + pix dele − contas dela − delivery − compras.
  O pai (Henrique) paga o apê e a comida; isso fica fora do saldo dela (D9).

Estado em estado_relacional[KEY] (JSON) — sem migration: o esquema é travado nos testes.
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "financas_json"
START_BALANCE = 640            # o que sobrou dos jobs de setembro quando a vida registrada começou
CONTAS_DELA = 189              # celular + streamings (casa :contas_dela)
DELIVERY_PRICE = {"açaí": 38, "acai": 38, "pizza": 72, "sushi": 95, "japa": 95, "hambúrguer": 54,
                  "hamburguer": 54, "burger": 54}
DELIVERY_DEFAULT = 55
EMERGENCY_WEEKLY_CHANCE = 0.12  # ~1 aperto a cada 2 meses
EMERGENCIES = (
    ("a tela do celular trincou e o conserto é caro", 380),
    ("levou uma multa por estacionar o patinete elétrico em lugar proibido", 195),
    ("o notebook que ela usa na facul deu pau e precisa de conserto", 450),
    ("a passagem pra ir em SP no aniversário da avó ficou mais cara do que ela tinha", 320),
)
GIFT_USES = ((60, "um açaí caprichado"), (150, "um skincare novo que ela tava namorando"),
             (300, "uma saída com as meninas"), (10**9, "um biquíni novo"))
RESERVE = 150                   # só devolve empréstimo se sobrar isso depois
_AMOUNT = re.compile(r"R\$\s*(\d+)")
MOVS_KEEP = 30


def _load(db) -> dict:
    try:
        raw = db.get_estado_relacional(KEY)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _save(db, st: dict) -> None:
    st["movs"] = st.get("movs", [])[-MOVS_KEEP:]
    st["vistos"] = st.get("vistos", [])[-300:]
    db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))


def _init(st: dict, now: datetime) -> dict:
    if "saldo" not in st:
        st.update(saldo=START_BALANCE, desde=now.isoformat(), vistos=[], movs=[], emprestimos=[],
                  pedido=None, presente=None)
    return st


def _mov(st: dict, at: datetime, valor: int, desc: str) -> None:
    st["saldo"] = int(st["saldo"]) + int(valor)
    st["movs"].append({"at": at.isoformat(timespec="minutes"), "valor": int(valor), "desc": desc})


def _event(db, key: str, at: datetime, summary: str, now: datetime, share: float = 0.6) -> None:
    with db.get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
               autonomy_level,importance,participants_json,share_worthy,created_at)
               VALUES (?,?,'money','dinheiro',?,'simulated',1,0.4,'["marina"]',?,?)""",
            (key, at.isoformat(), summary, share, now.isoformat()))
        conn.commit()


def _delivery_price(summary: str) -> int:
    low = summary.lower()
    return next((p for w, p in DELIVERY_PRICE.items() if w in low), DELIVERY_DEFAULT)


# ------------------------------------------------------------------ mundo --
def materialize(db, now: datetime) -> int:
    """Cachês e gastos que aconteceram viram saldo; apertos, devoluções e o uso do presente."""
    st = _init(_load(db), now)
    desde = st["desde"]
    changed = 0
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT event_key, event_at, summary FROM life_events WHERE event_at>=? AND event_at<=?
               AND (event_key LIKE 'freela:%:sinal' OR event_key LIKE 'freela:%:cache'
                    OR event_key LIKE 'casa:%:contas_dela' OR event_key LIKE 'meal:%:delivery')
               ORDER BY event_at""", (desde, now.isoformat()))]
    for row in rows:
        if row["event_key"] in st["vistos"]:
            continue
        at = datetime.fromisoformat(row["event_at"])
        key = row["event_key"]
        if key.startswith("freela:"):
            m = _AMOUNT.search(row["summary"] or "")
            if m:
                _mov(st, at, int(m.group(1)), "cachê do freela")
        elif key.endswith(":contas_dela"):
            _mov(st, at, -CONTAS_DELA, "contas dela (celular e streamings)")
        else:
            _mov(st, at, -_delivery_price(row["summary"] or ""), "delivery")
        st["vistos"].append(key)
        changed += 1
        if key.endswith(":cache"):
            changed += _repay(db, st, at, now)

    changed += _emergency(db, st, now)
    if st["saldo"] < 0 and not st.get("pedido"):
        st["pedido"] = {"valor": -st["saldo"] + 100, "motivo": "o dinheiro do mês acabou antes do cachê cair",
                        "at": now.isoformat()}
        _event(db, f"financas:{now:%Y-%m-%d}:aperto", now,
               "O dinheiro dela acabou antes do próximo cachê; vai pedir ajuda pro Patrick.", now, 0.8)
        changed += 1
    gift = st.get("presente")
    if gift and datetime.fromisoformat(gift["usar_em"]) <= now:
        at = datetime.fromisoformat(gift["usar_em"])
        _mov(st, at, -int(gift["gasto"]), f"presente do Patrick: {gift['uso']}")
        _event(db, f"financas:{at:%Y-%m-%dT%H%M}:presente_usado", at,
               f"Usou o pix do Patrick: comprou {gift['uso']} (R$ {gift['gasto']}).", now, 0.8)
        st["presente"] = None
        changed += 1
    _save(db, st)
    return changed


def _emergency(db, st: dict, now: datetime) -> int:
    """Aperto raro e determinístico por semana; ela pede pro Patrick (sempre ele primeiro)."""
    if st.get("pedido"):
        return 0
    week = now.date() - timedelta(days=now.weekday())
    rng = random.Random(f"financas-emergencia:{week.isoformat()}")
    if rng.random() >= EMERGENCY_WEEKLY_CHANCE:
        return 0
    at = datetime.combine(week + timedelta(days=rng.randint(0, 6)), datetime.min.time()) + \
        timedelta(minutes=rng.randint(9 * 60, 21 * 60))
    key = f"financas:{at:%Y-%m-%d}:emergencia"
    if at > now or at < datetime.fromisoformat(st["desde"]) or key in st["vistos"]:
        return 0
    motivo, valor = rng.choice(EMERGENCIES)
    st["pedido"] = {"valor": valor, "motivo": motivo, "at": at.isoformat()}
    st["vistos"].append(key)
    _event(db, key, at, f"Aperto: {motivo} (R$ {valor}). Vai pedir ajuda pro Patrick.", now, 0.9)
    return 1


def _repay(db, st: dict, at: datetime, now: datetime) -> int:
    """Caiu cachê e sobra folga: devolve o que deve pro Patrick."""
    done = 0
    for loan in st.get("emprestimos", []):
        if loan.get("devolvido_at") or st["saldo"] - loan["valor"] < RESERVE:
            continue
        _mov(st, at, -loan["valor"], "devolveu o empréstimo do Patrick")
        loan["devolvido_at"] = at.isoformat()
        _event(db, f"financas:{at:%Y-%m-%dT%H%M}:devolveu", at,
               f"Caiu o cachê e ela fez o pix de volta pro Patrick: R$ {loan['valor']} ({loan['motivo']}).",
               now, 0.9)
        done += 1
    return done


# ------------------------------------------------------------------- /pix --
def receive_pix(db, valor: int, nota: str, now: datetime) -> dict:
    """Pix do Patrick. Com pedido em aberto vira empréstimo; sem pedido, presente que ela vai usar."""
    st = _init(_load(db), now)
    _mov(st, now, valor, f"pix do Patrick{': ' + nota if nota else ''}")
    pedido = st.get("pedido")
    if pedido:
        kind = "emprestimo"
        st.setdefault("emprestimos", []).append(
            {"valor": min(valor, int(pedido["valor"])), "motivo": pedido["motivo"], "at": now.isoformat()})
        st["pedido"] = None if valor >= int(pedido["valor"]) else {**pedido, "valor": int(pedido["valor"]) - valor}
    else:
        kind = "presente"
        uso = next(u for limite, u in GIFT_USES if valor <= limite)
        if nota:
            uso = f"{uso} (ele disse: {nota})"
        rng = random.Random(f"pix:{now.isoformat()}")
        st["presente"] = {"valor": valor, "gasto": min(valor, max(20, int(valor * rng.uniform(0.7, 1.0)))),
                          "uso": uso, "usar_em": (now + timedelta(hours=rng.randint(2, 20))).isoformat()}
    _event(db, f"financas:{now:%Y-%m-%dT%H%M%S}:pix", now,
           f"O Patrick fez um pix de R$ {valor} pra ela" + (f" ('{nota}')" if nota else "") +
           (" pra cobrir o aperto." if kind == "emprestimo" else " de presente."), now, 0.7)
    _save(db, st)
    logger.info("financas.pix valor=%s kind=%s saldo=%s", valor, kind, st["saldo"])
    return {"kind": kind, "saldo": st["saldo"]}


def parse_value(text: str) -> Optional[int]:
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", (text or "").replace("R$", ""))
    if not m:
        return None
    try:
        return int(round(float(m.group(1).replace(",", "."))))
    except ValueError:
        return None


# ----------------------------------------------------------------- prompt --
def prompt_lines(db, now: datetime) -> list[str]:
    st = _load(db)
    if "saldo" not in st:
        return []
    lines = [f"[SEU DINHEIRO] Saldo seu: R$ {st['saldo']} (cachês dos jobs e pix do Patrick; o pai paga o apê "
             f"e a comida)."]
    pedido = st.get("pedido")
    if pedido:
        lines.append(f"Aperto: {pedido['motivo']} — faltam R$ {pedido['valor']}. Quem você procura primeiro é o "
                     "Patrick: peça pra ele com jeitinho e um pouco de vergonha, prometendo devolver com o "
                     "próximo cachê (se já pediu, não repita; espere ele).")
    devendo = sum(e["valor"] for e in st.get("emprestimos", []) if not e.get("devolvido_at"))
    if devendo:
        lines.append(f"Você deve R$ {devendo} ao Patrick; devolve quando cair o próximo cachê.")
    gift = st.get("presente")
    if gift:
        lines.append(f"O Patrick te deu R$ {gift['valor']} de presente; você vai usar em {gift['uso']}.")
    return lines
