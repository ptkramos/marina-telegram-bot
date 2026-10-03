"""Leitura do soak, melhorada antes do dia 4 (FRENTES, seção 0): no 02/10 o Patrick achou três coisas que o relatório
deixou passar — as fotos com a desculpa fixa da câmera, a comida que não matou a fome e o fundo de rua no Rei do Mate.
Conferências novas no relatório, com os casos reais de 02/10."""
import importlib.util
import random
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location(
    "relatorio_soak", Path(__file__).resolve().parents[1] / "scripts" / "relatorio_soak.py")
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)


def _estado(activity, region="Botafogo"):
    return {"activity": activity, "location_region": region, "sit": rs.situacao(activity, region),
            "at": datetime(2026, 10, 2, 15, 30)}


class PatrickEstranhouTest(unittest.TestCase):
    def test_pistas_de_02_10(self):
        self.assertEqual(rs.estranhou("Andando na chuva garota?! Vai chegar molhada em casa"), "?!")  # o chuvisco
        self.assertEqual(rs.estranhou("Mds, cadê? Deixa eu ver pf eu te imploro"), "cade")          # a foto
        self.assertTrue(rs.estranhou("Esqueceu de avisar né?! Vc n é mole"))
        self.assertTrue(rs.estranhou("como assim vc tá em casa"))
        self.assertTrue(rs.estranhou("n entendi"))
        self.assertTrue(rs.estranhou("mas você disse que ia pra academia"))

    def test_ue_e_muleta_dele(self):
        for fala in ("Eu gosto ué", "Então fica ué Se vc ficar eu fico", "Saudade de vc me deixa com vontade de vc ué",
                     "Tá bom bb", "que delícia amor"):
            self.assertEqual(rs.estranhou(fala), "", fala)


class FotoPedidaTest(unittest.TestCase):
    def test_pedidos(self):
        self.assertTrue(rs.pede_foto("Babando, levantando esse vestido q eu já tô curioso p ver uq tá usando por baixo"))
        self.assertTrue(rs.pede_foto("manda uma foto sua agora"))
        self.assertTrue(rs.pede_foto("Ah beleza, quero ver o resultado quando estiver pronta viu?"))
        self.assertTrue(rs.pede_foto("kd a foto?"))

    def test_nao_e_pedido(self):
        for fala in ("Tá bom bb", "Olha 🙌", "vou ver um filme mais tarde", "mandei a foto do meu almoço"):
            self.assertFalse(rs.pede_foto(fala), fala)


class FundoDaFotoTest(unittest.TestCase):
    def test_rua_dentro_do_rei_do_mate(self):
        """02/10, 15:41: «Behind her, a street in Botafogo» com ela tomando mate no Rei do Mate."""
        mate = _estado("Tomando um mate no Rei do Mate")
        self.assertIn("rua genérico", rs.fundo_contradiz("fora", "a street in Botafogo, Rio de Janeiro", mate))
        self.assertEqual(rs.fundo_contradiz("fora", "the inside of a snack bar in Botafogo, Rio de Janeiro", mate), "")

    def test_casa_x_rua(self):
        self.assertIn("com o mundo em casa", rs.fundo_contradiz(
            "fora", "a street in Botafogo", _estado("em casa, organizando o closet (closet)")))
        self.assertIn("com o mundo fora", rs.fundo_contradiz("quarto", "her bedroom", _estado("Tomando um açaí na Estação do Açaí")))
        self.assertEqual(rs.fundo_contradiz("quarto", "her bedroom", _estado("em casa, deitada à toa (quarto)")), "")
        self.assertEqual(rs.fundo_contradiz("fora", "Botafogo street", _estado("passeando com Milo")), "")
        self.assertEqual(rs.fundo_contradiz("fora", "a street", None), "")


class EnviadoForaDoHistoricoTest(unittest.TestCase):
    def test_desculpa_da_camera(self):
        """02/10, 15:41: a desculpa fixa foi pro Telegram e não entrou no histórico."""
        perto = ["Kkkkk olha as prioridades do garoto! Nem disfarça que tá com a cabeça cheia de maldade"]
        self.assertFalse(rs.no_historico(
            "Amor, tentei te mandar a fotinho agora mas a câmera do apê travou 🥺 Me pede de novo daqui a pouco", perto))

    def test_balao_de_fala_gravada(self):
        gravada = ["Hj tá bem tranquilo, amor. Vou ficar em casa desenhando e mais tarde saio com a Júlia"]
        self.assertTrue(rs.no_historico("Vou ficar em casa desenhando e mais tarde saio com a Júlia", gravada))
        self.assertTrue(rs.no_historico("Prometido é devido 😌",
                                        ["[1 foto(s): a foto que você prometeu] prometido é devido 😌"]))
        self.assertTrue(rs.no_historico("🥰", []))          # só emoji: nada pra conferir


class LogDoRelatorioTest(unittest.TestCase):
    def test_excecao_de_handler_nao_e_ruido(self):
        """02/10, 14:23: o BadRequest da confirmação do /ruim caiu em "rede" pela frase do python-telegram-bot."""
        self.assertFalse(any("No error handlers" in r for r in rs.RUIDO))

    def test_diretor_registra_o_cenario(self):
        import photo_director as pd
        from db import DatabaseManager
        from intimacy import IntimacyTurn
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(Path(tmp) / "d.db")
            ctx = SimpleNamespace(place_key="marina_apartment", presence_assertable=True, activity="", sublocation="",
                                  weather=None, present_people=())
            with self.assertLogs("photo_director", level="INFO") as cm:
                pd.direct(db, datetime(2026, 10, 2, 14, 44), request="manda uma foto", camera_ctx=ctx,
                          turn=IntimacyTurn(), rng=random.Random(3))
        linha = next(x for x in cm.output if "photo_director.cena" in x)
        self.assertRegex(linha, r"photo_director\.cena lugar=\S+ comodo=\S+ pose=\S+ cena=\S")


class LeituraDoDia4NoiteTest(unittest.TestCase):
    """O que a leitura de 03/10 achou e o script não pegava."""
    def test_aqui_onde_e_esqueceu_de_avisar(self):
        self.assertTrue(rs.estranhou("Aqui onde?"))
        self.assertTrue(rs.estranhou("Só esqueceu de avisar de novo, aí deixa o namorado preocupado"))

    def test_se_divertindo_em_casa(self):
        casa = [_estado("vendo Paradise Kiss no sofá")]
        self.assertEqual(rs.atividade_contradiz("Tô aqui, amor. Se divertindo ainda", casa), "se divertindo")
        self.assertEqual(rs.atividade_contradiz("Tô aqui, amor. Se divertindo ainda",
                                                [_estado("Saindo com a Júlia no Quartinho Bar")]), "")

    def test_banho_tomado(self):
        self.assertTrue(rs.RE_BANHO_FEITO.search("já sim, amor kkk banho tomado e tô largada no sofá"))
        self.assertFalse(rs.RE_BANHO_FEITO.search("vou tomar banho agora"))


if __name__ == "__main__":
    unittest.main()
