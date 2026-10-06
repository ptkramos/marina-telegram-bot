"""Lovense, passo 5b (Patrick, 05/10, noite): ela mesma.

Ela propõe pela vontade (tesão, ocasião, confiança e, no Hush, a curiosidade; a novidade cansa; depois de propor
ela espera, mais se ele deixou passar), por mensagem dela ou dentro da conversa; joga o Lush na bolsa quando sai
pra algo longo e "pode rolar" (conta ou leva calada, pelo que sente); usa sozinha no tempo livre; a opinião do
Hush volta à curiosidade (a Bia, ele com carinho, o tempo; insistir afasta); a amiga do lado percebe o gozo.
"""
import json
from datetime import timedelta
from unittest.mock import patch

from lovense import (AMIGAS_KEY, BOLSA_KEY, DESCOBERTA_KEY, PROPOSTA_KEY, SOZINHA_KEY, VONTADE_KEY)
from tests.test_lovense import LovenseBase, T0, s
from tests.test_lovense_corpo import FalsoLLM, com

SAIDA = {"key": "ida:quartinho", "destino": "o Quartinho Bar", "inicio": T0, "longa": True, "saindo": True}
NAO_E_PRA_MIM = {"hush": {"vezes": 2, "gosto": 0.05, "nao_e_pra_mim": True, "nao_desde": T0.isoformat()}}


class Base(LovenseBase):
    def vontade(self, atividade="HOME_RELAXING", quando=None, **f):
        with patch("lovense._feeling", return_value=com(**f)):
            return self.lv.vontade_de_propor(quando or s(0), atividade, feeling=com(**f))

    def onde(self, b):
        return next(x for x in self.lv.estado(s(1))["brinquedos"] if x["nome"] == b)["onde"]


