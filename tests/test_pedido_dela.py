"""25/09: o delivery que a Marina manda PRO Patrick ("vou te mandar um suquinho pelo app")."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import delivery
import financas
import pedido_dela
import webapp_server
from db import DatabaseManager

T = datetime(2026, 9, 25, 12, 17)
CARDAPIO = webapp_server.load_cardapio()


class OfertaTest(unittest.TestCase):
    def test_ofertas_de_verdade(self):
        for line in ("Vou te mandar um suquinho pelo app pra vc não precisar levantar",
                     "Já pedi um açaí pra você, chega daqui a pouco",
                     "te mandei uma canja pelo iFood, come tudo",
                     "Vou te pedir uma pizza hoje, aceita que dói menos"):
            self.assertTrue(pedido_dela.is_offer(line), line)

    def test_nao_e_oferta(self):
        for line in ("Depois eu te mando foto do açaí",                 # 24/09, fala real dela
                     "pedi pra você me buscar na PUC",
                     "Vou te mandar um beijo bem gostoso",
                     "Quer que eu te mande um suco pelo app?",          # pergunta, não pedido
                     "Posso te mandar uma canja?",
                     "vou pedir um açaí pra mim"):
            self.assertFalse(pedido_dela.is_offer(line), line)

    def test_item_pela_fala(self):
        self.assertEqual(pedido_dela.pick(CARDAPIO, "vou te mandar um suquinho")[1]["id"], "suco-laranja")
        self.assertEqual(pedido_dela.pick(CARDAPIO, "te mandei uma canja")[1]["id"], "canja")
        self.assertEqual(pedido_dela.pick(CARDAPIO, "te mandei uma coisinha", sick=True)[1]["id"], "canja")
        self.assertEqual(pedido_dela.pick(CARDAPIO, "te mandei uma coisinha")[1]["id"], "brigadeiros")


class PedidoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "p.db")
        p = patch.object(financas, "EMERGENCY_WEEKLY_CHANCE", 0.0)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_oferta_vira_pedido_do_dinheiro_dela_e_entrega(self):
        order = pedido_dela.observe_marina_line(
            self.db, CARDAPIO, "Vou te mandar um suquinho pelo app pra vc não precisar levantar", "", T)
        self.assertEqual(order["short"], "Suco de laranja")
        self.assertEqual(financas._load(self.db)["saldo"], financas.START_BALANCE - 14)
        self.assertIsNone(pedido_dela.observe_marina_line(self.db, CARDAPIO, "vou te mandar um açaí pelo app", "", T),
                          "um por vez")
        a_caminho = pedido_dela.prompt_lines(self.db, T + timedelta(minutes=5))[0]
        self.assertIn("Não ofereça de novo", a_caminho)
        self.assertIn("A caminho", pedido_dela.app_view(self.db, T)["detalhe"])
        self.assertIsNone(pedido_dela.tick(self.db, T + timedelta(minutes=10)))
        self.assertEqual(pedido_dela.tick(self.db, T + timedelta(hours=1)), "entregue")
        self.assertIn("não precisa perguntar se chegou", pedido_dela.prompt_lines(self.db, T + timedelta(hours=1))[0])
        self.assertIn("Entregue", pedido_dela.app_view(self.db, T + timedelta(hours=1))["detalhe"])
        self.assertEqual(pedido_dela.prompt_lines(self.db, T + timedelta(hours=5)), [])
        self.assertIsNone(pedido_dela.app_view(self.db, T + timedelta(hours=5)))

    def test_sem_saldo_nao_pede(self):
        st = financas._init({}, T)
        st["saldo"] = 10
        self.db.set_estado_relacional(financas.KEY, json.dumps(st))
        self.assertIsNone(pedido_dela.observe_marina_line(self.db, CARDAPIO, "vou te mandar uma pizza pelo app", "", T))

    def test_pedido_pra_ele_nao_vira_pedido_dela(self):
        self.assertFalse(delivery.observe(self.db, "Já pedi um açaí pra você, chega daqui a pouco", T))
        self.assertIsNone(delivery.open_order(self.db))

    def test_surpresa_decide_uma_vez_por_episodio(self):
        his = [(T - timedelta(minutes=30), "acordei dodói, amigdalite atacou")]
        self.assertEqual(pedido_dela.surprise_reason(his, T), "doente")
        self.assertIsNone(pedido_dela.surprise_reason([(T - timedelta(hours=6), "tô gripado")], T), "já passou")
        self.assertEqual(pedido_dela.surprise_reason([(T, "hoje foi um dia horrível")], T), "dia_ruim")
        with patch.object(pedido_dela, "SURPRISE_CHANCE", 1.0):
            at = pedido_dela.plan_surprise(self.db, "doente", T)
            self.assertGreater(at, T)
            self.assertEqual(pedido_dela.plan_surprise(self.db, "doente", T + timedelta(minutes=5)), at, "mesma decisão")
            pedido_dela.mark_surprise_done(self.db, "doente", T)
            self.assertIsNone(pedido_dela.plan_surprise(self.db, "doente", T + timedelta(minutes=50)))
        rest, item = pedido_dela.surprise_item(CARDAPIO, "doente", T)
        self.assertIn(item["id"], ("canja", "picoles", "suco-laranja"))


if __name__ == "__main__":
    unittest.main()
