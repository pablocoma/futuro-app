"""Los endpoints de `/api/profile/preferences`, de punta a punta: clonar,
`pull --rebase`, diff, commit, push. El contenido de cada campo ya lo
prueba `test_data_repo_write_preferences.py`; aquí lo que hace falta
comprobar es que la ruta HTTP encadena el mecanismo entero contra un
remoto de verdad -mismo patrón que `test_profile_api.py`-.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from futuro_api.main import create_app
from tests.conftest import DATA_REPO_WRITE_SEED, make_settings, seed_bare_repo


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    return seed_bare_repo(tmp_path, DATA_REPO_WRITE_SEED)


def _client(tmp_path: Path, bare_remote: Path, **overrides: object) -> TestClient:
    base: dict[str, object] = {
        "dev_auth_bypass": True,
        "data_repo_write_path": str(tmp_path / "clone"),
        "data_repo_write_remote": str(bare_remote),
    }
    base.update(overrides)
    settings = make_settings(**base)
    return TestClient(create_app(settings))


def _valid_edit(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "work_content": {
            "preference": "broad_and_varied",
            "avoid_narrow_specialization": True,
            "client_facing": "acceptable",
            "programming": "acceptable",
            "travel": "acceptable",
        },
        "work_intensity": {
            "willing_to_accept_high_intensity": True,
            "intended_duration_years": [2, 4],
            "condition": "La intensidad debe compensarse con ahorro, marca "
            "o aprendizaje excepcional. Texto inventado para el fixture.",
        },
        "work_mode": {"onsite": "accepted", "hybrid": "accepted", "remote": "accepted"},
        "geography": {
            "eu_passport": True,
            "visa_sponsorship": "accepted",
            "countries": "pending_research",
            "madrid_advantage": "no_rent",
        },
        "compensation": {
            "spain_minimum_gross_eur": 30000,
            "current_madrid_gross_eur": 24000,
            "current_madrid_net_monthly_eur": 1500,
            "current_madrid_payments_per_year": 12,
            "current_living_costs_monthly_eur": [300, 400],
            "current_annual_savings_eur": 12000,
            "savings_baseline_note": "Cifra y explicación inventadas para "
            "el fixture, editada de verdad.",
            "abroad_housing_assumption": "Alquilaría barato si se mudara: "
            "supuesto inventado para el fixture.",
            "outside_madrid_rule": "Debe superar el coste incremental de "
            "mudarse: regla inventada.",
            "international_targets": "pending_cost_of_living_analysis",
        },
        "language": {
            "spanish": "native",
            "english_interview": "functional",
            "evidence": ["invented_evidence_entry"],
            "cv_policy": "Política inventada para el fixture, no un dato real.",
        },
        "professional_project_documentation": {
            "contribution_granularity": "aggregate",
            "avoid_internal_task_breakdown": True,
            "acceptable_evidence": "Descripción inventada de evidencia "
            "aceptable para el fixture.",
            "cv_implication": "Implicación inventada para el CV, dato de prueba.",
        },
    }
    base.update(overrides)
    return base


def test_profile_preferences_closed_without_a_session(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote, dev_auth_bypass=False)
    response = client.get("/api/profile/preferences")
    assert response.status_code == 401


def test_get_preferences_clona_y_devuelve_lo_vigente(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.get("/api/profile/preferences")
    assert response.status_code == 200
    body = response.json()
    assert body["compensation"]["current_living_costs_monthly_eur"] == [300, 400]
    assert body["updated_at"] == "2026-01-01"


def test_diff_preferences_calcula_sin_escribir_ni_empujar(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/preferences/diff",
        json=_valid_edit(
            geography={
                "eu_passport": True,
                "visa_sponsorship": "accepted",
                "countries": "germany_and_netherlands",
                "madrid_advantage": "no_rent",
            }
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert "germany_and_netherlands" in body["diff"]
    assert body["validated"]["geography"]["countries"] == "germany_and_netherlands"

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1  # solo el commit de la semilla


def test_commit_preferences_escribe_commitea_y_empuja(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/preferences/commit",
        json=_valid_edit(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["commit_sha"]

    log = _git(bare_remote, "log", "-1", "--format=%H %an <%ae> %s", "dev")
    assert body["commit_sha"] in log.stdout
    assert "Futuro App <bot@futuro.local>" in log.stdout


def test_commit_preferences_rechaza_una_edicion_invalida_sin_tocar_el_remoto(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/preferences/commit",
        json=_valid_edit(
            work_intensity={
                "willing_to_accept_high_intensity": True,
                "intended_duration_years": [5, 2],  # rango decreciente, invalido
                "condition": "x",
            }
        ),
    )
    assert response.status_code == 422

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1
