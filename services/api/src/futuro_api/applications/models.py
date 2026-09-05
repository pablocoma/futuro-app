"""La tabla `applications`: el dossier mínimo de M3.

Registra qué variante de CV confirmó Pablo para una oferta y qué PDF exacto
descargó -su `sha256`-, nada más. `docs/OFFER_DATA_CONTRACT.md` (repositorio
privado) ya reserva este nombre para la candidatura completa, con `status`,
`channel`, `submitted_at`, `follow_up_at`, `outcome` e interacciones: esas
columnas son Fase 3 y entran con un `ALTER TABLE` aditivo cuando toque, no
con una tabla nueva ni un renombrado.

**Cuelga de la captura, no de la extracción ni del assessment.** Confirmar
una variante es un gesto de Pablo sobre *la oferta*, el mismo principio que
ya aplica `job_runs.capture_id`: si entra una reextracción entre medias, lo
que cambia es la recomendación que se puede confirmar, no la identidad de
qué oferta se está preparando.

**Append-only, con el mismo trigger de las otras capas.** Cambiar de
variante es una fila nueva, no un `UPDATE`: así queda el historial de qué
confirmó primero y qué decidió después, igual que si un anuncio se
reextrae dos veces. Vigente = la última por `(confirmed_at, id)`.

**`recommendation_id` es nullable y `SET NULL`.** Deja constancia de si
Pablo confirmó lo que dijo el modelo o eligió otra variante, pero no lo
exige: nada impide confirmar una variante sin que exista ninguna
recomendación -el trabajo de puntuación pudo fallar y los cinco PDF ya
existen igual-.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from futuro_api.db import Base, CreatedAt, UuidPk


class Application(Base):
    """El dossier mínimo: qué variante y qué PDF exacto, nada de estado."""

    __tablename__ = "applications"
    __table_args__ = (
        sa.Index(
            "ix_applications_capture_id_confirmed_at",
            "capture_id",
            sa.text("confirmed_at DESC"),
        ),
    )

    id: Mapped[UuidPk]
    capture_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_captures.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("offer_variant_recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # `text` sin CHECK, por lo mismo que `VariantRecommendation.variant`: el
    # vocabulario son los directorios de `cv/variants/` en el repositorio
    # privado, y la base de datos no los conoce. Lo valida el router contra
    # el repositorio de datos cargado en ese momento.
    variant: Mapped[str] = mapped_column(sa.Text, nullable=False)
    cv_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    confirmed_at: Mapped[CreatedAt]
