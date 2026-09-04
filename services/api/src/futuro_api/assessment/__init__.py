"""La capa `assessment` del contrato de datos: lo que se concluye de una oferta.

El reparto que gobierna este paquete, y que es **distinto** del de `offers/`:
en la extracción el LLM elegía y citaba; aquí **el LLM juzga y el código
calcula**. El modelo pone la nota de cada dimensión, la cita que la sostiene
y el motivo; la media ponderada, la renormalización, la cobertura, el cubo de
cartera y el nivel de esfuerzo salen de `scoring.py`, que es una función pura
y no ve al modelo.

La propiedad que justifica que esta capa exista aparte es que **se recalcula
sin volver a llamar al LLM**, y `recompute.py` es el camino que la hace real:
repuntuar todo el histórico es recorrer la base de datos, no volver a pagar
la extracción de cada oferta.

La única cosa de aquí que no es recalculable es la recomendación de variante
de CV, y por eso vive en su propia tabla: elegir variante exige llamar al
modelo, así que si compartiera fila con la puntuación, la propiedad de arriba
dejaría de ser cierta.
"""
