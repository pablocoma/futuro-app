"""Modelos de validación de escritura, uno por fichero del repositorio
privado. `Objectives` es el primero -M0-; M1-M4 añaden el resto según se
construyan sus rebanadas.

Validan el **resultado** de aplicar una edición, no el documento entero tal
cual: `ruamel.yaml` es quien conserva comentarios y orden en `objectives.py`,
y estos modelos son la puerta de Pydantic que decide si lo que va a quedar
escrito tiene la forma que el fichero promete -toda ella, no solo la parte
que el resto de la aplicación lee hoy-.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from futuro_api.offers.vocabularies import RoleFamily

# `OTHER` es el motivo de "esto no encaja en ningún objetivo", no una
# familia que se declare como propia: no tiene sentido en `objectives.yaml`.
_DECLARABLE_ROLE_FAMILIES = frozenset(RoleFamily) - {RoleFamily.OTHER}


class Transition(BaseModel):
    target_year: int = Field(gt=2000, lt=2100)
    urgency: str = Field(min_length=1)
    expected_tenure_years: tuple[int, int]

    @model_validator(mode="after")
    def _rango_creciente(self) -> Transition:
        low, high = self.expected_tenure_years
        if low > high:
            raise ValueError(
                "expected_tenure_years debe ir de menor a mayor: "
                f"[{low}, {high}] no lo es"
            )
        return self


class PrimaryObjective(BaseModel):
    statement: str = Field(min_length=1)


class RoleFamilies(BaseModel):
    # Vocabulario de código, no libre: `RoleFamily` es lo que
    # `offers/classification` usa para decidir si una oferta cae dentro del
    # objetivo. Un nombre que no coincida no rompería nada al guardar, pero
    # dejaría una familia inalcanzable en silencio -ninguna oferta la
    # tocaría nunca-, que es justo el fallo que este modelo existe para
    # atrapar al escribir y no al puntuar.
    core: tuple[str, ...] = Field(min_length=1)
    exploratory: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _vocabulario_conocido_y_sin_duplicados(self) -> RoleFamilies:
        declared = list(self.core) + list(self.exploratory)
        unknown = sorted(
            {name for name in declared if name not in _DECLARABLE_ROLE_FAMILIES}
        )
        if unknown:
            raise ValueError(
                f"role_families no reconoce {unknown}; las familias válidas "
                f"son {sorted(f.value for f in _DECLARABLE_ROLE_FAMILIES)}"
            )
        duplicated = sorted({name for name in declared if declared.count(name) > 1})
        if duplicated:
            raise ValueError(
                f"role_families repite {duplicated} entre «core» y "
                "«exploratory», o dentro de la misma lista"
            )
        return self


class EditableObjectives(BaseModel):
    """Las cuatro claves que el formulario edita.

    `version` y `updated_at` se quedan fuera a propósito: la primera no la
    toca esta rebanada -no hay ninguna regla de cuándo subirla, a
    diferencia de `scoring_model.yaml`, que sí cambia de comportamiento
    entre versiones- y la segunda la estampa el propio backend con la
    fecha de la escritura, no algo que se rellene a mano cada vez.
    """

    transition: Transition
    primary_objective: PrimaryObjective
    success_dimensions: tuple[str, ...] = Field(min_length=1)
    role_families: RoleFamilies


class Objectives(EditableObjectives):
    """La forma entera de `config/objectives.yaml`, las seis claves.

    Valida el documento completo tras aplicar una edición -toda su forma,
    no solo lo que el resto de la aplicación lee hoy de este fichero
    (`role_families.core`)-, porque este es el único momento en que algo
    comprueba que el fichero entero sigue teniendo sentido.
    """

    version: int = Field(ge=1)
    # YAML sin comillas lo lee como fecha, no como texto: `ruamel` lo carga
    # como `datetime.date` y hay que fecharlo de vuelta con lo mismo, no con
    # un string, para que se escriba sin comillas igual que estaba.
    updated_at: date
