"""Etapas do dia e card da aba Agora (Patrick, 26/09, decidido linha a linha com ele)."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import agenda
from agenda import Agenda
from commute import Leg
from db import DatabaseManager
from response_availability import ResponseAvailabilityPolicy
from seed_world_bible_v36 import seed_world_bible

DIA = datetime(2026, 9, 25)
IDA = Leg("commute:outing:2026-09-25:0:ida", DIA.replace(hour=19, minute=10), DIA.replace(hour=19, minute=30), "carona",
          "ida", "pro Quartinho Bar", "Botafogo", "o Theo")
VOLTA = Leg("commute:outing:2026-09-25:0:volta", DIA.replace(hour=22, minute=30), DIA.replace(hour=22, minute=50), "uber",
            "volta", "do Quartinho Bar", "Botafogo", "", "o motorista do uber errou o caminho",
            DIA.replace(hour=22, minute=40))


class FormatoTest(unittest.TestCase):
    def test_horas_e_duracao(self):
        self.assertEqual(agenda.aprox(DIA.replace(hour=20, minute=3)), "~20:05")
        self.assertEqual(agenda.duracao(timedelta(minutes=70)), "1h 10min")
        self.assertEqual(agenda.duracao(timedelta(minutes=47)), "47min")
        self.assertEqual(agenda.duracao(timedelta(hours=2)), "2h")
        self.assertEqual(agenda.em_bairro("Gávea"), "na Gávea")
        self.assertEqual(agenda.em_bairro("Botafogo"), "em Botafogo")


class AgendaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "a.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO eventos_pendentes (event_type, description, event_at, end_at, status, confirmed,
                            source_key, location_key, metadata_json, created_at)
                            VALUES ('social','Saindo com o Theo e a Júlia no Quartinho Bar',?,?,'pending',1,?,?,?,?)""",
                         ("2026-09-25T19:30:00", "2026-09-25T22:30:00", "outing:2026-09-25:0", "quartinho_bar",
                          json.dumps({"friends": ["theo_martins", "julia_azevedo"]}), "2026-09-20T00:00:00"))
            conn.commit()
        for alvo, valor in (("commute.Commute.legs_on", None), ("sleep_plan.SleepPlan.bed", DIA.replace(day=26, hour=1)),
                            ("sleep_plan.SleepPlan.wake", DIA.replace(hour=9))):
            p = (patch(alvo, side_effect=lambda day: [IDA, VOLTA] if day == DIA.date() else [])
                 if valor is None else patch(alvo, return_value=valor))
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_sequencia_do_role(self):
        etapas = Agenda(self.db).etapas(DIA.date(), DIA.replace(hour=23))
        self.assertEqual([e.tipo for e in etapas], ["arrumando", "caminho", "la", "voltando", "arrumando"])
        self.assertEqual([e.titulo for e in etapas],
                         ["Se arrumando", "A caminho", "No Quartinho", "Voltando pra casa", "Se arrumando"])
        prep = etapas[0]
        self.assertEqual([p.texto for p in prep.passos],
                         ["Tomando banho", "Secando cabelo", "Fazendo maquiagem", "Escolhendo roupa", "Esperando carona"])
        self.assertEqual(prep.fim, IDA.start)
        self.assertTrue(60 <= (IDA.start - prep.inicio).total_seconds() / 60 <= 90)
        self.assertEqual([p.texto for p in etapas[1].passos], ["No carro com o Theo", "Chegando no Quartinho"])
        self.assertEqual(etapas[-1].linha2, "Vai dormir às ~01:00")
        self.assertEqual([p.texto for p in etapas[-1].passos], ["Tirando maquiagem", "Tomando banho", "Colocando pijama"])

    def test_card_se_arrumando(self):
        prep = Agenda(self.db).etapas(DIA.date(), DIA)[0]
        c = Agenda(self.db).card(prep.inicio + timedelta(minutes=30))
        self.assertEqual(c["titulo"], "Se arrumando")
        self.assertEqual(c["linha2"], "Vai sair pro Quartinho Bar às ~19:10")
        self.assertEqual([g[1] for g in c["grade"]], ["Com", "Celular"])
        self.assertEqual(c["grade"][0][2], "Theo e Júlia")
        self.assertEqual(c["grade"][1][2], "Olha de vez em quando")
        self.assertEqual(c["barra"]["meio"].split(" · ")[0], "há 30min")
        atual = next(e for e in c["linha"] if e["estado"] == "agora")
        self.assertTrue(atual["passos"])

    def test_card_no_bar_so_mostra_o_que_ja_pediu(self):
        now = DIA.replace(hour=20, minute=30)
        c = Agenda(self.db).card(now)
        self.assertEqual((c["titulo"], c["linha2"]), ("No Quartinho", "Volta pra casa às ~22:30"))
        self.assertEqual(c["grade"][0], ["geo-alt", "Onde", "Botafogo"])
        from consumo import plan
        with self.db.get_connection() as conn:
            outing = dict(conn.execute("SELECT * FROM eventos_pendentes").fetchone())
        pedidos = [i for i in plan(outing) if i.at <= now]
        passos = next(e for e in c["linha"] if e["estado"] == "agora")["passos"]
        self.assertEqual(len(passos), len(pedidos))
        self.assertTrue(all(p["valor"] for p in passos))
        self.assertNotIn("faltam", c["barra"]["meio"])

    def test_volta_de_uber_com_imprevisto_curto(self):
        c = Agenda(self.db).card(DIA.replace(hour=22, minute=45))
        self.assertEqual(c["titulo"], "Voltando pra casa")
        self.assertIn(["car-front", "Como", "Uber"], c["grade"])
        passos = next(e for e in c["linha"] if e["estado"] == "agora")["passos"]
        self.assertIn(("Motorista errou o caminho", "aviso"), [(p["texto"], p["estado"]) for p in passos])
        self.assertTrue(any(p["valor"] for p in passos if p["texto"] == "No uber"))

    def test_se_arrumando_vira_atividade_e_disponibilidade_propria(self):
        prep = Agenda(self.db).etapas(DIA.date(), DIA)[0]
        act = Agenda(self.db).prep_activity(prep.inicio + timedelta(minutes=2))
        self.assertEqual(act["activity"], "se arrumando pra sair pro Quartinho Bar (tomando banho)")
        mapa = ResponseAvailabilityPolicy(self.db)._map_place_activity
        self.assertEqual(mapa("marina_apartment", act["activity"]), "GETTING_READY")
        self.assertEqual(mapa("marina_apartment", "se arrumando pra dormir (colocando pijama)"), "GETTING_READY")
        self.assertEqual(mapa("marina_apartment", "dormindo"), "SLEEPING")

    def test_fora_de_etapa_nao_tem_card(self):
        self.assertIsNone(Agenda(self.db).card(DIA.replace(hour=12)))


