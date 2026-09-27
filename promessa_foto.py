"""Promessa de foto vira foto (25/09, pedido do Patrick).

Na conversa das 15:22–15:34 ela prometeu "vou te mandar uma foto do bolo quando eu abrir" e
"tô separando as duas opções aqui na cama... jaja te mando" — e nada mandava depois: a
promessa virava um open loop que ninguém cumpria. Agora a promessa vira compromisso com hora:

- **looks**: "duas opções", "os finalistas", "o look" → 2 fotos no espelho do closet, mesma
  cena e roupas de sair diferentes (1 se ela falou de um look só), com legenda perguntando;
- **comida/objeto**: "foto do bolo" → selfie mostrando a comida (pose mostrando_comida);
- **selfie**: foto genérica.

Quando: "jaja/já já/daqui a pouco" → 3–10 min; "depois/mais tarde/quando eu abrir" → 20–50 min;
senão 5–15 min. Se ele pedir foto antes, a foto normal cumpre a promessa (sem foto em dobro).
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

KEY = "promessas_foto_json"
EXPIRE_AFTER = timedelta(hours=3)

_SEND = r"(?:vou\s+te\s+mandar|te\s+mand(?:o|ar)|vou\s+(?:te\s+)?mostrar|te\s+mostro|mando\s+pra\s+(?:voc[eê]|vc))"
PROMISE_RE = re.compile(rf"\b{_SEND}\b[^.!?\n]{{0,60}}", re.IGNORECASE)
_PHOTO_RE = re.compile(r"\b(?:fot(?:o|os|inho|inha|inhas)|selfie|look|lookinho|op[cç](?:[aã]o|[oõ]es)|"
                       r"finalistas?|roupa|vestido|como\s+(?:ficou|t[oô]|eu\s+t[oô]))\b", re.IGNORECASE)
_NOT_PHOTO_RE = re.compile(r"\b(?:mensagem|msg|[aá]udio|beij|localiza|link|pix|print)", re.IGNORECASE)
_QUESTION_RE = re.compile(r"\b(?:se\s+eu\s+te\s+mand|quer\s+que\s+eu|posso\s+te)\b|\?\s*$", re.IGNORECASE)
_SOON_RE = re.compile(r"\b(?:j[aá]\s*j[aá]|jaja|daqui\s+a\s+pouco|agora|rapidinho|j[aá]\s+te)\b", re.IGNORECASE)
_LATER_RE = re.compile(r"\b(?:depois|mais\s+tarde|quando\s+(?:eu\s+)?\w+)\b", re.IGNORECASE)
_LOOKS_RE = re.compile(r"\b(?:look|lookinho|op[cç](?:[aã]o|[oõ]es)|finalistas?|roupas?|vestido|blusa|saia|"
                       r"outfit|estilosa?|trocar\s+de\s+roupa)\b", re.IGNORECASE)
# "não consigo te mandar uma foto agora", "quem sabe eu … te mando na próxima" não são promessa
_HEDGE_BEFORE_RE = re.compile(r"\b(?:n[aã]o|nem|quem\s+sabe|talvez|na\s+pr[oó]xima|um\s+dia)\b[^.!?\n]{0,30}$",
                              re.IGNORECASE)
_TWO_RE = re.compile(r"\b(?:duas|dois|2|op[cç][oõ]es|finalistas)\b", re.IGNORECASE)


def _load(db) -> dict:
    try:
        raw = db.get_estado_relacional(KEY)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _save(db, st: dict) -> None:
    db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))


def is_promise(line: str) -> Optional[str]:
    """O trecho da promessa de foto, ou None (pergunta, mensagem, áudio… não contam)."""
    from pedido_dela import is_offer
    if is_offer(line):
        return None                        # "já te mando um suquinho pelo app" é delivery (pedido_dela)
    for m in PROMISE_RE.finditer(line or ""):
        seg = m.group(0)
        around = line[max(0, m.start() - 15):m.end() + 40]      # "jaja te mando": o "jaja" vem antes
        if _NOT_PHOTO_RE.search(seg) or _QUESTION_RE.search(line[max(0, m.start() - 20):m.end() + 3]):
            continue
        if _HEDGE_BEFORE_RE.search(line[max(0, m.start() - 40):m.start()]):
            continue
        if _PHOTO_RE.search(seg) or _SOON_RE.search(around):
            return seg
    return None


def classify(segment: str, context: str) -> tuple[str, int, str]:
    """(tipo, quantas fotos, assunto). O contexto (falas recentes) diz do que era a foto."""
    both = f"{segment} {context}"
    if _LOOKS_RE.search(segment) or (not _PHOTO_RE.search(segment) and _LOOKS_RE.search(context)):
        return "looks", 2 if _TWO_RE.search(both) else 1, "look"
    from photo_director import _food
    food = _food(segment) or _food(context)      # "quando chegar eu te mando uma foto antes de atacar" (o açaí)
    if food:
        m = re.search(r"\b(?:do|da|dos|das)\s+([\wçãéíóú]+(?:\s+de\s+[\wçãéíóú]+)?)", segment, re.IGNORECASE)
        return "comida", 1, (m.group(1).strip() if m else "")
    return "selfie", 1, ""


def observe_marina_line(db, line: str, context: str, now: datetime, *, intimate: bool = False) -> Optional[dict]:
    """Depois que a fala dela saiu: promessa de foto vira compromisso com hora."""
    seg = is_promise(line)
    if not seg or pending(db):
        return None
    kind, count, subject = classify(seg, f"{line} {context}")   # a frase inteira dela conta
    if intimate and kind == "selfie":
        # 25/09 16:39: "já te mando o estrago" no sexting virou selfie de conjunto. No clima, é íntima.
        kind, count, subject = "intimo", 1, ""
    rng = random.Random(f"promessa:{now.isoformat()}")
    window = (20, 50) if _LATER_RE.search(seg) else (3, 10) if _SOON_RE.search(line) else (5, 15)
    due = now + timedelta(minutes=rng.randint(*window))
    promise = {"kind": kind, "count": count, "subject": subject, "said": line.strip()[:200],
               "made_at": now.isoformat(), "due_at": due.isoformat(), "status": "pendente"}
    st = _load(db)
    st["promessa"] = promise
    _save(db, st)
    logger.info("promessa_foto.made kind=%s count=%s due=%s", kind, count, due.isoformat(timespec="minutes"))
    return promise


def pending(db) -> Optional[dict]:
    p = _load(db).get("promessa")
    return p if p and p.get("status") == "pendente" else None


def due(db, now: datetime) -> Optional[dict]:
    p = pending(db)
    if not p:
        return None
    if now - datetime.fromisoformat(p["made_at"]) > EXPIRE_AFTER:
        close(db, "expirou")
        return None
    return p if datetime.fromisoformat(p["due_at"]) <= now else None


def promise_intimate(db, said: str, due_at: datetime, now: datetime, *, where: str = "banho") -> dict:
    """Sexting: "vou pro box com o transparente… já te mando o estrago". Ao sair do banho ela manda
    os registros (o brinquedo e o gozo) — 25/09 16:28–16:39 ela anunciou 4x e nada chegava."""
    promise = {"kind": "intimo", "count": 2, "subject": where, "said": said.strip()[:200],
               "made_at": now.isoformat(), "due_at": due_at.isoformat(), "status": "pendente"}
    st = _load(db)
    st["promessa"] = promise
    _save(db, st)
    logger.info("promessa_foto.made kind=intimo where=%s due=%s", where, due_at.isoformat(timespec="minutes"))
    return promise


def promise_unhas(db, cor: str, due_at: datetime, now: datetime, *, pediu: bool) -> dict:
    """26/09 (Patrick): unha pronta → foto da mão. Sempre que ele escolheu a cor; às vezes, por vontade."""
    promise = {"kind": "unhas", "count": 1, "subject": cor, "said": f"unhas {cor}", "pediu": pediu,
               "made_at": now.isoformat(), "due_at": due_at.isoformat(), "status": "pendente"}
    st = _load(db)
    st["promessa"] = promise
    _save(db, st)
    logger.info("promessa_foto.made kind=unhas cor=%s due=%s", cor, due_at.isoformat(timespec="minutes"))
    return promise


def promise_cabelo(db, subject: str, due_at: datetime, now: datetime, *, pediu: bool, pose: str) -> dict:
    """26/09 (Patrick): cabelo feito → a foto. No salão alguém de lá tira; em casa, espelho ou tripé."""
    promise = {"kind": "cabelo", "count": 1, "subject": subject, "said": f"cabelo {subject}", "pediu": pediu,
               "pose": pose, "made_at": now.isoformat(), "due_at": due_at.isoformat(), "status": "pendente"}
    st = _load(db)
    st["promessa"] = promise
    _save(db, st)
    logger.info("promessa_foto.made kind=cabelo subject=%s due=%s", subject, due_at.isoformat(timespec="minutes"))
    return promise


MAX_ATTEMPTS = 3
# 26/09 (Patrick, /feedback): as opções de look não vêm em álbum — ela troca de roupa entre uma e outra.
CHANGE_OUTFIT_MIN = (3, 6)


def next_part(db, outfits: list, seed: int, now: datetime, *, poses: Optional[list] = None) -> dict:
    """Mandou a opção 1; a próxima vem depois de trocar de roupa (no tripé do closet, pose nova)."""
    st = _load(db)
    p = st["promessa"]
    rng = random.Random(f"troca:{now.isoformat()}")
    p.update({"part": p.get("part", 1) + 1, "outfits": outfits, "poses": poses, "seed": seed, "attempts": 0,
              "due_at": (now + timedelta(minutes=rng.randint(*CHANGE_OUTFIT_MIN))).isoformat()})
    _save(db, st)
    logger.info("promessa_foto.looks parte=%s due=%s", p["part"], p["due_at"][11:16])
    return p


def attempt(db) -> bool:
    """Conta uma tentativa de gerar; depois de MAX_ATTEMPTS a promessa fecha (sem gastar à toa)."""
    st = _load(db)
    p = st.get("promessa")
    if not p:
        return False
    p["attempts"] = p.get("attempts", 0) + 1
    _save(db, st)
    if p["attempts"] > MAX_ATTEMPTS:
        close(db, "falhou")
        return False
    return True


def close(db, how: str) -> None:
    st = _load(db)
    if st.get("promessa") and st["promessa"].get("status") == "pendente":
        st["promessa"]["status"] = how
        _save(db, st)
        logger.info("promessa_foto.%s", how)


def prompt_lines(db, now: datetime) -> list[str]:
    p = pending(db)
    if not p:
        return []
    if p["kind"] == "looks" and p.get("part", 1) > 1:
        return [f"[SUA PROMESSA] Você já mandou a opção {p['part'] - 1} de look e tá trocando de roupa pra "
                f"mandar a {p['part']}. Não diga que já mandou e não mande outra foto antes."]
    if p["kind"] == "cabelo":
        return [f"[FOTO DO CABELO] Seu cabelo ({p['subject']}) acabou de ficar pronto e você vai mandar a foto pro "
                "Patrick daqui a pouco. Não diga que já mandou."]
    if p["kind"] == "unhas":
        return [f"[FOTO DAS UNHAS] Suas unhas ({p['subject']}) acabaram de ficar prontas e você vai mandar a foto "
                "da mão pro Patrick daqui a pouco. Não diga que já mandou."]
    o_que = {"looks": "as opções de look" if p["count"] > 1 else "o look",
             "comida": f"a foto {('do ' + p['subject']) if p['subject'] else 'da comida'}",
             "selfie": "uma foto sua",
             "unhas": f"a foto da mão com as unhas {p['subject']} prontas",
             "intimo": ("os registros do banho (você se tocando e o depois) quando sair" if p["subject"] == "banho"
                        else "a foto que você prometeu no clima")}[p["kind"]]
    return [f"[SUA PROMESSA] Você disse que ia mandar {o_que} pro Patrick; vai mandar daqui a pouco. "
            "Não diga que já mandou e não prometa de novo."]
