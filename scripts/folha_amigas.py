"""Folha de personagem das amigas (27/09, Patrick): 4 vistas num fundo cinza, de body cinza justo.

    venv/Scripts/python.exe scripts/folha_amigas.py carol_menezes 3x4        # só a 3x4 de documento (data/amigas/<nome>_3x4.jpg)
    venv/Scripts/python.exe scripts/folha_amigas.py carol_menezes folha      # a folha, a partir da 3x4 (ou do RG, sem 3x4)

Salva com "_teste" no nome; a que vale é renomeada depois de aprovada. ~20 Buzz cada passo.
Com a folha no lugar, a troca de rosto e a foto da amiga sozinha usam ela no lugar do RG.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import civitai_images  # noqa: E402


async def main(amiga: str, passo: str) -> None:
    rg = ROOT / civitai_images.FRIEND_RG[amiga]
    if passo == "3x4":
        dados = await civitai_images.friend_id_photo(amiga)
        destino = rg.with_name(rg.stem.replace("_rg", "_3x4_teste") + ".jpg")
    else:
        id_foto = rg.with_name(rg.stem.replace("_rg", "_3x4") + ".jpg")
        dados = await civitai_images.friend_sheet(amiga, base=id_foto.read_bytes() if id_foto.is_file() else None)
        destino = rg.with_name(rg.stem.replace("_rg", "_folha_teste") + ".jpg")
    if not dados:
        print("falhou")
        return
    destino.write_bytes(dados)
    print(f"SALVO {destino}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "folha"))
