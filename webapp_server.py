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
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import parse_qsl

from aiohttp import web

logger = logging.getLogger("WebApp")

STATIC_DIR = Path(__file__).parent / "webapp"
CARDAPIO_PATH = STATIC_DIR / "cardapio.json"      # o de antes: ainda usado pelos pedidos dela (pedido_dela)
CATALOGO_PATH = STATIC_DIR / "catalogo.json"     # 26/09: lojas reais (scripts/ifood_build.py)
TAXA_SERVICO = 0.99                               # como no iFood de verdade (print do Patrick)
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
    # comprovante no chat como mensagem DELE (answerWebAppQuery): (query_id, url da imagem) -> ok
    post_receipt: Optional[Callable[[str, str], Awaitable[bool]]] = None
    public_url: str = ""
    # 27/09 (Instagram): texto das amigas (sync, roda numa thread) e a resposta dele a um story (vira chat)
    ig_texto: Optional[Callable[[str], str]] = None
    ig_story_reply: Optional[Callable[[dict, str, Optional[str]], Awaitable[None]]] = None


# Comprovantes (opção B): a imagem fica aqui alguns minutos, num endereço impossível de adivinhar,
# só pro Telegram buscar quando posta a mensagem dele.
RECEIPT_TTL_S = 15 * 60
_RECEIPTS: dict[str, tuple[bytes, float]] = {}


def _store_receipt(jpeg: bytes) -> str:
    import secrets
    now = time.time()
    for token in [t for t, (_, exp) in _RECEIPTS.items() if exp < now]:
        _RECEIPTS.pop(token, None)
    token = secrets.token_urlsafe(24)
    _RECEIPTS[token] = (jpeg, now + RECEIPT_TTL_S)
    return token


async def _receipt_file(request: web.Request) -> web.StreamResponse:
    item = _RECEIPTS.get(request.match_info["token"])
    if not item or item[1] < time.time():
        raise web.HTTPNotFound()
    return web.Response(body=item[0], content_type="image/jpeg")


async def _post_receipt(request: web.Request, jpeg: bytes) -> bool:
    """Posta o comprovante no chat, em nome dele. Sem query_id (app aberto por fora) não dá."""
    hooks: Hooks = request.app["hooks"]
    query_id = request.get("query_id")
    if not query_id or not hooks.post_receipt or not hooks.public_url:
        return False
    url = f"{hooks.public_url.rstrip('/')}/recibo/{_store_receipt(jpeg)}.jpg"
    try:
        return await hooks.post_receipt(query_id, url)
    except Exception:
        logger.exception("webapp.receipt.error")
        return False


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
    raw = request.headers.get("X-Telegram-Init-Data", "")
    user = validate_init_data(raw, hooks.bot_token)
    if not user or int(user.get("id", 0)) != int(hooks.allowed_user_id):
        logger.warning("webapp.denied path=%s user=%s", request.path, (user or {}).get("id"))
        return _error("sem permissão", 403)
    request["query_id"] = dict(parse_qsl(raw)).get("query_id")
    return await handler(request)


# -------------------------------------------------------------------- estáticos --
async def _index(request: web.Request) -> web.StreamResponse:
    # O webview do Telegram guarda app.js/app.css em cache: a versão no link força o novo após um deploy.
    version = str(int(max((STATIC_DIR / f).stat().st_mtime for f in ("app.js", "app.css", "insta.js"))))
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8").replace("__V__", version)
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})


# --------------------------------------------------------------------- dados --
def load_cardapio() -> dict:
    return json.loads(CARDAPIO_PATH.read_text(encoding="utf-8"))


_CATALOGO: dict = {}


def load_catalogo() -> dict:
    """Catálogo das lojas reais; recarrega se o arquivo mudou (deploy sem reiniciar)."""
    mtime = CATALOGO_PATH.stat().st_mtime
    if _CATALOGO.get("mtime") != mtime:
        _CATALOGO.update(mtime=mtime, data=json.loads(CATALOGO_PATH.read_text(encoding="utf-8")))
    return _CATALOGO["data"]


def loja_aberta(loja: dict, now: datetime) -> bool:
    abre, fecha = loja.get("abre", 0), loja.get("fecha", 24)
    return abre <= now.hour < fecha


def loja_resumo(loja: dict, now: datetime) -> dict:
    """A linha da loja na lista do iFood (sem o cardápio)."""
    out = {k: loja[k] for k in ("id", "nome", "tipo", "categoria", "logo", "capa", "km", "eta", "taxa", "nota",
                                "avaliacoes", "minimo", "abre", "mais_pedido")}
    out["aberta"] = loja_aberta(loja, now)
    return out


def _find_item(cardapio: dict, rest_id: str, item_id: str):
    for rest in cardapio.get("restaurantes", []):
        if rest["id"] == rest_id:
            for item in rest["itens"]:
                if item["id"] == item_id:
                    return rest, item
    return None, None


