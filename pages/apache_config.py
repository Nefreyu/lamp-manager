import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib
from pathlib import Path

from services.apache import (
    list_available_modules, list_enabled_modules,
    enable_module, disable_module
)
from pages.log_viewer import LogViewer

APACHE_CONF = "/etc/apache2/apache2.conf"
APACHE_ERROR_LOG = "/var/log/apache2/error.log"
APACHE_ACCESS_LOG = "/var/log/apache2/access.log"


class ModuleRow(Gtk.ListBoxRow):
    def __init__(self, name: str, enabled: bool, on_toggled):
        super().__init__()
        self.name = name
        self._updating = False

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)

        label = Gtk.Label(label=name)
        label.set_hexpand(True)
        label.set_xalign(0)
        box.append(label)

        self.switch = Gtk.Switch()
        self.switch.set_valign(Gtk.Align.CENTER)
        self._updating = True
        self.switch.set_active(enabled)
        self._updating = False
        self.switch.connect("state-set", lambda _, state: on_toggled(name, state) if not self._updating else False)
        box.append(self.switch)

        self.set_child(box)


class ApacheConfigPage(Gtk.Box):
    def __init__(self, service: dict, navigate_to):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        back_btn = Gtk.Button(label="Servicios")
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.set_halign(Gtk.Align.START)
        back_btn.connect("clicked", lambda _: navigate_to("servicios"))
        self.append(back_btn)

        title = Gtk.Label()
        title.set_markup(f"<span size='x-large' weight='bold'>{service['label']}</span>")
        title.set_xalign(0)
        self.append(title)
        self.append(Gtk.Separator())

        self.append(self._file_row("Configuración principal", APACHE_CONF, "document-edit-symbolic"))

        self.append(Gtk.Separator())

        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        self.append(notebook)

        # Pestaña Módulos
        modules_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        modules_box.set_margin_top(12)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Buscar módulo...")
        self.search_entry.connect("search-changed", self._on_search_changed)
        modules_box.append(self.search_entry)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_filter_func(self._filter_func)
        scrolled.set_child(self.listbox)
        modules_box.append(scrolled)

        notebook.append_page(modules_box, Gtk.Label(label="Módulos"))

        # Pestaña Log de errores
        error_log = LogViewer(APACHE_ERROR_LOG)
        error_log.set_margin_top(12)
        notebook.append_page(error_log, Gtk.Label(label="Log de errores"))

        # Pestaña Log de accesos
        access_log = LogViewer(APACHE_ACCESS_LOG)
        access_log.set_margin_top(12)
        notebook.append_page(access_log, Gtk.Label(label="Log de accesos"))

        self._load_modules()

    def _file_row(self, label: str, path: str, icon: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        name_label = Gtk.Label(label=label)
        name_label.set_xalign(0)
        name_label.set_hexpand(True)
        row.append(name_label)

        path_label = Gtk.Label()
        path_label.set_markup(f"<span color='gray' size='small'>{path}</span>")
        row.append(path_label)

        btn = Gtk.Button()
        btn.set_icon_name(icon)
        btn.set_tooltip_text(path)
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_sensitive(Path(path).exists())
        btn.connect("clicked", lambda _, p=path: self._open_file(p))
        row.append(btn)

        return row

    def _open_file(self, path: str):
        try:
            Gio.AppInfo.launch_default_for_uri(f"admin://{path}", None)
        except Exception:
            try:
                Gio.AppInfo.launch_default_for_uri(f"file://{path}", None)
            except Exception:
                pass

    def _load_modules(self):
        while child := self.listbox.get_first_child():
            self.listbox.remove(child)

        available = list_available_modules()
        enabled = list_enabled_modules()
        sorted_modules = sorted(available, key=lambda m: (0 if m in enabled else 1, m))

        for name in sorted_modules:
            row = ModuleRow(name, name in enabled, self._on_module_toggled)
            self.listbox.append(row)

    def _on_module_toggled(self, name: str, state: bool) -> bool:
        if state:
            enable_module(name)
        else:
            disable_module(name)
        GLib.timeout_add(500, self._load_modules)
        return False

    def _filter_func(self, row) -> bool:
        text = self.search_entry.get_text().lower()
        if not text:
            return True
        return text in row.name.lower()

    def _on_search_changed(self, _):
        self.listbox.invalidate_filter()