class ProporTests(Base):
    def test_em_casa_com_tesao_propoe_sem_tesao_nao(self):
        v = self.vontade(libido=0.72)
        self.assertTrue(v["quer"])
        self.assertEqual((v["brinquedos"], v["ocasiao"]), (["lush"], "em_casa"))
        self.assertFalse(self.vontade(libido=0.55)["quer"])

    def test_bom_humor_sem_tesao_nao_propoe(self):
        """Achado com o banco da produção (05/10, 22:58): diversão 0,95 e empolgada com ele, libido 0,63 — a
        disposicao dava 1,0 e ela propunha até o Hush no receio. Propor é do tesão; o Hush no receio, da curiosidade."""
        from tests.test_lovense_corpo import ep
        feliz = [ep("alegria", "diversao", 0.95, "o Patrick brincou"), ep("alegria", "empolgacao", 0.5, "ele")]
        self.lv.colocar(T0 - timedelta(days=2), ["lush"])     # já usou: a novidade passou
        self.lv.tirar(T0 - timedelta(days=2) + timedelta(minutes=30))
        self.assertFalse(self.vontade(libido=0.63, episodes=feliz)["quer"])
        v = self.vontade(libido=0.7, episodes=feliz)
        self.assertEqual(v["brinquedos"], ["lush"], "o Hush no receio não vem da empolgação")

    def test_lush_nunca_usado_a_vontade_de_testar(self):
        self.assertTrue(self.vontade(libido=0.6, energia=0.9)["quer"])

    def test_so_nas_ocasioes(self):
        self.assertFalse(self.vontade("HOME_BUSY", libido=0.9)["quer"], "ocupada em casa não é ocasião")
        manha = T0.replace(hour=8)
        self.assertEqual(self.vontade("WAKING", quando=manha, libido=0.8)["ocasiao"], "acordando")
        self.assertFalse(self.vontade("CLASS", libido=0.9)["quer"], "na aula sem nada na bolsa")

    def test_pendencia_nao_propoe(self):
        self.lv._abrir_pendencia(s(0))
        self.assertFalse(self.vontade(libido=0.95)["quer"])

    def test_depois_de_propor_espera_mais_se_ele_deixou_passar(self):
        self.lv._marcar_proposta(T0, "iniciativa", ["lush"])
        self.assertFalse(self.vontade(quando=T0 + timedelta(hours=5), libido=0.9)["quer"])
        self.assertTrue(self.vontade(quando=T0 + timedelta(hours=13), libido=0.9)["quer"])
        # Ele topou (sessão aberta logo depois): 4 h bastam.
        self.lv.colocar(s(600), ["lush"])
        self.lv.tirar(s(1200))
        self.assertTrue(self.vontade(quando=T0 + timedelta(hours=5), libido=0.9)["quer"])

    def test_hush_pela_curiosidade_com_tesao_alto(self):
        self.assertEqual(self.vontade(libido=0.72)["brinquedos"], ["lush"])
        v = self.vontade(libido=0.9)
        self.assertEqual(v["brinquedos"], ["hush"])
        self.assertIn("curiosa", v["motivo"])
        self.db.set_estado_relacional(DESCOBERTA_KEY, json.dumps(NAO_E_PRA_MIM))
        self.assertEqual(self.vontade(libido=0.95)["brinquedos"], ["lush"], "não é pra mim: nunca o Hush")

    def test_gostando_os_dois_juntos(self):
        self.db.set_estado_relacional(DESCOBERTA_KEY, json.dumps({"hush": {"vezes": 4, "gosto": 0.6}}))
        self.assertEqual(self.vontade(libido=0.9)["brinquedos"], ["lush", "hush"])

    def test_fora_com_o_lush_na_bolsa(self):
        self.lv.levar_na_bolsa(T0, "lush")
        v = self.vontade("CLASS", libido=0.9)
        self.assertTrue(v["quer"])
        self.assertEqual((v["brinquedos"], v["ocasiao"]), (["lush"], "fora_bolsa"))
        with patch("lovense._feeling", return_value=com(libido=0.9)):
            p = self.lv.proposta(s(0), "CLASS")
        self.assertIn("bolsa", p["detail"])
        self.assertIn("banheiro", p["detail"])

    def test_antes_de_sair_pra_algo_longo(self):
        with patch.object(self.lv, "_saida", return_value=dict(SAIDA, saindo=False)), \
                patch("lovense._feeling", return_value=com(libido=0.95)):
            v = self.lv.vontade_de_propor(s(0), "GETTING_READY", feeling=com(libido=0.95))
            p = self.lv.proposta(s(0), "GETTING_READY")
        self.assertEqual((v["ocasiao"], v["brinquedos"]), ("antes_de_sair", ["lush"]),
                         "o Hush no receio não sai de casa")
        self.assertIn("o Quartinho Bar", p["detail"])
        with patch.object(self.lv, "_saida", return_value=dict(SAIDA, longa=False)):
            self.assertFalse(self.lv.vontade_de_propor(s(0), "GETTING_READY", feeling=com(libido=0.95))["quer"])

    def test_na_conversa_o_prompt_puxa_e_falar_do_brinquedo_e_a_proposta(self):
        with patch("lovense._feeling", return_value=com(libido=0.8)):
            bloco = self.lv.prompt(s(0), "HOME_RELAXING", "oi amor, tudo bem?")
        self.assertIn("vontade de usar o Hush", bloco)
        self.assertIn("não insista", bloco)
        with patch("lovense._feeling", return_value=com(libido=0.55)):
            self.assertIsNone(self.lv.prompt(s(1), "HOME_RELAXING", "oi amor, tudo bem?"))
        feito = self.lv.observe_conversa("tô pensando no hush aqui 👀", "oi", s(30), atividade="HOME_RELAXING",
                                         llm=FalsoLLM({}))
        self.assertIn("propos", feito)
        self.assertEqual(json.loads(self.db.get_estado_relacional(PROPOSTA_KEY))["como"], "conversa")
        self.assertFalse(self.db.get_estado_relacional(VONTADE_KEY))


