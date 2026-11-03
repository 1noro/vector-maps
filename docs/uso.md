# Uso

Todo se lanza con `make`; por debajo, `python -m vectormaps` dentro de Docker.
La primera vez, `make` construye la imagen sola; `make docker` la reconstruye.

## `make map`

```bash
make map TL=lat,lon BR=lat,lon [PAPER=A4] [ORIENTATION=auto] [MARGIN=10] \
         [LAYERS=water,roads] [THEME=color] [PBF=ruta] [OUT=out/map.svg]
```

| Variable | Defecto | Qué hace |
|---|---|---|
| `TL`, `BR` | (obligatorias) | Esquinas arriba-izquierda y abajo-derecha, `LAT,LON` en grados |
| `PAPER` | `A4` | `A0`, `A1`, `A2`, `A3`, `A4` o `A5` |
| `ORIENTATION` | `auto` | `landscape`, `portrait`, o la que más se parezca al área |
| `MARGIN` | `10` | Mm de margen. Mínimo 6: ahí va la atribución |
| `LAYERS` | todas | `water,green,buildings,railways,roads`, separadas por comas |
| `THEME` | `color` | `color`, `bw`, o la ruta de un `.toml` propio |
| `PBF` | (Overpass) | Extracto local `.osm.pbf` en vez de Overpass |
| `OUT` | `out/map.svg` | Fichero de salida |

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

Para un cartel minimalista, `LAYERS=roads`; para un plano de situación,
`LAYERS=water,green,roads`.

### Temas

Un tema es un `.toml` en `src/vectormaps/themes/` (o cualquiera por ruta, con
`THEME=ruta.toml`). Cada `[layers.<capa>.<clase>]` lleva atributos SVG tal cual
(`fill`, `stroke`, `stroke-width` en mm…). Para uno propio, copia `bw.toml` y
cámbialo: un test exige que estile todas las clases de todas las capas.

- **`color`**: fondo crema, agua azul, verde, calles blancas y naranjas.
- **`bw`**: solo grises y negro, sin grandes superficies negras (tinta) y con
  anchos legibles en papel.

## Superponer dos zonas

Añade `TL2` y `BR2` (van juntas): una segunda zona sobre la primera, en la
**misma hoja** (mismo papel, orientación y margen) y **con su propia escala**.

| Variable | Defecto | Qué hace |
|---|---|---|
| `TL2`, `BR2` | — | Esquinas de la zona de encima |
| `LAYERS2` | las de `LAYERS` | Capas de la zona de encima |
| `THEME2` | el de `THEME` | Tema de la zona de encima |
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
  Otro servidor: `OVERPASS_URL=https://… make map …`.
- **PBF local**: `make pbf URL=https://download.geofabrik.de/…-latest.osm.pbf`
  lo baja a `data/pbf/`; luego, `PBF=data/pbf/<fichero>`. Recomendado para
  zonas grandes y para la superposición (el doble de consultas). El corte de
  cada zona se cachea. Los extractos están en
  [download.geofabrik.de](https://download.geofabrik.de/).

`make clean-cache` borra `data/cache/` (no los PBF); `make clean-out`, `out/`.

## Imprimir

El SVG está en milímetros: a 100 % se imprime al tamaño del papel elegido.
Para PDF: `inkscape out/mapa.svg --export-type=pdf`, o imprime desde
Inkscape/el navegador sin escalar ("tamaño real"). Hasta A2 un navegador
basta; A1/A0, en un servicio de impresión de planos, con el PDF. Los grosores
están pensados para papel; 0,1 mm es ya un trazo muy fino (comprueba tu impresora con una prueba).
