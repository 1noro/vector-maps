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
