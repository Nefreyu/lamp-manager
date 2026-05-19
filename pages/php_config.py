import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib
from pathlib import Path

from services.php import (
    get_installed_version,
    list_available_extensions, list_enabled_extensions,
    enable_extension, disable_extension,
    get_ini_value, set_ini_values, INI_PARAMS,
)
from pages.log_viewer import LogViewer


class ExtensionRow(Gtk.ListBoxRow):
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


class PhpConfigPage(Gtk.Box):
    def __init__(self, service: dict, navigate_to):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        self.php_ver = get_installed_version() or "8.5"

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

        php_ini = f"/etc/php/{self.php_ver}/fpm/php.ini"
        pool_conf = f"/etc/php/{self.php_ver}/fpm/pool.d/www.conf"

        self.append(self._file_row("php.ini (FPM)", php_ini, "document-edit-symbolic"))
        self.append(self._file_row("Configuración de pools", pool_conf, "document-edit-symbolic"))

        self.append(Gtk.Separator())

        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        self.append(notebook)

        # Pestaña php.ini
        ini_page = self._build_ini_section()
        ini_page.set_margin_top(12)
        ini_page.set_margin_bottom(12)
        notebook.append_page(ini_page, Gtk.Label(label="php.ini"))

        # Pestaña Extensiones
        ext_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ext_box.set_margin_top(12)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Buscar extensión...")
        self.search_entry.connect("search-changed", self._on_search_changed)
        ext_box.append(self.search_entry)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_filter_func(self._filter_func)
        scrolled.set_child(self.listbox)
        ext_box.append(scrolled)

        notebook.append_page(ext_box, Gtk.Label(label="Extensiones"))

        # Pestaña Logs
        log_page = LogViewer(f"/var/log/php{self.php_ver}-fpm.log")
        log_page.set_margin_top(12)
        notebook.append_page(log_page, Gtk.Label(label="Logs"))

        self._load_extensions()

    def _build_ini_section(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        title = Gtk.Label()
        title.set_markup("<span weight='bold'>Parámetros principales</span>")
        title.set_xalign(0)
        box.append(title)

        self._ini_fields = {}

        for param in INI_PARAMS:
            key = param["key"]
            current = get_ini_value(self.php_ver, key) or ""

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

            label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            label_box.set_hexpand(True)

            name_label = Gtk.Label(label=param["label"])
            name_label.set_xalign(0)
            label_box.append(name_label)

            if "hint" in param:
                hint_label = Gtk.Label()
                hint_label.set_markup(f"<span size='small' color='gray'>{param['hint']}</span>")
                hint_label.set_xalign(0)
                label_box.append(hint_label)

            row.append(label_box)

            if param.get("type") == "bool":
                widget = Gtk.Switch()
                widget.set_valign(Gtk.Align.CENTER)
                widget.set_active(current.lower() in ("on", "1", "true"))
            else:
                widget = Gtk.Entry()
                widget.set_text(current)
                widget.set_width_chars(16)
                widget.set_halign(Gtk.Align.END)

            self._ini_fields[key] = widget
            row.append(widget)
            box.append(row)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row.set_margin_top(4)

        self._ini_status = Gtk.Label(label="")
        self._ini_status.set_hexpand(True)
        self._ini_status.set_xalign(0)
        action_row.append(self._ini_status)

        self._save_btn = Gtk.Button(label="Guardar")
        self._save_btn.add_css_class("suggested-action")
        self._save_btn.connect("clicked", self._on_save_ini)
        action_row.append(self._save_btn)

        box.append(action_row)
        return box

    def _on_save_ini(self, button):
        values = {}
        for key, widget in self._ini_fields.items():
            if isinstance(widget, Gtk.Switch):
                values[key] = "On" if widget.get_active() else "Off"
            else:
                values[key] = widget.get_text().strip()

        self._save_btn.set_sensitive(False)
        self._save_btn.set_label("Guardando…")

        ok = set_ini_values(self.php_ver, values)

        if ok:
            self._ini_status.set_markup("<span color='green'>Guardado y PHP-FPM recargado.</span>")
        else:
            self._ini_status.set_markup("<span color='red'>Error al guardar.</span>")

        self._save_btn.set_sensitive(True)
        self._save_btn.set_label("Guardar")
        GLib.timeout_add_seconds(5, lambda: self._ini_status.set_markup("") or False)

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

    def _load_extensions(self):
        while child := self.listbox.get_first_child():
            self.listbox.remove(child)

        available = list_available_extensions(self.php_ver)
        enabled = list_enabled_extensions(self.php_ver)
        sorted_exts = sorted(available, key=lambda e: (0 if e in enabled else 1, e))

        for name in sorted_exts:
            row = ExtensionRow(name, name in enabled, self._on_extension_toggled)
            self.listbox.append(row)

    def _on_extension_toggled(self, name: str, state: bool) -> bool:
        if state:
            enable_extension(self.php_ver, name)
        else:
            disable_extension(self.php_ver, name)
        GLib.timeout_add(500, self._load_extensions)
        return False

    def _filter_func(self, row) -> bool:
        text = self.search_entry.get_text().lower()
        if not text:
            return True
        return text in row.name.lower()

    def _on_search_changed(self, _):
        self.listbox.invalidate_filter()
