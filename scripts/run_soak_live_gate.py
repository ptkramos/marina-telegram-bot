"""Synthetic provider smoke: no private DB, history, media or Telegram messages."""
import asyncio
import argparse
import ast
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def run(only=None):
    # Set this before importing modules with legacy database singletons.
    with tempfile.TemporaryDirectory(prefix='marina_live_gate_') as td:
        copy = Path(td) / 'test.db'
        os.environ['MARINA_DB_PATH'] = str(copy)
        from config import settings
        from telegram import Bot
        from telegram.request import HTTPXRequest
        from openai import OpenAI
        from voice_engine import voice_engine
        from voice_profile import PROFILE_CONVERSATIONAL, PROFILE_INTIMATE
        from sd_client import sd_client
        out = ROOT / 'data' / 'soak_live_gate.v370.json'
        results = json.loads(out.read_text())['checks'] if only and out.exists() else {}

        async def check(name, action):
            if only and name != only:
                return
            if name == 'photo_flux' and settings.PHOTO_PROVIDER_MAINTENANCE:
                results[name] = {'status': 'accepted_unavailable',
                                 'detail': 'User deferred GPU recovery; dynamic apology path enabled. No generation attempted.'}
                print(name, 'accepted_unavailable', flush=True)
                return
            try:
                detail = await action()
                results[name] = {'status': 'passed', 'detail': detail}
            except Exception as exc:
                # Provider errors may embed token-bearing URLs; never print them.
                results[name] = {'status': 'failed', 'error_type': type(exc).__name__}
            print(name, results[name]['status'], flush=True)

        async def telegram():
            request = HTTPXRequest(connect_timeout=15, read_timeout=20)
            async with Bot(settings.TELEGRAM_BOT_TOKEN, request=request) as client:
                me = await client.get_me()
                chat = await client.get_chat(settings.TARGET_CHAT_ID)
                webhook = await client.get_webhook_info()
                assert me.is_bot and chat.id == settings.TARGET_CHAT_ID
                assert not webhook.url, 'Webhook would compete with local polling'
            return 'identity, target chat and polling configuration verified; no messages sent'

        async def llm():
            with OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL,
                        timeout=45, max_retries=0) as client:
                response = await asyncio.to_thread(
                    client.chat.completions.create, model=settings.LLM_MODEL,
                    messages=[{'role': 'user', 'content': 'Teste tecnico sintetico. Responda apenas: pronto.'}],
                    max_tokens=30)
            assert response.choices[0].message.content.strip()
            return 'configured model answered synthetic connectivity prompt; no private context'

        async def voice(profile):
            path = await asyncio.wait_for(voice_engine.synthesize(
                'Oi amor, estou por aqui. Depois me conta como foi seu dia.', profile=profile), timeout=110)
            assert path and path.is_file() and path.stat().st_size > 1000
            with path.open('rb') as audio:
                assert audio.read(4) == b'OggS'
            path.unlink()
            return 'native Telegram OGG/Opus generated'

        async def photo_apology():
            # Read only the static instruction, never import or transmit private context.
            tree = ast.parse((ROOT / 'bot.py').read_text(encoding='utf-8'))
            instruction = next(ast.literal_eval(n.value) for n in tree.body
                               if isinstance(n, ast.Assign) and any(
                                   isinstance(t, ast.Name) and t.id == 'PHOTO_UNAVAILABLE_INSTRUCTION'
                                   for t in n.targets))
            with OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL,
                        timeout=45, max_retries=0) as client:
                response = await asyncio.to_thread(
                    client.chat.completions.create, model=settings.LLM_MODEL,
                    messages=[{'role': 'system', 'content': instruction},
                              {'role': 'user', 'content': 'Amor, manda uma foto?'}], max_tokens=120)
            reply = response.choices[0].message.content.strip()
            assert reply and '[MANDAR_' not in reply and 'aqui está a foto' not in reply.casefold()
            return 'configured LLM produced a conversational unavailability reply from synthetic input'

        async def image():
            result = await asyncio.wait_for(sd_client.generate_photo(
                'fully clothed adult woman in a casual blue sweater, warm smile, natural smartphone portrait',
                user_intent='selfie casual vestida'), timeout=420)
            assert result is not None
            from PIL import Image
            image = Image.open(result)
            image.verify()
            return 'configured FLUX workflow generated a valid image'

        await check('telegram_read_only', telegram)
        await check('conversation_llm', llm)
        await check('voice_conversational', lambda: voice(PROFILE_CONVERSATIONAL))
        await check('voice_intimate', lambda: voice(PROFILE_INTIMATE))
        await check('photo_flux', image)
        await check('photo_apology_llm', photo_apology)
        passed = all(v['status'] in ('passed', 'accepted_unavailable') for v in results.values())
        report = {'release': '3.7.0', 'finished_at': datetime.now().astimezone().isoformat(),
                  'checks': results, 'telegram_messages_sent': 0,
                  'status': ('passed_with_photo_maintenance' if settings.PHOTO_PROVIDER_MAINTENANCE else 'passed') if passed else 'failed'}
        out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        return 0 if passed else 1


if __name__ == '__main__':
    logging.basicConfig(level=logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', choices=['telegram_read_only', 'conversation_llm',
                                         'voice_conversational', 'voice_intimate', 'photo_flux', 'photo_apology_llm'])
    parser.add_argument('--diagnose-photo', action='store_true')
    args = parser.parse_args()
    if args.diagnose_photo:
        logging.getLogger('SDClient').setLevel(logging.INFO)
        logging.getLogger('sd_client').setLevel(logging.INFO)
    raise SystemExit(asyncio.run(run(args.only)))
