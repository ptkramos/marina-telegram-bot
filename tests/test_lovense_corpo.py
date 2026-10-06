"""Lovense, passo 5a (Patrick, 05/10): corpo e mundo.

Ele pede e ela topa ou recusa pelo que sente; a palavra ela puxa e, dita na fala dela, faz ele ter que parar;
ela coloca e tira quando fala que colocou/tirou; o corpo goza quando chega lá; o Lush dentro dela não incomoda
(ela só tira por motivo de verdade); o Hush é descoberta dela e usar fora de casa é ousadia que cresce; com o app
parado e a ideia sendo dela, ela cutuca.
"""
import json
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from lovense import DESCOBERTA_KEY, PENDENTE_KEY, _tem_palavra
from tests.test_lovense import LovenseBase, T0, s, sentindo


class FalsoLLM:
    """Modelo barato de mentira: devolve o JSON combinado e guarda o prompt."""

    def __init__(self, resposta: dict):
        self.resposta, self.prompts = resposta, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.prompts.append(kw["messages"][0]["content"])
        msg = SimpleNamespace(content=json.dumps(self.resposta))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def ep(family, kind, intensity, cause, target="o Patrick"):
    return SimpleNamespace(family=family, kind=kind, intensity=intensity, cause=cause, target=target, word=kind)


def com(**f):
    episodes = f.pop("episodes", [])
    x = sentindo(**f)
    x.episodes, x.valence, x.social_battery = episodes, 0.62, 0.7
    return x


class PalavraTests(unittest.TestCase):
    def test_so_a_palavra_conta(self):
        self.assertTrue(_tem_palavra("ABACAXI!!", "abacaxi"))
        self.assertFalse(_tem_palavra("para para para", "abacaxi"))
        self.assertFalse(_tem_palavra("a palavra hoje é abacaxi", "abacaxi"), "falar DA palavra não é dizer")
        self.assertFalse(_tem_palavra("abacaxi, bobo", "abacaxi", "qual é a palavra mesmo?"))
        self.assertFalse(_tem_palavra("abacaxizinho", "abacaxi"))


class ConversaTests(LovenseBase):
    def test_ela_coloca_quando_fala_e_a_palavra_combinada_vale(self):
        llm = FalsoLLM({"colocou": [], "tirou": [], "palavra": "abacaxi", "liberou": False, "ideia": "dele",
                        "conversaram": False})
        self.assertEqual(self.lv.observe_conversa("tá, mas a palavra é abacaxi", "usa o lush pra mim?", s(0),
                                                  atividade="HOME_RELAXING", llm=llm), ["palavra"])
        self.assertFalse(self.lv.estado(s(1))["conectada"])
        llm.resposta = {"colocou": ["lush"], "quando": "agora", "tirou": [], "palavra": None, "liberou": False,
                        "ideia": "dele", "conversaram": False}
        self.assertEqual(self.lv.observe_conversa("pronto, coloquei", "", s(60), atividade="HOME_RELAXING",
                                                  llm=llm), ["colocou"])
        est = self.lv.estado(s(61))
        self.assertTrue(est["conectada"])
        self.assertEqual(est["palavra"], "abacaxi")
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT origem FROM lovense_sessoes").fetchone()[0], "pedido")
        # Dizer a palavra na fala dela: ele tem que parar (sem modelo).
        self.assertEqual(self.lv.observe_conversa("ABACAXI", "", s(120), atividade="HOME_RELAXING",
                                                  llm=FalsoLLM({})), ["pediu_parar"])
        self.assertEqual(self.lv.estado(s(121))["aviso"], "pediu_parar")

    def test_sem_falar_de_brinquedo_nao_chama_o_modelo(self):
        llm = FalsoLLM({"colocou": ["lush"]})
        self.assertEqual(self.lv.observe_conversa("vou colocar a roupa e já desço", "bora?", s(0), llm=llm), [])
        self.assertEqual(llm.prompts, [])

    def test_vou_colocar_em_casa_acende_daqui_a_pouco(self):
        llm = FalsoLLM({"colocou": ["lush"], "quando": "daqui_a_pouco", "ideia": "dela"})
        self.assertEqual(self.lv.observe_conversa("peraí que vou colocar o lush", "", s(0),
                                                  atividade="HOME_RELAXING", llm=llm), ["vai_colocar"])
        self.assertFalse(self.lv.estado(s(30))["conectada"])
        self.assertEqual(self.lv.pendentes(s(30), "HOME_RELAXING"), [])
        self.assertEqual(self.lv.pendentes(s(130), "HOME_RELAXING"), ["colocou"])
        self.assertTrue(self.lv.estado(s(131))["conectada"])
        self.assertFalse(self.lv.tem_pendente())

    def test_fora_de_casa_sem_o_brinquedo_na_bolsa_nao_coloca(self):
        llm = FalsoLLM({"colocou": ["lush"], "quando": "agora"})
        self.assertEqual(self.lv.observe_conversa("coloquei o lush", "", s(0), atividade="CLASS", llm=llm), [])
        self.assertFalse(self.lv.estado(s(1))["conectada"])

    def test_tirar_em_casa_e_a_conversa_que_reconstroi(self):
        self.lv.colocar(T0, ["lush"])
        llm = FalsoLLM({"colocou": [], "tirou": ["lush"]})
        self.assertEqual(self.lv.observe_conversa("tirei, amor", "", s(10), atividade="HOME_RELAXING", llm=llm),
                         ["tirou"])
        self.assertFalse(self.lv.estado(s(11))["conectada"])
        self.lv._abrir_pendencia(s(20))
        llm = FalsoLLM({"conversaram": True})
        feito = self.lv.observe_conversa("tá, eu te desculpo, mas me magoou", "desculpa por aquilo, errei", s(30),
                                         llm=llm)
        self.assertEqual(feito, ["conversou:fechou"])
        self.assertIsNone(self.lv.pendencia(s(31)))


