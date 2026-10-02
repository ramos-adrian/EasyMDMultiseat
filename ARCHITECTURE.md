# Arquitectura

## Visión general

```
multiseat_manager.py ──► gui.py (GTK4/libadwaita) ─┐
        │                                          ├──► core.py ──► loginctl / systemctl / lspci / udevadm / pkexec
        └──► CLI interactivo (en el mismo archivo) ┘                └──► presets / settings JSON
        i18n.py (gettext) ◄── usado por todos los módulos; catálogos en locale/
```

Tres capas: **lanzador** (elige interfaz), **interfaces** (GUI y CLI, sin lógica de sistema) y **core** (único módulo que habla con el sistema operativo).

## core.py

| Área | Funciones | Notas |
|---|---|---|
| Ejecución | `run_cmd`, `run_root_script` | argv sin shell; `pkexec` si no es root |
| Nombres | `get_human_name_for_device`, `categorize_device`, `find_pci_info`, `find_usb_product`, `get_input_flags` | `lspci -mm` (cacheado), sysfs `product`, `udevadm` para teclado/ratón/tableta |
| Seats | `list_seats`, `next_seat_name`, `is_valid_seat`, `get_devices_for_seat`, `get_top_level_paths`, `attach_devices_to_seat`, `flush_all_seats` | seats arbitrarios `seatN` (ADR 0005); parseo del árbol de `loginctl seat-status` |
| Presets | `load_presets`, `save_presets`, `delete_preset`, `make_preset`, `preset_seat`, `preset_devices` | sistema + usuario, ver ADR 0003 |
| Display manager | `installed_display_managers`, `get_multiseat_dm`, `get_normal_dm`, `get_active_display_manager`, `set_multiseat_enabled`, `request_reboot` | detección automática, ver ADR 0004 |

### Parseo de `loginctl seat-status`

Salida en árbol: una línea con la ruta `/sys/...` seguida de una línea de descripción (`[MASTER] drm:card1`, `input:input28 "Nombre"`). Cada pareja ruta+descripción es un dispositivo. Se ocultan los subsistemas `leds` (ruido). `get_top_level_paths` descarta dispositivos cuyo ancestro también está en la lista, porque al asignar el padre los hijos le siguen (así se guardan los presets).

### Resolución de nombres

1. GPU/PCI: se busca el **último** slot PCI de la ruta (los anteriores son puentes) en `lspci -mm`.
2. Con etiqueta entre comillas en la descripción → esa etiqueta.
3. Si no, producto USB del ancestro más cercano + identificador.
4. Categoría/icono: tipo de subsistema, propiedades `ID_INPUT_*` de udev, y palabras clave como último recurso.

## Flujo de privilegios

Toda escritura va por `pkexec` (polkit). Para evitar un prompt por dispositivo, los lotes se ejecutan con `sh -c '<script>' sh args...` (un solo `pkexec`). Ver ADR 0002.

## Cambio de modo

- **Detección**: se buscan unidades `.service` de `KNOWN_DMS` (gdm3, gdm, lightdm, sddm, lxdm, xdm) en los directorios de systemd, colapsando alias (`gdm3.service -> gdm.service`). Multi-seat DM = el de `settings.json` (`multiseat_dm`) o el primero instalado de `lightdm`, `sddm`. DM normal = el recordado (`normal_dm`, se guarda al activar multi-seat) o el primero instalado distinto del multi-seat.
- **Activar multi-seat**: deshabilita todos los demás DM y habilita el multi-seat (un solo `pkexec`). Surte efecto al reiniciar.
- **Restaurar**: `loginctl flush-devices`, deshabilita los demás y habilita el DM normal.
- El estado se lee del symlink `/etc/systemd/system/display-manager.service` (configurado) y `systemctl is-active` (en ejecución).

## GUI (gui.py)

`MultiseatWindow` con `Adw.ViewStack`: Dispositivos (los movimientos se **preparan** en `self.pending` y no se aplican hasta pulsar «Aplicar cambios» en la barra inferior; seat0 a la izquierda; a la derecha un desplegable con cualquier otro seat y un botón «+» para crear el siguiente libre; búsqueda), Perfiles (lista expandible con aplicar/eliminar; cada perfil recuerda su seat) y Configuración (estado, DM detectados, cambio de modo, reinicio). Las llamadas a `core` son síncronas en el hilo de UI (aceptable: son rápidas salvo el diálogo de polkit).

## Internacionalización

Los textos fuente están en inglés dentro de `_("...")` (`i18n.py`, dominio `multiseat-manager`). El idioma sale de `LANGUAGE`/`LANG` o de `--lang xx`. `tools/i18n.py` reemplaza a xgettext/msgmerge/msgfmt: `extract` genera `locale/multiseat-manager.pot` y sincroniza los `.po`; `check` valida placeholders; `compile` genera los `.mo` (versionados para que funcione desde el código fuente). Ver ADR 0006.

## Instalación del lanzador

`multiseat-manager.desktop.in` es una plantilla con `@APPDIR@`; `install.sh` la instala con la ruta real del proyecto (usuario por defecto, `--system`, `--uninstall`). Ver ADR 0007.

## Limitaciones conocidas

- Sin tests automatizados; la lógica depende de hardware real.
- logind solo conoce los seats que tienen dispositivos: un seat nuevo creado en la GUI existe únicamente hasta que se le asigna algo.
- Multi-seat solo se automatiza para LightDM y SDDM; otros DM se pueden forzar con `multiseat_dm` en `settings.json` pero no están probados.
- `Adw.MessageDialog` está deprecado desde libadwaita 1.6 (funciona; migrar a `Adw.AlertDialog` cuando se exija ≥1.5).
