"""Consumo no rolê (Patrick, 26/09): "ela saiu e parece não ter consumido nada, já que a conta
bancária dela não teve movimento — é aqui que a vida dela acontece"."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import consumo
import financas
from consumo import Consumo, plan
from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible

BAR = {"source_key": "outing:2026-09-25:0", "event_at": "2026-09-25T19:30:00", "end_at": "2026-09-25T22:30:00",
       "location_key": "quartinho_bar", "metadata_json": json.dumps({"friends": ["theo_martins", "julia_azevedo"]})}


class PlanTest(unittest.TestCase):
    def test_mesmo_role_mesmos_pedidos(self):
        self.assertEqual(plan(BAR), plan(BAR))

    def test_bar_tem_bebida_dentro_do_horario(self):
        itens = plan(BAR)
        self.assertTrue(any(i.nome in {n for n, _, _ in consumo.BAR["bebidas"]} for i in itens))
        inicio, fim = datetime(2026, 9, 25, 19, 30), datetime(2026, 9, 25, 22, 30)
        self.assertTrue(all(inicio < i.at < fim for i in itens))

    def test_porcao_dividida_pelos_tres(self):
        for n in range(40):
            itens = plan({**BAR, "source_key": f"outing:2026-09-25:{n}"})
            porcao = next((i for i in itens if i.dividido), None)
            if porcao:
                cheio = next(p for nome, _, p in consumo.BAR["petiscos"] if nome == porcao.nome)
                self.assertEqual(porcao.valor, -(-cheio // 3))
                return
        self.fail("nenhum rolê com porção dividida em 40")

    def test_starbucks_usa_o_cardapio_do_app(self):
        cafe = {**BAR, "source_key": "outing:2026-09-24:4", "event_at": "2026-09-24T15:30:00",
                "end_at": "2026-09-24T16:45:00", "location_key": "starbucks_shopping_gavea",
                "metadata_json": json.dumps({"friends": ["julia_azevedo"]})}
        precos = {"Caramel Macchiato Grande": 27, "Frappuccino de Caramelo Grande": 30, "Latte Grande": 22,
                  "Pão de queijo": 13, "Cookie com gotas de chocolate": 12}
        for i in plan(cafe):
            self.assertEqual(i.valor, precos[i.nome])

    def test_uber(self):
        self.assertEqual(consumo.uber_price(20), 32)
        self.assertEqual(consumo.uber_price(20, dividido=True), 16)


class MaterializeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "c.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.execute("""INSERT INTO eventos_pendentes (event_type, description, event_at, end_at, status, confirmed,
                            source_key, location_key, metadata_json, created_at)
                            VALUES ('social','Saindo com o Theo e a Júlia no Quartinho Bar',?,?,'pending',1,?,?,?,?)""",
                         (BAR["event_at"], BAR["end_at"], BAR["source_key"], BAR["location_key"], BAR["metadata_json"],
                          "2026-09-20T00:00:00"))
            conn.commit()
        financas._save(self.db, financas._init({}, datetime(2026, 9, 20)))
        p = patch("commute.Commute.legs_on", return_value=[])
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_pedidos_viram_acontecimento_e_saem_do_saldo(self):
        fim = datetime(2026, 9, 25, 23, 0)
        esperado = sum(i.valor for i in plan(BAR))
        Consumo(self.db).materialize(fim)
        Consumo(self.db).materialize(fim)                       # idempotente
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT title, summary FROM life_events WHERE event_type='consumo'").fetchall()
        self.assertEqual(len(rows), len(plan(BAR)))
        self.assertTrue(all("Quartinho Bar" in r["summary"] and "R$ " in r["summary"] for r in rows))
        financas.materialize(self.db, fim)
        st = financas._load(self.db)
        self.assertEqual(st["saldo"], financas.START_BALANCE - esperado)
        self.assertTrue(all(m["desc"].startswith("Quartinho Bar · ") for m in st["movs"]))

    def test_so_o_que_ja_aconteceu(self):
        primeiro = plan(BAR)[0]
        Consumo(self.db).materialize(primeiro.at - timedelta(minutes=1))
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM life_events WHERE event_type='consumo'").fetchone()[0], 0)

    def test_comida_no_bar_e_o_jantar(self):
        for n in range(40):
            key = f"outing:2026-09-25:{n}"
            itens = plan({**BAR, "source_key": key})
            if any(i.comida for i in itens):
                break
        with self.db.get_connection() as conn:
            conn.execute("UPDATE eventos_pendentes SET source_key=?", (key,))
            conn.commit()
        Consumo(self.db).materialize(datetime(2026, 9, 25, 23, 0))
        from meals import Meals
        self.assertTrue(Meals(self.db)._logged(datetime(2026, 9, 25).date(), "jantar"))

    def test_role_cancelado_nao_consome(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE eventos_pendentes SET status='cancelled'")
            conn.commit()
        self.assertEqual(Consumo(self.db).materialize(datetime(2026, 9, 25, 23, 0)), 0)


class TransporteTest(unittest.TestCase):
    def test_uber_cobra_onibus_nao(self):
        from commute import Leg
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "t.db")
        with db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        t = datetime(2026, 9, 25, 16, 0)
        legs = [Leg("commute:2026-09-25:puc:volta", t, t + timedelta(minutes=20), "uber", "volta", "da PUC", "Gávea"),
                Leg("commute:2026-09-25:puc:ida", t - timedelta(hours=4), t - timedelta(hours=3), "onibus", "ida",
                    "pra PUC", "Gávea")]
        with patch("commute.Commute.legs_on", side_effect=lambda day: legs if day == t.date() else []):
            Consumo(db).materialize(t + timedelta(hours=1))
        with db.get_connection() as conn:
            rows = conn.execute("SELECT summary FROM life_events WHERE event_type='transporte'").fetchall()
        self.assertEqual([r["summary"] for r in rows], ["Pagou o uber voltando da PUC pra casa (R$ 32)."])


if __name__ == "__main__":
    unittest.main()
