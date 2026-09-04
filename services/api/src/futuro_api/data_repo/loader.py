"""Lee el repositorio privado desde un directorio, y solo lee.

Esta es la frontera con el repositorio privado `Futuro`, y es lo único que
M2 necesita de él. Detrás de esta frontera hay hoy un *bind mount* de solo
lectura y en M3 habrá un clon de git; el código de arriba no distingue una
cosa de la otra, porque lo único que sabe es que hay un directorio.

Tres propiedades que no son accidentales:

**Falla cerrado.** Sin directorio, o con un YAML que no cumple la forma, no
se puntúa: se lanza `DataRepoError` y el trabajo queda `failed` con el
motivo. No hay ningún camino en el que se puntúe con pesos por defecto,
porque no hay pesos por defecto.

**Comprueba lo que el código no puede dejar de dar por supuesto.** Los
nombres de dimensiones, de filtros y de variantes son libres: el código los
transporta. Las bandas, los cubos y los niveles de esfuerzo no lo son,
porque el código ramifica sobre ellos para calcular; si el YAML los
renombra, se dice aquí y no se puntúa mal en silencio. Lo mismo con la
escala 0-5, que está escrita en un CHECK de la base de datos.

**No cachea.** Se releen los ficheros en cada trabajo. Son seis YAML
pequeños al lado de una llamada al modelo que tarda segundos, y en local
tiene la propiedad que se quiere: editas un peso y el siguiente trabajo ya
lo usa.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from futuro_api.data_repo import vocabularies as vocab
from futuro_api.data_repo.models import (
    Bullet,
    DataRepo,
    Dimension,
    DisqualifyingCondition,
    Gate,
    ScoringModel,
    VariantGuide,
)

# Rutas relativas a la raíz del repositorio privado. En un solo sitio
# porque son la superficie de acoplamiento entera: si alguno se mueve allí,
# esto es lo que hay que cambiar aquí.
SCORING_MODEL = Path("config/scoring_model.yaml")
OBJECTIVES = Path("config/objectives.yaml")
CONSTRAINTS = Path("config/constraints.yaml")
CV_VARIANTS = Path("config/cv_variants.yaml")
BULLET_BANK = Path("cv/content/professional_bullet_bank.yaml")
VARIANTS_DIR = Path("cv/variants")
VARIANTS_GUIDE = VARIANTS_DIR / "README.md"

REQUIRED_FILES = (
    SCORING_MODEL,
    OBJECTIVES,
    CONSTRAINTS,
    CV_VARIANTS,
    BULLET_BANK,
    VARIANTS_GUIDE,
)

# La escala está en un CHECK de `offer_assessment_dimensions`, así que no
# puede cambiar desde un YAML sin una migración.
EXPECTED_SCORE_RANGE = (0, 5)

_yaml = YAML(typ="safe")


class DataRepoError(Exception):
    """El repositorio de datos no está, o no tiene la forma esperada."""


def _read(root: Path, relative: Path) -> tuple[Any, str]:
    """Carga un YAML y devuelve `(contenido, sha256 del fichero)`."""
    path = root / relative
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise DataRepoError(
            f"no se puede leer «{relative}» del repositorio de datos ({root}): {error}"
        ) from error
    try:
        loaded = _yaml.load(raw.decode())
    except (YAMLError, UnicodeDecodeError) as error:
        raise DataRepoError(f"«{relative}» no es un YAML válido: {error}") from error
    if not isinstance(loaded, dict):
        raise DataRepoError(f"«{relative}» debería ser un mapa en su raíz")
    return loaded, hashlib.sha256(raw).hexdigest()


def _require(source: Path, block: Any, key: str) -> Any:
    if not isinstance(block, dict) or key not in block:
        raise DataRepoError(f"«{source}» no declara «{key}»")
    return block[key]


def _text(value: Any) -> str:
    """Un valor del YAML como texto de una línea."""
    return " ".join(str(value).split())


def _mapping_of_text(block: Any, *, source: Path, key: str) -> dict[str, str]:
    if not isinstance(block, dict):
        raise DataRepoError(f"«{source}»: «{key}» debería ser un mapa")
    return {str(name): _text(value) for name, value in block.items()}


def _decimal(value: Any, *, source: Path, key: str) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise DataRepoError(f"«{source}»: «{key}» no es un número") from error


def _dimensions(data: dict[str, Any]) -> tuple[Dimension, ...]:
    """Las dimensiones, en el orden en que `weights` las declara.

    El orden importa porque es el de las barras de la pantalla, y el del
    YAML es el único que significa algo: reordenarlas alfabéticamente sería
    inventar una jerarquía que el modelo de scoring no tiene.
    """
    weights = _require(SCORING_MODEL, data, "weights")
    if not isinstance(weights, dict) or not weights:
        raise DataRepoError(f"«{SCORING_MODEL}»: «weights» está vacío")
    anchors_block = data.get("anchors") or {}
    if not isinstance(anchors_block, dict):
        raise DataRepoError(f"«{SCORING_MODEL}»: «anchors» debería ser un mapa")

    dimensions = []
    for name, weight in weights.items():
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            raise DataRepoError(
                f"«{SCORING_MODEL}»: el peso de «{name}» debería ser un entero "
                f"positivo, y es {weight!r}"
            )
        block = anchors_block.get(name) or {}
        if not isinstance(block, dict):
            raise DataRepoError(
                f"«{SCORING_MODEL}»: las anclas de «{name}» deberían ser un mapa"
            )
        anchors = {
            int(level): _text(text)
            for level, text in block.items()
            if isinstance(level, int) and not isinstance(level, bool)
        }
        notes = {
            str(label): _text(text)
            for label, text in block.items()
            if not isinstance(label, int) or isinstance(label, bool)
        }
        if not anchors:
            raise DataRepoError(
                f"«{SCORING_MODEL}»: «{name}» no tiene ninguna ancla escrita; "
                "sin anclas el modelo no tiene contra qué puntuar"
            )
        dimensions.append(
            Dimension(name=str(name), weight=weight, anchors=anchors, notes=notes)
        )
    return tuple(dimensions)


def _gates(data: dict[str, Any]) -> tuple[Gate, ...]:
    block = _require(SCORING_MODEL, data, "gates")
    if not isinstance(block, dict) or not block:
        raise DataRepoError(f"«{SCORING_MODEL}»: «gates» está vacío")
    gates = []
    for name, body in block.items():
        if not isinstance(body, dict):
            raise DataRepoError(
                f"«{SCORING_MODEL}»: el filtro «{name}» debería ser un mapa"
            )
        # `context` y `note` explican el filtro; el resto de claves dicen
        # cuándo vale qué. La distinción es del YAML y se respeta tal cual,
        # sin exigir un juego fijo de estados: `savings_floor` declara
        # `pass_spain` y `pass_abroad` en vez de un `pass` a secas.
        notes = {k: _text(v) for k, v in body.items() if k in ("context", "note")}
        criteria = {
            str(k): _text(v) for k, v in body.items() if k not in ("context", "note")
        }
        if not criteria:
            raise DataRepoError(
                f"«{SCORING_MODEL}»: el filtro «{name}» no dice cuándo se pasa "
                "ni cuándo se falla"
            )
        gates.append(Gate(name=str(name), criteria=criteria, notes=notes))
    return tuple(gates)


def _check_declared_names(
    declared: set[str], expected: type[StrEnum], *, key: str
) -> None:
    """Exige que el YAML declare exactamente los nombres del vocabulario.

    Es la red que sustituye al CHECK que estos tres vocabularios no pueden
    tener en el metadata. Se comprueba en las dos direcciones: un nombre
    que falta dejaría un cubo inalcanzable, y uno de más sería una regla que
    el código no sabe calcular y que nunca se asignaría.
    """
    known = {member.value for member in expected}
    missing = known - declared
    extra = declared - known
    if missing or extra:
        problems = []
        if missing:
            problems.append(f"faltan {sorted(missing)}")
        if extra:
            problems.append(f"sobran {sorted(extra)}")
        raise DataRepoError(
            f"«{SCORING_MODEL}»: «{key}» no coincide con lo que el código sabe "
            f"calcular ({', '.join(problems)}). El código ramifica sobre estos "
            "nombres, así que renombrarlos aquí no rompería una constraint: "
            "cambiaría el resultado en silencio. Si el modelo de scoring ha "
            "cambiado de verdad, hay que cambiar también "
            "futuro_api.assessment.scoring."
        )


def _scoring_model(root: Path) -> ScoringModel:
    data, sha256 = _read(root, SCORING_MODEL)

    scale = _require(SCORING_MODEL, data, "scale")
    span = _require(SCORING_MODEL, scale, "range")
    if not (isinstance(span, list) and len(span) == 2):
        raise DataRepoError(f"«{SCORING_MODEL}»: «scale.range» debería ser [min, max]")
    score_min, score_max = int(span[0]), int(span[1])
    if (score_min, score_max) != EXPECTED_SCORE_RANGE:
        raise DataRepoError(
            f"«{SCORING_MODEL}»: la escala es [{score_min}, {score_max}] y el "
            f"esquema espera {list(EXPECTED_SCORE_RANGE)}. La escala está en un "
            "CHECK de `offer_assessment_dimensions`, así que cambiarla exige "
            "una migración y no solo editar este YAML."
        )

    baseline_keys = [key for key in data if str(key).startswith("baseline_")]
    if len(baseline_keys) != 1:
        raise DataRepoError(
            f"«{SCORING_MODEL}»: se esperaba exactamente un bloque «baseline_*» "
            f"con la línea base económica, y hay {len(baseline_keys)}"
        )
    baseline_name = str(baseline_keys[0])
    baseline = data[baseline_name]
    if not isinstance(baseline, dict):
        raise DataRepoError(f"«{SCORING_MODEL}»: «{baseline_name}» debería ser un mapa")

    missing_data = _require(SCORING_MODEL, data, "missing_data")
    minimum_coverage = _decimal(
        _require(SCORING_MODEL, missing_data, "minimum_coverage"),
        source=SCORING_MODEL,
        key="missing_data.minimum_coverage",
    )
    if not Decimal(0) < minimum_coverage <= Decimal(1):
        raise DataRepoError(
            f"«{SCORING_MODEL}»: «missing_data.minimum_coverage» debería estar "
            f"entre 0 y 1, y es {minimum_coverage}"
        )

    output = _require(SCORING_MODEL, data, "output")
    effort_block = _require(SCORING_MODEL, output, "effort_tier")
    if not isinstance(effort_block, dict):
        raise DataRepoError(f"«{SCORING_MODEL}»: «output.effort_tier» debería ser mapa")
    order = _require(SCORING_MODEL, effort_block, "evaluation_order")
    if not isinstance(order, list) or not order:
        raise DataRepoError(
            f"«{SCORING_MODEL}»: «output.effort_tier.evaluation_order» está vacío. "
            "Sin orden, dos niveles se solapan y el resultado depende de cómo "
            "recorra el diccionario el intérprete."
        )
    tiers = {
        str(name): _mapping_of_text(
            body, source=SCORING_MODEL, key=f"effort_tier.{name}"
        )
        for name, body in effort_block.items()
        if name not in ("evaluation_order", "note")
    }

    portfolio = _require(SCORING_MODEL, data, "portfolio_assignment")
    buckets = {
        str(name): _text(rule)
        for name, rule in portfolio.items()
        if name not in ("note", "portfolio_policy")
    }
    bands = _mapping_of_text(
        _require(SCORING_MODEL, data, "probability_bands"),
        source=SCORING_MODEL,
        key="probability_bands",
    )

    _check_declared_names(set(bands), vocab.ProbabilityBand, key="probability_bands")
    _check_declared_names(
        set(buckets), vocab.PortfolioBucket, key="portfolio_assignment"
    )
    _check_declared_names(set(tiers), vocab.EffortTier, key="output.effort_tier")
    if set(order) != set(tiers):
        raise DataRepoError(
            f"«{SCORING_MODEL}»: «evaluation_order» ({sorted(order)}) no cubre "
            f"exactamente los niveles declarados ({sorted(tiers)})"
        )

    return ScoringModel(
        version=str(_require(SCORING_MODEL, data, "version")),
        updated_at=str(data.get("updated_at", "")),
        sha256=sha256,
        baseline_name=baseline_name,
        baseline=dict(baseline),
        dimensions=_dimensions(data),
        score_min=score_min,
        score_max=score_max,
        gates=_gates(data),
        probability_bands=bands,
        portfolio_buckets=buckets,
        effort_tiers=tiers,
        effort_evaluation_order=tuple(str(name) for name in order),
        minimum_coverage=minimum_coverage,
        never_rule=_text(_require(SCORING_MODEL, missing_data, "never")),
    )


def _variants(root: Path) -> VariantGuide:
    guide_path = root / VARIANTS_GUIDE
    try:
        guide_bytes = guide_path.read_bytes()
    except OSError as error:
        raise DataRepoError(
            f"no se puede leer la guía de variantes «{VARIANTS_GUIDE}»: {error}"
        ) from error

    config, _ = _read(root, CV_VARIANTS)
    declared_block = _require(CV_VARIANTS, config, "base_variants")
    if not isinstance(declared_block, dict) or not declared_block:
        raise DataRepoError(f"«{CV_VARIANTS}»: «base_variants» está vacío")
    declared = frozenset(str(name) for name in declared_block)

    variants_dir = root / VARIANTS_DIR
    try:
        on_disk = {entry.name for entry in variants_dir.iterdir() if entry.is_dir()}
    except OSError as error:
        raise DataRepoError(f"no se puede listar «{VARIANTS_DIR}»: {error}") from error

    # La intersección, y en el orden en que el YAML las declara: una carpeta
    # sin entrada en la configuración no es elegible —nadie ha decidido para
    # qué sirve— y una entrada sin carpeta tampoco, porque no hay documento.
    available = tuple(name for name in declared_block if name in on_disk)
    if not available:
        raise DataRepoError(
            f"ninguna de las variantes declaradas en «{CV_VARIANTS}» "
            f"({sorted(declared)}) tiene carpeta en «{VARIANTS_DIR}» "
            f"({sorted(on_disk)}). Sin documentos que elegir no hay "
            "recomendación posible."
        )

    return VariantGuide(
        guide_text=guide_bytes.decode(),
        guide_sha256=hashlib.sha256(guide_bytes).hexdigest(),
        available=available,
        declared=declared,
    )


def _bullets(root: Path) -> tuple[Bullet, ...]:
    data, _ = _read(root, BULLET_BANK)
    entries = _require(BULLET_BANK, data, "bullets")
    if not isinstance(entries, list) or not entries:
        raise DataRepoError(f"«{BULLET_BANK}»: «bullets» está vacío")

    bullets = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise DataRepoError(f"«{BULLET_BANK}»: cada bullet debería ser un mapa")
        bullet_id = entry.get("bullet_id")
        if not bullet_id:
            raise DataRepoError(f"«{BULLET_BANK}»: hay un bullet sin «bullet_id»")
        # El texto viaja en `text_en` en el banco real y en `text_es` en el
        # sintético, así que se acepta cualquier `text*`: lo que importa de
        # un bullet aquí es su identificador y su estado, no su idioma.
        text = next(
            (
                _text(value)
                for key, value in entry.items()
                if str(key).startswith("text") and value
            ),
            "",
        )
        families = entry.get("role_families") or []
        bullets.append(
            Bullet(
                bullet_id=str(bullet_id),
                text=text,
                evidence_status=str(entry.get("evidence_status", "")),
                cv_usage=str(entry.get("cv_usage", "")),
                role_families=tuple(str(family) for family in families),
            )
        )

    identifiers = [bullet.bullet_id for bullet in bullets]
    duplicated = sorted({name for name in identifiers if identifiers.count(name) > 1})
    if duplicated:
        raise DataRepoError(
            f"«{BULLET_BANK}»: hay identificadores repetidos ({duplicated}); una "
            "referencia a evidencia dejaría de ser inequívoca"
        )
    return tuple(bullets)


def load(root: Path | str) -> DataRepo:
    """Carga el repositorio privado entero, o lanza `DataRepoError`.

    Entero de una vez y no pieza a pieza: cargarlo por partes dejaría
    abierta la posibilidad de puntuar con un modelo de scoring y elegir
    variante con una guía de otro momento.
    """
    root = Path(root)
    if not root.is_dir():
        raise DataRepoError(
            f"«{root}» no es un directorio. El scoring necesita el repositorio "
            "de datos: en local se monta con DATA_REPO_HOST_PATH y en la VM lo "
            "deja ahí el clon de solo lectura."
        )
    absent = [
        str(relative) for relative in REQUIRED_FILES if not (root / relative).is_file()
    ]
    if absent:
        raise DataRepoError(
            f"«{root}» no parece el repositorio de datos: faltan {absent}"
        )

    objectives, _ = _read(root, OBJECTIVES)
    families = _require(OBJECTIVES, objectives, "role_families")
    core = _require(OBJECTIVES, families, "core")
    if not isinstance(core, list) or not core:
        raise DataRepoError(
            f"«{OBJECTIVES}»: «role_families.core» está vacío, y es lo que "
            "distingue una oferta experimental de una del objetivo"
        )

    constraints, _ = _read(root, CONSTRAINTS)
    conditions = constraints.get("disqualifying_conditions") or []
    if not isinstance(conditions, list):
        raise DataRepoError(
            f"«{CONSTRAINTS}»: «disqualifying_conditions» debería ser una lista"
        )

    return DataRepo(
        root=root,
        scoring=_scoring_model(root),
        core_role_families=frozenset(str(family) for family in core),
        disqualifying_conditions=tuple(
            DisqualifyingCondition(
                id=str(condition.get("id", "")), rule=_text(condition.get("rule", ""))
            )
            for condition in conditions
            if isinstance(condition, dict)
        ),
        variants=_variants(root),
        bullets=_bullets(root),
    )
