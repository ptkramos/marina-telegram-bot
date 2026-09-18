"""
tests/test_voice_router.py — Suíte de Testes do Roteador Adaptativo de Voz (Release 3.7.0).

Valida todas as regras arquiteturais de voz da Marina Salles (Release 3.7.0):
- Roteamento contextual (conversational vs intimate)
- Regra de lembretes sempre em voz natural
- Prioridade de apoio emocional sobre afeto alto
- Salvaguarda de ciclo menstrual (ovulação não força voz sensual sozinha)
- Overrides explícitos do Patrick
- Limite estrito de tags acústicas (0 a 2 tags)
- Fallback entre provedores sem cross-profile descontrolado
"""
import sys
import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
from voice_profile import (
    VoiceProfile,
    get_conversational_profile,
    get_intimate_profile,
    get_voice_profile,
    PROFILE_CONVERSATIONAL,
    PROFILE_INTIMATE,
)
from voice_router import VoiceRouter, VoiceSelectionContext, voice_router
from voice_engine import VoiceEngine


class TestVoiceRouter(unittest.TestCase):
    def setUp(self):
        self.router = VoiceRouter()

    def test_casual_chat_routes_to_conversational(self):
        """Conversas casuais, perguntas e rotina usam o perfil Conversational."""
        ctx = VoiceSelectionContext(
            intent="casual_chat",
            tone="carinhosa",
            user_text="Oi amor, como foi seu dia hoje?",
            is_proactive=False
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_CONVERSATIONAL)
        self.assertEqual(reason, "casual_or_informational")

    def test_planning_future_routes_to_conversational(self):
        """Planejamento de rotina e compromissos usa o perfil Conversational."""
        ctx = VoiceSelectionContext(
            intent="planning_future",
            tone="animada",
            user_text="A gente podia ver um filme no fim de semana, né?",
            is_proactive=False
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_CONVERSATIONAL)

    def test_support_needed_routes_to_conversational_even_with_high_affection(self):
        """Desabafos do Patrick ('dia pesado', 'uma merda') NUNCA devem usar voz sensual, mesmo com afeto alto."""
        ctx = VoiceSelectionContext(
            intent="support_needed",
            tone="dengosa",  # Mesmo se o tom prévio estivesse dengoso
            emotional_state={"affection": 95, "intimacy": 90},
            user_text="Amor, meu dia no trabalho hoje foi uma merda, tô exausto",
            is_proactive=False
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_CONVERSATIONAL)
        self.assertEqual(reason, "support_needed")

    def test_flirting_and_dengosa_routes_to_intimate(self):
        """Flerte com tom dengoso ativa o perfil Intimate."""
        ctx = VoiceSelectionContext(
            intent="flirting",
            tone="dengosa",
            user_text="Tô com muita saudade de ficar agarradinho com você na cama...",
            is_proactive=False
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_INTIMATE)
        self.assertEqual(reason, "flirting_and_intimate_tone")

    def test_sensual_intent_routes_to_intimate(self):
        """Intenção sensual/íntima ativa o perfil Intimate."""
        ctx = VoiceSelectionContext(
            intent="intimate",
            tone="sensual",
            user_text="Você fica tão linda quando fala pertinho de mim...",
            is_proactive=False
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_INTIMATE)

    def test_explicit_natural_override_wins_over_flirting(self):
        """Pedido explícito de voz normal/natural vence o roteador mesmo em contexto romântico."""
        ctx = VoiceSelectionContext(
            intent="flirting",
            tone="dengosa",
            user_text="Manda um áudio na voz normal me dizendo boa noite",
            is_proactive=False
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_CONVERSATIONAL)
        self.assertEqual(reason, "explicit_normal_override")

    def test_explicit_manhosa_override_wins_over_casual(self):
        """Pedido explícito de 'voz manhosa' vence o roteador mesmo em contexto casual."""
        ctx = VoiceSelectionContext(
            intent="casual_chat",
            tone="animada",
            user_text="Fala daquele seu jeitinho manhoso que eu adoro",
            is_proactive=False
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_INTIMATE)
        self.assertEqual(reason, "explicit_manhosa_override")

    def test_reminder_always_uses_conversational(self):
        """Lembretes nunca devem soar sedutores; devem usar estritamente Conversational."""
        ctx = VoiceSelectionContext(
            intent="reminder",
            tone="dengosa",
            is_reminder=True,
            user_text="Reunião às 14h",
            is_proactive=True
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_CONVERSATIONAL)
        self.assertEqual(reason, "reminder")

    def test_cycle_alone_does_not_force_intimate(self):
        """Fase ovulatória isolada NÃO deve forçar voz íntima se o diálogo for neutro/cotidiano."""
        ctx = VoiceSelectionContext(
            intent="question",
            tone="curiosa",
            emotional_state={"cycle_phase": "ovulatória", "affection": 85},
            user_text="Qual foi o almoço de hoje?",
            is_proactive=False
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_CONVERSATIONAL)
        self.assertNotEqual(profile.name, PROFILE_INTIMATE)

    def test_proactive_romantic_audio_can_use_intimate(self):
        """Iniciativa autônoma romântica da Marina com tom dengoso pode usar Intimate."""
        ctx = VoiceSelectionContext(
            intent="romantic",
            tone="dengosa",
            emotional_state={"affection": 90},
            user_text="",
            is_proactive=True,
            source="autonomous"
        )
        profile, reason = self.router.route(ctx)
        self.assertEqual(profile.name, PROFILE_INTIMATE)

    def test_profile_speed_and_voice_ids(self):
        """Valida que os perfis possuem os Voice IDs e cadências calibradas conforme o plano."""
        conv = get_conversational_profile()
        intim = get_intimate_profile()

        self.assertEqual(conv.name, PROFILE_CONVERSATIONAL)
        self.assertEqual(conv.speed, 1.00)
        self.assertIn("voice_", conv.voice_id)

        self.assertEqual(intim.name, PROFILE_INTIMATE)
        self.assertEqual(intim.speed, 0.96)
        self.assertIn("voice_", intim.voice_id)


