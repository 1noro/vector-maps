# Imagen de desarrollo y de ejecución, la misma. El código NO se copia dentro:
# el Makefile monta el repo en /src, así que cambiarlo no obliga a reconstruir.
# Solo se reconstruye (make docker) al cambiar este fichero o los requirements.
# Ver ADR 0001.
FROM python:3.12-slim-bookworm

# osmium-tool: ensambla multipolígonos y exporta a GeoJSON (ADR 0002).
# inkscape: el PDF (PDF=1), con textPath y halos como en el SVG (ADR 0007).
# gdal-bin: curvas de nivel y sombreado desde el DEM de Copernicus (ADR 0008).
RUN apt-get update \
	&& apt-get install -y --no-install-recommends osmium-tool inkscape gdal-bin \
	&& rm -rf /var/lib/apt/lists/*

# fonts-symbola: el símbolo ⌖ de la leyenda de los mapas circulares (DejaVu no lo trae).
# Capa aparte para no repetir la de arriba al tocarla.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends fonts-symbola \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-dev.txt

# Sin .pyc en el árbol del repo; el código se importa desde el volumen.
ENV PYTHONPATH=/src/src \
	PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1
WORKDIR /src
