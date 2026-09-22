"""Arena de modelos — Auditoria #9.

Roda a Marina DE VERDADE (process_incoming_batch / handle_photo_message, prompt,
planner, guards e segmentação em balões) contra modelos do OpenRouter, com
roteiros fixos e relógio congelado. Só o modelo muda.

Isolamento:
  * cada corrida (modelo × cenário × repetição) é um subprocesso com a sua
    própria CÓPIA do banco (backup SQLite read-only da produção, sem conversa);
  * nada vai para o Telegram (bot falso), nada vai para o marina.log;
  * visão, foto e voz são stubs — o que se avalia é a conversa.

Uso:
  python scripts/model_arena.py --models mistralai/mistral-nemo,deepseek/deepseek-v4-flash \
      --scenarios noite_domingo,dia_dela --reps 1 --parallel 4
Acompanhe: Get-Content logs\\testes_ao_vivo.log -Wait -Tail 30
"""
import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
LIVE_LOG = ROOT / "logs" / "testes_ao_vivo.log"
PROD_DB = ROOT / "marin_memory.db"
OUT_ROOT = ROOT / "data" / "model_arena"

# Tabelas de conversa/estado transitório zeradas na cópia: cada cenário começa
# numa conversa nova, com o mundo, o cânone e a memória de longo prazo intactos.
RESET_TABLES = ("conversas", "world_state", "response_availability_events",
                "response_pending_batch_items", "response_pending_batches",
                "open_loops", "eventos_pendentes", "reminders")