class TestVoiceEngineExpressionTagsAndFallback(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = VoiceEngine()

    def test_expression_tags_max_limit(self):
        """Garante que tags acústicas sejam no máximo 2 por mensagem (Seção 68)."""
        intim_profile = get_intimate_profile()
        conv_profile = get_conversational_profile()

        # Texto que já tem 2 tags de risos/respiração não ganha tags adicionais
        text_with_two = "Oi amor (chuckle) tudo bem? (laughs) tô aqui pensando em você"
        enriched = self.engine._apply_expression_tags(text_with_two, intim_profile, planner_tone="dengosa")
        count = enriched.count("(chuckle)") + enriched.count("(laughs)") + enriched.count("(breath)") + enriched.count("(sighs)")
        self.assertEqual(count, 2)

        # Texto neutro para perfil íntimo dengoso ganha no máximo 1 tag suave
        clean_saudade = "Tô com tanta saudade de você hoje meu bem"
        enriched_saudade = self.engine._apply_expression_tags(clean_saudade, intim_profile, planner_tone="dengosa")
        self.assertTrue(enriched_saudade.startswith("(sighs)") or enriched_saudade.startswith("(breath)"))

    @patch("voice_engine.requests.post")
    async def test_cross_profile_fallback_disabled_behavior(self, mock_post):
        """
        Se o perfil Intimate na Novita falhar e VOICE_ALLOW_CROSS_PROFILE_FALLBACK=False,
        o motor NÃO deve tentar Novita Conversational; deve ir direto para ElevenLabs/Gemini (Seção 65 e 93).
        """
        mock_post.side_effect = Exception("Novita 500 Internal Error")
        temp_dir = Path(__file__).resolve().parent.parent / "temp_audio"
        temp_dir.mkdir(exist_ok=True)

        with patch.object(self.engine, "_synthesize_elevenlabs", new_callable=AsyncMock) as mock_eleven:
            mock_eleven.return_value = temp_dir / "voice_mock.ogg"
            with patch.object(self.engine, "_synthesize_novita_minimax", wraps=self.engine._synthesize_novita_minimax) as mock_novita:
                ctx = VoiceSelectionContext(intent="flirting", tone="dengosa", user_text="saudades amor")
                result = await self.engine.synthesize("Oi amor saudades", profile="intimate", context=ctx)

                self.assertIsNotNone(result)
                # Verifica que Novita foi tentado exatamente 1 vez com o perfil íntimo (sem fallback cruzado)
                self.assertEqual(mock_novita.call_count, 1)
                first_call_profile = mock_novita.call_args[1].get("profile")
                self.assertEqual(first_call_profile.name, PROFILE_INTIMATE)
                # E o fallback acionado foi o ElevenLabs
                self.assertTrue(mock_eleven.called)


if __name__ == "__main__":
    unittest.main(verbosity=2)
