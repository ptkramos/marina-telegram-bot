import asyncio
import sys
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
