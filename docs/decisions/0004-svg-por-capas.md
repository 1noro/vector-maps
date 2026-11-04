# ADR 0004 — SVG en mm, un grupo por capa, estilo por atributos

Estado: aceptada

## Contexto

El SVG se imprime en color o en blanco y negro, y se abre en Inkscape y otros
editores para retocarlo.

## Decisión

- **Unidades en milímetros**: `width="210mm"`, `viewBox="0 0 210 297"`. Un
  `stroke-width="0.35"` es 0,35 mm en papel, sea cual sea la escala.
- **Un grupo por zona y por capa**, marcados `inkscape:groupmode="layer"`, con
  ids estables (`a-roads`, `b-water`…). Dentro, **un `<path>` por clase**
  (`a-roads-major`): menos elementos que uno por rasgo, y editable por clase.
- **El estilo son atributos de presentación** (`fill`, `stroke`,
  `stroke-width`…) copiados de un **tema TOML** (`themes/color.toml`,
  `themes/bw.toml`, o cualquier `.toml` por ruta). Sin `<style>` ni CSS
  externo.
- **El blanco y negro es otro tema**, no una conversión: solo grises y negro,
  sin grandes superficies negras (tinta) y con anchos legibles en papel.
- **La atribución** "© OpenStreetMap contributors (ODbL)" y las escalas van en
  el margen y en `<title>`, siempre, sin opción para quitarlas.
- Orden de dibujo fijo: agua, verde, edificios, ferrocarril, calles; dentro de
  cada capa, de la clase menos a la más importante.

## Razones

- Los atributos se respetan en Inkscape, Illustrator, navegadores y en
  convertidores a PDF; el CSS embebido, no siempre.
- Un tema TOML se retoca sin tocar código, y un test comprueba que estila todas
  las clases de todas las capas.
- ODbL permite el mapa como obra producida con cualquier licencia, pero exige
  la atribución.

## Consecuencias

- Lo que se pierde: estilos condicionales por etiqueta. Si hacen falta
  (puentes, túneles), son clases nuevas en la capa (TODO 3).
- Los polígonos usan `fill-rule="evenodd"` para los agujeros (islas, patios).

## Añadido del 03/11/2026: la leyenda

El pie del mapa pasa a ser una **leyenda** (capa `legend` en el SVG), en dos
líneas en el margen de abajo:

1. La atribución de OSM, el papel y la escala de cada zona.
2. **Las esquinas** `↖ lat, lon · ↘ lat, lon`, con 5 decimales (~1 m). Son las
   del **mapa tal como está en el papel**, no las que se pidieron: la zona
   crece hasta la forma de la hoja (ADR 0003), y son esas las que se ven.
   Pasadas de vuelta a `TL` y `BR` dan el mapa entero, pero **no el mismo**:
   sale un ~2 % más alejado (1,8–2,5 % medido en A0–A4). En UTM el rectángulo
   lat/lon entre esas dos esquinas queda algo girado, y como la zona crece y
   nunca se recorta, su caja envolvente es un poco mayor que el papel. Para
   repetir un mapa exacto, se repiten las esquinas que se pidieron. Con dos
   zonas se listan las dos, `A: … | B: …`.

Y, arriba a la derecha, en el margen de arriba, **la marca**: «Generated with
vector-maps by 1noro». El tamaño del texto se reduce solo si el margen o la
línea más larga lo piden (los A5 y los márgenes de 6 mm); nunca se sale de la
hoja.

## Añadido del 03/11/2026: el tema `monochrome`, tintado

`THEME=monochrome` es **el tema `bw` tintado de un color**, que se da en
hexadecimal con `TINT=#1f3b5c` (`--tint`; el `#` es opcional y vale la forma
corta `#fa0`). No es un `.toml` más: se construye al cargar, a partir de
`bw.toml`, así que cualquier cambio en `bw` le llega solo.

- Cada color del tema se pasa a su **luminosidad** y se lleva a la misma
  luminosidad del tinte: **el negro se vuelve el tinte y el blanco sigue
  blanco** (el papel y el halo de las etiquetas), y los grises, tonos claros
  del tinte. Anchos, discontinuas y fuentes no cambian.
- Sin `TINT`, un azul oscuro (`#1f3b5c`). Un `TINT` con otro tema es un error:
  tintar el de color daría otra cosa que no se ha pedido.
- En una superposición, `TINT2` es el de la zona de encima; si no se da y esa
  zona también es `monochrome`, hereda el `TINT`.
- El estilo sigue yendo como atributos de presentación (lo decidido arriba):
  el SVG lleva ya los colores tintados, no un filtro.

## Añadido del 03/11/2026: la leyenda mínima

`LEGEND=minimal` (`--legend minimal`) deja la leyenda en lo justo: una línea abajo
con las esquinas, la escala de cada zona y `© OpenStreetMap`, y la marca arriba.
Sin el papel, la orientación ni el «contributors (ODbL)».

- **La atribución de OSM no se quita** (decisión 5): el usuario pidió quitarla y
  se le consultó; se queda en la forma corta, que las normas de atribución de
  OSM aceptan. Sigue sin haber opción para quitarla del todo.
- Con relieve, el crédito de Copernicus (ADR 0008) sigue saliendo igual.
- La leyenda completa sigue siendo la de por defecto.
