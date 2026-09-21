"""Export recent Telegram conversation to a plain-text file for triage.

Reads the last session (or a window / count of messages) from `conversas` and
dumps a timestamped transcript that Patrick can paste back to Claude without
hand-copying prints. Also dumps the WorldState resolved and the last
availability decisions for cross-reference.

Sessions (Patch 018): a session is a contiguous run of messages with no gap
larger than `--session-gap-minutes` (default 45). This matches the human
notion of "the conversation I just had". By default the script exports **only
the most recent session** — much less noise than dumping 48h. Use
`--all-sessions` for the historical view.

Model attribution (Patch 018): each Marina turn prints the LLM model that
generated it, when known. Rows persisted before the migration show `-`.

Usage:
    python scripts/export_conversation_history.py                 # last session
    python scripts/export_conversation_history.py --hours 12      # last 12h
    python scripts/export_conversation_history.py --last 100      # last N msgs
    python scripts/export_conversation_history.py --all-sessions  # every session
    python scripts/export_conversation_history.py --session-gap-minutes 30

Output goes to `scratchpad/conversation_export_<timestamp>.txt`.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import db_manager  # noqa: E402


def _row_keys(row) -> set[str]:
    try:
        return set(row.keys())
    except Exception:
        return set()


def _format_row(row) -> str:
    ts = row["timestamp"] if "timestamp" in _row_keys(row) else "?"
    role = row["role"] if "role" in _row_keys(row) else "?"
    content = (row["content"] or "").rstrip()
    tag = "PATRICK" if role == "user" else ("MARINA" if role == "assistant" else role.upper())
    model = ""
    if role == "assistant" and "model" in _row_keys(row):
        model_val = row["model"] or ""
        model = f"  [model: {model_val}]" if model_val else "  [model: -]"
    return f"[{ts}] {tag}:{model}\n{content}\n"


def _fetch_all_rows() -> list:
    with db_manager.get_connection() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(conversas)").fetchall()}
        has_model = "model" in cols
        select = "SELECT id, timestamp, role, content" + (", model" if has_model else "") + " FROM conversas"
        return conn.execute(f"{select} ORDER BY id ASC").fetchall()


def _fetch_by_window(hours: int) -> list:
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with db_manager.get_connection() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(conversas)").fetchall()}
        has_model = "model" in cols
        select = "SELECT id, timestamp, role, content" + (", model" if has_model else "") + " FROM conversas"
        return conn.execute(
            f"{select} WHERE timestamp >= ? ORDER BY id ASC", (cutoff,)
        ).fetchall()


def _fetch_last_n(n: int) -> list:
    with db_manager.get_connection() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(conversas)").fetchall()}
        has_model = "model" in cols
        select = "SELECT id, timestamp, role, content" + (", model" if has_model else "") + " FROM conversas"
        rows = conn.execute(
            f"{select} ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return list(reversed(rows))


def _split_sessions(rows: list, gap_minutes: int) -> list[list]:
    """Split a chronologically-ordered list of rows into sessions. A new session
    starts when the gap between consecutive `timestamp` values exceeds
    `gap_minutes`."""
    if not rows:
        return []
    sessions: list[list] = [[rows[0]]]
    threshold = timedelta(minutes=gap_minutes)
    prev_ts = None
    try:
        prev_ts = datetime.fromisoformat(rows[0]["timestamp"])
    except Exception:
        prev_ts = None
    for row in rows[1:]:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
        except Exception:
            ts = None
        if prev_ts is not None and ts is not None and (ts - prev_ts) > threshold:
            sessions.append([])
        sessions[-1].append(row)
        if ts is not None:
            prev_ts = ts
    return sessions


def _dump_worldstate_recent() -> str:
    """Snapshot of the last few world_state resolutions for cross-reference."""
    try:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT observed_at, activity, location_place_id, "
                "location_region, energy_level, source_json "
                "FROM world_state ORDER BY id DESC LIMIT 10"
            ).fetchall()
    except Exception as exc:
        return f"(world_state indisponível: {exc})\n"
    if not rows:
        return "(sem resoluções recentes de world_state)\n"
    lines = ["--- Últimas 10 resoluções de WorldState (mais recente primeiro) ---"]
    for r in rows:
        loc = r["location_region"] or f"place_id={r['location_place_id']}"
        lines.append(f"  {r['observed_at']}  activity={r['activity']}  "
                     f"loc={loc}  energy={r['energy_level']:.2f}  "
                     f"source={r['source_json']}")
    return "\n".join(lines) + "\n"


def _dump_sleep_and_availability() -> str:
    """Snapshot recent availability decisions for cross-reference."""
    try:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT timestamp, decision, reason_code, urgency, "
                "activity_type, activity_source, pending_message_count, "
                "urgent_override "
                "FROM response_availability_events "
                "ORDER BY id DESC LIMIT 20"
            ).fetchall()
    except Exception as exc:
        return f"(response_availability_events indisponível: {exc})\n"
    if not rows:
        return "(sem eventos recentes de availability)\n"
    lines = ["--- Últimos 20 eventos de Response Availability ---"]
    for r in rows:
        override = " [URGENT_OVERRIDE]" if r["urgent_override"] else ""
        lines.append(
            f"  {r['timestamp']}  {r['decision']:8s}  "
            f"reason={r['reason_code']}  urg={r['urgency']}  "
            f"activity={r['activity_type']}({r['activity_source']})  "
            f"pending={r['pending_message_count']}{override}"
        )
    return "\n".join(lines) + "\n"


def _dump_model_summary(sessions: list[list]) -> str:
    """Table of Marina models used in each session, most recent last."""
    if not sessions:
        return ""
    lines = ["--- Modelos LLM usados por sessão (mais recente por último) ---"]
    for i, session in enumerate(sessions, start=1):
        if not session:
            continue
        first_ts = session[0]["timestamp"]
        last_ts = session[-1]["timestamp"]
        models: dict[str, int] = {}
        for row in session:
            if row["role"] == "assistant" and "model" in _row_keys(row):
                m = row["model"] or "-"
                models[m] = models.get(m, 0) + 1
        model_str = ", ".join(f"{m}×{c}" for m, c in sorted(models.items(), key=lambda kv: -kv[1]))
        if not model_str:
            model_str = "(sem respostas da Marina)"
        lines.append(f"  #{i}  {first_ts} → {last_ts}  ({len(session)} msgs)  models: {model_str}")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="Exporta conversa recente para debug")
    p.add_argument("--hours", type=int, default=None,
                   help="Janela em horas (ignora --last e --all-sessions).")
    p.add_argument("--last", type=int, default=None,
                   help="Últimos N turnos (ignora --all-sessions).")
    p.add_argument("--all-sessions", action="store_true",
                   help="Exporta todas as sessões, não só a mais recente.")
    p.add_argument("--session-gap-minutes", type=int, default=45,
                   help="Gap (min) entre mensagens que separa uma sessão da próxima. Default 45.")
    args = p.parse_args()

    if args.last is not None:
        rows = _fetch_last_n(args.last)
        label = f"últimos {args.last} turnos"
    elif args.hours is not None:
        rows = _fetch_by_window(args.hours)
        label = f"últimas {args.hours} horas"
    else:
        rows = _fetch_all_rows()
        label = "sessão mais recente" if not args.all_sessions else "todas as sessões"

    sessions_all = _split_sessions(rows, gap_minutes=args.session_gap_minutes)

    if args.hours is None and args.last is None and not args.all_sessions and sessions_all:
        sessions_to_dump = [sessions_all[-1]]
        rows = sessions_all[-1]
    else:
        sessions_to_dump = sessions_all

    out_dir = ROOT / "scratchpad"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"conversation_export_{stamp}.txt"

    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# Marina — export de conversa ({label})\n")
        f.write(f"# Gerado em {datetime.now().isoformat()}\n")
        f.write(f"# Total de linhas: {len(rows)}\n")
        f.write(f"# Sessões incluídas: {len(sessions_to_dump)} de {len(sessions_all)} total no banco\n")
        f.write(f"# Gap para separar sessões: {args.session_gap_minutes} min\n\n")
        f.write(_dump_worldstate_recent())
        f.write("\n")
        f.write(_dump_sleep_and_availability())
        f.write("\n")
        f.write(_dump_model_summary(sessions_all))
        f.write("\n")
        f.write("=" * 70 + "\n")
        f.write("CONVERSA\n")
        f.write("=" * 70 + "\n\n")
        for i, session in enumerate(sessions_to_dump, start=1):
            if len(sessions_to_dump) > 1:
                first_ts = session[0]["timestamp"] if session else "?"
                last_ts = session[-1]["timestamp"] if session else "?"
                f.write(f"\n--- Sessão #{i} ({first_ts} → {last_ts}) ---\n\n")
            for row in session:
                f.write(_format_row(row))
                f.write("\n")

    print(f"OK: exportado {len(rows)} turnos em {len(sessions_to_dump)} sessão(ões) para")
    print(f"  {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
