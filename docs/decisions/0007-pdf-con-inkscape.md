# ADR 0007 — El PDF, con Inkscape

Estado: aceptada

## Contexto

El 03/11/2026 el usuario pidió que `make map` pueda dejar, además del SVG, un
**PDF del tamaño del papel** al lado. El SVG sigue siendo el resultado (ADR
0004); el PDF es una copia para imprimir o mandar a una imprenta.

El SVG usa dos cosas que no todos los conversores pintan: el texto a lo largo
de las calles (`<textPath>`) y el halo de las etiquetas (`paint-order="stroke"`,
el trazo blanco detrás de la letra).

## Decisión

- **`PDF=1`** (`--pdf`) escribe `<OUT>.pdf` junto al SVG, con el mismo nombre.
  El PDF sale **del SVG ya escrito**, así que son el mismo mapa.
- Lo convierte **Inkscape** (`inkscape --export-type=pdf --export-area-page`),
  instalado en la misma imagen. El tamaño de página es el `width`/`height` en
  mm del SVG: el del papel elegido.
- El texto queda como texto, con la fuente incrustada (DejaVu): se puede buscar
  y seleccionar en el PDF.
- Como `PDF` y `PBF` se confunden al teclear, `PDF` solo admite `1`, y el
  `Makefile` avisa si se le pasa otra cosa.

## Razones

Probado el 03/11 con el mismo mapa de Santiago, en A4:

| Conversor | `textPath` | Halo (`paint-order`) | Imagen |
|---|---|---|---|
| `rsvg-convert` (librsvg) | **no**: calles sin nombre | sí | +~10 MB |
| CairoSVG 2.7 | sí | **no**: el halo tapa la letra; el nombre de la ciudad sale en blanco | +~50 MB |
| Inkscape 1.2 (Debian) | sí | sí | **+~300 MB** (288 → 586 MB) |

- Inkscape es el único que lo pinta todo igual que el SVG, y es con lo que ya
  se comprueban los mapas (el SVG por capas está pensado para él).
- **Cambiar el SVG para que valga CairoSVG** (dibujar el halo como una copia
  del texto debajo) duplicaría cada etiqueta al editar el mapa en Inkscape.
  No compensa.
- Un navegador sin cabeza (Chromium) también vale, pero pesa más que Inkscape
  y no añade nada.

## Consecuencias

- La imagen pesa el doble y su primera construcción tarda más. Hay que
  reconstruirla (`make docker`) para tener el PDF.
- Un test convierte un SVG diminuto con Inkscape de verdad (como osmium en los
  de las fuentes) y comprueba el tamaño de página.
- El PDF no se cachea: se rehace con el SVG, en un segundo o dos para un A4.
