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
- `make list`, `make check`, `make shell`, `make clean-cache` y `make clean-out`.
  Todo corre en Docker con el uid:gid del usuario del host (ADR 0001).

### Documentación

- README, `docs/uso.md`, `docs/desarrollo.md`, los ADR 0001 a 0005, `AGENTS.md`
  y los procedimientos de `docs/agentes/` con sus comandos para Claude Code,
  Qwen Code y OpenCode.
- Licencias: GPL-3.0 o superior para el código y CC BY-SA 4.0 para el resto.
