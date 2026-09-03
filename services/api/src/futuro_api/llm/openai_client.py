"""El cliente real. Es el único fichero del repositorio que importa el SDK.

Structured outputs en modo estricto: el esquema viaja como `text_format` y
el SDK devuelve el objeto ya parseado, así que no hay JSON que interpretar a
mano ni respuestas a medio formatear que salvar. Lo que el SDK no
garantiza es que lo parseado sea *verdad*: de eso se ocupa `offers/rules.py`.
"""

from __future__ import annotations

import logging
import time

from openai import AsyncOpenAI, OpenAIError
from openai.types.responses import ParsedResponse
from pydantic import BaseModel

from futuro_api.jobs.vocabularies import LlmCallStatus
from futuro_api.llm import LlmError, LlmRefusal, LlmResult, Usage
from futuro_api.llm import cost as pricing

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Implementación de `LlmClient` contra la API de OpenAI."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        # Se comprueba aquí y no al usarlo: un modelo sin tarifa conocida
        # impide arrancar, en vez de dejar que el primer trabajo registre un
        # coste que nadie sabe calcular.
        if not pricing.is_priced(model):
            raise pricing.UnknownModel(model)
        self._model = model
        # `max_retries` del SDK cubre los fallos de red y los 429; los
        # reintentos de trabajo entero los gestiona la cola, que es la que
        # sabe cuántas veces se ha intentado ya.
        self._client = AsyncOpenAI(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        system: str,
        user: str,
        schema: type[T],
    ) -> LlmResult[T]:
        started = time.perf_counter()
        try:
            response = await self._client.responses.parse(
                model=self._model,
                instructions=system,
                input=user,
                text_format=schema,
            )
        except OpenAIError as error:
            raise LlmError(f"la llamada a OpenAI falló: {error}") from error
        latency_ms = int((time.perf_counter() - started) * 1000)

        self._raise_if_unusable(response, purpose)
        parsed = response.output_parsed
        assert parsed is not None  # lo garantiza _raise_if_unusable

        usage = self._read_usage(response)
        return LlmResult(
            parsed=parsed,
            provider=pricing.PROVIDER,
            model=response.model or self._model,
            usage=usage,
            cost_usd=pricing.cost_usd(self._model, usage),
            pricing_version=pricing.PRICING_VERSION,
            latency_ms=latency_ms,
            request_id=response.id,
            status=LlmCallStatus.SUCCEEDED,
        )

    def _raise_if_unusable[M: BaseModel](
        self, response: ParsedResponse[M], purpose: str
    ) -> None:
        refusal = self._find_refusal(response)
        if refusal is not None:
            raise LlmRefusal(f"el modelo se negó a responder a {purpose}: {refusal}")
        if response.status == "incomplete":
            reason = (
                response.incomplete_details.reason
                if response.incomplete_details
                else "sin motivo"
            )
            # Truncada a medias no es una respuesta parcial aprovechable: le
            # faltarían campos, y un campo que falta es un campo sin
            # evidencia declarada.
            raise LlmError(f"la respuesta quedó incompleta ({reason})")
        if response.output_parsed is None:
            raise LlmError(
                f"la respuesta no se pudo parsear contra el esquema "
                f"(estado {response.status})"
            )

    @staticmethod
    def _find_refusal[M: BaseModel](response: ParsedResponse[M]) -> str | None:
        for item in response.output:
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) == "refusal":
                    return str(getattr(content, "refusal", "sin detalle"))
        return None

    @staticmethod
    def _read_usage[M: BaseModel](response: ParsedResponse[M]) -> Usage:
        usage = response.usage
        if usage is None:
            # No debería pasar. Si pasa, se conserva la extracción y se
            # registra el coste a cero: la llamada ya está pagada, y tirar
            # una respuesta buena por no poder contabilizarla sería gastar el
            # dinero dos veces. Queda el `request_id` para cuadrarlo contra
            # el panel del proveedor.
            logger.warning(
                "OpenAI no devolvió consumo para %s; el coste queda a cero",
                response.id,
            )
            return Usage(input_tokens=0, cached_input_tokens=0, output_tokens=0)
        details = usage.input_tokens_details
        output_details = usage.output_tokens_details
        return Usage(
            input_tokens=usage.input_tokens,
            cached_input_tokens=details.cached_tokens if details else 0,
            output_tokens=usage.output_tokens,
            reasoning_tokens=(
                output_details.reasoning_tokens if output_details else None
            ),
        )
