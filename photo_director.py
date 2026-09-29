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
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

import apartamento

logger = logging.getLogger(__name__)

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
    face: str = ""                # cara que é o charme da pose (vale no lugar da cara do humor)


DILDO_TEXT = "a realistic pink silicone dildo with a veined shaft"
DILDO_CLEAR_TEXT = "a clear transparent glass-like dildo"
# 27/09 (Patrick): o 3º brinquedo da gaveta, da pose de referência da cadeira.
PLUG_TEXT = "a small silver metal butt plug with a red heart-shaped jewel on its base"


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
    # Aprovada pelo Patrick (24/09, teste "X"): sentando no dildo transparente (o 2º brinquedo da
    # gaveta), só com o Grippy — o Pussy Helper não acrescentou e sumia com as mãos.
    Pose("sentando_dildo", "agachada de frente, sentando no dildo transparente preso na cama (timer)",
         ("quarto",), (4, 4), "three_quarter", "timer", "squatting on the bed facing the camera, her knees wide "
         "apart and her hands resting on her knees",
         beats=(("dildo", f"sinking down onto {DILDO_CLEAR_TEXT} standing upright on its round suction-cup base on "
                          "the white sheets, the dildo pushed deep inside her pussy"),
                ("climax", f"right after she came, still sitting down on {DILDO_CLEAR_TEXT}, her thighs "
                           "trembling"))),
    # Patrick, 24/09 (teste Y/Z): cavalgando deitada pra trás, câmera um pouco de cima. O ângulo
    # "de trás da cabeça" do prompt dele não sai: sem rosto no quadro, o LoRA dela puxa pra frente.
    Pose("cavalgando_reclinada", "deitada pra trás, apoiada na mão, cavalgando o dildo transparente (selfie de cima)",
         ("quarto",), (4, 4), "three_quarter", "selfie", "leaning back on the bed on her left hand, her right arm "
         "stretched up toward the camera taking the selfie from slightly above, her legs spread",
         beats=(("dildo", f"riding {DILDO_CLEAR_TEXT} standing upright on its round suction-cup base on the white "
                          "sheets, the dildo pushed deep inside her pussy"),
                ("climax", f"right after she came, still riding {DILDO_CLEAR_TEXT}, her thighs trembling"))),
    # Patrick, 25/09 (teste BB 0.5): provocando, chupando o dildo rosa olhando pra câmera.
    Pose("boquete_dildo", "deitada de lado, chupando o dildo rosa olhando pra câmera (selfie)", ("quarto",), (3, 4),
         "close", "selfie", "lying on her side on the bed, her right arm stretched toward the camera taking the "
         f"selfie, her left hand holding {DILDO_TEXT} to her mouth, her lips tightly wrapped around its tip, sucking "
         "it slowly while looking straight at the camera with teasing eyes"),
    # Patrick, 25/09 (teste ZE): de bruços meio de lado, chupando o dildo rosa em pé na ventosa (timer).
    Pose("boquete_de_lado", "de bruços na cama, chupando o dildo rosa em pé na ventosa (timer)", ("quarto",), (3, 4),
         "three_quarter", "timer", "side view photo, lying on her side on the bed with her head lowered toward "
         f"the sheets, sucking deep on {DILDO_TEXT} that stands upright on its round suction-cup base on the white "
         "sheets, her lips tightly wrapped around it far down the shaft, her eyes watering, her hands resting on "
         "the sheets", angle="side"),
    # Aprovada no teste do Creamy (Patrick, 24/09, "R_costas"): se dedilhando por trás, ajoelhada.
    Pose("cama_costas_dedando", "ajoelhada de costas, peito baixo, se dedilhando por trás (timer)", ("quarto",),
         (4, 4), "three_quarter", "timer", "kneeling on the bed seen from behind, her chest low and her ass up "
         "toward the camera, looking back over her shoulder, her left forearm resting on the pillow",
         angle="behind", beats=_beats("from behind, her ass up toward the camera", "right")),
    # 27/09 — poses de referência do Patrick (references/poses): só a pose; rosto, cabelo e luz são dela.
    Pose("chao_abracando_joelhos", "sentada no chão encostada na cama, abraçando os joelhos (timer)", ("quarto",),
         (0, 3), "full", "timer", "sitting on the light wood floor with her back against the side of the bed, her "
         "knees pulled up together and her feet apart, hugging her legs with both arms, her body leaning slightly "
         "toward the camera, glancing away and biting her lower lip"),
    Pose("cama_brucos_selfie", "de bruços na cama, queixo na mão e pés pro alto (selfie)", ("quarto",), (0, 3),
         "close", "selfie", "lying on her stomach on the bed, her chin resting on her left hand, her feet raised "
         "and crossed in the air behind her, her right arm stretched toward the camera taking the selfie from "
         "slightly above"),
    Pose("inclinada_pra_camera", "de pé, inclinada pra frente em direção à câmera (timer)", ("quarto", "closet"),
         (1, 3), "three_quarter", "timer", "standing and leaning forward toward the camera, her arms straight down "
         "in front of her with her hands together between her knees, her body leaning in, her head turned to one "
         "side and her eyes looking away from the camera toward the side",
         # 28/09 (testes com o Patrick): o "meio sorriso" do humor fechava a boca; "mouth slightly open / teeth
         # showing" abria a boca e a mordida sumia. A que mordeu de verdade (sentando no dildo) dizia só "biting her
         # lower lip" com os lábios entreabertos em volta.
         face="heavy-lidded lustful eyes and parted lips, biting her lower lip, her cheeks flushed"),
    Pose("coracao_maos", "ajoelhada na beira da cama fazendo coração com as mãos (timer)", ("quarto",), (0, 3),
         "three_quarter", "timer", "kneeling at the edge of the bed leaning slightly toward the camera, her hands "
         "together in front of her chest making a heart shape, her thumbs and index fingers touching, looking at "
         "the camera through the heart"),
    Pose("beira_cama_de_baixo", "sentada na beira da cama, selfie de baixo, entre as coxas", ("quarto",), (1, 4),
         "three_quarter", "selfie", "sitting on the edge of the bed with her legs spread apart, her right arm "
         "stretched down between her thighs taking the selfie from an extreme low angle, looking down at the "
         "camera over her body, a playful smirk with one eyebrow raised"),
    Pose("chao_pernas_pro_alto", "deitada no chão, pernas pro alto e abertas (timer)", ("quarto",), (4, 4),
         "three_quarter", "timer", "lying on her back on the floor beside the bed, her legs raised high and spread "
         "wide toward the camera, her hands holding the backs of her thighs, looking at the camera between her "
         "legs, sunlight through the sheer curtains casting soft stripes of light across her body"),
    Pose("cama_de_lado_bunda", "deitada de lado, bunda em primeiro plano, olhando pra trás (timer)", ("quarto",),
         (2, 3), "three_quarter", "timer", "lying on her side on the bed seen from behind at a low angle close to "
         "the mattress, her hip and ass in the foreground, her top arm resting along her body, looking back at "
         "the camera over her shoulder", angle="behind"),
    Pose("cama_empinada_celular", "de bruços com o quadril empinado, mexendo no celular (timer)", ("quarto",),
         (2, 3), "three_quarter", "timer", "side view photo, lying face-down on the bed with her hips raised high "
         "and her ass up, her chest and cheek low on the white sheets, holding a light pink smartphone in both "
         "hands in front of her face and looking at its screen", angle="side"),
    Pose("em_pe_quadril", "de pé perto da cama, quadril pro lado (timer)", ("quarto",), (1, 3), "full", "timer",
         "standing beside the bed with her hip pushed out to one side and her weight on one leg, one arm relaxed "
         "along her body, looking straight at the camera"),
    Pose("cama_perna_pra_camera", "deitada de moletom largo, uma perna esticada pra câmera (timer)", ("quarto",),
         (1, 2), "three_quarter", "timer", "lying on her back on the bed, one leg raised high and stretched "
         "straight toward the camera with the sole of her foot close to the lens, her other leg bent, one hand "
         "near her mouth", outfit="an oversized light blue hoodie and black cotton panties"),
    Pose("cabeceira_perna_alto", "encostada na cabeceira, uma perna pro alto (timer)", ("quarto",), (4, 4),
         "three_quarter", "timer", "sitting back against the rattan headboard facing the camera, one leg raised "
         "high and bent at the knee, her other leg spread open on the sheets",
         beats=_beats("one leg raised high, her legs spread", "right", _SQUEEZE_LEFT)),
    # ---------------------------------------------------------------- closet --
    Pose("espelho_corpo", "de pé na frente do espelho grande do closet", ("closet",), (0, 3), "full", "mirror",
         "standing barefoot in front of the tall mirror, her weight on one leg, her free hand resting on her hip"),
    # 26/09 (Patrick): mostrando look ela usa o tripé do closet, e a pose muda junto com o look.
    Pose("closet_look_frente", "de pé no meio do closet mostrando o look (tripé)", ("closet",), (0, 1), "full",
         "timer", "standing in the middle of the closet facing the camera, one hand on her hip, her weight on one "
         "leg, showing off her outfit"),
    Pose("closet_look_giro", "girando pra mostrar o look (tripé)", ("closet",), (0, 1), "full", "timer",
         "caught mid-turn in the middle of the closet, her hair and her outfit swinging with the movement, "
         "smiling at the camera over her shoulder"),
    Pose("closet_look_andando", "andando em direção ao tripé, desfilando o look", ("closet",), (0, 1), "full",
         "timer", "walking toward the camera mid-step like on a runway, one hand tucking her hair behind her ear"),
    Pose("closet_look_poltrona", "sentada na poltrona de pernas cruzadas, de look (tripé)", ("closet",), (0, 1),
         "full", "timer", "sitting in the cream armchair with her legs crossed, leaning back, both hands resting "
         "on the armrests"),
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
    # 27/09 (Patrick): o plug entrou no mundo com esta pose. De costas, olhando pra trás (o rosto segura o LoRA).
    # Teste 27/09: roupa SENDO tirada ("lifting", "pulled up/down") + nudez = recusa do Krea 2 (ruído de letras).
    # A roupa das poses de roupa puxada é escrita parada, no lugar onde ficou.
    Pose("poltrona_curvada_plug", "curvada na poltrona com a saia levantada, de costas (timer)", ("closet",), (4, 4),
         "three_quarter", "timer", "bent forward over the cream armchair seen from behind, her right hand resting "
         "on her lower back, looking back at the camera over her shoulder", angle="behind",
         outfit="a short brown skirt bunched up around her waist and a black cotton t-shirt",
         beats=(("plug", f"{PLUG_TEXT} inserted in her ass, the heart-shaped jewel resting flush against her skin"),
                ("climax", f"right after she came, her legs trembling, {PLUG_TEXT} still inserted in her ass"))),
    Pose("torso_alcas", "blusinha levantada, puxando as alças da calcinha pra cima (sem o rosto)", ("closet",),
         (3, 3), "torso", "timer", "standing against the wall facing the camera, both hands at her hips holding the "
         "thin side straps of her thong high on her hips",
         outfit="a light pink cropped t-shirt bunched up high on her chest with her breasts out, and a light pink "
                "ribbed thong"),
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
    # 27/09 (referência): de costas no espelho com o rosto de perfil — o "ângulo de trás" que o timer não dá (1d).
    Pose("espelho_perfil_costas", "de costas pro espelho, olhando por cima do ombro", ("banheiro", "closet"), (1, 3),
         "three_quarter", "mirror", "standing in side profile to the mirror with her body turned so her back and "
         "her ass face the mirror, looking over her shoulder at the phone screen, her free hand resting on her "
         "lower back", angle="behind"),
    # ------------------------------------------------------------------ sala --
    Pose("sofa_selfie", "encolhida no sofá, selfie", ("sala",), (0, 2), "close", "selfie",
         "curled up on the sofa with her head resting on a cushion, her right arm stretched toward the camera taking the selfie"),
    Pose("sofa_timer", "sentada no sofá com as pernas dobradas (timer)", ("sala",), (0, 3), "room", "timer",
         "sitting on the sofa with her legs tucked under her, one arm along the backrest, feet on the jute rug"),
    Pose("sala_janela", "de perfil no janelão, olhando pra câmera (timer)", ("sala",), (1, 3), "full", "timer",
         "standing by the big window in side profile, one hand resting on the window frame, looking back at the "
         "camera", angle="side"),
    Pose("sala_vinho_selfie", "selfie com uma taça de vinho no janelão", ("sala",), (0, 1), "three_quarter",
         "selfie", "standing by the big window holding a glass of red wine in her left hand, her right arm "
         "stretched toward the camera taking the selfie from slightly above"),
    # --------------------------------------------------------------- cozinha --
    Pose("cozinha_cafe", "encostada na bancada com o café", ("cozinha",), (0, 1), "three_quarter", "selfie",
         "leaning her hip against the countertop, holding a cup of coffee in her left hand, her right arm "
         "stretched toward the camera taking the selfie"),
    Pose("cozinha_bancada", "sentada na bancada (timer)", ("cozinha",), (1, 3), "full", "timer",
         "sitting on the edge of the white countertop, her hands resting on the counter beside her hips, her feet "
         "dangling"),
    Pose("cozinha_blusa_levantada", "na cozinha, blusa levantada e legging abaixada (sem o rosto)", ("cozinha",),
         (3, 3), "torso", "selfie", "standing by the countertop, her left hand resting on the waistband of her "
         "leggings at her thighs, her right arm stretched toward the camera taking the selfie",
         outfit="a black long-sleeved top bunched up high on her chest with her breasts out, and black leggings "
                "sitting low around her upper thighs"),
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
    Pose("academia_espelho_perfil", "de perfil no espelho da academia, mão no quadril", ("academia",), (0, 1),
         "full", "mirror", "standing in side profile to the mirrored wall, looking at the phone screen, her free "
         "hand resting on her hip, one knee slightly bent", angle="side",
         outfit="black high-waisted booty shorts and a soft unpadded maroon sports top, black sneakers"),
    Pose("piscina_espreguicadeira", "deitada na espreguiçadeira da piscina (timer)", ("piscina",), (0, 1), "full",
         "timer", "lying on a white lounger with one knee raised, her hands behind her head",
         outfit="a small soft triangle bikini in light blue"),
    # 27/09 (referência): na piscina do prédio é de biquíni — lugar de todo mundo.
    Pose("piscina_empinada_selfie", "de bruços na espreguiçadeira, empinada, língua pra fora (selfie)", ("piscina",),
         (1, 1), "close", "selfie", "lying on her stomach on a white lounger with her hips raised and her back "
         "arched, her right arm stretched toward the camera taking the selfie at a low angle, sticking her tongue "
         "out playfully", outfit="a small soft triangle bikini in light blue"),
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
    # ----------------------------------------------- do ponto de vista dela --
    # 26/09 (Patrick): comida, o Milo, a vista — foto tirada por ela, do ponto de vista dela: ela não aparece
    # (no máximo a mão na borda). Sai sem o LoRA dela (framing "pov").
    Pose("pov_comida", "a comida, do ponto de vista dela", ("cozinha", "sala", "quarto", "varanda"), (0, 1),
         "close", "pov", "{food} on the table right in front of her, seen from above at a slight angle, her hand "
         "holding a spoon at the edge of the frame"),
    Pose("pov_comida_rua", "a comida na mesa do lugar, do ponto de vista dela", ("fora",), (0, 1), "close", "pov",
         "{food} on the table right in front of her, seen from above at a slight angle, her hand holding a spoon "
         "at the edge of the frame"),
    Pose("pov_milo", "o Milo, do ponto de vista dela", ("sala", "quarto", "varanda", "cozinha"), (0, 1), "close",
         "pov", "{milo}, looking up at the camera"),
    Pose("pov_milo_rua", "o Milo no passeio, do ponto de vista dela", ("fora",), (0, 1), "close", "pov",
         "{milo} on the sidewalk, looking up at the camera, his leash held in her hand at the edge of the frame"),
    Pose("pov_vista", "a vista da varanda, do ponto de vista dela", ("varanda",), (0, 1), "room", "pov",
         "the view of Botafogo bay and Sugarloaf Mountain from her balcony, her hand resting on the railing at the "
         "edge of the frame"),
    # 26/09 (Patrick): unha pronta → a foto da mão, do ponto de vista dela (unhas.py)
    Pose("pov_unhas", "a mão com as unhas prontas, do ponto de vista dela", ("quarto", "sala", "varanda", "closet"),
         (0, 1), "close", "pov", "her own hand held up close to the camera, fingers gently spread, showing off her "
         "freshly done nails"),
    Pose("pov_unhas_rua", "a mão com as unhas prontas, na rua, do ponto de vista dela", ("fora",), (0, 1), "close",
         "pov", "her own hand held up close to the camera, fingers gently spread, showing off her freshly done nails"),
    # 26/09 (Patrick): às vezes a unha vem numa selfie, com a mão em destaque perto da boca
    Pose("unhas_selfie", "selfie com a mão das unhas prontas perto da boca", ("quarto", "sala", "varanda", "closet"),
         (0, 1), "close", "selfie", "her free hand raised to her lips with her fingertips lightly touching them, "
         "showing off her freshly done nails in the foreground"),
    Pose("unhas_selfie_rua", "selfie na rua com a mão das unhas prontas perto da boca", ("fora",), (0, 1), "close",
         "selfie", "her free hand raised to her lips with her fingertips lightly touching them, showing off her "
         "freshly done nails in the foreground"),
    # 26/09 (Patrick): cabelo feito — no salão alguém de lá tira; em casa, espelho ou tripé (cabelo.py)
    Pose("salao_cabelo", "na cadeira do salão com o cabelo pronto, alguém do salão tirando", ("fora",), (0, 1),
         "three_quarter", "friend", "sitting in the salon chair right after her hair appointment, facing the camera, "
         "her freshly done hair falling over her shoulders, smiling",
         outfit="a black hairdresser cape fastened at her neck and draped over her shoulders and body, a white "
                "ribbed tank top underneath"),
    Pose("cabelo_espelho", "no espelho mostrando o cabelo pronto", ("closet", "quarto"), (0, 1), "three_quarter",
         "mirror", "standing in front of the mirror, turning her head slightly, her free hand running through her freshly "
         "done hair to show it off"),
    Pose("cabelo_tripe", "no tripé mostrando o cabelo pronto", ("quarto", "sala", "closet"), (0, 1), "three_quarter",
         "timer", "facing the camera, running one hand through her freshly done hair to show it off"),
    # ------------------------------------------------------------------ rua --
    Pose("fora_selfie", "selfie na rua", ("fora",), (0, 1), "close", "selfie",
         "her right arm stretched toward the camera taking the selfie at arm's length"),
    Pose("fora_amiga_corpo", "de corpo inteiro, uma amiga tirando", ("fora",), (0, 1), "full", "friend",
         "standing relaxed with her weight on one leg, one hand holding the strap of her bag"),
    Pose("fora_amiga_andando", "andando em direção à câmera, uma amiga tirando", ("fora",), (0, 1),
         "three_quarter", "friend", "walking toward the camera mid-step, one hand tucking her hair behind her ear"),
    # 27/09 (Patrick, Instagram): fora de casa ela quase sempre está com gente — não precisa ser sempre selfie
    Pose("fora_amiga_rindo", "rindo olhando pro lado, uma amiga tirando sem ela posar", ("fora",), (0, 1),
         "three_quarter", "friend", "caught mid-laugh looking off to the side at someone out of frame, candid and "
         "unposed, one hand near her collarbone"),
    Pose("fora_amiga_sentada", "sentada à mesa, uma amiga tirando do outro lado", ("fora",), (0, 1),
         # 27/09 (foto 9, duas vezes selfie): olho na lente + uma mão livre = selfie; as duas mãos ficam ocupadas
         "three_quarter", "friend", "seen from across the table, sitting at a small table with the table edge and "
         "the back of her chair in the frame, her chin resting on her left hand and her right hand wrapped around "
         "her drink on the table, smiling at her friend who is taking the photo"),
    Pose("fora_amiga_encostada", "encostada na parede, uma amiga tirando", ("fora",), (0, 1), "full", "friend",
         "leaning back against a wall with one foot resting flat against it, arms relaxed, looking at the camera"),
    Pose("fora_amiga_costas", "indo embora e olhando por cima do ombro, uma amiga tirando", ("fora",), (0, 1),
         "three_quarter", "friend", "walking away from the camera and glancing back over her shoulder with a smile",
         angle="side"),
    # 28/09: foto de grupo — a amiga do rolê entra do lado direito e o rosto dela vem da foto-RG
    # (civitai_images.swap_friend_face). Só quando quem está com ela tem RG (FRIEND_RG). Cabeças um pouco
    # separadas (Patrick, 28/09): a costura da troca sempre tem um vão de fundo pra passar.
    Pose("fora_selfie_amiga", "selfie com a amiga, lado a lado", ("fora",), (0, 1), "close", "selfie",
         "taking a selfie together with her friend, her right arm stretched toward the camera, the two of them "
         "standing side by side, shoulder to shoulder, with a little space between their heads"),
    Pose("fora_selfie_amiga_abraco", "selfie com a amiga, abraçadas", ("fora",), (0, 1), "close", "selfie",
         "taking a selfie together with her friend, her right arm stretched toward the camera, her friend's arm "
         "around her shoulders, both smiling at the camera, their heads a little apart"),
    Pose("fora_amigas_alguem_tirando", "com a amiga, alguém tirando a foto das duas", ("fora",), (0, 1),
         "full", "friend", "standing side by side with her friend, arms around each other's waists, both "
         "smiling at the person taking the photo a few steps away, nobody in the photo holding a phone, with a "
         "little space between their heads"),
)
GROUP_POSES = ("fora_selfie_amiga", "fora_selfie_amiga_abraco", "fora_amigas_alguem_tirando")
GROUP_SIDE = "right"   # a amiga fica do lado direito; a troca de rosto cola só esse lado
_GROUP_ASK = re.compile(r"\b(?:com (?:a|o) (?:bia|carol|j[uú]lia|theo)|voc[eê]s duas|voc[eê]s dois|n[oó]s duas|"
                        r"as duas|os dois|juntas|juntos|com (?:a|sua|tua) amiga|foto de grupo)\b", re.IGNORECASE)
