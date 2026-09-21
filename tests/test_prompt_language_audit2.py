"""Auditoria #2 — nenhum rótulo ou prompt de processamento em inglês.

O Patch 021 traduziu os blocos de controle da conversa e foi considerado a
mudança mais impactante do soak. Mas ele cobriu só o prompt de fala: os prompts
de *processamento* (planner, consolidator, session reflector, vision) e dois
rótulos fixos do `world_context` continuaram em inglês.

O caso mais silencioso era o `response_goal`: era o único campo do schema do
planner sem instrução de idioma, então saía em inglês — e o `world_context`
injetava o valor cru no prompt da Marina como "Goal: ...", a cada turno.

Este arquivo existe para que a próxima tradução parcial falhe no CI em vez de
passar despercebida por semanas.
"""
import re
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import memory_consolidator
import planner
import session_reflector
import vision_service
from context_builder import context_builder


class ProcessingPromptsLanguageTests(unittest.TestCase):
    """Prompts que leem e escrevem português devem instruir em português."""

    CASOS = (
        ("planner", lambda: planner.PLANNER_SYSTEM_PROMPT),
        ("consolidator", lambda: memory_consolidator.CONSOLIDATOR_SYSTEM_PROMPT),
        ("session_reflector", lambda: session_reflector.SESSION_REFLECTOR_SYSTEM_PROMPT),
        ("vision", lambda: vision_service.VISION_PROMPT),
    )

    ABERTURAS_EN = ("You are", "Analyze the", "Extract durable",
                    "CLASSIFICATION AND", "RULES:", "HARD RULES:")

    def test_nenhum_prompt_de_processamento_abre_em_ingles(self):
        for nome, obter in self.CASOS:
            with self.subTest(prompt=nome):
                texto = obter()
                for marcador in self.ABERTURAS_EN:
                    self.assertNotIn(
                        marcador, texto,
                        f"prompt do {nome} voltou a conter instrução em inglês: {marcador!r}")

    def test_prompts_de_processamento_instruem_em_portugues(self):
        for nome, obter in self.CASOS:
            with self.subTest(prompt=nome):
                texto = obter()
                self.assertRegex(
                    texto, r"\b(Você|Responda|Analise|Extraia|Devolva|Seja)\b",
                    f"prompt do {nome} não tem instrução em português")

    def test_planner_exige_response_goal_em_portugues(self):
        """O campo que vazava inglês direto para o prompt da Marina."""
        texto = planner.PLANNER_SYSTEM_PROMPT
        trecho = re.search(r'"response_goal":\s*"([^"]+)"', texto)
        self.assertIsNotNone(trecho, "schema do planner deve declarar response_goal")
        self.assertRegex(
            trecho.group(1).upper(), r"PORTUGU[ÊE]S",
            "response_goal precisa exigir português — sem isso o planner "
            "escreve em inglês e o texto entra cru no prompt da Marina")


class PromptLabelsLanguageTests(unittest.TestCase):
    """Rótulos fixos do prompt montado em produção."""

    def setUp(self):
        msgs = context_builder.build(
            user_message="e a prova da quinta?",
            planner_tone="carinhosa",
            planner_goal="puxar detalhe concreto sobre a prova",
        )
        self.prompt = msgs[0]["content"]

    def test_sem_rotulos_em_ingles(self):
        for rotulo in ("[LEARNED STYLE]", "[PLANNER 3.5", "[KNOWLEDGE POLICY]",
                       "[CONTROL RULES]", "[HARD LINES]", "[MARINA VOICE]",
                       "[DATA CHANNEL POLICY]"):
            with self.subTest(rotulo=rotulo):
                self.assertNotIn(rotulo, self.prompt)

    def test_sem_labels_de_campo_em_ingles(self):
        """'Tone:' e 'Goal:' eram emitidos sem ramo condicional de idioma."""
        self.assertNotIn("Tone:", self.prompt)
        self.assertNotIn("Goal:", self.prompt)

    def test_com_equivalentes_em_portugues(self):
        for rotulo in ("[COMO O PATRICK ESCREVE]", "[INTENÇÃO DESTE TURNO",
                       "Tom:", "Objetivo:"):
            with self.subTest(rotulo=rotulo):
                self.assertIn(rotulo, self.prompt)


if __name__ == "__main__":
    unittest.main()
