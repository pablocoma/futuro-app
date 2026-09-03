"""Ingesta y extracción de ofertas.

Las tres capas del contrato (`Futuro/docs/OFFER_DATA_CONTRACT.md`) no se
mezclan: `capture` es inmutable, `extraction` es inmutable y versionada por
`prompt_version`, y `assessment` —recalculable— no existe todavía: es M2.
"""
