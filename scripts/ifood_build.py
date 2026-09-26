"""Monta webapp/catalogo.json: lojas reais + cardápios + fotos (26/09).

Entrada: scripts/ifood_lojas.py (lojas e logos), scripts/ifood_cardapios.py (itens),
scripts/ifood_osm.json (posição real de cada loja), webapp/fotos/ (fotos dos itens).
Tudo que é número "de app" (nota, avaliações, tempo, taxa, pedido mínimo) é determinístico
por loja: o mesmo catálogo sai igual em todo build.

Uso: python scripts/ifood_build.py
"""
from __future__ import annotations

import json
import random
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ifood_cardapios as C  # noqa: E402
import ifood_lojas as L  # noqa: E402

WEB = ROOT / "webapp"
REDES = {"mcdonalds", "bobs", "burger-king", "dominos", "spoleto", "habibs", "starbucks", "kopenhagen",
         "china-in-box", "milky-moo", "giraffas", "rei-do-mate"}
GRANDES = REDES | {"pacheco", "droga-raia", "venancio", "drogasmil", "zona-sul", "hortifruti", "pao-de-acucar",
                   "mundial", "guanabara", "assai", "carrefour", "megamatte", "bacio-di-latte", "gurume"}
# horário de funcionamento por categoria (abre, fecha); farmácia de rede é 24 h
HORARIO = {"Farmácia": (7, 23), "Mercado": (7, 22), "Cafés": (7, 20), "Açaí e sucos": (8, 22), "Açaí": (10, 23),
           "Sorvetes": (11, 23), "Doces": (10, 22)}
HORARIO_24H = {"pacheco", "droga-raia", "venancio"}


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def base_id(lid: str) -> str:
    return re.sub(r"-(bf|cg)$", "", lid)


def foto_key(lid: str, nome: str, tipo: str) -> str:
    if tipo in ("mercado", "farmacia"):
        return f"produtos/{slug(nome)}"
    b = base_id(lid)
    return f"{b}/{slug(nome)}" if b in REDES else f"{lid}/{slug(nome)}"


def _serve(nome: str, desc: str) -> str:
    m = re.search(r"[Ss]erve (\d)", desc) or (re.search(r"\b(30|40) peças\b", nome) and re.match("", ""))
    if re.search(r"[Ss]erve 2|pra dois|Pra dois|30 peças|40 peças|2 pizzas|inteiro|1 litro|Pote", f"{nome} {desc}"):
        return "Serve até 2 pessoas"
    return "Serve até 1 pessoa"


def build() -> dict:
    osm = json.loads((ROOT / "scripts" / "ifood_osm.json").read_text(encoding="utf-8"))
    lojas = []
    for lid, nome, _osm_name, area, tipo, categoria, _logo in L.LOJAS:
        rng = random.Random(f"loja:{lid}")
        km = osm[lid]["km"]
        b = base_id(lid)
        prep = {"restaurante": 15, "mercado": 25, "farmacia": 10}[tipo]
        eta_min = int(prep + km * 6 + rng.randint(0, 6))
        eta = [eta_min, eta_min + 10 + rng.choice((0, 5))]
        if area == "bf":
            taxa = 0.0 if km <= 1.0 or rng.random() < 0.35 else round(3.99 + km * 1.5, 2)
        else:
            taxa = round(5.99 + km * 1.8, 2)
        nota = round(rng.uniform(4.6, 4.9) if b in GRANDES else rng.uniform(4.4, 4.9), 1)
        avaliacoes = rng.randint(2500, 18000) if b in GRANDES else rng.randint(40, 1400)
        abre, fecha = (0, 24) if b in HORARIO_24H else HORARIO.get(categoria, (11, 23))
        minimo = {"restaurante": 15.0, "mercado": 30.0, "farmacia": 10.0}[tipo]
        if tipo == "restaurante":
            menu = C.CARDAPIOS[lid]
            fator = 1.0
        else:
            menu = C.MERCADO if tipo == "mercado" else C.FARMACIA
            fator = round(rng.uniform(0.95, 1.12), 3)
        secoes = []
        for sec, itens in menu.items():
            out = []
            for iname, desc, preco in itens:
                key = foto_key(lid, iname, tipo)
                foto = f"fotos/{key}.jpg" if (WEB / "fotos" / f"{key}.jpg").exists() else ""
                p = round(preco * fator + (0.0 if fator == 1.0 else 0.0), 2)
                if fator != 1.0:
                    p = round(int(p) + 0.99 if p % 1 > 0.5 else int(p) + 0.49, 2)
                out.append({"id": slug(iname), "nome": iname, "desc": desc, "preco": p, "foto": foto,
                            "serve": _serve(iname, desc) if tipo == "restaurante" else ""})
            secoes.append({"nome": sec, "itens": out})
        primeira = next((i["foto"] for s in secoes for i in s["itens"] if i["foto"]), "")
        lojas.append({
            "id": lid, "nome": nome, "area": area, "tipo": tipo, "categoria": categoria,
            "logo": f"lojas/{lid}.png", "capa": primeira, "km": km, "eta": eta, "taxa": taxa,
            "nota": nota, "avaliacoes": avaliacoes, "minimo": minimo, "abre": abre, "fecha": fecha,
            "mais_pedido": b in GRANDES and rng.random() < 0.5, "secoes": secoes,
        })
    return {"_sobre": "Gerado por scripts/ifood_build.py (26/09). Lojas reais (OpenStreetMap), logos reais, "
                      "cardápios do cânone da Marina. Não editar à mão: editar os scripts e rodar de novo.",
            "lojas": lojas}


def main() -> int:
    cat = build()
    (WEB / "catalogo.json").write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    itens = [i for l in cat["lojas"] for s in l["secoes"] for i in s["itens"]]
    print(f"{len(cat['lojas'])} lojas, {len(itens)} itens, {sum(1 for i in itens if i['foto'])} com foto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
