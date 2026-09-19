"""
Módulo de Construção de Contexto Estruturado (Context Builder).
Canonical runtime → WorldContextBuilder.

Response Rhythm: ContextBuilder may apply a baseline policy for callers that do
not go through bot.py. Reply turns in bot.py re-apply with turn-specific hints
(availability_budget_hint). apply_policy is idempotent (strips prior rhythm block).
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict

from memory_retriever import memory_retriever, MemoryRetriever
from memory import memory_manager, MemoryManager
from style_engine import StyleEngine
from config import settings
from prompt_policy import is_canonical_runtime_ready

logger = logging.getLogger("ContextBuilder")


MAX_HISTORY_CHARS = 24000
MAX_TOTAL_CONTEXT_CHARS = 64000


class ContextBuilder:
    def __init__(
        self,
        memory_mgr: Optional[MemoryManager] = None,
        retriever: Optional[MemoryRetriever] = None
    ):
        self.memory_mgr = memory_mgr or memory_manager
        self.retriever = retriever or (
            MemoryRetriever(db=self.memory_mgr.db) if memory_mgr is not None else memory_retriever
        )

    def build_system_prompt(
        self,
        user_message: str = "",
        quoted_context: str = "",
        web_context: str = "",
        vision_context: str = "",
        planner_tone: Optional[str] = None,
        planner_goal: Optional[str] = None,
        now: Optional[datetime] = None,
        privacy_subjects: Optional[list[tuple[str, int]]] = None,
    ) -> str:
        """Monta o único system prompt suportado: World Bible + WorldState."""
        from world_context import WorldContextBuilder
        from response_rhythm import apply_policy, select_policy

        world = WorldContextBuilder(
            self.memory_mgr.db,
            cycle_mgr=self.memory_mgr.cycle_mgr,
            retriever=self.retriever,
            stale_minutes=getattr(settings, "WORLD_STATE_DEFAULT_STALE_MINUTES", 60),
        )
        result = world.build(
            now=now, user_message=user_message,
            quoted_context=quoted_context, web_context=web_context,
            vision_context=vision_context, planner_tone=planner_tone,
            planner_goal=planner_goal,
            control_language=getattr(settings, "PROMPT_CONTROL_LANGUAGE", "en"),
            output_language=getattr(settings, "MARINA_OUTPUT_LANGUAGE", "pt-BR"),
            privacy_subjects=privacy_subjects,
        )
        return apply_policy(result, select_policy(user_message, plan={'tone': planner_tone or ''}))
    def build(
        self,
        user_message: str = "",
        quoted_context: str = "",
        web_context: str = "",
        vision_context: str = "",
        planner_tone: Optional[str] = None,
        planner_goal: Optional[str] = None,
        recent_history: Optional[List[Dict[str, str]]] = None,
        max_history_turns: Optional[int] = None,
        privacy_subjects: Optional[list[tuple[str, int]]] = None,
    ) -> List[Dict[str, str]]:
        """Lista de mensagens no formato OpenAI/OpenRouter com orçamento de histórico."""
        system_text = self.build_system_prompt(
            user_message=user_message,
            quoted_context=quoted_context,
            web_context=web_context,
            vision_context=vision_context,
            planner_tone=planner_tone,
            planner_goal=planner_goal,
            privacy_subjects=privacy_subjects,
        )

        messages = [{"role": "system", "content": system_text}]

        ready = is_canonical_runtime_ready(self.memory_mgr.db)

        # Let the existing character budget define the useful window. A fixed
        # message count dropped short but still relevant exchanges while most
        # of the 24k budget remained unused (the real "Tá vendo qual?" case).
        if recent_history is not None:
            history = (recent_history[-max_history_turns:]
                       if max_history_turns is not None else recent_history)
        elif privacy_subjects:
            # When an explicit confidential privacy subject is queried, withhold unclassified chat history
            history = []
        elif not ready:
            # Pre-clean SafeCore: never replay pre-v3.6 conversational history.
            history = []
        else:
            # 512 is only a defensive database read ceiling; the prompt window
            # is bounded below by MAX_HISTORY_CHARS and MAX_TOTAL_CONTEXT_CHARS.
            history = self.memory_mgr.get_historico_recente(limit=max_history_turns or 512)

        remaining_budget = max(0, MAX_TOTAL_CONTEXT_CHARS - len(system_text))
        allowed_history_chars = min(MAX_HISTORY_CHARS, remaining_budget)

        history_chars = 0
        safe_history = []
        for item in reversed(history):
            item_chars = len(item.get("content", ""))
            if history_chars + item_chars > allowed_history_chars:
                break
            safe_history.insert(0, item)
            history_chars += item_chars

        for item in safe_history:
            messages.append({"role": item["role"], "content": item["content"]})

        return messages


context_builder = ContextBuilder()


