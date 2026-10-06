"""Redesenho dos Bastidores, passo 1 (PLANO_WEBAPP, "Redesenho dos Bastidores — plano"; 06/10).

O histórico que só a tela lê (`bastidores_hist`, migração 037): orgasmos (com o Patrick e sozinha), a hora em que a
excitação acendeu, o retrato do vínculo da hora, o peso do dia e a pesagem da balança. Ela nunca lê isto.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import bastidores_hist as bh
from db import DatabaseManager
from intimacy import IntimacyEngine, observe_marina_line

T0 = datetime(2026, 10, 6, 21, 40)


class _Cycle:
    def get_cycle_info(self):
        return {"phase_key": "folicular", "libido": "teste"}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "hist.db")

    def tearDown(self):
        self.temp.cleanup()

    def todos(self, chave):
        return bh.lista(self.db, chave, T0 - timedelta(days=30), T0 + timedelta(days=30))


class TabelaTests(Base):
    def test_migration_cria_a_tabela(self):
        self.assertEqual(self.db.get_schema_version(), 38)
        self.assertEqual(self.todos("orgasmo"), [])

    def test_ref_nao_duplica(self):
        self.assertTrue(bh.gravar(self.db, "peso", T0, {"kg": 54.0}, ref="2026-10-06"))
        self.assertFalse(bh.gravar(self.db, "peso", T0 + timedelta(hours=3), {"kg": 55.0}, ref="2026-10-06"))
        self.assertEqual([r["kg"] for r in self.todos("peso")], [54.0])

    def test_erro_nunca_derruba_quem_chamou(self):
        with self.db.get_connection() as conn:
            conn.execute("DROP TABLE bastidores_hist")
            conn.commit()
        bh.orgasmo(self.db, T0, "sozinha", "em casa")
        bh.excitacao(self.db, 0.0, 0.5, T0)
        bh.retrato(self.db, T0)
        self.assertEqual(bh.lista(self.db, "orgasmo", T0), [])
        self.assertIsNone(bh.ultimo(self.db, "orgasmo", T0))


class OrgasmoTests(Base):
    def test_com_ele_e_sozinha_em_dias_diferentes(self):
        bh.orgasmo(self.db, T0 - timedelta(days=3), "sozinha", "antes de dormir")
        bh.orgasmo(self.db, T0, "patrick", "sexting")
        rs = self.todos("orgasmo")
        self.assertEqual([(r["com"], r["como"]) for r in rs], [("sozinha", "antes de dormir"), ("patrick", "sexting")])
        self.assertEqual(bh.ultimo(self.db, "orgasmo", T0 - timedelta(hours=1))["com"], "sozinha")

    def test_o_mesmo_gozo_por_dois_caminhos_e_um_so(self):
        # ela escreve "gozei" com o brinquedo ligado: intimacy (sexting) e Lovense registram o mesmo gozo
        bh.orgasmo(self.db, T0, "patrick", "sexting")
        bh.orgasmo(self.db, T0 + timedelta(seconds=5), "patrick", "lovense", brinquedos=["lush"], publico=False)
        rs = self.todos("orgasmo")
        self.assertEqual(len(rs), 1)
        self.assertEqual((rs[0]["com"], rs[0]["como"], rs[0]["brinquedos"]), ("patrick", "lovense", ["lush"]))

    def test_sozinha_chamando_ele_vira_com_ele_quando_coincide(self):
        bh.orgasmo(self.db, T0, "sozinha", "em casa", onde="no quarto", chamou=True)
        bh.orgasmo(self.db, T0 + timedelta(minutes=2), "patrick", "sexting")
        rs = self.todos("orgasmo")
        self.assertEqual(len(rs), 1)
        self.assertEqual((rs[0]["com"], rs[0]["como"], rs[0]["onde"]), ("patrick", "sexting", "no quarto"))

    def test_com_ele_nao_vira_sozinha(self):
        bh.orgasmo(self.db, T0, "patrick", "sexting")
        bh.orgasmo(self.db, T0 + timedelta(minutes=1), "sozinha", "em casa")
        self.assertEqual(self.todos("orgasmo")[0]["com"], "patrick")

    def test_longe_sao_dois(self):
        bh.orgasmo(self.db, T0, "patrick", "sexting")
        bh.orgasmo(self.db, T0 + timedelta(minutes=25), "patrick", "sexting")
        self.assertEqual(len(self.todos("orgasmo")), 2)

    def test_ela_escrever_que_gozou_registra(self):
        eng = IntimacyEngine(self.db, _Cycle())
        for i, fala in enumerate(["tô com um tesão do caralho em você", "fala putaria pra mim, sem vergonha",
                                  "me descreve o que você ia fazer com o meu pau"]):
            eng.observe(fala, now=T0 + timedelta(minutes=2 * i))
        self.assertTrue(observe_marina_line(self.db, "to gozando amor", T0 + timedelta(minutes=8)))
        rs = self.todos("orgasmo")
        self.assertEqual([(r["com"], r["como"], r["em"]) for r in rs],
                         [("patrick", "sexting", T0 + timedelta(minutes=8))])


class ExcitacaoTests(Base):
    def test_acende_uma_vez_e_de_novo_depois_de_esfriar(self):
        eng = IntimacyEngine(self.db, _Cycle())
        eng.observe("oi amor, tudo bem?", now=T0 - timedelta(minutes=5))           # nada: não acende
        self.assertEqual(self.todos("excitacao"), [])
        eng.observe("tô com um tesão do caralho em você", now=T0)
        eng.observe("fala putaria pra mim, sem vergonha", now=T0 + timedelta(minutes=2))
        self.assertEqual([r["em"] for r in self.todos("excitacao")], [T0])
        eng.observe("tô com um tesão do caralho em você", now=T0 + timedelta(hours=2))  # esfriou e acendeu de novo
        rs = self.todos("excitacao")
        self.assertEqual([(r["em"], r["origem"]) for r in rs],
                         [(T0, "conversa"), (T0 + timedelta(hours=2), "conversa")])

    def test_o_brinquedo_acende_com_origem_lovense(self):
        eng = IntimacyEngine(self.db, _Cycle())
        for seg in range(0, 600, 10):
            eng.estimular(T0 + timedelta(seconds=seg), 0.15)
        rs = self.todos("excitacao")
        self.assertEqual(len(rs), 1)
        self.assertEqual(rs[0]["origem"], "lovense")
        self.assertLess(rs[0]["em"], T0 + timedelta(minutes=3))

    def test_limiar(self):
        bh.excitacao(self.db, 0.05, 0.09, T0)
        bh.excitacao(self.db, 0.12, 0.40, T0)
        self.assertEqual(self.todos("excitacao"), [])
        bh.excitacao(self.db, 0.05, 0.10, T0)
        self.assertEqual(len(self.todos("excitacao")), 1)


class RetratoTests(Base):
    def test_vinculo_um_por_hora_e_peso_um_por_dia(self):
        bh.retrato(self.db, T0.replace(minute=3))
        bh.retrato(self.db, T0.replace(minute=13))
        bh.retrato(self.db, T0.replace(minute=3) + timedelta(hours=1))
        vs = self.todos("vinculo")
        self.assertEqual([v["em"].hour for v in vs], [21, 22])
        for k in ("affection", "romantic_intensity", "security", "hurt", "saudade"):
            self.assertIn(k, vs[0])
        self.assertEqual(len(self.todos("peso")), 1)
        self.assertEqual(self.todos("peso")[0]["kg"], 54.0)
        bh.retrato(self.db, T0 + timedelta(days=1))
        self.assertEqual(len(self.todos("peso")), 2)

    def test_retrato_segue_o_vinculo(self):
        bh.retrato(self.db, T0)
        self.db.ajustar_emocao("hurt", 0.3, T0 + timedelta(minutes=30))
        bh.retrato(self.db, T0 + timedelta(hours=1))
        a, b = self.todos("vinculo")
        self.assertGreater(b["hurt"], a["hurt"])

    def test_pesagem(self):
        bh.pesagem(self.db, T0, 54.04)
        bh.pesagem(self.db, T0 + timedelta(hours=1), 54.04)
        rs = self.todos("pesagem")
        self.assertEqual([(r["kg"], r["em"]) for r in rs], [(54.0, T0)])


if __name__ == "__main__":
    unittest.main()
