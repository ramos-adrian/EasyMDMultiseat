# Multi-Seat Manager

[Leer en español](README.es.md)

A GTK 4 / libadwaita app (plus a console menu) for Linux with systemd that manages
**logind multi-seat**: assign keyboards, mice, GPUs and other devices to any `seatN`,
save the layouts as presets, and switch between your normal display manager and a
multi-seat capable one.

## Why you may need another display manager

GDM (the default in GNOME, e.g. Ubuntu) cannot run several seats at once. **LightDM**
and **SDDM** can. When none of them is installed, the app tells you so and shows the
install command for your distribution, for example:

```
sudo apt install lightdm      # Debian / Ubuntu
sudo dnf install lightdm      # Fedora
sudo pacman -S lightdm        # Arch
sudo zypper install lightdm   # openSUSE
```

The app never installs packages by itself.

## Requirements

- Linux with systemd (`loginctl`, `systemctl`) and polkit (`pkexec`)
- Python 3
- For the GUI: PyGObject, GTK 4 and libadwaita 1 (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1` on Debian/Ubuntu)
- A multi-seat capable display manager (LightDM or SDDM)
- Real extra hardware: at least a second keyboard and mouse, and normally a second
  GPU (or a video adapter) for the extra seat

## Usage

```
./multiseat_manager.py          # GUI if a graphical session is available, else console
./multiseat_manager.py --gui
./multiseat_manager.py --cli
./multiseat_manager.py --lang es
./install.sh                    # add a launcher to your applications menu
./install.sh --system           # system-wide
./install.sh --uninstall
```

The interface is available in English and Spanish. To add a language see
`tools/i18n.py`: copy `locale/multiseat-manager.pot` to `locale/<lang>.po`, translate,
then run `python3 tools/i18n.py all`.

## What it changes on your system

Read this before using it:

- Attaching a device writes udev rules in `/etc/udev/rules.d/` (via `loginctl attach`).
- Enabling multi-seat enables the multi-seat display manager and **disables the others**.
  It takes effect after a reboot.
- Restoring normal mode runs `loginctl flush-devices` (removes those udev rules),
  re-enables your normal display manager and disables the multi-seat one.
- Each privileged operation asks for authentication once through polkit.

Settings and presets live in `~/.config/multiseat-manager/` (system presets in
`/etc/multiseat_presets.json`).

## Troubleshooting

If the system does not reach a login screen after a change:

1. Switch to a text console (Ctrl+Alt+F3) and log in.
2. Return to your previous display manager, e.g.
   `sudo systemctl disable lightdm && sudo systemctl enable gdm3`.
3. Remove the seat rules: `sudo loginctl flush-devices`, then reboot.

## Project layout

See [ARCHITECTURE.md](ARCHITECTURE.md) and the decision records in `ADR/` (written in Spanish).

## Status

Tested on Ubuntu with GDM → LightDM. Other display managers and distributions are
untested; reports and pull requests are welcome.
