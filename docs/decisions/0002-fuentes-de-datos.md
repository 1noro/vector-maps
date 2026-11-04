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

## Añadido del 03/11/2026: el área tiene que estar en el PBF

Con solo Galicia, pedir Tokio **no daba error**: osmium cortaba un área vacía y
salía un SVG de 1 KiB con el marco y nada más. Ahora `PbfSource.check` compara
el área con la caja de la cabecera del PBF (`osmium fileinfo -g header.boxes`;
la llevan los de Geofabrik) y, **antes de cortar nada**, falla con el rango que
cubre el fichero y cómo bajar otro (`make pbf URL=…`). Si el área cabe solo en
parte, avisa del porcentaje. Si el fichero no trae caja, no puede comprobarse, y
el pipeline avisa cuando ninguna capa da un solo rasgo ("no data found").
Con una superposición se comprueban las dos zonas antes de empezar.

## Añadido del 03/11/2026: si Overpass falla, qué extracto bajar

Cuando Overpass da un error (los 502/504 de ese día, un timeout, una respuesta
cortada), el error lleva una **pista** con el comando que hay que usar para
seguir en local:

1. Si algún `.osm.pbf` de `data/pbf/` ya cubre el área (por la caja de su
   cabecera), que se repita el mismo `make map` con `PBF=` ese fichero.
2. Si no, **el extracto más pequeño de Geofabrik que contiene el área**, con su
   `make pbf URL=…` y el `PBF=` de después. Para saberlo se baja **una vez** el
   índice de Geofabrik (`index-v1.json`, ~4 MB, con el contorno de cada
   extracto) a `data/cache/geofabrik/`: una sola petición, con nuestro
   `User-Agent`, sin cuenta ni clave, y solo cuando hace falta la pista.
   `make clean-cache` lo renueva.
3. Si no hay red o ningún extracto la contiene, el enlace a la lista.

Con dos zonas, el extracto tiene que contener **cada una**, no la caja que
abarca las dos: Madrid y Santiago caben en España, pero su caja común se mete
en Portugal y daría Europa entera.

Que la pista use Geofabrik no cambia lo decidido arriba: los datos siguen
saliendo de Overpass o de un PBF, y si el índice no se puede bajar, el error de
Overpass sale igual, solo con una pista menos precisa.

## Añadido del 04/11/2026: si Overpass falla y ya hay un extracto, se usa

Cuando Overpass falla (tras las esperas y los 3 intentos de siempre, nunca al
primer 5xx) y **algún `.osm.pbf` de `data/pbf/` cubre todas las zonas** (por la
caja de su cabecera, el más pequeño), `make map` sigue solo con él y lo avisa en
el log (`Overpass failed (…); using the local extract …`). Antes solo lo
sugería. Los datos que Overpass ya había dejado en la caché no se pierden.

- **No se baja nada por iniciativa propia**: un extracto pesa cientos de MB. Si
  no hay ninguno que sirva, sale el error de Overpass con la pista de Geofabrik,
  como antes.
- Si se pasó `PBF=`, no hay fallback: ya es la fuente elegida.
- Los datos del extracto pueden tener otra fecha que los de Overpass; por eso el
  aviso es un `WARNING`, no un `INFO`.

## Añadido del 04/11/2026: el log dice de dónde sale cada capa

El usuario creyó que la caché de Overpass no funcionaba: una capa fallaba en
cada ejecución, un fallo no se cachea (como manda la regla) y el mapa acababa
saliendo del extracto sin que se notara. Ahora:

- Cada línea de capa lleva su fuente: `layer water: 58 features (Overpass)`, o
  `(local extract galicia-latest.osm.pbf)`, o `(Copernicus DEM)` en el relieve.
- El error de Overpass nombra la capa (`layer water: Overpass answered HTTP
  504`), y el aviso del fallback dice que todas las capas salen del extracto
  (`…; drawing every layer from the local extract …`).

Nada cambia en cómo se piden, se esperan o se cachean los datos.
