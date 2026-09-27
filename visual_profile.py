"""
Módulo de Perfil Visual & Continuidade de Câmera da Marina Salles (v3.7.0).
Monta o prompt Krea 2 da Marina (identidade, corpo canônico, zoom por palavras)
e gerencia o estado e a continuidade de cena/look quando o Patrick pede 'mais uma', 'outra foto' ou 'de outro ângulo'.
"""
import re
import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional

from db import db_manager

logger = logging.getLogger("VisualProfile")

# --- Krea 2 (24/09) ---------------------------------------------------------
# Os autores de todos os LoRAs Krea 2 que usamos pedem TEXTO CORRIDO (4-5
# frases), não lista de tags. O SNOFS avisa: escrever "photo"/"photograph" e
# nunca "photorealistic" (o Krea 2 viu muita arte; o termo puxa textura de
# pintura). O LoRA novo da Marina foi treinado com o gatilho "marinaX" e com
# olho/cabelo/maquiagem descritos nas legendas — então são os traços daqui que
# definem a Marina: olhos âmbar, sardinhas leves, cabelo castanho com pontas
# loiras. "unblemished skin" segura as pintas que o Emotions adora inventar.
KREA2_TRIGGER = "marinaX"
KREA2_EMOTIONS_TRIGGER = "Detailed Emotions and Expressions"
# 24/09 (bateria com o LoRA): "warm light amber" saiu amarelo demais na luz do dia.
# 26/09 (Patrick): o cabelo de agora (cabelo.py) troca estes dois pedaços na foto — cor/corte e penteado.
HAIR_COLOR = "long chestnut brown hair with golden blonde tips"
HAIR_STYLE = "semi-straight with soft waves at the ends"
KREA2_IDENTITY = (
    "a candid smartphone photo of a young Brazilian woman with soft light amber-hazel eyes, a few faint light "
    f"freckles across her nose and cheeks, and {HAIR_COLOR}, {HAIR_STYLE}"
)
KREA2_BODY_SFW = "She has a fit, slim body with a natural sun-kissed tan."
# 24/09 (Patrick): a marquinha estava grande demais — agora é de micro biquíni. Não escrever
# "G-string"/"string": o modelo desenha a calcinha em vez da marca.
KREA2_BODY_NSFW = ("She has a fit, slim body with a natural sun-kissed tan and small micro bikini tan lines "
                   "(bikini tan-lines).")   # gatilho do LoRA de marquinha, que só entra na foto adulta
KREA2_CLOTHED = "She is fully clothed, her outfit covers her chest and body."
KREA2_NUDE = {
    "frontal": "She is completely naked, facing the camera.",
    "behind": ("Seen from behind, she is completely naked, showing her round firm butt with a thin thong "
               "tan line, looking back over her shoulder."),
    "side": "Seen from the side, she is completely naked, her slim waist and arched lower back in profile.",
}
# Corpo canônico (Patrick, 24/09): o da foto "adulta_a" da rodada 2 (pilha a, slider 2.5).
# Sempre as MESMAS palavras em toda foto adulta — é o que segura o corpo igual de uma
# foto pra outra. Pinta: tentativas de "uma só" viraram 3–4 → sem pinta nenhuma (Patrick, 24/09).
# 24/09 (teste): "full" + slider 2.5 aumentou demais — o tamanho fica só com o slider;
# "single beauty mark… no other moles" virou 3–4 pintas: posição concreta obedece melhor.
# 24/09 (FinePorn): "rosa" solto saía bege/amarronzado — amarrar a cor à boca dela segura o tom.
# 24/09: a cor no meio da frase não segurou (o FinePorn embute um LoRA de seios e mamilos);
# agora a cor abre o bloco, onde o Krea 2 dá mais peso.
KREA2_BODY_CANON = (
    "Light pink nipples and light pink pussy: her small nipples and medium areolas are a clear soft pink, "
    "the same light pink as her lips, and her pussy lips are that same soft pink. Her breasts are round and "
    "natural, with tiny pale micro bikini triangle tan lines that only cover her areolas. Her skin is clear and smooth, with no moles or "
    "dots on her chest or body. Her pussy is fully shaved, small and neat, framed by a thin, narrow, "
    "high-cut micro bikini tan line on her hips. Her anus is small, tight and light pink."
)
KREA2_MIRROR = ("She is taking a mirror selfie, holding a black iPhone 16 Pro, her hand and the phone "
                "visible in the reflection.")
