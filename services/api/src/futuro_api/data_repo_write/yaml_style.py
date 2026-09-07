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
    mapping: MutableMapping[str, object], key: str, text: str
) -> None:
    """Reescribe `mapping[key]` como bloque plegado, solo si `text` es
    distinto de lo que ya había -ni siquiera se construye el
    `FoldedScalarString` nuevo si no hace falta-."""
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
