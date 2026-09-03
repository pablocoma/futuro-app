"""La llamada de extracción: prompt, esquema y respuesta simulada.

Es la costura entre `offers/` y `llm/`. El módulo de LLM no sabe qué es una
oferta —recibe un prompt y un esquema— y este fichero es el único que sabe
cuáles son los de la extracción.
"""

from __future__ import annotations

from futuro_api.llm import LlmClient, LlmResult
from futuro_api.offers import prompt, schemas
from futuro_api.offers import vocabularies as vocab

# Identifica la tarea en `llm_calls.purpose`, que es lo que permite mirar el
# coste por tipo de trabajo en vez de un total ciego.
PURPOSE = "offer_extraction"

_BULLETS = ("- ", "* ", "• ", "– ")
_MAX_STUB_REQUIREMENTS = 5


async def extract(
    client: LlmClient, raw_text: str
) -> LlmResult[schemas.ExtractionDraft]:
    """Pide la extracción de un anuncio.

    Devuelve la respuesta *sin validar*: lo que sale de aquí puede tener
    citas inventadas y huecos rellenados. Pasarlo por `rules.validate` antes
    de guardarlo no es opcional.
    """
    return await client.structured(
        purpose=PURPOSE,
        system=prompt.SYSTEM_PROMPT,
        user=prompt.build_user_prompt(raw_text),
        schema=schemas.ExtractionDraft,
    )


def advert_from_prompt(user_prompt: str) -> str:
    """Recupera el anuncio de dentro de las marcas del mensaje de usuario.

    Lo necesita la respuesta simulada, que recibe el mensaje ya montado
    igual que lo recibiría el modelo. Si no encuentra las marcas devuelve el
    texto entero, para que se pueda llamar con un anuncio a pelo.
    """
    _, marker, rest = user_prompt.partition("<<<ANUNCIO")
    if not marker:
        return user_prompt.strip()
    advert, _, _ = rest.partition("ANUNCIO>>>")
    return advert.strip()


def _first_meaningful_line(lines: list[str]) -> str | None:
    for line in lines:
        if len(line) >= 3:
            return line
    return None


def canned_draft(user_prompt: str) -> schemas.ExtractionDraft:
    """Una extracción simulada, coherente con el texto que se le pasa.

    Las citas se toman del propio anuncio en vez de estar escritas a mano,
    y eso es lo que hace útil al stub: la verificación de citas de
    `rules.py` se ejecuta de verdad y pasa, así que la pantalla se puede
    desarrollar con cualquier anuncio pegado y sin gastar. Con citas fijas,
    cualquier otro anuncio dejaría todos los campos en `absent` y el camino
    real nunca se recorrería.

    Rellena poco a propósito: título, familia y los requisitos que parecen
    viñetas. Todo lo demás queda `absent`, que es lo que el contrato pide
    cuando no se sabe, y una simulación no sabe nada.
    """
    advert = advert_from_prompt(user_prompt)
    lines = [line.strip() for line in advert.splitlines() if line.strip()]

    title = _first_meaningful_line(lines)
    title_claim: schemas.Claim[str] = (
        schemas.Claim(
            value=title[:120],
            evidence=schemas.Evidence(
                status=vocab.EvidenceStatus.PUBLISHED,
                source_quote=title,
                reasoning=None,
                confidence=None,
            ),
        )
        if title
        else _absent()
    )

    requirements = [
        schemas.Requirement(
            text=line.removeprefix(bullet).strip()[:200],
            source_quote=line,
            kind=vocab.RequirementKind.MANDATORY,
            category=vocab.RequirementCategory.OTHER,
        )
        for line in lines
        if (bullet := next((b for b in _BULLETS if line.startswith(b)), ""))
        and len(line.removeprefix(bullet).strip()) >= 3
    ][:_MAX_STUB_REQUIREMENTS]

    return schemas.ExtractionDraft(
        identification=schemas.Identification(
            title=title_claim,
            role_family=schemas.Claim(
                value=vocab.RoleFamily.OTHER,
                evidence=schemas.Evidence(
                    status=vocab.EvidenceStatus.INFERRED,
                    source_quote=None,
                    # Lo dice en la propia evidencia, que es donde se ve en
                    # pantalla: una extracción simulada no se puede
                    # confundir con una real ni leyendo el detalle.
                    reasoning=(
                        "extracción simulada: no se ha llamado a ningún "
                        "modelo, así que la familia no se ha clasificado"
                    ),
                    confidence=vocab.Confidence.LOW,
                ),
            ),
            seniority_label=_absent(),
            experience_years_required=_absent(),
            location=_absent(),
            work_mode=_absent(),
            hiring_regions=_absent(),
            language_of_work=_absent(),
            contract_vehicle=_absent(),
            posting_status=_absent(),
        ),
        compensation=schemas.Compensation(
            amount_min=_absent(),
            amount_max=_absent(),
            currency=_absent(),
            period=_absent(),
            basis=_absent(),
            bonus_pct=_absent(),
            bonus_type=_absent(),
            equity=_absent(),
            territorial_adjustment=_absent(),
        ),
        companies=schemas.Companies(
            posting=_absent(), employer=_absent(), employer_confidence=None
        ),
        responsibilities=_absent(),
        requirements=requirements,
        anomalies=[],
    )


def _absent[T]() -> schemas.Claim[T]:
    return schemas.Claim(
        value=None,
        evidence=schemas.Evidence(
            status=vocab.EvidenceStatus.ABSENT,
            source_quote=None,
            reasoning=None,
            confidence=None,
        ),
    )
