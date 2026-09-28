"""Consumo no rolê (Patrick, 26/09): o que ela pede fora vira cânone.

Antes do reset ela foi ao bar e o banco não mexeu: o rolê só existia como "estar lá".
Agora cada saída tem o que ela consumiu, e cada consumo é acontecimento de verdade:
- entra no dia dela (life_events 'consumo'), e ela pode lembrar e comentar;
- sai do saldo dela (financas lê 'consumo:%' e 'transporte:%');
- comida conta como refeição do horário (o jantar no bar é o jantar; Meals não repete).

Decisões do Patrick (26/09): o lazer sai do saldo dela; uber também; ônibus e metrô são
do Riocard que o pai carrega (fora do saldo e fora do extrato). Pedido repetido aparece
de novo com o mesmo nome. Os itens são função do rolê (data, lugar, amigos): o mesmo
rolê sempre tem os mesmos pedidos, então o card da aba Agora e o extrato batem.
"""
from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CATALOGO = Path(__file__).parent / "webapp" / "catalogo.json"
BEACHES = ("copacabana_beach", "ipanema_beach", "leblon_beach")

# (nome curto pro card, como ela diria, preço)
BAR = {
    "bebidas": (("Gin tônica", "um gin tônica", 34), ("Chopp", "um chopp", 16), ("Caipirinha", "uma caipirinha", 28),
                ("Drink de maracujá", "um drink de maracujá", 32)),
    "petiscos": (("Fritas", "uma porção de fritas", 36), ("Bolinho de bacalhau", "uma porção de bolinho de bacalhau", 44),
                 ("Pastel de queijo", "uma porção de pastel de queijo", 38)),
    "agua": ("Água", "uma água", 7),
}
CINEMA = {"ingresso": ("Cinema", "o ingresso do cinema", 42), "pipoca": ("Pipoca", "uma pipoca grande", 34),
          "refri": ("Refri", "um refri", 12)}
PRAIA = {"cadeira": ("Cadeira e guarda-sol", "cadeira e guarda-sol", 30),
         "coco": ("Água de coco", "uma água de coco", 12),
         "extras": (("Mate", "um mate", 10), ("Biscoito Globo", "um biscoito Globo", 8),
                    ("Queijo coalho", "um queijo coalho", 15))}
ESTADIO = {"ingresso": ("Ingresso", "o ingresso do jogo", 60), "cerveja": ("Cerveja", "uma cerveja", 15),
           "agua": ("Água", "uma água", 6), "lanche": ("Cachorro-quente", "um cachorro-quente", 18)}
# Starbucks: os mesmos itens e preços do iFood do app (catálogo), pra o mundo bater com o app
STARBUCKS_LOJA = "starbucks-bf"
STARBUCKS_FALLBACK = {"Bebidas": (("Latte Grande", 21.9),), "Comidas": (("Pão de queijo", 12.9),)}

UBER_BASE, UBER_POR_MIN = 6.0, 1.3


@dataclass(frozen=True)
class Item:
    at: datetime
    nome: str            # "Gin tônica" (card e extrato)
    frase: str           # "um gin tônica" (acontecimento, voz do mundo)
    valor: int           # a parte dela, em reais
    dividido: bool = False
    comida: bool = False


def _rng(key: str) -> random.Random:
    return random.Random(f"consumo:{key}")


def _starbucks() -> dict:
    try:
        cat = json.loads(CATALOGO.read_text(encoding="utf-8"))
        loja = next(l for l in cat["lojas"] if l["id"] == STARBUCKS_LOJA)
        return {s["nome"]: tuple((i["nome"], i["preco"]) for i in s["itens"]) for s in loja["secoes"]}
    except Exception:
        return STARBUCKS_FALLBACK


def _secoes(loja_id: str) -> list:
    try:
        cat = json.loads(CATALOGO.read_text(encoding="utf-8"))
        return next(l for l in cat["lojas"] if l["id"] == loja_id)["secoes"]
    except Exception:
        return []


def _frase(nome: str) -> str:
    """28/09 (auditoria): "caramel Macchiato Grande" — nome de produto com maiúscula no meio fica como está;
    "Pão de queijo" vira "pão de queijo"."""
    return nome if any(c.isupper() for c in nome[1:]) else nome[:1].lower() + nome[1:]


def _no(lugar: str) -> str:
    """"na Drogarias Pacheco", "no Starbucks" (o mesmo artigo do card)."""
    try:
        from vontade import no
        return no(lugar)
    except Exception:
        return f"no {lugar}"


COMPRA = ("farmacia", "mercado")      # 28/09 (auditoria): loja que não é de comida — "Comprou", não "Pediu"


def _parte(preco: float, pessoas: int, dividido: bool) -> int:
    return int(math.ceil(preco / pessoas)) if dividido else int(round(preco))


