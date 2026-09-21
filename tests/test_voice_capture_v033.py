"""Patch 033 — captura de voz em tempo real (/bom e /ruim).

Fecha a Fase B1 do PLANO_VOZ_MARINA_V371: exemplos negativos marcados pelo
Patrick voltam ao prompt no bloco [COMO NÃO SOAR], em vez de ficarem apenas
registrados.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import bot
import voice_library


class ResolveTargetTests(unittest.TestCase):
    def setUp(self):
        bot.ULTIMAS_MENSAGENS_MARINA.clear()
        self.addCleanup(bot.ULTIMAS_MENSAGENS_MARINA.clear)

    def _update(self, reply=None):
        return SimpleNamespace(message=SimpleNamespace(reply_to_message=reply))

    def test_usa_ultima_fala_quando_nao_ha_reply(self):
        bot.ULTIMAS_MENSAGENS_MARINA[1] = [
            {"message_id": 10, "text": "primeira"},
            {"message_id": 11, "text": "última coisa que falei"},
        ]
        self.assertEqual(
            bot._resolve_marina_target(self._update(), 1),
            "última coisa que falei",
        )

    def test_reply_tem_prioridade_sobre_a_ultima(self):
        bot.ULTIMAS_MENSAGENS_MARINA[1] = [{"message_id": 11, "text": "a mais recente"}]
        reply = SimpleNamespace(text="a que o Patrick citou", message_id=10, caption=None)
        self.assertEqual(
            bot._resolve_marina_target(self._update(reply), 1),
            "a que o Patrick citou",
        )

    def test_reply_sem_texto_cai_no_historico_por_message_id(self):
        """Reply numa foto sem legenda ainda resolve via histórico."""
        bot.ULTIMAS_MENSAGENS_MARINA[1] = [
            {"message_id": 10, "text": "texto da mensagem citada"},
            {"message_id": 11, "text": "outra"},
        ]
        reply = SimpleNamespace(text=None, caption=None, message_id=10)
        self.assertEqual(
            bot._resolve_marina_target(self._update(reply), 1),
            "texto da mensagem citada",
        )

    def test_sem_historico_devolve_none(self):
        self.assertIsNone(bot._resolve_marina_target(self._update(), 999))

    def test_ignora_entradas_vazias(self):
        bot.ULTIMAS_MENSAGENS_MARINA[1] = [
            {"message_id": 10, "text": "fala real"},
            {"message_id": 11, "text": "   "},
        ]
        self.assertEqual(bot._resolve_marina_target(self._update(), 1), "fala real")


class AntibibliotecaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "COMO_NAO_SOAR_MARINA.md"

    def test_cria_arquivo_com_cabecalho_na_primeira_captura(self):
        self.assertFalse(self.path.exists())
        numero = bot._append_avoid_example(self.path, "oi", "resposta ruim", "motivo")
        self.assertEqual(numero, 1)
        conteudo = self.path.read_text(encoding="utf-8")
        self.assertIn("Como a Marina NÃO deve soar", conteudo)
        self.assertIn("## Evitar 001", conteudo)

    def test_numeracao_sequencial(self):
        for esperado in (1, 2, 3):
            numero = bot._append_avoid_example(
                self.path, "ctx", f"ruim {esperado}", "motivo")
            self.assertEqual(numero, esperado)

    def test_roundtrip_grava_e_parseia(self):
        bot._append_avoid_example(
            self.path,
            "q bom princesa, tá fazendo o que agora?",
            "Estou aqui no meu quarto, lendo um pouco antes de começar o dia.",
            "disse que estava em casa quando estava passeando com o Milo",
        )
        bot._append_avoid_example(
            self.path, "e você?", "Dormi também, obrigada por perguntar!",
            "polidez de atendente",
        )
        exemplos = voice_library.parse_avoid_examples(self.path)
        self.assertEqual(len(exemplos), 2)
        self.assertIn("meu quarto", exemplos[0].marina)
        self.assertIn("passeando com o Milo", exemplos[0].motivo)
        self.assertIn("tá fazendo o que agora", exemplos[0].patrick)
        self.assertIn("obrigada por perguntar", exemplos[1].marina)

    def test_motivo_vazio_nao_quebra(self):
        bot._append_avoid_example(self.path, "ctx", "fala ruim", "")
        exemplos = voice_library.parse_avoid_examples(self.path)
        self.assertEqual(len(exemplos), 1)
        self.assertEqual(exemplos[0].marina, "fala ruim")

    def test_arquivo_ausente_devolve_lista_vazia(self):
        ausente = Path(self.tmp.name) / "nao_existe.md"
        self.assertEqual(voice_library.parse_avoid_examples(ausente), [])


class AvoidBlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "COMO_NAO_SOAR_MARINA.md"

    def test_bloco_vazio_quando_nao_ha_capturas(self):
        with patch.object(voice_library, "_ANTIBIBLIOTECA_PATH", self.path):
            self.assertEqual(voice_library.build_avoid_block(), "")

    def test_bloco_traz_os_mais_recentes(self):
        for i in range(1, 7):
            bot._append_avoid_example(self.path, f"ctx {i}", f"fala ruim {i}", f"motivo {i}")
        with patch.object(voice_library, "_ANTIBIBLIOTECA_PATH", self.path):
            bloco = voice_library.build_avoid_block(limit=3)
        self.assertIn("[COMO NÃO SOAR", bloco)
        # Os 3 últimos entram, os 3 primeiros não.
        for i in (4, 5, 6):
            self.assertIn(f"fala ruim {i}", bloco)
        for i in (1, 2, 3):
            self.assertNotIn(f"fala ruim {i}", bloco)

    def test_bloco_identifica_a_fala_como_ruim(self):
        bot._append_avoid_example(self.path, "oi amor", "resposta protocolar", "soou SAC")
        with patch.object(voice_library, "_ANTIBIBLIOTECA_PATH", self.path):
            bloco = voice_library.build_avoid_block()
        self.assertIn("Marina (RUIM): resposta protocolar", bloco)
        self.assertIn("Problema: soou SAC", bloco)
        self.assertIn("Patrick: oi amor", bloco)


if __name__ == "__main__":
    unittest.main()
