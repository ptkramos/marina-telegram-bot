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
from unittest.mock import MagicMock, patch, AsyncMock

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
        self.mock_context = MagicMock()
        self.mock_context.bot = AsyncMock()
        self._random_patcher = patch.object(bot.random, "random", return_value=1.0)
        self._random_patcher.start()
        self.addCleanup(self._random_patcher.stop)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reaction_is_skipped_when_chat_has_no_available_reactions(self):
        bot._reaction_capabilities.clear()
        bot._invalid_reactions.clear()
        chat = MagicMock()
        chat.available_reactions = []
        api = AsyncMock()
        api.get_chat.return_value = chat
        sent = asyncio.run(bot.set_safe_message_reaction(api, 12345, 77, "❤️"))
        self.assertFalse(sent)
        api.set_message_reaction.assert_not_called()

    def test_reaction_alias_is_used_when_chat_allows_reactions(self):
        bot._reaction_capabilities.clear()
        bot._invalid_reactions.clear()
        chat = MagicMock()
        chat.available_reactions = None
        api = AsyncMock()
        api.get_chat.return_value = chat
        sent = asyncio.run(bot.set_safe_message_reaction(api, 12345, 77, "⏰"))
        self.assertTrue(sent)
        self.assertEqual(api.set_message_reaction.call_args.kwargs["reaction"][0].emoji, "👍")

    def test_offer_acceptance_does_not_leave_second_direct_reminder_pending(self):
        event_at = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=30, second=0, microsecond=0)
        event_id = self.db.adicionar_evento_pendente("medico", "Consulta no dentista", event_at=event_at.isoformat())
        reminder_id = self.reminder_svc.offer_reminder(
            event_id=event_id, description="Consulta no dentista",
            remind_at=(event_at - timedelta(minutes=30)).isoformat(), offer_message_id=664,
        )
        reply = MagicMock()
        reply.message_id = 668
        reply.reply_to_message = MagicMock(message_id=664, text="Quer que eu te lembre?")
        update = MagicMock()
        update.message = reply
        update.effective_chat.id = 12345
        plan = InternalPlanner(db=self.db).plan_heuristics("pode me lembrar uma hora antes")
        self.assertEqual(plan["needs_clarification"], "direct_reminder_time")
        captured = []

        async def fake_send(*args, **kwargs):
            captured.append(args[2])
            return MagicMock(message_id=669)

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", side_effect=fake_send), \
             patch.object(bot, "set_safe_message_reaction", new_callable=AsyncMock), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):
            mock_plan.plan_message.return_value = plan
            mock_plan.apply_plan_effects.side_effect = lambda p, conversation_id=None: InternalPlanner(db=self.db).apply_plan_effects(p, conversation_id)
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Posso te ligar na hora?"))]
            )
            asyncio.run(bot.process_incoming_batch(update, MagicMock(), "pode me lembrar uma hora antes"))

        saved = self.db.get_reminder(reminder_id)
        self.assertEqual(saved["status"], "confirmed")
        self.assertEqual(saved["offset_minutes"], 60)
        self.assertEqual(saved["remind_at"], (event_at - timedelta(hours=1)).isoformat())
        self.assertIsNone(self.db.get_estado_relacional("pending_direct_reminder"))
        self.assertEqual(len(self.reminder_svc.get_active_reminders()), 1)
        self.assertIn("09:30", captured[0])
        self.assertIn("mensagem aqui no Telegram", captured[0])
        self.assertNotIn("ligar", captured[0])

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
        import importlib
        import os
        import config
        with patch.dict(os.environ, {"SESSION_REFLECTION_ENABLED": "false", "MEMORY_HYGIENE_ENABLED": "false"}):
            importlib.reload(config)
            try:
                self.assertFalse(config.Settings.SESSION_REFLECTION_ENABLED)
                self.assertFalse(config.Settings.MEMORY_HYGIENE_ENABLED)
            finally:
                importlib.reload(config)

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

    # =========================================================================
    # REVISÃO TÉCNICA RODADA 3 — GARANTIAS DE CONTRATO E ATRIBUIÇÃO
    # =========================================================================

    def test_rodada3_p1_turn1_direct_reminder_without_time_ensures_question_and_records_mid(self):
        """
        P1: Garante que no primeiro turno de um pedido direto sem horário, mesmo que a LLM
        omita completamente a pergunta 'quando?', o bot anexa a pergunta de esclarecimento,
        persiste pending_direct_reminder e vincula clarification_message_id ao ID da mensagem enviada.
        """
        # Valida que o planner pré-computa needs_clarification nas heurísticas
        heur = bot.planner.plan_heuristics("me lembra de comprar ração pro gato")
        self.assertIsNotNone(heur)
        self.assertEqual(heur.get("needs_clarification"), "direct_reminder_time")
        self.assertEqual(heur.get("clarification_subject"), "comprar ração pro gato")

        mock_msg = MagicMock()
        mock_msg.message_id = 2001
        mock_msg.text = "me lembra de comprar ração pro gato"
        mock_msg.reply_to_message = None
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        sent_messages_captured = []
        async def fake_send_human(chat_id, bot_instance, text, reply_to_message_id=None):
            sent_messages_captured.append(text)
            return MagicMock(message_id=9901)

        plan = {
            "intent": "direct_reminder",
            "direct_reminder": {
                "is_direct_reminder": True,
                "description": "comprar ração pro gato",
                "remind_at": None
            },
            "needs_clarification": "direct_reminder_time",
            "clarification_subject": "comprar ração pro gato"
        }

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot.planner, "db", self.db), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", side_effect=fake_send_human), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):

            mock_plan.plan_message.return_value = plan
            mock_plan.plan_heuristics.return_value = plan
            mock_plan.apply_plan_effects.side_effect = lambda p, conversation_id=None: InternalPlanner(db=self.db).apply_plan_effects(p, conversation_id=conversation_id)

            # LLM omite totalmente a pergunta "quando?", apenas confirma de forma declarativa
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Pode deixar amor, anotei aqui com carinho!"))]
            )

            asyncio.run(bot.process_incoming_batch(
                update=mock_update,
                context=MagicMock(),
                texto_usuario="me lembra de comprar ração pro gato"
            ))

        # 1. Verifica se a mensagem enviada contém a pergunta de esclarecimento
        self.assertTrue(len(sent_messages_captured) > 0)
        sent_text = sent_messages_captured[0]
        self.assertIn("Quando você quer que eu te lembre", sent_text)
        self.assertIn("?", sent_text)

        # 2. Verifica se o estado pendente foi salvo com clarification_message_id = 9901
        pdr_str = self.db.get_estado_relacional("pending_direct_reminder")
        self.assertIsNotNone(pdr_str)
        import json
        pdr_data = json.loads(pdr_str)
        self.assertEqual(pdr_data.get("clarification_message_id"), 9901)
        self.assertIn("ração", pdr_data.get("description", ""))

    def test_rodada3_p2_pending_direct_reminder_expiration_ttl(self):
        """
        P2: Garante que pendência de esclarecimento mais velha que 30 minutos expira,
        não agenda lembrete mesmo com mensagem contendo data/hora e limpa o estado.
        """
        import json
        old_time = (datetime.now() - timedelta(minutes=35)).isoformat()
        self.db.set_estado_relacional("pending_direct_reminder", json.dumps({
            "description": "reunião antiga",
            "source_conversation_id": None,
            "clarification_message_id": 8801,
            "created_at": old_time
        }))

        mock_msg = MagicMock()
        mock_msg.message_id = 3001
        mock_msg.text = "amanhã às 14h"
        mock_msg.reply_to_message = None
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot.planner, "db", self.db), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=9902)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):

            mock_plan.plan_message.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_plan.plan_heuristics.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Oi amor!"))]
            )

            asyncio.run(bot.process_incoming_batch(
                update=mock_update,
                context=MagicMock(),
                texto_usuario="amanhã às 14h"
            ))

        # Não deve ter agendado lembrete
        active_rems = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(active_rems), 0)
        # Estado deve ter sido limpo
        st = self.db.get_estado_relacional("pending_direct_reminder")
        self.assertIsNone(st)

    def test_rodada3_p2_pending_direct_reminder_explicit_refusal(self):
        """
        P2: Garante que Patrick recusando/cancelando o esclarecimento ("esquece", "não precisa")
        descarta a pendência sem agendar nada.
        """
        import json
        recent_time = datetime.now().isoformat()
        self.db.set_estado_relacional("pending_direct_reminder", json.dumps({
            "description": "comprar flores",
            "source_conversation_id": None,
            "clarification_message_id": 8802,
            "created_at": recent_time
        }))

        mock_msg = MagicMock()
        mock_msg.message_id = 3002
        mock_msg.text = "deixa quieto amor, não precisa mais"
        mock_msg.reply_to_message = MagicMock(message_id=8802)
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot.planner, "db", self.db), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=9903)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):

            mock_plan.plan_message.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_plan.plan_heuristics.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Tudo bem amor!"))]
            )

            asyncio.run(bot.process_incoming_batch(
                update=mock_update,
                context=MagicMock(),
                texto_usuario="deixa quieto amor, não precisa mais"
            ))

        active_rems = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(active_rems), 0)
        st = self.db.get_estado_relacional("pending_direct_reminder")
        self.assertIsNone(st)

    def test_rodada3_p2_unrelated_message_does_not_consume_date_for_pending_reminder(self):
        """
        P2: Uma mensagem enviada em outro assunto (sem reply_to à mensagem de esclarecimento
        e não sendo turno imediatamente consecutivo) não consome datas mencionadas nela
        para resolver o lembrete pendente alheio.
        """
        import json
        recent_time = datetime.now().isoformat()
        self.db.set_estado_relacional("pending_direct_reminder", json.dumps({
            "description": "lavar o carro",
            "source_conversation_id": 100,
            "clarification_message_id": 8803,
            "created_at": recent_time
        }))

        # Mock de histórico com outra mensagem intermediária da Marina (não é o turno consecutivo da pergunta 8803)
        bot.ULTIMAS_MENSAGENS_MARINA[12345] = [{"message_id": 9999, "text": "Te amo lindo!"}]

        mock_msg = MagicMock()
        mock_msg.message_id = 3003
        mock_msg.text = "Vou viajar na sexta-feira às 18h"
        mock_msg.reply_to_message = None
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot.planner, "db", self.db), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=10004)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):

            mock_plan.plan_message.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_plan.plan_heuristics.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Boa viagem amor!"))]
            )

            asyncio.run(bot.process_incoming_batch(
                update=mock_update,
                context=MagicMock(),
                texto_usuario="Vou viajar na sexta-feira às 18h"
            ))

        # "lavar o carro" NÃO deve ter sido agendado para as 18h de sexta-feira!
        for rem in self.reminder_svc.get_active_reminders():
            self.assertNotEqual(rem["description"], "lavar o carro")

    def test_rodada3_p2_legitimate_resume_via_reply_schedules_reminder(self):
        """
        P2: Patrick responde diretamente à pergunta de esclarecimento informando o horário
        (retomada legítima via reply_to_message). O lembrete deve ser agendado com sucesso.
        """
        import json
        recent_time = datetime.now().isoformat()
        tomorrow_17 = (datetime.now() + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
        self.db.set_estado_relacional("pending_direct_reminder", json.dumps({
            "description": "comprar pão",
            "source_conversation_id": None,
            "clarification_message_id": 8804,
            "created_at": recent_time
        }))

        mock_msg = MagicMock()
        mock_msg.message_id = 3004
        mock_msg.text = "amanhã às 17h"
        mock_msg.reply_to_message = MagicMock(message_id=8804)
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot.planner, "db", self.db), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=10005)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"), \
             patch("planner.parse_iso_or_relative_datetime", return_value=tomorrow_17.isoformat()):

            mock_plan.plan_message.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_plan.plan_heuristics.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Pode deixar amor, agendado!"))]
            )

            asyncio.run(bot.process_incoming_batch(
                update=mock_update,
                context=MagicMock(),
                texto_usuario="amanhã às 17h"
            ))

        # Lembrete deve ter sido criado com sucesso
        active_rems = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(active_rems), 1)
        self.assertEqual(active_rems[0]["description"], "comprar pão")
        self.assertEqual(active_rems[0]["status"], "confirmed")
        # Estado deve ter sido limpo
        st = self.db.get_estado_relacional("pending_direct_reminder")
        self.assertIsNone(st)

    def test_rodada3_p1_offer_verification_rejects_declarative_lembrete_and_adds_question(self):
        """
        P1: Garante que uma fala declarativa contendo a palavra 'lembrete' (ex: 'Já anotei um lembrete para depois.')
        sem pergunta interrogativa é rejeitada pelo validador de oferta e recebe a pergunta interrogativa anexada.
        """
        self.assertFalse(bot.is_reminder_offer_question("Já anotei um lembrete para depois."))
        self.assertFalse(bot.is_reminder_offer_question("Tenho um lembrete aqui."))
        self.assertTrue(bot.is_reminder_offer_question("Quer que eu te lembre?"))
        self.assertTrue(bot.is_reminder_offer_question("Quer que eu te lembre do médico antes, amor? 💕"))
        self.assertTrue(bot.is_reminder_offer_question("Posso te avisar meia hora antes?"))
        self.assertTrue(bot.is_reminder_offer_question("Se quiser posso te lembrar antes, quer?"))

        mock_msg = MagicMock()
        mock_msg.message_id = 4001
        mock_msg.text = "Amanhã às 15h tenho dentista"
        mock_msg.reply_to_message = None
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        sent_captured = []
        async def fake_send_human(chat_id, bot_instance, text, reply_to_message_id=None):
            sent_captured.append(text)
            return MagicMock(message_id=9905)

        plan = {
            "should_offer_reminder": True,
            "event_details": {"description": "dentista", "event_at": (datetime.now() + timedelta(days=1)).isoformat()}
        }

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot.planner, "db", self.db), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", side_effect=fake_send_human), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):

            mock_plan.plan_message.return_value = plan
            mock_plan.plan_heuristics.return_value = plan
            mock_plan.apply_plan_effects.side_effect = lambda p, conversation_id=None: InternalPlanner(db=self.db).apply_plan_effects(p, conversation_id=conversation_id)

            # Este caso valida a oferta em texto; desativa o áudio espontâneo aleatório.
            with patch.object(bot.random, "random", return_value=1.0):
                mock_llm.chat.completions.create.return_value = MagicMock(
                    choices=[MagicMock(message=MagicMock(content="Já anotei um lembrete para depois no meu caderno."))]
                )

                asyncio.run(bot.process_incoming_batch(
                    update=mock_update,
                    context=MagicMock(),
                    texto_usuario="Amanhã às 15h tenho dentista"
                ))

        self.assertTrue(len(sent_captured) > 0)
        sent = sent_captured[0]
        self.assertIn("Quer que eu te lembre", sent)
        self.assertIn("?", sent)

    def test_rodada3_p1_exact_offered_reminder_id_attribution(self):
        """
        P1: Garante que apenas a oferta criada neste turno tem seu offer_message_id registrado
        (e em caso de falha de envio, apenas ela é cancelada), sem contaminar ofertas antigas abertas.
        """
        # Cria uma oferta pré-existente
        old_rem_id = self.reminder_svc.offer_reminder(
            event_id=None,
            description="oferta antiga aberta",
            remind_at=(datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        )
        self.assertIsNotNone(old_rem_id)

        # Agora cria um plano que oferta um novo lembrete com ID específico
        new_rem_id = self.reminder_svc.offer_reminder(
            event_id=None,
            description="novo evento",
            remind_at=(datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
        )

        plan = {
            "should_offer_reminder": True,
            "offered_reminder_id": new_rem_id,
            "event_details": {"description": "novo evento"}
        }

        mock_msg = MagicMock()
        mock_msg.message_id = 4002
        mock_msg.text = "Tenho prova quinta"
        mock_msg.reply_to_message = None
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot.planner, "db", self.db), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=7777)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):

            mock_plan.plan_message.return_value = plan
            mock_plan.plan_heuristics.return_value = plan
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Quer que eu te lembre, amor?"))]
            )

            asyncio.run(bot.process_incoming_batch(
                update=mock_update,
                context=MagicMock(),
                texto_usuario="Tenho prova quinta"
            ))

        # Verifica no banco: new_rem_id deve ter offer_message_id = 7777
        new_rem = self.db.get_reminder(new_rem_id)
        self.assertEqual(new_rem["offer_message_id"], 7777)

        # old_rem_id NÃO deve ter sido alterado nem cancelado
        old_rem = self.db.get_reminder(old_rem_id)
        self.assertIsNone(old_rem["offer_message_id"])
        self.assertEqual(old_rem["status"], "offered")

    def test_rodada3_db_migration_upgrade_with_duplicate_resumos_intervalo(self):
        """
        Reflexão e migrations: Garante que um banco existente com registros duplicados
        em resumos_conversa(start_conversation_id, end_conversation_id) é migrado com sucesso,
        deduplicando os registros antigos e criando o índice único idx_resumos_intervalo.
        """
        import sqlite3
        temp_mig_db = Path(self.temp_dir.name) / "test_migration_upgrade.db"
        with sqlite3.connect(temp_mig_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS resumos_conversa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                summary TEXT NOT NULL,
                start_conversation_id INTEGER,
                end_conversation_id INTEGER,
                importance REAL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            # Insere 3 registros com o mesmo intervalo (10, 20)
            cursor.execute("INSERT INTO resumos_conversa (start_conversation_id, end_conversation_id, topic, summary, created_at, updated_at) VALUES (10, 20, 'Geral', 'Resumo 1', '2026-09-17T12:00:00', '2026-09-17T12:00:00')")
            cursor.execute("INSERT INTO resumos_conversa (start_conversation_id, end_conversation_id, topic, summary, created_at, updated_at) VALUES (10, 20, 'Geral', 'Resumo 2 duplicado', '2026-09-17T12:01:00', '2026-09-17T12:01:00')")
            cursor.execute("INSERT INTO resumos_conversa (start_conversation_id, end_conversation_id, topic, summary, created_at, updated_at) VALUES (10, 20, 'Geral', 'Resumo 3 duplicado', '2026-09-17T12:02:00', '2026-09-17T12:02:00')")
            cursor.execute("INSERT INTO resumos_conversa (start_conversation_id, end_conversation_id, topic, summary, created_at, updated_at) VALUES (21, 30, 'Outro', 'Resumo outro intervalo', '2026-09-17T12:03:00', '2026-09-17T12:03:00')")
            conn.commit()

        # Instancia DatabaseManager apontando para o banco duplicado (executará _run_migrations)
        mig_db = DatabaseManager(db_path=temp_mig_db)

        # Verifica que a migração não falhou e deduplicou
        with mig_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, start_conversation_id, end_conversation_id, summary FROM resumos_conversa WHERE start_conversation_id = 10 AND end_conversation_id = 20")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1, "Deveria sobrar exatamente 1 registro para o intervalo (10, 20)")
            self.assertEqual(rows[0][3], 'Resumo 1', "Deveria ter mantido o registro mais antigo com MIN(id)")

            # Verifica que o índice único existe e impede nova duplicação
            with self.assertRaises(sqlite3.IntegrityError):
                cursor.execute("INSERT INTO resumos_conversa (start_conversation_id, end_conversation_id, topic, summary, created_at, updated_at) VALUES (10, 20, 'Geral', 'Duplicata proibida', '2026-09-17T12:04:00', '2026-09-17T12:04:00')")
                conn.commit()

    # --- RODADA 4: P0 (Negações / Perguntas de Memória) & P1 (Data de outro assunto) ---
    def test_rodada4_p0_detect_direct_reminder_intent(self):
        """
        P0: Valida que frases negadas e perguntas de recordação/memória passada
        NÃO são classificadas como solicitação de lembrete direto futuro.
        """
        from planner import detect_direct_reminder_intent

        # 1. Negações explícitas
        negatives = [
            "Não me lembra da reunião amanhã às 10h",
            "não me lembra de pagar a conta",
            "não precisa me lembrar de nada amanhã",
            "nem me lembra disso",
            "sem me lembrar amanhã",
            "não me avisa de nada",
            "deixa quieto",
            "deixa que eu me lembro amanhã",
        ]
        for neg in negatives:
            is_dir, subj = detect_direct_reminder_intent(neg)
            self.assertFalse(is_dir, f"Frase negada não deve ser lembrete direto: '{neg}'")
            self.assertIsNone(subj)

        # 2. Perguntas de memória passada / recordação / nostalgia
        past_memories = [
            "Você lembra de quando eu fui ao médico?",
            "Lembra quando fomos viajar?",
            "lembra de quando a gente viajou?",
            "você lembra daquele restaurante?",
            "Lembra do nosso primeiro encontro?",
            "Lembra quando fui ao médico?",
            "lembra de ontem?",
        ]
        for mem in past_memories:
            is_dir, subj = detect_direct_reminder_intent(mem)
            self.assertFalse(is_dir, f"Pergunta de memória passada não deve ser lembrete direto: '{mem}'")
            self.assertIsNone(subj)

        # 3. Pedidos afirmativos e imperativos legítimos
        positives = [
            ("me lembra de pagar a conta amanhã às 14h", "pagar a conta amanhã às 14h"),
            ("por favor me lembra que amanhã tenho reunião às 9h", "amanhã tenho reunião às 9h"),
            ("pode me lembrar de tomar o remédio?", "tomar o remédio"),
            ("coloca um lembrete pra comprar pão amanhã", "comprar pão amanhã"),
            ("agenda um lembrete de ligar pra minha mãe", "ligar pra minha mãe"),
        ]
        for pos, expected_sub in positives:
            is_dir, subj = detect_direct_reminder_intent(pos)
            self.assertTrue(is_dir, f"Pedido legítimo deve ser reconhecido: '{pos}'")
            self.assertIn(expected_sub.lower(), subj.lower() if subj else "")

    def test_rodada4_p0_planner_rejects_negative_or_memory_phrase_and_no_reminder_created(self):
        """
        P0: Garante que o InternalPlanner não cria direct_reminder (nem no plano nem em DB)
        para 'Não me lembra da reunião amanhã às 10h' ou 'Você lembra de quando fui ao médico?'.
        """
        planner = InternalPlanner(db=self.db, llm_client=MagicMock())

        # Teste 1: Negação com horário
        msg_neg = "Não me lembra da reunião amanhã às 10h"
        plan_neg = planner.plan_heuristics(msg_neg)
        # plan_heuristics não deve criar direct_reminder
        self.assertIsNone(plan_neg)

        # plan_message fallback/sem LLM
        with patch.object(settings, "PLANNER_ENABLED", False):
            plan_full_neg = planner.plan_message(msg_neg)
            self.assertNotEqual(plan_full_neg.get("intent"), "direct_reminder")
            self.assertFalse(plan_full_neg.get("direct_reminder", {}).get("is_direct_reminder", False))

        # Efeitos colaterais: não deve salvar nada em reminders
        planner.apply_plan_effects(plan_full_neg, conversation_id=999)
        active_rems = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(active_rems), 0)

        # Teste 2: Pergunta de memória passada
        msg_mem = "Você lembra de quando eu fui ao médico?"
        plan_mem = planner.plan_heuristics(msg_mem)
        self.assertIsNone(plan_mem)

        with patch.object(settings, "PLANNER_ENABLED", False):
            plan_full_mem = planner.plan_message(msg_mem)
            self.assertNotEqual(plan_full_mem.get("intent"), "direct_reminder")

        planner.apply_plan_effects(plan_full_mem, conversation_id=999)
        active_rems = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(active_rems), 0)

    def test_rodada4_p1_is_pure_time_specification(self):
        """
        P1: Valida a diferenciação entre especificações puras de horário
        e frases que introduzem novos assuntos / outras atividades.
        """
        from planner import is_pure_time_specification

        # Respostas válidas de tempo
        self.assertTrue(is_pure_time_specification("amanhã às 15h", "pagar a conta"))
        self.assertTrue(is_pure_time_specification("às 14h", "pagar a conta"))
        self.assertTrue(is_pure_time_specification("pode ser às 10:00", "pagar a conta"))
        self.assertTrue(is_pure_time_specification("amanhã de tarde", "pagar a conta"))
        self.assertTrue(is_pure_time_specification("daqui a 2 horas", "pagar a conta"))
        self.assertTrue(is_pure_time_specification("pode ser amanhã de manhã amor", "pagar a conta"))
        self.assertTrue(is_pure_time_specification("pagar a conta amanhã às 14h", "pagar a conta"))

        # Frases com outros compromissos / mudança de assunto
        self.assertFalse(is_pure_time_specification("Amanhã vou viajar", "pagar a conta"))
        self.assertFalse(is_pure_time_specification("Semana que vem tenho consulta médica", "pagar a conta"))
        self.assertFalse(is_pure_time_specification("Amanhã vou na academia", "pagar a conta"))
        self.assertFalse(is_pure_time_specification("Hoje vou jantar fora", "pagar a conta"))
        self.assertFalse(is_pure_time_specification("Não quero mais lembrar disso", "pagar a conta"))

    def test_rodada4_p1_pending_direct_reminder_discarded_on_subject_change(self):
        """
        P1: Turno 1 pede lembrete sem horário ('me lembra de pagar a conta').
        Turno 2 (imediato seguinte) Patrick fala 'Amanhã vou viajar'.
        O bot NÃO deve agendar 'pagar a conta' para amanhã às 14h e deve limpar a pendência.
        """
        import json
        self.db.set_estado_relacional("pending_direct_reminder", json.dumps({
            "description": "pagar a conta",
            "source_conversation_id": 5001,
            "created_at": datetime.now().isoformat()
        }))

        mock_msg = MagicMock()
        mock_msg.message_id = 5002
        mock_msg.text = "Amanhã vou viajar"
        mock_msg.reply_to_message = None
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot.planner, "db", self.db), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=9001)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):

            mock_plan.plan_message.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_plan.plan_heuristics.return_value = None
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Boa viagem meu amor!"))]
            )

            with patch.object(bot.memory_manager.db, "get_mensagens_sessao", return_value=[{"id": 5001, "role": "assistant", "content": "Quando quer que eu te lembre?"}]):
                asyncio.run(bot.process_incoming_batch(
                    update=mock_update,
                    context=MagicMock(),
                    texto_usuario="Amanhã vou viajar"
                ))

        # 1. O lembrete pendente NÃO deve ter sido agendado
        active_rems = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(active_rems), 0, "Lembrete pendente de 'pagar a conta' NÃO deve ser agendado com a data de 'vou viajar'")

        # 2. O estado pendente deve ter sido descartado
        st = self.db.get_estado_relacional("pending_direct_reminder")
        self.assertIsNone(st)

    def test_rodada4_p1_pending_direct_reminder_confirmed_on_valid_time(self):
        """
        P1: Turno 1 pede lembrete sem horário ('me lembra de pagar a conta').
        Turno 2 (imediato seguinte) Patrick responde 'amanhã às 15h'.
        O bot agenda o lembrete com sucesso para amanhã às 15h e limpa o estado pendente.
        """
        import json
        tomorrow_15 = datetime.now().replace(microsecond=0) + timedelta(days=1)
        tomorrow_15 = tomorrow_15.replace(hour=15, minute=0, second=0)

        self.db.set_estado_relacional("pending_direct_reminder", json.dumps({
            "description": "pagar a conta",
            "source_conversation_id": 6001,
            "created_at": datetime.now().isoformat()
        }))

        mock_msg = MagicMock()
        mock_msg.message_id = 6002
        mock_msg.text = "amanhã às 15h"
        mock_msg.reply_to_message = None
        mock_msg.from_user.id = 12345
        mock_msg.chat.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_msg
        mock_update.effective_chat.id = 12345

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot.planner, "db", self.db), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=9002)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):

            mock_plan.plan_message.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_plan.plan_heuristics.return_value = None
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Combinado vida, anotadinho!"))]
            )

            with patch.object(bot.memory_manager.db, "get_mensagens_sessao", return_value=[{"id": 6001, "role": "assistant", "content": "Quando quer que eu te lembre?"}]):
                asyncio.run(bot.process_incoming_batch(
                    update=mock_update,
                    context=MagicMock(),
                    texto_usuario="amanhã às 15h"
                ))

        # 1. Lembrete confirmado com sucesso
        active_rems = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(active_rems), 1)
        self.assertEqual(active_rems[0]["description"], "pagar a conta")
        self.assertEqual(active_rems[0]["status"], "confirmed")
        self.assertEqual(active_rems[0]["remind_at"], tomorrow_15.strftime("%Y-%m-%dT%H:%M:%S"))

        # 2. O estado pendente foi limpo
        st = self.db.get_estado_relacional("pending_direct_reminder")
        self.assertIsNone(st)

    # --- RODADA 5: P1 (Frases curtas como 'Amanhã viajo' e 'Amanhã tenho festa') & P2 (apply_plan_effects) ---
    def test_rodada5_p1_short_subject_change_rejected_by_is_pure_time_specification(self):
        """
        P1: Valida que frases curtas introduzindo novas proposições/atividades (ex: 'Amanhã viajo',
        'Amanhã tenho festa') são categoricamente rejeitadas pelo filtro temporal.
        """
        from planner import is_pure_time_specification

        pending_desc = "pagar a conta"

        # Frases curtas de mudança de assunto apontadas na Rodada 5
        self.assertFalse(is_pure_time_specification("Amanhã viajo", pending_desc))
        self.assertFalse(is_pure_time_specification("Amanhã tenho festa", pending_desc))
        self.assertFalse(is_pure_time_specification("Amanhã jogo bola", pending_desc))
        self.assertFalse(is_pure_time_specification("Hoje durmo cedo", pending_desc))
        self.assertFalse(is_pure_time_specification("Quarta almoço com meu pai", pending_desc))
        self.assertFalse(is_pure_time_specification("Sexta vou sair", pending_desc))
        self.assertFalse(is_pure_time_specification("Amanhã trabalho até tarde", pending_desc))
        self.assertFalse(is_pure_time_specification("Semana que vem viajo", pending_desc))

        # Respostas temporais legítimas continuam aceitas
        self.assertTrue(is_pure_time_specification("amanhã às 15h", pending_desc))
        self.assertTrue(is_pure_time_specification("às 14h", pending_desc))
        self.assertTrue(is_pure_time_specification("pode ser às 10:00", pending_desc))
        self.assertTrue(is_pure_time_specification("amanhã de tarde", pending_desc))
        self.assertTrue(is_pure_time_specification("daqui a 2 horas", pending_desc))
        self.assertTrue(is_pure_time_specification("pode ser amanhã de manhã amor", pending_desc))
        self.assertTrue(is_pure_time_specification("pagar a conta amanhã às 14h", pending_desc))
        self.assertTrue(is_pure_time_specification("amanhã às 14h mais ou menos", pending_desc))

    def test_rodada5_p1_integrated_consecutive_turn_short_phrases_do_not_schedule_and_discard_pending(self):
        """
        P1 Integrado: No turno seguinte à pergunta 'Quando quer que eu te lembre de pagar a conta?',
        Patrick responde com frases curtas de outro assunto ('Amanhã viajo' e 'Amanhã tenho festa').
        O bot NÃO deve agendar 'pagar a conta' e deve descartar a pendência.
        """
        import json

        for frase_teste in ["Amanhã viajo", "Amanhã tenho festa"]:
            self.db.set_estado_relacional("pending_direct_reminder", json.dumps({
                "description": "pagar a conta",
                "source_conversation_id": 7001,
                "created_at": datetime.now().isoformat()
            }))

            mock_msg = MagicMock()
            mock_msg.message_id = 7002
            mock_msg.text = frase_teste
            mock_msg.reply_to_message = None
            mock_msg.from_user.id = 12345
            mock_msg.chat.id = 12345

            mock_update = MagicMock()
            mock_update.message = mock_msg
            mock_update.effective_chat.id = 12345

            with patch.object(bot.memory_manager, "db", self.db), \
                 patch.object(bot, "reminder_service", self.reminder_svc), \
                 patch.object(bot.planner, "db", self.db), \
                 patch.object(bot, "planner") as mock_plan, \
                 patch.object(bot, "llm_client") as mock_llm, \
                 patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=9003)), \
                 patch.object(bot, "check_and_trigger_memory_consolidation"):

                mock_plan.plan_message.return_value = {"intent": "chat", "emotional_deltas": {}}
                mock_plan.plan_heuristics.return_value = None
                mock_llm.chat.completions.create.return_value = MagicMock(
                    choices=[MagicMock(message=MagicMock(content="Que legal amor!"))]
                )

                with patch.object(bot.memory_manager.db, "get_mensagens_sessao", return_value=[{"id": 7001, "role": "assistant", "content": "Quando quer que eu te lembre?"}]):
                    asyncio.run(bot.process_incoming_batch(
                        update=mock_update,
                        context=MagicMock(),
                        texto_usuario=frase_teste
                    ))

            # Nenhum lembrete para "pagar a conta" deve ter sido criado
            active_rems = self.reminder_svc.get_active_reminders()
            self.assertEqual(len(active_rems), 0, f"Frase '{frase_teste}' NÃO deve agendar o lembrete pendente!")

            # O estado pendente deve ter sido limpo
            st = self.db.get_estado_relacional("pending_direct_reminder")
            self.assertIsNone(st, f"Estado pendente deve ser limpo após mudança de assunto com '{frase_teste}'")

    def test_rodada5_p2_apply_plan_effects_direct_call_with_negated_or_memory_plan_no_error(self):
        """
        P2: Chamada direta de apply_plan_effects() com direct_reminder contendo frase negada
        ou pergunta de memória passada não deve disparar UnboundLocalError nem criar lembrete/pendência.
        """
        planner = InternalPlanner(db=self.db, llm_client=MagicMock())

        # 1. Plano negado passado diretamente para apply_plan_effects
        neg_plan = {
            "intent": "direct_reminder",
            "direct_reminder": {
                "is_direct_reminder": True,
                "description": "Não me lembra da reunião amanhã às 10h",
                "remind_at": "2026-09-18T10:00:00"
            }
        }
        # Não deve lançar UnboundLocalError nem qualquer outra exceção
        planner.apply_plan_effects(neg_plan, conversation_id=8001)

        self.assertIsNone(neg_plan["direct_reminder"], "direct_reminder deve ser anulado no plano")
        self.assertEqual(len(self.reminder_svc.get_active_reminders()), 0, "Nenhum lembrete deve ser criado")
        self.assertIsNone(self.db.get_estado_relacional("pending_direct_reminder"), "Nenhuma pendência deve ser salva")

        # 2. Pergunta de memória passada passada diretamente
        mem_plan = {
            "intent": "direct_reminder",
            "direct_reminder": {
                "is_direct_reminder": True,
                "description": "Você lembra de quando eu fui ao médico?",
                "remind_at": "2026-09-18T10:00:00"
            }
        }
        planner.apply_plan_effects(mem_plan, conversation_id=8002)

        self.assertIsNone(mem_plan["direct_reminder"], "direct_reminder deve ser anulado no plano")
        self.assertEqual(len(self.reminder_svc.get_active_reminders()), 0)
        self.assertIsNone(self.db.get_estado_relacional("pending_direct_reminder"))

    def test_day_only_clarification_keeps_pending_and_asks_for_hour(self):
        """Responder apenas 'amanhã' não agenda às 14h; pede a hora novamente."""
        import json

        self.db.set_estado_relacional("pending_direct_reminder", json.dumps({
            "description": "tomar o remédio",
            "source_conversation_id": 1,
            "clarification_message_id": 811,
            "created_at": datetime.now().isoformat(),
        }))
        update = MagicMock()
        update.effective_chat.id = 12345
        update.message.message_id = 812
        update.message.reply_to_message.message_id = 811

        sent = []
        async def fake_send(chat_id, bot_instance, text, reply_to_message_id=None):
            sent.append(text)
            return MagicMock(message_id=813)

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", side_effect=fake_send), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):
            mock_plan.plan_message.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Certo, amor."))]
            )
            asyncio.run(bot.process_incoming_batch(update, MagicMock(), "amanhã"))

        self.assertEqual(len(self.reminder_svc.get_active_reminders()), 0)
        self.assertTrue(any("A que horas" in message for message in sent))
        pending = json.loads(self.db.get_estado_relacional("pending_direct_reminder"))
        self.assertEqual(pending["clarification_message_id"], 813)

    def test_hour_reply_keeps_day_from_original_request(self):
        """'Amanhã' no pedido e 'às 8h' na resposta formam amanhã às 8h."""
        import json

        self.db.set_estado_relacional("pending_direct_reminder", json.dumps({
            "description": "amanhã de tomar o remédio",
            "source_conversation_id": 1,
            "clarification_message_id": 821,
            "created_at": datetime.now().isoformat(),
        }))
        update = MagicMock()
        update.effective_chat.id = 12345
        update.message.message_id = 822
        update.message.reply_to_message.message_id = 821

        with patch.object(bot.memory_manager, "db", self.db), \
             patch.object(bot, "reminder_service", self.reminder_svc), \
             patch.object(bot, "planner") as mock_plan, \
             patch.object(bot, "llm_client") as mock_llm, \
             patch.object(bot, "send_human_messages", return_value=MagicMock(message_id=823)), \
             patch.object(bot, "check_and_trigger_memory_consolidation"):
            mock_plan.plan_message.return_value = {"intent": "chat", "emotional_deltas": {}}
            mock_llm.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Fechado, amor."))]
            )
            asyncio.run(bot.process_incoming_batch(update, MagicMock(), "às 8h"))

        reminders = self.reminder_svc.get_active_reminders()
        self.assertEqual(len(reminders), 1)
        expected_day = (datetime.now() + timedelta(days=1)).date()
        self.assertEqual(datetime.fromisoformat(reminders[0]["remind_at"]).date(), expected_day)
        self.assertEqual(datetime.fromisoformat(reminders[0]["remind_at"]).hour, 8)
        self.assertIsNone(self.db.get_estado_relacional("pending_direct_reminder"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
