"""Auditoria #7 — infraestrutura do banco: isolamento, conexões e migrations."""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

import db as db_module
from db import BASE_DIR, DatabaseManager


class TestIsolationTests(unittest.TestCase):
    def test_suite_nunca_usa_o_banco_de_producao(self):
        """`python -m unittest discover` gravava no marin_memory.db real."""
        self.assertNotEqual(Path(db_module.DB_FILE).resolve(), (BASE_DIR / "marin_memory.db").resolve())
        self.assertNotEqual(Path(db_module.db_manager.db_path).resolve(),
                            (BASE_DIR / "marin_memory.db").resolve())


class ConnectionReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "reuse.db")
        self.db.enable_connection_reuse()

    def tearDown(self):
        self.db.close()  # conexão aberta trava o arquivo no Windows
        self.temp.cleanup()

    def test_mesma_thread_reaproveita_e_faz_commit(self):
        with self.db.get_connection() as a:
            a.execute("CREATE TABLE t (x INTEGER)")
            a.execute("INSERT INTO t VALUES (1)")
        with self.db.get_connection() as b:
            self.assertIs(a, b)
            self.assertFalse(b.in_transaction)
        other = sqlite3.connect(self.db.db_path)
        self.assertEqual(other.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)
        other.close()

    def test_excecao_faz_rollback(self):
        with self.db.get_connection() as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
        with self.assertRaises(RuntimeError):
            with self.db.get_connection() as conn:
                conn.execute("INSERT INTO t VALUES (1)")
                raise RuntimeError("falhou no meio")
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 0)

    def test_threads_diferentes_tem_conexoes_diferentes(self):
        seen = []

        def grab():
            with self.db.get_connection() as conn:
                seen.append(id(conn))

        workers = [threading.Thread(target=grab) for _ in range(2)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        with self.db.get_connection() as conn:
            seen.append(id(conn))
        self.assertEqual(len(set(seen)), 3)

    def test_transacao_em_lote_continua_funcionando(self):
        with self.db.get_connection() as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
        with self.assertRaises(RuntimeError):
            with self.db.transaction():
                with self.db.get_connection() as conn:
                    conn.execute("INSERT INTO t VALUES (1)")
                raise RuntimeError("lote abortado")
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 0)


class MigrationUnificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def test_schema_tem_uma_fonte_so(self):
        src = (BASE_DIR / "db.py").read_text(encoding="utf-8")
        self.assertNotIn("ALTER TABLE", src)
        self.assertNotIn("CREATE UNIQUE INDEX", src)

    def test_banco_novo_tem_coluna_da_020(self):
        db = DatabaseManager(Path(self.temp.name) / "novo.db")
        self.assertEqual(db.get_schema_version(), 25)
        with db.get_connection() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(reminders)")}
        self.assertIn("offer_message_id", cols)

    def test_banco_antigo_com_coluna_avulsa_migra_sem_erro(self):
        path = Path(self.temp.name) / "antigo.db"
        DatabaseManager(path)
        with sqlite3.connect(path) as conn:  # como a produção: coluna existe, versão 20 não
            conn.execute("DELETE FROM schema_version WHERE version>=20")
            conn.execute("DROP TABLE intimacy_state")  # 021 (Fase C.1) ainda não existia
        db = DatabaseManager(path)
        self.assertEqual(db.get_schema_version(), 25)
        with db.get_connection() as conn:
            self.assertIsNotNone(conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='intimacy_state'").fetchone())


if __name__ == "__main__":
    unittest.main()
