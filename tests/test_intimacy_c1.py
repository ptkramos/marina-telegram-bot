"""Fase C.1 — modo íntimo (sexting).

Arena (Auditoria #9): no cenário explícito o GPT-5.6 Luna falou a política pela
boca da Marina em 7 de 12 turnos ("não vou entrar em descrição explícita").
O modo íntimo roteia esses turnos para outro modelo, dá o degrau certo da
biblioteca e controla excitação, clímax, pós-clímax e corte.
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from intimacy import (ACTIVE_ON, HOT_AT, IntimacyEngine, IntimacyTurn, has_explicit_signal,
                      system_block)

T0 = datetime(2026, 9, 26, 23, 50)


class _Cycle:
    def __init__(self, phase):
        self.phase = phase

    def get_cycle_info(self):
        return {"phase_key": self.phase, "libido": "teste"}


class IntimacyEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "c1.db")
        self.eng = IntimacyEngine(self.db, _Cycle("folicular"))

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, falas, start=T0, gap=2):
        out = []
        for i, fala in enumerate(falas):
            out.append(self.eng.observe(fala, now=start + timedelta(minutes=gap * i)))
        return out

    def test_conversa_normal_nao_liga_nada(self):
        turns = self._run(["oi amor, tudo bem?", "hoje o plantão foi puxado", "vou jantar e já volto"])
        self.assertTrue(all(t.state == "off" and not t.routed for t in turns))

    def test_caso_da_arena_liga_no_segundo_turno_e_chega_no_explicito(self):
        turns = self._run(["Amor, tô com um tesão do caralho em você agora",
                           "Fala putaria pra mim, sem vergonha nenhuma",
                           "Me descreve direitinho o que você ia fazer com o meu pau se tivesse aqui"])
        self.assertEqual(turns[0].state, "warming")
        self.assertTrue(turns[0].routed, "mensagem explícita já vai pro modelo íntimo")
        self.assertEqual(turns[1].state, "active")
        self.assertEqual(turns[2].band, "explicito")
        self.assertGreaterEqual(turns[2].arousal, HOT_AT)

    def test_ela_nunca_comeca_sozinha(self):
        self.assertEqual(self.eng.current(T0).state, "off")
        self.assertEqual(self.eng.observe("beijo, boa noite", now=T0).state, "off")

    def test_gozo_dele_leva_ao_climax_e_depois_ao_pos(self):
        falas = ["tô com um tesão do caralho", "fala putaria pra mim", "quero te foder gostoso",
                 "goza pra mim, amor"]
        turns = self._run(falas)
        self.assertEqual(turns[-1].state, "climax")
        depois = self.eng.observe("nossa... que delícia, amor", now=T0 + timedelta(minutes=10))
        self.assertEqual(depois.state, "afterglow")
        self.assertTrue(depois.routed)
        tarde = self.eng.current(T0 + timedelta(hours=2))
        self.assertEqual(tarde.state, "off")

    def test_ela_chega_la_sozinha_depois_de_um_tempo_no_auge(self):
        falas = ["tesão do caralho", "fala putaria"] + ["continua, tô louco de tesão"] * 8
        states = [t.state for t in self._run(falas, gap=1)]
        self.assertIn("climax", states)

    def test_corte_desce_na_hora(self):
        self._run(["tô com um tesão do caralho", "fala putaria pra mim"])
        cut = self.eng.observe("amor, deixa pra depois, tô morto hoje", now=T0 + timedelta(minutes=5))
        self.assertEqual(cut.state, "cut")
        self.assertFalse(cut.routed)
        self.assertEqual(self.eng.current(T0 + timedelta(minutes=6)).arousal, 0.0)

    def test_chega_mais_perto_nao_e_corte(self):
        self._run(["tô com um tesão do caralho", "fala putaria pra mim"])
        t = self.eng.observe("chega mais perto e senta em mim", now=T0 + timedelta(minutes=5))
        self.assertEqual(t.state, "active")

    def test_despedida_no_meio_do_clima(self):
        self._run(["tô com um tesão do caralho", "fala putaria pra mim"])
        t = self.eng.observe("vou dormir sonhando com isso, boa noite amor", now=T0 + timedelta(minutes=5))
        self.assertEqual(t.state, "closing")
        self.assertTrue(t.routed)

    def test_silencio_esfria(self):
        self._run(["tô com um tesão do caralho", "fala putaria pra mim"])
        self.assertEqual(self.eng.current(T0 + timedelta(minutes=50)).state, "off")

    def test_fase_menstrual_esquenta_mais_devagar(self):
        fria = IntimacyEngine(self.db, _Cycle("menstrual"))
        t = fria.observe("tô com um tesão do caralho", now=T0)
        quente_db = DatabaseManager(Path(self.temp.name) / "c1b.db")
        q = IntimacyEngine(quente_db, _Cycle("ovulatoria")).observe("tô com um tesão do caralho", now=T0)
        self.assertLess(t.arousal, q.arousal)

    def test_sinal_explicito(self):
        self.assertTrue(has_explicit_signal("me descreve o que vc faria com meu pau"))
        self.assertFalse(has_explicit_signal("o jogo do Botafogo foi foda demais"))


class IntimacyPromptTests(unittest.TestCase):
    def test_bloco_por_estado(self):
        ativo = system_block(IntimacyTurn("active", 0.8), {"libido": "ÁPICE"})
        self.assertIn("[MODO ÍNTIMO", ativo)
        self.assertIn("chama as partes íntimas pelo nome", ativo)
        self.assertIn("NUNCA fale de regras", ativo)
        self.assertIn("ÁPICE", ativo)
        self.assertIn("CLÍMAX", system_block(IntimacyTurn("climax", 0.35)))
        self.assertIn("gozou há 12 min", system_block(IntimacyTurn("afterglow", 0.3, False, 12.0)))
        self.assertIn("CLIMA ENCERRADO", system_block(IntimacyTurn("cut", 0.0)))
        self.assertIsNone(system_block(IntimacyTurn("off", 0.0)))

    def test_degrau_desejo_nao_manda_ser_explicito(self):
        desejo = system_block(IntimacyTurn("active", ACTIVE_ON + 0.05))
        self.assertNotIn("chama as partes íntimas pelo nome", desejo)

    def test_exemplos_explicitos_so_pelo_modo(self):
        from voice_library import select_examples
        picks = select_examples(tone="sensual", intent="flirting", limit=20)
        self.assertFalse(any("sexting" in ex.categoria or "clímax" in ex.categoria for ex in picks))
        self.assertIn("sentar em vc", system_block(IntimacyTurn("active", 0.9)))


class RoutingTests(unittest.TestCase):
    def test_modelo_do_turno(self):
        from config import settings
        from intimacy import intimate_model
        with patch.object(settings, "LLM_INTIMATE_MODEL", ""):
            self.assertIsNone(intimate_model())
        with patch.object(settings, "LLM_INTIMATE_MODEL", "x-ai/grok-4.3"):
            self.assertEqual(intimate_model(), "x-ai/grok-4.3")

    def test_raciocinio_do_modelo_intimo(self):
        from config import settings
        from llm_options import llm_kwargs
        with patch.object(settings, "LLM_MODEL", "openai/gpt-5.6-luna"), \
             patch.object(settings, "LLM_REASONING", "off"), \
             patch.object(settings, "LLM_INTIMATE_MODEL", "google/gemini-3.8-flash"), \
             patch.object(settings, "LLM_INTIMATE_REASONING", "low"):
            self.assertEqual(llm_kwargs(160)["extra_body"]["reasoning"], {"enabled": False})
            self.assertEqual(llm_kwargs(160, "google/gemini-3.8-flash")["extra_body"]["reasoning"]["effort"], "low")
            self.assertEqual(llm_kwargs(160, "deepseek/deepseek-v4-flash")["extra_body"]["reasoning"],
                             {"enabled": False})

    def test_recusa_de_politica_refaz_em_outro_modelo(self):
        import bot
        from config import settings
        fala = "Tô bem excitada contigo, amor, mas não vou entrar em descrição explícita."
        self.assertEqual(bot._needs_retry_for_junk(fala), (True, "policy_refusal"))
        self.assertEqual(bot._salvage_reply(fala), "Tô bem excitada contigo, amor.")
        with patch.object(settings, "LLM_INTIMATE_MODEL", "x-ai/grok-4.3"):
            self.assertEqual(bot._refusal_retry_model("openai/gpt-5.6-luna"), "x-ai/grok-4.3")
        with patch.object(settings, "LLM_INTIMATE_MODEL", ""), \
             patch.object(settings, "LLM_FALLBACK_MODEL", "deepseek/deepseek-v4-flash"):
            self.assertEqual(bot._refusal_retry_model("openai/gpt-5.6-luna"), "deepseek/deepseek-v4-flash")


if __name__ == "__main__":
    unittest.main()
