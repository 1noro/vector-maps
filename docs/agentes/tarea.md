# Implementar un TODO

Procedimiento para implementar uno de los TODO numerados del proyecto. Lo
siguen igual una persona o cualquier agente de IA; los comandos `/tarea` de
cada herramienta solo apuntan aquí.

Antes de escribir nada:

1. Busca el marcador `TODO(N)` en el código, con el número del TODO, y su
   entrada en `docs/desarrollo.md`, con la historia y lo que no se salta.
2. Lee el ADR correspondiente en `docs/decisions/`.
3. Lee `AGENTS.md`, secciones "Decisiones cerradas" y "Reglas que no se saltan".

Al implementar:

- Respeta las firmas que ya existen: el resto del cableado depende de ellas.
- No refactorices de paso nada que no te hayan pedido.
- Si una decisión documentada te bloquea, dilo y espera. No la cambies.
- Un test por comportamiento nuevo, sin red.

Al terminar, ejecuta `make check` y arregla lo que salga. No hagas commit:
eso lo pide el usuario.
