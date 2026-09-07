"""El mecanismo de escritura en el repositorio privado, y solo el mecanismo.

Nada de aquí sabe qué es `config/objectives.yaml` ni ningún otro fichero:
solo clonar una vez, `pull --rebase`, `commit` con una autoría dada y
`push`, y cómo fallar sin forzar nada cuando hay un conflicto. Fase 2 lo
reutiliza sin cambiar una línea en M1-M4; lo que cambia por fichero vive en
un módulo propio (`objectives.py` es el primero).

Tres decisiones que no son accidentales:

**El clon lo hace la propia app, no un paso de deploy.** A diferencia del
clon de solo lectura de M3 -que refresca CI por `rsync` en cada deploy-,
este vive fuera del control de CI: `ensure_clone` clona una vez si el
directorio no es todavía un repositorio git, y no hace nada si ya lo es.
El deploy nunca lo toca.

**Cada invocación de `git` lleva su propio `-c safe.directory=*`, y nada de
`HOME` ni configuración global.** El directorio de trabajo es un volumen
montado desde el host, con el dueño del host y no el `uid` del contenedor;
sin esto, git moderno se niega a operar ("detected dubious ownership").
Acotarlo a `*` por invocación -no en un `.gitconfig` global- es tan seguro
como acotarlo al path exacto, porque cada llamada ya fija con `-C` cuál es
el único repositorio sobre el que opera.

**Un conflicto aborta y no fuerza nada.** Ni en el `pull --rebase` ni en el
`push`: la disciplina que pide `ARCHITECTURE.md` §5. El único intento de
recuperarse solo es un reintento de `push` tras un `pull --rebase` fresco,
para el caso más común -una carrera con otra escritura, no un choque de
contenido de verdad-.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


class GitOpsError(Exception):
    """Un fallo de git que no es un conflicto de contenido: remoto
    inalcanzable, clave rechazada, disco lleno."""


class GitConflictError(Exception):
    """`pull --rebase` o `push` chocaron. No se ha forzado nada."""

    def __init__(self, message: str, *, detail: str) -> None:
        super().__init__(message)
        self.detail = detail


@dataclass(frozen=True)
class GitRemote:
    """Cómo llegar al remoto: URL, rama, y la clave SSH si hace falta.

    `ssh_key_path` vacío significa que no hace falta -el remoto es un
    `file://` local, como en desarrollo- y entonces no se fija
    `GIT_SSH_COMMAND`: dejar que git use su configuración por omisión.
    """

    url: str
    branch: str
    ssh_key_path: str = ""
    known_hosts_path: str = ""

    def env(self) -> dict[str, str] | None:
        if not self.ssh_key_path:
            return None
        command = [
            "ssh",
            "-i",
            self.ssh_key_path,
            "-o",
            "IdentitiesOnly=yes",
            # Rechazar y no preguntar: sin esto, una huella que no
            # coincidiera con `known_hosts_path` se quedaría esperando una
            # confirmación interactiva que nunca llega.
            "-o",
            "StrictHostKeyChecking=yes",
        ]
        if self.known_hosts_path:
            command += ["-o", f"UserKnownHostsFile={self.known_hosts_path}"]
        return {"GIT_SSH_COMMAND": " ".join(command)}


def _run(
    path: Path | None, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    command = ["git"]
    if path is not None:
        command += ["-C", str(path), "-c", "safe.directory=*"]
    command += list(args)
    full_env = {**os.environ, **env} if env else None
    return subprocess.run(command, capture_output=True, text=True, env=full_env)


def ensure_clone(path: Path, remote: GitRemote) -> None:
    """Clona una vez. Si `path` ya es un repositorio git, no hace nada."""
    if (path / ".git").is_dir():
        return
    path.mkdir(parents=True, exist_ok=True)
    result = _run(
        None,
        "clone",
        "--branch",
        remote.branch,
        "--origin",
        "origin",
        remote.url,
        str(path),
        env=remote.env(),
    )
    if result.returncode != 0:
        raise GitOpsError(f"no se pudo clonar «{remote.url}»: {result.stderr}")


def pull_rebase(
    path: Path, remote: GitRemote, *, author_name: str, author_email: str
) -> None:
    """`git pull --rebase`. Si choca, aborta el rebase y no fuerza nada.

    Rebasar reescribe el committer de cada commit que se reproduce encima
    -aunque no toque su contenido ni a su autoría original-, así que hace
    falta una identidad aquí igual que en `commit_and_push`, o git se niega
    con «please tell me who you are» en cuanto haya algo que reproducir.
    """
    result = _run(
        path,
        "-c",
        f"user.name={author_name}",
        "-c",
        f"user.email={author_email}",
        "pull",
        "--rebase",
        "origin",
        remote.branch,
        env=remote.env(),
    )
    if result.returncode != 0:
        _run(path, "rebase", "--abort")
        raise GitConflictError(
            f"conflicto al traer «{remote.branch}»", detail=result.stderr
        )


def commit_and_push(
    path: Path,
    remote: GitRemote,
    files: Sequence[str],
    *,
    message: str,
    author_name: str,
    author_email: str,
) -> str:
    """Añade los ficheros dados, commitea con la autoría dada y empuja.

    `files` son rutas relativas a `path` -nunca `git add -A`-, porque este
    clon es de la app y solo debe llevar lo que esta escritura tocó, no lo
    que otra escritura a medias pudiera haber dejado.

    Si el `push` choca, se reintenta una vez con un `pull --rebase` fresco:
    es el caso de una carrera con otra escritura -tu propio caso real, con
    el checkout de tu portátil escribiendo al mismo remoto-. Si el segundo
    intento también choca, es un conflicto de contenido de verdad y se
    propaga sin forzar nada.

    Si `files` no cambió nada de verdad -confirmar sin haber tocado ningún
    campo, o pulsar el botón dos veces- no es un error: es que el
    repositorio ya refleja lo que se pedía. Se detecta antes de intentar el
    commit y se devuelve el `HEAD` actual, en vez de dejar que `git commit`
    falle con "nothing to commit" y eso suba como un 500.

    Devuelve el sha del commit -el nuevo, o el que ya había si no hizo
    falta ninguno-.
    """
    add = _run(path, "add", "--", *files)
    if add.returncode != 0:
        raise GitOpsError(f"no se pudo preparar el commit: {add.stderr}")

    staged = _run(path, "diff", "--cached", "--quiet", "--", *files)
    if staged.returncode == 0:
        sha = _run(path, "rev-parse", "HEAD")
        return sha.stdout.strip()

    commit = _run(
        path,
        "-c",
        f"user.name={author_name}",
        "-c",
        f"user.email={author_email}",
        "commit",
        "-m",
        message,
    )
    if commit.returncode != 0:
        raise GitOpsError(f"no se pudo commitear: {commit.stderr}")

    push = _run(path, "push", "origin", f"HEAD:{remote.branch}", env=remote.env())
    if push.returncode != 0:
        pull_rebase(path, remote, author_name=author_name, author_email=author_email)
        push = _run(path, "push", "origin", f"HEAD:{remote.branch}", env=remote.env())
        if push.returncode != 0:
            raise GitConflictError(
                f"conflicto al empujar a «{remote.branch}»", detail=push.stderr
            )

    sha = _run(path, "rev-parse", "HEAD")
    return sha.stdout.strip()
