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

    # =========================================================================
    # REVISÃO TÉCNICA RODADA 2 — REGRESSÕES E NOVAS PROTEÇÕES
    # =========================================================================

    def test_rodada2_p0_user_replied_to_msg_id_no_unbound_local(self):
        """
        P0: Garante que user_replied_to_msg_id é inicializado no topo de process_incoming_batch
        e que a presença de oferta pendente não causa UnboundLocalError: reply_to_id.
        """
        # Cria oferta pendente
        rem_id = self.reminder_svc.offer_reminder(None, "reunião de teste", "2026-09-18T10:00:00", offer_message_id=555)
        self.assertIsNotNone(rem_id)

        # Mock de update do Telegram com reply_to_message
        mock_msg = MagicMock()
        mock_msg.message_id = 1001
        mock_msg.text = "sim, pode me lembrar"
        mock_msg.reply_to_message.message_id = 555
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        # Executa em loop assíncrono isolado com mocks para evitar envio real ao telegram
        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=2000)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):

            mock_plan.plan_message.return_value = {
                "intention": "chat",
                "direct_reminder": {"is_direct_reminder": False},
                "emotional_delta": {}
            }
            mock_plan.plan_heuristics.return_value = {
                "intention": "chat",
                "direct_reminder": {"is_direct_reminder": False},
                "emotional_delta": {}
            }
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Beleza amor!"))]
            )

            # Não pode levantar UnboundLocalError
            try:
                asyncio.run(bot.process_incoming_batch(
                    update=mock_update,
                    context=MagicMock(),
                    texto_usuario="sim, pode me lembrar"
                ))
            except UnboundLocalError as ule:
                self.fail(f"process_incoming_batch falhou com UnboundLocalError: {ule}")

    def test_rodada2_p1_3_strict_affirmations_require_context(self):
        """
        P1.3: Frases genéricas (pode ser, por favor, quero sim, fechou, manda bala, etc)
        NÃO devem confirmar lembretes se has_context=False.
        Apenas frases explícitas contendo 'lembr' confirmam sem contexto.
        """
        genericas = [
            "pode ser", "por favor", "quero sim", "fechou", "manda bala",
            "claro", "com certeza", "sim", "bora", "beleza", "ok", "show"
        ]
        for frase in genericas:
            res_sem_ctx = self.reminder_svc.parse_confirmation_response(frase, has_context=False)
            self.assertEqual(
                res_sem_ctx.get("action"), "none",
                f"Frase genérica '{frase}' NÃO deveria confirmar reminder sem contexto!"
            )

            res_com_ctx = self.reminder_svc.parse_confirmation_response(frase, has_context=True)
            self.assertEqual(
                res_com_ctx.get("action"), "confirm",
                f"Frase genérica '{frase}' DEVERIA confirmar reminder quando tem contexto!"
            )

        explicitas = [
            "me lembra", "pode me lembrar", "me lembra sim",
            "coloca o lembrete", "marca esse lembrete", "quero o lembrete"
        ]
        for frase in explicitas:
            res_sem_ctx = self.reminder_svc.parse_confirmation_response(frase, has_context=False)
            self.assertEqual(
                res_sem_ctx.get("action"), "confirm",
                f"Frase explícita '{frase}' DEVE confirmar mesmo sem contexto prévio!"
            )

    def test_rodada2_p1_1_concurrent_reflection_lease_and_unique_constraint(self):
        """
        P1.1: Valida proteção atômica contra reflexões de sessão concorrentes e duplicação:
        1. Unique index em resumos_conversa(start_conversation_id, end_conversation_id)
        2. claim_session_reflection impede concorrência
        3. salvar_resumo_conversa trata IntegrityError e retorna None
        """
        # 1. Testa claim_session_reflection
        claimed1 = self.db.claim_session_reflection(start_id=1, end_id=10, lease_seconds=60)
        self.assertTrue(claimed1, "Primeiro claim deveria ter sucesso")

        # Concorrente tentando o mesmo intervalo deve ser rejeitado pelo lease
        claimed2 = self.db.claim_session_reflection(start_id=1, end_id=10, lease_seconds=60)
        self.assertFalse(claimed2, "Claim concorrente para mesmo end_id dentro do lease deve ser rejeitado")

        # Libera o claim
        self.db.release_session_reflection_claim(end_id=10)

        # Agora pode adquirir novamente
        claimed3 = self.db.claim_session_reflection(start_id=1, end_id=10, lease_seconds=60)
        self.assertTrue(claimed3, "Claim deve ter sucesso após release")

        # 2. Salva resumo no banco para o intervalo 1-10
        rid1 = self.db.salvar_resumo_conversa(
            topic="Test", summary="Resumo 1",
            start_conversation_id=1, end_conversation_id=10
        )
        self.assertIsNotNone(rid1)

        # Inserção duplicada com mesmo intervalo deve retornar None sem estourar exceção
        rid2 = self.db.salvar_resumo_conversa(
            topic="Test 2", summary="Resumo 2",
            start_conversation_id=1, end_conversation_id=10
        )
        self.assertIsNone(rid2, "Segunda inserção para mesmo intervalo deve retornar None devido a índice UNIQUE")

        # Claim após resumo já gravado também deve retornar False
        self.db.release_session_reflection_claim(end_id=10)
        claimed4 = self.db.claim_session_reflection(start_id=1, end_id=10)
        self.assertFalse(claimed4, "Não deve permitir claim para intervalo já gravado")

    def test_rodada2_p2_direct_reminder_clarification_and_second_turn_completion(self):
        """
        P2: Lembrete direto sem horário válido:
        - Planner deve setar needs_clarification='direct_reminder_time' e salvar pending_direct_reminder.
        - Segundo turno: quando Patrick responde com o horário, bot completa o agendamento.
        """
        planner = InternalPlanner(db=self.db)

        # Turno 1: Patrick pede lembrete sem horário claro ("me lembra de pagar o boleto")
        vague_plan = {
            "intention": "direct_reminder",
            "direct_reminder": {
                "is_direct_reminder": True,
                "description": "pagar a conta de luz",
                "remind_at": None
            }
        }
        with patch("reminder_service.reminder_service", self.reminder_svc):
            plan_out = planner.apply_plan_effects(vague_plan, conversation_id=101)

        self.assertEqual(plan_out.get("needs_clarification"), "direct_reminder_time")
        self.assertEqual(plan_out.get("clarification_subject"), "pagar a conta de luz")

        # Verifica persistência no estado relacional
        st = self.db.get_estado_relacional()
        self.assertIn("pending_direct_reminder", st)

        # Turno 2: Patrick responde fornecendo a hora
        tomorrow_10 = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        mock_msg2 = MagicMock()
        mock_msg2.message_id = 1002
        mock_msg2.text = "amanhã às 10h"
        mock_msg2.reply_to_message = None
        mock_msg2.from_user.id = 12345
        mock_msg2.chat.id = 12345

        mock_update2 = MagicMock()
        mock_update2.message = mock_msg2
        mock_update2.effective_chat.id = 12345

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=2001)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"), \
             patch("planner.parse_iso_or_relative_datetime", return_value=tomorrow_10.isoformat()):

            mock_plan.plan_message.return_value = {
                "intention": "chat",
                "direct_reminder": {"is_direct_reminder": False},
                "emotional_delta": {}
            }
            mock_plan.plan_heuristics.return_value = {
                "intention": "chat",
                "direct_reminder": {"is_direct_reminder": False},
                "emotional_delta": {}
            }
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Beleza amor, agendado!"))]
            )

            asyncio.run(bot.process_incoming_batch(
                update=mock_update2,
                context=MagicMock(),
                texto_usuario="amanhã às 10h"
            ))

        # O pending_direct_reminder deve ter sido limpo
        st2 = self.db.get_estado_relacional()
        self.assertNotIn("pending_direct_reminder", st2)

        # O reminder confirmado deve existir
        active_rems = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(active_rems), 1)
        self.assertEqual(active_rems[0]["description"], "pagar a conta de luz")
        self.assertEqual(active_rems[0]["status"], "confirmed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
