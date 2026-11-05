# AGENTS.md

Directrices para trabajar en este repositorio, para una persona o un agente de
IA. Las tres herramientas que se usan (**Claude Code**, **Qwen Code** y
**OpenCode**) lo leen solas (Claude Code, por el `@AGENTS.md` de `CLAUDE.md`),
y nada de aquí depende de una concreta. **Es corto a propósito**: la historia
vive en [`docs/desarrollo.md`](docs/desarrollo.md), los ADR y git.

**Con el usuario se habla en castellano.** El código y la documentación siguen
sus propias reglas de idioma ("Convenciones de código").

## Qué es esto

Scripts en Python que sacan mapas de OpenStreetMap como **SVG por capas**
(agua, verde, edificios, ferrocarril, calles, con sus nombres), en color o en blanco y negro,
listos para imprimir en papel A0–A5, y que pueden **superponer dos zonas con
distinto zoom** en la misma hoja. Cómo se usa, en el [README](README.md).

Es un proyecto personal de un solo mantenedor. **La simplicidad gana a la
elegancia.** Todo corre en Docker; en el host solo hacen falta `make` y
`docker`.

| Módulo (`src/vectormaps/`) | Qué hace |
|---|---|
| `paper.py` | los tamaños ISO A0–A5 |
| `area.py` | dos esquinas (o centro + radio) + papel + forma → `Frame` (UTM, escala) |
| `layers.py` | las capas: qué etiquetas de OSM entran en cada una y la consulta Overpass |
| `labels.py` | el idioma de los nombres, dónde se escribe el de cada calle y el antichoque |
| `sources.py` | de dónde salen los datos: `OverpassSource` o `PbfSource` |
| `overpass.py`, `osmexport.py`, `download.py` | cliente con caché, `osmium export`, descarga de PBF |
| `boundaries.py` | los límites administrativos: de las relaciones a líneas con sus niveles |
| `geofabrik.py` | qué extracto cubre un área, para la pista cuando Overpass falla |
| `pipeline.py` | `Frame` + capas + fuente → features por capa |
| `theme.py`, `themes/*.toml` | los estilos (bw, color, street, dark, blueprint, vintage, vintage-bw, poster, y monochrome: el bw tintado) |
| `pdf.py` | el PDF del tamaño del papel, con Inkscape |
| `relief.py` | el relieve: teselas del DEM de Copernicus, curvas y sombreado con GDAL |
| `progress.py` | el spinner de los pasos lentos, solo con terminal |
| `tmpfile.py` | el nombre del temporal de cada fichero, único para que dos `make map` no se pisen |
| `render.py` | features → SVG; un `Job` por zona, apiladas |
| `cli.py` | `map`, `list`, `download`, `wizard` |
| `wizard.py` | las preguntas en la terminal → el `argv` de `map`, y su memoria |

## Decisiones cerradas — NO reabrir sin motivo nuevo

Razonadas en `docs/decisions/`. Si crees que alguna está mal, dilo antes de
tocar código.

1. **Python, y todo dentro de Docker** (ADR 0001). Nada que dependa de una
   librería del host; nada de `pip install` fuera de la imagen.
2. **Los datos, de Overpass con caché o de un PBF local con osmium** (ADR 0002).
   Ambas fuentes entregan lo mismo y el resto del programa no distingue. Si
   Overpass falla y un PBF de `data/pbf/` cubre el área, se usa solo, con aviso;
   **nunca se descarga un extracto sin que el usuario lo pida**.
   **Sin cuentas ni claves**; si algún servicio las exigiera, se consulta antes.
3. **El área son dos esquinas (o un centro y un radio) y un papel ISO A; la
   zona crece, nunca se recorta** (ADR 0003), también con `SHAPE=square|circle`
   (el círculo es el circunscrito). Escala real en una proyección UTM local.
4. **El SVG va en mm, con un grupo de Inkscape por zona y por capa, y el estilo
   como atributos de presentación sacados de un tema TOML** (ADR 0004). No CSS
   externo: se pierde al abrirlo en otros programas.
