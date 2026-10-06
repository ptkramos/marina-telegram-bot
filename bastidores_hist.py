"""Redesenho dos Bastidores, passo 1 (06/10): o histórico que só a tela lê.

O desenho novo (PLANO_WEBAPP, "Redesenho dos Bastidores — plano") pede passado que o mundo não guardava: o
calendário de orgasmos (só existia a última vez: `intimacy_state.climax_at` e `libido_release_at`), o tracinho de
onde cada barra do casal estava ontem neste horário, a linha do peso dos últimos 30 dias e o "Excitada desde 21:40".
Tudo vai pra `bastidores_hist` (migração 037). Ela nunca lê isto: nada aqui entra no prompt nem muda o que ela faz,
e um erro aqui nunca derruba quem chamou (cada função engole e loga).

* `orgasmo`: com o Patrick (sexting ou Lovense) ou sozinha (antes de dormir, em casa, fora). O mesmo gozo chega por
  dois caminhos (ela escreve "gozei" com o brinquedo ligado → intimacy e Lovense): até DUPLICADO de distância é um só,
  e os detalhes se somam.
* `excitacao`: a hora em que acendeu (passou de ACESA vindo de baixo); a tela mostra o "desde" enquanto segue acesa.
* `retrato`: o relógio de 10 em 10 min grava o vínculo da hora (um por hora) e o peso do dia (um por dia).
* `pesagem`: a balança da academia (a bolinha vazia na linha do peso).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

ACESA = 0.10                         # abaixo disso a excitação é zero pra tela (o "desde" some)
DUPLICADO = timedelta(minutes=3)     # dois registros de gozo tão perto são o mesmo


def gravar(db, chave: str, em: datetime, valor: dict, ref: Optional[str] = None) -> bool:
    """Grava um registro; com `ref`, o mesmo (chave, ref) não entra duas vezes."""
    try:
        with db.get_connection() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO bastidores_hist (chave, em, ref, valor_json, criado_em) VALUES (?,?,?,?,?)",
                (chave, em.isoformat(), ref, json.dumps(valor, ensure_ascii=False), datetime.now().isoformat()))
            conn.commit()
            return bool(cur.rowcount)
    except Exception:
        logger.exception("bastidores_hist.gravar chave=%s", chave)
        return False


def lista(db, chave: str, desde: datetime, ate: Optional[datetime] = None) -> list[dict]:
    """Registros de `chave` em [desde, ate], do mais antigo pro mais novo: {em, ref, **valor}."""
    sql, args = "SELECT em, ref, valor_json FROM bastidores_hist WHERE chave=? AND em>=?", [chave, desde.isoformat()]
    if ate is not None:
        sql += " AND em<=?"
        args.append(ate.isoformat())
    try:
        with db.get_connection() as conn:
            rows = conn.execute(sql + " ORDER BY em, id", args).fetchall()
    except Exception:
        logger.exception("bastidores_hist.lista chave=%s", chave)
        return []
    return [{**json.loads(r["valor_json"]), "em": datetime.fromisoformat(r["em"]), "ref": r["ref"]} for r in rows]


def ultimo(db, chave: str, ate: datetime) -> Optional[dict]:
    try:
        with db.get_connection() as conn:
            r = conn.execute("SELECT em, ref, valor_json FROM bastidores_hist WHERE chave=? AND em<=? "
                             "ORDER BY em DESC, id DESC LIMIT 1", (chave, ate.isoformat())).fetchone()
    except Exception:
        logger.exception("bastidores_hist.ultimo chave=%s", chave)
        return None
    return {**json.loads(r["valor_json"]), "em": datetime.fromisoformat(r["em"]), "ref": r["ref"]} if r else None


# ------------------------------------------------------------------ orgasmo --
def orgasmo(db, em: datetime, com: str, como: str, **detalhe) -> None:
    """com: 'patrick' | 'sozinha'. como: 'sexting', 'lovense', 'antes de dormir', 'em casa', 'fora de casa'.
    detalhe: onde, brinquedos, publico, chamou (ela chamou o Patrick depois)."""
    valor = {"com": com, "como": como, **{k: v for k, v in detalhe.items() if v not in (None, [], "")}}
    try:
        with db.get_connection() as conn:
            perto = conn.execute(
                "SELECT id, valor_json FROM bastidores_hist WHERE chave='orgasmo' AND em>=? AND em<=? "
                "ORDER BY em LIMIT 1", ((em - DUPLICADO).isoformat(), (em + DUPLICADO).isoformat())).fetchone()
            if perto:
                antes = json.loads(perto["valor_json"])
                junto = {**antes, **{k: v for k, v in valor.items() if k not in ("com", "como")}}
                if com == "patrick" and antes.get("com") != "patrick":   # o mesmo gozo: com ele vale mais
                    junto["com"], junto["como"] = com, como
                if como == "lovense" or antes.get("como") == "lovense":
                    junto["como"] = "lovense"
                conn.execute("UPDATE bastidores_hist SET valor_json=? WHERE id=?",
                             (json.dumps(junto, ensure_ascii=False), perto["id"]))
            else:
                conn.execute("INSERT INTO bastidores_hist (chave, em, ref, valor_json, criado_em) "
                             "VALUES ('orgasmo',?,NULL,?,?)",
                             (em.isoformat(), json.dumps(valor, ensure_ascii=False), datetime.now().isoformat()))
            conn.commit()
    except Exception:
        logger.exception("bastidores_hist.orgasmo")


# ---------------------------------------------------------------- excitação --
def excitacao(db, antes: float, depois: float, em: datetime, origem: str = "conversa") -> None:
    """Acendeu: estava abaixo de ACESA (já esfriada até `em`) e passou. origem: 'conversa' | 'lovense'."""
    if antes < ACESA <= depois:
        gravar(db, "excitacao", em, {"origem": origem})


# ------------------------------------------------------------ vínculo e peso --
def retrato(db, now: Optional[datetime] = None) -> None:
    """Relógio de 10 em 10 min: o vínculo da hora (o primeiro da hora fica) e o peso do dia."""
    now = now or datetime.now()
    try:
        from emotion import EmotionEngine
        eng = EmotionEngine(db)
        vinculo = {k: round(v, 3) for k, v in eng.bond(now).items()}
        vinculo["saudade"] = round(eng._missing(now), 3)
        gravar(db, "vinculo", now, vinculo, ref=f"{now:%Y-%m-%dT%H}")
    except Exception:
        logger.exception("bastidores_hist.retrato.vinculo")
    try:
        from meals import Meals
        gravar(db, "peso", now, {"kg": float(Meals(db).weight()["kg"])}, ref=now.date().isoformat())
    except Exception:
        logger.exception("bastidores_hist.retrato.peso")


def pesagem(db, em: datetime, kg: float) -> None:
    gravar(db, "pesagem", em, {"kg": round(float(kg), 1)}, ref=em.date().isoformat())