KREA2_PHOTO = ("It looks like a real iPhone photo: natural light, real skin texture with visible pores, "
               "unblemished skin.")
# 24/09: "corpo inteiro, câmera a alguns metros" saiu SELFIE nas duas pilhas —
# "smartphone photo" + "iPhone photo" puxavam tudo pra câmera na mão dela.
# Quando a cena é de longe, é alguém (amiga, fotógrafo) tirando a foto.
KREA2_DISTANT = ("full body", "full-body", "corpo inteiro", "corpo todo", "few meters", "from a distance",
                 "wide shot", "photographer", "taken by", "de longe", "walking", "standing on")
KREA2_FRAMING_DISTANT = ("Full body shot taken from about four meters away, showing her from head to toe with "
                         "space around her, both arms relaxed at her sides.")
KREA2_PHOTO_DISTANT = ("It is a real photo taken by a friend a few meters away with a phone, her whole body in the "
                       "frame, not a selfie: natural light, real skin texture, unblemished skin.")
# C.1b (24/09): ela mora sozinha — foto de corpo inteiro em casa é o celular apoiado
# numa prateleira com o timer, não "uma amiga tirando".
# 24/09 (teste): "phone propped on a shelf" desenhou o celular DENTRO da foto — o texto não
# pode citar o aparelho; é "foto de timer tirada da altura da prateleira".
KREA2_PROPPED = ("self-timer", "timer", "propped", "celular apoiado")
KREA2_FRAMING_PROPPED = ("Self-timer photo taken from shelf height about two meters in front of her, showing most "
                         "of her body and the room around her.")
KREA2_PHOTO_PROPPED = ("It is a real self-timer photo, her hands free, not a selfie: natural light, real skin "
                       "texture, unblemished skin.")
_PROPPED_PHRASE = re.compile(r",?\s*(?:with\s+)?(?:her\s+)?(?:phone|camera)\s+(?:propped|leaning|standing)[^,.]*", re.I)
_NOT_A_PHOTO = re.compile(r"\b(photo[- ]?realistic|hyper[- ]?realistic|ultra[- ]?realistic|high realism|realism|8k|masterpiece)\b",
                          re.IGNORECASE)


# C.1b (24/09) — zoom por palavras (guia do Loraholic pro Krea 2): o quadro é de quem vem
# primeiro e ganha mais palavras. Close/três-quartos: ela primeiro, o cômodo numa linha
# desfocada. Corpo inteiro/cômodo: o cômodo abre o prompt e o rosto fica com pouca palavra
# (o LoRA segura o rosto). Parte do corpo encostada no cenário ("pés no tapete") entra no quadro.
ZOOMS = ("close", "three_quarter", "torso", "full", "room")
# Regras pra quem escreve a ação/roupa da cena (o diretor da C.1b). Patrick, 24/09, vendo as
# fotos do apê. Sempre em frase positiva: com CFG 1 negação vira pedido.
KREA2_DIRECTOR_RULES = (
    # O slider fica em 2.5 (decisão); quem exagera é o bojo/decote da roupa.
    "Outfits: prefer soft unpadded fabrics (cotton tees, tank tops, linen dresses, bralettes); if the outfit "
    "has cups or a push-up neckline, describe it as a soft natural fit that follows her real shape.",
    # "Síndrome do pescoço quebrado": o Krea 2 entorta a cabeça em toda foto se deixar. Não é
    # regra fixa (Patrick): a cabeça inclinada pode aparecer quando a pose pede, só não sempre.
    "Posture: vary it with the pose; by default her head sits upright and level with her shoulders, and a "
    "head tilt appears only when the moment calls for it.",
    # A cara vem do estado dela, como o corpo vem do peso (Patrick, 24/09): com tesão, expressão de
    # tesão; cansada, chateada, com saudade — aparece no rosto. Sorriso só quando ela está bem.
    "Expression: take it from her current mood and arousal (the Detailed Emotions LoRA follows the words); "
    "smile only when her mood is light.",
    # Garrafa flutuando na academia: ela segurava o celular do espelho e bebia ao mesmo tempo.
    "Objects: every object is held in a named hand or rests on a named surface; in a mirror selfie one "
    "hand holds the phone, so she holds at most one other object, in her free hand.",
)
KREA2_IDENTITY_SHORT = f"a young Brazilian woman with {HAIR_COLOR} and light amber-hazel eyes"

# Aparência canônica das amigas (Patrick, 28/09), pro Instagram e fotos de rolê. Sem LoRA de rosto:
# junto do LoRA da Marina ele mistura as duas (27/09), e só texto deixa a amiga com a cara da Marina.
# O rosto vem da foto-RG (civitai_images.FRIEND_RG, troca pelo Krea 2 Edit); o texto dá o corpo e o
# cabelo pra foto de grupo sair com a amiga no lugar. "en"/"pt" = quem ela é (fixo);
# "style" = o que ela gosta de usar (entra quando o look pede, não em toda foto).
FRIENDS_VISUAL = {
    "bia_andrade": {   # RG: a nº 4 das candidatas (Patrick, 28/09) — linda, desejada, namoradeira
        "en": ("a stunning young Brazilian woman with model-like beauty, light olive skin with a soft tan, long "
               "voluminous dark brown hair in loose messy waves with subtle lighter brown highlights, thick straight "
               "dark eyebrows and dark brown almond-shaped eyes"),
        "pt": ("morena linda, com cara de modelo, pele oliva levemente bronzeada, cabelo castanho-escuro comprido e "
               "volumoso em ondas soltas com mechas mais claras, sobrancelha grossa e reta, olhos castanho-escuros "
               "amendoados"),
        "style": ("dramatic black winged eyeliner, gold hoop earrings, black chokers, black night-out outfits",
                  "delineado gatinho marcado, argolas douradas, chokers pretas, roupa preta de balada"),
    },
    "carol_menezes": {   # RG: a nº 5 (Patrick, 28/09) — rosto da nº 1, físico da nº 4, pele branca rosada
        "en": ("a gorgeous young Brazilian woman with long voluminous honey-blonde hair in loose tousled waves with "
               "darker roots, bright light blue eyes framed by long dark lashes, thick groomed brown eyebrows, a round "
               "face with full cheeks, full pink lips and a wide bright smile, fair rosy white skin with a natural "
               "pink flush on her cheeks, clear smooth even-toned skin, a fit curvy body with toned abs, and a "
               "black-ink floral and skull tattoo sleeve on her left arm"),
        "pt": ("loira de cabelo mel comprido e volumoso, ondas soltas com a raiz mais escura, olhos azul-claros, "
               "sobrancelha grossa desenhada, rosto redondo de bochecha cheia, sorriso largo, pele branca rosada, "
               "corpo definido de academia com curvas e barriga trincada, braço esquerdo fechado de tatuagem "
               "(flores e caveira)"),
        "style": ("ribbed crop tops, high-waisted leggings, glossy pink lip gloss, hair up in a high ponytail at the gym",
                  "cropped canelado, legging de cintura alta, gloss rosa, rabo alto na academia"),
    },
    # RG (Patrick, 28/09): a menina de franja da foto de grupo do teste da Bia (27/09), editada por partes no
    # Krea 2 Edit — olho levemente japonês, íris verde, nariz de ponte baixa — e colada só olho e nariz.
    "julia_azevedo": {
        "en": ("a pretty young Japanese-Brazilian woman with straight glossy jet-black hair falling just past her "
               "shoulders and thick blunt bangs, gently almond-shaped clear green eyes, a small soft nose with a low "
               "flat bridge and a small round tip, a soft round face, fair porcelain skin with rosy cheeks, soft pink "
               "lips, a slim body, and a small fine-line crescent moon tattoo on her inner right forearm"),
        "pt": ("nipo-brasileira de cabelo preto liso e brilhante passando do ombro, franja reta e cheia, olhos "
               "verdes levemente amendoados, nariz pequeno de ponte baixa, rosto redondinho, pele de porcelana com "
               "bochecha corada, magra, tatuagem fininha de lua no antebraço direito"),
        "style": ("black winged eyeliner, a thin black cord choker, black ribbed tank tops, thrifted vintage pieces, "
                  "a film camera on a strap",
                  "delineado gatinho, gargantilha de cordão preto, regata canelada preta, peças de brechó, câmera "
                  "analógica na alça"),
    },
    "theo_martins": {   # RG: a nº 2 (28/09; o Patrick deixou a escolha comigo) — rosto de frente, meio sorriso debochado
        "en": ("a handsome young Brazilian man of mixed race with warm light-brown skin, short dark brown tight curls "
               "on top with low-faded sides, dark brown eyes with long lashes, thick dark eyebrows, a sharp jawline "
               "with a neatly trimmed light stubble, and a slim tall build"),
        "pt": ("pardo de pele morena clara, cachos curtos castanho-escuros no topo com a lateral baixa em degradê, "
               "olhos castanho-escuros de cílio comprido, sobrancelha grossa, maxilar marcado com barba rala aparada, "
               "magro e alto"),
        "style": ("oversized linen shirts open at the collar, a small silver stud earring, silver rings, fashion-forward outfits",
                  "camisa de linho larga com a gola aberta, brinquinho de prata, anéis de prata, roupa de quem entende de moda"),
        "noun": "man",
    },
}
KREA2_ZOOM_OPEN = {
    "close": "A close photo of",
    "three_quarter": "A three-quarter photo, framed from just above her head down to her thighs, of",
    # 27/09 (Patrick): pose "sem rosto" das referências. Sem rosto no quadro o LoRA dela puxa o rosto
    # pra frente (24/09) — o corte fica na boca, que segura quem ela é.
    "torso": "A close photo, framed from her lips down to her upper thighs with the top edge of the frame "
             "cutting across her mouth, of",
}


