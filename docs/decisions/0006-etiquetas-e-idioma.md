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

## Añadido del 03/11/2026: los nombres no salen por defecto

A petición del usuario, `street-names` y `places` **dejan el conjunto de capas
por defecto**, como el relieve (ADR 0008): un `make map` sin `LAYERS` dibuja
agua, verde, edificios, ferrocarril y calles, sin texto. Los nombres se añaden
con `INCLUDE_LAYERS=street-names,places` (o se piden en `LAYERS`). Lo
demás de este ADR (qué se etiqueta, el idioma, el halo) no cambia.

## Añadido del 04/11/2026: ninguna letra fuera del mapa

Un nombre de lugar se escribía si su **punto** caía dentro del mapa, sin mirar
hasta dónde llegaba el texto: «Sarela de Abaixo», a un milímetro del borde,
cruzaba el marco y acababa en el margen. Ahora:

- **Un nombre de lugar que no cabe entero no se escribe.** Su caja (el ancho
  sobreestimado de siempre, más el `letter-spacing` del tema, de 0,8 em sobre la
  línea base a 0,25 em por debajo, más medio halo) tiene que caer dentro del
  área del mapa: el rectángulo o, con `SHAPE=circle`, el círculo. No se mueve
  hacia dentro: desplazado ya no señalaría su sitio.
- **Un nombre de calle solo se escribe en el tramo que está a media letra y
  medio halo del borde** (el área del mapa encogida eso). Una calle pegada al
  borde se queda sin nombre.

Elegir entre etiquetas que se pisan sigue pendiente (TODO 1).

## Añadido del 05/11/2026: sin pisarse, el caserío y los nombres de ríos y parques

En el mapa de O Couto, el nombre del lugar («O Couto», `place=hamlet`) salía
por debajo del de un barrio suyo («O Lugar da Fonte», `place=neighbourhood`):
los dos caían en la clase `suburb` y se escribían en el orden en que llegaban de
OSM. A petición del usuario, cambian tres cosas (TODO 1):

- **`hamlet` es una clase propia de `places`**, entre `suburb` y `village`, con
  una letra de tamaño intermedio en todos los temas. Dentro de una clase, las
  reglas tienen **rango** (su orden en `layers.py`): `suburb` antes que
  `quarter` antes que `neighbourhood`. `Layer.match()` da la clase y el rango, y
  el `Item` lo lleva.
- **Los nombres no se pisan.** Se colocan de uno en uno, del más importante al
  menos (`layers.LABEL_PRIORITY`), y cada uno se queda con su sitio si está
  libre (`labels.Placer`):
  lugares (`city` > `town` > `village` > `hamlet` > `suburb`) > lagos y
  embalses > ríos > parques > reservas > calles (`major` > `secondary` >
  `minor`) > arroyos. Dentro de una clase, por rango y luego en el orden de OSM.
  El que encuentra su sitio ocupado prueba otros: un lugar, justo encima y
  justo debajo de su punto (`POINT_SHIFTS`, con un hueco de 0,3 em); un nombre a
  lo largo de una línea, otros puntos de su tramo (`SLOT_SHIFTS`). Si ninguno
  está libre, **no se escribe**. La flecha del norte cuenta como ocupada. El
  antichoque es por zona: en la superposición, los nombres de una zona no miran
  los de la otra.
- **Dos capas de texto nuevas, que no salen por defecto**: `water-names`
  (`lake`: `natural=water` sin `water=river|canal|stream|riverbank`, que se
  nombra en su línea, y `landuse=reservoir`; `river`: `waterway=river|canal`;
  `stream`: `waterway=stream`) y `green-names` (`park`:
  `leisure=park|garden`; `reserve`: `leisure=nature_reserve`). Un río se
  escribe a lo largo del cauce, como una calle; un lago o un parque, en el
  polo de inaccesibilidad (`polylabel`) de su mayor trozo en el mapa, y solo
  si el nombre cabe dentro (con media letra de holgura). Van en cursiva, del
  color del agua o del verde de cada tema.

Las rutas de los `textPath` pasan del grupo de la capa al `<defs>` de la zona:
se colocan todas las etiquetas antes de escribir ninguna capa. Lo demás de este
ADR (el idioma, el halo, que un nombre sin traducción sale tal cual) no cambia.

Siguen fuera los nombres de edificios y los puntos de interés.
