"""
Módulo de Banco de Dados Relacional SQLite para Marina Salles (v3.7.0).
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
import os
from contextlib import closing, contextmanager
from threading import local
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger("MarinaDB")

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = Path(os.environ["MARINA_DB_PATH"]).expanduser().resolve() if os.environ.get("MARINA_DB_PATH") else BASE_DIR / "marin_memory.db"
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


class _TransactionConnection:
    """Empresta a conexão do lote sem permitir commits parciais."""
    def __init__(self, conn):
        self.conn = conn
        self.failed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.failed = True

    def commit(self):
        pass

    def rollback(self):
        self.failed = True

    def __getattr__(self, name):
        return getattr(self.conn, name)


class DatabaseManager:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self._transaction_state = local()
        self._init_db()

    def get_connection(self):
        active = getattr(self._transaction_state, "connection", None)
        if active is not None:
            return active
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return _ManagedConnection(conn)

    @contextmanager
    def transaction(self):
        """Uma transação por lote, isolada por thread; métodos existentes a reutilizam."""
        if getattr(self._transaction_state, "connection", None) is not None:
            raise RuntimeError("Transação de memória aninhada não suportada")
        with self.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            borrowed = _TransactionConnection(conn)
            self._transaction_state.connection = borrowed
            try:
                yield
                if borrowed.failed:
                    raise RuntimeError("Uma operação do lote solicitou rollback")
            finally:
                del self._transaction_state.connection

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
                    try:
                        cursor.executescript(sql_content)
                    except sqlite3.OperationalError as e:
                        # Synthetic upgrades may replay an ADD COLUMN migration
                        # after its columns already landed (a downgrade that
                        # clears schema_version without dropping the table).
                        # The recovery stays scoped to migrations and columns
                        # listed here — never blanket-applied — so a genuine
                        # schema error still fails loudly.
                        # Patch 032 added 018: the test that rolls back to
                        # schema 8 keeps `conversas` intact, so replaying the
                        # migration hit "duplicate column name: model".
                        replayable = {
                            12: ('eventos_pendentes', {
                                'owner_character_key', 'end_at', 'location_key',
                                'source_key', 'story_thread_id', 'confirmed',
                                'metadata_json',
                            }),
                            18: ('conversas', {'model'}),
                        }
                        target = replayable.get(version_num)
                        if target is None or "duplicate column name" not in str(e).lower():
                            raise
                        table_name, known_columns = target
                        expected_alter = ['alter', 'table', table_name, 'add', 'column']
                        for fragment in sql_content.split(";"):
                            statement = '\n'.join(line for line in fragment.splitlines()
                                                  if not line.lstrip().startswith('--')).strip()
                            if not statement:
                                continue
                            try:
                                cursor.execute(statement)
                            except sqlite3.OperationalError as stmt_err:
                                tokens = statement.lower().split()
                                known_alter = (len(tokens) >= 6
                                               and tokens[:5] == expected_alter
                                               and tokens[5] in known_columns)
                                if not (known_alter and "duplicate column name" in str(stmt_err).lower()):
                                    raise
                        actual_columns = {row['name'] for row in cursor.execute(
                            f'PRAGMA table_info({table_name})').fetchall()}
                        if not known_columns <= actual_columns:
                            raise RuntimeError(
                                f'Migration {version_num} left required columns '
                                f'missing on {table_name}')
                    now_iso = datetime.now().isoformat()
                    cursor.execute(
                        "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?);",
                        (version_num, mig_name, now_iso)
                    )
                    conn.commit()
                    logger.info(f"Migration {version_num} aplicada com sucesso.")

            # Garante colunas de robustez mesmo se migrations já foram executadas
            try:
                cursor.execute("ALTER TABLE fatos_patrick ADD COLUMN last_decay_at TEXT;")
                conn.commit()
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE reminders ADD COLUMN offer_message_id INTEGER;")
                conn.commit()
            except Exception:
                pass
            try:
                cursor.execute("""
                DELETE FROM resumos_conversa
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM resumos_conversa
                    GROUP BY start_conversation_id, end_conversation_id
                ) AND start_conversation_id IS NOT NULL AND end_conversation_id IS NOT NULL;
                """)
                cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_resumos_intervalo
                ON resumos_conversa(start_conversation_id, end_conversation_id)
                WHERE start_conversation_id IS NOT NULL AND end_conversation_id IS NOT NULL;
                """)
                conn.commit()
            except Exception as e:
                logger.warning(f"Erro ao verificar/criar idx_resumos_intervalo: {e}")

    def get_schema_version(self) -> int:
        """Retorna a versão mais recente do schema aplicada no banco."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT MAX(version) AS max_v FROM schema_version;").fetchone()
            return row["max_v"] if row and row["max_v"] is not None else 0

    def _seed_default_profile(self):
        """Schema-required neutral defaults only — World Bible owns canon autobiography."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            perfil_base = {
                "nome": "Marina Salles",
                "namorado": "Patrick Ramos",
                "status_relacionamento": "Namorando Patrick Ramos",
            }
            for k, v in perfil_base.items():
                cursor.execute(
                    "INSERT OR IGNORE INTO perfil (chave, valor) VALUES (?, ?)", (k, v))
            cursor.execute(
                "INSERT OR IGNORE INTO ciclo_biologico (id, data_inicio_ciclo, updated_at) VALUES (1, '2026-09-02', ?)",
                (now_iso,),
            )
            # Auditoria #2: o seed criava a identidade do Patrick com o tier
            # default ('standard'). Nome próprio é o caso mais óbvio de core
            # memory — é o fato que a Marina deve ter presente em qualquer
            # conversa, e o retriever carrega cores independentemente de
            # palavra-chave. Sem isso o banco nascia sem nenhuma core memory.
            cursor.execute(
                """INSERT OR IGNORE INTO fatos_patrick
                   (fato, created_at, category, importance, confidence,
                    memory_tier, volatility, canonical_key, last_confirmed_at)
                   VALUES (?, ?, 'pessoal', 1.0, 1.0, 'core', 'stable',
                           'nome_patrick', ?)""",
                ("Nome: Patrick Ramos", now_iso, now_iso),
            )
            conn.commit()

    # --- MÉTODOS DE CONVERSAS & CURSOR DE CONSOLIDAÇÃO ---

    def adicionar_mensagem(self, role: str, content: str, is_initiative: bool = False, media_type: str = "text", timestamp: Optional[str] = None, model: Optional[str] = None) -> int:
        """Persist a chat turn. `model` is only stored for assistant turns and
        records which LLM produced the text (Patch 018 — auditoria de modelo).
        """
        now_iso = timestamp or datetime.now().isoformat()
        model_value = model if role == "assistant" else None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversas (timestamp, role, content, is_initiative, media_type, model)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now_iso, role, content, 1 if is_initiative else 0, media_type, model_value)
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

    def criar_backup(self, prefixo: str = "manual") -> Path:
        """Cria uma cópia SQLite consistente antes de operações destrutivas."""
        backup_dir = self.db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        safe_prefix = "".join(c for c in prefixo if c.isalnum() or c in "_-") or "manual"
        destino = backup_dir / f"{safe_prefix}_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
        with closing(sqlite3.connect(self.db_path, timeout=10.0)) as origem, \
             closing(sqlite3.connect(destino)) as copia:
            origem.execute("PRAGMA busy_timeout=10000")
            origem.backup(copia)
            check = copia.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise RuntimeError(f"Backup SQLite inválido: {check}")
        return destino

    def reset_soak_learning(self) -> dict:
        """Zera aprendizado e estado narrativo, preservando persona e mundo canônicos."""
        dynamic_tables = (
            "response_pending_batch_items",
            "response_pending_batches",
            "response_availability_events",
            "relationship_culture_evidence",
            "relationship_culture",
            "knowledge_shares",
            "knowledge_subject_aliases",
            "knowledge_subjects",
            "knowledge_items",
            "reminders",
            "eventos_pendentes",
            "open_loops",
            "preference_evidence",
            "social_evidence",
            "social_place_state",
            "world_hygiene_log",
            "world_decisions",
            "life_events_archive",
            "life_events",
            "story_threads",
            "world_state",
            "feedbacks",
            "estilo_linguagem",
            "gostos_marina",
            "resumos_conversa",
            "momentos_marcantes",
            "fatos_patrick",
            "conversas",
            "real_context_cache",
            "estado_relacional",
        )
        counts = {}
        now_iso = datetime.now().isoformat()
        with self.transaction():
            with self.get_connection() as conn:
                for table in dynamic_tables:
                    counts[table] = conn.execute(f'DELETE FROM "{table}"').rowcount
                # Auditoria #2: mesmo seed do _init_db — a identidade nasce como
                # core memory, não 'standard'.
                conn.execute(
                    """INSERT INTO fatos_patrick
                       (fato, created_at, category, importance, confidence,
                        memory_tier, volatility, canonical_key, last_confirmed_at)
                       VALUES (?, ?, 'pessoal', 1.0, 1.0, 'core', 'stable',
                               'nome_patrick', ?)""",
                    ("Nome: Patrick Ramos", now_iso, now_iso),
                )
                conn.executemany(
                    "INSERT INTO estado_relacional (chave, valor, updated_at) VALUES (?, ?, ?)",
                    (
                        ("current_nickname", "amor", now_iso),
                        ("closeness_level", "intimo", now_iso),
                        ("current_shared_topic", "dia a dia e planos juntos", now_iso),
                    ),
                )
                conn.execute(
                    "UPDATE estado_emocional SET valor=baseline, updated_at=?", (now_iso,)
                )
                placeholders = ",".join("?" for _ in dynamic_tables)
                conn.execute(
                    f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
                    dynamic_tables,
                )
        return counts

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
                   volatility, canonical_key, last_confirmed_at, confirmation_count,
                   needs_reconfirmation, last_decay_at
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
                       canonical_key, source_conversation_id, last_confirmed_at,
                       created_at, updated_at, access_count, active, confirmation_count, supersedes_id
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
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
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
        start_conversation_id: Optional[int] = None,
        end_conversation_id: Optional[int] = None,
        importance: float = 0.6
    ) -> Optional[int]:
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
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
            except sqlite3.IntegrityError as ie:
                if "UNIQUE constraint failed" in str(ie):
                    logger.warning(
                        f"Resumo para intervalo {start_conversation_id}-{end_conversation_id} já existe no banco; inserção ignorada."
                    )
                    return None
                raise

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
                           f.confirmation_count, f.access_count, f.created_at, f.updated_at,
                           f.source_conversation_id, f.active, f.supersedes_id, fts.rank
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
        source_conversation_id: Optional[int] = None,
        follow_up_prompt: Optional[str] = None,
        end_at: Optional[str] = None,
        owner_character_key: str = "patrick_ramos",
        location_key: Optional[str] = None,
        confirmed: int = 0,
        metadata_json: Optional[str] = None
    ) -> int:
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO eventos_pendentes
                (event_type, description, event_at, follow_up_after, status, importance, source_conversation_id, created_at, follow_up_prompt, end_at, owner_character_key, location_key, confirmed, metadata_json)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_type, description, event_at, follow_up_after, importance, source_conversation_id, now_iso, follow_up_prompt, end_at, owner_character_key, location_key, confirmed, metadata_json)
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
                SELECT id, event_type, description, event_at, follow_up_after, importance, source_conversation_id, created_at, follow_up_prompt
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

    def cancelar_evento_pendente(self, event_id: int) -> bool:
        """Cancela um evento pendente e cancela automaticamente quaisquer reminders atrelados a ele."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE eventos_pendentes SET status = 'cancelled', cancelled_at = ? WHERE id = ? AND status = 'pending'",
                (now_iso, event_id)
            )
            updated = cursor.rowcount > 0
            if updated:
                cursor.execute(
                    "UPDATE reminders SET status = 'cancelled', updated_at = ? WHERE event_id = ? AND status IN ('offered', 'confirmed')",
                    (now_iso, event_id)
                )
            conn.commit()
            return updated

    def atualizar_data_evento(
        self,
        event_id: int,
        new_event_at: str,
        new_follow_up_after: Optional[str] = None
    ) -> bool:
        """Atualiza a data do evento e recalcula automaticamente reminders atrelados baseados em offset_minutes."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE eventos_pendentes
                SET event_at = ?, follow_up_after = COALESCE(?, follow_up_after)
                WHERE id = ? AND status = 'pending'
                """,
                (new_event_at, new_follow_up_after, event_id)
            )
            if cursor.rowcount == 0:
                conn.commit()
                return False

            # Recalcula reminders ativos
            cursor.execute(
                "SELECT id, offset_minutes FROM reminders WHERE event_id = ? AND status IN ('offered', 'confirmed')",
                (event_id,)
            )
            active_reminders = cursor.fetchall()
            for r in active_reminders:
                rid = r["id"]
                off = r["offset_minutes"] or 0
                try:
                    ev_dt = datetime.fromisoformat(new_event_at)
                    new_remind = (ev_dt - timedelta(minutes=off)).isoformat()
                    cursor.execute(
                        "UPDATE reminders SET remind_at = ?, updated_at = ? WHERE id = ?",
                        (new_remind, now_iso, rid)
                    )
                except Exception as e:
                    logger.warning(f"Erro ao recalcular remind_at para reminder {rid}: {e}")

            conn.commit()
            return True

    def listar_eventos_pendentes(self, status: str = "pending", limit: int = 10) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM eventos_pendentes WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit)
            )
            return [dict(r) for r in cursor.fetchall()]

    def buscar_evento_pendente_identico(self, description: str, event_at: Optional[str] = None) -> Optional[dict]:
        """Busca evento pendente ativo com descrição e data idênticas para evitar duplicações (P1.3)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if event_at:
                cursor.execute(
                    "SELECT * FROM eventos_pendentes WHERE description = ? AND event_at = ? AND status = 'pending' LIMIT 1",
                    (description, event_at)
                )
            else:
                cursor.execute(
                    "SELECT * FROM eventos_pendentes WHERE description = ? AND status = 'pending' LIMIT 1",
                    (description,)
                )
            row = cursor.fetchone()
            return dict(row) if row else None

    # --- MÉTODOS DE OPEN LOOPS (ASSUNTOS EM ABERTO - RELEASE 3.5.1) ---

    def adicionar_open_loop(
        self,
        loop_type: str,
        content: str,
        importance: float = 0.5,
        due_at: Optional[str] = None,
        next_check_after: Optional[str] = None,
        source_conversation_id: Optional[int] = None
    ) -> int:
        """Cria um novo assunto/processo em aberto com o Patrick."""
        now_dt = datetime.now()
        now_iso = now_dt.isoformat()
        if next_check_after is None:
            # P2.1: Prazo inicial padrão (24h) para evitar check-in imediato em loops sem prazo
            next_check_after = (now_dt + timedelta(days=1)).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO open_loops
                (loop_type, content, status, importance, due_at, next_check_after, source_conversation_id, created_at, last_touched_at)
                VALUES (?, ?, 'open', ?, ?, ?, ?, ?, ?)
                """,
                (loop_type, content, importance, due_at, next_check_after, source_conversation_id, now_iso, now_iso)
            )
            conn.commit()
            return cursor.lastrowid

    def get_open_loop(self, loop_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM open_loops WHERE id = ?", (loop_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_open_loops_ativos(self, limit: int = 3) -> list[dict]:
        """Retorna os open loops ativos prioritários para injeção no prompt da Marina."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, loop_type, content, status, importance, due_at, next_check_after, last_touched_at
                FROM open_loops
                WHERE status = 'open' AND (is_archived = 0 OR is_archived IS NULL)
                ORDER BY importance DESC, last_touched_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_open_loops_para_checkin(self, now_iso: Optional[Union[str, datetime]] = None, limit: int = 2, now: Optional[Union[str, datetime]] = None) -> list[dict]:
        """Retorna open loops que já atingiram a data para checagem/pergunta carinhosa (P2.1)."""
        val = now or now_iso
        if isinstance(val, datetime):
            check_time = val.isoformat()
        elif isinstance(val, str):
            check_time = val
        else:
            check_time = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, loop_type, content, status, importance, due_at, next_check_after, last_touched_at
                FROM open_loops
                WHERE status = 'open' AND (is_archived = 0 OR is_archived IS NULL) AND (
                    next_check_after IS NOT NULL AND next_check_after <= ?
                )
                ORDER BY importance DESC, last_touched_at ASC
                LIMIT ?
                """,
                (check_time, limit)
            )
            return [dict(r) for r in cursor.fetchall()]

    def resolver_open_loop(self, loop_id: int, resolution_notes: Optional[str] = None) -> bool:
        """Marca o open loop como resolvido com notas contextuais."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE open_loops
                SET status = 'resolved', resolved_at = ?, resolution_notes = ?, last_touched_at = ?
                WHERE id = ? AND status = 'open'
                """,
                (now_iso, resolution_notes, now_iso, loop_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def abandonar_open_loop(self, loop_id: int) -> bool:
        """Marca um open loop como abandonado/descartado."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE open_loops SET status = 'abandoned', last_touched_at = ? WHERE id = ? AND status = 'open'",
                (now_iso, loop_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def atualizar_open_loop_touch(self, loop_id: int, next_check_after: Optional[str] = None) -> bool:
        """Atualiza a data em que o loop foi tocado/mencionado na conversa."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE open_loops SET last_touched_at = ?, next_check_after = COALESCE(?, next_check_after) WHERE id = ?",
                (now_iso, next_check_after, loop_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def arquivar_open_loops_antigos(self, dias: int = 30) -> int:
        """Marca como arquivados (is_archived = 1) os open loops resolvidos ou abandonados há mais de X dias."""
        limite_dt = (datetime.now() - timedelta(days=dias)).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE open_loops
                SET is_archived = 1
                WHERE status IN ('resolved', 'abandoned')
                  AND (resolved_at IS NOT NULL AND resolved_at < ?)
                  AND (is_archived = 0 OR is_archived IS NULL)
                """,
                (limite_dt,)
            )
            conn.commit()
            return cursor.rowcount

    # --- MÉTODOS DE SMART REMINDERS (RELEASE 3.5.1) ---

    def criar_reminder(
        self,
        description: str,
        remind_at: str,
        status: str = "offered",
        event_id: Optional[int] = None,
        offset_minutes: int = 30,
        source_conversation_id: Optional[int] = None
    ) -> int:
        """Cria um registro de reminder (por padrão com status 'offered' aguardando consentimento)."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO reminders
                (event_id, description, remind_at, offset_minutes, status, source_conversation_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, description, remind_at, offset_minutes, status, source_conversation_id, now_iso, now_iso)
            )
            conn.commit()
            return cursor.lastrowid

    def get_reminder(self, reminder_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_ultimo_reminder_ofertado(self, max_age_minutes: int = 60) -> Optional[dict]:
        """Recupera a oferta de lembrete mais recente ainda pendente de resposta do Patrick."""
        cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM reminders
                WHERE status = 'offered' AND created_at >= ?
                ORDER BY id DESC LIMIT 1
                """,
                (cutoff,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def confirmar_reminder(
        self,
        reminder_id: int,
        remind_at: Optional[str] = None,
        offset_minutes: Optional[int] = None
    ) -> bool:
        """Confirma o reminder após consentimento do Patrick."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE reminders
                SET status = 'confirmed',
                    remind_at = COALESCE(?, remind_at),
                    offset_minutes = COALESCE(?, offset_minutes),
                    updated_at = ?
                WHERE id = ? AND status IN ('offered', 'confirmed')
                """,
                (remind_at, offset_minutes, now_iso, reminder_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def recusar_reminder(self, reminder_id: int) -> bool:
        """Marca o reminder ofertado como recusado pelo Patrick."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET status = 'declined', updated_at = ? WHERE id = ? AND status = 'offered'",
                (now_iso, reminder_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def cancelar_reminder(self, reminder_id: int) -> bool:
        """Cancela um reminder agendado."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET status = 'cancelled', updated_at = ? WHERE id = ? AND status IN ('offered', 'confirmed')",
                (now_iso, reminder_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def cancelar_reminders_por_evento(self, event_id: int) -> int:
        """Cancela todos os reminders atrelados a um evento."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET status = 'cancelled', updated_at = ? WHERE event_id = ? AND status IN ('offered', 'confirmed')",
                (now_iso, event_id)
            )
            conn.commit()
            return cursor.rowcount

    def remarcar_reminder(self, reminder_id: int, new_remind_at: str) -> bool:
        """Altera o horário de disparo de um reminder."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET remind_at = ?, updated_at = ? WHERE id = ? AND status IN ('offered', 'confirmed')",
                (new_remind_at, now_iso, reminder_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_due_reminders(self, now_iso: Optional[str] = None) -> list[dict]:
        """Retorna todos os reminders confirmados prontos para envio (remind_at <= now)."""
        check_time = now_iso or datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT r.*, e.description as event_description, e.event_at
                FROM reminders r
                LEFT JOIN eventos_pendentes e ON r.event_id = e.id
                WHERE r.status = 'confirmed' AND r.remind_at <= ?
                ORDER BY r.remind_at ASC
                """,
                (check_time,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def claim_due_reminders(self, now_iso: Optional[str] = None, lease_seconds: int = 120) -> list[dict]:
        """
        Reserva atomicamente lembretes confirmados vencidos para envio no Telegram.
        Usa transação de escrita imediata e lease time para evitar envio duplicado
        por jobs concorrentes ou reinício durante o envio (Release 3.5.1 / Correção P1.2).
        """
        check_time = now_iso or datetime.now().isoformat()
        try:
            now_dt = datetime.fromisoformat(check_time)
        except Exception:
            now_dt = datetime.now()
        lease_cutoff = (now_dt - timedelta(seconds=lease_seconds)).isoformat()
        now_str = now_dt.isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                SELECT r.*, e.description as event_description, e.event_at
                FROM reminders r
                LEFT JOIN eventos_pendentes e ON r.event_id = e.id
                WHERE (r.status = 'confirmed' AND r.remind_at <= ?)
                   OR (r.status = 'sending' AND r.updated_at <= ?)
                ORDER BY r.remind_at ASC
                """,
                (now_str, lease_cutoff)
            )
            rows = cursor.fetchall()
            claimed = [dict(row) for row in rows]
            if claimed:
                ids = [r["id"] for r in claimed]
                placeholders = ",".join("?" for _ in ids)
                cursor.execute(
                    f"""
                    UPDATE reminders
                    SET status = 'sending', updated_at = ?
                    WHERE id IN ({placeholders})
                    """,
                    [now_str] + ids
                )
                for r in claimed:
                    r["status"] = "sending"
                    r["updated_at"] = now_str
            conn.commit()
            return claimed

    def release_reminder_claim(self, reminder_id: int) -> bool:
        """Libera a reserva de um reminder caso o envio falhe, revertendo para 'confirmed' (P1.2)."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET status = 'confirmed', updated_at = ? WHERE id = ? AND status = 'sending'",
                (now_iso, reminder_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def marcar_reminder_enviado(self, reminder_id: int) -> bool:
        """Marca o reminder como enviado no SQLite após envio com sucesso no Telegram (P1.2)."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET status = 'sent', sent_at = ?, updated_at = ? WHERE id = ? AND status IN ('sending', 'confirmed')",
                (now_iso, now_iso, reminder_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_reminder_by_event_id(self, event_id: int) -> Optional[dict]:
        """Retorna o lembrete associado a um evento caso exista (P1.3)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM reminders
                WHERE event_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (event_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def salvar_mensagem_oferta_reminder(self, reminder_id: int, message_id: int) -> bool:
        """Registra o message_id do Telegram em que a oferta de lembrete foi apresentada (P1.3)."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET offer_message_id = ?, updated_at = ? WHERE id = ?",
                (message_id, now_iso, reminder_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_active_reminders(self, limit: int = 10) -> list[dict]:
        """Retorna lembretes futuros ativos (confirmados ou ofertados) para comando /lembretes."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT r.*, e.description as event_description, e.event_at
                FROM reminders r
                LEFT JOIN eventos_pendentes e ON r.event_id = e.id
                WHERE r.status IN ('confirmed', 'offered') AND r.remind_at >= ?
                ORDER BY r.remind_at ASC LIMIT ?
                """,
                (now_iso, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    # --- MÉTODOS DE MEMORY HYGIENE E SESSION REFLECTION (RELEASE 3.5.3) ---

    def aplicar_confidence_decay(
        self,
        dias_volatil: int = 14,
        dias_medio: int = 60,
        now: Optional[datetime] = None
    ) -> dict:
        """
        Executa decay persistente de confiança nas memórias ativas com base na volatilidade e tempo decorrido.
        Regras da Seção 77 do Plano 3.5 e Correção P0.1:
        - Redução estritamente monotônica: novo_conf <= conf_atual para todas as volatilidades e tiers.
        - 'volatile': perde 0.10 a cada ciclo desde o último decaimento (ou confirmação/criação), com piso = min(conf_atual, 0.30) ou 0.05 se já menor.
        - 'medium': perde 0.05 a cada ciclo desde o último decaimento (ou confirmação/criação), com piso = min(conf_atual, 0.50) ou 0.05 se já menor.
        - 'stable' e tier 'core': preservam confiança e nunca sofrem aumento automático nem decaimento (novo_conf = conf_atual).
        - Memórias que caem abaixo de 0.60 de confiança são marcadas com needs_reconfirmation = 1.
        """
        dt_atual = now or datetime.now()
        decayed_count = 0
        reconfirmation_flagged = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, fato, category, importance, confidence, memory_tier, volatility,
                       canonical_key, created_at, updated_at, last_confirmed_at, needs_reconfirmation, last_decay_at
                FROM fatos_patrick
                WHERE active = 1
                """
            )
            fatos = cursor.fetchall()

            for f in fatos:
                fato_id = f["id"]
                tier = (f["memory_tier"] or "standard").lower()
                volatility = (f["volatility"] or "medium").lower()
                conf_atual = float(f["confidence"] if f["confidence"] is not None else 1.0)

                # P0.1: Prioriza last_decay_at, depois last_confirmed_at, depois created_at
                ref_str = f["last_decay_at"] or f["last_confirmed_at"] or f["created_at"]
                if not ref_str:
                    continue
                try:
                    ref_dt = datetime.fromisoformat(ref_str)
                except Exception:
                    continue

                dias_passados = (dt_atual - ref_dt).total_seconds() / 86400.0
                novo_conf = conf_atual
                deve_decaer = False

                if tier == "core" or volatility == "stable":
                    # Core e estável não decaem e NUNCA aumentam via rotina de higiene (P0.1 / §§ 9, 77)
                    novo_conf = conf_atual
                elif volatility == "volatile" and dias_passados >= dias_volatil:
                    ciclos = max(1, int(dias_passados // dias_volatil))
                    reducao = round(ciclos * 0.10, 2)
                    target_floor = 0.30 if conf_atual >= 0.30 else 0.10
                    floor = min(conf_atual, target_floor)
                    novo_conf = max(floor, round(conf_atual - reducao, 2))
                    # Invariante estrita: nunca pode aumentar
                    novo_conf = min(conf_atual, novo_conf)
                    deve_decaer = novo_conf < conf_atual
                elif volatility == "medium" and dias_passados >= dias_medio:
                    ciclos = max(1, int(dias_passados // dias_medio))
                    reducao = round(ciclos * 0.05, 2)
                    target_floor = 0.50 if conf_atual >= 0.50 else 0.10
                    floor = min(conf_atual, target_floor)
                    novo_conf = max(floor, round(conf_atual - reducao, 2))
                    novo_conf = min(conf_atual, novo_conf)
                    deve_decaer = novo_conf < conf_atual

                needs_reconf = 1 if (novo_conf < 0.60 and float(f["importance"] or 0.5) >= 0.50) else 0
                if needs_reconf and not f["needs_reconfirmation"]:
                    reconfirmation_flagged += 1

                if deve_decaer or needs_reconf != f["needs_reconfirmation"]:
                    cursor.execute(
                        """
                        UPDATE fatos_patrick
                        SET confidence = ?, needs_reconfirmation = ?, updated_at = ?, last_decay_at = ?
                        WHERE id = ?
                        """,
                        (novo_conf, needs_reconf, dt_atual.isoformat(), dt_atual.isoformat(), fato_id)
                    )
                    if deve_decaer:
                        decayed_count += 1

            conn.commit()

        return {
            "decayed_count": decayed_count,
            "reconfirmation_flagged": reconfirmation_flagged
        }

    def get_memorias_para_reconfirmacao(self, limit: int = 3) -> list[dict]:
        """Retorna memórias ativas prioritárias que necessitam de reconfirmação com o Patrick."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, fato, category, importance, confidence, memory_tier, volatility, canonical_key, last_confirmed_at
                FROM fatos_patrick
                WHERE active = 1
                  AND (needs_reconfirmation = 1 OR (confidence <= 0.60 AND importance >= 0.60))
                ORDER BY importance DESC, confidence ASC
                LIMIT ?
                """,
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def marcar_fato_reconfirmado(self, fato_id: int, nova_confianca: float = 1.0):
        """Reafirma uma memória que estava em dúvida, elevando confiança e zerando needs_reconfirmation (P0.1)."""
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE fatos_patrick
                SET confidence = ?,
                    confirmation_count = confirmation_count + 1,
                    last_confirmed_at = ?,
                    last_decay_at = NULL,
                    needs_reconfirmation = 0,
                    updated_at = ?
                WHERE id = ?
                """,
                (nova_confianca, now_iso, now_iso, fato_id)
            )
            conn.commit()

    def deduplicar_fatos_redundantes(self) -> int:
        """
        Deduplicação leve de memórias ativas:
        Identifica fatos ativos com canonical_key idêntica,
        inativando réplicas mais antigas sem destruir histórico.
        """
        deduplicated = 0
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT canonical_key, COUNT(*) as qtd
                FROM fatos_patrick
                WHERE active = 1 AND canonical_key IS NOT NULL AND canonical_key != ''
                GROUP BY canonical_key
                HAVING qtd > 1
                """
            )
            dupe_keys = cursor.fetchall()
            for dk in dupe_keys:
                key = dk["canonical_key"]
                cursor.execute(
                    """
                    SELECT id FROM fatos_patrick
                    WHERE active = 1 AND canonical_key = ?
                    ORDER BY id DESC
                    """,
                    (key,)
                )
                ids = [r["id"] for r in cursor.fetchall()]
                for old_id in ids[1:]:
                    cursor.execute(
                        "UPDATE fatos_patrick SET active = 0, updated_at = ? WHERE id = ?",
                        (now_iso, old_id)
                    )
                    deduplicated += 1

            conn.commit()
        return deduplicated

    def get_mensagens_sessao(self, limit: int = 50, since_id: Optional[int] = None) -> list[dict]:
        """Retorna mensagens recentes da conversa para reflexão da sessão a partir de um cursor opcional (P1.1)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if since_id is not None and since_id > 0:
                cursor.execute(
                    """
                    SELECT id, role, content, timestamp
                    FROM conversas
                    WHERE id > ?
                    ORDER BY id ASC LIMIT ?
                    """,
                    (since_id, limit)
                )
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
            else:
                cursor.execute(
                    """
                    SELECT id, role, content, timestamp
                    FROM conversas
                    ORDER BY id DESC LIMIT ?
                    """,
                    (limit,)
                )
                rows = cursor.fetchall()
                return [dict(r) for r in reversed(rows)]

    def get_ultimo_conversa_id_refletido(self) -> int:
        """Retorna o ID da última conversa refletida persistido no estado relacional (P1.1)."""
        st = self.get_estado_relacional()
        val = st.get("last_reflected_conversa_id")
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return 0

    def claim_session_reflection(self, start_id: int, end_id: int, lease_seconds: int = 120) -> bool:
        """
        Garante atomicidade da execução da reflexão de sessão (P1.1).
        Verifica se o intervalo já foi refletido ou se há um lease ativo não expirado.
        Se livre, registra lease temporário em estado_relacional.
        """
        now = datetime.now()
        now_iso = now.isoformat()
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                # 1. Verifica se já existe resumo gravado para este intervalo
                cursor.execute(
                    "SELECT id FROM resumos_conversa WHERE start_conversation_id = ? AND end_conversation_id = ?",
                    (start_id, end_id)
                )
                if cursor.fetchone():
                    conn.rollback()
                    return False

                # 2. Verifica se o cursor persistido já passou deste end_id
                cursor.execute("SELECT valor FROM estado_relacional WHERE chave = 'last_reflected_conversa_id'")
                row = cursor.fetchone()
                if row and row["valor"]:
                    try:
                        if int(row["valor"]) >= end_id:
                            conn.rollback()
                            return False
                    except ValueError:
                        pass

                # 3. Verifica se há lease ativo para este end_id
                cursor.execute("SELECT valor FROM estado_relacional WHERE chave = 'reflection_lease_end_id'")
                row_end = cursor.fetchone()
                cursor.execute("SELECT valor FROM estado_relacional WHERE chave = 'reflection_lease_until'")
                row_until = cursor.fetchone()

                if row_end and row_until and row_end["valor"] == str(end_id):
                    try:
                        until_dt = datetime.fromisoformat(row_until["valor"])
                        if now < until_dt:
                            conn.rollback()
                            return False
                    except Exception:
                        pass

                # 4. Adquire lease
                cursor.execute(
                    "INSERT OR REPLACE INTO estado_relacional (chave, valor, updated_at) VALUES (?, ?, ?)",
                    ("reflection_lease_end_id", str(end_id), now_iso)
                )
                cursor.execute(
                    "INSERT OR REPLACE INTO estado_relacional (chave, valor, updated_at) VALUES (?, ?, ?)",
                    ("reflection_lease_until", lease_until, now_iso)
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def release_session_reflection_claim(self, end_id: int):
        """Libera o lease de reflexão caso o processamento falhe antes de consolidar (P1.1)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM estado_relacional WHERE chave = 'reflection_lease_end_id'")
            row = cursor.fetchone()
            if row and row["valor"] == str(end_id):
                cursor.execute("DELETE FROM estado_relacional WHERE chave IN ('reflection_lease_end_id', 'reflection_lease_until')")
                conn.commit()

    # --- MÉTODOS DE ESTADO RELACIONAL ---

    def get_estado_relacional(self, chave: Optional[str] = None) -> Union[dict[str, str], Optional[str]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if chave:
                cursor.execute("SELECT valor FROM estado_relacional WHERE chave = ?", (chave,))
                row = cursor.fetchone()
                return row["valor"] if row else None
            cursor.execute("SELECT chave, valor FROM estado_relacional")
            return {r["chave"]: r["valor"] for r in cursor.fetchall()}

    def set_estado_relacional(self, chave: str, valor: Optional[str]):
        if valor is None or valor == "":
            self.remover_estado_relacional(chave)
            return
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO estado_relacional (chave, valor, updated_at) VALUES (?, ?, ?)",
                (chave, valor, now_iso)
            )
            conn.commit()

    def remover_estado_relacional(self, chave: str):
        """Remove uma chave de estado_relacional."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM estado_relacional WHERE chave = ?", (chave,))
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

