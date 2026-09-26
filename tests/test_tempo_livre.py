"""Tempo livre em casa (Patrick, 26/09): nada de "tempo livre em casa" — tudo o que ela faz
acontece de verdade e vira história."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import tempo_livre
from db import DatabaseManager
from response_availability import ResponseAvailabilityPolicy
from seed_world_bible_v36 import seed_world_bible
from tempo_livre import TempoLivre

T = datetime(2026, 9, 26, 14, 20)


class TempoLivreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "t.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        p = patch.object(TempoLivre, "_quer_se_tocar", return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _eventos(self):
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT event_key, event_type, title, summary FROM life_events")]

    def test_bloco_concreto_vira_acontecimento(self):
        b = TempoLivre(self.db).agora(T)
        self.assertLessEqual(b.inicio, T)
        self.assertLess(T, b.fim)
        self.assertNotIn("tempo livre", b.texto.lower())
        self.assertTrue(b.atividade.startswith("em casa, "))
        ev = self._eventos()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["event_type"], "tempo_livre")
        self.assertTrue(ev[0]["summary"].startswith("Ficou "))

    def test_mesmo_bloco_nao_muda_nem_duplica(self):
        a = TempoLivre(self.db).agora(T)
        b = TempoLivre(self.db).agora(T + timedelta(minutes=3))
        self.assertEqual((a.chave, a.texto, a.comodo), (b.chave, b.texto, b.comodo))
        self.assertEqual(len(self._eventos()), 1)
        self.assertEqual(TempoLivre(self.db).atual(T + timedelta(minutes=3)).chave, a.chave)

    def test_blocos_emendam(self):
        a = TempoLivre(self.db).agora(T)
        b = TempoLivre(self.db).agora(a.fim + timedelta(minutes=1))
        self.assertNotEqual(a.chave, b.chave)
        self.assertGreaterEqual(b.inicio, a.fim - timedelta(minutes=5))

    def test_texto_no_padrao_e_midia_real(self):
        for n in range(60):
            b = TempoLivre(self.db).agora(T + timedelta(hours=n % 9, minutes=7 * n))
            if not b:
                continue
            self.assertRegex(b.texto, r"^[A-ZÀ-Ú][a-zà-ú]+(ndo|ada)\b", b.texto)   # gerúndio (ou "Deitada à toa")
            self.assertNotIn("{", b.texto)
            if b.tipo == "musica":
                self.assertIn(b.texto.replace("Ouvindo ", ""), tempo_livre.ARTISTAS)
            if b.tipo == "jogando":
                self.assertIn(b.texto.replace("Jogando ", ""), tempo_livre.JOGOS)

    def test_disponibilidade(self):
        mapa = ResponseAvailabilityPolicy(self.db)._map_place_activity
        self.assertEqual(mapa("marina_apartment", "em casa, olhando o TikTok (quarto)"), "HOME_RELAXING")
        self.assertEqual(mapa("marina_apartment", "em casa, vendo o desfile da Chanel pelo celular (varanda)"), "HOME_BUSY")
        self.assertEqual(mapa("marina_apartment", "em casa, lendo É Assim que Acaba (sala)"), "HOME_BUSY")
        self.assertEqual(mapa("marina_apartment", "em casa, se tocando (quarto)"), "SOLO")


class SeTocandoTest(unittest.TestCase):
    def test_vale_no_corpo(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "s.db")
        seed_world_bible(db)
        with db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        with patch.object(TempoLivre, "_quer_se_tocar", return_value=True):
            b = TempoLivre(db).agora(T)
        self.assertEqual((b.tipo, b.texto, b.comodo), ("se_tocando", "Se tocando", "quarto"))
        from emotion import EmotionEngine
        last = EmotionEngine(db).last_release(b.fim)
        self.assertIsNotNone(last, "o orgasmo fica registrado no corpo dela")
        self.assertTrue(b.inicio <= last <= b.fim)
        with db.get_connection() as conn:
            row = conn.execute("SELECT summary FROM life_events WHERE event_key=?", (f"solo:{T.date()}",)).fetchone()
        self.assertIn("se tocou no quarto", row["summary"])
        self.assertIsNone(EmotionEngine(db).maybe_release_alone(T.replace(hour=23)), "uma vez por dia")


if __name__ == "__main__":
    unittest.main()