def _body_parts(is_nsfw: bool, focus_angle: str, outfit: Optional[str]) -> list[str]:
    """Roupa dita pelo diretor (lingerie, toalha…) ou os blocos de sempre (vestida/nua)."""
    if outfit and is_nsfw:   # 27/09: roupa puxada/levantada — o que aparece é o corpo canônico
        return [f"She is wearing {outfit}.", KREA2_BODY_NSFW, KREA2_BODY_CANON]
    if outfit:
        return [f"She is wearing {outfit}.", KREA2_BODY_SFW]
    if is_nsfw:
        return [KREA2_NUDE.get(focus_angle, KREA2_NUDE["frontal"]), KREA2_BODY_NSFW, KREA2_BODY_CANON]
    return [KREA2_CLOTHED, KREA2_BODY_SFW]


def krea2_zoom_prompt(action: str, *, zoom: str, setting: str, backdrop: str, is_nsfw: bool,
                      focus_angle: str = "frontal", framing: str = "selfie", outfit: Optional[str] = None,
                      expression: str = "") -> str:
    """Prompt com o zoom decidido. framing: selfie | mirror | timer | friend.

    outfit: roupa dita pelo diretor (substitui a frase "vestida"); None = vestida/nua de sempre.
    expression: a cara do momento (humor/tesão dela), logo depois da ação.
    """
    zoom = zoom if zoom in ZOOMS else "close"
    action = _NOT_A_PHOTO.sub("", action or "").strip(" ,.")
    if expression:
        action = f"{action}, {expression.strip(' ,.')}"
    head = f"{KREA2_TRIGGER}, {KREA2_EMOTIONS_TRIGGER}."
    if zoom in KREA2_ZOOM_OPEN:
        identity = KREA2_IDENTITY.split(" of ", 1)[1]
        parts = [head, f"{KREA2_ZOOM_OPEN[zoom]} {identity}, {action}."]
        parts += _body_parts(is_nsfw, focus_angle, outfit)
        parts.append(f"Behind her, {backdrop}.")
    else:
        opener = "A wide view photo of" if zoom == "room" else "A photo of"
        who = (f"In the distance, {KREA2_IDENTITY_SHORT}" if zoom == "room"
               else f"Full body shot of {KREA2_IDENTITY_SHORT}")
        parts = [head, f"{opener} {setting}.", f"{who}, {action}."]
        parts += _body_parts(is_nsfw, focus_angle, outfit)
    if framing == "mirror":
        parts.append(KREA2_MIRROR)
        parts.append(KREA2_PHOTO)
    elif framing == "timer":
        parts.append(KREA2_PHOTO_PROPPED)
    elif framing == "friend":
        parts.append(KREA2_PHOTO_DISTANT)
    else:
        parts.append(KREA2_PHOTO)
    return " ".join(parts)


def krea2_pov_prompt(subject: str, setting: str, *, hand: bool = False, nails: str = "") -> str:
    """26/09 (Patrick): comida, o Milo, a vista — do ponto de vista dela. Sem gatilho nem traços dela.
    hand: a foto é da mão dela (unha pronta); nails: a frase da cor de verdade das unhas (unhas.py)."""
    subject = _NOT_A_PHOTO.sub("", subject or "").strip(" ,.")
    who = ("Only her hand is in the photo, no face." if hand
           else "No person in the photo, only her hand at the edge of the frame at most.")
    return (f"A candid iPhone photo taken by a young woman from her own point of view: {subject}. "
            f"The scene: {setting}. {who} " + (f"{nails} " if nails else "") +
            "It looks like a real iPhone photo: natural light, casual framing, real textures.")


