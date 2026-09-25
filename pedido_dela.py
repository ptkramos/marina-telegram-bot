"""Delivery que a Marina manda PRO Patrick (25/09, ideia do Patrick).

Às 12:17 ela disse "vou te mandar um suquinho pelo app pra vc não precisar levantar" e
nada aconteceu: fala que vira nada, como o açaí dela antes do delivery.py. Agora:

- **Ela oferece na conversa** ("vou te mandar um suquinho pelo app") → vira pedido de
  verdade: item do cardápio do Mini App, sai do saldo dela, previsão de chegada.
- **De surpresa**, quando ele está doente ou teve um dia ruim (decisão do Patrick: "isso é
  lindo na relação"), às vezes ela manda sem avisar.
- **Chat é chat, app é app** (Patrick, 25/09: "nada de notificação no chat, polui"): a
  mensagem dela em que ela conta que mandou ganha um botão "🛵 Acompanhar entrega", como
  quem compartilha o link do iFood, e o acompanhamento (a caminho → entregue) fica no card
  do Mini App. Ela sabe o que mandou e quando chegou (prompt_lines), então não oferece de
  novo nem pergunta se chegou.
- Sem limite por dia (decisão do Patrick: "ela vai respeitar"); só um pedido por vez e
  só se o saldo dela deixar.

Estado em estado_relacional[KEY] (JSON), sem migration.
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "pedido_pro_patrick_json"
SHOW_AFTER_DELIVERY = timedelta(hours=3)

# "vou te mandar um suquinho pelo app", "já pedi um açaí pra você", "te mandei uma canja"
OFFER_RE = re.compile(
    r"\b(?:vou\s+te\s+(?:mandar|pedir|enviar)|te\s+mand(?:ei|o)|j[aá]\s+te\s+mandei|"
    r"(?:vou\s+pedir|j[aá]\s+pedi|acabei\s+de\s+pedir|pedi)\b[^.!?\n]{0,40}\bpra\s+(?:voc[eê]|vc|tu|ti))"
    r"[^.!?\n]{0,60}", re.IGNORECASE)
_DELIVERY_HINT_RE = re.compile(r"\b(?:app|ifood|delivery|rappi|entrega|motoboy)\b", re.IGNORECASE)
_NOT_NOW_RE = re.compile(r"\b(?:se\s+(?:voc[eê]|vc)\s+quiser|quer\s+que\s+eu|posso\s+te)\b", re.IGNORECASE)
# "depois eu te mando foto do açaí" (24/09) não é delivery
_NOT_FOOD_RE = re.compile(r"\b(?:fot(?:o|inho|inha)|[aá]udio|mensagem|msg|print|beij|v[ií]deo|nude|localiza|link)",
                          re.IGNORECASE)

# palavra dela → (restaurante, item) no webapp/cardapio.json
ITEM_WORDS = (
    (r"canja|caldo", ("caldo-e-cia", "canja")),
    (r"sop(?:a|inha)", ("caldo-e-cia", "sopa-legumes")),
    (r"suco\s+verde", ("acai-da-praia", "suco-verde")),
    (r"suco|suquinho", ("acai-da-praia", "suco-laranja")),
    (r"picol[eé]|sorvete", ("doceria-sorocaba", "picoles")),
    (r"a[cç]a[ií]", ("acai-da-praia", "acai-500")),
    (r"pizza", ("pizzaria-do-largo", "margherita")),
    (r"sushi|japa|japon[eê]s|temaki|poke", ("japa-botafogo", "temaki-salmao")),
    (r"hamb[uú]rguer|burger|lanche", ("burger-da-voluntarios", "smash")),
    (r"brigadeiro|docinho|doce", ("doceria-sorocaba", "brigadeiros")),
    (r"bolo", ("doceria-sorocaba", "bolo-pote")),
)
FALLBACK_SICK = ("caldo-e-cia", "canja")
FALLBACK = ("doceria-sorocaba", "brigadeiros")

# surpresa: quando ele está doente ou teve um dia ruim
BAD_DAY_RE = re.compile(
    r"\bdia\s+(?:horr[ií]vel|p[eé]ssimo|ruim|dif[ií]cil|puxado|cansativo)\b|\bt[oô]\s+(?:mal|triste|pra\s+baixo|"
    r"estressad[oa]|arrasad[oa]|acabad[oa])\b|\bfoi\s+uma\s+merda\b", re.IGNORECASE)
SURPRISE_CHANCE = 0.5            # por episódio (dia + motivo)
SURPRISE_DELAY_MIN = (8, 45)     # ela pensa um pouco antes de pedir
SURPRISE_WINDOW = timedelta(hours=4)
SURPRISE_ITEMS = {"doente": [("caldo-e-cia", "canja"), ("doceria-sorocaba", "picoles"),
                             ("acai-da-praia", "suco-laranja")],
                  "dia_ruim": [("doceria-sorocaba", "brigadeiros"), ("acai-da-praia", "acai-500"),
                               ("burger-da-voluntarios", "smash")]}


def _load(db) -> dict:
    try:
        raw = db.get_estado_relacional(KEY)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _save(db, st: dict) -> None:
    db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))


def current(db) -> Optional[dict]:
    return _load(db).get("pedido")


def open_order(db) -> Optional[dict]:
    p = current(db)
    return p if p and p.get("status") == "a_caminho" else None


def _item(cardapio: dict, ref: tuple) -> tuple:
    rest_id, item_id = ref
    for rest in cardapio["restaurantes"]:
        if rest["id"] == rest_id:
            for item in rest["itens"]:
                if item["id"] == item_id:
                    return rest, item
    raise KeyError(ref)


def pick(cardapio: dict, text: str, *, sick: bool = False) -> tuple:
    low = (text or "").casefold()
    for pattern, ref in ITEM_WORDS:
        if re.search(rf"\b(?:{pattern})\b", low):
            return _item(cardapio, ref)
    return _item(cardapio, FALLBACK_SICK if sick else FALLBACK)


def is_offer(line: str) -> bool:
    """Ela disse que vai mandar/mandou algo pra ele (e não só perguntou se ele quer)."""
    m = OFFER_RE.search(line or "")
    if not m or _NOT_NOW_RE.search(line or ""):
        return False
    seg = m.group(0)
    if _NOT_FOOD_RE.search(seg):
        return False
    return bool(_DELIVERY_HINT_RE.search(seg)
                or any(re.search(rf"\b(?:{p})\b", seg.casefold()) for p, _ in ITEM_WORDS))


def place(db, cardapio: dict, rest: dict, item: dict, now: datetime, *, surprise: bool, note: str = "") -> Optional[dict]:
    """Faz o pedido: sai do saldo dela. None se já tem um a caminho ou o saldo não deixa."""
    if open_order(db):
        return None
    import financas
    financas.materialize(db, now)
    if financas.spend(db, int(item["preco"]), f"delivery pro Patrick: {item['curto'].lower()}", now) is None:
        logger.info("pedido_dela.sem_saldo item=%s", item["id"])
        return None
    rng = random.Random(f"pedido-dela:{now.isoformat()}")
    eta = now + timedelta(minutes=rng.randint(*rest.get("eta", (30, 45))))
    order = {"what": item["nome"], "short": item["curto"], "restaurant": rest["nome"], "price": int(item["preco"]),
             "ordered_at": now.isoformat(), "eta_at": eta.isoformat(), "status": "a_caminho",
             "delivered_at": None, "surprise": surprise, "note": (note or "")[:160]}
    st = _load(db)
    st["pedido"] = order
    _save(db, st)
    with db.get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
               autonomy_level,importance,participants_json,share_worthy,created_at)
               VALUES (?,?,'gift','presente pro Patrick',?,'simulated',1,0.6,'["marina","patrick"]',0.4,?)""",
            (f"pra_ele:{now.isoformat(timespec='minutes')}", now.isoformat(),
             f"Mandou {item['nome']} do {rest['nome']} pro Patrick pelo app" + (" de surpresa" if surprise else "")
             + f" (R$ {item['preco']}).", now.isoformat()))
        conn.commit()
    logger.info("pedido_dela.placed item=%s surprise=%s eta=%s", item["id"], surprise, eta.isoformat(timespec="minutes"))
    return order


