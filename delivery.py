"""Delivery de verdade (24/09, conversa das 19h): "vou pedir pelo iFood" virava só fala.

Ela prometeu mandar foto do açaí quando chegasse, disse "ainda não chegou" e depois
"chegou" — tudo inventado na hora pelo modelo, e o /status nunca mostrou ela comendo.
Agora o pedido vira estado: hora do pedido, previsão de chegada (30–55 min); quando
chega, o Seu Jorge interfona, vira acontecimento do dia e ela passa a estar comendo.
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "delivery_json"
ETA_MIN = (30, 55)
EAT_MIN = (15, 30)
SHOW_AFTER_ARRIVAL = timedelta(hours=2)

_FOOD = r"(a[cç]a[ií]|pizza|hamb[uú]rguer|burger|sushi|japa|temaki|lanche|comida|poke|salada|pastel|esfiha)"
ORDER_RE = re.compile(
    r"\b(vou pedir|j[aá] pedi|acabei de pedir|pedi|t[oô] pedindo|vou pegar)\b[^.!?\n]{0,40}?"
    r"\b(ifood|delivery|rappi|" + _FOOD[1:-1] + r")\b",
    re.IGNORECASE)
FOOD_RE = re.compile(r"\b" + _FOOD + r"\b", re.IGNORECASE)


def _load(db) -> Optional[dict]:
    try:
        raw = db.get_estado_relacional(KEY)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _save(db, data: dict) -> None:
    db.set_estado_relacional(KEY, json.dumps(data, ensure_ascii=False))


HIST_KEY = "ifood_pedidos_json"
HIST_MAX = 30


def history(db) -> list[dict]:
    """Pedidos do Patrick pro app (aba Pedidos do iFood), do mais novo pro mais velho."""
    try:
        raw = db.get_estado_relacional(HIST_KEY)
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _remember(db, data: dict) -> None:
    hist = [{k: data.get(k) for k in ("what", "restaurant", "price", "note", "ordered_at", "eta_at",
                                             "loja_id", "logo", "itens") if data.get(k) is not None}] + history(db)
    db.set_estado_relacional(HIST_KEY, json.dumps(hist[:HIST_MAX], ensure_ascii=False))


def _contato_portaria(db, key: str, at: datetime) -> None:
    """26/09 (Patrick): pegar com o Seu Jorge é contato com ele — o Mundo mostrava 'sem contato'."""
    try:
        from social_world import SocialWorld
        SocialWorld(db).record(f"portaria:{key}", occurred_at=at.isoformat(), character_key="jorge_almeida",
                               valence=0.2, meaningful=True)
    except Exception:
        logger.warning("delivery.portaria.contato_falhou key=%s", key, exc_info=True)


def _what(text: str, fallback: str = "o pedido") -> str:
    m = FOOD_RE.search(text or "")
    return m.group(1).lower() if m else fallback


def observe(db, text: str, now: datetime, context: str = "") -> bool:
    """Fala dela ('vou pedir pelo iFood'): abre um pedido. context = conversa recente, pra achar o quê."""
    if not ORDER_RE.search(text or ""):
        return False
    from pedido_dela import is_offer
    if is_offer(text):
        return False                                   # "pedi um açaí pra você": é pro Patrick (pedido_dela)
    cur = _load(db)
    if cur and not cur.get("arrived_at"):
        return False                                   # já tem pedido a caminho
    rng = random.Random(f"delivery:{now.isoformat(timespec='minutes')}")
    what = _what(text, _what(context, "o pedido"))
    eta = now + timedelta(minutes=rng.randint(*ETA_MIN))
    _save(db, {"what": what, "ordered_at": now.isoformat(), "eta_at": eta.isoformat(), "arrived_at": None})
    logger.info("delivery.ordered what=%s eta=%s", what, eta.isoformat(timespec="minutes"))
    return True


def materialize(db, now: datetime) -> bool:
    """Chegou a hora: o pedido chega (acontecimento do dia) e ela passa a comer."""
    cur = _load(db)
    if not cur or cur.get("arrived_at") or cur.get("by") == "patrick":
        return False                                   # o presente dele é do gift_tick
    eta = datetime.fromisoformat(cur["eta_at"])
    if eta > now:
        return False
    cur["arrived_at"] = eta.isoformat()
    _save(db, cur)
    what = cur["what"]
    from meals import meal_kind
    key = f"meal:{eta.date().isoformat()}:{meal_kind(eta)}:delivery"
    end = eta + timedelta(minutes=random.Random(cur["ordered_at"]).randint(*EAT_MIN))
    meta, end = _saciedade(db, key, eta, end, what)
    # Vira A refeição do horário (o açaí das 19:55 é o jantar): a fome zera e o jantar
    # planejado do dia não sai em dobro (Meals pula tipo já registrado).
    with db.get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO life_events(event_key,event_at,end_at,event_type,title,summary,source_type,
               autonomy_level,importance,participants_json,share_worthy,metadata_json,created_at)
               VALUES (?,?,?,'meal','delivery',?,'simulated',1,0.2,?,0.5,?,?)""",
            (key, eta.isoformat(), end.isoformat(),
             f"O {what} do delivery chegou (o Seu Jorge interfonou) e ela foi comer.",
             json.dumps(["marina", "jorge_almeida"]), json.dumps(meta, ensure_ascii=False) if meta else None,
             now.isoformat()))
        conn.commit()
    _contato_portaria(db, f"delivery:{cur['ordered_at']}", eta)
    if end > now:
        raw = db.get_estado_relacional().get("pending_transition_json")
        busy = False
        try:
            busy = bool(raw) and datetime.fromisoformat(json.loads(raw)["end_at"]) > now
        except Exception:
            busy = False
        if not busy:
            db.set_estado_relacional("pending_transition_json", json.dumps({
                "routine_type": "meal", "activity": f"comendo o {what} em casa", "place_key": "marina_apartment",
                "announced_at": now.isoformat(), "transition_at": eta.isoformat(), "end_at": end.isoformat(),
                "dish": what}, ensure_ascii=False))
    logger.info("delivery.arrived what=%s at=%s", what, eta.isoformat(timespec="minutes"))
    return True


