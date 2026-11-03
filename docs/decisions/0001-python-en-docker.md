# ADR 0001 — Python, y todo dentro de Docker

Estado: aceptada

## Contexto

El proyecto convierte datos de OpenStreetMap en SVG. Se barajaron Python, Go y
Node (mapshaper + osm-to-svg), además de QGIS en modo headless y de la pila
Mapnik/osm-carto (la de MapOSMatic). Se pidió que el host no necesite ninguna
librería y que el SVG acabe en el host con el usuario de siempre.

## Decisión

**Python 3.12 con `shapely` y `pyproj`, en una sola imagen Docker** que también
lleva `osmium-tool`. El repo se monta en `/src` y el contenedor corre con el
uid:gid del usuario del host.

## Razones

- **La geometría es lo difícil** (recortar, proyectar, ensamblar multipolígonos)
  y Shapely/pyproj la resuelven. En Go habría que hacerla a mano.
- **Node** (mapshaper, osm-to-svg) da menos control del estilo de impresión:
  grosores en mm, orden de capas, atribución. `osm-to-svg` es además muy
  joven (4 estrellas, sin colores ni capas).
- **Mapnik/osm-carto/MapOSMatic** exigen PostGIS e importar con osm2pgsql: mucho
  más peso del que merece un script de mapas.
- **QGIS headless** exporta bien, pero la imagen es enorme y configurarlo
  desde un Makefile es incómodo.
- **No se copia código de `prettymaps`** (AGPL-3.0): solo se tomó la idea de
  "una capa por consulta de etiquetas".
- El código no se copia a la imagen sino que se monta: cambiarlo no obliga a
  reconstruir. La imagen se reconstruye (`make docker`) solo si cambian el
  `Dockerfile` o los `requirements*.txt`.

## Consecuencias

- En el host solo hacen falta `make` y `docker`.
- `./data` (cachés, PBF) y `./out` (SVG) son del usuario del host: los crea
  `make` y los contenedores corren con su uid:gid. Nada de `chown` ni root.
- Las versiones van fijadas en `requirements*.txt`.
