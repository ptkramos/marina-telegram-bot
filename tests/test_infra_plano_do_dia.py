"""Frente de infra (28/09): pilha no limite e o plano do dia calculado uma vez por rodada.

Antes, `Commute.legs_on(dia)` pedia a academia, que pedia as janelas de sono, que pediam o despertador, que pedia
`legs_on(dia)` de novo: o ciclo só parava no limite de pilha do Python (~1000 níveis), com o RecursionError engolido
por um `except Exception` — e o despertador do mesmo dia mudava conforme a ordem das perguntas.
"""
import random
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from academic_life import AcademicLife
from commute import Commute
from db import DatabaseManager, memo, rodada
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from sleep_plan import SleepPlan
from world_state import WorldStateManager

DIAS = [date(2026, 9, 21) + timedelta(days=i) for i in range(14)]


def _pilha_maxima(fn) -> int:
    estado = {"d": 0, "max": 0}

    def tracer(frame, event, arg):
        if event == "call":
            estado["d"] += 1
            estado["max"] = max(estado["max"], estado["d"])
        elif event == "return":
            estado["d"] -= 1
    sys.setprofile(tracer)
    try:
        fn()
    finally:
        sys.setprofile(None)
    return estado["max"]


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = self._banco("a.db")

    def tearDown(self):
        self.temp.cleanup()

    def _banco(self, nome):
        db = DatabaseManager(Path(self.temp.name) / nome)
        seed_world_bible(db)
        seed_academic(db)
        return db

    def _dias_de_aula(self, db):
        return [d for d in DIAS if AcademicLife(db).blocks_on(d)]


class PilhaTest(_Base):
    def test_despertador_nao_monta_o_dia_inteiro(self):
        with patch.object(Commute, "legs_on", side_effect=AssertionError("ciclo")) as legs_on:
            for day in self._dias_de_aula(self.db):
                SleepPlan(self.db).target_wake(day)
        legs_on.assert_not_called()

    def test_despertador_e_a_ida_pra_puc_menos_se_arrumar(self):
        dias = self._dias_de_aula(self.db)
        self.assertTrue(dias)
        for day in dias:
            ida = next(l for l in Commute(self.db).legs_on(day, planejado=True) if l.key.endswith(":puc:ida"))
            rng = random.Random(f"marina-sono:{day.isoformat()}:despertador")
            esperado = max(ida.start - timedelta(minutes=rng.randint(50, 80) + rng.randint(0, 10)),
                           datetime.combine(day, datetime.min.time()).replace(hour=5))
            self.assertEqual(SleepPlan(self.db).target_wake(day), esperado, day)

    def test_despertador_nao_depende_da_ordem_das_perguntas(self):
        outro = self._banco("b.db")
        ida = {d: SleepPlan(self.db).target_wake(d) for d in DIAS}
        volta = {d: SleepPlan(outro).target_wake(d) for d in reversed(DIAS)}
        self.assertEqual(ida, volta)

    def test_resolve_e_trechos_com_pilha_rasa(self):
        day = self._dias_de_aula(self.db)[0]
        base = len(__import__("inspect").stack(0))
        fundo = _pilha_maxima(lambda: (Commute(self.db).legs_on(day),
                                       SleepPlan(self.db).windows_on(day),
                                       WorldStateManager(self.db).resolve(datetime.combine(day, datetime.min.time())
                                                                          .replace(hour=12, minute=5))))
        self.assertLess(base + fundo, 300)       # antes: ~990 (limite do Python: 1000)


class RodadaTest(_Base):
    def _contador(self):
        calls = []

        def calcula():
            calls.append(1)
            return {"lista": [1, 2]}
        return calls, calcula

    def test_fora_da_rodada_sempre_calcula(self):
        calls, calcula = self._contador()
        memo(self.db, ("x",), calcula)
        memo(self.db, ("x",), calcula)
        self.assertEqual(len(calls), 2)

    def test_na_rodada_calcula_uma_vez_e_devolve_copia(self):
        calls, calcula = self._contador()
        with rodada(self.db):
            a = memo(self.db, ("x",), calcula)
            a["lista"].append(3)                     # quem recebe pode mexer
            b = memo(self.db, ("x",), calcula)
        self.assertEqual(len(calls), 1)
        self.assertEqual(b, {"lista": [1, 2]})

    def test_gravacao_invalida(self):
        calls, calcula = self._contador()
        with rodada(self.db):
            memo(self.db, ("x",), calcula)
            with self.db.get_connection() as conn:
                conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('t', '1', 'x')")
                conn.commit()
            memo(self.db, ("x",), calcula)
            with self.db.get_connection() as conn:     # leitura não invalida
                conn.execute("SELECT 1").fetchone()
            memo(self.db, ("x",), calcula)
        self.assertEqual(len(calls), 2)

    def test_gravacao_de_outro_gerente_no_mesmo_arquivo_invalida(self):
        calls, calcula = self._contador()
        outro = DatabaseManager(self.db.db_path)
        with rodada(self.db):
            memo(self.db, ("x",), calcula)
            with outro.get_connection() as conn:
                conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('t2', '1', 'x')")
                conn.commit()
            memo(self.db, ("x",), calcula)
        self.assertEqual(len(calls), 2)

    def test_transacao_aberta_sempre_calcula(self):
        calls, calcula = self._contador()
        with rodada(self.db):
            with self.db.transaction():
                memo(self.db, ("x",), calcula)
                memo(self.db, ("x",), calcula)
        self.assertEqual(len(calls), 2)

    def test_rodada_reentrante_e_descartada_no_fim(self):
        calls, calcula = self._contador()
        with rodada(self.db):
            memo(self.db, ("x",), calcula)
            with rodada(self.db):
                memo(self.db, ("x",), calcula)
            memo(self.db, ("x",), calcula)
        with rodada(self.db):
            memo(self.db, ("x",), calcula)
        self.assertEqual(len(calls), 2)

    def test_banco_que_nao_e_o_gerente_sempre_calcula(self):
        calls, calcula = self._contador()
        falso = object()
        with rodada(falso):
            memo(falso, ("x",), calcula)
            memo(falso, ("x",), calcula)
        self.assertEqual(len(calls), 2)

    def test_resolve_na_rodada_igual_ao_sem_rodada(self):
        outro = self._banco("b.db")
        day = self._dias_de_aula(self.db)[0]
        with patch("db.DatabaseManager.memo", lambda self, chave, calcula: calcula()):
            sem = [WorldStateManager(outro).resolve(datetime.combine(day, datetime.min.time()) + timedelta(hours=h))
                   ["activity"] for h in (6, 9, 12, 15, 18, 21)]
        com = [WorldStateManager(self.db).resolve(datetime.combine(day, datetime.min.time()) + timedelta(hours=h))
               ["activity"] for h in (6, 9, 12, 15, 18, 21)]
        self.assertEqual(sem, com)


if __name__ == "__main__":
    unittest.main()