class BolsaTests(Base):
    def rotina(self, libido, atividade="COMMUTE", saida=SAIDA, quando=None):
        with patch.object(self.lv, "_saida", return_value=saida), \
                patch("lovense._feeling", return_value=com(libido=libido)):
            return self.lv.rotina(quando or s(0), atividade)

    def test_com_muita_vontade_leva_e_conta(self):
        out = self.rotina(0.9)
        self.assertEqual(self.onde("lush"), "bolsa")
        self.assertIn("bolsa", out["contar"])
        self.lv.bolsa_contada(s(5))
        self.assertEqual(json.loads(self.db.get_estado_relacional(PROPOSTA_KEY))["como"], "bolsa")
        self.assertEqual(self.rotina(0.9, quando=s(60)), {}, "a mesma saída não decide de novo")

    def test_pode_rolar_leva_calada_e_o_prompt_sabe(self):
        self.assertEqual(self.rotina(0.75), {})
        self.assertEqual(self.onde("lush"), "bolsa")
        with patch("lovense._feeling", return_value=com(libido=0.5)):
            bloco = self.lv.prompt(s(10), "SOCIAL", "e aí, como tá o bar?")
        self.assertIn("ele ainda não sabe", bloco)
        self.lv.observe_conversa("adivinha quem veio comigo… o lush", "", s(20), atividade="SOCIAL",
                                 llm=FalsoLLM({}))
        self.assertTrue(json.loads(self.db.get_estado_relacional(BOLSA_KEY))["contou"])

    def test_sem_clima_nao_leva_e_em_casa_volta_pro_carregador(self):
        self.assertEqual(self.rotina(0.55), {})
        self.assertEqual(self.onde("lush"), "gaveta")
        self.lv.levar_na_bolsa(s(0), "lush")
        self.rotina(0.5, atividade="HOME_RELAXING", saida=None, quando=s(100))
        self.assertEqual(self.onde("lush"), "carregador")

    def test_saida_curta_nao_leva(self):
        self.rotina(0.95, saida=dict(SAIDA, longa=False))
        self.assertEqual(self.onde("lush"), "gaveta")