5. **La atribución "© OpenStreetMap contributors" va siempre en el SVG** y no
   tiene opción para quitarla (ODbL). Por eso el margen mínimo es de 6 mm.
6. **La superposición apila zonas con el mismo papel, orientación y margen, y
   cada una con su escala, tema, capas y opacidad** (ADR 0005).
7. **Las etiquetas son capas de texto (`street-names`, `places` y, desde el
   05/11, `water-names` y `green-names`); el idioma es un código de OSM (`es`
   por defecto) y, si no hay traducción, se muestra el `name` tal cual** (ADR
   0006). No se inventan traducciones. No están en las capas por defecto
   (añadido del 03/11). **No se pisan**: se colocan por `LABEL_PRIORITY` y el que
   no encuentra sitio no sale (añadido del 05/11).
8. **La leyenda lleva las esquinas del mapa tal como está en el papel y la marca
   «Generated with vector-maps by 1noro»** (ADR 0004, añadido del 03/11), y por
   defecto **una flecha al norte geográfico** (añadido del 04/11), que `NORTH=0`
   quita (añadido del 05/11).
9. **El PDF sale del SVG con Inkscape** (ADR 0007): es el único conversor que
   pinta `textPath` y los halos. Ni librsvg ni CairoSVG.
10. **El relieve (`hillshade`, `contours`) sale del DEM Copernicus GLO-30 con
    GDAL, no está en las capas por defecto y, si se dibuja, lleva la atribución
    de Copernicus** (ADR 0008).
11. **Los límites administrativos son tres capas de líneas, `parishes`,
    `municipalities` y `boundaries`, que no salen por defecto; una consulta trae
    solo los tramos del mapa y un tramo compartido lo dibuja la capa más alta
    presente** (ADR 0010).
12. **El wizard (`make wizard`) solo pregunta y llama a la CLI con el mismo
    `argv`; no valida ni dibuja por su cuenta** (ADR 0009). Una opción nueva de
    `make map` lleva también su pregunta.

## Reglas que no se saltan

### Sobre Overpass

El servidor público limita por IP y **se cae con frecuencia** (502/504 el
03/11/2026 en los cuatro espejos probados). Por eso: **una petición cada vez**,
caché en disco por consulta (con el recuadro redondeado, y una respuesta de un área
mayor sirve para las de dentro: ADR 0002), `User-Agent` propio, y **esperar** ante un
429/502/503/504 (nunca reintentos a ciegas; máximo 3 intentos). Un 200 con
`runtime error` es un fallo y **no se cachea**. Una fuente nueva de datos
respeta lo mismo.

### Sobre `./data` y `./out`

**Son del usuario del host, siempre.** Todo contenedor corre con
`-u $(HOST_UID):$(HOST_GID)` (lo pone el `Makefile`). Nada de `chown` ni de
root; `./data` y `./out` los crea `make` (`data-dir`), nunca Docker. Nada
dentro de `data/` ni de `out/` va a git.

### Sobre los tests

No tocan la red. Overpass se simula; osmium sí se ejecuta (está en la imagen)
sobre un `.osm` diminuto escrito a mano.

## Comandos

No hay Python ni osmium en el host: el `Makefile` lo ejecuta en un contenedor.

```bash
make                          # la ayuda (make help): objetivos y variables
make check                    # lint + tests. Lo que hay que pasar.
make test | lint | fmt        # por separado
make docker                   # reconstruye la imagen (Dockerfile o requirements)

make map TL=lat,lon BR=lat,lon [PAPER=A4] [THEME=bw|color] [LAYERS=a,b] [OUT=out/x.svg]
                              # por defecto: apaisado, margen 6, bw, leyenda mínima, dms y PDF
make map … THEME=monochrome TINT=#7a2e1f                        # el bw tintado de un color
make map … PDF=0                                                # sin el PDF (sale por defecto)
make map … NORTH=0                                              # sin la flecha del norte
make map … LEGEND=full                                          # leyenda larga (papel, © completa)
make map … INCLUDE_LAYERS=hillshade,contours | EXCLUDE_LAYERS=railways # añadir | quitar capas
make map … LABEL_LANG=gl                                         # idioma de los nombres (es por defecto)
make map … TITLE="Cecebre"                                      # un título en una banda encima del mapa
make map CENTER=lat,lon RADIUS=km                               # el área por centro y radio
make map … SHAPE=circle                                         # rect (defecto), square o circle
make map … TL2=lat,lon BR2=lat,lon [THEME2=bw] [OPACITY2=0.7]   # superponer otra zona
make map … PBF=data/pbf/galicia-latest.osm.pbf                  # datos locales
make wizard                   # lo mismo, guiado; recuerda la última vez (data/wizard.json)
make pbf URL=https://download.geofabrik.de/…-latest.osm.pbf     # bajar un extracto
make list                     # capas, papeles y temas
                              # las recetas no se muestran (.SILENT); lo lento lleva un spinner
make shell | clean-cache | clean-out
```

