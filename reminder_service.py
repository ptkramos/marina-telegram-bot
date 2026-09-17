"""
Serviço de Lembretes Inteligentes com Consentimento (Smart Reminders).
Marina Seltin — Release 3.5.1

Filosofia central:
- Detectar compromisso NÃO É criar reminder.
- A Marina oferece carinhosamente (status='offered') para eventos concretos.
- Somente com o consentimento expresso do Patrick ("sim", "pode ser", "me lembra meia hora antes")
  o reminder passa para status='confirmed'.
- Pedidos diretos ("me lembra amanhã às 8h de...") já trazem consentimento implícito e criam status='confirmed'.
- O disparo de lembretes é feito via APScheduler em job de alta frequência, independente da roleta de proatividade.
"""
import re
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from config import settings
from db import db_manager, DatabaseManager

logger = logging.getLogger("ReminderService")


class ReminderService:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or db_manager

    def offer_reminder(
        self,
        event_id: Optional[int],
        description: str,
        remind_at: str,
        offset_minutes: int = 30,
        source_conversation_id: Optional[int] = None
    ) -> int:
        """Registra um reminder ofertado aguardando consentimento explícito."""
        rid = self.db.criar_reminder(
            description=description,
            remind_at=remind_at,
            status="offered",
            event_id=event_id,
            offset_minutes=offset_minutes,
            source_conversation_id=source_conversation_id
        )
        logger.info(f"Reminder {rid} ofertado ao Patrick para '{description}' em {remind_at} (offset: {offset_minutes}m).")
        return rid

    def get_last_offered_reminder(self, max_age_minutes: int = 60) -> Optional[dict]:
        """Recupera a última oferta de lembrete pendente de confirmação."""
        return self.db.get_ultimo_reminder_ofertado(max_age_minutes=max_age_minutes)

    def parse_confirmation_response(self, text: str) -> Dict[str, Any]:
        """
        Analisa se a mensagem do Patrick é uma resposta de aceitação, recusa ou ajuste
        de offset a uma oferta recente de lembrete.
        """
        t = (text or "").lower().strip()
        t_clean = re.sub(r'[!?,.]+', '', t).strip()

        # Recusa explícita
        recusa_padroes = [
            r"^n(ã|a)o$",
            r"^n(ã|a)o precisa",
            r"^precisa n(ã|a)o",
            r"^deixa$",
            r"^deixa quieto",
            r"^n(ã|a)o quero",
            r"^n(ã|a)o precisa me lembrar",
            r"^tranquilo, n(ã|a)o precisa"
        ]
        for padrao in recusa_padroes:
            if re.search(padrao, t_clean):
                return {"action": "decline", "offset_minutes": None}

        # Aceitação ou ajuste de offset
        # Casos com offset explícito: "sim, meia hora antes", "15 minutos antes", "1h antes"
        offset = None
        if "meia hora" in t_clean or "30 min" in t_clean or "30min" in t_clean:
            offset = 30
        elif "15 min" in t_clean or "15min" in t_clean or "quinze minutos" in t_clean:
            offset = 15
        elif "1 hora" in t_clean or "1h" in t_clean or "uma hora" in t_clean:
            offset = 60
        elif "10 min" in t_clean or "10min" in t_clean or "dez minutos" in t_clean:
            offset = 10
        elif "20 min" in t_clean or "20min" in t_clean:
            offset = 20
        elif "2 horas" in t_clean or "2h" in t_clean or "duas horas" in t_clean:
            offset = 120

        # Aceitação pura ou com offset
        aceite_padroes = [
            r"^(sim|s|ss|simm|claro|com certeza|pode ser|por favor|quero|lembra sim|me lembra sim|fechou|manda bala)\b",
            r"\b(me lembra|quero sim|pode me lembrar|lembra aí|lembra ai)\b"
        ]
        for padrao in aceite_padroes:
            if re.search(padrao, t_clean):
                return {"action": "confirm", "offset_minutes": offset}

        # Se especificou apenas o tempo sem "sim" ("meia hora antes", "15 min antes")
        if offset is not None and ("antes" in t_clean or "antes de" in t_clean):
            return {"action": "confirm", "offset_minutes": offset}

        return {"action": "none", "offset_minutes": None}

    def confirm_reminder(
        self,
        reminder_id: int,
        custom_offset_minutes: Optional[int] = None
    ) -> bool:
        """Confirma o reminder, recalculando o remind_at caso o offset tenha sido alterado."""
        remind_at = None
        if custom_offset_minutes is not None:
            r = self.db.get_reminder(reminder_id)
            if r and r.get("event_id"):
                ev = self.db.listar_eventos_pendentes()
                ev_match = next((e for e in ev if e["id"] == r["event_id"]), None)
                if ev_match and ev_match.get("event_at"):
                    try:
                        ev_dt = datetime.fromisoformat(ev_match["event_at"])
                        remind_at = (ev_dt - timedelta(minutes=custom_offset_minutes)).isoformat()
                    except Exception as e:
                        logger.warning(f"Erro ao recalcular remind_at com novo offset: {e}")

        success = self.db.confirmar_reminder(
            reminder_id=reminder_id,
            remind_at=remind_at,
            offset_minutes=custom_offset_minutes
        )
        if success:
            logger.info(f"Reminder {reminder_id} confirmado com sucesso (offset: {custom_offset_minutes}m).")
        return success

    def decline_reminder(self, reminder_id: int) -> bool:
        """Marca o reminder ofertado como recusado pelo Patrick."""
        success = self.db.recusar_reminder(reminder_id)
        if success:
            logger.info(f"Reminder {reminder_id} recusado pelo Patrick.")
        return success

    def create_direct_reminder(
        self,
        description: str,
        remind_at: str,
        offset_minutes: int = 0,
        event_id: Optional[int] = None,
        source_conversation_id: Optional[int] = None
    ) -> int:
        """Cria um reminder já confirmado (pedido direto do usuário, ex: 'me lembra amanhã às 8h')."""
        rid = self.db.criar_reminder(
            description=description,
            remind_at=remind_at,
            status="confirmed",
            event_id=event_id,
            offset_minutes=offset_minutes,
            source_conversation_id=source_conversation_id
        )
        logger.info(f"Reminder direto {rid} criado e confirmado para '{description}' em {remind_at}.")
        return rid

    def reschedule_reminder(self, reminder_id: int, new_remind_at: str) -> bool:
        """Altera data e hora de disparo de um lembrete existente."""
        return self.db.remarcar_reminder(reminder_id, new_remind_at)

    def cancel_reminder(self, reminder_id: int) -> bool:
        """Cancela um lembrete agendado."""
        return self.db.cancelar_reminder(reminder_id)

    def get_due_reminders(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Busca lembretes confirmados vencidos para entrega imediata no Telegram."""
        now_iso = (now or datetime.now()).isoformat()
        return self.db.get_due_reminders(now_iso)

    def mark_sent(self, reminder_id: int) -> bool:
        """Registra no SQLite que o lembrete foi enviado com sucesso."""
        return self.db.marcar_reminder_enviado(reminder_id)

    def format_reminder_message(self, reminder: Dict[str, Any]) -> str:
        """Gera mensagem natural, carinhosa e humanizada para o lembrete da namorada."""
        desc = reminder.get("description", "seu compromisso").strip()
        
        # Limpa 'lembrar de' ou 'lembrar que' caso tenha vindo no desc
        desc_clean = re.sub(r'^(me lembrar de|me lembra de|lembrar de|lembrar que|que eu tenho que|que tenho que)\s+', '', desc, flags=re.IGNORECASE).strip()

        templates = [
            f"amor, passando pra te lembrar: {desc_clean}! torcendo pra dar tudo certo aqui ❤️",
            f"oie amor! lembrete que você me pediu: {desc_clean} 💕 não esquece hein!",
            f"amor, seu compromisso é daqui a pouquinho: {desc_clean}! vai lá que vai dar tudo certo 🥰",
            f"amorzin, lembrete: {desc_clean}! qualquer coisa me avisa depois, tá? ❤️",
            f"passando pra te avisar, meu bem: {desc_clean}! to aqui pensando em você 💕"
        ]
        return random.choice(templates)

    def get_active_reminders(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna lembretes futuros ativos para exibição em comandos administrativos."""
        return self.db.get_active_reminders(limit)


# Instância global singleton
reminder_service = ReminderService()
