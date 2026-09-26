"""25/09 15:22–15:34: ela prometeu foto do bolo e as duas opções de look, e nada chegava."""
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import photo_director
import promessa_foto
from db import DatabaseManager

T = datetime(2026, 9, 25, 15, 34)


class PromessaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "p.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_falas_reais(self):
        self.assertTrue(promessa_foto.is_promise(
            "Vou te mandar uma foto do bolo quando eu abrir, pra você conferir se eu me comportei"))
        self.assertTrue(promessa_foto.is_promise("Tô separando as duas opções aqui na cama... jaja te mando pra você dar a nota kkk"))
        self.assertIsNone(promessa_foto.is_promise("Se eu te mandar duas opções, vc dá o veredito?"), "pergunta")
        self.assertIsNone(promessa_foto.is_promise("te mando mensagem quando chegar"))
        self.assertIsNone(promessa_foto.is_promise("Vou te mandar um suquinho pelo app pra vc não precisar levantar"),
                          "delivery é do pedido_dela")
        self.assertIsNone(promessa_foto.is_promise("Vou te mandar um beijo bem gostoso"))
        # falsos positivos achados nas falas reais dela
        self.assertIsNone(promessa_foto.is_promise("E não consigo te mandar uma foto agora, a função tá em manutenção"))
        self.assertIsNone(promessa_foto.is_promise(
            "quem sabe eu não perco a vergonha e te mando pra você babar no meu estado?"))

    def test_roupa_e_comida_pelo_contexto(self):
        line = "Vou trocar agora, amor! Vou escolher uma bem linda e estilosa e já te mostro pra você aprovar kkk"
        p = promessa_foto.observe_marina_line(self.db, line, "", T)
        self.assertEqual(p["kind"], "looks")
        promessa_foto.close(self.db, "cumprida")
        seg = promessa_foto.is_promise("Quando chegar eu te mando uma foto antes de atacar kkk")
        self.assertEqual(promessa_foto.classify(seg, "Teu açaí já chegou?")[0], "comida")

    def test_duas_opcoes_de_look_pelo_contexto(self):
        ctx = "Se eu te mandar duas opções, vc dá o veredito? Vamos descobrir… quando escolher os dois finalistas"
        p = promessa_foto.observe_marina_line(
            self.db, "Fechado então! Tô separando as duas opções aqui na cama... jaja te mando pra você dar a nota kkk",
            ctx, T)
        self.assertEqual((p["kind"], p["count"]), ("looks", 2))
        due = datetime.fromisoformat(p["due_at"])
        self.assertTrue(T + timedelta(minutes=3) <= due <= T + timedelta(minutes=10), "jaja = logo")
        self.assertIn("opções de look", promessa_foto.prompt_lines(self.db, T)[0])
        self.assertIsNone(promessa_foto.due(self.db, T))
        self.assertIsNotNone(promessa_foto.due(self.db, due))
        promessa_foto.close(self.db, "cumprida")
        self.assertEqual(promessa_foto.prompt_lines(self.db, T), [])

    def test_foto_do_bolo_mais_tarde(self):
        p = promessa_foto.observe_marina_line(
            self.db, "Vou te mandar uma foto do bolo quando eu abrir, pra você conferir", "", T)
        self.assertEqual((p["kind"], p["subject"]), ("comida", "bolo"))
        self.assertGreaterEqual(datetime.fromisoformat(p["due_at"]), T + timedelta(minutes=20), "'quando eu abrir'")

    def test_expira_e_limita_tentativas(self):
        promessa_foto.observe_marina_line(self.db, "jaja te mando uma foto", "", T)
        self.assertIsNone(promessa_foto.due(self.db, T + timedelta(hours=4)))
        self.assertIsNone(promessa_foto.pending(self.db), "expirou")
        promessa_foto.observe_marina_line(self.db, "jaja te mando uma foto", "", T)
        for _ in range(promessa_foto.MAX_ATTEMPTS):
            self.assertTrue(promessa_foto.attempt(self.db))
        self.assertFalse(promessa_foto.attempt(self.db))
        self.assertIsNone(promessa_foto.pending(self.db))

    def test_opcoes_de_look_uma_de_cada_vez(self):
        """26/09 (/feedback): em álbum não dá — ela leva uns minutos trocando de roupa."""
        p = promessa_foto.observe_marina_line(self.db, "Tô separando as duas opções aqui... jaja te mando", "", T)
        self.assertEqual(p["count"], 2)
        sent_at = datetime.fromisoformat(p["due_at"])
        p2 = promessa_foto.next_part(self.db, ["look a", "look b"], 42, sent_at)
        self.assertEqual((p2["part"], p2["seed"]), (2, 42))
        due2 = datetime.fromisoformat(p2["due_at"])
        self.assertTrue(sent_at + timedelta(minutes=3) <= due2 <= sent_at + timedelta(minutes=6))
        self.assertIsNone(promessa_foto.due(self.db, sent_at + timedelta(minutes=1)), "trocando de roupa")
        self.assertIn("trocando de roupa", promessa_foto.prompt_lines(self.db, sent_at)[0])
        self.assertEqual(promessa_foto.due(self.db, due2)["outfits"], ["look a", "look b"])

    def test_looks_no_tripe_pose_muda_com_o_look(self):
        """26/09 (Patrick): look ela mostra no tripé do closet, e a pose muda junto com o look."""
        a, b = photo_director.WARDROBE["sair"][:2]
        poses = photo_director.LOOK_POSES[:2]
        shots = [photo_director.direct(self.db, T, request="look de sair", force_pose=pz, her_initiative=True,
                                       outfit_override=o, rng=random.Random(7)) for o, pz in zip((a, b), poses)]
        self.assertEqual([s.pose_id for s in shots], list(poses))
        self.assertEqual({s.room for s in shots}, {"closet"})
        self.assertTrue(all("self-timer" in s.prompt and "mirror selfie" not in s.prompt for s in shots))
        self.assertIn(a, shots[0].prompt)
        self.assertIn(b, shots[1].prompt)
        self.assertFalse(any(s.is_nsfw for s in shots))


