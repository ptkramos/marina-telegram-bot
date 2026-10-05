"""Soak, dia 6 (domingo 04/10) — relatório lido em 05/10. Os casos reais do dia:
G1 15:01 "Manda foto dele?" (o Milo) → selfie dela; 15:03 "sua safada, eu peço foto do Milo e vc manda foto tua?!" →
   selfie de lingerie (o "safada" a fez vestir o conjunto de renda); 15:04 "prometo que a próxima foto é do Milo" →
   a terceira selfie igual.
G2 15:02–15:05 a mesma pose ("selfie com a mão das unhas prontas perto da boca") três vezes seguidas.
G3 10:30 o café da manhã registrado no meio do banho (10:20–11:01).
G4 13:23 "e aquele vestido novo… o pix já saiu?" — o Pix era dele, de 02/10; comprar era ela. O assunto em aberto
   não dizia de quem era, e o reflector "resolvia" com a nota "mantido como assunto em aberto".
M1 /ruim 074 (15:16): áudio de ~10 s saiu com 22 s, arrastado.
M2 10:18 "Cheguei em casa acabada e vou tomar banho" — tinha chegado às 09:41.
Relatório: "a short … robe" contava como short; foto do Milo pedida × selfie que chegou não aparecia.
"""
import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible


def at(h, m=0, s=0, d=4):
    return datetime(2026, 10, d, h, m, s)


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "d6.db")
        seed_world_bible(self.db)

    def _fala(self, role, texto, quando):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO conversas(role, content, timestamp) VALUES (?,?,?)",
                         (role, texto, quando.isoformat()))
            conn.commit()


CTX = SimpleNamespace(place_key="marina_apartment", presence_assertable=True, present_people=(),
                      activity="brincando com o Milo", sublocation="varanda")


class FotoDoMiloTest(_Base):
    """G1: foto pedida ou prometida do Milo é do Milo, do ponto de vista dela."""

    def _direct(self, quando, request, her_line, session=None):
        import photo_director
        if session:
            photo_director.save_session(self.db, session)
        return photo_director.direct(self.db, quando, request=request, her_line=her_line, camera_ctx=CTX,
                                     rng=random.Random(1))

    def test_foto_dele_com_o_milo_no_assunto(self):
        self._fala("assistant", "Fui desmascarada mesmo\nTô brincando com o Milo na varanda agora", at(15, 1, 10))
        shot = self._direct(at(15, 1, 40), "Manda foto dele?\nTo com sdd",
                            "Mando sim, amor\nEle tá aqui pertinho de mim, já vou tirar uma dele pra você")
        self.assertTrue(shot.pov)
        self.assertEqual(shot.pose_id, "pov_milo")

    def test_foto_dele_sem_o_milo_no_assunto_e_dela(self):
        shot = self._direct(at(15, 1, 40), "Manda foto dele?", "")
        self.assertFalse(shot.pov)

    def test_bronca_com_safada_e_foto_tua(self):
        with patch("roupa.Roupa.pro_clima") as vestir:
            shot = self._direct(at(15, 3, 20), "Ksksksk o sua safada, eu peço foto do Milo e vc manda foto tua?!",
                                "KKKKKK foi mal, mandei a modelo errada\nAgora vai o Milo de verdade, sem participação "
                                "especial minha")
        self.assertEqual(shot.pose_id, "pov_milo")
        self.assertEqual(shot.level, 0)
        vestir.assert_not_called()                     # não troca de roupa pra uma foto em que ela não aparece

    def test_promessa_dela(self):
        shot = self._direct(at(15, 4, 30), "Ainda se sentindo com essas unhas que só manda foto mostrando elas",
                            "Talvez eu esteja um pouquinho obcecada mesmo\nMas prometo que a próxima foto é do Milo, "
                            "sem desvio de rota")
        self.assertEqual(shot.pose_id, "pov_milo")

    def test_foto_sua_com_o_milo_e_dela(self):
        import photo_director
        self.assertFalse(photo_director.pede_milo(self.db, at(15), "manda uma foto sua com o Milo", ""))
        self.assertFalse(photo_director.pede_milo(self.db, at(15), "manda foto do Milo", "vou tirar eu e o Milo"))
        self.assertTrue(photo_director.pede_milo(self.db, at(15), "manda foto do Milo", ""))


