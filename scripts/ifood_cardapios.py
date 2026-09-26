"""Cardápios do iFood da Marina (26/09). Cânone do mundo dela, não cópia do iFood.

Redes: produtos com os nomes oficiais (Big Mac, Whopper…). Lojas de bairro: pratos coerentes
com a casa. Preços do Rio em 2026 (calibrados pelos prints do Patrick: X-Tudo R$ 26,99,
McOferta Big Mac R$ 45,90, smoothie R$ 26,90).

Formato: loja_id → {seção: [(nome, descrição, preço), …]}. A 1ª seção são os Destaques.
"""
from __future__ import annotations

# item: (nome, descrição, preço)  — preço em reais
CARDAPIOS: dict[str, dict[str, list[tuple[str, str, float]]]] = {
    # ================================================================ Botafogo
    "estacao-acai": {
        "Açaí no copo": [
            ("Açaí 300 ml", "Açaí puro batido na hora com 2 acompanhamentos.", 19.90),
            ("Açaí 500 ml", "Açaí com banana, granola e leite em pó.", 27.90),
            ("Açaí 700 ml", "Açaí com morango, leite ninho e paçoca.", 35.90),
        ],
        "Tigelas": [
            ("Tigela Fit", "Açaí sem açúcar, banana, granola sem açúcar e mel.", 32.90),
            ("Tigela Nutella", "Açaí, Nutella, morango e leite ninho.", 39.90),
        ],
        "Bebidas": [
            ("Suco de laranja 500 ml", "Laranja espremida na hora.", 14.00),
            ("Água de coco 300 ml", "Gelada.", 9.00),
        ],
    },
    "bacio-di-latte": {
        "Gelatos": [
            ("Copo 2 sabores", "Escolha 2 sabores do dia. Pistache, doce de leite e chocolate belga são os mais pedidos.", 29.00),
            ("Copo 3 sabores", "Escolha 3 sabores do dia.", 36.00),
            ("Pote 500 ml", "Até 3 sabores pra levar pra casa.", 69.00),
        ],
        "Especiais": [
            ("Affogato", "Gelato de creme com um espresso por cima.", 24.00),
            ("Milkshake de pistache", "Batido com gelato de pistache.", 34.00),
        ],
    },
    "officina-gelato": {
        "Gelatos": [
            ("Casquinha 1 sabor", "Gelato artesanal na casquinha.", 18.00),
            ("Copo 2 sabores", "Frutas vermelhas, maracujá, chocolate 70%…", 26.00),
            ("Pote 1 litro", "Até 4 sabores.", 98.00),
        ],
        "Picolés": [
            ("Picolé de morango com leite condensado", "Artesanal.", 14.00),
            ("Picolé de limão siciliano", "Artesanal, sem lactose.", 12.00),
        ],
    },
    "milky-moo": {
        "Milkshakes": [
            ("Milkshake Ovomaltine 500 ml", "O clássico, com Ovomaltine crocante.", 26.90),
            ("Milkshake Nutella 500 ml", "Batido com Nutella e calda.", 29.90),
            ("Milkshake Morango 500 ml", "Morango com chantilly.", 24.90),
        ],
        "Casquinhas": [
            ("Casquinha mista", "Baunilha e chocolate.", 9.90),
        ],
    },
    "kopenhagen": {
        "Chocolates": [
            ("Língua de Gato 30 un", "Chocolate ao leite, o clássico da casa.", 69.90),
            ("Nhá Benta 4 un", "Marshmallow coberto com chocolate.", 39.90),
            ("Lajotinha 8 un", "Chocolate ao leite em tabletes.", 44.90),
        ],
        "Cafeteria": [
            ("Chocolate quente", "Cremoso, com chocolate da casa.", 22.00),
            ("Cappuccino", "Com canela.", 16.00),
        ],
    },
    "cake-and-co": {
        "Bolos": [
            ("Fatia de bolo de cenoura com brigadeiro", "Cobertura generosa de brigadeiro.", 19.00),
            ("Fatia de red velvet", "Com cream cheese.", 22.00),
            ("Bolo de pote de ninho com Nutella", "Camadas de massa branca, creme de ninho e Nutella.", 18.00),
        ],
        "Doces": [
            ("Brownie", "Com castanhas.", 14.00),
            ("Cookie gigante", "Gotas de chocolate.", 12.00),
        ],
    },
    "gurume": {
        "Destaques": [
            ("Combinado Gurumê 20 peças", "Sashimis, uramakis e niguiris do dia.", 119.00),
            ("Poke de salmão", "Arroz, salmão, avocado, edamame, cebola roxa e molho da casa.", 64.00),
        ],
        "Quentes": [
            ("Guioza 6 un", "Recheado de carne suína, grelhado.", 42.00),
            ("Yakisoba de legumes", "Macarrão com legumes na chapa.", 58.00),
        ],
        "Rolls": [
            ("Hot roll 10 un", "Salmão e cream cheese empanado.", 46.00),
            ("Uramaki filadélfia 8 un", "Salmão, cream cheese e cebolinha.", 44.00),
        ],
    },
    "mizu": {
        "Japonês": [
            ("Combinado 16 peças", "Sashimi, uramaki e hossomaki.", 89.00),
            ("Temaki de salmão", "Salmão, cream cheese e cebolinha.", 36.00),
        ],
        "Mexicano": [
            ("Tacos de carne 3 un", "Tortilha de milho, carne, guacamole e pico de gallo.", 48.00),
            ("Burrito de frango", "Frango, arroz, feijão, queijo e sour cream.", 46.00),
            ("Nachos com guacamole", "Pra dividir.", 38.00),
        ],
    },
    "go-sushi": {
        "Combinados": [
            ("Combo Go 30 peças", "Pra dois: sashimi, uramaki, hot e niguiri.", 129.00),
            ("Combo 15 peças", "Individual.", 69.00),
        ],
        "Temakis": [
            ("Temaki salmão completo", "Salmão, cream cheese e cebolinha.", 34.00),
            ("Temaki hot", "Empanado, com tarê.", 36.00),
        ],
    },
    "bobs-bf": {
        "Destaques": [
            ("Big Bob Combo", "Big Bob, batata média e refrigerante 500 ml.", 39.90),
            ("Milkshake Ovomaltine 400 ml", "O clássico do Bob's.", 21.90),
        ],
        "Sanduíches": [
            ("Big Bob", "Dois hambúrgueres, queijo, alface e molho especial.", 26.90),
            ("Cheddar Australiano", "Hambúrguer, cheddar e pão australiano.", 27.90),
        ],
        "Acompanhamentos": [
            ("Batata média", "Crocante.", 12.90),
        ],
    },
    "mcdonalds-bf": {
        "Destaques": [
            ("McOferta Média Big Mac", "Big Mac, McFritas média e bebida média.", 45.90),
            ("McOferta Média Quarterão", "Quarterão com queijo, McFritas média e bebida.", 45.90),
        ],
        "Sanduíches": [
            ("Big Mac", "Dois hambúrgueres, alface, queijo, molho especial, cebola e picles no pão com gergelim.", 29.90),
            ("Cheeseburger", "Hambúrguer, queijo, picles e cebola.", 12.90),
            ("McChicken", "Frango empanado, alface e maionese.", 24.90),
        ],
        "Sobremesas": [
            ("McFlurry Ovomaltine", "Sorvete com Ovomaltine.", 16.90),
            ("Casquinha", "Baunilha.", 5.90),
        ],
    },
    "burger-king-bf": {
        "Destaques": [
            ("Combo Whopper", "Whopper, batata média e refrigerante.", 44.90),
            ("Combo Stacker Duplo", "Stacker duplo, batata e refrigerante.", 42.90),
        ],
        "Sanduíches": [
            ("Whopper", "Carne grelhada no fogo, queijo, alface, tomate, cebola, picles e maionese.", 29.90),
            ("Chicken Crisp", "Frango empanado e maionese.", 19.90),
        ],
        "Sobremesas": [
            ("Sundae de chocolate", "Com calda.", 11.90),
        ],
    },
    "hells-burguer": {
        "Burgers": [
            ("Hell's Burguer", "Blend 180 g, cheddar inglês, bacon e cebola caramelizada no brioche.", 44.00),
            ("Smash duplo", "Dois smash de 90 g, queijo prato e molho da casa.", 36.00),
            ("Chicken Hell", "Frango crocante, picles e maionese de alho.", 38.00),
        ],
        "Acompanhamentos": [
            ("Batata rústica", "Com páprica e maionese da casa.", 22.00),
            ("Onion rings", "Anéis de cebola empanados.", 24.00),
        ],
    },
    "b-de-burguer": {
        "Burgers": [
            ("B Clássico", "Blend 160 g, queijo, alface, tomate e molho B.", 39.00),
            ("B Bacon", "Blend 160 g, cheddar e bacon crocante.", 44.00),
            ("B Veggie", "Hambúrguer de grão-de-bico e maionese de ervas.", 38.00),
        ],
        "Extras": [
            ("Fritas da casa", "Batata com casca.", 19.00),
            ("Milkshake de doce de leite", "400 ml.", 24.00),
        ],
    },
    "ferro-e-farinha": {
        "Pizzas de fermentação natural": [
            ("Margherita", "Molho de tomate, muçarela de búfala e manjericão.", 72.00),
            ("Diavola", "Molho, muçarela e salame picante.", 82.00),
            ("Quatro queijos", "Muçarela, gorgonzola, parmesão e catupiry.", 84.00),
        ],
        "Sobremesas": [
            ("Pizza de Nutella com morango", "Pequena.", 48.00),
        ],
    },
    "mamma-jamma": {
        "Pizzas": [
            ("Margherita", "Tomate, muçarela e manjericão.", 68.00),
            ("Calabresa", "Calabresa fatiada e cebola.", 72.00),
            ("Portuguesa", "Presunto, ovo, cebola, azeitona e muçarela.", 78.00),
        ],
        "Massas": [
            ("Nhoque ao sugo", "Com parmesão.", 56.00),
        ],
    },
    "dominos-bf": {
        "Destaques": [
            ("Pizza grande Pepperoni", "Muçarela e pepperoni.", 69.90),
            ("Combo 2 pizzas médias", "Escolha 2 sabores tradicionais.", 99.90),
        ],
        "Pizzas": [
            ("Pizza média Frango com Catupiry", "Frango desfiado e catupiry.", 54.90),
            ("Pizza média Margherita", "Muçarela, tomate e manjericão.", 49.90),
        ],
        "Sobremesas": [
            ("Petit Gâteau", "Com recheio de chocolate.", 19.90),
        ],
    },
    "spoleto-bf": {
        "Massas": [
            ("Monte sua massa", "Escolha massa, molho e até 4 ingredientes.", 42.90),
            ("Penne ao molho branco com frango", "Frango, champignon e molho branco.", 44.90),
            ("Espaguete à bolonhesa", "Molho de carne da casa.", 39.90),
        ],
        "Lasanhas": [
            ("Lasanha à bolonhesa", "Individual.", 46.90),
        ],
    },
    "tutto-nhoque": {
        "Nhoques": [
            ("Nhoque de batata ao sugo", "Molho de tomate fresco e manjericão.", 49.00),
            ("Nhoque de batata à bolonhesa", "Ragu de carne.", 56.00),
            ("Nhoque recheado de queijo ao molho rosé", "O mais pedido da casa.", 62.00),
        ],
        "Sobremesas": [
            ("Tiramisù", "Individual.", 24.00),
        ],
    },
    "gula-gula": {
        "Destaques": [
            ("Salada Gula Gula", "Folhas, frango grelhado, manga, castanhas e molho de mostarda e mel.", 64.00),
            ("Filé com fritas", "Filé mignon grelhado com batatas fritas.", 89.00),
        ],
        "Pratos": [
            ("Frango grelhado com legumes", "Com arroz de ervas.", 62.00),
            ("Risoto de cogumelos", "Shiitake, shimeji e parmesão.", 72.00),
        ],
        "Sobremesas": [
            ("Petit gâteau com sorvete", "Chocolate quente e sorvete de creme.", 34.00),
        ],
    },
    "joaquina": {
        "Pratos": [
            ("Moqueca de peixe", "Com arroz e pirão. Serve 1 pessoa.", 79.00),
            ("Escondidinho de carne-seca", "Com purê de aipim e queijo gratinado.", 58.00),
            ("Galinhada", "Arroz com frango, açafrão e cheiro-verde.", 52.00),
        ],
        "Petiscos": [
            ("Bolinho de feijoada 6 un", "Com couve e torresmo.", 38.00),
        ],
    },
    "dois-irmaos-caldos": {
        "Caldos e sopas": [
            ("Canja de galinha 500 ml", "Frango desfiado, arroz e legumes. Pra quem tá dodói.", 29.00),
            ("Caldo verde 500 ml", "Batata, couve e calabresa.", 28.00),
            ("Caldo de feijão 500 ml", "Com bacon e torradinhas.", 27.00),
            ("Sopa de legumes 500 ml", "Leve, sem carne.", 25.00),
        ],
        "Acompanhamentos": [
            ("Torradas com alho", "Porção.", 9.00),
        ],
    },
    "refeitorio-organico": {
        "Pratos do dia": [
            ("Prato orgânico com frango", "Arroz integral, feijão, frango grelhado e salada da horta.", 54.00),
            ("Prato vegetariano", "Arroz integral, lentilha, legumes assados e salada.", 48.00),
        ],
        "Sucos": [
            ("Suco verde 400 ml", "Couve, limão, gengibre e maçã.", 16.00),
        ],
    },
    "uni-poke": {
        "Pokes": [
            ("Poke de salmão", "Arroz de sushi, salmão, manga, pepino, edamame e molho ponzu.", 59.00),
            ("Poke de atum", "Atum, avocado, cebola roxa e shoyu.", 62.00),
            ("Poke vegano", "Tofu, cenoura, repolho roxo e molho de gergelim.", 49.00),
        ],
        "Bebidas": [
            ("Kombucha", "300 ml.", 16.00),
        ],
    },
    "vegan-vegan": {
        "Pratos": [
            ("Hambúrguer de feijão", "Com batata-doce assada.", 46.00),
            ("Strogonoff de cogumelos", "Com arroz e batata palha.", 52.00),
        ],
        "Doces": [
            ("Brownie vegano", "Sem lactose e sem ovo.", 16.00),
        ],
    },
    "natural-e-sabor": {
        "Pratos": [
            ("Filé de frango grelhado", "Com arroz, feijão, salada e legumes.", 38.00),
            ("Peixe grelhado", "Com arroz, purê e salada.", 44.00),
            ("Omelete de legumes", "Com salada.", 29.00),
        ],
        "Sucos": [
            ("Suco natural 500 ml", "Laranja, abacaxi com hortelã ou melancia.", 12.00),
        ],
    },
    "mr-wong": {
        "Pratos": [
            ("Frango xadrez", "Frango, pimentão, amendoim e molho agridoce.", 42.00),
            ("Yakisoba de carne", "Macarrão, carne e legumes.", 44.00),
            ("Rolinho primavera 4 un", "Recheado de legumes.", 22.00),
        ],
    },
    "china-in-box-bf": {
        "Destaques": [
            ("Yakissoba tradicional", "Macarrão, carne, frango e legumes na caixinha.", 49.90),
            ("Frango xadrez", "Com arroz.", 46.90),
        ],
        "Entradas": [
            ("Rolinho primavera 2 un", "Com molho agridoce.", 16.90),
        ],
        "Sobremesas": [
            ("Banana caramelada", "Com sorvete.", 18.90),
        ],
    },
    "megamatte-bf": {
        "Açaí": [
            ("Açaí 500 ml", "Com granola e banana.", 26.00),
            ("Açaí 300 ml", "Com granola.", 18.00),
        ],
        "Sucos e mates": [
            ("Mate com limão 500 ml", "O de sempre.", 10.00),
            ("Suco de laranja 500 ml", "Natural.", 13.00),
        ],
        "Lanches": [
            ("Sanduíche natural de frango", "Pão integral, frango, cenoura e maionese light.", 18.00),
        ],
    },
    "praia-sucos": {
        "Sucos": [
            ("Suco de laranja 500 ml", "Espremido na hora.", 13.00),
            ("Vitamina de banana com aveia", "500 ml.", 16.00),
            ("Suco detox", "Couve, abacaxi, gengibre e hortelã.", 15.00),
        ],
        "Lanches": [
            ("Misto quente", "Pão de forma, presunto e queijo.", 14.00),
            ("Tapioca de queijo coalho", "Com orégano.", 16.00),
        ],
    },
    "starbucks-bf": {
        "Bebidas": [
            ("Caramel Macchiato Grande", "Espresso, leite vaporizado, baunilha e calda de caramelo.", 26.90),
            ("Frappuccino de Caramelo Grande", "Com chantilly.", 29.90),
            ("Latte Grande", "Espresso e leite vaporizado.", 21.90),
        ],
        "Comidas": [
            ("Pão de queijo", "3 unidades.", 12.90),
            ("Cookie com gotas de chocolate", "", 11.90),
        ],
    },
    "rei-do-mate": {
        "Bebidas": [
            ("Mate gelado com limão 500 ml", "O clássico.", 11.90),
            ("Cappuccino", "Cremoso.", 13.90),
        ],
        "Salgados": [
            ("Pão de queijo 4 un", "Quentinho.", 12.90),
            ("Croissant de presunto e queijo", "", 15.90),
        ],
    },
    "the-slow-bakery": {
        "Pães": [
            ("Pão de fermentação natural", "Inteiro, casca crocante.", 32.00),
            ("Croissant de manteiga", "Folhado.", 16.00),
        ],
        "Cafés da manhã": [
            ("Tostada de avocado", "Pão de fermentação natural, avocado, ovo e gergelim.", 38.00),
            ("Cappuccino", "", 14.00),
        ],
    },
}

CARDAPIOS.update({
    # ============================================================ Campo Grande
    "mcdonalds-cg": CARDAPIOS["mcdonalds-bf"],
    "bobs-cg": CARDAPIOS["bobs-bf"],
    "burger-king-cg": CARDAPIOS["burger-king-bf"],
    "dominos-cg": CARDAPIOS["dominos-bf"],
    "spoleto-cg": CARDAPIOS["spoleto-bf"],
    "habibs-cg": {
        "Destaques": [
            ("Esfiha de carne 10 un", "A esfiha aberta do Habib's.", 29.90),
            ("Combo Bib's", "5 esfihas, 2 kibes e refrigerante.", 34.90),
        ],
        "Salgados": [
            ("Kibe frito 4 un", "Com limão.", 19.90),
            ("Beirute de frango", "Pão sírio, frango, queijo e salada.", 32.90),
        ],
        "Sobremesas": [
            ("Bibsfiha de chocolate", "Esfiha doce.", 9.90),
        ],
    },
    "giraffas-cg": {
        "Pratos": [
            ("Brasileirinho com filé de frango", "Arroz, feijão, batata frita, ovo e filé de frango.", 36.90),
            ("Picanha grelhada", "Arroz, feijão, farofa e vinagrete.", 54.90),
        ],
        "Sanduíches": [
            ("Giraffas Burger", "Hambúrguer, queijo e molho especial.", 26.90),
        ],
    },
    "fabuloso-burger": {
        "Burgers": [
            ("Fabuloso X-Tudo", "Pão, carne, ovo, bacon, presunto, queijo, alface, tomate e maionese da casa.", 29.90),
            ("Fabuloso Duplo", "Duas carnes, cheddar e bacon.", 34.90),
            ("X-Salada", "Carne, queijo, alface e tomate.", 22.90),
        ],
        "Porções": [
            ("Batata frita com cheddar e bacon", "Pra dividir.", 29.90),
        ],
    },
    "parme-cg": {
        "Destaques": [
            ("Parmegiana de frango", "Com arroz e fritas. Serve 1 pessoa.", 49.90),
            ("Parmegiana de filé", "Com arroz e fritas. Serve 1 pessoa.", 64.90),
        ],
        "Massas": [
            ("Espaguete ao sugo", "Com parmesão.", 34.90),
        ],
    },
    "makimono-sushi": {
        "Combinados": [
            ("Combinado 20 peças", "Uramaki, hot, niguiri e sashimi.", 79.90),
            ("Combinado 40 peças", "Pra dois.", 139.90),
        ],
        "Temakis": [
            ("Temaki de salmão", "Com cream cheese.", 32.90),
        ],
    },
    "casa-do-frango": {
        "Frango": [
            ("Frango assado inteiro", "Com farofa.", 54.90),
            ("Meio frango assado", "Com farofa e maionese.", 32.90),
        ],
        "Acompanhamentos": [
            ("Maionese de batata 500 g", "", 18.90),
            ("Arroz 500 g", "", 12.90),
        ],
        "Caldos": [
            ("Canja de galinha 500 ml", "Pra quem tá dodói.", 22.90),
        ],
    },
    "rei-da-picanha": {
        "Pratos": [
            ("Picanha na chapa", "Arroz, feijão tropeiro, farofa e vinagrete. Serve 2.", 119.90),
            ("Prato executivo de picanha", "Serve 1.", 54.90),
            ("Frango grelhado", "Com arroz, feijão e fritas.", 36.90),
        ],
    },
    "acai-grumari": {
        "Açaí": [
            ("Açaí 500 ml", "Com 3 acompanhamentos.", 22.90),
            ("Açaí 700 ml", "Com 4 acompanhamentos.", 29.90),
            ("Açaí 1 litro", "Pra dividir.", 39.90),
        ],
    },
    "craque-do-pao": {
        "Padaria": [
            ("Pão francês 10 un", "Quentinho.", 9.90),
            ("Sonho de creme", "", 7.90),
            ("Bolo de cenoura com chocolate", "Fatia.", 9.90),
        ],
        "Lanches": [
            ("Misto quente na chapa", "", 11.90),
            ("Café com leite", "", 6.90),
        ],
    },
})

