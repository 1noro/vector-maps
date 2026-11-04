# Uso

Todo se lanza con `make`; por debajo, `python -m vectormaps` dentro de Docker.
La primera vez, `make` construye la imagen sola; `make docker` la reconstruye.
`make` a secas (o `make help`) enseña los objetivos y las variables de `make map`.

## `make wizard`

Lo mismo que `make map`, pero guiado: pregunta cada opción (área, papel, capas,
estilo, superposición, datos y salida), con listas para elegir y casillas para
las capas, y antes de generar enseña el `make map …` equivalente.

```bash
make wizard
```

Recuerda las respuestas en `data/wizard.json`. La segunda vez va directo a un
menú con el último mapa: **generar** otra vez, **cambiar una sección** (por
ejemplo, solo el tema) o repasar todas las preguntas. Así, probar variantes es
cambiar una cosa y volver a generar. La memoria solo se guarda cuando el mapa
sale bien; para empezar de cero, borra `data/wizard.json`.

- Ctrl-C en mitad de una sección la deja como estaba; en el menú, sale.
- El nombre del fichero de salida se pregunta (se propone el último): si no
  lo cambias, se sobrescribe.
- Si el mapa falla (unas esquinas al revés, Overpass caído), sale el error y
  vuelves al menú.
- Necesita una terminal; desde un script, `make map`.

## `make map`

```bash
make map TL=lat,lon BR=lat,lon [PAPER=A4] [SHAPE=rect] [ORIENTATION=landscape] [MARGIN=6] \
         [LAYERS=water,roads] [INCLUDE_LAYERS=places] [EXCLUDE_LAYERS=railways] [THEME=bw] [TINT=#1f3b5c] [LABEL_LANG=es] [PBF=ruta] \
         [OUT=out/map.svg] [PDF=0] [LEGEND=full] [COORDS=dms]

# o el área por centro y radio (km), en vez de TL y BR:
make map CENTER=lat,lon RADIUS=km [PAPER=A4] [SHAPE=circle] …
```

| Variable | Defecto | Qué hace |
|---|---|---|
| `TL`, `BR` | (una de las dos formas) | Esquinas arriba-izquierda y abajo-derecha, `LAT,LON` en grados |
| `CENTER`, `RADIUS` | (la otra forma) | Centro `LAT,LON` y radio en km, en vez de `TL`/`BR`. El círculo de ese radio se ve siempre entero; el papel añade más mapa por el lado largo. No se mezclan con `TL`/`BR` |
| `PAPER` | `A4` | `A0`, `A1`, `A2`, `A3`, `A4` o `A5` |
| `SHAPE` | `rect` | Cómo se imprime el mapa en el papel (aparte del papel): `rect` llena la hoja; `square` es un cuadrado centrado y `circle` un círculo centrado, los dos tan anchos como el lado corto de la hoja. El círculo lleva un borde fino y lo de fuera queda en blanco. Con `circle` y `TL`/`BR` el círculo contiene todo el rectángulo (su diámetro es la diagonal); con `CENTER`/`RADIUS` es exactamente el de radio R |
| `ORIENTATION` | `landscape` | `landscape`, `portrait`, o `auto`: la que más se parezca al área |
| `MARGIN` | `6` | Mm de margen. Mínimo 6: ahí va la atribución |
| `LAYERS` | todas menos el relieve, los límites y los nombres | `water,green,buildings,railways,roads,street-names,places`, `hillshade,contours` (relieve) y `parishes,municipalities,boundaries` (límites), separadas por comas |
| `INCLUDE_LAYERS` | — | Capas que añadir a `LAYERS` (o a las de por defecto): `INCLUDE_LAYERS=street-names,places` |
| `EXCLUDE_LAYERS` | — | Capas que quitar de `LAYERS` (o de las de por defecto): `EXCLUDE_LAYERS=railways` |
| `LABEL_LANG` | `es` | Idioma de los nombres de calles y lugares, por código de OSM: `es`, `gl`, `en`, `ja`… Varios, `gl,es`: gana el primero que tenga traducción; `local` = como está mapeado |
| `THEME` | `bw` | `bw`, `color`, `street`, `dark`, `blueprint`, `vintage`, `vintage-bw`, `poster`, `monochrome`, o la ruta de un `.toml` propio |
| `TINT` | `#1f3b5c` | Color del tema `monochrome`, en hexadecimal (`#` opcional) |
| `PBF` | (Overpass) | Extracto local `.osm.pbf` en vez de Overpass |
| `OUT` | `out/map.svg` | Fichero de salida |
| `PDF` | `1` | Además del SVG, un PDF del tamaño del papel al lado (`out/map.pdf`). `PDF=0`: solo el SVG |
| `COORDS` | `dms` | Formato de las coordenadas de la leyenda: `dd` grados decimales (`42.88000, -8.54000`), `dm` grados y minutos decimales (`42°52.800'N 8°32.400'W`) o `dms` grados, minutos y segundos (`42°52'48.0"N 8°32'24.0"W`) |
| `LEGEND` | `minimal` | `minimal`: solo las esquinas, la escala, `© OpenStreetMap` y la marca; `full`: también el papel y la atribución larga |

