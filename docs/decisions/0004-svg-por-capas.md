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
