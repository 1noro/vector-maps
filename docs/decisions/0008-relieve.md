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

## Añadido del 04/11/2026: spline cúbico, no bilineal

El DEM se remuestreaba a la rejilla del mapa (`CELL_MM`, 0,25 mm de papel) con
**bilineal**. Entre cuatro valores, la bilineal es casi un plano, con una sola
pendiente por celda, y el sombreado depende de la pendiente: a escala de pueblo
(1:12000, donde 30 m son ~2,4 mm) cada celda salía como **un cuadro de un solo
tono** y las curvas se quebraban en cada borde de celda.

Ahora `gdalwarp -r cubicspline` (`relief.RESAMPLING`): una superficie suave, sin
aristas, sobre la que la pendiente cambia poco a poco. No inventa detalle (sigue
siendo el DEM de 30 m), pero ya no lo enseña en cuadros. A escalas pequeñas,
donde una celda del mapa abarca varias del DEM, apenas cambia nada.

El método va en la clave de la caché (`frame-….tif`), así que los DEM de antes no
se reusan; `make clean-cache` borra los viejos.

## Añadido del 04/11/2026: el texto exacto de Copernicus, y discreto en la leyenda mínima

El usuario pidió acortar la atribución de Copernicus con `LEGEND=minimal`, como
se acorta la de OSM («© OpenStreetMap»). **No se puede**: la licencia del DEM
(según el Copernicus Data Space) da dos textos fijos y ninguna forma corta, uno
para el DEM sin tocar y otro para lo modificado o derivado. El sombreado y las
curvas son derivados, así que corresponde el segundo, y el que escribíamos no
era exactamente ese. Ahora:

- El texto es **«Relief produced using Copernicus WorldDEM-30 © DLR e.V.
  2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under
  COPERNICUS by the European Union and ESA; all rights reserved»**: el de la
  licencia, palabra por palabra, con «Relief» delante para decir qué se derivó.
- Con **`LEGEND=minimal`** va **entero, pero al 70 % del tamaño de la leyenda y
  con opacidad 0,6**, y su largo ya no cuenta para el tamaño del resto (antes
  encogía también la marca y las esquinas). Con `LEGEND=full`, como siempre.

## Añadido del 04/11/2026: relieve rayado

El usuario quería que `vintage` dibujara el relieve como las hojas topográficas
antiguas, con rayas y no con un sombreado que parece 3D. Se probaron en borrador
cinco estilos sobre Cecebre (normales de pendiente, bandas de pendiente, rayado
de las laderas en sombra, curvas de Tanaka y punteado), y eligió **bandas de
pendiente**: rayas paralelas donde el terreno pasa de cierto ángulo, una tanda
más por cada banda más empinada.

- Es **otra forma de dibujar la capa `hillshade`**, no una capa nueva: la elige
  el tema con `style = "hatch"` y una lista `bands` en
  `[layers.hillshade.shade]`; sin `style`, sigue la imagen sombreada de siempre.
  Por eso el pipeline entrega ahora el DEM del mapa y es el render el que saca de
  él el sombreado o la pendiente.
- **La pendiente** sale de `gdaldem slope` sobre el DEM del mapa (en UTM, así
  que en grados reales) y se cachea a su lado (`frame-….-slope.tif`). Se lee como
  rejilla con numpy y cada raya se recorre en pasos de 0,12 mm, partiéndola donde
  la pendiente baja del umbral.
- **Es vectorial**: un `<path>` por banda (`a-hillshade-band-1`…), que se
  recorta con el marco como lo demás. Crece con el papel y con lo montañoso (un A4
  apaisado de Cecebre, unos 175 KiB de rayas), pero se imprime nítido a cualquier
  tamaño.
- Lleva la misma atribución de Copernicus: sigue siendo un derivado del DEM.
- `monochrome` tiñe los colores de las bandas como los de las tramas.
