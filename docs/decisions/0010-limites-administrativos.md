# ADR 0010 — Los límites administrativos

Estado: aceptada

## Contexto

El 04/11/2026 el usuario pidió los límites administrativos: fronteras de países,
comunidades autónomas, provincias, comarcas, concellos y parroquias. Pidió que
**no salgan por defecto** y que lo más local vaya **en capas aparte**, para poder
elegir con `LAYERS` qué niveles se ven.

En OSM un límite no es una vía con etiquetas: es una **relación**
`boundary=administrative` con un `admin_level` (en España, 2 país, 4 comunidad,
6 provincia, 7 comarca, 8 municipio, 9 parroquia en Galicia), y la línea son sus
vías miembro, que casi nunca llevan el nivel. Una misma vía suele ser a la vez el
borde de una parroquia, de su concello y de la provincia.

Las capas de hasta ahora piden a Overpass la relación entera (`(._;>;)`) para que
osmium monte el polígono. Para un límite eso sería bajar **la frontera entera de
España o de Galicia**, megas de geometría que caen fuera del mapa.

## Decisión

- **Tres capas, ninguna por defecto**, de lo más local a lo más general:

  | Capa | `admin_level` | Clases |
  |---|---|---|
  | `parishes` | 9–10 | `parish` |
  | `municipalities` | 8 | `municipality` |
  | `boundaries` | 2–7 | `country` (2), `region` (3–4), `province` (5–6), `district` (7) |

  En el orden de dibujo van **encima de las calles** (un límite de parroquia va
  muchas veces por un camino o una carretera) y debajo de los nombres. Las más
  generales, encima.
- **Líneas, no polígonos**: se dibujan las vías miembro, no el área. No hay
  relleno que poner y así no hace falta la relación completa.
- **La consulta trae solo lo que se ve**: las relaciones de límite que tocan el
  mapa, **sin geometría** (solo su lista de miembros), y de sus vías solo las que
  están dentro del área, con sus nodos. Es **la misma consulta para las tres
  capas**, con todos los niveles, así que pedir las tres cuesta una sola petición
  a Overpass: la segunda y la tercera salen de la caché.
- **Con un PBF local sale lo mismo** (ADR 0002): el corte `smart` de `osmium
  extract` ya deja las relaciones que tocan el área y las vías de dentro.
- **`boundaries.py`** saca las líneas de cualquiera de los dos ficheros:
  `osmium tags-filter r/boundary=administrative` deja las relaciones de límite y
  sus vías y nodos presentes, en XML, y Python lo lee. Cada vía sale **una vez**,
  con **todos los niveles que separa** (`vectormaps:admin_levels = "6;8"`).
  `osmexport` las añade al GeoJSON de siempre, así que la caché y el resto del
  programa no cambian.
- **Un tramo compartido se dibuja una vez, en la capa más alta de las que hay en
  el mapa** (`pipeline._boundaries`). Con las tres capas, el borde de un concello
  que es también de provincia sale en `boundaries` y no se repite debajo, con
  otro trazo asomando por los huecos. Pero si se quita `boundaries`, ese tramo
  pasa a `municipalities`: **cada capa sale cerrada aunque falten las demás**.
- **Sin límites por el mar**: las vías `maritime=yes` y las de la costa
  (`natural=coastline`) no se dibujan. Las aguas territoriales no se ven en un
  mapa de tierra, y en la costa ya está el agua para marcar el borde.
- **Los tramos de cada clase se unen** (`shapely.line_merge`) para que la raya y
  punto siga de un tramo al siguiente, en vez de empezar de nuevo en cada vía.
- **Los temas** las pintan como en los mapas impresos: raya y punto, más larga y
  gruesa cuanto más alto el nivel, y la parroquia punteada. `vintage` añade
  debajo una banda violeta translúcida (`casing-opacity`, ADR 0004) y dibuja la
  parroquia en puntos redondos, para que no se confunda con los caminos.

## Alternativas descartadas

- **Una sola capa con una clase por nivel**: para quitar las parroquias habría
  que hacer un tema propio. Las capas se eligen en la línea de órdenes y las
  clases no.
- **Bajar la relación entera y montar el polígono con osmium**, como el agua: es
  lo que hacían las demás capas, pero para un país o una comunidad son megas
  inútiles en cada consulta.
- **`out geom` de Overpass**, que recorta la geometría al área: el XML no es OSM
  normal y osmium no lo lee. Y el PBF necesitaría otro camino.

## Consecuencias

- Una consulta nueva a Overpass si se pide alguna de las tres capas.
- `osmexport.VERSION` pasa a `v3`: los GeoJSON cacheados de antes se rehacen una
  vez (los `.osm` de Overpass siguen valiendo).
- Las vías de un límite que aún no está mapeado como relación no salen.
- No se escriben los nombres de las unidades (concello de Oza…). Si se quiere,
  sería otra capa de texto (ADR 0006).
