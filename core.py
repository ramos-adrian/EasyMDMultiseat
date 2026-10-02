#!/usr/bin/env python3
"""
Multi-Seat Manager - Core logic module
Handles loginctl parsing, hardware discovery, device categorization, presets,
seat management and display manager configuration.

No GUI imports here: this module is shared by the CLI and the GTK interface.
"""

import os
import re
import json
import shlex
import subprocess
from pathlib import Path

from i18n import _

SYSTEM_PRESETS_FILE = Path("/etc/multiseat_presets.json")
USER_CONFIG_DIR = Path(os.path.expanduser("~/.config/multiseat-manager"))
USER_PRESETS_DIR = USER_CONFIG_DIR  # kept for backwards compatibility
USER_PRESETS_FILE = USER_CONFIG_DIR / "presets.json"
SETTINGS_FILE = USER_CONFIG_DIR / "settings.json"

DISPLAY_MANAGER_LINK = Path("/etc/systemd/system/display-manager.service")
UNIT_DIRS = (
    Path("/etc/systemd/system"),
    Path("/run/systemd/system"),
    Path("/usr/lib/systemd/system"),
    Path("/lib/systemd/system"),
)

# Display managers we know about, in order of preference when auto-detecting.
KNOWN_DMS = ("gdm3", "gdm", "lightdm", "sddm", "lxdm", "xdm")
# Those that can run several seats at once, in order of preference.
MULTISEAT_DMS = ("lightdm", "sddm")
DM_LABELS = {
    "gdm3": "GDM3", "gdm": "GDM", "lightdm": "LightDM",
    "sddm": "SDDM", "lxdm": "LXDM", "xdm": "XDM",
}

# How to install the preferred multi-seat DM, keyed by os-release ID / ID_LIKE.
INSTALL_COMMANDS = (
    (("debian", "ubuntu"), ["apt", "install", "lightdm"]),
    (("fedora", "rhel", "centos"), ["dnf", "install", "lightdm"]),
    (("arch",), ["pacman", "-S", "lightdm"]),
    (("suse", "opensuse"), ["zypper", "install", "lightdm"]),
)

MAIN_SEAT = "seat0"
SEAT_RE = re.compile(r'^seat[A-Za-z0-9_-]+$')

_PCI_MAP_CACHE = None


def is_root():
    return os.geteuid() == 0


