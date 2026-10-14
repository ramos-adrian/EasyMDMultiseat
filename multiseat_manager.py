#!/usr/bin/env python3
"""
EasyMDMultiseat
Smart universal launcher:
- Graphical session detected (Wayland/X11) or --gui: opens the GTK 4 / Libadwaita interface.
- Terminal/SSH without graphics, or --cli: opens the interactive console menu.
- --lang xx forces the interface language (en, es).
"""

import sys
import os
import argparse
from pathlib import Path

# Make sibling modules importable even when launched through a symlink
sys.path.insert(0, str(Path(__file__).resolve().parent))

import i18n


def _pre_parse_lang(argv):
    """Language must be set before importing modules that translate at import time."""
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


i18n.setup(_pre_parse_lang(sys.argv[1:]))
from i18n import _  # noqa: E402
import core  # noqa: E402


def has_graphical_display():
    """Checks whether an accessible graphical session exists."""
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
        return True

    uid = os.getuid()
    wayland_socket = Path(f"/run/user/{uid}/wayland-0")
    if wayland_socket.exists():
        os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
        os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        return True

    return False


def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')


def pause():
    input("\n" + _("Press Enter to continue..."))


def yes(answer):
    """Accepts the first letter of the translated 'yes' or an English 'y'."""
    return answer.strip().lower()[:1] in (_("y"), "y")


# -------------------------------------------------------------------
# Enriched terminal mode (CLI / TUI)
# -------------------------------------------------------------------
def print_banner():
    clear_screen()
    dm_info = core.get_active_display_manager()
    mode = _("Multi-Seat") if core.is_multiseat_mode() else _("Normal")
    print("\033[1;36m========================================================\033[0m")
    print("\033[1;37m                 MULTI-SEAT MANAGER                     \033[0m")
    print("\033[0;33m " + _("Boot mode: {mode} ({dm}) | Running: {running}").format(
        mode=mode, dm=core.dm_label(dm_info['enabled']), running=core.dm_label(dm_info['running'])) + "\033[0m")
    print("\033[1;36m========================================================\033[0m")


def pick_seat(default="seat1"):
    """Asks for a target seat (any seatN). Returns None if the name is invalid."""
    seats = [s for s in core.list_seats() if s != core.MAIN_SEAT]
    if seats:
        print(_("Existing seats: {seats}").format(seats=", ".join(seats)))
    name = input(_("Target seat (Enter = {default}, 'new' = next free): ").format(default=default)).strip()
    if not name:
        return default
    if name.lower() == "new":
        return core.next_seat_name()
    if not core.is_valid_seat(name) or name == core.MAIN_SEAT:
        print("\033[1;31m" + _("Invalid seat name: {seat}").format(seat=name) + "\033[0m")
        return None
    return name


def cli_enable_multiseat():
    print_banner()
    print("\033[1;33m=== " + _("Enable Multi-Seat Configuration") + " ===\033[0m")
    dm = core.get_multiseat_dm()
    if not dm:
        print("\033[1;31m" + _("No multi-seat capable display manager found.") + "\033[0m")
        print(core.multiseat_install_hint())
        pause()
        return
    print(_("This will enable {dm} and disable the other display managers to allow multiple desktops.").format(
        dm=core.dm_label(dm)))
    if not yes(input("\n" + _("Do you want to continue? (y/N): "))):
        return

    print("\n" + _("Applying configuration..."))
    ok, msg = core.set_multiseat_enabled(True)
    if ok:
        print("\033[1;32m✓ " + _("Configuration applied successfully.") + "\033[0m")
        if yes(input("\n" + _("Reboot the system now? (y/N): "))):
            print(_("Rebooting..."))
            core.request_reboot()
    else:
        print("\033[1;31m✗ " + _("Error configuring Multi-Seat: {error}").format(error=msg) + "\033[0m")
    pause()


def cli_reset_to_seat0():
    print_banner()
    print("\033[1;33m=== " + _("Return all devices to Seat 0") + " ===\033[0m")
    print(_("All devices assigned to other seats will return to the main seat, seat0."))
    if not yes(input("\n" + _("Do you want to continue? (y/N): "))):
        return
    ok, msg = core.flush_all_seats()
    if ok:
        print("\033[1;32m✓ " + _("All devices have returned to Seat 0") + "\033[0m")
    else:
        print("\033[1;31m✗ " + _("Error: {error}").format(error=msg) + "\033[0m")
    pause()


