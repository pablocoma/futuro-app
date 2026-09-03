"""El módulo de LLM, aislado.

Aislado quiere decir dos cosas concretas. Que nada de aquí sabe qué es una
oferta: quien llama trae su prompt y su esquema, y `offers/` es el único que
sabe cómo son los suyos. Y que el resto de la aplicación no importa el SDK
de OpenAI en ningún sitio, así que cambiar de proveedor es escribir otro
cliente que cumpla `LlmClient` y no tocar nada más.

Toda llamada devuelve, además de la respuesta, lo que costó: tokens, precio
y latencia. No es opcional ni se calcula aparte, porque un coste que hay que
acordarse de registrar es un coste que no se registra.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel

from futuro_api.jobs.vocabularies import LlmCallStatus

__all__ = [
    "LlmClient",
    "LlmError",
    "LlmRefusal",
    "LlmResult",
    "LlmCallStatus",
    "Usage",
]


@dataclass(frozen=True)
class Usage:
    """Tokens de una llamada.

    `cached_input_tokens` es un **subconjunto** de `input_tokens`, no un
    añadido: así lo devuelve el proveedor. Sumarlos por separado facturaría
    dos veces la parte cacheada, y es el error fácil de cometer aquí.

    `reasoning_tokens` se registra pero no se factura aparte: van dentro de
    los tokens de salida y ya están contados en `output_tokens`.
    """

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None = None


@dataclass(frozen=True)
class LlmResult[T: BaseModel]:
    """La respuesta ya parseada, con su procedencia y su coste."""

    parsed: T
    provider: str
    model: str
    usage: Usage
    cost_usd: Decimal
    pricing_version: str
    latency_ms: int
    request_id: str | None = None
    status: LlmCallStatus = LlmCallStatus.SUCCEEDED


class LlmError(Exception):
    """Algo salió mal en la llamada y no hay respuesta que parsear."""


class LlmRefusal(LlmError):
    """El modelo se negó a responder.

    Es un estado propio y no un fallo cualquiera: reintentarlo da lo mismo,
    así que quien encola el trabajo no debe tratarlo como un error
    transitorio.
    """


class LlmClient(Protocol):
    """Lo único que el resto de la aplicación sabe de un proveedor."""

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        system: str,
        user: str,
        schema: type[T],
    ) -> LlmResult[T]:
        """Pide una respuesta que cumpla `schema`.

        `purpose` no viaja al proveedor: identifica para qué era la llamada
        —`offer_extraction` hoy, el scoring de M2 mañana— y es lo que
        permite mirar el coste por tarea en vez de un total ciego.
        """
        ...