class PoseRepetidaTest(_Base):
    """G2: vestida, a próxima foto não repete a pose da anterior."""

    def test_nao_repete_a_selfie(self):
        sessao = {"place": "marina_apartment", "room": "varanda", "pose": "unhas_selfie", "level": 0,
                  "outfit": "an oversized white cotton t-shirt and black leggings", "beat": None, "seed": 7,
                  "at": at(15, 2).isoformat(), "food": "", "friend": "", "friend_outfit": ""}
        import photo_director
        photo_director.save_session(self.db, sessao)
        shot = photo_director.direct(self.db, at(15, 4), request="manda outra", her_line="", camera_ctx=CTX,
                                     rng=random.Random(3))
        self.assertNotEqual(shot.pose_id, "unhas_selfie")
        self.assertEqual(shot.room, "varanda")

    def test_igual_pedido_repete(self):
        sessao = {"place": "marina_apartment", "room": "varanda", "pose": "unhas_selfie", "level": 0,
                  "outfit": "x", "beat": None, "seed": 7, "at": at(15, 2).isoformat(), "food": "", "friend": "",
                  "friend_outfit": ""}
        import photo_director
        photo_director.save_session(self.db, sessao)
        shot = photo_director.direct(self.db, at(15, 4), request="manda outra igualzinha", her_line="",
                                     camera_ctx=CTX, rng=random.Random(3))
        self.assertEqual(shot.pose_id, "unhas_selfie")


class CafeNoBanhoTest(_Base):
    """G3: a refeição em casa que cai no banho espera ela sair."""

    def _banho(self, ini, fim):
        self.db.set_estado_relacional("pending_transition_json", json.dumps(
            {"routine_type": "shower", "activity": "tomando banho", "transition_at": ini.isoformat(),
             "end_at": fim.isoformat()}))

    def _materializa(self, now):
        from meals import Meals, MealSlot
        slot = MealSlot("cafe", "meal:2026-10-04:cafe", at(10, 30), 28, "casa", "brunch com panqueca e café gelado")
        m = Meals(self.db)
        with patch.object(Meals, "day_plan", return_value=[slot]), \
                patch.object(Meals, "_floor", return_value=at(5)), \
                patch.object(Meals, "_at_home", return_value=True), \
                patch.object(Meals, "_away_at", return_value=False), \
                patch.object(Meals, "_comida_chegando", return_value=False), \
                patch.object(Meals, "_belisca", return_value=0), \
                patch.object(Meals, "_belisca_na_puc", return_value=0), \
                patch.object(Meals, "_weigh_in"), patch.object(Meals, "_weekly_weight"):
            m.materialize(now)
        with self.db.get_connection() as conn:
            return conn.execute("SELECT event_at FROM life_events WHERE event_key='meal:2026-10-04:cafe'").fetchone()

    def test_no_banho_espera(self):
        self._banho(at(10, 20), at(11, 1))
        self.assertIsNone(self._materializa(at(10, 35)))

    def test_saiu_do_banho_come_depois(self):
        self._banho(at(10, 20), at(11, 1))
        row = self._materializa(at(11, 3))
        self.assertEqual(row["event_at"], at(11, 1).isoformat())

    def test_sem_banho_na_hora(self):
        self._banho(at(9, 0), at(9, 20))
        row = self._materializa(at(10, 35))
        self.assertEqual(row["event_at"], at(10, 30).isoformat())