class DisposicaoTests(LovenseBase):
    def disp(self, quais=("lush",), atividade="HOME_RELAXING", **f):
        with patch("lovense._feeling", return_value=com(**f)):
            return self.lv.disposicao(s(0), quais, atividade, feeling=com(**f))

    def test_tesao_topa_sem_clima_nao(self):
        self.assertTrue(self.disp(libido=0.8)["topa"])
        d = self.disp(libido=0.2)
        self.assertFalse(d["topa"])
        self.assertEqual(d["motivo"], "sem clima")

    def test_pendencia_recusa_mesmo_com_tesao(self):
        self.lv._abrir_pendencia(s(0))
        d = self.disp(libido=0.95)
        self.assertFalse(d["topa"])
        self.assertIn("conversarem", d["motivo"])

    def test_fora_de_casa_ficou_em_casa(self):
        d = self.disp(atividade="CLASS", libido=0.9)
        self.assertFalse(d["topa"])
        self.assertEqual(d["impossivel"], "o Lush ficou em casa")

    def test_hush_pede_mais(self):
        self.assertTrue(self.disp(("lush",), libido=0.7)["topa"])
        self.assertFalse(self.disp(("hush",), libido=0.7)["topa"], "receio: só com muito tesão")
        self.assertTrue(self.disp(("hush",), libido=0.95)["topa"])
        self.db.set_estado_relacional(DESCOBERTA_KEY, json.dumps({"hush": {"vezes": 2, "gosto": 0.05,
                                                                           "nao_e_pra_mim": True}}))
        d = self.disp(("hush",), libido=1.0)
        self.assertFalse(d["topa"])
        self.assertIn("não curtiu", d["motivo"])

    def test_briga_com_ele_baixa_a_vontade(self):
        d = self.disp(libido=0.7, episodes=[ep("raiva", "irritacao", 0.6, "ele esqueceu o aniversário")])
        self.assertLess(d["vontade"], self.disp(libido=0.7)["vontade"])


