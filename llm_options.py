"""Parâmetros comuns a toda chamada de LLM (Auditoria #9).

A arena de modelos mostrou duas coisas:
  * modelos híbridos (DeepSeek V4, GLM, Kimi…) podem raciocinar por padrão em
    alguns provedores — latência e custo sobem e o orçamento curto de fala
    (160 tokens) vira raciocínio, sobrando resposta vazia;
  * outros (Gemini 3.x Flash, GPT-5.x) NÃO deixam desligar o raciocínio e
    recusam `reasoning.enabled=false` com HTTP 400.

`LLM_REASONING` no .env decide, para todas as chamadas de uma vez:
  off (padrão)          → raciocínio desligado;
  minimal|low|medium    → raciocínio com esse esforço, fora da resposta, com
                          orçamento extra para não comer a fala.
O modelo íntimo (Fase C.1) tem o seu: `LLM_INTIMATE_REASONING`.
"""
from typing import Any, Dict, Optional

REASONING_EXTRA_TOKENS = 1500


def reasoning_for(model: Optional[str]) -> str:
    from config import settings  # lido na hora: testes recarregam `config`
    intimate = (getattr(settings, "LLM_INTIMATE_MODEL", "") or "").strip()
    if model and intimate and model == intimate:
        effort = getattr(settings, "LLM_INTIMATE_REASONING", "off")
    elif model and model != getattr(settings, "LLM_MODEL", model):
        effort = "off"  # reserva/outros: o que a arena validou
    else:
        effort = getattr(settings, "LLM_REASONING", "off")
    return (effort or "off").strip().lower()


def llm_kwargs(max_tokens: Optional[int], model: Optional[str] = None) -> Dict[str, Any]:
    effort = reasoning_for(model)
    if effort == "off":
        return {"max_tokens": max_tokens, "extra_body": {"reasoning": {"enabled": False}}}
    return {"max_tokens": (max_tokens or 400) + REASONING_EXTRA_TOKENS,
            "extra_body": {"reasoning": {"effort": effort, "exclude": True}}}
