"""La frontera con el repositorio privado `Futuro`, de solo lectura.

Este paquete es lo único de la aplicación que sabe que existe un
repositorio de datos, y lo único que sabe de él es que es un directorio. En
local ese directorio lo pone un *bind mount* al repositorio sintético o al
privado real; en producción, desde M3, lo pone un clon de git con su deploy
key de solo lectura. El cambio de M2 a M3 no tocó nada de aquí arriba, que
es la razón de que la frontera se montara antes que el clon.

Desde aquí no se escribe nunca. La mecánica de escritura con `pull --rebase`,
diff y confirmación que describe `ARCHITECTURE.md` §5 es de la Fase 2 y no
tiene ningún camino en este paquete.
"""

from __future__ import annotations

from futuro_api.data_repo.loader import DataRepoError, load, pdf_path
from futuro_api.data_repo.models import (
    Bullet,
    DataRepo,
    Dimension,
    DisqualifyingCondition,
    Gate,
    ScoringModel,
    VariantGuide,
)
from futuro_api.data_repo.vocabularies import (
    EffortTier,
    PortfolioBucket,
    ProbabilityBand,
)

__all__ = [
    "Bullet",
    "DataRepo",
    "DataRepoError",
    "Dimension",
    "DisqualifyingCondition",
    "EffortTier",
    "Gate",
    "PortfolioBucket",
    "ProbabilityBand",
    "ScoringModel",
    "VariantGuide",
    "load",
    "pdf_path",
]