def plan(outing: dict) -> list[Item]:
    """Os pedidos de uma saída (eventos_pendentes: source_key, event_at, end_at, location_key, metadata_json)."""
    start, saiu = datetime.fromisoformat(outing["event_at"]), datetime.fromisoformat(outing["end_at"])
    place = outing.get("location_key") or ""
    meta0 = json.loads(outing.get("metadata_json") or "{}") or {}
    # 26/09 (agenda reativa): saiu mais cedo — o plano segue o fim original e só vale o que veio antes
    end = datetime.fromisoformat(meta0["fim_original"]) if meta0.get("fim_original") else saiu
    friends = meta0.get("friends") or []
    pessoas = 1 + len(friends)
    rng = _rng(outing["source_key"])
    out: list[Item] = []

    def add(at, entry, *, dividido=False, comida=False):
        nome, frase, preco = entry
        if at < min(end, saiu):
            out.append(Item(at, nome, frase, _parte(preco, pessoas, dividido), dividido and pessoas > 1, comida))

    if place == "quartinho_bar":
        at = start + timedelta(minutes=rng.randint(5, 15))
        drink = rng.choice(BAR["bebidas"])
        for _ in range(rng.randint(2, 4)):
            if at > end - timedelta(minutes=15):
                break
            add(at, drink)
            if rng.random() < 0.3:
                drink = rng.choice(BAR["bebidas"])
            at += timedelta(minutes=rng.randint(35, 70))
        if rng.random() < 0.7:
            add(start + timedelta(minutes=rng.randint(30, 70)), rng.choice(BAR["petiscos"]), dividido=True, comida=True)
        if rng.random() < 0.3:
            add(end - timedelta(minutes=rng.randint(20, 40)), BAR["agua"])
    elif place == "estadio_nilton_santos":           # 26/09: jogo do Botafogo no estádio
        add(start, ESTADIO["ingresso"])
        at = start + timedelta(minutes=rng.randint(20, 40))
        for _ in range(rng.randint(1, 3)):
            if at > end - timedelta(minutes=20):
                break
            add(at, ESTADIO["cerveja"] if rng.random() < 0.7 else ESTADIO["agua"])
            at += timedelta(minutes=rng.randint(30, 50))
        if rng.random() < 0.5:
            add(start + timedelta(minutes=rng.randint(10, 30)), ESTADIO["lanche"], comida=True)
    elif place.startswith("loja_"):                     # 26/09: saída por vontade numa loja do catálogo
        meta = json.loads(outing.get("metadata_json") or "{}") or {}
        if meta.get("pago_por") == "pai":
            return []
        secoes = _secoes(meta.get("loja", ""))
        itens = [i for s in secoes for i in s["itens"]]
        if itens:
            at = start + timedelta(minutes=rng.randint(2, 6))
            escolhidos = rng.sample(itens, k=1 if rng.random() < 0.6 or len(itens) < 2 else 2)
            for n, i in enumerate(escolhidos):
                add(at + timedelta(minutes=n), (i["nome"], _frase(i["nome"]), i["preco"]),
                    comida=meta.get("tipo") in ("cafe", "acai"))
    elif place == "starbucks_shopping_gavea":
        menu = _starbucks()
        at = start + timedelta(minutes=rng.randint(3, 8))
        nome, preco = rng.choice(menu.get("Bebidas") or STARBUCKS_FALLBACK["Bebidas"])
        add(at, (nome, nome.lower(), preco))
        if rng.random() < 0.6:
            nome, preco = rng.choice(menu.get("Comidas") or STARBUCKS_FALLBACK["Comidas"])
            add(at + timedelta(minutes=1), (nome, nome.lower(), preco), comida=True)
    elif place == "shopping_gavea":
        at = start + timedelta(minutes=rng.randint(5, 20))
        add(at, CINEMA["ingresso"])
        add(at + timedelta(minutes=5), CINEMA["pipoca"], dividido=True, comida=True)
        if rng.random() < 0.5:
            add(at + timedelta(minutes=6), CINEMA["refri"])
    elif place in BEACHES:
        if rng.random() < 0.6:
            add(start + timedelta(minutes=rng.randint(5, 15)), PRAIA["cadeira"], dividido=True)
        add(start + timedelta(minutes=rng.randint(20, 40)), PRAIA["coco"])
        for entry in rng.sample(PRAIA["extras"], rng.randint(1, 2)):
            add(start + timedelta(minutes=rng.randint(50, 150)), entry, comida=entry[0] != "Mate")
    return sorted(out, key=lambda i: i.at)


def uber_price(minutes: float, dividido: bool = False) -> int:
    valor = UBER_BASE + UBER_POR_MIN * minutes
    return int(math.ceil(valor / 2)) if dividido else int(round(valor))


