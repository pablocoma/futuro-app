"""Aplica al escribir las `claim_rules.professional_contribution_language`
de `config/cv_variants.yaml`, Fase 2 M2.

Porta -no importa- la lógica de `src/cv_builder/claim_rules.py`. Los dos
paquetes (`cv-builder`, la generación del CV en CI, y `futuro-api`, esta
API) tienen `pyproject.toml`/`uv.lock` propios, sin workspace que los
conecte, y el `Dockerfile` de `api` no copia `src/cv_builder` a su imagen:
añadir esa dependencia acoplaría el ciclo de vida de dos paquetes que hoy
se versionan y despliegan por separado, por unas ~30 líneas sin ninguna
dependencia de framework. Si el código de origen cambia, esta copia hay
que actualizarla a mano -es el coste explícito de la duplicación, frente al
acoplamiento-.
"""

from __future__ import annotations

import re

from futuro_api.data_repo_write.models import ClaimRulesForValidation


class ClaimRuleViolation(Exception):
    """Un bullet no cumple las `claim_rules` y no puede guardarse así."""

    def __init__(self, bullet_id: str, reason: str) -> None:
        self.bullet_id = bullet_id
        self.reason = reason
        super().__init__(f"{bullet_id}: {reason}")


def _phrase_and_prefix(verb_id: str) -> tuple[str, str]:
    """Normaliza un id tipo `participated_in_development` a frase y prefijo.

    El banco de bullets y `cv_variants.yaml` no comparten vocabulario para
    el mismo verbo (uno usa `participated_in`, el otro
    `participated_in_development`). Comparar tanto la frase completa como
    sus dos primeras palabras cubre ambos sin acoplar el validador a un
    fichero concreto.
    """
    words = verb_id.split("_")
    phrase = " ".join(words)
    prefix = " ".join(words[:2])
    return phrase, prefix


def validate_contribution_language(
    bullet_id: str, text: str, claim_rules: ClaimRulesForValidation
) -> None:
    rules = claim_rules.professional_contribution_language
    text_lower = text.strip().lower()

    allowed = False
    for verb_id in rules.allowed:
        phrase, prefix = _phrase_and_prefix(verb_id)
        if text_lower.startswith(phrase) or text_lower.startswith(prefix):
            allowed = True
            break
    if not allowed:
        raise ClaimRuleViolation(
            bullet_id,
            f"no empieza por un verbo de contribución permitido: {text!r}",
        )

    for verb_id in rules.blocked_without_specific_confirmation:
        phrase, _prefix = _phrase_and_prefix(verb_id)
        # Coincidencia por palabra completa: una búsqueda de subcadena sin
        # límites de palabra da falsos positivos con verbos cortos como
        # "led", que aparece dentro de "scheduled" o "knowledge".
        if re.search(rf"\b{re.escape(phrase)}\b", text_lower):
            raise ClaimRuleViolation(
                bullet_id,
                f"contiene un verbo de ownership bloqueado ({phrase!r}): {text!r}",
            )
