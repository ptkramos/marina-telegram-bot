"""Soak, dia 1 (terça 29/09): o que o relatório e o Patrick acharam, com os horários do caso.

1. 15:01 "Cheguei em casa" com a aula até 15:00: almoçou na PUC (15:18) e a volta saiu 16:06, mas nesse meio o
   mundo caiu na rotina de casa.
2. 16:06 "indo da PUC pra Enseada a pé": o passeio do Milo foi marcado contando a volta sem o almoço e o trajeto
   emendou a volta da PUC com a ida pro passeio.
3. 19:01 "o plantão de amanhã": o assunto em aberto dizia "Patrick terá um plantão amanhã" desde 27/09.
4. 05:39 o xixi da manhã do Milo no meio do banho (05:23–05:47).
5. 11:47 "morrendo de fome" com quatro aulas seguidas e nada até 15:18: o belisco só existia em casa.
6. 15:37 "o Seu Jorge contou uma fofoca quando ela passou pela portaria" com ela almoçando na PUC.
7. O relatório deu 0 suspeitas: faltava mundo × mundo, "terminando o trabalho" na rua e "boa noite" de manhã.
"""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from casa import Casa
from commute import Commute, Leg
from db import DatabaseManager, ancorar_datas
from meals import MealSlot, Meals
from milo import Milo
from world_state import RoutineEngine, WorldStateManager

DIA = datetime(2026, 9, 29)


def at(h, m, s=0):
    return DIA.replace(hour=h, minute=m, second=s)


AULAS = [{"id": i, "start_at": f"2026-09-29T{h:02d}:00:00", "end_at": f"2026-09-29T{h + 2:02d}:00:00",
          "display_name": n}
         for i, (h, n) in enumerate(((7, "Práticas Experimentais II"), (9, "Linguagem e Estruturas"),
                                     (11, "Fundamentos em Ergodesign"), (13, "O Cristianismo")), 5)]
ALMOCO = MealSlot("almoco", "meal:2026-09-29:almoco", at(15, 18), 43, "puc",
                  "salada com frango no restaurante do campus")


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "d.db")

    def _patch(self, alvo, **kw):
        p = patch(alvo, **kw)
        p.start()
        self.addCleanup(p.stop)


class DepoisDaAulaTest(Base):
    def setUp(self):
        super().setUp()
        self._patch("academic_life.AcademicLife.blocks_on", side_effect=lambda d: AULAS if d == DIA.date() else [])
        self._patch("commute.Commute._choose", return_value=("metro_onibus", 45))
        self._patch("commute.Commute._driver", return_value=("", ""))

    def test_volta_da_puc_sai_depois_do_almoco_por_la(self):
        with patch("meals.Meals.almoco_pos_aula", return_value=ALMOCO):
            volta = Commute(self.db).volta_puc(DIA.date())
        self.assertEqual((volta.start, volta.end), (at(16, 6), at(16, 51)))
        with patch("meals.Meals.almoco_pos_aula", return_value=None):
            self.assertEqual(Commute(self.db).volta_puc(DIA.date()).start, at(15, 0))

    def test_entre_a_aula_e_a_volta_ela_esta_na_puc(self):
        m = WorldStateManager(self.db)
        with patch("meals.Meals.almoco_pos_aula", return_value=ALMOCO):
            self.assertIsNone(m._depois_da_aula(at(14, 59)))              # ainda na aula
            saindo = m._depois_da_aula(at(15, 1))
            almocando = m._depois_da_aula(at(15, 30))
            indo = m._depois_da_aula(at(16, 3))
            self.assertIsNone(m._depois_da_aula(at(16, 6)))               # a volta é do trajeto
        self.assertEqual((saindo["activity"], saindo["place_key"]),
                         ("saindo da aula, indo almoçar no restaurante da PUC", "puc_rio"))
        self.assertEqual(almocando["activity"],
                         "almoçando no restaurante da PUC (salada com frango no restaurante do campus)")
        self.assertEqual(indo["activity"], "saindo da PUC pra voltar pra casa")
        with patch("meals.Meals.almoco_pos_aula", return_value=None):
            self.assertIsNone(m._depois_da_aula(at(15, 1)))               # volta direto: nada no meio

    def test_passeio_do_milo_conta_a_chegada_de_verdade(self):
        with patch("meals.Meals.almoco_pos_aula", return_value=ALMOCO):
            ocupada = RoutineEngine(self.db)._class_busy(DIA.date())
        self.assertEqual(ocupada[1], at(16, 51))
        with patch("meals.Meals.almoco_pos_aula", return_value=None):
            self.assertEqual(RoutineEngine(self.db)._class_busy(DIA.date())[1], at(15, 45))


