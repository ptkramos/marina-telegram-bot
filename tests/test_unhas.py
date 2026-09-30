"""Unhas como status (Patrick, 26/09): cor, gel ou esmalte, gastando; em casa entediada, salão na
rotina/evento/mimo pago do saldo; às vezes pergunta a cor pra ele; foto da mão sempre depois se ele escolheu."""
import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from unhas import KEY, PRECO_SALAO, Unhas

T = datetime(2026, 9, 26, 15, 0)   # sábado, sem aula


class UnhasTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "u.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        for alvo, kw in (("academia.Academia.plano", {"return_value": None}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("meals.Meals.day_plan", {"return_value": []}),
                         ("sleep_plan.SleepPlan.in_bed", {"return_value": False})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        self.u = Unhas(self.db)

    def _atual(self, cor, tipo, dias, onde="casa"):
        st = json.loads(self.db.get_estado_relacional(KEY) or "{}")
        st["atual"] = {"cor": cor, "tipo": tipo, "onde": onde, "escolha": "ela",
                       "feita_em": (T - timedelta(days=dias)).isoformat()}
        self.db.set_estado_relacional(KEY, json.dumps(st))

    def test_partida_e_condicao(self):
        a = self.u.atual(T)
        self.assertEqual((a["cor"], a["tipo"], a["condicao"]), ("nude", "gel", "perfeita"))
        self._atual("vermelho", "comum", 6)
        a = self.u.atual(T)
        self.assertTrue(a["gasta"])
        self.assertEqual(a["condicao"], "gastando")
        self.assertIn("slightly worn", self.u.visual(T))
        self.assertIn("classic glossy red", self.u.visual(T))
        p = self.u.painel(T)
        self.assertEqual((p["cor"], p["estado"], p["tipo"], p["feita"]), ("Vermelho", "Gastando", "Esmalte", "Há 6 dias, em casa"))
        self._atual("vermelho", "gel", 20, "salao")
        self.assertEqual(self.u.painel(T)["estado"], "Vencendo")
        # 28/09 (Patrick): gel com 10 dias saía "Nova" — Perfeita nos primeiros dias, depois Nova
        self._atual("nude", "gel", 2, "salao")
        self.assertEqual((self.u.painel(T)["estado"], self.u.painel(T)["feita"]), ("Perfeita", "Há 2 dias, na Ophicina"))
        self._atual("nude", "gel", 10, "salao")
        self.assertEqual(self.u.painel(T)["estado"], "Nova")
        self.assertTrue(p["gasta"] and 0.8 < p["desgaste"] < 0.9)

    def test_em_casa_so_entediada_e_gasta(self):
        rng = random.Random(1)
        self._atual("vermelho", "comum", 2)
        self.assertFalse(self.u.quer_em_casa(T, T, rng), "unha nova: não refaz")
        self._atual("vermelho", "gel", 20, "salao")
        self.assertFalse(self.u.quer_em_casa(T, T, rng), "gel: quem resolve é o salão")
        self._atual("vermelho", "comum", 6)
        with patch("unhas.random.Random.random", return_value=0.1):
            self.assertTrue(self.u.quer_em_casa(T, T, random.Random(0)), "tarde à toa e unha gasta")
        with patch("unhas.random.Random.random", return_value=0.3):
            self.assertFalse(self.u.quer_em_casa(T, T, random.Random(0)), "à toa não é certeza")

    def test_casa_pergunta_ele_escolhe_e_manda_foto(self):
        self._atual("vermelho", "comum", 6)
        with patch("unhas.random.Random.random", return_value=0.1):     # pergunta
            s = self.u.comecou_em_casa(T, T + timedelta(minutes=45), T, "livre:2026-09-26:5")
        self.assertEqual(len(s["opcoes"]), 2)
        self.assertNotIn("vermelho", s["opcoes"], "não repete a cor que já estava")
        p = self.u.pergunta_pendente(T + timedelta(minutes=1))
        self.assertIn("dúvida entre", p["detail"])
        self.u.marca_pergunta_enviada(T + timedelta(minutes=1))
        self.assertIsNone(self.u.pergunta_pendente(T + timedelta(minutes=2)))
        self.assertIn("Você perguntou pro Patrick", "\n".join(self.u.prompt_lines(T + timedelta(minutes=2))))
        cor = self.u.observe_patrick("vai de preto amor", T + timedelta(minutes=5))
        self.assertEqual(cor, "preto", "qualquer cor que ele disser vale")
        self.assertEqual(self.u.materialize(T + timedelta(minutes=46)), 1)
        a = self.u.atual(T + timedelta(minutes=46))
        self.assertEqual((a["cor"], a["tipo"], a["escolha"]), ("preto", "comum", "patrick"))
        with self.db.get_connection() as conn:
            ev = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'unhas:%'").fetchone()[0]
        self.assertIn("a cor que o Patrick escolheu", ev)
        import promessa_foto
        self.assertEqual(promessa_foto.pending(self.db)["kind"], "unhas", "ele escolheu: foto sempre")

    def test_sem_resposta_ela_decide(self):
        self._atual("vermelho", "comum", 6)
        with patch("unhas.random.Random.random", return_value=0.1):
            s = self.u.comecou_em_casa(T, T + timedelta(minutes=45), T, "livre:x:1")
        self.u.marca_pergunta_enviada(T)
        self.u.materialize(T + timedelta(minutes=16))
        self.assertIsNone(self.u.observe_patrick("vermelho", T + timedelta(minutes=30)), "tarde demais")
        self.assertEqual(json.loads(self.db.get_estado_relacional(KEY))["sessao"]["cor"], s["opcoes"][0])

    def test_salao_rotina_paga_do_saldo(self):
        import financas
        self._atual("nude", "gel", 20, "salao")
        financas.materialize(self.db, T - timedelta(hours=1))      # dinheiro registrado desde antes
        saldo = financas._load(self.db)["saldo"]
        # (o sorteio em 0 vale pra todo Random, inclusive o da saúde: a trava de "passando mal" fica de fora aqui)
        with patch("unhas.random.Random.random", return_value=0.0), \
                patch("vontade.Vontade._sem_condicao", return_value=False):
            cid = self.u.talvez_salao(T)
        self.assertIsNotNone(cid)
        from agenda import Agenda
        etapas = Agenda(self.db).etapas(T.date(), T)
        self.assertEqual([e.tipo for e in etapas], ["arrumando", "caminho", "la", "voltando"])
        self.assertEqual(etapas[2].titulo, "Na Ophicina")
        self.assertEqual((etapas[2].passos[-1].texto, etapas[2].passos[-1].valor), ("Pagando", PRECO_SALAO))
        fim = etapas[2].fim
        self.u.materialize(fim + timedelta(minutes=1))
        a = self.u.atual(fim + timedelta(minutes=1))
        self.assertEqual((a["tipo"], a["onde"]), ("gel", "salao"))
        financas.materialize(self.db, fim + timedelta(minutes=2))
        self.assertEqual(financas._load(self.db)["saldo"], saldo - PRECO_SALAO)

    def test_motivo_seco(self):
        from unhas import motivo_txt
        self.assertEqual(motivo_txt("trabalho", T + timedelta(days=1), T), "job amanhã")
        self.assertEqual(motivo_txt("encontro", T + timedelta(hours=2), T), "encontro hoje")
        self.assertEqual(motivo_txt("rotina", None, T), "manutenção do gel")

    def test_salao_nao_vai_domingo_nem_sem_dinheiro(self):
        self._atual("nude", "gel", 20, "salao")
        with patch("unhas.random.Random.random", return_value=0.0):
            self.assertIsNone(self.u.talvez_salao(T + timedelta(days=1)), "domingo fechado")
            with patch.object(Unhas, "_saldo", return_value=PRECO_SALAO):
                self.assertIsNone(self.u.talvez_salao(T))

    def test_foto_leva_a_cor(self):
        from types import SimpleNamespace
        import photo_director
        self._atual("lilas", "gel", 3, "salao")
        ctx = SimpleNamespace(place_key="marina_apartment", presence_assertable=True, activity="", sublocation="",
                              weather=None, present_people=())
        shot = photo_director.direct(self.db, T, request="foto", camera_ctx=ctx, rng=random.Random(3))
        self.assertIn("pastel lilac", shot.prompt)
        mao = photo_director.direct(self.db, T, camera_ctx=ctx, force_pose="pov_unhas", rng=random.Random(3))
        self.assertTrue(mao.pov)
        self.assertIn("Only her hand", mao.prompt)
        self.assertIn("pastel lilac", mao.prompt)


if __name__ == "__main__":
    unittest.main()
