# Desarrollo

Qué queda por hacer, con el número que llevan los `TODO(N)` del código y
`AGENTS.md` ("Lo que queda"), y lo que se fue midiendo.

Cómo se relaciona con el resto de la documentación:

- **Lo que se decidió**, con sus razones, en [`decisions/`](decisions/).
- **Cómo se usa**, en [`uso.md`](uso.md).
- **Lo que cambia entre versiones**, en [`../CHANGELOG.md`](../CHANGELOG.md).

## Estado (04/11/2026)

Primera versión, 0.1.0 sin publicar: de dos esquinas (o un centro y un radio) a un SVG por capas, en
color y en blanco y negro, con nombres de calles y lugares en el idioma elegido,
con Overpass o un PBF local, con la superposición de dos zonas, relieve opcional
(curvas y sombreado, ADR 0008), PDF, mapa en rectángulo, cuadrado o círculo
(ADR 0003) y fallback automático a un PBF local si Overpass falla (ADR 0002).
160 tests, sin red. Desde el 04/11, también `make wizard` (ADR 0009).

Medido el 03/11, con el extracto de Galicia (112 MB) y Santiago de Compostela:

- A4 apaisado a 1:4120 con las cinco capas: unos 1.800 edificios, 1.250 calles
  y 170 zonas verdes; el SVG pesa ~280 KiB y sale en 3,4 s con el PBF.
- El mismo mapa, de Overpass, depende del día: ese 03/11 el servidor principal
  dio 502 y los espejos de private.coffee, VK Maps y kumi.systems, 504 o
  timeout (ADR 0002).

## TODO

1. **Etiquetas sin pisarse** y más nombres. Desde el 03/11 hay nombres de calles
   (`textPath`) y de lugares (ADR 0006), pero sin antichoque: dos nombres pueden
   solaparse. Falta además el nombre de parques, ríos y edificios y los puntos de
   interés. Lo difícil: decidir qué etiqueta gana (por clase y tamaño) y mover
   o quitar la otra.
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
7. **Buscar el área por nombre en el wizard** («Santiago de Compostela»), con
   Nominatim: elegir entre los resultados y sacar el área por centro y radio.
   Es un servicio nuevo de red, y respeta lo mismo que Overpass: una petición
   cada vez, caché, `User-Agent` propio y nada de claves (ADR 0002, 0009).

## Carencias menores

Salieron en la revisión del 03/11. Ninguna estropea un mapa normal; no llevan
número porque no hay `TODO` en el código.

- **El mensaje de espera de Overpass confunde.** «waiting 30 s» va seguido del
  spinner de la capa, que cuenta el tiempo de la capa entera (intentos y
  esperas), no la espera: parece que no se cumple. Mejor algo como
  `HTTP 502, attempt 2/3 in 30 s` (`overpass.py`).
- **El aviso de área grande sale también con PBF** y habla del Overpass público
  (`pipeline.py`, `LARGE_AREA_DEG2`). Debería depender de la fuente.
- **Los lugares mapeados como área no salen**: las reglas de `places` solo
  cogen nodos, y muchos barrios y parroquias son polígonos en OSM
  (`layers.py`).
- **`make pbf` deja el `.part`** si la descarga falla a medias (`download.py`).
- **Dos `make map` a la vez** comparten los temporales de la caché (`x.tmp`) y
  pueden pisarse; y «una petición cada vez» a Overpass se cumple dentro de un
  proceso, no entre dos.
- `render()` escribe el fondo, la tinta y el grosor del marco del tema sin
  escapar, a diferencia del resto de estilos.
- `fill-rule="evenodd"` se pone también en las líneas, donde no hace nada.
- `--over-layers`, `--over-theme` y `--over-opacity` sin `--over-tl` se ignoran
  sin avisar (`cli.py`).
- Un tema `.toml` sin `[page]` o `[layers]` da un `KeyError` con traza en vez de
  un mensaje que diga qué falta (`theme.py`).
