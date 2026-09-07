"""`claim_language.py`: la copia -no import- de `cv_builder.claim_rules`
para validar `text_en` de un bullet al guardarlo. Mismos casos que
`test_data_repo_write_bullet_bank.py` ejercita indirectamente, aquí
aislados de `ruamel` y del fichero."""

from __future__ import annotations

import pytest

from futuro_api.data_repo_write import claim_language
from futuro_api.data_repo_write.models import (
    ClaimRulesForValidation,
    ProfessionalContributionLanguage,
)

RULES = ClaimRulesForValidation(
    professional_contribution_language=ProfessionalContributionLanguage(
        allowed=("contributed_to", "worked_on"),
        blocked_without_specific_confirmation=("owned", "led"),
    )
)


def test_acepta_un_verbo_permitido_sin_verbo_bloqueado() -> None:
    claim_language.validate_contribution_language(
        "b1", "Contributed to an invented feature.", RULES
    )


def test_rechaza_un_texto_que_no_empieza_por_verbo_permitido() -> None:
    with pytest.raises(
        claim_language.ClaimRuleViolation, match="verbo de contribución"
    ):
        claim_language.validate_contribution_language(
            "b1", "Managed an invented feature.", RULES
        )


def test_rechaza_un_verbo_de_ownership_bloqueado() -> None:
    with pytest.raises(claim_language.ClaimRuleViolation, match="ownership"):
        claim_language.validate_contribution_language(
            "b1", "Contributed to and owned an invented feature.", RULES
        )


def test_no_da_falso_positivo_con_un_verbo_corto_dentro_de_otra_palabra() -> None:
    """ "led" no debería saltar dentro de "scheduled" o "knowledge"."""
    claim_language.validate_contribution_language(
        "b1", "Contributed to the scheduled knowledge base.", RULES
    )
