import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from config import settings
from response_rhythm import (
    apply_policy,
    needs_verbosity_retry,
    segment,
    select_policy,
    verbosity_retry_constraint,
)


class TestResponseRhythm(unittest.TestCase):
    def test_modes_and_voice_do_not_depend_on_intimacy(self):
        self.assertEqual(select_policy('oi').mode,'casual_short')
        self.assertEqual(select_policy('me explica detalhadamente').mode,'explanatory')
        self.assertEqual(select_policy('precisamos conversar').mode,'serious')
        self.assertEqual(select_policy('foi uma merda no trabalho').mode,'supportive')
        self.assertEqual(select_policy('conta',storytelling=True).mode,'storytelling')
        self.assertEqual(select_policy('oi',voice=True,plan={'tone':'intimate'}).voice_soft_seconds,15)
        self.assertEqual(select_policy('oi',plan={'followup_question':'none'}).followup_question,'not_required')
        self.assertEqual(select_policy('me lembra',plan={'needs_clarification':'direct_reminder_time'}).followup_question,'required_for_action')

    def test_casual_does_not_fragment_or_expand(self):
        # Long text (>180 chars) now auto-splits into 2 bubbles at sentence boundaries.
        text='Uma frase. '*30
        parts = segment(text,select_policy('oi'))
        self.assertEqual(len(parts), 2)
        self.assertEqual(' '.join(parts), text.strip())
        # Short merged line stays single bubble.
        self.assertEqual(segment('amor\nkkkk',select_policy('oi')),['amor\nkkkk'])
        self.assertEqual(segment('kkkk',select_policy('oi')),['kkkk'])
        self.assertEqual(segment('',select_policy()),[])

    def test_semantic_bubbles_and_transport_preserve_content(self):
        policy=select_policy('oba',plan={'intent':'excited'})
        parts=segment('Não acredito nisso!\nSério\nFoi muito engraçado.\nPreciso te contar.',policy)
        self.assertLessEqual(len(parts),3)
        self.assertTrue(all(len(p.split())>1 for p in parts))
        text='😀'*5000
        parts=segment(text,select_policy())
        self.assertEqual(''.join(parts),text)
        self.assertTrue(all(len(p.encode('utf-16-le'))//2<=4096 for p in parts))

    def test_excited_plain_text_can_use_two_semantic_bubbles(self):
        policy = select_policy('finalmente deu certo!!')
        self.assertEqual(policy.mode, 'excited')
        self.assertEqual(
            segment('Não acredito que deu certo! Tô feliz demais com isso.', policy),
            ['Não acredito que deu certo!', 'Tô feliz demais com isso.'],
        )

    def test_token_ceiling_tracks_character_budget_and_retry_is_rare(self):
        casual = select_policy('oi')
        explanatory = select_policy('me explica detalhadamente')
        self.assertEqual(casual.soft_char_limit, 180)
        self.assertLessEqual(casual.token_budget, 128)
        self.assertGreater(explanatory.token_budget, casual.token_budget)
        self.assertFalse(needs_verbosity_retry('x' * 360, casual))
        self.assertTrue(needs_verbosity_retry('x' * 361, casual))
        constraint = verbosity_retry_constraint('texto longo', casual)
        self.assertIn('180 characters', constraint)
        self.assertIn('Return only the replacement message', constraint)

    def test_prompt_overrides_only_rhythm(self):
        original='Identidade canônica.\nRitmo: múltiplos balões\nRisada: kkkk'
        result=apply_policy(original,select_policy())
        self.assertIn('Identidade canônica.',result)
        self.assertIn('Risada: kkkk',result)
        self.assertNotIn('múltiplos balões',result)
        self.assertIn('sem diálogo',result.lower())
        self.assertIn('em geral termine sem pergunta',result)
        self.assertEqual(apply_policy(result,select_policy()).count('[RITMO DE RESPOSTA]'),1)

    def test_telegram_transport_always_uses_canonical_rhythm(self):
        import bot
        fake=MagicMock(send_message=AsyncMock(),send_chat_action=AsyncMock())
        # Long text (>180 chars) auto-splits into 2 bubbles.
        text='Primeira frase um pouco maior. '*10
        with patch('bot.asyncio.sleep',new=AsyncMock()):
            asyncio.run(bot.send_human_messages(987,fake,text,response_policy=select_policy()))
        self.assertEqual(fake.send_message.await_count, 2)
        # Both bubbles together reconstruct the original content, minus the
        # period that closes each bubble (chat_naturalness).
        calls = [c.kwargs['text'] for c in fake.send_message.call_args_list]
        self.assertTrue(all(not c.endswith('.') for c in calls), calls)
        self.assertEqual('. '.join(calls) + '.', text.strip())

    def test_dynamic_generation_gets_policy_without_extra_llm(self):
        import bot
        response=MagicMock()
        response.choices[0].message.content='kkkk'
        with patch.object(bot.context_builder,'build_system_prompt',return_value='[CANONICAL WORLD]'),patch.object(bot.llm_client.chat.completions,'create',return_value=response) as create:
            self.assertEqual(bot.generate_dynamic_speech('oi'),'kkkk')
        create.assert_called_once()
        self.assertIn('[RITMO DE RESPOSTA]',create.call_args.kwargs['messages'][0]['content'])
        self.assertLessEqual(create.call_args.kwargs['max_tokens'], 120)
