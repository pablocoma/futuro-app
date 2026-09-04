"""Tablas de la capa `assessment` del contrato.

Cuatro decisiones de forma que no vienen dadas por el contrato y conviene
leer antes de tocar nada.

**Cuelga de la extracción, no de la captura.** Un assessment es la
conclusión sobre una lectura concreta del anuncio. Si se reextrae con otro
prompt, la conclusión anterior describe el anuncio tal como se leyó antes, y
seguir enseñándola como vigente sería mentir. El vigente es el último por
`(assessed_at, id)` de la extracción vigente: el mismo patrón que M1 usa
para la extracción, y sin marca mutable de «vigente» por el mismo motivo.

**Append-only, con el trigger de inmutabilidad de las otras dos capas.**
«Recalculable» significa insertar una fila nueva, no editar la vieja. Sin el
trigger, alguien arregla una nota en sitio y la promesa que justifica
guardar `scoring_model_version` —que dos ofertas puntuadas con modelos
distintos se noten— muere en silencio. Sin `unique(extraction_id,
scoring_model_version)`, por lo mismo que M1 no lo puso en las
extracciones: repuntuar tras un fallo con la misma versión tiene que poder
crear fila.

**Las dimensiones y los filtros son tablas hijas, no columnas.** Seis
columnas tipadas —`score_role_fit`, `score_career_capital_and_brand`…— serían
duplicar en el esquema la lista de dimensiones, que vive en
`config/scoring_model.yaml` y cambia sin pasar por aquí. Tampoco es la EAV
que M1 descartó: la forma es fija y uniforme, no un vocabulario de campos
que la base de datos desconoce. Y el precio de un join se cobra con lo que
un jsonb no daría: los CHECK que imponen la regla central del contrato —una
nota sin cita no entra— y poder preguntar en SQL cuánto puntúa de media una
dimensión en toda la cartera.

**La recomendación de variante es su propia tabla.** La propiedad que
define esta capa es que se recalcula sin volver a llamar al modelo, y la
elección de variante **no** se puede recalcular sin llamarlo. Si viviera
como tres columnas del assessment, cada repuntuación tendría que o pagar
otra llamada o arrastrar la elección anterior, y la propiedad dejaría de ser
cierta. Separada, repuntuar el histórico no toca ninguna variante elegida.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from futuro_api.assessment import vocabularies as vocab
from futuro_api.data_repo import vocabularies as data_vocab
from futuro_api.db import Base, CreatedAt, UuidPk, vocabulary
from futuro_api.offers import vocabularies as offers_vocab
from futuro_api.offers.models import OfferRequirement


class OfferAssessment(Base):
    """Capa 3. Lo que se concluye de una oferta, recalculable.

    Todas las columnas de esta tabla las calcula el código a partir de las
    notas de `offer_assessment_dimensions` y de los estados de
    `offer_assessment_gates`. Ninguna la puede poner el modelo: el esquema
    de salida de `assessment/schemas.py` no tiene dónde escribirlas.
    """

    __tablename__ = "offer_assessments"
    __table_args__ = (
        sa.CheckConstraint(
            "value_score IS NULL OR (value_score >= 0 AND value_score <= 5)",
            name="value_score_in_scale",
        ),
        sa.CheckConstraint(
            "coverage >= 0 AND coverage <= 1", name="coverage_is_a_fraction"
        ),
        # Un recálculo no tiene trabajo en la cola: no llama a nadie. Es la
        # invariante que hace comprobable la repuntuación, y si algún día
        # alguien «recalcula» llamando al LLM, esto no le deja guardarlo.
        #
        # En una sola dirección y no como bicondicional, aunque «un
        # assessment del modelo tiene trabajo» también sea verdad. El
        # motivo: `job_run_id` es `ON DELETE SET NULL`, así que un
        # bicondicional convertiría el borrado de una fila de `job_runs` en
        # una violación de CHECK, y encima irreparable, porque el trigger de
        # inmutabilidad bloquea el UPDATE que la arreglaría. Lo que sí queda
        # garantizado de un assessment del modelo es que declara su prompt y
        # su modelo, que es el CHECK de abajo.
        sa.CheckConstraint(
            "source <> 'recomputed' OR job_run_id IS NULL",
            name="recomputed_has_no_job",
        ),
        sa.CheckConstraint(
            "(source = 'llm') = (prompt_version IS NOT NULL AND model IS NOT NULL)",
            name="llm_declares_prompt_and_model",
        ),
        # Un recálculo dice de qué fila salió, para poder recorrer la cadena
        # hasta la que sí llamó al modelo. En una sola dirección por lo
        # mismo que el primero: `derived_from_id` también es `SET NULL`.
        sa.CheckConstraint(
            "source <> 'recomputed' OR derived_from_id IS NOT NULL",
            name="recomputed_declares_its_origin",
        ),
        # Un cubo que falta lleva siempre su motivo. Es lo que hace que un
        # hueco en pantalla se pueda leer —«el modelo de scoring no asigna
        # cubo a very_low»— en vez de parecer un fallo de la aplicación.
        sa.CheckConstraint(
            "portfolio_bucket IS NOT NULL OR portfolio_note IS NOT NULL",
            name="missing_bucket_explains_itself",
        ),
        sa.Index(
            "ix_offer_assessments_extraction_id_assessed_at",
            "extraction_id",
            sa.text("assessed_at DESC"),
        ),
    )

    id: Mapped[UuidPk]
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_extractions.id", ondelete="CASCADE"), nullable=False
    )
    # Un trabajo produce como mucho un assessment, y el índice único lo
    # impone, igual que en las extracciones de M1.
    job_run_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("job_runs.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    source: Mapped[vocab.AssessmentSource] = mapped_column(
        vocabulary(vocab.AssessmentSource, "assessment_source"), nullable=False
    )
    # De qué fila se recalculó esta. Deja el linaje explícito: una cadena de
    # repuntuaciones se puede recorrer hasta la que sí llamó al modelo.
    derived_from_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("offer_assessments.id", ondelete="SET NULL"), nullable=True
    )

    # Con qué modelo de scoring. La versión es lo que declara el YAML; el
    # hash es lo que el YAML *era*. Las dos, porque `version: 1` no cambió
    # las dos veces que el modelo cambió el 2026-08-13.
    scoring_model_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    scoring_model_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    # Nulos en un recálculo, que no llama a ningún modelo.
    prompt_version: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    model: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Nulo cuando la cobertura no llega al mínimo del modelo de scoring:
    # `missing_data.below_minimum` dice que entonces no se emite
    # puntuación, y un cero no es «no se sabe».
    value_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(3, 2), nullable=True)
    coverage: Mapped[Decimal] = mapped_column(sa.Numeric(4, 3), nullable=False)
    probability_band: Mapped[data_vocab.ProbabilityBand] = mapped_column(
        vocabulary(data_vocab.ProbabilityBand, "probability_band"), nullable=False
    )
    probability_reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    portfolio_bucket: Mapped[data_vocab.PortfolioBucket | None] = mapped_column(
        vocabulary(data_vocab.PortfolioBucket, "portfolio_bucket"), nullable=True
    )
    portfolio_note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    effort_tier: Mapped[data_vocab.EffortTier] = mapped_column(
        vocabulary(data_vocab.EffortTier, "effort_tier"), nullable=False
    )
    # Lo que el código le corrigió al modelo, con la misma forma que en la
    # extracción. No es un log: es la cuenta de cuántas veces se salta las
    # reglas al puntuar, que es lo que dice si hay que cambiar el prompt.
    corrections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    assessed_at: Mapped[CreatedAt]

    dimensions: Mapped[list[AssessmentDimension]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentDimension.position",
        lazy="selectin",
    )
    gates: Mapped[list[AssessmentGate]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentGate.position",
        lazy="selectin",
    )
    requirement_matches: Mapped[list[RequirementMatchRow]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AssessmentDimension(Base):
    """La nota de una dimensión, o el hueco donde no se pudo puntuar.

    `weight` y `anchor` se guardan con la fila en vez de releerse del YAML
    al pintar, y es lo que hace reproducible la composición ponderada de la
    pantalla: la barra de una oferta puntuada en marzo se dibuja con el peso
    que produjo su nota, no con el peso de hoy.

    Una dimensión sin puntuar **es esta misma fila** con `score` nulo y
    `unscored_reason` con el motivo. No hay una lista aparte de
    `unscored_dimensions` que pueda contradecir a las notas.
    """

    __tablename__ = "offer_assessment_dimensions"
    __table_args__ = (
        sa.CheckConstraint("weight > 0", name="weight_positive"),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 5)", name="score_in_scale"
        ),
        # La regla central del contrato, en la base de datos: «una nota sin
        # cita es inválida». Está además en `rules.py`, que es quien decide
        # qué hacer con ella; esto es la red de debajo.
        sa.CheckConstraint(
            "score IS NULL OR citation IS NOT NULL", name="score_needs_citation"
        ),
        # Y su simétrica: sin puntuar y con motivo, o puntuada y sin motivo
        # de no puntuación. Nunca las dos ni ninguna.
        sa.CheckConstraint(
            "(score IS NULL) = (unscored_reason IS NOT NULL)",
            name="unscored_explains_itself",
        ),
        sa.UniqueConstraint("assessment_id", "dimension"),
        sa.UniqueConstraint("assessment_id", "position"),
    )

    id: Mapped[UuidPk]
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_assessments.id", ondelete="CASCADE"), nullable=False
    )
    # El orden en que `weights` las declara en el YAML, que es el de las
    # barras. Sin esto lo decidiría el planificador.
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # `text` y sin CHECK a propósito: la lista de dimensiones vive en el
    # repositorio de datos y una migración no debe ir detrás de un YAML que
    # se edita a mano. El vocabulario válido lo comprueba `rules.py` contra
    # lo cargado en ese momento.
    dimension: Mapped[str] = mapped_column(sa.Text, nullable=False)
    weight: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    score: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    citation: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # El ancla escrita que aplica a la nota, copiada del YAML al puntuar.
    anchor: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    unscored_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    assessment: Mapped[OfferAssessment] = relationship(back_populates="dimensions")


class AssessmentGate(Base):
    """El veredicto de un filtro eliminatorio.

    `pending` y sin cita, o decidido y con cita: nunca otra combinación. Un
    filtro pendiente no se apoya en nada del anuncio —si algo lo resolviera,
    no estaría pendiente— y un filtro decidido sin cita comprobable es lo
    que `rules.py` degrada a pendiente.
    """

    __tablename__ = "offer_assessment_gates"
    __table_args__ = (
        sa.CheckConstraint(
            "(status = 'pending') = (citation IS NULL)",
            name="only_a_decided_gate_cites",
        ),
        sa.UniqueConstraint("assessment_id", "gate"),
        sa.UniqueConstraint("assessment_id", "position"),
    )

    id: Mapped[UuidPk]
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_assessments.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # `text` sin CHECK, por lo mismo que `dimension`.
    gate: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[vocab.GateStatus] = mapped_column(
        vocabulary(vocab.GateStatus, "gate_status"), nullable=False
    )
    citation: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)

    assessment: Mapped[OfferAssessment] = relationship(back_populates="gates")


class RequirementMatchRow(Base):
    """El cruce de un requisito contra el banco de evidencias.

    Vive aquí y no en `offer_requirements`, donde el contrato lo dibuja, y
    el motivo es una contradicción del propio contrato: `offer_requirements`
    es una capa inmutable —lo impone un trigger desde M1— y el cruce tiene
    que poder recalcularse, porque el banco de evidencias cambia. La Fase 2
    es literalmente «perfil editable». Si el cruce viviera en la extracción,
    volver a cruzar exigiría reextraer y pagar el LLM otra vez, que es justo
    lo que separar las capas evita.

    Así que `offer_requirements.match`, `.evidence_ref` y `.cv_action` se
    quedan en NULL para siempre, y NULL sigue significando «sin evaluar».

    `cv_action` existe aquí como columna y se queda nula: `ARCHITECTURE.md`
    §7 descarta explícitamente la adaptación fina por vacante, así que hoy
    nadie consumiría `include`/`prioritise`/`omit`, y un campo que nadie lee
    se llena mal sin que nadie se entere.

    Que el requisito y el assessment sean de la misma extracción lo garantiza
    quien construye las filas, no una constraint: expresarlo exigiría
    arrastrar `extraction_id` aquí y una clave ajena compuesta, y el único
    camino que escribe esta tabla las crea juntas.
    """

    __tablename__ = "offer_requirement_matches"
    __table_args__ = (
        # La prohibición central del contrato, ahora en la tabla que sí
        # rellena estos campos: sin referencia a una evidencia, el máximo
        # que se puede afirmar es `partial`.
        sa.CheckConstraint(
            "match <> 'meets' OR evidence_ref IS NOT NULL",
            name="meets_needs_evidence_ref",
        ),
        sa.UniqueConstraint("assessment_id", "requirement_id"),
    )

    id: Mapped[UuidPk]
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_assessments.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_requirements.id", ondelete="CASCADE"), nullable=False
    )
    match: Mapped[offers_vocab.RequirementMatch] = mapped_column(
        vocabulary(offers_vocab.RequirementMatch, "requirement_match"), nullable=False
    )
    # Un `bullet_id` que `rules.py` ha comprobado que existe, está
    # `verified` y es divulgable. Que resuelva no se puede imponer con una
    # clave ajena: el banco de evidencias no es una tabla, es un YAML del
    # repositorio privado.
    evidence_ref: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    cv_action: Mapped[offers_vocab.CvAction | None] = mapped_column(
        vocabulary(offers_vocab.CvAction, "cv_action"), nullable=True
    )
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)

    assessment: Mapped[OfferAssessment] = relationship(
        back_populates="requirement_matches"
    )
    requirement: Mapped[OfferRequirement] = relationship(lazy="selectin")


class VariantRecommendation(Base):
    """La variante de CV que el modelo eligió para una oferta.

    Tabla aparte del assessment porque no es recalculable sin el modelo: ver
    la cabecera del módulo. Cuelga de la extracción por lo mismo que el
    assessment, y guarda el hash de la guía que leyó el modelo, que es lo
    que permite saber después si la recomendación se hizo con la estrategia
    de variantes de entonces o con otra.

    En M3 Pablo confirma o cambia la variante. Esa confirmación será una
    fila suya en otra tabla y no un `UPDATE` aquí: esta fila dice qué eligió
    el modelo, y eso no cambia porque alguien decida otra cosa.
    """

    __tablename__ = "offer_variant_recommendations"
    __table_args__ = (
        sa.Index(
            "ix_offer_variant_recommendations_extraction_id_recommended_at",
            "extraction_id",
            sa.text("recommended_at DESC"),
        ),
    )

    id: Mapped[UuidPk]
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_extractions.id", ondelete="CASCADE"), nullable=False
    )
    job_run_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("job_runs.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    # `text` sin CHECK: el vocabulario son los directorios que existen en
    # `cv/variants/` del repositorio privado, y la base de datos no los
    # conoce. Lo comprueba `rules.validate_variant`, que rechaza la
    # recomendación entera si la variante no existe.
    variant: Mapped[str] = mapped_column(sa.Text, nullable=False)
    confidence: Mapped[offers_vocab.Confidence] = mapped_column(
        vocabulary(offers_vocab.Confidence, "confidence"), nullable=False
    )
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    variants_guide_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    recommended_at: Mapped[CreatedAt]