class EmendaDoMiloTest(unittest.TestCase):
    def test_passeio_do_milo_nao_sai_da_puc_nem_vai_da_enseada_pra_outro_lugar(self):
        volta_puc = Leg("commute:2026-09-29:puc:volta", at(16, 6), at(16, 51), "metro_onibus", "volta", "da PUC", "Gávea")
        ida_milo = Leg("commute:2026-09-29:milo:ida", at(16, 21), at(16, 25), "a_pe", "ida", "pra Enseada", "Botafogo")
        volta_milo = Leg("commute:2026-09-29:milo:volta", at(17, 42), at(17, 46), "a_pe", "volta", "da Enseada", "Botafogo")
        ida_unhas = Leg("commute:unhas:2026-09-29:1721:ida", at(17, 32), at(17, 42), "a_pe", "ida",
                        "pro Ophicina do Cabelo", "Botafogo")
        out = Commute._emendas([volta_puc, ida_milo, volta_milo, ida_unhas])
        self.assertIn(volta_puc, out)
        self.assertIn(volta_milo, out)
        self.assertEqual({l.origem for l in out}, {""})


class PlantaoDeAmanhaTest(Base):
    def test_data_relativa_vira_o_dia_de_quando_foi_anotado(self):
        self.assertEqual(ancorar_datas("Patrick terá um plantão amanhã e está se preparando", "2026-09-27T18:15:31"),
                         "Patrick terá um plantão na segunda (28/09) e está se preparando")
        self.assertEqual(ancorar_datas("Ver depois de amanhã; hoje não, ontem sim", datetime(2026, 9, 29, 12)),
                         "Ver na quinta (01/10); na terça (29/09) não, na segunda (28/09) sim")
        self.assertEqual(ancorar_datas("Nada relativo aqui", "2026-09-29T10:00"), "Nada relativo aqui")

    def test_prompt_e_checkin_leem_a_data(self):
        lid = self.db.adicionar_open_loop("other", "Patrick terá um plantão amanhã")
        with self.db.get_connection() as conn:                 # anotado em 27/09, como o de produção
            conn.execute("UPDATE open_loops SET content='Patrick terá um plantão amanhã', created_at=?, "
                         "next_check_after=? WHERE id=?", ("2026-09-27T18:15:31", "2026-09-28T00:00:00", lid))
            conn.commit()
        ativos = self.db.get_open_loops_ativos(limit=5)
        self.assertEqual([l["content"] for l in ativos], ["Patrick terá um plantão na segunda (28/09)"])
        prontos = self.db.get_open_loops_para_checkin(now=datetime(2026, 9, 29, 19, 1))
        self.assertEqual([l["content"] for l in prontos], ["Patrick terá um plantão na segunda (28/09)"])


class MiloEsperaOBanhoTest(Base):
    def setUp(self):
        super().setUp()
        item = {"key": "milo:2026-09-29:manha", "at": at(5, 39), "minutes": 10, "state": False,
                "summary": "Desceu rapidinho com o Milo pro xixi da manhã."}
        self._patch("milo.Milo.day_plan", return_value=[item])
        self._patch("meals.Meals._floor", return_value=at(0, 0))
        self._patch("milo._saiu", return_value=False)

    def _xixi(self):
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT event_at FROM life_events WHERE event_key='milo:2026-09-29:manha'").fetchone()
        return row["event_at"] if row else None

    def test_no_banho_espera_e_desce_quando_sai(self):
        with patch("meals.Meals._transition_busy", return_value=True):
            Milo(self.db).materialize(at(5, 40))
        self.assertIsNone(self._xixi())
        with patch("meals.Meals._transition_busy", return_value=False):
            Milo(self.db).materialize(at(5, 50))
        self.assertEqual(self._xixi(), at(5, 50).isoformat())

    def test_passou_uma_hora_nao_desce_mais(self):
        with patch("meals.Meals._transition_busy", return_value=False):
            Milo(self.db).materialize(at(6, 45))
        self.assertIsNone(self._xixi())


