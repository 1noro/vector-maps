# ADR 0003 — El área son dos esquinas y un papel ISO A

Estado: aceptada

## Contexto

Los mapas se imprimen siempre en rectángulos A5, A4, A3, A2, A1 o A0. No hace
falta interfaz gráfica.

## Decisión

- El área se da con **dos esquinas WGS84**, `--tl=LAT,LON` (arriba-izquierda)
  y `--br=LAT,LON` (abajo-derecha). Se valida que el orden sea el correcto.
- **El papel** es A0–A5, con orientación `auto` (apaisado si el área es más
  ancha que alta), `landscape` o `portrait`, y un margen (10 mm; mínimo 6).
- **La zona crece, nunca se recorta**: el rectángulo pedido se amplía por el
  lado corto, centrado, hasta tener la forma exacta de la parte imprimible del
  papel (`Frame.growth` dice cuánto). Así se ve siempre lo que se pidió.
- **Proyección UTM local** (la zona sale del centro del área), en metros: la
  escala es real. `Frame.scale` es el N de 1:N; no se redondea.

## Razones

- La forma de una hoja ISO A es fija (1:√2): una caja libre casi nunca encaja.
  Ampliar es lo único que no esconde nada.
- Web Mercator distorsiona la escala con la latitud; UTM, no, a esta escala.
- Dos esquinas es lo más simple y reproducible; centro+radio, nombre de lugar
  (Nominatim) y polígono GeoJSON se descartaron por ahora (TODO 4).

## Consecuencias

- Una zona con otra forma que el papel sale con más margen del pedido por un
  lado; el log lo dice ("grown 11% to fit the paper").
- Una esquina negativa se pasa con `--tl=-33.8,151.2` (con el igual) para que
  argparse no la tome por un flag. El `Makefile` ya lo hace.

## Añadido el 04/11/2026 — centro y radio

Se admite una segunda forma de dar el área: **`--center=LAT,LON` y
`--radius=KM`** (`CENTER`/`RADIUS` en `make`; `--over-center`/`--over-radius`
para la zona superpuesta). Excluyente con `--tl`/`--br`.

- Se convierte en las dos esquinas del **cuadrado de lado 2R** centrado (en
  UTM), y de ahí sigue `fit` como siempre. El círculo de radio R queda inscrito
  en ese cuadrado, así que **se ve siempre entero** y el papel añade mapa por el
  lado largo: sigue sin recortarse nada.
- Un área casi cuadrada (el lado corto, al menos el 95 % del largo) es un
  empate y `auto` elige apaisado: la conversión a lat/lon y vuelta la deja unos
  puntos por encima o por debajo y no debe decidir la orientación.

## Añadido el 04/11/2026 — forma del mapa en la hoja

Aparte del papel, **`--shape=rect|square|circle`** (`SHAPE` en `make`; `rect`
por defecto, como hasta ahora). La misma forma vale para las dos zonas
superpuestas.

- `rect`: el mapa llena la parte imprimible y la zona crece a su forma.
- `square` y `circle`: el mapa es una **caja cuadrada centrada** de lado el lado
  corto de la parte imprimible. `Frame` distingue ahora el margen de la página
  de la caja del mapa (`map_x`, `map_y`, `map_w`, `map_h`); los datos, el relieve
  y la escala se calculan solo sobre la caja.
- Sigue sin recortarse lo pedido: el **cuadrado** lleva el lado largo del área;
  el **círculo es el circunscrito** (diámetro = diagonal del rectángulo). Con
  `--center`/`--radius` el cuadrado mide 2R y el círculo es exactamente el de
  radio R.
- El círculo se recorta con un `<clipPath>` en el grupo de cada zona (se puede
  soltar en Inkscape) y lleva un trazo fino del borde; lo de fuera queda con el
  fondo del tema. La leyenda y la atribución siguen en el margen de la hoja.
- `Frame.growth` con un círculo o cuadrado compara su área con la del rectángulo
  pedido (un círculo circunscrito crece al menos un 57 %); con un radio es 0.

## Añadido del 04/11/2026: apaisado y 6 mm por defecto

A petición del usuario, la orientación por defecto pasa a ser **`landscape`**
(antes `auto`) y el margen, **6 mm** (antes 10, y sigue siendo el mínimo).
`ORIENTATION=auto` sigue eligiendo la que más se parezca al área. Lo demás de
este ADR no cambia.

## Añadido del 04/11/2026: el rectángulo también se recorta

Las geometrías se cortan en el borde del mapa (`clip_by_rect`), pero el trazo se
pinta alrededor de la línea: el remate redondo de una calle cortada en el borde
(`stroke-linecap="round"`), su contorno (ADR 0004) o una calle paralela al marco
y muy pegada **asomaban medio grosor por fuera del marco**. Se veía sobre todo
con los temas oscuros y las calles anchas.

Ahora **todas las formas llevan el `<clipPath>`** en el grupo de cada zona, no
solo el círculo: en `rect` y `square` es el rectángulo del mapa (`map_x`,
`map_y`, `map_w`, `map_h`). Se suelta en Inkscape igual que el del círculo. El
marco sigue dibujándose encima, fuera del recorte.

## Añadido del 05/11/2026: la banda del título

Con `--title` (`TITLE` en `make`), **la parte imprimible pierde por arriba una
banda para el título**: `fit(..., titled=True)` la mide como un 7 % del lado
corto del papel, con un tope de 40 mm, y `Frame.title_band` la guarda (0 sin
título). `print_h` ya la descuenta, y `map_y` cuenta desde debajo de ella; el
centro de la caja (`map_cx`, `map_cy`) deja de ser el de la hoja, y el círculo
se centra ahí.

Lo demás no cambia: con `rect` la zona **crece** hasta la forma nueva, más
apaisada, y con `square` y `circle` la caja es el cuadrado que cabe debajo de la
banda. Las dos zonas superpuestas llevan la misma banda, porque comparten la
página. Se eligió una banda propia, y no el margen ni una cartela sobre el mapa,
porque es la única posición en la que el título no puede chocar con la leyenda,
la marca ni la flecha, y en la que cabe una letra de título de verdad: con el
margen de 6 mm, en el margen solo caben unos 4 mm de letra.
