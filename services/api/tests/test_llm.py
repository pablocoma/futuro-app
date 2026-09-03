"""El módulo de LLM: coste, cliente simulado y configuración.

Ninguno de estos tests llama a OpenAI. El cliente real no se prueba aquí a
propósito: lo único que hace es traducir entre el SDK y `LlmResult`, y
probarlo exigiría o una clave en el CI o un doble del SDK que se parecería
más al SDK que a la realidad. Lo que sí se prueba es todo lo que decide algo:
la aritmética del coste, la puerta que impide usar un modelo sin tarifa, y
que el stub recorra el camino real de validación.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel

from futuro_api.config import Settings
from futuro_api.llm import LlmError, Usage
from futuro_api.llm import cost as pricing
from futuro_api.llm.stub import StubClient
from futuro_api.offers import extraction, prompt, rules, schemas
from tests.synthetic import ADVERT

# ---------------------------------------------------------------------------
# Coste
# ---------------------------------------------------------------------------


def test_the_cost_of_a_typical_offer() -> None:
    """Un anuncio son unos 5.000 tokens de entrada y 2.000 de salida."""
    usage = Usage(input_tokens=5_000, cached_input_tokens=0, output_tokens=2_000)
    assert pricing.cost_usd("gpt-5.6-terra", usage) == Decimal("0.034000")
    assert pricing.cost_usd("gpt-5.6-sol", usage) == Decimal("0.060000")
    assert pricing.cost_usd("gpt-5.6-luna", usage) == Decimal("0.003400")


def test_cached_tokens_are_a_subset_of_the_input_and_not_an_extra() -> None:
    """El error fácil de este módulo, fijado por un test.

    El proveedor cuenta los tokens cacheados **dentro** de `input_tokens`.
    Tratarlos como un añadido facturaría dos veces la parte cacheada: aquí
    serían 0,011 en vez de 0,001, un factor de once.
    """
    everything_cached = Usage(
        input_tokens=5_000, cached_input_tokens=5_000, output_tokens=0
    )
    assert pricing.cost_usd("gpt-5.6-terra", everything_cached) == Decimal("0.001000")


def test_an_unpriced_model_is_refused_with_something_useful_to_read() -> None:
    with pytest.raises(pricing.UnknownModel) as raised:
        pricing.cost_usd("gpt-5.6-inventado", Usage(1, 0, 1))
    message = str(raised.value)
    assert "no está en la tabla de tarifas" in message
    # Dice cuáles hay y qué hacer, no solo que no lo conoce.
    assert "gpt-5.6-terra" in message
    assert "su precio" in message


def test_a_call_that_reports_nothing_costs_nothing() -> None:
    assert pricing.cost_usd("gpt-5.6-terra", Usage(0, 0, 0)) == Decimal(0)


def test_nonsense_token_counts_never_produce_a_negative_cost() -> None:
    """Un coste negativo se sumaría al total como un descuento inexistente."""
    absurd = Usage(input_tokens=10, cached_input_tokens=99, output_tokens=-5)
    assert pricing.cost_usd("gpt-5.6-terra", absurd) >= 0


# ---------------------------------------------------------------------------
# Cliente simulado
# ---------------------------------------------------------------------------


class _Other(BaseModel):
    algo: str


async def test_the_stub_answers_and_charges_nothing() -> None:
    client = StubClient({extraction.PURPOSE: extraction.canned_draft})
    result = await extraction.extract(client, ADVERT)

    assert isinstance(result.parsed, schemas.ExtractionDraft)
    assert result.cost_usd == Decimal(0)
    # El nombre del modelo es lo que distingue una extracción simulada de
    # una real al mirar la fila guardada.
    assert result.model == "stub"
    assert result.pricing_version == "stub"


async def test_the_stub_refuses_a_purpose_nobody_prepared() -> None:
    """Devolver algo plausible es cómo un stub se cuela donde no tocaba."""
    client = StubClient({})
    with pytest.raises(LlmError, match="no tiene respuesta preparada"):
        await extraction.extract(client, ADVERT)


async def test_the_stub_refuses_a_response_of_the_wrong_shape() -> None:
    client = StubClient({extraction.PURPOSE: lambda _: _Other(algo="x")})
    with pytest.raises(LlmError, match="se esperaba ExtractionDraft"):
        await extraction.extract(client, ADVERT)


# ---------------------------------------------------------------------------
# La respuesta simulada recorre el camino real
# ---------------------------------------------------------------------------


def test_the_canned_draft_survives_the_real_validation() -> None:
    """Es lo que hace útil al stub y no solo cómodo.

    Sus citas se sacan del propio anuncio, así que la verificación de citas
    de `rules.py` se ejecuta de verdad y pasa. Con citas escritas a mano,
    cualquier anuncio distinto del de los tests dejaría todo en `absent` y
    el camino real no se recorrería nunca en local.
    """
    draft = extraction.canned_draft(prompt.build_user_prompt(ADVERT))
    result = rules.validate(draft, ADVERT)

    assert result.corrections == []
    assert result.columns["title"] == "Reclutamiento Bahía — oferta para cliente"
    assert len(result.requirements) == 5


def test_the_canned_draft_works_with_any_advert() -> None:
    other = "Cooperativa del Valle\n\n- Se necesita tractorista con carné.\n"
    draft = extraction.canned_draft(prompt.build_user_prompt(other))
    result = rules.validate(draft, other)

    assert result.corrections == []
    assert result.columns["title"] == "Cooperativa del Valle"
    assert result.requirements[0].text == "Se necesita tractorista con carné."


def test_the_canned_draft_does_not_invent_what_it_cannot_know() -> None:
    """Una simulación no sabe nada, así que casi todo queda `absent`."""
    draft = extraction.canned_draft(prompt.build_user_prompt(ADVERT))
    result = rules.validate(draft, ADVERT)

    assert result.columns["comp_amount_min"] is None
    assert result.columns["location"] is None
    assert result.posting_company_name is None
    assert result.employer_company_name is None
    assert "simulada" in result.evidence["role_family"]["reasoning"]


def test_the_advert_is_recovered_from_the_delimiters() -> None:
    built = prompt.build_user_prompt(ADVERT)
    assert extraction.advert_from_prompt(built) == ADVERT.strip()
    # Y sin marcas, se acepta el texto tal cual: así se puede llamar con un
    # anuncio a pelo desde un test.
    assert extraction.advert_from_prompt("un anuncio") == "un anuncio"


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"env": "development"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_the_default_provider_is_the_stub() -> None:
    """Para que el harness y el e2e funcionen sin clave y sin gastar."""
    assert _settings().llm_provider == "stub"
    assert _settings().llm_stubbed is True


def test_openai_without_a_key_or_a_model_does_not_start() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY, OPENAI_MODEL"):
        _settings(llm_provider="openai")


def test_a_model_without_a_known_price_does_not_start() -> None:
    """Antes no arrancar que registrar un coste que nadie sabe calcular."""
    with pytest.raises(ValueError, match="tabla de tarifas"):
        _settings(
            llm_provider="openai",
            openai_api_key="sk-inventada",
            openai_model="gpt-5.6-inventado",
        )


def test_a_priced_model_starts() -> None:
    settings = _settings(
        llm_provider="openai",
        openai_api_key="sk-inventada",
        openai_model="gpt-5.6-terra",
    )
    assert settings.llm_stubbed is False


def test_the_stub_is_refused_in_production() -> None:
    """Una extracción simulada en producción no la delataría la interfaz."""
    with pytest.raises(ValueError, match="LLM_PROVIDER=stub no vale"):
        Settings(
            env="production",
            session_secret="algo-distinto",
            google_client_id="id",
            google_client_secret="secreto",
            allowed_emails="alguien@example.test",
            public_base_url="https://example.test",
            llm_provider="stub",
        )


def test_the_stub_is_inert_rather_than_active_in_production() -> None:
    """`llm_stubbed` exige desarrollo, igual que el bypass de autenticación.

    Es el cinturón por si algún día el validador de producción se relaja: la
    propiedad que decide qué cliente se construye no depende solo de la
    variable.
    """
    settings = _settings(llm_provider="stub")
    object.__setattr__(settings, "env", "production")
    assert settings.llm_stubbed is False
