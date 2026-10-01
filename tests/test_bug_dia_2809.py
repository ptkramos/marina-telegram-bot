"""Bug do uso real: o dia 28/09 visto pelo Patrick na conversa, no card e no Hoje (com os horários do caso).

1. Almoço "no restaurante da PUC" 13:15–13:58 com a carona do Theo saindo às 13:00 (aula 09:00–13:00). Decisão do
   Patrick: depende da carona — com carona volta e almoça em casa; sozinha, às vezes almoça por lá e a volta sai depois.
2. "Vou comprar um sanduíche antes de entrar" (08:33, a caminho da PUC) não virou nada no mundo; às 13:41 o
   "comi um sanduíche rapidinho" ficou solto. Na rua, comprar/comer algo vira lanche fora, com o preço no saldo.
3. Story às 14:09 com "Baby 95" (Liniker) e o mundo/Hoje dizendo "ouvindo Sabrina Carpenter" o bloco inteiro.
4. Hoje: "Foi pra calçada 07:58" sem volta e "Foi pra PUC 08:19" logo depois — parecia que o Milo foi junto.
5. Hoje: a volta pra casa não aparecia ("Foi pra PUC 08:19–13:35" engolia a carona) e o Pinterest das 13:35, já
   em casa, caía dentro da PUC.
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import hoje
from agenda import Etapa
from commute import Commute, Leg
from db import DatabaseManager
from meals import Meals, comida_na_rua
from tempo_livre import Bloco

DIA = datetime(2026, 9, 28)


def at(h, m, s=0):
    return DIA.replace(hour=h, minute=m, second=s)


AULA = [{"id": 1, "start_at": "2026-09-28T09:00:00", "end_at": "2026-09-28T13:00:00",
         "display_name": "Projeto: Projetar em Sociedade"}]


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "d.db")


class AlmocoDepoisDaAulaTest(Base):
    def setUp(self):
        super().setUp()
        for alvo, kw in (("academic_life.AcademicLife.blocks_on", {"side_effect": lambda d: AULA if d == DIA.date() else []}),
                         ("rituals.Rituals.wake_at", {"return_value": at(7, 33)})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)

    def _com_volta(self, modo, ini=at(13, 0), fim=at(13, 35)):
        volta = Leg("commute:2026-09-28:puc:volta", ini, fim, modo, "volta", "da PUC", "Gávea")
        return patch("commute.Commute.legs_on", return_value=[volta])

    def test_com_carona_almoca_em_casa_depois_de_chegar(self):
        with self._com_volta("carona"):
            almoco = next(s for s in Meals(self.db).day_plan(DIA.date()) if s.kind == "almoco")
        self.assertEqual(almoco.where, "casa")
        self.assertGreaterEqual(almoco.at, at(13, 45))
        self.assertIsNone(Meals(self.db).almoco_pos_aula(DIA.date(), "carona"))

    def test_sozinha_as_vezes_almoca_por_la_e_a_volta_sai_depois(self):
        with patch.object(Meals, "ALMOCO_POR_LA", 1.0):
            almoco = Meals(self.db).almoco_pos_aula(DIA.date(), "metro_onibus")
            self.assertIn(almoco.where, ("puc", "gavea"))
            self.assertGreaterEqual(almoco.at, at(13, 10))
            with patch("commute.Commute._choose", return_value=("metro_onibus", 40)), \
                    patch("commute.Commute._driver", return_value=("", "")), \
                    patch("commute.Commute._incident", side_effect=lambda leg: leg), \
                    patch("academia.Academia.plano", return_value=None), \
                    patch("academia.PasseioMilo.plano", return_value=None):
                legs = Commute(self.db)._legs_planejados(DIA.date())
            volta = next(l for l in legs if l.key.endswith(":puc:volta"))
            self.assertEqual(volta.start, almoco.end + timedelta(minutes=5))
            with self._com_volta("metro_onibus", volta.start, volta.end):
                plano = next(s for s in Meals(self.db).day_plan(DIA.date()) if s.kind == "almoco")
            self.assertEqual((plano.where, plano.at), (almoco.where, almoco.at))

    def test_sozinha_sem_vontade_volta_e_come_em_casa(self):
        with patch.object(Meals, "ALMOCO_POR_LA", 0.0), self._com_volta("metro_onibus"):
            self.assertIsNone(Meals(self.db).almoco_pos_aula(DIA.date(), "metro_onibus"))
            almoco = next(s for s in Meals(self.db).day_plan(DIA.date()) if s.kind == "almoco")
        self.assertEqual(almoco.where, "casa")


class SanduicheNaRuaTest(Base):
    def test_frases(self):
        self.assertEqual(comida_na_rua("Tá bom, amor, vou comprar um sanduíche antes de entrar"), ("um sanduíche", 15))
        self.assertEqual(comida_na_rua("Vou sim, amor, vou pegar alguma coisa no caminho"), ("um lanche", 14))
        self.assertEqual(comida_na_rua("vou pegar um pão de queijo"), ("um pão de queijo", 9))
        self.assertIsNone(comida_na_rua("Boa, amor, vou colocar barrinhas na lista da semana kkk"))
        self.assertIsNone(comida_na_rua("vou pegar um uber"))
        self.assertIsNone(comida_na_rua("vou comprar um vestido"))

    def test_vira_lanche_fora_com_preco_uma_vez(self):
        with patch("meals.Meals._at_home", return_value=False), patch("agenda.Agenda.agora", return_value=None):
            self.assertIsNone(Meals(self.db).observe_marina_line(
                "Tá bom, amor, vou comprar um sanduíche antes de entrar\nMeu estômago já tá fazendo protesto aqui kkk",
                at(8, 33, 28)))
            Meals(self.db).observe_marina_line("vou comprar um sanduíche sim", at(8, 40))   # repetiu: não compra outro
        with self.db.get_connection() as conn:
            rows = [dict(r) for r in conn.execute("SELECT event_key, event_type, event_at, summary FROM life_events "
                                                  "ORDER BY event_key")]
        self.assertEqual([(r["event_type"], r["summary"]) for r in rows],
                         [("consumo", "Pediu um sanduíche no caminho (R$ 15)."),
                          ("snack", "Comeu um sanduíche no caminho.")])
        self.assertEqual(rows[1]["event_at"], at(8, 43, 28).isoformat())
        self.assertEqual(hoje.curto(rows[0])["valor"], 15)

    def test_no_role_quem_decide_e_o_consumo(self):
        la = Etapa("la", "No Starbucks", at(14, 55), at(15, 32), compromisso="vontade:2026-09-28:1440")
        with patch("meals.Meals._at_home", return_value=False), patch("agenda.Agenda.agora", return_value=la):
            self.assertFalse(Meals(self.db).lanche_na_rua("vou pegar um pão de queijo", at(14, 58)))


class MusicaTocandoTest(unittest.TestCase):
    FAIXAS = [{"at": "2026-09-28T13:59:56", "ms": 141393, "artista": "Sabrina Carpenter", "nome": "Bad Reviews"},
              {"at": "2026-09-28T14:02:17", "ms": 218424, "artista": "Chappell Roan", "nome": "Good Luck, Babe!"},
              {"at": "2026-09-28T14:05:55", "ms": 318995, "artista": "Liniker", "nome": "Baby 95"},
              {"at": "2026-09-28T14:11:14", "ms": 205520, "artista": "Chappell Roan", "nome": "Coffee"}]

    def test_mundo_acompanha_a_faixa(self):
        b = Bloco("livre:2026-09-28:16", "musica", "Ouvindo Sabrina Carpenter", "sala", "fone", False,
                  at(13, 59, 56), at(14, 20, 56), faixas=self.FAIXAS)
        self.assertIn("Baby 95", b.atividade_em(at(14, 9, 56)))
        self.assertIn("(Liniker)", b.atividade_em(at(14, 9, 56)))
        self.assertIn("Sabrina Carpenter", b.atividade_em(at(14, 0)))
        self.assertTrue(b.atividade_em(at(14, 9)).startswith("em casa, "))

    def test_hoje_diz_a_playlist_e_os_artistas(self):
        ev = {"event_type": "tempo_livre", "title": "Ouvindo Sabrina Carpenter", "summary":
              'Ficou ouvindo a playlist dela na sala: "Bad Reviews" (Sabrina Carpenter), "Good Luck, Babe!" '
              '(Chappell Roan), "Baby 95" (Liniker), "Coffee" (Chappell Roan).'}
        c = hoje.curto(ev)
        self.assertEqual((c["texto"], c["sub"]), ("Ouviu a playlist dela", "Sabrina Carpenter, Chappell Roan e Liniker"))


class HojeMiloEVoltaTest(Base):
    def test_calcada_tem_a_volta(self):
        c = hoje.curto({"event_type": "routine", "title": "Milo", "event_at": at(7, 58).isoformat(),
                        "end_at": at(8, 11).isoformat(), "summary": "Desceu rapidinho com o Milo pro xixi da manhã."})
        self.assertEqual((c["texto"], c["fim"]), ("Desceu com o Milo", at(8, 11)))

    def test_volta_pra_casa_e_o_que_vem_depois_fica_fora(self):
        la = Etapa("la", "Na PUC", at(9, 0), at(13, 0), lugar_key="puc_rio")
        volta = Etapa("voltando", "Voltando pra casa", at(13, 0), at(13, 35), como="Carona com o Theo")
        saida = {"key": "puc:2026-09-28", "ini": at(8, 19), "fim": at(13, 35), "titulo": "Foi pra PUC",
                 "previsto": "Na PUC", "ic": "school", "la": la, "volta": volta}
        eventos = [{"event_key": "livre:2026-09-28:15", "event_at": at(13, 35).isoformat(), "end_at": None,
                    "event_type": "tempo_livre", "title": "Olhando o Pinterest", "summary": "Ficou olhando o Pinterest na sala."}]
        with patch("hoje._saidas", return_value=[saida]), patch("hoje._eventos", return_value=eventos), \
                patch("hoje._blocos", return_value={}), patch("hoje._previstos", return_value=[]), \
                patch("sleep_plan.SleepPlan.wake", return_value=at(7, 33)):
            v = hoje.hoje_view(self.db, at(15, 5))
        itens = [i for p in v["periodos"] for i in p["itens"]]
        puc = next(i for i in itens if i["texto"] == "Foi pra PUC")
        self.assertEqual([(f["texto"], f["sub"], f["hora"]) for f in puc["filhos"]],
                         [("Voltou para casa", "Carona com o Theo", "13:00–13:35")])
        self.assertIn("Olhou o Pinterest", [i["texto"] for i in itens])


if __name__ == "__main__":
    unittest.main()
