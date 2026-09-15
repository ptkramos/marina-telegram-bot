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
from datetime import datetime, date, timedelta
from pathlib import Path

logger = logging.getLogger("MarinaDB")

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "marin_memory.db"

class DatabaseManager:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        is_new = not self.db_path.exists()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Tabela de Conversas (Histórico Permanente)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                is_initiative INTEGER DEFAULT 0,
                media_type TEXT DEFAULT 'text'
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversas_timestamp ON conversas(timestamp);")

            # 2. Tabela de Fatos sobre o Patrick
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS fatos_patrick (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fato TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                relevance INTEGER DEFAULT 1
            );
            """)

            # 3. Tabela de Gostos e Descobertas da Marina
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS gostos_marina (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                item TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(categoria, item)
            );
            """)

            # 4. Tabela de Perfil da Marina
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS perfil (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );
            """)

            # 5. Tabela de Feedbacks & Auto-Correções
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                autor TEXT NOT NULL,
                feedback TEXT NOT NULL,
                contexto_recente TEXT,
                status TEXT DEFAULT 'pendente'
            );
            """)

            # 6. Tabela do Ciclo Biológico
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ciclo_biologico (
                id INTEGER PRIMARY KEY,
                data_inicio_ciclo TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # 7. Tabela de Momentos Marcantes
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS momentos_marcantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                momento TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            # 8. Tabela de Estilo Linguístico do Casal
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS estilo_linguagem (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL,
                exemplos TEXT,
                updated_at TEXT NOT NULL
            );
            """)
            conn.commit()

        if is_new:
            logger.info("Banco SQLite criado com sucesso! Inicializando dados padrão...")
            self._seed_default_profile()

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

    # --- MÉTODOS DE CONVERSAS ---

    def adicionar_mensagem(self, role: str, content: str, is_initiative: bool = False, media_type: str = "text"):
        now_iso = datetime.now().isoformat()
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

    def get_mensagens_recentes(self, limit: int = 12) -> list[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content FROM conversas
                ORDER BY id DESC LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

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

    def adicionar_fato_patrick(self, fato: str):
        now_iso = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO fatos_patrick (fato, created_at) VALUES (?, ?)",
                (fato, now_iso)
            )
            conn.commit()

    def get_fatos_patrick(self) -> list[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fato FROM fatos_patrick ORDER BY id ASC")
            return [r["fato"] for r in cursor.fetchall()]

    def get_momentos_marcantes(self) -> list[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT momento FROM momentos_marcantes ORDER BY id ASC")
            return [r["momento"] for r in cursor.fetchall()]

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

    def salvar_estilo(self, chave: str, valor: str, exemplos: list = None):
        now_iso = datetime.now().isoformat()
        ex_str = json.dumps(exemplos or [], ensure_ascii=False)
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

db_manager = DatabaseManager()
