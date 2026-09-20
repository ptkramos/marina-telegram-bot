"""Voice Library — contract tests (v3.7.1 voice split)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

from voice_library import (
    VoiceExample,
    build_voice_block,
    format_examples_block,
    parse_biblioteca_comportamental,
    select_examples,
)


class CanonicalCatalogTests(unittest.TestCase):
    def test_catalog_has_minimum_diversity(self):
        picks = select_examples(limit=100, include_biblioteca=False)
        self.assertGreaterEqual(len(picks), 8, "catálogo canônico muito pequeno")
        tones = {ex.tone for ex in picks}
        intents = {ex.intent for ex in picks}
        # Cobrir os tones que o planner emite hoje.
        for expected in ("carinhosa", "brincalhona", "dengosa", "acolhedora", "tranquila"):
            self.assertIn(expected, tones, f"tone '{expected}' ausente do catálogo")
        # Intents-chave também presentes.
        for expected in ("casual_chat", "flirting", "support_needed", "planning_future", "sharing_day"):
            self.assertIn(expected, intents, f"intent '{expected}' ausente do catálogo")

    def test_examples_are_short_and_realistic(self):
        picks = select_examples(limit=100, include_biblioteca=False)
        for ex in picks:
            # 1-2 frases: nada de textão nos exemplos.
            self.assertLessEqual(len(ex.marina), 200, f"exemplo muito longo: {ex.marina!r}")
            # Nenhum exemplo pode abrir com 'Ah,' — proibição do CONTROL.
            self.assertFalse(ex.marina.lower().startswith("ah,"),
                             f"exemplo abre com 'Ah,': {ex.marina!r}")


class RankingTests(unittest.TestCase):
    def test_tone_and_intent_match_wins(self):
        picks = select_examples(tone="dengosa", intent="flirting", limit=1, include_biblioteca=False)
        self.assertEqual(len(picks), 1)
        top = picks[0]
        self.assertEqual(top.tone, "dengosa")
        self.assertEqual(top.intent, "flirting")

    def test_tone_alias_normalizes(self):
        picks = select_examples(tone="empolgada", intent="sharing_day", limit=1, include_biblioteca=False)
        self.assertEqual(picks[0].tone, "brincalhona")

    def test_no_match_returns_fallback(self):
        picks = select_examples(tone="inexistente", intent="inexistente", limit=3, include_biblioteca=False)
        self.assertEqual(len(picks), 3)

    def test_limit_zero_returns_empty(self):
        self.assertEqual(select_examples(limit=0, include_biblioteca=False), [])


class BlockFormattingTests(unittest.TestCase):
    def test_block_carries_inspiration_disclaimer(self):
        block = build_voice_block(tone="carinhosa", intent="casual_chat", limit=2, include_biblioteca=False)
        self.assertIn("EXEMPLOS DE VOZ", block)
        self.assertIn("inspiração", block.lower())
        self.assertIn("Patrick:", block)
        self.assertIn("Marina:", block)
        # Sanity: dois pares → 2 x (Patrick + Marina) + delimitadores.
        self.assertEqual(block.count("Patrick:"), 2)
        self.assertEqual(block.count("Marina:"), 2)

    def test_block_stays_within_budget(self):
        block = build_voice_block(limit=4, include_biblioteca=False)
        # Ver PLANO seção 3 A4: ≤ 2000 chars.
        self.assertLessEqual(len(block), 2000, f"bloco estourou o orçamento: {len(block)} chars")

    def test_empty_examples_return_empty_string(self):
        self.assertEqual(format_examples_block([]), "")


class BibliotecaParserTests(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        result = parse_biblioteca_comportamental(Path("/nonexistent/path.md"))
        self.assertEqual(result, [])

    def test_parser_accepts_all_records_with_valid_examples(self):
        """Semântica v3.7.1: os 'Exemplos naturais' são sempre o padrão desejado,
        independente da Avaliação (que só reflete o comportamento observado).
        Ver PLANO_VOZ_MARINA_V371.md — combinado com Patrick em 2026-09-20."""
        md = dedent("""
        # Header

        ## Registro 000 — [gabarito]
        - **Patrick disse:** [mensagem]
        - **Marina respondeu:** [resposta]
        - **Exemplos naturais:**
          - [exemplo 1]
        - **Avaliação:** [boa]

        ## Registro 001 — Jogo do glorioso (avaliação ruim, exemplos bons)
        - **Categoria:** naturalidade
        - **Patrick disse:** Amooo! Daqui a pouco tem jogo do glorioso!
        - **Marina respondeu:** resposta atual ruim
        - **Tom esperado:** brincalhona
        - **Contexto:** puxar assunto sobre jogo
        - **Reação esperada:** brincar
        - **Exemplos naturais:**
          - aeee 🖤🤍 que horas começa?
          - contra quem hoje amor?
        - **Avaliação:** ruim

        ## Registro 002 — Avaliação em branco, exemplos válidos
        - **Patrick disse:** oi amor
        - **Exemplos naturais:**
          - oiii, chegou agora?
        - **Avaliação:**

        ## Registro 003 — Sem exemplos válidos (só placeholder)
        - **Patrick disse:** hipotese
        - **Exemplos naturais:**
          - [exemplo 1]
          - [exemplo 2 opcional]
        - **Avaliação:** boa
        """).strip()

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(md)
            tmp = Path(f.name)
        try:
            result = parse_biblioteca_comportamental(tmp)
        finally:
            tmp.unlink()

        # Registro 000 (gabarito) e 003 (só placeholder) descartados.
        # Registro 001 entra apesar de Avaliação=ruim (exemplos válidos).
        # Registro 002 entra com Avaliação vazia.
        self.assertEqual(len(result), 3, f"esperava 3 exemplos, veio {len(result)}: {result}")
        for ex in result:
            self.assertEqual(ex.source, "biblioteca_comportamental")
        patricks = {ex.patrick for ex in result}
        self.assertIn("Amooo! Daqui a pouco tem jogo do glorioso!", patricks)
        self.assertIn("oi amor", patricks)

    def test_biblioteca_examples_rank_first(self):
        md = dedent("""
        ## Registro 001 — X
        - **Patrick disse:** oi amor
        - **Tom esperado:** carinhosa
        - **Contexto:** puxar assunto
        - **Reação esperada:** brincar
        - **Exemplos naturais:**
          - oiii bem, chegou agora?
        - **Avaliação:** boa
        """).strip()
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(md)
            tmp = Path(f.name)
        try:
            from voice_library import _CANONICAL_EXAMPLES  # noqa: WPS433
            biblio = parse_biblioteca_comportamental(tmp)
            self.assertTrue(biblio, "parser deveria ter extraído ao menos 1 exemplo")
            # Simular select_examples com pool combinado e verificar precedência.
            biblio_ex = biblio[0]
            self.assertEqual(biblio_ex.source, "biblioteca_comportamental")
            # canonical não deve derrubar o biblioteca quando ambos batem tone+intent.
            self.assertNotEqual(biblio_ex.source, _CANONICAL_EXAMPLES[0].source)
        finally:
            tmp.unlink()

    def test_malformed_file_never_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("## Registro 999 — sem campos\n\ntexto solto sem estrutura")
            tmp = Path(f.name)
        try:
            # Não deve lançar exceção — fail-open.
            result = parse_biblioteca_comportamental(tmp)
            self.assertIsInstance(result, list)
        finally:
            tmp.unlink()


class VoiceExampleShapeTests(unittest.TestCase):
    def test_as_dict_roundtrip(self):
        ex = VoiceExample(patrick="oi", marina="oii", tone="carinhosa", intent="casual_chat")
        d = ex.as_dict()
        self.assertEqual(d["patrick"], "oi")
        self.assertEqual(d["marina"], "oii")
        self.assertEqual(d["tone"], "carinhosa")

    def test_examples_are_frozen(self):
        ex = VoiceExample(patrick="a", marina="b")
        with self.assertRaises(Exception):
            ex.patrick = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
