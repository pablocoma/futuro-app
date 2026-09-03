"""Trabajos en cola y registro de coste.

Es la mitad operativa: `job_runs` y `llm_calls` son mutables a propósito. No
son capas del contrato de datos, sino el rastro de qué se ejecutó, cuándo,
cuántas veces y a qué precio.
"""