class CorpoTests(LovenseBase):
    def test_o_corpo_goza_e_vira_mundo(self):
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(s(5), "lush", 8)          # na aula, médio: gostoso (o forte já incomodaria)
        with patch("lovense._feeling", return_value=sentindo(libido=0.9)), \
                patch.object(self.lv, "estimular", return_value=0.95):
            eventos = self.lv.tick(s(20), atividade="CLASS")
        self.assertIn("gozou", eventos)
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'lovense:gozo:%'").fetchone()
            climax = conn.execute("SELECT climax_at FROM intimacy_state WHERE id=1").fetchone()
        self.assertIn("no meio da aula", row["summary"])
        self.assertTrue(climax and climax["climax_at"])
        t = self.lv.sentir(s(21), eventos, "CLASS")
        self.assertIn("você gozou agora", t["texto"])
        self.assertIn("tentando disfarçar", t["texto"])
        # Sensível: não goza de novo em seguida.
        with patch("lovense._feeling", return_value=sentindo(libido=0.9)), \
                patch.object(self.lv, "estimular", return_value=0.95):
            self.assertNotIn("gozou", self.lv.tick(s(60), atividade="CLASS"))

    def test_o_lush_parado_nao_incomoda_ela_fica(self):
        self.lv.colocar(T0, ["lush"])
        with patch("lovense._feeling", return_value=com(libido=0.5)):
            for m in range(0, 180, 10):
                self.assertEqual(self.lv.tick(T0 + timedelta(minutes=m), atividade="HOME_RELAXING"), [])
        self.assertTrue(self.lv.estado(T0 + timedelta(hours=3))["conectada"])

    def test_tira_pra_treinar_e_pra_dormir(self):
        self.lv.colocar(T0, ["lush"])
        with patch("lovense._feeling", return_value=com()):
            self.assertEqual(self.lv.tick(s(10), atividade="GYM"), ["tirou_academia"])
        self.assertFalse(self.lv.estado(s(11))["conectada"])
        self.lv.guardar(s(20), "lush")
        self.lv.colocar(s(30), ["lush"])
        with patch("lovense._feeling", return_value=com()):
            self.assertEqual(self.lv.tick(s(40), atividade="SLEEPING"), ["tirou_dormir"])

    def test_briga_por_outra_coisa_tira_o_clima(self):
        self.lv.colocar(T0, ["lush"])
        with patch("lovense._feeling", return_value=com(episodes=[ep("tristeza", "decepcao", 0.6,
                                                                     "ele sumiu o dia todo")])):
            eventos = self.lv.tick(s(10), atividade="HOME_RELAXING")
        self.assertEqual(eventos, ["tirou_briga"])
        self.assertIn("perdeu o clima", self.lv.sentir(s(11), eventos, "HOME_RELAXING")["texto"])

    def test_saudade_dele_nao_e_briga(self):
        # Achado na pré-visualização (05/10): a saudade (tristeza com ele) fazia ela tirar "porque perdeu o clima".
        self.lv.colocar(T0, ["lush"])
        with patch("lovense._feeling", return_value=com(episodes=[ep("tristeza", "saudade", 0.7, "longe dele")])):
            self.assertEqual(self.lv.tick(s(10), atividade="HOME_RELAXING"), [])
        self.assertTrue(self.lv.estado(s(11))["conectada"])


