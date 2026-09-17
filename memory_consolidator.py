"""
Módulo de Consolidação de Memória de Longo Prazo (Smart Memory Consolidator 2.0).
Analisa lotes de conversas de forma assíncrona para extrair fatos permanentes sobre Patrick,
detectar e resolver contradições, registrar momentos marcantes e gerar resumos temáticos.
Implementa controle estrito por 'decision', allowlist de candidatos anti-alucinação,
substituição atômica e validação de domínio.
"""
import re
import json
import logging
import asyncio
from typing import Optional, Set, Dict, List
from openai import OpenAI

from config import settings
from db import db_manager, DatabaseManager

logger = logging.getLogger("MemoryConsolidator")


class MemoryConsolidationError(RuntimeError):
    """Exceção levantada quando a consolidação de memória via LLM falha definitivamente."""
    pass


CONSOLIDATOR_SYSTEM_PROMPT = """Extraia fatos permanentes sobre Patrick Ramos para a memória da namorada Marina Seltin a partir do diálogo recente.
REGRAS DE CLASSIFICAÇÃO E INTELIGÊNCIA:
1. Ignore chitchat casual (oi, kkk, emojis, blz, elogios vazios, saudações). Use decision='ignore' se não houver conteúdo duradouro.
2. Extraia apenas preferências, rotina, planos futuros, projetos ou fatos relevantes de longo prazo.
3. Se Patrick reafirmar algo que já existe na lista de fatos conhecidos: defina decision='same', existing_fact_id=ID_DO_FATO. NÃO crie um fato duplicado.
4. Se contradizer ou atualizar fato conhecido: defina decision='update' ou 'contradiction', existing_fact_id=ID_DO_FATO_ANTIGO, supersedes_id=ID_DO_FATO_ANTIGO e descreva o novo fato.
5. Se for um fato totalmente novo: defina decision='new', existing_fact_id=null, supersedes_id=null.
6. Se Patrick pedir explicitamente para lembrar ("lembra que...", "guarda isso", "não esquece"): defina memory_tier='core', importance>=0.90, confidence=1.0.
7. Se Patrick revogar algo explicitamente ("esquece isso", "não guarda mais isso", "isso não vale mais"): inclua em 'keys_to_deactivate' ou 'facts_to_deactivate'.
8. Associe canonical_key (snake_case, ex: current_main_game, favorite_energy_drink, training_routine) para conceitos atualizáveis.
9. Defina volatility: 'stable' (família, identidade, gostos fundamentais), 'medium' (jogos atuais, projetos), 'volatile' (rotinas temporárias, horários da semana).
10. Responda ESTRITAMENTE em JSON:
{
  "facts_to_create": [
    {
      "fato": "string em 3ª pessoa",
      "category": "preferencia|rotina|trabalho|projeto|hobby|relacionamento|pessoal|saude|outro",
      "importance": 0.5,
      "confidence": 1.0,
      "memory_tier": "core|standard|contextual",
      "volatility": "stable|medium|volatile",
      "canonical_key": "string_ou_null",
      "decision": "new|same|update|contradiction|ignore",
      "existing_fact_id": null,
      "supersedes_id": null
    }
  ],
  "facts_to_deactivate": [{"existing_fact_id": 1, "reason": "string"}],
  "keys_to_deactivate": ["canonical_key_se_patrick_revogou"],
  "important_moments": [{"momento": "string", "importance": 0.8}],
  "topic_summary": "resumo curto em 1 frase ou null"
}"""


