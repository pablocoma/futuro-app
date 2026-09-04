# Estrategia de variantes del CV (INVENTADA, para el harness)

Ver la cabecera de `config/scoring_model.yaml`: nada de este directorio sale
del repositorio privado. La persona no existe y el oficio es otro.

Este fichero es el que se le pasa al modelo para que elija variante, así que
tiene que parecerse en forma al del repositorio privado: una tabla de guía
rápida y un apartado por variante.

## Guía rápida: qué archivo usar

| Variante | Archivo `.tex` | Usar como punto de partida cuando la oferta sea... |
|---|---|---|
| Cartografía náutica | `cartografia_nautica/CV_cartografia_nautica_es.tex` | Levantamiento de cartas náuticas, sondeo o señalización marítima |
| Topografía urbana | `topografia_urbana/CV_topografia_urbana_es.tex` | Replanteo, catastro urbano u obra civil |
| Teledetección | `teledeteccion/CV_teledeteccion_es.tex` | Análisis de imagen satelital o de vuelo fotogramétrico |
| Sistemas GIS | `sistemas_gis/CV_sistemas_gis_es.tex` | Montaje y explotación de sistemas de información geográfica |

Si una oferta mezcla familias, se elige la variante que cubra mejor sus
responsabilidades principales. No se mezclan variantes completas ni se crea
un CV desde cero.

## `cartografia_nautica`

Prioriza sondeo multihaz, mareógrafos, campañas embarcadas y normativa de la
organización hidrográfica.

## `topografia_urbana`

Prioriza estación total, GNSS, replanteo de obra y coordinación con
contratas.

## `teledeteccion`

Prioriza imagen satelital, corrección radiométrica, clasificación de
cubiertas y vuelo fotogramétrico.

## `sistemas_gis`

Prioriza bases de datos espaciales, servicios de mapas, automatización de
procesos y publicación de visores.

## `batimetria_profunda`

No se generará hasta que tenga campañas de sondeo profundo que enseñar.