La zona pedida **se amplía, nunca se recorta**, hasta tener la forma del papel;
el log dice cuánto ("grown 11 % to fit the paper") y la escala (`1:4120`).

### Capas

`make list` las enseña con sus clases. Se dibujan siempre en este orden, de
abajo arriba, y dentro de cada una, de la clase menos a la más importante:

| Capa | Clases |
|---|---|
| `green` | `green` |
| `water` | `water`, `stream`, `canal`, `river` |
| `hillshade` | `shade` (imagen o rayado; no sale por defecto) |
| `contours` | `minor`, `major` (no sale por defecto) |
| `buildings` | `building` |
| `railways` | `tram`, `rail` |
| `roads` | `path`, `service`, `minor`, `secondary`, `major` |
| `parishes` | `parish` (límites; no sale por defecto) |
| `municipalities` | `municipality` (límites; no sale por defecto) |
| `boundaries` | `district`, `province`, `region`, `country` (límites; no sale por defecto) |
| `street-names` | `minor`, `secondary`, `major` (texto; no sale por defecto) |
| `places` | `suburb`, `village`, `town`, `city` (texto; no sale por defecto) |

Las dos últimas son **etiquetas**: se dibujan encima de todo y salen en el idioma
de `LABEL_LANG`. **No salen por defecto**; para un mapa con nombres,
`INCLUDE_LAYERS=street-names,places`. Para un mapa sin el tren,
`EXCLUDE_LAYERS=railways`; para un cartel minimalista, `LAYERS=roads`; para un
plano de situación, `LAYERS=water,green,roads`.

Las tres se combinan: las de `LAYERS` (o las de por defecto), más las de
`INCLUDE_LAYERS`, menos las de `EXCLUDE_LAYERS`, y siempre en el orden de dibujo.
Añadir una que ya está o quitar una que no está no hace nada; un nombre que no
existe, la misma capa en `INCLUDE_LAYERS` y en `EXCLUDE_LAYERS`, o no dejar
ninguna, es un error.

### Límites administrativos

Tres capas, **ninguna por defecto**, de lo más local a lo más general:

- `parishes`: las parroquias (`admin_level` 9–10).
- `municipalities`: los concellos o municipios (8).
- `boundaries`: países (2), comunidades (3–4), provincias (5–6) y comarcas (7).

```bash
make map TL=… BR=… INCLUDE_LAYERS=boundaries,municipalities,parishes
```

Las tres usan **una sola consulta a Overpass**, que trae solo los tramos que se
ven, no la frontera entera. Un tramo que es a la vez de varias (el borde de un
concello que es también de provincia) se dibuja una vez, en la capa más alta de
las que pidas; si quitas esa, pasa a la siguiente, así que cada capa sale
cerrada sola. Los límites por el mar y por la costa no se dibujan. Los temas las
pintan en raya y punto, más gruesas cuanto más alto el nivel (ADR 0010).

### Relieve

`hillshade` (sombreado) y `contours` (curvas de nivel) **no salen por defecto**:
se añaden con `INCLUDE_LAYERS` (o se piden en `LAYERS`), por ejemplo

```bash
make map TL=… BR=… INCLUDE_LAYERS=hillshade,contours
```

