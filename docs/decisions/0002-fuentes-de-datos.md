# ADR 0002 — Overpass con caché o un PBF local

Estado: aceptada

## Contexto

Hay dos maneras razonables de obtener datos de OSM sin montar una base de
datos: preguntar a la **API Overpass** o cortar un **extracto PBF** local
(Geofabrik) con `osmium`. El usuario pidió las dos.

## Decisión

Dos fuentes con la misma interfaz (`sources.Source`), que entregan features en
lon/lat con su tipo (`polygon`/`line`) y sus etiquetas:

- **`OverpassSource`**: una consulta por capa y zona, cacheada en
  `data/cache/overpass/` por el texto exacto de la consulta.
- **`PbfSource`**: `osmium extract --strategy=smart` sobre el área (una vez,
  cacheado en `data/cache/pbf/`) y todas las capas salen de ese mismo corte.

En ambas, **`osmium export` hace la geometría**: ensambla los multipolígonos y
da GeoJSON-seq. El resto del programa no sabe de cuál se trata.

## Razones

- **Overpass es lo cómodo** para una zona de ciudad: nada que descargar. Pero el
  servidor público limita por IP (~10.000 peticiones y ~1 GB al día), aprieta
  los 429 desde agosto de 2026 y **se cae**: el 03/11/2026 el principal dio 502
  y los espejos de private.coffee, VK Maps y kumi.systems, 504 o timeout.
- **El PBF no depende de nadie** y sirve para zonas grandes. Cuesta una
  descarga (Galicia: 112 MB) y cortar con osmium.
- **`--strategy=smart`** mantiene completos los multipolígonos que cruzan el
  borde de la zona (un parque grande, un lago); la estrategia por defecto los
  dejaría rotos.
- Pasar las dos por `osmium export` evita escribir y mantener un ensamblador de
  multipolígonos propio.

## Reglas con Overpass

Una petición cada vez; esperar (no reintentar a ciegas) ante 429/502/503/504,
máximo 3 intentos; `User-Agent` propio; un 200 con `runtime error` es un fallo
y no se cachea; se avisa de las zonas grandes (>0,04 grados²). Servidor por
`OVERPASS_URL`.

## Sin cuentas ni claves

Overpass, Geofabrik y OSM no piden cuenta ni clave para esto; **una cuenta de
OSM no da más cuota en Overpass**. Si algún servicio las exigiera (hay espejos de
pago, como Tracestrack u Overspan), se consulta antes de usarlo.

## Consecuencias

- Una capa nueva se define una vez (`layers.py`) y vale para las dos fuentes.
- Cambiar el PBF (otra fecha) cambia la clave de la caché: no se sirve nada viejo.
