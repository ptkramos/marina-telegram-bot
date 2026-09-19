"""
Módulo de Recuperação Seletiva de Memória (Memory Retriever 2.0).
Substitui a injeção estática e cega de todos os fatos no prompt por busca híbrida contextual:
FTS5 multi-tipo + Core Memories + Ranking Híbrido Ponderado (com effective_confidence e volatilidade)
+ Deduplicação por diversidade e canonical_key + Fallback legado via feature flag.
"""
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict
from db import db_manager, DatabaseManager
from config import settings

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
            days = (datetime.now(dt.tzinfo) - dt).total_seconds() / 86400.0
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

    def compute_effective_confidence(self, fact: dict) -> float:
        """
        Calcula a confiança efetiva em tempo de retrieval baseada em volatilidade e idade:
        - stable: quase sem penalidade (apenas leve atenuação após 1 ano).
        - medium: sem penalidade até 90 dias, redução gradual posterior.
        - volatile: sem penalidade até 30 dias, redução gradual posterior.
        Não muta o banco de dados.
        """
        raw_conf = float(fact.get("confidence", 1.0))
        volatility = str(fact.get("volatility", "medium")).lower()

        timestamp_iso = fact.get("last_confirmed_at") or fact.get("updated_at") or fact.get("created_at")
        if not timestamp_iso:
            return raw_conf

        try:
            dt = datetime.fromisoformat(timestamp_iso)
            days = (datetime.now(dt.tzinfo) - dt).total_seconds() / 86400.0
        except Exception:
            return raw_conf

        if days <= 0:
            return raw_conf

        if volatility == "stable":
            if days > 365:
                penalty = min(0.05, ((days - 365) / 365.0) * 0.05)
                return min(raw_conf, max(0.0, round(raw_conf - penalty, 4)))
            return raw_conf
        elif volatility == "volatile":
            if days > 30:
                penalty = min(0.60, ((days - 30) / 60.0) * 0.60)
                return min(raw_conf, max(0.10, round(raw_conf - penalty, 4)))
            return raw_conf
        else:  # medium
            if days > 90:
                penalty = min(0.30, ((days - 90) / 90.0) * 0.30)
                return min(raw_conf, max(0.30, round(raw_conf - penalty, 4)))
            return raw_conf

    def compute_hybrid_score(
        self,
        fact: dict,
        lexical_score: float = 0.05,
        is_fts_match: bool = False,
        fts_rank: float = 0.0
    ) -> float:
        """
        Calcula pontuação híbrida normalizada (0.0 a 1.0):
        - Relevância Léxica / Contextual ponderada por FTS (default 40%)
        - Importância (default 20%)
        - Confiança Efetiva com Volatilidade (default 15%)
        - Frescor / Recência (default 10%)
        - Bônus de Core Memory (default 10%)
        - Desempate por histórico de acesso (default 5%)
        """
        # Se foi passado fts_rank relativo ou is_fts_match sem lexical_score específico
        if is_fts_match and lexical_score <= 0.05:
            if fts_rank < 0:
                lexical_score = min(1.0, 0.35 + 0.65 * abs(fts_rank) / (1.0 + abs(fts_rank)))
            else:
                lexical_score = 0.75

        importance = float(fact.get("importance", 0.5))
        effective_conf = self.compute_effective_confidence(fact)

        freshness_ts = fact.get("last_confirmed_at") or fact.get("updated_at") or fact.get("created_at")
        freshness = self._compute_freshness(freshness_ts)

        is_core = fact.get("memory_tier") == "core"
        core_bonus = 1.0 if is_core else 0.0

        access_count = fact.get("access_count", 0)
        access_bonus = min(1.0, access_count / 10.0)

        weights = settings.memory_weights()
        w_lex = weights["LEXICAL"]
        w_imp = weights["IMPORTANCE"]
        w_cnf = weights["CONFIDENCE"]
        w_frs = weights["FRESHNESS"]
        w_cor = weights["CORE"]
        w_acc = weights["ACCESS"]

        total_score = (
            (lexical_score * w_lex) +
            (importance * w_imp) +
            (effective_conf * w_cnf) +
            (freshness * w_frs) +
            (core_bonus * w_cor) +
            (access_bonus * w_acc)
        )
        return round(total_score, 4)

    def _retrieve_context_legacy(
        self,
        user_message: str = "",
        max_facts: int = 5,
        max_moments: int = 2,
        max_summaries: int = 1,
        record_access: bool = True
    ) -> Dict[str, list]:
        """Recuperação de memória no modo legado v3.4.3 (sem ranking composto, sem tiers ou volatilidade)."""
        keywords = self.extract_keywords(user_message)
        selected_facts = []
        seen_ids = set()

        if keywords:
            for kw in keywords[:3]:
                fts_results = self.db.buscar_fatos_fts(kw, limit=max_facts)
                for res in fts_results:
                    if res["id"] not in seen_ids:
                        selected_facts.append(res)
                        seen_ids.add(res["id"])
                    if len(selected_facts) >= max_facts:
                        break
                if len(selected_facts) >= max_facts:
                    break

        if len(selected_facts) < max_facts:
            all_facts = self.db.get_fatos_patrick_detalhados(active_only=True)
            for f in all_facts:
                if f["id"] not in seen_ids:
                    selected_facts.append(f)
                    seen_ids.add(f["id"])
                if len(selected_facts) >= max_facts:
                    break

        if record_access:
            for sf in selected_facts:
                if sf.get("id"):
                    try:
                        self.db.registrar_acesso_fato(sf["id"])
                    except Exception:
                        pass

        moments = self.db.get_momentos_marcantes(active_only=True)[-max_moments:]
        summaries_data = self.db.get_resumos_conversa(limit=max_summaries)
        summaries = [s["summary"] for s in summaries_data if s.get("summary")]

        return {
            "fatos": [sf["fato"] for sf in selected_facts],
            "momentos": moments,
            "resumos": summaries,
            "fatos_detalhados": selected_facts
        }

    def retrieve_context(
        self,
        user_message: str = "",
        max_facts: int = 5,
        max_moments: int = 3,
        max_summaries: int = 2,
        record_access: bool = True
    ) -> Dict[str, list]:
        """
        Recupera as memórias mais relevantes para a mensagem atual:
        1. FTS5 multi-tipo com relevância lexical relativa
        2. Injeção de Core Memories estáveis
        3. Pool limitado de fallback (sem full table scan)
        4. Ranking Híbrido com pontuação ponderada e effective_confidence
        5. Deduplicação por diversidade e canonical_key
        6. Controle de side-effects de access_count (record_access)
        """
        keywords = self.extract_keywords(user_message)
        candidates_map: Dict[int, dict] = {}
        lexical_scores: Dict[int, float] = {}

        # 1. Busca por palavras-chave via FTS5 em fatos com pontuação relativa
        if keywords:
            for kw in keywords[:4]:
                fts_results = self.db.buscar_fatos_fts(kw, limit=4)
                for rank_idx, res in enumerate(fts_results):
                    fid = res["id"]
                    candidates_map[fid] = res
                    # Rank score decrescente pela posição relativa do resultado FTS
                    pos_score = 1.0 / (1.0 + rank_idx * 0.35)
                    if fid in lexical_scores:
                        lexical_scores[fid] = min(1.0, lexical_scores[fid] + (pos_score * 0.30))
                    else:
                        lexical_scores[fid] = pos_score

        # 2. Carrega Core Memories
        core_memories = self.db.get_core_memories(limit=5)
        for cm in core_memories:
            fid = cm["id"]
            if fid not in candidates_map:
                candidates_map[fid] = cm

        # 3. Carrega pool limitado de candidatos ativos como fallback (SEM full-table scan)
        pool_size = getattr(settings, "MEMORY_CANDIDATE_POOL_SIZE", 20)
        fallback_candidates = self.db.get_memory_fallback_candidates(limit=pool_size)
        for f in fallback_candidates:
            fid = f["id"]
            if fid not in candidates_map:
                candidates_map[fid] = f

        # 4. Aplica Ranking Híbrido em todos os candidatos
        scored_facts = []
        for fid, f in candidates_map.items():
            lex_score = lexical_scores.get(fid, 0.05)
            is_fts = fid in lexical_scores
            fts_r = float(f.get("rank", 0.0))
            score = self.compute_hybrid_score(f, lexical_score=lex_score, is_fts_match=is_fts, fts_rank=fts_r)
            f_copy = dict(f)
            f_copy["hybrid_score"] = score
            f_copy["effective_confidence"] = self.compute_effective_confidence(f)
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

        # Atualiza métrica de acesso no banco para fatos selecionados APENAS se record_access for True
        retrieved_fact_strings = []
        for sf in selected_facts:
            fact_id = sf.get("id")
            if record_access and fact_id:
                try:
                    self.db.registrar_acesso_fato(fact_id)
                except Exception:
                    pass
            
            # Anotação de cautela para reconfirmação se a confiança efetiva for baixa (< 0.5)
            eff_conf = sf.get("effective_confidence", 1.0)
            if eff_conf < 0.5:
                retrieved_fact_strings.append(f"{sf['fato']} (lembrança vaga; reconfirmar naturalmente antes de afirmar)")
            elif eff_conf < 0.8:
                retrieved_fact_strings.append(f"{sf['fato']} (pode estar desatualizado; tratar com cautela)")
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
