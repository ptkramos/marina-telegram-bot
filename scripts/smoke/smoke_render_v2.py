"""Manual render probe contra o ComfyUI. Rodar à mão; faz chamada de GPU real.

Auditoria #1: movido de `test_render_v2.py` na raiz — o prefixo `test_` sugeria
que era parte da suíte automatizada.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sd_client import sd_client

async def test():
    print("Renderizando teste v2 com add_detail e novos negativos...")
    scene = "sitting on bed, wearing sexy black lace nightwear, soft bedroom morning light, confident seductive gaze"
    buf = await sd_client.generate_photo(scene)
    if buf:
        with open("marina_teste_v2.png", "wb") as f:
            f.write(buf.getbuffer())
        print("Sucesso! Imagem salva em marina_teste_v2.png")
    else:
        print("Falha na geracao!")

if __name__ == "__main__":
    asyncio.run(test())
