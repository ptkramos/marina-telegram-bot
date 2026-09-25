"""Mini App da Marina (PLANO_WEBAPP_MARINA.md, 25/09).

Roda dentro do processo do bot (mesmo banco, mesmo loop), em 127.0.0.1:8787; o nginx
da VPS publica em https://marina.psoft.app. Só o Patrick entra: toda chamada à API
manda o initData do Telegram, que é validado com o token do bot (HMAC) e tem que ser
do TARGET_CHAT_ID. O frontend (webapp/) é HTML/JS puro.

Duas partes com papéis opostos: a vida dela (banco, delivery) com cara de app real,
e os bastidores (status, emoção, o dia, o mundo), onde número e barrinha são bem-vindos.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import parse_qsl

from aiohttp import web

logger = logging.getLogger("WebApp")

STATIC_DIR = Path(__file__).parent / "webapp"
CARDAPIO_PATH = STATIC_DIR / "cardapio.json"
INIT_DATA_MAX_AGE = 24 * 3600
PIX_MAX = 5000


# ---------------------------------------------------------------- autenticação --
def validate_init_data(init_data: str, bot_token: str, *, now: Optional[float] = None,
                       max_age: int = INIT_DATA_MAX_AGE) -> Optional[dict]:
    """Confere a assinatura do Telegram (core.telegram.org/bots/webapps). Devolve o user ou None."""
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received = pairs.pop("hash", "")
    if not received:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if (now if now is not None else time.time()) - auth_date > max_age:
        return None
    try:
        return json.loads(pairs.get("user", "{}"))
    except ValueError:
        return None


# --------------------------------------------------------------------- ganchos --
@dataclass
class Hooks:
    """O que o app precisa do bot, sem importar o bot (evita import circular)."""
    db: Any
    bot_token: str
    allowed_user_id: int
    status: Callable[[datetime], dict]                        # _status_snapshot
    pix: Callable[[int, str], Awaitable[dict]]                # registra e faz ela reagir
    now: Callable[[], datetime] = datetime.now


def _json(data: Any, status: int = 200) -> web.Response:
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        raise TypeError(type(o).__name__)
    return web.json_response(data, status=status, dumps=lambda d: json.dumps(d, default=default, ensure_ascii=False))


def _error(msg: str, status: int) -> web.Response:
    return _json({"erro": msg}, status)


@web.middleware
async def _auth(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    hooks: Hooks = request.app["hooks"]
    user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), hooks.bot_token)
    if not user or int(user.get("id", 0)) != int(hooks.allowed_user_id):
        logger.warning("webapp.denied path=%s user=%s", request.path, (user or {}).get("id"))
        return _error("sem permissão", 403)
    return await handler(request)


# -------------------------------------------------------------------- estáticos --
async def _index(request: web.Request) -> web.StreamResponse:
    # O webview do Telegram guarda app.js/app.css em cache: a versão no link força o novo após um deploy.
    version = str(int(max((STATIC_DIR / f).stat().st_mtime for f in ("app.js", "app.css"))))
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8").replace("__V__", version)
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})


# --------------------------------------------------------------------- dados --
def load_cardapio() -> dict:
    return json.loads(CARDAPIO_PATH.read_text(encoding="utf-8"))


def _find_item(cardapio: dict, rest_id: str, item_id: str):
    for rest in cardapio.get("restaurantes", []):
        if rest["id"] == rest_id:
            for item in rest["itens"]:
                if item["id"] == item_id:
                    return rest, item
    return None, None


def order_view(order: Optional[dict], now: datetime) -> Optional[dict]:
    """O pedido do Patrick como ele vê no app (o dela não aparece: é a vida dela)."""
    if not order or order.get("by") != "patrick":
        return None
    status = order.get("status")
    eta = datetime.fromisoformat(order["eta_at"])
    view = {"what": order["what"], "restaurant": order["restaurant"], "price": order["price"],
            "note": order.get("note") or "", "status": status}
    if status == "a_caminho":
        view["detalhe"] = f"A caminho · chega por volta das {eta:%H:%M}"
    elif status == "portaria":
        why = {"dormindo": "ela tá dormindo", "banho": "ela tá no banho"}.get(order.get("waited"), "ela não tá em casa")
        view["detalhe"] = f"Chegou às {eta:%H:%M} · ficou na portaria com o Seu Jorge ({why})"
    else:
        got = datetime.fromisoformat(order["received_at"]) if order.get("received_at") else eta
        if now - got > timedelta(hours=3):
            return None
        view["detalhe"] = f"Entregue às {got:%H:%M}"
    return view


def _today_events(db, now: datetime, limit: int = 14) -> list[dict]:
    start = datetime.combine(now.date(), datetime.min.time()).isoformat()
    with db.get_connection() as conn:
        rows = conn.execute(
            """SELECT event_at, event_type, title, summary FROM life_events
               WHERE event_at>=? AND event_at<=? ORDER BY event_at DESC LIMIT ?""",
            (start, now.isoformat(), limit)).fetchall()
    return [{"at": datetime.fromisoformat(r["event_at"]).strftime("%H:%M"), "tipo": r["event_type"],
             "texto": (r["summary"] or r["title"] or "").strip()} for r in reversed(rows)]


# ---------------------------------------------------------------------- rotas --
async def api_inicio(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    now = hooks.now()
    snap = await asyncio.to_thread(hooks.status, now)
    import delivery
    import pedido_dela
    return _json({"agora": {k: snap.get(k) for k in ("now", "atividade", "local", "disponivel")},
                  "pedido": order_view(delivery._load(hooks.db), now),
                  "pra_voce": pedido_dela.app_view(hooks.db, now)})


async def api_bastidores(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    now = hooks.now()

    def collect():
        from emotion import EmotionEngine
        from social_day import SocialDay
        out = {"status": hooks.status(now), "emocao": EmotionEngine(hooks.db).panel(now),
               "hoje": _today_events(hooks.db, now)}
        try:
            out["mundo"] = SocialDay(hooks.db).world_summary(now)
        except Exception:
            logger.exception("webapp.mundo.error")
            out["mundo"] = ""
        return out
    return _json(await asyncio.to_thread(collect))


async def api_banco(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    now = hooks.now()
    import financas

    def collect():
        financas.materialize(hooks.db, now)
        st = financas._load(hooks.db)
        devendo = sum(e["valor"] for e in st.get("emprestimos", []) if not e.get("devolvido_at"))
        return {"saldo": st.get("saldo", 0), "movs": list(reversed(st.get("movs", []))),
                "devendo": devendo, "pedido": st.get("pedido")}
    return _json(await asyncio.to_thread(collect))


async def api_pix(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    try:
        body = await request.json()
        valor = int(round(float(body.get("valor", 0))))
    except (ValueError, TypeError, json.JSONDecodeError):
        return _error("valor inválido", 400)
    if not 1 <= valor <= PIX_MAX:
        return _error(f"o pix vai de R$ 1 a R$ {PIX_MAX}", 400)
    nota = str(body.get("recado") or "").strip()[:200]
    res = await hooks.pix(valor, nota)
    return _json({"ok": True, **res})


async def api_delivery(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    import delivery
    return _json({"cardapio": load_cardapio(), "pedido": order_view(delivery._load(hooks.db), hooks.now())})


async def api_delivery_pedir(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    import delivery
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _error("pedido inválido", 400)
    rest, item = _find_item(load_cardapio(), str(body.get("restaurante", "")), str(body.get("item", "")))
    if not item:
        return _error("item não encontrado no cardápio", 400)
    now = hooks.now()
    order = delivery.gift(hooks.db, what=item["nome"], restaurant=rest["nome"], price=item["preco"],
                          eta_min=tuple(rest.get("eta", (30, 50))), note=str(body.get("bilhete") or ""),
                          now=now, eats=bool(item.get("come", True)))
    if not order:
        return _error("já tem um pedido pra ela que ainda não foi entregue", 409)
    return _json({"ok": True, "pedido": order_view(order, now)})


def make_app(hooks: Hooks) -> web.Application:
    app = web.Application(middlewares=[_auth], client_max_size=64 * 1024)
    app["hooks"] = hooks
    app.router.add_get("/", _index)
    app.router.add_get("/api/inicio", api_inicio)
    app.router.add_get("/api/bastidores", api_bastidores)
    app.router.add_get("/api/banco", api_banco)
    app.router.add_post("/api/pix", api_pix)
    app.router.add_get("/api/delivery", api_delivery)
    app.router.add_post("/api/delivery", api_delivery_pedir)
    app.router.add_static("/static/", STATIC_DIR, show_index=False)
    return app


async def start(hooks: Hooks, host: str = "127.0.0.1", port: int = 8787) -> web.AppRunner:
    runner = web.AppRunner(make_app(hooks), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    logger.info("webapp.started http://%s:%s", host, port)
    return runner
