import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from config import settings
from response_rhythm import select_policy
from voice_prosody import (TTSProviderCapabilities,capabilities_for,
                           render_voice,sanitize_display_text,select_voice_prosody)


class TestVoiceProsody(unittest.TestCase):
    def test_neutral_and_no_theatrical_intimacy(self):
        p=select_voice_prosody('oi amor',select_policy('oi',voice=True,plan={'tone':'intimate'}))
        self.assertIsNone(p.emotion)
        self.assertEqual(p.sound_tag_budget,0)
        self.assertEqual(p.filler_budget,0)
        self.assertEqual(p.pause_profile,'none')
        self.assertEqual(select_voice_prosody('amor... que merda, aconteceu o quê?',select_policy('foi uma merda no trabalho')).emotion,None)
        self.assertEqual(select_voice_prosody('não gostei disso',select_policy('oi')).emotion,None)

    def test_capabilities_and_renderer_keep_display_clean(self):
        caps=TTSProviderCapabilities('test',True,frozenset({'neutral','surprised'}),True,True,frozenset({'(chuckle)'}),True,True)
        display='amor eu não acredito kkkkk'
        policy=select_voice_prosody(display,select_policy('oi'))
        result=render_voice(display,policy,caps)
        self.assertEqual(result.display_text,display)
        self.assertIn('(chuckle)',result.render_text)
        self.assertNotIn('(chuckle)',result.display_text)
        self.assertEqual(render_voice(display,policy,capabilities_for('fallback')).render_text,'amor eu não acredito')
        self.assertEqual(sanitize_display_text('oi (sighs) <#0.35#> amor'),'oi amor')
        self.assertEqual(sanitize_display_text('amor (pant)\nkkkk'),'amor\nkkkk')
        self.assertEqual(render_voice('kkkk',select_voice_prosody('kkkk'),capabilities_for('fallback')).render_text,'haha')

    def test_unsupported_features_are_removed(self):
        from voice_prosody import VoiceProsodyPolicy
        p=VoiceProsodyPolicy(emotion='surprised',speed=1.5,pause_profile='casual',continuous_sound=True)
        text='Oi amor. Você viu o que aconteceu agora mesmo?'
        result=render_voice(text,p,capabilities_for('fallback'))
        self.assertEqual(result.emotion,None)
        self.assertEqual(result.speed,1.0)
        self.assertFalse(result.continuous_sound)
        self.assertNotIn('<#',result.render_text)
        capped=render_voice(text,p,TTSProviderCapabilities('test',True,frozenset({'surprised'}),True,False,frozenset(),True,True))
        self.assertEqual(capped.emotion,'surprised')
        self.assertIn('<#0.30#>',capped.render_text)
        self.assertEqual(capped.speed,1.06)

    def test_voice_engine_keeps_same_profile_and_sanitizes_fallback(self):
        from voice_engine import VoiceEngine
        engine=VoiceEngine()
        captured=[]
        async def novita(text,out_ogg,profile=None,voice_plan=None):
            captured.append(('novita',text,profile.name))
            return False
        async def fallback(text,out_ogg):
            captured.append(('fallback',text,None))
            return True
        with patch.object(settings,'VOICE_PROSODY_ENABLED',True),patch.object(settings,'VOICE_PROSODY_SOUND_TAGS_ENABLED',True),patch.object(engine,'_synthesize_novita_minimax',new=novita),patch.object(engine,'_synthesize_elevenlabs',new=fallback):
            asyncio.run(engine.synthesize('amor eu não acredito kkkkk',profile='intimate'))
        self.assertEqual(captured[0][2],'intimate')
        self.assertEqual(len([x for x in captured if x[0]=='novita']),1)
        self.assertNotIn('(chuckle)',captured[1][1])
        self.assertNotIn('kkkk',captured[1][1])


if __name__=='__main__':
    unittest.main()
