"""Manual short speech probe. Run explicitly; never imported by unit tests.

Auditoria #1: movido de `voice_prosody_smoke_test.py` na raiz para cá. O nome
antigo, com prefixo `test_`, dava a entender que fazia parte da suíte — mas
`unittest discover -s tests` nunca o coletava, e se coletasse faria chamada de
rede real para a Novita.
"""
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings
from voice_engine import VoiceEngine
from voice_profile import get_voice_profile


SAMPLES = {
    'neutral': ('amor, eu já tô aqui em casa.', None, False),
    'happy': ('consegui terminar o projeto hoje!', 'happy', False),
    'chuckle': ('amor, você é muito bobo (chuckle)', None, False),
    'pause': ('eu pensei nisso. <#0.25#> e acho que pode dar certo.', None, False),
    'continuous': ('foi um dia corrido, mas consegui resolver o projeto e agora vou descansar.', None, True),
    # Controlled comparison: identical words in both profiles and all five variants.
    'compare_plain': ('amor, eu não acredito nisso. O Milo pegou minha meia de novo.', None, False),
    'compare_emotion': ('amor, eu não acredito nisso. O Milo pegou minha meia de novo.', 'surprised', False),
    'compare_pause': ('amor, eu não acredito nisso. <#0.25#> O Milo pegou minha meia de novo.', None, False),
    'compare_sound': ('amor, eu não acredito nisso. O Milo pegou minha meia de novo. (chuckle)', None, False),
    'compare_full': ('amor, eu não acredito nisso. <#0.25#> O Milo pegou minha meia de novo. (chuckle)', 'surprised', True),
}


def duration(path):
    try:
        p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],capture_output=True,text=True,timeout=15)
        return round(float(p.stdout.strip()),2) if p.returncode==0 else None
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return None


async def run(names,profiles,out):
    engine=VoiceEngine()
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    from voice_prosody import VoiceRenderPlan
    for profile_name in profiles:
        profile=get_voice_profile(profile_name)
        for name in names:
            words,emotion,continuous=SAMPLES[name]
            plan=VoiceRenderPlan(words,words,emotion,1.0,continuous,{'emotion':emotion} if emotion else {})
            target=out/f'{profile_name}_{name}.ogg'
            ok=await engine._synthesize_novita_minimax(words,target,profile=profile,voice_plan=plan)
            rows.append({'profile':profile_name,'sample':name,'success':ok,'duration_seconds':duration(target) if ok else None})
            print(f'{profile_name}/{name}: {"ok" if ok else "failed"}',flush=True)
    report={'model':engine.novita_voice_model,'endpoint':f'https://api.novita.ai/v3/minimax-{engine.novita_voice_model}',
            'tested_at':datetime.now().isoformat(),'rows':rows}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(r['success'] for r in rows) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Explicitly spend API credits')
    parser.add_argument('--samples',nargs='+',choices=tuple(SAMPLES),default=['neutral','happy','chuckle','pause','continuous'])
    parser.add_argument('--profiles',nargs='+',choices=('conversational','intimate'),default=['conversational','intimate'])
    parser.add_argument('--output',type=Path,default=Path('.runtime/voice_prosody'))
    args=parser.parse_args()
    if not args.run:
        parser.error('Pass --run to execute actual paid speech requests')
    raise SystemExit(asyncio.run(run(args.samples,args.profiles,args.output)))
