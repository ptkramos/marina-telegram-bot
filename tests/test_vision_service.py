"""
Testes Unitários Automatizados para o VisionService da Marina Salles (v3.7.0).
"""
import io
import sys
import base64
import unittest
from pathlib import Path
from PIL import Image
from unittest.mock import MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from vision_service import VisionService


class TestVisionService(unittest.TestCase):
    def setUp(self):
        self.service = VisionService()

    def _generate_test_image_bytes(self, width: int = 1600, height: int = 1200, color: str = "red") -> bytes:
        """Gera imagem em memória para teste de redimensionamento e encoding."""
        img = Image.new("RGB", (width, height), color=color)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    def test_resize_and_encode_image(self):
        """Verifica se imagens grandes são reduzidas com segurança para max_dimension mantendo aspect ratio."""
        large_bytes = self._generate_test_image_bytes(width=2000, height=1000)
        b64_str = self.service.resize_and_encode_image(large_bytes, max_dimension=1024)

        # Decodifica para verificar as novas dimensões
        decoded = base64.b64decode(b64_str)
        with Image.open(io.BytesIO(decoded)) as img:
            w, h = img.size
            self.assertLessEqual(w, 1024)
            self.assertLessEqual(h, 1024)
            self.assertEqual(w, 1024)
            self.assertEqual(h, 512)

    def test_format_vision_context_with_details(self):
        """Verifica se o bloco contextual de visão é gerado com instruções afetivas de namorada."""
        vision_data = {
            "scene": "um hambúrguer artesanal com batata frita",
            "people": [],
            "objects": ["prato", "copo de refrigerante"],
            "food": ["hambúrguer duplo com queijo", "batata frita"],
            "visible_text": ["Cardápio Burguer"],
            "notable_details": ["queijo derretido apetitoso"],
            "uncertain_details": []
        }
        caption = "Olha o meu almoço hoje amor!"
        context_str = self.service.format_vision_context(vision_data, caption=caption)

        self.assertIn("[FOTO RECEBIDA DO PATRICK AGORA]", context_str)
        self.assertIn("hambúrguer artesanal", context_str)
        self.assertIn("hambúrguer duplo com queijo", context_str)
        self.assertIn("Olha o meu almoço hoje amor!", context_str)
        self.assertIn("INSTRUÇÃO DE RESPOSTA", context_str)

    def test_fallback_data(self):
        """Garante retorno de fallback seguro caso ocorra erro ou a visão esteja desabilitada."""
        fallback = self.service._fallback_data("foto de praia", error="timeout simulado")
        self.assertEqual(fallback["scene"], "foto de praia")
        self.assertEqual(fallback["error"], "timeout simulado")
        self.assertIsInstance(fallback["objects"], list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
