"""Patch 030 — serialização de turnos no MessageDebouncer.

Reproduz o cenário do soak de 21/09 07:57, quando duas mensagens do Patrick
separadas por 8s (mais que a janela de debounce) abriram ciclos paralelos e as
respostas saíram fora de ordem semântica.
"""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import bot


class DebouncerSerializationTests(unittest.TestCase):
    def test_turno_lento_nao_roda_em_paralelo_com_o_seguinte(self):
        """Segunda mensagem espera o turno anterior terminar."""
        deb = bot.MessageDebouncer(delay_seconds=0.01)
        eventos: list[str] = []

        async def callback(update, context, texto):
            eventos.append(f"start:{texto}")
            await asyncio.sleep(0.15)  # simula latência do LLM
            eventos.append(f"end:{texto}")

        async def cenario():
            deb.add_message(1, "Bom dia amor", MagicMock(), MagicMock(), callback)
            await asyncio.sleep(0.05)  # janela expira, turno 1 entra no pipeline
            deb.add_message(1, "Tá acordada já?", MagicMock(), MagicMock(), callback)
            await asyncio.sleep(0.6)

        asyncio.run(cenario())

        # Sem o lock, a ordem seria start/start/end/end (execução paralela).
        self.assertEqual(eventos[0], "start:Bom dia amor")
        self.assertEqual(eventos[1], "end:Bom dia amor")
        self.assertEqual(eventos[2], "start:Tá acordada já?")
        self.assertEqual(eventos[3], "end:Tá acordada já?")

    def test_rajada_durante_turno_lento_vira_um_unico_turno(self):
        """Mensagens que chegam durante o turno anterior são coalescidas."""
        deb = bot.MessageDebouncer(delay_seconds=0.01)
        recebidos: list[str] = []

        async def callback(update, context, texto):
            recebidos.append(texto)
            await asyncio.sleep(0.2)

        async def cenario():
            deb.add_message(1, "primeira", MagicMock(), MagicMock(), callback)
            await asyncio.sleep(0.05)  # turno 1 já está rodando
            deb.add_message(1, "segunda", MagicMock(), MagicMock(), callback)
            await asyncio.sleep(0.03)
            deb.add_message(1, "terceira", MagicMock(), MagicMock(), callback)
            await asyncio.sleep(0.8)

        asyncio.run(cenario())

        self.assertEqual(recebidos[0], "primeira")
        # "segunda" e "terceira" entram no MESMO turno, não em dois.
        self.assertEqual(len(recebidos), 2, f"esperava 2 turnos, veio {recebidos}")
        self.assertEqual(recebidos[1], "segunda\nterceira")

    def test_rajada_dentro_da_janela_continua_agrupando(self):
        """Comportamento original preservado: burst dentro da janela = 1 turno."""
        deb = bot.MessageDebouncer(delay_seconds=0.12)
        recebidos: list[str] = []

        async def callback(update, context, texto):
            recebidos.append(texto)

        async def cenario():
            deb.add_message(1, "oi", MagicMock(), MagicMock(), callback)
            await asyncio.sleep(0.02)
            deb.add_message(1, "amor", MagicMock(), MagicMock(), callback)
            await asyncio.sleep(0.02)
            deb.add_message(1, "tudo bem?", MagicMock(), MagicMock(), callback)
            await asyncio.sleep(0.5)

        asyncio.run(cenario())

        self.assertEqual(recebidos, ["oi\namor\ntudo bem?"])

    def test_chats_diferentes_nao_bloqueiam_um_ao_outro(self):
        """O lock é por chat — conversa de outro chat não fica na fila."""
        deb = bot.MessageDebouncer(delay_seconds=0.01)
        ativos: list[int] = []
        max_simultaneos = 0

        async def callback(update, context, texto):
            nonlocal max_simultaneos
            ativos.append(1)
            max_simultaneos = max(max_simultaneos, len(ativos))
            await asyncio.sleep(0.15)
            ativos.pop()

        async def cenario():
            deb.add_message(1, "chat um", MagicMock(), MagicMock(), callback)
            deb.add_message(2, "chat dois", MagicMock(), MagicMock(), callback)
            await asyncio.sleep(0.5)

        asyncio.run(cenario())
        self.assertEqual(max_simultaneos, 2)


if __name__ == "__main__":
    unittest.main()
