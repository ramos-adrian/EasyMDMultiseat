# EasyMDMultiseat

Herramienta para Linux con systemd que administra multi-seat de logind: asigna periféricos a cualquier `seatN`, guarda perfiles (presets) y cambia entre el display manager normal (GDM, SDDM...) y uno multi-seat (LightDM/SDDM), detectados automáticamente. Interfaz en inglés/español (gettext).

> `CLAUDE.md`, `AGENT.md` y `GEMINI.md` son el MISMO archivo (hard link). Edita uno y los tres cambian. Si una herramienta rompe el enlace (escribe a un archivo nuevo), recréalo: `ln -f CLAUDE.md AGENT.md && ln -f CLAUDE.md GEMINI.md`.

## Archivos

- `multiseat_manager.py` — lanzador. `--gui` fuerza GTK, `--cli` fuerza menú de consola; sin flags elige según `DISPLAY`/`WAYLAND_DISPLAY`.
- `core.py` — toda la lógica (sin GTK): parseo de `loginctl seat-status`, nombres de hardware, presets, cambio de display manager.
- `gui.py` — GTK 4 + libadwaita (`Adw.ApplicationWindow`, pestañas Dispositivos / Perfiles / Configuración).
- `i18n.py` — gettext (`from i18n import _`); `locale/` — `.pot`, `.po` y `.mo` (en, es); `tools/i18n.py` — extrae/compila sin necesitar las herramientas gettext.
- `multiseat-manager.desktop.in` — plantilla del lanzador (`@APPDIR@`); `install.sh` la instala con la ruta real (`--system`, `--uninstall`).
- `ARCHITECTURE.md` — diseño; `ADR/` — decisiones de arquitectura.

## Ejecutar y probar

```
./multiseat_manager.py --gui      # o --cli
python3 -m py_compile *.py tools/i18n.py
python3 tools/i18n.py all         # tras tocar cualquier _("...")
./install.sh                      # lanzador de escritorio
./multiseat_manager.py --lang es  # forzar idioma
```
No hay suite de tests. Humo sin tocar el sistema: `python3 -c "import core; print(core.get_devices_for_seat('seat0')[:2])"`. Las operaciones de escritura (`attach`, `flush-devices`, `systemctl enable/disable`, reboot) modifican el sistema real: no las ejecutes sin que el usuario lo pida.

## Reglas del proyecto

- Dependencias: solo stdlib + PyGObject (`gi`, Gtk 4.0, Adw 1) para la GUI. `core.py` NUNCA importa `gi`.
- Nunca uses `shell=True` ni interpoles rutas en strings: `core.run_cmd` recibe una lista argv. Rutas sysfs pueden llevar caracteres raros.
- Una operación privilegiada = UN prompt de polkit. Agrupa varios comandos con `core.run_root_script` / `attach_devices_to_seat`, no llames `run_cmd(as_root=True)` en bucle.
- Los widgets `Adw.ActionRow`/`ExpanderRow` con texto de dispositivo deben llevar `set_use_markup(False)` (los nombres pueden contener `&` o `<`).
- Todo texto visible va en inglés dentro de `_("...")` con placeholders con nombre (`{seat}`), nunca f-strings ni concatenación dentro de `_()`; el español vive en `locale/es.po`. Tras cambiar textos: `python3 tools/i18n.py extract`, rellenar `es.po`, `python3 tools/i18n.py all` y commitear los `.mo`. Código y comentarios en inglés.
- Nada de seats ni display managers fijos: usa `core.list_seats()`, `core.is_valid_seat()`, `core.get_multiseat_dm()` / `get_normal_dm()`. Los nombres de seat se validan antes de pasarlos a `loginctl`.
- Presets: JSON `{nombre: {"seat": "seatN", "devices": [rutas sysfs de nivel superior]}}`; el formato antiguo (lista = seat1) se sigue leyendo. Sistema `/etc/multiseat_presets.json` + usuario `~/.config/multiseat-manager/presets.json` (el de usuario gana). Ver ADR 0003.
- Cuando la GUI y la CLI necesiten la misma lógica, ponla en `core.py`.

## Contexto

`loginctl attach` persiste vía reglas udev en `/etc/udev/rules.d/`; el cambio de DM requiere reinicio. Ajustes de usuario (DM normal recordado, o `multiseat_dm` forzado) en `~/.config/multiseat-manager/settings.json`.