def _normalize_canonical_key(key: Optional[str]) -> Optional[str]:
    """Normaliza canonical_key para snake_case seguro."""
    if not key or not isinstance(key, str):
        return None
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', key.strip().lower())
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean if clean else None


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
        Utiliza seleção seletiva de candidatos (MemoryRetriever) sem side-effects e monta allowlist de IDs/keys.
        """
        if not messages:
            return {
                "facts_to_create": [],
                "facts_to_deactivate": [],
                "keys_to_deactivate": [],
                "important_moments": [],
                "topic_summary": None,
                "_candidate_fact_ids": set(),
                "_candidate_keys": set(),
                "_candidates": []
            }

        # Seleção Inteligente de Candidatos (Memory Intelligence)
        if existing_facts is None:
            batch_text = " ".join(m.get("content", "") for m in messages)
            from memory_retriever import MemoryRetriever
            retriever = MemoryRetriever(db=self.db)
            # record_access=False evita feedback loop de popularidade durante background consolidation
            retrieval = retriever.retrieve_context(
                user_message=batch_text,
                max_facts=12,
                max_moments=2,
                record_access=False
            )
            existing_facts = retrieval.get("fatos_detalhados", [])

        # Allowlist interna de candidatos apresentados
        candidate_fact_ids = {f["id"] for f in existing_facts if f.get("id")}
        candidate_keys = {f["canonical_key"] for f in existing_facts if f.get("canonical_key")}

        facts_repr = []
        for f in existing_facts:
            tier_tag = f"[{f.get('memory_tier', 'standard')}]"
            key_tag = f"[key:{f.get('canonical_key')}]" if f.get('canonical_key') else ""
            facts_repr.append(f"- [ID {f.get('id')}]{tier_tag}{key_tag}[{f.get('category', 'geral')}]: {f.get('fato')}")
        facts_block = "\n".join(facts_repr) if facts_repr else "Nenhum fato correlato previamente registrado."

        conversation_repr = []
        for m in messages:
            role = "Patrick" if m.get("role") in ("user", "patrick") else "Marina"
            conversation_repr.append(f"{role}: {m.get('content', '')}")
        dialogue_block = "\n".join(conversation_repr)

        user_content = (
            f"FATOS CONHECIDOS RELEVANTES AO DIÁLOGO:\n{facts_block}\n\n"
            f"LOTE DE CONVERSA RECENTE PARA ANÁLISE:\n{dialogue_block}\n\n"
            "Analise o diálogo e retorne estritamente o JSON com decisões categorizadas, desativações, momentos e resumo."
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
                    max_tokens=650,
                    response_format={"type": "json_object"}
                )
                raw_text = response.choices[0].message.content.strip()
                data = json.loads(raw_text)
                return {
                    "facts_to_create": data.get("facts_to_create", []),
                    "facts_to_deactivate": data.get("facts_to_deactivate", []),
                    "keys_to_deactivate": data.get("keys_to_deactivate", []),
                    "important_moments": data.get("important_moments", []),
                    "topic_summary": data.get("topic_summary"),
                    "_candidate_fact_ids": candidate_fact_ids,
                    "_candidate_keys": candidate_keys,
                    "_candidates": existing_facts,
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
                    "keys_to_deactivate": [],
                    "important_moments": [],
                    "topic_summary": None,
                    "_candidate_fact_ids": candidate_fact_ids,
                    "_candidate_keys": candidate_keys,
                    "_candidates": existing_facts,
                    "error": str(e),
                    "success": False
                }

    def apply_consolidation(
        self,
        consolidation: dict,
        start_conv_id: Optional[int] = None,
        end_conv_id: Optional[int] = None
    ) -> dict:
        """
        Aplica no banco SQLite os fatos, desativações, momentos e resumos extraídos.
        Implementa controle autoritativo por 'decision', allowlist de candidatos e atomicidade.
        """
        created_count = 0
        confirmed_count = 0
        updated_count = 0
        deactivated_count = 0
        ignored_count = 0
        moments_count = 0
        summary_saved = False

        candidate_ids = set(consolidation.get("_candidate_fact_ids") or [])
        candidate_keys = set(consolidation.get("_candidate_keys") or [])
        candidates_list = consolidation.get("_candidates") or []

        # 0. Desativa por chaves canônicas explicitamente revogadas com proteção de allowlist
        for ck in consolidation.get("keys_to_deactivate", []):
            if ck and isinstance(ck, str):
                ck_clean = _normalize_canonical_key(ck)
                if not ck_clean:
                    continue
                if candidate_keys and ck_clean not in candidate_keys:
                    logger.warning(f"Desativação por chave '{ck_clean}' rejeitada: chave fora da allowlist de candidatos.")
                    continue
                count = self.db.desativar_fato_por_chave(ck_clean)
                deactivated_count += count
                logger.info(f"Fatos com canonical_key '{ck_clean}' desativados ({count} registros).")

        # 1. Desativa fatos contraditos com proteção de allowlist
        for deact in consolidation.get("facts_to_deactivate", []):
            fact_id = deact.get("existing_fact_id")
            if fact_id:
                if candidate_ids and fact_id not in candidate_ids:
                    logger.warning(f"Desativação de fato ID {fact_id} rejeitada: ID fora da allowlist de candidatos.")
                    continue
                self.db.desativar_fato(fact_id)
                deactivated_count += 1
                logger.info(f"Fato ID {fact_id} desativado: {deact.get('reason')}")

        # 2. Processa fatos orientados pela DECISION
        for fc in consolidation.get("facts_to_create", []):
            fato_text = (fc.get("fato") or "").strip()
            decision = str(fc.get("decision", "new")).strip().lower()

            # Sanitização e Whitelist de Decisão
            if decision not in ("new", "same", "update", "contradiction", "ignore"):
                decision = "new"

            # Caso IGNORE: nenhuma mutação
            if decision == "ignore":
                ignored_count += 1
                continue

            # Validação e Clamping de Domínio (P1.6)
            cat = str(fc.get("category", "geral")).strip().lower()
            if cat not in ("preferencia", "rotina", "trabalho", "projeto", "hobby",
                           "relacionamento", "pessoal", "saude", "outro", "geral"):
                cat = "geral"

            try:
                imp = max(0.0, min(1.0, float(fc.get("importance", 0.5))))
            except (ValueError, TypeError):
                imp = 0.5

            try:
                conf = max(0.0, min(1.0, float(fc.get("confidence", 1.0))))
            except (ValueError, TypeError):
                conf = 1.0

            tier = str(fc.get("memory_tier", "standard")).strip().lower()
            if tier not in ("core", "standard", "contextual"):
                tier = "standard"

            vol = str(fc.get("volatility", "medium")).strip().lower()
            if vol not in ("stable", "medium", "volatile"):
                vol = "medium"

            ck = _normalize_canonical_key(fc.get("canonical_key"))
            existing_id = fc.get("existing_fact_id") or fc.get("supersedes_id")

            # --- DECISION: SAME (Reafirmação / Confirmação) ---
            if decision == "same":
                target_id = None
                # 1. Se informou existing_fact_id, valida no allowlist
                if existing_id:
                    if not candidate_ids or existing_id in candidate_ids:
                        target_id = existing_id
                    else:
                        logger.warning(f"decision=same: existing_fact_id {existing_id} rejeitado (fora da allowlist).")

                # 2. Se não informou ID ou falhou, tenta resolver com segurança exclusivamente entre os candidatos
                if not target_id and candidates_list:
                    # Tenta match por canonical_key única
                    if ck:
                        matching_by_key = [c for c in candidates_list if c.get("canonical_key") == ck and c.get("active", 1)]
                        if len(matching_by_key) == 1:
                            target_id = matching_by_key[0]["id"]

                    # Tenta match por texto idêntico/normalizado
                    if not target_id and fato_text:
                        matching_by_text = [
                            c for c in candidates_list
                            if c.get("fato", "").strip().lower() == fato_text.lower() and c.get("active", 1)
                        ]
                        if len(matching_by_text) == 1:
                            target_id = matching_by_text[0]["id"]

                # 3. Se ainda assim não resolveu e candidate_ids está vazio (chamada direta de teste)
                if not target_id and existing_id:
                    target_id = existing_id

                if target_id:
                    confirmed = self.db.confirmar_fato(target_id)
                    if confirmed:
                        confirmed_count += 1
                        logger.info(f"Fato ID {target_id} reafirmado com sucesso (decision=same).")
                    else:
                        logger.warning(f"decision=same: Falha ao confirmar fato ID {target_id} (inativo ou inexistente).")
                else:
                    logger.warning(f"decision=same para '{fato_text}': Alvo ambíguo ou não identificado. Mutação ignorada por segurança.")
                continue

            # --- DECISION: UPDATE ou CONTRADICTION (Substituição Atômica) ---
            if decision in ("update", "contradiction"):
                target_id = None
                if existing_id:
                    if not candidate_ids or existing_id in candidate_ids:
                        target_id = existing_id
                    else:
                        logger.warning(f"decision={decision}: existing_fact_id {existing_id} rejeitado (fora da allowlist).")

                if not target_id and ck and candidates_list:
                    matching_by_key = [c for c in candidates_list if c.get("canonical_key") == ck and c.get("active", 1)]
                    if len(matching_by_key) == 1:
                        target_id = matching_by_key[0]["id"]

                if not target_id and existing_id and not candidate_ids:
                    target_id = existing_id

                if target_id:
                    new_fact_data = {
                        "fato": fato_text,
                        "category": cat,
                        "importance": imp,
                        "confidence": conf,
                        "source_conversation_id": end_conv_id,
                        "memory_tier": tier,
                        "volatility": vol,
                        "canonical_key": ck
                    }
                    new_id = self.db.substituir_fato_atomicamente(target_id, new_fact_data)
                    if new_id:
                        if new_id == target_id:
                            # Caso seguro de texto idêntico confirmado
                            confirmed_count += 1
                        else:
                            updated_count += 1
                            deactivated_count += 1
                        logger.info(f"Fato ID {target_id} substituído com sucesso por novo ID {new_id} (decision={decision}).")
                    else:
                        logger.warning(f"Falha atômica ao substituir fato ID {target_id}. Fato original preservado.")
                else:
                    logger.warning(f"decision={decision} para '{fato_text}': ID alvo não resolvido no allowlist. Nenhuma substituição realizada.")
                continue

            # --- DECISION: NEW (Inserção de Novo Fato) ---
            # Não desativa fatos anteriores automaticamente apenas pela presença de canonical_key!
            if not fato_text:
                continue

            row_id = self.db.adicionar_fato_patrick(
                fato=fato_text,
                category=cat,
                importance=imp,
                confidence=conf,
                source_conversation_id=end_conv_id,
                supersedes_id=existing_id,
                memory_tier=tier,
                volatility=vol,
                canonical_key=ck
            )
            if row_id and row_id > 0:
                created_count += 1
                logger.info(f"Novo fato aprendido: '{fato_text}' (Categoria: {cat} | Tier: {tier} | Key: {ck})")
            else:
                logger.info(f"Fato '{fato_text}' já existia no banco e foi ignorado pelo SQLite UNIQUE constraint.")

        # 3. Registra momentos marcantes
        for mom in consolidation.get("important_moments", []):
            mom_text = (mom.get("momento") or "").strip()
            if not mom_text:
                continue
            try:
                imp = max(0.0, min(1.0, float(mom.get("importance", 0.8))))
            except (ValueError, TypeError):
                imp = 0.8
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
            "confirmed": confirmed_count,
            "updated": updated_count,
            "deactivated": deactivated_count,
            "ignored": ignored_count,
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