BY_ID = {p.id: p for p in POSES}

# A posição que eles escreveram manda na pose (24/09: ela disse "de quatro na cama" e o sorteio
# mandou de costas no espelho). Em ordem de preferência; vale a primeira que aceita o nível.
POSE_WORDS = (
    (r"\bplug\b", ("poltrona_curvada_plug",)),
    (r"(de costas|por tr[aá]s).{0,25}espelho|espelho.{0,25}(de costas|por tr[aá]s)", ("espelho_perfil_costas",)),
    (r"cora[cç][aã]o com as m[aã]os|cora[cç][aã]ozinho com a m[aã]o", ("coracao_maos",)),
    (r"abra[cç]ando (os|as) (joelhos|pernas)", ("chao_abracando_joelhos",)),
    (r"ta[cç]a|vinho", ("sala_vinho_selfie",)),
    (r"de quatro|empinad", ("cama_de_quatro", "cama_costas_dedando", "cama_empinada_celular",
                            "piscina_empinada_selfie")),
    (r"de costas|por tr[aá]s", ("cama_costas_dedando", "cama_de_quatro", "cama_de_lado_bunda")),
    (r"(boquete|chupa\w*) de lado|dildo (preso|em p[eé]) na cama", ("boquete_de_lado",)),
    (r"boquete|mamada|chupa(ndo)? (o|esse|teu|seu) (dildo|consolo|brinquedo)", ("boquete_dildo", "boquete_de_lado")),
    (r"cavalga|quica|rebola|deitada pra tr[aá]s", ("cavalgando_reclinada", "sentando_dildo")),
    (r"senta|sentando", ("sentando_dildo", "cavalgando_reclinada")),
    (r"pernas abertas|abr\w* as pernas|arreganhad|deitada de costas", ("cama_tripe_duas_maos", "cama_pernas_abertas")),
    (r"chuveiro|no box|no banho", ("chuveiro_tocando", "chuveiro", "banheiro_toalha", "banheiro_espelho")),
    (r"poltrona", ("poltrona_aberta", "poltrona_pernas")),
    (r"apertando (os|meus) (seios|peitos)", ("cama_apertando",)),
    (r"de bru[cç]os", ("cama_de_brucos", "cama_brucos_selfie")),
    (r"pernas? pro alto|pernas? pra cima", ("chao_pernas_pro_alto", "cabeceira_perna_alto", "cama_perna_pra_camera")),
    (r"ajoelhad|de joelhos", ("cama_ajoelhada",)),
    (r"espelho", ("espelho_corpo", "banheiro_espelho", "academia_espelho")),
    (r"sof[aá]", ("sofa_timer", "sofa_selfie")),
    (r"bancada", ("cozinha_bancada", "cozinha_cafe")),
    (r"\bmilo\b|cachorr(?:o|inho)\b|doguinho", ("pov_milo", "pov_milo_rua")),
    (r"(?:a|da|essa|que) vista\b|p[oô]r do sol|paisagem|p[aã]o de a[cç][uú]car", ("pov_vista",)),
    (r"varanda", ("varanda_cadeira", "varanda_parapeito")),
)
# Canon visual do Milo (Shih Tzu, seed_world_bible). 26/09: nas fotos ele precisa ser sempre o mesmo cachorro.
MILO_VISUAL = ("Milo, her small Shih Tzu dog with a soft white and golden-brown coat in a short puppy cut, a "
               "little topknot, a black nose and big round dark eyes, wearing a light blue collar")
