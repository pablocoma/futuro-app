"""Las tareas que corre el worker.

Dos: extraer una oferta y puntuarla. La primera es la que justificó la cola
—una llamada al modelo tarda entre cinco y treinta segundos y nadie debe
esperar eso con una petición HTTP abierta— y la segunda es la que justifica
que `job_runs` y `llm_calls` sean dos tablas, porque hace dos llamadas.

El reparto con la cola es el mismo para las dos: arq decide *cuándo* se
reintenta, y la tarea decide *si* tiene sentido reintentar. Un rechazo del
modelo, una respuesta que incumple el contrato o un repositorio de datos
que no está darán lo mismo en el segundo intento, así que se marcan
fallidos y no se relanzan; un fallo de red sí se relanza.

Las dos comparten la envoltura de estados (`_run_job`), que es lo que
garantiza que un trabajo nuevo no se olvide de marcar `running`, de contar
los intentos o de distinguir un fallo permanente de uno transitorio.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from futuro_api import data_repo
from futuro_api.assessment import brief as assessment_brief
from futuro_api.assessment import calls, scoring
from futuro_api.assessment import prompt as assessment_prompt
from futuro_api.assessment import repository as assessment_repo
from futuro_api.assessment import rules as assessment_rules
from futuro_api.assessment import vocabularies as assessment_vocab
from futuro_api.config import Settings
from futuro_api.jobs import queue as job_queue
from futuro_api.jobs import repository as jobs_repo
from futuro_api.llm import LlmClient, LlmError, LlmRefusal
from futuro_api.models import JobRun, OfferCapture
from futuro_api.offers import extraction, prompt, rules
from futuro_api.offers import repository as offers_repo

logger = logging.getLogger(__name__)

# Intentos totales, contando el primero. Tres porque los fallos que merecen
# reintento son transitorios —un 429, un corte de red— y si tres seguidos
# fallan, el problema no se arregla esperando.
MAX_ATTEMPTS = 3

# Un trabajo que lleva esto sin acabar se da por perdido. Generoso frente a
# los dos minutos de espera del modelo por intento: lo que se busca cazar es
# un trabajo que se esfumó, no uno lento.
STALE_AFTER = timedelta(minutes=15)


class PermanentFailure(Exception):
    """Un fallo que reintentar no arregla."""


async def _run_job(
    ctx: dict[str, Any],
    job_run_id: str,
    *,
    label: str,
    body: Callable[[uuid.UUID, uuid.UUID], Awaitable[None]],
) -> None:
    """La envoltura de estados de cualquier trabajo sobre una captura.

    Recibe el identificador de la fila de `job_runs` y no el de la captura,
    porque la fila se crea antes de encolar: así, si el encolado falla,
    queda el rastro de un trabajo que nunca arrancó en vez de nada.

    Está extraída de la tarea de extracción de M1 sin cambiarle nada
    cuando llegó la segunda tarea. Lo que centraliza no es código bonito:
    es marcar `running`, contar los intentos, y —lo que más importa—
    distinguir un fallo permanente de uno transitorio. Un tercer tipo de
    trabajo que se escribiera desde cero se olvidaría de alguna de las
    tres, y el síntoma sería una fila en `running` para siempre.
    """
    sessions: async_sessionmaker[AsyncSession] = ctx["sessions"]
    run_id = uuid.UUID(job_run_id)
    attempt = int(ctx.get("job_try", 1))

    async with sessions() as session:
        run = await session.get(JobRun, run_id)
        if run is None:
            # Puede pasar si alguien borró la captura mientras el trabajo
            # esperaba en la cola: la fila se fue en cascada. No es un error
            # que merezca reintento.
            logger.warning("el trabajo %s ya no existe; se ignora", run_id)
            return
        if run.capture_id is None:
            await jobs_repo.mark_failed(
                session, run_id, error="el trabajo no apunta a ninguna captura"
            )
            await session.commit()
            return
        capture_id = run.capture_id
        await jobs_repo.mark_running(session, run_id, attempt=attempt)
        await session.commit()

    try:
        await body(run_id, capture_id)
    except PermanentFailure as failure:
        async with sessions() as session:
            await jobs_repo.mark_failed(
                session, run_id, error=jobs_repo.describe_error(failure)
            )
            await session.commit()
        # No se relanza: arq reintentaría algo que va a fallar igual.
        logger.warning("%s %s fallida sin reintento: %s", label, run_id, failure)
        return
    except Exception as error:
        async with sessions() as session:
            if attempt >= MAX_ATTEMPTS:
                await jobs_repo.mark_failed(
                    session, run_id, error=jobs_repo.describe_error(error)
                )
            else:
                await jobs_repo.mark_requeued(
                    session, run_id, error=jobs_repo.describe_error(error)
                )
            await session.commit()
        if attempt >= MAX_ATTEMPTS:
            logger.error("%s %s agotó los intentos: %s", label, run_id, error)
            return
        # Se relanza para que arq lo reintente con su espera.
        raise

    async with sessions() as session:
        await jobs_repo.mark_succeeded(session, run_id)
        await session.commit()


async def extract_offer(ctx: dict[str, Any], job_run_id: str) -> None:
    """Extrae una oferta ya capturada y guarda el resultado."""
    sessions: async_sessionmaker[AsyncSession] = ctx["sessions"]
    client: LlmClient = ctx["llm"]

    async def body(run_id: uuid.UUID, capture_id: uuid.UUID) -> None:
        await _run_extraction(sessions, client, run_id=run_id, capture_id=capture_id)
        # La puntuación se encadena aquí y no la pide nadie desde fuera: es
        # lo que hace que el recorrido siga siendo de punta a punta —pegar,
        # extraer, puntuar, ver— sin un botón intermedio. Si el encolado
        # falla, la extracción **no** se cae: se queda sin puntuar, la
        # pantalla lo dice y el botón de repuntuar sigue ahí. Perder la
        # extracción por no haber podido encolar lo siguiente sería tirar
        # una llamada ya pagada.
        await _chain_assessment(ctx, capture_id)

    await _run_job(ctx, job_run_id, label="extracción", body=body)


async def assess_offer(ctx: dict[str, Any], job_run_id: str) -> None:
    """Puntúa una oferta ya extraída y elige su variante de CV.

    Un solo trabajo con **dos** llamadas al modelo, y una sola transacción
    que guarda las dos cosas. Es el trabajo que `docs/decisions` de M1
    anticipó al separar `job_runs` de `llm_calls`.

    Atómico a propósito: si la elección de variante no se sostiene, no se
    guarda tampoco el assessment. Guardar medio resultado dejaría una
    oferta puntuada y sin variante que nadie distinguiría de una a la que
    todavía le falta la variante, y el trabajo aparecería como fallido
    habiendo escrito algo. Cuesta las dos llamadas, que es el mismo precio
    que M1 aceptó al rechazar una extracción entera.
    """
    sessions: async_sessionmaker[AsyncSession] = ctx["sessions"]
    client: LlmClient = ctx["llm"]
    settings: Settings = ctx["settings"]

    async def body(run_id: uuid.UUID, capture_id: uuid.UUID) -> None:
        await _run_assessment(
            sessions, client, settings, run_id=run_id, capture_id=capture_id
        )

    await _run_job(ctx, job_run_id, label="puntuación", body=body)


async def _chain_assessment(ctx: dict[str, Any], capture_id: uuid.UUID) -> None:
    """Encola la puntuación de una oferta recién extraída, si se puede."""
    queue: ArqRedis | None = ctx.get("redis")
    sessions: async_sessionmaker[AsyncSession] = ctx["sessions"]
    if queue is None:  # pragma: no cover - arq siempre lo pone
        logger.warning("sin cola en el contexto: la oferta se queda sin puntuar")
        return
    try:
        async with sessions() as session:
            await job_queue.enqueue_assessment(queue, session, capture_id)
    except Exception:
        logger.exception(
            "no se pudo encolar la puntuación de %s; la extracción se conserva",
            capture_id,
        )


async def _run_assessment(
    sessions: async_sessionmaker[AsyncSession],
    client: LlmClient,
    settings: Settings,
    *,
    run_id: uuid.UUID,
    capture_id: uuid.UUID,
) -> None:
    """Carga el repositorio de datos, llama dos veces, valida y guarda.

    El repositorio de datos se carga **antes** de llamar al modelo. No es
    casual: sin él no hay modelo de scoring que meter en el prompt, y
    descubrirlo después de pagar dos llamadas sería tirar el dinero por una
    comprobación que cuesta leer seis ficheros.
    """
    root = settings.data_repo_root
    if root is None:
        raise PermanentFailure(
            "no hay repositorio de datos configurado (DATA_REPO_PATH), así que "
            "no hay modelo de scoring con el que puntuar"
        )
    try:
        repo = data_repo.load(root)
    except data_repo.DataRepoError as error:
        # Reintentar no arregla un YAML mal formado ni un directorio que no
        # está: es permanente hasta que alguien lo toque.
        raise PermanentFailure(str(error)) from error

    async with sessions() as session:
        extraction = await offers_repo.current_extraction(session, capture_id)
        if extraction is None:
            raise PermanentFailure(
                f"la oferta {capture_id} no tiene ninguna extracción vigente que "
                "puntuar"
            )
        capture = await session.get(OfferCapture, extraction.capture_id)
        if capture is None:  # pragma: no cover - la FK lo impide
            raise PermanentFailure(f"la captura {capture_id} ya no existe")
        raw_text = capture.raw_text
        extraction_id = extraction.id
        brief = assessment_brief.brief_of(extraction)
        requirement_ids = {
            requirement.position: requirement.id
            for requirement in extraction.requirements
        }

    try:
        scoring_result = await calls.score(client, repo, brief, raw_text)
        variant_result = await calls.choose_variant(client, repo, brief, raw_text)
    except LlmRefusal as refusal:
        raise PermanentFailure(str(refusal)) from refusal
    except LlmError:
        raise

    # El coste se registra antes de validar y en su propia transacción, por
    # lo mismo que en M1: las llamadas ya están pagadas, y si la validación
    # rechaza el resultado el gasto tiene que constar igual.
    async with sessions() as session:
        await jobs_repo.record_llm_call(
            session,
            run_id=run_id,
            purpose=calls.SCORING_PURPOSE,
            prompt_version=assessment_prompt.SCORING_PROMPT_VERSION,
            result=scoring_result,
        )
        await jobs_repo.record_llm_call(
            session,
            run_id=run_id,
            purpose=calls.VARIANT_PURPOSE,
            prompt_version=assessment_prompt.VARIANT_PROMPT_VERSION,
            result=variant_result,
        )
        await session.commit()

    try:
        validated = assessment_rules.validate_scoring(
            scoring_result.parsed,
            repo=repo,
            raw_text=raw_text,
            requirement_positions=tuple(requirement_ids),
        )
        variant = assessment_rules.validate_variant(
            variant_result.parsed, variants=repo.variants
        )
    except assessment_rules.AssessmentRejected as rejected:
        raise PermanentFailure(str(rejected)) from rejected

    computed = scoring.compute(
        repo.scoring,
        dimensions=validated.dimensions,
        gates=validated.gates,
        band=validated.probability_band,
        role_family=brief.role_family,
        core_role_families=repo.core_role_families,
    )

    async with sessions() as session:
        await assessment_repo.save_assessment(
            session,
            extraction_id=extraction_id,
            job_run_id=run_id,
            source=assessment_vocab.AssessmentSource.LLM,
            derived_from_id=None,
            scoring_model_version=repo.scoring.version,
            scoring_model_sha256=repo.scoring.sha256,
            prompt_version=assessment_prompt.SCORING_PROMPT_VERSION,
            model=scoring_result.model,
            validated=validated,
            computed=computed,
            requirement_ids=requirement_ids,
        )
        await assessment_repo.save_variant_recommendation(
            session,
            extraction_id=extraction_id,
            job_run_id=run_id,
            validated=variant,
            variants_guide_sha256=repo.variants.guide_sha256,
            prompt_version=assessment_prompt.VARIANT_PROMPT_VERSION,
            model=variant_result.model,
        )
        await session.commit()


async def _run_extraction(
    sessions: async_sessionmaker[AsyncSession],
    client: LlmClient,
    *,
    run_id: uuid.UUID,
    capture_id: uuid.UUID,
) -> None:
    """Llama al modelo, valida y guarda.

    La llamada se hace **fuera** de la transacción que guarda: una petición
    de treinta segundos con una transacción abierta bloquearía filas todo
    ese rato por nada.
    """
    async with sessions() as session:
        capture = await session.get(OfferCapture, capture_id)
        if capture is None:
            raise PermanentFailure(f"la captura {capture_id} ya no existe")
        raw_text = capture.raw_text

    try:
        result = await extraction.extract(client, raw_text)
    except LlmRefusal as refusal:
        # El modelo se negó. Reintentar da lo mismo, así que es permanente.
        raise PermanentFailure(str(refusal)) from refusal
    except LlmError:
        # Fallo de la llamada: sí merece reintento, así que sube tal cual.
        raise

    # El coste se registra antes de validar: la llamada ya está pagada, y si
    # la validación rechaza la extracción el gasto tiene que constar igual.
    async with sessions() as session:
        await jobs_repo.record_llm_call(
            session,
            run_id=run_id,
            purpose=extraction.PURPOSE,
            prompt_version=prompt.PROMPT_VERSION,
            result=result,
        )
        await session.commit()

    try:
        validated = rules.validate(result.parsed, raw_text)
    except rules.ExtractionRejected as rejected:
        raise PermanentFailure(str(rejected)) from rejected

    async with sessions() as session:
        await offers_repo.save_extraction(
            session,
            capture_id=capture_id,
            job_run_id=run_id,
            prompt_version=prompt.PROMPT_VERSION,
            model=result.model,
            validated=validated,
        )
        await session.commit()


async def sweep_stale_runs(ctx: dict[str, Any]) -> int:
    """Da por perdidos los trabajos que se quedaron a medias.

    Corre periódicamente porque un trabajo puede desaparecer sin dejar
    rastro: si Redis se reinicia, la cola se vacía y la fila se queda en
    `queued` para siempre. Sin esto, la pantalla diría «en cola» de por vida.
    """
    sessions: async_sessionmaker[AsyncSession] = ctx["sessions"]
    async with sessions() as session:
        lost = await jobs_repo.fail_stale_runs(session, older_than=STALE_AFTER)
        await session.commit()
    if lost:
        logger.warning("%d trabajos dados por perdidos", len(lost))
    return len(lost)
