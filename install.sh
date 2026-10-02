#!/bin/sh
# Installs (or removes) the desktop launcher for the CURRENT location of the project.
#   ./install.sh              install for this user  (~/.local/share/applications)
#   ./install.sh --system     install system-wide    (/usr/share/applications, needs root)
#   ./install.sh --uninstall  remove the launcher (add --system for the system one)
set -eu

APPDIR=$(cd "$(dirname "$0")" && pwd -P)
NAME=multiseat-manager.desktop
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        --system) DEST=/usr/share/applications ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

if [ "$UNINSTALL" = 1 ]; then
    rm -f "$DEST/$NAME"
    echo "Removed $DEST/$NAME"
else
    mkdir -p "$DEST"
    chmod +x "$APPDIR/multiseat_manager.py"
    sed "s|@APPDIR@|$APPDIR|g" "$APPDIR/$NAME.in" > "$DEST/$NAME"
    echo "Installed $DEST/$NAME (Exec -> $APPDIR/multiseat_manager.py)"
fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DEST" 2>/dev/null || true
