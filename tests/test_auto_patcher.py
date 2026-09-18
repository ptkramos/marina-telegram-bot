"""
Testes unitários para o Auto-Patcher Transacional (v3.7.0) da Marina Salles.
Valida classificação de arquivos alvos, cálculo de diffs, staging isolado, compilação de sintaxe,
registro de auditoria no SQLite e mecanismo de rollback seguro.
"""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from auto_patcher import AutoPatcher, STAGING_DIR, BACKUP_DIR, BASE_DIR
from db import db_manager


class TestAutoPatcher(unittest.TestCase):

    def setUp(self):
        self.patcher = AutoPatcher()
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_determine_target_files(self):
        """Testa a identificação inteligente de arquivos alvos por nome e semântica."""
        # 1. Menção explícita
        t1 = self.patcher.determine_target_files("adicione uma função em visual_profile.py por favor")
        self.assertTrue(any(f.name == "visual_profile.py" for f in t1))

        t2 = self.patcher.determine_target_files("mude o cycle.py para 30 dias")
        self.assertTrue(any(f.name == "cycle.py" for f in t2))

        # 2. Reconhecimento semântico
        t3 = self.patcher.determine_target_files("coloque uma marquinha de biquíni mais forte e pele bronzeada")
        self.assertTrue(any(f.name == "visual_profile.py" for f in t3))

        t4 = self.patcher.determine_target_files("rastreie uma nova gíria e use mais emojis")
        self.assertTrue(any(f.name == "style_engine.py" for f in t4))

        t5 = self.patcher.determine_target_files("crie uma nova tabela no sqlite para salvar notas")
        self.assertTrue(any(f.name == "db.py" for f in t5))

    def test_compute_unified_diff(self):
        """Valida a geração de diffs no padrão unified diff."""
        old = "def foo():\n    return 1\n"
        new = "def foo():\n    return 2\n"
        diff = self.patcher._compute_unified_diff(old, new, "test.py")

        self.assertIn("--- a/test.py", diff)
        self.assertIn("+++ b/test.py", diff)
        self.assertIn("-    return 1", diff)
        self.assertIn("+    return 2", diff)

    def test_syntax_validation(self):
        """Verifica que a compilação rejeita sintaxe quebrada e aprova código íntegro."""
        valid_file = self.test_dir / "valid.py"
        valid_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
        ok, msg = self.patcher._validate_syntax_and_import(valid_file)
        self.assertTrue(ok)

        invalid_file = self.test_dir / "invalid.py"
        invalid_file.write_text("def broken_syntax(:\n    pass\n", encoding="utf-8")
        ok_inv, msg_inv = self.patcher._validate_syntax_and_import(invalid_file)
        self.assertFalse(ok_inv)
        self.assertIn("Erro de sintaxe", msg_inv)

    def test_db_audit_registration(self):
        """Valida o registro de auditoria de patches no banco SQLite."""
        test_patch_id = f"TEST-PATCH-{tempfile.mktemp()}"
        row_id = db_manager.registrar_patch(
            patch_id=test_patch_id,
            autor="Patrick Ramos",
            instruction="Melhoria de teste no prompt",
            target_files=["prompts.py"],
            diff_content="--- a/prompts.py\n+++ b/prompts.py\n",
            status="applied"
        )
        self.assertGreater(row_id, 0)

        patch_data = db_manager.get_patch_by_id(test_patch_id)
        self.assertIsNotNone(patch_data)
        self.assertEqual(patch_data["autor"], "Patrick Ramos")
        self.assertEqual(patch_data["status"], "applied")
        self.assertIn("prompts.py", patch_data["target_files"])

        # Teste de atualização de status
        db_manager.atualizar_status_patch(test_patch_id, "rolled_back")
        updated = db_manager.get_patch_by_id(test_patch_id)
        self.assertEqual(updated["status"], "rolled_back")

    def test_apply_and_rollback_flow(self):
        """Testa o fluxo transacional completo de aplicação com staging e reversão por rollback."""
        # Cria um arquivo simulado no workspace para o teste
        dummy_file = BASE_DIR / "dummy_test_module.py"
        original_content = "# Versao 1.0 Original\nVAL = 10\n"
        patched_content = "# Versao 2.0 Patched\nVAL = 20\n"
        dummy_file.write_text(original_content, encoding="utf-8")

        try:
            # Mocka a geração da LLM e a determinação de arquivos
            with patch.object(self.patcher, "determine_target_files", return_value=[dummy_file]), \
                 patch.object(self.patcher, "_generate_file_patch", return_value=patched_content):

                success, msg, diff = self.patcher.apply_patch("Altere o VAL para 20 no dummy_test_module.py")
                self.assertTrue(success)
                self.assertIn("dummy_test_module.py", msg)
                self.assertEqual(dummy_file.read_text(encoding="utf-8"), patched_content)

                # Executa o rollback
                rb_ok, rb_msg = self.patcher.rollback_patch()
                self.assertTrue(rb_ok)
                self.assertEqual(dummy_file.read_text(encoding="utf-8"), original_content)

        finally:
            if dummy_file.exists():
                dummy_file.unlink()


if __name__ == "__main__":
    unittest.main()
