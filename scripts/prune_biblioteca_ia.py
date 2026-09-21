"""Poda os registros 16-50 da BIBLIOTECA_COMPORTAMENTAL_MARINA.md.

Contexto: os registros 16-50 foram gerados por outra IA como bootstrap
inicial da biblioteca. O Patrick avaliou 21/09/2026 02:22 que a qualidade
não é boa suficiente para servir de few-shot e autorizou remoção.

O script:
    1. Faz backup do .md em data/feedback/backups/.
    2. Preserva registros 1-15 (revisados manualmente pelo Patrick) e 51+ (novo
       padrão pós-conversa comigo).
    3. Renumera os registros preservados sequencialmente (16, 17, 18...).
    4. Reescreve o arquivo.

Idempotente: rodar de novo em cima do arquivo já podado não muda nada
significativo (só faz backup redundante).

Uso:
    python scripts/prune_biblioteca_ia.py           # dry-run (mostra o que faria)
    python scripts/prune_biblioteca_ia.py --apply   # executa
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIBLIOTECA = ROOT / "data" / "feedback" / "BIBLIOTECA_COMPORTAMENTAL_MARINA.md"


def _split_records(text: str) -> tuple[str, list[tuple[int, str]]]:
    """Devolve (cabeçalho_antes_do_primeiro_registro, [(número, corpo)])."""
    header_re = re.compile(r"^##\s+Registro\s+(\d+)(.*)$", re.MULTILINE)
    matches = list(header_re.finditer(text))
    if not matches:
        return text, []
    prelude = text[: matches[0].start()]
    records: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        num = int(m.group(1))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        records.append((num, body))
    return prelude, records


def main() -> int:
    parser = argparse.ArgumentParser(description="Poda registros 16-50 da biblioteca comportamental.")
    parser.add_argument("--apply", action="store_true",
                        help="Executa o corte (sem essa flag é dry-run).")
    args = parser.parse_args()

    if not BIBLIOTECA.exists():
        print(f"[ERRO] Biblioteca não encontrada em {BIBLIOTECA}")
        return 1

    text = BIBLIOTECA.read_text(encoding="utf-8")
    prelude, records = _split_records(text)

    print("=" * 70)
    print("Poda de registros 16-50 (bootstrap de IA)")
    print("=" * 70)
    print()

    manter: list[tuple[int, str]] = []
    remover: list[tuple[int, str]] = []
    for num, body in records:
        title_m = re.search(r"^##\s+Registro\s+\d+(.*)$", body, flags=re.MULTILINE)
        title = title_m.group(1).strip(" —-") if title_m else ""
        if 16 <= num <= 50:
            remover.append((num, title))
        else:
            manter.append((num, body))

    print(f"REGISTROS ATUAIS: {len(records)}")
    print(f"  Preservar (1-15 + 51+): {len(manter)}")
    print(f"  Remover (16-50):        {len(remover)}")
    print()
    if remover:
        print("Registros que serão removidos:")
        for num, title in remover:
            print(f"  · Registro {num:03d} — {title[:60]}")
        print()

    # Após remoção: renumera 51+ para começar em 16 sequencialmente.
    new_records: list[tuple[int, str]] = []
    next_num = 1
    for _old_num, body in manter:
        # Substitui o header pelo novo número.
        new_header = f"## Registro {next_num:03d}"
        body_new = re.sub(r"^##\s+Registro\s+\d+", new_header, body, count=1, flags=re.MULTILINE)
        new_records.append((next_num, body_new))
        next_num += 1

    print(f"APÓS RENUMERAÇÃO: registros passam a ir de 001 a {next_num - 1:03d}")

    if not args.apply:
        print()
        print(">>> DRY-RUN. Nada foi alterado.")
        print(">>> Para executar: python scripts/prune_biblioteca_ia.py --apply")
        return 0

    # Backup.
    backups = ROOT / "data" / "feedback" / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backups / f"biblioteca_pre_prune_{stamp}.md"
    shutil.copy2(BIBLIOTECA, backup_path)
    print()
    print(f"Backup em: {backup_path}")

    # Reconstrói o arquivo.
    parts = [prelude.rstrip()]
    for _num, body in new_records:
        parts.append(body.rstrip())
    new_text = "\n\n".join(p for p in parts if p) + "\n"
    BIBLIOTECA.write_text(new_text, encoding="utf-8")

    print(f"[OK] Biblioteca reescrita: {len(new_records)} registros, numerados de 001 a {next_num - 1:03d}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
