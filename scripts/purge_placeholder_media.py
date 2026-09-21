"""Remove títulos-placeholder de mídia ("Filme de Romance") do banco real.

Contexto: em 20/09/2026 22:58 o LLM cadastrou um compromisso usando um título
genérico inventado ("Filme de Romance") em vez de um filme real. O Patch 021
adicionou HARD LINE contra inventar títulos e o Patch 023 criou o
MediaLookupService, mas nenhum dos dois remove o dado já persistido.

Enquanto o registro existir:
  * `eventos_pendentes.id=1` continua com status 'pending' (venceu 21/09 01:00
    e nunca fechou), então o CalendarWorld pode injetá-lo no prompt.
  * `world_state` guarda snapshots cuja `activity` é a concatenação suja
    "descrição | Follow-up: pergunta".
  * `conversas` guarda a fala original da Marina com o placeholder, que o
    retriever de memória pode trazer de volta e fazer ela repetir.

O script:
  1. Faz backup do .db em backups/.
  2. Marca eventos placeholder como 'cancelled' (não deleta — preserva trilha).
  3. Sanea `description` removendo "|" solto e sufixo "Follow-up:".
  4. Reescreve `world_state.activity` afetada para a forma limpa.
  5. Marca as conversas com placeholder para não voltarem via retriever.

Uso:
    python scripts/purge_placeholder_media.py           # dry-run
    python scripts/purge_placeholder_media.py --apply   # executa
"""
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "marin_memory.db"

# Títulos genéricos que o LLM inventa quando não sabe o nome real.
PLACEHOLDER_PATTERNS = (
    "filme de romance",
    "aquela série do netflix",
    "aquela serie do netflix",
    "filme de comédia",
    "filme de comedia",
    "filme de ação",
    "filme de acao",
    "série de suspense",
    "serie de suspense",
)


def _is_placeholder(text: str | None) -> bool:
    if not text:
        return False
    low = text.casefold()
    return any(p in low for p in PLACEHOLDER_PATTERNS)


# Título inventado → forma honesta, do jeito que a HARD LINE do Patch 021 manda
# ("ou pergunte ao Patrick, ou fale sem nome").
_HONEST_REPLACEMENT = "um filme que peguei aqui"
_PLACEHOLDER_TITLE_RE = re.compile(
    r"['\"“‘]?\s*(?:Filme de (?:Romance|Com[eé]dia|A[cç][aã]o)|"
    r"Aquela S[ée]rie do Netflix|S[ée]rie de Suspense)\s*['\"”’]?",
    re.IGNORECASE,
)


def _clean_activity(text: str) -> str:
    """Sanea `activity`/`description` de compromisso.

    Aqui a frase já traz o substantivo ("assistir ao filme X juntos"), então o
    título inventado é simplesmente removido — colocar "um filme que peguei
    aqui" produziria "assistir ao filme um filme que peguei aqui juntos".
    """
    cleaned = re.split(r"\s*\|\s*Follow-up:", text, maxsplit=1)[0]
    cleaned = _PLACEHOLDER_TITLE_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.rstrip(" |").strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove títulos-placeholder de mídia do banco real.")
    parser.add_argument("--apply", action="store_true",
                        help="Executa as escritas (sem a flag é dry-run).")
    args = parser.parse_args()

    if not DB.exists():
        print(f"[ERRO] Banco não encontrado em {DB}")
        return 1

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print("=" * 68)
    print("Purga de títulos-placeholder de mídia")
    print("=" * 68)
    print()

    # 1. Eventos pendentes.
    eventos = [
        r for r in conn.execute(
            "SELECT id, description, status, follow_up_prompt FROM eventos_pendentes"
        ).fetchall()
        if _is_placeholder(r["description"])
    ]
    print(f"eventos_pendentes com placeholder: {len(eventos)}")
    for r in eventos:
        novo = _clean_activity(r["description"] or "")
        print(f"  · id={r['id']} status={r['status']}")
        print(f"      description: {r['description']!r}")
        print(f"      -> cancelled, description={novo!r}")

    # 2. Snapshots de world_state.
    estados = [
        r for r in conn.execute(
            "SELECT id, activity FROM world_state"
        ).fetchall()
        if _is_placeholder(r["activity"])
    ]
    print()
    print(f"world_state com placeholder: {len(estados)}")
    for r in estados:
        print(f"  · id={r['id']} -> {_clean_activity(r['activity'] or '')!r}")

    # 3. Conversas.
    convs = [
        r for r in conn.execute(
            "SELECT id, role, content FROM conversas"
        ).fetchall()
        if _is_placeholder(r["content"])
    ]
    print()
    print(f"conversas com placeholder: {len(convs)}")
    for r in convs:
        print(f"  · id={r['id']} role={r['role']}: {(r['content'] or '')[:70]!r}")

    total = len(eventos) + len(estados) + len(convs)
    if total == 0:
        print()
        print(">>> Nada a fazer. Banco já está limpo.")
        conn.close()
        return 0

    if not args.apply:
        print()
        print(">>> DRY-RUN. Nada foi alterado.")
        print(">>> Para executar: python scripts/purge_placeholder_media.py --apply")
        conn.close()
        return 0

    # Backup antes de escrever.
    backups = ROOT / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backups / f"pre_placeholder_purge_{stamp}.db"
    conn.close()
    shutil.copy2(DB, backup_path)
    print()
    print(f"Backup em: {backup_path}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    now_iso = datetime.now().isoformat()

    for r in eventos:
        conn.execute(
            """UPDATE eventos_pendentes
               SET status='cancelled', cancelled_at=?, description=?,
                   follow_up_prompt=NULL
               WHERE id=?""",
            (now_iso, _clean_activity(r["description"] or ""), r["id"]),
        )

    for r in estados:
        conn.execute(
            "UPDATE world_state SET activity=? WHERE id=?",
            (_clean_activity(r["activity"] or ""), r["id"]),
        )

    # Conversas: substitui o título inventado por forma honesta, preservando
    # a estrutura da fala (o histórico continua legível, sem o placeholder).
    for r in convs:
        novo = _PLACEHOLDER_TITLE_RE.sub(_HONEST_REPLACEMENT, r["content"] or "")
        conn.execute("UPDATE conversas SET content=? WHERE id=?", (novo, r["id"]))

    conn.commit()
    conn.close()

    print(f"[OK] {len(eventos)} evento(s) cancelado(s), "
          f"{len(estados)} snapshot(s) saneado(s), "
          f"{len(convs)} conversa(s) reescrita(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