def krea2_prompt(scene: str, *, is_nsfw: bool, focus_angle: str = "frontal", is_mirror: bool = False) -> str:
    """Prompt em texto corrido pro Krea 2, com o gatilho do LoRA dela e os traços da Marina."""
    scene = _NOT_A_PHOTO.sub("", scene or "")
    scene = re.sub(r"\s*,(\s*,)+\s*", ", ", scene)
    scene = re.sub(r"\s{2,}", " ", scene).strip(" ,.")
    propped = not is_mirror and any(k in scene.lower() for k in KREA2_PROPPED)
    distant = not is_mirror and not propped and any(k in scene.lower() for k in KREA2_DISTANT)
    if propped:
        scene = _PROPPED_PHRASE.sub("", scene).strip(" ,.")
    identity = (KREA2_IDENTITY.replace("a candid smartphone photo of", "a candid full body photo of") if distant
                else KREA2_IDENTITY.replace("a candid smartphone photo of", "a candid photo of") if propped
                else KREA2_IDENTITY)
    parts = [f"{KREA2_TRIGGER}, {KREA2_EMOTIONS_TRIGGER}. {identity[0].upper()}{identity[1:]}."]
    if distant:   # o Krea 2 pesa mais o começo: o enquadramento vem antes de tudo
        parts.insert(0, KREA2_FRAMING_DISTANT)
    elif propped:
        parts.insert(0, KREA2_FRAMING_PROPPED)
    if scene:
        parts.append(f"Scene: {scene}.")
    if is_nsfw:
        parts.append(KREA2_NUDE.get(focus_angle, KREA2_NUDE["frontal"]))
        parts.append(KREA2_BODY_NSFW)
        parts.append(KREA2_BODY_CANON)
    else:
        parts.append(KREA2_CLOTHED)
        parts.append(KREA2_BODY_SFW)
    if is_mirror:
        parts.append(KREA2_MIRROR)
    parts.append(KREA2_PHOTO_DISTANT if distant else KREA2_PHOTO_PROPPED if propped else KREA2_PHOTO)
    return " ".join(parts)


# Palavras-chave para detecção
CONTINUITY_PATTERNS = [
    r"\b(manda|tira|envia|faz|quero)\s+(outra|mais\s+uma|outra\s+foto|mais\s+foto)\b",
    r"\b(mais\s+uma|outra\s+foto|outra|tira\s+outra|manda\s+mais)\b",
    r"\b(de\s+costas\s+agora|mostra\s+de\s+costas|de\s+ladinho|mostra\s+de\s+lado|de\s+lado\s+agora)\b",
    r"\b(de\s+outro\s+ângulo|de\s+outro\s+angulo|outro\s+ângulo|outro\s+angulo|outra\s+pose|muda\s+a\s+pose)\b",
    r"\b(mostra\s+mais|quero\s+ver\s+mais|continua)\b",
]

CLOTHED_KEYWORDS = [
    "vestida", "roupa", "com roupa", "de roupa", "vestido", "calça", "short", "shorts",
    "blusa", "camisa", "camiseta", "casaco", "moletom", "pijama", "look", "lookinho",
    "clothed", "fully clothed", "dressed", "outfit", "suit", "jacket", "jeans"
]

NSFW_KEYWORDS = [
    "pelada", "nua", "sem roupa", "nude", "nudes", "naked", "topless",
    "seios", "peito", "peitos", "teta", "tetas", "mamilo", "mamilos",
    "calcinha", "sutiã", "sutia", "lingerie", "biquini", "biquíni", "bikini",
    "vagina", "pussy", "safada", "buceta", "bunda", "ass", "boobs", "breasts", "undies", "panties"
]

ROUNDASS_KEYWORDS = ["ass", "bunda", "costas", "behind", "from behind", "back view", "calcinha de costas"]
SIDEBOOB_KEYWORDS = ["sideboob", "side view", "lateral", "decote lateral", "de lado", "de ladinho"]

CONTINUITY_WINDOW_SECONDS = 45 * 60  # 45 minutos para manter o look/ambiente da mesma sessão de fotos


