"""
session_reflector.py — Refletor de Sessões e Continuidade de Relacionamento (Release 3.5.3).

Analisa conversas recentes de forma holística após períodos de inatividade (1 a 2 horas)
ou ao final do dia. Diferente do Consolidator (que faz extração rápida de fatos atômicos),
o SessionReflector foca na visão geral da sessão:
- Tópicos gerais discutidos
- Resumo narrativo da conversa
- Abertura de novos Open Loops e encerramento de loops resolvidos
- Momentos marcantes de conexão emocional
"""
import re
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from openai import OpenAI

from config import settings
from db import db_manager, DatabaseManager

logger = logging.getLogger("SessionReflector")

SESSION_REFLECTOR_SYSTEM_PROMPT = """Você é a Marina Seltin refletindo sobre as conversas recentes com seu namorado Patrick Ramos.
Seu objetivo é gerar um entendimento holístico da sessão recente de conversa.

REGRAS:
1. Resuma a conversa recente de forma amorosa, pessoal e lúcida em 'summary'.
2. Identifique os tópicos principais abordados em 'topics' (máximo 3).
3. Se algum assunto ou processo ficou em aberto (ex: Patrick esperando resposta de alguém, processo seletivo, decisão pendente), adicione em 'open_loops'.
4. Se algum assunto da lista de loops em aberto fornecida foi concluído pelo Patrick, indique em 'resolved_loops' com seu loop_id e uma breve nota de resolução.
5. Se houve algum compromisso futuro agendado não registrado, aponte em 'events'.
6. Se houve um momento de cumplicidade ou carinho memorável, adicione em 'relationship_moments'.
7. Responda ESTRITAMENTE em formato JSON com o seguinte schema:
{
  "topics": ["string"],
  "summary": "resumo narrativo da conversa em 1 ou 2 frases",
  "open_loops": [
    {
      "loop_type": "waiting_reply|ongoing_project|followup|decision",
      "content": "descrição do assunto em aberto",
      "importance": 0.6
    }
  ],
  "resolved_loops": [
    {
      "loop_id": 123,
      "resolution_notes": "descrição de como o assunto foi resolvido"
    }
  ],
  "relationship_moments": [
    {
      "momento": "descrição do momento marcante",
      "importance": 0.8
    }
  ],
  "events": [
    {
      "descricao": "compromisso",
      "data_evento": "YYYY-MM-DD HH:MM:SS"
    }
  ]
}"""