Más, para usarlo: `docs/uso.md`.

## Convenciones de código

- Python 3.12, stdlib primero. Dependencias solo si pagan su peso
  (`shapely`, `pyproj`); versiones fijadas en `requirements*.txt`.
- `ruff` (lint + formato, 100 columnas) y `pytest`; `make check` los pasa.
- **Todo lo que el programa emite va en inglés**: logs, errores, `--help`.
  **El código va en inglés** (nombres, comentarios, tests). **Los ADR, `docs/`
  y este fichero, en castellano**; los comentarios del `Makefile`, también.
- Fechas en comentarios: "Nov 3" en vez de "03/11", con año solo si no es 2026.
- Los errores del usuario (esquinas mal, capa desconocida) son `ValueError` con
  un mensaje que dice qué hacer; la CLI los imprime sin traza.

## Flujo de git

- [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`,
  `fix:`, `docs:`…), en castellano.
- Los commits van en la rama en la que se esté (hoy, `main`). **No cambiar de
  rama, ni crear una, ni forzar contra `main`**, salvo que el usuario lo pida.
- **Nunca una línea de atribución a un agente de IA o su herramienta**
  (`Co-Authored-By`, "Generated with …") en commits ni PRs, aunque la
  herramienta lo haga por defecto. Los commits van a nombre del usuario.
- **Nunca commitear por iniciativa propia**: se deja sin commitear para que el
  usuario lo revise, y se commitea solo cuando lo pide en ese turno.
- **Cada tag actualiza antes `CHANGELOG.md`**: "Sin publicar" pasa a una
  sección con la versión y la fecha, y ese commit es el que se etiqueta.

## Al trabajar en una tarea

1. Lee el ADR relevante de `docs/decisions/` antes de tocar un módulo.
2. Un módulo por tarea. No refactorices de paso lo que no te han pedido.
3. Si una decisión documentada te bloquea, **dilo y espera**; no la cambies.
4. Los `TODO(N)` del código y de `docs/desarrollo.md` llevan el mismo número.
5. **Los ADR no se reescriben**: cuando algo cambia, se añade un apartado
   fechado.

Los procedimientos, en texto llano en `docs/agentes/`: `tarea.md` (implementar
un TODO) y `revisar-adr.md` (comprobar que el código respeta los ADR). Cada
herramienta tiene un comando que solo apunta ahí (`/tarea N`, `/revisar-adr`),
en `.claude/commands/`, `.opencode/command/` y `.qwen/commands/`, iguales:
**el procedimiento se cambia en `docs/agentes/`, nunca en el comando.**
`CLAUDE.md` es solo `@AGENTS.md`. **Nada en este fichero que solo entienda una
herramienta**, y **que siga siendo corto**.

## Lo que queda

El orden y el porqué, en `docs/desarrollo.md`. Abiertos:

- **1** — nombres de edificios y puntos de interés; antichoque entre zonas.
- **3** — puentes y túneles (trazo distinto) y más clases de calle.
- **4** — recorte de la hoja a un polígono (GeoJSON).
- **5** — escala redonda opcional (`--scale 1:5000`) en vez de la que salga.
- **6** — más de dos zonas superpuestas.
- **7** — buscar el área por nombre en el wizard (Nominatim).
- **8** — plus codes en las esquinas (el corto de Google Maps pide geocodificar).