def observe_marina_line(db, cardapio: dict, line: str, context: str, now: datetime, *, sick: bool = False) -> Optional[dict]:
    """Depois que a fala dela saiu: se ela prometeu mandar algo, o pedido acontece."""
    if not is_offer(line) or open_order(db):
        return None
    rest, item = pick(cardapio, line + " " + (context or ""), sick=sick)
    return place(db, cardapio, rest, item, now, surprise=False)


def tick(db, now: datetime) -> Optional[str]:
    """Entrega quando dá a hora. Devolve 'entregue' na transição."""
    st = _load(db)
    p = st.get("pedido")
    if not p or p["status"] != "a_caminho" or datetime.fromisoformat(p["eta_at"]) > now:
        return None
    p["status"], p["delivered_at"] = "entregue", p["eta_at"]
    _save(db, st)
    logger.info("pedido_dela.entregue what=%s", p["what"])
    return "entregue"


# -------------------------------------------------------------- surpresa --
def surprise_reason(his_recent: list[tuple[datetime, str]], now: datetime) -> Optional[str]:
    """Motivo pra ela mandar algo sem avisar: ele doente ou num dia ruim, dito nas últimas horas."""
    from health import PATRICK_SICK_RE
    recent = [t for at, t in his_recent if now - at <= SURPRISE_WINDOW]
    if any(PATRICK_SICK_RE.search(t or "") for t in recent):
        return "doente"
    if any(BAD_DAY_RE.search(t or "") for t in recent):
        return "dia_ruim"
    return None


