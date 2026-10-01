"""Lista de compras da semana (Patrick, 28/09 — item 3 do freio): "vou colocar barrinhas na lista da semana"
passa a existir no mundo, vai no prompt e no card do mercado, e é comprada de verdade na compra da semana."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from lista_compras import ListaCompras

SEG = datetime(2026, 9, 28, 8, 52)


class _LLM:
    def __init__(self, resposta: dict):
        self.resposta, self.chamadas = resposta, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.chamadas += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.resposta)))])


class ListaComprasTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "l.db")
        seed_world_bible(self.db)
        self.l = ListaCompras(self.db)

    def _barrinhas(self):
        llm = _LLM({"adicionar": [{"item": "Barrinhas de proteína", "quem": "patrick"}], "tirar": []})
        feito = self.l.observe("Boa, amor, vou colocar barrinhas na lista da semana kkk",
                               "Princesa, quando for fazer compra da semana\nCompra umas barrinhas", SEG, llm=llm)
        return feito, llm

    def test_conversa_de_08_52_entra_na_lista(self):
        feito, llm = self._barrinhas()
        self.assertEqual(feito["adicionou"], ["Barrinhas de proteína"])
        self.assertEqual([i["item"] for i in self.l.pendentes()], ["barrinhas de proteína"])
        self.assertEqual(self.l.pendentes()[0]["quem"], "patrick")
        self._barrinhas()
        self.assertEqual(len(self.l.pendentes()), 1, "não repete o mesmo item")

    def test_sem_assunto_de_lista_nao_chama_o_modelo(self):
        llm = _LLM({"adicionar": [{"item": "x", "quem": "marina"}]})
        self.assertIsNone(self.l.observe("Também te amo demais, seu bobo kkk", "Te amo demais", SEG, llm=llm))
        self.assertEqual(llm.chamadas, 0)

    def test_tirar_da_lista(self):
        self._barrinhas()
        llm = _LLM({"adicionar": [], "tirar": ["barrinhas"]})
        self.l.observe("ah, já tem barrinha aqui em casa, tirei da lista", "", SEG + timedelta(hours=1), llm=llm)
        self.assertEqual(self.l.pendentes(), [])

    def test_prompt_mostra_a_lista_e_a_proxima_compra(self):
        self._barrinhas()
        linhas = "\n".join(self.l.prompt_lines(SEG + timedelta(minutes=5)))
        self.assertIn("[LISTA DE COMPRAS DA SEMANA", linhas)
        self.assertIn("barrinhas de proteína (o Patrick pediu, segunda 08:52)", linhas)
        self.assertIn("Próxima compra da semana:", linhas)

    def _compra(self, at: datetime) -> dict:
        from vontade import Vontade
        cid = Vontade(self.db).mercado_semana(at, 50, at - timedelta(hours=2))
        self.assertIsNotNone(cid)
        return next(c for c in self.l._compras((at.date(),)) if c["id"] == cid)

    def test_compra_da_semana_compra_o_que_estava_na_lista(self):
        self._barrinhas()
        compra = self._compra(datetime(2026, 9, 29, 19, 0))
        carrinho = self.l.carrinho(compra)
        with patch.object(ListaCompras, "_estava_la", return_value=True):
            self.assertEqual(self.l.materialize(carrinho - timedelta(minutes=1)), 0, "antes do carrinho, nada")
            self.assertEqual(self.l.materialize(carrinho + timedelta(minutes=5)), 1)
            self.assertEqual(self.l.materialize(carrinho + timedelta(minutes=10)), 0, "uma vez só")
        self.assertEqual(self.l.pendentes(), [])
        with self.db.get_connection() as conn:
            ev = dict(conn.execute("SELECT * FROM life_events WHERE event_key LIKE 'lista:%'").fetchone())
        self.assertEqual(ev["summary"], "Comprou barrinhas de proteína no Zona Sul (da lista, pedido do Patrick).")
        from hoje import curto
        linha = curto(ev)
        self.assertEqual((linha["texto"], linha["sub"], linha["valor"]),
                         ("Comprou barrinhas de proteína", "O Patrick sugeriu", None))
        # o pai paga: fora do extrato dela (financas lê só consumo:/transporte:/compra:)
        self.assertFalse(ev["event_key"].startswith(("consumo:", "transporte:", "compra:")))
        depois = "\n".join(self.l.prompt_lines(carrinho + timedelta(hours=2)))
        self.assertIn("Já comprou barrinhas de proteína na compra da semana", depois)
        self.assertNotIn("Próxima compra", depois)
        self.assertEqual(self.l.nota(compra["source_key"], carrinho + timedelta(hours=2)), "barrinhas de proteína")

    def test_nao_foi_ao_mercado_a_lista_espera(self):
        self._barrinhas()
        compra = self._compra(datetime(2026, 9, 29, 19, 0))
        with patch.object(ListaCompras, "_estava_la", return_value=False):
            self.assertEqual(self.l.materialize(compra["fim"]), 0)
        self.assertEqual(len(self.l.pendentes()), 1)

    def test_pedido_depois_do_carrinho_fica_pra_proxima(self):
        compra = self._compra(datetime(2026, 9, 29, 19, 0))
        self.l.adicionar("granola", "marina", compra["fim"] - timedelta(minutes=5))
        with patch.object(ListaCompras, "_estava_la", return_value=True):
            self.assertEqual(self.l.materialize(compra["fim"]), 0)
        self.assertEqual([i["item"] for i in self.l.pendentes()], ["granola"])

    def test_card_mostra_a_lista_embaixo_do_passo(self):
        from agenda import Agenda, Passo
        self._barrinhas()
        passos = [Passo("Fazendo a lista", SEG), Passo("Pegando as sacolas", SEG)]
        Agenda(self.db)._nota_lista(passos, "Fazendo a lista", "mercado:2026-09-29", SEG + timedelta(hours=1))
        self.assertEqual([p.nota for p in passos], ["barrinhas de proteína", ""])


if __name__ == "__main__":
    unittest.main()
