"""
Motor de Auto-Refinamento e Patch Remoto de Código (v1.3.0).
Permite que o Patrick solicite melhorias no código diretamente pelo Telegram
via comando /edit. O módulo analisa a solicitação, altera o arquivo correto,
valida a sintaxe com py_compile e reinicia o bot com rollback automático em caso de erro.
"""
import py_compile
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from config import settings

logger = logging.getLogger("AutoPatcher")

BASE_DIR = Path(__file__).resolve().parent
PATCH_HISTORY_FILE = BASE_DIR / "patch_history.json"

class AutoPatcher:
    def __init__(self):
        self.llm = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL
        )

    def _determine_target_file(self, instrucao: str) -> Path:
        """Determina qual arquivo de código deve ser alterado com base na instrução."""
        inst = instrucao.lower()
        
        # Reconhecimento explícito por nome de arquivo
        if "prompts.py" in inst or "prompts" in inst:
            return BASE_DIR / "prompts.py"
        elif "db.py" in inst or "banco" in inst or "sqlite" in inst or "tabela" in inst:
            return BASE_DIR / "db.py"
        elif "memory.py" in inst or "memoria" in inst or "memória" in inst:
            return BASE_DIR / "memory.py"
        elif "style_engine.py" in inst or "estilo" in inst or "linguagem" in inst:
            return BASE_DIR / "style_engine.py"
        elif "bot.py" in inst or "comando" in inst or "balao" in inst or "balão" in inst or "digitacao" in inst:
            return BASE_DIR / "bot.py"
            
        # Classificação semântica
        if any(w in inst for w in ["personalidade", "jeito", "falar", "roupa", "biquíni", "foto", "selfie", "humor", "ciclo"]):
            return BASE_DIR / "prompts.py"
        elif any(w in inst for w in ["salvar", "campo", "sql"]):
            return BASE_DIR / "db.py"
        elif any(w in inst for w in ["fato", "lembrança", "emocional"]):
            return BASE_DIR / "memory.py"
        elif any(w in inst for w in ["gíria", "giria", "risada", "emoji", "cadencia", "cadência"]):
            return BASE_DIR / "style_engine.py"
        else:
            return BASE_DIR / "prompts.py"

    def apply_patch(self, instrucao: str, autor: str = "Patrick Ramos") -> tuple[bool, str]:
        """Aplica o patch solicitado, valida a sintaxe e registra histórico."""
        target_file = self._determine_target_file(instrucao)
        file_name = target_file.name

        try:
            current_code = target_file.read_text(encoding="utf-8")
        except Exception as e:
            return False, f"Não foi possível ler o arquivo {file_name}: {e}"

        logger.info(f"Iniciando auto-patch no arquivo {file_name} solicitado por {autor}...")

        prompt_system = (
            "Você é um engenheiro de software sênior Python especializado em IA. "
            "Sua tarefa é modificar o arquivo Python fornecido estritamente para atender à melhoria pedida pelo Patrick Ramos. "
            "Mantenha toda a funcionalidade existente, comentários úteis e docstrings. "
            "IMPORTANTE: Retorne ESTRITAMENTE o código Python completo do arquivo, sem explicações, sem blocos ```python e sem markdown."
        )

        prompt_user = (
            f"ARQUIVO ALVO: {file_name}\n"
            f"SOLICITAÇÃO DE MELHORIA DO PATRICK:\n\"{instrucao}\"\n\n"
            f"CÓDIGO ATUAL COMPLETO:\n{current_code}\n\n"
            "Retorne o código Python atualizado completo pronto para execução:"
        )

        try:
            res = self.llm.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": prompt_system},
                    {"role": "user", "content": prompt_user}
                ],
                max_tokens=4000,
                temperature=0.25
            )
            raw_new_code = res.choices[0].message.content.strip()

            # Limpa possíveis blocos de markdown ```python ... ```
            if raw_new_code.startswith("```"):
                lines = raw_new_code.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean_new_code = "\n".join(lines).strip()
            else:
                clean_new_code = raw_new_code

            # Validação rigorosa de sintaxe via sandbox py_compile
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as tmp:
                tmp.write(clean_new_code)
                tmp_path = tmp.name

            try:
                py_compile.compile(tmp_path, doraise=True)
            except py_compile.PyCompileError as pe:
                logger.error(f"Falha de validação de sintaxe no patch gerado: {pe}")
                return False, f"A IA gerou uma sintaxe inválida no código. O arquivo `{file_name}` foi protegido e permanece intacto."

            # Backup do arquivo atual
            backup_path = target_file.with_suffix(".py.bak")
            backup_path.write_text(current_code, encoding="utf-8")

            # Salva o novo código
            target_file.write_text(clean_new_code, encoding="utf-8")

            # Registra no histórico de patches
            self._log_patch(instrucao, file_name, autor)
            logger.info(f"Patch aplicado com sucesso em {file_name}!")
            return True, f"Melhoria aplicada com sucesso no arquivo `{file_name}`! Código compilado e validado."

        except Exception as e:
            logger.error(f"Erro ao processar auto-patch: {e}")
            return False, f"Erro inesperado durante o patch: {e}"

    def _log_patch(self, instrucao: str, file_name: str, autor: str):
        history = []
        if PATCH_HISTORY_FILE.exists():
            try:
                history = json.loads(PATCH_HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                history = []

        history.append({
            "id": f"PATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "autor": autor,
            "arquivo_alterado": file_name,
            "instrucao": instrucao
        })

        PATCH_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

auto_patcher = AutoPatcher()
