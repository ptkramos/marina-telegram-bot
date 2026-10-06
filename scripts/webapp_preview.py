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
    # 28/09 (infra): uma conexão por thread, como o bot — abrir uma por consulta deixava o Hoje de ~1 s em ~65 s
    db.enable_connection_reuse()

    def status(now: datetime) -> dict:
        # mesmo formato do bot._status_snapshot (valores de exemplo)
        return {"now": now.isoformat(), "atividade": "tempo livre em casa", "local": "Apartamento da Marina (Botafogo)",
                "disponivel": "Online, respondendo rápido", "ciclo_dia": 24, "ciclo_fase": "fase pré-menstrual / tpm",
                "saude": [], "proximo": ("aula de Projeto", "segunda 14:00"), "planos": [("bar com o Theo e a Júlia", "sábado 20:30")]}

    if banco:
        return await _serve(db, port, lambda now: status_real(db, now), fixo)
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


def status_real(db, now: datetime) -> dict:
    """28/09: com --db, o mesmo retrato do bot._status_snapshot lido da cópia (antes era o de exemplo, e a
    Por dentro mostrava 'cansada' com ela dormindo). Importar o bot abriria o banco local, então repete aqui."""
    from calendar_world import CalendarWorld
    from cycle import MenstrualCycleManager
    from health import Health
    from pending_response import ResponseAvailabilityPolicy
    from social_day import SocialDay
    from world_state import WorldStateManager

    def quando(at: datetime) -> str:
        dias = (at.date() - now.date()).days
        dia = "hoje" if dias == 0 else "amanhã" if dias == 1 else \
            ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")[at.weekday()]
        return f"{dia} {at:%H:%M}"

    st = WorldStateManager(db).resolve(now) or {}
    with db.get_connection() as conn:
        row = conn.execute("SELECT name FROM world_places WHERE id = ?", (st.get("location_place_id"),)).fetchone()
    local = " ".join(x for x in (row["name"] if row else "", f"({st['location_region']})" if st.get("location_region") else "") if x)
    policy = ResponseAvailabilityPolicy(db)
    act = policy._resolve_activity(now)[0]
    perfil = policy.profiles.get(act, {})
    disp = ("Dormindo" if act == "SLEEPING" else "Ocupada" if perfil.get("phone_access") == "LOW"
            else "Concentrada" if perfil.get("prefer") == "DEFER" else "Online")
    ciclo = MenstrualCycleManager(db.get_data_inicio_ciclo()).get_cycle_info()
    nxt = CalendarWorld(db).next(now, include_academic=True)
    return {"now": now.isoformat(), "atividade": (st.get("activity") or "").replace("_", " "), "local": local or "Rio de Janeiro",
            "disponivel": disp, "act_code": act, "ciclo_dia": ciclo["day"], "ciclo_len": ciclo.get("cycle_length"),
            "ciclo_fase": ciclo["name"].split(" (")[0].lower(),
            "saude": [(c.label, c.remedy) for c in Health(db).conditions(now)],
            "proximo": (nxt["activity"], quando(datetime.fromisoformat(nxt["start_at"]))) if nxt else None,
            "planos": [(p["description"], quando(datetime.fromisoformat(p["event_at"])))
                       for p in SocialDay(db).upcoming_outings(now, limit=2)]}


