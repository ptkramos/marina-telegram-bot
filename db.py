"""
Módulo de Banco de Dados Relacional SQLite para Marina Seltin (v1.3.0).
Gerencia a persistência definitiva e exclusiva em marin_memory.db:
- Histórico completo de conversas (sem limites)
- Fatos e memórias sobre o Patrick
- Gostos pessoais e descobertas da Marina
- Perfil e estado biológico (ciclo menstrual)
- Feedbacks e auto-correções
- Estilo linguístico e sincronia do casal
Sistema 100% autônomo sem dependência de arquivos JSON.
"""
import sqlite3
import json
import logging
from contextlib import closing
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("MarinaDB")

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "marin_memory.db"
MIGRATIONS_DIR = BASE_DIR / "migrations"

class _ManagedConnection:
    """Wrapper para sqlite3.Connection que garante commit/rollback e fecha a conexão no __exit__."""
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __enter__(self):
        self._conn.__enter__()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._conn.__exit__(exc_type, exc_val, exc_tb)
        finally:
            try:
                self._conn.close()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


class DatabaseManager:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self._init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return _ManagedConnection(conn)

    def _init_db(self):
        is_new = not self.db_path.exists()
        
        # Configura WAL mode persistente
        with closing(sqlite3.connect(self.db_path, timeout=5.0)) as raw_conn:
            raw_conn.execute("PRAGMA journal_mode=WAL;")

        # Executa migrações estruturadas
        self._run_migrations()

        if is_new:
            logger.info("Banco SQLite criado com sucesso! Inicializando dados padrão...")
            self._seed_default_profile()

    def _run_migrations(self):
        """Aplica migrações pendentes em ordem sequencial com registro em schema_version."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """)
            conn.commit()

            cursor.execute("SELECT version FROM schema_version;")
            applied_versions = {row["version"] for row in cursor.fetchall()}

            if not MIGRATIONS_DIR.exists():
                return

            migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            for mig_file in migration_files:
                parts = mig_file.stem.split("_", 1)
                try:
                    version_num = int(parts[0])
                    mig_name = parts[1] if len(parts) > 1 else mig_file.stem
                except ValueError:
                    continue

                if version_num not in applied_versions:
                    logger.info(f"Aplicando migration {version_num}: {mig_name}...")
                    sql_content = mig_file.read_text(encoding="utf-8")
                    cursor.executescript(sql_content)
                    now_iso = datetime.now().isoformat()
                    cursor.execute(
                        "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?);",
                        (version_num, mig_name, now_iso)
                    )
                    conn.commit()
                    logger.info(f"Migration {version_num} aplicada com sucesso.")

    def get_schema_version(self) -> int:
        """Retorna a versão mais recente do schema aplicada no banco."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT MAX(version) AS max_v FROM schema_version;").fetchone()
            return row["max_v"] if row and row["max_v"] is not None else 0

    def _seed_default_profile(self):
        """Inicializa os dados padrão da Marina caso o banco seja criado do zero."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            perfil_base = {
                "nome": "Marina Seltin",
                "idade": "19",
                "ocupacao": "Modelo fotográfica e comercial em início de carreira",
                "moradia": "Mora sozinha em seu apartamento",
                "namorado": "Patrick Ramos",
                "status_relacionamento": "Namorando recentemente, descobrindo o dia a dia juntos com muito amor e paixão",
                "habitos": "Acorda 8h~10h com preguiça gostosa na cama, treina quando dá vontade, dorme tarde. Adora mandar selfies e fotos de looks/biquínis e fotos íntimas pro Patrick.",
                "comportamento_sono": "Costuma ir dormir quando o Patrick vai, mas com frequência fica manhosa pedindo pra ele ficar mais 5 minutinhos ou mandando foto dengosa."
            }
            for k, v in perfil_base.items():
                cursor.execute("INSERT OR REPLACE INTO perfil (chave, valor) VALUES (?, ?)", (k, v))
                
            cursor.execute("INSERT OR REPLACE INTO ciclo_biologico (id, data_inicio_ciclo, updated_at) VALUES (1, '2026-09-02', ?)", (now_iso,))
            
            fatos_base = [
                "Nome: Patrick Ramos",
                "Começou a namorar comigo recentemente",
                "Trabalha e tem sua rotina corrida",
                "Me apoia e gosta do meu jeito fofo e do meu corpo"
            ]
            for f in fatos_base:
                cursor.execute("INSERT OR IGNORE INTO fatos_patrick (fato, created_at) VALUES (?, ?)", (f, now_iso))
                
            cursor.execute("INSERT OR IGNORE INTO momentos_marcantes (momento, created_at) VALUES ('O começo do nosso namoro e a cumplicidade que estamos construindo', ?)", (now_iso,))
            
            gostos_base = {
                "musica": ["The Weeknd", "Billie Eilish", "Pop moderno", "R&B gostosinho", "ouvir som no talo enquanto se arruma"],
                "estilo_e_moda": ["Looks confortáveis no apê", "Biquínis ousados", "Peças minimalistas elegantes", "Maquiagem glow bem natural"],
                "coisas_que_ama": ["Gatinhos fofos", "Cafuné demorado", "Comer brigadeiro de colher", "Ver o Patrick concentrado nas coisas dele"],
                "coisas_que_acha_estranhas_ou_dificeis": ["Jogos de videogame extremamente difíceis/estressantes", "Gente formal demais"]
            }
            for cat, itens in gostos_base.items():
                for it in itens:
                    cursor.execute("INSERT OR IGNORE INTO gostos_marina (categoria, item, created_at) VALUES (?, ?, ?)", (cat, it, now_iso))
                    
            conn.commit()

    # --- MÉTODOS DE CONVERSAS & CURSOR DE CONSOLIDAÇÃO ---

    def adicionar_mensagem(self, role: str, content: str, is_initiative: bool = False, media_type: str = "text", timestamp: Optional[str] = None) -> int:
        now_iso = timestamp or datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversas (timestamp, role, content, is_initiative, media_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now_iso, role, content, 1 if is_initiative else 0, media_type)
            )
            conn.commit()
            return cursor.lastrowid

    def registrar_iniciativa_marina(self, texto: str, media_type: str = "text") -> int:
        """Registra mensagem autônoma da Marina sem criar balão falso de usuário."""
        return self.adicionar_mensagem(
            role="assistant",
            content=texto,
            is_initiative=True,
            media_type=media_type
        )

    def get_mensagens_recentes(self, limit: int = 12) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, role, content FROM conversas
                ORDER BY id DESC LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            return [{"id": r["id"], "role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def get_conversas_desde(self, since_id: int = 0, limit: int = 50) -> list[dict]:
        """Retorna todas as conversas registradas após um ID para consolidação contínua em lote."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, timestamp, role, content, is_initiative, media_type
                FROM conversas
                WHERE id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (since_id, limit)
            )
            return [dict(r) for r in cursor.fetchall()]

    def contar_conversas_desde(self, since_id: int = 0) -> int:
        """Retorna a quantidade de novas mensagens ainda não consolidadas desde o cursor."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM conversas WHERE id > ?", (since_id,))
            row = cursor.fetchone()
            return row["total"] if row else 0

    def get_last_consolidated_conversation_id(self) -> int:
        """Retorna o cursor da última conversa consolidada pelo Memory Consolidator."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM estado_relacional WHERE chave = 'last_consolidated_conversation_id'")
            row = cursor.fetchone()
            if row and row["valor"]:
                try:
                    return int(row["valor"])
                except ValueError:
                    return 0
            return 0

    def set_last_consolidated_conversation_id(self, last_id: int):
        """Atualiza persistentemente o cursor da última conversa consolidada."""
        self.set_estado_relacional("last_consolidated_conversation_id", str(last_id))

    def get_total_conversas(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM conversas")
            return cursor.fetchone()["total"]

    def limpar_historico_conversas(self):
        """Limpa todo o histórico de conversas para iniciar do zero."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversas")
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='conversas'")
            except Exception:
                pass
            conn.commit()

    # --- MÉTODOS DE FATOS & MEMÓRIA AFETIVA ---

    def adicionar_fato_patrick(
        self,
        fato: str,
        category: str = "geral",
        importance: float = 0.5,
        confidence: float = 1.0,
        source_conversation_id: int = None,
        supersedes_id: int = None,
        memory_tier: str = "standard",
        volatility: str = "medium",
        canonical_key: str = None
    ) -> int:
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO fatos_patrick
                (fato, created_at, category, importance, confidence, active, source_conversation_id, supersedes_id, memory_tier, volatility, canonical_key, last_confirmed_at, confirmation_count)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 0)
                """,
                (fato, now_iso, category, importance, confidence, source_conversation_id, supersedes_id, memory_tier, volatility, canonical_key, now_iso)
            )
            conn.commit()
            return cursor.lastrowid if cursor.rowcount > 0 else 0

    def get_fatos_patrick(self, active_only: bool = True) -> list[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT fato FROM fatos_patrick"
            if active_only:
                query += " WHERE active = 1"
            query += " ORDER BY id ASC"
            cursor.execute(query)
            return [r["fato"] for r in cursor.fetchall()]

    def get_fatos_patrick_detalhados(self, active_only: bool = True) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
            SELECT id, fato, category, importance, confidence, created_at, updated_at,
                   access_count, active, supersedes_id, source_conversation_id, memory_tier,
                   volatility, canonical_key, last_confirmed_at, confirmation_count
            FROM fatos_patrick
            """
            if active_only:
                query += " WHERE active = 1"
            query += " ORDER BY importance DESC, id ASC"
            cursor.execute(query)
            return [dict(r) for r in cursor.fetchall()]

    def get_fato_detalhado(self, fato_id: int, active_only: bool = True) -> Optional[dict]:
        """Recupera um fato específico com todos os seus metadados."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
            SELECT id, fato, category, importance, confidence, created_at, updated_at,
                   access_count, active, supersedes_id, source_conversation_id, memory_tier,
                   volatility, canonical_key, last_confirmed_at, confirmation_count
            FROM fatos_patrick
            WHERE id = ?
            """
            if active_only:
                query += " AND active = 1"
            cursor.execute(query, (fato_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_memory_fallback_candidates(self, limit: int = 20) -> list[dict]:
        """Retorna pool limitado de memórias ativas ordenadas por relevância permanente para o Retriever."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, fato, category, importance, confidence, created_at, updated_at,
                       access_count, active, supersedes_id, source_conversation_id, memory_tier,
                       volatility, canonical_key, last_confirmed_at, confirmation_count
                FROM fatos_patrick
                WHERE active = 1
                ORDER BY importance DESC, confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_core_memories(self, limit: int = 5) -> list[dict]:
        """Retorna memórias centrais e estáveis (tier 'core') para o Context Builder."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, fato, category, importance, confidence, memory_tier, volatility,
                       canonical_key, source_conversation_id, last_confirmed_at
                FROM fatos_patrick
                WHERE active = 1 AND memory_tier = 'core'
                ORDER BY importance DESC, confidence DESC, id ASC
                LIMIT ?
                """,
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def confirmar_fato(self, fato_id: int) -> bool:
        """Incrementa confirmação e confiança de um fato ativo reafirmado pelo Patrick."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE fatos_patrick
                SET confirmation_count = confirmation_count + 1,
                    confidence = MIN(1.0, confidence + 0.1),
                    last_confirmed_at = ?,
                    updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (now_iso, now_iso, fato_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def substituir_fato_atomicamente(
        self,
        existing_fact_id: int,
        new_fact_data: dict
    ) -> Optional[int]:
        """
        Substitui atomicamente um fato antigo por um novo em uma única transação SQLite.
        Garante que a versão anterior só é inativada se o novo fato for inserido com sucesso.
        Se ocorrer qualquer erro (ex: constraint UNIQUE ou falha de dados), faz ROLLBACK
        e preserva o fato antigo intacto e ativo.
        """
        if not existing_fact_id or not new_fact_data:
            return None

        novo_fato = str(new_fact_data.get("fato", "")).strip()
        if not novo_fato:
            return None

        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor()
                # 1. Verifica se o fato antigo existe e está ativo
                cursor.execute(
                    "SELECT id, fato, canonical_key FROM fatos_patrick WHERE id = ? AND active = 1",
                    (existing_fact_id,)
                )
                old_row = cursor.fetchone()
                if not old_row:
                    logger.warning(f"substituir_fato_atomicamente: Fato {existing_fact_id} não encontrado ou já inativo.")
                    return None

                # Se o novo fato tiver o texto exatamente idêntico ao antigo ativo:
                # Trata como confirmação segura (same) em vez de replacement com conflito UNIQUE
                if old_row["fato"].strip() == novo_fato:
                    cursor.execute(
                        """
                        UPDATE fatos_patrick
                        SET confirmation_count = confirmation_count + 1,
                            confidence = MIN(1.0, confidence + 0.1),
                            last_confirmed_at = ?,
                            updated_at = ?
                        WHERE id = ? AND active = 1
                        """,
                        (now_iso, now_iso, existing_fact_id)
                    )
                    conn.commit()
                    return existing_fact_id

                # 2. Insere novo fato apontando supersedes_id para o antigo
                cursor.execute(
                    """
                    INSERT INTO fatos_patrick
                    (fato, created_at, category, importance, confidence, active,
                     source_conversation_id, supersedes_id, memory_tier, volatility,
                     canonical_key, last_confirmed_at, confirmation_count)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        novo_fato,
                        now_iso,
                        new_fact_data.get("category", "geral"),
                        float(new_fact_data.get("importance", 0.5)),
                        float(new_fact_data.get("confidence", 1.0)),
                        new_fact_data.get("source_conversation_id"),
                        existing_fact_id,
                        new_fact_data.get("memory_tier", "standard"),
                        new_fact_data.get("volatility", "medium"),
                        new_fact_data.get("canonical_key") or old_row["canonical_key"],
                        now_iso
                    )
                )
                new_id = cursor.lastrowid

                # 3. Inativa a versão antiga
                cursor.execute(
                    "UPDATE fatos_patrick SET active = 0, updated_at = ? WHERE id = ? AND active = 1",
                    (now_iso, existing_fact_id)
                )

                # 4. Confirma a transação inteira atomicamente
                conn.commit()
                return new_id
            except Exception as e:
                conn.rollback()
                logger.error(f"Erro em substituir_fato_atomicamente (rollback realizado): {e}")
                return None

    def desativar_fato(self, fato_id: int):
        """Desativa um fato antigo contradito ou substituído."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE fatos_patrick SET active = 0, updated_at = ? WHERE id = ?",
                (now_iso, fato_id)
            )
            conn.commit()

    def desativar_fato_por_chave(self, canonical_key: str) -> int:
        """Desativa fatos ativos associados a uma chave canônica específica (ex: revogação explícita)."""
        if not canonical_key:
            return 0
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE fatos_patrick SET active = 0, updated_at = ? WHERE canonical_key = ? AND active = 1",
                (now_iso, canonical_key)
            )
            conn.commit()
            return cursor.rowcount

    def get_fatos_por_chave(self, canonical_key: str, active_only: bool = True) -> list[dict]:
        """Recupera fatos por chave canônica."""
        if not canonical_key:
            return []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            q = "SELECT * FROM fatos_patrick WHERE canonical_key = ?"
            if active_only:
                q += " AND active = 1"
            cursor.execute(q, (canonical_key,))
            return [dict(r) for r in cursor.fetchall()]

    def registrar_acesso_fato(self, fato_id: int):
        """Atualiza contador de acesso e data do último uso da memória."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE fatos_patrick SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
                (now_iso, fato_id)
            )
            conn.commit()

    def adicionar_momento_marcante(
        self,
        momento: str,
        importance: float = 0.8,
        source_conversation_id: int = None
    ) -> int:
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO momentos_marcantes
                (momento, created_at, importance, active, source_conversation_id)
                VALUES (?, ?, ?, 1, ?)
                """,
                (momento, now_iso, importance, source_conversation_id)
            )
            conn.commit()
            return cursor.lastrowid

    def get_momentos_marcantes(self, active_only: bool = True) -> list[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT momento FROM momentos_marcantes"
            if active_only:
                query += " WHERE active = 1"
            query += " ORDER BY id ASC"
            cursor.execute(query)
            return [r["momento"] for r in cursor.fetchall()]

    # --- MÉTODOS DE RESUMOS DE CONVERSA ---

    def salvar_resumo_conversa(
        self,
        topic: str,
        summary: str,
        start_conversation_id: int = None,
        end_conversation_id: int = None,
        importance: float = 0.5
    ) -> int:
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO resumos_conversa
                (topic, summary, start_conversation_id, end_conversation_id, importance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (topic, summary, start_conversation_id, end_conversation_id, importance, now_iso, now_iso)
            )
            conn.commit()
            return cursor.lastrowid

    def get_resumos_conversa(self, limit: int = 5) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, topic, summary, start_conversation_id, end_conversation_id, importance, created_at
                FROM resumos_conversa
                ORDER BY id DESC LIMIT ?
                """,
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    # --- MÉTODOS DE BUSCA TEXTUAL FTS5 (SMART RETRIEVAL) ---

    def buscar_fatos_fts(self, termo: str, limit: int = 5) -> list[dict]:
        """Busca rápida por palavras-chave em fatos com SQLite FTS5."""
        if not termo or not termo.strip():
            return []
        termo_limpo = termo.strip().replace('"', '""')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT f.id, f.fato, f.category, f.importance, f.confidence,
                           f.memory_tier, f.volatility, f.canonical_key, f.last_confirmed_at,
                           f.confirmation_count, f.access_count, fts.rank
                    FROM fatos_fts fts
                    JOIN fatos_patrick f ON f.id = fts.rowid
                    WHERE fatos_fts MATCH ? AND f.active = 1
                    ORDER BY rank, f.importance DESC
                    LIMIT ?
                    """,
                    (f'"{termo_limpo}"', limit)
                )
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                logger.warning(f"Aviso na busca FTS de fatos para '{termo}': {e}")
                return []

    def buscar_momentos_fts(self, termo: str, limit: int = 3) -> list[dict]:
        """Busca por palavras-chave em momentos marcantes com SQLite FTS5."""
        if not termo or not termo.strip():
            return []
        termo_limpo = termo.strip().replace('"', '""')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT m.id, m.momento, m.importance, fts.rank
                    FROM momentos_fts fts
                    JOIN momentos_marcantes m ON m.id = fts.rowid
                    WHERE momentos_fts MATCH ? AND m.active = 1
                    ORDER BY rank, m.importance DESC
                    LIMIT ?
                    """,
                    (f'"{termo_limpo}"', limit)
                )
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                logger.warning(f"Aviso na busca FTS de momentos para '{termo}': {e}")
                return []

    def buscar_resumos_fts(self, termo: str, limit: int = 2) -> list[dict]:
        """Busca por palavras-chave em tópicos e resumos de conversas anteriores com SQLite FTS5."""
        if not termo or not termo.strip():
            return []
        termo_limpo = termo.strip().replace('"', '""')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT r.id, r.topic, r.summary, r.importance, fts.rank
                    FROM resumos_fts fts
                    JOIN resumos_conversa r ON r.id = fts.rowid
                    WHERE resumos_fts MATCH ?
                    ORDER BY rank, r.importance DESC
                    LIMIT ?
                    """,
                    (f'"{termo_limpo}"', limit)
                )
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                logger.warning(f"Aviso na busca FTS de resumos para '{termo}': {e}")
                return []

    def get_gostos(self) -> dict[str, list[str]]:
        gostos = {}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT categoria, item FROM gostos_marina ORDER BY id ASC")
            for r in cursor.fetchall():
                cat = r["categoria"]
                item = r["item"]
                if cat not in gostos:
                    gostos[cat] = []
                gostos[cat].append(item)
        return gostos

    def adicionar_gosto(self, categoria: str, item: str):
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO gostos_marina (categoria, item, created_at) VALUES (?, ?, ?)",
                (categoria, item, now_iso)
            )
            conn.commit()

    # --- MÉTODOS DE PERFIL & CICLO ---

    def get_perfil(self) -> dict[str, str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chave, valor FROM perfil")
            return {r["chave"]: r["valor"] for r in cursor.fetchall()}

    def get_data_inicio_ciclo(self) -> str:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_inicio_ciclo FROM ciclo_biologico WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return row["data_inicio_ciclo"]
            default_date = (date.today() - timedelta(days=12)).strftime("%Y-%m-%d")
            cursor.execute(
                "INSERT OR REPLACE INTO ciclo_biologico (id, data_inicio_ciclo, updated_at) VALUES (1, ?, ?)",
                (default_date, datetime.now().isoformat())
            )
            conn.commit()
            return default_date

    def set_data_inicio_ciclo(self, data_str: str):
        """Define e persiste com segurança a data de início do ciclo menstrual."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO ciclo_biologico (id, data_inicio_ciclo, updated_at) VALUES (1, ?, ?)",
                (data_str, datetime.now().isoformat())
            )
            conn.commit()

    # --- MÉTODOS DE FEEDBACK ---

    def salvar_feedback(self, feedback_id: str, feedback_texto: str, autor: str = "Patrick Ramos", contexto: list = None) -> dict:
        now_iso = datetime.now().isoformat()
        ctx_str = json.dumps(contexto or [], ensure_ascii=False)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO feedbacks (id, timestamp, autor, feedback, contexto_recente, status)
                VALUES (?, ?, ?, ?, ?, 'pendente')
                """,
                (feedback_id, now_iso, autor, feedback_texto, ctx_str)
            )
            conn.commit()
        return {
            "id": feedback_id,
            "timestamp": now_iso,
            "autor": autor,
            "feedback": feedback_texto,
            "status": "pendente"
        }

    def listar_feedbacks(self, status: str = None) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM feedbacks WHERE status = ? ORDER BY timestamp DESC", (status,))
            else:
                cursor.execute("SELECT * FROM feedbacks ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            result = []
            for r in rows:
                result.append({
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "autor": r["autor"],
                    "feedback": r["feedback"],
                    "contexto_recente": json.loads(r["contexto_recente"]) if r["contexto_recente"] else [],
                    "status": r["status"]
                })
            return result

    def atualizar_status_feedback(self, feedback_id: str, status: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE feedbacks SET status = ? WHERE id = ?",
                (status, feedback_id)
            )
            conn.commit()

    # --- MÉTODOS DE ESTILO LINGUÍSTICO & ESPELHAMENTO ---

    def salvar_estilo(self, chave: str, valor: str, exemplos: any = None):
        now_iso = datetime.now().isoformat()
        payload = [] if exemplos is None else exemplos
        ex_str = json.dumps(payload, ensure_ascii=False)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO estilo_linguagem (chave, valor, exemplos, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (chave, valor, ex_str, now_iso)
            )
            conn.commit()

    def get_estilo(self) -> dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chave, valor, exemplos FROM estilo_linguagem")
            rows = cursor.fetchall()
            result = {}
            for r in rows:
                result[r["chave"]] = {
                    "valor": r["valor"],
                    "exemplos": json.loads(r["exemplos"]) if r["exemplos"] else []
                }
            return result

    def adicionar_licao_linguagem(self, licao: str):
        """Salva uma regra/correção ensinada pelo Patrick para a Marina nunca mais errar."""
        estilo = self.get_estilo()
        existentes = estilo.get("licoes_aprendidas", {}).get("exemplos", [])
        if licao not in existentes:
            existentes.append(licao)
            self.salvar_estilo("licoes_aprendidas", ", ".join(existentes), existentes)

    def get_licoes_linguagem(self) -> list[str]:
        """Retorna a lista de correções aprendidas com o Patrick."""
        estilo = self.get_estilo()
        return estilo.get("licoes_aprendidas", {}).get("exemplos", [])

    # --- MÉTODOS DE EVENTOS PENDENTES (FOLLOW-UPS) ---

    def adicionar_evento_pendente(
        self,
        event_type: str,
        description: str,
        event_at: Optional[str] = None,
        follow_up_after: Optional[str] = None,
        importance: float = 0.5,
        source_conversation_id: Optional[int] = None
    ) -> int:
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO eventos_pendentes
                (event_type, description, event_at, follow_up_after, status, importance, source_conversation_id, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (event_type, description, event_at, follow_up_after, importance, source_conversation_id, now_iso)
            )
            conn.commit()
            return cursor.lastrowid

    def get_eventos_pendentes_para_followup(self, now_iso: Optional[str] = None) -> list[dict]:
        """Retorna eventos cujo horário de follow-up ou do evento já venceu."""
        check_time = now_iso or datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, event_type, description, event_at, follow_up_after, importance, source_conversation_id, created_at
                FROM eventos_pendentes
                WHERE status = 'pending' AND (
                    (follow_up_after IS NOT NULL AND follow_up_after <= ?) OR
                    (follow_up_after IS NULL AND event_at IS NOT NULL AND event_at <= ?)
                )
                ORDER BY importance DESC, id ASC
                """,
                (check_time, check_time)
            )
            return [dict(r) for r in cursor.fetchall()]

    def concluir_evento_pendente(self, event_id: int):
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE eventos_pendentes SET status = 'completed', completed_at = ? WHERE id = ?",
                (now_iso, event_id)
            )
            conn.commit()

    def listar_eventos_pendentes(self, status: str = "pending", limit: int = 10) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM eventos_pendentes WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit)
            )
            return [dict(r) for r in cursor.fetchall()]

    # --- MÉTODOS DE ESTADO RELACIONAL ---

    def get_estado_relacional(self) -> dict[str, str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chave, valor FROM estado_relacional")
            return {r["chave"]: r["valor"] for r in cursor.fetchall()}

    def set_estado_relacional(self, chave: str, valor: str):
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO estado_relacional (chave, valor, updated_at) VALUES (?, ?, ?)",
                (chave, valor, now_iso)
            )
            conn.commit()

    # --- MÉTODOS DE ESTADO EMOCIONAL COM CLAMP & DECAY ---

    def get_estado_emocional(self) -> dict[str, dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chave, valor, baseline, updated_at FROM estado_emocional")
            return {
                r["chave"]: {
                    "valor": float(r["valor"]),
                    "baseline": float(r["baseline"]),
                    "updated_at": r["updated_at"]
                }
                for r in cursor.fetchall()
            }

    def ajustar_emocao(self, chave: str, delta: float):
        """Ajusta uma dimensão emocional com limite rigoroso entre 0.0 e 1.0 (clamp)."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor, baseline FROM estado_emocional WHERE chave = ?", (chave,))
            row = cursor.fetchone()
            if row:
                novo_valor = max(0.0, min(1.0, float(row["valor"]) + delta))
                cursor.execute(
                    "UPDATE estado_emocional SET valor = ?, updated_at = ? WHERE chave = ?",
                    (round(novo_valor, 3), now_iso, chave)
                )
            else:
                novo_valor = max(0.0, min(1.0, 0.75 + delta))
                cursor.execute(
                    "INSERT INTO estado_emocional (chave, valor, baseline, updated_at) VALUES (?, ?, 0.75, ?)",
                    (chave, round(novo_valor, 3), now_iso)
                )
            conn.commit()

    def aplicar_decay_emocional(self, taxa: float = 0.10):
        """Aproxima gradualmente os estados emocionais em direção aos seus baselines naturais."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chave, valor, baseline FROM estado_emocional")
            rows = cursor.fetchall()
            for r in rows:
                val = float(r["valor"])
                base = float(r["baseline"])
                novo_val = max(0.0, min(1.0, val + (base - val) * taxa))
                cursor.execute(
                    "UPDATE estado_emocional SET valor = ?, updated_at = ? WHERE chave = ?",
                    (round(novo_val, 3), now_iso, r["chave"])
                )
    # --- MÉTODOS DE HISTÓRICO DE PATCHES (AUTO-PATCHER v3.4) ---

    def registrar_patch(
        self,
        patch_id: str,
        autor: str,
        instruction: str,
        target_files: list[str],
        diff_content: str,
        status: str = "applied"
    ) -> int:
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO patch_history (
                    patch_id, autor, instruction, target_files, diff_content, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                patch_id,
                autor,
                instruction,
                json.dumps(target_files, ensure_ascii=False),
                diff_content,
                status,
                now_iso
            ))
            conn.commit()
            return cursor.lastrowid

    def atualizar_status_patch(self, patch_id: str, status: str, reverted_at: Optional[str] = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if reverted_at:
                cursor.execute(
                    "UPDATE patch_history SET status = ?, reverted_at = ? WHERE patch_id = ?",
                    (status, reverted_at, patch_id)
                )
            else:
                cursor.execute(
                    "UPDATE patch_history SET status = ? WHERE patch_id = ?",
                    (status, patch_id)
                )
            conn.commit()

    def get_patch_history(self, limit: int = 10) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, patch_id, autor, instruction, target_files, diff_content, status, created_at, reverted_at
                FROM patch_history
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "patch_id": r["patch_id"],
                    "autor": r["autor"],
                    "instruction": r["instruction"],
                    "target_files": json.loads(r["target_files"]) if r["target_files"] else [],
                    "diff_content": r["diff_content"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "reverted_at": r["reverted_at"]
                }
                for r in rows
            ]

    def get_patch_by_id(self, patch_id: str) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, patch_id, autor, instruction, target_files, diff_content, status, created_at, reverted_at
                FROM patch_history
                WHERE patch_id = ?
            """, (patch_id,))
            r = cursor.fetchone()
            if not r:
                return None
            return {
                "id": r["id"],
                "patch_id": r["patch_id"],
                "autor": r["autor"],
                "instruction": r["instruction"],
                "target_files": json.loads(r["target_files"]) if r["target_files"] else [],
                "diff_content": r["diff_content"],
                "status": r["status"],
                "created_at": r["created_at"],
                "reverted_at": r["reverted_at"]
            }

    def get_last_applied_patch(self) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, patch_id, autor, instruction, target_files, diff_content, status, created_at, reverted_at
                FROM patch_history
                WHERE status = 'applied'
                ORDER BY id DESC
                LIMIT 1
            """)
            r = cursor.fetchone()
            if not r:
                return None
            return {
                "id": r["id"],
                "patch_id": r["patch_id"],
                "autor": r["autor"],
                "instruction": r["instruction"],
                "target_files": json.loads(r["target_files"]) if r["target_files"] else [],
                "diff_content": r["diff_content"],
                "status": r["status"],
                "created_at": r["created_at"],
                "reverted_at": r["reverted_at"]
            }

db_manager = DatabaseManager()

