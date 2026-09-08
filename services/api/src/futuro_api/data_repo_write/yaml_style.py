"""El estilo de `ruamel.yaml` compartido por todo módulo que edita un
fichero del repositorio privado, y la disciplina para no ensuciar un diff
con un reformateo que no viene a cuento.

**La configuración de indentado vive aquí y no repetida en cada fichero**
-`objectives.py` es el primero, `preferences.py` y `constraints.py` la
reutilizan-, porque una sola instancia que divergiera de las demás haría
que esa escritura concreta reformatee el fichero entero en su próximo
commit, sin que nadie lo note hasta ver un diff sospechosamente grande.
Comprobado byte a byte contra `career-strategy` real en Fase 2 M0: ver
`docs/decisions/fase-2-perfil-editable.md`.

**`set_folded_if_changed` y `set_string_list_if_changed` existen por un
hallazgo de M1, no de M0**: reasignar un valor a un `CommentedMap` o
`CommentedSeq` de ruamel -aunque el contenido final sea idéntico al que ya
había- puede perder metadatos de formato que no viven en el valor sino en
la posición. Comprobado contra `constraints.yaml` y `objectives.yaml`
reales el 2026-09-07:

- Envolver un texto en `FoldedScalarString` de nuevo -incluso con el mismo
  texto aplanado- lo reenvuelve con el ancho por omisión de `ruamel`, que
  no tiene por qué coincidir con el ancho a mano del fichero real. Sin
  guardia, `objectives.py` ya lo hacía sin darse cuenta en M0: editar
  `target_year` y dejar la declaración intacta igualmente reflowaba su
  línea.
- Reemplazar una `CommentedSeq` entera, o incluso mutarla con un
  slice-assign de contenido idéntico, puede perder la línea en blanco de
  cierre que quedó asociada a su último elemento.

La única forma fiable de no ensuciar el diff es no tocar nada cuando el
valor no cambió de verdad.

**Hallazgo de Fase 2 M2, con `professional_bullet_bank.yaml` real**: un
`null` explícito (`project_id: null`) se volvía a escribir en blanco
(`project_id:`) con la sola secuencia cargar->volcar, **sin tocar nada**.
No es un bug de `set_folded_if_changed` ni de ninguna de las dos funciones
de arriba -esos campos no pasan por ninguna de las dos-: es que el
representador de `None` por omisión de `ruamel.yaml` en modo *round-trip*
no reproduce el estilo `null` del nodo original, a diferencia de como sí
trata los escalares de texto y las listas. Comprobado byte a byte contra
`career-strategy` real el 2026-09-07: sin el representador de más abajo,
cargar y volcar `professional_bullet_bank.yaml` sin ninguna edición ya
difiere en esa línea.

**Segundo hallazgo de M2, con `role_variant_content.yaml` real**: sus
`skills.value` son escalares planos de una sola línea física, algunos por
encima de los 80 caracteres del ancho por omisión de `ruamel`; cargar y
volcar sin ninguna edición partía esa línea en dos. Ensanchar
`yaml.width` lo corrige **sin romper** el round-trip de los campos
plegados de los otros tres ficheros -comprobado explícitamente: `ruamel`
no fuerza un re-envolvido al ancho nuevo, conserva los saltos de línea del
escalar tal como se cargó mientras quepan bajo ese ancho-, así que un
ancho generoso es estrictamente más seguro que el de 80 por omisión.

**Hallazgo de Fase 2 M4, con `scoring_model.yaml` real**: reasignar un
escalar **numérico** sin comprobar antes si cambió pierde formato igual
que un texto -no solo los folded scalars tienen esta trampa-. Comprobado
el 2026-09-08: `minimum_coverage: 0.50` se reescribía como `0.5` con la
sola secuencia cargar->volcar de una reasignación incondicional, aunque
el valor puntuado fuera exactamente el mismo, porque un `float` de Python
no lleva los ceros decimales que sí lleva el `ScalarFloat` de `ruamel`.
Ningún módulo anterior (M0-M3) tenía un campo numérico con formato
significativo -pesos y años son enteros sin decimales, sin nada que
perder-, así que el hallazgo no podía haber aparecido antes.
`set_scalar_if_changed` cierra esto para cualquier escalar, no solo
texto: comparar por valor (`!=`) antes de reasignar deja intacto el nodo
de origen siempre que el valor no cambió de verdad, sea cual sea su tipo.

**`notes` de `scoring_model.yaml`, a diferencia de `hard_constraints`/
`pending_decisions`, es una lista de párrafos en bloque plegado, no de
líneas cortas.** `set_string_list_if_changed` reescribiría cada entrada
modificada como una cadena entrecomillada de una sola línea -válida, pero
un cambio de estilo que nadie pidió-; `set_folded_list_if_changed` pliega
cada entrada nueva, mismo criterio que `set_folded_if_changed` aplica a un
campo suelto.
"""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString


def _represent_none(representer: Any, _data: None) -> Any:
    return representer.represent_scalar("tag:yaml.org,2002:null", "null")


def data_repo_yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    # Generoso a propósito: por debajo de esto, un escalar plano de una
    # sola línea física más largo que el ancho se parte en dos al volcar,
    # aunque no se haya tocado -ver el hallazgo de arriba-.
    yaml.width = 100_000
    yaml.representer.add_representer(type(None), _represent_none)
    return yaml


def set_folded_if_changed(
    mapping: MutableMapping[Any, object], key: object, text: str
) -> None:
    """Reescribe `mapping[key]` como bloque plegado, solo si `text` es
    distinto de lo que ya había -ni siquiera se construye el
    `FoldedScalarString` nuevo si no hace falta-.

    `key` no está tipado como `str`: las anclas de una dimensión de
    `scoring_model.yaml` casan por un nivel numérico (`0`, `1`, ...) tanto
    como por una nota de nombre libre (`assumption`, ...)."""
    if str(mapping[key]) == text:
        return
    mapping[key] = FoldedScalarString(text)


def set_string_list_if_changed(
    container: MutableMapping[str, Any], key: str, values: Iterable[str]
) -> None:
    """Muta en su sitio la `CommentedSeq` de `container[key]` -nunca la
    reemplaza-, y solo si `values` difiere de lo que ya hay."""
    existing = container[key]
    new_values = list(values)
    if list(existing) == new_values:
        return
    existing[:] = new_values


def set_folded_list_if_changed(
    container: MutableMapping[str, Any], key: str, values: Iterable[str]
) -> None:
    """Como `set_string_list_if_changed`, pero plegando cada entrada nueva.

    Para una lista de párrafos -`notes` de `scoring_model.yaml`- y no de
    líneas cortas: sin plegar, una entrada modificada quedaría como una
    cadena entrecomillada de una sola línea en vez de conservar el estilo
    de bloque plegado (`>-`) del fichero real."""
    existing = container[key]
    new_values = list(values)
    if list(existing) == new_values:
        return
    existing[:] = [FoldedScalarString(text) for text in new_values]


def set_scalar_if_changed(
    mapping: MutableMapping[str, Any], key: str, value: object
) -> None:
    """Reasigna `mapping[key]` solo si `value` es distinto de lo que ya hay.

    Hace falta también para escalares **numéricos**, no solo para texto:
    ver el hallazgo de Fase 2 M4 más arriba. Comparar por valor antes de
    reasignar es lo único que deja intacto el nodo de origen -con su
    formato- cuando el valor no cambió de verdad, sin importar el tipo."""
    if mapping[key] != value:
        mapping[key] = value
