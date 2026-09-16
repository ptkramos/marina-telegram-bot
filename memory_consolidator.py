"""
Módulo de Consolidação de Memória de Longo Prazo (Smart Memory Consolidator).
Analisa lotes de conversas de forma assíncrona para extrair fatos permanentes sobre Patrick,
detectar e resolver contradições, registrar momentos marcantes e gerar resumos temáticos.
"""
import json
import logging
import asyncio
from typing import Optional
from openai import OpenAI

from config import settings
from db import db_manager, DatabaseManager

logger = logging.getLogger("MemoryConsolidator")


class MemoryConsolidationError(RuntimeError):
    """Exceção levantada quando a consolidação de memória via LLM falha definitivamente."""
    pass


CONSOLIDATOR_SYSTEM_PROMPT = """Extraia fatos permanentes sobre Patrick Ramos para a memória da namorada Marina Seltin a partir do diálogo recente.
REGRAS:
1. Ignore chitchat casual (oi, kkk, emojis, blz).
2. Extraia apenas preferências, rotina, planos futuros, projetos ou fatos relevantes.
3. Se contradizer fato existente, inclua o ID antigo em 'facts_to_deactivate' e crie o novo com 'supersedes_id'. Não duplique fatos já existentes.
4. Responda ESTRITAMENTE em JSON:
{
  "facts_to_create": [{"fato": "string em 3ª pessoa", "category": "preferencia|rotina|trabalho|hobby|pessoal|saude|outro", "importance": 0.5, "confidence": 1.0, "supersedes_id": null}],
  "facts_to_deactivate": [{"existing_fact_id": 1, "reason": "string"}],
  "important_moments": [{"momento": "string", "importance": 0.8}],
  "topic_summary": "resumo curto em 1 frase ou null"
}"""


