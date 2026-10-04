"""Aba Dinheiro dos Bastidores (Patrick, 28/09): topo com o mês, próximo cachê e contas; extrato agrupado por saída
(toca e abre os itens), fora de saída a ação no passado na linha e o detalhe embaixo."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import extrato
import financas
from db import DatabaseManager

AGORA = datetime(2026, 9, 28, 13, 20)   # segunda
EVENTOS = (
    ("transporte:commute:outing:2026-09-27:c3:ida", "2026-09-27T14:38:00", "Uber",
     "Pagou o uber indo pro Shopping da Gávea (R$ 35)."),
    ("consumo:outing:2026-09-27:c3:0", "2026-09-27T15:07:00", "Shopping da Gávea · Cinema",
     "Pediu o ingresso do cinema no Shopping da Gávea (R$ 42)."),
    ("consumo:outing:2026-09-27:c3:1", "2026-09-27T15:12:00", "Shopping da Gávea · Pipoca (dividiu)",
     "Dividiu uma pipoca grande com a Bia no Shopping da Gávea (R$ 17, a parte dela)."),
    ("transporte:commute:outing:2026-09-27:c3:volta", "2026-09-27T19:00:00", "Uber",
     "Pagou o uber voltando do Shopping da Gávea pra casa (R$ 35)."),
    ("consumo:vontade:2026-09-27:1923:0", "2026-09-27T19:39:26", "Drogarias Pacheco · Demaquilante Bioderma 250 ml",
     "Pediu demaquilante Bioderma 250 ml no Drogarias Pacheco (R$ 93)."),
    ("consumo:outing:2026-09-26:c1:0", "2026-09-26T21:13:00", "Quartinho Bar · Gin tônica",
     "Pediu um gin tônica no Quartinho Bar (R$ 34)."),
    ("consumo:outing:2026-09-26:c1:1", "2026-09-26T22:09:00", "Quartinho Bar · Gin tônica",
     "Pediu um gin tônica no Quartinho Bar (R$ 34)."),
    ("transporte:commute:outing:2026-09-26:c1:volta", "2026-09-26T23:59:00", "Uber (dividiu)",
     "Pagou o uber voltando do Quartinho Bar pra casa (R$ 7, dividido com a Bia)."),
    ("freela:c1:sinal", "2026-09-20T11:00:00", "trabalho", "A Lívia fez o pix de metade do cachê (catálogo da Farm): R$ 400."),
)
# movimentos como estavam na produção antes de 28/09 (sem a chave): o extrato acha pelo título e pela hora
MOVS = [
    {"at": "2026-09-20T11:00", "valor": 400, "desc": "cachê do freela"},
    {"at": "2026-09-26T20:17", "valor": 300, "desc": "pix do Patrick"},
    {"at": "2026-09-26T21:13", "valor": -34, "desc": "Quartinho Bar · Gin tônica"},
    {"at": "2026-09-26T22:09", "valor": -34, "desc": "Quartinho Bar · Gin tônica"},
    {"at": "2026-09-26T23:59", "valor": -7, "desc": "Uber (dividiu)"},
    {"at": "2026-09-27T14:38", "valor": -35, "desc": "Uber"},
    {"at": "2026-09-27T15:07", "valor": -42, "desc": "Shopping da Gávea · Cinema"},
    {"at": "2026-09-27T15:12", "valor": -17, "desc": "Shopping da Gávea · Pipoca (dividiu)"},
    {"at": "2026-09-27T19:00", "valor": -35, "desc": "Uber"},
    {"at": "2026-09-27T19:39", "valor": -93, "desc": "Drogarias Pacheco · Demaquilante Bioderma 250 ml"},
    {"at": "2026-09-28T12:00", "valor": -40, "desc": "presente do Patrick: um açaí caprichado"},
    {"at": "2026-09-28T12:30", "valor": -189, "desc": "contas dela (celular e streamings)"},
]


class ExtratoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(Path(self.tmp.name) / "p.db")
        with self.db.get_connection() as conn:
            for key, at, title, summary in EVENTOS:
                conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                                autonomy_level,importance,participants_json,share_worthy,created_at)
                                VALUES (?,?,'consumo',?,?,'simulated',1,0.1,'[]',0.1,?)""",
                             (key, at, title, summary, AGORA.isoformat()))
            conn.commit()
        self.dias = extrato.extrato_view(self.db, MOVS, AGORA)

    def _item(self, texto):
        return next(i for d in self.dias for i in d["itens"] if i["texto"] == texto)

    def test_dias_do_mais_novo_pro_mais_velho(self):
        self.assertEqual([d["dia"] for d in self.dias], ["Hoje", "Ontem", "Sáb, 26/09", "Dom, 20/09"])

    def test_saida_agrupada_com_total_e_itens(self):
        s = self._item("Foi no Shopping da Gávea")
        self.assertEqual(s["sub"], "Cinema, pipoca e uber")
        self.assertEqual((s["valor"], s["hora"]), (-129, "14:38"))
        self.assertEqual([(f["texto"], f["sub"]) for f in s["filhos"]],
                         [("Uber", "Ida"), ("Cinema", ""), ("Pipoca", "Dividiu com a Bia"), ("Uber", "Volta")])

    def test_repetido_vira_numero_e_uber_dividido(self):
        s = self._item("Foi no Quartinho Bar")
        self.assertEqual(s["sub"], "2 gin tônicas e uber")
        self.assertEqual(s["filhos"][-1]["sub"], "Volta, dividiu com a Bia")

    def test_lugar_feminino_e_quantidade_fora_do_resumo(self):
        s = self._item("Foi na Drogarias Pacheco")
        self.assertEqual(s["sub"], "Demaquilante Bioderma")
        self.assertEqual(s["filhos"], [])           # um item só: sem abrir

    def test_fora_de_saida_acao_na_linha(self):
        self.assertEqual(self._item("Recebeu o Pix do Patrick")["sub"], "")          # sem recado, nada embaixo
        self.assertEqual(self._item("Usou o Pix do Patrick")["sub"], "Um açaí caprichado")
        self.assertEqual(self._item("Pagou as contas")["sub"], "Celular e streamings")
        self.assertEqual(self._item("Recebeu metade do cachê")["sub"], "Catálogo da Farm")

    def test_movimento_novo_guarda_a_chave(self):
        st = financas._init({}, AGORA)
        financas._mov(st, AGORA, -12, "Uber", "transporte:commute:outing:2026-09-28:c1:ida")
        self.assertEqual(st["movs"][-1]["key"], "transporte:commute:outing:2026-09-28:c1:ida")


class TopoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(Path(self.tmp.name) / "p.db")

    def test_mes_calculado_dos_movimentos_antigos(self):
        self.db.set_estado_relacional(financas.KEY, json.dumps({"saldo": 595, "movs": MOVS[1:]}))
        st = financas._load(self.db)
        topo = extrato.topo_view(self.db, st, AGORA)
        self.assertEqual((topo["mes"], topo["entrou"], topo["saiu"]), ("setembro", 300, 34 + 34 + 7 + 35 + 42 + 17 + 35 + 93 + 40 + 189))
        rotulos = [r for _, r, _ in topo["linhas"]]
        self.assertEqual(rotulos, ["Próximo cachê", "Contas"])
        self.assertEqual(topo["linhas"][0][2], "Nenhum marcado")

    def test_contas_passadas_sem_registro_mostram_o_mes_que_vem(self):
        txt = extrato._contas(self.db, AGORA)
        self.assertRegex(txt, r"^Dia [5-8]/10, R\$ 189$")

    def test_contas_pagas(self):
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                            autonomy_level,importance,participants_json,share_worthy,created_at)
                            VALUES ('casa:2026-09-06:contas_dela','2026-09-06T15:00:00','casa','contas','x',
                            'simulated',1,0.1,'[]',0.1,'2026-09-06T15:00:00')""")
            conn.commit()
        self.assertRegex(extrato._contas(self.db, AGORA), r"^Pagas dia [5-8], R\$ 189$")


if __name__ == "__main__":
    unittest.main()
