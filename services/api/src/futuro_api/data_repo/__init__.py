"""La frontera con el repositorio privado `Futuro`, de solo lectura.

Este paquete es lo único de la aplicación que sabe que existe un
repositorio de datos, y lo único que sabe de él es que es un directorio.
Hoy ese directorio lo pone un *bind mount*; en M3 lo pondrá un clon de git
con su deploy key. Ese cambio no toca nada de aquí arriba, que es la razón
de que la frontera se monte ahora y el clon después.

Desde aquí no se escribe nunca. La mecánica de escritura con `pull --rebase`,
diff y confirmación que describe `ARCHITECTURE.md` §5 es de la Fase 2 y no
tiene ningún camino en este paquete.
"""

from __future__ import annotations

from futuro_api.data_repo.loader import DataRepoError, load
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
]
