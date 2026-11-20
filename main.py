# main.py
# pyright: reportAttributeAccessIssue=false
import configparser
import io
import logging
import os
import re
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from configManager import ConfigManager
from gridDBSelector import SteamGridDBSelectorWindow
from preferencesWindow import PreferencesWindow
from wmClassSelector import WMClassSelectorWindow

logger = logging.getLogger(__name__)

class CaseSensitiveConfigParser(configparser.ConfigParser):
    """ConfigParser preserving case sensitivity for .desktop files"""

    def optionxform(self, optionstr: str) -> str:
        return optionstr

class DesktopFileHandler:
    """FileHandler for manipulating .desktop files specific to steam shortcuts"""

    DESKTOP_ENTRY = "Desktop Entry"

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.parser = CaseSensitiveConfigParser(interpolation=None)
        self.raw_content = ""
        self.load()

    def load(self) -> None:
        """Reads .desktop file and loads into parser"""

        with open(self.file_path, "r", encoding="utf-8") as file:
            self.raw_content = file.read()

        self.parser.clear()
        self.parser.read_string(self.raw_content)

    def save(self, content: str | None = None) -> None:
        data_to_write = content if content is not None else self.to_string()
        with open(self.file_path, "w", encoding="utf-8") as file:
            file.write(data_to_write)
        self.raw_content = data_to_write

    def delete(self) -> None:
        if os.path.exists(self.file_path):
            gio_file = Gio.File.new_for_path(self.file_path)
            gio_file.trash(cancellable=None)
            logger.info("Moved file to trash: %s", self.file_path)

    def get_exec(self) -> str:
        if self.parser.has_section(self.DESKTOP_ENTRY):
            return self.parser.get(self.DESKTOP_ENTRY, "Exec", fallback="")
        return ""

    def get_steam_app_id(self) -> str | None:
        exec = self.get_exec()
        match = re.search(r"steam://rungameid/(\d+)", exec, re.IGNORECASE)

        if match:
            return match.group(1)
        return None

    def get_icon(self) -> str:
        if self.parser.has_section(self.DESKTOP_ENTRY):
            return self.parser.get(self.DESKTOP_ENTRY, "Icon", fallback="")
        return ""

    def set_icon(self, icon_path: str) -> None:
        if not self.parser.has_section(self.DESKTOP_ENTRY):
            self.parser.add_section(self.DESKTOP_ENTRY)
        self.parser.set(self.DESKTOP_ENTRY, "Icon", icon_path)

    def get_nodisplay(self) -> bool:
        if self.parser.has_option(self.DESKTOP_ENTRY, "NoDisplay"):
            return self.parser.getboolean(self.DESKTOP_ENTRY, "NoDisplay")
        return False

    def set_nodisplay(self, value: bool) -> None:
        if not self.parser.has_section(self.DESKTOP_ENTRY):
            self.parser.add_section(self.DESKTOP_ENTRY)
        self.parser.set(self.DESKTOP_ENTRY, "NoDisplay", "true" if value else "false")

    def get_wmclass(self) -> str:
        if self.parser.has_option(self.DESKTOP_ENTRY, "StartupWMClass"):
            return self.parser.get(self.DESKTOP_ENTRY, "StartupWMClass", fallback="")
        return ""

    def set_wmclass(self, wmclass: str) -> None:
        if not self.parser.has_section(self.DESKTOP_ENTRY):
            self.parser.add_section(self.DESKTOP_ENTRY)
        self.parser.set(self.DESKTOP_ENTRY, "StartupWMClass", wmclass)

    def to_string(self) -> str:
        output = io.StringIO()
        self.parser.write(output, space_around_delimiters=False)
        return output.getvalue()

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.set_title("Steam Iron")
        self.set_default_size(900, 726)

        self._setup_css()

        self.current_desktop_file: DesktopFileHandler
        self.ConfigManager = ConfigManager()
        self._update_ui: bool = False

        self._build_ui()

    def _setup_css(self) -> None:
        css_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")

        if os.path.exists(css_file_path):
            css_provider = Gtk.CssProvider()
            css_provider.load_from_path(css_file_path)

            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        else:
            logger.warning("CSS file not found at: %s", css_file_path)

    def _build_ui(self) -> None:
        root_box = Adw.ToolbarView()

        header_bar = self._build_topbar()
        main_box = self._build_mainbox()

        root_box.add_top_bar(header_bar)
        root_box.set_content(main_box)

        self.set_content(root_box)

        self._populate_sidebar()

        GLib.idle_add(self._adjust_window_size)

    def _build_mainbox(self) -> Gtk.Box:
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_box.set_hexpand(True)
        main_box.set_vexpand(True)

        sidebar = self._build_sidebar()
        editor = self._build_editor()

        main_box.append(sidebar)
        main_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        main_box.append(editor)

        return main_box

    def _build_topbar(self) -> Adw.HeaderBar:
        header_bar = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title="Steam Iron", subtitle="Steam Shortcut Manager")

        pref_btn = Gtk.Button.new_from_icon_name("preferences-system-symbolic")
        pref_btn.set_tooltip_text("Preferences")
        pref_btn.connect("clicked", self._on_open_preferences)

        header_bar.set_title_widget(title_widget)
        header_bar.pack_end(pref_btn)
        return header_bar

    def _build_sidebar(self) -> Gtk.Box:
        self.sidebar = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_start=18,
            margin_end=12,
            margin_top=12,
            margin_bottom=18,
            hexpand=False,
            vexpand=True,
        )
        self.sidebar.set_size_request(320, -1)

        scrolled =  Gtk.ScrolledWindow(
            hexpand=False,
            vexpand=True,
        )

        scrolled.add_css_class("card")
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-selected", self._on_game_selected)

        scrolled.set_child(self.list_box)

        self.sidebar_status = Adw.StatusPage(
            hexpand=True,
            vexpand=True,
            icon_name="preferences-system-windows-symbolic",
            title="No Shortcuts Available",
            description="No Steam shortcuts found, or all entries are ignored."
        )
        status_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        status_card.add_css_class("card")
        status_card.append(self.sidebar_status)

        self.sidebar_stack =Gtk.Stack(
            hexpand=True,
            vexpand=True,
        )
        self.sidebar_stack.add_named(scrolled, "list")
        self.sidebar_stack.add_named(status_card, "empty")
        self.sidebar_stack.set_visible_child_name("list")

        self.sidebar.append(self.sidebar_stack)

        return self.sidebar

    def _populate_sidebar(self) -> None:
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        desktop_file_dir = os.path.expanduser("~/.local/share/applications")
        if not os.path.exists(desktop_file_dir):
            return

        BLACKLIST = self.ConfigManager.get_full_ignored_shortcuts()
        self.MAX_LINE_LENGTH = 0

        for filename in sorted(os.listdir(desktop_file_dir)):
            if not filename.endswith(".desktop") or filename in BLACKLIST:
                continue

            full_path = os.path.join(desktop_file_dir, filename)

            try:
                handler = DesktopFileHandler(full_path)
            except (configparser.Error, OSError) as Error:
                logger.warning("Failed to parse %s: %s", filename, Error)
                continue

            if not handler.parser.has_section(handler.DESKTOP_ENTRY):
                continue

            categories = handler.parser.get(handler.DESKTOP_ENTRY, "Categories", fallback="")
            exec = handler.get_exec().lower()
            # exec = handler.parser.get(handler.DESKTOP_ENTRY, "Exec", fallback="").lower()

            is_game_category = "Game" in categories.split(";")
            is_steam_game = "steam://rungameid" in exec or "steamapps" in exec

            if not (is_game_category and is_steam_game):
                continue

            for line in handler.raw_content.splitlines():
                self.MAX_LINE_LENGTH = max(self.MAX_LINE_LENGTH, len(line))

            game_name = handler.parser.get(handler.DESKTOP_ENTRY, "Name", fallback=filename)
            game_icon = handler.parser.get(handler.DESKTOP_ENTRY, "Icon", fallback="")

            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            row_box.set_margin_start(12)
            row_box.set_margin_end(12)
            row_box.set_margin_top(8)
            row_box.set_margin_bottom(8)

            if game_icon.startswith("/"):
                icon_widget = Gtk.Image.new_from_file(game_icon)
            else:
                icon_name = game_icon if game_icon else "application-x-executable"
                icon_widget = Gtk.Image.new_from_icon_name(icon_name)
            icon_widget.set_pixel_size(32)
            icon_widget.set_margin_end(12)

            label= Gtk.Label(label=game_name, xalign=0, hexpand=True)
            label.set_margin_end(48)

            is_hidden = handler.get_nodisplay()

            hidden_icon = Gtk.Image.new_from_icon_name("feather-eye-off-symbolic")
            hidden_icon.set_tooltip_text("Shortcut Hidden (NoDisplay)")
            hidden_icon.add_css_class("dim-label")
            hidden_icon.set_margin_end(12)
            hidden_icon.set_visible(is_hidden)

            blacklist_button = Gtk.Button.new_from_icon_name("feather-eye-symbolic")
            blacklist_button.add_css_class("flat")
            blacklist_button.set_valign(Gtk.Align.CENTER)
            blacklist_button.set_tooltip_text("Ignore Shortcut")

            blacklist_button.connect("clicked", self._on_blacklist, filename)

            delete_button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            delete_button.add_css_class("flat")
            delete_button.add_css_class("destructive-action")
            delete_button.set_valign(Gtk.Align.CENTER)
            delete_button.set_margin_end(4)
            delete_button.set_tooltip_text("Delete Shortcut")

            delete_button.connect("clicked", self._on_delete, full_path, row, game_name)

            row.hidden_icon = hidden_icon
            row.icon_widget = icon_widget

            row_box.append(hidden_icon)
            row_box.append(icon_widget)
            row_box.append(label)
            row_box.append(blacklist_button)
            row_box.append(delete_button)

            row.set_child(row_box)
            row.full_path = full_path

            self.list_box.append(row)

        if self.list_box.get_first_child() is None:
            self.sidebar_stack.set_visible_child_name("empty")
            self.nodisplay_row.set_sensitive(False)
            self.wmclass_btn.set_sensitive(False)
            self.griddb_btn.set_sensitive(False)
            self.text_buffer.set_text("")
        else:
            self.sidebar_stack.set_visible_child_name("list")

        first_row = self.list_box.get_row_at_index(0)
        self.list_box.select_row(first_row)

    def _build_editor(self) -> Gtk.Box:
        editor_pane = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=18,
            hexpand=True,
            vexpand=True,
        )

        editor_pane.append(self._build_editor_quick_actions())
        editor_pane.append(self._build_editor_text())
        editor_pane.append(self._build_editor_io_actions())

        return editor_pane

    def _build_editor_quick_actions(self) -> Adw.PreferencesGroup:
        # Quick Actions Group
        quick_actions = Adw.PreferencesGroup(title="Quick Actions", description="Quickly update desktop file properties.")

        #No Display
        self.nodisplay_row = Adw.SwitchRow(title="Shortcut Hidden", subtitle="Toggles NoDisplay=True/False")
        self.nodisplay_row.set_sensitive(False)
        self.nodisplay_row.connect("notify::active", self._on_nodisplay)

        #Startup Window Manager Class
        self.wmclass_row = Adw.ActionRow(title="Shortcut Dock Icon", subtitle="Detect running process and set StartupWMClass=")
        self.wmclass_btn = Gtk.Button(label="Detect")
        self.wmclass_btn.set_valign(Gtk.Align.CENTER)
        self.wmclass_btn.set_sensitive(False)
        self.wmclass_btn.connect("clicked", self._on_wmclass)
        self.wmclass_row.add_suffix(self.wmclass_btn)

        #Assign steamGridDB Icon
        self.griddb_row = Adw.ActionRow(title="Shortcut Icon", subtitle="Download and select shortcut icon via steamGridDB.")
        self.griddb_btn = Gtk.Button(label="Download")
        self.griddb_btn.set_valign(Gtk.Align.CENTER)
        self.griddb_btn.set_sensitive(False)
        self.griddb_row.add_suffix(self.griddb_btn)
        self.griddb_btn.connect("clicked", self._on_griddb)

        quick_actions.add(self.griddb_row)
        quick_actions.add(self.wmclass_row)
        quick_actions.add(self.nodisplay_row)

        return quick_actions

    def _build_editor_text(self) -> Adw.PreferencesGroup:
        editor_text = Adw.PreferencesGroup(title="Shortcut Contents")

        scrolled = Gtk.ScrolledWindow(
            hexpand=True,
            vexpand=True,
            min_content_height=270,
            min_content_width=350,
        )
        scrolled.add_css_class("card")
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.textview = Gtk.TextView(
            monospace=True,
            wrap_mode=Gtk.WrapMode.NONE,
            left_margin=12,
            right_margin=12,
            top_margin=12,
            bottom_margin=12,
        )
        self.text_buffer = self.textview.get_buffer()

        scrolled.set_child(self.textview)
        editor_text.add(scrolled)

        return editor_text

    def _build_editor_io_actions(self) -> Gtk.Box:
        save_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        save_bar.set_margin_top(12)
        save_bar.set_margin_bottom(6)

        self.save_btn = Gtk.Button(label="Save Changes")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._on_save)

        save_bar.append(Gtk.Box(hexpand=True))
        save_bar.append(self.save_btn)
        save_bar.append(Gtk.Box(hexpand=True))

        return save_bar

    def _adjust_window_size(self) -> None:
        max_line_length = getattr(self, "MAX_LINE_LENGTH", 0)
        # print(f"[DEBUG] _adjust_window_size running -> max_line_length: {max_line_length}")

        sidebar_width = self.sidebar.get_width()
        # print(f"[DEBUG] _adjust_window_size running -> sidebar_width: {sidebar_width}")

        monospace_width = 9
        monospace_padding = 69
        target_width = max_line_length * monospace_width
        calculated_width = target_width + sidebar_width + monospace_padding
        # print(f"[DEBUG] _adjust_window_size running -> target_width: {target_width}")
        self.set_default_size(calculated_width,726)

        return GLib.SOURCE_REMOVE

    def _notify_menu(self, desktop_path: str) -> None:
        try:
            os.utime(desktop_path, None)

            parent_dir = os.path.dirname(desktop_path)
            if os.path.exists(parent_dir):
                os.utime(parent_dir, None)

            logger.info("Trigger Gnome Shell refresh for %s", desktop_path)
        except OSError as Error:
            logger.warning("Could not update timestamp: %s", Error)

    def _on_game_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None or not hasattr(row, "full_path"):
            return
        self._load_editor(row.full_path)

    def _load_editor(self, full_path: str) -> None:
        try:
            handler = DesktopFileHandler(full_path)
            self.current_desktop_file = handler

            self._update_ui = True
            self.text_buffer.set_text(handler.raw_content)

            if hasattr(self, "nodisplay_row"):
                has_app_id = handler.get_steam_app_id() is not None
                self.nodisplay_row.set_active(handler.get_nodisplay())
                self.nodisplay_row.set_sensitive(has_app_id)

            if hasattr(self, "griddb_btn"):
                has_app_id = handler.get_steam_app_id() is not None
                self.griddb_btn.set_sensitive(has_app_id)

            if hasattr(self, "wmclass_btn"):
                has_app_id = handler.get_steam_app_id() is not None
                self.wmclass_btn.set_sensitive(has_app_id)

            self._update_ui = False
        except OSError as Error:
            logger.error("Failed to read file %s: %s", full_path, Error)

    def _clear_editor(self) -> None:
        self.current_desktop_file = None

        self._update_ui = True
        self.text_buffer.set_text("")

        if hasattr(self, "nodisplay_row"):
            self.nodisplay_row.set_active(False)

        self.update_ui= False

    def _on_blacklist(self, _button: Gtk.Button, filename: str) -> None:
        clean_name = filename.removesuffix(".desktop")

        if self.ConfigManager.add_user_ignored_shortcut(clean_name):
            self._populate_sidebar()

    def _on_delete(self, _button: Gtk.Button, full_path: str, row: Gtk.ListBoxRow, game_name: str) -> None:
        dialog = Adw.AlertDialog(heading=f"Delete '{game_name}'?", body=f"This will move the shortcut to trash:\n\n'{full_path}'",)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")

        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        dialog.choose(self, None, self._on_delete_confirm, full_path, row)

    def _on_delete_confirm(self, dialog: Adw.AlertDialog, result: Gio.AsyncResult, full_path: str, row: Gtk.ListBoxRow) -> None:
        response = dialog.choose_finish(result)

        if response == "delete":
            try:
                if (self.current_desktop_file and self.current_desktop_file.file_path == full_path):
                    handler = self.current_desktop_file
                else:
                    handler = DesktopFileHandler(full_path)

                handler.delete()

                self._notify_gnome_menu_update(full_path)

                self.list_box.remove(row)

                if (self.current_desktop_file and self.current_desktop_file.file_path == full_path):
                    self._clear_editor()
            except (GLib.Error, OSError) as Error:
                logger.error("Failed to delete %s: %s", full_path, Error)

    def _on_nodisplay(self, switch_row: Adw.SwitchRow, _param: GLib.ParamSpec) -> None:
        if self._update_ui or not self.current_desktop_file:
            return

        is_active = switch_row.get_active()
        self.current_desktop_file.set_nodisplay(is_active)

        self._update_ui = True
        self.text_buffer.set_text(self.current_desktop_file.to_string())
        self._update_ui = False

    def _on_wmclass(self, _button: Gtk.Button) -> None:
        if not self.current_desktop_file:
            return

        steam_app_id = self.current_desktop_file.get_steam_app_id()

        def _window_selected(selected_wmclass: str) -> None:
            if self.current_desktop_file is None:
                return

            self.current_desktop_file.set_wmclass(selected_wmclass)
            self._update_ui = True
            self.text_buffer.set_text(self.current_desktop_file.to_string())
            self._update_ui = False

        dialog = WMClassSelectorWindow(self, steam_app_id, _window_selected)
        dialog.present()

    def _on_griddb(self, _button: Gtk.Button) -> None:
        if not self.current_desktop_file:
            return

        steam_app_id = self.current_desktop_file.get_steam_app_id()
        if not steam_app_id:
            return

        game_name = self.current_desktop_file.parser.get(
            self.current_desktop_file.DESKTOP_ENTRY, "Name", fallback="Unknown Game"
        )

        def _icon_selected(icon_path: str) -> None:
            if self.current_desktop_file is None:
                    return

            self.current_desktop_file.set_icon(icon_path)
            self._update_ui = True
            self.text_buffer.set_text(self.current_desktop_file.to_string())
            self._update_ui = False

        dialog = SteamGridDBSelectorWindow(self, game_name, steam_app_id, _icon_selected)
        dialog.present()

    def _on_save(self, _button: Gtk.Button) -> None:
        if not self.current_desktop_file:
            return

        start_iter = self.text_buffer.get_start_iter()
        end_iter = self.text_buffer.get_end_iter()

        buffer_text = self.text_buffer.get_text(start_iter, end_iter, include_hidden_chars=False)

        try:
            self.current_desktop_file.save(buffer_text)
            logger.info("Save changes to %s", self.current_desktop_file.file_path)

            self._notify_menu(self.current_desktop_file.file_path)

            selected_row = self.list_box.get_selected_row()
            if selected_row and hasattr(selected_row, "hidden_icon"):
                selected_row.hidden_icon.set_visible(self.current_desktop_file.get_nodisplay())

            if selected_row and hasattr(selected_row, "icon_widget"):
                new_icon = self.current_desktop_file.get_icon()
                if new_icon.startswith("/"):
                    selected_row.icon_widget.set_from_file(new_icon)
                else:
                    icon_name = new_icon if new_icon else "application-x-executable"
                    selected_row.icon_widget.set_from_icon_name(icon_name)
                selected_row.icon_widget.set_pixel_size(32)

        except OSError as Error:
            logger.error("Failed to write to %s: %s", self.current_desktop_file, Error,)

    def _on_open_preferences(self, _button: Gtk.Button) -> None:
        dialog = PreferencesWindow(self, on_settings_changed=self._populate_sidebar)
        dialog.present()

class SteamIronApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="com.github.steam_iron",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        setup_icon_paths()

    def do_activate(self) -> None:
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()

def main() -> None:
    app = SteamIronApplication()
    sys.exit(app.run(sys.argv))

def setup_icon_paths():
    display = Gdk.Display.get_default()
    if display:
        icon_theme = Gtk.IconTheme.get_for_display(display)
        system_paths = [
            "/usr/share/icons",
            "/usr/local/share/icons",
            os.path.expanduser("~/.local/share.icons"),
            os.path.expanduser("~/.icons"),
        ]
        for path in system_paths:
            if os.path.exists(path):
                icon_theme.add_search_path(path)

if __name__ == "__main__":
    main()