LOOK_POSES = ("closet_look_frente", "closet_look_giro", "closet_look_andando", "closet_look_poltrona")
FOODS = (
    (r"a[cç]a[ií]", "a bowl of açaí topped with granola"),
    (r"pizza", "a slice of pizza"),
    (r"hamb[uú]rg|burger", "a juicy burger"),
    (r"sushi|temaki", "a tray of sushi"),
    (r"sorvete", "an ice cream cone"),
    (r"brigadeiro", "a small plate of brigadeiros"),
    (r"caf[eé]\b|cappuccino", "a cup of coffee"),
    (r"salada", "a bowl of salad"),
    (r"bolo de pote", "a small clear jar of layered cake with Nutella and powdered milk, a spoon in it"),
    (r"bolo", "a slice of cake"),
    (r"canja|sopa|caldo", "a bowl of hot chicken soup"),
    (r"picol[eé]", "a fruit popsicle"),
)


# "foto sua com o Milo", "você e a vista": é foto dela, não do ponto de vista dela
_HER_IN_IT_RE = re.compile(r"(?<!pra )(?<!para )\b(?:sua|voc[eê]|vc|tu|contigo)\b", re.IGNORECASE)
_PHOTO_OF_RE = re.compile(r"\bfot(?:o|inho|inha)s?\s+d[oa]\b", re.IGNORECASE)


