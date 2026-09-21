"""
Módulo de Consolidação de Memória de Longo Prazo da Marina Salles (v3.7.0).
Analisa lotes de conversas de forma assíncrona para extrair fatos permanentes sobre Patrick,
detectar e resolver contradições, registrar momentos marcantes e gerar resumos temáticos.
Implementa controle estrito por 'decision', allowlist de candidatos anti-alucinação,
substituição atômica e validação de domínio.
"""
import re
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


# Auditoria #2: prompt traduzido para pt-BR (o Patch 021 mostrou que instrução
# em inglês sobre texto português degrada a saída) e regras de memory_tier
# ampliadas. Antes, a única regra que produzia tier='core' era o pedido
# explícito do Patrick ("lembra disso"), então na prática nenhum fato virava
# core — e o passo do MemoryRetriever que carrega core memories em todo turno,
# independente de palavra-chave, ficava inerte. O contrato da 3.5.0 define core
# como "projeto central, fato forte do relacionamento, preferência muito
# importante, informação explicitamente pedida para lembrar": quatro casos, dos
# quais só o último estava implementado.
CONSOLIDATOR_SYSTEM_PROMPT = """Extraia fatos duráveis sobre o Patrick Ramos para a memória da Marina Salles (namorada dele) a partir do diálogo recente.

REGRAS DE CLASSIFICAÇÃO:
1. Ignore conversa fiada (oi, kkk, emojis, ok, elogio vazio, cumprimento). Use decision='ignore' quando não houver conteúdo durável.
2. Extraia apenas preferências, rotina, planos futuros, projetos ou fatos relevantes de longo prazo.
3. Se o Patrick reafirma algo que já existe na lista de fatos conhecidos: decision='same', existing_fact_id=FACT_ID. NÃO crie fato duplicado.
4. Se contradiz ou atualiza um fato conhecido: decision='update' ou 'contradiction', existing_fact_id=ID_ANTIGO, supersedes_id=ID_ANTIGO, e descreva o fato novo.
5. Se é um fato completamente novo: decision='new', existing_fact_id=null, supersedes_id=null.
6. Se o Patrick pede explicitamente para lembrar ("lembra disso", "guarda isso", "não esquece"): memory_tier='core', importance>=0.90, confidence=1.0.
7. Se o Patrick revoga explicitamente ("esquece isso", "não guarda mais", "não vale mais"): inclua em 'keys_to_deactivate' ou 'facts_to_deactivate'.
8. Associe canonical_key (snake_case, ex.: jogo_atual, energetico_favorito, rotina_treino) para conceitos que mudam com o tempo.
9. Defina volatility: 'stable' (família, identidade, gostos fundamentais), 'medium' (jogos e projetos atuais), 'volatile' (rotina temporária, agenda da semana).

COMO ESCOLHER memory_tier:
- 'core' — identidade dele (nome, família, trabalho), projeto ou meta central da vida dele, fato forte do relacionamento de vocês, preferência muito importante, ou algo que ele pediu para lembrar. São os fatos que a Marina deveria ter presentes em qualquer conversa, mesmo sem ele mencionar o assunto.
- 'standard' — preferências, rotinas, projetos e planos normais. É o padrão: use quando estiver em dúvida.
- 'contextual' — detalhe de curto prazo que só importa nos próximos dias (compromisso pontual, tarefa da semana, algo que expira).

Seja criterioso com 'core': se tudo for core, nada é. Em geral um diálogo rende zero ou um fato core.

10. Responda ESTRITAMENTE em JSON, escrevendo fato, momento e topic_summary em português brasileiro:
{
  "facts_to_create": [
    {
      "fato": "frase em 3a pessoa, em português",
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
  "facts_to_deactivate": [{"existing_fact_id": 1, "reason": "motivo"}],
  "keys_to_deactivate": ["canonical_key_se_revogada"],
  "important_moments": [{"momento": "frase em português", "importance": 0.8}],
  "topic_summary": "resumo de uma frase em português ou null"
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
                # Keep the provider payload untouched here. Validation and
                # alias normalization belong to _validate_payload(), which
                # runs before any database write. Iterating malformed values
                # (for example `facts_to_create: null`) in this network-error
                # block used to turn a contract violation into an empty,
                # apparently successful consolidation.
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

    @staticmethod
    def _is_ambiguous_memory_text(value: Optional[str]) -> bool:
        """Identifica referências ambíguas ou genéricas que não devem ser persistidas como memória."""
        if not value or not isinstance(value, str):
            return False
        normalized = value.strip().casefold()
        ambiguous_markers = (
            "parecida com outra pessoa",
            "parecido com outra pessoa",
            "parecidas com outra pessoa",
            "parecidos com outra pessoa",
            "outra pessoa",
            "alguém desconhecido",
            "pessoa indeterminada",
        )
        return any(marker in normalized for marker in ambiguous_markers)

    @staticmethod
    def _validate_payload(payload: dict) -> dict:
        """Valida todo o JSON antes de qualquer escrita; metadados internos são preservados."""
        import math
        if not isinstance(payload, dict):
            raise MemoryConsolidationError("Resposta da consolidação deve ser objeto")
        clean = dict(payload)
        for name in ("facts_to_create", "facts_to_deactivate", "keys_to_deactivate", "important_moments"):
            items = payload.get(name, [])
            if not isinstance(items, list):
                raise MemoryConsolidationError(f"{name} deve ser lista")
            clean[name] = []
            for item in items:
                if name == "keys_to_deactivate":
                    if not isinstance(item, str) or not _normalize_canonical_key(item):
                        raise MemoryConsolidationError("Chave de revogação inválida")
                    clean[name].append(_normalize_canonical_key(item))
                    continue
                if not isinstance(item, dict):
                    raise MemoryConsolidationError(f"Item inválido em {name}")
                row = dict(item)
                for key in ("existing_fact_id", "supersedes_id"):
                    value = row.get(key)
                    if value is not None and (type(value) is not int or value <= 0):
                        raise MemoryConsolidationError(f"{key} deve ser inteiro positivo")
                if row.get("existing_fact_id") and row.get("supersedes_id") and row["existing_fact_id"] != row["supersedes_id"]:
                    raise MemoryConsolidationError("IDs conflitantes no mesmo item")
                if name == "facts_to_deactivate" and row.get("existing_fact_id") is None:
                    raise MemoryConsolidationError("Revogação sem ID")
                text_key = "fato" if name == "facts_to_create" else "momento"
                if name != "facts_to_deactivate":
                    if text_key not in row:
                        alt_keys = ("fact", "description", "content", "text") if text_key == "fato" else ("moment", "description", "content", "text")
                        for alt in alt_keys:
                            if alt in row and row[alt]:
                                row[text_key] = row[alt]
                                break
                    value = row.get(text_key, "")
                    if not isinstance(value, str):
                        raise MemoryConsolidationError(f"{text_key} deve ser texto")
                    row[text_key] = value.strip()
                    if MemoryConsolidator._is_ambiguous_memory_text(row[text_key]):
                        continue
                    for key, default in (("importance", 0.8 if name == "important_moments" else 0.5), ("confidence", 1.0)):
                        value = row.get(key, default)
                        try:
                            if isinstance(value, bool):
                                raise ValueError()
                            number = float(value)
                            if not math.isfinite(number):
                                raise ValueError()
                        except (TypeError, ValueError, OverflowError):
                            raise MemoryConsolidationError(f"{key} deve ser número finito")
                        row[key] = max(0.0, min(1.0, number))
                if name == "facts_to_create":
                    decision = row.get("decision", "new")
                    if not isinstance(decision, str) or decision.strip().lower() not in ("new", "same", "update", "contradiction", "ignore"):
                        raise MemoryConsolidationError("Decisão de memória inválida")
                    row["decision"] = decision.strip().lower()
                    if row["decision"] != "ignore" and not row["fato"]:
                        raise MemoryConsolidationError("Fato vazio")
                    for key, allowed, default in (
                        ("category", ("preferencia", "rotina", "trabalho", "projeto", "hobby", "relacionamento", "pessoal", "saude", "outro", "geral"), "geral"),
                        ("memory_tier", ("core", "standard", "contextual"), "standard"),
                        ("volatility", ("stable", "medium", "volatile"), "medium"),
                    ):
                        value = row.get(key, default)
                        value = value.strip().lower() if isinstance(value, str) else default
                        row[key] = value if value in allowed else default
                    if row.get("canonical_key") is not None and not isinstance(row["canonical_key"], str):
                        raise MemoryConsolidationError("canonical_key deve ser texto ou null")
                    row["canonical_key"] = _normalize_canonical_key(row.get("canonical_key"))
                    if row["decision"] == "new" and (row.get("existing_fact_id") or row.get("supersedes_id")):
                        raise MemoryConsolidationError("Novo fato não pode substituir um ID; use update")
                clean[name].append(row)
        summary = payload.get("topic_summary")
        if summary is not None and not isinstance(summary, str):
            raise MemoryConsolidationError("Resumo deve ser texto ou null")
        if summary and MemoryConsolidator._is_ambiguous_memory_text(summary):
            summary = None
        clean["topic_summary"] = summary
        return clean

    def apply_consolidation(
        self, consolidation: dict, start_conv_id: Optional[int] = None,
        end_conv_id: Optional[int] = None
    ) -> dict:
        payload = self._validate_payload(consolidation)
        candidate_ids = {i for i in (payload.get("_candidate_fact_ids") or []) if type(i) is int and i > 0}
        candidate_keys = set(payload.get("_candidate_keys") or [])
        candidates = [c for c in (payload.get("_candidates") or []) if c.get("id") in candidate_ids and c.get("active", 1)]

        def target_for(row):
            explicit = row.get("existing_fact_id") or row.get("supersedes_id")
            if explicit is not None:
                if explicit in candidate_ids:
                    return explicit
                logger.warning("Alvo rejeitado: ID %s fora dos candidatos", explicit)
                return None
            key = row.get("canonical_key")
            matches = [c for c in candidates if key and c.get("canonical_key") == key]
            if len(matches) == 1:
                return matches[0]["id"]
            if row["decision"] == "same":
                matches = [c for c in candidates if c.get("fato", "").strip().casefold() == row["fato"].casefold()]
                if len(matches) == 1:
                    return matches[0]["id"]
            logger.warning("Alvo ausente ou ambíguo; operação ignorada")
            return None

        revocations = set()
        for row in payload["facts_to_deactivate"]:
            if row["existing_fact_id"] in candidate_ids:
                revocations.add(row["existing_fact_id"])
            else:
                logger.warning("Revogação rejeitada: ID fora dos candidatos")
        for key in payload["keys_to_deactivate"]:
            if key not in candidate_keys:
                logger.warning("Revogação rejeitada: chave fora dos candidatos")
                continue
            revocations.update(c["id"] for c in candidates if c.get("canonical_key") == key)

        operations = []
        used_targets = set()
        for row in payload["facts_to_create"]:
            decision = row["decision"]
            target = target_for(row) if decision in ("same", "update", "contradiction") else None
            if decision == "ignore":
                ignored_target = row.get("existing_fact_id") or row.get("supersedes_id")
                ignored_ids = {ignored_target} if ignored_target else {c["id"] for c in candidates if row.get("canonical_key") and c.get("canonical_key") == row["canonical_key"]}
                if ignored_ids & revocations:
                    raise MemoryConsolidationError("ignore e revogação conflitantes")
            if target is not None:
                if target in used_targets:
                    raise MemoryConsolidationError("Múltiplas decisões sobre o mesmo fato")
                used_targets.add(target)
                if decision == "same" and target in revocations:
                    raise MemoryConsolidationError("same e revogação conflitantes")
                if decision in ("update", "contradiction"):
                    revocations.discard(target)
            operations.append((row, target))

        result = dict(created=0, confirmed=0, updated=0, deactivated=0, ignored=0, moments=0, summary_saved=False)
        try:
            with self.db.transaction():
                for row, target in operations:
                    decision = row["decision"]
                    if decision == "ignore" or (decision != "new" and target is None):
                        result["ignored"] += 1
                        continue
                    if decision == "same":
                        if not self.db.confirmar_fato(target):
                            raise MemoryConsolidationError("Candidato não está mais ativo")
                        result["confirmed"] += 1
                    elif decision in ("update", "contradiction"):
                        data = dict(row, source_conversation_id=end_conv_id)
                        new_id = self.db.substituir_fato_atomicamente(target, data)
                        if not new_id:
                            raise MemoryConsolidationError("Replacement falhou; revertendo lote inteiro")
                        result["confirmed" if new_id == target else "updated"] += 1
                        result["deactivated"] += int(new_id != target)
                    else:
                        new_id = self.db.adicionar_fato_patrick(
                            fato=row["fato"], category=row["category"], importance=row["importance"],
                            confidence=row["confidence"], memory_tier=row["memory_tier"],
                            volatility=row["volatility"], canonical_key=row["canonical_key"],
                            source_conversation_id=end_conv_id
                        )
                        result["created"] += int(bool(new_id))
                for target in revocations:
                    if self.db.get_fato_detalhado(target):
                        self.db.desativar_fato(target)
                        result["deactivated"] += 1
                for row in payload["important_moments"]:
                    if row["momento"]:
                        self.db.adicionar_momento_marcante(row["momento"], importance=row["importance"], source_conversation_id=end_conv_id)
                        result["moments"] += 1
                summary = payload.get("topic_summary")
                if summary and len(summary.strip()) > 8:
                    self.db.salvar_resumo_conversa(topic=summary.strip(), summary=summary.strip(), start_conversation_id=start_conv_id, end_conversation_id=end_conv_id)
                    result["summary_saved"] = True
        except MemoryConsolidationError:
            raise
        except Exception as exc:
            raise MemoryConsolidationError("Falha ao aplicar lote; todas as escritas revertidas") from exc
        return result

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
