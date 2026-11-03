.PHONY: docker pbf check test lint fmt map list shell data-dir clean-cache clean-out
.SILENT: data-dir

# Todo corre dentro de Docker: en el host solo hacen falta make y docker. Ver
# ADR 0001. El repo se monta en /src y el contenedor corre con el uid:gid de
# quien lanza make, así que lo que escribe (./out, ./data) es del usuario y se
# puede leer y borrar desde fuera sin sudo.
IMAGE := vector-maps:dev

export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)

DOCKER_RUN = docker run --rm \
	-u $(HOST_UID):$(HOST_GID) \
	-e HOME=/tmp \
	-e OVERPASS_URL \
	-v $(CURDIR):/src \
	-w /src \
	$(IMAGE)

# La imagen se construye sola la primera vez; `make docker` la reconstruye
# (al cambiar el Dockerfile o los requirements).
docker:
	docker build -t $(IMAGE) .

.image:
	docker image inspect $(IMAGE) >/dev/null 2>&1 || docker build -t $(IMAGE) .

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

# make map TL=lat,lon BR=lat,lon [PAPER=A4] [THEME=color|bw] [LAYERS=water,roads]
#          [ORIENTATION=auto|landscape|portrait] [MARGIN=10] [OUT=out/map.svg]
# Datos: por defecto Overpass; con PBF=ruta.osm.pbf, desde un extracto local.
# Y, para superponer una segunda área encima (mismo papel, otro zoom):
#          [TL2=lat,lon BR2=lat,lon] [LAYERS2=…] [THEME2=…] [OPACITY2=0.6]
# Se pasa con `--tl=` (con el igual) para que una latitud negativa no se lea como flag.
map: .image data-dir
	test -n "$(TL)" -a -n "$(BR)" || { echo "faltan TL y BR: make map TL=lat,lon BR=lat,lon" >&2; exit 1; }
	$(DOCKER_RUN) python -m vectormaps map \
		--tl="$(TL)" --br="$(BR)" \
		$(if $(PAPER),--paper $(PAPER)) \
		$(if $(ORIENTATION),--orientation $(ORIENTATION)) \
		$(if $(MARGIN),--margin $(MARGIN)) \
		$(if $(LAYERS),--layers $(LAYERS)) \
		$(if $(THEME),--theme $(THEME)) \
		$(if $(OUT),--out $(OUT)) \
		$(if $(PBF),--pbf $(PBF)) \
		$(if $(TL2),--over-tl="$(TL2)") $(if $(BR2),--over-br="$(BR2)") \
		$(if $(LAYERS2),--over-layers $(LAYERS2)) \
		$(if $(THEME2),--over-theme $(THEME2)) \
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
