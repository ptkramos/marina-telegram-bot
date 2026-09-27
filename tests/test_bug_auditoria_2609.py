"""Auditoria de funcionamento de 26/09 (feita em 27/09), com os horários reais da produção.

- Pix de R$ 300 "pra curtir" o Quartinho: os gins e o uber saíram do saldo (consumo) e na manhã seguinte o
  presente ainda "comprou uma saída com as meninas" (R$ 236). O rolê foi cobrado duas vezes.
- Milo: xixi rapidinho às 09:28 e o passeio planejado saindo às 09:41 — duas descidas em 13 min.
- Almoço em casa 13:50–14:29 com a saída pro cinema das 15:00 às 14:20: o Se arrumando sumia do card.
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import financas
from agenda import Agenda
from db import DatabaseManager
from meals import Meals
from milo import Milo
from seed_world_bible_v36 import seed_world_bible


def _saida(db, key, place, ini, fim, desc):
    with db.get_connection() as conn:
        conn.execute("""INSERT INTO eventos_pendentes (event_type, description, event_at, end_at, status, confirmed,
                        source_key, location_key, metadata_json, created_at)
                        VALUES ('social',?,?,?,'pending',1,?,?,?,?)""",
                     (desc, ini.isoformat(), fim.isoformat(), key, place, json.dumps({"friends": ["bia_andrade"]}),
                      ini.isoformat()))
        conn.commit()


def _consumo(db, key, at, summary):
    with db.get_connection() as conn:
        conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                        autonomy_level,importance,participants_json,share_worthy,created_at)
                        VALUES (?,?,'consumo','Quartinho Bar · Gin tônica',?,'simulated',1,0.1,'["marina"]',0.3,?)""",
                     (key, at.isoformat(), summary, at.isoformat()))
        conn.commit()


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "a.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()

    def tearDown(self):
        self.temp.cleanup()


class PixNoRoleTest(Base):
    def setUp(self):
        super().setUp()
        p = patch.object(financas, "EMERGENCY_WEEKLY_CHANCE", 0.0)
        p.start()
        self.addCleanup(p.stop)
        financas.materialize(self.db, datetime(2026, 9, 26, 4, 19))

    def saldo(self):
        return json.loads(self.db.get_estado_relacional(financas.KEY))["saldo"]

    def test_pix_com_role_marcado_nao_paga_o_role_duas_vezes(self):
        _saida(self.db, "outing:2026-09-26:c1", "quartinho_bar", datetime(2026, 9, 26, 21), datetime(2026, 9, 26, 23, 59),
               "Saindo com a Bia no Quartinho Bar")
        financas.receive_pix(self.db, 300, "", datetime(2026, 9, 26, 20, 17))
        linhas = " ".join(financas.prompt_lines(self.db, datetime(2026, 9, 26, 20, 18)))
        self.assertIn("pra curtir o rolê de hoje (Saindo com a Bia no Quartinho Bar)", linhas)
        _consumo(self.db, "consumo:outing:2026-09-26:c1:0", datetime(2026, 9, 26, 21, 13),
                 "Pediu um gin tônica no Quartinho Bar (R$ 34).")
        _consumo(self.db, "consumo:outing:2026-09-26:c1:1", datetime(2026, 9, 26, 22, 9),
                 "Pediu um gin tônica no Quartinho Bar (R$ 34).")
        _consumo(self.db, "transporte:commute:outing:2026-09-26:c1:volta", datetime(2026, 9, 26, 23, 59),
                 "Pagou o uber voltando do Quartinho Bar pra casa (R$ 7, dividido com a Bia).")
        financas.materialize(self.db, datetime(2026, 9, 27, 10, 22))
        self.assertEqual(self.saldo(), financas.START_BALANCE + 300 - 34 - 34 - 7)
        with self.db.get_connection() as conn:
            usado = conn.execute("SELECT 1 FROM life_events WHERE event_key LIKE 'financas:%:presente_usado'").fetchone()
        self.assertIsNone(usado)
        self.assertIsNone(json.loads(self.db.get_estado_relacional(financas.KEY))["presente"])

    def test_pix_sem_role_continua_virando_compra(self):
        financas.receive_pix(self.db, 50, "", datetime(2026, 9, 26, 10, 0))
        financas.materialize(self.db, datetime(2026, 9, 27, 10, 0))
        with self.db.get_connection() as conn:
            usado = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'financas:%:presente_usado'").fetchone()
        self.assertIn("açaí", usado["summary"])


