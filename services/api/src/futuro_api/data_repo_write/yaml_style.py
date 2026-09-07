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
"""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString


def data_repo_yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
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
