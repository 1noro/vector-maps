# Desarrollo

Qué queda por hacer, con el número que llevan los `TODO(N)` del código y
`AGENTS.md` ("Lo que queda"), y lo que se fue midiendo.

Cómo se relaciona con el resto de la documentación:

- **Lo que se decidió**, con sus razones, en [`decisions/`](decisions/).
- **Cómo se usa**, en [`uso.md`](uso.md).
- **Lo que cambia entre versiones**, en [`../CHANGELOG.md`](../CHANGELOG.md).

## Estado (03/11/2026)

Primera versión, 0.1.0 sin publicar: de dos esquinas a un SVG por capas, en
color y en blanco y negro, con Overpass o un PBF local, y con la superposición
de dos zonas. 40 tests, sin red.

Medido el 03/11, con el extracto de Galicia (112 MB) y Santiago de Compostela:

- A4 apaisado a 1:4120 con las cinco capas: unos 1.800 edificios, 1.250 calles
  y 170 zonas verdes; el SVG pesa ~280 KiB y sale en 3,4 s con el PBF.
- El mismo mapa, de Overpass, depende del día: ese 03/11 el servidor principal
  dio 502 y los espejos de private.coffee, VK Maps y kumi.systems, 504 o
  timeout (ADR 0002).

## TODO

1. **Etiquetas**: nombres de calles y de lugares. Hoy el SVG no lleva texto salvo
   el pie. Lo difícil: colocar el texto a lo largo de la calle y evitar
   solapes. Mejor `<textPath>` por clase y un tamaño en mm por tema.
2. **Contorno de las calles** (*casing*) en el tema de color: cada calle
   dibujada dos veces, la de abajo más ancha y oscura. Es un atributo más del
   tema (`casing-width`, `casing-color`).
3. **Puentes, túneles y más clases**: `tunnel=yes` discontinuo, `bridge=yes`
   con contorno, más tipos de `highway`/`railway`, `waterway=riverbank`.
4. **Recorte a un polígono** (GeoJSON), además del rectángulo. El
   rectángulo seguiría siendo el papel; el polígono, una máscara.
5. **Escala redonda opcional** (`--scale 1:5000`): hoy sale la que da el área.
   Fijarla recorta o amplía el área en torno al centro.
6. **Más de dos zonas superpuestas**: hoy `a` y `b`; el renderizador ya acepta
   una lista de `Job`, falta la sintaxis.