def cli_restore_normal():
    print_banner()
    print("\033[1;33m=== " + _("Restore Normal Configuration") + " ===\033[0m")
    dm = core.get_normal_dm()
    if not dm:
        print("\033[1;31m" + _("No normal display manager found (GDM, SDDM...).") + "\033[0m")
        pause()
        return
    print(_("This will enable {dm}, disable the multi-seat display manager and return all devices to seat0.").format(
        dm=core.dm_label(dm)))
    if not yes(input("\n" + _("Do you want to continue? (y/N): "))):
        return

    print("\n" + _("Restoring configuration..."))
    ok, msg = core.set_multiseat_enabled(False)
    if ok:
        print("\033[1;32m✓ " + _("Normal configuration restored successfully.") + "\033[0m")
        if yes(input("\n" + _("Reboot the system now? (y/N): "))):
            print(_("Rebooting..."))
            core.request_reboot()
    else:
        print("\033[1;31m✗ " + _("Error restoring: {error}").format(error=msg) + "\033[0m")
    pause()


def cli_assign_devices():
    print_banner()
    print("\033[1;33m=== " + _("Assign Devices to a Seat") + " ===\033[0m")
    target = pick_seat()
    if target is None:
        pause()
        return

    pending = {}  # sysfs path -> seat; nothing is applied until the user confirms
    while True:
        print_banner()
        print("\033[1;33m=== " + _("Assign Devices to {seat}").format(seat=target) + " ===\033[0m")
        print(_("Devices currently on seat0:") + "\n")

        devices = core.get_devices_for_seat(core.MAIN_SEAT)
        if not devices:
            print(_("No devices found on seat0 or the query failed."))
            pause()
            return

        for i, dev in enumerate(devices, 1):
            master_tag = " \033[1;35m[MASTER]\033[0m" if dev['is_master'] else ""
            mark = "\033[1;33m●\033[0m" if dev['path'] in pending else " "
            print(f"\033[1;32m{i:2d}.\033[0m {mark}[{dev['category']}] \033[1m{dev['desc']}\033[0m{master_tag}")
            print(f"       \033[2m{dev['path']}\033[0m")

        n_pending = len(core.collapse_assignments(pending))
        print("\n\033[1;33m" + _("{n} pending change(s) → {seat} (not applied yet)").format(n=n_pending, seat=target) + "\033[0m")
        print(_("Number = mark/unmark device | a = apply | c = clear | 0 = back"))

        choice = input("\n" + _("Your choice: ")).strip().lower()
        if choice == "0":
            if pending and not yes(input(_("Discard the pending changes? (y/N): "))):
                continue
            break
        if choice == "c":
            pending.clear()
        elif choice == "a":
            if not pending:
                print(_("Nothing to apply."))
            else:
                print("\n" + _("Applying changes..."))
                ok, msg = core.apply_seat_assignments(pending)
                if ok:
                    print("\033[1;32m✓ " + _("Changes applied"))
                    pending.clear()
                    print("\033[0m", end="")
                else:
                    print("\033[1;31m✗ " + _("Error: {error}").format(error=msg) + "\033[0m")
            pause()
        elif choice.isdigit() and 1 <= int(choice) <= len(devices):
            path = devices[int(choice) - 1]['path']
            family = [d['path'] for d in devices if d['path'] == path or d['path'].startswith(path + "/")]
            if path in pending:
                for p in family:
                    pending.pop(p, None)
            else:
                for p in family:
                    pending[p] = target
        else:
            print(_("Invalid option."))
            pause()