def live(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode(), flush=True)
    LIVE_LOG.parent.mkdir(exist_ok=True)
    with LIVE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def make_snapshot(dest: Path) -> None:
    src = sqlite3.connect(f"file:{PROD_DB.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    src.backup(dst)
    src.close()
    for table in RESET_TABLES:
        dst.execute(f"DELETE FROM {table}")
    dst.commit()
    dst.close()


# ---------------------------------------------------------------- filho ----

def run_child(model: str, scenario: str, rep: int, out: Path, db_path: Path, reasoning: str,
              intimate: str = "") -> None:
    import datetime as dtmod
    from scripts_clock import install_clock
    clock = install_clock(dtmod)            # antes de QUALQUER import do bot

    os.environ["MARINA_DB_PATH"] = str(db_path)
    os.environ["MARINA_LOG_TO_FILE"] = "0"
    import logging
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from openai.resources.chat.completions import Completions
    from model_arena_scenarios import SCENARIOS

    sc = SCENARIOS[scenario]
    clock.set(sc["inicio"])

    calls, bubbles, mandatory_reasoning = [], [], set()
    original_create = Completions.create
    reasoning_cfg = {"enabled": False} if reasoning == "off" else {"effort": reasoning}

    def create(self, *args, **kwargs):
        caller = sys._getframe(1).f_code
        # O bot escolhe o modelo (principal, íntimo ou reserva); a arena só observa.
        used = kwargs.get("model") or model
        extra = dict(kwargs.pop("extra_body", None) or {})
        extra.setdefault("reasoning", reasoning_cfg)
        extra["usage"] = {"include": True}
        rec = {"caller": f"{Path(caller.co_filename).stem}.{caller.co_name}", "model": used,
               "max_tokens": kwargs.get("max_tokens"), "t": clock.now().isoformat()}
        if used in mandatory_reasoning:
            # Modelos que não deixam desligar o raciocínio: esforço baixo, raciocínio
            # fora da resposta e orçamento extra para ele não comer a fala.
            extra["reasoning"] = {"effort": "low", "exclude": True}
            kwargs["max_tokens"] = (kwargs.get("max_tokens") or 400) + 1500
            rec["reasoning"] = "mandatory_low"
        t0 = time.perf_counter()
        try:
            resp = original_create(self, *args, extra_body=extra, **kwargs)
        except Exception as exc:
            if "Reasoning is mandatory" in str(exc) and used not in mandatory_reasoning:
                mandatory_reasoning.add(used)
                return create(self, *args, **kwargs)
            rec.update(error=f"{type(exc).__name__}: {str(exc)[:300]}",
                       latency=round(time.perf_counter() - t0, 2))
            calls.append(rec)
            raise
        usage = getattr(resp, "usage", None)
        rec.update(latency=round(time.perf_counter() - t0, 2),
                   provider=getattr(resp, "provider", None),
                   prompt_tokens=getattr(usage, "prompt_tokens", None),
                   completion_tokens=getattr(usage, "completion_tokens", None),
                   cost=getattr(usage, "cost", None),
                   finish=resp.choices[0].finish_reason if resp.choices else None,
                   content=(resp.choices[0].message.content if resp.choices else None))
        calls.append(rec)
        return resp

    Completions.create = create

    import bot
    from config import settings
    settings.LLM_MODEL = model
    settings.LLM_INTIMATE_MODEL = intimate
    settings.PHOTO_PROVIDER_MAINTENANCE = True
    logging.getLogger().setLevel(logging.INFO if os.environ.get("ARENA_VERBOSE") else logging.WARNING)

    real_sleep = asyncio.sleep

    async def fast_sleep(_delay=0, *a, **k):
        await real_sleep(0)

    class _Asyncio:
        sleep = staticmethod(fast_sleep)

        def __getattr__(self, name):
            return getattr(asyncio, name)

    bot.asyncio = _Asyncio()

    # Voz: nunca chamar o provedor real. O áudio entra na transcrição como texto.
    fake_audio = Path(db_path).with_suffix(".ogg")
    fake_audio.write_bytes(b"OggS")

    async def fake_synthesize(text, *a, **k):
        bubbles.append(f"[áudio] {text}")
        return fake_audio

    bot.voice_engine.synthesize = fake_synthesize
    bot.voice_engine.is_configured = lambda: True

    counter = iter(range(5000, 10**6))

    class FakeBot:
        async def send_message(self, **kw):
            bubbles.append(kw.get("text", ""))
            return SimpleNamespace(message_id=next(counter))

        def __getattr__(self, name):
            async def noop(*a, **k):
                return SimpleNamespace(message_id=next(counter), file_id="x")
            return noop

    chat = SimpleNamespace(id=settings.TARGET_CHAT_ID)
    context = SimpleNamespace(bot=FakeBot())
    turns_out = []

    async def drain():
        me = asyncio.current_task()
        pending = [t for t in asyncio.all_tasks() if t is not me]
        if pending:
            _done, rest = await asyncio.wait(pending, timeout=90)
            for task in rest:
                task.cancel()

    async def main():
        start = sc["inicio"]
        from datetime import timedelta
        for minutes, content in sc["turnos"]:
            clock.set(start + timedelta(minutes=minutes))
            bubbles.clear()
            n_calls = len(calls)
            mid = next(counter)
            t0 = time.perf_counter()
            error = None
            try:
                if isinstance(content, dict):
                    photo = SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace(
                        download_as_bytearray=AsyncMock(return_value=bytearray(b"img")))))
                    update = SimpleNamespace(effective_chat=chat, effective_user=chat,
                                             message=SimpleNamespace(message_id=mid, photo=[photo],
                                                                     caption=content["foto"],
                                                                     reply_to_message=None))
                    with patch.object(bot.vision_service, "analyze_image", AsyncMock(return_value={})), \
                         patch.object(bot.vision_service, "format_vision_context",
                                      return_value=f"[VISÃO] {content['visao']}"):
                        await bot.handle_photo_message(update, context)
                    user_text = f"[foto] {content['foto']}"
                else:
                    update = SimpleNamespace(effective_chat=chat, effective_user=chat,
                                             message=SimpleNamespace(message_id=mid, reply_to_message=None))
                    with patch.object(bot.availability_service, "evaluate_and_maybe_defer",
                                      return_value=("proceed", None, None)):
                        await bot.process_incoming_batch(update, context, content)
                    user_text = content
                await drain()
            except Exception as exc:
                import traceback
                error = f"{type(exc).__name__}: {exc} | {traceback.format_exc()[-600:]}"
                user_text = content if isinstance(content, str) else f"[foto] {content['foto']}"
            state = None
            try:
                with sqlite3.connect(db_path) as conn:
                    row = conn.execute("SELECT activity, location_region FROM world_state "
                                       "ORDER BY id DESC LIMIT 1").fetchone()
                state = f"{row[0]} @ {row[1]}" if row else None
            except Exception:
                pass
            turn_calls = calls[n_calls:]
            turns_out.append({"at": clock.now().strftime("%a %d/%m %H:%M"), "patrick": user_text,
                              "marina": list(bubbles), "error": error, "world": state,
                              "wall_s": round(time.perf_counter() - t0, 1), "calls": turn_calls})
            reply = " ⏎ ".join(bubbles) or f"(sem resposta{': ' + error if error else ''})"
            live(f"   {model.split('/')[-1]:<24} {scenario}#{rep}  P: {user_text[:50]}")
            live(f"   {'':<24} {'':<{len(scenario) + 3}} M: {reply[:160]}")

    asyncio.run(main())
    out.write_text(json.dumps({"model": model + (f"+{intimate}" if intimate else ""), "scenario": scenario,
                               "rep": rep, "reasoning": reasoning,
                               "turns": turns_out}, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- pai ------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=False)
    ap.add_argument("--scenarios", default="all")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--reasoning", default="off", help="off | minimal | low | medium")
    ap.add_argument("--run", default=time.strftime("%Y%m%d_%H%M%S"))
    ap.add_argument("--intimate", default="", help="modelos íntimos (Fase C.1), separados por vírgula")
    ap.add_argument("--child", nargs=7, metavar=("MODEL", "SCEN", "REP", "OUT", "DB", "REASONING", "INTIMATE"))
    args = ap.parse_args()

    if args.child:
        model, scen, rep, out, db, reasoning, intimate = args.child
        run_child(model, scen, int(rep), Path(out), Path(db), reasoning, "" if intimate == "-" else intimate)
        return 0

    from model_arena_scenarios import SCENARIOS
    scenarios = list(SCENARIOS) if args.scenarios == "all" else args.scenarios.split(",")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    run_dir = OUT_ROOT / args.run
    (run_dir / "db").mkdir(parents=True, exist_ok=True)
    snapshot = run_dir / "db" / "_snapshot.db"
    if not snapshot.exists():
        make_snapshot(snapshot)

    jobs = []
    intimates = [m.strip() for m in args.intimate.split(",") if m.strip()] or [""]
    for model in models:
        for intimate in intimates:
            for scen in scenarios:
                for rep in range(1, args.reps + 1):
                    tag = model.replace('/', '__') + (f"+{intimate.replace('/', '__')}" if intimate else "")
                    out = run_dir / f"{tag}__{scen}__{rep}.json"
                    if not out.exists():
                        jobs.append((model, intimate, scen, rep, out))
    live(f"=== ARENA {args.run}: {len(models)} modelos × {len(scenarios)} cenários × {args.reps} "
         f"= {len(jobs)} corridas (paralelo {args.parallel}) ===")

    def run(job):
        model, intimate, scen, rep, out = job
        db = run_dir / "db" / f"{out.stem}.db"
        db.write_bytes(snapshot.read_bytes())
        live(f"▶ {model}{' + ' + intimate if intimate else ''} · {scen}#{rep}")
        t0 = time.time()
        log = out.with_suffix(".log").open("w", encoding="utf-8")
        proc = subprocess.run([sys.executable, str(Path(__file__)), "--child", model, scen, str(rep),
                               str(out), str(db), args.reasoning, intimate or "-"],
                              cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=1800)
        log.close()
        db.unlink(missing_ok=True)
        db.with_suffix(".ogg").unlink(missing_ok=True)
        status = "ok" if proc.returncode == 0 and out.exists() else f"FALHOU rc={proc.returncode}"
        live(f"■ {model} · {scen}#{rep} — {status} em {time.time() - t0:.0f}s")

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        list(pool.map(run, jobs))
    live(f"=== ARENA {args.run} terminada — resultados em {run_dir.relative_to(ROOT)} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