class MemoryConsolidator:
    def __init__(self, db: Optional[DatabaseManager] = None, llm_client: Optional[OpenAI] = None):
        self.db = db or db_manager
        self.llm = llm_client or OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL
        )

    def consolidate_dialogue(
        self,
        messages: list[dict],
        existing_facts: Optional[list[dict]] = None
    ) -> dict:
        """
        Executa a consolidação de um lote de mensagens utilizando a LLM com structured output JSON.
        Pode ser executado de forma síncrona ou envolvido em asyncio.to_thread.
        """
        if not messages:
            return {
                "facts_to_create": [],
                "facts_to_deactivate": [],
                "important_moments": [],
                "topic_summary": None
            }

        # Carrega fatos ativos se não fornecidos
        if existing_facts is None:
            existing_facts = self.db.get_fatos_patrick_detalhados(active_only=True)

        facts_repr = []
        for f in existing_facts:
            facts_repr.append(f"- [ID {f.get('id')}][{f.get('category', 'geral')}]: {f.get('fato')}")
        facts_block = "\n".join(facts_repr) if facts_repr else "Nenhum fato registrado anteriormente."

        conversation_repr = []
        for m in messages:
            role = "Patrick" if m.get("role") in ("user", "patrick") else "Marina"
            conversation_repr.append(f"{role}: {m.get('content', '')}")
        dialogue_block = "\n".join(conversation_repr)

        user_content = (
            f"FATOS CONHECIDOS ATIVOS ATUALMENTE:\n{facts_block}\n\n"
            f"LOTE DE CONVERSA RECENTE PARA ANÁLISE:\n{dialogue_block}\n\n"
            "Analise e retorne estritamente o JSON com novos fatos, contradições/desativações, momentos e resumo."
        )

        for attempt in range(3):
            try:
                response = self.llm.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": CONSOLIDATOR_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.2,
                    max_tokens=600,
                    response_format={"type": "json_object"}
                )
                raw_text = response.choices[0].message.content.strip()
                data = json.loads(raw_text)
                return {
                    "facts_to_create": data.get("facts_to_create", []),
                    "facts_to_deactivate": data.get("facts_to_deactivate", []),
                    "important_moments": data.get("important_moments", []),
                    "topic_summary": data.get("topic_summary"),
                    "success": True
                }
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "rate" in err_str.lower()) and attempt < 2:
                    import time
                    wait_time = (attempt + 1) * 3.0
                    logger.warning(f"Rate limit upstream no consolidator (tentativa {attempt + 1}/3). Aguardando {wait_time}s: {e}")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Erro ao consolidar memória via LLM: {e}")
                return {
                    "facts_to_create": [],
                    "facts_to_deactivate": [],
                    "important_moments": [],
                    "topic_summary": None,
                    "error": str(e),
                    "success": False
                }

    def apply_consolidation(
        self,
        consolidation: dict,
        start_conv_id: Optional[int] = None,
        end_conv_id: Optional[int] = None
    ) -> dict:
        """Aplica no banco SQLite os fatos, desativações, momentos e resumos extraídos."""
        created_count = 0
        deactivated_count = 0
        moments_count = 0
        summary_saved = False

        # 1. Desativa fatos contraditos
        for deact in consolidation.get("facts_to_deactivate", []):
            fact_id = deact.get("existing_fact_id")
            if fact_id:
                self.db.desativar_fato(fact_id)
                deactivated_count += 1
                logger.info(f"Fato ID {fact_id} desativado por contradição: {deact.get('reason')}")

        # 2. Cria novos fatos
        for fc in consolidation.get("facts_to_create", []):
            fato_text = (fc.get("fato") or "").strip()
            if not fato_text:
                continue
            cat = fc.get("category", "geral")
            imp = float(fc.get("importance", 0.5))
            conf = float(fc.get("confidence", 1.0))
            supersedes = fc.get("supersedes_id")
            
            row_id = self.db.adicionar_fato_patrick(
                fato=fato_text,
                category=cat,
                importance=imp,
                confidence=conf,
                source_conversation_id=end_conv_id,
                supersedes_id=supersedes
            )
            if row_id:
                created_count += 1
                logger.info(f"Novo fato aprendido: '{fato_text}' (Categoria: {cat})")

        # 3. Registra momentos marcantes
        for mom in consolidation.get("important_moments", []):
            mom_text = (mom.get("momento") or "").strip()
            if not mom_text:
                continue
            imp = float(mom.get("importance", 0.8))
            self.db.adicionar_momento_marcante(
                momento=mom_text,
                importance=imp,
                source_conversation_id=end_conv_id
            )
            moments_count += 1
            logger.info(f"Momento marcante registrado: '{mom_text}'")

        # 4. Salva resumo de conversa se houver tópico relevante
        topic_summary = consolidation.get("topic_summary")
        if topic_summary and isinstance(topic_summary, str) and len(topic_summary.strip()) > 8:
            self.db.salvar_resumo_conversa(
                topic=topic_summary.strip(),
                summary=topic_summary.strip(),
                start_conversation_id=start_conv_id,
                end_conversation_id=end_conv_id
            )
            summary_saved = True
            logger.info(f"Resumo temático salvo: '{topic_summary.strip()}'")

        return {
            "created": created_count,
            "deactivated": deactivated_count,
            "moments": moments_count,
            "summary_saved": summary_saved
        }

    async def consolidate_and_apply_async(
        self,
        messages: list[dict],
        start_conv_id: Optional[int] = None,
        end_conv_id: Optional[int] = None
    ) -> dict:
        """Executa consolidação em thread assíncrona isolada sem bloquear o loop do bot."""
        consolidation = await asyncio.to_thread(self.consolidate_dialogue, messages)
        if not consolidation.get("success", True) or consolidation.get("error"):
            err_msg = consolidation.get("error") or "Falha na extração de memória pela LLM"
            raise MemoryConsolidationError(f"Consolidação de memória abortada: {err_msg}")

        result = await asyncio.to_thread(
            self.apply_consolidation,
            consolidation,
            start_conv_id,
            end_conv_id
        )
        result["success"] = True
        return result


memory_consolidator = MemoryConsolidator()
