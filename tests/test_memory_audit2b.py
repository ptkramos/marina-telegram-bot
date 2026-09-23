"""Auditoria #2b — memória revisitada antes da Fase D (rotina viva).

Casos reais do banco de 22/09: "Patrick avisar quando chegar em casa" aberto
4 vezes e agendado para check-in proativo dois dias depois; "consulta com o
dentista amanhã" ativo para sempre; fato sobre a Marina e fatos tirados das
falas dela gravados como fatos do Patrick.
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from db import DatabaseManager
from memory_consolidator import CONSOLIDATOR_SYSTEM_PROMPT, MemoryConsolidator
from memory_hygiene import MemoryHygieneService
from planner import parse_iso_or_relative_datetime


class _DB(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "m2b.db")

    def tearDown(self):
        self.temp.cleanup()

    def _age_loop(self, loop_id, hours):
        past = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("UPDATE open_loops SET created_at=?, last_touched_at=? WHERE id=?", (past, past, loop_id))
            conn.commit()


class ShortLivedLoopsTest(_DB):
    def test_trip_promise_never_becomes_a_checkin(self):
        lid = self.db.adicionar_open_loop("promise", "Patrick avisar quando chegar em casa")
        self.assertIsNone(self.db.get_open_loop(lid)["next_check_after"])
        later = datetime.now() + timedelta(days=2)
        self.assertEqual(self.db.get_open_loops_para_checkin(now=later), [])

    def test_repeated_promise_is_touched_not_duplicated(self):
        first = self.db.adicionar_open_loop("promise", "Patrick avisar quando chegar em casa")
        again = self.db.adicionar_open_loop("promise", "Patrick avisar quando ele chegar em casa")
        self.assertEqual(first, again)
        other = self.db.adicionar_open_loop("promise", "Contar ao Patrick o que comeu no jantar")
        self.assertNotEqual(first, other)

    def test_stale_short_loop_leaves_the_prompt_and_is_abandoned(self):
        lid = self.db.adicionar_open_loop("waiting", "Aguardar Patrick avisar quando subir no ônibus")
        self.assertIn(lid, [l["id"] for l in self.db.get_open_loops_ativos(limit=5)])
        self._age_loop(lid, 13)
        self.assertNotIn(lid, [l["id"] for l in self.db.get_open_loops_ativos(limit=5)])
        self.assertEqual(self.db.vencer_open_loops_curtos(), 1)
        loop = self.db.get_open_loop(lid)
        self.assertEqual(loop["status"], "abandoned")
        self.assertIsNotNone(loop["resolved_at"])

    def test_projects_keep_the_24h_checkin(self):
        lid = self.db.adicionar_open_loop("project", "Escrever artigo sobre IA")
        self.assertIsNotNone(self.db.get_open_loop(lid)["next_check_after"])
        self._age_loop(lid, 30)
        self.assertIn(lid, [l["id"] for l in self.db.get_open_loops_ativos(limit=5)])

    def test_abandoned_loops_are_archived_after_30_days(self):
        lid = self.db.adicionar_open_loop("task", "Algo que perdeu o sentido")
        self.db.abandonar_open_loop(lid)
        past = (datetime.now() - timedelta(days=31)).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("UPDATE open_loops SET resolved_at=? WHERE id=?", (past, lid))
            conn.commit()
        self.assertEqual(self.db.arquivar_open_loops_antigos(dias=30), 1)

    def test_descriptive_hint_has_no_date_without_default(self):
        self.assertIsNone(parse_iso_or_relative_datetime("quando chegar em casa"))
        self.assertIsNotNone(parse_iso_or_relative_datetime("quando chegar em casa", default_offset_hours=48))


class ContextualFactsTest(_DB):
    def test_contextual_fact_expires_after_three_days(self):
        fid = self.db.adicionar_fato_patrick(
            "Patrick tem consulta com o dentista em 23/09/2026 às 10h30.", category="saude",
            memory_tier="contextual", volatility="volatile")
        stable = self.db.adicionar_fato_patrick("Patrick usa aparelho ortodôntico.", category="saude")
        now = datetime.now()
        self.assertEqual(self.db.expirar_fatos_contextuais(dias=3, now=now), 0)
        self.assertEqual(self.db.expirar_fatos_contextuais(dias=3, now=now + timedelta(days=4)), 1)
        with self.db.get_connection() as conn:
            active = dict(conn.execute("SELECT id, active FROM fatos_patrick").fetchall())
        self.assertEqual((active[fid], active[stable]), (0, 1))

    def test_hygiene_cycle_runs_the_expirations(self):
        result = MemoryHygieneService(self.db).run_hygiene_cycle(force=True)
        self.assertIn("expired_contextual_facts", result)
        self.assertIn("expired_short_loops", result)


class ConsolidatorPromptTest(_DB):
    def test_evidence_rules_are_in_the_prompt(self):
        p = CONSOLIDATOR_SYSTEM_PROMPT
        self.assertIn("Só o que o PATRICK diz é evidência", p)
        self.assertIn("Nunca grave fato sobre a Marina", p)
        self.assertIn("Uma ocorrência não é hábito", p)
        self.assertIn("DATA ABSOLUTA", p)
        self.assertIn("ZERO momentos", p)

    def test_today_goes_with_the_dialogue(self):
        llm = MagicMock()
        llm.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"facts_to_create": []}'))])
        MemoryConsolidator(db=self.db, llm_client=llm).consolidate_dialogue(
            [{"role": "user", "content": "amanhã tenho dentista às 10:30"}], existing_facts=[])
        user = llm.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn(f"HOJE: ", user)
        self.assertIn(datetime.now().strftime("%d/%m/%Y"), user)


if __name__ == "__main__":
    unittest.main()