def run_cmd(cmd, as_root=False):
    """
    Runs a command WITHOUT a shell. `cmd` is an argv list (a str is split with shlex).
    If as_root is True and the process is not root, it is prefixed with pkexec.
    Returns (ok, stdout) or (False, error message).
    """
    argv = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
    if as_root and not is_root():
        argv = ["pkexec"] + argv
    try:
        result = subprocess.run(
            argv,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip() or (e.stdout or "").strip()
        return False, err or str(e)
    except OSError as e:
        return False, str(e)


def run_root_script(script, *args):
    """
    Runs a POSIX sh script as root in a SINGLE privilege prompt.
    Extra args are passed as "$@" (safe against spaces/quotes).
    """
    return run_cmd(["sh", "-c", script, "sh", *args], as_root=True)


# -------------------------------------------------------------------
# Settings (small user-level JSON)
# -------------------------------------------------------------------
def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_settings():
    return _read_json(SETTINGS_FILE)


def update_settings(**changes):
    settings = load_settings()
    settings.update(changes)
    try:
        _write_json(SETTINGS_FILE, settings)
    except OSError:
        pass  # settings are a convenience, never fatal


# -------------------------------------------------------------------
# Hardware names
# -------------------------------------------------------------------
def get_pci_names():
    """
    Parses lspci -mm to map PCI slots (e.g. 01:00.0) to readable device names.
    """
    global _PCI_MAP_CACHE
    if _PCI_MAP_CACHE is not None:
        return _PCI_MAP_CACHE

    pci_map = {}
    ok, out = run_cmd(["lspci", "-mm"])
    if ok and out:
        # 01:00.0 "VGA compatible controller" "NVIDIA Corporation" "GA106 [GeForce RTX 3060]" ...
        pattern = re.compile(r'^([0-9a-fA-F:.]+)\s+"([^"]*)"\s+"([^"]*)"\s+"([^"]*)"')
        for line in out.splitlines():
            m = pattern.match(line)
            if m:
                slot, dev_class, vendor, dev_name = m.groups()
                clean_vendor = re.sub(
                    r'(\s+Corporation|\s+Inc\.|\s+Co\.,\s*Ltd\.|\s+Technology|\s*\[.*?\]|,)', '', vendor
                ).strip()
                title = f"{clean_vendor} {dev_name}".strip() if dev_name else vendor
                pci_map[slot] = {
                    "class": dev_class,
                    "vendor": vendor,
                    "name": dev_name,
                    "title": title,
                }
    _PCI_MAP_CACHE = pci_map
    return pci_map


def _is_gpu_class(pci_class):
    return any(k in pci_class for k in ("VGA", "3D controller", "Display controller"))


def find_pci_info(path):
    """
    Returns lspci info for the deepest PCI function in a sysfs path.
    Paths look like .../0000:00:01.1/0000:01:00.0/drm/card1; the LAST slot is the
    device itself, earlier ones are bridges.
    """
    pci_map = get_pci_names()
    slots = re.findall(r'[0-9a-fA-F]{4}:([0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F])', path)
    for slot in reversed(slots):
        if slot in pci_map:
            return pci_map[slot]
    return None


def parse_desc(desc):
    """
    Splits a loginctl description like `input:input28 "Logitech Keyboard"`
    into (subsystem, ident, label).
    """
    m = re.match(r'^([A-Za-z0-9_\-]+):(\S*)\s*(?:"(.*)")?\s*$', desc.strip())
    if not m:
        return "", desc.strip(), ""
    subsystem, ident, label = m.groups()
    return subsystem, ident, (label or "").strip()


def find_usb_product(path):
    """Looks for the nearest ancestor (max 8 levels) exposing a USB `product` file."""
    probe = Path(path)
    for _i in range(8):
        if str(probe) in ("/", "/sys", "/sys/devices"):
            break
        prod_file = probe / "product"
        if prod_file.is_file():
            try:
                name = prod_file.read_text().strip()
                if name:
                    return name
            except OSError:
                pass
        probe = probe.parent
    return ""


def get_input_flags(path):
    """Returns the set of ID_INPUT_* udev properties for an input device."""
    ok, out = run_cmd(["udevadm", "info", "-q", "property", "-p", path])
    if not ok:
        return set()
    return {line.split("=", 1)[0] for line in out.splitlines() if line.startswith("ID_INPUT_") and line.endswith("=1")}


def get_human_name_for_device(path, raw_desc):
    """
    Returns (friendly_name, icon, category) for a device using loginctl's description,
    sysfs and lspci.
    """
    subsystem, ident, label = parse_desc(raw_desc.replace("'", ""))

    # GPU / PCI devices: prefer the lspci name
    if subsystem in ("pci", "drm", "graphics") or "/drm/card" in path:
        info = find_pci_info(path)
        if info and _is_gpu_class(info["class"]):
            title = info["title"]
            if subsystem in ("drm", "graphics") and ident:
                title = f"{title} ({ident})"
            return title, "video-display-symbolic", _("Graphics Card / Display")
        if subsystem == "pci" and info:
            return info["title"], "preferences-system-symbolic", info["class"]
        if subsystem in ("drm", "graphics"):
            name = label or ident
            return _("Display Output ({name})").format(name=name), "video-display-symbolic", _("Graphics Card / Display")

    product = find_usb_product(path) if subsystem != "pci" else ""
    if label:
        friendly = label
    elif product:
        friendly = f"{product} ({ident})"
    else:
        friendly = raw_desc.replace('"', "").strip() or Path(path).name

    icon, cat = categorize_device(path, f"{subsystem} {label} {product}", subsystem)
    return friendly, icon, cat


def categorize_device(path, desc, subsystem=""):
    """
    Categorizes a device and returns (icon name, translated category label).
    `desc` is free text (name/product); `subsystem` is the kernel subsystem if known.
    """
    path_lower = path.lower()
    desc_lower = desc.lower()
    if not subsystem:
        subsystem = parse_desc(desc)[0]

    if subsystem == "input":
        flags = get_input_flags(path)
        if "ID_INPUT_KEYBOARD" in flags:
            return "input-keyboard-symbolic", _("Keyboard")
        if "ID_INPUT_TABLET" in flags:
            return "input-tablet-symbolic", _("Graphics Tablet")
        if flags & {"ID_INPUT_MOUSE", "ID_INPUT_TOUCHPAD", "ID_INPUT_POINTINGSTICK"}:
            return "input-mouse-symbolic", _("Mouse / Pointer")

    if subsystem in ("drm", "graphics") or "/drm/" in path_lower or "/graphics/" in path_lower:
        return "video-display-symbolic", _("Display / Graphics")
    if subsystem == "sound":
        return "audio-card-symbolic", _("Audio / Microphone")
    if subsystem in ("video4linux", "media"):
        return "camera-web-symbolic", _("Camera / Video")
    if subsystem == "net" or "/net/" in path_lower:
        return "network-wired-symbolic", _("Network")

    if re.search(r'keyboard|teclado', desc_lower):
        return "input-keyboard-symbolic", _("Keyboard")
    if re.search(r'wacom|tablet|\bpen\b|ctl-', desc_lower):
        return "input-tablet-symbolic", _("Graphics Tablet")
    if re.search(r'mouse|ratón|touchpad', desc_lower):
        return "input-mouse-symbolic", _("Mouse / Pointer")
    if re.search(r'audio|\bmic(rophone)?\b|headphone|headset|snowball', desc_lower):
        return "audio-card-symbolic", _("Audio / Microphone")
    if re.search(r'camera|\bcam\b|webcam', desc_lower):
        return "camera-web-symbolic", _("Camera / Video")
    if subsystem in ("usb", "hidraw") or "/usb" in path_lower:
        return "drive-removable-media-symbolic", _("USB Device")
    return "preferences-system-symbolic", _("System / Other")


# -------------------------------------------------------------------
# Display managers
# -------------------------------------------------------------------
def dm_label(name):
    """Human label for a display manager name."""
    return DM_LABELS.get(name, name)


def _unit_path(name):
    for d in UNIT_DIRS:
        p = d / f"{name}.service"
        if p.exists():
            return p
    return None


def installed_display_managers():
    """
    Known display managers with an installed systemd unit. Aliases (e.g. gdm3.service
    -> gdm.service) are collapsed to the real unit name.
    """
    found = []
    for name in KNOWN_DMS:
        p = _unit_path(name)
        if p is None:
            continue
        try:
            real = p.resolve().stem
        except OSError:
            real = name
        if real == name or real not in KNOWN_DMS:
            found.append(name)
    return found


def _is_active(unit):
    ok, out = run_cmd(["systemctl", "is-active", unit])
    return ok and out.strip() == "active"


def get_enabled_display_manager():
    """Name of the display manager configured for boot, or "unknown"."""
    if DISPLAY_MANAGER_LINK.is_symlink():
        stem = Path(os.readlink(DISPLAY_MANAGER_LINK)).stem
        return stem or "unknown"
    return "unknown"


def get_active_display_manager():
    """
    Returns {"enabled": <dm configured for boot>, "running": <dm running now>}.
    """
    running = "inactive"
    for name in installed_display_managers():
        if _is_active(name):
            running = name
            break
    return {"enabled": get_enabled_display_manager(), "running": running}


def _os_release_ids():
    """IDs from /etc/os-release (ID plus ID_LIKE), lowercase."""
    ids = []
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            key, _sep, value = line.partition("=")
            if key in ("ID", "ID_LIKE"):
                ids += value.strip().strip('"\'').lower().split()
    except OSError:
        pass
    return ids


def multiseat_install_hint():
    """
    Explains why a multi-seat display manager is needed and, when the distribution
    is recognised, the command to install LightDM. Never installs anything itself.
    """
    ids = _os_release_ids()
    for names, argv in INSTALL_COMMANDS:
        if any(n in ids for n in names):
            return _("GDM cannot run several seats at once; LightDM and SDDM can. "
                     "Install LightDM with: {command}").format(command=shlex.join(["sudo"] + argv))
    return _("GDM cannot run several seats at once; LightDM and SDDM can. "
             "Install one of them with your package manager.")


def get_multiseat_dm():
    """Display manager used for multi-seat mode (user setting, else auto-detected), or None."""
    installed = installed_display_managers()
    preferred = load_settings().get("multiseat_dm")
    if preferred in installed:
        return preferred
    for name in MULTISEAT_DMS:
        if name in installed:
            return name
    return None


def get_normal_dm():
    """Display manager used for normal mode (remembered, else auto-detected), or None."""
    installed = installed_display_managers()
    multi = get_multiseat_dm()
    remembered = load_settings().get("normal_dm")
    if remembered in installed and remembered != multi:
        return remembered
    for name in installed:
        if name != multi:
            return name
    return None


def is_multiseat_mode():
    dm = get_multiseat_dm()
    return dm is not None and get_enabled_display_manager() == dm


def _switch_display_manager(target, flush=False):
    """Disables every other known DM and enables `target`, in one privilege prompt."""
    others = [d for d in installed_display_managers() if d != target]
    script = (
        ("loginctl flush-devices; " if flush else "")
        + 'target="$1"; shift; '
        'for dm in "$@"; do systemctl disable "$dm" 2>/dev/null; done; '
        'systemctl enable "$target"'
    )
    return run_root_script(script, target, *others)


def set_multiseat_enabled(enable=True):
    """
    enable=True : enable the multi-seat DM (LightDM/SDDM), disable the others.
    enable=False: flush seats, enable the normal DM, disable the multi-seat one.
    Returns (ok, message). Takes effect on next boot.
    """
    if enable:
        target = get_multiseat_dm()
        if not target:
            return False, _("No multi-seat capable display manager found.") + " " + multiseat_install_hint()
        current = get_enabled_display_manager()
        if current not in ("unknown", target):
            update_settings(normal_dm=current)
        ok, out = _switch_display_manager(target)
        return ok, (_("{dm} enabled, other display managers disabled.").format(dm=dm_label(target)) if ok else out)

    target = get_normal_dm()
    if not target:
        return False, _("No normal display manager found (GDM, SDDM...).")
    ok, out = _switch_display_manager(target, flush=True)
    return ok, (_("{dm} enabled, seats reset to seat0.").format(dm=dm_label(target)) if ok else out)


def request_reboot():
    """Requests a clean system reboot."""
    return run_cmd(["systemctl", "reboot"], as_root=True)


# -------------------------------------------------------------------
# Seats and devices
# -------------------------------------------------------------------
# Subsystems that only add noise to the device lists (always follow their parent).
HIDDEN_SUBSYSTEMS = {"leds"}


def is_valid_seat(name):
    return bool(SEAT_RE.match(name or ""))


def list_seats():
    """Seats known to logind (those with devices), seat0 first."""
    ok, out = run_cmd(["loginctl", "--no-pager", "--no-legend", "list-seats"])
    seats = [line.split()[0] for line in out.splitlines() if line.strip()] if ok else []
    seats = [s for s in seats if is_valid_seat(s)]
    if MAIN_SEAT not in seats:
        seats.append(MAIN_SEAT)
    return sorted(seats, key=lambda s: (s != MAIN_SEAT, len(s), s))


def next_seat_name(existing=None):
    """First free seatN (N>=1)."""
    existing = set(existing if existing is not None else list_seats())
    n = 1
    while f"seat{n}" in existing:
        n += 1
    return f"seat{n}"


def get_devices_for_seat(seat=MAIN_SEAT):
    """
    Parses `loginctl seat-status <seat>` and returns a list of devices with metadata.
    Output format (tree):
        ├─/sys/devices/...            <- path line
        │ [MASTER] drm:card1          <- description line
    """
    if not is_valid_seat(seat):
        return []
    ok, output = run_cmd(["loginctl", "--no-pager", "seat-status", seat])
    if not ok or not output:
        return []

    devices = []
    current_path = None

    for line in output.split("\n"):
        path_match = re.search(r'(/sys/\S.*)$', line)
        if path_match:
            current_path = path_match.group(1).strip()
            continue
        if not current_path or not line.strip():
            continue

        desc = re.sub(r'^[├└│\s─]+', '', line).strip()
        is_master = "[MASTER]" in desc
        desc = desc.replace("[MASTER]", "").strip()
        path, current_path = current_path, None

        if parse_desc(desc)[0] in HIDDEN_SUBSYSTEMS:
            continue

        friendly_name, icon, category = get_human_name_for_device(path, desc)
        devices.append({
            "path": path,
            "desc": friendly_name,
            "raw_desc": desc,
            "icon": icon,
            "category": category,
            "is_master": is_master,
            "seat": seat,
        })

    return devices


def get_top_level_paths(devices):
    """
    Filters devices to only include top-level parent paths.
    Sub-devices attach automatically when the parent device is attached.
    """
    paths = [dev["path"] for dev in devices]
    return [
        dev for dev in devices
        if not any(dev["path"].startswith(other + "/") for other in paths if other != dev["path"])
    ]


def attach_device_to_seat(path, target_seat="seat1"):
    """Attaches a device to a specific seat."""
    return attach_devices_to_seat([path], target_seat)


def attach_devices_to_seat(paths, target_seat="seat1"):
    """
    Attaches several devices to a seat with ONE privilege prompt.
    Returns (all_ok, message); message lists failures when not all_ok.
    """
    if not is_valid_seat(target_seat):
        return False, _("Invalid seat name: {seat}").format(seat=target_seat)
    paths = list(paths)
    if not paths:
        return True, ""
    script = (
        'seat="$1"; shift; rc=0; '
        'for p in "$@"; do loginctl attach "$seat" "$p" || { echo "failed: $p" >&2; rc=1; }; done; '
        'exit $rc'
    )
    return run_root_script(script, target_seat, *paths)


def collapse_assignments(assignments):
    """
    Drops assignments already implied by an ancestor path moving to the same seat
    (sub-devices follow their parent), keeping only top-level paths.
    """
    return {
        path: seat for path, seat in assignments.items()
        if not any(
            path.startswith(other + "/") and assignments[other] == seat
            for other in assignments if other != path
        )
    }


def apply_seat_assignments(assignments):
    """
    Applies {sysfs_path: seat} for any mix of seats with ONE privilege prompt.
    Returns (all_ok, message).
    """
    bad = sorted({seat for seat in assignments.values() if not is_valid_seat(seat)})
    if bad:
        return False, _("Invalid seat name: {seat}").format(seat=", ".join(bad))
    top = collapse_assignments(assignments)
    if not top:
        return True, ""
    script = (
        'rc=0; while [ "$#" -ge 2 ]; do '
        'loginctl attach "$1" "$2" || { echo "failed: $2" >&2; rc=1; }; shift 2; '
        'done; exit $rc'
    )
    args = [arg for path, seat in top.items() for arg in (seat, path)]
    return run_root_script(script, *args)


def flush_all_seats():
    """Flushes all custom seat assignments, returning all devices to seat0."""
    return run_cmd(["loginctl", "flush-devices"], as_root=True)


# -------------------------------------------------------------------
# Presets
# -------------------------------------------------------------------
# A preset is stored either as a legacy list of sysfs paths (always meant for seat1)
# or as {"seat": "seatN", "devices": [paths]}.
def make_preset(seat, paths):
    return {"seat": seat, "devices": list(paths)}


def preset_devices(preset):
    return list(preset.get("devices", [])) if isinstance(preset, dict) else list(preset)


def preset_seat(preset):
    if isinstance(preset, dict) and is_valid_seat(preset.get("seat")):
        return preset["seat"]
    return "seat1"


def get_presets_file():
    """
    Returns the file presets are written to: the system file when running as root
    or when it is writable, otherwise the per-user file.
    """
    if is_root() or (SYSTEM_PRESETS_FILE.exists() and os.access(SYSTEM_PRESETS_FILE, os.W_OK)):
        return SYSTEM_PRESETS_FILE
    return USER_PRESETS_FILE


def load_presets():
    """Loads presets from the system file, overlaid by the user file (user wins)."""
    presets = _read_json(SYSTEM_PRESETS_FILE)
    presets.update(_read_json(USER_PRESETS_FILE))
    return presets


def save_presets(presets):
    """
    Saves the presets dict. When falling back to the user file, entries identical to
    the (read-only) system file are not duplicated.
    Returns (ok, path_or_error).
    """
    target = get_presets_file()
    data = dict(presets)
    if target == USER_PRESETS_FILE:
        system = _read_json(SYSTEM_PRESETS_FILE)
        data = {k: v for k, v in presets.items() if system.get(k) != v}
    try:
        _write_json(target, data)
        return True, str(target)
    except OSError as e:
        return False, str(e)


def delete_preset(name):
    """Deletes a preset from every file that contains it. Returns (ok, message)."""
    removed = False
    for path in (USER_PRESETS_FILE, SYSTEM_PRESETS_FILE):
        data = _read_json(path)
        if name in data:
            del data[name]
            try:
                _write_json(path, data)
                removed = True
            except OSError as e:
                return False, _("Cannot modify {path}: {error}").format(path=path, error=e)
    return (True, "") if removed else (False, _("The preset does not exist"))
