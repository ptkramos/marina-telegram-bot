"""
Módulo de Recuperação Seletiva de Memória (Memory Retriever).
Substitui a injeção estática e cega de todos os fatos no prompt por busca híbrida contextual:
FTS5 (palavras-chave da mensagem) + relevância permanente + recência de acesso.
"""
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict
from db import db_manager, DatabaseManager

logger = logging.getLogger("MemoryRetriever")

STOP_WORDS = {
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "é", "com", "não",
    "uma", "os", "no", "se", "na", "por", "mais", "as", "dos", "como", "mas", "foi",
    "ao", "ele", "das", "tem", "à", "seu", "sua", "ou", "ser", "quando", "muito",
    "nos", "já", "está", "eu", "também", "só", "pelo", "pela", "até", "isso", "ela",
    "entre", "era", "depois", "sem", "mesmo", "aos", "ter", "seus", "quem", "nas",
    "me", "esse", "eles", "estão", "você", "tinha", "foram", "essa", "num", "nem",
    "suas", "meu", "às", "minha", "têm", "numa", "pelos", "elas", "havia", "seja",
    "qual", "será", "nós", "tenho", "lhe", "deles", "essas", "esses", "pelas", "este",
    "fosse", "dele", "tu", "te", "vocês", "vos", "lhes", "meus", "minhas", "teu",
    "tua", "teus", "tuas", "nosso", "nossa", "nossos", "nossas", "dela", "delas",
    "esta", "estes", "estas", "aquele", "aquela", "aqueles", "aquelas", "isto", "aquilo",
    "estou", "está", "estamos", "estão", "estive", "esteve", "estivemos", "estiveram",
    "hei", "havemos", "houve", "houveram", "houver", "houvera", "houvéramos", "haja",
    "hajam", "hajamos", "houvesse", "houvessem", "houvéssemos", "houver", "houvermos",
    "houverem", "houverei", "houverá", "houveremos", "houverão", "houveria", "houveriam",
    "sou", "somos", "são", "fui", "fomos", "fôramos", "seja", "sejamos", "sejam",
    "fosse", "fôssemos", "fossem", "for", "formos", "forem", "serei", "será", "seremos",
    "serão", "seria", "seríamos", "seriam", "tenho", "tem", "temos", "têm", "tinha",
    "tínhamos", "tinham", "tive", "teve", "tivemos", "tiveram", "tivera", "tivéramos",
    "tenha", "tenhamos", "tenham", "tivesse", "tivéssemos", "tivessem", "tiver",
    "tivermos", "tiverem", "terei", "terá", "teremos", "terão", "teria", "teríamos",
    "teriam", "amor", "vida", "marina", "patrick", "oi", "ola", "olá", "oie", "bom",
    "boa", "dia", "tarde", "noite", "kkkk", "haha", "rsrs", "tudo", "bem", "aí", "sim"
}