class DescobertaTests(LovenseBase):
    def test_hush_cansa_no_comeco_e_a_vez_boa_vira_gosto(self):
        self.lv.colocar(T0, ["lush", "hush"])
        self.lv.comando(T0, "hush", 3)
        with patch("lovense._feeling", return_value=com(libido=0.6)):
            for m in range(0, 10):
                for seg in range(0, 60, 10):
                    self.lv.tick(T0 + timedelta(minutes=m, seconds=seg + 5), atividade="HOME_RELAXING")
            eventos = self.lv.tick(T0 + timedelta(minutes=10, seconds=5), atividade="HOME_RELAXING")
        self.assertEqual(eventos, ["tirou_hush"], "receio: uns 10 min e ela tira o Hush")
        est = self.lv.estado(T0 + timedelta(minutes=11))
        self.assertTrue(est["conectada"], "o Lush continua")
        d = self.lv._descoberta()
        self.assertEqual(d["hush"]["vezes"], 1)
        self.assertGreater(d["hush"]["gosto"], 0.2)
        self.assertEqual(self.lv.estagio_hush(d), "descobrindo")
        with self.db.get_connection() as conn:
            self.assertIn("gostou mais do que esperava", conn.execute(
                "SELECT summary FROM life_events WHERE event_key LIKE 'lovense:hush:%'").fetchone()[0])
        self.assertIn("tirou", self.lv.sentir(T0 + timedelta(minutes=11), eventos, "HOME_RELAXING")["texto"])

    def test_duas_vezes_ruins_nao_e_pra_ela(self):
        for vez in range(2):
            t = T0 + timedelta(hours=3 * vez)
            self.lv.colocar(t, ["hush"])
            self.lv.comando(t, "hush", 20)
            with patch("lovense._feeling", return_value=com(libido=0.3)):
                for seg in range(5, 125, 10):
                    self.lv.tick(t + timedelta(seconds=seg), atividade="HOME_RELAXING")
            self.lv.tirar(t + timedelta(minutes=3))
            self.lv.guardar(t + timedelta(minutes=4), "hush")
        d = self.lv._descoberta()
        self.assertEqual(self.lv.estagio_hush(d), "nao_e_pra_mim")

    def test_ousadia_so_anda_quando_usou_fora(self):
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0, "lush", 3)
        with patch("lovense._feeling", return_value=com(libido=0.6)):
            for seg in range(5, 185, 10):
                self.lv.tick(T0 + timedelta(seconds=seg), atividade="HOME_RELAXING")
        self.lv.tirar(T0 + timedelta(minutes=4))
        self.assertEqual(self.lv._descoberta()["fora"]["vezes"], 0)
        self.lv.colocar(T0 + timedelta(hours=1), ["lush"])
        self.lv.comando(T0 + timedelta(hours=1), "lush", 3)
        with patch("lovense._feeling", return_value=com(libido=0.6)):
            for seg in range(5, 185, 10):
                self.lv.tick(T0 + timedelta(hours=1, seconds=seg), atividade="CLASS")
        self.lv.tirar(T0 + timedelta(hours=1, minutes=4), em_casa=False)
        d = self.lv._descoberta()["fora"]
        self.assertEqual(d["vezes"], 1)
        self.assertGreater(d["ousadia"], 0)


class ParadoTests(LovenseBase):
    def test_a_ideia_foi_dela_e_ele_sumiu_ela_cutuca(self):
        self.lv.colocar(T0, ["lush"], origem="dela")
        with patch("lovense._feeling", return_value=com(libido=0.5)):
            self.assertIsNone(self.lv.sentir(T0 + timedelta(minutes=10), [], "HOME_RELAXING"))
            t = self.lv.sentir(T0 + timedelta(minutes=19), [], "HOME_RELAXING")
            self.assertEqual(t["motivo"], "parado")
            self.assertIn("a ideia foi sua", t["texto"])
            self.assertIsNone(self.lv.sentir(T0 + timedelta(minutes=30), [], "HOME_RELAXING"))
            self.assertEqual(self.lv.sentir(T0 + timedelta(minutes=50), [], "HOME_RELAXING")["motivo"], "parado")
            self.assertIsNone(self.lv.sentir(T0 + timedelta(minutes=90), [], "HOME_RELAXING"), "cutuca 2 vezes")

    def test_pedido_dele_ela_espera_sem_cutucar(self):
        self.lv.colocar(T0, ["lush"], origem="pedido")
        with patch("lovense._feeling", return_value=com(libido=0.5)):
            self.assertIsNone(self.lv.sentir(T0 + timedelta(minutes=40), [], "HOME_RELAXING"))
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT kind, cause FROM emotion_episodes WHERE source_key LIKE 'lovense:colocou:%'"
                               ).fetchone()
        self.assertEqual(row["kind"], "expectativa")
        self.assertIn("sem saber quando", row["cause"])


