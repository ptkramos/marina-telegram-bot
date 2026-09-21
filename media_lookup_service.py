"""Media title lookup para Marina citar filme/série real em vez de inventar.

Patch 023 — Origem: soak 20/09/2026 22:57, Marina disse "Filme de Romance"
placeholder porque o CONTROL proibia inventar mas o prompt não trazia
referência real de mídia atual.

Contrato:
    - `refresh_if_stale(now)`  -> tenta buscar via DuckDuckGo se cache expirou.
    - `get_prompt_block(now)`  -> devolve `[MÍDIA REAL EM ALTA] ...` ou string
                                  vazia se sem dados (fail-open).

Cache no `real_context_cache` que já existe (chave `media_hot:br`).
TTL: `MEDIA_LOOKUP_REFRESH_HOURS` (default 24h). Se busca falhar, mantém
cache antigo até a próxima janela — nunca deixa a Marina no vácuo.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from calendar_world import RealContextCache, local_time
from config import settings
from db import DatabaseManager

logger = logging.getLogger("MediaLookup")

_CACHE_KEY = "media_hot:br"

# Consultas curtas em pt-BR pra pegar títulos que qualquer jovem brasileiro
# reconheceria. Cada consulta traz até 3 resultados; a gente combina.
_QUERIES = (
    "filmes em cartaz cinema brasil hoje",
    "séries mais assistidas netflix brasil essa semana",
    "animes populares crunchyroll 2026",
)

# Regex para extrair candidato de título entre aspas ou capitalizado no meio
# do snippet. Não é ciência exata — a gente só precisa de 5-8 candidatos.
# Auditoria #3: o lookahead era `(?=\s*(?:é|...))`. `\s*` aceita zero espaços e
# não havia fronteira de palavra, então o "é" de dentro de "séries" casava como
# o verbo "é" — "Top 10 Netflix: séries" virava o título "Top 10 Netflix: s", e
# o prompt da Marina recebeu "[MÍDIA REAL EM ALTA] - Veja as 10 s". Agora exige
# pelo menos um espaço e fronteira de palavra depois do gatilho.
_TITLE_RE = re.compile(
    r'["“]([A-ZÁÊÔÂÃÍÉÓÚ][^"”\n]{2,60})["”]'
    r'|([A-ZÁÊÔÂÃÍÉÓÚ][\wÁÊÔÂÃÍÉÓÚáêôâãíéóú:!?\'\- ]{2,50}?)'
    r'(?=\s+(?:é|estreou|estreia|foi lançado|entrou|chegou|na Netflix|na Amazon|no streaming|do momento)\b)'
)

# Manchetes de agregador que o regex captura mas não são títulos de obra.
_HEADLINE_PREFIXES = (
    "top ", "veja ", "confira ", "lista ", "ranking ", "os mais ", "as mais ",
    "melhores ", "netflix atualiza", "novidades ", "lançamentos ", "estreias ",
)


class MediaLookupService:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.cache = RealContextCache(db)

    def refresh_if_stale(self, now: Optional[datetime] = None) -> bool:
        """Refaz busca se cache expirou; devolve True quando algo foi refrescado."""
        if not getattr(settings, "MEDIA_LOOKUP_ENABLED", True):
            return False
        if not getattr(settings, "REAL_CONTEXT_FETCH_ENABLED", False):
            return False
        now = local_time(now or datetime.now())
        existing = self.cache.get(_CACHE_KEY, now=now)
        if existing:
            # cache.get já respeita expires_at, então qualquer hit é válido.
            return False
        try:
            titles = self._fetch_titles()
        except Exception as exc:
            logger.warning("media_lookup.fetch_fail exc=%s (mantendo cache antigo)", exc)
            return False
        if not titles:
            logger.info("media_lookup.fetch_empty (mantendo cache antigo)")
            return False
        ttl_hours = int(getattr(settings, "MEDIA_LOOKUP_REFRESH_HOURS", 24))
        expires_at = now + timedelta(hours=ttl_hours)
        try:
            self.cache.put(
                _CACHE_KEY, kind="media",
                payload={"titles": titles},
                source_name="ddgs:media_hot",
                observed_at=now, expires_at=expires_at,
            )
        except Exception as exc:
            logger.warning("media_lookup.cache_put_fail exc=%s", exc)
            return False
        logger.info("media_lookup.refreshed n=%d ttl_h=%d", len(titles), ttl_hours)
        return True

    def get_prompt_block(self, now: Optional[datetime] = None) -> str:
        """Bloco `[MÍDIA REAL EM ALTA]` para injetar no prompt. Vazio se sem dados."""
        if not getattr(settings, "MEDIA_LOOKUP_ENABLED", True):
            return ""
        now = local_time(now or datetime.now())
        entry = self.cache.get(_CACHE_KEY, now=now)
        if not entry:
            return ""
        titles = entry.get("payload", {}).get("titles") or []
        if not titles:
            return ""
        # Mostra até 8 títulos, um por linha, curto.
        shown = titles[:8]
        lines = ["[MÍDIA REAL EM ALTA — se for citar filme/série/anime hoje, use um destes]"]
        lines.extend(f"- {t}" for t in shown)
        return "\n".join(lines)

    def _fetch_titles(self) -> list[str]:
        """DuckDuckGo → extrai títulos candidatos → dedupe → devolve top-8."""
        from web_search_adapter import search_text

        raw_titles: list[str] = []
        for query in _QUERIES:
            try:
                results = search_text(query, max_results=3, timeout=5)
            except Exception as exc:
                logger.warning("media_lookup.query_fail query=%r exc=%s", query, exc)
                continue
            for r in results:
                body = f"{r.get('title', '')}. {r.get('body', '')}"
                for match in _TITLE_RE.finditer(body):
                    candidate = (match.group(1) or match.group(2) or "").strip(" .,-:;'\"")
                    if _looks_like_title(candidate):
                        raw_titles.append(candidate)

        # Dedupe preservando ordem.
        seen: set[str] = set()
        unique: list[str] = []
        for t in raw_titles:
            key = t.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(t)
            if len(unique) >= 8:
                break
        return unique


# Filtros de sanidade para descartar candidatos ruins que o regex pega.
_TITLE_BLOCKLIST = {
    "netflix", "amazon", "hbo", "max", "disney", "prime", "star", "brasil",
    "cinema", "filme", "série", "serie", "animes", "temporada", "streaming",
    "melhores", "principais", "top", "novos", "melhores filmes",
}


def _looks_like_title(candidate: str) -> bool:
    if not candidate or len(candidate) < 3 or len(candidate) > 60:
        return False
    lowered = candidate.casefold()
    if lowered in _TITLE_BLOCKLIST:
        return False
    if lowered.startswith(_HEADLINE_PREFIXES):
        return False
    # Fragmento terminado em letra solta ("... das s") é corte de palavra.
    # Só letra: "Round 6", "Duna 2" são títulos legítimos.
    if re.search(r"\s[^\W\d_]$", candidate):
        return False
    # Precisa ter pelo menos uma letra minúscula depois da primeira (evita
    # ACRÔNIMOS/CAIXA-ALTA que geralmente são categorias, não títulos).
    if candidate.isupper() and len(candidate) > 5:
        return False
    return True


__all__ = ["MediaLookupService"]
