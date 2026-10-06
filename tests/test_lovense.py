"""Lovense pelo Mini App, passo 1 (PLANO_WEBAPP, "Lovense pelo Mini App — plano"; Patrick, 04–05/10).

Estado do brinquedo: bateria que gasta pelo nível e carrega em casa, palavra de segurança com prazo de 30 s,
escada (firme, bronca, corte) quando ele não para, e a confiança (`trust`) que só volta conversando.
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from db import DatabaseManager
from lovense import Lovense

T0 = datetime(2026, 10, 6, 14, 0)


def s(seg):
    return T0 + timedelta(seconds=seg)


class LovenseBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "lovense.db")
        with self.db.get_connection() as conn:
            conn.execute("UPDATE estado_emocional SET valor=0.8, baseline=0.8, updated_at=? WHERE chave='trust'",
                         (T0.isoformat(),))
            conn.execute("UPDATE lovense_brinquedos SET bateria=1.0, bateria_em=?, onde='gaveta'", (T0.isoformat(),))
            conn.commit()
        self.lv = Lovense(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def bat(self, b, when):
        return next(x for x in self.lv.estado(when)["brinquedos"] if x["nome"] == b)["bateria"]

    def trust(self, when):
        return self.lv.confianca(when)


class EstadoTests(LovenseBase):
    def test_migration_cria_brinquedos_e_confianca(self):
        self.assertEqual(self.db.get_schema_version(), 38)
        est = self.lv.estado(T0)
        self.assertFalse(est["conectada"])
        self.assertEqual(est["estado"], "desconectada")
        self.assertEqual([b["nome"] for b in est["brinquedos"]], ["lush", "hush"])
        self.assertAlmostEqual(self.trust(T0), 0.8, places=3)

    def test_inicio_limpo_devolve_os_brinquedos(self):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM lovense_brinquedos")
            conn.commit()
        est = self.lv.estado(T0)
        self.assertEqual([(b["nome"], b["onde"], b["bateria"]) for b in est["brinquedos"]],
                         [("lush", "gaveta", 1.0), ("hush", "gaveta", 1.0)])
        self.lv.colocar(T0, ["lush"])
        self.assertTrue(self.lv.estado(T0)["conectada"])

    def test_colocar_acende_e_comando_vale(self):
        self.lv.colocar(T0, ["lush"], lugar="marina_apartment")
        self.assertTrue(self.lv.estado(T0)["conectada"])
        r = self.lv.comando(s(5), "lush", 12)
        self.assertTrue(r["ok"])
        lush = self.lv.estado(s(6))["brinquedos"][0]
        self.assertEqual((lush["nivel"], lush["em_uso"], lush["onde"]), (12, True, "nela"))
        # O Hush não está nela: comando pra ele não vale.
        self.assertEqual(self.lv.comando(s(7), "hush", 5)["erro"], "brinquedo")

    def test_sem_sessao_o_app_nao_controla(self):
        self.assertEqual(self.lv.comando(T0, "lush", 10)["erro"], "desconectada")

    def test_os_dois_juntos_cada_um_a_parte(self):
        self.lv.colocar(T0, ["lush"])
        self.lv.colocar(s(60), ["hush"])
        self.lv.comando(s(70), "lush", 15)
        self.lv.comando(s(71), "hush", 4)
        niveis = {b["nome"]: b["nivel"] for b in self.lv.estado(s(72))["brinquedos"]}
        self.assertEqual(niveis, {"lush": 15, "hush": 4})
        self.lv.parar(s(80))
        self.assertEqual({b["nivel"] for b in self.lv.estado(s(81))["brinquedos"]}, {0})

    def test_fora_de_casa_so_com_o_brinquedo_na_bolsa(self):
        with self.assertRaises(ValueError):
            self.lv.colocar(T0, ["lush"], fora_de_casa=True)
        self.assertTrue(self.lv.levar_na_bolsa(T0, "lush"))
        self.lv.colocar(s(10), ["lush"], fora_de_casa=True, lugar="puc_rio")
        self.assertTrue(self.lv.estado(s(11))["fora_de_casa"])
        # Fora, tirar (no banheiro) devolve pra bolsa e encerra.
        self.assertIn("tirou", self.lv.tirar(s(600), em_casa=False))
        lush = self.lv.estado(s(601))["brinquedos"][0]
        self.assertEqual(lush["onde"], "bolsa")
        self.assertFalse(self.lv.estado(s(601))["conectada"])

    def test_padrao_precisa_de_nome_conhecido(self):
        self.lv.colocar(T0, ["lush"])
        self.assertEqual(self.lv.comando(s(1), "lush", 10, "padrao", "inventado")["erro"], "padrao")
        self.assertTrue(self.lv.comando(s(2), "lush", 10, "padrao", "onda")["ok"])


class BateriaTests(LovenseBase):
    def test_forte_gasta_mais_que_fraco(self):
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0, "lush", 20)
        forte = 1 - self.bat("lush", T0 + timedelta(minutes=30))
        self.tearDown()
        self.setUp()
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0, "lush", 4)
        fraco = 1 - self.bat("lush", T0 + timedelta(minutes=30))
        self.assertGreater(forte, 2.5 * fraco)
        self.assertAlmostEqual(forte, 0.25, places=2)      # nível 20 dura ~2 h

    def test_bateria_acaba_e_a_sessao_acaba(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE lovense_brinquedos SET bateria=0.10 WHERE brinquedo='lush'")
            conn.commit()
        self.lv.colocar(T0, ["lush"])
        self.lv.comando(T0, "lush", 20)                      # 0,10 / 0,50 por hora = 12 min
        est = self.lv.estado(T0 + timedelta(minutes=20))
        self.assertIn("sessao_acabou_bateria", est["eventos"])
        self.assertFalse(est["conectada"])
        self.assertEqual(est["brinquedos"][0]["bateria"], 0)
        with self.db.get_connection() as conn:
            fim = conn.execute("SELECT fim_em, motivo_fim FROM lovense_sessoes").fetchone()
        self.assertEqual(fim["motivo_fim"], "bateria")
        self.assertEqual(datetime.fromisoformat(fim["fim_em"]), T0 + timedelta(minutes=12))

    def test_tirou_em_casa_carrega(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE lovense_brinquedos SET bateria=0.30 WHERE brinquedo='lush'")
            conn.commit()
        self.lv.colocar(T0, ["lush"])
        self.lv.tirar(T0 + timedelta(minutes=1))
        self.assertGreater(self.bat("lush", T0 + timedelta(minutes=61)), 0.95)
        self.assertEqual(self.bat("lush", T0 + timedelta(hours=5)), 1.0)

    def test_sem_bateria_ela_nao_coloca(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE lovense_brinquedos SET bateria=0.02 WHERE brinquedo='hush'")
            conn.commit()
        with self.assertRaises(ValueError):
            self.lv.colocar(T0, ["hush"])


class PalavraTests(LovenseBase):
    def ligado(self, nivel=14):
        self.lv.colocar(T0, ["lush"])
        self.lv.combinar_palavra(T0, "abacaxi")
        self.lv.comando(s(5), "lush", nivel)

    def test_parou_dentro_dos_30s_a_confianca_sobe(self):
        self.ligado()
        self.assertIn("pediu_parar", self.lv.pedir_parar(s(10)))
        self.assertEqual(self.lv.estado(s(11))["aviso"], "pediu_parar")
        r = self.lv.parar(s(30))
        self.assertIn("respeitou", r["eventos"])
        self.assertGreater(self.trust(s(31)), 0.8)
        self.assertEqual(self.lv.tick(s(200)), [])           # nada de escada depois

    def test_nao_parou_firme_bronca_e_corte(self):
        self.ligado()
        self.lv.pedir_parar(s(10))
        self.assertEqual(self.lv.tick(s(30)), [])
        self.assertEqual(self.lv.tick(s(41)), ["firme"])
        self.assertAlmostEqual(self.trust(s(42)), 0.8, places=3)
        self.assertEqual(self.lv.tick(s(71)), ["bronca"])
        depois_bronca = self.trust(s(72))
        self.assertLess(depois_bronca, 0.75)
        self.assertEqual(self.lv.tick(s(101)), ["cortou"])
        est = self.lv.estado(s(102))
        self.assertFalse(est["conectada"])
        self.assertEqual(est["aviso"], "cortou")
        self.assertLess(self.trust(s(103)), depois_bronca)
        # Cortar não é tirar: o Lush continua nela.
        self.assertEqual(est["brinquedos"][0]["onde"], "nela")
        self.assertEqual(self.lv.comando(s(110), "lush", 5)["erro"], "desconectada")

    def test_sem_conseguir_mexer_no_celular_nao_corta(self):
        self.ligado()
        self.lv.pedir_parar(s(10))
        self.lv.tick(s(75))
        self.assertEqual(self.lv.tick(s(200), pode_mexer_no_celular=False), [])
        self.assertTrue(self.lv.estado(s(201))["conectada"])
        self.assertEqual(self.lv.tick(s(300)), ["cortou"])

    def test_parou_tarde_custa_um_pouco(self):
        self.ligado()
        self.lv.pedir_parar(s(10))
        self.lv.tick(s(45))
        self.assertIn("parou_tarde", self.lv.parar(s(50))["eventos"])
        self.assertLess(self.trust(s(51)), 0.8)
        self.assertIsNone(self.lv.pendencia(s(51)))          # tarde não é briga

    def test_tick_atrasado_entrega_a_escada_toda(self):
        self.ligado()
        self.lv.pedir_parar(s(10))
        self.assertEqual(self.lv.tick(s(500)), ["firme", "bronca", "cortou"])

    def test_religar_depois_da_palavra_e_desrespeito(self):
        self.ligado()
        self.lv.pedir_parar(s(10))
        self.lv.parar(s(15))
        r = self.lv.comando(s(60), "lush", 10)
        self.assertIn("religou", r["eventos"])               # o prazo já passou: ela repete firme na hora
        self.assertEqual(self.lv.tick(s(61)), [])
        self.assertEqual(self.lv.tick(s(91)), ["bronca"])

    def test_ela_libera_e_o_controle_volta(self):
        self.ligado()
        self.lv.pedir_parar(s(10))
        self.lv.parar(s(12))
        self.assertTrue(self.lv.liberar(s(120)))
        self.assertEqual(self.lv.estado(s(121))["estado"], "conectada")
        self.lv.comando(s(130), "lush", 18)
        self.assertEqual(self.lv.tick(s(400)), [])

    def test_palavra_com_tudo_parado_nao_da_ponto(self):
        self.ligado(nivel=0)
        self.lv.pedir_parar(s(10))
        self.assertEqual(self.lv.tick(s(200)), [])
        self.assertAlmostEqual(self.trust(s(201)), 0.8, places=3)

    def test_repetir_a_palavra_nao_reinicia_o_prazo(self):
        self.ligado()
        self.lv.pedir_parar(s(10))
        self.lv.pedir_parar(s(35))
        self.assertEqual(self.lv.tick(s(41)), ["firme"])


class ConfiancaTests(LovenseBase):
    def briga(self, inicio: datetime):
        self.lv.colocar(inicio, ["lush"])
        self.lv.comando(inicio, "lush", 15)
        self.lv.pedir_parar(inicio + timedelta(seconds=1))
        self.lv.tick(inicio + timedelta(seconds=120))
        self.lv.tirar(inicio + timedelta(minutes=10))

    def test_confianca_nao_volta_sozinha_com_pendencia(self):
        self.briga(T0)
        baixa = self.trust(T0 + timedelta(minutes=11))
        self.assertLess(baixa, 0.7)
        self.assertFalse(self.lv.pode_topar(T0 + timedelta(minutes=11)))
        self.assertAlmostEqual(self.trust(T0 + timedelta(days=20)), baixa, places=3)

    def test_conversa_fecha_e_ela_volta_a_relaxar(self):
        self.briga(T0)
        dia = T0 + timedelta(days=2)
        r = self.lv.conversar(dia)
        self.assertTrue(r["fechou"])
        self.assertTrue(self.lv.pode_topar(dia))
        logo = self.trust(dia)
        # Sem pendência, relaxa até o normal com meia-vida de 14 dias, contando a partir da conversa.
        self.assertGreater(self.trust(dia + timedelta(days=14)), logo)
        self.assertLess(self.trust(dia + timedelta(days=14)), 0.8)

    def test_mais_de_uma_vez_pede_mais_conversa(self):
        self.briga(T0)
        self.briga(T0 + timedelta(days=3))
        p = self.lv.pendencia(T0 + timedelta(days=3, hours=1))
        self.assertEqual((p["incidentes"], p["faltam"]), (2, 2))
        primeira = T0 + timedelta(days=4)
        self.assertEqual(self.lv.conversar(primeira), {"fechou": False, "faltam": 1})
        # A mesma conversa (minutos depois) não conta duas vezes.
        self.assertEqual(self.lv.conversar(primeira + timedelta(minutes=30)), {"fechou": False, "faltam": 1})
        self.assertFalse(self.lv.pode_topar(primeira + timedelta(hours=1)))
        self.assertTrue(self.lv.conversar(primeira + timedelta(days=1))["fechou"])

    def test_cortar_direto_ja_e_incidente(self):
        self.lv.colocar(T0, ["lush"])
        self.assertIn("cortou", self.lv.cortar(s(30)))
        self.assertEqual(self.lv.pendencia(s(31))["incidentes"], 1)
        self.assertLess(self.trust(s(31)), 0.8)

    def test_sem_pendencia_conversar_nao_faz_nada(self):
        self.assertIsNone(self.lv.conversar(T0))

    def test_reset_do_soak_limpa_o_lovense(self):
        self.briga(T0)
        self.db.reset_soak_learning()
        self.assertIsNone(self.lv.pendencia(T0))
        self.assertEqual(self.lv.sessoes_recentes(T0 + timedelta(days=1)), 0)


if __name__ == "__main__":
    unittest.main()


class SentirTests(LovenseBase):
    """Passo 3: o que ela sente vira turno só quando ela sente diferença (texto interno, nunca a fala dela)."""

    def setUp(self):
        super().setUp()
        self.lv.colocar(T0, ["lush"])

    def test_sem_comando_nao_ha_turno(self):
        self.assertIsNone(self.lv.sentir(s(5)))

    def test_ligou_vira_turno_e_a_rajada_vira_um_so(self):
        for i, n in enumerate((2, 4, 6, 8, 10, 12)):
            self.lv.comando(s(10 + i * 0.5), "lush", n)
        t = self.lv.sentir(s(16))
        self.assertEqual(t["motivo"], "mudou")
        self.assertTrue(t["texto"].startswith("[Brinquedo, pelo app do Patrick: Ele ligou o Lush"))
        self.assertIn("vibrando forte", t["texto"])
        self.assertIn("provocando", t["texto"])          # seis mexidas no clássico
        # Nada mudou desde o turno: nada a sentir.
        self.assertIsNone(self.lv.sentir(s(20)))

    def test_mexida_pequena_nao_vira_turno(self):
        self.lv.comando(s(10), "lush", 10)
        self.lv.sentir(s(15))
        self.lv.comando(s(80), "lush", 12)               # +2: ela nem nota
        self.assertIsNone(self.lv.sentir(s(85)))
        self.lv.comando(s(90), "lush", 14)               # +4 desde o último turno: sente
        self.assertIn("aumentou o Lush", self.lv.sentir(s(95))["texto"])

    def test_no_maximo_um_turno_a_cada_45_s_sem_perder_o_que_mudou(self):
        self.lv.comando(s(10), "lush", 10)
        self.lv.sentir(s(15))
        self.lv.comando(s(20), "lush", 20)
        self.assertIsNone(self.lv.sentir(s(25)))         # cedo demais
        t = self.lv.sentir(s(61))                        # o relógio pega depois
        self.assertIn("aumentou o Lush", t["texto"])
        self.assertIn("no máximo", t["texto"])

    def test_parou_e_ligou_desligou_provocando(self):
        self.lv.comando(s(10), "lush", 10)
        self.lv.sentir(s(15))
        self.lv.comando(s(70), "lush", 0)
        self.assertIn("Ele parou o Lush", self.lv.sentir(s(75))["texto"])
        self.lv.comando(s(130), "lush", 18)
        self.lv.comando(s(132), "lush", 0)
        self.assertIn("por uns segundos (chegou a no máximo) e desligou", self.lv.sentir(s(140))["texto"])

    def test_padrao_novo(self):
        self.lv.comando(s(10), "lush", 10)
        self.lv.sentir(s(15))
        self.lv.comando(s(70), "lush", 10, "padrao", "onda")
        t = self.lv.sentir(s(75))["texto"]
        self.assertIn("mudou o ritmo do Lush", t)
        self.assertIn("em ondas que sobem e descem", t)

    def test_toque_soltou(self):
        self.lv.comando(s(10), "lush", 14, "toque")
        self.assertIn("no ritmo do dedo dele", self.lv.sentir(s(15))["texto"])
        self.lv.comando(s(70), "lush", 0, "toque")
        self.assertIn("tirou o dedo", self.lv.sentir(s(75))["texto"])
        # Do Clássico pro Toque: passou o dedo e soltou (pré-visualização, 05/10).
        self.lv.comando(s(130), "lush", 19)
        self.lv.sentir(s(135))
        self.lv.comando(s(190), "lush", 14, "toque")
        self.lv.comando(s(191), "lush", 0, "toque")
        self.assertIn("tirou o dedo e o Lush parou", self.lv.sentir(s(195))["texto"])

    def test_mesmo_ritmo_o_tesao_acumula(self):
        self.lv.comando(s(10), "lush", 10)
        self.lv.sentir(s(15))
        self.assertIsNone(self.lv.sentir(s(15 + 4 * 60)))
        t = self.lv.sentir(s(15 + 5 * 60))
        self.assertEqual(t["motivo"], "sustentado")
        self.assertIn("Faz 5 min que o Lush vibra no mesmo ritmo", t["texto"])
        self.assertIsNone(self.lv.sentir(s(15 + 10 * 60)))     # depois do primeiro, de 10 em 10 min
        self.assertIn("Faz 15 min", self.lv.sentir(s(15 + 15 * 60))["texto"])

    def test_fraquinho_parado_nao_acumula(self):
        self.lv.comando(s(10), "lush", 2)
        self.lv.sentir(s(15))
        self.assertIsNone(self.lv.sentir(s(15 + 20 * 60)))

    def test_eventos_da_palavra_sempre_viram_turno(self):
        self.lv.comando(s(10), "lush", 10)
        self.lv.sentir(s(15))
        self.lv.pedir_parar(s(20))
        r = self.lv.comando(s(25), "lush", 0)
        t = self.lv.sentir(s(26), r["eventos"])                 # 6 s depois do último turno: o evento passa
        self.assertIn("parou na hora, como combinado", t["texto"])
        self.assertNotIn("ele parou o Lush", t["texto"])
        self.assertNotIn("abacaxi", t["texto"])

    def test_nao_parou_firme_com_o_que_ela_sente_agora(self):
        self.lv.comando(s(10), "lush", 16)
        self.lv.sentir(s(15))
        self.lv.pedir_parar(s(20))
        t = self.lv.sentir(s(51), self.lv.tick(s(51)))
        self.assertIn("Faz 30 s que você disse a palavra de segurança", t["texto"])
        self.assertIn("agora vibrando muito forte", t["texto"])

    def test_cortou_e_bateria_com_a_sessao_ja_fechada(self):
        self.lv.comando(s(10), "lush", 16)
        self.lv.pedir_parar(s(20))
        self.lv.tick(s(81))
        t = self.lv.sentir(s(111), self.lv.tick(s(111)))
        self.assertIn("Você cortou o controle dele", t["texto"])
        self.assertFalse(self.lv.estado(s(112))["conectada"])

    def test_bateria_acabou(self):
        self.lv.comando(s(10), "lush", 20)
        t = self.lv.sentir(s(3 * 3600), self.lv.estado(s(3 * 3600))["eventos"])
        self.assertIn("A bateria do Lush acabou", t["texto"])
        self.assertIn("perdeu a conexão", t["texto"])

    def test_os_eventos_dela_nao_viram_turno(self):
        self.assertIsNone(self.lv.sentir(s(5), ["pediu_parar", "tirou"]))



def sentindo(libido=0.5, excitacao=0.0, desconforto=0.0, energia=0.7, gozou_ha=None):
    """O que ela sente (os campos de EmotionEngine.feeling que o ponto bom usa)."""
    from types import SimpleNamespace
    return SimpleNamespace(libido=libido, excitation=excitacao, discomfort=desconforto, energy=energia,
                           hours_since_release=gozou_ha, cycle_phase="folicular")


class RecepcaoTests(LovenseBase):
    """Passo 4 (Patrick, 05/10): tudo depende de ela estar gostando — o ponto bom muda com o tesão, o lugar, o
    corpo e o tempo; acima dele incomoda, perto é gostoso, no ponto com tesão alto ela se entrega."""

    def setUp(self):
        super().setUp()
        self.lv.colocar(T0, ["lush"])

    def rec(self, quando, atividade="HOME_RELAXING", **f):
        return self.lv.recepcao(quando, atividade, feeling=sentindo(**f))

    def test_sem_sessao_e_parado(self):
        self.assertEqual(self.rec(s(5))["estado"], "parado")
        self.lv.tirar(s(6))
        self.assertIsNone(self.rec(s(7)))

    def test_o_tesao_sobe_o_ponto_bom(self):
        self.lv.comando(s(10), "lush", 16)
        sem_clima = self.rec(s(20), libido=0.3)
        com_tesao = self.rec(s(20), libido=0.9)
        self.assertEqual(sem_clima["estado"], "incomodada")
        self.assertEqual(com_tesao["estado"], "gostando")
        self.assertGreater(com_tesao["ponto"], sem_clima["ponto"])

    def test_com_gente_perto_o_forte_incomoda(self):
        self.lv.comando(s(10), "lush", 10)
        self.assertEqual(self.rec(s(20), "HOME_RELAXING")["estado"], "gostando")
        aula = self.rec(s(20), "CLASS")
        self.assertEqual(aula["estado"], "incomodada")
        self.assertIn("pra onde você está", aula["frase"])
        self.assertTrue(aula["publico"])

    def test_corpo_colica_desce_o_ponto(self):
        self.lv.comando(s(10), "lush", 10)
        self.assertEqual(self.rec(s(20), desconforto=0.6)["estado"], "incomodada")

    def test_sensivel_logo_depois_de_gozar(self):
        self.lv.comando(s(10), "lush", 4)
        self.assertEqual(self.rec(s(20), libido=0.8)["estado"], "gostando")
        r = self.rec(s(20), libido=0.8, gozou_ha=0.1)
        self.assertEqual(r["estado"], "incomodada")
        self.assertIn("sensível", r["frase"])

    def test_forte_sem_parar_cansa(self):
        self.lv.comando(s(10), "lush", 16)
        self.assertEqual(self.rec(s(60), libido=0.75)["estado"], "gostando")
        r = self.rec(T0 + timedelta(minutes=40), libido=0.75)
        self.assertTrue(r["cansou"])
        self.assertEqual(r["estado"], "incomodada")
        self.assertIn("cansou", r["frase"])

    def test_curtindo_precisa_da_excitacao_e_do_ponto(self):
        self.lv.comando(s(10), "lush", 14)
        self.assertEqual(self.rec(s(20), libido=0.8, excitacao=0.2)["estado"], "gostando")
        r = self.rec(s(20), libido=0.8, excitacao=0.7)
        self.assertEqual(r["estado"], "curtindo")
        self.assertGreater(r["grau"], 0.5)
        self.lv.comando(s(30), "lush", 2)                       # muito abaixo do ponto: só gostoso, quer mais
        r = self.rec(s(40), libido=0.8, excitacao=0.7)
        self.assertEqual(r["estado"], "gostando")
        self.assertIn("fraco pro tesão", r["frase"])

    def test_o_estimulo_soma_excitacao_e_incomodando_quase_nada(self):
        from intimacy import IntimacyEngine
        self.lv.comando(s(10), "lush", 12)
        t = s(10)
        for _ in range(36):                                     # 6 min no relógio de 10 s
            t += timedelta(seconds=10)
            self.lv.estimular(t, self.lv.recepcao(t, "HOME_RELAXING", feeling=sentindo(libido=0.6)))
        gostando = IntimacyEngine(self.db).current(t).arousal
        self.assertGreater(gostando, 0.3)
        with self.db.get_connection() as conn:
            conn.execute("UPDATE intimacy_state SET arousal=0, updated_at=?", (t.isoformat(),))
            conn.commit()
        for _ in range(36):
            t += timedelta(seconds=10)
            self.lv.estimular(t, self.lv.recepcao(t, "CLASS", feeling=sentindo(libido=0.6)))
        self.assertLess(IntimacyEngine(self.db).current(t).arousal, gostando / 2)


class BanhoEFimDaEscadaTests(LovenseBase):
    """Passo 4: no banho, forte demais ela tira ali e dá o esporro depois; no fim da escada da palavra ela acaba
    pelo jeito mais fácil no momento, e largar o que fazia pra ir tirar é o mais punitivo."""

    def setUp(self):
        super().setUp()
        self.lv.colocar(T0, ["lush"])

    def test_banho_forte_demais_ela_tira_sem_mexer_na_confianca(self):
        from unittest.mock import patch
        self.lv.comando(s(10), "lush", 20)
        with patch("lovense._feeling", return_value=sentindo(libido=0.4)):
            eventos = self.lv.tick(s(20), atividade="SHOWER")
        self.assertIn("tirou_incomodada", eventos)
        est = self.lv.estado(s(21))
        self.assertFalse(est["conectada"])
        self.assertEqual(next(b for b in est["brinquedos"] if b["nome"] == "lush")["onde"], "carregador")
        self.assertAlmostEqual(self.trust(s(21)), 0.8, places=2)
        self.assertIsNone(self.lv.pendencia(s(21)))
        with self.db.get_connection() as conn:
            ep = conn.execute("SELECT family, kind, target FROM emotion_episodes WHERE source_key LIKE 'lovense:tirou:%'"
                              ).fetchone()
        self.assertEqual((ep["family"], ep["kind"], ep["target"]), ("raiva", "irritacao", "o Patrick"))
        t = self.lv.sentir(s(22), eventos)
        self.assertIn("tirou o brinquedo no banho", t["texto"])

    def test_banho_gostoso_ela_fica(self):
        from unittest.mock import patch
        self.lv.comando(s(10), "lush", 6)
        with patch("lovense._feeling", return_value=sentindo(libido=0.5)):
            self.assertEqual(self.lv.tick(s(20), atividade="SHOWER"), [])
        self.assertTrue(self.lv.estado(s(21))["conectada"])

    def _ate_o_fim(self, atividade, quando):
        from unittest.mock import patch
        self.lv.comando(s(10), "lush", 16)
        with patch("lovense._feeling", return_value=sentindo(libido=0.9)):
            self.lv.pedir_parar(s(20))
            self.lv.tick(s(81), atividade=atividade)                # bronca
            return self.lv.tick(quando, atividade=atividade)

    def test_celular_na_mao_corta(self):
        self.assertIn("cortou", self._ate_o_fim("HOME_RELAXING", s(111)))

    def test_em_casa_sem_celular_tira_ali_e_pesa_igual_ao_corte(self):
        eventos = self._ate_o_fim("SHOWER", s(111))
        self.assertIn("tirou_na_bronca", eventos)
        self.assertAlmostEqual(self.trust(s(112)), 0.8 - 0.10 - 0.08, places=2)
        self.assertIsNotNone(self.lv.pendencia(s(112)))
        self.assertFalse(self.lv.estado(s(112))["conectada"])
        self.assertIsNone(self.lv.estado(s(112))["aviso"])         # tirar não é o corte: o app só desconecta

    def test_fora_sem_celular_aguenta_e_depois_larga_tudo(self):
        self.assertEqual(self._ate_o_fim("CASTING", s(111)), [])   # no meio do casting: aguenta
        from unittest.mock import patch
        with patch("lovense._feeling", return_value=sentindo(libido=0.9)):
            eventos = self.lv.tick(s(20 + 90 + 120), atividade="CASTING")
        self.assertIn("tirou_largando", eventos)
        self.assertAlmostEqual(self.trust(s(231)), 0.8 - 0.10 - 0.15, places=2)
        est = self.lv.estado(s(231))
        self.assertEqual(next(b for b in est["brinquedos"] if b["nome"] == "lush")["onde"], "bolsa")
        self.assertEqual(self.lv._incidentes(s(231)), 2)            # conta em dobro: a pendência dura mais
        t = self.lv.sentir(s(232), eventos)
        self.assertIn("largar o que estava fazendo", t["texto"])


class SentirComRecepcaoTests(LovenseBase):
    """Passo 4: o turno diz como ela está recebendo; começar a incomodar sem ele mexer também vira turno."""

    def setUp(self):
        super().setUp()
        self.lv.colocar(T0, ["lush"])

    def test_turno_diz_como_ela_recebe(self):
        from unittest.mock import patch
        with patch("lovense._feeling", return_value=sentindo(libido=0.6)):
            self.lv.comando(s(10), "lush", 8)
            t = self.lv.sentir(s(15), [], "HOME_RELAXING")
        self.assertIn("ligou o Lush", t["texto"])
        self.assertIn("está gostoso", t["texto"])

    def test_chegou_na_aula_e_comecou_a_incomodar(self):
        from unittest.mock import patch
        with patch("lovense._feeling", return_value=sentindo(libido=0.6)):
            self.lv.comando(s(10), "lush", 11)
            self.lv.sentir(s(15), [], "HOME_RELAXING")
            self.assertIsNone(self.lv.sentir(s(70), [], "HOME_RELAXING"))
            t = self.lv.sentir(s(80), [], "CLASS")
            self.assertEqual(t["motivo"], "incomodou")
            self.assertIn("continua vibrando", t["texto"])
            self.assertIn("forte demais pra onde você está", t["texto"])
            self.assertIsNone(self.lv.sentir(s(140), [], "CLASS"))    # já disse: não repete
