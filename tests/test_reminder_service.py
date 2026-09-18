"""
Testes unitários e de integração para Smart Reminders (Lembretes Inteligentes com Consentimento).
Marina Salles — Release 3.7.0
"""
import sys
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from reminder_service import ReminderService
from config import settings


class TestReminderService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_reminders.db"
        self.db = DatabaseManager(db_path=self.db_path)
        self.service = ReminderService(db=self.db)

    def tearDown(self):
        del self.service
        del self.db
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_reminder_offer_and_confirmation_lifecycle(self):
        """Oferta de lembrete -> consentimento do Patrick ('sim') -> status confirmed."""
        ev_id = self.db.adicionar_evento_pendente(
            event_type="medico",
            description="Consulta com dentista",
            event_at="2026-09-20T15:00:00",
            follow_up_after="2026-09-20T17:00:00"
        )

        # 1. Marina oferece lembrete
        rem_id = self.service.offer_reminder(
            event_id=ev_id,
            description="Consulta com dentista",
            remind_at="2026-09-20T14:30:00",
            offset_minutes=30
        )
        self.assertGreater(rem_id, 0)

        # Verifica status inicial = 'offered'
        rem_det = self.db.get_reminder(rem_id)
        self.assertEqual(rem_det["status"], "offered")

        # Verifica que get_last_offered_reminder encontra a oferta
        last = self.service.get_last_offered_reminder()
        self.assertIsNotNone(last)
        self.assertEqual(last["id"], rem_id)

        # 2. Patrick responde 'sim, pode ser'
        res_parse = self.service.parse_confirmation_response("sim, pode ser")
        self.assertEqual(res_parse["action"], "confirm")
        self.assertIsNone(res_parse["offset_minutes"])

        # 3. Confirma o reminder
        confirmed = self.service.confirm_reminder(rem_id)
        self.assertTrue(confirmed)

        rem_det_pos = self.db.get_reminder(rem_id)
        self.assertEqual(rem_det_pos["status"], "confirmed")
        self.assertEqual(rem_det_pos["remind_at"], "2026-09-20T14:30:00")

    def test_reminder_confirmation_with_custom_offset(self):
        """Patrick responde ajustando o offset ('me lembra uma hora antes')."""
        ev_id = self.db.adicionar_evento_pendente(
            event_type="trabalho",
            description="Reunião com diretoria",
            event_at="2026-09-20T16:00:00"
        )
        rem_id = self.service.offer_reminder(
            event_id=ev_id,
            description="Reunião com diretoria",
            remind_at="2026-09-20T15:30:00",
            offset_minutes=30
        )

        res_parse = self.service.parse_confirmation_response("me lembra 1 hora antes amor")
        self.assertEqual(res_parse["action"], "confirm")
        self.assertEqual(res_parse["offset_minutes"], 60)

        self.service.confirm_reminder(rem_id, custom_offset_minutes=60)
        rem_det = self.db.get_reminder(rem_id)
        self.assertEqual(rem_det["status"], "confirmed")
        self.assertEqual(rem_det["offset_minutes"], 60)
        self.assertEqual(rem_det["remind_at"], "2026-09-20T15:00:00")

    def test_reminder_refusal(self):
        """Patrick recusa a oferta de lembrete ('não precisa amor')."""
        rem_id = self.service.offer_reminder(
            event_id=None,
            description="Tomar suplemento",
            remind_at="2026-09-20T10:00:00"
        )

        res_parse = self.service.parse_confirmation_response("não precisa amor")
        self.assertEqual(res_parse["action"], "decline")

        declined = self.service.decline_reminder(rem_id)
        self.assertTrue(declined)

        rem_det = self.db.get_reminder(rem_id)
        self.assertEqual(rem_det["status"], "declined")

    def test_direct_reminder_creation(self):
        """Patrick pede diretamente ('me lembra amanhã às 8h de comprar pão') -> status já confirmed."""
        rem_id = self.service.create_direct_reminder(
            description="Comprar pão",
            remind_at="2026-09-18T08:00:00"
        )
        rem_det = self.db.get_reminder(rem_id)
        self.assertEqual(rem_det["status"], "confirmed")
        self.assertEqual(rem_det["description"], "Comprar pão")

    def test_event_cancellation_cancels_linked_reminder(self):
        """Ao cancelar evento pendente, lembretes associados devem ser cancelados automaticamente."""
        ev_id = self.db.adicionar_evento_pendente(
            event_type="encontro",
            description="Jantar com amigos",
            event_at="2026-09-21T20:00:00"
        )
        rem_id = self.service.offer_reminder(
            event_id=ev_id,
            description="Jantar com amigos",
            remind_at="2026-09-21T19:30:00"
        )
        self.service.confirm_reminder(rem_id)

        # Cancela o evento
        canc_res = self.db.cancelar_evento_pendente(ev_id)
        self.assertTrue(canc_res)

        # Reminder agora está cancelled
        rem_det = self.db.get_reminder(rem_id)
        self.assertEqual(rem_det["status"], "cancelled")

    def test_event_reschedule_updates_reminder_time(self):
        """Ao remarcar a data de um evento, o reminder atrelado deve recalcular seu remind_at."""
        ev_id = self.db.adicionar_evento_pendente(
            event_type="reuniao",
            description="Reunião de alinhamento",
            event_at="2026-09-22T14:00:00"
        )
        rem_id = self.service.offer_reminder(
            event_id=ev_id,
            description="Reunião de alinhamento",
            remind_at="2026-09-22T13:30:00",
            offset_minutes=30
        )
        self.service.confirm_reminder(rem_id)

        # Remarca evento para 16:00
        self.db.atualizar_data_evento(ev_id, new_event_at="2026-09-22T16:00:00")

        # Reminder agora deve ser 15:30
        rem_det = self.db.get_reminder(rem_id)
        self.assertEqual(rem_det["remind_at"], "2026-09-22T15:30:00")

    def test_due_reminders_delivery_and_mark_sent(self):
        """get_due_reminders retorna apenas confirmados com remind_at <= now e mark_sent marca como sent."""
        now = datetime.now()
        # Lembrete vencido (5 minutos atrás)
        r_due_id = self.service.create_direct_reminder(
            description="Lembrete vencido",
            remind_at=(now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        )
        # Lembrete futuro (daqui a 1 hora)
        r_future_id = self.service.create_direct_reminder(
            description="Lembrete futuro",
            remind_at=(now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        )
        # Lembrete ofertado vencido (não confirmado -> não deve sair)
        r_offered_id = self.service.offer_reminder(
            event_id=None,
            description="Lembrete não confirmado",
            remind_at=(now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        )

        due_list = self.service.get_due_reminders(now)
        due_ids = [r["id"] for r in due_list]
        self.assertIn(r_due_id, due_ids)
        self.assertNotIn(r_future_id, due_ids)
        self.assertNotIn(r_offered_id, due_ids)

        # Marca como enviado
        sent_ok = self.service.mark_sent(r_due_id)
        self.assertTrue(sent_ok)

        # Não consta mais na lista de due
        due_pos = self.service.get_due_reminders(now)
        due_ids_pos = [r["id"] for r in due_pos]
        self.assertNotIn(r_due_id, due_ids_pos)

    def test_reboot_persistence(self):
        """Reiniciar o processo e recriar o DatabaseManager mantém todos os reminders intactos."""
        rem_id = self.service.create_direct_reminder(
            description="Lembrete persistente após reboot",
            remind_at="2026-09-25T10:00:00"
        )

        # Simula encerramento do processo e reabertura do banco
        new_db = DatabaseManager(db_path=self.db_path)
        new_service = ReminderService(db=new_db)

        rem = new_service.db.get_reminder(rem_id)
        self.assertIsNotNone(rem)
        self.assertEqual(rem["description"], "Lembrete persistente após reboot")
        self.assertEqual(rem["status"], "confirmed")
        del new_service
        del new_db


if __name__ == "__main__":
    unittest.main()