- Salen del **DEM Copernicus GLO-30** (30 m), no de OSM. La primera vez se baja la
  tesela de 1°×1° que cubre la zona (~40 MB cada una) a `data/cache/dem/`; luego
  vale para cualquier mapa dentro, sin red. No pide cuenta ni clave.
- **Las curvas** van cada 5 m en un plano de ciudad, 10 m a 1:25.000, y más
  separadas cuanto menor sea la escala; una de cada cinco, más gruesa.
- **El sombreado** es una imagen dentro del SVG: el suelo llano queda
  transparente y solo se oscurecen las laderas en sombra (y se aclaran un poco
  las que miran al sol), así que se ve sobre cualquier capa. Sus colores son
  `shadow` y `highlight` del tema.
- **O rayado**, si el tema pone `style = "hatch"` en `[layers.hillshade.shade]`:
  rayas vectoriales sobre las laderas, más densas cuanto más empinadas, como en
  los mapas antiguos. Cada banda de `bands` raya donde la pendiente pasa de
  `slope` grados, con rayas a `spacing` mm, `angle`, `width`, `color` y `offset`
  (para intercalarla con otra del mismo ángulo). Lo usa `vintage`:

  ```toml
  [layers.hillshade.shade]
  style = "hatch"
  bands = [
    { slope = 6, spacing = 0.9, angle = 30, width = 0.08, color = "#c8643c" },
    { slope = 12, spacing = 0.9, angle = 30, width = 0.08, color = "#c8643c", offset = 0.45 },
    { slope = 20, spacing = 0.6, angle = -30, width = 0.09, color = "#8a3a1e" },
  ]
  ```
- Con relieve, el margen de arriba lleva a la izquierda la **atribución de
  Copernicus**, que exige su licencia.
- El DEM mide la superficie (con edificios y árboles): en un plano urbano las
  curvas tienen pequeños bultos. Por qué y qué alternativas se miraron, en el
  ADR 0008.

### Temas

Un tema es un `.toml` en `src/vectormaps/themes/` (o cualquiera por ruta, con
`THEME=ruta.toml`). Cada `[layers.<capa>.<clase>]` lleva atributos SVG tal cual
(`fill`, `stroke`, `stroke-width` en mm…). Una línea puede llevar además
`casing-width` (mm a cada lado) y `casing-color`: un contorno, la misma línea más
ancha por debajo; con `casing-opacity`, translúcido (la banda de los límites de
`vintage`). Un relleno puede ser una trama: `fill = "pattern:<nombre>"`, con
la trama definida en `[patterns.<nombre>]` (`kind = "lines"`, rayas a `spacing` mm
con `angle`, `width`, `color`, `background` y, si se quiere, trazos de `dash` mm;
o `kind = "dots"`, puntos de `radius`); `vintage.toml` trae tres de ejemplo.
También vale en `stroke`: `vintage-bw` raya así el interior de las calles principales.
Para uno propio, copia `bw.toml` y
cámbialo: un test exige que estile todas las clases de todas las capas.

- **`color`**: fondo crema, agua azul, verde, calles blancas y naranjas, con un
  contorno fino.
- **`street`**: a la manera de los callejeros web: suelo gris claro, agua azul
  cielo, verde suave, edificios grises, calles blancas con contorno gris y las
  principales amarillas con contorno ocre.
- **`dark`**: un mapa de noche: suelo azul marino, agua casi negra, verde
  apagado, edificios pizarra, calles grises y principales ámbar. Para pantalla o
  imprenta: en una impresora de casa gasta mucha tinta.
- **`blueprint`**: un plano de arquitecto, líneas blancas sobre azul. Los
  edificios son solo contorno y las calles, doble línea (el color del fondo sobre
  un contorno blanco). También gasta mucha tinta.
- **`vintage`**: una hoja topográfica del siglo XIX: papel crema, agua clara con
  líneas finas que siguen la orilla por dentro (los ríos entran en el embalse
  como una sola masa de agua), prados en trazos verdes, edificios rayados,
  calles en doble línea negra (las principales rellenas de ocre y amarillo) y
  todos los nombres en cursiva (EB Garamond). Con el relieve
  (`INCLUDE_LAYERS=hillshade,contours`) las laderas salen rayadas en rojo, como
  en aquellas hojas.
