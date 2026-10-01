"""Agenda reativa (Patrick, 26/09): o que ela topa na conversa vira compromisso de verdade, e tudo
pode ser interrompido se houver motivo (passou mal, banheiro, cansou, rolê chato, tédio, tesão)."""
import itertools
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agenda import Agenda
from agenda_reativa import AgendaReativa, classe_disponibilidade
from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from vontade import Vontade

T = datetime(2026, 9, 26, 16, 0)   # sábado, sem aula


class FakeLLM:
    def __init__(self, resposta: dict):
        self.resposta, self.chamadas = resposta, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.chamadas += 1
        msg = SimpleNamespace(content=json.dumps(self.resposta))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def sentir(**kw):
    base = dict(discomfort=0.0, energy=0.7, valence=0.6, social_battery=0.7, episodes=[], libido=0.3,
                excitation=0.0, missing=0.0, bond={})
    return SimpleNamespace(**{**base, **kw})


class AgendaReativaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "r.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        for alvo, kw in (("academia.Academia.plano", {"return_value": None}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("meals.Meals.day_plan", {"return_value": []}),
                         ("sleep_plan.SleepPlan.in_bed", {"return_value": False}),
                         # 27/09: o random.random()=0 dos testes sorteava uma virose (agenda viva: doente só farmácia)
                         ("emotion.EmotionEngine._discomfort", {"return_value": (0.0, "")})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        from seed_academic_v36 import seed_academic
        from social_day import SocialDay
        seed_academic(self.db)
        SocialDay(self.db)._floor(T - timedelta(hours=1))
        self.r = AgendaReativa(self.db)

    def _cafe(self):
        with patch("vontade.random.Random.random", return_value=0.0), \
                patch("vontade.random.Random.choices", side_effect=lambda pop, weights=None: [
                    "cafe" if "cafe" in pop else pop[0]]):
            self.assertIsNotNone(Vontade(self.db).talvez(T))
        return next(e for e in Agenda(self.db).etapas(T.date(), T) if e.tipo == "la")

    def _evento(self, like: str) -> str:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE ?", (like,)).fetchone()
        return row[0] if row else ""

    # ------------------------------------------------------------ conversa --
    def test_ele_convence_e_ela_vai_treinar(self):
        llm = FakeLLM({"acao": "vai_fazer", "tipo": "academia", "quando": "agora", "motivo": "o Patrick convenceu"})
        out = self.r.observe_conversa("aff tá bom, vou me trocar", "vai treinar sim", T, llm=llm)
        self.assertIsNotNone(out)
        etapas = Agenda(self.db).etapas(T.date(), T)
        self.assertEqual([e.tipo for e in etapas], ["arrumando", "caminho", "la", "voltando"])
        self.assertEqual(etapas[0].inicio, T, "se arruma a partir de quando topou")
        self.assertEqual(etapas[2].lugar_key, "bodytech_sao_clemente")
        self.assertEqual(self._evento("vontade:%:c1600:decidiu"), "O Patrick convenceu e ela saiu pra academia.")

    def test_fala_sem_cara_de_plano_nem_chama_o_modelo(self):
        llm = FakeLLM({"acao": "vai_fazer", "tipo": "cafe", "quando": "agora"})
        self.assertIsNone(self.r.observe_conversa("kkkk que isso amor", "vc é doida", T, llm=llm))
        self.assertEqual(llm.chamadas, 0)

    def test_nenhuma_nao_mexe_na_agenda(self):
        llm = FakeLLM({"acao": "nenhuma", "tipo": None, "quando": None})
        self.assertIsNone(self.r.observe_conversa("vou pensar", "vamos no cinema amanhã?", T, llm=llm))
        self.assertEqual(Agenda(self.db).etapas(T.date(), T), [])

    def test_desistiu_antes_de_sair(self):
        self._cafe()
        llm = FakeLLM({"acao": "desistiu", "tipo": "cafe", "quando": None, "motivo": "começou a chover"})
        out = self.r.observe_conversa("desisti do café, tá chovendo", "vai sair?", T + timedelta(minutes=2), llm=llm)
        self.assertTrue(out and out["cancelado"])
        self.assertEqual(Agenda(self.db).etapas(T.date(), T), [])
        self.assertRegex(self._evento("desistiu:%"), r"^Desistiu de sair pr[oa] [^:]+: começou a chover\.$")
        self.assertNotIn("café", self._evento("desistiu:%").split(":")[0].casefold(), "o lugar, não o tipo")

    def test_adianta_a_academia_planejada(self):
        from academia import Academia, Planejada
        plano = {"inicio": (T + timedelta(hours=2)).isoformat(), "fim": (T + timedelta(hours=3)).isoformat(),
                 "onde": "rua"}
        self.db.set_estado_relacional("academia_json", json.dumps({T.date().isoformat(): plano}))
        with patch("academia.Academia.plano", Planejada.plano):
            llm = FakeLLM({"acao": "vai_fazer", "tipo": "academia", "quando": "agora"})
            self.assertIsNotNone(self.r.observe_conversa("tá, vou agora então", "vai logo", T, llm=llm))
            novo = Academia(self.db).plano(T.date(), T)
            self.assertLess(novo["inicio"], T + timedelta(minutes=40))
            self.assertEqual(novo["fim"] - novo["inicio"], timedelta(hours=1), "mesma duração do treino")
            prep = next(e for e in Agenda(self.db).etapas(T.date(), T) if e.tipo == "arrumando")
            self.assertEqual(prep.inicio, T)

    def test_vou_mais_tarde_se_arruma_perto_da_hora(self):
        llm = FakeLLM({"acao": "vai_fazer", "tipo": "academia", "quando": "18:00", "motivo": ""})
        self.assertIsNotNone(self.r.observe_conversa("vou às 18h, antes da janta", "vai pra academia hoje?", T, llm=llm))
        prep, ida = Agenda(self.db).etapas(T.date(), T)[:2]
        self.assertEqual(ida.inicio, datetime(2026, 9, 26, 18, 0))
        self.assertGreater(prep.inicio, T + timedelta(minutes=90), "não fica 2 h se arrumando")
        self.assertEqual(self._evento("vontade:%:decidiu"), "Combinou com o Patrick de sair pra academia às 18:00.")

    def test_remarca_a_academia_pra_mais_tarde(self):
        from academia import Academia, Planejada
        plano = {"inicio": (T + timedelta(hours=1)).isoformat(), "fim": (T + timedelta(hours=2)).isoformat(),
                 "onde": "rua"}
        self.db.set_estado_relacional("academia_json", json.dumps({T.date().isoformat(): plano}))
        with patch("academia.Academia.plano", Planejada.plano):
            llm = FakeLLM({"acao": "vai_fazer", "tipo": "academia", "quando": "19:00"})
            self.assertIsNotNone(self.r.observe_conversa("vou só às 19h", "vai treinar?", T, llm=llm))
            self.assertEqual(Academia(self.db).plano(T.date(), T)["inicio"], datetime(2026, 9, 26, 19, 12))
        self.assertEqual(self._evento("remarcou:%"), "Combinou com o Patrick de sair pra academia às 19:00.")

    def test_vou_embora_encerra_o_que_ela_esta_fazendo(self):
        la = self._cafe()
        agora = la.inicio + timedelta(minutes=10)
        llm = FakeLLM({"acao": "vai_embora", "tipo": None, "quando": "agora", "motivo": "o café tava cheio"})
        self.assertIsNotNone(self.r.observe_conversa("vou embora daqui, tá lotado", "e aí?", agora, llm=llm))
        volta = next(e for e in Agenda(self.db).etapas(T.date(), agora) if e.tipo == "voltando")
        self.assertLessEqual(volta.inicio, agora + timedelta(minutes=5))

    # ---------------------------------------------------------- interromper --
    def test_sair_mais_cedo_encurta_e_a_volta_acompanha(self):
        la = self._cafe()
        antes = [p.texto for p in la.passos]
        agora = la.inicio + (la.fim - la.inicio) / 2
        info = self.r.interromper(agora, "tedio")
        self.assertIsNotNone(info)
        self.assertNotIn("uber", info, "tédio volta como veio")
        etapas = Agenda(self.db).etapas(T.date(), agora)
        la2 = next(e for e in etapas if e.tipo == "la")
        volta = next(e for e in etapas if e.tipo == "voltando")
        self.assertEqual(la2.fim, agora + timedelta(minutes=5))
        self.assertEqual(volta.inicio, la2.fim)
        self.assertEqual(volta.como, "A pé")
        self.assertEqual(la2.passos[-1].texto, "Saindo mais cedo, tédio")
        self.assertTrue(la2.passos[-1].aviso)
        self.assertFalse(any(p.aviso for p in volta.passos), "a volta fica limpa (Patrick, layout C)")
        self.assertTrue(all(p.texto in antes for p in la2.passos[:-1]), "nada novo no que já tinha pedido")
        self.assertIn("Saiu mais cedo", self._evento("interrupcao:%"))
        self.assertIsNone(self.r.interromper(agora + timedelta(minutes=1), "cansou"), "uma vez só")

    def test_card_layout_c(self):
        la = self._cafe()
        agora = la.inicio + (la.fim - la.inicio) / 2
        self.r.interromper(agora, "tedio")
        ag = Agenda(self.db)
        card = ag.card(agora + timedelta(minutes=1))           # ainda lá, saindo
        self.assertIn(["alert-circle", "Motivo", "Tédio"], card["grade"])
        volta = next(e for e in ag.etapas(T.date(), agora) if e.tipo == "voltando")
        card = ag.card(volta.inicio + timedelta(minutes=1))
        self.assertEqual(card["titulo"], "Voltando para casa")
        self.assertIn(["alert-circle", "Motivo", "Tédio"], card["grade"])
        item_la = next(i for i in card["linha"] if i["texto"] == la.titulo)
        self.assertEqual(item_la["passos"][0]["estado"], "aviso")
        self.assertRegex(item_la["passos"][0]["texto"], r"^Saiu \d+ minutos? antes$")

    def test_passando_mal_volta_de_uber_e_avisa_ele(self):
        la = self._cafe()
        agora = la.inicio + (la.fim - la.inicio) / 2
        info = self.r.interromper(agora, "passando_mal")
        self.assertTrue(info["uber"])
        volta = next(e for e in Agenda(self.db).etapas(T.date(), agora) if e.tipo == "voltando")
        self.assertEqual(volta.como, "Uber")
        self.assertIn("Voltou de uber", self._evento("interrupcao:%"))
        aviso = self.r.aviso_saida(agora + timedelta(minutes=1))
        self.assertEqual(aviso["motivo"], "passando_mal")
        from proactivity_service import ProactivityService
        with patch.object(ProactivityService, "saudade", return_value={"trigger": False}):
            self.assertEqual(ProactivityService(self.db).should_trigger(agora + timedelta(minutes=1)),
                             (True, "saiu_mais_cedo"))
        self.r.marca_aviso_enviado(agora + timedelta(minutes=2))
        self.assertIsNone(self.r.aviso_saida(agora + timedelta(minutes=3)), "avisa uma vez")

    def test_milo_e_desistir_da_academia_planejada(self):
        from academia import Planejada
        plano = {"inicio": (T + timedelta(hours=2)).isoformat(), "fim": (T + timedelta(hours=3)).isoformat(),
                 "onde": "rua"}
        self.db.set_estado_relacional("academia_json", json.dumps({T.date().isoformat(): plano}))
        with patch("academia.Academia.plano", Planejada.plano):
            llm = FakeLLM({"acao": "desistiu", "tipo": "academia", "quando": None, "motivo": "tá com cólica"})
            self.assertTrue(self.r.observe_conversa("desisti da academia hj", "vai treinar?", T, llm=llm))
        self.assertEqual(self._evento("desistiu:academia:%"), "Desistiu de sair pra academia hoje: tá com cólica.")
        llm = FakeLLM({"acao": "vai_fazer", "tipo": "milo", "quando": "agora", "motivo": "o Milo tava pedindo"})
        self.assertIsNotNone(self.r.observe_conversa("vou descer com ele", "o milo tá chorando?", T, llm=llm))
        self.assertEqual(self._evento("vontade:%:decidiu"),
                         "Combinou com o Patrick e saiu com o Milo pra Enseada: o Milo tava pedindo.")

    def test_iniciativa_num_compromisso_segue_o_celular(self):
        import bot
        for code, pode in (("OUT_SOLO", True), ("SOCIAL", True), ("CLASS", False), ("GYM", False), ("WORK", False)):
            with patch.object(bot.availability_service.policy, "_resolve_activity",
                              return_value=(code, "CONFIRMED_COMMITMENT", None, "fresh", True)):
                self.assertIs(bot._celular_na_mao(T), pode, code)

    def test_pix_dele_paga_o_uber(self):
        import financas
        from consumo import Consumo
        financas._save(self.db, financas._init({}, T))
        la = self._cafe()
        agora = la.inicio + (la.fim - la.inicio) / 2
        info = self.r.interromper(agora, "banheiro")
        volta = next(e for e in Agenda(self.db).etapas(T.date(), agora) if e.tipo == "voltando")
        Consumo(self.db).materialize(volta.fim)
        financas.materialize(self.db, volta.fim)
        depois_uber = financas._load(self.db)["saldo"]
        res = financas.receive_pix(self.db, info["uber"]["valor"], "", volta.fim + timedelta(minutes=5))
        self.assertEqual(res["kind"], "uber")
        self.assertEqual(financas._load(self.db)["saldo"], depois_uber + info["uber"]["valor"])
        self.assertEqual(financas.pix_turn_text(20, "pro uber, melhoras", res),
                         '[Pix de R$ 20 do Patrick — recado: "pro uber, melhoras"]', "o porquê é o recado dele")
        self.assertEqual(financas.receive_pix(self.db, 50, "", volta.fim + timedelta(minutes=6))["kind"], "presente")

    def test_talvez_interrompe_quando_passa_mal(self):
        la = self._cafe()
        agora = la.inicio + (la.fim - la.inicio) * 0.6
        with patch("emotion.EmotionEngine.feeling", return_value=sentir(discomfort=0.9)), \
                patch("agenda_reativa.random.Random.random", return_value=0.01):
            info = self.r.talvez(agora)
        self.assertEqual(info["motivo"], "passando_mal")

    def test_talvez_num_dia_normal_nao_faz_nada(self):
        la = self._cafe()
        agora = la.inicio + (la.fim - la.inicio) * 0.6
        with patch("emotion.EmotionEngine.feeling", return_value=sentir()), \
                patch("agenda_reativa.random.Random.random", return_value=0.2):
            self.assertIsNone(self.r.talvez(agora))

    def test_nao_larga_logo_no_comeco(self):
        la = self._cafe()
        with patch("emotion.EmotionEngine.feeling", return_value=sentir(discomfort=0.9)), \
                patch("agenda_reativa.random.Random.random", return_value=0.01):
            self.assertIsNone(self.r.talvez(la.inicio + timedelta(minutes=1)))

    # --------------------------------------------------------------- tesão --
    def test_tesao_se_tranca_no_banheiro(self):
        from emotion import RELEASE_KEY
        from world_state import WorldStateManager
        with patch("vontade.random.Random.random", return_value=0.0), \
                patch("vontade.random.Random.choices", side_effect=lambda pop, weights=None: ["shopping"]):
            Vontade(self.db).talvez(T)
        la = next(e for e in Agenda(self.db).etapas(T.date(), T) if e.tipo == "la")
        agora = la.inicio + timedelta(minutes=30)
        p = self.r.pausar(agora, "tesao", chama_ele=True)
        self.assertEqual(p["onde"], "no banheiro do shopping")
        snap = WorldStateManager(self.db).resolve(agora + timedelta(minutes=2), force=True)
        self.assertTrue(snap["activity"].startswith("trancada no banheiro do shopping"), snap["activity"])
        self.assertEqual(classe_disponibilidade(snap["activity"]), "HOME_RELAXING")
        self.assertEqual(classe_disponibilidade("trancada no banheiro do shopping, se tocando"), "SOLO")
        self.assertTrue(self.db.get_estado_relacional(RELEASE_KEY))
        from tempo_livre import convite_sexting
        self.assertEqual(convite_sexting(self.db, agora + timedelta(minutes=1))["onde"], "no banheiro do shopping")
        passos = [q.texto for q in next(e for e in Agenda(self.db).etapas(T.date(), agora) if e.tipo == "la").passos]
        self.assertIn("Se masturbando no banheiro", passos)
        depois = WorldStateManager(self.db).resolve(datetime.fromisoformat(p["fim"]) + timedelta(minutes=1), force=True)
        self.assertFalse(depois["activity"].startswith("trancada"), "volta pro que fazia")

    def test_tesao_volta_correndo_pra_casa(self):
        la = self._cafe()
        agora = la.inicio + (la.fim - la.inicio) * 0.5
        with patch("emotion.EmotionEngine.feeling", return_value=sentir(libido=0.99)), \
                patch("agenda_reativa.random.Random.random", side_effect=itertools.chain([0.01], itertools.repeat(0.9))):
            info = self.r.talvez(agora)                 # sorteio, e não vai pro banheiro: vai pra casa
        self.assertEqual(info["motivo"], "tesao")
        volta = next(e for e in Agenda(self.db).etapas(T.date(), agora) if e.tipo == "voltando")
        self.assertIsNone(self.r.alivio_em_casa(volta.fim - timedelta(minutes=1)))
        self.assertIs(self.r.alivio_em_casa(volta.fim + timedelta(minutes=1)), False)
        self.assertIsNone(self.r.alivio_em_casa(volta.fim + timedelta(minutes=2)), "consumido")

    # --------------------------------------------------------------- aula --
    def test_sai_no_meio_da_aula_e_as_seguintes_caem(self):
        from academic_life import AcademicLife
        dia = next(T.date() + timedelta(days=d) for d in range(1, 8)
                   if len(AcademicLife(self.db).blocks_on(T.date() + timedelta(days=d))) >= 2)
        blocos = AcademicLife(self.db).blocks_on(dia)
        b0 = blocos[0]
        ini, fim = datetime.fromisoformat(b0["start_at"]), datetime.fromisoformat(b0["end_at"])
        agora = ini + (fim - ini) * 0.6
        c = next(c for c in Agenda(self.db)._compromissos(dia) if c["tipo"] == "faculdade")
        self.assertIsNotNone(self.r.interromper(agora, "banheiro", c=c))
        depois = AcademicLife(self.db).blocks_on(dia)
        self.assertEqual(len(depois), 1)
        self.assertEqual(datetime.fromisoformat(depois[0]["end_at"]), agora + timedelta(minutes=2))
        volta = next(e for e in Agenda(self.db).etapas(dia, agora) if e.tipo == "voltando")
        self.assertEqual(volta.inicio, agora + timedelta(minutes=2))


if __name__ == "__main__":
    unittest.main()
