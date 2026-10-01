"""Bug do uso real: Hoje desconexo do card (27/09, 01:05), com os horários do caso.

- Card "Se arrumando" (pra dormir) marcava banho às 01:00, com o banho de chegada rolando 00:31–01:12.
- Hoje mostrava "Tomou banho e lavou o cabelo 00:31–01:12" no passado, com o banho ainda acontecendo.
- "Olhou o Instagram 00:02–00:38": começou antes de ela chegar (00:05) e passou por cima do banho.
- "Beliscou pipoca vendo série" às 21:07, com ela no Quartinho Bar.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import hoje
from agenda import Agenda
from commute import Leg
from db import DatabaseManager
from meals import Meals, MealSlot
from seed_world_bible_v36 import seed_world_bible
from tempo_livre import TempoLivre

DIA = datetime(2026, 9, 26)
IDA = Leg("commute:outing:2026-09-26:c1:ida", DIA.replace(hour=20, minute=48), DIA.replace(hour=21), "a_pe",
          "ida", "pro Quartinho Bar", "Botafogo")
VOLTA = Leg("commute:outing:2026-09-26:c1:volta", DIA.replace(hour=23, minute=59), datetime(2026, 9, 27, 0, 5),
            "uber_dividido", "volta", "do Quartinho Bar", "Botafogo", "a Bia")
BED = datetime(2026, 9, 27, 1, 30)


def _evento(db, key, at, tipo, title, summary):
    with db.get_connection() as conn:
        conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,autonomy_level,
                        importance,participants_json,share_worthy,created_at)
                        VALUES (?,?,?,?,?,'simulated',1,0.1,'["marina"]',0.1,?)""",
                     (key, at.isoformat(), tipo, title, summary, at.isoformat()))
        conn.commit()


class BaseCaso(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "h.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO eventos_pendentes (event_type, description, event_at, end_at, status, confirmed,
                            source_key, location_key, metadata_json, created_at)
                            VALUES ('social','Saindo com a Bia no Quartinho Bar',?,?,'pending',1,?,?,?,?)""",
                         ("2026-09-26T21:00:00", "2026-09-26T23:59:00", "outing:2026-09-26:c1", "quartinho_bar",
                          json.dumps({"friends": ["bia_andrade"]}), "2026-09-26T19:00:00"))
            conn.commit()
        for alvo, valor in (("commute.Commute.legs_on", None), ("sleep_plan.SleepPlan.bed", BED),
                            ("sleep_plan.SleepPlan.wake", DIA.replace(hour=9, minute=1))):
            p = (patch(alvo, side_effect=lambda day: [IDA, VOLTA] if day == DIA.date() else [])
                 if valor is None else patch(alvo, return_value=valor))
            p.start()
            self.addCleanup(p.stop)
        _evento(self.db, "banho:2026-09-27T0031", datetime(2026, 9, 27, 0, 31), "routine", "banho",
                "Tomou banho e lavou o cabelo (00:31–01:12).")

    def tearDown(self):
        self.temp.cleanup()


class CardUmSoTest(BaseCaso):
    def test_banho_de_chegada_vira_o_banho_do_se_arrumando(self):
        prep = Agenda(self.db).etapas(DIA.date(), datetime(2026, 9, 27, 1, 5))[-1]
        self.assertEqual(prep.chave, "prep:dormir:2026-09-26")
        self.assertEqual([p.texto for p in prep.passos],
                         ["Tomando banho e lavando o cabelo", "Tirando maquiagem", "Colocando pijama"])
        self.assertEqual(prep.inicio, datetime(2026, 9, 27, 0, 31))
        self.assertGreaterEqual(prep.passos[1].inicio, datetime(2026, 9, 27, 1, 12))
        card = Agenda(self.db).card(datetime(2026, 9, 27, 1, 5))
        self.assertEqual(card["titulo"], "Indo dormir")
        agora = [p["texto"] for item in card["linha"] for p in item["passos"] if p["estado"] == "agora"]
        self.assertEqual(agora, ["Tomando banho e lavando o cabelo"])

    def test_nao_toma_segundo_banho_depois_do_primeiro(self):
        ag = Agenda(self.db)
        for minuto in range(12, 30):
            now = datetime(2026, 9, 27, 1, minuto)
            passo = ag.passo_atual(ag.agora(now), now)
            self.assertNotEqual(passo.texto, "Tomando banho", now)

    def test_banho_longe_da_cama_sai_da_lista(self):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM life_events")
            conn.commit()
        _evento(self.db, "banho:2026-09-27T0006", datetime(2026, 9, 27, 0, 6), "routine", "banho",
                "Tomou banho (00:06–00:20).")
        with patch("sleep_plan.SleepPlan.bed", return_value=datetime(2026, 9, 27, 2, 30)):
            prep = Agenda(self.db).etapas(DIA.date(), datetime(2026, 9, 27, 2))[-1]
        self.assertEqual([p.texto for p in prep.passos], ["Tirando maquiagem", "Colocando pijama"])


class HojeTest(BaseCaso):
    def test_banho_em_curso_no_presente_e_instagram_cortado(self):
        _evento(self.db, "livre:2026-09-26:33", datetime(2026, 9, 27, 0, 2), "tempo_livre", "Olhando o Instagram",
                "Ficou olhando o Instagram no quarto.")
        with patch.object(hoje, "_blocos", return_value={"livre:2026-09-26:33": datetime(2026, 9, 27, 0, 38)}), \
                patch.object(hoje, "_saidas", return_value=[]), patch.object(hoje, "_previstos", return_value=[]):
            view = hoje.hoje_view(self.db, datetime(2026, 9, 27, 1, 5))
        noite = {i["texto"]: i["hora"] for p in view["periodos"] if p["nome"] == "Noite" for i in p["itens"]}
        self.assertEqual(noite["Olhou o Instagram"], "00:02–00:31")
        self.assertEqual(noite["Tomando banho"], "00:31–")
        with patch.object(hoje, "_blocos", return_value={}), patch.object(hoje, "_saidas", return_value=[]), \
                patch.object(hoje, "_previstos", return_value=[]):
            depois = hoje.hoje_view(self.db, datetime(2026, 9, 27, 1, 20))
        textos = [i["texto"] for p in depois["periodos"] for i in p["itens"]]
        self.assertIn("Tomou banho", textos)

    def test_bloco_em_casa_nao_comeca_antes_de_chegar(self):
        self.assertEqual(TempoLivre(self.db)._chegou(datetime(2026, 9, 27, 0, 7)), VOLTA.end)
        self.assertEqual(TempoLivre(self.db)._chegou(datetime(2026, 9, 27, 1, 0)), datetime.min)


class LancheNoBarTest(BaseCaso):
    def test_pipoca_nao_acontece_com_ela_no_bar(self):
        slot = MealSlot("lanche", "meal:2026-09-26:lanche:2", DIA.replace(hour=20, minute=50), 10, "casa",
                        "pipoca vendo série")
        m = Meals(self.db)
        with patch.object(Meals, "day_plan", return_value=[slot]), \
                patch.object(Meals, "_floor", return_value=DIA), patch.object(Meals, "_at_home", return_value=False), \
                patch.object(Meals, "_weekly_weight"), patch.object(Meals, "_belisca", return_value=0), \
                patch.object(Meals, "_weigh_in"):
            self.assertEqual(m.materialize(DIA.replace(hour=21, minute=7)), 0)
        with self.db.get_connection() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM life_events WHERE event_key LIKE 'meal:%'").fetchone())


if __name__ == "__main__":
    unittest.main()
