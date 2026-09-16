"""
Módulo de Perfil Visual & Continuidade de Câmera da Marina Seltin.
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

# --- DNA VISUAL CALIBRADO DA MARINA SELTIN ---
# Extraído e calibrado diretamente a partir da referência perfeita oficial (marina_teste_calibrada.png)
# FLUX.1 Dev FP8 + marina_flux (1.0) + NSFW_master (0.7 quando nsfw)
MARINA_VISUAL_DNA_BASE = (
    "candid amateur photo of marina_reference, 19yo woman, gorgeous face, "
    "expressive luminous honey-amber eyes, delicate nose, full plump lips, full cheeks, "
    "voluminous wavy chocolate brown hair with golden blonde tips"
)

MARINA_PHYSIQUE_DNA = (
    "fit athletic model physique, slim waist, shapely feminine proportions, "
    "natural standing posture, perky upright busts, round bubble butt, clean neat natural female anatomy, "
    "subtle beach golden tan glow, natural sun-kissed skin tone with visible crisp bikini tan lines"
)

MARINA_REALISM_TAGS = (
    "authentic apartment lighting, high realism, highly detailed natural skin texture with visible fine pores, "
    "natural skin folds and subtle imperfections, authentic flash photography reflection, realistic non-plastic non-rubber skin, "
    "shot on iphone, raw candid mobile photography"
)

MIRROR_SELFIE_TRIGGER = (
    "candid mirror selfie, holding space black iphone 16 pro with sleek matte titanium frame and triple camera lens module, "
    "natural hand grip, authentic phone glass reflection, mirror reflection"
)


# Presets de Anatomia
ANATOMY_SFW = "fully clothed, modest elegant casual outfit, zero nudity, natural model posture"

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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CameraState":
        return cls(
            scene_tags=d.get("scene_tags", ""),
            outfit=d.get("outfit", ""),
            location=d.get("location", ""),
            focus_angle=d.get("focus_angle", "frontal"),
            is_nsfw=bool(d.get("is_nsfw", False)),
            full_prompt=d.get("full_prompt", ""),
            timestamp=float(d.get("timestamp", 0.0))
        )


class VisualProfileManager:
    """Gerencia o DNA visual da Marina Seltin, continuidade de câmera e construção de prompts."""

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
        focus_angle: Optional[str] = None
    ) -> tuple[str, bool, str]:
        """
        Monta o prompt FLUX.1 Dev calibrado. Se for detectado pedido de continuidade dentro da janela
        temporal, preserva o outfit e ambiente da foto anterior variando pose/ângulo.
        Retorna: (full_prompt, is_nsfw, focus_angle)
        """
        combined_text = f"{scene_description} {user_intent}".strip()
        is_continuity = self.is_continuity_request(combined_text)

        now = time.time()
        has_recent_state = (
            self._current_state is not None
            and (now - self._current_state.timestamp) <= CONTINUITY_WINDOW_SECONDS
        )

        if is_continuity and has_recent_state:
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

        full_prompt = (
            f"{MARINA_VISUAL_DNA_BASE}, {scene_part}, {anatomy_tag}, "
            f"{MARINA_PHYSIQUE_DNA}, {MARINA_REALISM_TAGS}"
        ).strip(", ")

        return full_prompt, final_nsfw, final_angle


    def record_photo_generation(
        self,
        scene_tags: str,
        full_prompt: str,
        is_nsfw: bool,
        focus_angle: str = "frontal",
        outfit: str = "",
        location: str = ""
    ):
        """Registra a geração bem-sucedida de foto para manter a continuidade."""
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
            timestamp=now
        )

        try:
            payload = json.dumps(self._current_state.to_dict())
            db_manager.set_estado_relacional("camera_last_state", payload)
            logger.info(f"📸 Estado de câmera registrado: loc={loc}, outfit={out}, angle={focus_angle}, nsfw={is_nsfw}")
        except Exception as e:
            logger.warning(f"Falha ao persistir camera_last_state no banco: {e}")


# Instância global do perfil visual
visual_profile = VisualProfileManager()
