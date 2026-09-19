"""
Script de Verificação de Saúde e Integridade (Healthcheck) da Marina Salles (v3.7.0).
Valida sintaxe, importações, integridade de SQLite/WAL, configurações essenciais
e construção de prompts SEM abrir conexões de polling no Telegram.

Uso:
    python healthcheck.py
Retorna código de saída 0 em caso de sucesso ou 1 caso haja falhas críticas.
"""
import sys
import compileall
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent

class HealthChecker:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def log_pass(self, title: str, detail: str = ""):
        self.passed += 1
        msg = f"[PASS] {title}"
        if detail:
            msg += f" -> {detail}"
        print(msg)

    def log_fail(self, title: str, error: str = ""):
        self.failed += 1
        msg = f"[FAIL] {title}"
        if error:
            msg += f" -> {error}"
        print(msg)

    def log_warn(self, title: str, warning: str = ""):
        self.warnings += 1
        msg = f"[WARN] {title}"
        if warning:
            msg += f" -> {warning}"
        print(msg)

    def check_syntax(self) -> bool:
        print("\n--- 1. Verificação Sintática (compileall) ---")
        try:
            success = compileall.compile_dir(str(BASE_DIR), maxlevels=1, quiet=1)
            if success:
                self.log_pass("Sintaxe de todos os arquivos Python (.py)", "100% válida")
                return True
            else:
                self.log_fail("Sintaxe de arquivos Python", "Erros de compilação detectados")
                return False
        except Exception as e:
            self.log_fail("Compilação sintática", str(e))
            return False

    def check_configuration(self) -> bool:
        print("\n--- 2. Verificação de Configuração ---")
        try:
            from config import settings
            errors = settings.validate()
            if errors:
                for err in errors:
                    self.log_fail("Configuração Inválida", err)
                return False

            self.log_pass(
                "Configuração Base",
                f"{settings.APP_NAME} v{settings.APP_VERSION} | Debounce: {settings.MESSAGE_DEBOUNCE_SECONDS}s"
            )
            self.log_pass(
                "Autorização de Acesso",
                f"TARGET_CHAT_ID configurado e restrito: {settings.TARGET_CHAT_ID}"
            )
            return True
        except Exception as e:
            self.log_fail("Carregamento de config.py", str(e))
            return False

    def check_database(self) -> bool:
        print("\n--- 3. Verificação do Banco de Dados SQLite ---")
        try:
            from db import db_manager
            with db_manager.get_connection() as conn:
                # Integridade estrutural do SQLite
                check = conn.execute("PRAGMA integrity_check;").fetchone()[0]
                if check.lower() == "ok":
                    self.log_pass("Integridade Física SQLite", "PRAGMA integrity_check = OK")
                else:
                    self.log_fail("Integridade Física SQLite", f"Falha: {check}")
                    return False

                # Pragmas de concorrência
                wal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
                timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
                fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]

                if wal.lower() == "wal":
                    self.log_pass("Modo de Concorrência WAL", f"journal_mode = {wal}")
                else:
                    self.log_warn("Modo de Concorrência", f"journal_mode é {wal} (esperado WAL)")

                self.log_pass("Parâmetros de Conexão", f"busy_timeout={timeout}ms | foreign_keys={fk}")

                # Schema version e contagem básica
                schema_v = db_manager.get_schema_version()
                total_conversas = db_manager.get_total_conversas()
                total_fatos = len(db_manager.get_fatos_patrick())

                self.log_pass(
                    "Schema e Dados Persistentes",
                    f"Versão schema: {schema_v} | Conversas: {total_conversas} | Fatos: {total_fatos}"
                )
                return True
        except Exception as e:
            self.log_fail("Banco de Dados", str(e))
            return False

    def check_module_imports(self) -> bool:
        print("\n--- 4. Verificação de Importação de Módulos ---")
        modules = [
            "config",
            "db",
            "cycle",
            "style_engine",
            "feedback_manager",
            "memory",
            "memory_retriever",
            "memory_consolidator",
            "sd_client",
            "voice_engine",
            "context_builder",
            "planner",
            "proactivity_service",
            "vision_service",
            "visual_profile",
            "bot"
        ]


        all_ok = True
        for mod_name in modules:
            try:
                __import__(mod_name)
                self.log_pass(f"Módulo '{mod_name}'", "Importado com sucesso")
            except Exception as e:
                self.log_fail(f"Módulo '{mod_name}'", str(e))
                all_ok = False
        return all_ok

    def check_context_and_prompts(self) -> bool:
        print("\n--- 5. Verificação de Prompt Authority ---")
        try:
            from prompt_policy import build_safe_core_prompt, get_daypart, CONTROL_EN
            from context_builder import context_builder
            from config import settings

            daypart = get_daypart()
            safe = build_safe_core_prompt(db=None)
            if ('Marina ' + 'Seltin') in safe or '19yo' in safe:
                self.log_fail("SafeCore", "legado pré-v3.6 detectado no fallback")
                return False
            if '[CONTROL RULES]' not in CONTROL_EN:
                self.log_fail("CONTROL_EN", "ausente")
                return False
            ctrl = getattr(settings, 'PROMPT_CONTROL_LANGUAGE', 'en')
            out = getattr(settings, 'MARINA_OUTPUT_LANGUAGE', 'pt-BR')
            self.log_pass("SafeCore + daypart", f"daypart={daypart}")
            self.log_pass("Language policy", f"control={ctrl} output={out}")
            self.log_pass("Context builder", f"available={context_builder is not None}")
            return True
        except Exception as e:
            self.log_fail("Construção de contexto", str(e))
            return False

    def run(self) -> int:
        start_time = datetime.now()
        print(f"==================================================")
        print(f"   MARINA SALLES — DIAGNÓSTICO DE SAÚDE DO SISTEMA")
        print(f"   Data: {start_time.strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"==================================================")

        self.check_syntax()
        self.check_configuration()
        self.check_database()
        self.check_module_imports()
        self.check_context_and_prompts()

        elapsed = (datetime.now() - start_time).total_seconds()
        print("\n--------------------------------------------------")
        print(f"Resultado Final: {self.passed} PASS | {self.warnings} WARN | {self.failed} FAIL")
        print(f"Tempo total de diagnóstico: {elapsed:.2f}s")
        print("--------------------------------------------------")

        if self.failed > 0:
            print("Status: SISTEMA COM FALHAS (VERIFIQUE OS LOGS ACIMA)\n")
            return 1
        else:
            print("Status: SISTEMA 100% OPERACIONAL E SAUDÁVEL\n")
            return 0


if __name__ == "__main__":
    checker = HealthChecker()
    exit_code = checker.run()
    sys.exit(exit_code)
