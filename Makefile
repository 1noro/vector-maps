.PHONY: help docker .image pbf check test lint fmt map list shell data-dir clean-cache clean-out

# Las recetas no se muestran: el log solo lleva lo que dicen los programas. Lo
# que tarda (construir la imagen) va con un spinner (scripts/with-spinner.sh).
.SILENT:

# `make` a secas enseña la ayuda (y no construye nada).
.DEFAULT_GOAL := help

# Al añadir un objetivo o una variable de `make map`, añadirlo aquí también.
define HELP
vector-maps: mapas de OpenStreetMap en SVG por capas, para imprimir.

Uso: make <objetivo> [VARIABLE=valor …]

  map      un mapa:  make map TL=lat,lon BR=lat,lon [opciones]
           o por centro y radio:  make map CENTER=lat,lon RADIUS=km [opciones]
             (el círculo de ese radio se ve siempre entero; no se mezcla con TL/BR)
             PAPER=A4            A0…A5
             SHAPE=rect          cómo se imprime en el papel: rect, square, circle
             ORIENTATION=auto    auto, landscape, portrait
             MARGIN=10           mm (mínimo 6)
             LAYERS=a,b          capas (sin relieve ni nombres por defecto; make list)
             INCLUDE_LAYERS=a,b  capas que añadir a LAYERS (o a las de por defecto)
             EXCLUDE_LAYERS=a,b  capas que quitar de LAYERS (o de las de por defecto)
             THEME=color         color, bw, monochrome, o un .toml
             TINT=#1f3b5c        color de THEME=monochrome
             LABEL_LANG=es       idioma de los nombres (es, gl, en…; local)
             OUT=out/map.svg     fichero de salida
             PDF=1               también un PDF del tamaño del papel
             LEGEND=minimal      leyenda corta: esquinas, escala, © OpenStreetMap y marca
             COORDS=dd           coordenadas de la leyenda: dd (42.88000, -8.54000),
                                 dm (42°52.800'N 8°32.400'W), dms (42°52'48.0"N 8°32'24.0"W)
             PBF=data/pbf/x.osm.pbf   datos de un extracto local, no de Overpass
                                 (sin PBF, si Overpass falla y un extracto de data/pbf/
                                 cubre el área, se usa solo, con aviso)
           superponer otra zona encima (mismo papel, otro zoom):
             TL2=lat,lon BR2=lat,lon (o CENTER2=lat,lon RADIUS2=km)
             [LAYERS2=…] [INCLUDE_LAYERS2=…]
             [EXCLUDE_LAYERS2=…] [THEME2=…] [TINT2=…] [OPACITY2=0.7]
           nombres y relieve no salen por defecto; se añaden con INCLUDE_LAYERS:
             INCLUDE_LAYERS=street-names,places        nombres de calles y lugares
             INCLUDE_LAYERS=hillshade,contours         relieve (baja ~40 MB/grado² la 1.ª vez)
  pbf      bajar un extracto:  make pbf URL=https://download.geofabrik.de/…-latest.osm.pbf
  list     capas, papeles y temas

  check    lint + tests (lo que hay que pasar)
  test, lint, fmt
  docker   reconstruir la imagen (al cambiar el Dockerfile o los requirements)
  shell    una shell dentro de la imagen
  clean-cache, clean-out   borrar data/cache/ u out/

Ejemplo:
  make map TL=42.8845,-8.5510 BR=42.8775,-8.5385 THEME=bw PDF=1 OUT=out/santiago.svg

Más: docs/uso.md
endef
export HELP

help:
	echo "$$HELP"

# Todo corre dentro de Docker: en el host solo hacen falta make y docker. Ver
# ADR 0001. El repo se monta en /src y el contenedor corre con el uid:gid de
# quien lanza make, así que lo que escribe (./out, ./data) es del usuario y se
# puede leer y borrar desde fuera sin sudo.
IMAGE := vector-maps:dev

export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)

# Con terminal, el contenedor también la tiene: así el spinner de Python se dibuja.
TTY := $(shell [ -t 2 ] && echo -t)

DOCKER_RUN = docker run --rm $(TTY) \
	-u $(HOST_UID):$(HOST_GID) \
	-e HOME=/tmp \
	-e OVERPASS_URL \
	-v $(CURDIR):/src \
	-w /src \
	$(IMAGE)

# La imagen se construye sola la primera vez; `make docker` la reconstruye
# (al cambiar el Dockerfile o los requirements).
docker:
	scripts/with-spinner.sh "Construyendo la imagen $(IMAGE)" docker build -t $(IMAGE) .

.image:
	docker image inspect $(IMAGE) >/dev/null 2>&1 || \
		scripts/with-spinner.sh "Construyendo la imagen $(IMAGE) (solo la primera vez, tarda unos minutos)" docker build -t $(IMAGE) .

# Crea ./data y ./out como el usuario del host: si no los crearía Docker al
# montar, como root, y el contenedor no podría escribir.
data-dir:
	test "$(HOST_UID)" != 0 || { echo "no lances make como root: ./data y ./out quedarían de root" >&2; exit 1; }
	mkdir -p data/cache out
	ajenos="$$(find data out -maxdepth 2 ! -user $(HOST_UID) 2>/dev/null)"; \
	if [ -n "$$ajenos" ]; then \
		echo "estos ficheros no son de tu usuario (uid $(HOST_UID)):" >&2; \
		echo "$$ajenos" | sed 's/^/  /' >&2; \
		exit 1; \
	fi

test: .image
	$(DOCKER_RUN) pytest -q

lint: .image
	$(DOCKER_RUN) ruff check .
	$(DOCKER_RUN) ruff format --check .