class SextingNoBanhoTest(unittest.TestCase):
    """25/09 16:28–16:39: ela anunciou o box 4x, ficou no chat e os registros nunca chegaram."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "s.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_falas_reais_levam_ela_pro_banho(self):
        from rituals import SHOWER_NOW_RE, SHOWER_PROMISE_RE
        for fala in ("vou entrar debaixo da água agora", "Vou levar o transparente pro box cmg agora",
                     "já tô entrando debaixo da água quente com a cabeça em você", "tô indo pro chuveiro"):
            self.assertTrue(SHOWER_NOW_RE.search(fala) or SHOWER_PROMISE_RE.search(fala), fala)
        for fala in ("adoro banho quente", "depois do banho eu te conto", "a água tá gelada"):
            self.assertFalse(SHOWER_NOW_RE.search(fala), fala)

    def test_registros_do_banho_com_o_transparente(self):
        from intimacy import IntimacyTurn
        said = "se toca gostoso com aquele brinquedinho transparente / Vou levar o transparente pro box"
        shots = [photo_director.direct(self.db, T, request=f"no chuveiro com o dildo {said}", her_line=said,
                                       turn=turn, her_initiative=True, force_pose="chuveiro_tocando",
                                       rng=random.Random(3))
                 for turn in (IntimacyTurn("active", 0.9), IntimacyTurn("climax", 0.95))]
        self.assertEqual([s.beat for s in shots], ["dildo", "climax"])
        self.assertIn(photo_director.DILDO_CLEAR_TEXT, shots[0].prompt)
        self.assertNotIn(photo_director.DILDO_TEXT, shots[0].prompt)
        self.assertTrue(all(s.is_nsfw for s in shots))

    def test_saiu_do_banho_encerra_o_banho(self):
        """16:53 'gozei… já tô saindo do chuveiro': as mensagens dele ficaram presas até 17:10."""
        import json
        from rituals import Rituals
        r = Rituals(self.db)
        self.assertTrue(r.observe_marina_line("vou entrar debaixo da água agora", T))
        pend = json.loads(self.db.get_estado_relacional("pending_transition_json"))
        self.assertGreater(datetime.fromisoformat(pend["end_at"]), T + timedelta(minutes=15))
        r.observe_marina_line("gozei, pqp… já tô saindo do chuveiro pra secar a mão", T + timedelta(minutes=6))
        pend = json.loads(self.db.get_estado_relacional("pending_transition_json"))
        self.assertEqual(datetime.fromisoformat(pend["end_at"]), T + timedelta(minutes=6))

    def test_estrago_no_sexting_e_promessa_intima(self):
        p = promessa_foto.observe_marina_line(self.db, "vou me tocar até tremer as pernas / já te mando o estrago todinho",
                                              "", T, intimate=True)
        self.assertEqual((p["kind"], p["subject"]), ("intimo", ""))
        promessa_foto.close(self.db, "cumprida")
        p = promessa_foto.observe_marina_line(self.db, "jaja te mando uma foto", "", T)
        self.assertEqual(p["kind"], "selfie", "fora do clima continua selfie")

    def test_promessa_intima_vence_na_saida_do_banho(self):
        saida = T + timedelta(minutes=20)
        promessa_foto.promise_intimate(self.db, "já te mando o estrago", saida, T)
        self.assertIn("registros do banho", promessa_foto.prompt_lines(self.db, T)[0])
        self.assertIsNone(promessa_foto.due(self.db, T + timedelta(minutes=10)))
        self.assertEqual(promessa_foto.due(self.db, saida)["kind"], "intimo")


if __name__ == "__main__":
    unittest.main()
