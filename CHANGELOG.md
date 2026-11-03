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

- **Etiquetas**: dos capas de texto, `street-names` (el nombre de la calle,
  escrito a lo largo de ella) y `places` (ciudades, pueblos, barrios), con halo
  para leerse sobre el mapa. **Idioma elegible** con `LABEL_LANG` / `--lang`
  (`es` por defecto; `gl,es` para varios; `local` = como está mapeado): sale
  `name:<código>` y, si no existe, el `name` tal cual (ADR 0006).
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
- **Tema `monochrome`**: el `bw` tintado del color de `TINT=#rrggbb` (`TINT2`
  para la zona de encima; ADR 0004).

### Cambiado

- `make` ya no muestra los comandos que ejecuta (`.SILENT`): el log lleva solo lo
  que dicen los programas.
- `osmium export` saca también puntos; los ficheros exportados en caché llevan la
  versión del export en el nombre (`v2`), así que los de antes no se reusan. El
  texto de los `.osm` descargados sí se reutiliza.

### Documentación

- ADR 0006 (etiquetas e idioma) y 0007 (el PDF con Inkscape); añadidos del 03/11
  a los ADR 0002 y 0004.
- README, `docs/uso.md`, `docs/desarrollo.md`, los ADR 0001 a 0005, `AGENTS.md`
  y los procedimientos de `docs/agentes/` con sus comandos para Claude Code,
  Qwen Code y OpenCode.
- Licencias: GPL-3.0 o superior para el código y CC BY-SA 4.0 para el resto.
