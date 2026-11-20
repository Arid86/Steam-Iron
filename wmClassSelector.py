# wmClassSelector.py
# pyright: reportAttributeAccessIssue=false
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

from configManager import ConfigManager
from wmClassHelper import WMClassHelper


class WMClassSelectorWindow(Adw.Window):
    def __init__(
        self,
        parent_window: Gtk.Window,
        steam_app_id: str | None,
        on_process_selected,
        game_name: str | None = None,
    ) -> None:
        super().__init__(transient_for=parent_window, modal=True)

        self.helper = WMClassHelper()
        self.ConfigManager = ConfigManager()
        self.steam_app_id = steam_app_id
        self.game_name = game_name
        self._on_process_selected = on_process_selected
        self.selected_process: str | None = None

        self.set_title("Select Game Process / Window")
        self.set_default_size(500, 400)

        self._build_ui()
        GLib.idle_add(self._load_processes)

    def _build_ui(self) -> None:
        root_box = Adw.ToolbarView()

        header = Adw.HeaderBar()
        subtitle = (
            f"{self.game_name} (App ID: {self.steam_app_id})"
            if self.game_name
            else f"App ID: {self.steam_app_id}"
        )
        title_widget = Adw.WindowTitle(title="Select Window / Process", subtitle=subtitle)
        header.set_title_widget(title_widget)

        self.status_page = Adw.StatusPage(vexpand=True)
        self.status_page.set_title("Scanning active processes...")
        self.status_page.set_icon_name("preferences-system-windows-symbolic")

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.start()
        self.status_page.set_child(self.spinner)

        self.list_box = Gtk.ListBox(vexpand=True)
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-selected", self._on_item_selected)

        self.scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.scrolled.add_css_class("card")
        self.scrolled.set_margin_start(12)
        self.scrolled.set_margin_end(12)
        self.scrolled.set_margin_top(12)
        self.scrolled.set_margin_bottom(12)
        self.scrolled.set_child(self.list_box)
        self.scrolled.set_visible(False)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_margin_start(12)
        button_box.set_margin_end(12)
        button_box.set_margin_top(12)
        button_box.set_margin_bottom(12)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.destroy())

        self.apply_btn = Gtk.Button(label="Apply")
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.set_sensitive(False)
        self.apply_btn.connect("clicked", self._on_apply)

        button_box.append(cancel_btn)
        button_box.append(Gtk.Box(hexpand=True))
        button_box.append(self.apply_btn)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        layout.append(self.status_page)
        layout.append(self.scrolled)
        layout.append(button_box)

        root_box.add_top_bar(header)
        root_box.set_content(layout)
        self.set_content(root_box)

    def _load_processes(self) -> None:
        self._force_ui_update()
        time.sleep(0.3)

        self.helper.get_processes(
            self._add_process_row,
            steam_app_id=self.steam_app_id,
            game_name=self.game_name,
        )

    def _add_process_row(self, rows: list[dict[str, str]], error: str | None) -> None:
        self.spinner.stop()

        if error or not rows:
            self.status_page.set_title("No Matching Processes Found")
            self.status_page.set_description(error or "Ensure the target game is running.")
            return

        self.status_page.set_visible(False)
        self.scrolled.set_visible(True)

        for row_data in rows:
            wmclass = row_data.get("wmclass", "")
            steam_app_id = row_data.get("steam_app_id")
            title = row_data.get("title", "Untitled Process")

            if not wmclass:
                continue

            row = Adw.ActionRow()
            row.set_title(title)
            row.set_subtitle(f"Steam AppID: {steam_app_id} | StartupWMClass: {wmclass}")
            row.wmclass = wmclass

            ignore_btn = Gtk.Button.new_from_icon_name("feather-eye-symbolic")
            ignore_btn.add_css_class("flat")
            ignore_btn.set_valign(Gtk.Align.CENTER)
            ignore_btn.set_tooltip_text("Ignore Process")

            ignore_btn.connect(
                "clicked",
                lambda _btn, p_title=title, r=row: self._on_ignore_process(p_title, r),
            )
            row.add_suffix(ignore_btn)

            self.list_box.append(row)

    def _on_ignore_process(self, process_title: str, row: Adw.ActionRow):
        if self.ConfigManager.add_user_ignored_process(process_title):
            self.list_box.remove(row)

        if not self.list_box.get_first_child():
            self.scrolled.set_visible(False)
            self.status_page.set_visible(True)
            self.status_page.set_title("No Matching Processes Remaining")
            self.status_page.set_description("All scanned processes were ignored.")
            self.apply_btn.set_sensitive(False)

    def _on_item_selected(self, _list_box: Gtk.ListBox, row: Adw.ActionRow | None) -> None:
        if row and hasattr(row, "wmclass"):
            self.selected_process = row.wmclass
            self.apply_btn.set_sensitive(True)

    def _on_apply(self, _button: Gtk.Button) -> None:
        if self.selected_process:
            self._on_process_selected(self.selected_process)
            self.destroy()

    def _force_ui_update(self) -> None:
        context = GLib.MainContext.default()

        while context.pending():
            context.iteration(False)