def _worded_pose(text: str, level: int, at_home: bool, *, hers: bool = False) -> Optional[Pose]:
    """hers: a fala é dela — foto sem ela só se ela disse "foto do Milo/da vista"."""
    low = (text or "").lower()
    pov_ok = not _HER_IN_IT_RE.search(low) and (not hers or _PHOTO_OF_RE.search(low))
    for pattern, ids in POSE_WORDS:
        if re.search(pattern, low):
            for pid in ids:
                pose = BY_ID[pid]
                if pose.framing == "pov" and not pov_ok:
                    continue
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
    # 25/09: "se eu te mandar duas opções, vc dá o veredito?" — roupa de sair à noite (bar, rolê).
    "sair": ("a black satin slip midi dress with thin straps",
             "a white off-shoulder linen top and high-waisted light blue jeans",
             "a light blue ribbed crop top and a flowy white midi skirt",
             "a little black cotton dress and white sneakers",
             "a denim mini skirt and a soft black ribbed tank top",
             "a floral wrap dress in soft terracotta tones"),
    "lingerie": ("a soft unpadded white lace bralette and matching panties",
                 "a light pink unpadded lace bralette and thong",
                 "a black sheer unpadded lace bralette and matching thong"),
}

# Pedido dele → degrau. O mais alto que aparecer vale.
_ASK = (
    (4, r"buceta|xota|xoxota|pussy|se toca|te toca|tocando|siririca|masturb|dedo|dedinho|enfia|abre (a|as|pra)|"
        r"dildo|consolo|brinquedo|\bplug\b|"
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
_BEAT_ASK = (("plug", r"\bplug\b"), ("dildo", r"dildo|consolo|brinquedo|vibrador"), ("lick", r"lamb|chupa (o|os) dedo"),
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
    lora_weights: dict = field(default_factory=dict)   # pesos decididos aqui (Creamy pela excitação)
    special: bool = False                              # gozo especial (esguicho) → depois vai a selfie molinha
    pov: bool = False                                  # 26/09: do ponto de vista dela, sem ela (sem o LoRA dela)
    friend: str = ""                                   # 28/09: amiga na foto (chave do FRIEND_RG) → troca de rosto
    friend_side: str = GROUP_SIDE


def _group_friend(camera_ctx, request: str = "") -> str:
    """A amiga que pode entrar na foto: quem está com ela e tem foto-RG (a citada no pedido primeiro)."""
    from civitai_images import FRIEND_RG
    people = [p for p in (getattr(camera_ctx, "present_people", ()) or ()) if p in FRIEND_RG]
    low = (request or "").lower()
    for key in people:
        if re.search(rf"\b{key.split('_')[0]}\b", low):
            return key
    return people[0] if people else ""


def _friend_sentence(friend: str, outfit: str) -> str:
    """A amiga numa frase só dela, depois da roupa da Marina (senão a expressão e o "She" grudam nela)."""
    from visual_profile import FRIENDS_VISUAL
    noun = FRIENDS_VISUAL[friend].get("noun", "woman")
    return (f"On the {GROUP_SIDE} side of the photo, beside her, is her friend, "
            f"{FRIENDS_VISUAL[friend]['en']}, wearing {outfit}; the two {'women' if noun == 'woman' else 'friends'} "
            f"look clearly different from each other.")


_GARMENTS = re.compile(r"tank top|crop top|tee\b|t-shirt|dress|jeans|skirt|shorts|top\b")


def _friend_outfit(marina_outfit: Optional[str], rng: random.Random) -> str:
    """Roupa de sair da amiga, sem repetir a peça da Marina (duas de regata preta parecem uniforme)."""
    hers = set(_GARMENTS.findall(marina_outfit or ""))
    options = [o for o in WARDROBE["sair"] if o != marina_outfit and not hers & set(_GARMENTS.findall(o))]
    return rng.choice(options or [o for o in WARDROBE["sair"] if o != marina_outfit])


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


def _luz_fora(hour: int) -> str:
    """Luz da cena fora de casa pela hora. 28/09: o Quartinho às 21h saiu com sol na janela — o lugar sozinho
    ("evening indoor ambient light") não segurou; diz o que a câmera vê lá fora, não o que falta."""
    if hour >= 18 or hour < 5:
        return ", at night: warm artificial lights, and any window or doorway shows the dark night street with city lights"
    return ""


def _default_room(level: int, now: datetime, rng: random.Random) -> str:
    if level >= 2:
        return "closet" if rng.random() < 0.3 else "quarto"
    if now.hour >= 22 or now.hour < 7:
        return "quarto"
    if now.hour < 10:
        return rng.choice(("cozinha", "quarto"))
    return rng.choice(("sala", "sala", "varanda", "quarto"))


_TROCAVEL = re.compile(r"sports top|bikini")      # roupa fixa da pose que é a de agora dela (treino, praia)
_OCASIAO_TROCAVEL = {"sports top": "treino", "bikini": "praia"}


def _roupa_de_agora(db, pose: Pose, level: int, at: datetime, at_home: bool, intimo: bool) -> Optional[str]:
    """28/09 (Patrick): a foto usa a roupa que ela está vestindo de verdade (roupa.py). No clima, em casa, é a peça
    que ela pôs pra ele (e fica a mesma em todas as fotos da sessão)."""
    if db is None or level >= 3:
        return None
    try:
        from roupa import Roupa
        r = Roupa(db)
        if pose.outfit:
            m = _TROCAVEL.search(pose.outfit)
            if m:
                return r.en_em(at) if r.ocasiao_em(at) == _OCASIAO_TROCAVEL[m.group(0)] else None
            # bug 17 (28/09): no clima, a peça que ela pôs pra ele ganha da roupa fixa da pose (menos a toalha)
            if not (at_home and intimo and level >= 1) or "towel" in pose.outfit:
                return None
        if at_home and intimo and level >= 1:
            return r.pro_clima(at, level)
        if level == 2 and r.ocasiao_em(at) != "provocar":
            return None
        return r.en_em(at)
    except Exception:
        logger.exception("photo_director.roupa")
        return None


def _outfit(pose: Pose, level: int, now: datetime, at_home: bool, rng: random.Random, db=None,
            intimo: bool = False, at: Optional[datetime] = None) -> tuple[Optional[str], bool]:
    """(roupa, veio do estado dela)."""
    estado = _roupa_de_agora(db, pose, level, at or now, at_home, intimo)
    if estado:
        return estado, True
    return _outfit_sorteio(pose, level, now, at_home, rng), False


def _outfit_sorteio(pose: Pose, level: int, now: datetime, at_home: bool, rng: random.Random) -> Optional[str]:
    """Sem o estado da roupa (teste, banco sem mundo): o sorteio antigo."""
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
    pick = "touch" if getattr(turn, "arousal", 0) >= HOT_AT else "tease"
    return pick if pick in tags else tags[0]     # pose com momentos próprios (sentando no dildo)


def direct(db, now: datetime, *, request: str = "", her_line: str = "", camera_ctx=None, turn=None,
           feeling=None, her_initiative: bool = False, chooser: Optional[Callable] = None,
           rng: Optional[random.Random] = None, fertile: bool = False, force_pose: Optional[str] = None,
           expression_override: str = "", outfit_override: Optional[str] = None,
           friend_outfit_override: Optional[str] = None, scene_at: Optional[datetime] = None) -> DirectedShot:
    """Decide a foto inteira e devolve o prompt pronto pro Krea 2. `scene_at`: a hora da cena quando a foto é de
    antes (post do rolê de ontem à noite); a luz de fora segue ela."""
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
    worded = _worded_pose(request, level, at_home) or _worded_pose(her_line, level, at_home, hers=True)
    food = _food(f"{request} {her_line}") if level <= 1 else None
    if food:
        worded = BY_ID["pov_comida" if at_home else "pov_comida_rua"]      # 26/09: comida é do ponto de vista dela
    if getattr(turn, "state", "") == "climax" and not worded and level >= 3:
        current = BY_ID.get((session or {}).get("pose", ""))
        if not (current and current.beats):          # sem cena com "momentos" rolando: foto do depois
            worded = BY_ID["pos_gozo"]
    friend = _group_friend(camera_ctx, request) if not at_home and level <= 1 else ""
    if friend and not worded and _GROUP_ASK.search(f"{request} {her_line}"):
        worded = BY_ID[GROUP_POSES[0]]
    if force_pose in BY_ID:
        worded = BY_ID[force_pose]
    if worded and worded.id in GROUP_POSES and not friend:
        worded = None                                # ninguém com ela (ou sem RG): não tem com quem
    if session and session.get("pose") in GROUP_POSES and session.get("friend") != friend:
        session = None                               # a amiga foi embora: a sessão da foto de grupo acabou
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
    intimo = not outfit_override and ((asked or 0) >= 1 or getattr(turn, "state", "off") in
                                      ("warming", "active", "climax", "afterglow"))
    if keep:
        room = session["room"]
        seed = session["seed"]
        outfit, do_estado = _outfit(pose, level, now, at_home, rng, db, intimo, scene_at)
        if not do_estado and session.get("level") == level and session.get("outfit") is not None:
            outfit = session["outfit"]
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
        # foto sem ela (comida, Milo, vista) só quando o assunto pede; "manda uma foto" é dela
        candidates = [p for p in POSES if room in p.rooms and p.levels[0] <= level <= p.levels[1]
                      and p.framing != "pov" and p.id != "mostrando_comida"]   # comida só se o assunto é comida
        if not at_home and not getattr(camera_ctx, "present_people", ()):
            candidates = [p for p in candidates if p.framing != "friend"]
        if not friend:
            candidates = [p for p in candidates if p.id not in GROUP_POSES]
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
        outfit, _ = _outfit(pose, level, now, at_home, rng, db, intimo, scene_at)

    if outfit_override and level <= 1:
        outfit = outfit_override           # 25/09: as duas opções de look que ela prometeu mandar
    beat = _pick_beat(pose, request, turn, session if keep else None) if level >= 4 else None
    action = dict(pose.beats)[beat] if beat else pose.action
    if beat:
        action = f"{pose.action}, {action}"
    action = action.replace("{food}", food or _food(session.get("food", "") if session else "") or "her snack")
    in_photo = friend if pose.id in GROUP_POSES else ""
    friend_outfit = ""
    if in_photo:
        friend_outfit = (friend_outfit_override or ((session or {}).get("friend_outfit") if keep else None)
                         or _friend_outfit(outfit, rng))
    if re.search(r"transparente|de vidro|\bclear\b", f"{request} {her_line}", re.IGNORECASE):
        action = action.replace(DILDO_TEXT, DILDO_CLEAR_TEXT)    # os dois dildos dela: rosa e transparente
    weather = getattr(camera_ctx, "weather", None) if camera_ctx else None
    rain = "chuva" if weather and (weather.get("heavy_rain") or "rain" in json.dumps(weather).lower()) else None
    luz = ""
    if room == "fora":
        from camera_world import PLACE_VISUAL
        visual = PLACE_VISUAL.get(place or "", "a street in Botafogo, Rio de Janeiro")
        visual = re.sub(r",?\s*candid (indoor )?smartphone photo", "", visual)
        luz = _luz_fora((scene_at or now).hour)
        setting, backdrop = f"{visual}{luz}", f"{visual.split(',')[0]} in soft focus{luz}"
    else:
        setting, backdrop = apartamento.setting(room, now, rain), apartamento.backdrop(room, now, rain)
    lora_weights = {}
    creamy = creamy_weight(beat, getattr(turn, "arousal", 0.0))
    if creamy:
        import civitai_images
        lora_weights[civitai_images.KREA2_CREAMY] = creamy
        if beat != "climax":            # no gozo o gatilho já entra pelo "right after she came"
            action = f"{action}, creamy wetness around her fingers, creamythings, creamy vagina"
    # Pose com roupa fixa no nível 3+ é roupa puxada/levantada (27/09): vale o corpo canônico junto.
    nude = level >= 3 and (outfit is None or outfit == pose.outfit)
    prompt = krea2_zoom_prompt(action, zoom=pose.zoom, setting=setting, backdrop=backdrop,
                               is_nsfw=nude, focus_angle=pose.angle, framing=pose.framing,
                               outfit=outfit,
                               expression=expression_override or pose.face or expression(feeling, turn))
    if in_photo:
        friend_line = _friend_sentence(in_photo, friend_outfit)
        prompt = (prompt.replace("Behind her, ", f"{friend_line} Behind them, ", 1) if "Behind her, " in prompt
                  else f"{prompt} {friend_line}")
    if luz:     # 28/09: "natural light" do molde puxava sol pra foto da noite
        prompt = re.sub(r"\b([Nn])atural light", lambda m: ("W" if m.group(1) == "N" else "w") + "arm night-time light",
                        prompt)
    # Gozo especial: se dedilhando (pose com o momento "fingers"), às vezes — o dobro no período fértil.
    special = (beat == "climax" and "fingers" in dict(pose.beats) and room in apartamento.ROOMS
               and rng.random() < SPECIAL_CLIMAX_CHANCE * (2 if fertile else 1))
    if special:
        import civitai_images
        sp = BY_ID[SPECIAL_POSE]
        prompt = krea2_zoom_prompt(f"{sp.action}, {SPECIAL_ACTION}", zoom=sp.zoom, setting=setting,
                                   backdrop=backdrop, is_nsfw=True, focus_angle=sp.angle, framing=sp.framing,
                                   expression=(face := rng.choice(SPECIAL_EXPRESSIONS)))
        lora_weights = {civitai_images.KREA2_SQUIRT: 1.5, civitai_images.KREA2_CREAMY: 0.0,
                        civitai_images.KREA2_FINGERING: 0.0}
        if face == AHEGAO_TRIGGER:
            lora_weights[civitai_images.KREA2_AHEGAO] = AHEGAO_WEIGHT
    nails = _nails(db, now)                  # 26/09: a cor de verdade das unhas dela (unhas.py)
    if nails:
        prompt = f"{prompt} {nails}"
    # 28/09: a make de verdade (roupa.py) — feita, borrada ou sem; cena passada (post de ontem) fica sem frase
    make = _make(db, now) if scene_at is None else ""
    if make:
        prompt = f"{prompt} {make}"
    prompt = _hair(db, now, prompt, action, cena_passada=scene_at is not None)  # 26/09: o cabelo de agora — cor, corte e penteado (cabelo.py)
    where = apartamento.ROOMS[room]["pt"] if room in apartamento.ROOMS else "na rua"
    facts = f"lugar: {where}; pose: {pose.pt}; roupa: {outfit or 'pelada'}"
    if beat:
        facts += f"; momento: {beat}"
    if in_photo:
        from social_day import short_name
        facts += f"; na foto junto com você: {short_name(in_photo)}"
    if declined:
        facts += "; ela está fora de casa e não dá pra mandar foto mais ousada daqui — provoca prometendo pra depois"
    new_session = {"place": place or HOME, "room": room, "pose": pose.id, "level": level, "outfit": outfit,
                   "beat": beat, "seed": seed, "at": now.isoformat(), "food": f"{request} {her_line}" if food else "",
                   "friend": in_photo, "friend_outfit": friend_outfit}
    # Calcinha/toalha em foto "normal" o moderador do Civitai barra: vai como adulta (Buzz amarelo).
    # 28/09: a gaveta íntima dela (roupa.py) — lingerie, fetiche e transparência também vão como adulta
    adult = level >= 2 or bool(outfit and re.search(r"panties|thong|towel|bralette|stockings|bodysuit|vinyl|"
                                                    r"harness|costume|nightie|babydoll", outfit))
    if pose.framing == "pov":
        # 26/09: foto tirada por ela, ela não aparece. Não vira sessão (o próximo "manda outra" é dela).
        from visual_profile import krea2_pov_prompt
        subject = action.replace("{milo}", MILO_VISUAL)
        mao = pose.id.startswith("pov_unhas")
        return DirectedShot(prompt=krea2_pov_prompt(subject, setting, hand=mao,
                                                    nails=nails if (mao or "hand" in subject) else ""), is_nsfw=False, focus_angle="frontal",
                            place_key=place or "", room=room, pose_id=pose.id, level=0, beat=None, outfit=None,
                            seed=seed, facts=f"lugar: {where}; foto tirada por você, do seu ponto de vista (você "
                            f"não aparece): {pose.pt}", session=session or {}, pov=True)
    return DirectedShot(prompt=prompt, is_nsfw=adult, focus_angle=pose.angle, place_key=place or "",
                        room=room, pose_id=pose.id, level=level, beat=beat, outfit=outfit, seed=seed,
                        facts=facts + ("; gozo especial: esguichou forte" if special else ""), declined=declined,
                        session=new_session, lora_weights=lora_weights, special=special, friend=in_photo)


_HAIR_DA_POSE = re.compile(r"\b(?:wet|damp|tangled|spread)\b", re.IGNORECASE)


def _hair(db, now: datetime, prompt: str, action: str, *, cena_passada: bool = False) -> str:
    """Troca o cabelo fixo do perfil pelo de agora. Se a pose já diz como o cabelo está (molhado, espalhado
    no travesseiro, embaraçado), o penteado fica o da pose. Cena passada (post do rolê de ontem): o estado guarda
    só a última lavagem, então molhado/touca/banho seriam os de hoje — fica o penteado do perfil (28/09)."""
    from visual_profile import HAIR_COLOR, HAIR_STYLE
    try:
        from cabelo import ESTILOS, Cabelo
        cab = Cabelo(db)
        cor, estilo = cab.visual(now)
        if cena_passada and cab.penteado(now) in ("molhado", "secando", "touca", "banho"):
            estilo = ESTILOS["natural"][1]
    except Exception:
        logger.exception("photo_director.cabelo")
        return prompt
    if cor:
        prompt = prompt.replace(HAIR_COLOR, cor)
    if estilo and not _HAIR_DA_POSE.search(action or ""):
        prompt = prompt.replace(HAIR_STYLE, estilo)
    return prompt


def _nails(db, now: datetime) -> str:
    try:
        from unhas import Unhas
        return Unhas(db).visual(now)
    except Exception:
        logger.exception("photo_director.unhas")
        return ""


def _make(db, at: datetime) -> str:
    if db is None:
        return ""
    try:
        from roupa import Roupa
        return Roupa(db).make_prompt(at)
    except Exception:
        logger.exception("photo_director.make")
        return ""


# Creamy pela excitação (Patrick, 24/09): sem Creamy no começo; se dedilhando, do degrau
# explícito pra cima ele sobe de 0.3 a 0.7 com o tesão; no gozo, 0.7.
CREAMY_MIN, CREAMY_MAX = 0.3, 0.7
CREAMY_BEATS = ("touch", "fingers", "spread")


def creamy_weight(beat: Optional[str], arousal: float) -> float:
    from intimacy import HOT_AT
    if beat == "climax":
        return CREAMY_MAX
    if beat not in CREAMY_BEATS or arousal < HOT_AT:
        return 0.0
    frac = min(1.0, (arousal - HOT_AT) / (1.0 - HOT_AT))
    return round(CREAMY_MIN + frac * (CREAMY_MAX - CREAMY_MIN), 2)


# Gozo especial (Patrick, 25/09, teste "WW"): a cena do tripé, as duas mãos apertando os seios e o
# esguicho saindo sozinho; Krea2 Squirt 1.5, SEM Fingering e SEM Creamy (o Creamy embranquece o jato).
# O prompt personalizado de squirt (teste MM) quebrava junto com o Fingering: ficou a cena padrão.
# Expressão varia a cada gozo extremo, "nessa linha" (Patrick). Depois ela manda a selfie molinha.
# PROVISÓRIO até o Patrick definir os fatores: 25% dos gozos se dedilhando, o dobro no período fértil.
SPECIAL_CLIMAX_CHANCE = 0.25
SPECIAL_POSE = "cama_tripe_duas_maos"
SPECIAL_ACTION = ("both hands squeezing her breasts while she comes, her legs spread wide on the white sheets, her "
                  "thighs trembling, squirting hands-free, a clear jet of liquid spraying from her pussy onto the "
                  "white sheets, squirt, female ejaculation")
# Ahegao (Patrick, 25/09, teste YY): LoRA Ahegao Face em 0.5 — 0.8 revirava demais e mexia no corpo.
AHEGAO_TRIGGER = "She is making the ahegao face - eyes rolled back and tongue hanging out, her cheeks flushed"
AHEGAO_WEIGHT = 0.5
SPECIAL_EXPRESSIONS = (
    "heavy-lidded eyes still looking straight at the camera, her lips parted in a trembling moan, her cheeks flushed",
    "biting her lower lip hard, heavy-lidded eyes on the camera, her cheeks flushed",
    "her mouth open in a silent moan, her brows raised, her eyes half closed but still on the camera, cheeks flushed",
    AHEGAO_TRIGGER,
)
AFTER_SPECIAL_EXPRESSION = "half-closed sleepy eyes, all limp and relaxed on the bed, a faint dazed smile"


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
