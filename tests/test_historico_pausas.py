"""Bugs 14 e 16 (28/09): fala velha dela no histórico voltando como se fosse de agora.

Às 17:24, passeando com o Milo, ela disse "tô organizando umas referências de look" (a fala das 13:41); às 18:58,
treinando na Bodytech, "sofá com o Milo, escolhendo umas referências". O histórico ia sem hora, e o bloco
"desde a sua última mensagem" sumia assim que ela respondia de novo (18:57).
"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import since_last
from context_builder import marcar_pausas, tirar_lote_do_historico
from db import DatabaseManager


def _m(role, content, hh, mm, dia=28):
    return {"role": role, "content": content, "timestamp": datetime(2026, 9, dia, hh, mm).isoformat()}


TARDE = [
    _m("user", "Tá por onde?", 13, 40),
    _m("assistant", "Tô em casa, olhando o Pinterest", 13, 41),
    _m("user", "Demaaais", 13, 48),
    _m("assistant", "Sumido, hein?", 16, 2),
    _m("user", "Oii bebezinha", 17, 24),
    _m("assistant", "Tô organizando umas referências de look", 17, 24),
    _m("user", "Moreco", 18, 56),
    _m("assistant", "Oi, meu amor", 18, 56),
    _m("user", "Tá onde agr?", 18, 58),
]


class MarcarPausasTest(unittest.TestCase):
    def test_primeira_mensagem_dele_depois_da_pausa_leva_a_hora(self):
        out = marcar_pausas(TARDE)
        self.assertEqual(out[6]["content"], "[18:56 — depois de 1h32 sem conversa] Moreco")
        self.assertEqual(out[8]["content"], "Tá onde agr?")
        self.assertEqual(out[0]["content"], "Tá por onde?")

    def test_pausa_antes_da_iniciativa_dela_marca_a_dele_seguinte(self):
        out = marcar_pausas(TARDE)
        self.assertEqual(out[3]["content"], "Sumido, hein?")          # a dela nunca leva marca
        self.assertEqual(out[4]["content"], "[17:24 — depois de 3h36 sem conversa] Oii bebezinha")

    def test_outro_dia_leva_a_data(self):
        out = marcar_pausas([_m("assistant", "boa noite", 23, 50, dia=27), _m("user", "Bom dia!", 5, 52)])
        self.assertEqual(out[1]["content"], "[28/09, 05:52 — depois de 6h02 sem conversa] Bom dia!")

    def test_sem_hora_fica_como_estava(self):
        hist = [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "oii"}]
        self.assertEqual(marcar_pausas(hist), hist)

    def test_so_role_e_content_vao_pro_modelo(self):
        self.assertEqual(set(marcar_pausas(TARDE)[0]), {"role", "content"})


class LoteDuplicadoTest(unittest.TestCase):
    """O lote dele é gravado ao chegar: estava no fim do histórico e ia de novo como última mensagem."""

    def test_tira_a_copia_e_leva_a_marca(self):
        msgs = [{"role": "system", "content": "S"}] + marcar_pausas(TARDE[:7])
        marca = tirar_lote_do_historico(msgs, "Moreco")
        self.assertEqual(marca, "[18:56 — depois de 1h32 sem conversa] ")
        self.assertEqual(msgs[-1]["role"], "assistant")

    def test_lote_de_varias_bolhas(self):
        msgs = [{"role": "system", "content": "S"}, {"role": "assistant", "content": "oi"},
                {"role": "user", "content": "amor"}, {"role": "user", "content": "tá onde?"}]
        self.assertEqual(tirar_lote_do_historico(msgs, "amor\ntá onde?"), "")
        self.assertEqual(len(msgs), 2)

    def test_mensagem_antiga_sem_resposta_fica(self):
        msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "kkkk"},
                {"role": "user", "content": "tá onde?"}]
        tirar_lote_do_historico(msgs, "tá onde?")
        self.assertEqual(msgs[-1]["content"], "kkkk")


class RetomadaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "c.db")
        with self.db.get_connection() as conn:
            for m in TARDE:
                conn.execute("INSERT INTO conversas (timestamp, role, content) VALUES (?,?,?)",
                             (m["timestamp"], m["role"], m["content"]))
            conn.commit()
        for p in (patch.object(since_last, "_legs", return_value=[]),
                  patch.object(since_last, "_now_activity", return_value="treinando na academia")):
            p.start()
            self.addCleanup(p.stop)

    def test_bloco_continua_ancorado_antes_da_pausa(self):
        lines = "\n".join(since_last.prompt_lines(self.db, datetime(2026, 9, 28, 18, 58, 10)))
        self.assertIn("ANTES DA PAUSA NA CONVERSA (às 17:24)", lines)
        self.assertIn("AGORA você está: treinando na academia", lines)

    def test_conversa_longa_depois_da_pausa_nao_repete_o_bloco(self):
        with self.db.get_connection() as conn:
            for mm in range(0, 60, 10):
                conn.execute("INSERT INTO conversas (timestamp, role, content) VALUES (?,?,?)",
                             (datetime(2026, 9, 28, 19, mm).isoformat(), "assistant", "kkk"))
            conn.commit()
        self.assertEqual(since_last.prompt_lines(self.db, datetime(2026, 9, 28, 19, 58)), [])


if __name__ == "__main__":
    unittest.main()
