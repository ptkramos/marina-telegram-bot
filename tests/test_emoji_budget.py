"""Teto de emoji por fala e /feedback chegando ao prompt (22/09).

Medido no soak do Luna: 15 de 15 falas do dia levavam emoji, média 1,2 por fala
e 😘 respondia por 9 dos 21 — virou tique de fecho. O Patrick registrou
`/feedback Não é necessário que toda mensagem termine com emojis` e nada mudou,
porque o comando gravava no banco e o único injetor vivia em
`memory.get_contexto_emocional`, marcado como legacy e sem chamador em produção.
"""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import re

import bot
from db import DatabaseManager
from response_rhythm import segment, select_policy, thin_emojis
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from world_context import WorldContextBuilder

_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿\U0001F900-\U0001F9FF]")


class EmojiCapTests(unittest.TestCase):
    def test_sobra_um_emoji_por_fala(self):
        fala = "Isso faz muita diferença pra mim, amor 🥺 Obrigada por estar sempre comigo. Te amo 🫶"
        saida = thin_emojis(fala)
        self.assertEqual(len(_EMOJI_RE.findall(saida)), 1, saida)

    def test_o_emoji_preservado_e_o_primeiro(self):
        """O primeiro marca o pivô da batida; tirar ele desmancharia o balão."""
        saida = thin_emojis("Bom dia, amor 😘 Tô indo pra facul agora, te amo 🥺")
        self.assertIn("😘", saida)
        self.assertNotIn("🥺", saida)

    def test_pivo_continua_virando_dois_baloes(self):
        fala = "Bom dia, amor 😘 Bom trabalho pra você, vai com calma e se cuida 🫶"
        self.assertEqual(len(segment(thin_emojis(fala), select_policy("oi amor"))), 2)

    def test_emoji_composto_nao_e_quebrado(self):
        """😮‍💨 é um emoji com ZWJ: cortar no meio deixa dois emojis soltos."""
        fala = "Saí da facul agora, tô voltando pra casa de Uber pela Gávea 😮‍💨\nHoje foram quatro aulas kkk"
        saida = thin_emojis(fala)
        self.assertIn("😮‍💨", saida)

    def test_fala_sem_emoji_fica_intacta(self):
        fala = "Tô na PUC ainda, amor. Saio às 15h e te chamo."
        self.assertEqual(thin_emojis(fala), fala)

    def test_nunca_deixa_a_fala_sem_texto(self):
        for fala in ("😘", "🥺 🫶"):
            with self.subTest(fala=fala):
                self.assertEqual(thin_emojis(fala), fala)

    def test_nao_deixa_espaco_dobrado_nem_antes_de_pontuacao(self):
        saida = thin_emojis("Te amo demais 🫶, amor. Tô morrendo de saudade 🥺 kkk")
        self.assertNotIn("  ", saida)
        self.assertNotRegex(saida, r"\s+[,.!?]")


class EmojiTailTests(unittest.TestCase):
    """Feedback do Patrick: nem toda mensagem precisa terminar com emoji."""

    FALAS = [
        "Tô na PUC, amor, na aula de O Cristianismo. Vai até às 15h, então tô aqui firme ainda 😘",
        "Kkkkk total, amor. Hoje foi dia de luta, mas vou descansar depois 😘",
        "Foi tranquilo sim, amor. Ele me tratou com respeito direitinho 😘",
        "Não, amor, já cheguei em casa faz um tempinho. Tô descansando agora 😘",
        "Que bom que tá tranquilo, amor. Vou te esperar pra conversar às 19h30 😘",
        "Também te amo demais, meu amor ❤️",
        "Vai sim, amor. Só preciso chegar em casa e apagar um pouquinho kkk 🥺",
        "Acabei de sair da facul. Tô morta, quero só deitar 😴",
    ]

    def test_parte_das_falas_perde_o_emoji_do_fecho(self):
        secas = [f for f in self.FALAS if not _EMOJI_RE.search(thin_emojis(f))]
        self.assertTrue(secas, "nenhuma fala terminou seca")
        self.assertLess(len(secas), len(self.FALAS), "todas as falas ficaram sem emoji")

    def test_decisao_e_estavel_para_a_mesma_fala(self):
        for fala in self.FALAS:
            primeiro = thin_emojis(fala)
            for _ in range(5):
                self.assertEqual(thin_emojis(fala), primeiro)

    def test_kill_switch_devolve_a_fala_crua(self):
        # Patch no settings que o módulo realmente lê: outros testes recarregam
        # `config`, então `from config import settings` aqui pode ser outro objeto.
        import response_rhythm
        with patch.object(response_rhythm.settings, "VOICE_EMOJI_BUDGET", False):
            fala = "Isso faz diferença pra mim, amor 🥺 Te amo 🫶"
            self.assertEqual(thin_emojis(fala), fala)

    def test_limpeza_de_fala_aplica_o_teto(self):
        saida = bot.limpar_fala_marina("Isso faz diferença pra mim, amor 🥺 Te amo demais 🫶")
        self.assertEqual(len(_EMOJI_RE.findall(saida)), 1, saida)


class FeedbackNoPromptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(Path(self.tmp.name) / "feedback.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO world_bootstrap (key, value, updated_at)
                   VALUES ('clean_canonical_start_done', '1', '2026-09-18T00:00:00')"""
            )

    def _prompt(self):
        return WorldContextBuilder(self.db).build(
            now=datetime(2026, 9, 22, 16, 0), user_message="oi amor"
        )

    def test_feedback_pendente_entra_no_prompt_so_se_ligado(self):
        self.db.salvar_feedback("fb-emoji", "Não é necessário que toda mensagem termine com emojis")
        self.assertNotIn("[PEDIDOS DO PATRICK", self._prompt(), "23/09: /feedback é caderno, não ordem")
        from unittest.mock import patch
        import world_context   # o settings que o world_context enxerga (a suíte recarrega config)
        with patch.object(world_context.settings, "PATRICK_FEEDBACK_IN_PROMPT", True, create=True):
            prompt = self._prompt()
        self.assertIn("[PEDIDOS DO PATRICK", prompt)
        self.assertIn("toda mensagem termine com emojis", prompt)

    def test_sem_feedback_nao_cria_bloco_vazio(self):
        self.assertNotIn("[PEDIDOS DO PATRICK", self._prompt())

    def test_feedback_resolvido_sai_do_prompt(self):
        self.db.salvar_feedback("fb-antigo", "fala menos 'mano'")
        with self.db.get_connection() as conn:
            conn.execute("UPDATE feedbacks SET status='resolvido' WHERE id='fb-antigo'")
        self.assertNotIn("fala menos", self._prompt())


if __name__ == "__main__":
    unittest.main()
