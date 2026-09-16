"""
Módulo de Recuperação Seletiva de Memória (Memory Retriever).
Substitui a injeção estática e cega de todos os fatos no prompt por busca híbrida contextual:
FTS5 (palavras-chave da mensagem) + relevância permanente + recência de acesso.
"""
import re
import logging
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

    def retrieve_context(
        self,
        user_message: str = "",
        max_facts: int = 5,
        max_moments: int = 2,
        max_summaries: int = 1
    ) -> Dict[str, list]:
        """
        Recupera as memórias mais relevantes para a mensagem atual:
        1. FTS5 matching baseado nas palavras-chave da mensagem
        2. Fatos essenciais / alta importância (ex: nome, namoro, preferências centrais)
        3. Momentos marcantes relacionados ou recentes
        4. Resumos de conversas anteriores relevantes
        """
        keywords = self.extract_keywords(user_message)
        matched_facts: List[dict] = []

        # 1. Busca por palavras-chave via FTS5
        if keywords:
            for kw in keywords[:4]:
                fts_results = self.db.buscar_fatos_fts(kw, limit=3)
                for res in fts_results:
                    if not any(f["id"] == res["id"] for f in matched_facts):
                        matched_facts.append(res)
                if len(matched_facts) >= max_facts:
                    break

        # 2. Fatos de alta importância / fundamentais (sempre carregados até o limite)
        all_facts = self.db.get_fatos_patrick_detalhados(active_only=True)
        selected_facts: List[dict] = []

        # Adiciona os matches FTS primeiro
        for f in matched_facts[:max_facts]:
            selected_facts.append(f)

        # Preenche com os fatos mais importantes caso haja espaço
        for f in all_facts:
            if len(selected_facts) >= max_facts:
                break
            if not any(sf["id"] == f["id"] for sf in selected_facts):
                selected_facts.append(f)

        # Atualiza métrica de acesso no banco para fatos selecionados
        retrieved_fact_strings = []
        for sf in selected_facts:
            fact_id = sf.get("id")
            if fact_id:
                try:
                    self.db.registrar_acesso_fato(fact_id)
                except Exception:
                    pass
            retrieved_fact_strings.append(sf["fato"])

        # 3. Momentos marcantes (prioriza recentes / ativos)
        all_moments = self.db.get_momentos_marcantes(active_only=True)
        selected_moments = all_moments[-max_moments:] if all_moments else []

        # 4. Resumos de conversas anteriores (traz o mais recente se existir)
        resumos = self.db.get_resumos_conversa(limit=max_summaries)
        selected_summaries = [r["summary"] for r in resumos if r.get("summary")]

        return {
            "fatos": retrieved_fact_strings,
            "momentos": selected_moments,
            "resumos": selected_summaries,
            "fatos_detalhados": selected_facts
        }


memory_retriever = MemoryRetriever()
