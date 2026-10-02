# ADR 0004 — Detección automática del display manager (multi-seat vs normal)

- Estado: aceptado (reemplaza la versión «GDM3 ↔ LightDM fijo»)

## Contexto
GDM no maneja bien sesiones simultáneas en varios seats; LightDM y SDDM sí. La versión inicial asumía Debian/Ubuntu (`gdm3`/`lightdm`) con nombres fijos, lo que fallaba en otras distros (unidad `gdm`, SDDM en KDE, etc.). En Ubuntu reciente `gdm3.service` es un alias de `gdm.service`.

## Decisión
- Se detectan los DM instalados (`KNOWN_DMS`) buscando su unidad systemd y colapsando alias.
- DM multi-seat: ajuste `multiseat_dm` o el primero instalado de (`lightdm`, `sddm`). DM normal: el que estaba activo antes de activar multi-seat (guardado en `settings.json` como `normal_dm`) o el primero instalado que no sea el multi-seat.
- Cambiar de modo = deshabilitar los demás DM y habilitar el objetivo en un solo `pkexec`; efecto en el siguiente arranque. No se reinicia el DM en caliente (mataba la sesión activa).
- Si no hay DM multi-seat instalado, la GUI desactiva el botón y la CLI explica qué instalar.

## Consecuencias
+ Funciona en distros con GDM/SDDM/LightDM sin tocar código. − Otros DM (greetd, lxdm…) solo con ajuste manual y sin probar.