- **`vintage-bw`**: el `vintage` pensado para una impresora en blanco y negro:
  solo negro sobre blanco, sin grises ni transparencias (una láser los convierte
  en puntos). Lo distinguen las tramas y el grosor: agua rayada (los ríos y
  canales entran en el embalse como un solo cuerpo rayado), prados punteados,
  edificios rayados, calles en doble línea (las principales rayadas por dentro),
  el tren en tramos blancos y negros y el relieve en rayas negras finas, con las
  curvas secundarias punteadas.
- **`poster`**: la ciudad en líneas, para enmarcar: calles negras sobre blanco,
  cada clase con su grosor, y agua suave; parques y edificios no se pintan (sus
  grupos siguen en el SVG). Muy bonito con `SHAPE=circle`.
- **`bw`** (el de por defecto): solo grises y negro, sin grandes superficies
  negras (tinta) y con anchos legibles en papel. El agua es un solo gris sin
  borde, superficies y líneas, para que un río se funda con sus tramos anchos;
  los arroyos son continuos y las discontinuas, solo caminos.
- **`monochrome`**: el `bw` tintado del color de `TINT`: el negro pasa a ser ese
  color, los grises sus tonos claros y el blanco sigue blanco. Por ejemplo,
  `THEME=monochrome TINT=#7a2e1f` para un granate. Sin `TINT`, azul oscuro.

### Idioma de los nombres

OSM guarda el nombre local en `name` y las traducciones en `name:es`, `name:gl`,
`name:en`… Con `LABEL_LANG=es` (el defecto) se usa `name:es` si existe y, si no,
`name` **tal cual**: no se inventa nada. En Galicia casi todo está mapeado solo en
gallego, así que muchas calles salen como "Rúa do Pombal" aunque pidas `es`;
`LABEL_LANG=gl,es` da gallego donde lo haya y castellano donde no, y
`LABEL_LANG=local` es siempre el nombre mapeado.

Los nombres de las calles se escriben a lo largo de la calle (`textPath`), en
tramos que quepan: una calle corta o muy curva se queda sin nombre. Dos nombres
pueden pisarse: no hay antichoque todavía (TODO 1).

> **Para ver el SVG, Inkscape o un navegador.** `rsvg-convert` (librsvg) no pinta
> los `textPath`: con él las calles salen sin nombre.

### La leyenda

Por defecto, la leyenda es la mínima (`LEGEND=minimal`, más abajo). Con
`LEGEND=full`, el margen de abajo lleva dos líneas: la atribución de OSM con el papel y la
escala, y las **esquinas `TL` y `BR` del mapa tal como está en el papel** (no
las que pediste: la zona crece hasta la forma de la hoja). Pasadas de vuelta a
`TL`/`BR` dan el mapa entero pero un ~2 % más alejado, por cómo se proyecta el
rectángulo; para repetir un mapa exacto, repite las esquinas que pediste. El
margen de arriba, a la derecha, lleva la marca
«Generated with vector-maps by 1noro». Con dos zonas se listan las dos esquinas. Con `SHAPE=circle` no hay esquinas que dar: la leyenda lleva en su lugar las
coordenadas del centro del mapa, `⌖ lat, lon`.

Con `LEGEND=minimal`, la de por defecto, el pie se queda en una sola línea, sin
el papel ni la orientación:

```
↖ 43.29888, -8.32043 · ↘ 43.27792, -8.27935 · 1:12102 · © OpenStreetMap
```

y la marca arriba. `© OpenStreetMap` no se puede quitar: la licencia de los
datos (ODbL) pide que el mapa lo diga (ADR 0004).

### El norte

Todo mapa lleva, arriba a la derecha dentro del mapa, una **flecha al norte**: media
en tinta y media en el color del papel, con una «N» en la letra de los nombres
del tema y un halo para leerse sobre cualquier cosa. Apunta al **norte
geográfico**, no al de la cuadrícula: el mapa se dibuja en UTM, cuyo norte se
separa de los meridianos cuanto más lejos del meridiano central del huso (medio
grado en Cecebre, hasta ~2,5° al borde del huso). Su tamaño va con el del mapa,
hasta 24 mm. Está en su propia capa de Inkscape, `north`.

## Superponer dos zonas

