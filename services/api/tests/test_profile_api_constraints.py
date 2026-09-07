"""Los endpoints de `/api/profile/constraints`, de punta a punta. El
contenido de cada campo -incluido el CRUD de `disqualifying_conditions` y
`superseded_decisions`- ya lo prueba `test_data_repo_write_constraints.py`;
aquí lo que hace falta comprobar es que la ruta HTTP encadena el mecanismo
entero contra un remoto de verdad -mismo patrón que `test_profile_api.py`-.
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
        "hard_constraints": [
            "no_fabricated_claims",
            "no_employer_or_client_confidential_information",
        ],
        "current_known_constraints": {
            "timing": "transition_during_2026",
            "spain_salary_floor_gross_eur": 30000,
            "relocation": "accepted",
            "visa_sponsorship": "accepted",
            "eu_work_authorization": True,
        },
        "sector_policy": {
            "excluded_industries": [],
            "rule": "Regla inventada de política sectorial para el fixture.",
            "note": "Nota inventada, no un dato real.",
        },
        "disqualifying_conditions": [
            {
                "id": "invented_condition_one",
                "rule": "Regla inventada de descalificación número uno, "
                "para el fixture.",
            },
            {
                "id": "invented_condition_two",
                "rule": "Regla inventada de descalificación número dos, "
                "para el fixture.",
            },
        ],
        "accepted_conditions": {
            "on_call_and_shift_work": "aceptado",
            "high_intensity": "Aceptado según preferences.yaml, nota "
            "inventada para el fixture.",
        },
        "pending_decisions": ["invented_pending_decision"],
        "superseded_decisions": [
            {
                "key": "invented_superseded_decision",
                "text": "Texto inventado explicando por qué se sustituyó "
                "esta decisión.",
            }
        ],
    }
    base.update(overrides)
    return base


def test_profile_constraints_closed_without_a_session(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote, dev_auth_bypass=False)
    response = client.get("/api/profile/constraints")
    assert response.status_code == 401


def test_get_constraints_clona_y_devuelve_lo_vigente_con_el_mapa_convertido(
    tmp_path: Path, bare_remote: Path
) -> None:
    """El fichero real declara `superseded_decisions` como mapa; el
    endpoint lo devuelve como la lista de pares que espera el formulario."""
    client = _client(tmp_path, bare_remote)
    response = client.get("/api/profile/constraints")
    assert response.status_code == 200
    body = response.json()
    assert body["superseded_decisions"] == [
        {
            "key": "invented_superseded_decision",
            "text": "Texto inventado explicando por qué se sustituyó esta decisión.",
        }
    ]
    assert len(body["disqualifying_conditions"]) == 2


def test_diff_constraints_calcula_sin_escribir_ni_empujar(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/constraints/diff",
        json=_valid_edit(pending_decisions=["otra_decision_pendiente"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert "otra_decision_pendiente" in body["diff"]

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1


def test_commit_constraints_anade_una_condicion_y_una_decision_sustituida(
    tmp_path: Path, bare_remote: Path
) -> None:
    """Recorrido de punta a punta del CRUD, a través de HTTP: añadir una
    fila a `disqualifying_conditions` y una entrada a
    `superseded_decisions` en el mismo commit."""
    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/constraints/commit",
        json=_valid_edit(
            disqualifying_conditions=[
                {
                    "id": "invented_condition_one",
                    "rule": "Regla inventada de descalificación número uno, "
                    "para el fixture.",
                },
                {
                    "id": "invented_condition_two",
                    "rule": "Regla inventada de descalificación número dos, "
                    "para el fixture.",
                },
                {
                    "id": "invented_condition_three",
                    "rule": "Condición añadida por HTTP.",
                },
            ],
            superseded_decisions=[
                {
                    "key": "invented_superseded_decision",
                    "text": "Texto inventado explicando por qué se "
                    "sustituyó esta decisión.",
                },
                {"key": "otra_sustituida", "text": "Decisión añadida por HTTP."},
            ],
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["commit_sha"]

    log = _git(bare_remote, "log", "-1", "--format=%H %an <%ae> %s", "dev")
    assert body["commit_sha"] in log.stdout
    assert "Futuro App <bot@futuro.local>" in log.stdout

    again = client.get("/api/profile/constraints").json()
    assert len(again["disqualifying_conditions"]) == 3
    assert len(again["superseded_decisions"]) == 2


def test_commit_constraints_rechaza_una_edicion_invalida_sin_tocar_el_remoto(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/constraints/commit",
        json=_valid_edit(hard_constraints=[]),
    )
    assert response.status_code == 422

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1