class AssuntoSemDonoTest(_Base):
    """G4: o assunto em aberto diz de quem é; nota de "não resolveu" não fecha o assunto."""

    def test_prompt_pede_o_dono(self):
        from session_reflector import SESSION_REFLECTOR_SYSTEM_PROMPT
        self.assertIn("começando pelo nome", SESSION_REFLECTOR_SYSTEM_PROMPT)

    def test_nota_de_nao_resolvido(self):
        from session_reflector import _NAO_RESOLVIDO_RE
        self.assertTrue(_NAO_RESOLVIDO_RE.search(
            "Não há evidência de resolução na conversa; mantido como assunto em aberto."))
        self.assertFalse(_NAO_RESOLVIDO_RE.search(
            "Os detalhes do rolê com Júlia foram contados: elas foram sozinhas."))

    def test_reflector_nao_fecha(self):
        from session_reflector import SessionReflector
        lid = self.db.adicionar_open_loop(loop_type="task", content="Comprar o vestido até domingo", importance=0.6)
        r = SessionReflector(db=self.db, llm_client=object())
        r.apply_reflection({"summary": "x", "topics": [], "open_loops": [], "relationship_moments": [], "events": [],
                            "resolved_loops": [{"loop_id": lid, "resolution_notes":
                                                "Não há evidência de resolução na conversa; mantido como assunto "
                                                "em aberto."}]},
                           allowed_loop_ids=[lid])
        self.assertEqual(self.db.get_open_loop(lid)["status"], "open")

    def test_iniciativa_sabe_que_o_pix_foi_dele(self):
        from proactivity_service import ProactivityService
        import inspect
        self.assertIn("a parte dele já foi", inspect.getsource(ProactivityService))


class AudioArrastadoTest(unittest.TestCase):
    """M1: o áudio que sai muito mais lento que a fala é gerado de novo."""

    def test_limiar(self):
        from voice_engine import arrastado
        self.assertTrue(arrastado(22.35, 10.4))          # /ruim 074
        self.assertTrue(arrastado(22.71, 12.8))          # 03/10 15:26
        self.assertFalse(arrastado(7.82, 3.2))           # curto: a estimativa erra muito
        self.assertFalse(arrastado(20.76, 13.6))
        self.assertFalse(arrastado(None, 10.0))


class ProvocouOPatrickTest(_Base):
    """M3 (decisão do Patrick): só ela no clima — ele pediu pra parar — é "Provocou o Patrick"."""

    def _bloco(self):
        from tempo_livre import Bloco
        return Bloco("livre:2026-10-04:s1", "sexting", "Transando com o Patrick por mensagem", "quarto", "celular",
                     True, at(15, 8, 31), at(15, 31))

    def test_ele_pediu_pra_parar(self):
        from tempo_livre import TempoLivre
        for h, m, t in ((15, 12, "Quero só ver em, então vai botar uma roupa, quando eu chegar em casa te aviso aí vc "
                                 "pode colocar essa lingerie de novo 🤤"),
                        (15, 23, "Caralho como eu amo quando minha namorada fica safada! Obrigado Deus 🙏"),
                        (15, 25, "Marinaaa paraaa é sério eu não quero saber, fica a vontade pra gozar pensando em mim "
                                 "aí, mas não me provoca quando eu tô no trabalho é sério ksksksk"),
                        (15, 26, "Divirta-se aí sozinha ksksksk 😏")):
            self._fala("user", t, at(h, m))
        self.assertEqual(TempoLivre(self.db)._resumo(self._bloco()), "Provocou o Patrick por mensagem no quarto.")

    def test_ele_entrou(self):
        from tempo_livre import TempoLivre
        self._fala("user", "para de enrolar e tira a roupa", at(15, 10))
        self._fala("user", "goza pra mim", at(15, 20))
        self.assertEqual(TempoLivre(self.db)._resumo(self._bloco()), "Transou com o Patrick por mensagem no quarto.")

    def test_sem_mensagem_dele_fica_transou(self):
        from tempo_livre import TempoLivre
        self.assertEqual(TempoLivre(self.db)._resumo(self._bloco()), "Transou com o Patrick por mensagem no quarto.")

    def test_hoje(self):
        from hoje import curto
        ev = {"event_type": "tempo_livre", "title": "Transando com o Patrick por mensagem",
              "summary": "Provocou o Patrick por mensagem no quarto.", "event_at": at(15, 8).isoformat(),
              "end_at": None, "event_key": "livre:2026-10-04:s1"}
        c = curto(ev)
        self.assertEqual((c["texto"], c["sub"], c["presente"]),
                         ("Provocou o Patrick", "No quarto por mensagem", "Provocando o Patrick"))