class BeliscoNaPucTest(Base):
    def setUp(self):
        super().setUp()
        self._patch("academic_life.AcademicLife.blocks_on", side_effect=lambda d: AULAS if d == DIA.date() else [])
        self._patch("meals.Meals._transition_busy", return_value=False)
        self._patch("meals.Meals.hunger", return_value=0.8)
        self._patch("meals.Meals.day_plan", return_value=[ALMOCO])

    def _na_aula(self, block_id=7):
        return patch("world_repository.WorldStateRepository.latest", return_value={
            "activity": "na faculdade (Fundamentos em Ergodesign)",
            "source_json": json.dumps({"reason": "confirmed_commitment", "academic_block_id": block_id})})

    def _beliscos(self):
        with self.db.get_connection() as conn:
            return [r["summary"] for r in conn.execute("SELECT summary FROM life_events WHERE event_type='snack'")]

    def test_com_fome_belisca_na_troca_de_aula(self):
        with self._na_aula():
            self.assertEqual(Meals(self.db)._belisca_na_puc(at(11, 47), at(0, 0)), 0)   # no meio da aula: espera
            self.assertEqual(Meals(self.db)._belisca_na_puc(at(13, 3), at(0, 0)), 1)
            self.assertEqual(Meals(self.db)._belisca_na_puc(at(13, 8), at(0, 0)), 0)    # já beliscou
        (texto,) = self._beliscos()
        self.assertRegex(texto, r"^Beliscou .*(cantina da PUC|entre as aulas)\.$")

    def test_sem_fome_ou_fora_da_aula_nao_belisca(self):
        with self._na_aula(), patch("meals.Meals.hunger", return_value=0.3):
            self.assertEqual(Meals(self.db)._belisca_na_puc(at(13, 3), at(0, 0)), 0)
        with self._na_aula(block_id=None):
            self.assertEqual(Meals(self.db)._belisca_na_puc(at(13, 3), at(0, 0)), 0)
        with self._na_aula():
            self.assertEqual(Meals(self.db)._belisca_na_puc(at(7, 3), at(0, 0)), 0)     # primeira aula: não


class CoisaDeCasaEsperaEleChegarTest(Base):
    def setUp(self):
        super().setUp()
        self._patch("casa.Casa.day_plan", side_effect=lambda d: [
            {"key": "casa:2026-09-29:perrengue", "at": at(15, 37),
             "summary": "O Seu Jorge contou uma fofoca do prédio quando ela passou pela portaria."}]
            if d == DIA.date() else [])
        self._patch("meals.Meals._floor", return_value=at(0, 0))

    def _quando(self):
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT event_at FROM life_events WHERE event_key='casa:2026-09-29:perrengue'").fetchone()
        return row["event_at"] if row else None

    def test_fofoca_da_portaria_so_quando_ela_chega(self):
        with patch("meals.Meals._at_home", return_value=False):
            Casa(self.db).materialize(at(15, 40))
        self.assertIsNone(self._quando())
        with patch("meals.Meals._at_home", return_value=True), patch("meals.Meals._away_at", return_value=True):
            Casa(self.db).materialize(at(16, 55))
        self.assertEqual(self._quando(), at(16, 55).isoformat())


_spec = importlib.util.spec_from_file_location(
    "relatorio_soak", Path(__file__).resolve().parents[1] / "scripts" / "relatorio_soak.py")
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)


def _estado(activity, region="Botafogo"):
    return {"activity": activity, "location_region": region, "sit": rs.situacao(activity, region), "at": at(12, 0)}


class RelatorioDia1Test(unittest.TestCase):
    def test_trabalho_na_rua_e_na_manicure(self):
        self.assertTrue(rs.atividade_contradiz("Tô terminando umas referências do trabalho aqui",
                                               [_estado("indo da PUC pra Enseada a pé", "a caminho (Botafogo)")]))
        self.assertTrue(rs.atividade_contradiz("Termino esse trabalho e fico com você depois, amor",
                                               [_estado("Fazendo as unhas na Ophicina do Cabelo")]))
        self.assertFalse(rs.atividade_contradiz("Tô terminando umas referências do trabalho aqui",
                                                [_estado("em casa, montando looks (closet)")]))
        self.assertFalse(rs.atividade_contradiz("tô fazendo o trabalho na biblioteca",
                                                [_estado("na faculdade (O Cristianismo)", "Gávea")]))

    def test_saudacao_fora_de_hora(self):
        self.assertEqual(rs.saudacao_fora_de_hora("Fico feliz que chegou bem Boa noite, te amo", at(5, 36)), "boa noite")
        self.assertEqual(rs.saudacao_fora_de_hora("Boa noite, meu futuro marido", at(22, 31)), "")
        self.assertEqual(rs.saudacao_fora_de_hora("Bom dia, amor", at(6, 41)), "")


if __name__ == "__main__":
    unittest.main()
