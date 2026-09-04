"""Construye el cliente de LLM que toca según la configuración.

Está en su propio fichero para que importar `futuro_api.llm` no arrastre el
SDK de OpenAI: solo quien construye un cliente de verdad lo necesita.

Las respuestas simuladas se inyectan aquí y no viven en `llm/`, que no sabe
qué es una oferta. La dirección de las dependencias se mantiene:
`offers` → `llm`, nunca al revés.
"""

from __future__ import annotations

from futuro_api.assessment import calls
from futuro_api.config import Settings
from futuro_api.llm import LlmClient
from futuro_api.llm.openai_client import OpenAIClient
from futuro_api.llm.stub import StubClient
from futuro_api.offers import extraction


def build_client(settings: Settings) -> LlmClient:
    if settings.llm_stubbed:
        return StubClient(
            {
                extraction.PURPOSE: extraction.canned_draft,
                calls.SCORING_PURPOSE: calls.canned_scoring,
                calls.VARIANT_PURPOSE: calls.canned_variant,
            }
        )
    return OpenAIClient(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )
