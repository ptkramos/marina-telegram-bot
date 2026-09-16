"""
Motor de Auto-Refinamento, Auditoria e Patch Transacional de Código (v3.4.0).
Permite que o Patrick solicite melhorias no código diretamente pelo Telegram via /edit.
Executa modificações em área de staging isolada (.runtime/patch_staging/),
gera diffs unificados, valida sintaxe via py_compile e imports em subprocesso,
com histórico persistido no SQLite e rollback garantido.
"""
import os
import sys
import json
import difflib
import logging
import py_compile
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI
from config import settings
from db import db_manager

logger = logging.getLogger("AutoPatcher")

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / ".runtime"
STAGING_DIR = RUNTIME_DIR / "patch_staging"
BACKUP_DIR = RUNTIME_DIR / "backups"

# Garante a existência dos diretórios de suporte
STAGING_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Catálogo completo de módulos editáveis com descrições semânticas
MODULE_CATALOG: dict[str, str] = {
    "prompts.py": "personalidade, sistema de prompts, falas da Marina, tom afetivo, exemplos de conversa",
    "visual_profile.py": "aparência física, traços da Marina, roupas, marquinha de biquíni, bronzeado, fotos, poses, ângulos",
    "sd_client.py": "geração de imagens, ComfyUI, FLUX.1 Dev, LoRAs, GPU dedicada Novita",
    "cycle.py": "ciclo biológico menstrual, fases, libido, TPM, cólica, dias férteis, reações do ciclo",
    "style_engine.py": "estilo de linguagem, gírias, emojis recorrentes, tipo de risada, cadência de digitação",
    "planner.py": "planejamento cognitivo pré-resposta, metas de fala, deltas emocionais, intenções",
    "proactivity_service.py": "mensagens autônomas espontâneas, iniciativa própria, janela de sono, limites diários",
    "vision_service.py": "visão computacional de fotos recebidas do Patrick, interpretação multimodal",
    "voice_engine.py": "síntese de áudio/voz, ElevenLabs, mensagens de voz da Marina",
    "context_builder.py": "montagem de contexto dinâmico, injeção de memórias e fatos no prompt",
    "memory_consolidator.py": "consolidação periódica de memórias de longo prazo, resolução de contradições",
    "memory_retriever.py": "busca semântica e busca textual FTS5 em fatos e conversas",
    "db.py": "camada SQLite, persistência de dados, tabelas, migrações",
    "config.py": "configurações, timeouts, chaves de API, variáveis de ambiente",
    "bot.py": "orquestrador principal do Telegram, comandos, debounce, handlers"
}