class VaiSeTocarTest(_Base):
    """M4 (decisão do Patrick): "vou me divertir sim" com tesão de verdade vira o próximo bloco em casa."""

    def _feeling(self, excitation, libido=0.4, since=5.0):
        return SimpleNamespace(excitation=excitation, libido=libido, hours_since_release=since)

    def test_com_tesao(self):
        from tempo_livre import TempoLivre
        from agenda_reativa import AgendaReativa
        with patch("emotion.EmotionEngine.feeling", return_value=self._feeling(0.89)):
            self.assertTrue(TempoLivre(self.db).promessa_de_se_tocar(
                "Folgado\nvou me divertir sim\nmas relaxa que guardo um pouco desse tesão pra quando você chegar aqui",
                "Divirta-se aí sozinha ksksksk 😏", at(15, 26)))
        self.assertFalse(AgendaReativa(self.db).alivio_em_casa(at(15, 31)))       # False = sozinha (não None)
        self.assertIsNone(AgendaReativa(self.db).alivio_em_casa(at(15, 32)))      # consumido

    def test_sem_tesao(self):
        from tempo_livre import TempoLivre
        with patch("emotion.EmotionEngine.feeling", return_value=self._feeling(0.1, 0.3)):
            self.assertFalse(TempoLivre(self.db).promessa_de_se_tocar("vou me divertir sim", "Divirta-se sozinha",
                                                                      at(15, 26)))

    def test_acabou_de_gozar(self):
        from tempo_livre import TempoLivre
        with patch("emotion.EmotionEngine.feeling", return_value=self._feeling(0.9, since=0.3)):
            self.assertFalse(TempoLivre(self.db).promessa_de_se_tocar("vou me tocar sozinha", "", at(15, 26)))

    def test_divertir_na_festa_nao(self):
        from tempo_livre import TempoLivre
        with patch("emotion.EmotionEngine.feeling", return_value=self._feeling(0.9)):
            self.assertFalse(TempoLivre(self.db).promessa_de_se_tocar("vou me divertir na festa", "aproveita",
                                                                      at(15, 26)))


class BanhoDaRuaTest(unittest.TestCase):
    """M2: o banho da rua é 10–30 min depois da chegada — não é "acabei de chegar"."""

    def test_texto(self):
        import inspect
        import rituals
        src = inspect.getsource(rituals.Rituals._banho)
        self.assertNotIn("acabou de chegar da rua", src)
        self.assertIn("voltou da rua faz um tempinho", src)


def _relatorio():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "relatorio_soak", Path(__file__).resolve().parents[1] / "scripts" / "relatorio_soak.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RelatorioDia6Test(unittest.TestCase):
    def test_short_adjetivo(self):
        rx = _relatorio().RE_SHORT_ADJETIVO
        desc = "roupa: a short light pink satin robe loosely tied over a soft unpadded white lace bralette"
        self.assertNotIn("short", rx.sub(" ", desc))
        self.assertIn("short", rx.sub(" ", "roupa: an oversized white cotton t-shirt and grey cotton shorts short"))

    def test_foto_do_milo(self):
        rx = _relatorio().RE_FOTO_DO_MILO
        self.assertTrue(rx.search("eu peço foto do milo e vc manda foto tua?!"))
        self.assertTrue(rx.search("prometo que a próxima foto é do milo"))
        self.assertTrue(rx.search("manda foto dele?"))
        self.assertFalse(rx.search("manda uma foto sua"))


if __name__ == "__main__":
    unittest.main()
