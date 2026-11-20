# preferencesWindow.py
# pyright: reportAttributeAccessIssue=false
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from configManager import ConfigManager


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(
        self,
        parent_window: Gtk.Window,
        on_settings_changed,
    ):
        super().__init__(transient_for=parent_window, modal=True)

        self.helper = ConfigManager()
        self.keyring_timeout = 0
        self.on_settings_changed = on_settings_changed

        self.set_title("Preferences")
        self.set_default_size(550, 600)

        self._build_ui()
        self.connect("close-request", self._on_close_request)

    def _build_ui(self) -> None:
        root_box = Adw.PreferencesPage()
        self.add(root_box)

        api_key_group = Adw.PreferencesGroup(
            title="StreamGridDB API Key",
            description="Set your API Key for fetching icons."
        )
        self.api_key = Adw.PasswordEntryRow(title="API Key")
        self.api_key.set_text(self.helper.get_api_key())

        save_btn = Gtk.Button.new_from_icon_name("object-select-symbolic")
        save_btn.add_css_class("flat")
        save_btn.set_valign(Gtk.Align.CENTER)
        save_btn.set_tooltip_text("Save")
        save_btn.connect("clicked", lambda _: self._on_api_key_save(self.api_key.get_text()))

        self.api_key.add_suffix(save_btn)

        self.api_key.connect("apply", self._on_api_key_apply)
        self.api_key.connect("entry-activated", self._on_api_key_apply)
        api_key_group.add(self.api_key)
        root_box.add(api_key_group)

        ignored_shortcut_group = Adw.PreferencesGroup(
            title="Ignored Shortcuts",
            description=".desktop files ignored during shortcut scan."
        )
        self._setup_editable_list(
            ignored_shortcut_group,
            defaults=self.helper.get_default_ignored_shortcuts(),
            user_list=self.helper.get_user_ignored_shortcuts(),
            on_add=self._on_add_shortcut,
            on_remove=self._on_remove_shortcut
        )
        root_box.add(ignored_shortcut_group)

        ignored_process_group = Adw.PreferencesGroup(
            title="Ignored Processes",
            description="Processes ignored during StartupWMClass scan."
        )
        self._setup_editable_list(
            ignored_process_group,
            defaults=self.helper.get_default_ignored_processes(),
            user_list=self.helper.get_user_ignored_processes(),
            on_add=self._on_add_process,
            on_remove=self._on_remove_process
        )
        root_box.add(ignored_process_group)

    def _setup_editable_list(
        self,
        group,
        defaults,
        user_list,
        on_add,
        on_remove
    ) -> None:
        add_row = Adw.EntryRow(title="Add Entry")

        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_btn.add_css_class("flat")
        add_btn.set_valign(Gtk.Align.CENTER)
        add_btn.set_tooltip_text("Add Entry")
        add_row.add_suffix(add_btn)

        list_box = Gtk.ListBox()
        list_box.add_css_class("boxed-list")
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.set_margin_top(12)
        list_box.set_margin_bottom(6)

        add_btn.connect("clicked", lambda _: on_add(add_row, list_box, on_remove))
        add_row.connect("entry-activated", lambda _: on_add(add_row, list_box, on_remove))

        group.add(add_row)
        group.add(list_box)

        for item in sorted(user_list):
            self._add_row(list_box, item, is_default=False, on_remove_callback=on_remove)

        if defaults:
            expander_row = Adw.ExpanderRow(
                title="Default Rules",
                subtitle=f"{len(defaults)} protected default entries"
            )
            expander_row.add_prefix(Gtk.Image.new_from_icon_name("changes-prevent-symbolic"))
            expander_row.add_css_class("dim-label")

            for item in sorted(defaults):
                sub_row = Adw.ActionRow(title=item)
                sub_row.add_css_class("dim-label")

                lock_icon = Gtk.Image.new_from_icon_name("changes-prevent-symbolic")
                lock_icon.add_css_class("dim-label")
                lock_icon.set_tooltip_text("Default app rule (Protected)")
                lock_icon.set_valign(Gtk.Align.CENTER)
                sub_row.add_suffix(lock_icon)

                expander_row.add_row(sub_row)

            list_box.append(expander_row)

    def _add_row(self, list_box: Gtk.ListBox, text: str, is_default: bool, on_remove_callback) -> None:
        row = Adw.ActionRow(title=text)

        if is_default:
            lock_icon = Gtk.Image.new_from_icon_name("changes-prevent-symbolic")
            lock_icon.add_css_class("dim-label")
            lock_icon.set_tooltip_text("Default Entry (Protected)")
            lock_icon.set_valign(Gtk.Align.CENTER)
            row.add_suffix(lock_icon)
            row.add_css_class("dim-label")
            row.is_default = True

            list_box.append(row)
        else:
            del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            del_btn.add_css_class("flat")
            del_btn.add_css_class("destructive-action")
            del_btn.set_valign(Gtk.Align.CENTER)
            del_btn.set_tooltip_text("Delete Entry")
            del_btn.connect("clicked", lambda _: on_remove_callback(row, list_box, text))
            row.add_suffix(del_btn)
            row.is_default = False

            if on_remove_callback:
                del_btn.connect("clicked", lambda _btn, callback=on_remove_callback, r=row, t=text: callback(r, list_box, t))

            default_index = -1
            index = 0
            while child := list_box.get_row_at_index(index):
                if isinstance(child, Adw.ExpanderRow):
                    default_index = index
                    break
                index += 1

            if default_index != -1:
                list_box.insert(row, default_index)
            else:
                list_box.append(row)

    def _on_api_key_apply(self, entry: Adw.PasswordEntryRow) -> None:
        self.save_api_key(entry.get_text())

    def _on_api_key_save(self, key_text: str) -> None:
        success = self.helper.set_api_key(key_text)
        if not success:
            self.api_key.add_css_class("error")
        else:
            self.api_key.remove_css_class("error")

    def _on_add_shortcut(self, entry: Gtk.Entry, list_box: Gtk.ListBox, on_remove_callback) -> None:
        text = entry.get_text().strip()
        if text and self.helper.add_user_ignored_shortcut(text):
            self._add_row(list_box, text, is_default=False, on_remove_callback=on_remove_callback)
            entry.set_text("")
            self._trigger_callback()

    def _on_remove_shortcut(self, row: Adw.ActionRow, list_box: Gtk.ListBox, text: str) -> None:
        if self.helper.remove_user_ignored_shortcut(text):
            list_box.remove(row)
            self._trigger_callback()

    def _on_add_process(self, entry: Gtk.Entry, list_box: Gtk.ListBox, on_remove_callback) -> None:
        text = entry.get_text().strip()
        if text and self.helper.add_user_ignored_process(text):
            self._add_row(list_box, text, is_default=False, on_remove_callback=on_remove_callback)
            entry.set_text("")

    def _on_remove_process(self, row: Adw.ActionRow, list_box: Gtk.ListBox, text: str) -> None:
        if self.helper.remove_user_ignored_process(text):
            list_box.remove(row)

    def _on_close_request(self, window) -> bool:
        self._on_api_key_save(self.api_key.get_text())
        return False

    def _trigger_callback(self) -> None:
        if callable(self.on_settings_changed):
            self.on_settings_changed()
