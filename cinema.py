"""Cinema de verdade num rolê (27/09).

Bug do uso real: "Cinema e shopping com a Bia" (15:00–19:00) só tinha as compras como passos (Cinema, Pipoca,
Refri), e a aba Agora ficou em "Refri" das 15:13 às 19:00. No chat ela inventou o filme ("A Princesinha") e a hora
em que a sessão acabou. Agora o rolê tem sessão: um filme em cartaz de verdade no Brasil (TMDB), que começa depois
do ingresso e da pipoca e dura trailers + o filme; depois, o passeio pelo shopping.

O filme é escolhido uma vez e fica gravado no compromisso (metadata_json "filme"), pra não trocar se a lista em
cartaz mudar. Sem TMDB (offline, testes): a sessão existe, sem título, com duração média.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

LUGARES = ("shopping_gavea",)
TRAILERS_MIN = 15
DURACAO_PADRAO = 110
ESPERA_MIN = (10, 20)          # do ingresso até a sessão começar (pipoca e fila)
GOSTO = {10749: 3, 35: 3, 53: 2, 9648: 2, 18: 1, 16: 1, 27: 1}   # romance, comédia, suspense, mistério...
FORA = {10751, 99, 10770}      # família (infantil), documentário, filme de TV
DEPOIS = (("Olhando as lojas", 60), ("No provador", 40))
FALHA_ESPERA = timedelta(minutes=30)    # TMDB fora: não tenta de novo a cada resolve (cada tentativa espera até 8 s)
_falhou: dict = {}


def e_cinema(outing: Optional[dict]) -> bool:
    return bool(outing) and (outing.get("location_key") or "") in LUGARES


def _meta(outing: dict) -> dict:
    return json.loads(outing.get("metadata_json") or "{}") or {}


def filme(db, outing: dict) -> Optional[dict]:
    """{"titulo", "minutos"} do filme da sessão; None se não deu pra saber qual (sem TMDB)."""
    meta = _meta(outing)
    if meta.get("filme"):
        return meta["filme"]
    quando = _falhou.get(outing["source_key"])
    if quando and datetime.now() - quando < FALHA_ESPERA:
        return None
    try:
        from tmdb import TMDB
        t = TMDB(db)
        cartaz = [f for f in t.now_playing() if not FORA & set(f["genre_ids"])]
    except Exception:
        logger.warning("cinema.cartaz_falhou", exc_info=True)
        _falhou[outing["source_key"]] = datetime.now()
        return None
    if not cartaz:
        _falhou[outing["source_key"]] = datetime.now()
        return None
    rng = random.Random(f"cinema:{outing['source_key']}")
    pesos = [1 + sum(GOSTO.get(g, 0) for g in f["genre_ids"]) for f in cartaz]
    escolhido = rng.choices(cartaz, weights=pesos, k=1)[0]
    minutos = DURACAO_PADRAO
    try:
        info = t.details("movie", escolhido["id"])
        if isinstance(info, dict) and info.get("minutes"):
            minutos = int(info["minutes"])
    except Exception:
        pass
    escolha = {"titulo": escolhido["title"], "minutos": minutos, "tmdb": escolhido["id"]}
    meta["filme"] = escolha
    with db.get_connection() as conn:
        conn.execute("UPDATE eventos_pendentes SET metadata_json=? WHERE source_key=?",
                     (json.dumps(meta, ensure_ascii=False), outing["source_key"]))
        conn.commit()
    outing["metadata_json"] = json.dumps(meta, ensure_ascii=False)
    logger.info("cinema.filme titulo=%s minutos=%s", escolha["titulo"], minutos)
    return escolha


def sessao(db, outing: dict) -> Optional[dict]:
    """A sessão do rolê: {"inicio", "fim", "titulo"} (titulo pode ser None)."""
    if not e_cinema(outing):
        return None
    from consumo import CINEMA, plan
    inicio_role = datetime.fromisoformat(outing["event_at"])
    meta = _meta(outing)
    fim_role = datetime.fromisoformat(meta.get("fim_original") or outing["end_at"])
    ingresso = next((i.at for i in plan(outing) if i.nome == CINEMA["ingresso"][0]), inicio_role)
    f = filme(db, outing)
    dura = timedelta(minutes=TRAILERS_MIN + int((f or {}).get("minutos") or DURACAO_PADRAO))
    rng = random.Random(f"sessao:{outing['source_key']}")
    ini = ingresso + timedelta(minutes=rng.randint(*ESPERA_MIN))
    if ini + dura > fim_role - timedelta(minutes=10):          # não cabe: a sessão é a mais cedo que dá
        ini = max(ingresso + timedelta(minutes=8), fim_role - timedelta(minutes=10) - dura)
    return {"inicio": ini, "fim": min(ini + dura, fim_role), "titulo": (f or {}).get("titulo")}


def passo_sessao(s: dict) -> str:
    return f"Assistindo: {s['titulo']}" if s.get("titulo") else "Na sessão"     # 01/10 (catálogo)


def _outing(db, event_id) -> Optional[dict]:
    if not event_id:
        return None
    with db.get_connection() as conn:
        row = conn.execute("""SELECT source_key, event_at, end_at, location_key, metadata_json FROM eventos_pendentes
                              WHERE id=?""", (event_id,)).fetchone()
    return dict(row) if row else None


def na_sessao(db, event_id, now: datetime) -> Optional[dict]:
    """A sessão, se ela está dentro do cinema agora (o mundo e a disponibilidade leem daqui)."""
    outing = _outing(db, event_id)
    s = sessao(db, outing) if e_cinema(outing) else None
    return s if s and s["inicio"] <= now < s["fim"] else None


def atividade(s: dict) -> str:
    return f"na sessão de {s['titulo']}" if s.get("titulo") else "na sessão do cinema"


def linha_prompt(db, event_id, now: datetime) -> Optional[str]:
    """Pro prompt: o filme e a hora da sessão (antes, durante ou depois), pra ela não inventar."""
    outing = _outing(db, event_id)
    s = sessao(db, outing) if e_cinema(outing) else None
    if not s:
        return None
    nome = f"\"{s['titulo']}\"" if s.get("titulo") else "um filme sem título definido aqui (não invente um nome)"
    if now < s["inicio"]:
        quando = f"a sessão começa às {s['inicio']:%H:%M} e acaba lá pelas {s['fim']:%H:%M}"
    elif now < s["fim"]:
        quando = (f"você está DENTRO da sessão agora (desde {s['inicio']:%H:%M}, acaba lá pelas {s['fim']:%H:%M}): "
                  "celular no silencioso, só dá uma espiada rápida")
    else:
        quando = f"a sessão foi das {s['inicio']:%H:%M} às {s['fim']:%H:%M}; depois dela, passeio pelo shopping até a hora de voltar"
    return f"[CINEMA — FATO] O filme é {nome}; {quando}. Não cite outro filme."
