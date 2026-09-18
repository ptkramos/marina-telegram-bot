import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from config import settings
from response_rhythm import select_policy, segment, apply_policy


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
        text='Uma frase. '*30
        self.assertEqual(segment(text,select_policy('oi')),[text.strip()])
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

    def test_prompt_overrides_only_rhythm(self):
        original='Identidade canônica.\nRitmo: múltiplos balões\nRisada: kkkk'
        result=apply_policy(original,select_policy())
        self.assertIn('Identidade canônica.',result)
        self.assertIn('Risada: kkkk',result)
        self.assertNotIn('múltiplos balões',result)
        self.assertIn('no invented dialogue',result.lower())
        self.assertIn('usually finish without a question',result)
        self.assertEqual(apply_policy(result,select_policy()).count('[RESPONSE RHYTHM]'),1)

    def test_telegram_one_message_and_flag_off_legacy(self):
        import bot
        fake=MagicMock(send_message=AsyncMock(),send_chat_action=AsyncMock())
        text='Primeira frase um pouco maior. '*10
        with patch.object(settings,'RESPONSE_RHYTHM_ENABLED',True),patch('bot.asyncio.sleep',new=AsyncMock()):
            asyncio.run(bot.send_human_messages(987,fake,text,response_policy=select_policy()))
        self.assertEqual(fake.send_message.await_count,1)
        self.assertEqual(fake.send_message.call_args.kwargs['text'],text.strip())
        fake.send_message.reset_mock()
        with patch.object(settings,'RESPONSE_RHYTHM_ENABLED',False),patch('bot.asyncio.sleep',new=AsyncMock()):
            asyncio.run(bot.send_human_messages(987,fake,text))
        self.assertEqual(fake.send_message.await_count,2)

    def test_dynamic_generation_gets_policy_without_extra_llm(self):
        import bot
        response=MagicMock()
        response.choices[0].message.content='kkkk'
        with patch.object(settings,'RESPONSE_RHYTHM_ENABLED',True),patch.object(settings,'LIVING_WORLD_ENABLED',False),patch.object(bot.llm_client.chat.completions,'create',return_value=response) as create:
            self.assertEqual(bot.generate_dynamic_speech('oi'),'kkkk')
        create.assert_called_once()
        self.assertIn('[RESPONSE RHYTHM]',create.call_args.kwargs['messages'][0]['content'])
