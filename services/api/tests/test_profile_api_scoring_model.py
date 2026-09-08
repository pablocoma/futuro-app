"""Los endpoints de `/api/profile/scoring-model`, de punta a punta. El
contenido de cada campo ya lo prueba `test_data_repo_write_scoring_model.py`;
aquí lo que hace falta comprobar es que la ruta HTTP encadena el mecanismo
entero contra un remoto de verdad -mismo patrón que
`test_profile_api_cv_variants.py`-.
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


def _scoring_model_edit(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "description": "Modelo de comparación INVENTADO, harness de escritura.",
        "baseline": {
            "gross_annual_eur": 24000,
            "payments_per_year": 12,
            "net_monthly_eur": 1600,
            "net_annual_eur": 19200,
            "living_costs_monthly_eur": [350, 450],
            "annual_savings_eur": [13800, 14800],
            "reference_savings_eur": 14000,
            "savings_rate": 0.70,
            "cause": "Motivo inventado de por qué ahorra tanto quedándose donde está.",
            "implication": (
                "Implicación inventada de qué debe batir un puesto en el extranjero."
            ),
        },
        "dimensions": [
            {
                "name": "invented_dimension_one",
                "weight": 30,
                "anchors": [
                    {"label": "assumption", "text": "Supuesto inventado."},
                    {"label": "0", "text": "Ancla de nivel 0."},
                    {"label": "1", "text": "Ancla de nivel 1."},
                    {"label": "3", "text": "Ancla de nivel 3."},
                    {"label": "5", "text": "Ancla de nivel 5."},
                ],
            },
            {
                "name": "invented_dimension_two",
                "weight": 25,
                "anchors": [
                    {"label": "0", "text": "Ancla de nivel 0."},
                    {"label": "3", "text": "Ancla de nivel 3."},
                    {"label": "5", "text": "Ancla de nivel 5."},
                ],
            },
            {
                "name": "invented_dimension_three",
                "weight": 45,
                "anchors": [
                    {"label": "note", "text": "Nota inventada."},
                    {"label": "0", "text": "Ancla de nivel 0."},
                    {"label": "1", "text": "Ancla de nivel 1."},
                    {"label": "3", "text": "Ancla de nivel 3."},
                    {"label": "5", "text": "Ancla de nivel 5."},
                ],
            },
        ],
        "gates": [
            {
                "name": "invented_gate_one",
                "rows": [
                    {"label": "pass", "text": "Criterio de paso."},
                    {"label": "fail", "text": "Criterio de fallo."},
                ],
            },
            {
                "name": "invented_gate_two",
                "rows": [
                    {"label": "context", "text": "Contexto."},
                    {"label": "pass_a", "text": "Criterio A."},
                    {"label": "pass_b", "text": "Criterio B."},
                    {"label": "pending", "text": "Criterio de pendiente."},
                ],
            },
        ],
        "probability_bands": {
            "high": "Banda alta.",
            "medium": "Banda media.",
            "low": "Banda baja.",
            "very_low": "Banda muy baja.",
        },
        "minimum_coverage": 0.55,
        "never_rule": "Regla inventada de qué nunca se estima.",
        "effort_evaluation_order": ["skip", "cheap", "full", "standard"],
        "portfolio_policy": {
            "realistic": 0.40,
            "realistic_stretch": 0.35,
            "aspirational": 0.20,
            "experimental": 0.05,
            "status": "descriptive",
            "note": "Nota de la política de cartera.",
        },
        "notes": ["Primera nota.", "Segunda nota."],
    }
    base.update(overrides)
    return base


def test_profile_scoring_model_closed_without_a_session(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote, dev_auth_bypass=False)
    response = client.get("/api/profile/scoring-model")
    assert response.status_code == 401


def test_get_scoring_model_clona_y_devuelve_lo_vigente(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.get("/api/profile/scoring-model")
    assert response.status_code == 200
    body = response.json()
    assert body["baseline_name"] == "baseline_puerto_inventado"
    assert {d["name"] for d in body["dimensions"]} == {
        "invented_dimension_one",
        "invented_dimension_two",
        "invented_dimension_three",
    }
    # Bloques de solo lectura viajan completos.
    assert "required_fields" in body["output"]
    assert "realistic" in body["portfolio_assignment"]


def test_commit_scoring_model_edita_el_peso_de_una_dimension(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _scoring_model_edit()
    edit["dimensions"][0]["weight"] = 40
    response = client.post("/api/profile/scoring-model/commit", json=edit)
    assert response.status_code == 201
    body = response.json()
    assert body["commit_sha"]

    log = _git(bare_remote, "log", "-1", "--format=%H %an <%ae> %s", "dev")
    assert body["commit_sha"] in log.stdout
    assert "Futuro App <bot@futuro.local>" in log.stdout

    again = client.get("/api/profile/scoring-model").json()
    dimension = next(
        d for d in again["dimensions"] if d["name"] == "invented_dimension_one"
    )
    assert dimension["weight"] == 40


def test_commit_scoring_model_rechaza_un_orden_de_esfuerzo_incompleto(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _scoring_model_edit()
    edit["effort_evaluation_order"] = ["full", "standard", "cheap"]
    response = client.post("/api/profile/scoring-model/commit", json=edit)
    assert response.status_code == 422

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1


def test_commit_scoring_model_rechaza_una_dimension_sin_ancla_numerica(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _scoring_model_edit()
    edit["dimensions"][0]["anchors"] = [{"label": "assumption", "text": "solo nota"}]
    response = client.post("/api/profile/scoring-model/commit", json=edit)
    assert response.status_code == 422

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1
