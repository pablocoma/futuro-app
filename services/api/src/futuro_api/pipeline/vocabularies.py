"""El vocabulario del estado de una candidatura.

Los cinco valores están cerrados en `docs/OFFER_DATA_CONTRACT.md`
(repositorio privado); no se inventan aquí. Es vocabulario de **código** y no
del repositorio privado -no hay ningún YAML que lo declare, a diferencia de
`role_families`-, así que no hay ningún camino de ampliarlo desde fuera.
"""

from __future__ import annotations

from enum import StrEnum


class ApplicationStatus(StrEnum):
    """Sin orden forzado: cualquier transición es válida.

    El kanban de `docs/APP_SCREENS.md` se arrastra a mano, y una oferta
    puede pasar de `research` a `closed` sin pasar por las demás -se
    descartó sin llegar a preparar nada-. La base de datos no impone una
    máquina de estados; si algún día hace falta, es una decisión aparte,
    no algo que esta rebanada dé por hecho.
    """

    RESEARCH = "research"
    PREPARING = "preparing"
    SUBMITTED = "submitted"
    INTERVIEW = "interview"
    CLOSED = "closed"


# El valor implícito de "sin decidir todavía". No se escribe una fila al
# capturar -ver `repository.current_status`-, así que toda captura sin
# ningún evento se lee como si tuviera esta.
DEFAULT_STATUS = ApplicationStatus.RESEARCH
