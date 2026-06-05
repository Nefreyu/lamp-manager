import gi
import logging
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio
from pathlib import Path

log = logging.getLogger(__name__)


from services.systemd import _PHP_VERSIONS

PHPMYADMIN_CONF = "/etc/phpmyadmin/config.inc.php"
PHPMYADMIN_APACHE_CONF = "/etc/apache2/conf-available/phpmyadmin.conf"


def _detect_fpm_conf() -> str:
    for ver in _PHP_VERSIONS:
        path = f"/etc/phpmyadmin/php{ver}-fpm.conf"
        if Path(path).exists():
            return path
    return f"/etc/phpmyadmin/php{_PHP_VERSIONS[0]}-fpm.conf"


PHPMYADMIN_FPM_CONF = _detect_fpm_conf()


class PhpMyAdminConfigPage(Gtk.Box):
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

        url = service.get("url", "http://localhost/phpmyadmin")
        url_label = Gtk.Label()
        url_label.set_markup(f"<span color='gray' size='small'>{url}</span>")
        url_label.set_xalign(0)
        self.append(url_label)

        self.append(Gtk.Separator())

        self.append(self._file_row("Configuración principal", PHPMYADMIN_CONF, "document-edit-symbolic"))
        self.append(self._file_row("Integración con Apache", PHPMYADMIN_APACHE_CONF, "document-edit-symbolic"))
        self.append(self._file_row("Integración con PHP-FPM", PHPMYADMIN_FPM_CONF, "document-edit-symbolic"))

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
            except Exception as e:
                log.warning("No se pudo abrir el archivo %s: %s", path, e)