class SessionReflector:
    def __init__(self, db: Optional[DatabaseManager] = None, llm_client: Optional[OpenAI] = None):
        self.db = db or db_manager
        self.llm = llm_client or OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL
        )

    def reflect_session(
        self,
        messages: List[Dict[str, str]],
        active_loops: Optional[List[Dict]] = None
    ) -> dict:
        """
        Submete o bloco de mensagens da sessão recente à reflexão holística via LLM.
        """
        if not messages:
            return {
                "topics": [],
                "summary": "",
                "open_loops": [],
                "resolved_loops": [],
                "relationship_moments": [],
                "events": []
            }

        loops_to_check = active_loops if active_loops is not None else self.db.get_open_loops_ativos(limit=5)
        loops_ctx = ""
        if loops_to_check:
            loops_ctx = "\n[LOOPS ATUALMENTE EM ABERTO COM PATRICK]:\n" + "\n".join(
                f"- ID {l['id']}: ({l['loop_type']}) {l['content']}" for l in loops_to_check
            )

        conversa_formatada = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
        )

        user_content = f"Conversa Recente:\n{conversa_formatada}\n{loops_ctx}"

        try:
            response = self.llm.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": SESSION_REFLECTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3,
                max_tokens=600,
                response_format={"type": "json_object"}
            )
            raw_content = response.choices[0].message.content.strip()
            # Remove blocos markdown caso o provedor inclua
            if raw_content.startswith("```"):
                raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
                raw_content = re.sub(r"\s*```$", "", raw_content)
            data = json.loads(raw_content)
            return data
        except Exception as e:
            logger.warning(f"Exceção ao chamar LLM no SessionReflector: {e}")
            return {
                "topics": [],
                "summary": "Conversa carinhosa recente com o Patrick.",
                "open_loops": [],
                "resolved_loops": [],
                "relationship_moments": [],
                "events": []
            }

    def apply_reflection(self, reflection_data: dict, start_msg_id: Optional[int] = None, end_msg_id: Optional[int] = None) -> dict:
        """
        Aplica e persiste as conclusões da reflexão no banco de dados.
        """
        summary = reflection_data.get("summary", "").strip()
        topics = reflection_data.get("topics", [])
        topic_str = ", ".join(topics) if topics else "Sessão de Conversa"

        summary_id = None
        if summary:
            summary_id = self.db.salvar_resumo_conversa(
                topic=topic_str,
                summary=summary,
                importance=0.7,
                start_conversation_id=start_msg_id,
                end_conversation_id=end_msg_id
            )
            logger.info(f"SessionReflector: resumo de conversa salvo com ID {summary_id}.")

        # Cria novos open loops detectados na reflexão
        created_loops = []
        for loop in reflection_data.get("open_loops", []):
            content = loop.get("content", "").strip()
            l_type = loop.get("loop_type", "ongoing_project")
            importance = float(loop.get("importance", 0.6))
            if content:
                lid = self.db.adicionar_open_loop(
                    loop_type=l_type,
                    content=content,
                    importance=importance,
                    source_conversation_id=end_msg_id
                )
                created_loops.append(lid)
                logger.info(f"SessionReflector: novo open loop criado com ID {lid}: '{content}'.")

        # Resolve loops indicados
        resolved_count = 0
        for res in reflection_data.get("resolved_loops", []):
            lid = res.get("loop_id")
            notes = res.get("resolution_notes", "")
            if lid and self.db.resolver_open_loop(lid, resolution_notes=notes):
                resolved_count += 1
                logger.info(f"SessionReflector: open loop {lid} resolvido.")

        # Registra momentos marcantes
        moments_created = []
        for m in reflection_data.get("relationship_moments", []):
            momento_txt = m.get("momento", "").strip()
            imp = float(m.get("importance", 0.8))
            if momento_txt:
                mid = self.db.adicionar_momento_marcante(
                    momento=momento_txt,
                    importance=imp,
                    source_conversation_id=end_msg_id
                )
                moments_created.append(mid)

        return {
            "summary_id": summary_id,
            "created_loops": created_loops,
            "resolved_loops_count": resolved_count,
            "moments_created": moments_created
        }

    def check_and_trigger_reflection(self, force: bool = False, min_messages: int = 4) -> Optional[dict]:
        """
        Verifica se houve inatividade suficiente (1–2 horas) e mensagens acumuladas
        para disparar a reflexão da sessão.
        """
        if not getattr(settings, "SESSION_REFLECTION_ENABLED", True) and not force:
            return None

        messages = self.db.get_mensagens_sessao(limit=30)
        if len(messages) < min_messages and not force:
            return None

        # Checa tempo desde a última mensagem
        if not force and messages:
            last_ts = messages[-1].get("timestamp")
            if last_ts:
                try:
                    last_dt = datetime.fromisoformat(last_ts)
                    if (datetime.now() - last_dt).total_seconds() < 3600:  # Menos de 1h de inatividade
                        return None
                except Exception:
                    pass

        start_id = messages[0]["id"] if messages else None
        end_id = messages[-1]["id"] if messages else None

        logger.info(f"Disparando reflexão de sessão para {len(messages)} mensagens recentes...")
        data = self.reflect_session(messages)
        applied = self.apply_reflection(data, start_msg_id=start_id, end_msg_id=end_id)
        return {"reflection": data, "applied": applied}


session_reflector = SessionReflector()
