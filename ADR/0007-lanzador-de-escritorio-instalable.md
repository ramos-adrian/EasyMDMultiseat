# ADR 0007 — Lanzador `.desktop` generado por `install.sh`

- Estado: aceptado

## Contexto
El `.desktop` original tenía una ruta `Exec=` absoluta, inservible en otra máquina o carpeta.

## Decisión
Se guarda una plantilla `multiseat-manager.desktop.in` con `@APPDIR@` y nombres traducidos (`Name[es]`, …). `install.sh` la instala con la ruta real (`~/.local/share/applications` o `--system`) y soporta `--uninstall`. `multiseat_manager.py` añade su propio directorio a `sys.path`, así que funciona también vía symlink.

## Consecuencias
+ Portátil y sin rutas personales en el repositorio. − Si se mueve la carpeta hay que volver a ejecutar `install.sh`.