if __name__ == "__main__":
    unittest.main()


class CardCasaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "c.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        for alvo in ("commute.Commute.legs_on",):
            p = patch(alvo, return_value=[])
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _snap(self, activity, now, plano=None):
        from world_state import WorldStateManager
        WorldStateManager(self.db).states.add_snapshot({
            "state_date": now.date().isoformat(), "observed_at": now.isoformat(), "location_place_id": 1,
            "location_region": "Botafogo", "activity": activity, "energy_level": 0.6, "weather_context_json": None,
            "current_plan_json": plano, "source_json": {"truth_type": "system", "reason": "x"}})

    def test_tempo_livre(self):
        from tempo_livre import TempoLivre
        now = DIA.replace(hour=14, minute=10)
        with patch.object(TempoLivre, "_quer_se_tocar", return_value=False):
            b = TempoLivre(self.db).agora(now)
        self._snap(b.atividade, now)
        c = Agenda(self.db).card_casa(now + timedelta(minutes=2), "Olha com frequência")
        self.assertEqual((c["titulo"], c["linha2"]), ("Em casa", b.texto))
        self.assertIn(["door-open", "Cômodo", b.comodo_nome], c["grade"])
        self.assertEqual(c["grade"][0], ["geo-alt", "Onde", "Botafogo"])
        self.assertEqual(next(x for x in c["linha"] if x["estado"] == "agora")["texto"], b.texto)

    def test_refeicao_se_alimentando(self):
        now = DIA.replace(hour=20, minute=10)
        self._snap("jantando em casa", now, {"activity": "jantando em casa", "start_at": now.isoformat(),
                                              "end_at": (now + timedelta(minutes=30)).isoformat()})
        c = Agenda(self.db).card_casa(now + timedelta(minutes=5), "Olha de vez em quando")
        self.assertEqual((c["titulo"], c["linha2"]), ("Se alimentando", "Jantando"))
        self.assertEqual(c["barra"]["meio"], "há 5min · faltam ~25min")

    def test_passeio_do_milo_e_saida(self):
        now = DIA.replace(hour=9, minute=0)
        self._snap("passeando com Milo", now, {"activity": "passeando com Milo", "start_at": now.isoformat(),
                                                "end_at": (now + timedelta(minutes=30)).isoformat()})
        c = Agenda(self.db).card_casa(now + timedelta(minutes=10), "Olha de vez em quando")
        self.assertEqual(c["titulo"], "Na Enseada")
        self.assertEqual(c["linha2"], "Volta pra casa às ~09:30")
        self.assertIn(["people", "Com", "Milo"], c["grade"])
