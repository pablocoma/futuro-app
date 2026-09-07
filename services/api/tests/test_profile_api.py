"""Los endpoints de `/api/profile/objectives`, de punta a punta: clonar,
`pull --rebase`, diff, commit, push, y el conflicto sin forzar nada. El
remoto es un repo bare de verdad -ver `conftest.seed_bare_repo`-, porque
esto es justo lo que un árbol de ficheros sueltos no puede probar.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from futuro_api.data_repo_write import git_ops
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
        "transition": {
            "target_year": 2030,
            "urgency": "low",
            "expected_tenure_years": [2, 4],
        },
        "primary_objective": {"statement": "Un objetivo cualquiera, editado."},
        "success_dimensions": ["net_savings", "transferable_learning"],
        "role_families": {"core": ["data_engineer"], "exploratory": []},
    }
    base.update(overrides)
    return base


def test_the_profile_endpoints_are_closed_without_a_session(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote, dev_auth_bypass=False)
    response = client.get("/api/profile/objectives")
    assert response.status_code == 401


def test_profile_endpoints_are_503_without_configuration(tmp_path: Path) -> None:
    settings = make_settings(dev_auth_bypass=True)
    client = TestClient(create_app(settings))
    response = client.get("/api/profile/objectives")
    assert response.status_code == 503


def test_get_objectives_clona_y_devuelve_lo_vigente(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.get("/api/profile/objectives")
    assert response.status_code == 200
    body = response.json()
    assert body["role_families"]["core"] == ["data_engineer", "data_scientist"]
    assert body["updated_at"] == "2026-01-01"


def test_diff_calcula_sin_escribir_ni_empujar(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/objectives/diff",
        json=_valid_edit(),
    )
    assert response.status_code == 200
    body = response.json()
    assert "-  statement:" not in body["diff"]  # el diff existe y no está vacío
    assert "+  statement:" in body["diff"] or "Un objetivo cualquiera" in body["diff"]
    assert body["validated"]["primary_objective"]["statement"] == (
        "Un objetivo cualquiera, editado."
    )

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1  # solo el commit de la semilla


def test_commit_escribe_commitea_y_empuja(tmp_path: Path, bare_remote: Path) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/objectives/commit",
        json=_valid_edit(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["commit_sha"]

    log = _git(bare_remote, "log", "-1", "--format=%H %an <%ae> %s", "dev")
    assert body["commit_sha"] in log.stdout
    assert "Futuro App <bot@futuro.local>" in log.stdout

    # Y de verdad quedó escrito: un segundo GET lo confirma.
    again = client.get("/api/profile/objectives")
    assert again.json()["primary_objective"]["statement"] == (
        "Un objetivo cualquiera, editado."
    )


def test_commit_rechaza_una_edicion_invalida_sin_tocar_el_remoto(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/objectives/commit",
        json=_valid_edit(role_families={"core": [], "exploratory": []}),
    )
    assert response.status_code == 422

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1


def test_commit_reporta_el_conflicto_sin_forzar_nada(
    tmp_path: Path, bare_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El choque de contenido real -dos escrituras a la misma línea- ya
    está probado de punta a punta contra un remoto de verdad en
    `test_data_repo_write_git_ops.py::test_commit_and_push_no_fuerza_un_conflicto_de_verdad`.

    Reproducirlo aquí exigiría ganarle la carrera al propio `pull --rebase`
    que el endpoint hace antes de escribir -algo que, con el reemplazo
    estructurado de campos de este mecanismo, solo choca de verdad en la
    ventana estrechísima entre el commit y el push propios-. Lo que hace
    falta comprobar a este nivel es otra cosa: que la ruta HTTP traduce un
    `GitConflictError` en un 409 con el motivo, sin forzar nada, así que se
    provoca directamente.
    """

    def _choca(*args: object, **kwargs: object) -> str:
        raise git_ops.GitConflictError("conflicto de mentira", detail="detalle")

    monkeypatch.setattr(git_ops, "commit_and_push", _choca)

    client = _client(tmp_path, bare_remote)
    response = client.post(
        "/api/profile/objectives/commit",
        json=_valid_edit(),
    )
    assert response.status_code == 409
    assert "conflicto" in response.json()["detail"]

    # Nada se ha empujado: el remoto sigue solo con la semilla.
    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1
