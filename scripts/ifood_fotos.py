"""Fotos dos itens do iFood pelo Pexels (API oficial, chave PEXELS_API_KEY no .env) — 26/09.

Busca em inglês (em português o Pexels erra: "canja de galinha" trazia galinha viva). Salva
webapp/fotos/<chave>.jpg (quadrada, 640 px) e o crédito em webapp/fotos/creditos.json.
Itens de marca (Big Mac, Tio João…) com foto genérica ficam em PROVISORIAS: trocar pela
foto oficial (Google Imagens, devagar) quando der.

Uso: python scripts/ifood_fotos.py [chave …]   (sem argumento: só as que faltam)
     python scripts/ifood_fotos.py --escolha chave=N   (usa o N-ésimo resultado)
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOTOS = ROOT / "webapp" / "fotos"
CREDITOS = FOTOS / "creditos.json"

EN = {
    "kopenhagen/lingua-de-gato-30-un": "milk chocolate thin bars box",
    "kopenhagen/lajotinha-8-un": "milk chocolate squares",
    "kopenhagen/cappuccino": "cappuccino cup cinnamon",
    "go-sushi/combo-go-30-pecas": "sushi platter assorted",
    "go-sushi/temaki-salmao-completo": "salmon temaki hand roll",
    "go-sushi/temaki-hot": "fried sushi hand roll",
    "bobs/big-bob-combo": "burger fries soda combo",
    "mcdonalds/mcoferta-media-big-mac": "big mac fries coke meal",
    "mcdonalds/mcoferta-media-quarterao": "cheeseburger fries soda meal",
    "burger-king/combo-whopper": "whopper burger fries soda",
    "mamma-jamma/nhoque-ao-sugo": "gnocchi tomato sauce",
    "dominos/pizza-grande-pepperoni": "pepperoni pizza",
    "dominos/combo-2-pizzas-medias": "two pizzas boxes",
    "dominos/pizza-media-frango-com-catupiry": "chicken cheese pizza",
    "dominos/pizza-media-margherita": "margherita pizza basil",
    "dominos/petit-gateau": "chocolate lava cake",
    "spoleto/monte-sua-massa": "pasta bowl vegetables",
    "spoleto/penne-ao-molho-branco-com-frango": "penne chicken cream sauce",
    "spoleto/espaguete-a-bolonhesa": "spaghetti bolognese",
    "spoleto/lasanha-a-bolonhesa": "lasagna bolognese",
    "tutto-nhoque/nhoque-de-batata-ao-sugo": "potato gnocchi tomato basil",
    "tutto-nhoque/nhoque-de-batata-a-bolonhesa": "gnocchi meat ragu",
    "tutto-nhoque/nhoque-recheado-de-queijo-ao-molho-rose": "gnocchi pink sauce",
    "tutto-nhoque/tiramisu": "tiramisu",
    "gula-gula/salada-gula-gula": "chicken salad mango nuts",
    "gula-gula/file-com-fritas": "steak and fries",
    "gula-gula/frango-grelhado-com-legumes": "grilled chicken vegetables plate",
    "gula-gula/risoto-de-cogumelos": "mushroom risotto",
    "gula-gula/petit-gateau-com-sorvete": "lava cake ice cream",
    "joaquina/moqueca-de-peixe": "brazilian fish stew moqueca",
    "joaquina/escondidinho-de-carne-seca": "baked cassava mash casserole cheese",
    "joaquina/galinhada": "chicken rice turmeric",
    "joaquina/bolinho-de-feijoada-6-un": "fried croquettes plate",
    "starbucks/caramel-macchiato-grande": "caramel macchiato",
    "starbucks/frappuccino-de-caramelo-grande": "caramel frappuccino whipped cream",
    "starbucks/latte-grande": "latte coffee cup",
    "starbucks/pao-de-queijo": "brazilian cheese bread",
    "starbucks/cookie-com-gotas-de-chocolate": "chocolate chip cookie",
    "rei-do-mate/mate-gelado-com-limao-500-ml": "iced tea lemon cup",
    "rei-do-mate/cappuccino": "cappuccino",
    "rei-do-mate/pao-de-queijo-4-un": "pao de queijo",
    "rei-do-mate/croissant-de-presunto-e-queijo": "ham cheese croissant",
    "estacao-acai/acai-300-ml": "acai cup",
    "estacao-acai/acai-500-ml": "acai banana granola cup",
    "estacao-acai/acai-700-ml": "acai strawberry cup",
    "estacao-acai/tigela-fit": "acai bowl banana granola",
    "estacao-acai/tigela-nutella": "acai bowl strawberry chocolate",
    "estacao-acai/suco-de-laranja-500-ml": "orange juice glass",
    "estacao-acai/agua-de-coco-300-ml": "coconut water glass straw",
    "bacio-di-latte/copo-2-sabores": "gelato cup two flavors",
    "bacio-di-latte/copo-3-sabores": "gelato cup scoops",
    "bacio-di-latte/pote-500-ml": "gelato tub",
    "bacio-di-latte/affogato": "affogato",
    "bacio-di-latte/milkshake-de-pistache": "pistachio milkshake",
    "officina-gelato/casquinha-1-sabor": "gelato cone",
    "officina-gelato/copo-2-sabores": "ice cream cup berries",
    "officina-gelato/pote-1-litro": "ice cream container",
    "officina-gelato/picole-de-morango-com-leite-condensado": "strawberry popsicle",
    "officina-gelato/picole-de-limao-siciliano": "lemon popsicle",
    "milky-moo/milkshake-ovomaltine-500-ml": "chocolate malt milkshake",
    "milky-moo/milkshake-nutella-500-ml": "nutella milkshake",
    "milky-moo/milkshake-morango-500-ml": "strawberry milkshake",
    "milky-moo/casquinha-mista": "soft serve ice cream cone swirl",
    "cake-and-co/fatia-de-bolo-de-cenoura-com-brigadeiro": "carrot cake slice",
    "cake-and-co/fatia-de-red-velvet": "red velvet cake slice",
    "cake-and-co/bolo-de-pote-de-ninho-com-nutella": "layered dessert jar",
    "cake-and-co/brownie": "brownie walnuts",
    "cake-and-co/cookie-gigante": "giant chocolate chip cookie",
    "gurume/combinado-gurume-20-pecas": "sushi sashimi combo",
    "gurume/poke-de-salmao": "salmon poke bowl",
    "gurume/guioza-6-un": "gyoza dumplings",
    "gurume/yakisoba-de-legumes": "vegetable yakisoba noodles",
    "gurume/hot-roll-10-un": "tempura sushi roll",
    "gurume/uramaki-filadelfia-8-un": "philadelphia roll sushi",
    "mizu/combinado-16-pecas": "sushi combo plate",
    "mizu/temaki-de-salmao": "temaki salmon",
    "mizu/tacos-de-carne-3-un": "beef tacos guacamole",
    "mizu/burrito-de-frango": "chicken burrito",
    "mizu/nachos-com-guacamole": "nachos guacamole",
    "hells-burguer/hell-s-burguer": "gourmet burger bacon caramelized onion",
    "hells-burguer/smash-duplo": "double smash burger",
    "hells-burguer/chicken-hell": "crispy chicken sandwich pickles",
    "hells-burguer/batata-rustica": "rustic potato wedges",
    "hells-burguer/onion-rings": "onion rings",
    "b-de-burguer/b-classico": "classic cheeseburger lettuce tomato",
    "b-de-burguer/b-bacon": "bacon cheddar burger",
    "b-de-burguer/b-veggie": "veggie burger",
    "b-de-burguer/fritas-da-casa": "french fries skin on",
    "b-de-burguer/milkshake-de-doce-de-leite": "caramel milkshake",
    "dois-irmaos-caldos/canja-de-galinha-500-ml": "chicken rice soup",
    "dois-irmaos-caldos/caldo-verde-500-ml": "caldo verde kale soup",
    "dois-irmaos-caldos/caldo-de-feijao-500-ml": "black bean soup",
    "dois-irmaos-caldos/sopa-de-legumes-500-ml": "vegetable soup",
    "dois-irmaos-caldos/torradas-com-alho": "garlic toast",
    "refeitorio-organico/prato-organico-com-frango": "healthy plate brown rice chicken salad",
    "refeitorio-organico/prato-vegetariano": "vegetarian plate lentils vegetables",
    "refeitorio-organico/suco-verde-400-ml": "green juice",
    "uni-poke/poke-de-salmao": "salmon poke bowl mango",
    "uni-poke/poke-de-atum": "tuna poke bowl avocado",
    "uni-poke/poke-vegano": "tofu poke bowl",
    "uni-poke/kombucha": "kombucha bottle",
    "vegan-vegan/hamburguer-de-feijao": "bean burger sweet potato",
    "vegan-vegan/strogonoff-de-cogumelos": "mushroom stroganoff rice",
    "vegan-vegan/brownie-vegano": "vegan brownie",
    "natural-e-sabor/file-de-frango-grelhado": "grilled chicken rice beans salad",
    "natural-e-sabor/peixe-grelhado": "grilled fish mashed potatoes",
    "natural-e-sabor/omelete-de-legumes": "vegetable omelette",
    "natural-e-sabor/suco-natural-500-ml": "fruit juice glasses",
    "mr-wong/frango-xadrez": "kung pao chicken",
    "mr-wong/yakisoba-de-carne": "beef chow mein",
    "mr-wong/rolinho-primavera-4-un": "spring rolls",
    "china-in-box/yakissoba-tradicional": "chow mein box",
    "china-in-box/frango-xadrez": "kung pao chicken rice",
    "china-in-box/rolinho-primavera-2-un": "spring rolls sweet sour sauce",
    "china-in-box/banana-caramelada": "caramelized banana ice cream",
    "the-slow-bakery/pao-de-fermentacao-natural": "sourdough bread loaf",
    "the-slow-bakery/croissant-de-manteiga": "butter croissant",
    "the-slow-bakery/tostada-de-avocado": "avocado toast egg",
    "the-slow-bakery/cappuccino": "cappuccino latte art",
    "praia-sucos/suco-de-laranja-500-ml": "fresh orange juice",
    "praia-sucos/vitamina-de-banana-com-aveia": "banana oat smoothie",
    "praia-sucos/suco-detox": "green detox juice",
    "praia-sucos/misto-quente": "grilled ham cheese sandwich",
    "praia-sucos/tapioca-de-queijo-coalho": "tapioca crepe cheese",
    "habibs/esfiha-de-carne-10-un": "sfiha meat pies",
    "habibs/combo-bib-s": "arabic food esfiha kibbeh",
    "habibs/kibe-frito-4-un": "fried kibbeh",
    "habibs/beirute-de-frango": "chicken pita sandwich",
    "habibs/bibsfiha-de-chocolate": "chocolate pastry",
    "giraffas/brasileirinho-com-file-de-frango": "rice beans fries egg chicken plate",
    "giraffas/picanha-grelhada": "picanha rice farofa",
    "giraffas/giraffas-burger": "cheeseburger",
    "fabuloso-burger/fabuloso-x-tudo": "burger egg bacon ham cheese",
    "fabuloso-burger/fabuloso-duplo": "double cheeseburger bacon",
    "fabuloso-burger/x-salada": "cheeseburger lettuce tomato",
    "fabuloso-burger/batata-frita-com-cheddar-e-bacon": "loaded fries cheese bacon",
    "parme-cg/parmegiana-de-frango": "chicken parmigiana fries",
    "parme-cg/parmegiana-de-file": "beef parmigiana",
    "parme-cg/espaguete-ao-sugo": "spaghetti tomato sauce parmesan",
    "makimono-sushi/combinado-20-pecas": "sushi combo 20 pieces",
    "makimono-sushi/combinado-40-pecas": "large sushi platter",
    "makimono-sushi/temaki-de-salmao": "salmon hand roll",
    "casa-do-frango/frango-assado-inteiro": "whole roast chicken",
    "casa-do-frango/meio-frango-assado": "half roast chicken",
    "casa-do-frango/maionese-de-batata-500-g": "potato salad mayonnaise",
    "casa-do-frango/arroz-500-g": "white rice bowl",
    "casa-do-frango/canja-de-galinha-500-ml": "chicken soup bowl",
    "rei-da-picanha/picanha-na-chapa": "grilled picanha steak",
    "rei-da-picanha/prato-executivo-de-picanha": "steak rice beans plate",
    "rei-da-picanha/frango-grelhado": "grilled chicken breast fries",
    "acai-grumari/acai-500-ml": "acai cup toppings",
    "acai-grumari/acai-700-ml": "acai bowl fruits",
    "acai-grumari/acai-1-litro": "acai large bowl",
    "craque-do-pao/pao-frances-10-un": "bread rolls basket",
    "craque-do-pao/sonho-de-creme": "cream filled doughnut",
    "craque-do-pao/bolo-de-cenoura-com-chocolate": "carrot cake chocolate",
    "craque-do-pao/misto-quente-na-chapa": "toasted ham cheese sandwich",
    "craque-do-pao/cafe-com-leite": "coffee with milk glass",
    "produtos/banana-prata-1-kg": "bananas bunch",
    "produtos/maca-gala-1-kg": "red apples",
    "produtos/morango-250-g": "strawberries box",
    "produtos/tomate-1-kg": "tomatoes",
    "produtos/alface-crespa": "lettuce",
    "produtos/abacate-1-kg": "avocado",
    "produtos/arroz-tio-joao-1-kg": "rice bag",
    "produtos/feijao-preto-camil-1-kg": "black beans",
    "produtos/macarrao-barilla-500-g": "spaghetti package",
    "produtos/azeite-gallo-500-ml": "olive oil bottle",
    "produtos/cafe-melitta-500-g": "coffee bag package",
    "produtos/granola-800-g": "granola",
    "produtos/leite-italac-integral-1-l": "milk carton box",
    "produtos/iogurte-grego-vigor": "yogurt cups",
    "produtos/queijo-mucarela-fatiado-200-g": "sliced mozzarella cheese",
    "produtos/ovos-brancos-12-un": "eggs carton",
    "produtos/manteiga-aviacao-200-g": "butter",
    "produtos/agua-crystal-1-5-l": "water bottle",
    "produtos/coca-cola-2-l": "coca cola bottle",
    "produtos/suco-del-valle-uva-1-l": "grape juice glass",
    "produtos/agua-de-coco-kero-coco-1-l": "coconut water carton",
    "produtos/detergente-ype-500-ml": "dish soap bottle",
    "produtos/papel-higienico-neve-12-rolos": "toilet paper rolls",
    "produtos/sabao-em-po-omo-1-6-kg": "washing powder box",
    "produtos/shampoo-seda-325-ml": "shampoo bottle",
    "produtos/racao-golden-caes-pequeno-porte-3-kg": "dog food kibble bowl",
    "produtos/petisco-dog-chow-60-g": "dog treats",
    "produtos/dipirona-500-mg-10-comprimidos": "pills blister pack",
    "produtos/paracetamol-750-mg-20-comprimidos": "white tablets",
    "produtos/ibuprofeno-400-mg-10-capsulas": "capsules medicine",
    "produtos/neosaldina-20-drageas": "medicine tablets",
    "produtos/pastilha-strepsils-mel-e-limao-8-un": "throat lozenges candy",
    "produtos/vitamina-c-cewin-500-mg-30-comprimidos": "vitamin c tablets",
    "produtos/soro-fisiologico-500-ml": "saline nasal spray",
    "produtos/benegrip-20-comprimidos": "cold medicine pills",
    "produtos/absorvente-always-noturno-8-un": "sanitary pads",
    "produtos/protetor-solar-neutrogena-fps-50": "sunscreen bottle",
    "produtos/hidratante-nivea-400-ml": "body lotion",
    "produtos/demaquilante-bioderma-250-ml": "micellar water",
    "produtos/teste-de-gravidez-clear-blue": "pregnancy test",
    "produtos/buscofem-10-capsulas": "capsules pills",
}
# marca própria com foto genérica: trocar pela oficial quando der
PROVISORIAS = {k for k in EN if k.split("/")[0] in {"kopenhagen", "bobs", "mcdonalds", "burger-king", "dominos",
                                                      "spoleto", "starbucks", "rei-do-mate", "milky-moo", "habibs",
                                                      "giraffas", "china-in-box"}
               or any(m in k for m in ("tio-joao", "camil", "barilla", "gallo", "melitta", "italac", "vigor",
                                       "aviacao", "crystal", "coca-cola", "del-valle", "kero-coco", "ype", "neve",
                                       "omo", "seda", "golden", "dog-chow", "neosaldina", "strepsils", "cewin",
                                       "benegrip", "always", "neutrogena", "nivea", "bioderma", "clear-blue",
                                       "buscofem"))}


def _key() -> str:
    from dotenv import dotenv_values
    return (dotenv_values(ROOT / ".env").get("PEXELS_API_KEY") or "").strip().strip('"')


def search(query: str, n: int = 5) -> list[dict]:
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": query, "per_page": n})
    req = urllib.request.Request(url, headers={"Authorization": _key(), "User-Agent": "marin-telegram-bot"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)["photos"]


def save(key: str, photo: dict) -> None:
    from PIL import Image
    data = urllib.request.urlopen(urllib.request.Request(photo["src"]["large"], headers={"User-Agent": "marin-telegram-bot"}),
                                  timeout=30).read()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    side = min(img.size)
    img = img.crop(((img.width - side) // 2, (img.height - side) // 2, (img.width + side) // 2, (img.height + side) // 2))
    img = img.resize((640, 640), Image.LANCZOS)
    path = FOTOS / f"{key}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=86)
    cred = json.loads(CREDITOS.read_text(encoding="utf-8")) if CREDITOS.exists() else {}
    cred[key] = {"fonte": "Pexels", "fotografo": photo["photographer"], "url": photo["url"],
                 "provisoria": key in PROVISORIAS}
    CREDITOS.write_text(json.dumps(cred, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    escolha = {}
    if args and args[0] == "--escolha":
        escolha = dict((a.split("=")[0], int(a.split("=")[1])) for a in args[1:])
        keys = list(escolha)
    else:
        keys = args or [k for k in EN if not (FOTOS / f"{k}.jpg").exists()]
    for key in keys:
        try:
            photos = search(EN[key])
            idx = escolha.get(key, 1) - 1
            if len(photos) <= idx:
                print(f"-- {key}: sem resultado")
                continue
            save(key, photos[idx])
            print(f"OK {key}")
        except Exception as exc:
            print(f"-- {key}: {type(exc).__name__}")
        time.sleep(0.4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