def cli_manage_presets():
    while True:
        print_banner()
        print("\033[1;33m=== " + _("Profile (Preset) Manager") + " ===\033[0m")
        print(_("1. Save the current state of a seat as a new profile"))
        print(_("2. Apply a profile"))
        print(_("3. View saved profiles"))
        print(_("4. Delete a profile"))
        print(_("5. Back"))

        choice = input("\n" + _("Select an option (1-5): ")).strip()
        presets = core.load_presets()

        if choice == '1':
            seat = pick_seat()
            if seat is None:
                pause()
                continue
            top_devs = core.get_top_level_paths(core.get_devices_for_seat(seat))
            if not top_devs:
                print("\n\033[1;31m" + _("No devices are currently assigned to {seat}.").format(seat=seat) + "\033[0m")
                pause()
                continue
            print("\n" + _("Main devices on {seat} to save ({n}):").format(seat=seat, n=len(top_devs)))
            for d in top_devs:
                print(f" - {d['desc']}")
            name = input("\n" + _("Enter a name for the profile (empty to cancel): ")).strip()
            if name:
                presets[name] = core.make_preset(seat, [d['path'] for d in top_devs])
                ok, path = core.save_presets(presets)
                if ok:
                    print("\033[1;32m✓ " + _("Profile '{name}' saved successfully.").format(name=name) + "\033[0m")
                else:
                    print("\033[1;31m✗ " + _("Error saving: {error}").format(error=path) + "\033[0m")
                pause()
        elif choice == '2':
            if not presets:
                print("\n" + _("No saved profiles."))
                pause()
                continue
            names = list(presets.keys())
            print("\n" + _("Available profiles:"))
            for i, n in enumerate(names, 1):
                print(_("{i}. {name} ({count} devices → {seat})").format(
                    i=i, name=n, count=len(core.preset_devices(presets[n])), seat=core.preset_seat(presets[n])))
            print(_("0. Cancel"))
            try:
                c = int(input("\n" + _("Select a profile to apply (0-{n}): ").format(n=len(names))))
            except ValueError:
                continue
            if 1 <= c <= len(names):
                sel_name = names[c - 1]
                paths = core.preset_devices(presets[sel_name])
                seat = core.preset_seat(presets[sel_name])
                ok, msg = core.attach_devices_to_seat(paths, seat)
                if not ok:
                    print("\033[1;31m✗ " + _("Profile '{name}' applied with errors: {error}").format(name=sel_name, error=msg) + "\033[0m")
                else:
                    print("\033[1;32m✓ " + _("Profile '{name}' applied ({n} devices).").format(name=sel_name, n=len(paths)) + "\033[0m")
                    if core.get_multiseat_dm() and yes(input(_("Enable the multi-seat display manager and reboot now? (y/N): "))):
                        ok, msg = core.set_multiseat_enabled(True)
                        if ok:
                            core.request_reboot()
                        else:
                            print("\033[1;31m✗ " + _("Error configuring Multi-Seat: {error}").format(error=msg) + "\033[0m")
            pause()
        elif choice == '3':
            if not presets:
                print("\n" + _("No saved profiles."))
            else:
                for n, preset in presets.items():
                    paths = core.preset_devices(preset)
                    print("\n\033[1;34m• " + n + "\033[0m " + _("({count} devices → {seat}):").format(
                        count=len(paths), seat=core.preset_seat(preset)))
                    for p in paths:
                        friendly, _icon, cat = core.get_human_name_for_device(p, p.split('/')[-1])
                        print(f"    - [{cat}] {friendly}")
            pause()
        elif choice == '4':
            if not presets:
                print("\n" + _("No saved profiles."))
                pause()
                continue
            names = list(presets.keys())
            for i, n in enumerate(names, 1):
                print(f"{i}. {n}")
            print(_("0. Cancel"))
            try:
                c = int(input("\n" + _("Select a profile to delete (0-{n}): ").format(n=len(names))))
            except ValueError:
                continue
            if 1 <= c <= len(names):
                sel_name = names[c - 1]
                if yes(input(_("Are you sure you want to delete '{name}'? (y/N): ").format(name=sel_name))):
                    ok, msg = core.delete_preset(sel_name)
                    if ok:
                        print("\033[1;32m✓ " + _("Profile deleted.") + "\033[0m")
                    else:
                        print(f"\033[1;31m✗ {msg}\033[0m")
            pause()
        elif choice == '5':
            break


def run_cli():
    try:
        _run_cli_loop()
    except (EOFError, KeyboardInterrupt):
        print()


def _run_cli_loop():
    while True:
        print_banner()
        print(_("1. Enable Multi-Seat Mode"))
        print(_("2. Manually assign devices to a seat"))
        print(_("3. Manage Profiles / Presets"))
        print(_("4. Restore Normal Configuration (and flush seats)"))
        print(_("5. Return all devices to Seat 0"))
        print(_("6. Exit"))

        choice = input("\n" + _("Select an option (1-6): ")).strip()
        if choice == '1':
            cli_enable_multiseat()
        elif choice == '2':
            cli_assign_devices()
        elif choice == '3':
            cli_manage_presets()
        elif choice == '4':
            cli_restore_normal()
        elif choice == '5':
            cli_reset_to_seat0()
        elif choice == '6':
            clear_screen()
            return


def main():
    parser = argparse.ArgumentParser(description=_("EasyMDMultiseat"))
    parser.add_argument("--gui", action="store_true", help=_("Force the GTK4/Libadwaita graphical interface"))
    parser.add_argument("--cli", action="store_true", help=_("Force the interactive console menu"))
    parser.add_argument("--lang", metavar="LANG", help=_("Interface language (en, es)"))
    args, _unknown = parser.parse_known_args()

    if args.cli:
        run_cli()
        return

    if args.gui or has_graphical_display():
        try:
            import gui
        except Exception as e:
            print(_("[Warning] Could not initialize the graphical interface ({error}).").format(error=e))
            print(_("Starting in interactive terminal mode..."))
            run_cli()
        else:
            sys.exit(gui.main())
    else:
        run_cli()


if __name__ == '__main__':
    main()
