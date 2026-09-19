"""
Engine de Aprendizado e Espelhamento de Estilo Linguístico (v2.0).
Observa a forma como o Patrick escreve, ri, pontua e usa emojis,
acumulando contadores estatísticos e médias móveis no SQLite para que a Marina
espelhe de maneira ponderada e orgânica o vocabulário, as risadas e a cadência do seu namorado.

DEFAULT_PTBR_STYLE may exist as configuration. LEARNED_PATRICK_STYLE only after
real samples — never seed fake observations into an empty DB.
"""
import re
import json
import logging
from typing import Optional, Dict, Any, List
from collections import Counter

from db import db_manager, DatabaseManager
from config import settings

logger = logging.getLogger("StyleEngine")

# Padrões comuns de risada no Brasil
REGEX_RISADA_K = re.compile(r'\b(k{2,})\b', re.IGNORECASE)
REGEX_RISADA_HAHA = re.compile(r'\b(ha(ha)+h?)\b', re.IGNORECASE)
REGEX_RISADA_RSRS = re.compile(r'\b(rs(rs)+)\b', re.IGNORECASE)

# Lista base de gírias e expressões comuns para rastreamento
GIRIAS_CATALOGADAS = [
    "fechou", "trampo", "trampar", "codar", "código", "suave", "bizarro", "mano", "véi",
    "top", "firmeza", "blz", "valeu", "show", "né", "bora", "aff", "eita",
    "massa", "tranquilo", "vácuo", "sono", "preguiça"
]

# Config defaults (not claimed as Patrick observations)
DEFAULT_PTBR_STYLE = {
    "risada": "kkkk",
    "emojis": "🥰, 💕, ❤️, 🥺, 🙈",
    "girias": "trampo, codar, bora, suave, fechou",
    "cadencia": "mensagens curtas e ágeis, descontraídas, pontuação leve sem formalidade",
}

# Regex para captura de emojis Unicode
REGEX_EMOJIS = re.compile(
    r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U000024C2-\U0001F251]\uFE0F?'
)

MIN_SAMPLES_THRESHOLD = 2


