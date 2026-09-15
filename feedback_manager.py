"""
Módulo de Gerenciamento de Feedbacks e Sugestões do Telegram (v1.3.0 - SQLite Exclusivo).
Permite que o Patrick envie /feedback diretamente no Telegram.
As mensagens e o contexto recente são salvos com segurança exclusiva no SQLite (marin_memory.db).
"""
import logging
from datetime import datetime
from db import db_manager

logger = logging.getLogger("FeedbackManager")

class FeedbackManager:
    def __init__(self):
        self.db = db_manager

    def registrar_feedback(self, feedback_texto: str, autor: str = "Patrick Ramos", contexto_recente: list = None) -> dict:
        fb_id = f"FB-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # Filtra o contexto recente (últimas 4 mensagens)
        contexto_limpo = []
        if contexto_recente:
            for item in contexto_recente[-4:]:
                contexto_limpo.append({
                    "role": item.get("role", "user"),
                    "content": item.get("content", "")[:300]
                })

        # Salva exclusivamente no SQLite
        registro = self.db.salvar_feedback(
            feedback_id=fb_id,
            feedback_texto=feedback_texto.strip(),
            autor=autor,
            contexto=contexto_limpo
        )
        registro["contexto_conversa_recente"] = contexto_limpo

        logger.info(f"Feedback {fb_id} registrado com sucesso exclusivamente no SQLite!")
        return registro

    def listar_feedbacks(self, status: str = None) -> list[dict]:
        return self.db.listar_feedbacks(status=status)

feedback_manager = FeedbackManager()
