# Multi-Seat Manager

[Read in English](README.md)

Aplicación GTK 4 / libadwaita (y menú de consola) para Linux con systemd que administra
el **multi-seat de logind**: asigna teclados, ratones, GPU y otros dispositivos a cualquier
`seatN`, guarda las configuraciones como perfiles y cambia entre tu gestor de inicio
normal y uno compatible con multi-seat.

## Por qué puedes necesitar otro gestor de inicio

GDM (el de GNOME, por ejemplo en Ubuntu) no puede ejecutar varios seats a la vez.
**LightDM** y **SDDM** sí. Si no hay ninguno instalado, la app lo indica y muestra el
comando de instalación para tu distribución, por ejemplo:

```
sudo apt install lightdm      # Debian / Ubuntu
sudo dnf install lightdm      # Fedora
sudo pacman -S lightdm        # Arch
sudo zypper install lightdm   # openSUSE
```

La app nunca instala paquetes por sí sola.

## Requisitos

- Linux con systemd (`loginctl`, `systemctl`) y polkit (`pkexec`)
- Python 3
- Para la GUI: PyGObject, GTK 4 y libadwaita 1 (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1` en Debian/Ubuntu)
- Un gestor de inicio compatible con multi-seat (LightDM o SDDM)
- Hardware adicional real: al menos otro teclado y ratón, y normalmente otra GPU
  (o un adaptador de vídeo) para el seat extra

## Uso

```
./multiseat_manager.py          # GUI si hay sesión gráfica, si no consola
./multiseat_manager.py --gui
./multiseat_manager.py --cli
./multiseat_manager.py --lang es
./install.sh                    # añade un lanzador al menú de aplicaciones
./install.sh --system           # para todo el sistema
./install.sh --uninstall
```

Para añadir un idioma, copia `locale/multiseat-manager.pot` a `locale/<idioma>.po`,
traduce y ejecuta `python3 tools/i18n.py all`.

## Qué cambia en tu sistema

Lee esto antes de usarla:

- Asignar un dispositivo escribe reglas udev en `/etc/udev/rules.d/` (con `loginctl attach`).
- Activar multi-seat habilita el gestor multi-seat y **deshabilita los demás**. Se aplica
  tras reiniciar.
- Restaurar el modo normal ejecuta `loginctl flush-devices` (borra esas reglas udev),
  vuelve a habilitar tu gestor normal y deshabilita el multi-seat.
- Cada operación privilegiada pide autenticación una sola vez mediante polkit.

Los ajustes y perfiles están en `~/.config/multiseat-manager/` (perfiles del sistema en
`/etc/multiseat_presets.json`).

## Solución de problemas

Si tras un cambio el sistema no llega a la pantalla de inicio de sesión:

1. Cambia a una consola de texto (Ctrl+Alt+F3) e inicia sesión.
2. Vuelve a tu gestor anterior, p. ej.
   `sudo systemctl disable lightdm && sudo systemctl enable gdm3`.
3. Elimina las reglas de seats: `sudo loginctl flush-devices` y reinicia.

## Estructura del proyecto

Ver [ARCHITECTURE.md](ARCHITECTURE.md) y los registros de decisiones en `ADR/`.

## Estado

Probado en Ubuntu con GDM → LightDM. Otras distribuciones y gestores de inicio no están
probados; se agradecen reportes y pull requests.
