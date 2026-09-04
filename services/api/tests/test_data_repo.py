"""La frontera con el repositorio privado.

Todo lo de aquí corre contra el repositorio de datos **sintético** de
`fixtures/data_repo/`, que imita la forma del privado y no comparte ni un
dato con él. Ver la cabecera de su `config/scoring_model.yaml`: es distinto
a propósito en todo lo que el código no debe dar por supuesto.
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from futuro_api import data_repo
from futuro_api.data_repo import loader
from tests.conftest import DATA_REPO


@pytest.fixture
def repo_copy(tmp_path: Path) -> Path:
    """Una copia del repositorio sintético que un test puede estropear."""
    destination = tmp_path / "data_repo"
    shutil.copytree(DATA_REPO, destination)
    return destination


def test_the_synthetic_repo_loads_whole() -> None:
    repo = data_repo.load(DATA_REPO)
    assert repo.scoring.version == "7"
    assert repo.scoring.total_weight == 100
    assert repo.scoring.minimum_coverage == Decimal("0.60")
    assert repo.core_role_families == {"data_engineer", "data_scientist", "cartografo"}
    assert [c.id for c in repo.disqualifying_conditions] == [
        "factura_por_su_cuenta",
        "pago_por_produccion",
    ]


def test_dimensions_keep_the_order_of_the_yaml() -> None:
    """El orden del YAML es el de las barras de la pantalla.

    Ordenarlas alfabéticamente inventaría una jerarquía que el modelo de
    scoring no tiene.
    """
    repo = data_repo.load(DATA_REPO)
    assert repo.scoring.dimension_names == (
        "ahorro_estimado",
        "aprendizaje",
        "ubicacion",
        "encaje_de_rol",
    )
    assert [d.weight for d in repo.scoring.dimensions] == [40, 30, 20, 10]


def test_an_anchor_interpolates_downwards() -> None:
    """El 2 y el 4 se explican con el ancla de abajo.

    El YAML define 0, 1, 3 y 5, así que un 4 se justifica con el texto del
    3: eso es lo que significa interpolar. Devolver `None` para el 4 dejaría
    la nota sin explicación en pantalla.
    """
    dimension = data_repo.load(DATA_REPO).scoring.dimensions[0]
    assert dimension.anchor_for(3) == dimension.anchor_for(4)
    assert dimension.anchor_for(0) != dimension.anchor_for(1)


def test_only_variants_with_a_folder_are_selectable() -> None:
    """Una variante declarada y sin carpeta no se puede elegir.

    `batimetria_profunda` está en `cv_variants.yaml` y no tiene carpeta,
    igual que `quant_exploratory` en el repositorio privado. El vocabulario
    sale del disco justamente por esto: el LLM elige entre documentos que
    existen, y eso es una propiedad del vocabulario y no un ruego del
    prompt.
    """
    variants = data_repo.load(DATA_REPO).variants
    assert "batimetria_profunda" in variants.declared
    assert "batimetria_profunda" not in variants.available
    assert variants.declared_but_missing == ("batimetria_profunda",)
    assert len(variants.available) == 4


def test_a_bullet_needs_both_states_to_be_usable() -> None:
    """`verified` **y** divulgable. Uno solo no sostiene un `meets`.

    El primero dice que el contenido está comprobado y el segundo que se
    puede divulgar. El banco sintético tiene los tres casos a propósito.
    """
    repo = data_repo.load(DATA_REPO)
    assert {b.bullet_id for b in repo.usable_bullets} == {
        "sondeo_multihaz",
        "bases_espaciales",
    }
    candidate = repo.bullet("replanteo_de_obra")
    blocked = repo.bullet("vuelo_fotogrametrico")
    assert candidate is not None and not candidate.usable  # candidate
    assert blocked is not None and not blocked.usable  # verified, pero no divulgable


def test_the_hash_changes_with_the_file_and_not_with_the_version(
    repo_copy: Path,
) -> None:
    """El `sha256` es lo que detecta un cambio que nadie versionó.

    `config/scoring_model.yaml` del repositorio privado declara `version: 1`
    y el modelo cambió dos veces el mismo día. Con el hash, dos ofertas
    puntuadas con textos distintos del mismo `version` se distinguen.
    """
    before = data_repo.load(repo_copy).scoring
    path = repo_copy / loader.SCORING_MODEL
    path.write_text(
        path.read_text().replace("ahorro_estimado: 40", "ahorro_estimado: 45")
    )
    after = data_repo.load(repo_copy).scoring
    assert after.version == before.version
    assert after.sha256 != before.sha256


# ---------------------------------------------------------------------------
# Falla cerrado
# ---------------------------------------------------------------------------


def test_a_missing_directory_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(data_repo.DataRepoError, match="no es un directorio"):
        data_repo.load(tmp_path / "no-existe")


def test_a_directory_that_is_not_the_data_repo_says_what_is_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(data_repo.DataRepoError, match="faltan"):
        data_repo.load(tmp_path)


def test_a_renamed_probability_band_refuses_to_load(repo_copy: Path) -> None:
    """El código ramifica sobre las bandas, así que no son vocabulario libre.

    Renombrar `high` en el YAML no rompería ninguna constraint: cambiaría en
    silencio el resultado de una comparación y todas las ofertas caerían en
    otro cubo. Por eso el cargador lo comprueba.
    """
    path = repo_copy / loader.SCORING_MODEL
    path.write_text(path.read_text().replace("\n  high: >-", "\n  altisima: >-"))
    with pytest.raises(data_repo.DataRepoError, match="probability_bands"):
        data_repo.load(repo_copy)


def test_an_extra_portfolio_bucket_refuses_to_load(repo_copy: Path) -> None:
    """Un cubo que el código no sabe calcular nunca se asignaría.

    Se comprueba en las dos direcciones: uno que falta deja un cubo
    inalcanzable y uno de más es una regla que nadie aplicaría, y las dos
    pasarían inadvertidas sin esto.
    """
    path = repo_copy / loader.SCORING_MODEL
    path.write_text(
        path.read_text().replace(
            "  discard: valor < 3.0",
            "  inventado: una regla que el código no conoce\n  discard: valor < 3.0",
        )
    )
    with pytest.raises(data_repo.DataRepoError, match="portfolio_assignment"):
        data_repo.load(repo_copy)


def test_a_changed_scale_refuses_to_load(repo_copy: Path) -> None:
    """La escala 0-5 está en un CHECK del esquema, no solo en el YAML.

    Cambiarla ahí sin migración dejaría filas que la base de datos rechaza
    en el último momento, y el error saldría en el sitio menos útil.
    """
    path = repo_copy / loader.SCORING_MODEL
    path.write_text(path.read_text().replace("range: [0, 5]", "range: [0, 10]"))
    with pytest.raises(data_repo.DataRepoError, match="migración"):
        data_repo.load(repo_copy)


def test_an_evaluation_order_that_misses_a_tier_refuses_to_load(
    repo_copy: Path,
) -> None:
    """Sin orden completo, dos niveles se solapan y gana el que caiga."""
    path = repo_copy / loader.SCORING_MODEL
    path.write_text(
        path.read_text().replace(
            "evaluation_order: [skip, cheap, full, standard]",
            "evaluation_order: [skip, cheap, full]",
        )
    )
    with pytest.raises(data_repo.DataRepoError, match="evaluation_order"):
        data_repo.load(repo_copy)


def test_a_dimension_without_anchors_refuses_to_load(repo_copy: Path) -> None:
    """Sin anclas escritas el modelo no tiene contra qué puntuar."""
    path = repo_copy / loader.SCORING_MODEL
    text = path.read_text().replace("weights:", "weights:\n  sin_anclas: 5", 1)
    path.write_text(text)
    with pytest.raises(data_repo.DataRepoError, match="ancla"):
        data_repo.load(repo_copy)


def test_a_repeated_bullet_id_refuses_to_load(repo_copy: Path) -> None:
    """Un identificador repetido haría ambigua una referencia a evidencia."""
    path = repo_copy / loader.BULLET_BANK
    path.write_text(
        path.read_text().replace(
            "  - bullet_id: bases_espaciales", "  - bullet_id: sondeo_multihaz", 1
        )
    )
    with pytest.raises(data_repo.DataRepoError, match="repetidos"):
        data_repo.load(repo_copy)


def test_no_variant_with_a_folder_refuses_to_load(repo_copy: Path) -> None:
    """Sin documentos que elegir no hay recomendación posible."""
    for folder in (repo_copy / loader.VARIANTS_DIR).iterdir():
        if folder.is_dir():
            shutil.rmtree(folder)
    with pytest.raises(data_repo.DataRepoError, match="carpeta"):
        data_repo.load(repo_copy)
