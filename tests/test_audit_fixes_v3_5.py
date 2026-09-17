"""
tests/test_audit_fixes_v3_5.py — Testes de Regressão para a Revisão Técnica Completa 3.5.0 a 3.5.3
Valida as correções das falhas críticas identificadas no relatório REVISAO_TECNICA_MARINA_V3_5_COMPLETA.md:
- P0.1: Decaimento de confiança estritamente monotônico (nunca aumenta a confiança).
- P1.1: Cursor de reflexão de sessão e prevenção de replay/duplicação.
- P1.2: Reserva atômica de reminders (claim) e prevenção de disparo concorrente duplo.
- P1.3: Deduplicação de ofertas de reminders e confirmação dependente de contexto ("sim" isolado não confirma assunto alheio).
- P1.4: Allowlist estrita de Open Loops apresentados na reflexão de sessão.
- P1.5: Lembrete direto sem horário explícito não assume +1h arbitrário.
- P2.1: Open loops sem hint recebem delay inicial e não ficam imediatamente prontos para proatividade.
- P2.2: Feature flags SESSION_REFLECTION_ENABLED e MEMORY_HYGIENE_ENABLED desativadas por padrão.
"""
import sys
import unittest
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
from db import DatabaseManager
from memory_hygiene import MemoryHygieneService
from session_reflector import SessionReflector
from reminder_service import ReminderService
from planner import InternalPlanner
import bot