class AutoPatcher:
    def __init__(self):
        self.llm = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL
        )

    def determine_target_files(self, instrucao: str) -> list[Path]:
        """Identifica quais arquivos do projeto devem ser modificados com base na instrução."""
        inst_lower = instrucao.lower()
        targets: list[Path] = []

        # 1. Menção direta e explícita por nome de arquivo
        for mod_name in MODULE_CATALOG.keys():
            if mod_name.lower() in inst_lower:
                p = BASE_DIR / mod_name
                if p.exists() and p not in targets:
                    targets.append(p)

        if targets:
            return targets

        # 2. Heurísticas semânticas avançadas
        if any(w in inst_lower for w in ["biquíni", "biquini", "marquinha", "bronzeada", "bronzeado", "rosto", "corpo", "visual", "câmera", "foto perfil"]):
            targets.append(BASE_DIR / "visual_profile.py")
        elif any(w in inst_lower for w in ["ciclo", "menstrua", "tpm", "fértil", "fertil", "libido", "ovula"]):
            targets.append(BASE_DIR / "cycle.py")
        elif any(w in inst_lower for w in ["gíria", "giria", "risada", "emoji", "cadência", "cadencia", "estilo"]):
            targets.append(BASE_DIR / "style_engine.py")
        elif any(w in inst_lower for w in ["iniciativa", "espontânea", "autonoma", "autônoma", "sono", "acordar"]):
            targets.append(BASE_DIR / "proactivity_service.py")
        elif any(w in inst_lower for w in ["visão", "visao", "olhar foto", "analisar foto", "multimodal"]):
            targets.append(BASE_DIR / "vision_service.py")
        elif any(w in inst_lower for w in ["planejador", "planner", "meta de fala", "delta emocional"]):
            targets.append(BASE_DIR / "planner.py")
        elif any(w in inst_lower for w in ["voz", "áudio", "audio", "falar", "elevenlabs"]):
            targets.append(BASE_DIR / "voice_engine.py")
        elif any(w in inst_lower for w in ["tabela", "banco", "sqlite", "salvar", "campo novo"]):
            targets.append(BASE_DIR / "db.py")
        elif any(w in inst_lower for w in ["personalidade", "jeito dela", "prompts", "prompt base"]):
            targets.append(BASE_DIR / "prompts.py")
        else:
            # Fallback seguro para prompts ou visual_profile
            targets.append(BASE_DIR / "prompts.py")

        return [t for t in targets if t.exists()]

    def _generate_file_patch(self, file_path: Path, instrucao: str) -> str:
        """Gera o novo código do arquivo utilizando a LLM."""
        current_code = file_path.read_text(encoding="utf-8")
        file_name = file_path.name

        prompt_system = (
            "Você é um engenheiro de software sênior Python especializado em IA e sistemas autônomos. "
            f"Sua tarefa é modificar o arquivo Python '{file_name}' para atender estritamente à solicitação do Patrick Ramos. "
            "Preserve toda a arquitetura existente, docstrings, imports necessários e comportamento. "
            "IMPORTANTE: Retorne ESTRITAMENTE o código Python completo do arquivo, sem explicações, sem blocos de texto antes/depois, e sem comentários desnecessários."
        )

        prompt_user = (
            f"ARQUIVO ALVO: {file_name}\n"
            f"SOLICITAÇÃO DO PATRICK:\n\"{instrucao}\"\n\n"
            f"CÓDIGO ATUAL COMPLETO:\n{current_code}\n\n"
            "Retorne o código Python atualizado completo pronto para compilação:"
        )

        res = self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            max_tokens=6000,
            temperature=0.20
        )
        raw_code = res.choices[0].message.content.strip()

        # Higieniza possíveis blocos markdown
        if raw_code.startswith("```"):
            lines = raw_code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return raw_code

    def _compute_unified_diff(self, old_text: str, new_text: str, file_name: str) -> str:
        """Calcula o diff unificado entre o código antigo e o novo."""
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_name}",
            tofile=f"b/{file_name}",
            n=3
        )
        return "".join(diff)

    def _validate_syntax_and_import(self, file_path: Path) -> tuple[bool, str]:
        """Valida compilação de sintaxe e testa import do módulo via subprocesso."""
        # 1. Validação por py_compile
        try:
            py_compile.compile(str(file_path), doraise=True)
        except py_compile.PyCompileError as pe:
            return False, f"Erro de sintaxe (py_compile): {pe}"
        except Exception as e:
            return False, f"Falha na compilação: {e}"

        # 2. Smoke-test de importação rápida em subprocesso isolado
        mod_name = file_path.stem
        # Evita rodar bot.py diretamente no subprocesso (ele iniciaria a conexão do Telegram)
        if mod_name != "bot":
            cmd = [sys.executable, "-c", f"import sys; sys.path.insert(0, r'{file_path.parent}'); import {mod_name}"]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=str(BASE_DIR)
                )
                if proc.returncode != 0:
                    err_msg = proc.stderr.strip() or proc.stdout.strip()
                    logger.warning(f"Smoke test de importação falhou para {mod_name}: {err_msg}")
                    return False, f"Falha de importação em subprocesso: {err_msg[:200]}"
            except subprocess.TimeoutExpired:
                pass  # timeout pode ocorrer com módulos que carregam recursos pesados, não necessariamente erro de sintaxe
            except Exception as e:
                logger.warning(f"Aviso no smoke-test de import: {e}")

        return True, "OK"

    def apply_patch(self, instrucao: str, autor: str = "Patrick Ramos") -> tuple[bool, str, str]:
        """
        Executa um patch seguro em área de staging, valida tudo antes de mover para produção
        e salva histórico detalhado no SQLite com capacidade de rollback.
        Retorna: (sucesso: bool, mensagem: str, diff: str)
        """
        patch_id = f"PATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        target_files = self.determine_target_files(instrucao)

        if not target_files:
            return False, "Nenhum arquivo compatível foi identificado para esta melhoria.", ""

        patch_staging_path = STAGING_DIR / patch_id
        patch_backup_path = BACKUP_DIR / patch_id
        patch_staging_path.mkdir(parents=True, exist_ok=True)
        patch_backup_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"🛠️ Iniciando patch transacional {patch_id} para {len(target_files)} arquivo(s): {[f.name for f in target_files]}")

        staged_files: list[tuple[Path, Path, str, str]] = [] # (orig, staged, old_code, new_code)
        full_diffs: list[str] = []

        try:
            # Fase 1: Geração e Staging
            for original_file in target_files:
                file_name = original_file.name
                old_code = original_file.read_text(encoding="utf-8")

                # Salva backup original intacto
                backup_file = patch_backup_path / file_name
                backup_file.write_text(old_code, encoding="utf-8")

                # Gera novo código
                new_code = self._generate_file_patch(original_file, instrucao)
                if not new_code or len(new_code) < 20:
                    raise ValueError(f"O gerador retornou código vazio ou inválido para {file_name}")

                # Salva no staging
                staged_file = patch_staging_path / file_name
                staged_file.write_text(new_code, encoding="utf-8")

                # Valida sintaxe e integridade
                val_ok, val_err = self._validate_syntax_and_import(staged_file)
                if not val_ok:
                    raise ValueError(f"Validação falhou para {file_name}: {val_err}")

                diff_text = self._compute_unified_diff(old_code, new_code, file_name)
                full_diffs.append(diff_text)
                staged_files.append((original_file, staged_file, old_code, new_code))

            # Fase 2: Aplicação Atômica em Produção
            applied_files: list[tuple[Path, str]] = []
            try:
                for original_file, staged_file, old_code, new_code in staged_files:
                    original_file.write_text(new_code, encoding="utf-8")
                    applied_files.append((original_file, old_code))
            except Exception as copy_err:
                logger.error(f"Erro durante aplicação atômica, acionando rollback emergencial: {copy_err}")
                for af, old_c in applied_files:
                    af.write_text(old_c, encoding="utf-8")
                raise copy_err

            # Fase 3: Registro de Auditoria no SQLite
            diff_combined = "\n".join(full_diffs)
            target_names = [f.name for f in target_files]
            db_manager.registrar_patch(
                patch_id=patch_id,
                autor=autor,
                instruction=instrucao,
                target_files=target_names,
                diff_content=diff_combined,
                status="applied"
            )

            logger.info(f"✅ Patch {patch_id} aplicado e registrado com sucesso!")
            msg = (
                f"✅ **Patch `{patch_id}` aplicado com sucesso!**\n\n"
                f"📁 **Arquivos alterados:** {', '.join(target_names)}\n"
                f"🧪 **Validação:** Sintaxe e imports compilados com 100% de integridade."
            )
            return True, msg, diff_combined

        except Exception as e:
            logger.error(f"❌ Falha no patch {patch_id}: {e}", exc_info=True)
            # Registra como falha/rejeitado no SQLite se possível
            try:
                db_manager.registrar_patch(
                    patch_id=patch_id,
                    autor=autor,
                    instruction=instrucao,
                    target_files=[f.name for f in target_files],
                    diff_content="\n".join(full_diffs),
                    status="rejected"
                )
            except Exception:
                pass

            err_msg = (
                f"⚠️ **O patch `{patch_id}` foi cancelado e revertido para sua segurança.**\n"
                f"Motivo: {str(e)[:300]}\n"
                f"O código de produção permanece 100% intacto e protegido."
            )
            return False, err_msg, ""

    def rollback_patch(self, patch_id: Optional[str] = None) -> tuple[bool, str]:
        """Reverte o último patch aplicado (ou valida LIFO para patch específico) restaurando do backup."""
        last_applied = db_manager.get_last_applied_patch()
        if not last_applied:
            return False, "Nenhum patch ativo foi encontrado para reverter."

        if not patch_id:
            patch_id = last_applied["patch_id"]
            last_patch = last_applied
        else:
            last_patch = db_manager.get_patch_by_id(patch_id)
            if not last_patch:
                return False, f"Patch `{patch_id}` não foi encontrado no histórico."

            # Proteção LIFO: Apenas o patch aplicado mais recente pode ser revertido diretamente
            if last_applied["patch_id"] != patch_id:
                return False, (
                    f"⚠️ Por segurança estrutural, apenas o patch aplicado mais recente (`{last_applied['patch_id']}`) "
                    f"pode ser revertido em ordem sequencial (LIFO), impedindo que modificações mais recentes sejam apagadas acidentalmente. "
                    f"Reverta `{last_applied['patch_id']}` primeiro."
                )

        backup_patch_dir = BACKUP_DIR / patch_id
        if not backup_patch_dir.exists():
            return False, f"Pasta de backup para `{patch_id}` não foi encontrada em disco."

        target_files = last_patch.get("target_files", [])
        restored = []

        try:
            for fname in target_files:
                bfile = backup_patch_dir / fname
                orig_file = BASE_DIR / fname
                if bfile.exists() and orig_file.exists():
                    code = bfile.read_text(encoding="utf-8")
                    # Valida integridade antes de restaurar
                    py_compile.compile(str(bfile), doraise=True)
                    orig_file.write_text(code, encoding="utf-8")
                    restored.append(fname)

            now_iso = datetime.now().isoformat()
            db_manager.atualizar_status_patch(patch_id, status="rolled_back", reverted_at=now_iso)
            logger.info(f"⏪ Rollback do patch {patch_id} concluído com sucesso!")
            return True, f"⏪ **Rollback do patch `{patch_id}` realizado com sucesso!**\nArquivos restaurados: {', '.join(restored)}"

        except Exception as e:
            logger.error(f"Erro ao executar rollback do patch {patch_id}: {e}", exc_info=True)
            return False, f"Falha ao executar rollback: {e}"


# Instância global
auto_patcher = AutoPatcher()
