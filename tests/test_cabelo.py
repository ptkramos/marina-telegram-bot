"""Cabelo como status (Patrick, 26/09): dia de lavar no banho, penteado de agora, corte, luzes e hidratação;
salão na Ophicina junta o que venceu (pago do saldo); pergunta penteado/corte pra ele; sugestão dele vira
mudança; o cabelo de agora manda nas fotos."""
import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from cabelo import KEY, SERVICOS, Cabelo

T = datetime(2026, 9, 26, 15, 0)   # sábado, sem aula


class CabeloTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "c.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        for alvo, kw in (("academia.Academia.plano", {"return_value": None}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("meals.Meals.day_plan", {"return_value": []}),
                         ("sleep_plan.SleepPlan.in_bed", {"return_value": False}),
                         ("cabelo.Cabelo._no_banho", {"return_value": False})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        self.c = Cabelo(self.db)

    def _set(self, **kw):
        st = self.c._state(T)
        for k, dias in kw.items():
            st[k] = (T - timedelta(days=dias)).isoformat() if isinstance(dias, (int, float)) else dias
        self.db.set_estado_relacional(KEY, json.dumps(st))

    def test_partida_painel_e_foto(self):
        c = self.c.condicao(T)
        self.assertEqual((c["lavagem"], c["pontas"], c["corte"], c["tom"]), ("2º dia", "Boas", "reto", "dourado"))
        p = self.c.painel(T)
        self.assertEqual(p["penteado"], "Solto natural")
        self.assertEqual([b["label"] for b in p["barras"]], ["Lavagem", "Pontas", "Luzes", "Hidratação"])
        self.assertEqual(p["linhas"][1][2], "Reto, há 5 semanas")
        cor, estilo = self.c.visual(T)
        self.assertEqual(cor, "long chestnut brown hair with golden blonde tips")
        self.assertEqual(estilo, "semi-straight with soft waves at the ends")
        self._set(lavado_em=2.5)
        self.assertIn(self.c.penteado(T), ("coque_oleoso", "rabo_baixo"), "3º dia: oleoso, preso")
        self._set(corte="franja", cortado_em=10, rosa_em=3)
        cor, _ = self.c.visual(T)
        self.assertIn("pastel pink dyed tips", cor)
        self.assertIn("blunt bangs", cor)
        self._set(cortado_em=50)
        self.assertEqual(self.c.condicao(T)["corte"], "cortina", "a franja cheia cresce e vira cortina")

    def test_banho_lava_no_segundo_dia_e_protege_escova(self):
        self._set(lavado_em=0.2)
        self.assertEqual(self.c.banho(T, 15, T), 0, "lavou hoje: não lava de novo")
        self._set(lavado_em=2)
        extra = self.c.banho(T, 15, T)
        self.assertGreater(extra, 0, "3º dia: sempre lava")
        st = json.loads(self.db.get_estado_relacional(KEY))
        self.assertEqual(st["lavado_em"], T.isoformat())
        self.assertIn(self.c.penteado(T + timedelta(minutes=20)), ("molhado", "secando"))
        self._set(lavado_em=1, secagem="escova_salao")
        self.assertEqual(self.c.banho(T, 15, T), 0, "escova do salão: não lava no 2º dia")

    def test_umectacao_lava_no_proximo_banho(self):
        self._set(hidratado_em=20, lavado_em=0.1)
        with patch("cabelo.random.Random.random", return_value=0.01):
            self.assertTrue(self.c.quer_umectar(T, T, random.Random(0)))
        self.c.umectou(T, T + timedelta(minutes=70), T)
        self.assertEqual(self.c.penteado(T + timedelta(minutes=30)), "touca")
        self.assertGreater(self.c.banho(T + timedelta(minutes=80), 15, T + timedelta(minutes=80)), 0)

    def test_salao_junta_o_vencido_e_paga(self):
        self._set(cortado_em=80, tonalizado_em=60, hidratado_em=5)
        with patch("cabelo.Cabelo._saldo", return_value=2000), patch("cabelo.MUDAR_CHANCE", 0.0), \
                patch("cabelo.SALAO_PERGUNTA_CHANCE", 0.0), patch("cabelo.random.Random.random", return_value=0.01):
            cid = self.c.talvez_salao(T)
        self.assertTrue(cid)
        s = self.c.sessao(T)
        self.assertEqual(s["servicos"], ["tonalizar", "corte", "escova"])
        self.assertEqual(s["preco"], sum(SERVICOS[x][1] for x in ("tonalizar", "corte", "escova")))
        with self.db.get_connection() as conn:
            meta = json.loads(conn.execute("SELECT metadata_json FROM eventos_pendentes WHERE source_key=?",
                                           (s["chave"],)).fetchone()[0])
        self.assertEqual(meta["passos"][-1], ["Pagando", 5])
        fim = datetime.fromisoformat(s["fim"])
        self.c.materialize(fim + timedelta(minutes=1))
        with self.db.get_connection() as conn:
            ev = conn.execute("SELECT summary FROM life_events WHERE event_key=?", (f"compra:{s['chave']}",)).fetchone()
        self.assertIn(f"· R$ {s['preco']}", ev["summary"])
        c = self.c.condicao(fim + timedelta(minutes=2))
        self.assertEqual((c["pontas"], c["luzes"], c["lavagem"]), ("Boas", "Nova", "Lavado hoje"))
        self.assertEqual(self.c.penteado(fim + timedelta(minutes=2)), "escova")

    def test_pergunta_do_salao_ele_escolhe(self):
        self._set(cortado_em=80, tonalizado_em=10, hidratado_em=5)
        with patch("cabelo.Cabelo._saldo", return_value=2000), patch("cabelo.MUDAR_CHANCE", 0.0), \
                patch("cabelo.SALAO_PERGUNTA_CHANCE", 1.0), patch("cabelo.random.Random.random", return_value=0.01):
            self.assertTrue(self.c.talvez_salao(T))
        p = self.c.pergunta_pendente(T + timedelta(minutes=1))
        self.assertIn("salão", p["detail"])
        self.assertEqual(p["opcoes"], ["pontas", "repicado"])
        self.c.marca_pergunta_enviada(T + timedelta(minutes=1))
        self.assertEqual(self.c.observe_patrick("repica amor, vai ficar linda", T + timedelta(minutes=3)), "repicado")
        s = self.c.sessao(T + timedelta(minutes=4))
        self.assertEqual((s["mudanca"], s["quem"]), ("repicado", "patrick"))
        self.assertIn("Ele escolheu: repicar", "\n".join(self.c.prompt_lines(T + timedelta(minutes=4))))
        fim = datetime.fromisoformat(s["fim"])
        with patch("promessa_foto.promise_cabelo") as promete:
            self.c.materialize(fim - timedelta(minutes=5))
        self.assertEqual(promete.call_args.kwargs["pose"], "salao_cabelo")
        self.assertTrue(promete.call_args.kwargs["pediu"])
        self.c.materialize(fim + timedelta(minutes=1))
        self.assertEqual(self.c.condicao(fim + timedelta(minutes=2))["corte"], "repicado")
        with self.db.get_connection() as conn:
            ev = conn.execute("SELECT summary FROM life_events WHERE event_key=?", (f"compra:{s['chave']}",)).fetchone()
        self.assertEqual(ev["summary"], "Cabelo na Ophicina: repicado (o Patrick escolheu) e escova · R$ 220.")
        linhas = self.c.painel(fim + timedelta(minutes=2))["linhas"]
        self.assertEqual(linhas[0][2], "Hoje, escova no salão")
        self._set(rosa_em=3)
        self.assertEqual(self.c.painel(T)["linhas"][-1], ["brush", "Rosa", "Há 3 dias, desbota em ~3 semanas"])

    def test_sugestao_dele_vira_mudanca(self):
        self.assertEqual(self.c.observe_patrick("vc ficaria linda de franja sabia", T), "franja")
        self.assertIn("sugeriu franja", "\n".join(self.c.prompt_lines(T)))
        self.assertIsNone(Cabelo(self.db).observe_patrick("hoje fui cortar o cabelo", T))

    def test_penteado_de_sair_pergunta_e_foto(self):
        prep = {"chave": "prep:noite:1", "prep_tipo": "noite", "start_at": T.isoformat(),
                "end_at": (T + timedelta(minutes=80)).isoformat()}
        with patch("cabelo.random.Random.random", return_value=0.1):
            self.assertIsNone(self.c.se_arrumando(prep, T))
        p = self.c.pergunta_pendente(T + timedelta(minutes=1))
        self.assertIn("se arrumando pra sair", p["detail"])
        self.c.marca_pergunta_enviada(T + timedelta(minutes=1))
        a, b = p["opcoes"]
        from cabelo import ESTILOS
        escolhido = self.c.observe_patrick(f"vai de {ESTILOS[b][0].lower()}", T + timedelta(minutes=5))
        self.assertEqual(escolhido, b)
        with patch("promessa_foto.promise_cabelo") as promete:
            self.c.materialize(T + timedelta(minutes=61))
        self.assertTrue(promete.called, "ele escolheu: sempre manda a foto")
        self.assertIn(promete.call_args.kwargs["pose"], ("cabelo_espelho", "cabelo_tripe"))
        self.assertEqual(self.c.penteado(T + timedelta(minutes=90)), b)


if __name__ == "__main__":
    unittest.main()
