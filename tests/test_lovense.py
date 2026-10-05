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
        self.assertEqual(self.db.get_schema_version(), 34)
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
