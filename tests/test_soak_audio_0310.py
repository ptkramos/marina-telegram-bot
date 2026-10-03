"""Soak, dia 5 (sábado 03/10, 13:41): "Eu nem mandei áudio!"

No meio do sexting ela mandou um áudio de vontade própria ("O drama meu pai kkkkkk… vem cá receber um chamego",
log `chat.enviado tipo=audio` às 13:41:18). O Patrick respondeu "Mds tu não imagina como esse audio me deixou agr"
e ela: "Que áudio, Patrick? Ficou doido de vez? Eu nem mandei áudio!". O banco gravou a fala do áudio como texto
(media_type='text') e o histórico nem lia a coluna — pro modelo, aquilo tinha sido digitado.
"""
import ast
import inspect
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from context_builder import MARCA_AUDIO_DELA, marcar_pausas
from db import DatabaseManager
from memory import MemoryManager

AUDIO = ("O drama meu pai kkkkkk\nAmor, para de graça!\nVc sabe muito bem que é o namorado mais perfeito do mundo cmg\n"
         "Tô só te provocando, seu bobo... vem cá receber um chamego vem")


class AudioNoHistoricoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "c.db")
        self.mm = MemoryManager(self.db)
        ts = lambda hh, mm, ss: datetime(2026, 10, 3, hh, mm, ss).isoformat()
        self.db.adicionar_mensagem(role="user", content="Então tudo que eu faço durante o dia não serve é isso?!",
                                   timestamp=ts(13, 41, 9))
        self.mm.registrar_mensagem_assistente(AUDIO, model="m", media_type="voice")
        self.db.adicionar_mensagem(role="user", content="Mds tu não imagina como esse audio me deixou agr 🥵",
                                   timestamp=ts(13, 42, 32))

    def test_audio_dela_vai_pro_modelo_marcado(self):
        hist = marcar_pausas(self.mm.get_historico_recente(limit=10))
        self.assertEqual(hist[1]["role"], "assistant")
        self.assertEqual(hist[1]["content"], f"{MARCA_AUDIO_DELA} {AUDIO}")

    def test_texto_e_falas_dele_ficam_sem_marca(self):
        self.mm.registrar_mensagem_assistente("Que áudio, Patrick?", model="m")
        hist = marcar_pausas(self.mm.get_historico_recente(limit=10))
        self.assertNotIn(MARCA_AUDIO_DELA, hist[0]["content"])
        self.assertNotIn(MARCA_AUDIO_DELA, hist[2]["content"])
        self.assertEqual(hist[3]["content"], "Que áudio, Patrick?")

    def test_banco_guarda_o_texto_limpo(self):
        """Relatório do soak e observadores (fome, promessa de foto) leem o content: a marca é só no prompt."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT content, media_type FROM conversas WHERE role='assistant'").fetchone()
        self.assertEqual((row["content"], row["media_type"]), (AUDIO, "voice"))


class MarcaCopiadaTest(unittest.TestCase):
    def test_marca_copiada_pelo_modelo_nao_sai_no_chat(self):
        import bot
        self.assertEqual(bot.limpar_fala_marina("[áudio] Tô só te provocando"), "Tô só te provocando")
        self.assertEqual(bot.limpar_fala_marina("[Áudio] Vem cá"), "Vem cá")


class GravacaoDoTurnoTest(unittest.TestCase):
    def test_os_dois_caminhos_de_gravacao_levam_a_midia(self):
        """Resposta ao vivo e resposta de lote pendente: as duas gravam media_type do que saiu."""
        import bot
        arvore = ast.parse(inspect.getsource(bot))
        com_midia = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and getattr(no.func, "attr", "") in (
                    "registrar_mensagem_assistente", "adicionar_mensagem"):
                kw = {k.arg: k.value for k in no.keywords}
                if isinstance(kw.get("media_type"), ast.Name) and kw["media_type"].id == "midia_dela":
                    com_midia.append(no.func.attr)
        self.assertEqual(sorted(com_midia), ["adicionar_mensagem", "registrar_mensagem_assistente"])


if __name__ == "__main__":
    unittest.main()