async def _serve(db, port: int, status, fixo) -> None:
    async def pix(valor: int, recado: str) -> dict:
        return {"ok": True}

    async def post_receipt(query_id: str, url: str) -> bool:
        print("comprovante:", url)
        return True

    async def story_reply(story: dict, texto: str, query_id) -> None:
        print("resposta ao story:", story["id"], texto)

    # 05/10 (Lovense, passo 3): igual ao bot — junta a rajada, pergunta ao `sentir` e guarda o turno que ela
    # receberia (/dev/lovense?acao=turnos); o relógio de 10 s roda num laço aqui.
    # Passo 4: onde ela está (tipo da disponibilidade) fica simulado — /dev/lovense?acao=onde&a=CLASS.
    lv_turnos: list = []
    lv_espera: dict = {"task": None, "eventos": []}
    lv_onde: dict = {"a": "HOME_RELAXING"}

    async def lovense_sentir(eventos: list) -> None:
        from lovense import Lovense
        turno = await asyncio.to_thread(Lovense(db).sentir, hooks.now(), eventos, lv_onde["a"])
        if turno:
            print("lovense.turno:", turno["texto"])
            lv_turnos.append({"em": hooks.now().strftime("%H:%M:%S"), **turno})

    async def lovense_eventos(eventos: list, now) -> None:
        if eventos:
            print("lovense:", now.strftime("%H:%M:%S"), eventos)
        lv_espera["eventos"] += eventos
        if lv_espera["task"] and not lv_espera["task"].done():
            lv_espera["task"].cancel()

        async def assentou():
            from lovense import JUNTAR
            try:
                await asyncio.sleep(JUNTAR.total_seconds())
            except asyncio.CancelledError:
                return
            lv_espera["task"] = None
            ev, lv_espera["eventos"] = lv_espera["eventos"], []
            await lovense_sentir(ev)
        lv_espera["task"] = asyncio.create_task(assentou())

    async def lovense_relogio(app) -> None:
        async def laco():
            from lovense import Lovense
            while True:
                await asyncio.sleep(10)
                lv = Lovense(db)
                if await asyncio.to_thread(lv.tem_pendente):
                    await asyncio.to_thread(lv.pendentes, hooks.now(), lv_onde["a"])
                if await asyncio.to_thread(lv.sessao_ativa):
                    await lovense_sentir(await asyncio.to_thread(lv.tick, hooks.now(), atividade=lv_onde["a"]))
        app["lv_relogio"] = asyncio.create_task(laco())

    relogio = {"t": fixo}                     # /dev/agora?t=2026-09-25T21:20 troca o horário sem reiniciar
    hooks = webapp_server.Hooks(db=db, bot_token=TOKEN, allowed_user_id=USER, status=status, pix=pix,
                                post_receipt=post_receipt, public_url=f"http://127.0.0.1:{port}",
                                now=lambda: relogio["t"] or datetime.now(),
                                ig_texto=lambda prompt: "kkkk tá de olho hein", ig_story_reply=story_reply,
                                lovense=lovense_eventos)
    original_make = webapp_server.make_app

    async def dev_agora(request):
        t = request.query.get("t", "")
        relogio["t"] = datetime.fromisoformat(t) if t else None
        info = {"agora": relogio["t"].isoformat() if relogio["t"] else "real"}
        if relogio["t"] and request.query.get("mundo"):
            # roda o mundo nesse horário (só na cópia do banco): o card em casa lê o retrato dele
            from world_state import WorldStateManager
            snap = await asyncio.to_thread(WorldStateManager(db).resolve, relogio["t"], force=True)
            info["atividade"] = snap.get("activity")
        return web.json_response(info)

    async def dev_lovense(request):
        """05/10 (Lovense, passo 2): o que ela faz, simulado — /dev/lovense?acao=colocar&b=lush,hush | palavra |
        pedir_parar | liberar | cortar | tirar | tick (anda o relógio da escada) | conversar | turnos (passo 3: o que
        ela recebeu como turno) | onde&a=CLASS (passo 4: onde ela está) | recepcao (como está recebendo) |
        responde&m=oi (quando ela responderia)."""
        from lovense import Lovense
        lv, now = Lovense(db), hooks.now()
        acao, bs = request.query.get("acao", ""), [b for b in request.query.get("b", "lush").split(",") if b]

        def onde():
            lv_onde["a"] = request.query.get("a", "HOME_RELAXING")
            return lv_onde

        def responde():
            from response_availability import ResponseAvailabilityPolicy
            pol = ResponseAvailabilityPolicy(db)
            atividade = lv_onde["a"]
            pol._resolve_activity = lambda _now: (atividade, "WORLD_STATE", None, "fresh", True)
            d = pol.evaluate(request.query.get("m", "oi amor"), now=now)
            return {"decisao": d.decision, "motivo": d.reason_code,
                    "em_s": round((d.selected_target_at - d.earliest_reply_at).total_seconds())}
        try:
            res = {"onde": onde, "recepcao": lambda: lv.recepcao(now, lv_onde["a"]), "responde": responde,
                   "colocar": lambda: lv.colocar(now, bs, lugar="quarto"),
                   "palavra": lambda: lv.combinar_palavra(now, request.query.get("p", "abacaxi")),
                   "pedir_parar": lambda: lv.pedir_parar(now), "liberar": lambda: lv.liberar(now),
                   "cortar": lambda: lv.cortar(now), "tirar": lambda: lv.tirar(now, bs),
                   "tick": lambda: lv.tick(now, atividade=lv_onde["a"]), "conversar": lambda: lv.conversar(now),
                   "turnos": lambda: lv_turnos,
                   # passo 5a: a fala dela (modelo barato de verdade), o bloco do prompt, se ela toparia agora
                   "fala": lambda: lv.observe_conversa(request.query.get("f", ""), request.query.get("m", ""), now,
                                                       atividade=lv_onde["a"]),
                   "pendentes": lambda: lv.pendentes(now, lv_onde["a"]),
                   "prompt": lambda: lv.prompt(now, lv_onde["a"], request.query.get("c", "")),
                   "disposicao": lambda: lv.disposicao(now, bs, lv_onde["a"]),
                   "descoberta": lambda: lv._descoberta(),
                   # passo 5b: ela propõe (vontade/proposta), a bolsa ao sair (rotina), sozinha, a amiga (q=bia_andrade)
                   "vontade": lambda: lv.vontade_de_propor(now, lv_onde["a"]),
                   "proposta": lambda: lv.proposta(now, lv_onde["a"]),
                   "rotina": lambda: lv.rotina(now, lv_onde["a"]),
                   "sozinha": lambda: lv.sozinha(now, bool(request.query.get("ele"))),
                   "amiga": lambda: lv.conversa_com_amiga(now, request.query.get("q", "bia_andrade"))}[acao]()
        except (KeyError, ValueError) as e:
            return web.json_response({"erro": str(e)}, status=400)
        return web.json_response({"res": res, "estado": lv.estado(now)}, dumps=lambda d: json.dumps(d, default=str))

    def make_app(h):
        app = original_make(h)
        app.router.add_get("/dev/agora", dev_agora)
        app.router.add_get("/dev/lovense", dev_lovense)
        app.on_startup.append(lovense_relogio)
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
