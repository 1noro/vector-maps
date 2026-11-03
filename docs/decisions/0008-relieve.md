# ADR 0008 — El relieve: curvas de nivel y sombreado, del DEM de Copernicus

Estado: aceptada

## Contexto

El 03/11/2026 el usuario pidió una capa de relieve, **que no salga por
defecto**. Eligió tener las dos formas habituales, cada una en su capa, y
calcularlas con GDAL.

OSM no tiene el terreno: como mucho, la altura de algún pico. Hace falta un
modelo digital de elevación (DEM), y eso es una **fuente de datos nueva**, aparte
de Overpass y del PBF (ADR 0002).

## Decisión

- **Dos capas**: `hillshade` (sombreado) y `contours` (curvas de nivel, clases
  `minor` y `major`). **No están en el conjunto por defecto**: se piden en
  `LAYERS`. En el orden de dibujo, el sombreado va sobre el agua y el verde, y
  las curvas debajo de los edificios.
- **Los datos: Copernicus DEM GLO-30**, 30 m, todo el planeta, abierto en AWS
  (`copernicus-dem-30m.s3.amazonaws.com`), **sin cuenta ni clave**.
  - Se baja **la tesela entera de 1°×1°** (~40 MB) una vez a `data/cache/dem/`, y
    vale para cualquier mapa dentro de ella, también sin red después.
  - Donde no hay tesela (el mar abierto, un 404) se deja una marca `.none` para
    no volver a preguntar.
  - Una petición cada vez, con nuestro `User-Agent` y la misma espera ante
    429/5xx que con Overpass.
- **GDAL** (`gdal-bin`, en la imagen como osmium) hace el resto:
  - `gdalwarp` corta y reproyecta el DEM al **UTM del mapa**, en una rejilla
    alineada con el marco: una celda son 0,25 mm de papel. El tamaño depende del
    papel, no de la zona.
  - `gdal_contour` saca las curvas. La equidistancia sale de la escala
    (`escala / 2500`, redondeada a 5, 10, 20, 25, 50… m; nunca menos de 5 m) y
    una de cada cinco es maestra. Se simplifican a 0,1 mm de papel.
  - `gdaldem hillshade` (sol al noroeste, a 45°) da el sombreado, y
    `gdaldem color-relief` lo pasa a un **PNG transparente**: el suelo llano no
    se ve, las laderas en sombra toman el color `shadow` del tema, y las que
    miran al sol, un poco del `highlight`. Así se pone encima de cualquier capa
    sin modos de fusión.
- **El sombreado va como `<image>` en su capa**, con el PNG dentro del SVG
  (base64), del tamaño del rectángulo del mapa. Es la única capa ráster.
- **El tema** lleva `[layers.hillshade.shade]` con `shadow`, `highlight` (que
  no son atributos SVG, sino los colores del PNG) y `opacity`, y las curvas como
  cualquier línea. `monochrome` los tinta como todo lo demás.
- **La atribución de Copernicus**, que exige su licencia, va **arriba a la
  izquierda** (en el margen de la marca), **solo si el mapa lleva relieve**.

## Razones

- **Fuentes descartadas**: SRTM pide cuenta de NASA Earthdata y OpenTopography
  una clave (regla: sin cuentas). Los *Terrain Tiles* de AWS mezclan fuentes de
  distinta calidad y obligan a decodificar PNG. Copernicus es una sola fuente,
  reciente y global.
- **Teselas enteras y no lecturas parciales** (`/vsicurl/`): más bajada la
  primera vez, pero la caché vale para cualquier mapa posterior, sin red, como
  un PBF. Y el código es más simple.
- **Las dos capas aparte**: las curvas son vector (se editan y se imprimen
  nítidas), y el sombreado da la forma del terreno de un vistazo. Cada una se
  pide sola.

## Consecuencias

- La imagen crece con GDAL. Hay que reconstruirla (`make docker`).
- **GLO-30 es un modelo de superficie (DSM)**: mide lo que hay encima del suelo,
  así que los edificios grandes y los bosques asoman como pequeños bultos en
  las curvas de un plano urbano. En el campo y a escala de comarca no se nota.
- Un SVG con sombreado pesa más: el PNG de un A4 son unos cientos de KiB, y el
  de un A0, varios MB.
- Falta, si hace falta: la cota escrita en las curvas maestras y elegir la
  equidistancia a mano.
- Los tests no tocan la red: la bajada se simula, y GDAL corre de verdad sobre
  una tesela sintética (una colina gaussiana) hecha en el propio test.
