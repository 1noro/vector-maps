# Changelog

Los cambios del proyecto por versión. Sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
[semántico](https://semver.org/lang/es/).

**Cada vez que se crea un tag hay que actualizar este fichero**, antes de
crearlo: lo que haya en "Sin publicar" pasa a una sección nueva con la versión y
la fecha, y el commit del changelog es el que se etiqueta. Ver "Flujo de git" en
`AGENTS.md`.

Los apartados son los de siempre: **Añadido** (funcionalidad nueva),
**Cambiado** (comportamiento que ya existía), **Corregido** (bugs) y
**Documentación**. Un cambio que rompa algo —un flag, el formato del SVG, un
tema— se marca con **BREAKING** y sube la versión mayor.

## Sin publicar

### Añadido

- **Fallback a un PBF local**: si Overpass falla y un extracto de `data/pbf/` ya
  cubre el área, `make map` sigue con él y lo avisa (ADR 0002). No descarga
  nada solo.
- **Forma del mapa en la hoja**: `SHAPE=rect|square|circle` (`--shape`), aparte del
  papel. `square` y `circle` son una caja cuadrada centrada del lado corto de la
  hoja; el círculo se recorta con un `clipPath` por zona y lleva un borde fino
  (ADR 0003).
- **Área por centro y radio**: `CENTER=lat,lon RADIUS=km` (y `CENTER2`/`RADIUS2`
  para la zona superpuesta) como alternativa a `TL`/`BR`. El círculo de ese
  radio cabe siempre entero (ADR 0003). Un área casi cuadrada (±5 %) elige el
  apaisado con `ORIENTATION=auto`.
- **`make map`**: de dos esquinas (`TL`, `BR`) y un papel A0–A5 a un SVG en mm,
  con un grupo de Inkscape por capa (`water`, `green`, `buildings`, `railways`,
  `roads`), a escala real en UTM, con la atribución de OSM en el pie. La zona se
  amplía a la forma del papel y nunca se recorta (ADR 0003, 0004).
- **Dos temas**: `color` y `bw` (grises y negro, pensado para imprimir en
  monocromo), o cualquier `.toml` propio por ruta.
- **Dos fuentes de datos** (ADR 0002): Overpass con caché en disco y espera ante
  429/5xx, o un extracto PBF local cortado con `osmium` (`PBF=`). `make pbf URL=…`
  descarga el extracto a `data/pbf/`.
- **Superponer dos zonas** en la misma hoja, cada una con su zoom, tema, capas y
  opacidad (`TL2`, `BR2`, `THEME2`, `LAYERS2`, `OPACITY2`; ADR 0005).
- `make list`, `make check`, `make shell`, `make clean-cache` y `make clean-out`;
  `make` a secas (`make help`) enseña la ayuda.
  Todo corre en Docker con el uid:gid del usuario del host (ADR 0001).

- **Etiquetas** (no salen por defecto; se añaden con `INCLUDE_LAYERS`): dos capas de
  texto, `street-names` (el nombre de la calle, escrito a lo largo de ella) y
  `places` (ciudades, pueblos, barrios), con halo para leerse sobre el mapa.
  **Idioma elegible** con `LABEL_LANG` / `--lang` (`es` por defecto; `gl,es`
  para varios; `local` = como está mapeado): sale `name:<código>` y, si no
  existe, el `name` tal cual (ADR 0006).
- **Leyenda** en el pie, con las **esquinas `TL` y `BR` del mapa tal como está en
  el papel** (las dos zonas, si se superponen) y, arriba a la derecha, la marca
  «Generated with vector-maps by 1noro» (ADR 0004).
- **Spinner** con el tiempo transcurrido al construir la imagen y en los pasos
  lentos (`scripts/with-spinner.sh`, `vectormaps.progress`), solo con terminal.
- **Falla si el área está fuera del PBF** (Tokio con el de Galicia), antes de
  cortar nada; avisa si cabe solo en parte; y avisa si ninguna capa da datos.
- **Si Overpass falla, el error dice cómo seguir en local**: el PBF de
  `data/pbf/` que ya cubre el área o, si no hay, el extracto de Geofabrik más
  pequeño que la contiene, con su `make pbf URL=…` (ADR 0002).
- **Ctrl-C** sale con `interrupted` y código 130, sin traza.
- **`PDF=1`**: además del SVG, un PDF del tamaño del papel al lado, hecho con
  Inkscape (nuevo en la imagen; ADR 0007).
- **Relieve**: capas `hillshade` (sombreado) y `contours` (curvas de nivel), del
  DEM Copernicus GLO-30 con GDAL; no salen por defecto (`INCLUDE_LAYERS=…`). Con
  relieve, la leyenda lleva la atribución de Copernicus (ADR 0008).
- **`EXCLUDE_LAYERS`** (`EXCLUDE_LAYERS2` en la superposición): quita capas de
  `LAYERS` o de las de por defecto.
- **`INCLUDE_LAYERS`** (`INCLUDE_LAYERS2` en la superposición): añade capas a
  `LAYERS` o a las de por defecto, p. ej. `INCLUDE_LAYERS=street-names,places`.
- **`LEGEND=minimal`**: la leyenda en una línea, con las esquinas, la escala y
  `© OpenStreetMap`, y la marca arriba (ADR 0004).
- **Tema `monochrome`**: el `bw` tintado del color de `TINT=#rrggbb` (`TINT2`
  para la zona de encima; ADR 0004).

### Cambiado

- La leyenda escribe las esquinas con `↖` y `↘` (antes `TL` y `BR`) y, con una
  sola zona, la escala va sin la letra (`1:4120`, no `A 1:4120`; ADR 0004).
- `COORDS=dd|dm|dms` cambia el formato de las coordenadas de la leyenda (ADR 0004).
- Con `SHAPE=circle` la leyenda da el centro (`⌖ lat, lon`) en vez de las esquinas. La imagen instala `fonts-symbola` para
  dibujarlo (`make docker`; ADR 0007).
- `ORIENTATION=auto` elige apaisado cuando el área es casi cuadrada (±5 %).
- `make help` recoge `CENTER`/`RADIUS`, `SHAPE` y `CENTER2`/`RADIUS2`.
- `make` ya no muestra los comandos que ejecuta (`.SILENT`): el log lleva solo lo
  que dicen los programas.
- `osmium export` saca también puntos; los ficheros exportados en caché llevan la
  versión del export en el nombre (`v2`), así que los de antes no se reusan. El
  texto de los `.osm` descargados sí se reutiliza.

### Documentación

- ADR 0006 (etiquetas e idioma), 0007 (el PDF con Inkscape) y 0008 (relieve); añadidos del 03/11
  a los ADR 0002 y 0004.
- README, `docs/uso.md`, `docs/desarrollo.md`, los ADR 0001 a 0005, `AGENTS.md`
  y los procedimientos de `docs/agentes/` con sus comandos para Claude Code,
  Qwen Code y OpenCode.
- Licencias: GPL-3.0 o superior para el código y CC BY-SA 4.0 para el resto.