class MemoryRetriever:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or db_manager

    def extract_keywords(self, text: str) -> List[str]:
        """Extrai palavras-chave significativas do texto do usuário."""
        if not text:
            return []
        tokens = re.findall(r'\b[a-zA-ZáéíóúÁÉÍÓÚâêîôûÂÊÎÔÛãõÃÕçÇ0-9]{3,}\b', text.lower())
        keywords = [t for t in tokens if t not in STOP_WORDS]
        return keywords[:8]

    def _compute_freshness(self, timestamp_iso: Optional[str]) -> float:
        """Calcula fator de frescor (0.0 a 1.0) baseado na data de criação/confirmação."""
        if not timestamp_iso:
            return 0.5
        try:
            dt = datetime.fromisoformat(timestamp_iso)
            days = (datetime.now() - dt).total_seconds() / 86400.0
            if days <= 7:
                return 1.0
            elif days <= 30:
                return 0.8
            elif days <= 90:
                return 0.5
            elif days <= 180:
                return 0.3
            return 0.15
        except Exception:
            return 0.5

    def compute_hybrid_score(
        self,
        fact: dict,
        is_fts_match: bool = False,
        fts_rank: float = 0.0
    ) -> float:
        """
        Calcula pontuação híbrida normalizada (0.0 a 1.0):
        - 40% Relevância Léxica / Contextual
        - 20% Importância
        - 15% Confiança
        - 10% Frescor / Recência
        - 10% Bônus de Core Memory
        - 5%  Desempate por histórico de acesso (evitando loop de popularidade)
        """
        lexical_score = 1.0 if is_fts_match else 0.05
        importance = float(fact.get("importance", 0.5))
        confidence = float(fact.get("confidence", 1.0))
        
        freshness_ts = fact.get("last_confirmed_at") or fact.get("updated_at") or fact.get("created_at")
        freshness = self._compute_freshness(freshness_ts)

        is_core = fact.get("memory_tier") == "core"
        core_bonus = 1.0 if is_core else 0.0

        access_count = fact.get("access_count", 0)
        access_bonus = min(1.0, access_count / 10.0)

        total_score = (
            (lexical_score * 0.40) +
            (importance * 0.20) +
            (confidence * 0.15) +
            (freshness * 0.10) +
            (core_bonus * 0.10) +
            (access_bonus * 0.05)
        )
        return round(total_score, 4)

    def retrieve_context(
        self,
        user_message: str = "",
        max_facts: int = 5,
        max_moments: int = 2,
        max_summaries: int = 1
    ) -> Dict[str, list]:
        """
        Recupera as memórias mais relevantes para a mensagem atual:
        1. FTS5 multi-tipo em fatos, momentos e resumos
        2. Injeção de Core Memories estáveis
        3. Ranking Híbrido com pontuação balanceada
        4. Deduplicação por diversidade e canonical_key
        """
        keywords = self.extract_keywords(user_message)
        candidates_map: Dict[int, dict] = {}
        fts_matched_ids = set()

        # 1. Busca por palavras-chave via FTS5 em fatos
        if keywords:
            for kw in keywords[:4]:
                fts_results = self.db.buscar_fatos_fts(kw, limit=4)
                for res in fts_results:
                    fid = res["id"]
                    candidates_map[fid] = res
                    fts_matched_ids.add(fid)

        # 2. Carrega Core Memories
        core_memories = self.db.get_core_memories(limit=4)
        for cm in core_memories:
            fid = cm["id"]
            if fid not in candidates_map:
                candidates_map[fid] = cm

        # 3. Carrega fatos ativos adicionais para avaliação
        all_facts = self.db.get_fatos_patrick_detalhados(active_only=True)
        for f in all_facts:
            fid = f["id"]
            if fid not in candidates_map:
                candidates_map[fid] = f

        # 4. Aplica Ranking Híbrido em todos os candidatos
        scored_facts = []
        for fid, f in candidates_map.items():
            is_fts = fid in fts_matched_ids
            score = self.compute_hybrid_score(f, is_fts_match=is_fts)
            f_copy = dict(f)
            f_copy["hybrid_score"] = score
            scored_facts.append(f_copy)

        # Ordena pela pontuação híbrida decrescente
        scored_facts.sort(key=lambda x: x["hybrid_score"], reverse=True)

        # 5. Deduplicação por Diversidade (Canonical Key e Categorias)
        selected_facts: List[dict] = []
        seen_canonical_keys = set()
        category_counts: Dict[str, int] = {}

        for f in scored_facts:
            if len(selected_facts) >= max_facts:
                break

            ck = f.get("canonical_key")
            if ck and ck in seen_canonical_keys:
                continue

            cat = f.get("category", "geral")
            # Limita a no máximo 2 fatos da mesma categoria se houver outros
            if category_counts.get(cat, 0) >= 2 and len(scored_facts) > max_facts:
                continue

            selected_facts.append(f)
            if ck:
                seen_canonical_keys.add(ck)
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Preenche até max_facts caso o filtro de categoria tenha sido estrito demais
        if len(selected_facts) < max_facts:
            for f in scored_facts:
                if len(selected_facts) >= max_facts:
                    break
                if not any(sf["id"] == f["id"] for sf in selected_facts):
                    ck = f.get("canonical_key")
                    if ck and ck in seen_canonical_keys:
                        continue
                    selected_facts.append(f)
                    if ck:
                        seen_canonical_keys.add(ck)

        # Atualiza métrica de acesso no banco para fatos selecionados
        retrieved_fact_strings = []
        for sf in selected_facts:
            fact_id = sf.get("id")
            if fact_id:
                try:
                    self.db.registrar_acesso_fato(fact_id)
                except Exception:
                    pass
            
            # Se confiança for baixa (< 0.5), sinaliza sutileza para reconfirmação
            conf = float(sf.get("confidence", 1.0))
            if conf < 0.5:
                retrieved_fact_strings.append(f"{sf['fato']} (lembrança vaga/a confirmar)")
            else:
                retrieved_fact_strings.append(sf["fato"])

        # 6. Momentos marcantes com suporte a FTS5 + recentes
        selected_moments = []
        if keywords:
            for kw in keywords[:3]:
                mom_results = self.db.buscar_momentos_fts(kw, limit=max_moments)
                for mr in mom_results:
                    txt = mr.get("momento")
                    if txt and txt not in selected_moments:
                        selected_moments.append(txt)
                if len(selected_moments) >= max_moments:
                    break

        if len(selected_moments) < max_moments:
            all_moments = self.db.get_momentos_marcantes(active_only=True)
            for m in reversed(all_moments):
                if len(selected_moments) >= max_moments:
                    break
                if m not in selected_moments:
                    selected_moments.append(m)

        # 7. Resumos de conversas anteriores com suporte a FTS5 + recentes
        selected_summaries = []
        if keywords:
            for kw in keywords[:2]:
                res_results = self.db.buscar_resumos_fts(kw, limit=max_summaries)
                for rr in res_results:
                    s_txt = rr.get("summary")
                    if s_txt and s_txt not in selected_summaries:
                        selected_summaries.append(s_txt)
                if len(selected_summaries) >= max_summaries:
                    break

        if len(selected_summaries) < max_summaries:
            recent_resumos = self.db.get_resumos_conversa(limit=max_summaries)
            for r in recent_resumos:
                s_txt = r.get("summary")
                if s_txt and s_txt not in selected_summaries:
                    selected_summaries.append(s_txt)
                if len(selected_summaries) >= max_summaries:
                    break

        return {
            "fatos": retrieved_fact_strings,
            "momentos": selected_moments,
            "resumos": selected_summaries,
            "fatos_detalhados": selected_facts
        }


memory_retriever = MemoryRetriever()
