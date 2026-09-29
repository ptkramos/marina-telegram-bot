"""Relatório diário do soak: as regras que acham suspeita sozinhas (casos reais de 28/09)."""
import importlib.util
import unittest
from datetime import date, datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "relatorio_soak", Path(__file__).resolve().parents[1] / "scripts" / "relatorio_soak.py")
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)


def _estado(activity, region="Botafogo"):
    return {"activity": activity, "location_region": region, "sit": rs.situacao(activity, region),
            "at": datetime(2026, 9, 28, 12, 0)}


class SituacaoTests(unittest.TestCase):
    def test_classes_do_mundo(self):
        casos = {
            ("dormindo", "Botafogo"): "dormindo",
            ("indo pra PUC de metrô e ônibus", "a caminho (Gávea)"): "caminho",
            ("se arrumando pra sair pro Starbucks (saindo)", "Botafogo"): "arrumando",
            ("se arrumando pra dormir (tomando banho)", "Botafogo"): "banho",
            ("na faculdade (Projeto: Projetar em Sociedade)", "Gávea"): "aula",
            ("treinando na academia", "Botafogo"): "academia",
            ("passeando com Milo", "Botafogo"): "rua",
            ("em casa, olhando o Pinterest (sala)", "Botafogo"): "casa",
            ("comendo o Cappuccino que o Patrick mandou", "Botafogo"): "casa",
            ("Tomando um café no Starbucks", "Botafogo"): "fora",
        }
        for (act, reg), esperado in casos.items():
            self.assertEqual(rs.situacao(act, reg), esperado, act)


class FalaMundoTests(unittest.TestCase):
    def test_bug16_em_casa_na_academia(self):
        """28/09, 18:58: «Tô em casa, amor» com o mundo treinando na academia."""
        (classe, _, palavras), = rs.alegacoes("Tô em casa, amor Deitada no sofá com o Milo")
        self.assertTrue(rs.contradiz(classe, palavras, [_estado("treinando na academia")]))
        self.assertFalse(rs.contradiz(classe, palavras, [_estado("em casa, deitada à toa (quarto)")]))

    def test_lugar_certo_nao_acusa(self):
        (classe, _, palavras), = rs.alegacoes("tô na academia ainda kkk")
        self.assertFalse(rs.contradiz(classe, palavras, [_estado("treinando na academia")]))
        self.assertTrue(rs.contradiz(classe, palavras, [_estado("em casa, olhando o X (sala)")]))

    def test_indo_dormir_nao_e_trajeto(self):
        self.assertEqual(rs.alegacoes("tô indo pra cama agora"), [])

    def test_fazendo_em_casa_com_o_mundo_na_rua(self):
        """28/09, 17:24: «Tô organizando umas referências de look aqui» passeando com o Milo na Enseada."""
        fala = "Oii, amor Tô organizando umas referências de look aqui e o Milo tá dormindo do meu lado"
        self.assertEqual(rs.atividade_contradiz(fala, [_estado("passeando com Milo")]), "tô organizando")
        self.assertEqual(rs.atividade_contradiz(fala, [_estado("em casa, montando looks (closet)")]), "")

    def test_futuro_nao_acusa(self):
        self.assertEqual(rs.atividade_contradiz("quando eu chegar vou deitar no sofá",
                                                [_estado("voltando da PUC pra casa de carona com o Theo",
                                                         "a caminho (Gávea)")]), "")


class FezNoDiaTests(unittest.TestCase):
    def test_sanduiche_que_nao_existiu(self):
        """28/09, 13:41: «comi um sanduíche rapidinho» sem sanduíche nenhum no mundo."""
        feito = rs._sem_acento("almoço Almoço no restaurante da PUC: salada com frango no restaurante do campus.")
        achou = rs.fez_contradiz("Já sim, amor, comi um sanduíche rapidinho", feito)
        self.assertEqual(len(achou), 1)
        self.assertIn("sanduiche", achou[0])
        self.assertEqual(rs.fez_contradiz("comi um sanduíche", feito + " comeu sanduiche natural"), [])

    def test_milo_e_almoco(self):
        self.assertTrue(rs.fez_contradiz("desci rapidinho com o Milo", "acordou"))
        self.assertEqual(rs.fez_contradiz("desci rapidinho com o Milo", "desceu rapidinho com o milo pro xixi"), [])
        self.assertEqual(rs.fez_contradiz("Almocei sim, amor, foi salada com frango lá na PUC",
                                          "almoco no restaurante da puc"), [])


class QuebrasTests(unittest.TestCase):
    def test_numero_sumido_do_bug16(self):
        self.assertTrue(rs.quebras("Oi, meu amor. Me pesei ,4 kg kkk"))
        self.assertEqual(rs.quebras("Me pesei hoje: 54,4 kg kkk"), [])

    def test_outro_alfabeto_e_resto_de_codigo(self):
        self.assertTrue(rs.quebras("Kkkkk nem fala, deixa quietinho entãoеиҳәеит"))
        self.assertTrue(rs.quebras("tô indo pro {lugar}"))
        self.assertEqual(rs.quebras("kkk kkk que bom"), [])


class DiaTests(unittest.TestCase):
    def test_ultimo_dia_fechado(self):
        self.assertEqual(rs._dia_padrao(datetime(2026, 9, 29, 5, 10)), date(2026, 9, 28))
        self.assertEqual(rs._dia_padrao(datetime(2026, 9, 29, 14, 0)), date(2026, 9, 28))
        self.assertEqual(rs._dia_padrao(datetime(2026, 9, 29, 4, 30)), date(2026, 9, 27))


if __name__ == "__main__":
    unittest.main()