class Consumo:
    def __init__(self, db):
        self.db = db

    def _outings(self, day) -> list[dict]:
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                """SELECT source_key, event_at, end_at, location_key, metadata_json FROM eventos_pendentes
                   WHERE (source_key LIKE ? OR source_key LIKE ?) AND confirmed=1 AND status != 'cancelled'
                   AND end_at IS NOT NULL ORDER BY event_at""", (f"outing:{day.isoformat()}:%", f"vontade:{day.isoformat()}:%"))]

    def _place_name(self, key: str) -> str:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT name FROM world_places WHERE canonical_key=?", (key,)).fetchone()
        return row["name"] if row else key

    def items_of(self, outing: dict, now: datetime) -> list[Item]:
        """O que já foi pedido até agora (o card da aba Agora lê daqui)."""
        return [i for i in plan(outing) if i.at <= now]

    def materialize(self, now: datetime) -> int:
        created = 0
        with self.db.get_connection() as conn:
            clean = conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone()
        if not clean:
            return 0
        from social_day import SocialDay, short_name
        floor = SocialDay(self.db)._floor(now)
        for day in (now.date() - timedelta(days=1), now.date()):
            for outing in self._outings(day):
                lugar = self._place_name(outing["location_key"])
                friends = (json.loads(outing.get("metadata_json") or "{}") or {}).get("friends") or []
                com = " e ".join(short_name(f) for f in friends)
                for n, item in enumerate(plan(outing)):
                    if not (floor <= item.at <= now):
                        continue
                    created += self._record(outing, n, item, lugar, com, friends, now)
            created += self._transport(day, floor, now)
        return created

    def _record(self, outing, n, item: Item, lugar: str, com: str, friends: list, now: datetime) -> int:
        compra = (json.loads(outing.get("metadata_json") or "{}") or {}).get("tipo") in COMPRA
        if item.dividido:
            summary = f"Dividiu {item.frase} com {com} {_no(lugar)} (R$ {item.valor}, a parte dela)."
        else:
            summary = f"{'Comprou' if compra else 'Pediu'} {item.frase} {_no(lugar)} (R$ {item.valor})."
        title = f"{lugar} · {item.nome}" + (" (dividiu)" if item.dividido else "")
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'consumo',?,?,'simulated',1,0.1,?,0.2,?)""",
                (f"consumo:{outing['source_key']}:{n}", item.at.isoformat(), title, summary,
                 json.dumps(["marina", *friends]), now.isoformat()))
            if cur.rowcount and item.comida:
                self._meal(conn, item, lugar, friends, now)
            conn.commit()
        return cur.rowcount or 0

    def _meal(self, conn, item: Item, lugar: str, friends: list, now: datetime) -> None:
        """Comida fora é a refeição do horário: o jantar no bar é o jantar (Meals não repete)."""
        from meals import meal_kind
        kind = meal_kind(item.at)
        day = item.at.date().isoformat()
        if conn.execute("SELECT 1 FROM life_events WHERE event_type IN ('meal','snack') AND event_key LIKE ? LIMIT 1",
                        (f"meal:{day}:{kind}%",)).fetchone():
            return
        conn.execute(
            """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
               autonomy_level,importance,participants_json,share_worthy,created_at)
               VALUES (?,?,?,?,?,'simulated',1,0.1,?,0.2,?)""",
            (f"meal:{day}:{kind}:fora", item.at.isoformat(), "snack" if kind == "lanche" else "meal",
             f"comeu fora ({lugar})", f"Comeu {item.frase} {_no(lugar)}.", json.dumps(["marina", *friends]),
             now.isoformat()))

    def _transport(self, day, floor: datetime, now: datetime) -> int:
        """Uber sai do saldo dela; ônibus e metrô são do Riocard do pai (fora do saldo)."""
        try:
            from commute import Commute
            legs = Commute(self.db).legs_on(day)
        except Exception:
            logger.exception("consumo.transporte.legs")
            return 0
        created = 0
        for leg in legs:
            if leg.mode not in ("uber", "uber_dividido") or not (floor <= leg.start <= now):
                continue
            minutos = (leg.end - leg.start).total_seconds() / 60
            dividido = leg.mode == "uber_dividido"
            valor = uber_price(minutos, dividido)
            trecho = f"indo {leg.destination}" if leg.direction == "ida" else f"voltando {leg.destination} pra casa"
            summary = f"Pagou o uber {trecho} (R$ {valor}" + (f", dividido com {leg.companion})." if dividido else ").")
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                       autonomy_level,importance,participants_json,share_worthy,created_at)
                       VALUES (?,?,'transporte',?,?,'simulated',1,0.05,?,0.1,?)""",
                    (f"transporte:{leg.key}", leg.start.isoformat(), "Uber" + (" (dividiu)" if dividido else ""),
                     summary, json.dumps(["marina"]), now.isoformat()))
                conn.commit()
                created += cur.rowcount or 0
        return created