class PromptTests(LovenseBase):
    def test_sem_sessao_so_quando_fala_de_brinquedo(self):
        with patch("lovense._feeling", return_value=com(libido=0.6)):   # sem vontade de propor (passo 5b)
            self.assertIsNone(self.lv.prompt(s(0), "HOME_RELAXING", "e aí, como foi a aula?"))
        with patch("lovense._feeling", return_value=com(libido=0.8)):
            p = self.lv.prompt(s(0), "HOME_RELAXING", "usa o lush pra mim?")
        self.assertIn("Se ele pedir pra você usar o Lush agora: você topa", p)
        self.assertIn("você puxa", p)
        self.assertIn("nunca usou: curiosa e com medo", p)

    def test_com_sessao_na_aula_escondido(self):
        self.lv.colocar(T0, ["lush"])
        self.lv.combinar_palavra(T0, "abacaxi")
        self.lv.comando(s(5), "lush", 6)
        with patch("lovense._feeling", return_value=com(libido=0.6)):
            p = self.lv.prompt(s(10), "CLASS", "")
        self.assertIn("Palavra de segurança desta vez: \"abacaxi\"", p)
        self.assertIn("no meio da aula", p)
        self.assertIn("nada de cama, gaveta", p)
        self.assertIn("só no banheiro do lugar", p)

    def test_sem_palavra_ela_puxa(self):
        self.lv.colocar(T0, ["lush"])
        with patch("lovense._feeling", return_value=com()):
            self.assertIn("ainda não combinaram a palavra", self.lv.prompt(s(10), "HOME_RELAXING", ""))


if __name__ == "__main__":
    unittest.main()


class EntregaTests(LovenseBase):
    """05/10 (Patrick): ele encomendou e avisa no chat quando chegar; até lá ela sabe que vem, mas não tem."""

    def test_a_caminho_ele_avisa_portaria_e_recebe(self):
        from lovense import CARGA_DE_FABRICA
        self.lv.encomendar(T0, ate=T0 + timedelta(hours=2))
        with self.assertRaises(ValueError):
            self.lv.colocar(s(10), ["lush"])
        self.assertEqual(self.lv.disposicao(s(10), ["lush"], feeling=com(libido=0.9))["impossivel"],
                         "ainda não chegou (o Patrick encomendou)")
        with patch("lovense._feeling", return_value=com()):
            p = self.lv.prompt(s(10), "HOME_RELAXING", "e aí")
        self.assertIn("Ainda não chegaram", p)
        self.assertFalse(self.lv.observe_patrick("o lovense tá chegando", s(20)), "tá chegando ainda não é chegou")
        self.assertTrue(self.lv.observe_patrick("chegou! desce pra pegar", s(30)))
        self.assertIsNone(self.lv.entrega_tick(s(60), pode_pegar=True))
        self.assertEqual(self.lv.entrega_tick(s(240), pode_pegar=False, por_que="banho"), "portaria")
        with patch("lovense._feeling", return_value=com()):
            self.assertIn("portaria com o Seu Jorge", self.lv.prompt(s(250), "SHOWER", ""))
        self.assertIsNone(self.lv.entrega_tick(s(300), pode_pegar=False, por_que="banho"))
        self.assertEqual(self.lv.entrega_tick(s(600), pode_pegar=True), "recebido")
        est = self.lv.estado(s(601))
        for b in est["brinquedos"]:
            self.assertEqual(b["onde"], "carregador")
            self.assertGreaterEqual(b["bateria"], CARGA_DE_FABRICA)
        self.assertEqual(self.lv.entrega_a_anunciar()["esperou"], "banho")
        self.lv.marcar_anunciada()
        self.assertIsNone(self.lv.entrega_a_anunciar())
        with self.db.get_connection() as conn:
            self.assertIn("tinha ficado na portaria", conn.execute(
                "SELECT summary FROM life_events WHERE event_key LIKE 'lovense:entrega:%'").fetchone()[0])
        self.lv.colocar(s(700), ["lush"])
        self.assertTrue(self.lv.estado(s(701))["conectada"])

    def test_sem_aviso_chega_no_horario(self):
        self.lv.encomendar(T0, ate=T0 + timedelta(hours=1))
        self.assertIsNone(self.lv.entrega_tick(T0 + timedelta(minutes=59), pode_pegar=True))
        self.assertEqual(self.lv.entrega_tick(T0 + timedelta(hours=1), pode_pegar=True), "recebido")
