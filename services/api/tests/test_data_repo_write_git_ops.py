"""`git_ops.py` contra un remoto de git real -un repo bare local-, sin tocar
GitHub ni el repositorio privado. Es lo único de este mecanismo que
necesita un `push` que valga: un árbol de ficheros sueltos no basta para
probar una carrera ni un conflicto.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from futuro_api.data_repo_write import git_ops
from futuro_api.data_repo_write.git_ops import GitConflictError, GitRemote
from tests.conftest import DATA_REPO_WRITE_SEED, seed_bare_repo


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    return seed_bare_repo(tmp_path, DATA_REPO_WRITE_SEED)


def _remote(bare: Path) -> GitRemote:
    # Sin `ssh_key_path`: un remoto local no necesita `GIT_SSH_COMMAND`.
    return GitRemote(url=str(bare), branch="dev")


async def test_ensure_clone_clona_una_vez(tmp_path: Path, bare_remote: Path) -> None:
    work = tmp_path / "work"
    remote = _remote(bare_remote)

    await git_ops.ensure_clone(work, remote)
    assert (work / "config" / "objectives.yaml").is_file()
    assert (work / "config" / "objectives.yaml").read_text() == (
        DATA_REPO_WRITE_SEED / "config" / "objectives.yaml"
    ).read_text()

    # Segunda llamada: el directorio ya es un repo git, no hace nada.
    (work / "config" / "objectives.yaml").write_text("cambiado a mano\n")
    await git_ops.ensure_clone(work, remote)
    assert (work / "config" / "objectives.yaml").read_text() == "cambiado a mano\n"


async def test_pull_rebase_sin_cambios_remotos_no_hace_nada_raro(
    tmp_path: Path, bare_remote: Path
) -> None:
    work = tmp_path / "work"
    remote = _remote(bare_remote)
    await git_ops.ensure_clone(work, remote)

    await git_ops.pull_rebase(
        work, remote, author_name="Futuro App", author_email="bot@futuro.local"
    )  # no debe lanzar


async def test_commit_and_push_avanza_el_remoto_con_la_autoria_dada(
    tmp_path: Path, bare_remote: Path
) -> None:
    work = tmp_path / "work"
    remote = _remote(bare_remote)
    await git_ops.ensure_clone(work, remote)

    (work / "config" / "objectives.yaml").write_text("version: 2\n")
    sha = await git_ops.commit_and_push(
        work,
        remote,
        ["config/objectives.yaml"],
        message="version 2",
        author_name="Futuro App",
        author_email="bot@futuro.local",
    )

    log = _git(bare_remote, "log", "-1", "--format=%H %an <%ae>", "dev")
    assert sha in log.stdout
    assert "Futuro App <bot@futuro.local>" in log.stdout


async def test_commit_and_push_reintenta_tras_una_carrera_sin_conflicto_de_verdad(
    tmp_path: Path, bare_remote: Path
) -> None:
    """Dos clones -como tu portátil y la app- escribiendo al mismo remoto en
    ficheros distintos: el segundo se encuentra el remoto movido, reintenta
    un `pull --rebase`, y como no hay choque de contenido, el push acaba
    entrando.
    """
    remote = _remote(bare_remote)

    work_a = tmp_path / "work_a"
    await git_ops.ensure_clone(work_a, remote)
    work_b = tmp_path / "work_b"
    await git_ops.ensure_clone(work_b, remote)

    (work_a / "config" / "objectives.yaml").write_text("version: 2\n")
    await git_ops.commit_and_push(
        work_a,
        remote,
        ["config/objectives.yaml"],
        message="a",
        author_name="A",
        author_email="a@test",
    )

    # B no ha visto el cambio de A: escribe un fichero distinto.
    (work_b / "otro.yaml").write_text("x: 1\n")
    sha_b = await git_ops.commit_and_push(
        work_b,
        remote,
        ["otro.yaml"],
        message="b",
        author_name="B",
        author_email="b@test",
    )

    log = _git(bare_remote, "log", "--format=%H", "dev")
    shas = log.stdout.split()
    assert sha_b in shas
    assert len(shas) == 3  # seed + a + b


async def test_commit_and_push_no_fuerza_un_conflicto_de_verdad(
    tmp_path: Path, bare_remote: Path
) -> None:
    remote = _remote(bare_remote)

    work_a = tmp_path / "work_a"
    await git_ops.ensure_clone(work_a, remote)
    work_b = tmp_path / "work_b"
    await git_ops.ensure_clone(work_b, remote)

    (work_a / "config" / "objectives.yaml").write_text("version: 2\n")
    await git_ops.commit_and_push(
        work_a,
        remote,
        ["config/objectives.yaml"],
        message="a",
        author_name="A",
        author_email="a@test",
    )

    # B edita la misma línea sin haber visto el cambio de A: choque real.
    (work_b / "config" / "objectives.yaml").write_text("version: 3\n")
    with pytest.raises(GitConflictError):
        await git_ops.commit_and_push(
            work_b,
            remote,
            ["config/objectives.yaml"],
            message="b",
            author_name="B",
            author_email="b@test",
        )

    # Sin rebase a medias: el intento de recuperarse aborta limpio.
    assert not (work_b / ".git" / "rebase-merge").exists()
    assert not (work_b / ".git" / "rebase-apply").exists()
    # Y el commit de B sigue ahí, local y sin perder: solo no se ha podido
    # sincronizar, que es justo lo que "no forzar nada" quiere decir.
    log = _git(work_b, "log", "-1", "--format=%s")
    assert log.stdout.strip() == "b"


async def test_commit_and_push_sin_cambios_no_falla_y_devuelve_el_head_actual(
    tmp_path: Path, bare_remote: Path
) -> None:
    """Confirmar sin haber tocado nada -o pulsar el botón dos veces- no es
    un error: es que el repositorio ya refleja lo que se pedía. Antes de
    esta comprobación, `git commit` fallaba con "nothing to commit" y eso
    subía como un `GitOpsError`; se descubrió con un 500 real en pantalla.
    """
    work = tmp_path / "work"
    remote = _remote(bare_remote)
    await git_ops.ensure_clone(work, remote)

    before = _git(work, "rev-parse", "HEAD").stdout.strip()
    sha = await git_ops.commit_and_push(
        work,
        remote,
        ["config/objectives.yaml"],
        message="sin cambios",
        author_name="Futuro App",
        author_email="bot@futuro.local",
    )

    assert sha == before
    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 1  # nada nuevo llegó al remoto


async def test_concurrent_requests_on_the_same_clone_do_not_corrupt_git(
    tmp_path: Path, bare_remote: Path
) -> None:
    """El bug real que arregló el lock, y no un choque de contenido.

    `router.py` sostiene `git_ops.lock_for(root)` desde `pull_rebase` hasta
    `commit_and_push` -incluida la escritura en disco de en medio, que vive
    en otro módulo-. Sin ese lock, dos peticiones a `/perfil` corriendo de
    verdad al mismo tiempo -algo que `asyncio.to_thread` por sí solo hace
    posible- encontraban "fatal: Cannot rebase onto multiple branches" sin
    que ningún contenido hubiera chocado nunca: es como se descubrió,
    arreglando primero el bloqueo del *event loop* y viendo la CI seguir en
    rojo por esto. Cada tarea toca un fichero distinto -sin ninguna carrera
    de contenido de por medio, que es un problema aparte y ya aceptado
    (ver `docs/decisions/fase-2-perfil-editable.md`)-, así que si el lock
    funciona, las diez entran; si no, `asyncio.gather` propaga la primera
    excepción de git.
    """
    work = tmp_path / "work"
    remote = _remote(bare_remote)
    await git_ops.ensure_clone(work, remote)

    async def one_request(marker: str) -> None:
        async with git_ops.lock_for(work):
            await git_ops.pull_rebase(
                work,
                remote,
                author_name="Futuro App",
                author_email="bot@futuro.local",
            )
            (work / f"{marker}.yaml").write_text(f"{marker}: true\n")
            await git_ops.commit_and_push(
                work,
                remote,
                [f"{marker}.yaml"],
                message=f"añadir {marker}",
                author_name="Futuro App",
                author_email="bot@futuro.local",
            )

    await asyncio.gather(*(one_request(f"marker_{i}") for i in range(10)))

    log = _git(bare_remote, "log", "--format=%H", "dev")
    assert len(log.stdout.split()) == 11  # la semilla + los diez commits
