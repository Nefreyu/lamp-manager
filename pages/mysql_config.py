import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio
from pathlib import Path

from services.mysql import get_conf_path, MYSQL_ERROR_LOG, MYSQL_SLOW_LOG
from pages.log_viewer import LogViewer


class MysqlConfigPage(Gtk.Box):
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

        self.append(self._file_row("Configuración principal", get_conf_path(), "document-edit-symbolic"))
        self.append(Gtk.Separator())

        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        self.append(notebook)

        error_log = LogViewer(MYSQL_ERROR_LOG)
        error_log.set_margin_top(12)
        notebook.append_page(error_log, Gtk.Label(label="Log de errores"))

        slow_log = LogViewer(MYSQL_SLOW_LOG)
        slow_log.set_margin_top(12)
        notebook.append_page(slow_log, Gtk.Label(label="Log de consultas lentas"))

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
