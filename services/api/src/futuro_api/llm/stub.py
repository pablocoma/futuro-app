"""Cliente inerte, para desarrollo y para el CI.

Existe por tres razones concretas, y ninguna es comodidad. El CI no tiene
clave y no debería tenerla. El e2e necesita ser determinista, y una llamada
a un modelo no lo es. Y desarrollar la pantalla de la oferta a base de
llamadas de verdad cuesta dinero por cada recarga.

No es un mock de test: vive en el código de la aplicación porque
`LLM_PROVIDER=stub` es una configuración legítima en local. Lo que no es
legítimo es en producción, y `Settings` lo rechaza igual que rechaza el
bypass de autenticación.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal

from pydantic import BaseModel

from futuro_api.jobs.vocabularies import LlmCallStatus
from futuro_api.llm import LlmError, LlmResult, Usage

# El modelo se guarda con este nombre en `offer_extractions.model`, así que
# una extracción simulada se distingue de una real mirando la fila, no
# adivinando por el contenido.
STUB_MODEL = "stub"
STUB_PRICING_VERSION = "stub"


class StubClient:
    """Devuelve respuestas preparadas y no gasta nada.

    Las respuestas se inyectan por propósito. No hay ninguna por defecto: si
    alguien pide un propósito que nadie ha preparado, falla en vez de
    devolver algo plausible, que es la forma en que un stub se cuela en un
    camino donde no tocaba.
    """

    def __init__(self, responses: Mapping[str, Callable[[str], BaseModel]]) -> None:
        self._responses = dict(responses)

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        system: str,
        user: str,
        schema: type[T],
    ) -> LlmResult[T]:
        build = self._responses.get(purpose)
        if build is None:
            raise LlmError(
                f"el cliente simulado no tiene respuesta preparada para "
                f"«{purpose}»; conocidos: {', '.join(sorted(self._responses))}"
            )
        parsed = build(user)
        if not isinstance(parsed, schema):
            raise LlmError(
                f"la respuesta preparada para «{purpose}» es "
                f"{type(parsed).__name__} y se esperaba {schema.__name__}"
            )
        return LlmResult(
            parsed=parsed,
            provider=STUB_MODEL,
            model=STUB_MODEL,
            usage=Usage(input_tokens=0, cached_input_tokens=0, output_tokens=0),
            cost_usd=Decimal(0),
            pricing_version=STUB_PRICING_VERSION,
            latency_ms=0,
            request_id=None,
            status=LlmCallStatus.SUCCEEDED,
        )