# ============================================================== mercado e farmácia
# Produtos iguais em toda rede; o preço varia um pouco por loja (fator por loja no build).
MERCADO = {
    "Hortifruti": [
        ("Banana prata 1 kg", "", 7.99), ("Maçã gala 1 kg", "", 11.99), ("Morango 250 g", "Bandeja.", 9.99),
        ("Tomate 1 kg", "", 8.99), ("Alface crespa", "Unidade.", 3.99), ("Abacate 1 kg", "", 12.99),
    ],
    "Mercearia": [
        ("Arroz Tio João 1 kg", "", 7.49), ("Feijão preto Camil 1 kg", "", 8.99), ("Macarrão Barilla 500 g", "Espaguete n. 5.", 8.49),
        ("Azeite Gallo 500 ml", "Extra virgem.", 36.90), ("Café Melitta 500 g", "Tradicional.", 24.90), ("Granola 800 g", "", 22.90),
    ],
    "Laticínios e frios": [
        ("Leite Italac integral 1 L", "", 5.49), ("Iogurte grego Vigor", "Tradicional, 4 un.", 14.99),
        ("Queijo muçarela fatiado 200 g", "", 13.99), ("Ovos brancos 12 un", "", 13.99), ("Manteiga Aviação 200 g", "", 16.99),
    ],
    "Bebidas": [
        ("Água Crystal 1,5 L", "Sem gás.", 3.49), ("Coca-Cola 2 L", "", 11.99), ("Suco Del Valle uva 1 L", "", 8.99),
        ("Água de coco Kero Coco 1 L", "", 12.99),
    ],
    "Limpeza e higiene": [
        ("Detergente Ypê 500 ml", "", 2.99), ("Papel higiênico Neve 12 rolos", "Folha dupla.", 24.90),
        ("Sabão em pó Omo 1,6 kg", "", 32.90), ("Shampoo Seda 325 ml", "", 16.90),
    ],
    "Pet": [
        ("Ração Golden cães pequeno porte 3 kg", "Pro Milo.", 79.90), ("Petisco Dog Chow 60 g", "", 9.99),
    ],
}
FARMACIA = {
    "Dor e febre": [
        ("Dipirona 500 mg 10 comprimidos", "", 6.99), ("Paracetamol 750 mg 20 comprimidos", "", 12.99),
        ("Ibuprofeno 400 mg 10 cápsulas", "", 14.99), ("Neosaldina 20 drágeas", "", 24.90),
    ],
    "Gripe e garganta": [
        ("Pastilha Strepsils mel e limão 8 un", "", 19.90), ("Vitamina C Cewin 500 mg 30 comprimidos", "", 17.90),
        ("Soro fisiológico 500 ml", "", 7.99), ("Benegrip 20 comprimidos", "", 19.90),
    ],
    "Cuidados": [
        ("Absorvente Always noturno 8 un", "", 11.90), ("Protetor solar Neutrogena FPS 50", "200 ml.", 69.90),
        ("Hidratante Nivea 400 ml", "", 29.90), ("Demaquilante Bioderma 250 ml", "", 89.90),
    ],
    "Saúde da mulher": [
        ("Teste de gravidez Clear Blue", "", 39.90), ("Buscofem 10 cápsulas", "Pra cólica.", 22.90),
    ],
}
