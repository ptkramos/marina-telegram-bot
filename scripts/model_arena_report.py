"""Relatório da arena de modelos: transcrições lado a lado + métricas objetivas.

python scripts/model_arena_report.py <run> [--transcripts] [--scenario X] [--model Y]
"""
import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "data" / "model_arena"

ASSISTANT_TICS = re.compile(r"\b(como posso ajudar|estou aqui para|fico feliz em|é importante|lembre-se|"
                            r"não hesite|qualquer coisa que precisar|sinto muito ouvir)\b", re.I)
NON_PT = re.compile(r"[Ѐ-ӿ一-鿿؀-ۿ]|\b(the|you|and|I'm|with)\b")


def load(run, scenario=None, model=None):
    rows = []
    for f in sorted((OUT_ROOT / run).glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if (scenario and d["scenario"] != scenario) or (model and model not in d["model"]):
            continue
        rows.append(d)
    return rows


def metrics(runs):
    by_model = defaultdict(lambda: defaultdict(list))
    for d in runs:
        m = by_model[d["model"]]
        for t in d["turns"]:
            text = " ".join(t["marina"])
            m["turns"].append(1)
            m["empty"].append(0 if text.strip() else 1)
            m["error"].append(1 if t["error"] else 0)
            m["chars"].append(len(text))
            m["bubbles"].append(len(t["marina"]))
            m["ends_q"].append(1 if text.rstrip(" 😊🥰😘💕❤️🤭😏😅🙈✨").endswith("?") else 0)
            m["tics"].append(1 if ASSISTANT_TICS.search(text) else 0)
            m["non_pt"].append(1 if NON_PT.search(text) else 0)
            m["wall"].append(t["wall_s"])
            for c in t["calls"]:
                m["cost"].append(c.get("cost") or 0)
                m["call_err"].append(1 if c.get("error") else 0)
                if c["caller"].startswith("bot.") and c.get("latency") is not None:
                    m["lat_bot"].append(c["latency"])
    table = []
    for model, m in by_model.items():
        n = len(m["turns"])
        table.append({
            "model": model, "turns": n,
            "sem_resposta%": round(100 * sum(m["empty"]) / n),
            "erro%": round(100 * sum(m["error"]) / n),
            "chars": round(statistics.mean(m["chars"])),
            "baloes": round(statistics.mean(m["bubbles"]), 1),
            "termina_?%": round(100 * sum(m["ends_q"]) / n),
            "tique_assist%": round(100 * sum(m["tics"]) / n),
            "outra_lingua%": round(100 * sum(m["non_pt"]) / n),
            "lat_resposta_s": round(statistics.median(m["lat_bot"]), 1) if m["lat_bot"] else None,
            "turno_s": round(statistics.median(m["wall"]), 1),
            "US$/turno": round(sum(m["cost"]) / n, 5),
            "falha_api": sum(m["call_err"]),
        })
    return sorted(table, key=lambda r: r["model"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--transcripts", action="store_true")
    ap.add_argument("--scenario")
    ap.add_argument("--model")
    a = ap.parse_args()
    runs = load(a.run, a.scenario, a.model)
    if a.transcripts:
        by_scen = defaultdict(list)
        for d in runs:
            by_scen[d["scenario"]].append(d)
        for scen, ds in by_scen.items():
            print(f"\n{'=' * 90}\nCENÁRIO {scen}\n{'=' * 90}")
            for i, turn in enumerate(ds[0]["turns"]):
                print(f"\n[{turn['at']}] PATRICK: {turn['patrick']}")
                for d in ds:
                    t = d["turns"][i] if i < len(d["turns"]) else None
                    txt = " ⏎ ".join(t["marina"]) if t else "-"
                    tag = f"{d['model'].split('/')[-1]}#{d['rep']}"
                    extra = f"  [ERRO {t['error'][:80]}]" if t and t["error"] else ""
                    print(f"  {tag:<28} {txt}{extra}")
    print()
    cols = ["model", "turns", "sem_resposta%", "erro%", "chars", "baloes", "termina_?%", "tique_assist%",
            "outra_lingua%", "lat_resposta_s", "turno_s", "US$/turno", "falha_api"]
    print(" | ".join(cols))
    for r in metrics(runs):
        print(" | ".join(str(r[c]) for c in cols))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
