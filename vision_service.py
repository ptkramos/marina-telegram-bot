"""
Serviço de Visão Computacional Multimodal da Marina Seltin (Vision Service).
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

VISION_PROMPT = """Você é o Sistema de Percepção Visual da namorada Marina Seltin.
Analise a foto que Patrick Ramos (namorado da Marina) acabou de enviar e retorne ESTRITAMENTE um JSON estruturado com os elementos reais e concretos visíveis na imagem.

ESTRUTURA OBRIGATÓRIA (JSON puro):
{
  "scene": "descrição clara e concisa do ambiente ou situação geral (ex: prato de almoço em restaurante, selfie do Patrick no espelho, praia ensolarada, monitor com código)",
  "people": ["descrição curta de pessoas presentes ou 'Patrick' se for selfie/ele"],
  "objects": ["principais objetos visíveis"],
  "food": ["itens de comida ou bebida se houver"],
  "visible_text": ["textos legíveis em placas, telas, camisetas se houver"],
  "notable_details": ["detalhes marcantes que chamam atenção carinhosa"],
  "uncertain_details": []
}

REGRAS:
- Seja factual e objetivo. Não invente nada além do que a imagem mostra.
- Devolva APENAS o JSON válido, sem tags markdown ou comentários.
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
        """Formata os dados visuais estruturados em um bloco contextual orgânico para o Context Builder."""
        scene = vision_data.get("scene", "foto enviada pelo Patrick")
        people = vision_data.get("people", [])
        food = vision_data.get("food", [])
        objects = vision_data.get("objects", [])
        text = vision_data.get("visible_text", [])
        notables = vision_data.get("notable_details", [])

        lines = [f"[FOTO RECEBIDA DO PATRICK AGORA]"]
        lines.append(f"- O que você está vendo na foto: {scene}")
        if people:
            lines.append(f"- Pessoas na foto: {', '.join(people)}")
        if food:
            lines.append(f"- Comida/Bebida visível: {', '.join(food)}")
        if objects:
            lines.append(f"- Objetos/Ambiente: {', '.join(objects[:5])}")
        if text:
            lines.append(f"- Textos visíveis na imagem: {', '.join(text[:3])}")
        if notables:
            lines.append(f"- Detalhes marcantes: {', '.join(notables[:3])}")
        if caption:
            lines.append(f"- Legenda que o Patrick escreveu junto: \"{caption}\"")

        lines.append(
            "(INSTRUÇÃO DE RESPOSTA: Reaja de forma 100% natural, espontânea e carinhosa como namorada do Patrick ao que você acabou de ver na foto dele! "
            "NUNCA diga 'vejo na imagem', 'a foto mostra' ou use linguagem robótica; comente diretamente sobre a foto com afeto, como qualquer pessoa real faz no Telegram!)."
        )
        return "\n".join(lines)


vision_service = VisionService()
