"""Aplica en código las `claim_rules` de `config/cv_variants.yaml`.

No se confía en ningún modelo ni en el criterio de quien edita el banco de
bullets: un bullet solo entra en un CV si pasa estas comprobaciones.
"""

from __future__ import annotations

import re

from .models import Bullet, ClaimRules

REQUIRED_EVIDENCE_STATUS = "verified"
REQUIRED_CV_USAGE = "eligible_with_internal_policy_check"


class ClaimRuleViolation(Exception):
    """Un bullet no cumple las claim_rules y no puede entrar en un CV."""

    def __init__(self, bullet_id: str, reason: str) -> None:
        self.bullet_id = bullet_id
        self.reason = reason
        super().__init__(f"{bullet_id}: {reason}")


def validate_bullet_eligibility(bullet: Bullet) -> None:
    if bullet.evidence_status != REQUIRED_EVIDENCE_STATUS:
        raise ClaimRuleViolation(
            bullet.bullet_id,
            f"evidence_status es {bullet.evidence_status!r}, "
            f"se requiere {REQUIRED_EVIDENCE_STATUS!r}",
        )
    if bullet.cv_usage != REQUIRED_CV_USAGE:
        raise ClaimRuleViolation(
            bullet.bullet_id,
            f"cv_usage es {bullet.cv_usage!r}, se requiere {REQUIRED_CV_USAGE!r}",
        )


def _phrase_and_prefix(verb_id: str) -> tuple[str, str]:
    """Normaliza un id tipo `participated_in_development` a frase y prefijo.

    Los dos ficheros de origen no comparten vocabulario para el mismo verbo
    (el banco de bullets usa `participated_in`; `cv_variants.yaml` usa
    `participated_in_development`). Comparar tanto la frase completa como
    sus dos primeras palabras cubre ambos sin acoplar el validador a un
    fichero concreto.
    """
    words = verb_id.split("_")
    phrase = " ".join(words)
    prefix = " ".join(words[:2])
    return phrase, prefix


def validate_contribution_language(
    bullet_id: str, text: str, claim_rules: ClaimRules
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
