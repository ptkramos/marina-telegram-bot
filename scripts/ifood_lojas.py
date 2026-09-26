"""Lojas reais do iFood da Marina (26/09, decisão do Patrick).

Base: OpenStreetMap (© contribuidores do OpenStreetMap, ODbL) — nome, tipo e posição reais.
Nada vem da API do iFood. Botafogo é a vizinhança dela; Campo Grande, a do Patrick (o presente
que ela manda pra ele sai de loja perto dele).

Cada loja: (id, nome como no app, nome no OSM, área, tipo, categoria, logo)
logo: "wd:<arquivo no Wikimedia Commons>" | "site:<url>" (ícone/og:image do site) | "" (procurar)

Uso: python scripts/ifood_lojas.py  →  webapp/lojas.json + webapp/lojas/<id>.png
"""
from __future__ import annotations

LOJAS = [
    # ------------------------------------------------------------ Botafogo (ela)
    # açaí, sorvete, doces
    ("estacao-acai", "Estação do Açaí", "Estação do Açaí", "bf", "restaurante", "Açaí", ""),
    ("bacio-di-latte", "Bacio di Latte", "Bacio di Latte", "bf", "restaurante", "Sorvetes", "site:https://baciodilatte.com.br/"),
    ("officina-gelato", "Officina del Gelato", "Officina del Gelato", "bf", "restaurante", "Sorvetes", "site:https://www.officinagelato.com/"),
    ("milky-moo", "Milky Moo", "Milky Moo", "bf", "restaurante", "Doces", "site:https://www.milkymoo.com.br"),
    ("kopenhagen", "Kopenhagen", "Kopenhagen", "bf", "restaurante", "Doces", "wd:Logotipo da Kopenhagen.svg"),
    ("cake-and-co", "Cake & Co.", "Cake & Co.", "bf", "restaurante", "Doces", ""),
    # japonesa
    ("gurume", "Gurumê", "Gurumê", "bf", "restaurante", "Japonesa", ""),
    ("go-sushi", "Go Sushi", "Go Sushi", "bf", "restaurante", "Japonesa", ""),
    ("mizu", "Mizu", "Mizu", "bf", "restaurante", "Japonesa", "site:http://www.restaurantemizu.com.br/"),
    # lanches
    ("hells-burguer", "Hell's Burguer", "Hell's Burguer", "bf", "restaurante", "Lanches", "site:http://www.hellsburguer82.com.br/"),
    ("b-de-burguer", "B de Burguer", "B de Burguer", "bf", "restaurante", "Lanches", ""),
    ("bobs-bf", "Bob's", "Bob's", "bf", "restaurante", "Lanches", "wd:Logotipo do Bob's.svg"),
    ("mcdonalds-bf", "McDonald's", "McDonald's", "bf", "restaurante", "Lanches", "wd:McDonald's Golden Arches.svg"),
    ("burger-king-bf", "Burger King", "Burger King", "bf", "restaurante", "Lanches", "wd:Burger King 2020.svg"),
    # pizza e italiana
    ("ferro-e-farinha", "Ferro e Farinha", "Ferro e Farinha", "bf", "restaurante", "Pizza", ""),
    ("mamma-jamma", "Mamma Jamma", "Mamma Jamma", "bf", "restaurante", "Pizza", ""),
    ("dominos-bf", "Domino's Pizza", "Domino's", "bf", "restaurante", "Pizza", "wd:Domino's 2025.svg"),
    ("spoleto-bf", "Spoleto", "Spoleto", "bf", "restaurante", "Italiana", "wd:Logotipo do Spoleto.svg"),
    ("tutto-nhoque", "Tutto Nhoque", "Tutto Nhoque", "bf", "restaurante", "Italiana", ""),
    # brasileira
    ("gula-gula", "Gula Gula", "Gula Gula", "bf", "restaurante", "Brasileira", "site:https://gulaguladelivery.com.br/restaurantes"),
    ("joaquina", "Joaquina", "Joaquina", "bf", "restaurante", "Brasileira", ""),
    ("dois-irmaos-caldos", "Dois Irmãos Caldos e Sopas", "Dois Irmãos Caldos e Sopas", "bf", "restaurante", "Brasileira", ""),
    ("galeteria-botafogo", "Galeteria Botafogo", "Galeteria e Restaurante Botafogo", "bf", "restaurante", "Brasileira", ""),
    # saudável
    ("refeitorio-organico", "Refeitório Orgânico", "Refeitório Orgânico", "bf", "restaurante", "Saudável", "site:http://refeitorioorganico.com.br/"),
    ("uni-poke", "Uni", "Uni", "bf", "restaurante", "Saudável", ""),
    ("vegan-vegan", "Vegan Vegan", "Vegan Vegan", "bf", "restaurante", "Saudável", "site:https://veganvegan.com.br/"),
    ("natural-e-sabor", "Natural & Sabor", "Natural & Sabor", "bf", "restaurante", "Saudável", ""),
    # outras cozinhas
    ("ben-ali", "Ben Ali", "Ben Ali", "bf", "restaurante", "Árabe", ""),
    ("tacos-e-wraps", "Tacos & Wraps", "Tacos & Wraps", "bf", "restaurante", "Mexicana", ""),
    ("mr-wong", "Mr. Wong", "Mr. Wong", "bf", "restaurante", "Chinesa", ""),
    ("china-in-box-bf", "China in Box", "China in Box", "bf", "restaurante", "Chinesa", "site:https://www.chinainbox.com.br/"),
    # cafés e sucos
    ("starbucks-bf", "Starbucks", "Starbucks", "bf", "restaurante", "Cafés", "wd:Starbucks Corporation Logo 2011.svg"),
    ("the-slow-bakery", "The Slow Bakery", "The Slow Bakery", "bf", "restaurante", "Cafés", ""),
    ("rei-do-mate", "Rei do Mate", "Rei do Mate", "bf", "restaurante", "Cafés", "wd:Logotipo da Rei do Mate.svg"),
    ("praia-sucos", "Praia Sucos", "Praia Sucos", "bf", "restaurante", "Sucos", ""),
    ("megamatte-bf", "Megamatte", "Megamatte", "bf", "restaurante", "Sucos", "site:https://megamatte.com.br/"),
    # farmácias
    ("droga-raia-bf", "Droga Raia", "Droga Raia", "bf", "farmacia", "Farmácia", "site:https://www.drogaraia.com.br/"),
    ("pacheco-bf", "Drogarias Pacheco", "Pacheco", "bf", "farmacia", "Farmácia", "wd:Logotipo da Drogarias Pacheco.svg"),
    ("venancio-bf", "Drogaria Venâncio", "Venâncio", "bf", "farmacia", "Farmácia", ""),
    ("drogasmil-bf", "Drogasmil", "Drogasmil", "bf", "farmacia", "Farmácia", ""),
    # mercados
    ("zona-sul", "Zona Sul", "Zona Sul", "bf", "mercado", "Mercado", "site:https://www.zonasul.com.br/"),
    ("hortifruti-bf", "Hortifruti", "Hortifruti", "bf", "mercado", "Mercado", "site:https://www.hortifruti.com.br/"),
    ("pao-de-acucar-bf", "Pão de Açúcar", "Pão de Açúcar", "bf", "mercado", "Mercado", "site:https://www.paodeacucar.com/"),
    ("mundial-bf", "Supermercados Mundial", "Mundial", "bf", "mercado", "Mercado", ""),
    # ------------------------------------------------------- Campo Grande (Patrick)
    ("mcdonalds-cg", "McDonald's", "McDonald's", "cg", "restaurante", "Lanches", "wd:McDonald's Golden Arches.svg"),
    ("bobs-cg", "Bob's", "Bob's", "cg", "restaurante", "Lanches", "wd:Logotipo do Bob's.svg"),
    ("burger-king-cg", "Burger King", "Burger King", "cg", "restaurante", "Lanches", "wd:Burger King 2020.svg"),
    ("fabuloso-burger", "Fabuloso Burger", "Fabuloso Burger", "cg", "restaurante", "Lanches", ""),
    ("habibs-cg", "Habib's", "Habib's", "cg", "restaurante", "Árabe", "wd:Logotipo do Habib's.svg"),
    ("dominos-cg", "Domino's Pizza", "Domino's", "cg", "restaurante", "Pizza", "wd:Domino's 2025.svg"),
    ("parme-cg", "Parmê", "Parmê", "cg", "restaurante", "Italiana", ""),
    ("spoleto-cg", "Spoleto", "Spoleto", "cg", "restaurante", "Italiana", "wd:Logotipo do Spoleto.svg"),
    ("makimono-sushi", "Makimono Sushi", "Makimono Sushi", "cg", "restaurante", "Japonesa", ""),
    ("giraffas-cg", "Giraffas", "Giraffa's", "cg", "restaurante", "Brasileira", "site:https://www.giraffas.com.br/"),
    ("casa-do-frango", "Casa do Frango", "Casa do Frango", "cg", "restaurante", "Brasileira", ""),
    ("rei-da-picanha", "Rei da Picanha", "Rei da Picanha", "cg", "restaurante", "Brasileira", ""),
    ("acai-grumari", "Açaí Grumari", "Açaí Grumari", "cg", "restaurante", "Açaí", ""),
    ("craque-do-pao", "Craque do Pão", "Craque do Pão", "cg", "restaurante", "Cafés", "site:https://craquedopao.com.br/"),
    ("pacheco-cg", "Drogarias Pacheco", "Pacheco", "cg", "farmacia", "Farmácia", "wd:Logotipo da Drogarias Pacheco.svg"),
    ("venancio-cg", "Drogaria Venâncio", "Drogaria Venâncio", "cg", "farmacia", "Farmácia", ""),
    ("guanabara-cg", "Supermercados Guanabara", "Supermercado Guanabara", "cg", "mercado", "Mercado", "site:https://www.supermercadosguanabara.com.br/"),
    ("assai-cg", "Assaí Atacadista", "Assaí Atacadista", "cg", "mercado", "Mercado", "wd:Assaí Atacadista logo 2024.svg"),
]


