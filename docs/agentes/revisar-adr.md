# Revisar las decisiones

Procedimiento para comprobar que el código respeta las decisiones
documentadas. Lo siguen igual una persona o cualquier agente de IA; los
comandos `/revisar-adr` de cada herramienta solo apuntan aquí.

Revisa que el código cumple las decisiones de `docs/decisions/` y las reglas
de `AGENTS.md`. Si esta lista y un ADR no dicen lo mismo, manda el ADR, con sus
añadidos fechados: dilo en el informe para que se corrija la lista. Comprueba:

- **ADR 0001**: ¿algo del `Makefile` o de los scripts exige Python, osmium o
  librerías en el host? ¿Todo `docker run` lleva `-u` con `HOST_UID:HOST_GID`?
  ¿Algún target hace `chown` o necesita root? ¿`./data` y `./out` los crea
  `make` (`data-dir`)?
- **ADR 0002**: ¿ambas fuentes (`OverpassSource`, `PbfSource`) devuelven lo mismo
  y nada fuera de `sources.py` sabe de cuál se trata? ¿Overpass sigue yendo de
  una en una, con caché, `User-Agent` y espera ante 429/502/503/504 (máx. 3
  intentos)? ¿Un `runtime error` en un 200 se trata como fallo y no se cachea?
  ¿Se ha colado alguna cuenta, clave o servicio externo sin consultar?
- **ADR 0003**: ¿`area.fit` hace crecer la zona y nunca la recorta? ¿La escala
  sale de metros del terreno en UTM, no de grados? ¿El margen mínimo (6 mm)
  sigue exigido?
- **ADR 0004**: ¿el SVG va en mm, con un grupo de Inkscape por zona y por
  capa? ¿El estilo viene de los temas TOML como atributos de presentación (sin
  `<style>` ni CSS externo)? ¿Todo tema estila todas las clases de todas las
  capas (hay un test)? ¿La atribución de OSM sigue siempre en el SVG, sin
  opción para quitarla?
- **ADR 0005**: ¿la zona superpuesta usa el mismo papel, orientación y margen
  que la base? ¿Cada zona conserva su escala, tema, capas y opacidad? ¿La
  atribución lista la escala de cada zona?
- **ADR 0006**: ¿`street-names` y `places` siguen siendo capas de texto, las
  últimas en dibujarse? ¿El nombre sale de `name:<código>` y, si no hay, del
  `name` tal cual, sin traducciones inventadas? ¿`es` sigue siendo el idioma por
  defecto? ¿Se cambió `osmexport.VERSION` al cambiar lo que escribe `export`?
  ¿Algún tema deja sin estilo una clase de texto?
- **ADR 0007**: ¿el PDF sale del SVG ya escrito, con Inkscape y
  `--export-area-page`, y tiene el tamaño del papel? ¿`PDF` sigue sin admitir
  otra cosa que `1` en el `Makefile`?
- **ADR 0008**: ¿`hillshade` y `contours` siguen fuera de las capas por
  defecto? ¿Las teselas se bajan una vez, con `User-Agent` y espera ante
  429/5xx, y el mar (404) queda marcado? ¿La atribución de Copernicus sale si
  y solo si el mapa lleva relieve?
- **Tema `monochrome`** (ADR 0004): ¿sigue saliendo de `bw.toml` al cargar, con
  el negro como el tinte y el blanco blanco? ¿Un `TINT` con otro tema da error?
- **Leyenda**: ¿lleva las esquinas del mapa en el papel (no las pedidas), la
  atribución, las escalas y la marca «Generated with vector-maps by 1noro»?
  ¿Cabe en la hoja con el margen mínimo y en A5? ¿`LEGEND=minimal` sigue
  llevando `© OpenStreetMap` (y el crédito de Copernicus si hay relieve)?
- **Fuentes**: ¿`PbfSource.check` falla antes de cortar si el área está fuera
  del PBF?
- **Tests**: ¿alguno toca la red?

Informa de lo que encuentres. No arregles nada sin preguntar antes.
