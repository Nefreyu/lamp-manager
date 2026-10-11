import gi
import logging
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib
from pathlib import Path

log = logging.getLogger(__name__)

from services.nginx import NGINX_ERROR_LOG, NGINX_ACCESS_LOG
from pages.log_viewer import LogViewer

NGINX_CONF = "/etc/nginx/nginx.conf"


class NginxConfigPage(Gtk.Box):
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

        self.append(self._file_row("Configuración principal", NGINX_CONF, "document-edit-symbolic"))
        self.append(Gtk.Separator())

        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        self.append(notebook)

        error_log = LogViewer(NGINX_ERROR_LOG)
        error_log.set_margin_top(12)
        notebook.append_page(error_log, Gtk.Label(label="Log de errores"))

        access_log = LogViewer(NGINX_ACCESS_LOG)
        access_log.set_margin_top(12)
        notebook.append_page(access_log, Gtk.Label(label="Log de accesos"))

    def _file_row(self, label: str, path: str, icon: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        name_label = Gtk.Label(label=label)
        name_label.set_xalign(0)
        name_label.set_hexpand(True)
        row.append(name_label)

        path_label = Gtk.Label()
        path_label.set_markup(f"<span color='gray' size='small'>{GLib.markup_escape_text(path)}</span>")
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
            except Exception as e:
                log.warning("No se pudo abrir el archivo %s: %s", path, e)
