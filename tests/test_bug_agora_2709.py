"""Bug do uso real: desencontros do mundo, da aba Agora e do chat em 27/09 (varredura das 24 h), com os horários do caso.

1. Dois banhos no Se arrumando: banho de verdade 13:51–13:59; o "vai de uber" das 14:02 mudou a ida e o card voltou
   pro "Tomando banho" (14:03–14:16).
2. "Refri" das 15:13 às 19:00 no Shopping da Gávea: o rolê do cinema não tinha sessão; ela inventou o filme.
3. Farmácia "saindo do Shopping": voltou de uber (19:00–19:20), em casa deu vontade de ir à Pacheco (19:23), e a ida
   saiu "do Shopping da Gávea, a pé" desde 19:00 — a volta de uber sumiu.
4. "Tô no Shopping da Gávea ainda" às 19:37, na farmácia: o prompt dizia "local reservado" e não dizia que ela voltou.
5. Beliscou iogurte às 19:28, já saindo pra farmácia.
6. "Te aviso quando estiver indo pra casa" (19:42) e não avisou: só existia promessa de chegada.
7. Jantou tapioca às 21:32 com o McDonald's que ele avisou ("pedi, tá chegando") a caminho; recebeu "de surpresa".
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import arrival_promise
import cinema
import delivery
from agenda import Agenda
from commute import Commute, Leg
from db import DatabaseManager
from meals import Meals, MealSlot
from response_availability import ResponseAvailabilityPolicy
from seed_world_bible_v36 import seed_world_bible
from world_context import WorldContextBuilder

DIA = datetime(2026, 9, 27)
IDA = Leg("commute:outing:2026-09-27:c3:ida", DIA.replace(hour=14, minute=38), DIA.replace(hour=15), "uber",
          "ida", "pro Shopping da Gávea", "Gávea")
VOLTA = Leg("commute:outing:2026-09-27:c3:volta", DIA.replace(hour=19), DIA.replace(hour=19, minute=20), "uber",
            "volta", "do Shopping da Gávea", "Gávea")
FILME = {"titulo": "Idiotas", "minutos": 95}


def at(h, m):
    return DIA.replace(hour=h, minute=m)


def _evento(db, key, quando, tipo, summary):
    with db.get_connection() as conn:
        conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,autonomy_level,
                        importance,participants_json,share_worthy,created_at)
                        VALUES (?,?,?,?,?,'simulated',1,0.1,'["marina"]',0.1,?)""",
                     (key, quando.isoformat(), tipo, tipo, summary, quando.isoformat()))
        conn.commit()