def timeline(ordered: datetime, eta: datetime, now: datetime, *, delivered: bool,
             final_label: str = "Pedido entregue") -> tuple[list[dict], str]:
    """Etapas do iFood (decisão do Patrick, 25/09): confirmado → em preparo → saiu → entregue."""
    total = max(eta - ordered, timedelta(minutes=5))
    marks = [("Pedido confirmado", ordered), ("Em preparo", ordered + total * 0.1),
             ("Saiu para entrega", ordered + total * 0.6), (final_label, eta)]
    current = 3 if delivered else max(i for i, (_, at) in enumerate(marks[:3]) if at <= now or i == 0)
    steps = [{"label": label, "at": at.strftime("%H:%M") if i <= current else None,
              "done": i < current or (delivered and i == 3), "current": i == current}
             for i, (label, at) in enumerate(marks)]
    headline = f"{final_label} · {eta:%H:%M}" if delivered else f"Previsão de entrega: {eta:%H:%M}"
    return steps, headline


# 25/09 (Patrick): pedido entregue ficava 3 h na tela inicial. No iFood o "Pedido entregue"
# aparece e some; a Marina continua lembrando (prompt_lines) pelas 3 h dela.
SHOW_DELIVERED = timedelta(minutes=30)


def order_view(order: Optional[dict], now: datetime) -> Optional[dict]:
    """O pedido do Patrick como ele vê no app (o dela não aparece: é a vida dela)."""
    if not order or order.get("by") != "patrick":
        return None
    status = order.get("status")
    eta = datetime.fromisoformat(order["eta_at"])
    delivered = status in ("portaria", "recebido")
    if delivered and now - eta > SHOW_DELIVERED:
        return None
    # "Entregue na portaria" sem motivo: o iFood não sabe onde ela está (decisão do Patrick).
    final = "Entregue na portaria" if order.get("waited") else "Pedido entregue"
    steps, headline = timeline(datetime.fromisoformat(order["ordered_at"]), eta, now, delivered=delivered,
                               final_label=final)
    return {"what": order["what"], "restaurant": order["restaurant"], "price": order["price"],
            "note": order.get("note") or "", "status": status, "steps": steps, "headline": headline}


DIAS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def history_view(hist: list[dict], now: datetime) -> list[dict]:
    """Aba Pedidos do iFood (print real 26/09): dia, loja com logo, itens com foto e situação."""
    out = []
    for h in hist:
        eta = datetime.fromisoformat(h["eta_at"])
        at = datetime.fromisoformat(h["ordered_at"])
        itens = h.get("itens") or [{"id": None, "nome": h["what"], "qtd": 1, "foto": None}]
        out.append({"what": h["what"], "restaurant": h["restaurant"], "price": h["price"],
                    "when": at.strftime("%d/%m"), "dia": f"{DIAS[at.weekday()]}, {at:%d/%m/%Y}",
                    "loja_id": h.get("loja_id"), "logo": h.get("logo"), "itens": itens,
                    "concluido": eta <= now,
                    "status": "Pedido concluído" if eta <= now else "Em andamento"})
    return out


def gift_to_him_view(db, now: datetime) -> Optional[dict]:
    """"Presente da Ma": o pedido que ELA mandou pro Patrick, no mesmo formato do iFood."""
    import pedido_dela
    p = pedido_dela.current(db)
    if not p:
        return None
    eta = datetime.fromisoformat(p["eta_at"])
    if p["status"] == "entregue":
        return None          # 26/09 (Patrick): na tela inicial só até ser entregue
    steps, headline = timeline(datetime.fromisoformat(p["ordered_at"]), eta, now, delivered=False)
    return {"what": p["short"], "restaurant": p["restaurant"], "note": p.get("note") or "", "status": p["status"],
            "steps": steps, "headline": headline}


def _hoje(db, now: datetime) -> dict:
    """26/09 (Patrick): linha do tempo do dia inteiro, por período, com saídas e previsto (hoje.py)."""
    try:
        from hoje import hoje_view
        return hoje_view(db, now)
    except Exception:
        logger.exception("webapp.hoje.error")
        return {"periodos": []}


