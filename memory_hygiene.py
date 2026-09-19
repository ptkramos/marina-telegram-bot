"""
memory_hygiene.py — Serviço de Higiene e Manutenção de Memória (Release 3.5.3).

Executa rotinas periódicas (diárias ou on-demand) para manter a memória da Marina saudável,
relevante e livre de ruídos:
1. Confidence Decay: aplica decaimento controlado baseado em volatilidade ('volatile', 'medium', 'stable', 'core').
2. Deduplicação Leve: inativa réplicas mais antigas de fatos ativos com canonical_keys redundantes.
3. Arquivamento de Open Loops: move loops resolvidos ou abandonados há mais de 30 dias para o arquivo.
4. Identificação de Reconfirmação Natural: sinaliza memórias antigas que devem ser checadas suavemente com Patrick.
"""
import logging
from datetime import datetime
from typing import Optional

from config import settings
from db import db_manager, DatabaseManager

logger = logging.getLogger("MemoryHygiene")


class MemoryHygieneService:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or db_manager

    def run_hygiene_cycle(self, now: Optional[datetime] = None, force: bool = False) -> dict:
        """
        Executa um ciclo completo de higiene e manutenção da memória.
        Retorna um dicionário com as métricas da execução.
        """
        if not getattr(settings, "MEMORY_HYGIENE_ENABLED", False) and not force:
            logger.info("Memory Hygiene desativado por feature flag (MEMORY_HYGIENE_ENABLED=False).")
            return {"status": "disabled", "success": False}

        now_dt = now or datetime.now()
        logger.info(f"Iniciando ciclo de Memory Hygiene ({now_dt.isoformat()})...")

        # 1. Decay de Confiança
        decay_stats = self.db.aplicar_confidence_decay(
            dias_volatil=14,
            dias_medio=60,
            now=now_dt
        )
        logger.info(f"Memory Hygiene: decay aplicado em {decay_stats['decayed_count']} fatos, {decay_stats['reconfirmation_flagged']} sinalizados para reconfirmação.")

        # 2. Deduplicação leve
        dedup_count = self.db.deduplicar_fatos_redundantes()
        if dedup_count > 0:
            logger.info(f"Memory Hygiene: {dedup_count} fatos redundantes inativados.")

        # 3. Arquivamento de Open Loops antigos
        archived_loops = self.db.arquivar_open_loops_antigos(dias=30)
        if archived_loops > 0:
            logger.info(f"Memory Hygiene: {archived_loops} open loops antigos arquivados.")

        # 4. Candidatos a reconfirmação
        reconf_cands = self.db.get_memorias_para_reconfirmacao(limit=3)

        world_hygiene = None
        if getattr(settings, 'WORLD_HYGIENE_ENABLED', False) and True:
            from world_hygiene import WorldHygiene
            world_hygiene = WorldHygiene(self.db).run_cycle(now=now_dt)

        result = {
            "timestamp": now_dt.isoformat(),
            "decay": decay_stats,
            "deduplicated_count": dedup_count,
            "archived_loops_count": archived_loops,
            "reconfirmation_candidates_count": len(reconf_cands),
            "reconfirmation_candidates": [c["fato"] for c in reconf_cands],
            "world_hygiene": world_hygiene,
            "status": "completed",
            "success": True
        }
        logger.info(f"Ciclo de Memory Hygiene concluído com sucesso: {result}")
        return result

    def get_reconfirmation_prompt_suggestion(self) -> Optional[str]:
        """
        Retorna uma sugestão sutil para a Marina reconfirmar uma memória antiga no diálogo
        Ex: 'você ainda tá mexendo naquele projeto X?'
        """
        cands = self.db.get_memorias_para_reconfirmacao(limit=1)
        if not cands:
            return None
        fato = cands[0]["fato"]
        return f"Você pode checar carinhosamente com o Patrick se a seguinte informação ainda é válida: '{fato}'"


memory_hygiene_service = MemoryHygieneService()

