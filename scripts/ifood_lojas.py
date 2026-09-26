"""Lojas reais do iFood da Marina (26/09, decisão do Patrick).

Base: OpenStreetMap (© contribuidores do OpenStreetMap, ODbL) — nome, tipo e posição reais.
Nada vem da API do iFood. Botafogo é a vizinhança dela; Campo Grande, a do Patrick (o presente
que ela manda pra ele sai de loja perto dele).

Cada loja: (id, nome como no app, nome no OSM, área, tipo, categoria, logo)
logo: "wd:<arquivo no Wikimedia Commons>" | "site:<url>" (ícone/og:image do site) | "" (procurar)

Uso: python scripts/ifood_lojas.py  →  webapp/lojas.json + webapp/lojas/<id>.png
"""
from __future__ import annotations

# 26/09 (Patrick): loja de bairro sem logo fácil sai. Ficaram só as com logo real.
# logo: "wd:" Wikimedia · "site:" ícone do site · "print:" recortado dos prints do iFood do Patrick · "google:" Google Imagens
LOJAS = [
    # ------------------------------------------------------------ Botafogo (ela)
    ("kopenhagen", "Kopenhagen", "Kopenhagen", "bf", "restaurante", "Doces", "wd:Logotipo da Kopenhagen.svg"),
    ("megamatte-bf", "Megamatte", "Megamatte", "bf", "restaurante", "Açaí e sucos", "site:https://megamatte.com.br/"),
    ("go-sushi", "Go Sushi", "Go Sushi", "bf", "restaurante", "Japonesa", "site:https://gosushi.com.br/"),
    ("bobs-bf", "Bob's", "Bob's", "bf", "restaurante", "Lanches", "wd:Logotipo do Bob's.svg"),
    ("mcdonalds-bf", "McDonald's", "McDonald's", "bf", "restaurante", "Lanches", "wd:McDonald's Golden Arches.svg"),
    ("burger-king-bf", "Burger King", "Burger King", "bf", "restaurante", "Lanches", "wd:Burger King 2020.svg"),
    ("ferro-e-farinha", "Ferro e Farinha", "Ferro e Farinha", "bf", "restaurante", "Pizza", "site:https://ferroefarinha.com.br/"),
    ("mamma-jamma", "Mamma Jamma", "Mamma Jamma", "bf", "restaurante", "Pizza", "site:https://mammajamma.com.br/"),
    ("dominos-bf", "Domino's Pizza", "Domino's", "bf", "restaurante", "Pizza", "wd:Domino's 2025.svg"),
    ("spoleto-bf", "Spoleto", "Spoleto", "bf", "restaurante", "Italiana", "wd:Logotipo do Spoleto.svg"),
    ("tutto-nhoque", "Tutto Nhoque", "Tutto Nhoque", "bf", "restaurante", "Italiana", "google:"),
    ("gula-gula", "Gula Gula", "Gula Gula", "bf", "restaurante", "Brasileira", "site:https://gulagula.com.br/"),
    ("joaquina", "Joaquina", "Joaquina", "bf", "restaurante", "Brasileira", "site:https://joaquinarestaurante.com.br/"),
    ("starbucks-bf", "Starbucks", "Starbucks", "bf", "restaurante", "Cafés", "site:https://www.starbucks.com/"),
    ("rei-do-mate", "Rei do Mate", "Rei do Mate", "bf", "restaurante", "Cafés", "wd:Logotipo da Rei do Mate.svg"),
    ("pacheco-bf", "Drogarias Pacheco", "Pacheco", "bf", "farmacia", "Farmácia", "wd:Logotipo da Drogarias Pacheco.svg"),
    ("venancio-bf", "Drogaria Venâncio", "Venâncio", "bf", "farmacia", "Farmácia", "print:"),
    ("drogasmil-bf", "Drogasmil", "Drogasmil", "bf", "farmacia", "Farmácia", "print:"),
    ("cristal-bf", "Drogaria Cristal", "Cristal", "bf", "farmacia", "Farmácia", "print:"),
    ("supermarket-bf", "Supermarket", "Supermarket Botafogo", "bf", "mercado", "Mercado", "print:"),
    # 26/09: mercados e farmácias são importantes pra ela — logos pelo Google Imagens (ícone de app)
    ("zona-sul", "Zona Sul", "Zona Sul", "bf", "mercado", "Mercado", "google:"),
    ("hortifruti-bf", "Hortifruti", "Hortifruti", "bf", "mercado", "Mercado", "google:"),
    ("pao-de-acucar-bf", "Pão de Açúcar", "Pão de Açúcar", "bf", "mercado", "Mercado", "google:"),
    ("mundial-bf", "Supermercados Mundial", "Mundial", "bf", "mercado", "Mercado", "google:"),
    ("droga-raia-bf", "Droga Raia", "Droga Raia", "bf", "farmacia", "Farmácia", "google:"),
    # 26/09: restaurantes de bairro de volta, logo pelo Google Imagens ("conferir": nome repetido em outras cidades)
    ("estacao-acai", "Estação do Açaí", "Estação do Açaí", "bf", "restaurante", "Açaí", "google:"),
    ("bacio-di-latte", "Bacio di Latte", "Bacio di Latte", "bf", "restaurante", "Sorvetes", "google:"),
    ("officina-gelato", "Officina del Gelato", "Officina del Gelato", "bf", "restaurante", "Sorvetes", "google:"),
    ("milky-moo", "Milky Moo", "Milky Moo", "bf", "restaurante", "Doces", "google:"),
    ("cake-and-co", "Cake & Co.", "Cake & Co.", "bf", "restaurante", "Doces", "google:conferir"),
    ("gurume", "Gurumê", "Gurumê", "bf", "restaurante", "Japonesa", "google:"),
    ("mizu", "Mizu", "Mizu", "bf", "restaurante", "Japonesa", "google:"),
    ("hells-burguer", "Hell's Burguer", "Hell's Burguer", "bf", "restaurante", "Lanches", "google:"),
    ("b-de-burguer", "B de Burguer", "B de Burguer", "bf", "restaurante", "Lanches", "google:"),
    ("dois-irmaos-caldos", "Dois Irmãos Caldos e Sopas", "Dois Irmãos Caldos e Sopas", "bf", "restaurante", "Brasileira", "google:"),
    ("refeitorio-organico", "Refeitório Orgânico", "Refeitório Orgânico", "bf", "restaurante", "Saudável", "google:"),
    ("uni-poke", "Uni", "Uni", "bf", "restaurante", "Saudável", "google:"),
    ("vegan-vegan", "Vegan Vegan", "Vegan Vegan", "bf", "restaurante", "Saudável", "google:"),
    ("natural-e-sabor", "Natural & Sabor", "Natural & Sabor", "bf", "restaurante", "Saudável", "google:"),
    ("mr-wong", "Mr. Wong", "Mr. Wong", "bf", "restaurante", "Chinesa", "google:conferir"),
    ("china-in-box-bf", "China in Box", "China in Box", "bf", "restaurante", "Chinesa", "google:"),
    ("the-slow-bakery", "The Slow Bakery", "The Slow Bakery", "bf", "restaurante", "Cafés", "google:"),
    ("praia-sucos", "Praia Sucos", "Praia Sucos", "bf", "restaurante", "Açaí e sucos", "google:"),
    # ------------------------------------------------------- Campo Grande (Patrick)
    ("mcdonalds-cg", "McDonald's", "McDonald's", "cg", "restaurante", "Lanches", "wd:McDonald's Golden Arches.svg"),
    ("bobs-cg", "Bob's", "Bob's", "cg", "restaurante", "Lanches", "wd:Logotipo do Bob's.svg"),
    ("burger-king-cg", "Burger King", "Burger King", "cg", "restaurante", "Lanches", "wd:Burger King 2020.svg"),
    ("habibs-cg", "Habib's", "Habib's", "cg", "restaurante", "Árabe", "wd:Logotipo do Habib's.svg"),
    ("dominos-cg", "Domino's Pizza", "Domino's", "cg", "restaurante", "Pizza", "wd:Domino's 2025.svg"),
    ("spoleto-cg", "Spoleto", "Spoleto", "cg", "restaurante", "Italiana", "wd:Logotipo do Spoleto.svg"),
    ("giraffas-cg", "Giraffas", "Giraffa's", "cg", "restaurante", "Brasileira", "site:https://www.giraffas.com.br/"),
    ("fabuloso-burger", "Fabuloso Burger", "Fabuloso Burger", "cg", "restaurante", "Lanches", "google:"),
    ("parme-cg", "Parmê", "Parmê", "cg", "restaurante", "Italiana", "google:"),
    ("makimono-sushi", "Makimono Sushi", "Makimono Sushi", "cg", "restaurante", "Japonesa", "google:"),
    ("casa-do-frango", "Casa do Frango", "Casa do Frango", "cg", "restaurante", "Brasileira", "google:"),
    ("rei-da-picanha", "Rei da Picanha", "Rei da Picanha", "cg", "restaurante", "Brasileira", "google:conferir"),
    ("acai-grumari", "Açaí Grumari", "Açaí Grumari", "cg", "restaurante", "Açaí", "google:"),
    ("craque-do-pao", "Craque do Pão", "Craque do Pão", "cg", "restaurante", "Cafés", "google:"),
    ("pacheco-cg", "Drogarias Pacheco", "Pacheco", "cg", "farmacia", "Farmácia", "wd:Logotipo da Drogarias Pacheco.svg"),
    ("venancio-cg", "Drogaria Venâncio", "Drogaria Venâncio", "cg", "farmacia", "Farmácia", "print:"),
    ("max-cg", "Drogarias Max", "Drogarias Max", "cg", "farmacia", "Farmácia", "print:"),
    ("guanabara-cg", "Supermercados Guanabara", "Supermercado Guanabara", "cg", "mercado", "Mercado", "site:https://www.supermercadosguanabara.com.br/"),
    ("assai-cg", "Assaí Atacadista", "Assaí Atacadista", "cg", "mercado", "Mercado", "wd:Assaí Atacadista logo 2024.svg"),
    ("carrefour-cg", "Carrefour", "Carrefour", "cg", "mercado", "Mercado", "print:"),
    ("supermarket-cg", "Supermarket", "Supermarket", "cg", "mercado", "Mercado", "print:"),
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