Añade `TL2` y `BR2` (van juntas; o `CENTER2` y `RADIUS2`): una segunda zona sobre la primera, en la
**misma hoja** (mismo papel, orientación, margen y `SHAPE`) y **con su propia escala**.

| Variable | Defecto | Qué hace |
|---|---|---|
| `TL2`, `BR2` | — | Esquinas de la zona de encima |
| `CENTER2`, `RADIUS2` | — | O su centro y su radio (km), en vez de las esquinas |
| `LAYERS2` | las de la zona de abajo | Capas de la zona de encima |
| `THEME2` | el de `THEME` | Tema de la zona de encima |
| `TINT2` | el de `TINT` | Color, si la zona de encima es `monochrome` |
| `INCLUDE_LAYERS2` | — | Capas que añadir a la zona de encima |
| `EXCLUDE_LAYERS2` | — | Capas que quitar de la zona de encima |
| `OPACITY2` | `1` | Opacidad, de 0 a 1 |

Consejos: con edificios muy ampliados la zona de encima tapa mucho. Prueba
`LAYERS2=roads,water` (solo calles y agua del detalle), una opacidad menor, o
un tema distinto para distinguir las dos. La atribución del pie dice las dos
escalas (`A 1:4120 + B 1:888`).

En el SVG hay un grupo `area-a` y otro `area-b`; abre el fichero en Inkscape
(Capas, `Ctrl+Mayús+L`) para ocultar, mover o borrar una zona entera.

## Datos

- **Overpass** (por defecto): una consulta por capa y zona, cacheada en
  `data/cache/overpass/`. El servidor público limita y **se cae a veces**; el
  programa espera y reintenta hasta 3 veces, y lo ya descargado no se repite.
  Otro servidor: `OVERPASS_URL=https://… make map …`. **Si acaba fallando**:
  si ya tienes en `data/pbf/` un PBF que cubre el área (todas las zonas), `make
  map` **sigue solo con él** y lo avisa (`Overpass failed (layer water: …);
  drawing every layer from the local extract …`); ojo, sus datos pueden ser de
  otra fecha. Un fallo no se cachea: la siguiente vez se vuelve a pedir esa capa
  a Overpass (y a esperar) antes de pasar al extracto; para ir directo, añade
  `PBF=`. El log dice de dónde sale cada capa:
  `layer water: 58 features (local extract galicia-latest.osm.pbf)` u
  `(Overpass)`. Nunca baja un extracto
  por su cuenta. Si no hay ninguno que sirva, el error dice qué extracto de
  Geofabrik bajar, con el comando:

  ```
  error: Overpass answered HTTP 504
  hint: work offline with the Kantō region extract, downloaded once:
    make pbf URL=https://download.geofabrik.de/asia/japan/kanto-latest.osm.pbf
    and repeat the same `make map` adding PBF=data/pbf/kanto-latest.osm.pbf
  ```

  Un PBF trae todas las capas de su región, no una sola: se baja una vez y vale
  para cualquier mapa dentro de ella.
- **PBF local**: `make pbf URL=https://download.geofabrik.de/…-latest.osm.pbf`
  lo baja a `data/pbf/`; luego, `PBF=data/pbf/<fichero>`. Recomendado para
  zonas grandes y para la superposición (el doble de consultas). El corte de
  cada zona se cachea. **El área tiene que estar dentro del PBF**: si no (Tokio con
  el de Galicia), falla antes de empezar y dice qué rango cubre el fichero; si solo
  cabe en parte, avisa del porcentaje. Los extractos están en
  [download.geofabrik.de](https://download.geofabrik.de/).

`make clean-cache` borra `data/cache/` (no los PBF); `make clean-out`, `out/`.

## Imprimir

El SVG está en milímetros: a 100 % se imprime al tamaño del papel elegido.
Por defecto (**`PDF=1`**; `PDF=0` lo quita) queda al lado un PDF del tamaño del papel (con Inkscape, dentro de la
imagen; ADR 0007), con los nombres de las calles y el texto seleccionable.
Imprímelo sin escalar ("tamaño real"). Hasta A2 un navegador o un visor de PDF
basta; A1/A0, en un servicio de impresión de planos, con el PDF. Los grosores
están pensados para papel; 0,1 mm es ya un trazo muy fino (comprueba tu impresora con una prueba).
