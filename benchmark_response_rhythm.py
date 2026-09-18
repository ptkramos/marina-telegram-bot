"""Synthetic A/B/C benchmark. No Telegram, no production memory, no model fallback."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import os
from pathlib import Path
import statistics
import tempfile


CASES = {
 'casual': ['oi amor','cheguei','tô fazendo café','vou tomar banho'],
 'joke': ['kkkkkkkk','derrubei café na camisa de novo','meu cachorro roubou minha meia','errei a porta do escritório kkkkk'],
 'flirt': ['saudade do teu abraço','você ficou linda hoje','queria um beijo agora','tô pensando em você'],
 'routine': ['como foi sua manhã?','já almoçou?','o Milo tá bem?','tá em casa?'],
 'support': ['amor hoje foi uma merda no trabalho','tô triste hoje','queria desabafar um pouco','hoje eu só queria um abraço'],
 'long_support': ['Meu chefe mudou o prazo de novo e eu fiquei até tarde tentando entregar. Tô cansado e nem quero resolver isso agora. Só queria falar com você.', 'Briguei com um amigo, depois perdi o ônibus e cheguei atrasado. Foi tudo acumulando e me deu vontade de chorar.', 'Faz dias que parece que tudo dá errado. Não quero conselho agora, só companhia.', 'Consegui entregar o projeto mas tô esgotado. Passei a semana dormindo mal e ainda acho que não ficou bom.'],
 'conflict': ['precisamos conversar sobre ontem','fiquei magoado com o que você disse','quero discutir uma coisa séria do nosso namoro','não gostei quando você ignorou meu limite'],
 'question': ['qual bairro você mora?','como chama sua melhor amiga?','você tem carro?','o que você estuda?'],
 'explanation': ['me explica detalhadamente como você monta um look','me explica passo a passo como organizar meu portfólio','quero uma análise das opções pra organizar meu dia','me explica em detalhes como funciona um projeto de design'],
 'story': ['me conta aquela história do Milo','conta o que aconteceu com a meia','quero saber da travessura do Milo','conta a história com calma'],
 'reminder': ['me lembra de beber água às 16h','me lembra de ligar pro dentista','cancela meu lembrete','me lembra da reunião amanhã às 10h'],
 'open_loop': ['voltei da entrevista','deu certo o que eu tava tentando','resolvi aquele problema','não consegui falar com ele ainda'],
 'proactive': ['Mande um oi espontâneo, sem inventar evento.','Puxe uma conversa leve sem inventar evento.','Mande uma reação carinhosa breve.','Mande uma mensagem casual sem exigir resposta.'],
 'voice': ['me manda um áudio de bom dia','quero ouvir tua voz, amor','me fala rapidinho como você tá','manda um áudio dizendo oi'],
}


def run(output, workers=4, variants='ABC', categories=None):
    with tempfile.TemporaryDirectory(prefix='rhythm_bench_') as temp:
        os.environ['MARINA_DB_PATH']=str(Path(temp)/'memory.db')
        from config import settings
        from openai import OpenAI
        from db import db_manager
        from bootstrap_v36 import bootstrap
        from context_builder import ContextBuilder
        from memory import MemoryManager
        from response_rhythm import select_policy,apply_policy,segment
        bootstrap(db_manager.db_path,trusted_cycle_anchor='2026-09-02',now=datetime(2026,9,17,16))
        settings.LIVING_WORLD_ENABLED=True
        settings.RESPONSE_RHYTHM_ENABLED=False
        builder=ContextBuilder(memory_mgr=MemoryManager(db=db_manager))
        root=Path(__file__).resolve().parent
        baseline=root/'tests/fixtures/response_rhythm_baseline'
        tree=ast.parse((baseline/'prompts.py').read_text(encoding='utf-8-sig'))
        legacy=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MARIN_SYSTEM_PROMPT' for t in n.targets))
        tree=ast.parse((baseline/'bot.py').read_text(encoding='utf-8-sig'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='split_into_human_bubbles')
        import re
        scope={'re':re}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'<baseline splitter>','exec'),scope)
        legacy_split=scope['split_into_human_bubbles']
        jobs=[]
        for category, messages in CASES.items():
            if categories and category not in categories:
                continue
            for index,message in enumerate(messages):
                plan={'intent':{'support':'support_needed','long_support':'support_needed','conflict':'serious','story':'storytelling'}.get(category,'casual_chat')}
                if category=='reminder' and 'dentista' in message:
                    plan['needs_clarification']='direct_reminder_time'
                policy=select_policy(message,plan=plan,voice=category=='voice')
                world=builder.build_system_prompt(user_message=message,now=datetime(2026,9,17,16))
                extra='\nCenário sintético deste teste: Milo pegou uma meia, correu até o sofá e devolveu quando Marina ofereceu o brinquedo.' if category=='story' else ''
                for variant,prompt in [('A',legacy),('B',world),('C',apply_policy(world,policy))]:
                    if variant in variants:
                        jobs.append((category,index,message,variant,prompt+extra,policy))
        def generate(job):
            category,index,message,variant,prompt,policy=job
            try:
                with OpenAI(api_key=settings.LLM_API_KEY,base_url=settings.LLM_BASE_URL,timeout=90,max_retries=0) as client:
                    result=client.chat.completions.create(model=settings.LLM_MODEL,messages=[{'role':'system','content':prompt},{'role':'user','content':message}],max_tokens=policy.token_budget if variant=='C' else 160,temperature=.8,frequency_penalty=.3,presence_penalty=.25)
                text=result.choices[0].message.content or ''
                bubbles=segment(text,policy) if variant=='C' else legacy_split(text)
                return dict(category=category,index=index,variant=variant,input=message,output=text,chars=len(text),bubbles=len(bubbles),question='?' in text,finish_reason=result.choices[0].finish_reason,voice_estimated_seconds=len(text.split())/2.5 if category=='voice' else None)
            except Exception as exc:
                return dict(category=category,index=index,variant=variant,error=type(exc).__name__)
        rows=[]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(generate,j) for j in jobs]):
                rows.append(future.result())
                if len(rows)%12==0:
                    print(f'Completed {len(rows)}/{len(jobs)}',flush=True)
        summary={}
        for variant in 'ABC':
            good=[r for r in rows if r['variant']==variant and 'error' not in r]
            if good:
                lengths=sorted(r['chars'] for r in good)
                summary[variant]=dict(count=len(good),median_chars=statistics.median(lengths),p90_chars=lengths[int(.9*(len(lengths)-1))],avg_bubbles=statistics.mean(r['bubbles'] for r in good),one_bubble=sum(r['bubbles']==1 for r in good)/len(good),question_rate=sum(r['question'] for r in good)/len(good),truncated=sum(r['finish_reason']=='length' for r in good))
        output=Path(output)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps({'model':settings.LLM_MODEL,'baseline':'snapshot before rhythm, not historical 3.4.3','summary':summary,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(summary),flush=True)
        return 1 if any('error' in r for r in rows) else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='.runtime/response_rhythm/benchmark.json')
    parser.add_argument('--variants',default='ABC',choices=('ABC','C'))
    parser.add_argument('--categories',nargs='+',choices=tuple(CASES))
    args=parser.parse_args()
    raise SystemExit(run(args.output,variants=args.variants,categories=args.categories))
