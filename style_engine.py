"""
Engine de Aprendizado e Espelhamento de Estilo Linguístico (v1.3.0).
Observa a forma como o Patrick escreve, ri, pontua e usa emojis,
gravando os padrões no SQLite para que a Marina espelhe naturalmente
o vocabulário e a cadência do seu namorado.
"""
import re
import json
import logging
from pathlib import Path
from db import db_manager

logger = logging.getLogger("StyleEngine")

# Padrões comuns de risada no Brasil
REGEX_RISADA_K = re.compile(r'\b(k{2,})\b', re.IGNORECASE)
REGEX_RISADA_HAHA = re.compile(r'\b(ha(ha)+h?)\b', re.IGNORECASE)
REGEX_RISADA_RSRS = re.compile(r'\b(rs(rs)+)\b', re.IGNORECASE)

# Lista de gírias e expressões comuns para rastreamento
GIRIAS_CATALOGADAS = [
    "trampo", "trampar", "codar", "código", "suave", "bizarro", "mano", "véi",
    "top", "firmeza", "blz", "valeu", "show", "né", "bora", "aff", "eita",
    "massa", "tranquilo", "vácuo", "sono", "preguiça"
]

# Regex para captura de emojis Unicode
REGEX_EMOJIS = re.compile(
    r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U000024C2-\U0001F251]'
)

class StyleEngine:
    def __init__(self):
        self.db = db_manager
        self._ensure_default_style()

    def _ensure_default_style(self):
        estilo = self.db.get_estilo()
        if not estilo.get("risada"):
            self.db.salvar_estilo("risada", "kkkk", ["kkkk", "kkk"])
        if not estilo.get("emojis_favoritos"):
            self.db.salvar_estilo("emojis_favoritos", "🥰, 💕, ❤️, 🥺, 🙈", ["🥰", "💕", "❤️"])
        if not estilo.get("girias"):
            self.db.salvar_estilo("girias", "trampo, codar, bora, suave", ["trampo", "codar", "bora"])
        if not estilo.get("cadencia"):
            self.db.salvar_estilo("cadencia", "mensagens curtas, descontraídas, pontuação leve sem formalidade", [])

    def processar_mensagem_patrick(self, texto: str):
        """Analisa a mensagem do Patrick e atualiza métricas de estilo em segundo plano."""
        if not texto or len(texto.strip()) < 2:
            return

        texto_limpo = texto.strip()

        # 1. Rastreio de Risada
        if REGEX_RISADA_K.search(texto_limpo):
            self.db.salvar_estilo("risada", "kkkk", ["kkkk", "kkkkk"])
        elif REGEX_RISADA_HAHA.search(texto_limpo):
            self.db.salvar_estilo("risada", "haha", ["haha", "hahaha"])
        elif REGEX_RISADA_RSRS.search(texto_limpo):
            self.db.salvar_estilo("risada", "rsrs", ["rsrs"])

        # 2. Rastreio de Emojis
        emojis_encontrados = REGEX_EMOJIS.findall(texto_limpo)
        if emojis_encontrados:
            estilo = self.db.get_estilo()
            existentes = estilo.get("emojis_favoritos", {}).get("exemplos", [])
            atualizados = list(dict.fromkeys(emojis_encontrados + existentes))[:8]
            self.db.salvar_estilo("emojis_favoritos", ", ".join(atualizados), atualizados)

        # 3. Rastreio de Gírias e Vocabulário
        palavras_texto = set(re.findall(r'\b\w+\b', texto_limpo.lower()))
        girias_detectadas = [g for g in GIRIAS_CATALOGADAS if g in palavras_texto]
        if girias_detectadas:
            estilo = self.db.get_estilo()
            existentes_g = estilo.get("girias", {}).get("exemplos", [])
            atualizadas_g = list(dict.fromkeys(girias_detectadas + existentes_g))[:10]
            self.db.salvar_estilo("girias", ", ".join(atualizadas_g), atualizadas_g)

        # 4. Rastreio de Cadência (ex: se usa reticências '...')
        if "..." in texto_limpo or "…" in texto_limpo:
            self.db.salvar_estilo("cadencia", "frases ágeis, uso expressivo de reticências (...) para criar clima descontraído", ["..."])

    def get_style_prompt_injection(self) -> str:
        """Retorna as instruções de espelhamento para o prompt da Marina."""
        estilo = self.db.get_estilo()
        risada = estilo.get("risada", {}).get("valor", "kkkk")
        emojis = estilo.get("emojis_favoritos", {}).get("valor", "💕, 🥰, 🙈")
        girias = estilo.get("girias", {}).get("valor", "trampo, codar, bora, suave")
        cadencia = estilo.get("cadencia", {}).get("valor", "mensagens curtas e ágeis em múltiplos balões")

        return f"""
[SINCRONIA LINGUÍSTICA DO CASAL (COMO O PATRICK ESCREVE)]
- Risada compartilhada do casal: {risada} (ria como ele, nunca use risadas artificiais).
- Emojis mais trocados entre vocês: {emojis}
- Gírias e expressões que você pegou dele: {girias}
- Ritmo de escrita: {cadencia}
(Espelhe essa mesma descontração e intimidade para a conversa soar 100% autêntica e conectada!).
"""

style_engine = StyleEngine()
