"""Promessa de avisar quando chegar (feedback do Patrick, 23/09).

Ela disse "te aviso assim que chegar no shopping, prometo" e não avisou; ele
cobrou 45 min depois ("esqueceu de avisar né"). O bot não tinha como cumprir:
a fala virava texto e mais nada. Agora a promessa vira um lembrete dela,
amarrado ao trajeto real do mundo (commute.py): quando a perna termina, ela
avisa com a própria voz.

Soak, dia 4 (02/10, Quartinho): "Assim que eu sair te mando mensagem E quando chegar no Quartinho também" — a
saída nem virou promessa (só "quando sair" contava, e só pra casa) e a chegada foi "esquecida" por sorteio (5%).
O Patrick decidiu (03/10): sem sorteio — ela cumpre o que prometeu; e avisa sozinha quando é de bom tom (volta pra
casa de rolê à noite, ou quando ele já cobrou o aviso naquele dia). Cabem várias promessas ao mesmo tempo (saída e
chegada), e a hora do aviso segue o trajeto de agora (com atraso), não o planejado quando ela prometeu.

Nada aqui chama LLM ou rede.
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, time, timedelta
from typing import Optional

KEY = "arrival_promise_json"          # lista de promessas (até 02/10 era uma só)
FEITAS_KEY = "arrival_promise_implicitas"
LATE_MIN = (2, 6)                 # tira o sapato, larga a bolsa, aí avisa
LEAVE_MIN = (0, 2)                # entrou no uber / saiu andando: avisa logo
LOOKAHEAD = timedelta(minutes=90)  # perna que ainda vai começar
# 27/09 (volta do Quartinho): "te aviso quando chegar em casa" às 21:39, com a volta só às 23:59 —
# ficava fora dos 90 min e a promessa não era gravada. A volta pra casa vale até o fim da noite.
LOOKAHEAD_HOME = timedelta(hours=12)
NOITE = time(21, 0)               # volta de rolê a partir daqui: avisa que chegou sem ele pedir

_PROMISE_RE = re.compile(r"\b(?:te\s+)?aviso\b|\bte\s+(?:mando|dou)\s+(?:um\s+)?(?:sinal|not[ií]cia|mensagem|msg)",
                         re.I)
_ARRIVE_RE = re.compile(r"\bcheg(?:ar|o|ue|uei|ando)\b", re.I)
_HOME_RE = re.compile(r"\b(?:casa|ap[eê]|apartamento)\b", re.I)
_ARRIVED_RE = re.compile(r"\bcheguei\b", re.I)
_OTHER_RE = re.compile(r"\bcheg\w*\s+n[oa]s?\s+(?!casa\b|ap[eê]\b|apartamento\b)\w+", re.I)
# 27/09, 19:42: "te aviso quando estiver indo pra casa" (ele ia pedir comida) — promessa de SAÍDA, não de chegada.
_LEAVE_RE = re.compile(r"\b(?:estiver|tiver|for|t[oô])\s+(?:indo|voltando)\s+(?:pra|para)\s+casa\b"
                       r"|\bquando\s+(?:eu\s+)?(?:for\s+embora|for\s+pra\s+casa|pedir\s+o\s+uber|entrar\s+no\s+uber)",
                       re.I)
# 02/10, 19:51: "Assim que eu sair te mando mensagem" / "Quando estiver saindo me avisa" — sair pro próximo trecho.
_SAIR_RE = re.compile(r"\b(?:assim\s+que|quando|logo\s+que)\s+(?:eu\s+)?(?:sair|estiver\s+saindo|for\s+sair|"
                      r"t[oô]\s+saindo)\b", re.I)
_LEFT_RE = re.compile(r"\b(?:indo|voltando)\s+pra\s+casa\b|\bsa[ií]\b|\bsaindo\b|\bno\s+uber\b", re.I)
# o Patrick cobrou o aviso naquele dia: daí em diante ela avisa toda chegada (02/10, 20:30 e 23:28)
_COBROU_RE = re.compile(r"\besquec\w*\s+de\s+(?:me\s+)?avisar\b|\bn[aã]o\s+(?:me\s+)?avisou\b|\bnem\s+avisou\b",
                        re.I)


def _load(db) -> list[dict]:
    raw = db.get_estado_relacional(KEY)
    try:
        data = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        data = []
    if isinstance(data, dict):            # o formato de antes (uma promessa só)
        data = [data]
    return [p for p in data if isinstance(p, dict) and p.get("leg")]


def _save(db, promises: list[dict]) -> None:
    db.set_estado_relacional(KEY, json.dumps(promises, ensure_ascii=False) if promises else "")


def _add(db, promise: dict) -> dict:
    outras = [p for p in _load(db) if (p["leg"], p.get("kind")) != (promise["leg"], promise.get("kind"))]
    _save(db, outras + [promise])
    return promise


def observe(db, her_line: str, his_last: str, now: Optional[datetime] = None) -> Optional[dict]:
    """Se a fala dela promete avisar a saída e/ou a chegada, amarra cada promessa ao trajeto real.
    Devolve a primeira promessa gravada (ou None)."""
    now = now or datetime.now()
    text, his = her_line or "", his_last or ""
    if not _PROMISE_RE.search(text):
        return None
    feitas = []
    if _LEAVE_RE.search(text) or (_LEAVE_RE.search(his) and not _ARRIVE_RE.search(text)):
        feitas.append(_observe_leave(db, now, so_volta=True))
    else:
        if _SAIR_RE.search(text) or _SAIR_RE.search(his):
            feitas.append(_observe_leave(db, now, so_volta=False))
        if _ARRIVE_RE.search(text) or _ARRIVE_RE.search(his):
            feitas.append(_observe_arrive(db, text, his, now))
    feitas = [p for p in feitas if p]
    return feitas[0] if feitas else None


def _observe_arrive(db, text: str, his: str, now: datetime) -> Optional[dict]:
    # a fala dela manda: "chegar no shopping" não vira casa só porque ele escreveu "casa"
    home = bool(_HOME_RE.search(text)) or (not _OTHER_RE.search(text) and bool(_HOME_RE.search(his)))
    leg = _target_leg(db, now, home=home)
    if leg is None:
        return None
    return _add(db, _promessa(leg, now, "chegada"))


def _promessa(leg, now: datetime, kind: str) -> dict:
    if kind == "saida":
        rng = random.Random(f"aviso:{leg.key}:saida")
        depois = rng.randint(*LEAVE_MIN)
        base, where = leg.start, leg.destination
    else:
        rng = random.Random(f"aviso:{leg.key}")
        depois = rng.randint(*LATE_MIN)
        base = leg.end
        where = "em casa" if leg.direction == "volta" else leg.destination.replace("pra ", "na ").replace("pro ", "no ")
    return {"made_at": now.isoformat(), "leg": leg.key, "kind": kind, "direction": leg.direction,
            "depois_min": depois, "due_at": (base + timedelta(minutes=depois)).isoformat(),
            "where": where, "how": leg.how}


def _observe_leave(db, now: datetime, *, so_volta: bool) -> Optional[dict]:
    """Avisa quando SAIR: amarrada ao começo do próximo trecho (`so_volta`: só a volta pra casa)."""
    legs = _legs(db, now)
    if legs is None:
        return None
    janela = LOOKAHEAD_HOME if so_volta else LOOKAHEAD
    proximos = [leg for leg in legs if (leg.direction == "volta" or not so_volta)
                and leg.start >= now - timedelta(minutes=1) and leg.start <= now + janela]
    if not proximos:
        return None
    return _add(db, _promessa(min(proximos, key=lambda leg: leg.start), now, "saida"))


def _legs(db, now: datetime):
    try:
        from commute import Commute
        c = Commute(db)
        return [leg for day in (now.date() - timedelta(days=1), now.date()) for leg in c.legs_on(day)]
    except Exception:
        return None


def _target_leg(db, now: datetime, *, home: bool):
    legs = _legs(db, now)
    if legs is None:
        return None
    live = [leg for leg in legs if leg.end > now and leg.start <= now + LOOKAHEAD]
    if home:
        voltas = [leg for leg in legs if leg.direction == "volta" and leg.end > now
                  and leg.start <= now + LOOKAHEAD_HOME]
        live = voltas or live
    return min(live, key=lambda leg: leg.end) if live else None


def _cobrou_hoje(db, now: datetime) -> bool:
    desde = datetime.combine(now.date() if now.hour >= 5 else now.date() - timedelta(days=1), time(5, 0))
    with db.get_connection() as conn:
        rows = conn.execute("SELECT content FROM conversas WHERE role='user' AND timestamp>=? AND timestamp<=?",
                            (desde.isoformat(), now.isoformat())).fetchall()
    return any(_COBROU_RE.search(r["content"] or "") for r in rows)


def implicitas(db, now: Optional[datetime] = None) -> Optional[dict]:
    """De bom tom (Patrick, 03/10): voltando pra casa de um rolê à noite — ou, se ele já cobrou o aviso no dia,
    em qualquer chegada de rolê — ela avisa que chegou sem ninguém pedir. Uma vez por trecho."""
    now = now or datetime.now()
    legs = _legs(db, now)
    if not legs:
        return None
    try:
        feitas = set(json.loads(db.get_estado_relacional(FEITAS_KEY) or "[]"))
    except (TypeError, ValueError):
        feitas = set()
    cobrou = None
    for leg in legs:
        if ":outing:" not in leg.key or leg.key in feitas or not (leg.start <= now < leg.end):
            continue
        noite = leg.direction == "volta" and (leg.start.time() >= NOITE or leg.start.time() < time(5, 0))
        if not noite:
            cobrou = _cobrou_hoje(db, now) if cobrou is None else cobrou
            if not cobrou:
                continue
        feitas.add(leg.key)
        db.set_estado_relacional(FEITAS_KEY, json.dumps(sorted(feitas)[-20:]))
        if any(p["leg"] == leg.key and p.get("kind") == "chegada" for p in _load(db)):
            continue                                     # ela já tinha prometido
        promessa = _promessa(leg, now, "chegada")
        promessa["made_at"] = leg.start.isoformat()      # o que ela disse desde que saiu conta ("cheguei")
        promessa["de_bom_tom"] = True
        return _add(db, promessa)
    return None


def _due_at(p: dict, legs: Optional[list]) -> datetime:
    """A hora do aviso pelo trajeto de agora (o atraso empurra), ou a gravada se o trecho sumiu."""
    leg = next((leg for leg in legs or () if leg.key == p["leg"]), None)
    if leg is not None and "depois_min" in p:
        base = leg.start if p.get("kind") == "saida" else leg.end
        return base + timedelta(minutes=p["depois_min"])
    return datetime.fromisoformat(p["due_at"])


def due(db, now: Optional[datetime] = None) -> Optional[dict]:
    """Uma promessa venceu e ela ainda não avisou? Devolve e tira da lista (uma vez só)."""
    now = now or datetime.now()
    promessas = _load(db)
    if not promessas:
        if db.get_estado_relacional(KEY):
            _save(db, [])
        return None
    legs = _legs(db, now)
    restantes, venceu = [], None
    for p in promessas:
        try:
            quando = _due_at(p, legs)
        except (TypeError, ValueError, KeyError):
            continue                                     # promessa estragada: some
        if venceu is not None or now < quando:
            restantes.append(p)
        elif now - quando <= timedelta(hours=2):         # já passou muito: some sem aviso
            venceu = p
    _save(db, restantes)
    if venceu is None:
        return None
    with db.get_connection() as conn:
        rows = conn.execute("SELECT content FROM conversas WHERE role='assistant' AND timestamp>?",
                            (venceu["made_at"],)).fetchall()
    ja_disse = _LEFT_RE if venceu.get("kind") == "saida" else _ARRIVED_RE
    if any(ja_disse.search(r["content"] or "") for r in rows):
        return None   # já contou na conversa que chegou (ou que saiu)
    return venceu