fmt: .image
	$(DOCKER_RUN) ruff check --fix .
	$(DOCKER_RUN) ruff format .

# Lo que hay que pasar antes de dar por buena una tarea.
check: lint test

list: .image
	$(DOCKER_RUN) python -m vectormaps list

# make map TL=lat,lon BR=lat,lon [PAPER=A4]   (o el área por centro y radio: CENTER=lat,lon RADIUS=km) [THEME=color|bw] [LAYERS=water,roads]
#          [INCLUDE_LAYERS=street-names,places]   (añadir capas a LAYERS o a las de por defecto)
#          [EXCLUDE_LAYERS=railways]   (quitar capas de LAYERS o de las de por defecto)
#          [SHAPE=rect|square|circle]   (cómo se imprime el mapa en el papel; por defecto rect)
#          [ORIENTATION=auto|landscape|portrait] [MARGIN=10] [OUT=out/map.svg]
#          [LABEL_LANG=es]   (idioma de los nombres: es, gl, en… o varios: gl,es)
#          [PDF=1]           (además del SVG, un PDF del tamaño del papel al lado)
#          [COORDS=dd|dm|dms]  (formato de las coordenadas de la leyenda; por defecto dd)
#          [LEGEND=minimal]  (solo esquinas, escala, © OpenStreetMap y la marca; ADR 0004)
#          [THEME=monochrome TINT=#1f3b5c]   (el bw tintado de un color; # opcional)
# Datos: por defecto Overpass; con PBF=ruta.osm.pbf, desde un extracto local.
# Y, para superponer una segunda área encima (mismo papel, otro zoom):
#          [TL2=lat,lon BR2=lat,lon | CENTER2=lat,lon RADIUS2=km] [LAYERS2=…] [INCLUDE_LAYERS2=…] [EXCLUDE_LAYERS2=…]
#          [THEME2=…] [TINT2=…] [OPACITY2=0.6]
# El relieve (hillshade, contours) y los nombres (street-names, places) no salen por
# defecto: se añaden con INCLUDE_LAYERS o se piden en LAYERS (ADR 0006 y 0008).
# Se pasa con `--tl=` (con el igual) para que una latitud negativa no se lea como flag.
map: .image data-dir
	test \( -n "$(TL)" -a -n "$(BR)" \) -o \( -n "$(CENTER)" -a -n "$(RADIUS)" \) || { echo "falta el área: TL=lat,lon BR=lat,lon, o CENTER=lat,lon RADIUS=km" >&2; exit 1; }
	# PDF y PBF se confunden al teclear: PDF solo admite 1.
	test -z "$(PDF)" -o "$(PDF)" = 1 || { echo "PDF=1 añade el PDF; para un extracto local es PBF=$(PDF)" >&2; exit 1; }
	$(DOCKER_RUN) python -m vectormaps map \
		$(if $(TL),--tl="$(TL)") $(if $(BR),--br="$(BR)") \
		$(if $(CENTER),--center="$(CENTER)") $(if $(RADIUS),--radius $(RADIUS)) \
		$(if $(PAPER),--paper $(PAPER)) \
		$(if $(ORIENTATION),--orientation $(ORIENTATION)) \
		$(if $(MARGIN),--margin $(MARGIN)) \
		$(if $(SHAPE),--shape $(SHAPE)) \
		$(if $(LAYERS),--layers $(LAYERS)) \
		$(if $(INCLUDE_LAYERS),--include-layers $(INCLUDE_LAYERS)) \
		$(if $(EXCLUDE_LAYERS),--exclude-layers $(EXCLUDE_LAYERS)) \
		$(if $(THEME),--theme $(THEME)) \
		$(if $(TINT),--tint="$(TINT)") \
		$(if $(LABEL_LANG),--lang $(LABEL_LANG)) \
		$(if $(OUT),--out $(OUT)) \
		$(if $(PDF),--pdf) \
		$(if $(LEGEND),--legend $(LEGEND)) \
		$(if $(COORDS),--coords $(COORDS)) \
		$(if $(PBF),--pbf $(PBF)) \
		$(if $(TL2),--over-tl="$(TL2)") $(if $(BR2),--over-br="$(BR2)") \
		$(if $(CENTER2),--over-center="$(CENTER2)") $(if $(RADIUS2),--over-radius $(RADIUS2)) \
		$(if $(LAYERS2),--over-layers $(LAYERS2)) \
		$(if $(INCLUDE_LAYERS2),--over-include-layers $(INCLUDE_LAYERS2)) \
		$(if $(EXCLUDE_LAYERS2),--over-exclude-layers $(EXCLUDE_LAYERS2)) \
		$(if $(THEME2),--over-theme $(THEME2)) \
		$(if $(TINT2),--over-tint="$(TINT2)") \
		$(if $(OPACITY2),--over-opacity $(OPACITY2))

# make pbf URL=https://download.geofabrik.de/europe/spain/galicia-latest.osm.pbf
# Deja el extracto en ./data/pbf, y luego: make map … PBF=data/pbf/galicia-latest.osm.pbf
pbf: .image data-dir
	test -n "$(URL)" || { echo "falta URL: make pbf URL=https://…/región-latest.osm.pbf" >&2; exit 1; }
	$(DOCKER_RUN) python -m vectormaps download "$(URL)"

shell: .image
	docker run --rm -it -u $(HOST_UID):$(HOST_GID) -e HOME=/tmp -v $(CURDIR):/src -w /src $(IMAGE) bash

clean-cache:
	rm -rf data/cache

clean-out:
	rm -rf out
