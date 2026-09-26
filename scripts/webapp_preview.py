"""Pré-visualização local do Mini App (26/09): banco temporário, token de teste, sem o bot.

Uso: python scripts/webapp_preview.py [porta]   → http://127.0.0.1:8799
A página recebe um initData assinado com o token de teste (window.__DEV_INIT), e só esta
pré-visualização injeta isso: em produção o app só aceita o initData do Telegram.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiohttp import web  # noqa: E402

import webapp_server  # noqa: E402
from db import DatabaseManager  # noqa: E402
from seed_world_bible_v36 import seed_world_bible  # noqa: E402

TOKEN, USER = "dev-preview-token", 1


def signed_init() -> str:
    pairs = {"auth_date": str(int(time.time()) + 6 * 3600), "user": json.dumps({"id": USER, "first_name": "Patrick"}),
             "query_id": "dev"}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def main(port: int) -> None:
    db = DatabaseManager(Path(tempfile.mkdtemp()) / "preview.db")
    seed_world_bible(db)

    def status(now: datetime) -> dict:
        return {"now": now.isoformat(), "atividade": "tempo livre em casa", "local": "Apartamento da Marina (Botafogo)",
                "disponivel": "Online, respondendo rápido"}

    async def pix(valor: int, recado: str) -> dict:
        return {"ok": True}

    async def post_receipt(query_id: str, url: str) -> bool:
        print("comprovante:", url)
        return True

    hooks = webapp_server.Hooks(db=db, bot_token=TOKEN, allowed_user_id=USER, status=status, pix=pix,
                                post_receipt=post_receipt, public_url=f"http://127.0.0.1:{port}")
    original_index = webapp_server._index

    async def index(request):
        resp = await original_index(request)
        html = resp.text.replace("<script src=\"/static/app.js",
                                 f"<script>window.__DEV_INIT={json.dumps(signed_init())}</script><script src=\"/static/app.js", 1)
        return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})

    webapp_server._index = index
    runner = await webapp_server.start(hooks, port=port)
    print(f"pré-visualização em http://127.0.0.1:{port}")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8799))