# ---------------------------------------------------------------------------- baixar
import io
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "webapp" / "lojas"
UA = {"User-Agent": "Mozilla/5.0 (marin-telegram-bot; uso pessoal)"}
HOME = {"bf": (-22.9519, -43.1846), "cg": (-22.9036, -43.5611)}


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _site_icon_urls(site: str) -> list[str]:
    """Ícones que o próprio site declara, do maior pro menor."""
    html = _get(site).decode("utf-8", "ignore")
    found = []
    for tag in re.findall(r"<link[^>]+>", html, re.I):
        rel = (re.search(r'rel=["\']([^"\']+)', tag, re.I) or [None, ""])[1].lower()
        href = (re.search(r'href=["\']([^"\']+)', tag, re.I) or [None, ""])[1]
        if href and ("apple-touch-icon" in rel or rel.strip() in ("icon", "shortcut icon")):
            size = re.search(r'sizes=["\'](\d+)', tag)
            found.append((int(size.group(1)) if size else (180 if "apple" in rel else 32), urllib.parse.urljoin(site, href)))
    og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I)
    urls = [u for _s, u in sorted(found, reverse=True)]
    if og:
        urls.append(urllib.parse.urljoin(site, og.group(1)))
    return urls


def _square(data: bytes, size: int = 256):
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    img.thumbnail((int(size * 0.8), int(size * 0.8)), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return canvas.convert("RGB")


def fetch_logo(loja_id: str, logo: str) -> str:
    """Salva webapp/lojas/<id>.png; devolve a origem usada ('' se não achou)."""
    if not logo:
        return ""
    candidates = []
    if logo.startswith("wd:"):
        name = urllib.parse.quote(logo[3:].replace(" ", "_"))
        candidates = [f"https://commons.wikimedia.org/wiki/Special:FilePath/{name}?width=512"]
    elif logo.startswith("site:"):
        try:
            candidates = _site_icon_urls(logo[5:])
        except Exception as exc:
            print(f"   {loja_id}: site falhou ({type(exc).__name__})")
    for url in candidates:
        if url.lower().endswith(".svg"):
            continue
        try:
            img = _square(_get(url))
        except Exception:
            continue
        if min(img.size) < 64:
            continue
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        img.save(OUT_DIR / f"{loja_id}.png")
        return url
    return ""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    only = set(sys.argv[1:])
    for loja_id, nome, _osm, _area, _tipo, _cat, logo in LOJAS:
        if only and loja_id not in only:
            continue
        got = fetch_logo(loja_id, logo)
        print(f"{'OK ' if got else '-- '}{loja_id:22} {got[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
