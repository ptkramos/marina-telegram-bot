"""Pré-visualização local do Mini App (26/09): banco temporário, token de teste, sem o bot.

Uso: python scripts/webapp_preview.py [porta] [--db cópia.db] [--agora 2026-09-25T18:40]
     → http://127.0.0.1:8799. Com --db, abre uma CÓPIA de um banco real (ex.: backup) sem semear nada;
     com --agora, o app vê esse horário (pra conferir o card da aba Agora em cada etapa).
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


async def main(port: int, banco: str = "", agora: str = "") -> None:
    fixo = datetime.fromisoformat(agora) if agora else None
    if banco:
        import shutil
        copia = Path(tempfile.mkdtemp()) / "preview.db"
        shutil.copy(banco, copia)
        db = DatabaseManager(copia)
    else:
        db = DatabaseManager(Path(tempfile.mkdtemp()) / "preview.db")
        seed_world_bible(db)

    def status(now: datetime) -> dict:
        # mesmo formato do bot._status_snapshot (valores de exemplo)
        return {"now": now.isoformat(), "atividade": "tempo livre em casa", "local": "Apartamento da Marina (Botafogo)",
                "disponivel": "Online, respondendo rápido", "ciclo_dia": 24, "ciclo_fase": "fase pré-menstrual / tpm",
                "saude": [], "proximo": ("aula de Projeto", "segunda 14:00"), "planos": [("bar com o Theo e a Júlia", "sábado 20:30")]}

    if banco:
        return await _serve(db, port, status, fixo)
    # um sentimento e movimentações de exemplo pros Bastidores
    import financas
    from emotion import EmotionEngine
    agora = datetime.now()
    EmotionEngine(db).feel("tristeza", "saudade", 0.5, "ele passou o dia sumido", agora, target="o Patrick")
    financas.receive_pix(db, 150, "pro açaí", agora)
    import canon_extras
    from social_world import seed_social
    seed_social(db)
    canon_extras.ensure(db)
    with db.get_connection() as conn:          # um contato de exemplo pro Mundo
        conn.execute("UPDATE social_relationships SET last_interaction_at=?, contact_frequency=4 WHERE character_key='bia_andrade'",
                     (agora.replace(hour=8, minute=15).isoformat(),))

    await _serve(db, port, status, fixo)


async def _serve(db, port: int, status, fixo) -> None:
    async def pix(valor: int, recado: str) -> dict:
        return {"ok": True}

    async def post_receipt(query_id: str, url: str) -> bool:
        print("comprovante:", url)
        return True

    relogio = {"t": fixo}                      # /dev/agora?t=2026-09-25T21:20 troca o horário sem reiniciar
    hooks = webapp_server.Hooks(db=db, bot_token=TOKEN, allowed_user_id=USER, status=status, pix=pix,
                                post_receipt=post_receipt, public_url=f"http://127.0.0.1:{port}",
                                now=lambda: relogio["t"] or datetime.now())
    original_make = webapp_server.make_app

    async def dev_agora(request):
        t = request.query.get("t", "")
        relogio["t"] = datetime.fromisoformat(t) if t else None
        return web.json_response({"agora": relogio["t"].isoformat() if relogio["t"] else "real"})

    def make_app(h):
        app = original_make(h)
        app.router.add_get("/dev/agora", dev_agora)
        return app

    webapp_server.make_app = make_app
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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("porta", nargs="?", type=int, default=8799)
    ap.add_argument("--db", default="")
    ap.add_argument("--agora", default="")
    a = ap.parse_args()
    asyncio.run(main(a.porta, a.db, a.agora))
