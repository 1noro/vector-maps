# ADR 0009 — El wizard en la terminal

Estado: aceptada

## Contexto

El 04/11/2026 el usuario pidió una forma guiada de hacer mapas: `make map`
tiene ya más de veinte variables y, para probar variantes (otro papel, otro
tema, una zona superpuesta), hay que acordarse de cómo se llama cada una. El
comando tenía que seguir existiendo tal cual.

## Decisión

- **`make wizard`** (`python -m vectormaps wizard`) hace las preguntas por
  secciones: área, papel, capas, estilo, superposición, datos y salida.
- **El wizard no dibuja nada**: convierte las respuestas en el mismo `argv` de
  `vectormaps map` y llama a `cli.main`. Las comprobaciones y los mensajes de
  error son los de la CLI. Antes de generar enseña el **`make map …`
  equivalente**, con solo lo que no es el valor por defecto, para copiarlo o
  aprenderlo.
- **Recuerda las respuestas** en `data/wizard.json` (del usuario, fuera de
  git), y las guarda solo cuando un mapa sale bien. La primera vez se pasa por
  todas las preguntas; las siguientes, se va directo a un menú con la última
  configuración: generar, cambiar una sección o repasarlo todo. Un fichero
  ilegible o de una versión anterior no es un error: se aprovecha lo que se
  pueda y el resto vuelve a su valor por defecto.
- **Ctrl-C** en mitad de una sección la deja como estaba y vuelve al menú; en el
  menú, sale. Un mapa que falla enseña el error y también vuelve al menú.
- La librería es **questionary** (2.1, sobre `prompt_toolkit`), con las
  versiones fijadas en `requirements.txt`. Las preguntas, como todo lo que
  emite el programa, van en inglés.
- El `Makefile` lanza el contenedor con `-it` (el resto, solo con `-t`) y se
  niega con un mensaje si no hay terminal.

## Razones

- **Un solo camino hasta el mapa.** Si el wizard validara por su cuenta, las
  dos formas acabarían diciendo cosas distintas. Las preguntas solo validan lo
  que se puede comprobar al escribir (una esquina `LAT,LON`, un número, un
  color), y para eso usan las mismas funciones (`parse_corner`, `parse_langs`,
  `parse_tint`).
- **questionary** da listas con flechas, casillas para las capas y validación al
  escribir con muy poco código, y solo arrastra `prompt_toolkit` (y `wcwidth`).
  Se descartaron:
  - **solo la stdlib** (`input()`): sin dependencias, pero elegir capas
    escribiendo nombres es justo lo que se quería evitar;
  - **Textual**: un formulario a pantalla completa es más cómodo para editar en
    cualquier orden, pero es mucho más código y una dependencia mucho más
    pesada para un proyecto de un solo mantenedor. El menú de secciones da casi
    lo mismo.
- Enseñar el `make map` equivalente hace que el wizard sirva también para
  aprender el comando, y que una prueba buena se pueda repetir sin él.

## Consecuencias

- La imagen se reconstruye una vez (`make docker`) para tener questionary.
- `cli.py` importa el wizard solo en el subcomando `wizard`: el resto de
  comandos no carga questionary.
- Los tests no abren ninguna terminal: comprueban que las respuestas dan un
  `argv` que acepta el parser, que cada variable del `make map` enseñado es la
  que el `Makefile` pasa a esa opción, y la memoria (guardar, leer, ficheros
  rotos).
- Cada opción nueva de `make map` necesita también su pregunta en
  `wizard.py`. Si falta, el wizard simplemente no la ofrece: no rompe nada.
