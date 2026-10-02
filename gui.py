#!/usr/bin/env python3
"""
Multi-Seat Manager - Modern GTK 4 / Libadwaita Interface
"""

import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

import core
from i18n import _


def make_row(title, subtitle=None):
    """ActionRow whose texts are NOT parsed as Pango markup (device names may contain & or <)."""
    row = Adw.ActionRow()
    row.set_use_markup(False)
    row.set_title(title)
    if subtitle:
        row.set_subtitle(subtitle)
    return row


class MultiseatWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title(_("Multi-Seat Manager"))
        self.set_default_size(1020, 680)

        # State
        self.search_term = ""
        self.target_seat = "seat1"
        self.extra_seats = set()      # seats created in the UI that have no devices yet
        self.seat_names = []
        self._updating_seats = False
        self.devices_by_seat = {}     # seat -> devices as reported by logind
        self.current_seat = {}        # sysfs path -> seat it really belongs to
        self.all_devices = []         # every device, seat0 first
        self.devices_target = []
        self.pending = {}             # sysfs path -> seat chosen but NOT yet applied

        self.toast_overlay = Adw.ToastOverlay()
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main_box)
        self.set_content(self.toast_overlay)

        self.header_bar = Adw.HeaderBar()
        main_box.append(self.header_bar)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text(_("Refresh devices and status"))
        refresh_btn.connect("clicked", self.on_refresh_clicked)
        self.header_bar.pack_start(refresh_btn)

        self.title_widget = Adw.WindowTitle(
            title=_("Multi-Seat Manager"),
            subtitle=_("Loading system status...")
        )
        self.header_bar.set_title_widget(self.title_widget)

        self.view_stack = Adw.ViewStack()
        view_switcher = Adw.ViewSwitcher()
        view_switcher.set_stack(self.view_stack)
        view_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        self.header_bar.pack_end(view_switcher)

        self.page_devices = self.build_devices_page()
        self.page_presets = self.build_presets_page()
        self.page_system = self.build_system_page()

        self.view_stack.add_titled_with_icon(self.page_devices, "devices", _("Devices"), "video-display-symbolic")
        self.view_stack.add_titled_with_icon(self.page_presets, "presets", _("Profiles"), "emblem-default-symbolic")
        self.view_stack.add_titled_with_icon(self.page_system, "system", _("Settings"), "preferences-system-symbolic")
        main_box.append(self.view_stack)

        self.refresh_all()

    def show_toast(self, message):
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

    def show_error_dialog(self, title, message):
        dialog = Adw.MessageDialog.new(self, title, message)
        dialog.add_response("ok", _("OK"))
        dialog.present()

    # -------------------------------------------------------------
    # Page 1: Devices & Seats
    # -------------------------------------------------------------
    def build_seat_column(self, header_widgets):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_hexpand(True)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for w in header_widgets:
            header.append(w)
        box.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(listbox)
        box.append(scroll)
        return box, listbox

    def build_devices_page(self):
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page_box.set_margin_top(12)
        page_box.set_margin_bottom(12)
        page_box.set_margin_start(16)
        page_box.set_margin_end(16)

        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Search device by name, type or path..."))
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self.on_search_changed)
        filter_box.append(self.search_entry)

        flush_btn = Gtk.Button(label=_("Reset everything to Seat 0"))
        flush_btn.set_icon_name("edit-undo-symbolic")
        flush_btn.add_css_class("flat")
        flush_btn.connect("clicked", self.on_flush_devices_clicked)
        filter_box.append(flush_btn)
        page_box.append(filter_box)

        seats_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        seats_paned.set_position(500)
        seats_paned.set_vexpand(True)
        page_box.append(seats_paned)

        # Main seat column
        title0 = Gtk.Label(label=_("Seat 0 (Main)"))
        title0.add_css_class("heading")
        title0.set_halign(Gtk.Align.START)
        self.main_count_label = Gtk.Label(label="")
        self.main_count_label.add_css_class("dim-label")
        box0, self.main_list = self.build_seat_column([title0, self.main_count_label])
        seats_paned.set_start_child(box0)

        # Target seat column: dropdown + "new seat"
        self.seat_dropdown = Gtk.DropDown.new_from_strings(["seat1"])
        self.seat_dropdown.connect("notify::selected", self.on_seat_selected)
        new_seat_btn = Gtk.Button(icon_name="list-add-symbolic")
        new_seat_btn.set_tooltip_text(_("Add a new seat"))
        new_seat_btn.connect("clicked", self.on_new_seat_clicked)
        self.target_count_label = Gtk.Label(label="")
        self.target_count_label.add_css_class("dim-label")
        box1, self.target_list = self.build_seat_column(
            [self.seat_dropdown, new_seat_btn, self.target_count_label]
        )
        seats_paned.set_end_child(box1)

        # Pending-changes bar: nothing touches the system until "Apply" is pressed
        self.pending_bar = Gtk.ActionBar()
        self.pending_label = Gtk.Label(label="")
        self.pending_label.add_css_class("heading")
        self.pending_bar.pack_start(self.pending_label)
        apply_btn = Gtk.Button(label=_("Apply changes"))
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self.on_apply_pending_clicked)
        self.pending_bar.pack_end(apply_btn)
        discard_btn = Gtk.Button(label=_("Discard"))
        discard_btn.connect("clicked", self.on_discard_pending_clicked)
        self.pending_bar.pack_end(discard_btn)
        self.pending_bar.set_revealed(False)
        page_box.append(self.pending_bar)

        return page_box

    def update_seat_dropdown(self):
        """Rebuilds the seat dropdown from logind + seats created in the UI."""
        names = {s for s in core.list_seats() if s != core.MAIN_SEAT}
        names |= self.extra_seats
        names |= {self.target_seat, "seat1"}
        new_names = sorted(names, key=lambda s: (len(s), s))
        self._updating_seats = True
        # Replacing the model while the popup is still handling a click freezes GTK:
        # only touch it when the list really changed.
        if new_names != self.seat_names:
            self.seat_names = new_names
            self.seat_dropdown.set_model(Gtk.StringList.new(self.seat_names))
        self.seat_dropdown.set_selected(self.seat_names.index(self.target_seat))
        self._updating_seats = False

    def on_seat_selected(self, dropdown, _pspec):
        if self._updating_seats:
            return
        idx = dropdown.get_selected()
        if 0 <= idx < len(self.seat_names):
            self.target_seat = self.seat_names[idx]
            # Let the dropdown popup close before doing any work
            GLib.idle_add(self._refresh_idle)

    def _refresh_idle(self):
        self.refresh_all()
        return GLib.SOURCE_REMOVE

    def on_new_seat_clicked(self, btn):
        name = core.next_seat_name(set(self.seat_names) | {core.MAIN_SEAT})
        self.extra_seats.add(name)
        self.target_seat = name
        self.refresh_all()
        self.show_toast(_("{seat} created. Move devices to it to activate it.").format(seat=name))

    def on_search_changed(self, entry):
        self.search_term = entry.get_text().strip().lower()
        self.populate_device_lists()

    def _clear(self, listbox):
        while True:
            row = listbox.get_first_child()
            if not row:
                break
            listbox.remove(row)

    def _matches(self, dev):
        term = self.search_term
        return not term or term in dev['desc'].lower() or term in dev['category'].lower() or term in dev['path'].lower()

    def effective_seat(self, path):
        return self.pending.get(path, self.current_seat.get(path))

    def populate_device_lists(self):
        self._clear(self.main_list)
        self._clear(self.target_list)
        target = self.target_seat

        left = [d for d in self.all_devices if self.effective_seat(d['path']) == core.MAIN_SEAT and self._matches(d)]
        right = [d for d in self.all_devices if self.effective_seat(d['path']) == target and self._matches(d)]

        self.main_count_label.set_text(_("{n} devices").format(n=len(left)))
        for dev in left:
            self.main_list.append(self.create_device_row(dev, core.MAIN_SEAT))

        self.target_count_label.set_text(_("{n} devices").format(n=len(right)))
        if not right:
            self.target_list.append(make_row(
                _("No devices assigned to {seat}").format(seat=target),
                _("Assign devices from Seat 0 or apply a profile."),
            ))
        else:
            for dev in right:
                self.target_list.append(self.create_device_row(dev, target))

        self.update_pending_bar()

    def update_pending_bar(self):
        n = len(core.collapse_assignments(self.pending))
        self.pending_bar.set_revealed(n > 0)
        self.pending_label.set_text(_("{n} pending change(s) — nothing is applied until you confirm").format(n=n))

    def create_device_row(self, dev, shown_in):
        path = dev['path']
        short_path = path
        if len(short_path) > 55:
            short_path = "..." + short_path[-52:]
        subtitle = f"{dev['category']} • {short_path}"
        if dev['is_master']:
            subtitle = f"⭐ MASTER • {subtitle}"
        is_pending = path in self.pending
        if is_pending:
            subtitle = "● " + _("Pending: {src} → {dst}").format(
                src=self.current_seat.get(path, "?"), dst=self.pending[path]) + " • " + subtitle
        row = make_row(dev['desc'], subtitle)
        if is_pending:
            row.add_css_class("accent")

        icon = Gtk.Image.new_from_icon_name(dev['icon'])
        icon.set_pixel_size(24)
        row.add_prefix(icon)

        if is_pending:
            btn = Gtk.Button(label=_("Undo"))
            btn.set_icon_name("edit-undo-symbolic")
            btn.connect("clicked", lambda b, p=path: self.unstage_device(p))
        else:
            dest = self.target_seat if shown_in == core.MAIN_SEAT else core.MAIN_SEAT
            to_main = dest == core.MAIN_SEAT
            btn = Gtk.Button(label=_("To {seat}").format(seat=dest))
            btn.set_icon_name("go-previous-symbolic" if to_main else "go-next-symbolic")
            btn.add_css_class("destructive-action" if to_main else "suggested-action")
            btn.connect("clicked", lambda b, p=path, t=dest: self.stage_device(p, t))
        btn.set_valign(Gtk.Align.CENTER)
        row.add_suffix(btn)
        return row

    def _family(self, path):
        """The device plus its sub-devices currently on the same seat (they move together)."""
        seat = self.current_seat.get(path)
        return [d['path'] for d in self.all_devices
                if self.current_seat.get(d['path']) == seat
                and (d['path'] == path or d['path'].startswith(path + "/"))]

    def stage_device(self, path, target_seat):
        """Marks a device (and its sub-devices) to move; nothing is applied yet."""
        for p in self._family(path):
            if self.current_seat.get(p) == target_seat:
                self.pending.pop(p, None)
            else:
                self.pending[p] = target_seat
        self.populate_device_lists()

    def unstage_device(self, path):
        for p in [path] + [q for q in self.pending if q.startswith(path + "/")]:
            self.pending.pop(p, None)
        self.populate_device_lists()

    def on_discard_pending_clicked(self, btn):
        self.pending.clear()
        self.populate_device_lists()

    def on_apply_pending_clicked(self, btn):
        count = len(core.collapse_assignments(self.pending))
        seats = sorted(set(self.pending.values()))
        dialog = Adw.MessageDialog.new(
            self,
            _("Apply {n} change(s)?").format(n=count),
            _("Devices will be reassigned to: {seats}. This changes the real seat configuration.").format(
                seats=", ".join(seats)),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("apply", _("Apply changes"))
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response_id):
            if response_id != "apply":
                return
            ok, msg = core.apply_seat_assignments(self.pending)
            for seat in seats:
                self.extra_seats.discard(seat)
            self.refresh_all()  # drops whatever was really applied from the pending set
            if ok:
                self.show_toast(_("Changes applied"))
            else:
                self.show_error_dialog(_("Some changes could not be applied"), msg)

        dialog.connect("response", on_response)
        dialog.present()

    def on_flush_devices_clicked(self, btn):
        dialog = Adw.MessageDialog.new(
            self,
            _("Reset all seats?"),
            _("All devices assigned to other seats will return to the main seat, seat0."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("flush", _("Reset"))
        dialog.set_response_appearance("flush", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response_id):
            if response_id == "flush":
                ok, msg = core.flush_all_seats()
                if ok:
                    self.extra_seats.clear()
                    self.pending.clear()
                    self.show_toast(_("All devices have returned to Seat 0"))
                    self.refresh_all()
                else:
                    self.show_error_dialog(_("Error"), msg)

        dialog.connect("response", on_response)
        dialog.present()

    # -------------------------------------------------------------
    # Page 2: Presets
    # -------------------------------------------------------------
    def build_presets_page(self):
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page_box.set_margin_top(16)
        page_box.set_margin_bottom(16)
        page_box.set_margin_start(20)
        page_box.set_margin_end(20)

        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        save_current_btn = Gtk.Button(label=_("Save selected seat as new profile"))
        save_current_btn.set_icon_name("document-new-symbolic")
        save_current_btn.add_css_class("suggested-action")
        save_current_btn.connect("clicked", self.on_create_preset_clicked)
        top_bar.append(save_current_btn)

        info_label = Gtk.Label(label=_("Profiles store the main devices assigned to the seat chosen in the Devices tab."))
        info_label.add_css_class("dim-label")
        top_bar.append(info_label)
        page_box.append(top_bar)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.presets_group = Adw.PreferencesGroup()
        scroll.set_child(self.presets_group)
        page_box.append(scroll)
        self.presets_scroll = scroll
        return page_box

    def populate_presets(self):
        presets = core.load_presets()

        # PreferencesGroup has no "remove all": replace it with a fresh one
        new_group = Adw.PreferencesGroup()
        new_group.set_title(_("Saved Profiles"))
        new_group.set_description(
            _("{n} profile(s) available in {path}").format(n=len(presets), path=core.get_presets_file())
        )
        self.presets_scroll.set_child(new_group)
        self.presets_group = new_group

        if not presets:
            self.presets_group.add(make_row(
                _("No saved profiles"),
                _("Assign devices to a seat and click 'Save selected seat as new profile'."),
            ))
            return

        for name, preset in presets.items():
            paths = core.preset_devices(preset)
            seat = core.preset_seat(preset)
            expander = Adw.ExpanderRow()
            expander.set_use_markup(False)
            expander.set_title(name)
            expander.set_subtitle(_("{n} main device(s) • {seat}").format(n=len(paths), seat=seat))
            expander.add_prefix(Gtk.Image.new_from_icon_name("emblem-default-symbolic"))

            btn_apply = Gtk.Button(label=_("Apply"))
            btn_apply.set_icon_name("media-playback-start-symbolic")
            btn_apply.add_css_class("suggested-action")
            btn_apply.set_valign(Gtk.Align.CENTER)
            btn_apply.connect("clicked", lambda b, n=name, p=paths, s=seat: self.on_apply_preset(n, p, s))
            expander.add_suffix(btn_apply)

            btn_del = Gtk.Button(icon_name="edit-delete-symbolic")
            btn_del.set_tooltip_text(_("Delete this profile"))
            btn_del.add_css_class("destructive-action")
            btn_del.set_valign(Gtk.Align.CENTER)
            btn_del.connect("clicked", lambda b, n=name: self.on_delete_preset(n))
            expander.add_suffix(btn_del)

            for path in paths:
                friendly, icon, cat = core.get_human_name_for_device(path, path.split('/')[-1])
                dev_row = make_row(friendly, f"{cat} • {path}")
                dev_row.add_prefix(Gtk.Image.new_from_icon_name(icon))
                expander.add_row(dev_row)

            self.presets_group.add(expander)

    def on_create_preset_clicked(self, btn):
        seat = self.target_seat
        top_devices = core.get_top_level_paths(self.devices_target)
        if not top_devices:
            self.show_error_dialog(
                _("{seat} is empty").format(seat=seat),
                _("First assign the desired devices to the seat in the 'Devices' tab before creating a profile."),
            )
            return

        dialog = Adw.MessageDialog.new(
            self,
            _("Save New Profile"),
            _("{n} main device(s) of {seat} will be saved.").format(n=len(top_devices), seat=seat),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save"))
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")

        entry = Gtk.Entry()
        entry.set_placeholder_text(_("E.g. Two Players Setup, Secondary Desk..."))
        entry.connect("activate", lambda e: dialog.response("save"))
        dialog.set_extra_child(entry)

        def on_response(d, response_id):
            if response_id == "save":
                name = entry.get_text().strip()
                if not name:
                    self.show_toast(_("Invalid profile name"))
                    return
                presets = core.load_presets()
                presets[name] = core.make_preset(seat, [dev['path'] for dev in top_devices])
                ok, path = core.save_presets(presets)
                if ok:
                    self.show_toast(_("Profile '{name}' saved").format(name=name))
                    self.populate_presets()
                else:
                    self.show_error_dialog(_("Error saving profile"), path)

        dialog.connect("response", on_response)
        dialog.present()

    def on_apply_preset(self, name, paths, seat):
        multi_dm = core.get_multiseat_dm()
        dialog = Adw.MessageDialog.new(
            self,
            _("Apply profile '{name}'?").format(name=name),
            _("{n} device(s) will be assigned to {seat}.").format(n=len(paths), seat=seat)
            + "\n" + _("Do you also want to prepare the system with a multi-seat display manager?"),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("apply_only", _("Only Assign Devices"))
        dialog.add_response("apply_and_reboot", _("Assign and Reboot"))
        dialog.set_response_appearance("apply_and_reboot", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_enabled("apply_and_reboot", multi_dm is not None)

        def on_response(d, response_id):
            if response_id not in ("apply_only", "apply_and_reboot"):
                return
            ok, msg = core.attach_devices_to_seat(paths, seat)
            self.extra_seats.discard(seat)
            self.target_seat = seat
            self.refresh_all()
            if not ok:
                self.show_error_dialog(_("Profile '{name}' could not be fully applied").format(name=name), msg)
                return
            self.show_toast(_("Profile '{name}' applied ({n} devices)").format(name=name, n=len(paths)))

            if response_id == "apply_and_reboot":
                ok, msg = core.set_multiseat_enabled(True)
                if ok:
                    self.prompt_reboot_confirmation()
                else:
                    self.show_error_dialog(_("Error enabling Multi-Seat"), msg)

        dialog.connect("response", on_response)
        dialog.present()

    def on_delete_preset(self, name):
        dialog = Adw.MessageDialog.new(
            self,
            _("Delete profile '{name}'?").format(name=name),
            _("This action cannot be undone."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response_id):
            if response_id == "delete":
                ok, msg = core.delete_preset(name)
                if ok:
                    self.show_toast(_("Profile '{name}' deleted").format(name=name))
                    self.populate_presets()
                else:
                    self.show_error_dialog(_("Error deleting profile"), msg)

        dialog.connect("response", on_response)
        dialog.present()

    # -------------------------------------------------------------
    # Page 3: System Settings & Display Manager
    # -------------------------------------------------------------
    def build_system_page(self):
        page = Adw.PreferencesPage()

        group_status = Adw.PreferencesGroup()
        group_status.set_title(_("Current System Status"))
        page.add(group_status)

        self.row_dm_status = make_row(_("Display Manager"))
        self.row_dm_status.add_prefix(Gtk.Image.new_from_icon_name("preferences-desktop-display-symbolic"))
        group_status.add(self.row_dm_status)

        self.row_seats_status = make_row(_("Seats Configured in systemd"))
        self.row_seats_status.add_prefix(Gtk.Image.new_from_icon_name("system-run-symbolic"))
        group_status.add(self.row_seats_status)

        self.group_mode = Adw.PreferencesGroup()
        self.group_mode.set_title(_("Operating Mode"))
        page.add(self.group_mode)

        self.row_enable_multi = make_row(_("Enable Multi-Seat Mode"))
        self.row_enable_multi.add_prefix(Gtk.Image.new_from_icon_name("user-available-symbolic"))
        self.btn_enable = Gtk.Button(label=_("Enable Multi-Seat"))
        self.btn_enable.set_icon_name("object-select-symbolic")
        self.btn_enable.add_css_class("suggested-action")
        self.btn_enable.set_valign(Gtk.Align.CENTER)
        self.btn_enable.connect("clicked", self.on_enable_multiseat_clicked)
        self.row_enable_multi.add_suffix(self.btn_enable)
        self.group_mode.add(self.row_enable_multi)

        self.row_restore_normal = make_row(_("Restore Normal Mode"))
        self.row_restore_normal.add_prefix(Gtk.Image.new_from_icon_name("edit-undo-symbolic"))
        self.btn_restore = Gtk.Button(label=_("Restore Normal"))
        self.btn_restore.set_icon_name("view-refresh-symbolic")
        self.btn_restore.set_valign(Gtk.Align.CENTER)
        self.btn_restore.connect("clicked", self.on_restore_normal_clicked)
        self.row_restore_normal.add_suffix(self.btn_restore)
        self.group_mode.add(self.row_restore_normal)

        group_actions = Adw.PreferencesGroup()
        group_actions.set_title(_("Session and Reboot Actions"))
        page.add(group_actions)

        row_reboot = make_row(
            _("Reboot the System"),
            _("Cleanly applies all hardware and graphics driver changes."),
        )
        row_reboot.add_prefix(Gtk.Image.new_from_icon_name("system-reboot-symbolic"))
        btn_reboot = Gtk.Button(label=_("Reboot Now"))
        btn_reboot.add_css_class("destructive-action")
        btn_reboot.set_valign(Gtk.Align.CENTER)
        btn_reboot.connect("clicked", lambda b: self.prompt_reboot_confirmation())
        row_reboot.add_suffix(btn_reboot)
        group_actions.add(row_reboot)

        return page

    def update_system_status(self):
        dm_info = core.get_active_display_manager()
        enabled = dm_info['enabled']
        running = dm_info['running']
        multi_dm = core.get_multiseat_dm()
        normal_dm = core.get_normal_dm()

        mode = _("Multi-Seat Mode") if core.is_multiseat_mode() else _("Standard Mode")
        self.title_widget.set_subtitle(
            _("{mode} (boot: {enabled}, running: {running})").format(
                mode=mode, enabled=core.dm_label(enabled), running=core.dm_label(running))
        )
        self.row_dm_status.set_subtitle(
            _("Configured for boot: {enabled} • Running: {running}").format(
                enabled=core.dm_label(enabled), running=core.dm_label(running))
        )
        seats = [core.MAIN_SEAT] + [s for s in self.seat_names if s not in self.extra_seats]
        self.row_seats_status.set_subtitle(", ".join(seats))

        self.group_mode.set_description(
            _("Multi-seat needs a display manager that can run several desktops at once. "
              "Detected: {multi}. Normal mode uses: {normal}.").format(
                multi=core.dm_label(multi_dm) if multi_dm else _("none installed"),
                normal=core.dm_label(normal_dm) if normal_dm else _("none"))
        )
        if multi_dm:
            self.row_enable_multi.set_subtitle(
                _("Enables {dm} and disables the other display managers. Seat 0 and the other seats can log in simultaneously.").format(
                    dm=core.dm_label(multi_dm))
            )
        else:
            self.row_enable_multi.set_subtitle(core.multiseat_install_hint())
        self.btn_enable.set_sensitive(multi_dm is not None)

        if normal_dm:
            self.row_restore_normal.set_subtitle(
                _("Enables {dm}, disables {multi} and returns all devices to Seat 0.").format(
                    dm=core.dm_label(normal_dm), multi=core.dm_label(multi_dm) if multi_dm else "-")
            )
        else:
            self.row_restore_normal.set_subtitle(_("No normal display manager found."))
        self.btn_restore.set_sensitive(normal_dm is not None)

    def on_enable_multiseat_clicked(self, btn):
        dm = core.dm_label(core.get_multiseat_dm())
        dialog = Adw.MessageDialog.new(
            self,
            _("Enable Multi-Seat Mode"),
            _("This will configure {dm} for the next boot and disable the other display managers.").format(dm=dm)
            + "\n\n" + _("Your current session will stay open so you can save your work.")
            + "\n" + _("Apply the change now?"),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("apply", _("Apply and Continue"))
        dialog.add_response("apply_reboot", _("Apply and Reboot Now"))
        dialog.set_response_appearance("apply_reboot", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response_id):
            if response_id in ("apply", "apply_reboot"):
                ok, msg = core.set_multiseat_enabled(True)
                if ok:
                    self.show_toast(_("Multi-Seat mode configured for next boot"))
                    self.refresh_all()
                    if response_id == "apply_reboot":
                        core.request_reboot()
                else:
                    self.show_error_dialog(_("Error enabling Multi-Seat"), msg)

        dialog.connect("response", on_response)
        dialog.present()

    def on_restore_normal_clicked(self, btn):
        dialog = Adw.MessageDialog.new(
            self,
            _("Restore Normal Mode"),
            _("All devices will be reset to Seat 0 (loginctl flush-devices) and {dm} will be set as the display manager.").format(
                dm=core.dm_label(core.get_normal_dm()))
            + "\n\n" + _("Do you want to continue?"),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("restore", _("Restore and Continue"))
        dialog.add_response("restore_reboot", _("Restore and Reboot"))
        dialog.set_response_appearance("restore_reboot", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response_id):
            if response_id in ("restore", "restore_reboot"):
                ok, msg = core.set_multiseat_enabled(False)
                if ok:
                    self.extra_seats.clear()
                    self.show_toast(_("Normal configuration restored"))
                    self.refresh_all()
                    if response_id == "restore_reboot":
                        core.request_reboot()
                else:
                    self.show_error_dialog(_("Error restoring configuration"), msg)

        dialog.connect("response", on_response)
        dialog.present()

    def prompt_reboot_confirmation(self):
        dialog = Adw.MessageDialog.new(
            self,
            _("Reboot the computer?"),
            _("The system will reboot immediately. Make sure you have saved all your work."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("reboot", _("Reboot Now"))
        dialog.set_response_appearance("reboot", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response_id):
            if response_id == "reboot":
                core.request_reboot()

        dialog.connect("response", on_response)
        dialog.present()

    # -------------------------------------------------------------
    # Shared Helpers
    # -------------------------------------------------------------
    def refresh_all(self):
        self.update_seat_dropdown()
        seats = [core.MAIN_SEAT] + [s for s in self.seat_names]
        self.devices_by_seat = {seat: core.get_devices_for_seat(seat) for seat in seats}
        self.all_devices = [d for seat in seats for d in self.devices_by_seat[seat]]
        self.current_seat = {d['path']: d['seat'] for d in self.all_devices}
        self.devices_target = self.devices_by_seat.get(self.target_seat, [])
        # Forget staged moves that are done or whose device disappeared
        self.pending = {
            p: s for p, s in self.pending.items()
            if p in self.current_seat and self.current_seat[p] != s
        }
        self.populate_device_lists()
        self.populate_presets()
        self.update_system_status()

    def on_refresh_clicked(self, btn):
        self.refresh_all()
        self.show_toast(_("Devices and status refreshed"))


class MultiseatApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.ramos_adrian.EasyMDMultiseat",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = MultiseatWindow(application=self)
        win.present()


def main():
    app = MultiseatApp()
    return app.run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
