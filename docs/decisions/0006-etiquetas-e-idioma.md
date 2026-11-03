# ADR 0006 — Etiquetas de calles y lugares, con idioma elegible

Estado: aceptada

## Contexto

El 03/11/2026 el usuario pidió que el mapa lleve los nombres de las carreteras
y de los lugares, pudiendo elegir el idioma, y el castellano por defecto.

## Decisión

- **Dos capas nuevas, de texto**: `street-names` (el nombre de las calles,
  escrito a lo largo de la calle) y `places` (ciudades, pueblos, aldeas y
  barrios, en su punto). Se dibujan las últimas y entran en el conjunto por
  defecto; `LAYERS=` las quita.
- **Qué se etiqueta**: de las calles, las clases `major`, `secondary` y `minor`
  que tengan `name`; de los lugares, `place=city|town|village|suburb|quarter|
  neighbourhood|hamlet`. Una capa, una consulta, con `["name"]` en la propia
  consulta (Overpass no devuelve lo que luego se tiraría).
- **El idioma** es `--lang` / `LABEL_LANG`, por código de OSM (`es`, `gl`, `en`,
  `ja`, `zh-Hans`…), **`es` por defecto**. Puede ser una lista (`gl,es`): gana la
  primera con `name:<código>`; si ninguna lo tiene, **el `name` tal como está
  en OSM**. `local` fuerza el `name` sin traducir.
- **Dónde va el texto de las calles**: OSM parte cada calle en vías en cada
  cruce, así que se unen las de un mismo nombre (`line_merge`) y se escribe el
  nombre en tramos cortos (un tramo por cada 6 anchos de texto) con `<textPath>`,
  orientados para leerse de izquierda a derecha. **Se descartan los tramos
  más cortos que el texto** y los que serpentean, para no escribir sobre una
  curva cerrada.
- **El estilo es del tema** como el resto (ADR 0004): `font-size` en mm, relleno
  y un **halo** blanco (`stroke` + `paint-order="stroke"`) para que se lea
  encima de calles y edificios.
- `osmium export` pasa a sacar también **puntos** (`--geometry-types=point,…`).
  Los ficheros exportados en caché llevan la versión del export en el nombre
  (`osmexport.VERSION`), para no servir los de antes, que no tenían puntos.

## Razones

- Un idioma por código de OSM es lo que hay: `name:es`, `name:gl`… En Galicia
  la mayoría de las calles solo tienen `name` (en gallego): con `es` salen tal
  cual, y con `gl,es` o `local` no cambia nada. Lo honesto es mostrar lo que hay
  y no inventar una traducción.
- Un `textPath` sobre un tramo propio por etiqueta deja a cada nombre su
  trazado, editable en Inkscape, sin tener que calcular rotaciones.
- Sobreestimar el ancho del texto (0,62 em por carácter): si el trazado es más
  corto que el texto, `textPath` descarta las letras que no caben.

## Límites conocidos

- **No hay antichoque**: dos nombres pueden pisarse (calles que se cruzan, un
  nombre de calle sobre uno de lugar). Es el TODO 1 de `docs/desarrollo.md`.
- Los nombres de parques, ríos o edificios no están: solo calles y lugares.
- **`rsvg-convert` (librsvg) no soporta `textPath`**: con él las calles salen sin
  nombre. Inkscape y los navegadores sí. Para comprobar un SVG, Inkscape.
- Con un `local`/idioma sin traducciones en Asia, los nombres salen en su
  escritura; la tipografía la pone el visor (`sans-serif`).

## Consecuencias

- Cada zona añade dos consultas de Overpass; con el PBF, nada (salen del mismo
  corte).
- Un tema nuevo tiene que estilar `street-names` y `places` (hay un test).
