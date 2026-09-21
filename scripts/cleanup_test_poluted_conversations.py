"""Remove pares de conversa inseridos por test_context_builder no banco de produção.

Contexto (Patch 018): antes do fix, `tests/test_context_builder.py` usava o
`memory_manager` global sem tempfile isolado. Rodar essa suíte pelo menos 6
vezes durante o soak 19-20/09/2026 inseriu 6 pares idênticos de fixture:

    role=user       content="Boa noite vida"
    role=assistant  content="Boa noite meu amor!"

Este script:
  1. Faz backup do banco (marin_memory.db → backups/pre_patch018_cleanup_*.db)
  2. Confere que os IDs alvos existem E que o conteúdo bate exatamente
  3. Deleta apenas essas linhas (transação única, rollback em erro)
  4. Confirma o estado final

Uso:
    python scripts/cleanup_test_poluted_conversations.py           # dry-run
    python scripts/cleanup_test_poluted_conversations.py --apply   # executa

Idempotente: se rodado de novo, encontra 0 linhas para deletar e sai limpo.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import db_manager  # noqa: E402


# IDs inspecionados manualmente em 20/09/2026 antes do fix.
# Cada tupla é (id, role_esperada, content_esperado).
POISONED = (
    (38, "user",      "Boa noite vida"),
    (39, "assistant", "Boa noite meu amor!"),
    (56, "user",      "Boa noite vida"),
    (57, "assistant", "Boa noite meu amor!"),
    (77, "user",      "Boa noite vida"),
    (78, "assistant", "Boa noite meu amor!"),
    (79, "user",      "Boa noite vida"),
    (80, "assistant", "Boa noite meu amor!"),
    (81, "user",      "Boa noite vida"),
    (82, "assistant", "Boa noite meu amor!"),
    (83, "user",      "Boa noite vida"),
    (84, "assistant", "Boa noite meu amor!"),
)


def _backup(source: Path) -> Path:
    backups_dir = ROOT / "backups"
    backups_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backups_dir / f"pre_patch018_cleanup_{stamp}.db"
    shutil.copy2(source, target)
    return target


def _identify() -> list[tuple[int, str, str]]:
    """Retorna a lista de IDs cujo conteúdo bate exatamente com o esperado."""
    to_delete = []
    with db_manager.get_connection() as conn:
        for _id, expected_role, expected_content in POISONED:
            row = conn.execute(
                "SELECT id, role, content, timestamp FROM conversas WHERE id=?",
                (_id,),
            ).fetchone()
            if row is None:
                print(f"  id={_id}: ausente (já limpo ou nunca existiu) — pulando")
                continue
            if row["role"] != expected_role or row["content"] != expected_content:
                print(f"  id={_id}: DIVERGÊNCIA — role={row['role']!r} content={row['content'][:60]!r}; PULANDO")
                continue
            to_delete.append((_id, row["role"], row["content"]))
            print(f"  id={_id}: {row['timestamp']}  {row['role']:9s}  {row['content']}")
    return to_delete


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpa pares de fixture do banco de produção.")
    parser.add_argument("--apply", action="store_true",
                        help="Executa o DELETE (sem essa flag, é dry-run).")
    args = parser.parse_args()

    print("=" * 70)
    print("Patch 018 — limpeza de fixtures de test_context_builder")
    print("=" * 70)
    print()
    print("Linhas identificadas para deleção:")
    print()

    to_delete = _identify()

    if not to_delete:
        print()
        print("Nada para deletar — banco já limpo.")
        return 0

    print()
    print(f"Total: {len(to_delete)} linhas")

    if not args.apply:
        print()
        print(">>> DRY-RUN. Passe --apply para executar.")
        print(">>> Exemplo: python scripts/cleanup_test_poluted_conversations.py --apply")
        return 0

    # Backup
    db_path = ROOT / "marin_memory.db"
    if not db_path.exists():
        print(f"[ERRO] Banco {db_path} não encontrado.")
        return 1
    backup_path = _backup(db_path)
    print()
    print(f"Backup criado em: {backup_path}")

    # Executa em transação
    print()
    print("Executando DELETE...")
    with db_manager.get_connection() as conn:
        try:
            for _id, _role, _content in to_delete:
                conn.execute("DELETE FROM conversas WHERE id=?", (_id,))
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[ERRO] Rollback executado: {exc}")
            return 2

    # Verifica
    with db_manager.get_connection() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM conversas WHERE content IN ('Boa noite vida','Boa noite meu amor!')"
        ).fetchone()[0]
    print(f"[OK] Deleção concluída. Linhas restantes com esses conteúdos: {remaining}")
    if remaining > 0:
        print("[AVISO] Ainda restam — pode haver mensagens legítimas do Patrick com esse texto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