def _saciedade(db, key: str, at: datetime, end: datetime, what: str) -> tuple[Optional[dict], datetime]:
    """26/09: o presente/pedido é refeição de verdade — a fome cai enquanto ela come, e satisfeita
    ela guarda o resto (mesma regra do Meals)."""
    try:
        from meals import MealSlot, Meals, meal_kind
        kind = meal_kind(at)
        slot = MealSlot(kind, key, at, max(5, int((end - at).total_seconds() // 60)), "casa", what)
        sac = Meals(db).saciedade(slot)
        sac["prato"] = what
        return sac, at + timedelta(minutes=sac["minutos"])
    except Exception:
        logger.exception("delivery.saciedade")
        return None, end


# ------------------------------------------------- presente do Patrick (Mini App, 25/09) --
# Ele pede pelo app e ela não sabe: é surpresa. Quando o entregador chega, o mundo
# decide: em casa e acordada, ela recebe e (se não comeu há pouco) come; fora, dormindo
# ou no banho, fica com o Seu Jorge na portaria até ela poder pegar. Ele paga: o evento
# é "meal:…:presente", que as finanças não cobram (elas cobram só "meal:…:delivery").
GIFT_SHOW_AFTER = timedelta(hours=3)


def open_order(db) -> Optional[dict]:
    """Pedido ainda não resolvido (dela a caminho, ou presente não recebido)."""
    cur = _load(db)
    if not cur:
        return None
    if cur.get("by") == "patrick":
        return None if cur.get("status") == "recebido" else cur
    return None if cur.get("arrived_at") else cur


def gift(db, *, what: str, restaurant: str, price: int, eta_min: tuple, note: str, now: datetime,
         eats: bool = True, extra: Optional[dict] = None) -> Optional[dict]:
    """O Patrick manda comida pra ela. None se já tem pedido em aberto.
    extra: loja_id, logo e itens do iFood novo (vão pro histórico da aba Pedidos)."""
    if open_order(db):
        return None
    rng = random.Random(f"presente:{now.isoformat()}")
    eta = now + timedelta(minutes=rng.randint(*eta_min))
    data = {"by": "patrick", "what": what, "restaurant": restaurant, "price": int(price),
            "note": (note or "").strip()[:200], "eats": bool(eats), "ordered_at": now.isoformat(),
            "eta_at": eta.isoformat(), "arrived_at": None, "status": "a_caminho",
            "received_at": None, "waited": None, "ate_recently": False, "announced": False, **(extra or {})}
    _save(db, data)
    _remember(db, data)
    logger.info("delivery.gift what=%s eta=%s", what, eta.isoformat(timespec="minutes"))
    return data


def gift_tick(db, now: datetime, *, can_receive: bool, why_not: str = "", ate_recently: bool = False,
              transition_busy: bool = False) -> Optional[str]:
    """Anda o presente: 'portaria' (chegou e ela não pôde pegar) ou 'recebido'."""
    cur = _load(db)
    if not cur or cur.get("by") != "patrick" or cur.get("status") == "recebido":
        return None
    eta = datetime.fromisoformat(cur["eta_at"])
    if eta > now:
        return None
    if cur["status"] == "a_caminho":
        cur["arrived_at"] = eta.isoformat()
        if not can_receive:
            cur["status"], cur["waited"] = "portaria", why_not or "fora"
            _save(db, cur)
            logger.info("delivery.gift.portaria why=%s", cur["waited"])
            return "portaria"
    elif not can_receive:
        return None                                    # continua na portaria
    at = eta if cur["status"] == "a_caminho" else now
    cur.update(status="recebido", received_at=at.isoformat(), ate_recently=bool(ate_recently))
    _save(db, cur)
    what, rest = cur["what"], cur["restaurant"]
    portaria = " (tinha ficado na portaria com o Seu Jorge)" if cur.get("waited") else ""
    eats_now = cur.get("eats", True) and not ate_recently
    if eats_now:
        summary = f"O Patrick mandou de surpresa {what} do {rest} pelo app; ela recebeu{portaria} e foi comer."
    else:
        summary = (f"O Patrick mandou de surpresa {what} do {rest} pelo app; ela recebeu{portaria}"
                   + (" e guardou pra depois, porque tinha acabado de comer." if ate_recently else "."))
    if cur.get("note"):
        summary += f" Bilhete que ele escreveu pra ela: \"{cur['note']}\"."
    from meals import meal_kind
    key = (f"meal:{at.date().isoformat()}:{meal_kind(at)}:presente" if eats_now
           else f"presente:{at.isoformat(timespec='minutes')}")
    end = at + timedelta(minutes=random.Random(cur["ordered_at"]).randint(*EAT_MIN))
    meta, end = _saciedade(db, key, at, end, what) if eats_now else (None, end)
    if meta and meta.get("larga"):
        summary += " Comeu até ficar satisfeita e guardou o resto."
    elif meta and meta.get("excesso"):
        summary += " Comeu tudo, além da conta, e ficou estufada."

    with db.get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO life_events(event_key,event_at,end_at,event_type,title,summary,source_type,
               autonomy_level,importance,participants_json,share_worthy,metadata_json,created_at)
               VALUES (?,?,?,?,'presente do Patrick',?,'simulated',1,0.6,?,0.9,?,?)""",
            (key, at.isoformat(), end.isoformat() if eats_now else None, "meal" if eats_now else "gift", summary,
             json.dumps(["marina", "patrick", "jorge_almeida"]), json.dumps(meta, ensure_ascii=False) if meta else None,
             now.isoformat()))
        conn.commit()
    _contato_portaria(db, f"presente:{cur['ordered_at']}", at)
    if eats_now and end > now and not transition_busy:
        db.set_estado_relacional("pending_transition_json", json.dumps({
            "routine_type": "meal", "activity": f"comendo o {what} que o Patrick mandou", "place_key": "marina_apartment",
            "announced_at": now.isoformat(), "transition_at": at.isoformat(), "end_at": end.isoformat(),
            "dish": what}, ensure_ascii=False))
    logger.info("delivery.gift.recebido what=%s waited=%s ate_recently=%s", what, cur.get("waited"), ate_recently)
    return "recebido"


def gift_to_announce(db) -> Optional[dict]:
    cur = _load(db)
    if cur and cur.get("by") == "patrick" and cur.get("status") == "recebido" and not cur.get("announced"):
        return cur
    return None


def mark_announced(db) -> None:
    cur = _load(db)
    if cur:
        cur["announced"] = True
        _save(db, cur)


def prompt_lines(db, now: datetime) -> list[str]:
    cur = _load(db)
    if not cur:
        return []
    if cur.get("by") == "patrick":
        # Surpresa: até receber ela não sabe de nada.
        if cur.get("status") != "recebido" or not cur.get("received_at"):
            return []
        got = datetime.fromisoformat(cur["received_at"])
        if now - got > GIFT_SHOW_AFTER:
            return []
        line = (f"[DELIVERY] O Patrick te mandou de surpresa {cur['what']} do {cur['restaurant']} pelo app; "
                f"chegou pra você às {got:%H:%M}")
        if cur.get("ate_recently"):
            line += " (você tinha acabado de comer e guardou pra depois)"
        if cur.get("note"):
            # 26/09 (Evitar 031): "minha gatinha" no bilhete é ele falando de você, não o contrário.
            line += (f". Bilhete que ele escreveu pra você: \"{cur['note']}\" (é a voz dele: \"minha\"/\"meu\" ali "
                     "é ele falando de você)")
        return [line + "."]
    ordered = datetime.fromisoformat(cur["ordered_at"])
    if cur.get("arrived_at"):
        arrived = datetime.fromisoformat(cur["arrived_at"])
        if now - arrived > SHOW_AFTER_ARRIVAL:
            return []
        return [f"[DELIVERY] O {cur['what']} que você pediu chegou às {arrived:%H:%M}."]
    eta = datetime.fromisoformat(cur["eta_at"])
    return [f"[DELIVERY] Você pediu {cur['what']} às {ordered:%H:%M}; ainda não chegou "
            f"(o app diz que chega lá pelas {eta:%H:%M})."]
