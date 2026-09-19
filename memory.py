"""
Módulo de Memória Persistente e Evolutiva da Marina Salles (v3.7.0 - SQLite & Estilo Dinâmico).
Conecta-se ao banco marin_memory.db através do db_manager:
- Histórico completo infinito no banco relacional
- Contexto recente dinâmico (mantém a LLM rápida e sem alucinações)
- Fatos afetivos e ciclo menstrual de 28 dias
- Sincronia linguística e espelhamento de estilo (style_engine)
"""
import logging
from pathlib import Path
from cycle import MenstrualCycleManager
from db import db_manager
from style_engine import style_engine

logger = logging.getLogger("MarinaMemory")

class MemoryManager:
    def __init__(self, db=None):
        self.db = db or db_manager
        data_ciclo = self.db.get_data_inicio_ciclo()
        self.cycle_mgr = MenstrualCycleManager(data_ciclo)

    @property
    def data(self) -> dict:
        """Propriedade para compatibilidade com o bot.py e código legado."""
        return {
            "perfil": self.db.get_perfil(),
            "fatos_sobre_patrick": self.db.get_fatos_patrick(),
            "momentos_marcantes": self.db.get_momentos_marcantes(),
            "gostos_e_interesses": self.db.get_gostos(),
            "historico_recente": self.get_historico_recente(limit=10)
        }

    def registrar_interacao(self, user_msg: str, bot_msg: str) -> tuple[int, int]:
        """Registra a interação na tabela 'conversas' do SQLite permanentemente e retorna os IDs."""
        u_id = self.registrar_mensagem_usuario(user_msg)
        b_id = self.registrar_mensagem_assistente(bot_msg, is_initiative=user_msg.startswith("[Iniciativa da Marina"))
        return u_id, b_id

    def registrar_mensagem_usuario(self, user_msg: str) -> int:
        """Persiste uma entrada recebida e aplica somente efeitos derivados do usuário."""
        is_init = 1 if user_msg.startswith("[Iniciativa da Marina") else 0
        u_id = self.db.adicionar_mensagem(role="user", content=user_msg, is_initiative=bool(is_init))
        if not is_init:
            from relationship_world import RelationshipWorld

            try:
                RelationshipWorld(self.db).observe_explicit_user_culture(
                    user_msg, conversation_id=u_id)
            except (ValueError, RuntimeError) as exc:
                logger.warning('Cultura do casal ignorada: %s', exc)
        return u_id

    def registrar_mensagem_assistente(self, bot_msg: str, *, is_initiative: bool = False) -> int:
        """Persiste apenas uma fala cuja entrega já foi confirmada."""
        return self.db.adicionar_mensagem(
            role="assistant", content=bot_msg, is_initiative=is_initiative)

    def get_historico_recente(self, limit: int = 10) -> list[dict]:
        """Retorna as últimas N mensagens do banco para alimentar o chat ativo."""
        return self.db.get_mensagens_recentes(limit=limit)

    def aprender_fato_patrick(self, fato: str):
        """Salva um novo fato sobre o Patrick na tabela 'fatos_patrick'."""
        self.db.adicionar_fato_patrick(fato)

    def registrar_descoberta(self, categoria: str, descoberta: str):
        """Salva uma nova preferência na tabela 'gostos_marina'."""
        self.db.adicionar_gosto(categoria=categoria, item=descoberta)

    def get_context_for_message(self, current_message: str) -> str:
        """Recupera contexto seletivo e balanceado para a mensagem atual."""
        from context_builder import context_builder
        return context_builder.build_system_prompt(user_message=current_message)

    def get_contexto_emocional(self) -> str:
        fatos_lista = self.db.get_fatos_patrick()
        fatos = "\n".join([f"- {f}" for f in fatos_lista])
        momentos_lista = self.db.get_momentos_marcantes()
        momentos = "\n".join([f"- {m}" for m in momentos_lista])
        
        gostos = self.db.get_gostos()
        musicas = ", ".join(gostos.get("musica", []))
        coisas_ama = ", ".join(gostos.get("coisas_que_ama", []))
        coisas_estranha = ", ".join(gostos.get("coisas_que_acha_estranhas_ou_dificeis", []))
        
        contexto_biologico = self.cycle_mgr.get_prompt_context()
        contexto_estilo = style_engine.get_style_prompt_injection()
        licoes = self.db.get_licoes_linguagem()
        licoes_str = "\n".join([f"- {lic}" for lic in licoes]) if licoes else "- Nenhuma correção necessária apontada ainda."

        # Feedbacks do Patrick entram no prompt (antes ficavam só gravados e ignorados)
        feedbacks_ativos = []
        for status in ("pendente", "em_andamento"):
            feedbacks_ativos.extend(self.db.listar_feedbacks(status=status))
        # Mais recentes primeiro, sem duplicar, limita a 8
        vistos = set()
        feedbacks_unicos = []
        for fb in feedbacks_ativos:
            if fb["id"] in vistos:
                continue
            vistos.add(fb["id"])
            feedbacks_unicos.append(fb)
        feedbacks_unicos = feedbacks_unicos[:8]
        if feedbacks_unicos:
            fb_lines = "\n".join([f"- {fb['feedback']}" for fb in feedbacks_unicos])
            bloco_feedback = f"""
[ORIENTAÇÕES DO PATRICK — OBRIGATÓRIO SEGUIR]
O Patrick deixou estes pedidos de melhoria. Incorpora de forma NATURAL (sem citar que é feedback, sem dizer "anotei", sem meta-fala):
{fb_lines}
"""
        else:
            bloco_feedback = ""
        
        return f"""
[LEGACY MEMORY CONTEXT — deprecated; not used by Living World / SafeCore production paths]
- Partner: Patrick Ramos.
- Remembered facts:
{fatos}
Special moments:
{momentos}
[PERSONAL TASTES]
- Music: {musicas}
- Loves: {coisas_ama}
- Finds odd/hard: {coisas_estranha}
(React with your own taste filter; do not invent a fixed age.)
{contexto_biologico}
{contexto_estilo}
{bloco_feedback}
[CORRECTIONS FROM PATRICK]
{licoes_str}
"""

memory_manager = MemoryManager()

