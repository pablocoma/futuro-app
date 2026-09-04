"""Un resumen de la oferta ya extraída, en texto, para el prompt.

Existe para que `prompt.py` no sepa nada de SQLAlchemy —igual que en M1, que
solo recibía el texto pegado— y para que lo que se le manda al modelo al
puntuar sea explícitamente **la extracción**, no el anuncio otra vez. La
diferencia importa: la extracción ya pasó por `rules.py`, así que lo que
llega aquí son datos con su evidencia comprobada, y el modelo puntúa sobre
eso en vez de volver a leer el anuncio a su manera.

El anuncio también viaja, pero para otra cosa: es el pajar contra el que se
comprueban las citas, así que el modelo tiene que poder copiar de él.
"""

from __future__ import annotations

from dataclasses import dataclass

from futuro_api.models import OfferExtraction
from futuro_api.offers import vocabularies as offers_vocab


@dataclass(frozen=True)
class BriefRequirement:
    """Un requisito, con la posición por la que se le referencia."""

    position: int
    text: str
    kind: offers_vocab.RequirementKind
    category: offers_vocab.RequirementCategory


@dataclass(frozen=True)
class OfferBrief:
    """Lo que se sabe de una oferta, sin sobres de evidencia.

    Los sobres se quedan fuera a propósito: al puntuar, lo que importa de un
    campo es su valor o su ausencia, y arrastrar la cita de cada campo
    duplicaría el anuncio, que ya va aparte y entero.

    Un campo ausente **se dice**, no se omite. Que el anuncio no publique
    salario es información que el modelo necesita para dejar la dimensión
    sin puntuar en vez de buscarla otra vez.
    """

    fields: tuple[tuple[str, str], ...]
    requirements: tuple[BriefRequirement, ...]
    anomalies: tuple[str, ...]
    role_family: str | None

    def render(self) -> str:
        lines = [f"- {name}: {value}" for name, value in self.fields]
        if self.requirements:
            lines.append("- requisitos:")
            lines += [
                f"  [{requirement.position}] ({requirement.kind.value}, "
                f"{requirement.category.value}) {requirement.text}"
                for requirement in self.requirements
            ]
        if self.anomalies:
            lines.append("- anomalías detectadas en el anuncio:")
            lines += [f"  · {anomaly}" for anomaly in self.anomalies]
        return "\n".join(lines)


ABSENT = "sin datos"

# Los campos de la extracción que se le pasan al modelo al puntuar, con el
# nombre con el que se le presentan. Escritos a mano y no derivados del
# esquema, al contrario que en las vistas: aquí la lista es un juicio sobre
# qué hace falta para puntuar, no la totalidad del contrato. `hiring_regions`
# o `status_checked_at` no aportan nada a una nota y solo gastarían tokens.
_FIELDS: tuple[tuple[str, str], ...] = (
    ("title", "puesto"),
    ("role_family", "familia de puesto"),
    ("seniority_label", "seniority declarada"),
    ("experience_years_required", "años de experiencia exigidos"),
    ("location", "ubicación"),
    ("work_mode", "modalidad"),
    ("language_of_work", "idiomas de trabajo"),
    ("contract_vehicle", "vehículo contractual"),
    ("comp_amount_min", "compensación mínima publicada"),
    ("comp_amount_max", "compensación máxima publicada"),
    ("comp_currency", "moneda"),
    ("comp_period", "periodo"),
    ("comp_basis", "base o total"),
    ("comp_bonus_pct", "bonus (%)"),
    ("comp_bonus_type", "tipo de bonus"),
    ("comp_equity", "equity"),
    ("comp_territorial_adjustment", "ajuste territorial"),
)


def _readable(value: object) -> str:
    if value is None:
        return ABSENT
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else ABSENT
    return str(value)


def brief_of(extraction: OfferExtraction) -> OfferBrief:
    """El resumen de una extracción, con las empresas por delante."""
    companies = []
    if extraction.posting_company is not None:
        companies.append(("quien publica", extraction.posting_company.name))
    if extraction.employer_company is not None:
        confidence = extraction.employer_confidence
        companies.append(
            (
                "empleador final",
                f"{extraction.employer_company.name} "
                f"(confianza: {confidence.value if confidence else 'sin declarar'})",
            )
        )

    fields = tuple(companies) + tuple(
        (label, _readable(getattr(extraction, column, None)))
        for column, label in _FIELDS
    )
    responsibilities = extraction.responsibilities or []
    if responsibilities:
        fields += (("responsabilidades", " | ".join(responsibilities)),)

    return OfferBrief(
        fields=fields,
        requirements=tuple(
            BriefRequirement(
                position=requirement.position,
                text=requirement.text,
                kind=requirement.kind,
                category=requirement.category,
            )
            for requirement in extraction.requirements
        ),
        anomalies=tuple(
            f"{anomaly.text} — {anomaly.explanation}"
            for anomaly in extraction.anomalies
        ),
        role_family=(extraction.role_family.value if extraction.role_family else None),
    )
