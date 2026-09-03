"""El esquema que se le manda al modelo tiene que ser válido para él.

*Structured outputs* en modo estricto impone unas cuantas condiciones, y la
API las rechaza con un 400 si no se cumplen. Sin este test, el fallo
aparecería en la primera llamada real —con la clave puesta y el gasto
hecho— en vez de en el harness.
"""

from __future__ import annotations

from typing import Any

from futuro_api.offers.schemas import ExtractionDraft

# Palabras clave que el modo estricto no acepta. La tentación de usarlas es
# real: `minLength` para exigir citas de verdad, `maximum` para acotar un
# porcentaje. Esas comprobaciones van en `rules.py`, que además puede
# explicar por qué falla algo en vez de devolver un 400 opaco.
UNSUPPORTED = (
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "multipleOf",
    "default",
)


def _problems(node: Any, path: str) -> list[str]:
    if not isinstance(node, dict):
        return []
    found: list[str] = []

    if "properties" in node:
        properties = set(node["properties"])
        if node.get("additionalProperties") is not False:
            found.append(f"{path}: le falta additionalProperties=false")
        missing = properties - set(node.get("required", []))
        if missing:
            found.append(f"{path}: {sorted(missing)} no están en required")

    for keyword in UNSUPPORTED:
        if keyword in node:
            found.append(f"{path}: usa «{keyword}», que el modo estricto rechaza")

    for container in ("properties", "$defs"):
        for name, child in node.get(container, {}).items():
            found += _problems(child, f"{path}.{name}")
    if "items" in node:
        found += _problems(node["items"], f"{path}[]")
    for combinator in ("anyOf", "oneOf", "allOf"):
        for index, child in enumerate(node.get(combinator, [])):
            found += _problems(child, f"{path}.{combinator}[{index}]")
    return found


def test_the_draft_schema_is_valid_for_strict_structured_outputs() -> None:
    problems = _problems(ExtractionDraft.model_json_schema(), "raíz")
    assert problems == []


def test_nothing_in_the_draft_has_a_default() -> None:
    """Un valor por defecto haría que el campo no fuese obligatorio.

    Y un campo que el modelo puede omitir es un campo cuya evidencia nadie
    ha declarado, que es justo lo que el contrato no permite.
    """
    schema = ExtractionDraft.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
