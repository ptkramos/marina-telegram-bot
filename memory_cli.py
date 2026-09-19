"""
CLI de Auditoria e Gestão de Memória da Marina Salles (v3.7.0).
Permite que o Patrick (ou o assistente no IDE) visualize, audite e exporte
todos os dados salvos no SQLite de forma simples e legível.

Uso:
  python memory_cli.py stats          -> Resumo completo do banco de dados
  python memory_cli.py chat [N]       -> Exibe as últimas N mensagens trocadas
  python memory_cli.py facts          -> Exibe tudo o que ela lembra sobre o Patrick
  python memory_cli.py feedbacks      -> Lista feedbacks registrados
  python memory_cli.py export [md]    -> Exporta todo o banco para um relatório legível
"""
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from typing import Optional

from db import db_manager
from cycle import MenstrualCycleManager


def _age_from_birth_date(birth_date: Optional[str], *, ref: Optional[datetime] = None) -> str:
    """Derive age from birth_date; never invent a hardcoded annual fallback."""
    if not birth_date:
        return "unknown/not available"
    try:
        b = datetime.fromisoformat(str(birth_date)[:10]).date()
        today = (ref or datetime.now()).date()
        age = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
        return str(age)
    except Exception:
        return "unknown/not available"


def show_stats():
    total_msgs = db_manager.get_total_conversas()
    fatos = db_manager.get_fatos_patrick()
    perfil = db_manager.get_perfil()
    gostos = db_manager.get_gostos()
    feedbacks = db_manager.listar_feedbacks()
    data_ciclo = db_manager.get_data_inicio_ciclo()
    cycle_mgr = MenstrualCycleManager(data_ciclo)
    ciclo_info = cycle_mgr.get_cycle_info()

    total_gostos = sum(len(itens) for itens in gostos.values())
    birth = perfil.get("birth_date") or perfil.get("data_nascimento")
    if not birth:
        try:
            from world_repository import WorldBibleRepository
            marina = WorldBibleRepository(db_manager).get_character("marina") or {}
            birth = marina.get("birth_date")
        except Exception:
            birth = None
    age_label = _age_from_birth_date(birth)

    print("=" * 60)
    print("🌹 PAINEL DE MEMÓRIA DA MARINA SALLES (SQLite)")
    print("=" * 60)
    print(f"• Nome: {perfil.get('nome', 'Marina Salles')} ({age_label} anos)")
    print(f"• Namorado: {perfil.get('namorado', 'Patrick Ramos')}")
    print(f"• Banco de Dados: marin_memory.db ({db_manager.db_path.stat().st_size / 1024:.1f} KB)")
    print(f"• Fase do Ciclo: Dia {ciclo_info['day']} de 28 ({ciclo_info['name']})")
    print(f"• Total de Conversas Registradas: {total_msgs} mensagens")
    print(f"• Fatos que ela Lembra de Você: {len(fatos)} fatos")
    print(f"• Preferências e Gostos Próprios: {total_gostos} itens catalogados")
    print(f"• Feedbacks Salvos no Sistema: {len(feedbacks)} registros")
    print("=" * 60)

def show_chat(limit=10):
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, role, content, is_initiative FROM conversas ORDER BY id DESC LIMIT ?", (limit,))
        rows = list(reversed(cursor.fetchall()))
        
    print(f"\n💬 ÚLTIMAS {len(rows)} MENSAGENS (Histórico Permanente do SQLite):")
    print("-" * 60)
    for r in rows:
        hora = r["timestamp"][11:19] if len(r["timestamp"]) >= 19 else r["timestamp"]
        autor = "Marina 🌹" if r["role"] == "assistant" else "Patrick 👤"
        iniciativa = " [Iniciativa Própria]" if r["is_initiative"] else ""
        print(f"[{hora}] {autor}{iniciativa}:")
        for linha in r["content"].splitlines():
            print(f"   {linha}")
        print()
    print("-" * 60)

def show_facts():
    fatos = db_manager.get_fatos_patrick()
    print(f"\n🧠 O QUE A MARINA GUARDA NA LEMBRANÇA SOBRE O PATRICK ({len(fatos)} itens):")
    print("-" * 60)
    for i, f in enumerate(fatos, 1):
        print(f" {i}. {f}")
    print("-" * 60)

def show_feedbacks():
    fbs = db_manager.listar_feedbacks()
    print(f"\n🛠️ CENTRAL DE FEEDBACKS ({len(fbs)} registros salvos):")
    print("-" * 60)
    for fb in fbs:
        print(f"• [{fb['id']}] {fb['timestamp'][:16]} - Autor: {fb['autor']} ({fb['status'].upper()})")
        print(f"  Observação: {fb['feedback']}")
        if fb.get("contexto_recente"):
            print(f"  Contexto salvo: {len(fb['contexto_recente'])} falas anexadas")
        print()
    print("-" * 60)

def export_dump():
    export_file = BASE_DIR / "relatorio_memoria_marina.md"
    perfil = db_manager.get_perfil()
    fatos = db_manager.get_fatos_patrick()
    gostos = db_manager.get_gostos()
    
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, role, content FROM conversas ORDER BY id ASC")
        mensagens = cursor.fetchall()

    md = []
    md.append(f"# 🌹 Relatório Completo de Memória — Marina Salles")
    md.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}\n")
    birth = perfil.get("birth_date") or perfil.get("data_nascimento")
    if not birth:
        try:
            from world_repository import WorldBibleRepository
            marina_char = WorldBibleRepository(db_manager).get_character("marina") or {}
            birth = marina_char.get("birth_date")
        except Exception:
            birth = None
    age_label = _age_from_birth_date(birth)
    md.append(f"## 1. Perfil\n- Nome: {perfil.get('nome')}\n- Namorado: {perfil.get('namorado')}\n- Idade: {age_label}\n")
    md.append(f"## 2. Fatos que Lembra do Patrick")
    for f in fatos:
        md.append(f"- {f}")
    md.append("\n## 3. Gostos & Estilo")
    for cat, itens in gostos.items():
        md.append(f"- **{cat.replace('_', ' ').capitalize()}**: {', '.join(itens)}")
    md.append(f"\n## 4. Histórico Completo ({len(mensagens)} mensagens)")
    for m in mensagens:
        autor = "Marina" if m["role"] == "assistant" else "Patrick"
        md.append(f"**[{m['timestamp'][:19]}] {autor}:** {m['content']}\n")
    
    export_file.write_text("\n".join(md), encoding="utf-8")
    print(f"Relatório exportado com sucesso para: {export_file}")

def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "stats"
    
    if cmd == "stats":
        show_stats()
    elif cmd == "chat":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 10
        show_chat(limit)
    elif cmd == "facts":
        show_facts()
    elif cmd == "feedbacks":
        show_feedbacks()
    elif cmd in ("export", "dump"):
        export_dump()
    else:
        print("Comando não reconhecido. Use: stats, chat, facts, feedbacks ou export.")

if __name__ == "__main__":
    main()
