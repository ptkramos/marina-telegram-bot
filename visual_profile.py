"""
Módulo de Perfil Visual & Continuidade de Câmera da Marina Salles (v3.7.0).
Centraliza o DNA visual calibrado da Marina baseado na referência oficial (marina_teste_calibrada.png)
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

# --- DNA VISUAL CALIBRADO — Marina Salles ---
# Extraído e calibrado a partir da referência oficial (marina_teste_calibrada.png)
# FLUX.1 Dev FP8 + marina_flux (1.0) + NSFW_master (0.7 quando nsfw)
# Age is NOT hard-coded; use young adult descriptor only.
MARINA_VISUAL_DNA_BASE = (
    "candid amateur photo of marina_reference, young adult Brazilian woman, gorgeous face, "
    "expressive luminous honey-amber eyes, delicate nose, full plump lips, full cheeks, "
    "voluminous wavy chocolate brown hair with golden blonde tips"
)

MARINA_PHYSIQUE_DNA = (
    "fit athletic model physique, slim waist, shapely feminine proportions, "
    "natural standing posture, perky upright busts, round bubble butt, clean neat natural female anatomy, "
    "subtle beach golden tan glow, natural sun-kissed skin tone with visible crisp bikini tan lines"
)

# 24/09: foto normal com o corpo descrito como na adulta ("perky upright busts,
# round bubble butt, bikini tan lines") saiu SEM ROUPA pelo Civitai — o
# pedido era selfie de pijama. Na foto vestida o corpo fica sem esses termos.
MARINA_PHYSIQUE_SFW = (
    "fit athletic model physique, slim waist, natural standing posture, "
    "subtle beach golden tan glow, natural sun-kissed skin tone"
)

MARINA_REALISM_TAGS = (
    "authentic natural lighting, high realism, highly detailed natural skin texture with visible fine pores, "
    "natural skin folds and subtle imperfections, authentic flash photography reflection, realistic non-plastic non-rubber skin, "
    "shot on iphone, raw candid mobile photography"
)

MIRROR_SELFIE_TRIGGER = (
    "candid mirror selfie, holding space black iphone 16 pro with sleek matte titanium frame and triple camera lens module, "
    "natural hand grip, authentic phone glass reflection, mirror reflection"
)


# Presets de Anatomia
ANATOMY_SFW = ("fully clothed, wearing clothes that cover chest and body, modest casual outfit, "
               "no nudity, no cleavage, natural model posture")

ANATOMY_NSFW_FRONTAL = (
    "completely naked, uncensored, perky natural breasts, firm upright high-set bust, "
    "visible bikini top tan line, erect pink nipples with detailed natural areolas, slim waist, natural hips, "
    "visible bikini bottom tan lines on hips, round bubble butt, detailed explicit female anatomy, pink labia, shaved pussy"
)

ANATOMY_NSFW_BEHIND = (
    "from behind, round bubble butt projecting backward, firm shapely buttocks, "
    "visible cheeky bikini tan lines on tan buttocks, perky natural female curves, "
    "completely naked, uncensored, detailed explicit female anatomy"
)

ANATOMY_NSFW_SIDE = (
    "side view profile, completely naked, uncensored, perky upright high-set natural breast with visible erect pink nipple and areola, "
    "visible side bikini tan lines, slim waist, arched lower back, explicit female anatomy"
)



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
KREA2_IDENTITY = (
    "a candid smartphone photo of a young Brazilian woman with soft light amber-hazel eyes, a few faint light "
    "freckles across her nose and cheeks, and long chestnut brown hair with golden blonde tips, "
    "semi-straight with soft waves at the ends"
)
KREA2_BODY_SFW = "She has a fit, slim body with a natural sun-kissed tan."
KREA2_BODY_NSFW = "She has a fit, slim body with a natural sun-kissed tan and visible bikini tan lines."
KREA2_CLOTHED = "She is fully clothed, her outfit covers her chest and body."
KREA2_NUDE = {
    "frontal": "She is completely naked, facing the camera.",
    "behind": ("Seen from behind, she is completely naked, showing her round firm butt with cheeky bikini "
               "tan lines, looking back over her shoulder."),
    "side": "Seen from the side, she is completely naked, her slim waist and arched lower back in profile.",
}
# Corpo canônico (Patrick, 24/09): o da foto "adulta_a" da rodada 2 (pilha a, slider 2.5).
# Sempre as MESMAS palavras em toda foto adulta — é o que segura o corpo igual de uma
# foto pra outra. Uma pinta só, fixa, no seio esquerdo (decisão do Patrick).
# 24/09 (teste): "full" + slider 2.5 aumentou demais — o tamanho fica só com o slider;
# "single beauty mark… no other moles" virou 3–4 pintas: posição concreta obedece melhor.
# 24/09 (FinePorn): "rosa" solto saía bege/amarronzado — amarrar a cor à boca dela segura o tom.
KREA2_BODY_CANON = (
    "Her breasts are round and natural, with medium areolas and small nipples in a clear soft pink, the "
    "same light pink as her lips, and pale triangle bikini tan lines on them. She has a single unique "
    "tiny dark mole just above her left nipple; no freckles or dots anywhere else on her chest. Her pussy "
    "is fully shaved, small and neat, with clear light pink inner lips, the same soft pink as her nipples, "
    "framed by a pale bikini-bottom tan line. Her anus is small, tight and light pink."
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
_NOT_A_PHOTO = re.compile(r"\b(photo[- ]?realistic|hyper[- ]?realistic|ultra[- ]?realistic|high realism|realism|8k|masterpiece)\b",
                          re.IGNORECASE)


def krea2_prompt(scene: str, *, is_nsfw: bool, focus_angle: str = "frontal", is_mirror: bool = False) -> str:
    """Prompt em texto corrido pro Krea 2, com o gatilho do LoRA dela e os traços da Marina."""
    scene = _NOT_A_PHOTO.sub("", scene or "")
    scene = re.sub(r"\s*,(\s*,)+\s*", ", ", scene)
    scene = re.sub(r"\s{2,}", " ", scene).strip(" ,.")
    distant = not is_mirror and any(k in scene.lower() for k in KREA2_DISTANT)
    identity = KREA2_IDENTITY.replace("a candid smartphone photo of", "a candid full body photo of") if distant         else KREA2_IDENTITY
    parts = [f"{KREA2_TRIGGER}, {KREA2_EMOTIONS_TRIGGER}. {identity[0].upper()}{identity[1:]}."]
    if distant:   # o Krea 2 pesa mais o começo: o enquadramento vem antes de tudo
        parts.insert(0, KREA2_FRAMING_DISTANT)
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
    parts.append(KREA2_PHOTO_DISTANT if distant else KREA2_PHOTO)
    return " ".join(parts)


def _krea2_active() -> bool:
    try:
        from config import settings
        if getattr(settings, "IMAGE_ENGINE", "") != "civitai":
            return False
        import civitai_images
        return civitai_images.ecosystem() == "krea2"
    except Exception:
        return False

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
        Monta o prompt FLUX.1 Dev calibrado. Se for detectado pedido de continuidade dentro da janela
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

        # Seleciona bloco anatômico calibrado
        clothed_cues = ["clothed", "wearing", "dress", "vestid", "roupa", "hoodie", "top", "pajama", "pijama", "jeans", "shorts", "shirt", "casual"]
        if not final_nsfw or any(k in scene_part.lower() for k in clothed_cues):
            anatomy_tag = ANATOMY_SFW
            final_nsfw = False
        elif final_angle == "behind":
            anatomy_tag = ANATOMY_NSFW_BEHIND
        elif final_angle == "side":
            anatomy_tag = ANATOMY_NSFW_SIDE
        else:
            anatomy_tag = ANATOMY_NSFW_FRONTAL

        # Se for pedido de selfie no espelho, enriquece a cena com os triggers do iPhone 16 Pro preto
        is_mirror = any(kw in combined_text.lower() for kw in ["espelho", "mirror", "selfie no espelho", "mirror selfie", "segurando celular"])
        if is_mirror and not any(kw in scene_part.lower() for kw in ["mirror selfie", "holding space black"]):
            scene_part = f"{scene_part}, {MIRROR_SELFIE_TRIGGER}".strip(", ")

        if _krea2_active():
            scene_krea2 = scene_part
            if is_mirror:
                scene_krea2 = scene_krea2.replace(MIRROR_SELFIE_TRIGGER, "").strip(" ,")
            return (krea2_prompt(scene_krea2, is_nsfw=final_nsfw, focus_angle=final_angle, is_mirror=is_mirror),
                    final_nsfw, final_angle)

        physique = MARINA_PHYSIQUE_DNA if final_nsfw else MARINA_PHYSIQUE_SFW
        full_prompt = (
            f"{MARINA_VISUAL_DNA_BASE}, {scene_part}, {anatomy_tag}, "
            f"{physique}, {MARINA_REALISM_TAGS}"
        ).strip(", ")

        return full_prompt, final_nsfw, final_angle


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


def build_flux_prompt(scene_tags: str, is_nsfw: bool = False, focus_angle: str = 'frontal') -> str:
    """Thin wrapper — visual_profile is the single visual authority."""
    prompt, _, _ = visual_profile.build_scene_prompt(
        scene_description=scene_tags,
        is_nsfw=is_nsfw,
        focus_angle=focus_angle,
    )
    return prompt
