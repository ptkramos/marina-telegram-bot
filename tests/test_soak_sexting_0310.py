"""Soak, dia 5 (sábado 03/10): o sexting da tarde.

- 15:40 (conversas 1198) no meio da cena, por áudio: "Preciso dar uma pausa por aqui. Prefiro não continuar com
  mensagens desse tipo" — recusa do Gemini que o filtro não pegou (sem `llm.junk_reply` no log). Às 15:41 ela
  sustentou pela menstruação (dia 4): o bloco do modo íntimo dizia "Libido: Baixa para sexo… sem cobrança".
- O Patrick: "o sexting hoje não cria ação no Bastidores do Agora, nem Hoje". Das 15:04 às 15:44 o mundo tinha ela
  "ouvindo a playlist no closet" (15:10) e "olhando o Pinterest (closet)" (15:32); às 15:41 ela usou isso na fala
  ("Tava até aqui no closet catando umas ideias de looks no Pinterest").
"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import bot
from cycle import PHASES
from db import DatabaseManager
from hoje import hoje_view
from intimacy import IntimacyEngine, IntimacyTurn, observe_marina_line, system_block
from seed_world_bible_v36 import seed_world_bible
from tempo_livre import TempoLivre


def t(h, m):
    return datetime(2026, 10, 3, h, m)


class RecusaDoGeminiTest(unittest.TestCase):
    def test_a_fala_das_15_40_e_recusa(self):
        fala = "Preciso dar uma pausa por aqui. Prefiro não continuar com mensagens desse tipo"
        self.assertTrue(bot._is_policy_refusal(fala))
        self.assertEqual(bot._needs_retry_for_junk(fala), (True, "policy_refusal"))

    def test_variacoes(self):
        for fala in ("Não me sinto confortável em continuar com isso", "Prefiro não prosseguir com esse conteúdo",
                     "Vou parar com conversas desse teor por aqui"):
            self.assertTrue(bot._is_policy_refusal(fala), fala)

    def test_fala_de_namorada_passa(self):
        for fala in ("aff, que raiva desse tipo de coisa vindo de mãe",
                     "Preciso dar uma pausa pra comer, amor, já volto",
                     "Isso não, amor kkkk, me deixa respirar",
                     "Amor, falei sério ali, vamos dar uma segurada nesse papo por agora",
                     "Prefiro não continuar esse assunto da minha mãe hoje"):
            self.assertFalse(bot._is_policy_refusal(fala), fala)


class MenstruadaNoClimaTest(unittest.TestCase):
    def _ciclo(self, fase, dia):
        return {"phase_key": fase, "day": dia, "libido": PHASES[fase]["libido"]}

    def test_menstruada_no_modo_nao_le_libido_baixa(self):
        bloco = system_block(IntimacyTurn("active", 0.62), self._ciclo("menstrual", 4))
        self.assertNotIn("Baixa para sexo", bloco)
        self.assertNotIn("sem cobrança", bloco)
        self.assertIn("menstruada (dia 4 do ciclo)", bloco)
        self.assertIn("não motivo pra largar a cena", bloco)

    def test_outras_fases_seguem_iguais(self):
        bloco = system_block(IntimacyTurn("active", 0.62), self._ciclo("folicular", 8))
        self.assertIn(f"Libido pela fase do ciclo hoje: {PHASES['folicular']['libido']}", bloco)


class SextingNoMundoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "t.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) "
                         "VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        for alvo, kw in (("tempo_livre.TempoLivre._quer_se_masturbar", {"return_value": None}),
                         ("unhas.Unhas.quer_em_casa", {"return_value": False}),
                         ("cabelo.Cabelo.quer_umectar", {"return_value": False}),
                         ("tempo_livre.TempoLivre._ate", {"side_effect": lambda ini, fim: fim}),
                         ("intimacy.IntimacyEngine._libido", {"return_value": 1.0})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        self.tl = TempoLivre(self.db)
        self.antes = self.tl.agora(t(15, 0))          # o que ela fazia em casa antes do clima
        self._mundo(t(15, 0), self.antes.atividade)

    def _mundo(self, at, atividade):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_state (state_date, observed_at, activity, source_json) VALUES (?,?,?,?)",
                         (at.date().isoformat(), at.isoformat(), atividade,
                          json.dumps({"reason": "free_time"})))
            conn.commit()

    def _clima(self, at, texto="tô louco de tesão, quero te comer"):
        return IntimacyEngine(self.db).observe(texto, {}, now=at)

    def test_o_clima_vira_o_bloco_em_casa(self):
        self.assertEqual(self._clima(t(15, 4)).state, "active")
        agora = self.tl.agora(t(15, 6))
        self.assertEqual(agora.tipo, "sexting")
        self.assertEqual(agora.texto, "Transando com o Patrick por mensagem")
        self.assertEqual(agora.atividade, "em casa, transando com o Patrick por mensagem (quarto)")
        # o que ela fazia acaba quando o clima começa
        antes = next(b for b in self.tl.do_dia(t(15, 6)) if b.chave == self.antes.chave)
        self.assertEqual(antes.fim, t(15, 4))

    def test_nao_sorteia_pinterest_no_meio(self):
        for h, m in ((15, 4), (15, 12), (15, 20), (15, 28), (15, 36)):
            self._clima(t(h, m))
            self.assertEqual(self.tl.agora(t(h, m + 2)).tipo, "sexting", (h, m))
        sextings = [b for b in self.tl.do_dia(t(15, 40)) if b.tipo == "sexting"]
        self.assertEqual(len(sextings), 1)
        self.assertEqual((sextings[0].inicio, sextings[0].fim), (t(15, 4), t(15, 41)))

    def _cena(self, ate):
        for m in range(4, ate + 1, 3):                    # uma fala dele a cada 3 min, como às 15:04–15:40
            self._clima(t(15, m))

    def test_hoje_durante_e_depois_do_gozo(self):
        self._cena(31)
        itens = [i for p in hoje_view(self.db, t(15, 32))["periodos"] for i in p["itens"]]
        linha = next(i for i in itens if i["ic"] == "message-heart")
        self.assertEqual((linha["texto"], linha["sub"], linha["hora"]),
                         ("Transando com o Patrick", "No quarto por mensagem", "15:04–"))

        self.assertTrue(observe_marina_line(self.db, "tô gozando, amor", t(15, 44)))
        itens = [i for p in hoje_view(self.db, t(16, 10))["periodos"] for i in p["itens"]]
        linha = next(i for i in itens if i["ic"] == "message-heart")
        self.assertEqual((linha["texto"], linha["sub"], linha["hora"]),
                         ("Transou com o Patrick", "No quarto por mensagem, gozou", "15:04–15:44"))
        with self.db.get_connection() as conn:
            ev = conn.execute("SELECT summary, share_worthy FROM life_events WHERE event_key LIKE 'livre:%:s1'").fetchone()
        self.assertEqual(ev["summary"], "Transou com o Patrick por mensagem no quarto e gozou.")
        self.assertEqual(ev["share_worthy"], 0.0)

    def test_depois_volta_pro_tempo_livre(self):
        self._cena(28)
        self._clima(t(15, 30), "depois amor, tô cansado")       # ele cortou
        depois = self.tl.agora(t(15, 50))
        self.assertNotEqual(depois.tipo, "sexting")
        self.assertGreaterEqual(depois.inicio, t(15, 30))

    def test_fora_de_casa_nao_vira_bloco(self):
        self._mundo(t(15, 2), "no Shopping da Gávea com a Bia")
        self._clima(t(15, 4))
        self.assertFalse(any(b.tipo == "sexting" for b in self.tl.do_dia(t(15, 6))))

    def test_card_do_agora_sem_barra(self):
        from agenda import Agenda
        self._cena(40)
        self._mundo(t(15, 5), "em casa, transando com o Patrick por mensagem (quarto)")
        card = Agenda(self.db).card_casa(t(15, 40), "na mão")
        self.assertEqual((card["titulo"], card["linha2"]), ("Em casa", "Transando com o Patrick por mensagem"))
        self.assertIn(["door", "Cômodo", "Quarto"], card["grade"])
        self.assertEqual((card["barra"]["pct"], card["barra"]["desde"]), (None, "15:04"))


if __name__ == "__main__":
    unittest.main()
