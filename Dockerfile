# Imagen de desarrollo y de ejecución, la misma. El código NO se copia dentro:
# el Makefile monta el repo en /src, así que cambiarlo no obliga a reconstruir.
# Solo se reconstruye (make docker) al cambiar este fichero o los requirements.
# Ver ADR 0001.
FROM python:3.12-slim-bookworm

# osmium-tool: ensambla multipolígonos y exporta a GeoJSON (ADR 0002).
RUN apt-get update \
	&& apt-get install -y --no-install-recommends osmium-tool \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-dev.txt

# Sin .pyc en el árbol del repo; el código se importa desde el volumen.
ENV PYTHONPATH=/src/src \
	PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1
WORKDIR /src