class TestAuditFixesV35(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_audit_fixes.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.reminder_svc = ReminderService(self.db)
        self.reflector = SessionReflector(db=self.db, llm_client=MagicMock())
        self.hygiene = MemoryHygieneService(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    # --- P0.1: HIGIENE / DECAIMENTO DE CONFIANÇA ---
    def test_p0_1_confidence_decay_monotonic_and_never_increases(self):
        """
        P0.1: Garante que o decaimento de confiança é estritamente monotônico.
        Uma memória volátil com baixa confiança (ex: 0.20) criada há 25 dias
        JAMAIS deve ter sua confiança elevada (ex: para 0.90). Deve ser <= conf_anterior.
        """
        old_dt = (datetime.now() - timedelta(days=25)).isoformat()

        # Caso 1: Fato volátil com confiança 0.20
        fid_low = self.db.adicionar_fato_patrick("Patrick gosta de suco de maracujá às vezes", confidence=0.20, volatility="volatile")
        with self.db.get_connection() as conn:
            conn.execute("UPDATE fatos_patrick SET created_at = ?, last_confirmed_at = NULL WHERE id = ?", (old_dt, fid_low))
            conn.commit()

        conf_before = self.db.get_fato_detalhado(fid_low)["confidence"]
        self.assertAlmostEqual(conf_before, 0.20)

        # Executa higiene forçando execução
        self.hygiene.run_hygiene_cycle(force=True)

        fato_after = self.db.get_fato_detalhado(fid_low)
        conf_after = fato_after["confidence"]
        self.assertLessEqual(conf_after, conf_before, "A confiança nunca pode aumentar durante o decaimento!")
        self.assertAlmostEqual(conf_after, 0.10)  # Decaiu de 0.20 para o piso 0.10
        self.assertEqual(fato_after["needs_reconfirmation"], 1)

        # Caso 2: Fato estável com confiança 0.60
        fid_stable = self.db.adicionar_fato_patrick("Patrick tem um gato", confidence=0.60, volatility="stable")
        with self.db.get_connection() as conn:
            conn.execute("UPDATE fatos_patrick SET created_at = ?, last_confirmed_at = NULL WHERE id = ?", (old_dt, fid_stable))
            conn.commit()

        self.hygiene.run_hygiene_cycle(force=True)
        conf_stable_after = self.db.get_fato_detalhado(fid_stable)["confidence"]
        self.assertLessEqual(conf_stable_after, 0.60, "Fatos estáveis nunca podem aumentar sua confiança automaticamente!")

        # Caso 3: Fato com confiança já no piso absoluto (0.10)
        fid_floor = self.db.adicionar_fato_patrick("Fato no piso", confidence=0.10, volatility="volatile")
        with self.db.get_connection() as conn:
            conn.execute("UPDATE fatos_patrick SET created_at = ?, last_confirmed_at = NULL WHERE id = ?", (old_dt, fid_floor))
            conn.commit()

        self.hygiene.run_hygiene_cycle(force=True)
        conf_floor_after = self.db.get_fato_detalhado(fid_floor)["confidence"]
        self.assertAlmostEqual(conf_floor_after, 0.10, msg="Fato no piso não deve decair abaixo do mínimo nem subir.")

    # --- P1.1: CURSOR DE REFLEXÃO DE SESSÃO E PREVENÇÃO DE REPLAY ---
    def test_p1_1_session_reflection_cursor_and_replay_prevention(self):
        """
        P1.1: Garante que a reflexão de sessão usa cursor persistente.
        A mesma sessão não pode ser reprocessada repetidamente gerando resumos duplicados.
        """
        old_time = (datetime.now() - timedelta(hours=3)).isoformat()
        for i in range(4):
            self.db.adicionar_mensagem("user" if i % 2 == 0 else "assistant", f"Mensagem teste {i}", timestamp=old_time)

        self.reflector.reflect_session = MagicMock(return_value={
            "topics": ["Trabalho"],
            "summary": "Patrick falou sobre o trabalho.",
            "open_loops": [{"content": "Aguardar retorno do cliente", "loop_type": "waiting"}],
            "resolved_loops": [],
            "relationship_moments": [],
            "events": []
        })

        # Primeira execução: reflete as 4 mensagens
        res1 = self.reflector.check_and_trigger_reflection(force=True)
        self.assertIsNotNone(res1)
        self.assertEqual(len(self.db.get_resumos_conversa(limit=10)), 1)
        self.assertEqual(len(self.db.get_open_loops_ativos(limit=10)), 1)

        # Cursor deve ter sido atualizado para 4
        cursor_id = self.db.get_ultimo_conversa_id_refletido()
        self.assertEqual(cursor_id, 4)

        # Segunda execução imediata: não há mensagens novas desde id=4
        res2 = self.reflector.check_and_trigger_reflection(force=True)
        self.assertIsNone(res2)
        # Contagem de resumos e loops permanece 1 (zero duplicações)
        self.assertEqual(len(self.db.get_resumos_conversa(limit=10)), 1)
        self.assertEqual(len(self.db.get_open_loops_ativos(limit=10)), 1)

    def test_p1_1_session_reflection_llm_failure_does_not_advance_cursor(self):
        """
        P1.1: Em caso de erro na LLM, não deve criar resumo genérico nem avançar o cursor.
        """
        old_time = (datetime.now() - timedelta(hours=3)).isoformat()
        for i in range(4):
            self.db.adicionar_mensagem("user", f"Msg {i}", timestamp=old_time)

        # Simula falha da LLM (retorna None)
        self.reflector.reflect_session = MagicMock(return_value=None)
        res = self.reflector.check_and_trigger_reflection(force=True)
        self.assertIsNone(res)
        self.assertEqual(self.db.get_ultimo_conversa_id_refletido(), 0)
        self.assertEqual(len(self.db.get_resumos_conversa(limit=10)), 0)

    # --- P1.2: RESERVA ATÔMICA DE REMINDERS E TRATAMENTO DE CONCORRÊNCIA ---
    def test_p1_2_reminder_atomic_claim_concurrency(self):
        """
        P1.2: Garante que claim_due_reminders impede que duas rotinas concorrentes
        disparem o mesmo reminder.
        """
        due_time = (datetime.now() - timedelta(minutes=1)).isoformat()
        rid = self.reminder_svc.create_direct_reminder("Reunião urgente", due_time)
        self.assertIsNotNone(rid)

        # Primeira tentativa de claim
        claimed_1 = self.reminder_svc.claim_due_reminders()
        self.assertEqual(len(claimed_1), 1)
        self.assertEqual(claimed_1[0]["id"], rid)
        self.assertEqual(claimed_1[0]["status"], "sending")

        # Segunda tentativa de claim imediata (concorrente)
        claimed_2 = self.reminder_svc.claim_due_reminders()
        self.assertEqual(len(claimed_2), 0, "O reminder já está em 'sending' com lease válido; não pode ser re-claimado!")

    def test_p1_2_reminder_release_claim_on_send_failure(self):
        """
        P1.2: Se o envio do reminder falhar, a claim deve ser liberada (status='confirmed').
        """
        due_time = (datetime.now() - timedelta(minutes=1)).isoformat()
        rid = self.reminder_svc.create_direct_reminder("Dentista", due_time)

        claimed = self.reminder_svc.claim_due_reminders()
        self.assertEqual(len(claimed), 1)

        # Simula falha de envio liberando claim
        self.reminder_svc.release_claim(rid)
        rem = self.db.get_reminder(rid)
        self.assertEqual(rem["status"], "confirmed", "Após falha, reminder deve voltar para 'confirmed' para retry.")

    # --- P1.3: DEDUPLICAÇÃO DE OFERTAS E CONFIRMAÇÃO CONTEXTUAL ---
    def test_p1_3_reminder_offer_deduplication(self):
        """
        P1.3: Aplicar o mesmo plano de evento com reminder duas vezes não gera duas ofertas.
        """
        planner = InternalPlanner(db=self.db, llm_client=MagicMock())
        event_at = (datetime.now() + timedelta(days=2)).isoformat()
        plan = {
            "creates_event": True,
            "event_details": {"event_type": "médico", "description": "Consulta Oftalmo", "event_at": event_at},
            "should_offer_reminder": True,
            "recommended_reminder_offset_minutes": 60
        }

        with patch("reminder_service.reminder_service", self.reminder_svc):
            planner.apply_plan_effects(plan, conversation_id=1)
            planner.apply_plan_effects(plan, conversation_id=2)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM reminders WHERE status = 'offered'")
            count = cursor.fetchone()["count"]

        self.assertEqual(count, 1, "Oferta de reminder repetida para o mesmo evento deve ser deduplicada.")

    def test_p1_3_parse_confirmation_response_requires_context_for_bare_affirmation(self):
        """
        P1.3: Um 'sim' solto sem contexto da oferta de reminder não deve acionar ação 'confirm'.
        """
        self.reminder_svc.offer_reminder(None, "Tomar remédio", (datetime.now() + timedelta(hours=2)).isoformat())

        # 'sim' sem contexto -> 'none'
        resp_no_ctx = self.reminder_svc.parse_confirmation_response("sim", has_context=False)
        self.assertEqual(resp_no_ctx["action"], "none")

        # 'sim' com contexto comprovado -> 'confirm'
        resp_with_ctx = self.reminder_svc.parse_confirmation_response("sim", has_context=True)
        self.assertEqual(resp_with_ctx["action"], "confirm")

        # Frase explícita de reminder -> 'confirm' mesmo sem context flag
        resp_explicit = self.reminder_svc.parse_confirmation_response("me lembra sim por favor", has_context=False)
        self.assertEqual(resp_explicit["action"], "confirm")

        # Recusa explícita
        resp_decline = self.reminder_svc.parse_confirmation_response("não precisa me lembrar amor")
        self.assertEqual(resp_decline["action"], "decline")

    # --- P1.4: ALLOWLIST DE OPEN LOOPS NA REFLEXÃO ---
    def test_p1_4_session_reflector_loop_allowlist_validation(self):
        """
        P1.4: SessionReflector só pode resolver loops que estavam presentes na lista de apresentados.
        Loops não apresentados ou IDs inexistentes devem ser ignorados.
        """
        loop_id_protected = self.db.adicionar_open_loop("waiting", "Esperando aprovação do projeto")
        loop_id_allowed = self.db.adicionar_open_loop("decision", "Decidir qual hotel reservar")

        # Passa apenas loop_id_allowed na allowlist
        allowed_ids = {loop_id_allowed}
        reflection_payload = {
            "summary": "Conversamos sobre a viagem.",
            "resolved_loops": [
                {"loop_id": loop_id_protected, "resolution_notes": "Tentativa indevida de resolver"},
                {"loop_id": loop_id_allowed, "resolution_notes": "Hotel escolhido com sucesso"},
                {"loop_id": 999999, "resolution_notes": "ID inexistente"}
            ]
        }

        res = self.reflector.apply_reflection(reflection_payload, allowed_loop_ids=allowed_ids)
        self.assertEqual(res["resolved_loops_count"], 1)

        # loop_id_protected DEVE continuar aberto
        loop_prot = self.db.get_open_loop(loop_id_protected)
        self.assertEqual(loop_prot["status"], "open")

        # loop_id_allowed DEVE estar resolvido
        loop_allow = self.db.get_open_loop(loop_id_allowed)
        self.assertEqual(loop_allow["status"], "resolved")

    # --- P1.5: PEDIDO DIRETO SEM HORÁRIO EXPLÍCITO ---
    def test_p1_5_direct_reminder_without_explicit_time_does_not_assume_one_hour(self):
        """
        P1.5: direct_reminder não deve assumir offset arbitrário de +1 hora se o horário não for reconhecido.
        Deve exigir horário reconhecível e futuro para criar o reminder confirmado.
        """
        planner = InternalPlanner(db=self.db, llm_client=MagicMock())

        # Caso vago sem horário reconhecível
        vague_plan = {
            "direct_reminder": {
                "is_direct_reminder": True,
                "description": "Lembrar de comprar pão",
                "remind_at": "mais tarde quando der"
            }
        }
        with patch("reminder_service.reminder_service", self.reminder_svc):
            planner.apply_plan_effects(vague_plan, conversation_id=1)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM reminders WHERE status = 'confirmed'")
            self.assertEqual(cursor.fetchone()["count"], 0, "Não deve criar reminder confirmado para horário vago!")

        # Caso com data/hora válida no futuro
        future_iso = (datetime.now() + timedelta(hours=3)).replace(microsecond=0).isoformat()
        valid_plan = {
            "direct_reminder": {
                "is_direct_reminder": True,
                "description": "Lembrar de ligar pro médico",
                "remind_at": future_iso
            }
        }
        with patch("reminder_service.reminder_service", self.reminder_svc):
            planner.apply_plan_effects(valid_plan, conversation_id=2)

        active_rems = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(active_rems), 1)
        self.assertEqual(active_rems[0]["description"], "Lembrar de ligar pro médico")

    # --- P2.1: OPEN LOOP SEM NEXT_CHECK_AFTER RECEBE DELAY INICIAL ---
    def test_p2_1_open_loop_initial_check_delay(self):
        """
        P2.1: Open loops sem next_check_hint recebem delay inicial padrão (ex: 24h)
        e não ficam imediatamente prontos para check-in proativo no momento da criação.
        """
        lid = self.db.adicionar_open_loop("ongoing_project", "Escrever artigo sobre IA")
        loop = self.db.get_open_loop(lid)

        self.assertIsNotNone(loop["next_check_after"], "next_check_after não pode ser NULL ao criar loop!")
        check_dt = datetime.fromisoformat(loop["next_check_after"])
        self.assertGreater(check_dt, datetime.now(), "next_check_after inicial deve estar no futuro!")

        # Consulta de checkin imediata: não deve retornar este loop
        prontos_agora = self.db.get_open_loops_para_checkin(now=datetime.now())
        self.assertNotIn(lid, [p["id"] for p in prontos_agora], "Loop recém-criado não pode estar pronto imediatamente!")

        # Simula passagem de tempo (25 horas depois)
        prontos_futuro = self.db.get_open_loops_para_checkin(now=datetime.now() + timedelta(hours=25))
        self.assertIn(lid, [p["id"] for p in prontos_futuro], "Loop deve ficar pronto após next_check_after expirar.")

    # --- P2.2: FEATURE FLAGS DESATIVADAS POR PADRÃO ---
    def test_p2_2_feature_flags_disabled_by_default(self):
        """
        P2.2: Garante que SESSION_REFLECTION_ENABLED e MEMORY_HYGIENE_ENABLED
        permanecem False por padrão no código de configuração conforme § 85 do plano.
        """
        # Verifica se na classe Settings os defaults são False
        from config import Settings
        fresh_settings = Settings()
        self.assertFalse(fresh_settings.SESSION_REFLECTION_ENABLED)
        self.assertFalse(fresh_settings.MEMORY_HYGIENE_ENABLED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
