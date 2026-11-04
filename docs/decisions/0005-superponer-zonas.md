# ADR 0005 — Superponer dos zonas en la misma hoja

Estado: aceptada

## Contexto

El 03/11/2026 el usuario pidió poder superponer dos zonas del mapa, una encima
de otra, para combinarlas y ver cómo queda. No tienen por qué tener el mismo
zoom, pero sí la misma forma (cuadrado, rectángulo, A4…).

## Decisión

- Una ejecución de `map` pasa de una zona a **dos**: la base (`--tl/--br`) y la
  superpuesta (`--over-tl/--over-br`, las dos juntas).
- **Misma forma = mismo papel, orientación y margen.** La zona superpuesta se
  ajusta con `area.fit` a la orientación de la base. Como `fit` hace crecer cada
  zona hasta la forma del papel (ADR 0003), las dos ocupan exactamente el mismo
  rectángulo de la hoja, cada una **con su propia escala**.
- Cada zona es un `Job` con **sus capas** (`--over-layers`, por defecto las de
  la base), **su tema** (`--over-theme`: p. ej. color debajo y bw encima) y
  **su opacidad** (`--over-opacity`, 0–1, un `opacity` en su grupo).
- En el SVG: `area-a` y `area-b`, cada una con sus grupos de capa (ids con
  prefijo `a-`/`b-`), dibujadas en ese orden; la página y el marco, una sola vez
  (con el fondo y la tinta del tema de la base).
- La atribución lista la escala de cada zona (`A 1:4120 + B 1:888`).
- Desde el 04/11/2026 la zona de encima también puede darse por centro y radio
  (`--over-center`/`--over-radius`) y comparte la forma de la hoja (`--shape`,
  ADR 0003): las dos zonas son cuadrados o círculos del mismo tamaño en el papel.

## Razones

- Obligar a la misma forma de hoja evita decidir dónde "caería" una zona de otra
  forma, y es lo que se pidió.
- Apilar grupos de Inkscape deja ocultar, mover o borrar una zona entera desde
  el editor sin regenerar nada.
- Tema y capas por zona permiten el uso típico: contexto en color y detalle en
  blanco y negro, o solo calles del detalle sobre el contexto completo.

## Consecuencias

- Hoy son dos zonas, `a` y `b`. Más de dos pide una sintaxis nueva; el
  renderizador ya acepta una lista de `Job`.
- Una zona de otra forma que la base crece más (el log lo avisa).
- Cada zona hace sus propias consultas: con Overpass, el doble de peticiones
  (cacheadas), por eso conviene el PBF para superponer.
