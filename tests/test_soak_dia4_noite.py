"""Soak, dia 4 (02/10), da tarde em diante — lido em 03/10:
1. 19:44 "Quer que eu pague um Uber?" → "Quero sim, melhor ir de Uber com essa chuva": o combinado não pegou e ela foi
   a pé, na chuva, com os R$ 200 do Uber na conta.
2. 20:05/20:06 "encontrou a Júlia no Quartinho" e caipirinha com ela ainda em casa (chegou 22 min atrasada).
3. 23:26 "Se divertindo ainda" em casa desde 23:06; 23:43 "cheguei e apaguei no sofá" (TikTok, Milo, série).
4. 23:45 "Já sim, banho tomado" — o [BANHO — FATO] dizia "a resposta é sim" pelo banho das 18:31, antes do rolê.
5. "vele" no fim da fala (20:30, 23:39).
6. Aviso de chegada: esquecido por sorteio; "assim que eu sair te mando mensagem" nem virou promessa; a volta da
   noite sem aviso (o Patrick, 03/10: avisa quando ele pede ou quando é de bom tom).
7. Chuva (não chuvisco) tira a ida a pé (Patrick, 03/10).
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import arrival_promise
from commute import Leg
from db import DatabaseManager

DIA = datetime(2026, 10, 2)
IDA = Leg("commute:outing:2026-10-02:m1931:ida", datetime(2026, 10, 2, 19, 50), datetime(2026, 10, 2, 20, 0),
          "a_pe", "ida", "pro Quartinho Bar", "Botafogo", compromisso="outing:2026-10-02:m1931")
VOLTA = Leg("commute:outing:2026-10-02:m1931:volta", datetime(2026, 10, 2, 23, 0), datetime(2026, 10, 2, 23, 6),
            "uber_dividido", "volta", "do Quartinho Bar", "Botafogo", companion="a Júlia")


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "d.db")
        self.legs = [IDA, VOLTA]
        p = patch("commute.Commute.legs_on", side_effect=lambda day, *a, **k: list(self.legs) if day == DIA.date() else [])
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()


class AvisoTest(_Base):
    def test_saida_e_chegada_no_mesmo_prometo(self):
        """19:51: "Aviso sim, amor Assim que eu sair te mando mensagem E quando chegar no Quartinho também, prometo"."""
        arrival_promise.observe(self.db, "Aviso sim, amor Assim que eu sair te mando mensagem E quando chegar no "
                                "Quartinho também, prometo", "Quando estiver saindo me avisa E quando chegar lá também",
                                datetime(2026, 10, 2, 19, 51))
        saida = arrival_promise.due(self.db, IDA.start + timedelta(minutes=3))
        self.assertEqual((saida["kind"], saida["direction"]), ("saida", "ida"))
        self.assertIsNone(arrival_promise.due(self.db, IDA.end - timedelta(minutes=1)))
        chegada = arrival_promise.due(self.db, IDA.end + timedelta(minutes=7))
        self.assertEqual((chegada["kind"], chegada["where"]), ("chegada", "no Quartinho Bar"))

    def test_sem_sorteio_pra_esquecer(self):
        self.assertFalse(hasattr(arrival_promise, "FORGET_CHANCE"))

    def test_o_atraso_empurra_o_aviso(self):
        """Ela prometeu às 19:51 com a ida planejada pras 20:00; chegou 20:22 — o aviso é depois de chegar."""
        arrival_promise.observe(self.db, "te aviso quando chegar no Quartinho", "", datetime(2026, 10, 2, 19, 45))
        from dataclasses import replace
        self.legs = [replace(IDA, start=IDA.start + timedelta(minutes=22), end=IDA.end + timedelta(minutes=22)), VOLTA]
        self.assertIsNone(arrival_promise.due(self.db, IDA.end + timedelta(minutes=8)), "ainda a caminho")
        self.assertIsNotNone(arrival_promise.due(self.db, IDA.end + timedelta(minutes=30)))

    def test_volta_da_noite_avisa_sem_ele_pedir(self):
        self.assertIsNone(arrival_promise.implicitas(self.db, IDA.start + timedelta(minutes=2)), "ida de dia: não")
        p = arrival_promise.implicitas(self.db, VOLTA.start + timedelta(minutes=1))
        self.assertEqual(p["where"], "em casa")
        self.assertIsNone(arrival_promise.implicitas(self.db, VOLTA.start + timedelta(minutes=2)), "uma vez só")
        self.assertIsNotNone(arrival_promise.due(self.db, VOLTA.end + timedelta(minutes=7)))

    def test_ja_tinha_dito_que_chegou(self):
        arrival_promise.implicitas(self.db, VOLTA.start + timedelta(minutes=1))
        self.db.adicionar_mensagem(role="assistant", content="Cheguei, amor",
                                   timestamp=(VOLTA.end + timedelta(minutes=1)).isoformat())
        self.assertIsNone(arrival_promise.due(self.db, VOLTA.end + timedelta(minutes=7)))

    def test_depois_da_cobranca_avisa_qualquer_chegada(self):
        """20:30: "Esqueceu de avisar né?!" — daí em diante a chegada do rolê é avisada mesmo de dia."""
        cedo = Leg("commute:outing:2026-10-02:x:volta", datetime(2026, 10, 2, 20, 40), datetime(2026, 10, 2, 20, 50),
                   "a_pe", "volta", "do Rei do Mate", "Botafogo")
        self.legs = [cedo]
        self.assertIsNone(arrival_promise.implicitas(self.db, datetime(2026, 10, 2, 20, 41)))
        self.db.set_estado_relacional(arrival_promise.FEITAS_KEY, "[]")
        self.db.adicionar_mensagem(role="user", content="Esqueceu de avisar né?! Vc n é mole",
                                   timestamp=datetime(2026, 10, 2, 20, 30).isoformat())
        self.assertIsNotNone(arrival_promise.implicitas(self.db, datetime(2026, 10, 2, 20, 42)))

    def test_formato_antigo_ainda_vale(self):
        self.db.set_estado_relacional(arrival_promise.KEY, json.dumps(
            {"made_at": "2026-10-02T19:51:00", "leg": IDA.key, "due_at": "2026-10-02T20:05:00", "where": "no Quartinho Bar"}))
        self.assertIsNotNone(arrival_promise.due(self.db, datetime(2026, 10, 2, 20, 6)))


class UberCombinadoTest(_Base):
    def test_quero_sim_melhor_de_uber(self):
        from agenda_reativa import AgendaReativa
        trocados = AgendaReativa(self.db).combinar_uber(
            "Quero sim, melhor ir de Uber com essa chuva Aqui em Botafogo tá chovendo também",
            "Quer que eu pague um Uber? Tá chovendo aqui, n sei aí", datetime(2026, 10, 2, 19, 44))
        self.assertIn(IDA.key, trocados)

    def test_recusa_continua_recusa(self):
        from agenda_reativa import AgendaReativa
        self.assertEqual(AgendaReativa(self.db).combinar_uber(
            "Não precisa, amor, prefiro ir a pé", "Quer que eu pague um Uber?", datetime(2026, 10, 2, 19, 44)), [])


class ChuvaTest(unittest.TestCase):
    def test_chuva_tira_o_a_pe(self):
        import commute
        with tempfile.TemporaryDirectory() as tmp:
            c = commute.Commute(DatabaseManager(Path(tmp) / "c.db"))
            for cond, a_pe in (("rain", False), ("storm", False), ("drizzle", True), ("cloudy", True)):
                with patch.object(commute.Commute, "_tempo", return_value={"condition": cond}):
                    modos = {c._decide(DIA.date(), f"t{cond}{i}", "Botafogo", datetime(2026, 10, 2, 20, 0))[0]
                             for i in range(40)}
                self.assertEqual("a_pe" in modos, a_pe, cond)


class PromptDepoisDoRoleTest(_Base):
    def _mundo(self, *linhas):
        with self.db.get_connection() as conn:
            for at, act in linhas:
                conn.execute("INSERT INTO world_state(state_date, observed_at, activity, location_region) "
                             "VALUES (?,?,?,?)", (at.date().isoformat(), at.isoformat(), act, "Botafogo"))
            conn.commit()

    def test_em_casa_desde_23_06_vai_no_fim_do_prompt(self):
        from world_context import desde_que_voltou
        self._mundo((datetime(2026, 10, 2, 23, 9), "em casa, olhando o TikTok (sala)"),
                    (datetime(2026, 10, 2, 23, 14), "passeio rapidinho com o Milo (xixi da noite)"),
                    (datetime(2026, 10, 2, 23, 26), "vendo Paradise Kiss no sofá"))
        dica = desde_que_voltou(self.db, datetime(2026, 10, 2, 23, 26), datetime(2026, 10, 2, 21, 18))
        self.assertIn("23:06", dica)
        self.assertIn("olhando o TikTok", dica)
        self.assertIn("vendo Paradise Kiss", dica)
        self.assertIsNone(desde_que_voltou(self.db, datetime(2026, 10, 2, 23, 40), datetime(2026, 10, 2, 23, 27)),
                          "já conversaram depois de ela chegar")

    def test_banho_de_antes_do_role_nao_vale(self):
        """23:45 "Já tomou banho depois que voltou?" — o banho foi 18:31–19:00, antes do Quartinho."""
        from world_context import WorldContextBuilder
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,"
                         "autonomy_level,importance,participants_json,share_worthy,created_at) "
                         "VALUES ('banho:2026-10-02:noite','2026-10-02T18:31:00','routine','banho',"
                         "'Tomou banho (18:31–19:00).','simulated',1,0.1,'[]',0.1,'2026-10-02T18:31:00')")
            conn.commit()
        b = WorldContextBuilder.__new__(WorldContextBuilder)
        b.db = self.db
        fato = b._banho(datetime(2026, 10, 2, 23, 45))
        self.assertIn("NÃO tomou banho desde que voltou", fato)
        self.assertNotIn("a resposta é sim", fato)


class ConsumoNaChegadaTest(unittest.TestCase):
    def test_caipirinha_depois_de_chegar(self):
        """Ida planejada pras 20:00, chegou 20:22: a caipirinha não sai com ela em casa."""
        import consumo
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(Path(tmp) / "c.db")
            o = {"source_key": "outing:2026-10-02:m1931", "event_at": "2026-10-02T20:00:00",
                 "end_at": "2026-10-02T23:00:00", "location_key": "quartinho_bar",
                 "metadata_json": json.dumps({"friends": ["julia_azevedo"]})}
            with patch("commute.Commute.chegada", return_value=datetime(2026, 10, 2, 20, 22)):
                movido = consumo.Consumo(db)._na_chegada(o, DIA.date())
            self.assertEqual(movido["event_at"], "2026-10-02T20:22:00")
            self.assertTrue(all(i.at >= datetime(2026, 10, 2, 20, 22) for i in consumo.plan(movido)))


class FalaTest(unittest.TestCase):
    def test_vele_sai_da_fala(self):
        import bot
        self.assertEqual(bot.limpar_fala_marina("Kkkkk foi mal, amor, vacilei feio vele"),
                         "Kkkkk foi mal, amor, vacilei feio")
        self.assertEqual(bot.limpar_fala_marina("tô presa nesse vestidinho mesmo vele"),
                         "tô presa nesse vestidinho mesmo")


if __name__ == "__main__":
    unittest.main()
