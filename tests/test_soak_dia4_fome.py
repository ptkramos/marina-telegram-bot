"""Soak, dia 4 (02/10, Patrick): "ela saiu, foi em dois lugares, comeu pra cacete e continuou com fome depois".
Estação do Açaí 14:56 (suco + Tigela Nutella) e Rei do Mate 15:18 (mate gelado + croissant). O mundo só contou o
mate (uma bebida) como lanche, sem saciedade: a Tigela caiu no "horário do almoço" já almoçado e o croissant era o
2º item do lanche. A fome às 17:30 estava em 0,66; com a comida contada, 0,14."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager


def at(h, m):
    return datetime(2026, 10, 2, h, m)


ACAI = {"source_key": "vontade:2026-10-02:1440", "event_at": at(14, 53).isoformat(), "end_at": at(15, 9).isoformat(),
        "location_key": "loja_estacao_acai",
        "metadata_json": json.dumps({"loja": "estacao-acai", "tipo": "acai", "origem": "vontade"})}
MATE = {"source_key": "vontade:2026-10-02:e1454", "event_at": at(15, 15).isoformat(), "end_at": at(16, 0).isoformat(),
        "location_key": "loja_rei_do_mate",
        "metadata_json": json.dumps({"loja": "rei-do-mate", "tipo": "cafe", "origem": "emenda"})}


class ComidaForaTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / "f.db")
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO life_events(event_key,event_at,end_at,event_type,title,summary,source_type,
                            autonomy_level,importance,participants_json,share_worthy,metadata_json,created_at)
                            VALUES ('meal:2026-10-02:almoco',?,?,'meal','almoço','Almoço em casa.','simulated',1,0.2,
                            '[]',0.2,?,?)""",
                         (at(13, 9).isoformat(), at(13, 18).isoformat(),
                          json.dumps({"fome_antes": 0.327, "comeu": 0.227, "porcao": 0.9, "larga": True,
                                      "excesso": 0.0, "minutos": 9}), at(13, 9).isoformat()))
            conn.commit()

    def _itens(self, outing):
        from consumo import plan
        return plan(outing)

    def test_bebida_nao_e_comida(self):
        from consumo import Item
        comida = {i.nome: i.comida for o in (ACAI, MATE) for i in self._itens(o)}
        self.assertTrue(comida, "os dois lugares pediram alguma coisa")
        for nome, eh in comida.items():
            self.assertEqual(eh, not any(b in nome.lower() for b in ("suco", "mate gelado", "água", "cappuccino")),
                             nome)

    def _registra(self, outing, item, n):
        from consumo import Consumo
        cs = Consumo(self.db)
        cs._record(outing, n, item, cs._place_name(outing["location_key"]), "", [], at(17, 40))

    def test_toda_comida_conta_e_a_fome_cai(self):
        from consumo import Item
        from meals import Meals
        antes = Meals(self.db).hunger(at(17, 30))
        tigela = Item(at(14, 57), "Tigela Nutella", "tigela nutella", 40, False, True)
        suco = Item(at(14, 56), "Suco de laranja 500 ml", "suco de laranja 500 ml", 14, False, False)
        mate = Item(at(15, 18), "Mate gelado com limão 500 ml", "mate gelado com limão 500 ml", 12, False, False)
        croissant = Item(at(15, 19), "Croissant de presunto e queijo", "croissant de presunto e queijo", 16, False, True)
        for outing, n, item in ((ACAI, 0, suco), (ACAI, 1, tigela), (MATE, 0, mate), (MATE, 1, croissant)):
            self._registra(outing, item, n)
        with self.db.get_connection() as conn:
            comeu = {r["event_key"]: (r["event_type"], json.loads(r["metadata_json"] or "{}"))
                     for r in conn.execute("SELECT event_key, event_type, metadata_json FROM life_events "
                                           "WHERE event_type IN ('meal','snack') AND event_key != 'meal:2026-10-02:almoco'")}
        self.assertEqual(set(comeu), {"lanche:2026-10-02:fora:vontade:2026-10-02:1440:1", "meal:2026-10-02:lanche:fora"})
        self.assertTrue(all("fome_antes" in meta for _, meta in comeu.values()), "comida fora com saciedade")
        depois = Meals(self.db).hunger(at(17, 30))
        self.assertGreater(antes, 0.5)
        self.assertLess(depois, 0.3)

    def test_hoje_nao_repete_o_que_ela_pediu(self):
        import inspect
        import hoje
        self.assertIn('":fora:" in ev["event_key"]', inspect.getsource(hoje))


if __name__ == "__main__":
    unittest.main()