class StyleEngine:
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or db_manager
        # Intentionally do NOT seed fake learned observations into empty DB.

    def patrick_sample_count(self) -> int:
        """Total Patrick-message samples reflected in cadence (0 if never learned)."""
        estilo = self.db.get_estilo()
        cad = estilo.get("cadencia", {}).get("exemplos", {})
        if isinstance(cad, dict):
            return int(cad.get("total_messages", 0) or 0)
        return 0

    def has_learned_style(self) -> bool:
        return self.patrick_sample_count() >= MIN_SAMPLES_THRESHOLD

    def get_custom_slang_catalog(self) -> List[str]:
        """Retorna o catálogo completo de gírias (base + customizadas salvas no banco)."""
        estilo = self.db.get_estilo()
        custom = estilo.get("catalogo_girias_custom", {}).get("exemplos", [])
        combined = set(GIRIAS_CATALOGADAS)
        if isinstance(custom, list):
            combined.update(custom)
        return sorted(list(combined))

    def adicionar_giria_ao_catalogo(self, giria: str):
        """Adiciona uma nova gíria ao catálogo permanente."""
        g_limpa = giria.strip().lower()
        if not g_limpa:
            return
        estilo = self.db.get_estilo()
        custom = estilo.get("catalogo_girias_custom", {}).get("exemplos", [])
        if not isinstance(custom, list):
            custom = []
        if g_limpa not in custom:
            custom.append(g_limpa)
            self.db.salvar_estilo("catalogo_girias_custom", ", ".join(custom), custom)

    def processar_mensagem_patrick(self, texto: str):
        """Analisa a mensagem do Patrick acumulando estatísticas para espelhamento ponderado.

        EVIDENCE-ONLY: never persist DEFAULT_PTBR_STYLE values as if they were
        observed from Patrick. Each dimension stores only what was actually seen.
        """
        if not texto or len(texto.strip()) < 2:
            return

        texto_limpo = texto.strip()
        estilo = self.db.get_estilo()

        # 1. Laughter tracking — evidence-only, no default seed
        risada_data = estilo.get("risada", {}).get("exemplos", {})
        if not isinstance(risada_data, dict):
            risada_data = {}

        if REGEX_RISADA_K.search(texto_limpo):
            risada_data["kkkk"] = risada_data.get("kkkk", 0) + 1
        elif REGEX_RISADA_HAHA.search(texto_limpo):
            risada_data["haha"] = risada_data.get("haha", 0) + 1
        elif REGEX_RISADA_RSRS.search(texto_limpo):
            risada_data["rsrs"] = risada_data.get("rsrs", 0) + 1

        total_risadas = sum(risada_data.values())
        if total_risadas >= MIN_SAMPLES_THRESHOLD:
            risada_dominante = max(risada_data.items(), key=lambda x: x[1])[0]
        else:
            # No observed dominance yet — store empty, NOT a default
            risada_dominante = ""
        self.db.salvar_estilo("risada", risada_dominante, risada_data)

        # 2. Emoji tracking — evidence-only
        emojis_data = estilo.get("emojis_favoritos", {}).get("exemplos", {})
        if not isinstance(emojis_data, dict):
            emojis_data = {}

        emojis_encontrados = REGEX_EMOJIS.findall(texto_limpo)
        for em in emojis_encontrados:
            em_key = "❤️" if "\u2764" in em else em
            emojis_data[em_key] = emojis_data.get(em_key, 0) + 1

        top_emojis = sorted(emojis_data.items(), key=lambda x: x[1], reverse=True)[:8]
        # Only store actually observed emojis, never default list
        top_emojis_str = ", ".join([e[0] for e in top_emojis]) if top_emojis else ""
        self.db.salvar_estilo("emojis_favoritos", top_emojis_str, emojis_data)

        # 3. Slang tracking — evidence-only
        girias_data = estilo.get("girias", {}).get("exemplos", {})
        if not isinstance(girias_data, dict):
            girias_data = {}

        catalogo = self.get_custom_slang_catalog()
        palavras_texto = set(re.findall(r'\b\w+\b', texto_limpo.lower()))
        girias_detectadas = [g for g in catalogo if g in palavras_texto]
        for g in girias_detectadas:
            girias_data[g] = girias_data.get(g, 0) + 1

        top_girias = sorted(girias_data.items(), key=lambda x: x[1], reverse=True)[:8]
        # Only store actually observed slang, never default list
        top_girias_str = ", ".join([g[0] for g in top_girias]) if top_girias else ""
        self.db.salvar_estilo("girias", top_girias_str, girias_data)

        # 4. Cadence statistics — always tracked (cadence is inherently observational)
        cadencia_data = estilo.get("cadencia", {}).get("exemplos", {})
        if not isinstance(cadencia_data, dict):
            cadencia_data = {
                "total_messages": 0,
                "total_words": 0,
                "total_chars": 0,
                "ellipses_count": 0,
                "exclamation_count": 0,
                "lowercase_count": 0
            }

        palavras = texto_limpo.split()
        num_palavras = len(palavras)
        num_chars = len(texto_limpo)

        total_msgs = cadencia_data.get("total_messages", 0) + 1
        total_words = cadencia_data.get("total_words", 0) + num_palavras
        total_chars = cadencia_data.get("total_chars", 0) + num_chars

        tem_reticencias = 1 if ("..." in texto_limpo or "…" in texto_limpo) else 0
        ellipses_count = cadencia_data.get("ellipses_count", 0) + tem_reticencias

        tem_exclamacao = 1 if "!" in texto_limpo else 0
        exclamation_count = cadencia_data.get("exclamation_count", 0) + tem_exclamacao

        e_minuscula = 1 if texto_limpo and texto_limpo[0].islower() else 0
        lowercase_count = cadencia_data.get("lowercase_count", 0) + e_minuscula

        avg_words = round(total_words / max(total_msgs, 1), 1)
        ellipses_ratio = round(ellipses_count / max(total_msgs, 1), 2)
        exclamation_ratio = round(exclamation_count / max(total_msgs, 1), 2)

        cadencia_data.update({
            "total_messages": total_msgs,
            "total_words": total_words,
            "total_chars": total_chars,
            "avg_words": avg_words,
            "ellipses_count": ellipses_count,
            "exclamation_count": exclamation_count,
            "lowercase_count": lowercase_count,
            "ellipses_ratio": ellipses_ratio,
            "exclamation_ratio": exclamation_ratio
        })

        if avg_words <= 6.0:
            ritmo_desc = "mensagens curtas e ágeis (média de poucas palavras por balão)"
        elif avg_words <= 14.0:
            ritmo_desc = "mensagens naturais de 1 a 2 frases por vez"
        else:
            ritmo_desc = "mensagens mais completas e detalhadas"

        if ellipses_ratio >= 0.20:
            ritmo_desc += ", uso frequente de reticências (...) para criar clima íntimo e informal"
        if exclamation_ratio >= 0.25:
            ritmo_desc += ", tom enérgico com pontuação expressiva (!)"

        self.db.salvar_estilo("cadencia", ritmo_desc, cadencia_data)

    def _has_observed_data(self, dimension_key: str) -> bool:
        """Check whether a style dimension has any real observed data (count > 0)."""
        estilo = self.db.get_estilo()
        exemplos = estilo.get(dimension_key, {}).get("exemplos", {})
        if not isinstance(exemplos, dict):
            return False
        return sum(exemplos.values()) > 0

    def get_learned_style_summary(self) -> str:
        """Evidence-aware style summary for WorldContext consumption.

        Returns empty string if threshold not met or no real observations exist.
        Only includes dimensions with actual observed evidence — never defaults.
        """
        if not self.has_learned_style():
            return ""

        estilo = self.db.get_estilo()
        parts = []

        # Laughter — only if actually observed
        if self._has_observed_data("risada"):
            valor = estilo.get("risada", {}).get("valor", "")
            if valor:
                parts.append(f"Laugh pattern: {valor}")

        # Emojis — only if actually observed
        if self._has_observed_data("emojis_favoritos"):
            valor = estilo.get("emojis_favoritos", {}).get("valor", "")
            if valor:
                parts.append(f"Frequent emojis: {valor}")

        # Slang — only if actually observed
        if self._has_observed_data("girias"):
            valor = estilo.get("girias", {}).get("valor", "")
            if valor:
                parts.append(f"Shared slang: {valor}")

        # Cadence — always observational by nature
        cadencia = estilo.get("cadencia", {}).get("valor", "")
        if cadencia:
            parts.append(f"Writing rhythm: {cadencia}")

        if not parts:
            return ""
        return "; ".join(parts)

    def get_style_prompt_injection(self) -> str:
        """Learned Patrick style block only after real samples; else empty string.

        Each dimension only appears if it has real observed evidence (count > 0).
        """
        if not self.has_learned_style():
            return ""

        estilo = self.db.get_estilo()
        lines = ["[SINCRONIA LINGUÍSTICA DO CASAL (COMO O PATRICK ESCREVE)]"]

        # Laughter — only if actually observed
        if self._has_observed_data("risada"):
            risada = estilo.get("risada", {}).get("valor", "")
            if risada:
                lines.append(f"- Risada compartilhada do casal: {risada} (ria como ele, nunca use risadas artificiais).")

        # Emojis — only if actually observed
        if self._has_observed_data("emojis_favoritos"):
            emojis = estilo.get("emojis_favoritos", {}).get("valor", "")
            if emojis:
                lines.append(f"- Emojis mais trocados entre vocês: {emojis}")

        # Slang — only if actually observed
        if self._has_observed_data("girias"):
            girias = estilo.get("girias", {}).get("valor", "")
            if girias:
                lines.append(f"- Gírias e expressões que você pegou dele: {girias}")

        # Cadence — always observational
        cadencia = estilo.get("cadencia", {}).get("valor", "")
        if cadencia:
            lines.append(f"- Ritmo de escrita: {cadencia}")

        lines.append("(Espelhe essa mesma descontração e intimidade para a conversa soar 100% autêntica e conectada!).")

        if len(lines) <= 2:
            # Only header + footer, no real data
            return ""

        return "\n" + "\n".join(lines) + "\n"


style_engine = StyleEngine()
