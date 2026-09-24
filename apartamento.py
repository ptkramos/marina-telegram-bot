"""Cânone visual do apartamento da Marina (C.1b, Patrick 24/09: "claro e praiano").

O seed do mundo só diz o essencial (7º andar, 3 quartos, vista da Enseada de
Botafogo, closet-estúdio, academia e piscina no prédio). Aqui cada cômodo ganha
móveis e cores FIXOS, sempre com as mesmas palavras — é o que faz a cama da foto
de hoje ser a mesma de amanhã. Texto em inglês, concreto (cor, material,
posição), e nunca negação: com CFG 1 o Krea 2 transforma "sem X" em pedido de X.

A luz vem da hora e do tempo, então a mesma cama aparece com sol de manhã e com
o abajur à noite.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

ROOMS: dict[str, dict] = {
    "quarto": {
        "pt": "o seu quarto",
        "scene": ("her bedroom with off-white walls, a queen bed with crisp white sheets and a beige linen "
                  "throw, a natural rattan headboard, sheer linen curtains and a light wood nightstand with a "
                  "ceramic lamp"),
        "night": "the warm glow of the ceramic bedside lamp",
        "short": "white sheets and a rattan headboard",
        "hints": r"quarto|cama|bedroom|\bbed\b|len[çc]ol|travesseiro|deitad",
    },
    "banheiro": {
        "pt": "o banheiro da sua suíte",
        "scene": ("her bathroom with light marble-look porcelain tiles, a clear glass shower enclosure, a large "
                  "round mirror with a soft backlight and a light wood vanity"),
        "night": "the soft backlight of the round mirror",
        "short": "light marble-look tiles and a round backlit mirror",
        "hints": r"banheiro|banho|chuveiro|\bbox\b|bathroom|shower|bath\b",
    },
    "closet": {
        "pt": "o seu closet-estúdio",
        "scene": ("her walk-in closet studio with white built-in shelves, an open clothing rack, a tall "
                  "full-length mirror with a thin light wood frame, a ring light on a stand and a cream armchair"),
        "night": "the bright even light of the ring light",
        "short": "white shelves and a clothing rack",
        "hints": r"closet|espelh|provador|look|mirror|arara",
    },
    "sala": {
        "pt": "a sala",
        "scene": ("her living room with light wood floors, a sand-colored linen sofa, a jute rug, a large "
                  "monstera plant, a small round dog bed beside the sofa and a big window facing Botafogo bay"),
        "night": "warm floor lamp light, the city lights of Botafogo in the window",
        "short": "a sand linen sofa and a monstera plant",
        "hints": r"\bsala\b|sof[aá]|sofa|living room|\btv\b|televis",
    },
    "cozinha": {
        "pt": "a cozinha",
        "scene": ("her open kitchen with white cabinets, a white quartz countertop, two high light wood stools "
                  "and small potted herbs by the window"),
        "night": "warm pendant lights over the countertop",
        "short": "white cabinets and a white quartz countertop",
        "hints": r"cozinha|kitchen|bancada|fog[aã]o|geladeira|caf[eé] da manh",
    },
    "varanda": {
        "pt": "a varanda",
        "scene": ("her seventh-floor balcony with a glass railing, a light wood deck, potted plants and a woven "
                  "hanging chair, overlooking Botafogo bay with Sugarloaf Mountain in the distance"),
        "night": "the city lights of Botafogo bay and a warm wall sconce",
        "short": "a glass railing and Botafogo bay behind",
        "hints": r"varanda|sacada|balcony|p[aã]o de a[çc][úu]car",
    },
    "academia": {
        "pt": "a academia do prédio",
        "scene": ("the small gym of her building with a mirrored wall, a rack of dumbbells, a treadmill and a "
                  "black rubber floor"),
        "night": "bright white ceiling lights",
        "short": "a mirrored wall and dumbbells",
        "hints": r"academia do pr[eé]dio|gym|academia",
    },
    "piscina": {
        "pt": "a piscina do prédio",
        "scene": ("the rooftop pool of her building with a light stone deck, white loungers and a view over "
                  "Botafogo"),
        "night": "the glow of the underwater pool lights",
        "short": "white loungers and blue pool water",
        "hints": r"piscina|pool",
    },
}

# camera_world.ROOM_HINTS → cômodo daqui
FROM_CAMERA = {"bedroom": "quarto", "bathroom": "banheiro", "living room": "sala",
               "kitchen": "cozinha", "balcony": "varanda"}

# Cômodos sem janela pra fora: a luz é sempre a de dentro.
_INDOOR_ONLY = {"banheiro", "closet", "academia"}


def room_for(text: str, default: Optional[str] = None) -> Optional[str]:
    """Cômodo citado no texto (pedido dele, fala dela, sublocal da câmera)."""
    low = (text or "").lower()
    if low in FROM_CAMERA:
        return FROM_CAMERA[low]
    for key, room in ROOMS.items():
        if re.search(room["hints"], low):
            return key
    return default


def light(room: str, now: datetime, weather: Optional[str] = None) -> str:
    """Luz pela hora e pelo tempo (Rio no fim de setembro: sol ~5h50–18h)."""
    h = now.hour + now.minute / 60
    night = h < 6 or h >= 18.3
    if night or room in _INDOOR_ONLY:
        return ROOMS[room]["night"] if night else _indoor_day(room)
    if weather and re.search(r"chuv|nubl|rain|cloud|garoa", weather.lower()):
        return "soft diffused grey daylight from an overcast sky"
    if h < 9.5:
        return "soft morning sunlight"
    if h >= 16.5:
        return "warm golden hour sunlight"
    return "bright natural daylight"


def _indoor_day(room: str) -> str:
    return {"banheiro": "soft daylight from a small frosted window",
            "closet": "the bright even light of the ring light",
            "academia": "bright white ceiling lights"}[room]


def setting(room: str, now: datetime, weather: Optional[str] = None) -> str:
    """Cômodo inteiro — abre o prompt quando o zoom é de corpo inteiro ou do cômodo."""
    room = room if room in ROOMS else "quarto"
    return f"{ROOMS[room]['scene']}, lit by {light(room, now, weather)}"


def backdrop(room: str, now: datetime, weather: Optional[str] = None) -> str:
    """Fundo desfocado — uma linha só, pro close e pro três-quartos (o zoom é orçamento de palavras)."""
    room = room if room in ROOMS else "quarto"
    name = ROOMS[room]["scene"].split(" with ")[0]
    return f"{name} in soft focus: {ROOMS[room]['short']}, {light(room, now, weather)}"


def scene(room: str, now: datetime, weather: Optional[str] = None) -> str:
    """Frase do cômodo pro prompt do Krea 2."""
    room = room if room in ROOMS else "quarto"
    return f"She is in {ROOMS[room]['scene']}, lit by {light(room, now, weather)}"