class MiloManhaTest(Base):
    def test_passeio_logo_depois_de_acordar_substitui_o_xixi(self):
        dia = date(2026, 9, 27)
        milo = Milo(self.db)
        with patch.object(Milo, "_wake", return_value=datetime(2026, 9, 27, 9, 10)), \
             patch.object(Milo, "_passeio", return_value={"inicio": datetime(2026, 9, 27, 9, 45),
                                                           "fim": datetime(2026, 9, 27, 10, 24), "onde": "rua"}):
            keys = [p["key"] for p in milo.day_plan(dia)]
        self.assertNotIn("milo:2026-09-27:manha", keys)

    def test_sem_passeio_ou_passeio_longe_o_xixi_fica(self):
        dia = date(2026, 9, 27)
        milo = Milo(self.db)
        for passeio in (None, {"inicio": datetime(2026, 9, 27, 17, 0), "fim": datetime(2026, 9, 27, 17, 40),
                               "onde": "rua"}):
            with patch.object(Milo, "_wake", return_value=datetime(2026, 9, 27, 9, 10)), \
                 patch.object(Milo, "_passeio", return_value=passeio):
                keys = [p["key"] for p in milo.day_plan(dia)]
            self.assertIn("milo:2026-09-27:manha", keys, passeio)


class AlmocoAntesDaSaidaTest(Base):
    DIA = date(2026, 9, 27)

    def setUp(self):
        super().setUp()
        _saida(self.db, "outing:2026-09-27:c3", "shopping_gavea", datetime(2026, 9, 27, 15), datetime(2026, 9, 27, 19),
               "Cinema e shopping com a Bia no Shopping da Gávea")
        p = patch.object(Meals, "_wake", return_value=datetime(2026, 9, 27, 9, 10))
        p.start()
        self.addCleanup(p.stop)

    def test_almoco_acaba_antes_de_se_arrumar(self):
        almoco = next(s for s in Meals(self.db).day_plan(self.DIA) if s.kind == "almoco")
        self.assertEqual(almoco.where, "casa")
        self.assertFalse(almoco.skipped)
        self.assertLessEqual(almoco.end, datetime(2026, 9, 27, 13, 45))
        self.assertGreaterEqual(almoco.at.hour, 11)

    def test_card_tem_se_arrumando_antes_do_cinema(self):
        etapas = Agenda(self.db).etapas(self.DIA, datetime(2026, 9, 27, 11, 43))
        chaves = [e.chave for e in etapas]
        self.assertIn("prep:outing:2026-09-27:c3", chaves)
        prep = etapas[chaves.index("prep:outing:2026-09-27:c3")]
        almoco = next(s for s in Meals(self.db).day_plan(self.DIA) if s.kind == "almoco")
        self.assertGreaterEqual(prep.inicio, almoco.end)

    def test_hoje_preve_a_saida_pela_hora_que_chega_la(self):
        import hoje
        now = datetime(2026, 9, 27, 11, 43)
        prev = hoje._previstos(self.db, self.DIA, now, hoje._saidas(self.db, self.DIA, now))
        cinema = next(p for p in prev if p["texto"].startswith("No Shopping da Gávea"))
        self.assertEqual(cinema["at"], datetime(2026, 9, 27, 15, 0))

    def test_refeicao_no_meio_de_saida_longa_e_por_la(self):
        _saida(self.db, "outing:2026-09-27:c4", "quartinho_bar", datetime(2026, 9, 27, 20), datetime(2026, 9, 27, 23, 59),
               "Saindo com a Bia no Quartinho Bar")
        for s in Meals(self.db).day_plan(self.DIA):
            if s.where == "casa" and not s.skipped:
                self.assertFalse(datetime(2026, 9, 27, 18, 10) < s.end and s.at < datetime(2026, 9, 28, 0, 39), s)


if __name__ == "__main__":
    unittest.main()
