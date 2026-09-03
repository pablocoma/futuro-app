"""Tarifas y cálculo del coste de una llamada.

La tabla se copia a mano de la página de precios del proveedor, con su
fecha, y **un modelo que no esté aquí no se puede usar**: preferimos que el
trabajo se niegue a arrancar antes que registrar un coste inventado. Es la
misma disciplina que en el resto del proyecto —no rellenar un hueco con una
estimación— aplicada al dinero.

`PRICING_VERSION` se guarda en cada fila de `llm_calls` junto a los tokens,
así que si una tarifa estaba mal, el coste se recalcula sin haber perdido el
dato. Es la propiedad que hace recalculable la capa `assessment`, aplicada
aquí.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from futuro_api.llm import Usage

# Precios consultados en la página oficial de OpenAI el 2026-09-03. Subir
# esta fecha exige revisar la tabla entera, no solo añadir una fila.
PRICING_VERSION = "openai/2026-09-03"

PROVIDER = "openai"

_MILLION = Decimal(1_000_000)

# El coste se guarda en NUMERIC(10,6): seis decimales de dólar, que a estos
# precios distingue llamadas de menos de un céntimo.
_CENTS = Decimal("0.000001")


@dataclass(frozen=True)
class Price:
    """Dólares por millón de tokens."""

    input_usd: Decimal
    cached_input_usd: Decimal
    output_usd: Decimal


# Solo los tres modelos que tienen sentido para esta tarea. `terra` es el
# que se usa: un anuncio son unos 5.000 tokens de entrada y 2.000 de salida,
# así que sale por unos tres céntimos, que es el ~1 €/mes que ARCHITECTURE
# §13 presupuesta. `luna` está por si el volumen creciera y `sol` por si la
# fidelidad de las citas resultara insuficiente, que es lo que se paga al
# bajar de gama en esta tarea concreta.
PRICING: dict[str, Price] = {
    "gpt-5.6-sol": Price(Decimal("4.00"), Decimal("0.40"), Decimal("20.00")),
    "gpt-5.6-terra": Price(Decimal("2.00"), Decimal("0.20"), Decimal("12.00")),
    "gpt-5.6-luna": Price(Decimal("0.20"), Decimal("0.02"), Decimal("1.20")),
}


class UnknownModel(LookupError):
    """El modelo configurado no tiene tarifa conocida."""

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(
            f"«{model}» no está en la tabla de tarifas de {PRICING_VERSION}; "
            f"conocidos: {', '.join(sorted(PRICING))}. Añádelo con su precio "
            "y su fecha antes de usarlo."
        )


def is_priced(model: str) -> bool:
    return model in PRICING


def cost_usd(model: str, usage: Usage) -> Decimal:
    """Coste en dólares de una llamada, redondeado a seis decimales.

    Los tokens cacheados se descuentan de los de entrada antes de aplicar
    su propia tarifa: el proveedor los cuenta dentro de `input_tokens`, y
    tratarlos como un añadido facturaría dos veces esa parte.
    """
    price = PRICING.get(model)
    if price is None:
        raise UnknownModel(model)

    cached = max(usage.cached_input_tokens, 0)
    uncached = max(usage.input_tokens - cached, 0)
    total = (
        uncached * price.input_usd
        + cached * price.cached_input_usd
        + max(usage.output_tokens, 0) * price.output_usd
    ) / _MILLION
    return total.quantize(_CENTS)
