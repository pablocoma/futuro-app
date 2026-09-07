"""Los endpoints de `/api/profile/bullet-bank` y `/api/profile/role-variants`,
de punta a punta. El contenido de cada campo ya lo prueba
`test_data_repo_write_bullet_bank.py`/`test_data_repo_write_role_variant_content.py`;
aquí lo que hace falta comprobar es que la ruta HTTP encadena el mecanismo
entero contra un remoto de verdad -mismo patrón que `test_profile_api_constraints.py`-.
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


def _bullet_bank_edit(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "bullets": [
            {
                "bullet_id": "invented_bullet_one",
                "text_en": "Contributed to building an invented internal tool "
                "for the fixture.",
                "evidence_status": "verified",
                "cv_usage": "eligible_with_internal_policy_check",
            },
            {
                "bullet_id": "invented_bullet_two",
                "text_en": "Explored an early prototype for the fixture, "
                "not yet confirmed.",
                "evidence_status": "candidate",
                "cv_usage": "blocked",
            },
        ]
    }
    base.update(overrides)
    return base


def _role_variants_edit(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "variants": {
            "invented_variant_one": {
                "display_name": "Invented Variant One",
                "use_when": "Nota inventada de cuándo usar esta variante, "
                "para el fixture.",
                "profile": "Perfil inventado para la variante uno, sin "
                "ningún dato real.",
                "skills": [
                    {"label": "Programming", "value": "Invented, Language"},
                    {"label": "Tools", "value": "Invented Tool A, Invented Tool B"},
                ],
            },
            "invented_variant_two": {
                "display_name": "Invented Variant Two",
                "use_when": "Otra nota inventada de cuándo usar esta variante, "
                "para el fixture.",
                "profile": "Perfil inventado para la variante dos, sin "
                "ningún dato real.",
                "skills": [
                    {"label": "Programming", "value": "Invented, Language"},
                ],
            },
        }
    }
    base.update(overrides)
    return base


def test_profile_bullet_bank_closed_without_a_session(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote, dev_auth_bypass=False)
    response = client.get("/api/profile/bullet-bank")
    assert response.status_code == 401


def test_get_bullet_bank_clona_y_devuelve_lo_vigente(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.get("/api/profile/bullet-bank")
    assert response.status_code == 200
    body = response.json()
    assert len(body["bullets"]) == 2
    # `policy` -bloque fijo- viaja completo, con la revisión de redacción
    # de estado ya confirmada.
    assert "status_claims_confirmed_2026_08_14" in body["policy"]


def test_diff_bullet_bank_calcula_sin_escribir_ni_empujar(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _bullet_bank_edit()
    edit["bullets"][0]["text_en"] = "Worked on an edited invented tool."
    response = client.post("/api/profile/bullet-bank/diff", json=edit)
    assert response.status_code == 200
    body = response.json()
    assert "Worked on an edited invented tool" in body["diff"]

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1


def test_commit_bullet_bank_anade_un_bullet_nuevo(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _bullet_bank_edit()
    edit["bullets"].append(
        {
            "bullet_id": "invented_bullet_three",
            "text_en": "Worked on a bullet added by HTTP.",
            "evidence_status": "candidate",
            "cv_usage": "blocked",
        }
    )
    response = client.post("/api/profile/bullet-bank/commit", json=edit)
    assert response.status_code == 201
    body = response.json()
    assert body["commit_sha"]

    log = _git(bare_remote, "log", "-1", "--format=%H %an <%ae> %s", "dev")
    assert body["commit_sha"] in log.stdout
    assert "Futuro App <bot@futuro.local>" in log.stdout

    again = client.get("/api/profile/bullet-bank").json()
    assert len(again["bullets"]) == 3


def test_commit_bullet_bank_rechaza_un_verbo_bloqueado_sin_tocar_el_remoto(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _bullet_bank_edit()
    edit["bullets"][0]["text_en"] = "Contributed to and owned the invented tool."
    response = client.post("/api/profile/bullet-bank/commit", json=edit)
    assert response.status_code == 422

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1


def test_profile_role_variants_closed_without_a_session(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote, dev_auth_bypass=False)
    response = client.get("/api/profile/role-variants")
    assert response.status_code == 401


def test_get_role_variants_clona_y_devuelve_lo_vigente(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    response = client.get("/api/profile/role-variants")
    assert response.status_code == 200
    body = response.json()
    assert set(body["variants"]) == {"invented_variant_one", "invented_variant_two"}


def test_commit_role_variants_edita_el_perfil_de_una_variante(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _role_variants_edit()
    edit["variants"]["invented_variant_one"]["profile"] = "Perfil editado por HTTP."
    response = client.post("/api/profile/role-variants/commit", json=edit)
    assert response.status_code == 201
    body = response.json()
    assert body["commit_sha"]

    log = _git(bare_remote, "log", "-1", "--format=%H %an <%ae> %s", "dev")
    assert body["commit_sha"] in log.stdout
    assert "Futuro App <bot@futuro.local>" in log.stdout

    again = client.get("/api/profile/role-variants").json()
    assert again["variants"]["invented_variant_one"]["profile"] == (
        "Perfil editado por HTTP."
    )


def test_commit_role_variants_rechaza_una_clave_desconocida(
    tmp_path: Path, bare_remote: Path
) -> None:
    client = _client(tmp_path, bare_remote)
    edit = _role_variants_edit()
    edit["variants"]["a_new_variant"] = edit["variants"]["invented_variant_one"]
    response = client.post("/api/profile/role-variants/commit", json=edit)
    assert response.status_code == 422

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1