class SozinhaTests(Base):
    def sozinha(self, libido, chama_ele=False, quando=None):
        return self.lv.sozinha(quando or s(0), chama_ele, feeling=com(libido=libido))

    def test_primeiras_vezes_pela_curiosidade_depois_pelo_tesao(self):
        self.assertEqual(self.sozinha(0.78), ["lush"])
        self.db.set_estado_relacional(SOZINHA_KEY, json.dumps({"lush": 3}))
        self.assertEqual(self.sozinha(0.78), [])
        self.assertEqual(self.sozinha(0.78, chama_ele=True), ["lush"], "com saudade, chama ele pro app")

    def test_hush_sozinha_pela_curiosidade_vira_descoberta(self):
        self.assertEqual(self.sozinha(0.9), ["lush", "hush"])
        self.lv.usou_sozinha(s(0), s(1200), ["lush", "hush"], "livre:x", s(1200))
        d = json.loads(self.db.get_estado_relacional(DESCOBERTA_KEY))
        self.assertEqual(d["hush"]["vezes"], 1)
        self.assertGreater(d["hush"]["gosto"], 0.2)
        self.assertLess(self.bat("hush", s(1201)), 1.0)
        self.assertEqual(self.sozinha(0.9, quando=s(3600)), ["lush"], "o Hush sozinha: no máximo a cada 3 dias")
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'lovense:hush:sozinha%'"
                               ).fetchone()
        self.assertIn("sozinha, no controle dela", row["summary"])

    def test_sem_bateria_ou_na_bolsa_nao(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE lovense_brinquedos SET bateria=0.1")
            conn.commit()
        self.assertEqual(self.sozinha(0.95), [])


class HushOpiniaoTests(Base):
    def setUp(self):
        super().setUp()
        self.db.set_estado_relacional(DESCOBERTA_KEY, json.dumps(NAO_E_PRA_MIM))

    def estagio(self):
        return self.lv.estagio_hush(self.lv._descoberta())

    def test_a_bia_reacende_depois_de_dois_dias(self):
        self.assertEqual(self.lv.conversa_com_amiga(T0 + timedelta(days=1), "bia_andrade"), "")
        self.assertEqual(self.estagio(), "nao_e_pra_mim")
        self.assertEqual(self.lv.conversa_com_amiga(T0 + timedelta(days=1), "julia_azevedo"), "")
        extra = self.lv.conversa_com_amiga(T0 + timedelta(days=2, hours=1), "bia_andrade")
        self.assertIn("curiosa de novo", extra)
        self.assertEqual(self.estagio(), "descobrindo")
        with patch("lovense._feeling", return_value=com(libido=0.5)):
            bloco = self.lv.prompt(T0 + timedelta(days=3), "HOME_RELAXING", "e o hush?")
        self.assertIn("curiosa de novo (conversando com a Bia)", bloco)

    def test_ele_com_carinho_reabre_insistir_afasta(self):
        llm = FalsoLLM({"hush": "pressao"})
        self.assertIn("hush_pressao", self.lv.observe_conversa("já falei que não, amor", "usa o hush vai",
                                                               T0 + timedelta(hours=13), llm=llm))
        self.assertIn('"hush"', llm.prompts[0])
        self.assertEqual(self.estagio(), "nao_e_pra_mim")
        llm.resposta = {"hush": "carinho"}
        self.assertNotIn("hush_reabriu", self.lv.observe_conversa("hmm, talvez", "e o hush, sem pressão?",
                                                                  T0 + timedelta(hours=14), llm=llm),
                         "insistiu: o tempo recomeçou")
        self.assertIn("hush_reabriu", self.lv.observe_conversa("hmm, talvez", "e o hush, sem pressão?",
                                                               T0 + timedelta(hours=26), llm=llm))
        self.assertEqual(self.estagio(), "descobrindo")

    def test_ela_mesma_com_o_tempo(self):
        with patch("lovense._feeling", return_value=com(libido=0.8)):
            self.lv._curiosidade_com_o_tempo(T0 + timedelta(days=10))
            self.assertEqual(self.estagio(), "nao_e_pra_mim")
            self.lv._curiosidade_com_o_tempo(T0 + timedelta(days=22))
        self.assertEqual(self.estagio(), "descobrindo")


class AmigaTests(Base):
    def gozar(self, nivel, ousadia=0.0):
        d = self.lv._descoberta()
        d["fora"]["ousadia"] = ousadia
        self.db.set_estado_relacional(DESCOBERTA_KEY, json.dumps(d))
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO world_state(state_date, observed_at, activity, active_people_json)
                            VALUES (?, ?, 'Saindo com a Bia no Quartinho Bar', '["bia_andrade"]')""",
                         (T0.date().isoformat(), T0.isoformat()))
            conn.commit()
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(s(5), "lush", nivel)
        with patch("lovense._feeling", return_value=com(libido=0.95)), \
                patch.object(self.lv, "estimular", return_value=0.95):
            return self.lv.tick(s(20), atividade="SOCIAL")

    def test_nervosa_a_bia_percebe_e_ela_disfarca(self):
        eventos = self.gozar(6)
        self.assertIn("amiga:bia_andrade:disfarcou", eventos)
        t = self.lv.sentir(s(21), eventos, "SOCIAL")
        self.assertIn("a Bia estava do seu lado e percebeu", t["texto"])
        self.assertIn("disfarçou", t["texto"])
        self.assertIn("zoou ela", self.lv.conversa_com_amiga(T0 + timedelta(hours=20), "bia_andrade"))
        self.assertEqual(self.lv.conversa_com_amiga(T0 + timedelta(hours=22), "bia_andrade"), "", "zoa uma vez")

    def test_solta_e_fraquinho_ninguem_percebe(self):
        self.assertNotIn("amiga", " ".join(self.gozar(4, ousadia=0.6)))
        self.assertIsNone(self.db.get_estado_relacional(AMIGAS_KEY) or None)

    def test_solta_e_forte_conta_pra_bia(self):
        self.assertIn("amiga:bia_andrade:contou", self.gozar(14, ousadia=0.6))