def plan_surprise(db, reason: str, now: datetime) -> Optional[datetime]:
    """Decide uma vez por episódio (dia + motivo) se ela vai mandar algo, e quando."""
    st = _load(db)
    key = f"{now.date().isoformat()}:{reason}"
    decided = st.setdefault("surpresas", {})
    if key not in decided:
        rng = random.Random(f"surpresa:{key}")
        go = rng.random() < SURPRISE_CHANCE
        at = now + timedelta(minutes=rng.randint(*SURPRISE_DELAY_MIN)) if go else None
        decided[key] = {"go": go, "at": at.isoformat() if at else None, "done": False}
        st["surpresas"] = dict(list(decided.items())[-20:])
        _save(db, st)
        logger.info("pedido_dela.surpresa_decidida key=%s go=%s", key, go)
    entry = decided.get(key) or {}
    if not entry.get("go") or entry.get("done"):
        return None
    return datetime.fromisoformat(entry["at"])


def mark_surprise_done(db, reason: str, now: datetime) -> None:
    st = _load(db)
    entry = st.get("surpresas", {}).get(f"{now.date().isoformat()}:{reason}")
    if entry:
        entry["done"] = True
        _save(db, st)


def surprise_item(cardapio: dict, reason: str, now: datetime) -> tuple:
    options = SURPRISE_ITEMS.get(reason) or [FALLBACK]
    return _item(cardapio, random.Random(f"surpresa-item:{now.date()}:{reason}").choice(options))


# ---------------------------------------------------------------- prompt --
def prompt_lines(db, now: datetime) -> list[str]:
    p = current(db)
    if not p:
        return []
    ordered = datetime.fromisoformat(p["ordered_at"])
    how = " de surpresa" if p.get("surprise") else ""
    if p["status"] == "a_caminho":
        eta = datetime.fromisoformat(p["eta_at"])
        return [f"[SEU PEDIDO PRO PATRICK] Você mandou{how} {p['what']} do {p['restaurant']} pra ele pelo app às "
                f"{ordered:%H:%M} (R$ {p['price']}, do seu dinheiro); o app diz que chega lá pelas {eta:%H:%M}. "
                "Ele acompanha a entrega pelo link que você mandou. Não ofereça de novo."]
    got = datetime.fromisoformat(p["delivered_at"])
    if now - got > SHOW_AFTER_DELIVERY:
        return []
    return [f"[SEU PEDIDO PRO PATRICK] O {p['what']} que você mandou{how} pra ele foi entregue às {got:%H:%M} "
            "(o app mostrou a entrega). Você não precisa perguntar se chegou; se ele não comentou, pode perguntar "
            "se ele gostou, uma vez."]