@dataclass
class CameraState:
    scene_tags: str
    outfit: str
    location: str
    focus_angle: str = "frontal"
    is_nsfw: bool = False
    full_prompt: str = ""
    timestamp: float = 0.0
    place_key: str = ""
    world_snapshot_id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CameraState":
        snapshot_id = d.get("world_snapshot_id")
        if snapshot_id is not None:
            try:
                snapshot_id = int(snapshot_id)
            except (TypeError, ValueError):
                snapshot_id = None
        return cls(
            scene_tags=d.get("scene_tags", ""),
            outfit=d.get("outfit", ""),
            location=d.get("location", ""),
            focus_angle=d.get("focus_angle", "frontal"),
            is_nsfw=bool(d.get("is_nsfw", False)),
            full_prompt=d.get("full_prompt", ""),
            timestamp=float(d.get("timestamp", 0.0)),
            place_key=d.get("place_key", "") or "",
            world_snapshot_id=snapshot_id,
        )


class VisualProfileManager:
    """Gerencia o DNA visual da Marina Salles, continuidade de câmera e construção de prompts."""

    def __init__(self):
        self._current_state: Optional[CameraState] = None
        self._load_state_from_db()

    def _load_state_from_db(self):
        """Restaura o último estado de câmera persistido no SQLite."""
        try:
            rel = db_manager.get_estado_relacional()
            raw = rel.get("camera_last_state")
            if raw:
                d = json.loads(raw)
                self._current_state = CameraState.from_dict(d)
                logger.info("Estado de câmera anterior restaurado do SQLite com sucesso.")
        except Exception as e:
            logger.warning(f"Não foi possível carregar camera_last_state do banco: {e}")

    def get_last_state(self) -> Optional[CameraState]:
        return self._current_state

    def clear_state(self):
        self._current_state = None
        try:
            db_manager.set_estado_relacional("camera_last_state", "")
        except Exception:
            pass

    def is_continuity_request(self, text: str) -> bool:
        """Identifica se o texto do usuário solicita continuidade da foto recente."""
        if not text:
            return False
        text_lower = text.lower().strip()
        for pattern in CONTINUITY_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        return False

    def is_nsfw_text(self, text: str) -> bool:
        """Verifica se o texto pede nudez/NSFW, tratando 'sem roupa' antes de checar termos vestidos."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["sem roupa", "sem nada", "tira a roupa", "arranca a roupa"]):
            return True
        if any(re.search(rf"\b{re.escape(kw)}\b", text_lower) for kw in CLOTHED_KEYWORDS):
            return False
        return any(re.search(rf"\b{re.escape(kw)}\b", text_lower) for kw in NSFW_KEYWORDS)


    def extract_focus_angle(self, text: str, default: str = "frontal") -> str:
        """Extrai o ângulo visual pedido pelo texto (behind, side ou frontal)."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ROUNDASS_KEYWORDS):
            return "behind"
        if any(kw in text_lower for kw in SIDEBOOB_KEYWORDS):
            return "side"
        return default

    def _infer_location(self, scene: str) -> str:
        s = scene.lower()
        if "bedroom" in s or "quarto" in s or "cama" in s or "bed" in s:
            return "bedroom"
        if "bathroom" in s or "banheiro" in s or "espelho" in s or "mirror" in s:
            return "bathroom"
        if "living room" in s or "sala" in s or "sofa" in s or "sofá" in s:
            return "living room"
        if "kitchen" in s or "cozinha" in s:
            return "kitchen"
        if "balcony" in s or "varanda" in s:
            return "balcony"
        return "modern apartment"

    def _infer_outfit(self, scene: str, is_nsfw: bool) -> str:
        if is_nsfw:
            return "completely naked"
        s = scene.lower()
        for kw in ["pajama", "pijama", "hoodie", "moletom", "dress", "vestido", "top", "lingerie", "bikini", "biquini", "shorts", "jeans"]:
            if kw in s:
                return f"casual {kw}"
        return "casual chic outfit"

    def build_scene_prompt(
        self,
        scene_description: str,
        user_intent: str = "",
        is_nsfw: Optional[bool] = None,
        focus_angle: Optional[str] = None,
        *,
        current_place_key: Optional[str] = None,
        require_world_match: bool = False,
    ) -> tuple[str, bool, str]:
        """
        Monta o prompt Krea 2 da cena. Se for detectado pedido de continuidade dentro da janela
        temporal, preserva o outfit e ambiente da foto anterior variando pose/ângulo.
        Com require_world_match, só reutiliza look/sublocal se o place_key atual coincidir.
        Retorna: (full_prompt, is_nsfw, focus_angle)
        """
        combined_text = f"{scene_description} {user_intent}".strip()
        is_continuity = self.is_continuity_request(combined_text)

        now = time.time()
        has_recent_state = (
            self._current_state is not None
            and (now - self._current_state.timestamp) <= CONTINUITY_WINDOW_SECONDS
        )
        world_ok = True
        if require_world_match and has_recent_state:
            prev = self._current_state
            if not current_place_key:
                world_ok = False
            elif prev.place_key and prev.place_key != current_place_key:
                world_ok = False
            elif not prev.place_key and current_place_key:
                # Estado legado sem place_key: não afirmar continuidade geográfica.
                world_ok = False

        if is_continuity and has_recent_state and world_ok:
            prev = self._current_state
            logger.info(f"🔄 Continuidade ativada! Reutilizando ambiente '{prev.location}' e look '{prev.outfit}'.")

            # Determina novo ângulo se solicitado
            new_angle = self.extract_focus_angle(combined_text, default=prev.focus_angle)
            actual_nsfw = prev.is_nsfw if is_nsfw is None else is_nsfw

            # Ajusta pose de continuidade
            if new_angle != prev.focus_angle:
                pose_variation = f"now showing {new_angle} angle in the same {prev.location}"
            else:
                pose_variation = f"different candid pose in the same {prev.location}, subtle playful variation"

            if actual_nsfw:
                outfit_clause = "completely naked"
            else:
                outfit_clause = prev.outfit or "casual comfortable outfit"

            scene_part = f"{pose_variation}, {outfit_clause}"
            final_angle = new_angle
            final_nsfw = actual_nsfw
        else:
            if is_continuity and has_recent_state and not world_ok:
                logger.info("Continuidade de câmera invalidada: local/contexto do mundo mudou.")
            # Nova sessão de foto
            final_nsfw = self.is_nsfw_text(combined_text) if is_nsfw is None else is_nsfw
            final_angle = self.extract_focus_angle(combined_text, default="frontal") if focus_angle is None else focus_angle
            scene_part = scene_description.strip()

        # Foto vestida nunca vira adulta: pista de roupa na cena derruba o nsfw.
        clothed_cues = ["clothed", "wearing", "dress", "vestid", "roupa", "hoodie", "top", "pajama", "pijama", "jeans", "shorts", "shirt", "casual"]
        if not final_nsfw or any(k in scene_part.lower() for k in clothed_cues):
            final_nsfw = False

        is_mirror = any(kw in combined_text.lower() for kw in ["espelho", "mirror", "selfie no espelho", "mirror selfie", "segurando celular"])
        return (krea2_prompt(scene_part, is_nsfw=final_nsfw, focus_angle=final_angle, is_mirror=is_mirror),
                final_nsfw, final_angle)


    def record_photo_generation(
        self,
        scene_tags: str,
        full_prompt: str,
        is_nsfw: bool,
        focus_angle: str = "frontal",
        outfit: str = "",
        location: str = "",
        place_key: str = "",
        world_snapshot_id: Optional[int] = None,
    ):
        """Registra foto efetivamente enviada; geração pura não deve chamar isto."""
        loc = location or self._infer_location(scene_tags)
        out = outfit or self._infer_outfit(scene_tags, is_nsfw)
        now = time.time()

        self._current_state = CameraState(
            scene_tags=scene_tags,
            outfit=out,
            location=loc,
            focus_angle=focus_angle,
            is_nsfw=is_nsfw,
            full_prompt=full_prompt,
            timestamp=now,
            place_key=place_key or "",
            world_snapshot_id=world_snapshot_id,
        )

        try:
            payload = json.dumps(self._current_state.to_dict())
            db_manager.set_estado_relacional("camera_last_state", payload)
            logger.info(
                f"📸 Estado de câmera registrado: loc={loc}, outfit={out}, "
                f"angle={focus_angle}, nsfw={is_nsfw}, place_key={place_key or '-'}"
            )
        except Exception as e:
            logger.warning(f"Falha ao persistir camera_last_state no banco: {e}")


# Instância global do perfil visual
visual_profile = VisualProfileManager()
