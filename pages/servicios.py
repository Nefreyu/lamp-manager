import gi
import logging
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gio, GLib, Gdk
from pathlib import Path

log = logging.getLogger(__name__)
from services.systemd import (
    SERVICES, get_status, is_installed,
    start_service, stop_service, reload_service, restart_service,
    install_mailpit_service, uninstall_mailpit_service,
    get_service_ports,
)
from services.apache import get_version as get_apache_version
from services.mysql import get_version as get_mysql_version
from services.php import get_version as get_php_version
from services.recommendations import get_missing as get_missing_recommendations
from config import settings
from services.vhosts import APACHE_SITES_ENABLED

_fpm_service = next((s for s in SERVICES if s["id"].endswith("-fpm")), None)
_VERSION_FNS = {
    "apache2": get_apache_version,
    "mysql": get_mysql_version,
}
if _fpm_service:
    _VERSION_FNS[_fpm_service["id"]] = get_php_version


class RecommendationsPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_bottom(4)
        self.refresh()

    def refresh(self):
        child = self.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.remove(child)
            child = next_child

        missing = get_missing_recommendations()
        self.set_visible(bool(missing))
        if not missing:
            return

        header = Gtk.Label()
        header.set_markup("<b>Servicios recomendados no instalados</b>")
        header.set_xalign(0)
        header.set_margin_bottom(6)
        self.append(header)

        for i, rec in enumerate(missing):
            if i > 0:
                self.append(Gtk.Separator())
            self.append(self._build_row(rec))

        self.append(Gtk.Separator())

    def _build_row(self, rec: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_top(6)
        row.set_margin_bottom(6)

        icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        icon.set_valign(Gtk.Align.START)
        icon.set_margin_top(2)
        row.append(icon)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content.set_hexpand(True)

        name = Gtk.Label()
        name.set_markup(f"<b>{rec['label']}</b>")
        name.set_xalign(0)
        content.append(name)

        desc = Gtk.Label(label=rec["description"])
        desc.set_xalign(0)
        desc.set_wrap(True)
        desc.add_css_class("dim-label")
        content.append(desc)

        for opt in rec["commands"]:
            cmd_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            cmd_row.set_margin_top(4)

            cmd_label = Gtk.Label()
            cmd_label.set_markup(f"<tt>{opt['cmd']}</tt>")
            cmd_label.set_xalign(0)
            cmd_label.set_hexpand(True)
            cmd_row.append(cmd_label)

            copy_btn = Gtk.Button(label="Copiar")
            copy_btn.set_valign(Gtk.Align.CENTER)
            copy_btn.set_tooltip_text(f"Copiar comando de {opt['label']}")
            cmd = opt["cmd"]
            copy_btn.connect("clicked", lambda _, c=cmd: self.get_clipboard().set(c))
            cmd_row.append(copy_btn)

            content.append(cmd_row)

        row.append(content)
        return row


class ServiceRow(Gtk.Box):
    def __init__(self, service: dict, navigate_to, on_changed=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.add_css_class("item-row")
        self.service = service
        self.service_id = service["id"]
        self.optional = service.get("optional", False)
        self.web_only = service.get("web_only", False)
        self.on_changed = on_changed
        self._updating = False

        # Nombre como botón de navegación
        label_text = service["label"]
        version_fn = _VERSION_FNS.get(self.service_id)
        if version_fn and is_installed(service):
            version = version_fn()
            if version:
                label_text += f" {version}"
        name_btn = Gtk.Button(label=label_text)
        name_btn.add_css_class("flat")
        name_btn.set_hexpand(True)
        name_btn.get_child().set_xalign(0)
        name_btn.connect("clicked", lambda _: navigate_to(f"service-{self.service_id}"))
        self.append(name_btn)

        # Indicador de estado
        self.status_label = Gtk.Label()
        self.append(self.status_label)

        self.ports_label = Gtk.Label()
        self.ports_label.add_css_class("dim-label")
        self.append(self.ports_label)

        # Botón instalar/desinstalar (solo servicios opcionales)
        if self.optional:
            self.install_button = Gtk.Button()
            self.install_button.connect("clicked", self.on_install_clicked)
            self.append(self.install_button)

        # Botón abrir en navegador
        self.url = service.get("url")
        if self.url:
            self.link_button = Gtk.Button()
            self.link_button.set_icon_name("web-browser-symbolic")
            self.link_button.set_tooltip_text(self.url)
            self.link_button.set_valign(Gtk.Align.CENTER)
            self.link_button.connect("clicked", self.on_open_url)
            self.append(self.link_button)

        # Botón recargar (solo servicios con reloadable=True)
        if service.get("reloadable"):
            self.reload_button = Gtk.Button()
            self.reload_button.set_icon_name("view-refresh-symbolic")
            self.reload_button.set_tooltip_text("Recargar configuración")
            self.reload_button.set_valign(Gtk.Align.CENTER)
            self.reload_button.connect("clicked", self.on_reload_clicked)
            self.append(self.reload_button)

        # Botón reiniciar (solo servicios con restartable=True)
        if service.get("restartable"):
            self.restart_button = Gtk.Button()
            self.restart_button.set_icon_name("system-reboot-symbolic")
            self.restart_button.set_tooltip_text("Reiniciar servicio")
            self.restart_button.set_valign(Gtk.Align.CENTER)
            self.restart_button.connect("clicked", self.on_restart_clicked)
            self.append(self.restart_button)

        # Switch arrancar/parar (no aplica a servicios web_only)
        if not self.web_only:
            self.switch = Gtk.Switch()
            self.switch.set_valign(Gtk.Align.CENTER)
            self.switch.connect("state-set", self.on_switch_toggled)
            self.append(self.switch)

        self.refresh()

    def on_open_url(self, button):
        Gio.AppInfo.launch_default_for_uri(self.url, None)

    def on_reload_clicked(self, button):
        self.status_label.set_markup("<span color='gray'>Reiniciando...</span>")
        self.set_sensitive(False)
        GLib.timeout_add(50, self._do_reload)

    def _do_reload(self):
        if self.service_id == "apache2":
            from services.apache import configtest
            ok, msg = configtest()
            if not ok:
                self.status_label.set_markup(f"<span color='red' size='small'>Error de configuración: {GLib.markup_escape_text(msg)}</span>")
                self.set_sensitive(True)
                return False
        reload_service(self.service_id)
        self.set_sensitive(True)
        self.refresh()
        return False

    def on_restart_clicked(self, button):
        self.status_label.set_markup("<span color='gray'>Reiniciando...</span>")
        self.set_sensitive(False)
        GLib.timeout_add(50, self._do_restart)

    def _do_restart(self):
        restart_service(self.service_id)
        self.set_sensitive(True)
        self.refresh()
        return False

    def refresh(self):
        self._updating = True

        binary = self.service.get("binary")
        if binary:
            self.set_visible(Path(binary).exists())
            if not self.get_visible():
                self._updating = False
                return

        if not is_installed(self.service):
            self.status_label.set_markup("<span color='orange'>⚠ no instalado</span>")
            if not self.web_only:
                self.switch.set_active(False)
                self.switch.set_sensitive(False)
            if self.url:
                self.link_button.set_sensitive(False)
            if self.optional:
                self.install_button.set_label("Instalar servicio")
            if self.service.get("reloadable"):
                self.reload_button.set_sensitive(False)
            if self.service.get("restartable"):
                self.restart_button.set_sensitive(False)
        else:
            self.status_label.set_markup("")
            if self.web_only:
                if self.url:
                    self.link_button.set_sensitive(True)
            else:
                active = get_status(self.service_id)
                self.switch.set_active(active)
                self.switch.set_sensitive(True)
                if self.url:
                    if self.service_id == "apache2":
                        ssl_enabled = (APACHE_SITES_ENABLED / "000-localhost-ssl.conf").exists()
                        self.url = "https://localhost" if ssl_enabled else "http://localhost"
                        self.link_button.set_tooltip_text(self.url)
                    self.link_button.set_sensitive(active)
                if self.service.get("reloadable"):
                    self.reload_button.set_sensitive(active)
                if self.service.get("restartable"):
                    self.restart_button.set_sensitive(active)
            if self.optional:
                self.install_button.set_label("Desinstalar servicio")

        if self.optional:
            binary = self.service.get("binary")
            self.install_button.set_visible(Path(binary).exists() if binary else True)

        process = self.service.get("process")
        if process and is_installed(self.service):
            ports = get_service_ports(process)
            self.ports_label.set_text(" · ".join(f":{p}" for p in ports))
        else:
            self.ports_label.set_text("")

        self._updating = False

    def on_switch_toggled(self, switch, state):
        if self._updating:
            return False
        if state:
            result = start_service(self.service_id)
        else:
            result = stop_service(self.service_id)
        log.info("Operación en %s: %s", self.service_id, result)
        def after_toggle():
            self.refresh()
            if self.on_changed:
                self.on_changed()
        GLib.timeout_add(500, after_toggle)
        return False

    def on_install_clicked(self, button):
        if is_installed(self.service):
            uninstall_mailpit_service()
        else:
            storage_enabled = settings.get("mailpit", "storage_enabled") == "true"
            storage_path = settings.get("mailpit", "storage_path")
            install_mailpit_service(storage_enabled, storage_path)
        GLib.timeout_add(500, self.refresh)


class ServiciosPage(Gtk.Box):
    def __init__(self, navigate_to):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        css = Gtk.CssProvider()
        css.load_from_data(b".item-row { border-radius:6px; padding-top:6px; padding-bottom:6px; padding-right:8px; } .item-row:hover { background-color: alpha(@window_fg_color, 0.08); } .item-row button.flat:hover { background-color: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Servicios</span>")
        title.set_xalign(0)
        self.append(title)
        self.append(Gtk.Separator())

        self.recommendations_panel = RecommendationsPanel()
        self.append(self.recommendations_panel)

        # Banner de aviso Apache+PHP-FPM
        self.fpm_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.fpm_banner.set_margin_bottom(4)

        banner_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        self.fpm_banner.append(banner_icon)

        banner_label = Gtk.Label(label="Apache está activo pero PHP-FPM no. Los proyectos PHP no funcionarán.")
        banner_label.set_hexpand(True)
        banner_label.set_xalign(0)
        self.fpm_banner.append(banner_label)

        fix_btn = Gtk.Button(label="Arrancar PHP-FPM")
        fix_btn.add_css_class("suggested-action")
        fix_btn.connect("clicked", self.on_start_fpm)
        self.fpm_banner.append(fix_btn)

        self.fpm_banner.set_visible(False)
        self.append(self.fpm_banner)

        self.rows = []
        for service in SERVICES:
            row = ServiceRow(service, navigate_to, on_changed=self._check_fpm_warning)
            self.append(row)
            self.rows.append(row)

        refresh_btn = Gtk.Button(label="Refrescar")
        refresh_btn.connect("clicked", self.on_refresh)
        refresh_btn.set_halign(Gtk.Align.START)
        self.append(refresh_btn)

        self._check_fpm_warning()
        GLib.timeout_add_seconds(30, self._auto_refresh)

    def _check_fpm_warning(self):
        apache = next((s for s in SERVICES if s["id"] == "apache2"), None)
        fpm = next((s for s in SERVICES if s["id"].endswith("-fpm")), None)
        if apache and fpm and is_installed(apache) and is_installed(fpm):
            show = get_status("apache2") and not get_status(fpm["id"])
            self.fpm_banner.set_visible(show)

    def on_start_fpm(self, button):
        fpm = next((s for s in SERVICES if s["id"].endswith("-fpm")), None)
        if fpm:
            start_service(fpm["id"])
        GLib.timeout_add(500, self._after_start_fpm)

    def _after_start_fpm(self):
        self._check_fpm_warning()
        for row in self.rows:
            row.refresh()

    def _auto_refresh(self):
        if self.get_mapped():
            self.on_refresh(None)
        return True

    def on_refresh(self, button):
        self.recommendations_panel.refresh()
        for row in self.rows:
            row.refresh()
        self._check_fpm_warning()


class ServiceConfigPage(Gtk.Box):
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

        placeholder = Gtk.Label(
            label=f"Sección para la configuración del servicio de {service['label']}"
        )
        placeholder.set_xalign(0)
        self.append(placeholder)
