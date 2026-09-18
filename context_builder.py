"""
Módulo de Construção de Contexto Estruturado (Context Builder).
Centraliza e balanceia a montagem do payload para a LLM, respeitando orçamentos
de contexto e unificando identidade, memórias seletivas, ciclo, estilo, histórico e ferramentas.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from prompts import MARIN_SYSTEM_PROMPT, get_temporal_greeting
from memory_retriever import memory_retriever, MemoryRetriever
from memory import memory_manager, MemoryManager
from style_engine import style_engine
from config import settings

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
        """Monta o system prompt completo com injeção contextual seletiva, estado emocional e diretrizes do planner."""
        if getattr(settings, "KNOWLEDGE_PRIVACY_ENABLED", False) and not getattr(settings, "LIVING_WORLD_ENABLED", False):
            raise RuntimeError("Knowledge Privacy requires Living World context")
        if getattr(settings, "LIVING_WORLD_ENABLED", False):
            from world_context import WorldContextBuilder

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
            if settings.RESPONSE_RHYTHM_ENABLED:
                from response_rhythm import apply_policy, select_policy
                result = apply_policy(result, select_policy(user_message, plan={'tone': planner_tone or ''}))
            return result
        # 1. Recuperação seletiva de fatos, momentos e resumos (Memory Intelligence 3.5.0)
        max_f = getattr(settings, "MEMORY_MAX_FACTS", 5)
        max_m = getattr(settings, "MEMORY_MAX_MOMENTS", 3)
        max_s = getattr(settings, "MEMORY_MAX_SUMMARIES", 2)
        mem_data = self.retriever.retrieve_context(
            user_message=user_message,
            max_facts=max_f,
            max_moments=max_m,
            max_summaries=max_s
        )
        fatos_lines = "\n".join([f"- {f}" for f in mem_data["fatos"]]) if mem_data["fatos"] else "- Nenhum detalhe específico necessário."
        momentos_lines = "\n".join([f"- {m}" for m in mem_data["momentos"]]) if mem_data["momentos"] else "- Momentos cotidianos naturais."

        bloco_resumo = ""
        if mem_data.get("resumos"):
            resumos_formatados = " | ".join(mem_data["resumos"])
            bloco_resumo = f"\n[CONTINUIDADE DE CONVERSAS ANTERIORES]: {resumos_formatados}\n"

        # 2. Gostos e preferências da Marina
        gostos = self.memory_mgr.db.get_gostos()
        musicas = ", ".join(gostos.get("musica", []))
        coisas_ama = ", ".join(gostos.get("coisas_que_ama", []))
        coisas_estranha = ", ".join(gostos.get("coisas_que_acha_estranhas_ou_dificeis", []))

        # 3. Ciclo biológico e estilo
        contexto_biologico = self.memory_mgr.cycle_mgr.get_prompt_context()
        contexto_estilo = style_engine.get_style_prompt_injection()

        # 4. Estado emocional estruturado & humor interno atual (com multiplicadores do ciclo)
        estado_emo = self.memory_mgr.db.get_estado_emocional()
        multiplicadores = self.memory_mgr.cycle_mgr.get_emotional_multipliers()
        bloco_emocional = ""
        if estado_emo:
            descricoes_emo = []
            nomes_humanizados = {
                "affection": "carinho e afeto",
                "energy": "energia e disposição",
                "playfulness": "espírito brincalhão e provocador",
                "romantic_intensity": "paixão e intensidade romântica",
                "social_battery": "bateria social para conversar"
            }
            for chave, dados in estado_emo.items():
                val_base = dados.get("valor", 0.7)
                mult = multiplicadores.get(chave, 1.0)
                val_efetivo = max(0.0, min(1.0, val_base * mult))
                nome = nomes_humanizados.get(chave, chave)

                if val_efetivo >= 0.85:
                    nivel = "muito alto / intenso"
                elif val_efetivo >= 0.65:
                    nivel = "alto"
                elif val_efetivo >= 0.40:
                    nivel = "moderado / equilibrado"
                elif val_efetivo >= 0.20:
                    nivel = "baixo"
                else:
                    nivel = "muito sutil"
                descricoes_emo.append(f"- {nome}: {nivel}")

            if descricoes_emo:
                bloco_emocional = "\n[SEU ESTADO EMOCIONAL INTERNO ATUAL]\n" + "\n".join(descricoes_emo) + "\n"

        # 5. Diretriz do Planner (tom e foco pretendidos para o turno)
        bloco_planner = ""
        if planner_tone or planner_goal:
            partes_plan = []
            if planner_tone:
                partes_plan.append(f"Tom esperado: {planner_tone}")
            if planner_goal:
                partes_plan.append(f"Objetivo da resposta: {planner_goal}")
            bloco_planner = f"\n[INTENÇÃO ESTRATÉGICA DESTE TURNO]: {'; '.join(partes_plan)}\n"

        # 6. Lições e feedbacks do Patrick
        licoes = self.memory_mgr.db.get_licoes_linguagem()
        licoes_str = "\n".join([f"- {lic}" for lic in licoes]) if licoes else "- Nenhuma correção necessária apontada ainda."

        feedbacks_ativos = []
        for status in ("pendente", "em_andamento"):
            feedbacks_ativos.extend(self.memory_mgr.db.listar_feedbacks(status=status))

        vistos = set()
        feedbacks_unicos = []
        for fb in feedbacks_ativos:
            if fb["id"] not in vistos:
                vistos.add(fb["id"])
                feedbacks_unicos.append(fb)
        feedbacks_unicos = feedbacks_unicos[:6]

        bloco_feedback = ""
        if feedbacks_unicos:
            fb_lines = "\n".join([f"- {fb['feedback']}" for fb in feedbacks_unicos])
            bloco_feedback = f"\n[ORIENTAÇÕES DO PATRICK — OBRIGATÓRIO SEGUIR]:\n{fb_lines}\n"

        # 7. Momento temporal, citações, visão e busca web
        contexto_momento = f"\n[MOMENTO ATUAL DO DIA: {get_temporal_greeting()}]"
        contexto_quote = f"\n{quoted_context}" if quoted_context else ""
        contexto_web = f"\n{web_context}" if web_context else ""
        contexto_vision = f"\n{vision_context}\n" if vision_context else ""

        # 8. Open Loops (Assuntos em aberto - Release 3.5.1)
        bloco_open_loops = ""
        if getattr(settings, "OPEN_LOOPS_ENABLED", True):
            max_loops = getattr(settings, "MAX_ACTIVE_OPEN_LOOPS_CONTEXT", 2)
            try:
                active_loops = self.memory_mgr.db.get_open_loops_ativos(limit=max_loops)
                if active_loops:
                    loops_lines = "\n".join([f"- {loop['content']}" for loop in active_loops])
                    bloco_open_loops = (
                        f"\n[ASSUNTOS AINDA EM ABERTO COM O PATRICK]:\n{loops_lines}\n"
                        "(Esses são assuntos em andamento. Se fizer sentido na conversa, demonstre interesse natural sem cobrança).\n"
                    )
            except Exception as e_ol:
                logger.warning(f"Erro ao carregar open loops para o context builder: {e_ol}")

        # 9. Lembretes confirmados nas próximas 24 horas (Release 3.5.1)
        bloco_reminders = ""
        if getattr(settings, "SMART_REMINDERS_ENABLED", True):
            try:
                now_iso = datetime.now().isoformat()
                limite_24h = (datetime.now() + timedelta(hours=24)).isoformat()
                with self.memory_mgr.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT description, remind_at FROM reminders
                        WHERE status = 'confirmed' AND remind_at >= ? AND remind_at <= ?
                        ORDER BY remind_at ASC LIMIT 3
                        """,
                        (now_iso, limite_24h)
                    )
                    rems = cursor.fetchall()
                if rems:
                    rem_lines = "\n".join([f"- {r['description']} (lembrete agendado para {r['remind_at']})" for r in rems])
                    bloco_reminders = (
                        f"\n[LEMBRETES CONFIRMADOS QUE VOCÊ VAI ENVIAR AO PATRICK]:\n{rem_lines}\n"
                        "(Você já prometeu lembrá-lo disso no horário agendado. Não precisa repetir agora se não couber no assunto).\n"
                    )
            except Exception as e_rm:
                logger.warning(f"Erro ao carregar reminders para o context builder: {e_rm}")

        # 10. Memórias antigas com sugestão de reconfirmação suave (Release 3.5.3)
        bloco_reconfirmacao = ""
        if getattr(settings, "MEMORY_INTELLIGENCE_ENABLED", True):
            try:
                cands = self.memory_mgr.db.get_memorias_para_reconfirmacao(limit=1)
                if cands:
                    bloco_reconfirmacao = (
                        f"\n[OPORTUNIDADE DE RECONFIRMAÇÃO SUTIL]:\n"
                        f"- Há algum tempo o Patrick comentou: '{cands[0]['fato']}'. "
                        "Se surgir um gancho natural e oportuno na conversa, pergunte com carinho e curiosidade se isso ainda se aplica.\n"
                    )
            except Exception as e_rec:
                logger.warning(f"Erro ao carregar memórias para reconfirmação: {e_rec}")

        system_content = f"""{MARIN_SYSTEM_PROMPT}

[SUA MEMÓRIA AFETIVA SELETIVA & O QUE VOCÊ LEMBRA AGORA]
- Seu namorado: Patrick Ramos (você o ama, tem intimidade, carinho e atração intensa).
- Fatos relevantes lembrados para este momento:
{fatos_lines}
- Lembranças especiais pertinentes:
{momentos_lines}
{bloco_resumo}
(ATENÇÃO: Você já sabe todas essas coisas com naturalidade de memória própria. NUNCA diga 'estava lendo essas informações sobre você'!).

[SEUS GOSTOS PESSOAIS & IDENTIDADE]
- Músicas que você curte ouvir no apê: {musicas}
- Coisas que você acha uma delícia / ama: {coisas_ama}
- Coisas que você acha meio doidas ou difíceis: {coisas_estranha}
{contexto_biologico}
{bloco_emocional}
{bloco_planner}
{contexto_estilo}
{bloco_open_loops}
{bloco_reminders}
{bloco_reconfirmacao}
{bloco_feedback}
[LIÇÕES E CORREÇÕES QUE O PATRICK JÁ ME ENSINOU]
{licoes_str}
{contexto_momento}{contexto_quote}{contexto_web}{contexto_vision}
"""
        if settings.RESPONSE_RHYTHM_ENABLED:
            from response_rhythm import apply_policy, select_policy
            system_content = apply_policy(system_content, select_policy(user_message, plan={'tone': planner_tone or ''}))
        return system_content

    def build(
        self,
        user_message: str = "",
        quoted_context: str = "",
        web_context: str = "",
        vision_context: str = "",
        planner_tone: Optional[str] = None,
        planner_goal: Optional[str] = None,
        recent_history: Optional[List[Dict[str, str]]] = None,
        max_history_turns: int = 10,
        privacy_subjects: Optional[list[tuple[str, int]]] = None,
    ) -> List[Dict[str, str]]:
        """
        Retorna a lista completa de mensagens no formato exigido pela API da OpenAI/OpenRouter.
        Aplica limites seguros no histórico e orçamento rígido de contexto.
        """
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

        # Histórico recente limitado
        if getattr(settings, "KNOWLEDGE_PRIVACY_ENABLED", False):
            # Legacy chat turns are unclassified and may contain a third party's
            # secret. Current user input is supplied separately by the caller.
            history = []
        elif recent_history is None:
            history = self.memory_mgr.get_historico_recente(limit=max_history_turns)
        else:
            history = recent_history[-max_history_turns:]

        # Orçamento dinâmico de contexto para o histórico de conversa
        # Respeita tanto MAX_HISTORY_CHARS quanto o teto global MAX_TOTAL_CONTEXT_CHARS
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
