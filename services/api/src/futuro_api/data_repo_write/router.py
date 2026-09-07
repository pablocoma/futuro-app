"""Los endpoints del perfil editable, Fase 2.

`config/objectives.yaml` es el primero -M0-. Los tres endpoints comparten
el mismo patrón: clonar si hace falta, `pull --rebase` **siempre**, y
recién entonces cargar y actuar. Ni `GET` se salta el `pull`: aunque
`ARCHITECTURE.md` §5 solo lo exige "antes de escribir", enseñar el
formulario con datos que ya están desactualizados es la manera más segura
de acabar chocando en el `commit`, y `pull --rebase` es barato al lado de
la llamada al LLM que sí espera esta misma app en otras pantallas.

`diff` y `commit` recalculan los dos desde cero -pull, carga, aplica,
valida- en vez de que `diff` deje algo pendiente para que `commit`
reutilice: nada expira, nada se queda a medias si se cierra la pestaña
entre ver el diff y confirmar.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Body, HTTPException, Request, status
from pydantic import BaseModel

from futuro_api.config import Settings
from futuro_api.data_repo_write import constraints, git_ops, objectives, preferences
from futuro_api.data_repo_write.git_ops import GitRemote
from futuro_api.data_repo_write.models import (
    Constraints,
    EditableConstraints,
    EditableObjectives,
    EditablePreferences,
    Objectives,
    Preferences,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])

# La autoría fija de toda escritura de esta app, decidida en
# `ARCHITECTURE.md` §5. No hay ningún camino en el que un commit de este
# mecanismo lleve otra.
AUTHOR_NAME = "Futuro App"
AUTHOR_EMAIL = "bot@futuro.local"


def _configured(request: Request) -> tuple[Path, GitRemote]:
    """El clon y su remoto, o un 503 si el mecanismo no está montado.

    Mismo criterio que `data_repo._loaded_data_repo`: sin la deploy key ni
    el directorio aprovisionados en la VM, escribir falla con el motivo a
    la vista en vez de tumbar la aplicación entera por una función que
    todavía no puede funcionar.
    """
    settings = cast(Settings, request.app.state.settings)
    root = settings.data_repo_write_root
    remote = settings.data_repo_write_remote_config
    if root is None or remote is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "el mecanismo de escritura del perfil no está configurado "
                "(DATA_REPO_WRITE_PATH / DATA_REPO_WRITE_REMOTE)"
            ),
        )
    return root, remote


def _conflict(error: git_ops.GitConflictError) -> HTTPException:
    # El `stderr` de git va al log y no al cliente: es ruido técnico -rutas
    # del contenedor, el propio comando- y el `detail` de esta API es
    # siempre una cadena, el mismo contrato que el resto de `offers/router.py`.
    logging.getLogger(__name__).warning("conflicto en el perfil: %s", error.detail)
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


def _sync(root: Path, remote: GitRemote) -> None:
    try:
        git_ops.ensure_clone(root, remote)
        git_ops.pull_rebase(
            root, remote, author_name=AUTHOR_NAME, author_email=AUTHOR_EMAIL
        )
    except git_ops.GitConflictError as error:
        raise _conflict(error) from error
    except git_ops.GitOpsError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error


class ObjectivesDiffResponse(BaseModel):
    diff: str
    validated: Objectives


class ObjectivesCommitResponse(BaseModel):
    commit_sha: str
    diff: str


@router.get("/objectives", summary="El objectives.yaml vigente")
async def get_objectives(request: Request) -> Objectives:
    root, remote = _configured(request)
    _sync(root, remote)
    return objectives.current(root)


@router.post(
    "/objectives/diff",
    summary="Calcula el diff de una edición, sin escribir nada",
)
async def diff_objectives(
    request: Request, edit: Annotated[EditableObjectives, Body()]
) -> ObjectivesDiffResponse:
    root, remote = _configured(request)
    _sync(root, remote)
    try:
        result = objectives.prepare(root, edit, today=date.today())
    except objectives.ObjectivesValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return ObjectivesDiffResponse(diff=result.unified_diff, validated=result.validated)


@router.post(
    "/objectives/commit",
    status_code=status.HTTP_201_CREATED,
    summary="Escribe, commitea y empuja una edición",
)
async def commit_objectives(
    request: Request, edit: Annotated[EditableObjectives, Body()]
) -> ObjectivesCommitResponse:
    root, remote = _configured(request)
    _sync(root, remote)
    try:
        result = objectives.write(root, edit, today=date.today())
    except objectives.ObjectivesValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error

    try:
        sha = git_ops.commit_and_push(
            root,
            remote,
            [objectives.RELATIVE_PATH],
            message="profile: actualizar config/objectives.yaml",
            author_name=AUTHOR_NAME,
            author_email=AUTHOR_EMAIL,
        )
    except git_ops.GitConflictError as error:
        raise _conflict(error) from error
    except git_ops.GitOpsError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error

    return ObjectivesCommitResponse(commit_sha=sha, diff=result.unified_diff)


class PreferencesDiffResponse(BaseModel):
    diff: str
    validated: Preferences


class PreferencesCommitResponse(BaseModel):
    commit_sha: str
    diff: str


@router.get("/preferences", summary="El preferences.yaml vigente")
async def get_preferences(request: Request) -> Preferences:
    root, remote = _configured(request)
    _sync(root, remote)
    return preferences.current(root)


@router.post(
    "/preferences/diff",
    summary="Calcula el diff de una edición, sin escribir nada",
)
async def diff_preferences(
    request: Request, edit: Annotated[EditablePreferences, Body()]
) -> PreferencesDiffResponse:
    root, remote = _configured(request)
    _sync(root, remote)
    try:
        result = preferences.prepare(root, edit, today=date.today())
    except preferences.PreferencesValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return PreferencesDiffResponse(diff=result.unified_diff, validated=result.validated)


@router.post(
    "/preferences/commit",
    status_code=status.HTTP_201_CREATED,
    summary="Escribe, commitea y empuja una edición",
)
async def commit_preferences(
    request: Request, edit: Annotated[EditablePreferences, Body()]
) -> PreferencesCommitResponse:
    root, remote = _configured(request)
    _sync(root, remote)
    try:
        result = preferences.write(root, edit, today=date.today())
    except preferences.PreferencesValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error

    try:
        sha = git_ops.commit_and_push(
            root,
            remote,
            [preferences.RELATIVE_PATH],
            message="profile: actualizar config/preferences.yaml",
            author_name=AUTHOR_NAME,
            author_email=AUTHOR_EMAIL,
        )
    except git_ops.GitConflictError as error:
        raise _conflict(error) from error
    except git_ops.GitOpsError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error

    return PreferencesCommitResponse(commit_sha=sha, diff=result.unified_diff)


class ConstraintsDiffResponse(BaseModel):
    diff: str
    validated: Constraints


class ConstraintsCommitResponse(BaseModel):
    commit_sha: str
    diff: str


@router.get("/constraints", summary="El constraints.yaml vigente")
async def get_constraints(request: Request) -> Constraints:
    root, remote = _configured(request)
    _sync(root, remote)
    return constraints.current(root)


@router.post(
    "/constraints/diff",
    summary="Calcula el diff de una edición, sin escribir nada",
)
async def diff_constraints(
    request: Request, edit: Annotated[EditableConstraints, Body()]
) -> ConstraintsDiffResponse:
    root, remote = _configured(request)
    _sync(root, remote)
    try:
        result = constraints.prepare(root, edit, today=date.today())
    except constraints.ConstraintsValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return ConstraintsDiffResponse(diff=result.unified_diff, validated=result.validated)


@router.post(
    "/constraints/commit",
    status_code=status.HTTP_201_CREATED,
    summary="Escribe, commitea y empuja una edición",
)
async def commit_constraints(
    request: Request, edit: Annotated[EditableConstraints, Body()]
) -> ConstraintsCommitResponse:
    root, remote = _configured(request)
    _sync(root, remote)
    try:
        result = constraints.write(root, edit, today=date.today())
    except constraints.ConstraintsValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error

    try:
        sha = git_ops.commit_and_push(
            root,
            remote,
            [constraints.RELATIVE_PATH],
            message="profile: actualizar config/constraints.yaml",
            author_name=AUTHOR_NAME,
            author_email=AUTHOR_EMAIL,
        )
    except git_ops.GitConflictError as error:
        raise _conflict(error) from error
    except git_ops.GitOpsError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error

    return ConstraintsCommitResponse(commit_sha=sha, diff=result.unified_diff)
