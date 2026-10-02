# ADR 0003 — Presets en archivo de sistema + archivo de usuario

- Estado: aceptado (formato ampliado en el ADR 0005)

## Contexto
`/etc/multiseat_presets.json` pertenece a root (644) y la app corre como usuario. La versión inicial leía el primer archivo no vacío, de modo que los presets guardados en `~/.config` quedaban ocultos por el de sistema y no se podía borrar nada.

## Decisión
- Lectura: sistema y luego usuario; el de usuario tiene prioridad.
- Escritura: sistema si es root o escribible; si no, usuario (solo entradas distintas a las del sistema).
- Borrado (`delete_preset`): se quita de cada archivo que lo contenga; si el de sistema no es escribible se informa el error.
- Formato: `{nombre: {"seat": "seatN", "devices": [rutas sysfs de nivel superior]}}`. El formato antiguo `{nombre: [rutas]}` se interpreta como `seat1`.

## Consecuencias
+ Presets de sistema compartidos sin perder los personales. + Archivos antiguos siguen funcionando. − Borrar un preset de sistema requiere permisos.
