"""Ofertas inventadas y constructores de respuestas del modelo.

Nada de aquí es real: ni la empresa, ni la consultora, ni el puesto, ni el
framework que el anuncio dice que hay que dominar. Este repositorio es
público y no entran datos personales ni ofertas reales, tampoco en fixtures.

El anuncio está escrito para tocar a propósito los casos difíciles del
contrato:

- Quien publica (una consultora) no es el empleador final, que hay que
  deducir de la cabecera.
- Pide cinco años de experiencia con un framework publicado el año pasado,
  que es una anomalía que ni se cumple ni se ignora.
- Publica banda salarial sin aclarar si es base o total.
"""

from __future__ import annotations

from typing import Any

from futuro_api.offers import schemas
from futuro_api.offers import vocabularies as vocab

ADVERT = """\
Reclutamiento Bahía — oferta para cliente

Ingeniero de Datos · Sevilla · híbrido

Astillero Nube S.L. construye herramientas de análisis para cooperativas
agrícolas y busca un Ingeniero de Datos para su equipo de Sevilla.

Qué harás
- Mantener y ampliar los pipelines de ingesta de datos de sensores.
- Modelar el almacén analítico junto al equipo de producto.

Qué pedimos
- Imprescindible SQL avanzado.
- Al menos 3 años de experiencia en ingeniería de datos.
- Se valora Python y experiencia con orquestadores de flujos.
- Español nativo e inglés profesional.
- Cinco años de experiencia con Marea, nuestro framework interno, publicado
  el año pasado.

Condiciones
- Banda salarial: 38.000 - 46.000 euros brutos anuales.
- Bonus variable de hasta el 10% sobre el fijo.
- Modalidad híbrida: dos días en oficina.
- Contrato indefinido.

Publica esta oferta Reclutamiento Bahía en nombre de su cliente.
"""


def published(value: Any, quote: str) -> schemas.Claim[Any]:
    return schemas.Claim(
        value=value,
        evidence=schemas.Evidence(
            status=vocab.EvidenceStatus.PUBLISHED,
            source_quote=quote,
            reasoning=None,
            confidence=None,
        ),
    )


def inferred(
    value: Any,
    reasoning: str,
    confidence: vocab.Confidence = vocab.Confidence.HIGH,
) -> schemas.Claim[Any]:
    return schemas.Claim(
        value=value,
        evidence=schemas.Evidence(
            status=vocab.EvidenceStatus.INFERRED,
            source_quote=None,
            reasoning=reasoning,
            confidence=confidence,
        ),
    )


def absent() -> schemas.Claim[Any]:
    return schemas.Claim(
        value=None,
        evidence=schemas.Evidence(
            status=vocab.EvidenceStatus.ABSENT,
            source_quote=None,
            reasoning=None,
            confidence=None,
        ),
    )


def good_draft() -> schemas.ExtractionDraft:
    """Una respuesta que cumple todas las reglas.

    Es la línea base: `validate` no debe corregirle nada. Los tests de
    incumplimiento parten de esta y estropean un solo campo, para que lo que
    falla sea siempre inequívoco.
    """
    return schemas.ExtractionDraft(
        identification=schemas.Identification(
            title=published("Ingeniero de Datos", "Ingeniero de Datos"),
            role_family=inferred(
                vocab.RoleFamily.DATA_ENGINEER,
                "el puesto se llama Ingeniero de Datos y pide pipelines y almacén",
            ),
            seniority_label=inferred(
                vocab.SeniorityLabel.MID,
                "pide tres años de experiencia, sin etiqueta de seniority",
                vocab.Confidence.MEDIUM,
            ),
            experience_years_required=published(
                3.0, "Al menos 3 años de experiencia en ingeniería de datos"
            ),
            location=published("Sevilla", "para su equipo de Sevilla"),
            work_mode=published(
                vocab.WorkMode.HYBRID, "Modalidad híbrida: dos días en oficina"
            ),
            hiring_regions=absent(),
            language_of_work=published(
                ["es", "en"], "Español nativo e inglés profesional"
            ),
            contract_vehicle=published(
                vocab.ContractVehicle.EMPLOYMENT, "Contrato indefinido"
            ),
            posting_status=absent(),
        ),
        compensation=schemas.Compensation(
            amount_min=published(38000.0, "Banda salarial: 38.000 - 46.000 euros"),
            amount_max=published(46000.0, "38.000 - 46.000 euros brutos anuales"),
            currency=published("EUR", "euros brutos anuales"),
            period=published(vocab.CompensationPeriod.YEAR, "euros brutos anuales"),
            # El anuncio no dice si la banda es fija o total: `unclear` es la
            # respuesta correcta, no la más probable.
            basis=published(
                vocab.CompensationBasis.UNCLEAR, "Banda salarial: 38.000 - 46.000"
            ),
            bonus_pct=published(10.0, "Bonus variable de hasta el 10% sobre el fijo"),
            bonus_type=published(vocab.BonusType.MAX, "Bonus variable de hasta el 10%"),
            equity=absent(),
            territorial_adjustment=absent(),
        ),
        companies=schemas.Companies(
            posting=published(
                "Reclutamiento Bahía", "Publica esta oferta Reclutamiento Bahía"
            ),
            employer=inferred(
                "Astillero Nube S.L.",
                "la consultora publica en nombre de su cliente, y la cabecera "
                "nombra a Astillero Nube S.L. como quien busca el puesto",
            ),
            employer_confidence=vocab.EmployerConfidence.HIGH,
        ),
        responsibilities=published(
            [
                "Mantener y ampliar los pipelines de ingesta de datos de sensores",
                "Modelar el almacén analítico junto al equipo de producto",
            ],
            "Mantener y ampliar los pipelines de ingesta de datos de sensores",
        ),
        requirements=[
            schemas.Requirement(
                text="SQL avanzado",
                source_quote="Imprescindible SQL avanzado",
                kind=vocab.RequirementKind.MANDATORY,
                category=vocab.RequirementCategory.TECHNOLOGY,
            ),
            schemas.Requirement(
                text="3 años de experiencia en ingeniería de datos",
                source_quote="Al menos 3 años de experiencia en ingeniería de datos",
                kind=vocab.RequirementKind.MANDATORY,
                category=vocab.RequirementCategory.EXPERIENCE_YEARS,
            ),
            schemas.Requirement(
                text="Python",
                source_quote="Se valora Python",
                kind=vocab.RequirementKind.DESIRABLE,
                category=vocab.RequirementCategory.TECHNOLOGY,
            ),
            schemas.Requirement(
                text="Cinco años de experiencia con Marea",
                source_quote="Cinco años de experiencia con Marea",
                kind=vocab.RequirementKind.ANOMALOUS,
                category=vocab.RequirementCategory.EXPERIENCE_YEARS,
            ),
        ],
        anomalies=[
            schemas.Anomaly(
                requirement_index=3,
                text="cinco años con un framework de hace uno",
                explanation=(
                    "el propio anuncio dice que Marea se publicó el año pasado, "
                    "así que nadie puede acumular cinco años con él"
                ),
                source_quote="publicado\nel año pasado",
            ),
        ],
    )
