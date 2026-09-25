"""C.1b — diretor de cena das fotos da Marina (Patrick, 24/09).

Quem decide a foto é ela, pelo momento: onde está (cômodo canônico do apê, ou a
rua), o clima da conversa (excitação do `intimacy`), o humor (`emotion`) e o que
o Patrick pediu. O LLM não escreve mais tags soltas: no máximo escolhe uma pose
do catálogo; cômodo, roupa, luz, zoom e expressão vêm do código.

Decisões do Patrick:
- Ousadia: entre "um passo por vez" e "ela decide". Ela sobe um degrau além do
  clima se ele pedir; às vezes provoca e manda um degrau abaixo antes.
- Sessão com gancho: a primeira foto fixa cômodo, roupa, posição e câmera; as
  seguintes só avançam a ação (mão, dedos, abrir, lamber os dedos, gozar). Só
  troca de posição se a conversa pedir.
- Expressão pelo humor e pelo tesão dela (como o corpo segue o peso).
- Roupa sem bojo exagerado; cabeça reta por padrão; objeto sempre numa mão.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

import apartamento

SESSION_KEY = "photo_session_json"
SESSION_TTL_MIN = 45
SELF_PHOTO_KEY = "photo_self_initiated_at"
# Patrick, 24/09: "uma só foto por sexting é sacanagem" — no clima ela manda mais (sem exagerar).
SELF_PHOTO_GAP_MIN = 5           # no modo íntimo
CLIMAX_PHOTO_CHANCE = 0.8        # quando ela goza, geralmente manda foto do depois
# Ideias pra legenda do pós-gozo (inspiração pro LLM, nunca frase fixa).
CLIMAX_CAPTION_IDEAS = (
    "Ideias de tom pra legenda (inspire-se, não copie): mostrar o estrago que ele fez ('olha como você me "
    "deixou'), ainda tremendo ou sem ar, sem forças pra levantar da cama, cabelo e lençol destruídos, "
    "culpar ele de brincadeira, um pedido manhoso de carinho depois.")
SELF_PHOTO_GAP_CASUAL_MIN = 60   # no dia a dia (Patrick, 24/09: "libera com limite")
PROVOKE_BELOW_CHANCE = 0.3   # pediu dois degraus acima: às vezes ela provoca com um só

# Teto de ousadia pelo clima (intimacy.IntimacyTurn.band).
CAP = {"off": 1, "cut": 0, "closing": 1, "warming": 2, "desejo": 3, "explicito": 4, "climax": 4, "afterglow": 3}
HOME = "marina_apartment"


@dataclass(frozen=True)
class Pose:
    id: str
    pt: str                       # como ela descreveria (vai pro LLM escolher e pra legenda)
    rooms: tuple                  # cômodos do apê, ou ("fora",)
    levels: tuple                 # (mínimo, máximo) de ousadia que a pose aceita
    zoom: str
    framing: str                  # selfie | mirror | timer | friend
    action: str
    angle: str = "frontal"
    outfit: Optional[str] = None  # roupa fixa da pose (toalha, biquíni, academia)
    beats: tuple = ()             # (marca, ação) em ordem; a última é o gozo


DILDO_TEXT = "a realistic pink silicone dildo with a veined shaft"


def _beats(where: str, hand: str, other: str = "") -> tuple:
    """Momentos da cena explícita — a posição fica, só a mão avança.

    other: o que a outra mão faz quando ela está livre (timer/tripé, Patrick 24/09: "um dedo dentro
    e a outra mão apertando um peito"). "squeezing her breast" liga o LoRA de apertar (0.6).
    """
    two = f", {other}" if other else ""
    return (
        ("tease", f"her {hand} hand resting on her inner thigh, {where}"),
        ("touch", f"her {hand} fingers rubbing her clit{two}, {where}"),
        # Texto aprovado com o Fingering 1.0 (Patrick, 24/09): o "dentro" com profundidade concreta.
        ("fingers", f"two fingers of her {hand} hand pushed deep inside her wet pussy up to the knuckles{two}, "
                    f"{where}"),
        ("spread", f"her {hand} fingers spreading her pussy open{two}, {where}"),
        # O dildo dela (cânone, gaveta da mesinha): feito pelo texto, o Grippy 1.0 faz entrar (24/09).
        ("dildo", f"{DILDO_TEXT} pushed deep inside her pussy, her {hand} hand holding its round suction-cup "
                  f"base{two}, {where}"),
        ("lick", f"bringing her glistening {hand} fingers to her lips and licking them, {where}"),
        ("climax", f"right after she came, her body trembling and her {hand} hand resting on her pussy{two}, "
                   f"{where}"),
    )


_SQUEEZE_LEFT = "her left hand squeezing her breast"


POSES: tuple[Pose, ...] = (
    # ---------------------------------------------------------------- quarto --
    Pose("cama_deitada_selfie", "deitada de barriga pra cima na cama, selfie de cima", ("quarto",), (0, 3),
         "close", "selfie", "lying on her back on the bed with her hair spread over the white pillow, her right "
         "arm stretched up toward the camera taking the selfie, her left arm resting beside her head"),
    Pose("cama_de_lado", "deitada de lado no travesseiro", ("quarto",), (0, 3), "close", "selfie",
         "lying on her side on the bed facing the camera, her head resting on the pillow, her left hand tucked "
         "under her cheek, her right arm stretched toward the camera taking the selfie"),
    Pose("cama_sentada_timer", "sentada de pernas cruzadas no meio da cama (timer)", ("quarto",), (0, 3), "full",
         "timer", "sitting cross-legged in the middle of the bed, her hands resting on her knees, her back straight"),
    Pose("cama_ajoelhada", "ajoelhada na cama, sentada nos calcanhares (timer)", ("quarto",), (1, 3),
         "three_quarter", "timer", "kneeling upright on the bed, sitting back on her heels, her hands resting on "
         "her thighs"),
    Pose("cama_de_brucos", "de bruços na cama, apoiada nos cotovelos (timer)", ("quarto",), (1, 3),
         "three_quarter", "timer", "lying on her stomach across the bed propped up on her elbows, her feet crossed "
         "in the air behind her, looking at the camera"),
    Pose("cama_apertando", "ajoelhada na cama apertando os seios (timer)", ("quarto",), (3, 4), "three_quarter",
         "timer", "kneeling on the bed squeezing her breasts with both hands, looking at the camera"),
    Pose("cama_pernas_abertas", "deitada de costas, pernas abertas, selfie de cima", ("quarto",), (4, 4),
         "three_quarter", "selfie", "lying on her back on the bed with her knees up and her legs spread apart, "
         "her right arm stretched up toward the camera taking the selfie",
         beats=_beats("her legs spread wide on the white sheets", "left")),
    # Tripé (Patrick, 24/09): celular fixo, as duas mãos livres pra se tocar.
    Pose("cama_tripe_duas_maos", "deitada de pernas abertas, celular no tripé, as duas mãos livres (timer)",
         ("quarto",), (3, 4), "three_quarter", "timer", "lying back on the pillows with her knees up and her legs "
         "spread apart, both hands free", beats=_beats("her legs spread wide on the white sheets", "right",
                                                      _SQUEEZE_LEFT)),
    Pose("cama_de_quatro", "de quatro na cama, de costas pra câmera (timer)", ("quarto",), (1, 4),
         "three_quarter", "timer", "on all fours on the bed seen from behind, her knees apart and her back arched, "
         "looking back over her shoulder", angle="behind",
         beats=_beats("her ass up toward the camera", "right")),
    # ---------------------------------------------------------------- closet --
    Pose("espelho_corpo", "de pé na frente do espelho grande do closet", ("closet",), (0, 3), "full", "mirror",
         "standing barefoot in front of the tall mirror, her weight on one leg, her free hand resting on her hip"),
    # 24/09 (/ruim): "de costas pro espelho" saiu irreal (reflexo e selfie brigando) — de costas é timer.
    Pose("closet_costas", "de costas pra câmera no closet, olhando por cima do ombro (timer)", ("closet",), (1, 3),
         "full", "timer", "standing with her back to the camera near the clothing rack, looking back over her "
         "shoulder, one hand resting on her lower back", angle="behind"),
    Pose("poltrona_pernas", "sentada de lado na poltrona, pernas no braço (timer)", ("closet",), (1, 3), "full",
         "timer", "sitting sideways in the cream armchair with her legs draped over one armrest, one hand in her "
         "hair"),
    Pose("poltrona_aberta", "na poltrona de frente pro espelho, perna no braço (timer)", ("closet",), (4, 4),
         "full", "timer", "sitting in the cream armchair facing the camera, one leg hooked over the armrest and "
         "her legs spread", beats=_beats("her leg hooked over the armrest", "right", _SQUEEZE_LEFT)),
    # -------------------------------------------------------------- banheiro --
    Pose("banheiro_espelho", "na pia, de frente pro espelho redondo", ("banheiro",), (0, 3), "three_quarter",
         "mirror", "standing at the vanity facing the round mirror, her free hand pushing her damp hair back"),
    Pose("banheiro_toalha", "saindo do banho, enrolada na toalha", ("banheiro",), (1, 1), "three_quarter",
         "mirror", "standing at the vanity with water drops on her shoulders, her free hand holding the towel "
         "closed at her chest", outfit="a white bath towel wrapped around her body"),
    Pose("chuveiro", "no chuveiro atrás do vidro (timer)", ("banheiro",), (3, 3), "three_quarter", "timer",
         "standing under the shower behind the glass, water running over her body, both hands running through "
         "her wet hair"),
    Pose("chuveiro_tocando", "encostada no azulejo, no chuveiro (timer)", ("banheiro",), (4, 4), "three_quarter",
         "timer", "leaning her back against the tiled wall under the shower, water running over her body, her "
         "legs apart", beats=_beats("water running down her body", "right", _SQUEEZE_LEFT)),
    # ------------------------------------------------------------------ sala --
    Pose("sofa_selfie", "encolhida no sofá, selfie", ("sala",), (0, 2), "close", "selfie",
         "curled up on the sofa with her head resting on a cushion, her right arm stretched toward the camera taking the selfie"),
    Pose("sofa_timer", "sentada no sofá com as pernas dobradas (timer)", ("sala",), (0, 3), "room", "timer",
         "sitting on the sofa with her legs tucked under her, one arm along the backrest, feet on the jute rug"),
    Pose("sala_janela", "de perfil no janelão, olhando pra câmera (timer)", ("sala",), (1, 3), "full", "timer",
         "standing by the big window in side profile, one hand resting on the window frame, looking back at the "
         "camera", angle="side"),
    # --------------------------------------------------------------- cozinha --
    Pose("cozinha_cafe", "encostada na bancada com o café", ("cozinha",), (0, 1), "three_quarter", "selfie",
         "leaning her hip against the countertop, holding a cup of coffee in her left hand, her right arm "
         "stretched toward the camera taking the selfie"),
    Pose("cozinha_bancada", "sentada na bancada (timer)", ("cozinha",), (1, 3), "full", "timer",
         "sitting on the edge of the white countertop, her hands resting on the counter beside her hips, her feet "
         "dangling"),
    # --------------------------------------------------------------- varanda --
    Pose("varanda_cadeira", "na cadeira suspensa da varanda (timer)", ("varanda",), (0, 2), "full", "timer",
         "sitting in the hanging chair, her bare feet on the wood deck, her hands resting on the chair's rim"),
    Pose("varanda_parapeito", "no guarda-corpo com a enseada atrás, selfie", ("varanda",), (0, 1),
         "three_quarter", "selfie", "leaning her left forearm on the glass railing with the bay behind her, "
         "her right arm stretched toward the camera taking the selfie"),
    # ---------------------------------------------------------------- prédio --
    Pose("academia_espelho", "no espelho da academia do prédio", ("academia",), (0, 1), "three_quarter", "mirror",
         "standing in front of the mirrored wall after a workout, her free hand resting on her hip, a light glow "
         "of sweat on her skin", outfit="black leggings and a soft unpadded black sports top"),
    Pose("piscina_espreguicadeira", "deitada na espreguiçadeira da piscina (timer)", ("piscina",), (0, 1), "full",
         "timer", "lying on a white lounger with one knee raised, her hands behind her head",
         outfit="a small soft triangle bikini in light blue"),
    # Depois de gozar (Patrick, 24/09: "adoro ver como você fica depois que goza").
    Pose("pos_gozo", "jogada na cama logo depois de gozar, selfie de cima", ("quarto",), (3, 4), "close",
         "selfie", "lying on her back on the messy white sheets right after she came, her hair tangled over the "
         "pillow, her skin glowing with sweat, her chest rising with heavy breaths, her right arm stretched up "
         "toward the camera taking the selfie"),
    # --------------------------------------------------- mostrando algo --
    # 24/09: ela prometeu 3x a foto do açaí e nunca mandou. {food} vem da conversa (FOODS).
    Pose("mostrando_comida", "selfie mostrando a comida", ("cozinha", "sala", "quarto", "varanda", "fora"),
         (0, 1), "close", "selfie", "holding {food} up close to the camera in her left hand, her right arm "
         "stretched toward the camera taking the selfie"),
    # ------------------------------------------------------------------ rua --
    Pose("fora_selfie", "selfie na rua", ("fora",), (0, 1), "close", "selfie",
         "her right arm stretched toward the camera taking the selfie at arm's length"),
    Pose("fora_amiga_corpo", "de corpo inteiro, uma amiga tirando", ("fora",), (0, 1), "full", "friend",
         "standing relaxed with her weight on one leg, one hand holding the strap of her bag"),
    Pose("fora_amiga_andando", "andando em direção à câmera, uma amiga tirando", ("fora",), (0, 1),
         "three_quarter", "friend", "walking toward the camera mid-step, one hand tucking her hair behind her ear"),
)
BY_ID = {p.id: p for p in POSES}

# A posição que eles escreveram manda na pose (24/09: ela disse "de quatro na cama" e o sorteio
# mandou de costas no espelho). Em ordem de preferência; vale a primeira que aceita o nível.
POSE_WORDS = (
    (r"de quatro|empinad|por tr[aá]s", ("cama_de_quatro",)),
    (r"pernas abertas|abr\w* as pernas|arreganhad|deitada de costas", ("cama_tripe_duas_maos", "cama_pernas_abertas")),
    (r"chuveiro|no box|no banho", ("chuveiro_tocando", "chuveiro", "banheiro_toalha", "banheiro_espelho")),
    (r"poltrona", ("poltrona_aberta", "poltrona_pernas")),
    (r"apertando (os|meus) (seios|peitos)", ("cama_apertando",)),
    (r"de bru[cç]os", ("cama_de_brucos",)),
    (r"ajoelhad|de joelhos", ("cama_ajoelhada",)),
    (r"espelho", ("espelho_corpo", "banheiro_espelho", "academia_espelho")),
    (r"sof[aá]", ("sofa_timer", "sofa_selfie")),
    (r"bancada", ("cozinha_bancada", "cozinha_cafe")),
    (r"varanda", ("varanda_cadeira", "varanda_parapeito")),
)
FOODS = (
    (r"a[cç]a[ií]", "a bowl of açaí topped with granola"),
    (r"pizza", "a slice of pizza"),
    (r"hamb[uú]rg|burger", "a juicy burger"),
    (r"sushi|temaki", "a tray of sushi"),
    (r"sorvete", "an ice cream cone"),
    (r"brigadeiro", "a small plate of brigadeiros"),
    (r"caf[eé]\b|cappuccino", "a cup of coffee"),
    (r"salada", "a bowl of salad"),
    (r"bolo", "a slice of cake"),
)


def _worded_pose(text: str, level: int, at_home: bool) -> Optional[Pose]:
    low = (text or "").lower()
    for pattern, ids in POSE_WORDS:
        if re.search(pattern, low):
            for pid in ids:
                pose = BY_ID[pid]
                if pose.levels[0] <= level <= pose.levels[1] and ("fora" in pose.rooms) != at_home:
                    return pose
    return None


def _food(text: str) -> Optional[str]:
    low = (text or "").lower()
    for pattern, food in FOODS:
        if re.search(pattern, low):
            return food
    return None

# Guarda-roupa (regra do Patrick: tecido macio, sem bojo exagerado).
WARDROBE = {
    "casa_dia": ("an oversized white cotton t-shirt and grey cotton shorts",
                 "a light blue ribbed cotton tank top and denim shorts",
                 "a loose beige linen shirt and white cotton shorts"),
    "casa_noite": ("a light pink satin camisole and matching shorts",
                   "an oversized grey hoodie and pajama shorts",
                   "a white cotton tank top and striped pajama shorts"),
    "fora": ("a white cotton tee and light blue jeans",
             "a light linen sundress with thin straps",
             "a black ribbed cotton tank top and a flowy midi skirt"),
    "provoca": ("only an oversized white t-shirt slipping off one shoulder and white cotton panties",
                "a tiny white cotton tank top and matching cotton panties",
                "a light pink satin camisole and tiny matching shorts"),
    "lingerie": ("a soft unpadded white lace bralette and matching panties",
                 "a light pink unpadded lace bralette and thong",
                 "a black sheer unpadded lace bralette and matching thong"),
}

# Pedido dele → degrau. O mais alto que aparecer vale.
_ASK = (
    (4, r"buceta|xota|xoxota|pussy|se toca|te toca|tocando|siririca|masturb|dedo|dedinho|enfia|abre (a|as|pra)|"
        r"dildo|consolo|brinquedo|"
        r"abrindo|goza|gozando|gozei|molhadinha"),
    (3, r"pelad|\bnua\b|nude|sem roupa|peit|seio|mamilo|bunda|raba|tira a roupa|tira tudo"),
    (2, r"calcinha|suti[aã]|lingerie|langerie|renda|fio dental|de toalha"),
    (1, r"gostosa|sensual|provoca|sexy|safad|decote|biqu[ií]ni"),
)
_CLOTHED = re.compile(r"\b(vestida|de roupa|com roupa|look|lookinho|roupa do dia)\b")
_POSE_CHANGE = re.compile(r"\b(deita|deitada|vira|virada|de quatro|de costas|senta|sentada|levanta|de p[eé]|"
                          r"em p[eé]|ajoelha|outra posi[cç][aã]o|muda (a|de) posi|no chuveiro|no espelho|na cama|"
                          r"no sof[aá]|na poltrona|na bancada)\b")
_CLIMAX = re.compile(r"\b(goza pra mim|goza comigo|gozei|gozando|vou gozar|gozar junto|goza)\b")
_BEAT_ASK = (("dildo", r"dildo|consolo|brinquedo|vibrador"), ("lick", r"lamb|chupa (o|os) dedo"),
             ("spread", r"abre|abrindo"),
             ("fingers", r"enfia|dedo dentro|dedos dentro|dedinho"), ("touch", r"se toca|te toca|tocando|siririca"))


@dataclass
class DirectedShot:
    prompt: str
    is_nsfw: bool
    focus_angle: str
    place_key: str
    room: str
    pose_id: str
    level: int
    beat: Optional[str]
    outfit: Optional[str]
    seed: int
    facts: str
    declined: str = ""            # "fora de casa": pediu mais do que dá pra mandar da rua
    session: dict = field(default_factory=dict)


def asked_level(text: str) -> Optional[int]:
    low = (text or "").lower()
    for level, pattern in _ASK:
        if re.search(pattern, low):
            return level
    if _CLOTHED.search(low):
        return 0
    return None


def expression(feeling, turn) -> str:
    """A cara do momento: tesão primeiro, depois o que ela sente, depois o corpo."""
    state = getattr(turn, "state", "off")
    if state == "climax":
        return "her eyes half closed and her mouth open in pleasure, her cheeks flushed"
    if state == "active":
        from intimacy import HOT_AT
        if getattr(turn, "arousal", 0) >= HOT_AT:
            return "heavy-lidded lustful eyes and parted lips, biting her lower lip, her cheeks flushed"
        return "a sultry half-lidded look and a slow teasing smirk"
    if state == "afterglow":
        return "a dreamy satisfied look, flushed cheeks and a lazy soft smile"
    if state == "warming":
        return "a playful teasing smirk"
    if feeling is None:
        return "a soft natural expression"
    strong = [e for e in (feeling.episodes or []) if e.intensity >= 0.35]
    if strong:
        ep = max(strong, key=lambda e: e.intensity)
        by_kind = {"saudade": "a soft wistful look and a small longing smile",
                   "empolgacao": "a bright excited smile", "carinho": "a warm loving smile",
                   "ternura": "a warm loving smile", "vergonha": "a shy embarrassed look, her cheeks pink"}
        by_family = {"tristeza": "a soft sad look with a faint pout", "raiva": "an annoyed look with a slight frown",
                     "medo": "a worried look, her lips pressed together", "tedio": "a bored, half-lidded look",
                     "alegria": "a genuine happy smile", "afeto": "a warm loving smile",
                     "vergonha": "a shy embarrassed look, her cheeks pink"}
        if ep.kind in by_kind or ep.family in by_family:
            return by_kind.get(ep.kind) or by_family[ep.family]
    if feeling.discomfort >= 0.5:
        return "a tired, slightly pale look"
    if feeling.energy < 0.35:
        return "sleepy heavy eyes and a soft tired smile"
    if getattr(feeling, "libido", 0) >= 0.72:
        return "a subtle mischievous look"
    if feeling.valence >= 0.62:
        return "a relaxed natural smile"
    if feeling.valence < 0.45:
        return "a calm, neutral look"
    return "a soft natural expression"


def _band(turn) -> str:
    state = getattr(turn, "state", "off")
    if state == "active":
        return getattr(turn, "band", "desejo")
    return state if state in CAP else "off"


def decide_level(asked: Optional[int], turn, session: Optional[dict], *, her_initiative: bool,
                 rng: random.Random) -> int:
    band = _band(turn)
    cap = CAP.get(band, 1)
    current = (session or {}).get("level")
    if asked is not None:
        level = asked if asked <= cap else min(4, cap + 1)   # ela topa ir um degrau além do clima
        if current is not None and level > current + 1 and band != "climax" and rng.random() < PROVOKE_BELOW_CHANCE:
            level = current + 1                              # provoca antes de entregar tudo
        return level
    if her_initiative or band in ("desejo", "explicito", "climax"):
        level = cap if rng.random() >= PROVOKE_BELOW_CHANCE else max(0, cap - 1)
    else:
        level = min(cap, current if current is not None else 0)
    if current is not None and band not in ("afterglow", "cut", "closing"):
        level = max(level, min(current, cap))                # no meio da sessão não volta a se vestir
    return level


def load_session(db, now: datetime) -> Optional[dict]:
    try:
        raw = db.get_estado_relacional(SESSION_KEY)
        data = json.loads(raw) if raw else None
    except Exception:
        return None
    if not data:
        return None
    try:
        if now - datetime.fromisoformat(data["at"]) > timedelta(minutes=SESSION_TTL_MIN):
            return None
    except Exception:
        return None
    return data


def save_session(db, session: dict) -> None:
    db.set_estado_relacional(SESSION_KEY, json.dumps(session, ensure_ascii=False))


def _default_room(level: int, now: datetime, rng: random.Random) -> str:
    if level >= 2:
        return "closet" if rng.random() < 0.3 else "quarto"
    if now.hour >= 22 or now.hour < 7:
        return "quarto"
    if now.hour < 10:
        return rng.choice(("cozinha", "quarto"))
    return rng.choice(("sala", "sala", "varanda", "quarto"))


def _outfit(pose: Pose, level: int, now: datetime, at_home: bool, rng: random.Random) -> Optional[str]:
    if pose.outfit:
        return pose.outfit
    if level >= 3:
        return None                                          # nua: blocos do corpo canônico
    if level == 2:
        return rng.choice(WARDROBE["lingerie"])
    if level == 1 and at_home:
        return rng.choice(WARDROBE["provoca"])
    if not at_home:
        return rng.choice(WARDROBE["fora"])
    return rng.choice(WARDROBE["casa_noite" if now.hour >= 20 or now.hour < 7 else "casa_dia"])


def _pick_beat(pose: Pose, request: str, turn, session: Optional[dict]) -> Optional[str]:
    if not pose.beats:
        return None
    tags = [t for t, _ in pose.beats]
    low = (request or "").lower()
    if getattr(turn, "state", "") == "climax" or _CLIMAX.search(low):
        return "climax"
    for tag, pattern in _BEAT_ASK:
        if re.search(pattern, low) and tag in tags:
            return tag
    prev = (session or {}).get("beat")
    if prev in tags and session and session.get("pose") == pose.id:
        return tags[min(tags.index(prev) + 1, len(tags) - 2)]  # avança um momento; o gozo fica reservado
    from intimacy import HOT_AT
    return "touch" if getattr(turn, "arousal", 0) >= HOT_AT else "tease"


def direct(db, now: datetime, *, request: str = "", her_line: str = "", camera_ctx=None, turn=None,
           feeling=None, her_initiative: bool = False, chooser: Optional[Callable] = None,
           rng: Optional[random.Random] = None) -> DirectedShot:
    """Decide a foto inteira e devolve o prompt pronto pro Krea 2."""
    from visual_profile import krea2_zoom_prompt
    rng = rng or random.Random()
    session = load_session(db, now)
    place = getattr(camera_ctx, "place_key", None) if camera_ctx else None
    assertable = bool(getattr(camera_ctx, "presence_assertable", False)) if camera_ctx else False
    at_home = place == HOME or not assertable                # sem certeza de onde está: trata como casa
    if session and session.get("place") != (place or HOME):
        session = None
    asked = asked_level(request)
    level = decide_level(asked, turn, session, her_initiative=her_initiative, rng=rng)
    declined = ""
    if not at_home and level > 1:
        declined, level = "fora de casa", 1

    # A posição dita na conversa manda: pedido dele primeiro, depois a fala dela.
    worded = _worded_pose(request, level, at_home) or _worded_pose(her_line, level, at_home)
    food = _food(f"{request} {her_line}") if level <= 1 else None
    if food:
        worded = BY_ID["mostrando_comida"]
    if getattr(turn, "state", "") == "climax" and not worded and level >= 3:
        current = BY_ID.get((session or {}).get("pose", ""))
        if not (current and current.beats):          # sem cena com "momentos" rolando: foto do depois
            worded = BY_ID["pos_gozo"]
    change = bool(_POSE_CHANGE.search((request or "").lower())) or bool(
        worded and session and worded.id != session.get("pose"))
    room_asked = apartamento.room_for(request) if at_home else None
    keep = (session is not None and not change and (room_asked in (None, session.get("room")))
            and session.get("pose") in BY_ID)
    if keep:
        pose = BY_ID[session["pose"]]
        lo, hi = pose.levels
        if not (lo <= level <= hi):
            keep = False
    if keep:
        room = session["room"]
        seed = session["seed"]
        outfit = session.get("outfit") if session.get("level") == level else None
        if outfit is None:
            outfit = _outfit(pose, level, now, at_home, rng)
    else:
        if at_home:
            activity = (getattr(camera_ctx, "activity", None) or "") if camera_ctx else ""
            sub = (getattr(camera_ctx, "sublocation", None) or "") if camera_ctx else ""
            room = room_asked
            if not room and session and not change:
                room = session.get("room")                   # mesma sessão, pose nova no mesmo cômodo
            room = (room or apartamento.room_for(activity) or apartamento.room_for(sub)
                    or _default_room(level, now, rng))
        else:
            room = "fora"
        candidates = [p for p in POSES if room in p.rooms and p.levels[0] <= level <= p.levels[1]]
        if not at_home and not getattr(camera_ctx, "present_people", ()):
            candidates = [p for p in candidates if p.framing != "friend"]
        if not candidates and at_home:                       # o cômodo não tem pose desse nível: vai pro quarto
            room = "quarto"
            candidates = [p for p in POSES if "quarto" in p.rooms and p.levels[0] <= level <= p.levels[1]]
        pose = worded
        if pose and room not in pose.rooms:
            room = pose.rooms[0] if at_home else "fora"
        if pose is None and chooser and len(candidates) > 1:
            try:
                picked = chooser([(p.id, p.pt) for p in candidates], request, her_line)
                pose = BY_ID.get(picked) if picked in {p.id for p in candidates} else None
            except Exception:
                pose = None
        pose = pose or rng.choice(candidates)
        seed = rng.randint(1, 2**31 - 1)
        outfit = _outfit(pose, level, now, at_home, rng)

    beat = _pick_beat(pose, request, turn, session if keep else None) if level >= 4 else None
    action = dict(pose.beats)[beat] if beat else pose.action
    if beat:
        action = f"{pose.action}, {action}"
    action = action.replace("{food}", food or _food(session.get("food", "") if session else "") or "her snack")
    weather = getattr(camera_ctx, "weather", None) if camera_ctx else None
    rain = "chuva" if weather and (weather.get("heavy_rain") or "rain" in json.dumps(weather).lower()) else None
    if room == "fora":
        from camera_world import PLACE_VISUAL
        visual = PLACE_VISUAL.get(place or "", "a street in Botafogo, Rio de Janeiro")
        visual = re.sub(r",?\s*candid (indoor )?smartphone photo", "", visual)
        setting, backdrop = visual, f"{visual.split(',')[0]} in soft focus"
    else:
        setting, backdrop = apartamento.setting(room, now, rain), apartamento.backdrop(room, now, rain)
    nude = level >= 3 and outfit is None
    prompt = krea2_zoom_prompt(action, zoom=pose.zoom, setting=setting, backdrop=backdrop,
                               is_nsfw=nude, focus_angle=pose.angle, framing=pose.framing,
                               outfit=outfit, expression=expression(feeling, turn))
    where = apartamento.ROOMS[room]["pt"] if room in apartamento.ROOMS else "na rua"
    facts = f"lugar: {where}; pose: {pose.pt}; roupa: {outfit or 'pelada'}"
    if beat:
        facts += f"; momento: {beat}"
    if declined:
        facts += "; ela está fora de casa e não dá pra mandar foto mais ousada daqui — provoca prometendo pra depois"
    new_session = {"place": place or HOME, "room": room, "pose": pose.id, "level": level, "outfit": outfit,
                   "beat": beat, "seed": seed, "at": now.isoformat(), "food": f"{request} {her_line}" if food else ""}
    # Calcinha/toalha em foto "normal" o moderador do Civitai barra: vai como adulta (Buzz amarelo).
    adult = level >= 2 or bool(outfit and re.search(r"panties|thong|towel", outfit))
    return DirectedShot(prompt=prompt, is_nsfw=adult, focus_angle=pose.angle, place_key=place or "",
                        room=room, pose_id=pose.id, level=level, beat=beat, outfit=outfit, seed=seed,
                        facts=facts, declined=declined, session=new_session)


def confirm_sent(db, shot: DirectedShot) -> None:
    """Só a foto que foi mesmo pro Telegram vira sessão (gancho da próxima)."""
    save_session(db, shot.session)


# ------------------------------------------------------- iniciativa dela --
def may_self_initiate(db, now: datetime, turn) -> bool:
    """Ela pode mandar foto por conta própria: no clima a cada 12 min; no dia a dia 1 por hora."""
    state = getattr(turn, "state", "off")
    if state in ("cut", "closing"):
        return False
    gap = SELF_PHOTO_GAP_MIN if state in ("active", "climax") else SELF_PHOTO_GAP_CASUAL_MIN
    try:
        last = db.get_estado_relacional(SELF_PHOTO_KEY)
        if last and now - datetime.fromisoformat(last) < timedelta(minutes=gap):
            return False
    except Exception:
        pass
    return True


def mark_self_initiated(db, now: datetime) -> None:
    db.set_estado_relacional(SELF_PHOTO_KEY, now.isoformat())


SELF_PHOTO_TAG = re.compile(r"\s*\[FOTO\]\s*", re.IGNORECASE)
SELF_PHOTO_HINT_CASUAL = ("[FOTO SUA] Se você prometeu mandar foto de alguma coisa e agora dá (ex.: a comida "
                          "chegou), ou quer mostrar algo seu de verdade (a comida, o look, o pós-treino), termine a "
                          "mensagem com [FOTO]. Só quando fizer sentido — nunca por obrigação.")
SELF_PHOTO_HINT = ("- Se VOCÊ quiser provocar ele com uma foto sua agora (não precisa ele pedir), termine a "
                   "mensagem com [FOTO]. Só quando fizer sentido na cena — de vez em quando, não toda hora.")
