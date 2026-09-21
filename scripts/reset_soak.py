"""Reset completo do soak — banco zerado, canon preservado.

Chama `DatabaseManager.reset_soak_learning()`, que deleta em transação única:
    - conversas, resumos, momentos, estilo, gostos, fatos_patrick
    - eventos_pendentes, reminders, open_loops, feedbacks
    - pending_batches, availability_events
    - relationship_culture(_evidence), knowledge_shares/subjects/items
    - preference_evidence, social_evidence/place_state
    - life_events(_archive), story_threads, world_state, world_hygiene_log
    - world_decisions, real_context_cache, estado_relacional
    - mundo vivo (Auditoria #8): NPCs e lugares de ficção descobertos,
      marcas do dia social em world_bootstrap, convivência com o círculo
      canônico volta ao ponto de partida

E preserva (deixados intactos):
    - Persona canônica (world_characters, world_places, world_bootstrap)
    - Grade da PUC (academic_profile, academic_courses, academic_schedule_blocks)
    - Perfil da Marina (perfil, ciclo_biologico); avatar e DNA visual ficam no código
    - Rotinas (routine_patterns), schema_version, migrations aplicadas

Ao final:
    - Cria 'Nome: Patrick Ramos' em fatos_patrick (seed mínimo)
    - Reinsere baseline em estado_relacional (nickname, closeness, topic)
    - Zera estado_emocional para os valores baseline

Faz backup do banco antes de qualquer coisa, dry-run por padrão.

Uso:
    python scripts/reset_soak.py             # dry-run (mostra o que faria)
    python scripts/reset_soak.py --apply     # executa
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


def _snapshot_counts() -> dict[str, int]:
    """Contagem por tabela antes do reset — pra mostrar o que vai limpar."""
    tables = (
        "conversas", "fatos_patrick", "momentos_marcantes", "resumos_conversa",
        "estilo_linguagem", "gostos_marina", "eventos_pendentes", "reminders",
        "open_loops", "feedbacks", "response_pending_batches",
        "response_availability_events", "world_state", "estado_relacional",
        "story_threads", "life_events", "knowledge_subjects", "knowledge_items",
        "relationship_culture", "preference_evidence", "social_evidence",
    )
    counts: dict[str, int] = {}
    with db_manager.get_connection() as conn:
        for t in tables:
            try:
                counts[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except Exception:
                counts[t] = -1
        # Auditoria #8: o mundo vivo (#6) mora em tabelas que também guardam
        # o cânone; o reset remove só a parte que nasceu no soak.
        extras = {
            "mundo vivo: NPCs descobertos": "SELECT COUNT(*) FROM world_characters WHERE canonical_key LIKE 'npc!_%' ESCAPE '!'",
            "mundo vivo: lugares de ficção descobertos": "SELECT COUNT(*) FROM world_places WHERE canon_locked=0 AND json_extract(usage_rules_json,'$.internal_fiction')=1",
            "mundo vivo: marcas (início, histórias, pulos)": "SELECT COUNT(*) FROM world_bootstrap WHERE key='social_day_start' OR key LIKE 'skip:%' OR key LIKE 'story_day:%' OR key LIKE 'canonized:%'",
        }
        for label, sql in extras.items():
            try:
                counts[label] = conn.execute(sql).fetchone()[0]
            except Exception:
                counts[label] = -1
    return counts


def _print_counts(counts: dict[str, int], header: str) -> None:
    print(header)
    for t, c in sorted(counts.items()):
        marker = "  " if c > 0 else "· "
        note = " (tabela ausente)" if c < 0 else ""
        print(f"  {marker}{t:40s} {max(c, 0):6d}{note}")


def _preserved_summary() -> dict[str, int]:
    # Auditoria #8: "calendar_events" e "avatar_atual" não existem neste
    # schema e apareciam como "(ausente)", sugerindo perda de dados. O avatar e
    # o DNA visual moram no código (visual_profile.py); a grade, nas academic_*.
    tables = ("world_characters", "world_places", "world_bootstrap",
              "academic_profile", "academic_courses", "academic_schedule_blocks",
              "routine_patterns", "perfil", "ciclo_biologico",
              "social_relationships", "character_preferences")
    counts: dict[str, int] = {}
    with db_manager.get_connection() as conn:
        for t in tables:
            try:
                counts[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except Exception:
                counts[t] = -1
    return counts


def _backup() -> Path:
    """Cópia consistente do banco antes do reset."""
    source = ROOT / "marin_memory.db"
    if not source.exists():
        raise SystemExit(f"[ERRO] banco não encontrado em {source}")
    backups = ROOT / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backups / f"pre_soak_reset_{stamp}.db"
    shutil.copy2(source, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset completo do soak preservando canon.")
    parser.add_argument("--apply", action="store_true",
                        help="Executa o reset (sem essa flag é dry-run).")
    args = parser.parse_args()

    print("=" * 70)
    print("RESET SOAK — banco zerado, canon preservado")
    print("=" * 70)
    print()

    before = _snapshot_counts()
    _print_counts(before, "Estado ATUAL (será deletado no reset):")

    preserved = _preserved_summary()
    print()
    print("Estado PRESERVADO (fica intacto após reset):")
    for t, c in sorted(preserved.items()):
        note = " (ausente)" if c < 0 else ""
        print(f"  · {t:40s} {max(c, 0):6d}{note}")

    total_to_clear = sum(max(c, 0) for c in before.values())
    print()
    print(f"Total de linhas a serem removidas: {total_to_clear}")

    if not args.apply:
        print()
        print(">>> DRY-RUN. Nada foi alterado.")
        print(">>> Para executar de fato: python scripts/reset_soak.py --apply")
        return 0

    print()
    print("Executando backup do banco...")
    backup_path = _backup()
    print(f"  backup em {backup_path}")

    print()
    print("Executando reset_soak_learning()...")
    counts = db_manager.reset_soak_learning()

    print()
    print("Linhas removidas por tabela:")
    for t, c in sorted(counts.items()):
        if c:
            print(f"  {t:40s} {c:6d}")

    after = _snapshot_counts()
    residual = {t: c for t, c in after.items() if c > 0}
    print()
    if residual:
        print("Linhas remanescentes (esperadas: fatos_patrick=1, estado_relacional=3):")
        for t, c in sorted(residual.items()):
            print(f"  {t:40s} {c:6d}")
    else:
        print("Nenhuma linha remanescente nas tabelas dinâmicas.")

    print()
    print("[OK] Reset completo. Reinicie o bot para o novo soak zerado.")
    print(f"[INFO] Backup preservado em {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
