from typing import Any

import pytest

from cv_builder.claim_rules import (
    ClaimRuleViolation,
    validate_bullet_eligibility,
    validate_contribution_language,
)
from cv_builder.models import Bullet, ClaimRules

CLAIM_RULES = ClaimRules.model_validate(
    {
        "professional_contribution_language": {
            "allowed": [
                "contributed_to",
                "worked_on",
                "participated_in_development",
            ],
            "blocked_without_specific_confirmation": [
                "owned",
                "led",
                "architected",
                "built_end_to_end",
            ],
        }
    }
)


def make_bullet(**overrides: Any) -> Bullet:
    defaults: dict[str, Any] = {
        "bullet_id": "test_bullet",
        "text_en": "Contributed to something.",
        "evidence_status": "verified",
        "cv_usage": "eligible_with_internal_policy_check",
        "role_variants": ["widget_maker"],
    }
    defaults.update(overrides)
    return Bullet.model_validate(defaults)


def test_eligible_bullet_passes() -> None:
    validate_bullet_eligibility(make_bullet())


def test_candidate_evidence_status_rejected() -> None:
    with pytest.raises(ClaimRuleViolation):
        validate_bullet_eligibility(make_bullet(evidence_status="candidate"))


def test_blocked_cv_usage_rejected() -> None:
    with pytest.raises(ClaimRuleViolation):
        validate_bullet_eligibility(make_bullet(cv_usage="blocked"))


@pytest.mark.parametrize(
    "text",
    [
        "Contributed to a shared platform.",
        "Worked on integrating services.",
        "Participated in preparing a framework.",
    ],
)
def test_allowed_contribution_verbs_pass(text: str) -> None:
    validate_contribution_language("test_bullet", text, CLAIM_RULES)


def test_participated_in_development_id_matches_participated_in_text() -> None:
    # El banco de bullets usa el id `participated_in`; `cv_variants.yaml`
    # usa `participated_in_development`. Ambos deben aceptar el mismo texto.
    validate_contribution_language(
        "test_bullet", "Participated in validating a system.", CLAIM_RULES
    )


def test_verb_not_at_start_is_rejected() -> None:
    with pytest.raises(ClaimRuleViolation):
        validate_contribution_language(
            "test_bullet", "Delivered a project end to end.", CLAIM_RULES
        )


@pytest.mark.parametrize(
    "text",
    [
        "Led the redesign of a platform.",
        "Owned the delivery of a project.",
        "Architected a new system from scratch.",
        "Contributed to a project, built end to end by the team.",
    ],
)
def test_blocked_ownership_verbs_rejected(text: str) -> None:
    with pytest.raises(ClaimRuleViolation):
        validate_contribution_language("test_bullet", text, CLAIM_RULES)


def test_short_blocked_word_does_not_false_positive_on_substring() -> None:
    # "led" no debe disparar sobre palabras como "scheduled" o "knowledge":
    # la comprobación es por palabra completa, no por subcadena.
    validate_contribution_language(
        "test_bullet",
        "Contributed to a well-scheduled rollout backed by domain knowledge.",
        CLAIM_RULES,
    )