def _fala(db, quando, role, texto):
    with db.get_connection() as conn:
        conn.execute("INSERT INTO conversas (timestamp, role, content) VALUES (?,?,?)",
                     (quando.isoformat(), role, texto))
        conn.commit()


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "a.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO eventos_pendentes (event_type, description, event_at, end_at, status, confirmed,
                            source_key, location_key, metadata_json, created_at)
                            VALUES ('social','Cinema e shopping com a Bia no Shopping da Gávea',?,?,'pending',1,?,?,?,?)""",
                         ("2026-09-27T15:00:00", "2026-09-27T19:00:00", "outing:2026-09-27:c3", "shopping_gavea",
                          json.dumps({"friends": ["bia_andrade"], "origin": "convite"}), "2026-09-27T11:02:14"))
            conn.commit()
        for alvo, kw in (("commute.Commute.legs_on", {"side_effect": lambda day: [IDA, VOLTA] if day == DIA.date() else []}),
                         ("agenda.Agenda._refeicoes_em_casa", {"return_value": []}),
                         ("academia.Academia.plano", {"return_value": None}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("sleep_plan.SleepPlan.wake", {"return_value": at(9, 10)}),
                         ("sleep_plan.SleepPlan.bed", {"return_value": datetime(2026, 9, 28, 1, 0)}),
                         ("cinema.filme", {"return_value": FILME})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()


class DoisBanhosTest(Base):
    def setUp(self):
        super().setUp()
        _evento(self.db, "banho:2026-09-27T1351", at(13, 51), "routine", "Tomou banho (13:51–13:59).")

    def _prep(self, now):
        return next(e for e in Agenda(self.db).etapas(DIA.date(), now) if e.tipo == "arrumando")

    def test_o_banho_que_aconteceu_e_o_banho_do_se_arrumando(self):
        prep = self._prep(at(14, 3))
        self.assertEqual(prep.inicio, at(13, 51))
        self.assertEqual((prep.passos[0].texto, prep.passos[0].inicio), ("Tomando banho", at(13, 51)))
        self.assertEqual([p.texto for p in prep.passos[1:]], ["Fazendo maquiagem", "Escolhendo roupa", "Chamando o Uber"])
        self.assertEqual(prep.passos[1].inicio, at(13, 59))
        for minuto in range(0, 38):                    # 14:00–14:37: banho nunca mais
            agora = Agenda(self.db).prep_activity(at(14, minuto))
            self.assertNotIn("banho", agora["activity"], minuto)

    def test_banho_bem_antes_so_tira_o_passo(self):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM life_events")
            conn.commit()
        _evento(self.db, "banho:2026-09-27T1240", at(12, 40), "routine", "Tomou banho (12:40–12:55).")
        prep = self._prep(at(14, 10))
        self.assertGreater(prep.inicio, at(13, 30))
        self.assertNotIn("Tomando banho", [p.texto for p in prep.passos])

    def test_sem_banho_ainda_o_passo_continua(self):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM life_events")
            conn.commit()
        self.assertEqual(self._prep(at(14, 10)).passos[0].texto, "Tomando banho")


class CinemaTest(Base):
    def test_card_mostra_a_sessao_e_depois_o_passeio(self):
        ag = Agenda(self.db)
        agora = lambda t: [p["texto"] for i in ag.card(t)["linha"] for p in i["passos"] if p["estado"] == "agora"]
        self.assertEqual(agora(at(16, 0)), ["Assistindo: Idiotas"])
        self.assertIn(["device-mobile", "Celular", "Na bolsa, silenciado"], ag.card(at(16, 0))["grade"])
        self.assertIn(agora(at(18, 16))[0], ("Olhando as lojas", "No provador"))
        self.assertNotEqual(agora(at(17, 50)), ["Refri"])

    def test_sessao_cabe_no_role(self):
        outing = cinema._outing(self.db, 1)
        s = cinema.sessao(self.db, outing)
        self.assertGreater(s["inicio"], at(15, 5))
        self.assertEqual(s["fim"] - s["inicio"], timedelta(minutes=95 + cinema.TRAILERS_MIN))
        self.assertLessEqual(s["fim"], at(18, 50))

    def test_prompt_e_mundo_sabem_o_filme(self):
        linha = cinema.linha_prompt(self.db, 1, at(18, 16))
        self.assertIn('"Idiotas"', linha)
        self.assertIn("foi das", linha)
        self.assertIn("DENTRO da sessão", cinema.linha_prompt(self.db, 1, at(16, 0)))
        s = cinema.na_sessao(self.db, 1, at(16, 0))
        act = f"Cinema e shopping com a Bia no Shopping da Gávea ({cinema.atividade(s)})"
        self.assertEqual(ResponseAvailabilityPolicy(self.db)._map_place_activity("shopping_gavea", act), "CLASS")
        self.assertIsNone(cinema.na_sessao(self.db, 1, at(18, 16)))


class FarmaciaTest(Base):
    PACHECO = Leg("commute:vontade:2026-09-27:1923:ida", at(19, 31), at(19, 35), "a_pe", "ida",
                  "pra Drogarias Pacheco", "Botafogo", decidido_em=at(19, 23))

    def test_decidiu_em_casa_sai_de_casa(self):
        legs = Commute._emendas([VOLTA, self.PACHECO])
        self.assertIn(VOLTA, legs, "a volta de uber do shopping continua")
        ida = next(l for l in legs if l.direction == "ida")
        self.assertEqual((ida.start, ida.origem), (at(19, 31), ""))

    def test_emenda_de_antes_continua(self):
        sem_decisao = Leg(self.PACHECO.key, at(19, 31), at(19, 35), "a_pe", "ida", "pra Drogarias Pacheco", "Botafogo")
        legs = Commute._emendas([VOLTA, sem_decisao])
        self.assertNotIn(VOLTA, legs)
        self.assertEqual(legs[0].origem, "do Shopping da Gávea")

    def test_prompt_diz_que_voltou_e_saiu_de_novo(self):
        with patch("commute.Commute.ultima_volta", return_value=VOLTA):
            linha = WorldContextBuilder(self.db)._saiu_de_novo(at(19, 37), "Drogarias Pacheco")
        self.assertIn("chegou em casa às 19:20", linha)
        self.assertIn("NÃO está mais no Shopping da Gávea", linha)

    def test_sem_mascara_de_local_reservado(self):
        import inspect
        import world_context
        self.assertNotIn("location = 'local reservado'", inspect.getsource(world_context))

    def test_nao_belisca_saindo_de_casa(self):
        m = Meals(self.db)
        with patch.object(Agenda, "agora", return_value=object()):
            self.assertTrue(m._numa_etapa(at(19, 28)))
        with patch.object(Agenda, "agora", return_value=None):
            self.assertFalse(m._numa_etapa(at(20, 30)))


class AvisoIndoPraCasaTest(Base):
    def test_promessa_de_saida_amarra_no_comeco_da_volta(self):
        p = arrival_promise.observe(
            self.db, "Aaaah, amor, você não existe kkk / Vou pedir o Uber daqui a pouco e te aviso quando estiver "
            "indo pra casa, tá?", "Quando for pra casa avisa, vou pedir comida p vc", at(18, 42))
        self.assertEqual((p["kind"], p["leg"]), ("saida", VOLTA.key))
        self.assertIsNone(arrival_promise.due(self.db, at(18, 59)), "ainda no shopping")
        self.assertIsNotNone(arrival_promise.due(self.db, at(19, 3)), "entrou no uber: avisa")

    def test_ja_disse_que_saiu_nao_repete(self):
        arrival_promise.observe(self.db, "te aviso quando estiver indo pra casa", "", at(18, 42))
        _fala(self.db, at(18, 58), "assistant", "Tô indo pra casa agora, amor")
        self.assertIsNone(arrival_promise.due(self.db, at(19, 3)))

    def test_chegada_continua_igual(self):
        p = arrival_promise.observe(self.db, "Fechou, te aviso quando chegar em casa", "", at(18, 42))
        self.assertNotEqual(p.get("kind"), "saida")


class PresenteAvisadoTest(Base):
    def _pedido(self):
        _fala(self.db, at(21, 28), "user", "Oww vou pedir tua comida, tá com vontade de que?")
        _fala(self.db, at(21, 28), "assistant", "Pode ser hambúrguer com batata, amor. Hoje eu tô faminta mesmo")
        delivery.gift(self.db, what="McOferta Média Big Mac", restaurant="McDonald's", price=45, eta_min=(30, 30),
                      note="", now=at(21, 31))
        _fala(self.db, at(21, 31), "user", "Pedi, tá chegando em uns 30 minutos")

    def test_jantar_espera_a_comida_que_ele_avisou(self):
        self._pedido()
        m = Meals(self.db)
        self.assertTrue(m._comida_chegando(at(21, 32)))
        jantar = MealSlot("jantar", "meal:2026-09-27:jantar", at(21, 32), 26, "casa", "tapioca de queijo com presunto")
        with patch.object(Meals, "day_plan", return_value=[jantar]), patch.object(Meals, "_floor", return_value=at(0, 0)), \
                patch.object(Meals, "_at_home", return_value=True), patch.object(Meals, "_away_at", return_value=False):
            m.materialize(at(21, 40))
        self.assertFalse(m._logged(DIA.date(), "jantar"), "não jantou tapioca")
        self.assertIn("chega lá pelas 22:01", " ".join(delivery.prompt_lines(self.db, at(21, 40))))

    def test_recebe_sem_ser_surpresa(self):
        self._pedido()
        self.assertEqual(delivery.gift_tick(self.db, at(22, 1), can_receive=True), "recebido")
        with self.db.get_connection() as conn:
            summary = conn.execute("SELECT summary FROM life_events WHERE title='presente do Patrick'").fetchone()[0]
        self.assertNotIn("surpresa", summary)
        self.assertIn("foi comer", summary)

    def test_sem_aviso_continua_surpresa(self):
        delivery.gift(self.db, what="Açaí", restaurant="Oakberry", price=30, eta_min=(30, 30), note="", now=at(21, 31))
        self.assertFalse(delivery.avisado(self.db, now=at(21, 40)))
        self.assertFalse(Meals(self.db)._comida_chegando(at(21, 40)))
        self.assertEqual(delivery.prompt_lines(self.db, at(21, 40)), [])


if __name__ == "__main__":
    unittest.main()
