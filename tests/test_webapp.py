"""Mini App da Marina (25/09): autenticação do Telegram, rotas, e o delivery surpresa no mundo dela."""
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import urlencode

from aiohttp.test_utils import TestClient, TestServer

import delivery
import financas
import webapp_server
from db import DatabaseManager

TOKEN = "123456:TESTE"
PATRICK = 753715685
T = datetime(2026, 9, 25, 19, 0)


def signed(user_id=PATRICK, token=TOKEN, auth_date=None, tamper=False):
    fields = {"auth_date": str(int(auth_date if auth_date is not None else time.time())),
              "query_id": "AAE", "user": json.dumps({"id": user_id, "first_name": "Patrick"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["user"] = json.dumps({"id": 1, "first_name": "Outro"})
    return urlencode(fields)


class InitDataTest(unittest.TestCase):
    def test_valida_assinatura_do_telegram(self):
        self.assertEqual(webapp_server.validate_init_data(signed(), TOKEN)["id"], PATRICK)

    def test_recusa_adulterado_expirado_e_token_errado(self):
        self.assertIsNone(webapp_server.validate_init_data(signed(tamper=True), TOKEN))
        self.assertIsNone(webapp_server.validate_init_data(signed(auth_date=time.time() - 2 * 86400), TOKEN))
        self.assertIsNone(webapp_server.validate_init_data(signed(token="999:OUTRO"), TOKEN))
        self.assertIsNone(webapp_server.validate_init_data("", TOKEN))
        self.assertIsNone(webapp_server.validate_init_data("user=%7B%7D&auth_date=1", TOKEN))


class DeliveryGiftTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "g.db")

    def tearDown(self):
        self.temp.cleanup()

    def _gift(self, note="pra aguentar a aula", eats=True):
        return delivery.gift(self.db, what="açaí de 500 ml", restaurant="Açaí da Praia", price=38,
                             eta_min=(30, 30), note=note, now=T, eats=eats)

    def _events(self):
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT event_key, event_type, summary FROM life_events")]

    def test_em_casa_recebe_na_hora_e_come_sem_cobrar_dela(self):
        self._gift()
        financas.materialize(self.db, T)
        saldo = financas._load(self.db)["saldo"]
        self.assertIsNone(delivery.gift_tick(self.db, T + timedelta(minutes=10), can_receive=True))
        self.assertEqual(delivery.gift_tick(self.db, T + timedelta(minutes=31), can_receive=True), "recebido")
        ev = self._events()
        self.assertTrue(any(e["event_key"].endswith(":presente") and e["event_type"] == "meal" for e in ev), ev)
        self.assertIn("pra aguentar a aula", ev[0]["summary"])
        financas.materialize(self.db, T + timedelta(minutes=40))
        self.assertEqual(financas._load(self.db)["saldo"], saldo, "quem pagou foi ele")
        self.assertIsNotNone(delivery.gift_to_announce(self.db))
        delivery.mark_announced(self.db)
        self.assertIsNone(delivery.gift_to_announce(self.db))

    def test_surpresa_nao_vaza_antes_de_receber(self):
        self._gift()
        self.assertEqual(delivery.prompt_lines(self.db, T + timedelta(minutes=5)), [])
        delivery.gift_tick(self.db, T + timedelta(minutes=31), can_receive=False, why_not="fora")
        self.assertEqual(delivery.prompt_lines(self.db, T + timedelta(minutes=40)), [], "na portaria ela ainda não sabe")
        delivery.gift_tick(self.db, T + timedelta(minutes=90), can_receive=True)
        lines = delivery.prompt_lines(self.db, T + timedelta(minutes=95))
        self.assertTrue(lines and "surpresa" in lines[0] and "pra aguentar a aula" in lines[0])

    def test_fora_fica_na_portaria_e_ela_pega_depois(self):
        self._gift()
        self.assertEqual(delivery.gift_tick(self.db, T + timedelta(minutes=31), can_receive=False, why_not="fora"),
                         "portaria")
        self.assertIsNone(delivery.gift_to_announce(self.db))
        self.assertIsNone(delivery.gift_tick(self.db, T + timedelta(minutes=60), can_receive=False))
        self.assertEqual(delivery.gift_tick(self.db, T + timedelta(minutes=120), can_receive=True), "recebido")
        g = delivery.gift_to_announce(self.db)
        self.assertEqual(g["waited"], "fora")
        self.assertIn("portaria", self._events()[0]["summary"])

    def test_comeu_ha_pouco_guarda_pra_depois(self):
        self._gift()
        delivery.gift_tick(self.db, T + timedelta(minutes=31), can_receive=True, ate_recently=True)
        ev = self._events()[0]
        self.assertEqual(ev["event_type"], "gift")
        self.assertIn("guardou pra depois", ev["summary"])

    def test_um_pedido_por_vez_e_o_dela_nao_atrapalha_o_proximo(self):
        self.assertIsNotNone(self._gift())
        self.assertIsNone(self._gift(), "já tem um a caminho")
        delivery.gift_tick(self.db, T + timedelta(minutes=31), can_receive=True)
        self.assertIsNotNone(delivery.gift(self.db, what="x", restaurant="y", price=10, eta_min=(20, 20),
                                           note="", now=T + timedelta(hours=2)))

    def test_materialize_dela_nao_mexe_no_presente(self):
        self._gift()
        self.assertFalse(delivery.materialize(self.db, T + timedelta(hours=2)))
        self.assertEqual(delivery._load(self.db)["status"], "a_caminho")

    def test_order_view(self):
        order = self._gift()
        view = webapp_server.order_view(order, T + timedelta(minutes=20))
        self.assertIn("Previsão de entrega", view["headline"])
        self.assertEqual([s["label"] for s in view["steps"]],
                         ["Pedido confirmado", "Em preparo", "Saiu para entrega", "Pedido entregue"])
        self.assertEqual([s["label"] for s in view["steps"] if s["current"]], ["Saiu para entrega"])
        delivery.gift_tick(self.db, T + timedelta(minutes=31), can_receive=False, why_not="dormindo")
        view = webapp_server.order_view(delivery._load(self.db), T + timedelta(minutes=40))
        self.assertTrue(view["headline"].startswith("Entregue na portaria"))
        self.assertNotIn("dormindo", json.dumps(view), "o iFood não sabe onde ela está")
        order = delivery._load(self.db)
        eta = datetime.fromisoformat(order["eta_at"])
        self.assertIsNotNone(webapp_server.order_view(order, eta + timedelta(minutes=25)))
        self.assertIsNone(webapp_server.order_view(order, eta + timedelta(minutes=35)),
                          "entregue some da tela inicial (25/09: ficava 3 h)")
        self.assertIsNone(webapp_server.order_view({"by": "marina"}, T), "o pedido dela não aparece")


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "a.db")
        self.pix = AsyncMock(return_value={"kind": "presente", "saldo": 690})
        self.receipt = AsyncMock(return_value=True)
        status = lambda now: {"now": now, "atividade": "tempo livre em casa", "local": "Apê (Botafogo)",
                              "disponivel": "Online"}
        hooks = webapp_server.Hooks(db=self.db, bot_token=TOKEN, allowed_user_id=PATRICK, status=status,
                                    pix=self.pix, now=lambda: T, post_receipt=self.receipt,
                                    public_url="https://marina.test")
        self.client = TestClient(TestServer(webapp_server.make_app(hooks)))
        await self.client.start_server()
        self.h = {"X-Telegram-Init-Data": signed()}

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def test_sem_initdata_ou_outro_usuario_da_403(self):
        self.assertEqual((await self.client.get("/api/dinheiro")).status, 403)
        other = {"X-Telegram-Init-Data": signed(user_id=42)}
        self.assertEqual((await self.client.get("/api/dinheiro", headers=other)).status, 403)

    async def test_index_abre_sem_login(self):
        r = await self.client.get("/")
        self.assertEqual(r.status, 200)
        self.assertIn("telegram-web-app.js", await r.text())

    async def test_dinheiro_dela_e_pix_com_comprovante(self):
        r = await self.client.get("/api/dinheiro", headers=self.h)
        self.assertEqual((await r.json())["saldo"], financas.START_BALANCE)
        bad = await self.client.post("/api/pix", headers=self.h, json={"valor": 0})
        self.assertEqual(bad.status, 400)
        ok = await self.client.post("/api/pix", headers=self.h, json={"valor": "50", "recado": "pro açaí"})
        self.assertEqual(ok.status, 200)
        self.pix.assert_awaited_once_with(50, "pro açaí")
        self.assertTrue((await ok.json())["comprovante"])
        query_id, url = self.receipt.await_args.args
        self.assertEqual(query_id, "AAE", "o comprovante sai em nome dele, pela sessão do app")
        img = await self.client.get(url.replace("https://marina.test", ""))
        self.assertEqual(img.status, 200)
        self.assertEqual(img.headers["Content-Type"], "image/jpeg")
        self.assertEqual((await self.client.get("/recibo/inventado.jpg")).status, 404)

    async def test_ifood_lojas_reais_e_sacola(self):
        """26/09: lojas reais de Botafogo, sacola com vários itens, mínimo e taxa de serviço."""
        d = await (await self.client.get("/api/ifood", headers=self.h)).json()
        self.assertGreater(len(d["lojas"]), 30)
        self.assertNotIn("mcdonalds-cg", {l["id"] for l in d["lojas"]}, "Campo Grande é pro presente dela")
        loja = await (await self.client.get("/api/ifood/loja/starbucks-bf", headers=self.h)).json()
        latte = next(i for s in loja["secoes"] for i in s["itens"] if i["nome"] == "Latte Grande")
        self.assertTrue(latte["foto"])
        pouco = {"loja": "starbucks-bf", "itens": [{"id": "pao-de-queijo", "qtd": 1}]}
        r = await self.client.post("/api/delivery", headers=self.h, json=pouco)
        self.assertEqual(r.status, 409, "abaixo do pedido mínimo")
        pedido = {"loja": "starbucks-bf", "itens": [{"id": latte["id"], "qtd": 2, "obs": "pra minha gatinha"},
                                                    {"id": "pao-de-queijo", "qtd": 1}]}
        r = await self.client.post("/api/delivery", headers=self.h, json=pedido)
        self.assertEqual(r.status, 200)
        order = delivery._load(self.db)
        self.assertEqual(order["what"], "2x Latte Grande e Pão de queijo")
        self.assertEqual(order["note"], "pra minha gatinha")
        self.assertEqual(self.receipt.await_count, 1)
        self.assertEqual((await self.client.get("/api/ifood/loja/mcdonalds-cg", headers=self.h)).status, 404)
        # 26/09 (print da aba Pedidos): o histórico traz logo, itens com foto e o dia por extenso
        h = (await (await self.client.get("/api/ifood", headers=self.h)).json())["pedidos"][0]
        self.assertEqual(h["loja_id"], "starbucks-bf")
        self.assertTrue(h["logo"])
        self.assertEqual([(i["nome"], i["qtd"]) for i in h["itens"]], [("Latte Grande", 2), ("Pão de queijo", 1)])
        self.assertTrue(all(i["foto"] for i in h["itens"]))
        self.assertRegex(h["dia"], r"^(Seg|Ter|Qua|Qui|Sex|Sáb|Dom), \d\d/\d\d/\d{4}$")

    def test_loja_fechada(self):
        loja = {"abre": 11, "fecha": 23}
        self.assertFalse(webapp_server.loja_aberta(loja, datetime(2026, 9, 26, 7, 30)))
        self.assertTrue(webapp_server.loja_aberta(loja, datetime(2026, 9, 26, 12, 0)))

    async def test_delivery_pede_e_nao_deixa_pedir_em_dobro(self):
        d = await (await self.client.get("/api/delivery", headers=self.h)).json()
        rest = d["cardapio"]["restaurantes"][0]
        body = {"restaurante": rest["id"], "item": rest["itens"][0]["id"], "bilhete": "surpresa"}
        self.assertEqual((await self.client.post("/api/delivery", headers=self.h, json=body)).status, 200)
        dobro = await self.client.post("/api/delivery", headers=self.h, json=body)
        self.assertEqual(dobro.status, 409)
        self.assertEqual((await dobro.json())["erro"], "Você tem um pedido em andamento")
        self.assertEqual(self.receipt.await_count, 1, "comprovante do pedido")
        self.assertEqual((await self.client.post("/api/delivery", headers=self.h,
                                                 json={"restaurante": "x", "item": "y"})).status, 400)
        inicio = await (await self.client.get("/api/inicio", headers=self.h)).json()
        self.assertNotIn("pedido", inicio, "26/09: pedido dele só no iFood")
        d = await (await self.client.get("/api/delivery", headers=self.h)).json()
        self.assertEqual(d["pedido"]["status"], "a_caminho")
        self.assertEqual([(p["restaurant"], p["status"]) for p in d["pedidos"]], [(rest["nome"], "Em andamento")])

    async def test_bastidores_traz_as_barrinhas(self):
        d = await (await self.client.get("/api/bastidores", headers=self.h)).json()
        self.assertEqual([b["label"] for b in d["emocao"]["body"]], ["Energia", "Fome", "Tesão"])
        self.assertTrue(all(0 <= b["value"] <= 1 for b in d["emocao"]["voces"]))
        self.assertEqual(d["status"]["celular"], "Responde rápido")
        self.assertIn("pessoas", d["mundo"])


class ComprovanteTest(unittest.TestCase):
    def test_imagens_sao_jpeg(self):
        import recibo
        for data in (recibo.pix(50, "pro açaí", T), recibo.pedido("Açaí 500 ml", "Açaí da Praia", 38, T, "", T)):
            self.assertTrue(data.startswith(b"\xff\xd8"), "JPEG (o Telegram exige pra foto via inline)")
            self.assertGreater(len(data), 5000)

    def test_pedido_em_colunas_com_taxas(self):
        """26/09: itens com quantidade, nome e preço em colunas; subtotal e taxas alinhados à direita."""
        import recibo
        itens = [{"qtd": 2, "nome": "Croissant de presunto e queijo com requeijão cremoso extra", "preco": 31.8},
                 {"qtd": 1, "nome": "Latte Grande", "preco": 21.9}]
        logo = Path(webapp_server.STATIC_DIR) / "lojas" / "starbucks-bf.png"
        data = recibo.pedido(itens, "Starbucks", 54.69, T, "", T, taxa=0, servico=0.99,
                             logo_loja=logo if logo.exists() else None)
        self.assertTrue(data.startswith(b"\xff\xd8"))
        self.assertEqual(recibo._wrap("a b c", recibo._font(26), 10_000), ["a b c"])

    def test_marina_ignora_o_comprovante_via_bot(self):
        import asyncio
        from types import SimpleNamespace
        from telegram.ext import ApplicationHandlerStop
        import bot
        ctx = SimpleNamespace(bot=SimpleNamespace(id=999))
        via = SimpleNamespace(effective_message=SimpleNamespace(via_bot=SimpleNamespace(id=999)))
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(bot._ignore_own_via_bot(via, ctx))
        normal = SimpleNamespace(effective_message=SimpleNamespace(via_bot=None))
        self.assertIsNone(asyncio.run(bot._ignore_own_via_bot(normal, ctx)), "mensagem normal segue pra ela")


class CardapioTest(unittest.TestCase):
    def test_cardapio_bem_formado(self):
        c = webapp_server.load_cardapio()
        ids = set()
        for r in c["restaurantes"]:
            self.assertEqual(len(r["eta"]), 2)
            for i in r["itens"]:
                self.assertGreater(i["preco"], 0)
                self.assertNotIn((r["id"], i["id"]), ids)
                ids.add((r["id"], i["id"]))


if __name__ == "__main__":
    unittest.main()
