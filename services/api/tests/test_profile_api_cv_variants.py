"""Los endpoints de `/api/profile/cv-variants` y
`/api/profile/project-catalog`, de punta a punta. El contenido de cada campo
ya lo prueba `test_data_repo_write_cv_variants.py`/
`test_data_repo_write_project_catalog.py`; aquí lo que hace falta comprobar
es que la ruta HTTP encadena el mecanismo entero contra un remoto de verdad
-mismo patrón que `test_profile_api_bullet_bank.py`-.
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


def _cv_variants_edit(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "base_variants": {
            "invented_variant_one": {
                "target_roles": ["invented_role_one"],
                "emphasis": ["invented_emphasis_one"],
                "professional_project_priority": ["invented_project_professional"],
                "public_project_priority": ["invented_project_academic"],
                "candidate_bullet_priority": ["invented_bullet_one"],
            },
            "invented_variant_two": {
                "target_roles": ["invented_role_two"],
                "emphasis": ["invented_emphasis_two"],
                "professional_project_priority": ["invented_project_professional"],
                "public_project_priority": ["invented_project_academic"],
                "candidate_bullet_priority": ["invented_bullet_two"],
            },
        }
    }
    base.update(overrides)
    return base


def _project_catalog_edit(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "projects": [
            {
                "project_id": "invented_project_professional",
                "safe_name": "Invented Professional Project",
                "evidence_status": "verified",
                "cv_usage": "conditional",
                "interview_usage": "conditional",
                "pending_confirmations": ["invented_pending_confirmation"],
            },
            {
                "project_id": "invented_project_academic",
                "safe_name": "Invented Academic Project",
                "evidence_status": "publishable",
                "cv_usage": "eligible",
                "interview_usage": "eligible",
                "pending_confirmations": [],
            },
        ]
    }
    base.update(overrides)
    return base


def test_profile_cv_variants_closed_without_a_session(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote, dev_auth_bypass=False)
    response = client.get("/api/profile/cv-variants")
    assert response.status_code == 401


def test_get_cv_variants_clona_y_devuelve_lo_vigente(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.get("/api/profile/cv-variants")
    assert response.status_code == 200
    body = response.json()
    assert set(body["base_variants"]) == {
        "invented_variant_one",
        "invented_variant_two",
        "invented_variant_blocked",
    }
    # `claim_rules` -bloque fijo- viaja completo.
    assert "professional_contribution_language" in body["claim_rules"]


def test_commit_cv_variants_edita_las_listas_de_una_variante(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _cv_variants_edit()
    edit["base_variants"]["invented_variant_one"]["emphasis"] = ["edited_by_http"]
    response = client.post("/api/profile/cv-variants/commit", json=edit)
    assert response.status_code == 201
    body = response.json()
    assert body["commit_sha"]

    log = _git(bare_remote, "log", "-1", "--format=%H %an <%ae> %s", "dev")
    assert body["commit_sha"] in log.stdout
    assert "Futuro App <bot@futuro.local>" in log.stdout

    again = client.get("/api/profile/cv-variants").json()
    assert again["base_variants"]["invented_variant_one"]["emphasis"] == [
        "edited_by_http"
    ]


def test_commit_cv_variants_rechaza_un_bullet_id_desconocido(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _cv_variants_edit()
    edit["base_variants"]["invented_variant_one"]["candidate_bullet_priority"] = [
        "no_such_bullet"
    ]
    response = client.post("/api/profile/cv-variants/commit", json=edit)
    assert response.status_code == 422

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1


def test_profile_project_catalog_closed_without_a_session(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote, dev_auth_bypass=False)
    response = client.get("/api/profile/project-catalog")
    assert response.status_code == 401


def test_get_project_catalog_clona_y_devuelve_lo_vigente(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.get("/api/profile/project-catalog")
    assert response.status_code == 200
    body = response.json()
    assert len(body["projects"]) == 2
    assert "allowed_evidence_statuses" in body["rules"]


def test_commit_project_catalog_edita_una_fila(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _project_catalog_edit()
    edit["projects"][0]["safe_name"] = "Renamed by HTTP"
    response = client.post("/api/profile/project-catalog/commit", json=edit)
    assert response.status_code == 201
    body = response.json()
    assert body["commit_sha"]

    log = _git(bare_remote, "log", "-1", "--format=%H %an <%ae> %s", "dev")
    assert body["commit_sha"] in log.stdout
    assert "Futuro App <bot@futuro.local>" in log.stdout

    again = client.get("/api/profile/project-catalog").json()
    renamed = next(
        p
        for p in again["projects"]
        if p["project_id"] == "invented_project_professional"
    )
    assert renamed["safe_name"] == "Renamed by HTTP"


def test_commit_project_catalog_rechaza_dar_de_alta_un_proyecto(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _project_catalog_edit()
    edit["projects"].append(
        {
            "project_id": "a_new_project",
            "safe_name": "New",
            "evidence_status": "candidate",
            "cv_usage": "blocked",
            "interview_usage": "blocked",
            "pending_confirmations": [],
        }
    )
    response = client.post("/api/profile/project-catalog/commit", json=edit)
    assert response.status_code == 422

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1
