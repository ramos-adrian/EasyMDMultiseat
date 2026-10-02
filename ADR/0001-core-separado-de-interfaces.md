# ADR 0001 — Núcleo separado de las interfaces

- Estado: aceptado

## Contexto
La herramienta debe funcionar con entorno gráfico y por terminal/SSH (p. ej. si el display manager está caído tras un cambio mal hecho).

## Decisión
Toda la lógica de sistema vive en `core.py` sin importar GTK. `gui.py` y el menú CLI de `multiseat_manager.py` solo presentan y llaman a `core`. El lanzador cae a CLI si GTK no puede importarse.

## Consecuencias
+ La CLI funciona sin PyGObject. + Lógica reutilizable y verificable sin ventana.
− Duplicación de flujos de confirmación entre GUI y CLI.
