#!/bin/sh
# Installs (or removes) the desktop launcher for the CURRENT location of the project.
#   ./install.sh              install for this user  (~/.local/share/applications)
#   sudo ./install.sh --system     install for ALL users: copies the app to /opt/easymdmultiseat,
#                                  adds /usr/share/applications launcher and /usr/local/bin/easymdmultiseat
#   ./install.sh --uninstall       remove the launcher (add --system for the system-wide install)
set -eu

APPDIR=$(cd "$(dirname "$0")" && pwd -P)
NAME=multiseat-manager.desktop
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
UNINSTALL=0
SYSTEM=0
SYSDIR=/opt/easymdmultiseat
BINLINK=/usr/local/bin/easymdmultiseat

for arg in "$@"; do
    case "$arg" in
        --system) DEST=/usr/share/applications; SYSTEM=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

if [ "$SYSTEM" = 1 ] && [ "$(id -u)" != 0 ]; then
    echo "--system needs root: run  sudo $0 $*" >&2
    exit 1
fi

if [ "$UNINSTALL" = 1 ]; then
    rm -f "$DEST/$NAME"
    if [ "$SYSTEM" = 1 ]; then
        rm -rf "$SYSDIR"
        rm -f "$BINLINK"
        echo "Removed $SYSDIR and $BINLINK"
    fi
    echo "Removed $DEST/$NAME"
elif [ "$SYSTEM" = 1 ]; then
    # Copy to a world-readable location: other users cannot read /home/<you>.
    rm -rf "$SYSDIR"
    mkdir -p "$SYSDIR" "$DEST"
    cp -r "$APPDIR"/*.py "$APPDIR"/locale "$APPDIR"/tools "$SYSDIR"/
    chmod -R a+rX "$SYSDIR"
    chmod 755 "$SYSDIR/multiseat_manager.py"
    ln -sf "$SYSDIR/multiseat_manager.py" "$BINLINK"
    sed "s|@APPDIR@|$SYSDIR|g" "$APPDIR/$NAME.in" > "$DEST/$NAME"
    chmod 644 "$DEST/$NAME"
    echo "Installed for all users: $SYSDIR, $DEST/$NAME, $BINLINK"
else
    mkdir -p "$DEST"
    chmod +x "$APPDIR/multiseat_manager.py"
    sed "s|@APPDIR@|$APPDIR|g" "$APPDIR/$NAME.in" > "$DEST/$NAME"
    echo "Installed $DEST/$NAME (Exec -> $APPDIR/multiseat_manager.py)"
fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DEST" 2>/dev/null || true
