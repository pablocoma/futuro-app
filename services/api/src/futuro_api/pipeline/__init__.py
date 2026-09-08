"""El estado de una candidatura, en su propia línea de tiempo.

`docs/OFFER_DATA_CONTRACT.md` (repositorio privado `Futuro`) describe
`applications.status` como si estado y dossier vivieran en la misma fila.
Se separan aquí a propósito: el estado empieza en `research`, antes de que
exista ninguna variante confirmada, y `applications` (Fase 1 M3) exige
`variant`/`cv_sha256` desde el primer día -forzar las dos cosas en una
tabla habría exigido hacerlos nullable y mezclar dos eventos distintos,
cambiar de variante y cambiar de etapa, en una sola fila-.

`offer_status_events` cuelga de `capture_id`, igual que `applications`:
append-only, con el mismo trigger de inmutabilidad, «vigente» = la última
fila por `(occurred_at DESC, id DESC)`. No hay columna `submitted_at` ni
parecidas: son el `occurred_at` de la fila donde el estado tomó ese valor.

Fase 3, rebanada 1. Ver `docs/decisions/fase-3-estados-de-candidatura.md`.
"""

from __future__ import annotations
