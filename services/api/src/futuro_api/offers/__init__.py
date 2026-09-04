"""Ingesta y extracción de ofertas.

Las tres capas del contrato (`Futuro/docs/OFFER_DATA_CONTRACT.md`) no se
mezclan: `capture` es inmutable, `extraction` es inmutable y versionada por
`prompt_version`, y `assessment` —recalculable— vive en `assessment/`, con
un reparto distinto entre el modelo y el código.
"""
