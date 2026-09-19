"""
Serviço de Visão Computacional Multimodal da Marina Salles (Vision Service v3.7.0).
Permite que a Marina veja, interprete e reaja com carinho e naturalidade de namorada
às fotos enviadas pelo Patrick no Telegram (selfies, refeições, pets, lugares, objetos).
"""
import io
import json
import base64
import logging
import asyncio
from typing import Optional, Dict, Any
from PIL import Image
from openai import OpenAI

from config import settings

logger = logging.getLogger("VisionService")

VISION_PROMPT = """You are Marina Salles' visual perception extraction component.
Analyze the photo Patrick Ramos just sent and return STRICTLY structured JSON of concrete visible elements.

REQUIRED JSON:
{
  "scene": "clear concise description of setting/situation",
  "people": ["short descriptions or 'Patrick' if selfie"],
  "objects": ["main visible objects"],
  "food": ["food/drink items if any"],
  "visible_text": ["legible text on signs/screens/shirts if any"],
  "notable_details": ["details worth a caring remark"],
  "uncertain_details": []
}

RULES:
- Be factual. Do not invent beyond the image.
- Return ONLY valid JSON, no markdown.
"""


class VisionService:
    def __init__(self, llm_client: Optional[OpenAI] = None, vision_model: Optional[str] = None):
        self.llm = llm_client or OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL
        )
        self.vision_model = vision_model or settings.VISION_MODEL

    def resize_and_encode_image(self, image_bytes: bytes, max_dimension: int = 1024) -> str:
        """Redimensiona com segurança a imagem mantendo aspect ratio e converte para base64 JPEG."""
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Converte para RGB caso esteja em RGBA ou Palette
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")

            width, height = img.size
            if max(width, height) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85, optimize=True)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")

    async def analyze_image(self, image_bytes: bytes, caption: str = "") -> Dict[str, Any]:
        """Processa a foto recebida via API de visão multimodal e retorna dados estruturados."""
        if not getattr(settings, "VISION_ENABLED", True):
            logger.info("Visão desabilitada por configuração.")
            return self._fallback_data("Foto recebida do Patrick")

        try:
            b64_img = await asyncio.to_thread(self.resize_and_encode_image, image_bytes)

            user_prompt = "Descreva detalhadamente o que você vê nesta foto enviada pelo Patrick."
            if caption:
                user_prompt += f" Legenda enviada com a foto: '{caption}'"

            messages = [
                {"role": "system", "content": VISION_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_img}"
                            }
                        }
                    ]
                }
            ]

            response = await asyncio.to_thread(
                self.llm.chat.completions.create,
                model=self.vision_model,
                messages=messages,
                max_tokens=300,
                temperature=0.2,
                response_format={"type": "json_object"}
            )

            raw_text = response.choices[0].message.content.strip()
            data = json.loads(raw_text)
            logger.info(f"Visão computacional processada com sucesso: {data.get('scene')}")
            return {
                "scene": data.get("scene", "foto enviada pelo Patrick"),
                "people": data.get("people", []),
                "objects": data.get("objects", []),
                "food": data.get("food", []),
                "visible_text": data.get("visible_text", []),
                "notable_details": data.get("notable_details", []),
                "uncertain_details": data.get("uncertain_details", [])
            }
        except Exception as e:
            logger.error(f"Erro ao analisar imagem com Vision API: {e}")
            fallback_scene = f"foto enviada pelo Patrick: {caption}" if caption else "foto enviada pelo Patrick"
            return self._fallback_data(fallback_scene, error=str(e))

    def _fallback_data(self, scene: str, error: Optional[str] = None) -> Dict[str, Any]:
        data = {
            "scene": scene,
            "people": [],
            "objects": [],
            "food": [],
            "visible_text": [],
            "notable_details": [],
            "uncertain_details": []
        }
        if error:
            data["error"] = error
        return data

    def format_vision_context(self, vision_data: Dict[str, Any], caption: str = "") -> str:
        """Data-only vision evidence for the context builder (no behavioral imperatives)."""
        scene = vision_data.get("scene", "foto enviada pelo Patrick")
        people = vision_data.get("people", [])
        food = vision_data.get("food", [])
        objects = vision_data.get("objects", [])
        text = vision_data.get("visible_text", [])
        notables = vision_data.get("notable_details", [])

        lines = ["[VISION EVIDENCE — data only]"]
        lines.append(f"- scene: {scene}")
        if people:
            lines.append(f"- people: {', '.join(people)}")
        if food:
            lines.append(f"- food: {', '.join(food)}")
        if objects:
            lines.append(f"- objects: {', '.join(objects[:5])}")
        if text:
            lines.append(f"- visible_text: {', '.join(text[:3])}")
        if notables:
            lines.append(f"- notable_details: {', '.join(notables[:3])}")
        if caption:
            lines.append(f'- caption: "{caption}"')
        from prompt_policy import format_vision_evidence
        return format_vision_evidence(lines)


vision_service = VisionService()