# ---------------------------------------------------------------------- rotas --
async def api_inicio(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    now = hooks.now()
    snap = await asyncio.to_thread(hooks.status, now)
    import delivery
    import pedido_dela
    # 26/09 (Patrick): o pedido dele não aparece na tela inicial, só no iFood (Pedidos).
    import instagram
    return _json({"agora": {k: snap.get(k) for k in ("now", "atividade", "local", "disponivel")},
                  "pra_voce": gift_to_him_view(hooks.db, now),
                  "insta_novo": instagram.feed_novo(hooks.db, now)})   # 27/09: bolinha no ícone


# --------------------------------------------- Bastidores: textos (Patrick, 26/09) --
# Voz híbrida: rótulos e dados falam como painel ("você"); sentimento fala do jeito dela.
# 26/09 (Patrick): o celular sempre como "Olha …"
TELEFONE = (("Dormindo", "Olha quando acordar"), ("Ocupada", "Olha nos intervalos"),
            ("Concentrada", "Olha nos intervalos"), ("Online", "Olha com frequência"))
CELULAR_POR_ATIVIDADE = {
    "SLEEPING": "Olha quando acordar", "SHOWER": "Olha depois do banho",
    "CLASS": "Olha nos intervalos", "WORK": "Olha nos intervalos", "CASTING": "Olha nos intervalos",
    "GYM": "Olha nos intervalos",
    "MEAL": "Olha de vez em quando", "SOCIAL": "Olha de vez em quando", "GETTING_READY": "Olha de vez em quando",
    "WAKING": "Olha de vez em quando", "PET_WALK": "Olha de vez em quando", "MICRO_WAKE": "Olha de vez em quando",
    "COMMUTE": "Olha com frequência", "HOME_RELAXING": "Olha com frequência", "UNKNOWN": "Olha com frequência",
    "HOME_BUSY": "Olha de vez em quando", "SOLO": "Olha depois", "OUT_SOLO": "Olha com frequência",
    "MANICURE": "Olha de vez em quando"}
FASES = {"fase menstrual": "Menstruada", "fase folicular": "Fase folicular",       # nomes do cycle.py, em minúscula
         "fase ovulatória / período fértil": "Período fértil", "fase lútea inicial": "Fase lútea",
         "fase pré-menstrual / tpm": "TPM"}
# preposição de cada sentimento quando é por alguém: "com saudade DELE", "grata A ELE", "chateada COM ele"
DE_ALGUEM = {"com saudade", "orgulhosa", "admirada", "com vergonha"}
A_ALGUEM = {"grata"}
SEM_ALGUEM = {"com culpa"}          # o motivo embaixo já diz com quem


def _hora(at: datetime) -> str:
    return f"{at.hour}h{at.minute:02d}" if at.minute else f"{at.hour}h"


def _quando_txt(txt: str) -> str:
    """'hoje 14:00' (do /status) → 'hoje 14h'."""
    try:
        dia, hm = txt.rsplit(" ", 1)
        h, m = hm.split(":")
        return f"{dia} {int(h)}h{m}" if m != "00" else f"{dia} {int(h)}h"
    except ValueError:
        return txt


def status_view(snap: dict) -> dict:
    local = (snap.get("local") or "").replace(" (fictícia)", "")
    if local.startswith("Apartamento da Marina"):
        local = "Em casa" + local[len("Apartamento da Marina"):].replace(" (", " · ").rstrip(")")
    else:
        local = local.replace(" (", " · ").rstrip(")")
    disp = snap.get("disponivel") or ""
    celular = CELULAR_POR_ATIVIDADE.get(snap.get("act_code") or "") or next(
        (txt for key, txt in TELEFONE if disp.startswith(key)), disp)
    fase = snap.get("ciclo_fase") or ""
    return {"atividade": cap(snap.get("atividade") or ""), "local": local, "celular": celular,
            "dormindo": disp.startswith("Dormindo"),
            "ciclo": f"Dia {snap['ciclo_dia']} · {FASES.get(fase, cap(fase))}" if snap.get("ciclo_dia") else "",
            "saude": [f"{cap(l)} · {r}" for l, r in snap.get("saude") or []],
            "proximo": f"{cap(snap['proximo'][0])}, {_quando_txt(snap['proximo'][1])}" if snap.get("proximo") else "",
            "planos": [f"{cap(p)}, {_quando_txt(w)}" for p, w in snap.get("planos") or []]}


def cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _alguem(target: str, word: str) -> str:
    """'o Patrick' vira ele; os outros ficam com o nome curto ('a Bia')."""
    if not target or word in SEM_ALGUEM:
        return ""
    if target == "o Patrick":
        return "dele" if word in DE_ALGUEM else "a ele" if word in A_ALGUEM else "com ele"
    art, _, resto = target.partition(" ")
    if word in DE_ALGUEM:
        return f"d{art} {resto}"                                  # "da Bia", "do Theo"
    if word in A_ALGUEM:
        return f"à {resto}" if art == "a" else f"ao {resto}"
    return f"com {target}"


# os eventos do mundo são gravados em 3ª pessoa ("O Patrick fez um pix pra ela"); na tela vira a voz certa
_PATRICK_RE = re.compile(r"\b[Oo] Patrick\b")


def voz_painel(txt: str) -> str:
    """Painel falando com você: 'O Patrick fez um pix pra ela' → 'Você fez um Pix pra ela'."""
    txt = re.sub(r"\b([oa])s? (\w+) do Patrick\b", lambda m: f"{m.group(1)} {'seu' if m.group(1) == 'o' else 'sua'} {m.group(2)}", txt or "")
    txt = re.sub(r"\bdo Patrick\b", "de você", txt)
    txt = re.sub(r"\bno Patrick\b", "em você", txt)
    txt = re.sub(r"\b(?:pro|para o) Patrick\b", "pra você", txt)
    txt = _PATRICK_RE.sub("você", txt)
    txt = re.sub(r"\bPatrick\b", "você", txt)                   # "(Patrick ficou de enviar…)"
    return cap(txt.replace("pix", "Pix"))


def voz_dela(txt: str) -> str:
    """Motivo do sentimento do jeito dela: 'O Patrick fez um pix pra ela' → 'Ele fez um Pix pra mim';
    'ele te elogiou' → 'ele me elogiou'."""
    txt = _PATRICK_RE.sub("ele", txt or "")
    for a, b in ((r"\bdo Patrick\b", "dele"), (r"\bpra ela\b", "pra mim"), (r"\bcom ela\b", "comigo"),
                 (r"\bte\b", "me"), (r"\bde você\b", "de mim"), (r"\bcom você\b", "comigo"), (r"^você\b", "eu")):
        txt = re.sub(a, b, txt)
    return cap(txt.replace("pix", "Pix"))


def _horas(h: float) -> str:
    h_int, m = int(h), int(round((h - int(h)) * 60))
    if m == 60:
        h_int, m = h_int + 1, 0
    return f"{h_int}h{m:02d}" if m else f"{h_int}h"


def emocao_view(e: dict, dormindo: bool) -> dict:
    """Painel de emoção em texto de gente: linhas rotuladas em vez de 'dormiu 8,7 h · TPM'."""
    body = [dict(b) for b in e["body"]]
    if dormindo:
        body[0]["word"] = "dormindo"                 # 'exausta' dormindo era pressão de sono, não ela mal
    linhas = []
    if dormindo:
        linhas.append(["moon", "Sono", "dormindo agora"])
    elif e.get("hours_slept") is not None:
        acordou = e.get("awake_since")
        linhas.append(["moon", "Sono", f"dormiu {_horas(e['hours_slept'])}"
                       + (f" · acordou às {_hora(datetime.fromisoformat(str(acordou)))}" if acordou else "")])
    if e.get("hours_since_release") is not None:
        h = e["hours_since_release"]
        linhas.append(["heartbeat", "Último orgasmo", f"há {round(h)} h" if h < 48 else f"há {round(h / 24)} dias"])
    if e.get("discomfort_why"):
        linhas.append(["bandage", "Desconforto", cap(e["discomfort_why"])])
    sentindo = [{"texto": cap(" ".join(x for x in (f["word"], _alguem(f["target"], f["word"])) if x)),
                 "motivo": voz_dela(f["cause"]), "valor": f["value"], "vezes": f["count"], "ate_resolver": f["until_resolved"]}
                for f in e["feelings"]]
    return {"body": body, "no_clima": e.get("in_the_mood", False), "linhas": linhas, "humor": cap(e["mood"]),
            "humor_barras": e["mood_bars"], "sentindo": sentindo, "voces": e["bond"]}


MOVS = ((re.compile(r"^pix do Patrick(?:: (.+))?$"), lambda m: "Seu Pix" + (f" · {m.group(1)}" if m.group(1) else "")),
        (re.compile(r"^presente do Patrick: (.+?)(?: \(ele disse: .*\))?$"), lambda m: f"Seu presente: {m.group(1)}"),
        (re.compile(r"^delivery pro Patrick: (.+)$"), lambda m: f"Delivery pra você: {m.group(1)}"),
        (re.compile(r"^devolveu o empréstimo do Patrick$"), lambda m: "Devolveu seu empréstimo"),
        (re.compile(r"^contas dela \((.+)\)$"), lambda m: cap(m.group(1))))


def mov_desc(desc: str) -> str:
    """Extrato em voz de painel: 'pix do Patrick: pro açaí' → 'Seu Pix · pro açaí'."""
    for rx, fmt in MOVS:
        m = rx.match(desc or "")
        if m:
            return fmt(m)
    return cap(desc or "")


async def api_bastidores(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    now = hooks.now()

    def collect():
        from emotion import EmotionEngine
        from social_day import SocialDay
        status = status_view(hooks.status(now))
        try:
            from agenda import Agenda
            ag = Agenda(hooks.db)
            status["card"] = ag.card(now) or ag.card_casa(now, status["celular"])   # 26/09: layout D
        except Exception:
            logger.exception("webapp.agenda.error")
            status["card"] = None
        out = {"status": status, "emocao": emocao_view(EmotionEngine(hooks.db).panel(now), status["dormindo"]),
               "hoje": _hoje(hooks.db, now)}
        try:
            from unhas import Unhas                  # 26/09: unhas como status (seção própria no Por dentro)
            out["unhas"] = Unhas(hooks.db).painel(now)
        except Exception:
            logger.exception("webapp.unhas.error")
            out["unhas"] = None
        try:
            from cabelo import Cabelo                # 26/09: cabelo como status (seção própria no Por dentro)
            out["cabelo"] = Cabelo(hooks.db).painel(now)
        except Exception:
            logger.exception("webapp.cabelo.error")
            out["cabelo"] = None
        try:
            out["mundo"] = SocialDay(hooks.db).world_panel(now)
        except Exception:
            logger.exception("webapp.mundo.error")
            out["mundo"] = {"pessoas": [], "lugares": [], "rolando": [], "planos": []}
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
        movs = [{**m, "desc": mov_desc(m.get("desc", ""))} for m in reversed(st.get("movs", []))]
        return {"saldo": st.get("saldo", 0), "movs": movs,
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
        return _error(f"Digite um valor entre R$ 1 e R$ {PIX_MAX}", 400)
    nota = str(body.get("recado") or "").strip()[:200]
    res = await hooks.pix(valor, nota)
    import recibo
    jpeg = await asyncio.to_thread(recibo.pix, valor, nota, hooks.now())
    return _json({"ok": True, **res, "comprovante": await _post_receipt(request, jpeg)})


async def api_delivery(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    import delivery
    now = hooks.now()
    return _json({"cardapio": load_cardapio(), "pedido": order_view(delivery._load(hooks.db), now),
                  "pedidos": history_view(delivery.history(hooks.db), now)})


async def api_ifood(request: web.Request) -> web.Response:
    """iFood do Patrick: lojas de Botafogo (entrega na Casa da Ma), pedido em andamento e histórico."""
    hooks: Hooks = request.app["hooks"]
    import delivery
    now = hooks.now()
    lojas = [loja_resumo(l, now) for l in load_catalogo()["lojas"] if l["area"] == "bf"]
    return _json({"lojas": lojas, "pedido": order_view(delivery._load(hooks.db), now),
                  "pedidos": history_view(delivery.history(hooks.db), now)})


async def api_ifood_loja(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    loja = next((l for l in load_catalogo()["lojas"] if l["id"] == request.match_info["id"] and l["area"] == "bf"), None)
    if not loja:
        return _error("loja não encontrada", 404)
    return _json(dict(loja, aberta=loja_aberta(loja, hooks.now())))


def _sacola(loja: dict, itens: list) -> tuple[list[dict], float]:
    """Itens da sacola conferidos com o catálogo: [(item, qtd, obs)], subtotal."""
    por_id = {i["id"]: i for s in loja["secoes"] for i in s["itens"]}
    linhas, subtotal = [], 0.0
    for it in itens[:30]:
        item = por_id.get(str(it.get("id", "")))
        qtd = int(it.get("qtd") or 0)
        if not item or not 1 <= qtd <= 20:
            raise ValueError("item inválido")
        linhas.append({"item": item, "qtd": qtd, "obs": str(it.get("obs") or "").strip()[:140]})
        subtotal += item["preco"] * qtd
    if not linhas:
        raise ValueError("sacola vazia")
    return linhas, round(subtotal, 2)


async def _pedir_sacola(request: web.Request, hooks: "Hooks", body: dict) -> web.Response:
    """26/09: pedido do iFood novo (loja real, sacola com vários itens)."""
    import delivery
    import recibo
    now = hooks.now()
    loja = next((l for l in load_catalogo()["lojas"] if l["id"] == str(body.get("loja")) and l["area"] == "bf"), None)
    if not loja:
        return _error("loja não encontrada", 400)
    try:
        linhas, subtotal = _sacola(loja, body.get("itens") or [])
    except (ValueError, TypeError):
        return _error("item não encontrado no cardápio", 400)
    if not loja_aberta(loja, now):
        return _error(f"Loja fechada • Abre às {loja['abre']:02d}:00", 409)
    if subtotal < loja["minimo"]:
        return _error(f"O pedido mínimo dessa loja é {_brl(loja['minimo'])}", 409)
    total = round(subtotal + loja["taxa"] + TAXA_SERVICO, 2)
    nomes = [f"{l['qtd']}x {l['item']['nome']}" if l["qtd"] > 1 else l["item"]["nome"] for l in linhas]
    what = nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]
    nota = " / ".join(l["obs"] for l in linhas if l["obs"])
    come = loja["tipo"] == "restaurante" and loja["categoria"] not in ("Doces", "Sorvetes")
    # a aba Pedidos mostra logo, itens e foto (e o "Adicione à sacola" repete a sacola)
    extra = {"loja_id": loja["id"], "logo": loja["logo"],
             "itens": [{"id": l["item"]["id"], "nome": l["item"]["nome"], "qtd": l["qtd"], "foto": l["item"]["foto"]}
                       for l in linhas]}
    order = delivery.gift(hooks.db, what=what, restaurant=loja["nome"], price=round(total), eta_min=tuple(loja["eta"]),
                          note=nota, now=now, eats=come, extra=extra)
    if not order:
        return _error("Você tem um pedido em andamento", 409)
    itens = [{"qtd": l["qtd"], "nome": l["item"]["nome"], "preco": l["item"]["preco"] * l["qtd"]} for l in linhas]
    jpeg = await asyncio.to_thread(recibo.pedido, itens, loja["nome"], total, datetime.fromisoformat(order["eta_at"]),
                                   nota, now, taxa=loja["taxa"], servico=TAXA_SERVICO,
                                   logo_loja=STATIC_DIR / loja["logo"])
    return _json({"ok": True, "pedido": order_view(order, now), "comprovante": await _post_receipt(request, jpeg)})


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def api_delivery_pedir(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    import delivery
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _error("pedido inválido", 400)
    if body.get("loja"):
        return await _pedir_sacola(request, hooks, body)
    rest, item = _find_item(load_cardapio(), str(body.get("restaurante", "")), str(body.get("item", "")))
    if not item:
        return _error("item não encontrado no cardápio", 400)
    now = hooks.now()
    order = delivery.gift(hooks.db, what=item["nome"], restaurant=rest["nome"], price=item["preco"],
                          eta_min=tuple(rest.get("eta", (30, 50))), note=str(body.get("bilhete") or ""),
                          now=now, eats=bool(item.get("come", True)))
    if not order:
        return _error("Você tem um pedido em andamento", 409)
    import recibo
    jpeg = await asyncio.to_thread(recibo.pedido, item["nome"], rest["nome"], item["preco"],
                                   datetime.fromisoformat(order["eta_at"]), order.get("note") or "", now)
    return _json({"ok": True, "pedido": order_view(order, now), "comprovante": await _post_receipt(request, jpeg)})


# ----------------------------------------------- Instagram (27/09, Etapa 5) --
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def ig_quando(at: datetime, now: datetime) -> str:
    """Como o Instagram mostra: agora, 5 min, 3 h, 2 d, 12 de set."""
    s = (now - at).total_seconds()
    if s < 60:
        return "agora"
    if s < 3600:
        return f"{int(s // 60)} min"
    if s < 86400:
        return f"{int(s // 3600)} h"
    if s < 7 * 86400:
        return f"{int(s // 86400)} d"
    return f"{at.day} de {MESES[at.month - 1]}"


def ig_autor(autor: str) -> dict:
    import instagram
    p = instagram.PERFIS.get(autor)
    if not p:
        return {"chave": autor, "handle": autor, "nome": "", "avatar": "", "iniciais": autor[:2].upper(), "perfil": False}
    av = p.get("avatar", "")
    if av.startswith("ig/"):
        av = f"/{av}" if instagram.caminho(av[3:]) else ""
    elif av:
        av = f"/{av}"
    nome = p["nome"]
    iniciais = "PR" if autor == "patrick" else "".join(w[0] for w in nome.split()[:2]).upper()
    return {"chave": autor, "handle": p["handle"], "nome": nome, "avatar": av, "perfil": autor != "patrick",
            "iniciais": iniciais}


def ig_post_view(db, p: dict, now: datetime) -> dict:
    import instagram
    coms = instagram.comentarios(db, p["id"], now)
    story = json.loads(p.get("story_json") or "null")
    return {"id": p["id"], "tipo": p["tipo"], "autor": ig_autor(p["autor"]),
            "imagem": f"/ig/{p['imagem']}" if p.get("imagem") else "", "story": story,
            "legenda": p["legenda"], "local": p["local"], "quando": ig_quando(datetime.fromisoformat(p["criado_em"]), now),
            "curtidas": instagram.curtidas(p, now), "curtiu": bool(p.get("curtido_patrick_em")),
            "marcados": [ig_autor(a) for a in json.loads(p["marcados_json"] or "[]")],
            "n_comentarios": len(coms), "visto": bool(p.get("visto_patrick_em")),
            "curtido_por": "masalles" if p["autor"] != "marina" and p.get("curtido_marina_em") else ""}


def ig_comentarios_view(db, pid: int, now: datetime) -> list[dict]:
    import instagram
    coms = instagram.comentarios(db, pid, now)
    raiz: dict[int, dict] = {}
    out = []
    for c in coms:
        v = {"id": c["id"], "autor": ig_autor(c["autor"]), "texto": c["texto"],
             "quando": ig_quando(datetime.fromisoformat(c["criado_em"]), now),
             "curtidas": (1 if c.get("curtido_marina_em") else 0) + (1 if c.get("curtido_patrick_em") else 0),
             "curtiu": bool(c.get("curtido_patrick_em")), "dela": bool(c.get("curtido_marina_em")),
             "seu": c["autor"] == "patrick", "respostas": []}
        pai = c.get("pai_id")
        while pai and pai not in raiz and any(x["id"] == pai for x in coms):   # resposta de resposta: fica na raiz
            pai = next(x["pai_id"] for x in coms if x["id"] == pai)
        if pai and pai in raiz:
            raiz[pai]["respostas"].append(v)
        else:
            raiz[c["id"]] = v
            out.append(v)
    return out


def ig_stories_view(db, now: datetime) -> list[dict]:
    import instagram
    grupos: dict[str, list] = {}
    for s in instagram.stories_ativos(db, now):
        grupos.setdefault(s["autor"], []).append(ig_post_view(db, s, now))
    ordem = ["marina", *instagram.AMIGAS]
    return [{"autor": ig_autor(a), "itens": grupos[a], "visto": all(x["visto"] for x in grupos[a])}
            for a in ordem if a in grupos]


async def api_ig(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    import instagram
    now = hooks.now()
    posts = instagram._rows(hooks.db, "SELECT * FROM ig_posts WHERE tipo='feed' AND criado_em<=? "
                                      "ORDER BY criado_em DESC LIMIT 40", (now.isoformat(),))
    instagram.patrick_abriu(hooks.db, now)
    return _json({"stories": ig_stories_view(hooks.db, now), "posts": [ig_post_view(hooks.db, p, now) for p in posts],
                  "atividade_nova": bool(ig_atividade(hooks.db, now, so_novas=True))})


async def api_ig_perfil(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    import instagram
    autor = request.match_info["autor"]
    perfil = instagram.PERFIS.get(autor)
    if not perfil or autor == "patrick":
        return _error("perfil não encontrado", 404)
    now = hooks.now()
    posts = instagram.posts_feed(hooks.db, autor, now)
    marcadas = [p for p in instagram._rows(hooks.db, "SELECT * FROM ig_posts WHERE tipo='feed' AND criado_em<=? "
                                                     "AND autor!=? ORDER BY criado_em DESC", (now.isoformat(), autor))
                if autor in json.loads(p["marcados_json"] or "[]")]
    return _json({"autor": ig_autor(autor), "bio": perfil["bio"], "seguidores": perfil["seguidores"],
                  "seguindo": perfil["seguindo"], "n_posts": len(posts),
                  "stories": [s for s in ig_stories_view(hooks.db, now) if s["autor"]["chave"] == autor],
                  "posts": [ig_post_view(hooks.db, p, now) for p in posts],
                  "marcadas": [ig_post_view(hooks.db, p, now) for p in marcadas]})


async def api_ig_post(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    import instagram
    now = hooks.now()
    p = instagram.post(hooks.db, int(request.match_info["id"]))
    if not p or datetime.fromisoformat(p["criado_em"]) > now:
        return _error("post não encontrado", 404)
    return _json({**ig_post_view(hooks.db, p, now), "comentarios": ig_comentarios_view(hooks.db, p["id"], now)})


async def api_ig_curtir(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    import instagram
    body = await request.json()
    on = bool(body.get("on"))
    if body.get("comentario"):
        instagram.curtir_comentario(hooks.db, int(body["comentario"]), hooks.now(), on)
    elif body.get("post"):
        instagram.curtir_post(hooks.db, int(body["post"]), hooks.now(), on)
    else:
        return _error("nada pra curtir", 400)
    return _json({"ok": True})


async def api_ig_comentar(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    import instagram
    body = await request.json()
    texto = str(body.get("texto") or "").strip()[:300]
    pid = int(body.get("post") or 0)
    p = instagram.post(hooks.db, pid)
    if not texto or not p:
        return _error("Escreva um comentário", 400)
    pai = int(body["pai"]) if body.get("pai") else None
    now = hooks.now()
    cid = instagram.comentar(hooks.db, pid, "patrick", texto, now, pai_id=pai)
    if hooks.ig_texto:
        asyncio.create_task(_ig_amiga_entra(hooks, pid, cid, texto, now))
    return _json({"ok": True, "id": cid})


async def _ig_amiga_entra(hooks: Hooks, pid: int, cid: int, texto: str, now: datetime) -> None:
    """Às vezes uma amiga responde o comentário dele (a marcada, ou a Bia), minutos ou horas depois."""
    import instagram
    import random
    from social_day import short_name
    try:
        amiga = instagram.resposta_de_amiga(hooks.db, pid, cid)
        if not amiga:
            return
        p = instagram.post(hooks.db, pid)
        resp = instagram._limpa(await asyncio.to_thread(
            hooks.ig_texto, f"No Instagram, num post da Marina ({instagram._foto_pros_outros(p)}; legenda "
            f"\"{p['legenda']}\"), o Patrick, namorado dela, comentou \"{texto}\". Quem responde: "
            f"{instagram.QUEM_ESCREVE[amiga]}. Escreva a resposta de {short_name(amiga)} a esse comentário, do jeito "
            "dela: curtinha (até 10 palavras), português informal, no máximo 1 emoji. Responda só com o comentário."
            + instagram._nao_repita(hooks.db, amiga)))
        if resp:
            at = now + timedelta(minutes=random.Random(f"ig:entra:quando:{cid}").randint(15, 180))
            instagram.comentar(hooks.db, pid, amiga, resp, at, pai_id=cid)
    except Exception:
        logger.exception("webapp.ig.amiga_entra")


async def api_ig_story(request: web.Request) -> web.Response:
    """Story: visto, coração ou resposta (a resposta vai pro chat como mensagem dele)."""
    hooks: Hooks = request.app["hooks"]
    import instagram
    body = await request.json()
    s = instagram.post(hooks.db, int(body.get("id") or 0))
    if not s or s["tipo"] != "story":
        return _error("story não encontrado", 404)
    now = hooks.now()
    acao = body.get("acao")
    if acao == "visto":
        instagram._exec(hooks.db, "UPDATE ig_posts SET visto_patrick_em=COALESCE(visto_patrick_em, ?) WHERE id=?",
                        (now.isoformat(), s["id"]))
    elif acao == "coracao":
        instagram.curtir_post(hooks.db, s["id"], now, bool(body.get("on", True)))
    elif acao == "responder":
        texto = str(body.get("texto") or "").strip()[:300]
        if not texto:
            return _error("Escreva uma mensagem", 400)
        if s["autor"] != "marina" or not hooks.ig_story_reply:
            return _error("Só dá pra responder os stories da Ma", 400)
        await hooks.ig_story_reply(s, texto, request.get("query_id"))
        return _json({"ok": True, "chat": bool(request.get("query_id"))})
    return _json({"ok": True})


def ig_atividade(db, now: datetime, *, so_novas: bool = False) -> list[dict]:
    """O coração: quem respondeu e quem curtiu os comentários dele."""
    import instagram
    viu = db.get_estado_relacional("ig_patrick_viu_atividade") or ""
    n = now.isoformat()
    out = []
    for c in instagram._rows(db, """SELECT r.*, c.texto AS dele FROM ig_comentarios r
                                    JOIN ig_comentarios c ON c.id=r.pai_id
                                    WHERE c.autor='patrick' AND r.autor!='patrick' AND r.criado_em<=?""", (n,)):
        out.append({"at": c["criado_em"], "autor": ig_autor(c["autor"]), "post": c["post_id"],
                    "texto": f"respondeu: {c['texto']}"})
    for c in instagram._rows(db, """SELECT * FROM ig_comentarios WHERE autor='patrick' AND curtido_marina_em<=?""", (n,)):
        out.append({"at": c["curtido_marina_em"], "autor": ig_autor("marina"), "post": c["post_id"],
                    "texto": f"curtiu seu comentário: {c['texto']}"})
    for p in instagram._rows(db, """SELECT * FROM ig_posts WHERE autor!='marina' AND tipo='feed' AND criado_em<=?
                                    AND marcados_json LIKE '%marina%'""", (n,)):
        out.append({"at": p["criado_em"], "autor": ig_autor(p["autor"]), "post": p["id"],
                    "texto": "marcou a masalles numa publicação"})
    out.sort(key=lambda x: x["at"], reverse=True)
    if so_novas:
        return [x for x in out if x["at"] > viu]
    return [{**x, "quando": ig_quando(datetime.fromisoformat(x["at"]), now), "nova": x["at"] > viu} for x in out[:40]]


async def api_ig_atividade(request: web.Request) -> web.Response:
    hooks: Hooks = request.app["hooks"]
    now = hooks.now()
    itens = ig_atividade(hooks.db, now)
    hooks.db.set_estado_relacional("ig_patrick_viu_atividade", now.isoformat())
    return _json({"itens": itens})


async def _ig_file(request: web.Request) -> web.StreamResponse:
    import instagram
    p = instagram.caminho(request.match_info["nome"])
    if not p:
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "public, max-age=604800"})


def make_app(hooks: Hooks) -> web.Application:
    app = web.Application(middlewares=[_auth], client_max_size=64 * 1024)
    app["hooks"] = hooks
    app.router.add_get("/", _index)
    app.router.add_get("/api/inicio", api_inicio)
    app.router.add_get("/api/bastidores", api_bastidores)
    app.router.add_get("/api/dinheiro", api_banco)        # o dinheiro DELA, nos bastidores
    app.router.add_post("/api/pix", api_pix)
    app.router.add_get("/recibo/{token}.jpg", _receipt_file)
    app.router.add_get("/api/delivery", api_delivery)
    app.router.add_get("/api/ifood", api_ifood)
    app.router.add_get("/api/ifood/loja/{id}", api_ifood_loja)
    app.router.add_post("/api/delivery", api_delivery_pedir)
    app.router.add_get("/api/ig", api_ig)                       # 27/09: Instagram da Ma
    app.router.add_get("/api/ig/perfil/{autor}", api_ig_perfil)
    app.router.add_get("/api/ig/post/{id}", api_ig_post)
    app.router.add_get("/api/ig/atividade", api_ig_atividade)
    app.router.add_post("/api/ig/curtir", api_ig_curtir)
    app.router.add_post("/api/ig/comentar", api_ig_comentar)
    app.router.add_post("/api/ig/story", api_ig_story)
    app.router.add_get("/ig/{nome}", _ig_file)                  # fotos: nome impossível de adivinhar
    app.router.add_static("/static/", STATIC_DIR, show_index=False)
    return app


async def start(hooks: Hooks, host: str = "127.0.0.1", port: int = 8787) -> web.AppRunner:
    runner = web.AppRunner(make_app(hooks), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    logger.info("webapp.started http://%s:%s", host, port)
    return runner
