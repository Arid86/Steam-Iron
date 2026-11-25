# gridDBSelector.py
# pyright: reportAttributeAccessIssue=false
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from gridDBHelper import SteamGridDBHelper


class SteamGridDBSelectorWindow(Adw.Window):
    def __init__(
        self,
        parent_window: Gtk.Window,
        game_name: str,
        steam_app_id: str,
        _on_icon_selected,
    ):
        super().__init__(transient_for=parent_window, modal=True)

        self.game_name = game_name
        self.steam_app_id = steam_app_id
        self._on_icon_selected = _on_icon_selected
        self.helper = SteamGridDBHelper()
        self.selected_file_path: str | None = None

        self.set_title(f"Select Icon - {game_name}")
        self.set_default_size(610, 505)

        self._build_ui()
        GLib.idle_add(self._load_icons)

    def _build_ui(self) -> None:
        root_box = Adw.ToolbarView()

        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title="Select Icon", subtitle=f"App ID:{self.steam_app_id}")
        header.set_title_widget(title)

        self.progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.progress_box.set_margin_start(12)
        self.progress_box.set_margin_end(12)
        self.progress_box.set_margin_top(12)

        self.status_label = Gtk.Label(label="Connecting to SteamGridDB...", xalign=0)
        self.status_label.add_css_class("dim-label")

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_fraction(0.0)

        self.progress_box.append(self.status_label)
        self.progress_box.append(self.progress_bar)

        self.status_page = Adw.StatusPage(vexpand=True)
        self.status_page.set_icon_name("dialog-password-symbolic")
        self.status_page.set_title("No SteamGridDB API Key Found")
        self.status_page.set_description("Add your SteamGridDB API Key in Preferences to search and download icons. You will need to login to SteamGridDB with your Steam account. You'll be able to generate an api key from your account page.")
        self.status_page.set_visible(False)

        self.scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.scrolled.add_css_class("card")
        self.scrolled.set_can_focus(False)
        self.scrolled.set_margin_start(12)
        self.scrolled.set_margin_end(12)
        self.scrolled.set_margin_top(6)
        self.scrolled.set_margin_bottom(6)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_can_focus(False)
        self.flowbox.set_focusable(False)
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_halign(Gtk.Align.CENTER)
        self.flowbox.set_row_spacing(6)
        self.flowbox.set_column_spacing(6)
        self.flowbox.set_max_children_per_line(5)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_margin_start(12)
        self.flowbox.set_margin_end(12)
        self.flowbox.set_margin_top(12)
        self.flowbox.set_margin_bottom(12)

        self.scrolled.set_child(self.flowbox)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_margin_start(12)
        button_box.set_margin_end(12)
        button_box.set_margin_top(8)
        button_box.set_margin_bottom(12)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.destroy())

        self.apply_btn = Gtk.Button(label="Apply")
        self.apply_btn.add_css_class("suggested_action")
        self.apply_btn.set_sensitive(False)
        self.apply_btn.connect("clicked", self._on_apply)

        button_box.append(cancel_btn)
        button_box.append(Gtk.Box(hexpand=True))
        button_box.append(self.apply_btn)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        layout.append(self.progress_box)
        layout.append(self.status_page)
        layout.append(self.scrolled)
        layout.append(button_box)

        root_box.add_top_bar(header)
        root_box.set_content(layout)
        self.set_content(root_box)

        self.flowbox.connect("child-activated", self._on_item_selected)

    def _load_icons(self) -> None:
        if not self.helper.api_key:
            self.progress_box.set_visible(False)
            self.scrolled.set_visible(False)
            self.status_page.set_visible(True)
            return

        self.status_label.set_text("Connecting to SteamGridDB...")
        self.progress_bar.set_fraction(0.15)
        self._force_ui_update()
        time.sleep(0.25)

        sgdb_game_id = self.helper.search_id(self.steam_app_id)
        if not sgdb_game_id:
            self.status_label.set_text("No game available for App ID: %s", sgdb_game_id)
            self.progress_bar.set_visible(False)
            return

        self.status_label.set_text("Fetching available icons...")
        self.progress_bar.set_fraction(0.30)
        self._force_ui_update()
        time.sleep(0.15)

        icons = self.helper.fetch_icons(sgdb_game_id)
        total_icons = len(icons)

        if not total_icons:
            self.status_label.set_text("No icons available for App ID: %s", sgdb_game_id)
            self.progress_bar.set_visible(False)
            return

        for index, icon in enumerate(icons, start=1):
            thumb_url = icon.get("thumb") or icon.get("url")
            icon_id = icon.get("id")

            if isinstance(icon_id, int) and isinstance(thumb_url, str):
                if self.helper.cached_icon(icon_id, thumb_url):
                    self.status_label.set_text(f"Loading icon {index} of {total_icons} from cache...")
                else:
                    self.status_label.set_text(f"Downloading icon {index} of {total_icons}...")

                fraction = 0.30 + (0.70 * (index / total_icons))
                self.progress_bar.set_fraction(fraction)
                self._force_ui_update()

                cached_path = self.helper.download_icons(icon_id, thumb_url)

                if cached_path and Gio.File.new_for_path(cached_path).query_exists():
                    self._add_icon_tile(cached_path)

            time.sleep(0.05)

        time.sleep(0.2)
        self.status_label.set_text("Loading complete...")

    def _add_icon_tile(self, file_path: str) -> None:
        image = Gtk.Image.new_from_file(file_path)
        image.set_pixel_size(96)

        child = Gtk.FlowBoxChild()
        child.set_child(image)
        child.file_path = file_path

        child.set_halign(Gtk.Align.START)
        child.set_valign(Gtk.Align.START)

        child.set_size_request(106,106)

        self.flowbox.append(child)

    def _on_apply(self, _button: Gtk.Button) -> None:
        if self.selected_file_path:
            file_path = self.helper.copy_icon(self.selected_file_path, self.steam_app_id)
            self._on_icon_selected(file_path)
            self.destroy()

    def _on_item_selected(self, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild) -> None:
        if hasattr(child, "file_path"):
            self.selected_file_path = child.file_path
            self.apply_btn.set_sensitive(True)

    def _force_ui_update(self) -> None:
        context = GLib.MainContext.default()

        while context.pending():
            context.iteration(False)
