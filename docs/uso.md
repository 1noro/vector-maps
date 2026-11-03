# Uso

Todo se lanza con `make`; por debajo, `python -m vectormaps` dentro de Docker.
La primera vez, `make` construye la imagen sola; `make docker` la reconstruye.
`make` a secas (o `make help`) enseña los objetivos y las variables de `make map`.

## `make map`

```bash
make map TL=lat,lon BR=lat,lon [PAPER=A4] [ORIENTATION=auto] [MARGIN=10] \
         [LAYERS=water,roads] [THEME=color] [TINT=#1f3b5c] [LABEL_LANG=es] [PBF=ruta] \
         [OUT=out/map.svg] [PDF=1]
```

| Variable | Defecto | Qué hace |
|---|---|---|
| `TL`, `BR` | (obligatorias) | Esquinas arriba-izquierda y abajo-derecha, `LAT,LON` en grados |
| `PAPER` | `A4` | `A0`, `A1`, `A2`, `A3`, `A4` o `A5` |
| `ORIENTATION` | `auto` | `landscape`, `portrait`, o la que más se parezca al área |
| `MARGIN` | `10` | Mm de margen. Mínimo 6: ahí va la atribución |
| `LAYERS` | todas | `water,green,buildings,railways,roads,street-names,places`, separadas por comas |
| `LABEL_LANG` | `es` | Idioma de los nombres de calles y lugares, por código de OSM: `es`, `gl`, `en`, `ja`… Varios, `gl,es`: gana el primero que tenga traducción; `local` = como está mapeado |
| `THEME` | `color` | `color`, `bw`, `monochrome`, o la ruta de un `.toml` propio |
| `TINT` | `#1f3b5c` | Color del tema `monochrome`, en hexadecimal (`#` opcional) |
| `PBF` | (Overpass) | Extracto local `.osm.pbf` en vez de Overpass |
| `OUT` | `out/map.svg` | Fichero de salida |
| `PDF` | — | `PDF=1`: además, un PDF del tamaño del papel al lado (`out/map.pdf`) |

La zona pedida **se amplía, nunca se recorta**, hasta tener la forma del papel;
el log dice cuánto ("grown 11 % to fit the paper") y la escala (`1:4120`).

### Capas

`make list` las enseña con sus clases. Se dibujan siempre en este orden, de
abajo arriba, y dentro de cada una, de la clase menos a la más importante:

| Capa | Clases |
|---|---|
| `water` | `water`, `stream`, `canal`, `river` |
| `green` | `green` |
| `buildings` | `building` |
| `railways` | `tram`, `rail` |
| `roads` | `path`, `service`, `minor`, `secondary`, `major` |
| `street-names` | `minor`, `secondary`, `major` (texto) |
| `places` | `suburb`, `village`, `town`, `city` (texto) |

Las dos últimas son **etiquetas**: se dibujan encima de todo y salen en el idioma
de `LABEL_LANG`. Para un mapa sin nombres, `LAYERS=water,green,buildings,railways,roads`;
para un cartel minimalista, `LAYERS=roads`; para un plano de situación,
`LAYERS=water,green,roads`.

### Temas

Un tema es un `.toml` en `src/vectormaps/themes/` (o cualquiera por ruta, con
`THEME=ruta.toml`). Cada `[layers.<capa>.<clase>]` lleva atributos SVG tal cual
(`fill`, `stroke`, `stroke-width` en mm…). Para uno propio, copia `bw.toml` y
cámbialo: un test exige que estile todas las clases de todas las capas.

- **`color`**: fondo crema, agua azul, verde, calles blancas y naranjas.
- **`bw`**: solo grises y negro, sin grandes superficies negras (tinta) y con
  anchos legibles en papel.
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

El margen de abajo lleva dos líneas: la atribución de OSM con el papel y la
escala, y las **esquinas `TL` y `BR` del mapa tal como está en el papel** (no
las que pediste: la zona crece hasta la forma de la hoja). Pasadas de vuelta a
`TL`/`BR` dan el mapa entero pero un ~2 % más alejado, por cómo se proyecta el
rectángulo; para repetir un mapa exacto, repite las esquinas que pediste. El
margen de arriba, a la derecha, lleva la marca
«Generated with vector-maps by 1noro». Con dos zonas se listan las dos esquinas.

## Superponer dos zonas

Añade `TL2` y `BR2` (van juntas): una segunda zona sobre la primera, en la
**misma hoja** (mismo papel, orientación y margen) y **con su propia escala**.

| Variable | Defecto | Qué hace |
|---|---|---|
| `TL2`, `BR2` | — | Esquinas de la zona de encima |
| `LAYERS2` | las de `LAYERS` | Capas de la zona de encima |
| `THEME2` | el de `THEME` | Tema de la zona de encima |
| `TINT2` | el de `TINT` | Color, si la zona de encima es `monochrome` |
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
  Otro servidor: `OVERPASS_URL=https://… make map …`. **Si acaba fallando, el
  error dice cómo seguir en local**: si ya tienes un PBF que cubre el área, que
  repitas el mismo `make map` con `PBF=` ese fichero; si no, qué extracto de
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
**`PDF=1`** deja al lado un PDF del tamaño del papel (con Inkscape, dentro de la
imagen; ADR 0007), con los nombres de las calles y el texto seleccionable.
Imprímelo sin escalar ("tamaño real"). Hasta A2 un navegador o un visor de PDF
basta; A1/A0, en un servicio de impresión de planos, con el PDF. Los grosores
están pensados para papel; 0,1 mm es ya un trazo muy fino (comprueba tu impresora con una prueba).
