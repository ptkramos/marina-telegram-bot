"""
session_reflector.py — Refletor de Sessões e Continuidade de Relacionamento (Release 3.7.0).

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
from typing import Optional, List, Dict, Iterable, Set
from openai import OpenAI

from config import settings
from llm_options import llm_kwargs
from db import db_manager, DatabaseManager

logger = logging.getLogger("SessionReflector")

# Auditoria #2: traduzido para pt-BR pelo mesmo motivo do consolidator — este
# componente lê conversa em português e grava saída em português, mas raciocinava
# sob instrução em inglês. O Patch 021 tratou o prompt de conversa; os prompts de
# processamento (consolidator, reflector) tinham ficado de fora.
SESSION_REFLECTOR_SYSTEM_PROMPT = """Você é o componente interno de reflexão de sessão da Marina.
Use apenas a evidência da conversa fornecida. Não invente interioridade, biografia ou fatos novos por plausibilidade.

REGRAS:
1. Resuma a conversa recente com clareza em 'summary'.
2. Liste os assuntos principais em 'topics' (no máximo 3).
3. Processos inacabados → 'open_loops'.
4. Open loops fornecidos que foram concluídos → 'resolved_loops', com o loop_id.
5. Compromissos futuros ainda não registrados → 'events'.
6. Momentos de conexão memoráveis entre os dois → 'relationship_moments'.
7. Responda ESTRITAMENTE neste schema JSON, com os textos em português brasileiro:
{
  "topics": ["assunto"],
  "summary": "resumo narrativo de 1 a 2 frases",
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
      "resolution_notes": "como foi resolvido"
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
                **llm_kwargs(600),
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
            return None

    def apply_reflection(
        self,
        reflection_data: dict,
        start_msg_id: Optional[int] = None,
        end_msg_id: Optional[int] = None,
        allowed_loop_ids: Optional[Iterable[int]] = None
    ) -> dict:
        """
        Aplica e persiste as conclusões da reflexão no banco de dados.
        Verifica idempotência do intervalo de mensagens e valida loops com allowlist (P1.1 / P1.4).
        """
        if not reflection_data:
            return {"summary_id": None, "created_loops": [], "resolved_loops_count": 0, "moments_created": []}

        # Idempotência por intervalo de sessão
        if start_msg_id and end_msg_id:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM resumos_conversa WHERE start_conversation_id = ? AND end_conversation_id = ?",
                    (start_msg_id, end_msg_id)
                )
                if cursor.fetchone():
                    logger.info(f"Sessão {start_msg_id}-{end_msg_id} já refletida anteriormente; pulando duplicação.")
                    return {"summary_id": None, "created_loops": [], "resolved_loops_count": 0, "moments_created": []}

        summary = (reflection_data.get("summary") or "").strip()
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
            if summary_id is None and start_msg_id and end_msg_id:
                logger.info(f"Resumo para sessão {start_msg_id}-{end_msg_id} já gravado por outra instância; abortando aplicação concorrente.")
                return {"summary_id": None, "created_loops": [], "resolved_loops_count": 0, "moments_created": []}
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

        # Resolve loops indicados com validação estrita de allowlist (P1.4)
        resolved_count = 0
        allowed_set = set(allowed_loop_ids) if allowed_loop_ids is not None else set()
        for res in reflection_data.get("resolved_loops", []):
            lid = res.get("loop_id")
            notes = res.get("resolution_notes", "")
            if not isinstance(lid, int) or lid <= 0:
                logger.warning(f"SessionReflector: loop_id inválido ignorado: {lid}")
                continue
            if lid not in allowed_set:
                logger.warning(f"SessionReflector: tentativa de resolver loop {lid} não apresentado na lista de loops ativos.")
                continue
            loop_db = self.db.get_open_loop(lid)
            if not loop_db or loop_db.get("status") != "open":
                logger.warning(f"SessionReflector: loop {lid} não existe ou não está aberto.")
                continue

            if self.db.resolver_open_loop(lid, resolution_notes=notes):
                resolved_count += 1
                logger.info(f"SessionReflector: open loop {lid} resolvido com sucesso.")

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
        para disparar a reflexão da sessão com controle estrito de cursor (P1.1).
        """
        if not getattr(settings, "SESSION_REFLECTION_ENABLED", False) and not force:
            return None

        last_reflected_id = self.db.get_ultimo_conversa_id_refletido()
        messages = self.db.get_mensagens_sessao(limit=30, since_id=last_reflected_id if last_reflected_id > 0 else None)
        if not messages:
            return None
        if len(messages) < min_messages and not force:
            return None

        # Checa tempo desde a última mensagem
        if not force and messages:
            last_ts = messages[-1].get("timestamp")
            if last_ts:
                try:
                    last_dt = datetime.fromisoformat(last_ts)
                    idle_minutes = getattr(settings, "SESSION_REFLECTION_IDLE_MINUTES", 90)
                    if (datetime.now() - last_dt).total_seconds() < idle_minutes * 60:
                        return None
                except Exception:
                    pass

        start_id = messages[0]["id"] if messages else None
        end_id = messages[-1]["id"] if messages else None

        if start_id and end_id:
            if not self.db.claim_session_reflection(start_id, end_id):
                logger.info(f"Reflexão para intervalo {start_id}-{end_id} já concluída ou em andamento em outra instância; abortando.")
                return None

        # Busca loops ativos para apresentar à LLM e define allowlist
        active_loops = self.db.get_open_loops_ativos(limit=5)
        allowed_loop_ids = {l["id"] for l in active_loops}

        logger.info(f"Disparando reflexão de sessão para {len(messages)} mensagens recentes (cursor: {last_reflected_id} -> {end_id})...")
        try:
            data = self.reflect_session(messages, active_loops=active_loops)
        except TypeError:
            try:
                data = self.reflect_session(messages)
            except Exception as e:
                logger.warning(f"Exceção ao chamar reflect_session: {e}")
                data = None
        except Exception as e:
            logger.warning(f"Exceção ao chamar reflect_session: {e}")
            data = None

        if not data:
            if end_id:
                self.db.release_session_reflection_claim(end_id)
            logger.warning("Reflect session falhou ou retornou vazio; abortando aplicação para evitar resumos espúrios.")
            return None

        applied = self.apply_reflection(data, start_msg_id=start_id, end_msg_id=end_id, allowed_loop_ids=allowed_loop_ids)
        if applied and end_id:
            self.db.set_estado_relacional("last_reflected_conversa_id", str(end_id))
            logger.info(f"Cursor de reflexão de sessão avançado para {end_id}.")

        return {"reflection": data, "applied": applied}


session_reflector = SessionReflector()
